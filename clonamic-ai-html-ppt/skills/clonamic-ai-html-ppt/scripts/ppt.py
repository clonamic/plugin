"""clonamic-AI-HTML-PPT CLI for the AI. Every command prints one JSON object (wait --stream prints one per line).

  open [--deck ID|NAME] [--new NAME] [--preset KEY] [--host H] [--no-browser]
                                                                     start or reuse the editor, open the browser
  status                                                             is the editor running, and where
  wait --deck D --session S [--timeout 55] [--stream]                next event: message (+run)|resume|timeout|closed|replaced|error
  agent next --deck D --run R                                        advance a run to its next AI step; prints the instruction
  agent submit --deck D --run R --node plan|reply < output.json      submit that step's JSON and advance
  snapshot --deck D [--page ID] [--ids a,b | --rect x,y,w,h] [--scale 2]   PNG of a page region
  outline --deck D [--page ID]                                       compact tree for reading (format.md §5)
  get --deck D (--ids a,b | --page ID)                               full nodes with rev
  patch --deck D [--label T] [--actor ai] < ops.json                 apply an op batch ([...] or {"ops": [...]})
  check --deck D [--pages a,b]                                       measure, write auto sizes, lint → {issues, warnings, counts}
  say --deck D < text                                                AI chat reply
  asset FILE                                                         upload an image/video file → {hash, mime, w, h} for IMAGE fills
  pdf --deck D [--pages a,b] [--mode single|each] [--dir PATH]       export PDF with headless Chrome
  stop                                                               shut the editor down
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

from store import data_dir

HERE = Path(__file__).resolve().parent
BASE, SPAN = int(os.environ.get("PPT_BASE_PORT", 24242)), 100
APP = "ai-html-ppt"


def out(data: dict, code: int = 0) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)
    if code:
        sys.exit(code)


def info() -> dict | None:
    try:
        return json.loads((data_dir() / "server.json").read_text())
    except (OSError, ValueError):
        return None


def call(srv: dict, method: str, path: str, data=None, timeout: float = 10):
    """(status, parsed body) — JSON, or {"text": ...} for text/plain."""
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{srv['port']}{path}", data=body, method=method,
                                 headers={"Content-Type": "application/json", "X-PPT-Token": srv.get("token", ""),
                                          "X-PPT-Client": "cli"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, kind, text = resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        status, kind, text = exc.code, exc.headers.get("Content-Type", ""), exc.read()
    if kind.startswith("text/plain"):
        return status, {"text": text.decode()}
    try:
        return status, json.loads(text or b"{}")
    except ValueError:
        return status, {"error": text.decode(errors="replace")[:500]}


def running() -> dict | None:
    """server.json of a live editor for this HOME, else None."""
    srv = info()
    if not srv:
        return None
    try:
        status, health = call(srv, "GET", "/api/health", timeout=3)  # a refused port fails at once; only a busy server waits
    except (OSError, ValueError):
        return None
    return srv if status == 200 and health.get("app") == APP and health.get("pid") == srv.get("pid") else None


def free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_server() -> dict:
    port = next((p for p in range(BASE, BASE + SPAN) if free(p)), None)
    if port is None:
        out({"ok": False, "error": f"{BASE}~{BASE + SPAN - 1} 사이에 빈 포트가 없습니다."}, 2)
    data_dir().mkdir(parents=True, exist_ok=True)
    log = open(data_dir() / "server.log", "ab")
    subprocess.Popen([sys.executable, str(HERE / "server.py"), "--port", str(port)], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True, cwd=str(HERE))
    for _ in range(100):
        srv = running()
        if srv and srv["port"] == port:
            return srv
        time.sleep(0.1)
    out({"ok": False, "error": "편집기 서버가 시작되지 않았습니다.", "log": str(data_dir() / "server.log")}, 2)


def need_server() -> dict:
    srv = running()
    if srv is None:
        out({"ok": False, "error": "편집기 서버가 꺼져 있습니다. open을 먼저 실행하세요.", "closed": True}, 3)
    return srv


def resolve_deck(srv: dict, ref: str | None) -> int | None:
    if ref is None:
        return None
    _, decks = call(srv, "GET", "/api/decks")
    return next((d["id"] for d in decks if str(d["id"]) == ref), None) or next((d["id"] for d in decks if d["name"] == ref), None)


def deck_arg(srv: dict, ref: str) -> int:
    deck = resolve_deck(srv, ref)
    if deck is None:
        out({"ok": False, "error": f"문서「{ref}」이(가) 없습니다."}, 2)
    return deck


def result(status: int, data, good: int = 200) -> None:
    body = data if isinstance(data, dict) else {"result": data}
    out({"ok": status == good, **body}, 0 if status == good else 2)


def cmd_open(args) -> None:
    first = not (data_dir() / "ppt.db").exists()
    srv = running() or start_server()
    deck = None
    if args.new:  # the same command again reopens that deck instead of making a copy
        deck = resolve_deck(srv, args.new)
        if deck is None:
            status, made = call(srv, "POST", "/api/decks", {"name": args.new, "preset": args.preset})
            if status != 201:
                out({"ok": False, **made}, 2)
            deck = made["id"]
    elif args.deck:
        deck = deck_arg(srv, args.deck)
    session = secrets.token_hex(6)
    if args.host:
        status, data = call(srv, "POST", "/api/sessions", {"session": session, "host": args.host, "deck": deck})
        if status != 200:
            out({"ok": False, **data}, 2)
    url = f"http://127.0.0.1:{srv['port']}/" + (f"#{deck}" if deck else "")
    if not args.no_browser:
        webbrowser.open(url)
    _, decks = call(srv, "GET", "/api/decks")
    out({"ok": True, "url": url, "port": srv["port"], "deck": deck, "session": session, "first_run": first,
         "decks": [{"id": d["id"], "name": d["name"], "pages": d["pages"]} for d in decks][:20]})


def cmd_status(args) -> None:
    srv = running()
    if srv is None:
        return out({"ok": True, "running": False})
    _, decks = call(srv, "GET", "/api/decks")
    out({"ok": True, "running": True, "port": srv["port"], "pid": srv["pid"], "url": f"http://127.0.0.1:{srv['port']}/",
         "decks": [{"id": d["id"], "name": d["name"], "pages": d["pages"]} for d in decks][:20]})


def cmd_wait(args) -> None:
    """--stream keeps going and stays silent on timeout, so a host that treats each line as an event only wakes
    for something real."""
    srv = running()
    if srv is None:
        return out({"status": "closed"})
    deck = deck_arg(srv, args.deck)
    failures = 0
    while True:
        try:
            status, data = call(srv, "GET", f"/api/wait?deck={deck}&token={quote(args.session)}&timeout={args.timeout}",
                                timeout=args.timeout + 15)
        except (OSError, ValueError) as exc:
            if running() is None:
                status, data = 200, {"status": "closed"}
            elif (failures := failures + 1) < 3:
                continue
            else:
                status, data = 500, {"error": str(exc)}
        if status != 200:
            return out({"status": "error", "error": data.get("error", f"HTTP {status}")}, 2)
        failures = 0
        if data.get("status") == "message":
            msg = data["message"]
            data["message"] = {"id": msg["id"], "text": msg["text"][:4000], "cut": len(msg["text"]) > 4000, "meta": msg["meta"]}
        if args.stream and data.get("status") == "timeout":
            continue
        out(data)
        if not args.stream or data.get("status") in ("closed", "replaced"):
            return


def cmd_outline(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    status, data = call(srv, "GET", f"/api/decks/{deck}/outline" + (f"?page={quote(args.page)}" if args.page else ""))
    if status != 200:
        out({"ok": False, **data}, 2)
    out({"ok": True, "outline": data["text"]})


def cmd_get(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    if not (args.ids or args.page):
        out({"ok": False, "error": "--ids 또는 --page가 필요합니다."}, 2)
    query = f"ids={quote(args.ids)}" if args.ids else f"page={quote(args.page)}"
    result(*call(srv, "GET", f"/api/decks/{deck}/nodes?{query}"))


def cmd_patch(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    payload = json.loads(sys.stdin.read())
    batch = payload.get("ops") if isinstance(payload, dict) else payload
    result(*call(srv, "POST", f"/api/decks/{deck}/ops",
                 {"actor": args.actor, "client": "cli", "label": args.label, "ops": batch}, timeout=60))


def cmd_check(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    pages = [p for p in (args.pages or "").split(",") if p]
    status, data = call(srv, "POST", f"/api/decks/{deck}/check", {"pages": pages}, timeout=600)
    if status == 200:
        found = data["issues"] + data["warnings"]
        data["counts"] = {c: sum(f["code"] == c for f in found) for c in dict.fromkeys(f["code"] for f in found)}
    result(status, data)


def cmd_say(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    result(*call(srv, "POST", f"/api/decks/{deck}/messages", {"role": "ai", "text": sys.stdin.read().strip()}), good=201)


def cmd_asset(args) -> None:
    srv = need_server()
    path = os.path.expanduser(args.file)
    kind = mimetypes.guess_type(path)[0] or "application/octet-stream"  # the server sniffs the real type
    with open(path, "rb") as f:
        req = urllib.request.Request(f"http://127.0.0.1:{srv['port']}/api/assets", data=f.read(), method="POST",
                                     headers={"Content-Type": kind, "X-PPT-Token": srv.get("token", ""), "X-PPT-Client": "cli"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status, body = resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        status, body = exc.code, json.loads(exc.read() or b"{}")
    result(status, body)


def cmd_pdf(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    pages = [p for p in (args.pages or "").split(",") if p]
    body = {"pages": pages, "mode": args.mode, "dir": args.dir}
    result(*call(srv, "POST", f"/api/decks/{deck}/pdf", body, timeout=130 * max(len(pages), 30)))


def cmd_agent(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    base = f"/api/decks/{deck}/runs/{args.run}"
    if args.action == "next":
        return result(*call(srv, "POST", f"{base}/next", {}, timeout=600))
    if args.node not in ("plan", "reply"):
        out({"ok": False, "error": "--node는 plan 또는 reply입니다."}, 2)
    output = json.loads(sys.stdin.read())
    result(*call(srv, "POST", f"{base}/submit", {"node": args.node, "output": output}, timeout=600))


def cmd_snapshot(args) -> None:
    srv = need_server()
    deck = deck_arg(srv, args.deck)
    query = {"page": args.page, "ids": args.ids, "rect": args.rect, "scale": args.scale}
    text = "&".join(f"{k}={quote(str(v))}" for k, v in query.items() if v)
    result(*call(srv, "GET", f"/api/decks/{deck}/snapshot?{text}", timeout=180))


def cmd_stop(args) -> None:
    srv = running()
    if srv is None:
        return out({"ok": True, "running": False})
    try:
        call(srv, "POST", "/api/shutdown", {})
    except (OSError, ValueError):
        pass
    for _ in range(100):
        if free(srv["port"]) and not (data_dir() / "server.json").exists():
            return out({"ok": True, "running": False, "port": srv["port"]})
        time.sleep(0.1)
    out({"ok": False, "error": "편집기 서버가 10초 안에 멈추지 않았습니다.", "pid": srv["pid"]}, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("--deck")
    p.add_argument("--new")
    p.add_argument("--preset", default="SLIDE_16_9")
    p.add_argument("--host", choices=["claude-code", "codex", "cursor", "grok", "other"])
    p.add_argument("--no-browser", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("wait")
    p.add_argument("--deck", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--timeout", type=float, default=55)
    p.add_argument("--stream", action="store_true")
    p = sub.add_parser("outline")
    p.add_argument("--deck", required=True)
    p.add_argument("--page")
    p = sub.add_parser("get")
    p.add_argument("--deck", required=True)
    p.add_argument("--ids")
    p.add_argument("--page")
    p = sub.add_parser("patch")
    p.add_argument("--deck", required=True)
    p.add_argument("--label", default="AI 편집")
    p.add_argument("--actor", default="ai", choices=["ai", "user"])
    p = sub.add_parser("check")
    p.add_argument("--deck", required=True)
    p.add_argument("--pages")
    sub.add_parser("say").add_argument("--deck", required=True)
    sub.add_parser("asset").add_argument("file")
    p = sub.add_parser("pdf")
    p.add_argument("--deck", required=True)
    p.add_argument("--pages")
    p.add_argument("--mode", default="single", choices=["single", "each"])
    p.add_argument("--dir", default="~/Downloads")
    p = sub.add_parser("agent")
    p.add_argument("action", choices=["next", "submit"])
    p.add_argument("--deck", required=True)
    p.add_argument("--run", type=int, required=True)
    p.add_argument("--node")
    p = sub.add_parser("snapshot")
    p.add_argument("--deck", required=True)
    p.add_argument("--page")
    p.add_argument("--ids")
    p.add_argument("--rect")
    p.add_argument("--scale", type=float)
    sub.add_parser("stop")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        out({"ok": False, "error": "Python 3.12 이상이 필요합니다. `uv python install 3.12` 또는 OS 패키지 관리자로 설치하세요."}, 2)
    try:
        {"open": cmd_open, "status": cmd_status, "wait": cmd_wait, "outline": cmd_outline, "get": cmd_get, "patch": cmd_patch, "check": cmd_check,
         "say": cmd_say, "asset": cmd_asset, "pdf": cmd_pdf, "agent": cmd_agent, "snapshot": cmd_snapshot, "stop": cmd_stop}[args.cmd](args)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:  # one JSON object even on failure
        out({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 2)


if __name__ == "__main__":
    main()
