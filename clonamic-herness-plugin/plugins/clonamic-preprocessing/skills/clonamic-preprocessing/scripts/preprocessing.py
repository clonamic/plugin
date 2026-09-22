#!/usr/bin/env python3
"""Skill-local preprocessing and crash-safe queue operations."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("text must be a string")
    text = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    compact: list[str] = []
    for line in lines:
        if line or not compact or compact[-1]:
            compact.append(line)
    return "\n".join(compact).strip()


def clarification_contract(text: str, missing_fields: Iterable[str]) -> dict[str, Any]:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = normalize_text(text)
    fields: list[str] = []
    for raw in missing_fields:
        field = normalize_text(str(raw)).casefold().replace(" ", "_")
        if field and field not in fields:
            fields.append(field)
    if not normalized and "request" not in fields:
        fields.insert(0, "request")
    questions = [
        {
            "field": field,
            "question": f"Specify the required {field.replace('_', ' ')}.",
        }
        for field in fields
    ]
    return {
        "original_text": text,
        "normalized_text": normalized,
        "required": bool(questions),
        "ready_for_queue": bool(normalized) and not questions,
        "questions": questions,
    }


def queue_state(
    path: str | Path,
    *,
    lock_timeout: float = 2.0,
    lock_stale_after: float = 30.0,
) -> dict[str, Any]:
    with _queue_lock(path, timeout=lock_timeout, stale_after=lock_stale_after):
        return _read_state(path)


def enqueue(
    path: str | Path,
    text: str,
    *,
    priority: int = 100,
    item_id: str | None = None,
    lock_timeout: float = 2.0,
    lock_stale_after: float = 30.0,
) -> dict[str, Any]:
    if not isinstance(text, str):
        raise TypeError("queue text must be a string")
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("queue text must not be empty")
    resolved_id = normalize_text(item_id or uuid.uuid4().hex)
    if not resolved_id:
        raise ValueError("item id must not be empty")
    with _queue_lock(path, timeout=lock_timeout, stale_after=lock_stale_after):
        state = _read_state(path)
        if any(item.get("id") == resolved_id for item in state["items"]):
            raise ValueError(f"duplicate item id: {resolved_id}")
        item = {
            "id": resolved_id,
            "text": text,
            "normalized_text": normalized,
            "priority": int(priority),
            "sequence": state["next_sequence"],
            "state": "pending",
            "result": None,
            "attempts": 0,
        }
        state["next_sequence"] += 1
        state["items"].append(item)
        _write_state(path, state)
        return dict(item)


def claim_next(
    path: str | Path,
    *,
    worker_id: str,
    active_stale_after: float = 300.0,
    lock_timeout: float = 2.0,
    lock_stale_after: float = 30.0,
) -> dict[str, Any] | None:
    resolved_worker = normalize_text(worker_id)
    if not resolved_worker:
        raise ValueError("worker_id must not be empty")
    if active_stale_after < 0:
        raise ValueError("active_stale_after must not be negative")
    with _queue_lock(path, timeout=lock_timeout, stale_after=lock_stale_after):
        state = _read_state(path)
        now = time.time()
        _recover_stale_active(state, stale_after=active_stale_after, now=now)
        pending = [item for item in state["items"] if item.get("state") == "pending"]
        if not pending:
            return None
        selected = min(pending, key=lambda item: (int(item["priority"]), int(item["sequence"])))
        selected["state"] = "active"
        selected["worker_id"] = resolved_worker
        selected["claim_id"] = uuid.uuid4().hex
        selected["claimed_at"] = now
        selected["attempts"] = int(selected.get("attempts", 0)) + 1
        _write_state(path, state)
        return dict(selected)


def record(
    path: str | Path,
    item_id: str,
    claim_id: str,
    state_name: str,
    result: Any = None,
    *,
    lock_timeout: float = 2.0,
    lock_stale_after: float = 30.0,
) -> dict[str, Any]:
    if state_name not in {"done", "failed"}:
        raise ValueError("state must be done or failed")
    with _queue_lock(path, timeout=lock_timeout, stale_after=lock_stale_after):
        state = _read_state(path)
        for item in state["items"]:
            if item.get("id") != item_id:
                continue
            if item.get("state") != "active" or item.get("claim_id") != claim_id:
                raise ValueError("claim does not own the active item")
            item["state"] = state_name
            item["result"] = result
            item.pop("worker_id", None)
            item.pop("claim_id", None)
            item.pop("claimed_at", None)
            _write_state(path, state)
            return dict(item)
        raise KeyError(item_id)


def run_loop_auto(
    path: str | Path,
    executor: Callable[[Mapping[str, Any]], Any],
    *,
    enabled: bool = False,
    max_steps: int = 32,
    worker_id: str = "loop_auto",
    active_stale_after: float = 300.0,
) -> dict[str, Any]:
    if enabled is not True:
        return {"status": "disabled", "processed": [], "failed": None}
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    processed: list[str] = []
    for _ in range(max_steps):
        item = claim_next(path, worker_id=worker_id, active_stale_after=active_stale_after)
        if item is None:
            return {"status": "drained", "processed": processed, "failed": None}
        try:
            result = executor(dict(item))
        except Exception as exc:
            record(path, item["id"], item["claim_id"], "failed", {"error": str(exc)})
            return {"status": "stopped", "processed": processed, "failed": item["id"]}
        record(path, item["id"], item["claim_id"], "done", result)
        processed.append(item["id"])
    remaining = any(item.get("state") == "pending" for item in queue_state(path)["items"])
    status = "limit_reached" if remaining else "drained"
    return {"status": status, "processed": processed, "failed": None}


def _read_state(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"version": 1, "next_sequence": 0, "items": []}
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("items"), list):
        raise ValueError("invalid queue file")
    if not isinstance(raw.get("next_sequence"), int) or raw["next_sequence"] < 0:
        raise ValueError("invalid queue sequence")
    for item in raw["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ValueError("invalid queue item")
        normalized = item.get("normalized_text")
        if normalized is None:
            item["normalized_text"] = normalize_text(item["text"])
        elif not isinstance(normalized, str):
            raise ValueError("invalid normalized queue text")
    return raw


def _recover_stale_active(state: dict[str, Any], *, stale_after: float, now: float) -> int:
    recovered = 0
    for item in state["items"]:
        if item.get("state") != "active":
            continue
        claimed_at = item.get("claimed_at")
        if isinstance(claimed_at, (int, float)) and now - float(claimed_at) < stale_after:
            continue
        item["state"] = "pending"
        item.pop("worker_id", None)
        item.pop("claim_id", None)
        item.pop("claimed_at", None)
        recovered += 1
    return recovered


@contextmanager
def _queue_lock(path: str | Path, *, timeout: float, stale_after: float):
    if timeout < 0 or stale_after < 0:
        raise ValueError("lock timing values must not be negative")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{target}.lock")
    token = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    file_descriptor: int | None = None
    while file_descriptor is None:
        try:
            file_descriptor = _create_new_lock(lock_path)
            os.write(file_descriptor, token.encode("ascii"))
            os.fsync(file_descriptor)
        except FileExistsError:
            if _remove_stale_lock(lock_path, stale_after=stale_after):
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"queue lock wait exceeded {timeout:.3f}s")
            time.sleep(min(0.01, max(0.001, deadline - time.monotonic())))
    try:
        yield
    finally:
        os.close(file_descriptor)
        try:
            if lock_path.read_text(encoding="ascii") == token:
                lock_path.unlink()
        except FileNotFoundError:
            pass


def _create_new_lock(path: Path) -> int:
    return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)


def _remove_stale_lock(path: Path, *, stale_after: float) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return True
    if age < stale_after:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return True


def _write_state(path: str | Path, state: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clonamic-preprocessing")
    sub = parser.add_subparsers(dest="action", required=True)
    normalize = sub.add_parser("normalize")
    normalize.add_argument("text")
    clarify = sub.add_parser("clarify")
    clarify.add_argument("text")
    clarify.add_argument("--missing", action="append", default=[])
    add = sub.add_parser("enqueue")
    add.add_argument("--queue", required=True)
    add.add_argument("--text", required=True)
    add.add_argument("--priority", type=int, default=100)
    add.add_argument("--id")
    take = sub.add_parser("next")
    take.add_argument("--queue", required=True)
    take.add_argument("--worker", required=True)
    save = sub.add_parser("record")
    save.add_argument("--queue", required=True)
    save.add_argument("--id", required=True)
    save.add_argument("--claim", required=True)
    save.add_argument("--state", choices=("done", "failed"), required=True)
    save.add_argument("--result", default="null")
    args = parser.parse_args(argv)
    try:
        if args.action == "normalize":
            output: Any = {"normalized_text": normalize_text(args.text)}
        elif args.action == "clarify":
            output = clarification_contract(args.text, args.missing)
        elif args.action == "enqueue":
            output = enqueue(args.queue, args.text, priority=args.priority, item_id=args.id)
        elif args.action == "next":
            output = claim_next(args.queue, worker_id=args.worker)
        else:
            output = record(args.queue, args.id, args.claim, args.state, json.loads(args.result))
        print(json.dumps({"ok": True, "result": output}, ensure_ascii=False, sort_keys=True))
        return 0
    except (TypeError, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
