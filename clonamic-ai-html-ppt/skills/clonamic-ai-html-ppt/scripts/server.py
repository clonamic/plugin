"""Editor server on 127.0.0.1: static web app, deck JSON API, op batches, SSE, the AI's long-poll, assets, PDF.

Lifetime = the browser tabs: it stops 10 s after the last event stream closes; if none ever opened, 180 s after
start or the last CLI call with no wait in flight; on POST /api/shutdown, or on SIGTERM. While running, ~/.clonamic/ai-html-ppt/server.json holds
{port, pid, token, started} (mode 0600).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import os
import re
import secrets
import select
import signal
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, unquote, urlparse

import agent
import lint
import ops
import pdf
from store import FOCUS_STATUS, NotFound, Store, data_dir

VERSION = "0.1.0"
APP = "ai-html-ppt"
WEB = Path(__file__).resolve().parent.parent / "assets" / "web"
MAX_JSON, MAX_UPLOAD, GZIP_MIN = 20 * 2**20, 200 * 2**20, 8192
PING = 15.0
AI_IDLE = 10.0  # seconds without a wait before the AI counts as disconnected
SNAP_MARGIN, SNAP_MAX, SNAP_KEEP = 24, 4096, 50
HOSTS = ("claude-code", "codex", "cursor", "grok", "other")
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
         ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
         ".otf": "font/otf", ".map": "application/json", ".txt": "text/plain"}
STATIC_ROOTS = ("js", "vendor")
STATIC_FILES = ("index.html", "print.html", "schema.json", "app.css")
META = '<meta name="ppt-token" content="">'
DATA = '<script id="ppt-data" type="application/json"></script>'
HASH = re.compile(r"[0-9a-f]{64}")


def inject(html: str, token: str, data=None) -> str:
    """Token into <meta name="ppt-token">; for print.html also the deck JSON into <script id="ppt-data">."""
    html = html.replace(META, f'<meta name="ppt-token" content="{token}">')
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html = html.replace(DATA, f'<script id="ppt-data" type="application/json">{payload}</script>')
    return html


def asset_hashes(nodes: list[dict]) -> list[str]:
    """Every asset hash referenced in these nodes' props (image paints, video asset/poster)."""
    found: dict[str, None] = {}

    def walk(v) -> None:
        if isinstance(v, dict):
            for k, item in v.items():
                if k in ("asset", "poster") and isinstance(item, str) and HASH.fullmatch(item):
                    found[item] = None
                else:
                    walk(item)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    for n in nodes:
        walk(n["props"])
    return list(found)


class HttpError(Exception):
    def __init__(self, status: int, body: dict):
        super().__init__(body.get("error"))
        self.status, self.body = status, body


