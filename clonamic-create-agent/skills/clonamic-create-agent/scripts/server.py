"""Editor server: static web page, JSON API, chat queue for the waiting AI, SSE for open tabs.

Lifetime = the browser tabs: once a tab has connected, the server stops shortly after the last one closes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import select
import sys
import traceback
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import checks
import exporter
import patch
import render
import schema
from store import Conflict, Store, code_hash, data_dir

VERSION = schema.VERSION
APP = "clonamic-create-agent"
WEB = Path(__file__).resolve().parent.parent / "assets" / "web"
MAX_BODY = 5_000_000
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml"}


def today() -> str:
    return dt.date.today().isoformat()


class BadRequest(ValueError):
    """A request the caller can fix; the message is shown as is."""


def num(text, what: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        raise BadRequest(f"{what} 번호는 숫자여야 합니다.") from None


def wait_seconds(text) -> float:
    """1~600 seconds; anything unreadable (nan, inf, words) waits the usual 55."""
    try:
        t = float(text)
    except (TypeError, ValueError):
        t = 55.0
    return max(1.0, min(t if math.isfinite(t) else 55.0, 600.0))


def without_layout(doc: dict) -> str:
    return json.dumps({k: v for k, v in doc.items() if k != "layout"}, sort_keys=True, ensure_ascii=False)


def default_path(proj: dict) -> str:
    return f"~/Documents/clonamic-agents/{render.slug(proj['doc'].get('name', ''))}-{proj['id']}"


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
        self.waiting: dict[int, int] = {}  # project -> waits in flight
        self.code = code_hash()

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
            self.waiting[pid] = self.waiting.get(pid, 0) + 1
        deadline = time.time() + timeout
        try:
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
        finally:
            with self.cond:
                self.waiting[pid] -= 1
                self.seen[pid] = time.time()


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        # helpers
        def fail(self, status: int, message: str) -> None:
            """An error answer; a client that already went away gets nothing."""
            try:
                self.send(status, {"error": message})
            except (BrokenPipeError, ConnectionResetError):
                pass

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
            except (BrokenPipeError, ConnectionResetError):
                pass
            except BadRequest as exc:
                self.fail(400, str(exc))
            except (ValueError, KeyError, TypeError, AttributeError):
                self.fail(400, "잘못된 요청입니다.")
            except Exception:  # noqa: BLE001 - the CLI expects one JSON object, never a dropped connection
                traceback.print_exc(file=sys.stderr)  # server.log keeps the details; the answer does not
                self.fail(500, "편집기 서버 오류가 났습니다. server.log를 확인하세요.")

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
                return self.send(200, {"app": APP, "version": VERSION, "data_dir": str(data_dir()), "code": app.code})
            if route == ["schema"]:
                return self.send(200, schema.SCHEMA)
            if route == ["events"]:
                return self.sse()
            if route == ["wait"]:  # takes a message, so like a write it needs the CLI's header
                if self.headers.get("X-Clonamic") != "1":
                    return self.deny()
                pid = num(q.get("project", 0), "프로젝트")
                if not self.project(pid):
                    return None
                return self.send(200, app.wait(pid, q.get("token", ""), wait_seconds(q.get("timeout", 55))))
            if route == ["projects"]:
                return self.send(200, app.store.projects())
            if len(route) >= 2 and route[0] == "projects":
                pid = num(route[1], "프로젝트")
                proj = self.project(pid)
                if not proj:
                    return None
                rest = route[2:]
                if not rest:
                    proj["ai_seen"] = round(time.time() - app.seen[pid], 1) if pid in app.seen else None
                    proj["ai_waiting"] = app.waiting.get(pid, 0) > 0
                    proj["default_path"] = default_path(proj)
                    return self.send(200, proj)
                if rest == ["messages"]:
                    return self.send(200, app.store.messages(pid, num(q.get("after", 0), "메시지")))
                if rest == ["check"]:
                    return self.send(200, {"issues": checks.run(proj["doc"])})
                if rest == ["preview"]:
                    files = render.render(proj["doc"], app.store.changelog(pid), today(), proj["polished"])
                    path = render.path_for(proj["doc"], q.get("target", "project"))
                    text = files.get(path, "")
                    if path and not text and render.inner_edge(proj["doc"], q.get("target", "")):
                        text = "이 연결은 조건이나 반복이 없어 따로 파일을 만들지 않습니다. 출발 단계 문서의 ‘다음 연결’ 표에 한 줄로 들어갑니다."
                    return self.send(200, {"path": path, "text": text})
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
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (exporter.ExportError, BadRequest) as exc:
                self.fail(400, str(exc))
            except (ValueError, KeyError, TypeError, AttributeError):
                self.fail(400, "잘못된 요청입니다. 보낸 값의 형식을 확인하세요.")
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
                self.fail(500, "편집기 서버 오류가 났습니다. server.log를 확인하세요.")

        def route(self, method: str, route: list[str], data: dict) -> None:
            store = app.store
            if method == "POST" and route == ["projects"]:
                pid = store.create(schema.clean_name(data.get("name"), "새 프로젝트"))
                app.emit("projects", pid)
                return self.send(201, {"id": pid})
            if method == "POST" and route == ["projects", "import"]:
                doc = exporter.load_design(data.get("text", ""))
                if err := schema.basic_error(doc) or schema.shape_error(schema.migrate(doc)):
                    return self.send(400, {"error": err})
                doc["name"] = schema.clean_name(doc.get("name"), "가져온 프로젝트")
                pid = store.create(doc["name"], doc)
                app.emit("projects", pid)
                return self.send(201, {"id": pid})
            if len(route) == 3 and route[0] == "cards" and method == "POST" and route[2] in ("apply", "dismiss"):
                return self.card(num(route[1], "제안"), route[2], data.get("keys"))
            if len(route) < 2 or route[0] != "projects":
                return self.send(404, {"error": "not found"})
            pid = num(route[1], "프로젝트")
            proj = self.project(pid)
            if not proj:
                return None
            rest = route[2:]
            if method == "DELETE" and not rest:
                store.delete(pid)
                app.emit("projects", pid)
                return self.send(200, {"ok": True})
            if method == "PUT" and not rest:
                return self.put(pid, proj, data)
            if method == "POST" and rest == ["messages"]:
                role = data.get("role", "user")
                if role not in ("user", "ai"):
                    return self.send(400, {"error": "role"})
                status = "new" if role == "user" else ""
                mid = store.add_message(pid, role, "text", {"text": data.get("text", "")}, status)
                app.emit("message", pid)
                return self.send(201, {"id": mid})
            if method == "POST" and rest == ["cards"]:
                if err := schema.basic_error(data.get("doc")) or schema.shape_error(schema.migrate(data["doc"])):
                    return self.send(400, {"error": "제안의 doc: " + err})
                base = store.at_version(pid, num(data.get("base_version"), "기준 버전"))
                if base is None:
                    return self.send(409, {"error": "제안의 base_version이 너무 오래됐습니다. get으로 다시 받아 제안하세요.", "version": proj["version"]})
                card = {k: data.get(k) for k in ("title", "criterion", "reason", "targets", "changes", "effect", "rejected")}
                card |= {"kind": data.get("kind", "review"), "base_version": int(data["base_version"]), "patch": patch.diff(base, data["doc"]),
                         "checked": data.get("checked") is True}
                mid = store.add_message(pid, "ai", "card", card, "pending")
                app.emit("message", pid)
                return self.send(201, {"id": mid})
            if method == "POST" and rest == ["polish"]:
                mid = store.add_message(pid, "user", "polish", {"text": "한국어 다듬기 요청"}, "new")
                app.emit("message", pid)
                return self.send(201, {"id": mid})
            if method == "POST" and rest == ["export"]:
                # The path is checked first, so a bad path shows up even while the design still has issues.
                path = (data.get("path") or proj["export_path"] or "").strip()
                if not path:
                    return self.send(400, {"error": "저장 경로가 필요합니다."})
                issues = checks.run(proj["doc"])
                errors = checks.errors(issues)
                draft = bool(errors) and data.get("draft") is True  # a draft says so at the top of README
                files = render.render(proj["doc"], store.changelog(pid), today(), proj["polished"], len(errors) if draft else 0)
                info = exporter.plan(path, files) | {"issues": issues, "errors": len(errors)}
                if data.get("dry"):
                    return self.send(200, info)
                if errors and not draft:
                    return self.send(422, {"error": f"검사 오류 {len(errors)}개가 있습니다. 고치거나 초안으로 내보내세요.", "issues": issues})
                result = exporter.write(path, files)
                store.set_export_path(pid, path)
                return self.send(200, result | {"polished": proj["polished"], "draft": draft})
            return self.send(404, {"error": "not found"})

        def card(self, mid: int, action: str, keys: list | None = None) -> None:
            """Apply the chosen units of a card's patch (all when `keys` is None) onto the current document."""
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
            if not proj:
                return self.send(404, {"error": "프로젝트가 없습니다."})
            if keys is not None and not (isinstance(keys, list) and all(isinstance(k, str) for k in keys)):
                return self.send(400, {"error": "keys는 문자열 목록이어야 합니다."})
            items = card.get("patch")
            if items is None:  # a card stored before patches existed carries the whole document
                base = store.at_version(pid, card["base_version"])
                if base is None:
                    return self.send(409, {"error": "설계가 바뀌어 이 제안을 적용할 수 없습니다. 다시 제안을 요청하세요."})
                items = patch.diff(base, card["doc"])
            chosen = items if keys is None else [it for it in items if it["key"] in set(keys)]
            if items and not chosen:
                return self.send(400, {"error": "적용할 항목을 하나 이상 고르세요."})
            try:
                doc, conflicts = patch.apply(proj["doc"], chosen)
            except KeyError as exc:
                return self.send(409, {"error": exc.args[0]})
            if conflicts:
                return self.send(409, {"error": "제안 뒤에 바뀐 곳이 있어 적용할 수 없습니다: " + ", ".join(conflicts)
                                       + ". 그 항목을 빼고 적용하거나 다시 제안을 요청하세요.", "conflicts": conflicts})
            if err := schema.shape_error(doc):
                return self.send(409, {"error": "고른 항목만으로는 문서가 맞지 않습니다: " + err})
            polish = card.get("kind") == "polish"  # only a polish checked by clonamic-korean counts as done
            if not polish:
                doc.setdefault("decisions", []).append(
                    {"decision": card.get("title") or "", "why": card.get("reason") or "", "rejected": card.get("rejected") or ""})
            try:
                version = store.save(pid, doc, proj["version"], polished=polish and card.get("checked") is True and len(chosen) == len(items))
            except Conflict:
                return self.send(409, {"error": "설계가 바뀌어 이 제안을 적용할 수 없습니다. 다시 제안을 요청하세요."})
            store.log(pid, today(), card.get("title") or "", card.get("reason") or "",
                      ", ".join(dict.fromkeys(it["target"] for it in chosen)) or ", ".join(card.get("targets") or []))
            store.set_status(mid, "applied")
            app.emit("project", pid)
            app.emit("message", pid)
            return self.send(200, {"version": version})

        def put(self, pid: int, proj: dict, data: dict) -> None:
            """Save. A save made from an older version is merged onto the current one when the two touched
            different things (patch units); otherwise 409 lists what both changed."""
            store = app.store
            doc = data.get("doc")
            if err := schema.basic_error(doc) or schema.shape_error(schema.migrate(doc)):
                return self.send(400, {"error": err})
            version, merged = num(data.get("version"), "버전"), False
            before = proj["doc"]
            keep = proj["polished"] and proj["version"] == version and without_layout(before) == without_layout(doc)
            try:
                new = store.save(pid, doc, version, polished=keep)  # moving cards keeps a polish
            except Conflict as exc:
                base = store.at_version(pid, version)
                if base is None:
                    return self.send(409, {"error": "다른 곳에서 먼저 바뀌었습니다.", "version": exc.args[0], "conflicts": []})
                cur = store.get(pid)
                doc, conflicts = patch.merge(base, doc, cur["doc"])
                if conflicts or schema.shape_error(doc):
                    return self.send(409, {"error": "다른 곳에서 같은 곳을 먼저 고쳤습니다.", "version": cur["version"], "conflicts": conflicts})
                before = cur["doc"]
                try:
                    new = store.save(pid, doc, cur["version"])
                except Conflict as again:
                    return self.send(409, {"error": "다른 곳에서 먼저 바뀌었습니다.", "version": again.args[0], "conflicts": []})
                merged = True
            if data.get("note"):
                affected = data.get("affected") or ", ".join(dict.fromkeys(it["target"] for it in patch.diff(before, doc)))
                store.log(pid, today(), data["note"], data.get("why", ""), affected)
            app.emit("project", pid)
            return self.send(200, {"version": new, "merged": merged, "polished": keep and not merged})

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
