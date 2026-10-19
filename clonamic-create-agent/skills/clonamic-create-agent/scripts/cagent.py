"""clonamic-create-agent CLI. Every command prints one JSON object (wait --stream prints one per line).

  open [--project NAME|ID] [--new NAME] [--no-browser]   start or reuse the editor and open the browser
  wait --project ID --session S [--timeout 55] [--stream] next chat message: status message|timeout|closed|replaced|error
                                                         (--stream keeps going and never prints timeout)
  get --project ID                                       current document and version
  put --project ID --version V [--note T --why T --affected T] < doc.json
  say --project ID < text                                AI chat reply (plain text, no markdown)
  propose --project ID < card.json                       proposal card {title, criterion, reason, targets, changes, effect, doc, base_version, kind}
  check --project ID                                     pre-export checks
  korean [--check] [< text]                              locate clonamic-korean, or run its checker on text
"""

from __future__ import annotations

import argparse
import json
import math
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import korean
from store import code_hash, data_dir

HERE = Path(__file__).resolve().parent
BASE, SPAN = 23232, 100
APP = "clonamic-create-agent"


def out(data: dict, code: int = 0) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)
    if code:
        sys.exit(code)


def call(port: int, method: str, path: str, data=None, timeout: float = 10):
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method,
                                 headers={"Content-Type": "application/json", "X-Clonamic": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"error": raw.decode(errors="replace")[:500]}


def ours(port: int) -> bool:
    try:
        status, data = call(port, "GET", "/api/health", timeout=1)
    except (OSError, ValueError):
        return False
    return status == 200 and data.get("app") == APP and data.get("data_dir") == str(data_dir())


def free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def find_server() -> int | None:
    return next((p for p in range(BASE, BASE + SPAN) if not free(p) and ours(p)), None)


def pick_port() -> int | None:
    """First free port from 23232 upward (+1 per port in use)."""
    return next((p for p in range(BASE, BASE + SPAN) if free(p)), None)


def log_tail() -> str:
    """The last error line in server.log (a broken database, a bad Python), so a failed start says why."""
    try:
        lines = (data_dir() / "server.log").read_text(errors="replace").strip().splitlines()
    except OSError:
        return ""
    return next((x.strip() for x in reversed(lines) if "Error" in x or "error" in x), lines[-1].strip() if lines else "")


def start_server(first: float = 180.0) -> int:
    """`first`: how long the server waits for its first tab (longer when no browser is opened for the user)."""
    port = pick_port()
    if port is None:
        out({"ok": False, "error": f"{BASE}~{BASE + SPAN - 1} 사이에 빈 포트가 없습니다."}, 2)
    data_dir().mkdir(parents=True, exist_ok=True)
    log = open(data_dir() / "server.log", "ab")
    subprocess.Popen([sys.executable, str(HERE / "server.py"), "--port", str(port), "--first", str(first)], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True, cwd=str(HERE))
    for _ in range(50):
        if ours(port):
            return port
        time.sleep(0.1)
    out({"ok": False, "error": "편집기 서버가 시작되지 않았습니다.", "reason": log_tail(), "log": str(data_dir() / "server.log")}, 2)


def need_server() -> int:
    port = find_server()
    if port is None:
        out({"ok": False, "error": "편집기 서버가 꺼져 있습니다. open을 먼저 실행하세요.", "closed": True}, 3)
    return port


def resolve_project(port: int, ref: str) -> int | None:
    _, projects = call(port, "GET", "/api/projects")
    for p in projects:
        if str(p["id"]) == ref or p["name"] == ref:
            return p["id"]
    return None


def cmd_open(args) -> None:
    first = not data_dir().exists()
    port = find_server() or start_server(1800.0 if args.no_browser else 180.0)
    pid, reopened = None, False
    if args.new:  # running the same command again reopens that project instead of making a copy
        pid = resolve_project(port, args.new)
        reopened = pid is not None
        if pid is None:
            _, made = call(port, "POST", "/api/projects", {"name": args.new})
            pid = made["id"]
    elif args.project:
        pid = resolve_project(port, args.project)
        if pid is None:
            out({"ok": False, "error": f"프로젝트「{args.project}」이(가) 없습니다.", "port": port}, 2)
    url = f"http://127.0.0.1:{port}/" + (f"#{pid}" if pid else "")
    if not args.no_browser:
        webbrowser.open(url)
    _, projects = call(port, "GET", "/api/projects")
    _, health = call(port, "GET", "/api/health")
    stale = health.get("code") != code_hash()  # started from older files: the tabs still run the old editor
    out({"ok": True, "url": url, "port": port, "project": pid, "session": secrets.token_hex(6), "reopened": reopened,
         "data_dir": str(data_dir()), "first_run": first, "stale": stale,
         **({"notice": "편집기 서버가 예전 코드로 돌고 있습니다. 열린 탭을 모두 닫으면 10초 뒤 꺼지고, 다시 실행하면 새 코드로 뜹니다."}
            if stale else {}),
         "projects": [{"id": p["id"], "name": p["name"]} for p in projects][:20] if pid is None else None})