class App:
    def __init__(self, store: Store, token: str, grace: float = 10.0, first: float = 180.0):
        self.store, self.token, self.grace, self.first = store, token, grace, first
        self.cond = threading.Condition()
        self.bus: deque = deque(maxlen=2000)  # (n, deck, event, data, seq)
        self.n = 0
        self.clients = 0
        self.ever = False
        self.touched = time.time()  # start, then the last CLI call (X-PPT-Client: cli)
        self.closing = False
        self.sessions: dict[int, str] = {}  # deck → session of the AI waiting on it
        self.hosts: dict[str, str] = {}  # session → host AI
        self.seen: dict[int, float] = {}
        self.inflight: dict[int, int] = {}
        self.last_ai: dict[int, tuple] = {}
        self.server: ThreadingHTTPServer | None = None
        ctx = SimpleNamespace(store=store, commit=self.commit, amend=self.amend, say=self.say, snapshot=self.try_snapshot, measure=self.try_measure,
                              export=self.export, pins_changed=self.pins_changed, notify=self.ai_changed,
                              interrupted=self.ask_confirm)
        self.runner = agent.Runner(agent.edit_graph(), agent.Checkpointer(store), ctx)

    def publish(self, deck: int, event: str, data: dict, seq: int | None = None) -> None:
        with self.cond:
            self.n += 1
            self.bus.append((self.n, deck, event, data, seq))
            self.cond.notify_all()

    def stop(self) -> None:
        """Tell streams and waiters, then stop serving (from a thread: shutdown() blocks until serve_forever ends)."""
        with self.cond:
            if self.closing:
                return
            self.closing = True
            self.cond.notify_all()

        def later() -> None:
            time.sleep(0.3)  # let the streams write `closing`
            if self.server:
                self.server.shutdown()

        threading.Thread(target=later, daemon=True).start()

    def watch(self) -> None:
        """Stop after the last stream closes (grace). Until a stream ever opens, stop `first` s after the last CLI call
        once no wait is in flight, so a headless AI keeps it while it works. Announce AI disconnects."""
        empty_since = None
        while not self.closing:
            time.sleep(0.2)
            for deck, key in list(self.last_ai.items()):
                if key[0] and not self.ai_status(deck)["connected"]:
                    self.ai_changed(deck)
            with self.cond:
                clients, ever, waiting = self.clients, self.ever, any(self.inflight.values())
            now = time.time()
            if clients or (not ever and waiting):
                empty_since = None
                continue
            empty_since = empty_since or now
            if (ever and now - empty_since >= self.grace) or (not ever and now - self.touched >= self.first):
                with self.cond:
                    if self.clients:
                        empty_since = None
                        continue
                self.stop()
                return

    # the AI side (format.md §9.1)
    def ai_status(self, deck: int) -> dict:
        seen = self.seen.get(deck)
        seen_s = None if seen is None else round(time.time() - seen, 1)
        connected = self.inflight.get(deck, 0) > 0 or (seen_s is not None and seen_s < AI_IDLE)
        return {"connected": connected, "host": self.hosts.get(self.sessions.get(deck, "")), "seen_s": seen_s,
                "run": self.runner.saver.latest(deck)}

    def ai_changed(self, deck: int) -> None:
        """SSE `ai` when connection, host, or the latest run changed."""
        status = self.ai_status(deck)
        key = (status["connected"], status["host"], json.dumps(status["run"], sort_keys=True))
        if self.last_ai.get(deck) != key:
            self.last_ai[deck] = key
            self.publish(deck, "ai", status)

    def wait(self, deck: int, session: str, timeout: float) -> dict:
        """Next thing for the AI: message (+run), resume (a confirm answered), timeout (call again), closed, or replaced."""
        with self.cond:
            self.sessions[deck] = session
            self.inflight[deck] = self.inflight.get(deck, 0) + 1
            self.seen[deck] = time.time()
        self.ai_changed(deck)
        deadline = time.time() + timeout
        try:
            while True:
                with self.cond:
                    self.seen[deck] = time.time()
                    if self.closing:
                        return {"status": "closed"}
                    if self.sessions.get(deck) != session:
                        return {"status": "replaced"}
                    # under the same lock as the session check, so a replaced waiter takes nothing
                    resumed = self.runner.saver.take_resume(deck)
                    msg = None if resumed else self.store.take(deck)
                if resumed:
                    return {"status": "resume", "run": resumed}
                if msg:
                    return {"status": "message", "message": msg, "run": self.runner.saver.for_message(msg["id"])}
                left = deadline - time.time()
                if left <= 0:
                    return {"status": "timeout"}
                with self.cond:
                    self.cond.wait(min(left, 1.0))
        finally:
            with self.cond:
                self.inflight[deck] -= 1
                self.seen[deck] = time.time()

    # tools for the agent graph and the API
    def commit(self, deck: int, batch, label: str, actor: str = "ai", client: str = "agent") -> dict:
        result = self.store.commit(deck, batch, {"actor": actor, "client": client, "label": label})
        self.publish(deck, "ops", result["event"], result["seq"])
        return result

    def amend(self, deck: int, seq: int, batch: list) -> dict | None:
        """Write measured boxes into batch `seq` (no new history entry); None when it is no longer the newest."""
        try:
            result = self.store.amend(deck, seq, batch)
        except (ops.OpError, ops.Conflict):
            return None
        if result:
            self.publish(deck, "ops", result["event"], seq)
        return result

    def say(self, deck: int, text: str, meta: dict) -> dict:
        msg = self.store.add_message(deck, "ai", text, meta)
        self.publish(deck, "msg", msg)
        return msg

    def ask_confirm(self, run: dict, payload: dict) -> None:
        pages = f", 페이지 {len(payload['pages'])}개" if payload["pages"] else ""
        self.say(run["deck"], f"이 편집은 요소 {payload['deletions']}개{pages}를 지웁니다. 진행할까요?",
                 {"kind": "confirm", "run": run["id"]} | payload)

    def pins_changed(self, deck: int) -> None:
        self.publish(deck, "focus", {"pins": self.store.pins(deck)})

    def print_url(self, deck: int, pages: list[str], **params) -> str:
        extra = "".join(f"&{k}={quote(str(v))}" for k, v in params.items())
        return (f"http://127.0.0.1:{self.server.server_address[1]}/print.html?deck={deck}&pages={quote(','.join(pages))}"
                f"{extra}&token={quote(self.token)}")

    def export(self, deck: int, wanted: list, mode: str, folder: str) -> list[str]:
        pages = self.store.pages(deck)
        index = {p["id"]: (i + 1, p) for i, p in enumerate(pages)}
        wanted = wanted or [p["id"] for p in pages]
        if not isinstance(wanted, list) or any(not isinstance(w, str) or w not in index for w in wanted) or mode not in ("single", "each"):
            raise ValueError("pages는 이 문서의 page id 목록, mode는 single|each입니다.")
        name = self.store.deck(deck)["deck"]["name"]
        return pdf.export(lambda ids: self.print_url(deck, ids), name, [(index[w][0], w, index[w][1]["name"]) for w in wanted],
                          mode, folder or "~/Downloads")

    def snapshot(self, deck: int, page: str | None = None, rect: dict | None = None, ids: list[str] | None = None,
                 scale: float = 1.0) -> dict:
        """PNG of a page region (format.md §9.5) → {path, w, h}."""
        data = self.store.deck(deck)
        box = lint.boxes(data["nodes"])
        pages = [p["id"] for p in self.store.pages(deck)]
        if page is None:
            page = box[ids[0]][4] if ids and ids[0] in box else (pages[0] if pages else None)
        if page not in pages:
            raise ValueError("없는 페이지입니다.")
        pw, ph = box[page][2], box[page][3]
        if ids:
            targets = [i for i in ids if i in box and box[i][4] == page and i != page]
            by = {n["id"]: n for n in data["nodes"]}
            measured = (self.try_measure(deck, [page]) or {}) if any(any(lint.auto_sized(by[i])) for i in targets) else {}
            chosen = [(m["x"], m["y"], m["w"], m["h"]) if (m := measured.get(i)) else box[i] for i in targets]
            if not chosen:
                raise ValueError("ids가 이 페이지에 없습니다.")
            x0, y0 = min(b[0] for b in chosen) - SNAP_MARGIN, min(b[1] for b in chosen) - SNAP_MARGIN
            x1, y1 = max(b[0] + b[2] for b in chosen) + SNAP_MARGIN, max(b[1] + b[3] for b in chosen) + SNAP_MARGIN
        elif rect:
            x0, y0, x1, y1 = rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"]
        else:
            x0, y0, x1, y1 = 0, 0, pw, ph
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, pw), min(y1, ph)
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        scale = min(max(float(scale), 0.1), 4.0, SNAP_MAX / w, SNAP_MAX / h)
        folder = data_dir() / "snapshots"
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{deck}-{page}-{time.time_ns()}.png"
        rect_text = ",".join(f"{v:g}" for v in (x0, y0, w, h))
        pdf.screenshot(self.print_url(deck, [page], mode="snapshot", rect=rect_text, scale=f"{scale:g}"), out,
                       max(round(w * scale), 1), max(round(h * scale), 1))
        for old in sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[SNAP_KEEP:]:
            old.unlink(missing_ok=True)
        pw_px, ph_px = pdf.png_size(out)
        return {"path": str(out), "w": pw_px, "h": ph_px}

    def try_snapshot(self, deck: int, page: str, rect: dict | None = None, ids: list[str] | None = None) -> dict | None:
        try:
            return self.snapshot(deck, page, rect, ids)
        except (pdf.ChromeMissing, pdf.PdfError, ValueError, OSError):
            return None

    def try_measure(self, deck: int, pages: list[str]) -> dict | None:
        """Text and table boxes from print.html measure mode, or None when Chrome cannot tell."""
        try:
            return pdf.measure(self.print_url(deck, pages, mode="measure"))
        except (pdf.ChromeMissing, pdf.PdfError, ValueError, OSError):
            return None


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        # responses
        def send(self, status: int, data, kind: str = "application/json", headers: dict | None = None,
                 cache: str = "no-store", etag: bool = False) -> None:
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            texty = kind.startswith("text/") or kind in ("application/json", "image/svg+xml")
            headers = dict(headers or {})
            if texty:
                headers["Vary"] = "Accept-Encoding"
                if len(body) > GZIP_MIN and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                    body = gzip.compress(body, 5)
                    headers["Content-Encoding"] = "gzip"
            if etag:
                tag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
                headers["ETag"] = tag
                wanted = [t.strip().removeprefix("W/") for t in (self.headers.get("If-None-Match") or "").split(",")]
                if tag in wanted or "*" in wanted:
                    self.send_response(304)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Cache-Control", cache)
                    self.end_headers()
                    return
            self.send_response(status)
            self.send_header("Content-Type", kind + ("; charset=utf-8" if texty else ""))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def fail(self, status: int, body: dict) -> None:
            self.close_connection = True  # an unread request body must not be parsed as the next request
            self.send(status, body)

        # request guards
        def allowed(self) -> bool:
            """Host blocks DNS rebinding; Sec-Fetch-Site blocks other sites' pages."""
            port = self.server.server_address[1]
            return (self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")
                    and self.headers.get("Sec-Fetch-Site") != "cross-site")

        def token_ok(self) -> bool:
            return hmac.compare_digest(self.headers.get("X-PPT-Token") or "", app.token)

        def raw_body(self, limit: int) -> bytes:
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 <= size <= limit:
                raise HttpError(413, {"error": f"본문이 너무 큽니다(최대 {limit // 2**20}MB)."})
            return self.rfile.read(size) if size else b""

        def json_body(self) -> dict:
            raw = self.raw_body(MAX_JSON)
            try:
                data = json.loads(raw or b"{}", parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
            except ValueError:
                raise HttpError(400, {"error": "JSON이 아닙니다."}) from None
            if not isinstance(data, dict):
                raise HttpError(400, {"error": "JSON 객체가 아닙니다."})
            return data

        # dispatch
        def do_GET(self) -> None:
            self.dispatch("GET")

        def do_HEAD(self) -> None:
            self.dispatch("GET")

        def do_POST(self) -> None:
            self.dispatch("POST")

        def do_PATCH(self) -> None:
            self.dispatch("PATCH")

        def do_DELETE(self) -> None:
            self.dispatch("DELETE")

        def dispatch(self, method: str) -> None:
            try:
                if not self.allowed() or (method != "GET" and not self.token_ok()):
                    return self.fail(403, {"error": "forbidden"})
                if self.headers.get("X-PPT-Client") == "cli" and self.token_ok():
                    app.touched = time.time()
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                parts = [unquote(p) for p in url.path.split("/") if p]
                if parts[:1] == ["api"]:
                    return self.api(method, parts[1:], q)
                if method != "GET":
                    return self.fail(404, {"error": "not found"})
                if parts[:1] == ["assets"] and len(parts) == 2:
                    return self.asset(parts[1])
                return self.static(parts, q)
            except HttpError as exc:
                self.fail(exc.status, exc.body)
            except ops.OpError as exc:
                self.fail(400, {"error": str(exc), "index": exc.index, "key": exc.key})
            except ops.Conflict as exc:
                self.fail(409, {"error": str(exc), "conflicts": exc.conflicts})
            except NotFound:
                self.fail(404, {"error": "문서가 없습니다."})
            except pdf.ChromeMissing as exc:
                self.fail(503, {"error": str(exc), "fallback": "print"})
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                self.fail(400, {"error": f"잘못된 요청입니다: {exc}"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:  # noqa: BLE001 - callers expect one JSON object, never a dropped connection
                self.fail(500, {"error": f"편집기 서버 오류: {type(exc).__name__}: {exc}"})

        def api(self, method: str, route: list[str], q: dict) -> None:
            store = app.store
            if method == "GET":
                if route == ["health"]:
                    return self.send(200, {"ok": True, "app": APP, "version": VERSION, "pid": os.getpid()})
                if route == ["events"]:
                    return self.sse(int(q["deck"]), q)
                if route == ["wait"]:  # takes a message, so like a write it needs the token
                    if not self.token_ok():
                        return self.fail(403, {"error": "forbidden"})
                    deck = int(q["deck"])
                    store.pages(deck)  # 404 for an unknown deck
                    return self.send(200, app.wait(deck, q.get("token", ""), min(max(float(q.get("timeout", 55)), 0), 600)))
                if route == ["decks"]:
                    return self.send(200, store.decks())
            if route == ["shutdown"] and method == "POST":
                self.send(200, {"ok": True})
                return app.stop()
            if route == ["assets"] and method == "POST":
                if not (self.headers.get("Content-Type") or "").startswith(("image/", "video/")):
                    return self.fail(415, {"error": "Content-Type은 image/* 또는 video/*입니다."})
                try:
                    return self.send(200, store.put_asset(self.raw_body(MAX_UPLOAD)))
                except ValueError as exc:
                    return self.fail(415, {"error": str(exc)})
            if route == ["decks"] and method == "POST":
                data = self.json_body()
                name, preset = data.get("name") or "새 문서", data.get("preset") or "SLIDE_16_9"
                if not isinstance(name, str) or len(name) > 200 or preset not in ops.SCHEMA["presets"]:
                    return self.fail(400, {"error": "name(200자 이하)이나 preset이 맞지 않습니다.",
                                           "presets": list(ops.SCHEMA["presets"])})
                return self.send(201, {"id": store.create_deck(name, preset)})
            if route == ["sessions"] and method == "POST":  # ppt.py open --host: which AI holds this session
                data = self.json_body()
                if not isinstance(data.get("session"), str) or data.get("host") not in HOSTS:
                    return self.fail(400, {"error": f"session은 문자열, host는 {'|'.join(HOSTS)}입니다."})
                app.hosts[data["session"]] = data["host"]
                if data.get("deck") is not None:  # open --deck: the AI is here now, before its first wait
                    deck = int(data["deck"])
                    store.pages(deck)
                    with app.cond:
                        app.sessions[deck], app.seen[deck] = data["session"], time.time()
                for deck, session in list(app.sessions.items()):
                    if session == data["session"]:
                        app.ai_changed(deck)
                return self.send(200, {"ok": True})
            if len(route) < 2 or route[0] != "decks":
                return self.fail(404, {"error": "not found"})
            deck, rest = int(route[1]), route[2:]
            if method == "GET":
                return self.deck_get(deck, rest, q)
            if method == "DELETE" and not rest:
                store.delete_deck(deck)
                return self.send(200, {"ok": True})
            if method in ("PATCH", "DELETE") and len(rest) == 2 and rest[0] == "focus":
                return self.pin_change(deck, int(rest[1]), method)
            if method != "POST":
                return self.fail(404, {"error": "not found"})
            data = self.json_body()
            if rest == ["ops"]:
                meta = self.meta(data)
                result = app.commit(deck, data.get("ops"), meta["label"], meta["actor"], meta["client"])
                return self.send(200, {"seq": result["seq"], "revs": result["revs"]})
            if rest in (["undo"], ["redo"]):
                meta = self.meta(data | {"label": rest[0]})
                result = (store.undo if rest == ["undo"] else store.redo)(deck, meta)
                if result is None:
                    return self.send(200, {"seq": None})
                app.publish(deck, "ops", result["event"], result["seq"])
                return self.send(200, {"seq": result["seq"]})
            if rest == ["messages"]:
                role, text, meta = data.get("role", "user"), data.get("text", ""), data.get("meta") or {}
                if role not in ("user", "ai") or not isinstance(text, str) or len(text) > 100000 or not isinstance(meta, dict):
                    return self.fail(400, {"error": "role은 user|ai, text는 100000자 이하 문자열, meta는 객체입니다."})
                msg = store.add_message(deck, role, text, meta)
                run = app.runner.start(deck, {"message": msg}, msg["id"], text[:40]) if role == "user" else None
                app.publish(deck, "msg", msg)
                return self.send(201, {"id": msg["id"]} | ({"run": run} if run else {}))
            if rest == ["check"]:  # ppt.py check: verify without a web request
                pages = data.get("pages") or [p["id"] for p in store.pages(deck)]
                if not isinstance(pages, list) or not all(isinstance(p, str) for p in pages):
                    return self.fail(400, {"error": "pages는 page id 목록입니다."})
                return self.send(200, agent.check(app.runner.ctx, deck, pages))
            if rest == ["pdf"]:
                return self.send(200, {"files": app.export(deck, data.get("pages") or [], data.get("mode") or "single",
                                                           data.get("dir") or "~/Downloads")})
            if rest == ["focus"]:
                return self.pin_add(deck, data)
            if len(rest) == 3 and rest[0] == "runs":
                run = self.run_of(deck, int(rest[1]))
                try:
                    if rest[2] == "next":
                        return self.send(200, app.runner.next(run["id"]))
                    if rest[2] == "submit":
                        return self.send(200, app.runner.submit(run["id"], data.get("node"), data.get("output")))
                    if rest[2] == "undo":
                        seqs = run["state"].get("applied_seqs", [])
                        if not seqs:
                            return self.fail(409, {"error": "이 실행이 바꾼 내용이 없습니다."})
                        events = store.undo_run(deck, seqs, self.meta(data | {"label": "undo"}))
                        if events is None:
                            return self.fail(409, {"error": "이후 다른 변경이 있어 되돌릴 수 없습니다."})
                        for event in events:
                            app.publish(deck, "ops", event["event"], event["seq"])
                        return self.send(200, {"seq": events[-1]["seq"], "undone": seqs})
                    if rest[2] == "confirm":
                        if not isinstance(data.get("ok"), bool):
                            return self.fail(400, {"error": "ok는 true/false입니다."})
                        return self.send(200, app.runner.resume(run["id"], data["ok"]))
                except agent.StepError as exc:
                    return self.fail(409 if rest[2] == "confirm" else 400, {"error": str(exc)})
            return self.fail(404, {"error": "not found"})

        def deck_get(self, deck: int, rest: list[str], q: dict) -> None:
            store = app.store
            if not rest:
                return self.send(200, store.deck(deck))
            if rest == ["outline"]:
                data = store.deck(deck)
                return self.send(200, ops.outline(data["deck"], data["nodes"], q.get("page")).encode(), "text/plain")
            if rest == ["nodes"]:
                got = store.nodes(deck, ids=[i for i in q.get("ids", "").split(",") if i],
                                  pages=[q["page"]] if q.get("page") else None)
                return self.send(200, {"seq": got["seq"], "nodes": got["nodes"]})
            if rest == ["messages"]:
                return self.send(200, store.messages(deck))
            if rest == ["ai"]:
                store.pages(deck)
                return self.send(200, app.ai_status(deck))
            if rest == ["focus"]:
                return self.send(200, store.pins(deck))
            if rest == ["runs"]:
                store.pages(deck)
                return self.send(200, app.runner.saver.runs(deck, min(int(q.get("limit", 20)), 200)))
            if len(rest) == 2 and rest[0] == "runs":
                run = self.run_of(deck, int(rest[1]))
                return self.send(200, {"run": agent.Checkpointer.summary(run) | {"message_id": run["message_id"]},
                                       "state": run["state"], "steps": app.runner.saver.steps(run["id"])})
            if rest == ["snapshot"]:  # launches Chrome and writes a file, so like a write it needs the token
                if not self.token_ok():
                    return self.fail(403, {"error": "forbidden"})
                rect = None
                if q.get("rect"):
                    x, y, w, h = (float(v) for v in q["rect"].split(","))
                    rect = {"x": x, "y": y, "w": w, "h": h}
                ids = [i for i in q.get("ids", "").split(",") if i] or None
                return self.send(200, app.snapshot(deck, q.get("page") or None, rect, ids, float(q.get("scale", 1))))
            return self.fail(404, {"error": "not found"})

        def run_of(self, deck: int, run_id: int) -> dict:
            run = app.runner.saver.load(run_id)
            if run is None or run["deck"] != deck:
                raise HttpError(404, {"error": "실행이 없습니다."})
            return run

        def pin_add(self, deck: int, data: dict) -> None:
            pages = [p["id"] for p in app.store.pages(deck)]
            ids, rect, note = data.get("ids") or [], data.get("rect"), data.get("note") or ""
            ok = data.get("page") in pages and isinstance(ids, list) and len(ids) <= 1000 and all(isinstance(i, str) for i in ids)
            ok = ok and isinstance(note, str) and len(note) <= 2000
            ok = ok and (rect is None or isinstance(rect, dict) and set(rect) == {"x", "y", "w", "h"}
                         and all(ops.is_num(v) for v in rect.values()) and rect["w"] >= 0 and rect["h"] >= 0)
            if not ok:
                return self.fail(400, {"error": "page는 이 문서의 page id, ids는 id 목록, rect는 {x,y,w,h}, note는 2000자 이하입니다."})
            pin = app.store.add_pin(deck, data["page"], ids, rect, note)
            app.pins_changed(deck)
            return self.send(201, {"id": pin})

        def pin_change(self, deck: int, pin: int, method: str) -> None:
            if method == "DELETE":
                found = app.store.delete_pin(deck, pin)
            else:
                data = self.json_body()
                note, status = data.get("note"), data.get("status")
                if (note is not None and (not isinstance(note, str) or len(note) > 2000)) or (status is not None and status not in FOCUS_STATUS):
                    return self.fail(400, {"error": f"note는 2000자 이하, status는 {'|'.join(FOCUS_STATUS)}입니다."})
                found = app.store.update_pin(deck, pin, note, status)
            if not found:
                return self.fail(404, {"error": "핀이 없습니다."})
            app.pins_changed(deck)
            return self.send(200, {"ok": True})

        @staticmethod
        def meta(data: dict) -> dict:
            meta = {"actor": data.get("actor", "user"), "client": data.get("client") or "", "label": data.get("label") or ""}
            if meta["actor"] not in ("user", "ai") or not all(isinstance(meta[k], str) for k in ("client", "label")) \
                    or len(meta["client"]) > 64 or len(meta["label"]) > 200:
                raise HttpError(400, {"error": "actor는 user|ai, client는 64자, label은 200자 이하 문자열입니다."})
            return meta

        # files
        def static(self, parts: list[str], q: dict) -> None:
            rel = "/".join(parts) or "index.html"
            ok = (rel in STATIC_FILES or (len(parts) > 1 and parts[0] in STATIC_ROOTS)) \
                and not any(p in (".", "..") or "/" in p or "\\" in p for p in parts)
            target = (WEB / rel).resolve()
            if not ok or WEB.resolve() not in target.parents or not target.is_file():
                return self.fail(404, {"error": "not found"})
            body = target.read_bytes()
            kind = TYPES.get(target.suffix, "application/octet-stream")
            if rel == "print.html" and q.get("deck"):
                return self.send(200, inject(body.decode(), app.token, self.print_data(int(q["deck"]), q)).encode(), kind)
            if rel in ("index.html", "print.html"):
                body = inject(body.decode(), app.token).encode()
            return self.send(200, body, kind, cache="no-cache", etag=True)

        @staticmethod
        def print_data(deck: int, q: dict) -> dict:
            pages = [p["id"] for p in app.store.pages(deck)]
            wanted = [p for p in q.get("pages", "").split(",") if p] or pages
            if any(p not in pages for p in wanted):
                raise HttpError(404, {"error": "없는 페이지입니다."})
            got = app.store.nodes(deck, pages=wanted)
            return {"deck": got["deck"], "pages": wanted, "nodes": got["nodes"], "assets": asset_hashes(got["nodes"])}

        def asset(self, digest: str) -> None:
            row = app.store.asset(digest) if HASH.fullmatch(digest) else None
            if row is None:
                return self.fail(404, {"error": "에셋이 없습니다."})
            headers = {"ETag": f'"{digest}"', "Accept-Ranges": "bytes"}
            cache = "public, max-age=31536000, immutable"
            if f'"{digest}"' in (self.headers.get("If-None-Match") or ""):
                self.send_response(304)
                self.send_header("ETag", headers["ETag"])
                self.send_header("Cache-Control", cache)
                self.end_headers()
                return None
            data, size = row["data"], len(row["data"])
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if m and (m[1] or m[2]):  # one range, for <video> seeking (Safari needs it)
                start, end = (int(m[1]), int(m[2] or size - 1)) if m[1] else (max(size - int(m[2]), 0), size - 1)
                if start >= size or start > end:
                    return self.send(416, b"", "application/octet-stream", {"Content-Range": f"bytes */{size}"}, cache)
                end = min(end, size - 1)
                return self.send(206, data[start:end + 1], row["mime"], headers | {"Content-Range": f"bytes {start}-{end}/{size}"}, cache)
            return self.send(200, data, row["mime"], headers, cache)

        # events
        def gone(self) -> bool:
            """An event stream client never sends after its request, so a readable socket means it closed."""
            try:
                ready, _, _ = select.select([self.connection], [], [], 0)
                return bool(ready) and self.connection.recv(1, socket.MSG_PEEK) == b""
            except OSError:
                return True

        def event(self, name: str, data: dict, seq: int | None = None) -> None:
            head = f"id: {seq}\n" if seq is not None else ""
            self.wfile.write(f"{head}event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())

        def sse(self, deck: int, q: dict) -> None:
            app.store.pages(deck)  # 404 for an unknown deck, before the stream starts
            last = self.headers.get("Last-Event-ID") or q.get("last")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.close_connection = True
            with app.cond:
                app.clients += 1
                app.ever = True
                seen = app.n
            try:
                self.wfile.write(b"retry: 1000\n: open\n\n")
                sent = None
                if last not in (None, ""):
                    replay = app.store.replay(deck, int(last)) if last.isdigit() else None
                    if replay is None:
                        self.event("reset", {})
                    for ev in replay or []:
                        self.event("ops", ev, ev["seq"])
                        sent = ev["seq"]
                self.wfile.flush()
                quiet = time.monotonic()
                while not self.gone():
                    with app.cond:
                        if app.n == seen and not app.closing:
                            app.cond.wait(1.0)
                        closing = app.closing
                        lost = bool(app.bus) and app.bus[0][0] > seen + 1
                        fresh = [e for e in app.bus if e[0] > seen and e[1] == deck]
                        seen = app.n
                    if closing:
                        self.event("closing", {})
                        self.wfile.flush()
                        return
                    if lost:
                        self.event("reset", {})
                    for _, _, name, data, seq in fresh:
                        if seq is not None and sent is not None and seq <= sent and not data.get("amend"):
                            continue  # already replayed (an amend is idempotent, so it always goes out)
                        self.event(name, data, seq)
                    if fresh or lost:
                        quiet = time.monotonic()
                    elif time.monotonic() - quiet >= PING:
                        self.wfile.write(b": ping\n\n")
                        quiet = time.monotonic()
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                with app.cond:
                    app.clients -= 1

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64  # a browser loads dozens of ES modules at once; the default backlog of 5 resets them


def persistent_token() -> str:
    """One token per data dir (~/.clonamic/ai-html-ppt/token, 0600), so open tabs keep working across server restarts."""
    path = data_dir() / "token"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        token = path.read_text().strip()
        if len(token) >= 24:
            return token
        path.unlink()  # empty or damaged: make a new one
        return persistent_token()
    token = secrets.token_urlsafe(24)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    return token


def serve(port: int, grace: float = 10.0, first: float = 180.0, store: Store | None = None, token: str | None = None):
    """Bound server and its App; the caller runs serve_forever()."""
    app = App(store or Store(), token or persistent_token(), grace, first)
    server = Server(("127.0.0.1", port), make_handler(app))
    app.server = server
    threading.Thread(target=app.watch, daemon=True).start()
    return server, app


def write_info(path: Path, info: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(info, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def run(port: int, grace: float, first: float) -> None:
    server, app = serve(port, grace, first)
    info_path = data_dir() / "server.json"
    write_info(info_path, {"port": port, "pid": os.getpid(), "token": app.token, "started": time.time()})
    signal.signal(signal.SIGTERM, lambda *_: app.stop())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if json.loads(info_path.read_text()).get("pid") == os.getpid():
                info_path.unlink()
        except (OSError, ValueError):
            pass
        server.server_close()
        app.store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--grace", type=float, default=10.0)
    parser.add_argument("--first", type=float, default=180.0)
    args = parser.parse_args()
    run(args.port, args.grace, args.first)


if __name__ == "__main__":
    main()
