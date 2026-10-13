"""Editor server: static web page, JSON API, chat queue for the waiting AI, SSE for open tabs.

Lifetime = the browser tabs: once a tab has connected, the server stops shortly after the last one closes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import select
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import checks
import exporter
import render
import schema
from store import Conflict, Store, data_dir

VERSION = "0.1.0"
APP = "clonamic-create-agent"
WEB = Path(__file__).resolve().parent.parent / "assets" / "web"
MAX_BODY = 5_000_000
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml"}


def today() -> str:
    return dt.date.today().isoformat()


class App:
    def __init__(self, store: Store, grace: float = 10.0, first: float = 180.0):
        self.store, self.grace, self.first = store, grace, first
        self.cond = threading.Condition()
        self.events: deque = deque(maxlen=200)
        self.seq = 0
        self.clients = 0
        self.ever = False
        self.closing = False
        self.tokens: dict[int, str] = {}
        self.seen: dict[int, float] = {}

    def emit(self, kind: str, pid: int) -> None:
        with self.cond:
            self.seq += 1
            self.events.append((self.seq, {"type": kind, "project": pid}))
            self.cond.notify_all()

    def watch(self, server: ThreadingHTTPServer) -> None:
        """Stop after the last tab closes (grace), or if no tab ever connects (first)."""
        started, empty_since = time.time(), None
        while True:
            time.sleep(0.5)
            with self.cond:
                clients, ever = self.clients, self.ever
            now = time.time()
            if clients:
                empty_since = None
                continue
            empty_since = empty_since or now
            if (ever and now - empty_since >= self.grace) or (not ever and now - started >= self.first):
                with self.cond:
                    if self.clients:  # a tab opened just now
                        empty_since = None
                        continue
                    self.closing = True
                    self.cond.notify_all()
                time.sleep(0.3)
                server.shutdown()
                return

    def wait(self, pid: int, token: str, timeout: float) -> dict:
        """Next unhandled message. Ends only with a message, a timeout (call again), closed, or replaced."""
        with self.cond:
            self.tokens[pid] = token
        deadline = time.time() + timeout
        while True:
            with self.cond:
                self.seen[pid] = time.time()
                if self.closing:
                    return {"status": "closed"}
                if self.tokens.get(pid) != token:
                    return {"status": "replaced"}
                msg = self.store.take(pid)  # under the same lock as the token check, so a replaced waiter takes nothing
            if msg:
                return {"status": "message", "message": msg}
            left = deadline - time.time()
            if left <= 0:
                return {"status": "timeout"}
            with self.cond:
                self.cond.wait(min(left, 1.0))


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        # helpers
        def send(self, status: int, data, kind: str = "application/json") -> None:
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def body(self) -> dict:
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 <= size <= MAX_BODY:
                raise ValueError("body size")
            data = json.loads(self.rfile.read(size) or b"{}") if size else {}
            if not isinstance(data, dict):
                raise ValueError("not an object")
            return data

        def allowed(self) -> bool:
            """Only this machine's page or CLI: the Host blocks DNS rebinding, Sec-Fetch-Site blocks other sites' pages."""
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost") and self.headers.get("Sec-Fetch-Site") != "cross-site"

        def deny(self) -> None:
            self.close_connection = True  # an unread request body must not be parsed as the next request
            self.send(403, {"error": "forbidden"})

        def project(self, pid: int) -> dict | None:
            proj = app.store.get(pid)
            if not proj:
                self.send(404, {"error": "프로젝트가 없습니다."})
            return proj

        # routing
        def do_GET(self) -> None:
            try:
                self.get()
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                self.send(400, {"error": f"잘못된 요청입니다: {exc}"})
            except Exception as exc:  # noqa: BLE001 - the CLI expects one JSON object, never a dropped connection
                self.send(500, {"error": f"편집기 서버 오류: {exc}"})

        def get(self) -> None:
            if not self.allowed():
                return self.deny()
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            parts = [p for p in url.path.split("/") if p]
            if not parts or parts[0] != "api":
                return self.static(url.path)
            route = parts[1:]
            if route == ["health"]:
                return self.send(200, {"app": APP, "version": VERSION, "data_dir": str(data_dir())})
            if route == ["schema"]:
                return self.send(200, schema.SCHEMA)
            if route == ["events"]:
                return self.sse()
            if route == ["wait"]:  # takes a message, so like a write it needs the CLI's header
                if self.headers.get("X-Clonamic") != "1":
                    return self.deny()
                pid = int(q.get("project", 0))
                if not self.project(pid):
                    return None
                return self.send(200, app.wait(pid, q.get("token", ""), min(float(q.get("timeout", 55)), 600)))
            if route == ["projects"]:
                return self.send(200, app.store.projects())
            if len(route) >= 2 and route[0] == "projects":
                pid = int(route[1])
                proj = self.project(pid)
                if not proj:
                    return None
                rest = route[2:]
                if not rest:
                    proj["ai_seen"] = round(time.time() - app.seen[pid], 1) if pid in app.seen else None
                    proj["default_path"] = "~/Documents/clonamic-agents/" + render.slug(proj["doc"].get("name", ""))
                    return self.send(200, proj)
                if rest == ["messages"]:
                    return self.send(200, app.store.messages(pid, int(q.get("after", 0))))
                if rest == ["check"]:
                    return self.send(200, {"issues": checks.run(proj["doc"])})
                if rest == ["preview"]:
                    files = render.render(proj["doc"], app.store.changelog(pid), today(), proj["polished"])
                    path = render.path_for(proj["doc"], q.get("target", "project"))
                    return self.send(200, {"path": path, "text": files.get(path, "")})
                if rest == ["design"]:
                    files = render.render(proj["doc"], app.store.changelog(pid), today(), proj["polished"])
                    return self.send(200, files["design.json"].encode(), "application/json")
            return self.send(404, {"error": "not found"})

        def do_POST(self) -> None:
            self.mutate("POST")

        def do_PUT(self) -> None:
            self.mutate("PUT")

        def do_DELETE(self) -> None:
            self.mutate("DELETE")

        def mutate(self, method: str) -> None:
            # A custom header cannot be sent cross-site without a CORS preflight, which this server never answers.
            if not self.allowed() or self.headers.get("X-Clonamic") != "1":
                return self.deny()
            try:
                data = self.body()
            except ValueError:
                self.close_connection = True
                return self.send(400, {"error": "JSON 객체가 아니거나 너무 큽니다."})
            route = [p for p in urlparse(self.path).path.split("/") if p][1:]
            try:
                self.route(method, route, data)
            except exporter.ExportError as exc:
                self.send(400, {"error": str(exc)})
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                self.send(400, {"error": f"잘못된 요청입니다: {exc}"})
            except Exception as exc:  # noqa: BLE001
                self.send(500, {"error": f"편집기 서버 오류: {exc}"})

        def route(self, method: str, route: list[str], data: dict) -> None:
            store = app.store
            if method == "POST" and route == ["projects"]:
                name = (data.get("name") or "새 프로젝트").strip()
                pid = store.create(name)
                app.emit("projects", pid)
                return self.send(201, {"id": pid})
            if method == "POST" and route == ["projects", "import"]:
                doc = exporter.load_design(data.get("text", ""))
                if err := schema.shape_error(schema.migrate(doc)):
                    return self.send(400, {"error": err})
                pid = store.create(doc.get("name", ""), doc)
                app.emit("projects", pid)
                return self.send(201, {"id": pid})
            if len(route) == 3 and route[0] == "cards" and method == "POST" and route[2] in ("apply", "dismiss"):
                return self.card(int(route[1]), route[2])
            if len(route) < 2 or route[0] != "projects":
                return self.send(404, {"error": "not found"})
            pid = int(route[1])
            proj = self.project(pid)
            if not proj:
                return None
            rest = route[2:]
            if method == "DELETE" and not rest:
                store.delete(pid)
                app.emit("projects", pid)
                return self.send(200, {"ok": True})
            if method == "PUT" and not rest:
                if isinstance(data.get("doc"), dict):
                    schema.migrate(data["doc"])
                if err := schema.shape_error(data.get("doc")):
                    return self.send(400, {"error": err})
                try:
                    version = store.save(pid, data["doc"], int(data["version"]))
                except Conflict as exc:
                    return self.send(409, {"error": "다른 곳에서 먼저 바뀌었습니다.", "version": exc.args[0]})
                if data.get("note"):
                    store.log(pid, today(), data["note"], data.get("why", ""), data.get("affected", ""))
                app.emit("project", pid)
                return self.send(200, {"version": version})
            if method == "POST" and rest == ["messages"]:
                role = data.get("role", "user")
                if role not in ("user", "ai"):
                    return self.send(400, {"error": "role"})
                status = "new" if role == "user" else ""
                mid = store.add_message(pid, role, "text", {"text": data.get("text", "")}, status)
                app.emit("message", pid)
                return self.send(201, {"id": mid})
            if method == "POST" and rest == ["cards"]:
                if isinstance(data.get("doc"), dict):
                    schema.migrate(data["doc"])
                if err := schema.shape_error(data.get("doc")):
                    return self.send(400, {"error": "제안의 doc: " + err})
                card = {k: data.get(k) for k in ("title", "criterion", "reason", "targets", "changes", "effect", "rejected")}
                card |= {"kind": data.get("kind", "review"), "doc": data["doc"], "base_version": int(data["base_version"])}
                mid = store.add_message(pid, "ai", "card", card, "pending")
                app.emit("message", pid)
                return self.send(201, {"id": mid})
            if method == "POST" and rest == ["polish"]:
                mid = store.add_message(pid, "user", "polish", {"text": "한국어 다듬기 요청"}, "new")
                app.emit("message", pid)
                return self.send(201, {"id": mid})
            if method == "POST" and rest == ["export"]:
                issues = checks.run(proj["doc"])
                if issues:
                    return self.send(422, {"error": "검사를 통과하지 못했습니다.", "issues": issues})
                path = (data.get("path") or proj["export_path"] or "").strip()
                if not path:
                    return self.send(400, {"error": "저장 경로가 필요합니다."})
                files = render.render(proj["doc"], store.changelog(pid), today(), proj["polished"])
                if data.get("dry"):
                    return self.send(200, exporter.plan(path, files))
                result = exporter.write(path, files)
                store.set_export_path(pid, path)
                return self.send(200, result | {"polished": proj["polished"]})
            return self.send(404, {"error": "not found"})

        def card(self, mid: int, action: str) -> None:
            store = app.store
            msg = store.message(mid)
            if not msg or msg["kind"] != "card" or msg["status"] != "pending":
                return self.send(404, {"error": "적용할 수 있는 제안이 아닙니다."})
            pid, card = msg["project_id"], msg["body"]
            if action == "dismiss":
                store.set_status(mid, "dismissed")
                app.emit("message", pid)
                return self.send(200, {"ok": True})
            proj = store.get(pid)
            if not proj or proj["version"] != card["base_version"]:
                return self.send(409, {"error": "설계가 바뀌어 이 제안을 적용할 수 없습니다. 다시 제안을 요청하세요."})
            doc = card["doc"]
            polish = card.get("kind") == "polish"
            if not polish:
                doc.setdefault("decisions", []).append(
                    {"decision": card.get("title") or "", "why": card.get("reason") or "", "rejected": card.get("rejected") or ""})
            try:
                version = store.save(pid, doc, proj["version"], polished=polish)
            except Conflict:
                return self.send(409, {"error": "설계가 바뀌어 이 제안을 적용할 수 없습니다. 다시 제안을 요청하세요."})
            store.log(pid, today(), card.get("title") or "", card.get("reason") or "", ", ".join(card.get("targets") or []))
            store.set_status(mid, "applied")
            app.emit("project", pid)
            app.emit("message", pid)
            return self.send(200, {"version": version})

        def static(self, path: str) -> None:
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB / rel).resolve()
            if WEB.resolve() not in target.parents or not target.is_file():
                return self.send(404, b"not found", "text/plain")
            return self.send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

        def gone(self) -> bool:
            """An event stream client never sends after its request, so a readable socket means it closed."""
            try:
                ready, _, _ = select.select([self.connection], [], [], 0)
                return bool(ready) and self.connection.recv(1, socket.MSG_PEEK) == b""
            except OSError:
                return True

        def sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.close_connection = True
            with app.cond:
                app.clients += 1
                app.ever = True
                last = app.seq
            try:
                self.wfile.write(b": open\n\n")
                self.wfile.flush()
                quiet = 0.0
                while not self.gone():
                    with app.cond:
                        if app.seq == last and not app.closing:
                            app.cond.wait(1.0)
                        if app.closing:
                            return
                        fresh = [e for s, e in app.events if s > last]
                        last = app.seq
                    for event in fresh:
                        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    quiet = 0.0 if fresh else quiet + 1.0
                    if quiet >= 15:
                        self.wfile.write(b": ping\n\n")
                        quiet = 0.0
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                with app.cond:
                    app.clients -= 1

    return Handler


def serve(port: int, grace: float = 10.0, first: float = 180.0, store: Store | None = None):
    app = App(store or Store(), grace, first)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    server.daemon_threads = True
    threading.Thread(target=app.watch, args=(server,), daemon=True).start()
    return server, app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--grace", type=float, default=10.0)
    parser.add_argument("--first", type=float, default=180.0)
    args = parser.parse_args()
    server, _ = serve(args.port, args.grace, args.first)
    server.serve_forever()


if __name__ == "__main__":
    main()
