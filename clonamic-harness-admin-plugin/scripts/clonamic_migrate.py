#!/usr/bin/env python3
"""Reversible active-surface migration from legacy custom names to Clonamic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path


MAPPINGS = (
    ("clx-modular-architecture-design", "clonamic-modular-design"),
    ("clx-autoclearmemory", "clonamic-memory"),
    ("clx-anti-overengineering", "clonamic-supercoder"),
    ("clx-anti-hallucination", "clonamic-context-integrity"),
    ("clx-harness-full-package", "clonamic-herness-plugin"),
    ("clx-bracket-payload", "clonamic-bracket-payload"),
    ("clx-vercel-web-design-guidelines", "clonamic-vercel-web-design-guidelines"),
    ("clx-hand-drawn-diagrams", "clonamic-hand-drawn-diagrams"),
    ("clx-grok-delegate", "clonamic-grok-delegate"),
    ("clx-session-intent", "clonamic-session-intent"),
    ("clx-concise-report", "clonamic-report"),
    ("clx-report-policy", "clonamic-report"),
    ("clx-dataset-work", "clonamic-dataset-work"),
    ("clx-codex-config", "clonamic-codex-config"),
    ("clx-claude-config", "clonamic-claude-config"),
    ("clx-harness-factory", "clonamic-harness-factory"),
    ("clx-repo-backup", "clonamic-repo-backup"),
    ("clx-preprocessing", "clonamic-preprocessing"),
    ("clx-preprocess", "clonamic-preprocessing"),
    ("clx-supercoder", "clonamic-supercoder"),
    ("clx-ultracode", "clonamic-ultracode"),
    ("clx-grok-call", "clonamic-grok"),
    ("clx-hermes-call", "clonamic-hermes"),
    ("clx-forgetforge", "clonamic-memory"),
    ("clx-clear-korean", "clonamic-korean"),
    ("clx-flow-map", "clonamic-code-router"),
    ("clx-grill-me", "clonamic-grill-me"),
    ("clx-ai-delegate", "clonamic-ai-delegate"),
    ("clx-algorithmic-art", "clonamic-algorithmic-art"),
    ("clx-apple-design", "clonamic-apple-design"),
    ("clx-canvas-design", "clonamic-canvas-design"),
    ("clx-color-expert", "clonamic-color-expert"),
    ("clx-figma-workflow", "clonamic-figma-workflow"),
    ("clx-frontend-design", "clonamic-frontend-design"),
    ("clx-immersive-web", "clonamic-immersive-web"),
    ("clx-playwright", "clonamic-playwright"),
    ("clx-theme-factory", "clonamic-theme-factory"),
    ("clx-unslop", "clonamic-unslop"),
    ("clx-hwpx", "clonamic-hwpx"),
    ("clx-model", "clonamic-model"),
    ("clx-skillbook", "clonamic-skillbook"),
    ("clx-delegate", "clonamic-delegate"),
    ("cluxion", "clonamic"),
)

CLI_MAPPINGS = {
    "clx-ai-delegate": "clonamic-ai-delegate",
    "clx-grok-delegate": "clonamic-grok-delegate",
    "clx-grok-call": "clonamic-grok-call",
    "clx-hermes-call": "clonamic-hermes-call",
    "clx-supercoder": "clonamic-supercoder",
    "clx-ultracode": "clonamic-ultracode",
    "cluxion-supercoder": "clonamic-supercoder",
    "cluxion-ultracode": "clonamic-ultracode",
    "cluxion-preprocess": "clonamic-preprocess",
}

TEXT_ROOTS = (
    ".agents/user",
    ".codex/guides",
    ".codex/rules",
    ".codex/prompts",
    ".claude/guides",
    ".claude/rules",
)
TEXT_FILES = (
    ".agents/AGENTS.md",
    ".agents/models.toml",
    ".codex/AGENTS.md",
    ".codex/config.toml",
    ".claude/CLAUDE.md",
    ".claude/settings.json",
    ".grok/config.toml",
    ".grok/sandbox.toml",
)
SKILL_ROOTS = (
    ".agents/skills",
    ".codex/skills",
    ".codex/skills-disabled",
    ".claude/skills",
)
ARCHIVE_SKILLS = {
    "anti-ai-writing",
    "brainstorming",
    "docx",
    "dumbify",
    "ensemble-consensus",
    "gstack",
    "impeccable",
    "pdf",
    "pptx",
    "storytelling",
    "systematic-debugging",
    "test-driven-development",
    "verification-before-completion",
    "viral-hooks",
    "voice-dna",
    "xlsx",
}
TEXT_SUFFIXES = {".md", ".json", ".toml", ".yaml", ".yml", ".txt"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def text_paths(home: Path) -> list[Path]:
    paths = [home / relative for relative in TEXT_FILES]
    for relative in TEXT_ROOTS:
        root = home / relative
        if root.is_dir():
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and path.suffix.casefold() in TEXT_SUFFIXES
                and ".pre-" not in path.name
            )
    return sorted({path for path in paths if path.is_file() and not path.is_symlink()})


def replace_names(value: str) -> str:
    for source, target in MAPPINGS:
        value = value.replace(source, target)
    return value


def atomic_text(path: Path, value: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
        temporary = ""
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def manifest_path(backup: Path) -> Path:
    return backup / "migration/manifest.json"


def write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def apply(home: Path, backup: Path) -> dict:
    target = manifest_path(backup)
    if target.is_file():
        return json.loads(target.read_text(encoding="utf-8"))
    store = target.parent / "files"
    store.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "home": str(home), "files": [], "moves": [], "created": []}

    for index, path in enumerate(text_paths(home)):
        before = path.read_text(encoding="utf-8")
        after = replace_names(before)
        if after == before:
            continue
        saved = store / f"{index:04d}-{path.name}"
        shutil.copy2(path, saved)
        payload["files"].append(
            {"path": str(path), "backup": str(saved), "sha256": digest(saved)}
        )
        atomic_text(path, after)

    archive = backup / "migration/skills"
    for relative in SKILL_ROOTS:
        root = home / relative
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.name.startswith("clx-") and path.name not in ARCHIVE_SKILLS:
                continue
            destination = archive / relative.removeprefix(".") / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, destination)
            payload["moves"].append({"source": str(path), "archive": str(destination)})

    local_bin = home / ".local/bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    for old, new in CLI_MAPPINGS.items():
        source = local_bin / old
        destination = local_bin / new
        if not source.exists() or destination.exists():
            continue
        destination.write_text(
            f'#!/bin/sh\nexec "{source}" "$@"\n', encoding="utf-8"
        )
        destination.chmod(0o755)
        payload["created"].append(str(destination))

    write_manifest(target, payload)
    return payload


def rollback(home: Path, backup: Path) -> dict:
    target = manifest_path(backup)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if Path(payload["home"]).resolve() != home.resolve():
        raise ValueError("backup belongs to another home")
    for path in payload["created"]:
        Path(path).unlink(missing_ok=True)
    for row in reversed(payload["moves"]):
        source = Path(row["source"])
        archived = Path(row["archive"])
        source.parent.mkdir(parents=True, exist_ok=True)
        if archived.exists() and not source.exists():
            os.replace(archived, source)
    for row in payload["files"]:
        source = Path(row["backup"])
        if digest(source) != row["sha256"]:
            raise ValueError("backup hash mismatch")
        destination = Path(row["path"])
        shutil.copy2(source, destination)
    return payload


def verify(home: Path, backup: Path) -> dict:
    findings = []
    for path in text_paths(home):
        text = path.read_text(encoding="utf-8")
        if "clx-" in text or "cluxion" in text.casefold():
            findings.append(str(path))
    for relative in SKILL_ROOTS:
        root = home / relative
        if root.is_dir():
            findings.extend(
                str(path)
                for path in root.iterdir()
                if path.name.startswith("clx-") or path.name in ARCHIVE_SKILLS
            )
    result = {"ok": not findings, "findings": sorted(findings), "manifest": str(manifest_path(backup))}
    if findings:
        raise ValueError(json.dumps(result, ensure_ascii=False))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "apply", "verify", "rollback"))
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--backup", required=True)
    args = parser.parse_args(argv)
    home = Path(args.home).resolve()
    backup = Path(args.backup).resolve()
    try:
        if args.command == "preflight":
            result = {
                "text_files": len(text_paths(home)),
                "legacy_skills": sum(
                    1
                    for relative in SKILL_ROOTS
                    for path in ((home / relative).iterdir() if (home / relative).is_dir() else ())
                    if path.name.startswith("clx-") or path.name in ARCHIVE_SKILLS
                ),
            }
        elif args.command == "apply":
            result = apply(home, backup)
        elif args.command == "verify":
            result = verify(home, backup)
        else:
            result = rollback(home, backup)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