def cmd_wait(args) -> None:
    """Statuses: message, timeout, closed, replaced, error. --stream keeps going and stays silent on timeout,
    so a host that treats each line as an event (Claude Code Monitor) only wakes for something real."""
    port = find_server()
    if port is None:  # the tabs closed between two waits
        return out({"status": "closed"})
    args.timeout = max(1.0, min(args.timeout if math.isfinite(args.timeout) else 55.0, 600.0))  # never a busy loop
    failures = 0
    while True:
        try:
            status, data = call(port, "GET", f"/api/wait?project={args.project}&token={args.session}&timeout={args.timeout}",
                                timeout=args.timeout + 15)
        except (OSError, ValueError) as exc:
            if find_server() is None:
                status, data = 200, {"status": "closed"}
            elif (failures := failures + 1) < 3:
                continue
            else:
                status, data = 500, {"error": str(exc)}
        if status != 200:
            return out({"status": "error", "error": data.get("error", f"HTTP {status}")}, 2)
        failures = 0
        if data.get("status") == "message":
            data["message"] = trim(data["message"])
        if args.stream and data.get("status") == "timeout":
            continue
        out(data)
        if not args.stream or data.get("status") in ("closed", "replaced"):
            return


def trim(message: dict) -> dict:
    """Keep the line short for host output limits; the full text is in `get` and the messages API."""
    text = message.get("body", {}).get("text", "")
    return {"id": message["id"], "kind": message["kind"], "text": text[:4000], "cut": len(text) > 4000}


def read_stdin() -> str:
    return sys.stdin.read()


def cmd_get(args) -> None:
    port = need_server()
    status, data = call(port, "GET", f"/api/projects/{args.project}")
    if status != 200:
        out({"ok": False, **data}, 2)
    _, messages = call(port, "GET", f"/api/projects/{args.project}/messages")
    data["recent_messages"] = [{"id": m["id"], "role": m["role"], "kind": m["kind"], "status": m["status"],
                                "text": m["body"].get("text") or m["body"].get("title", "")} for m in messages[-20:]]
    out({"ok": True, **data})


def cmd_put(args) -> None:
    port = need_server()
    payload = {"doc": json.loads(read_stdin()), "version": args.version, "note": args.note, "why": args.why,
               "affected": args.affected}
    status, data = call(port, "PUT", f"/api/projects/{args.project}", payload)
    out({"ok": status == 200, **data}, 0 if status == 200 else 2)


def cmd_say(args) -> None:
    port = need_server()
    status, data = call(port, "POST", f"/api/projects/{args.project}/messages", {"role": "ai", "text": read_stdin().strip()})
    out({"ok": status == 201, **data}, 0 if status == 201 else 2)


def cmd_propose(args) -> None:
    port = need_server()
    card = json.loads(read_stdin())
    status, data = call(port, "POST", f"/api/projects/{args.project}/cards", card)
    out({"ok": status == 201, **data}, 0 if status == 201 else 2)


def cmd_check(args) -> None:
    port = need_server()
    status, data = call(port, "GET", f"/api/projects/{args.project}/check")
    if status != 200:
        out({"ok": False, **data}, 2)
    errors = [i for i in data["issues"] if i.get("level", "error") == "error"]  # warnings never block
    out({"ok": not errors, "errors": len(errors), "warnings": len(data["issues"]) - len(errors), **data})


def cmd_korean(args) -> None:
    data, code = korean.check(read_stdin() if args.check else None)
    out(data, code if args.check else 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("--project")
    p.add_argument("--new")
    p.add_argument("--no-browser", action="store_true")
    p = sub.add_parser("wait")
    p.add_argument("--project", type=int, required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--timeout", type=float, default=55)
    p.add_argument("--stream", action="store_true")
    for name in ("get", "say", "propose", "check"):
        sub.add_parser(name).add_argument("--project", type=int, required=True)
    p = sub.add_parser("put")
    p.add_argument("--project", type=int, required=True)
    p.add_argument("--version", type=int, required=True)
    p.add_argument("--note", default="")
    p.add_argument("--why", default="")
    p.add_argument("--affected", default="")
    sub.add_parser("korean").add_argument("--check", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        out({"ok": False, "error": "Python 3.12 이상이 필요합니다. `uv python install 3.12` 또는 OS 패키지 관리자로 설치하세요."}, 2)
    try:
        {"open": cmd_open, "wait": cmd_wait, "get": cmd_get, "put": cmd_put, "say": cmd_say, "propose": cmd_propose,
         "check": cmd_check, "korean": cmd_korean}[args.cmd](args)
    except (OSError, ValueError, KeyError, TypeError) as exc:  # one JSON object even on failure (bad stdin JSON, server gone)
        out({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 2)


if __name__ == "__main__":
    main()
