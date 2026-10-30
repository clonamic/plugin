"""Local dashboard (readability). 127.0.0.1 only, standard library only.

Reads each project's SQLite (WAL, so it never blocks the organisation) and a
few files under .claude/fde-mode/. Writes are few and never reach Claude Code:
a question card's status (asked / assumed / dropped / held / open), and in the
conversation view the interviewer's notes and chat-room turns, which become a
round only when the user presses [저장]. The main conversation stays the place
where the user talks to Claude and decides.

Every request must name 127.0.0.1/localhost as Host and must not come from
another site (Origin / Sec-Fetch-Site), so a page elsewhere cannot read the
conversation (DNS rebinding). Writes also need the token printed into the page,
which changes every time the server starts.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fde_mode import __version__, asked, convo, db, registry, roster
from fde_mode.paths import P, global_dir
from fde_mode.state import PHASES, Ctx, effective_switches, get_state, timeline
from fde_mode import config
from fde_mode.util import iso, read_json

WEB = Path(__file__).resolve().parent / "web"
BASE_PORT = 28420
TOKEN = secrets.token_urlsafe(24)  # new on every server start; the page gets it in a <meta>, writes must send it back
MAX_BODY = 2_000_000  # a whole interview pasted into the chat box, and its split turns sent back
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}


def _server_file() -> Path:
    return global_dir() / "server.json"


def _free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("빈 포트를 찾지 못했습니다")


def _jload(v: str | None, default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except json.JSONDecodeError:
        return default


class Api:
    """Read model for one project."""

    def __init__(self, root: str):
        self.p = P(Path(root))
        self.cfg = config.load(self.p)
        self.conn = db.connect(self.p.db)

    def close(self) -> None:
        self.conn.close()

    def overview(self) -> dict:
        st = get_state(self.conn)
        c = lambda sql: db.scalar(self.conn, sql, default=0)  # noqa: E731
        runs = db.rows(self.conn, "SELECT * FROM runs ORDER BY created_at DESC LIMIT 30")
        for r in runs:
            r["params"] = _jload(r.get("params"), {})
            r["stage_name"] = (r["params"].get("stage_names") or {}).get(str(r["stage"]), "")
            r.pop("params", None)
        notes = db.rows(self.conn, "SELECT ts, ref, payload FROM events WHERE kind='notify' ORDER BY id DESC LIMIT 25")
        for n in notes:
            n["payload"] = _jload(n.get("payload"), {})
        boot = db.one(self.conn, "SELECT ts, payload FROM events WHERE kind='boot.checked' ORDER BY id DESC LIMIT 1")
        return {
            "project": {"root": str(self.p.root), "name": self.cfg.get("project", {}).get("name") or self.p.root.name,
                        "profile": self.cfg.get("project", {}).get("profile")},
            "state": {"mode": st.get("mode"), "phase": st.get("phase"), "phase_ko": PHASES.get(st.get("phase"), ""),
                      "round": st.get("round"), "flags": st.get("flags"), "updated_at": st.get("updated_at")},
            "switches": effective_switches(self.cfg, st), "timeline": timeline(self.cfg),
            "counts": {
                "utterances": c("SELECT COUNT(*) FROM utterances"),
                "requirements": c("SELECT COUNT(*) FROM requirements"),
                "must": c("SELECT COUNT(*) FROM requirements WHERE priority='must'"),
                "open_questions": c("SELECT COUNT(*) FROM questions WHERE status='open'"),
                "answered_questions": c("SELECT COUNT(*) FROM questions WHERE status='answered'"),
                "pending_decisions": c("SELECT COUNT(*) FROM decisions WHERE status IN ('new','asked') AND grade IN ('D1','D2')"),
                "assumptions": c("SELECT COUNT(*) FROM assumptions WHERE status IN ('active','proposed')"),
                "agents_running": c("SELECT COUNT(*) FROM dispatches WHERE status='issued'"),
                "agents_done": c("SELECT COUNT(*) FROM dispatches WHERE status='done'"),
                "agents_failed": c("SELECT COUNT(*) FROM dispatches WHERE status='failed'"),
                "tasks": c("SELECT COUNT(*) FROM tasks"), "tasks_done": c("SELECT COUNT(*) FROM tasks WHERE status='done'"),
            },
            "runs": runs, "notifications": notes, "boot": boot,
        }

    def cards(self) -> dict:
        utt = {u["id"]: u for u in db.rows(self.conn, "SELECT id, speaker, text FROM utterances")}
        qs = db.rows(self.conn, "SELECT * FROM questions ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'held' THEN 1 "
                                "WHEN 'asked' THEN 2 WHEN 'answered' THEN 3 ELSE 4 END, bucket, ord, id")
        for q in qs:
            for k in ("flags", "evidence", "answer_us"):
                q[k] = _jload(q.get(k), [])
            for k in ("lens", "verifier", "counter"):
                q[k] = _jload(q.get(k), {})
            q["evidence_text"] = [{"id": e, "text": utt.get(e, {}).get("text", "")} for e in q["evidence"]]
            q["answers_text"] = [{"id": e, "text": utt.get(e, {}).get("text", "")} for e in q["answer_us"]]
        asm = db.rows(self.conn, "SELECT * FROM assumptions ORDER BY id DESC")
        dropped = db.rows(self.conn, "SELECT id, round, agent, gap, status, payload FROM candidates WHERE status LIKE 'ranked:drop%' "
                                     "OR status LIKE 'dropped:%' OR status='rejected:no-stake' ORDER BY id DESC LIMIT 80")
        agent_of = {c["id"]: c["agent"] for c in db.rows(self.conn, "SELECT id, agent FROM candidates")}
        for x in dropped:
            members = (_jload(x.pop("payload", None), {}) or {}).get("members") or []
            x["lens_agents"] = sorted({agent_of.get(m, m.split(":")[1] if ":" in m else m) for m in members}) or [x["agent"]]
        return {"questions": qs, "assumptions": asm, "dropped": dropped}

    def decisions(self) -> list:
        rows = db.rows(self.conn, "SELECT * FROM decisions ORDER BY CASE status WHEN 'new' THEN 0 WHEN 'asked' THEN 1 ELSE 2 END, id DESC")
        for r in rows:
            r["options"] = _jload(r.get("options"), [])
            r["blocking"] = _jload(r.get("blocking"), [])
        return rows

    def requirements(self) -> dict:
        reqs = db.rows(self.conn, "SELECT * FROM requirements ORDER BY id")
        for r in reqs:
            r["evidence"] = _jload(r.get("evidence"), [])
            r["conflict"] = _jload(r.get("conflict"), [])
            r.pop("payload", None)
        tests = db.rows(self.conn, "SELECT * FROM tests ORDER BY id")
        for t in tests:
            t["requirements"] = _jload(t.get("requirements"), [])
            t.pop("payload", None)
        risks = db.rows(self.conn, "SELECT id, text, severity, source, status FROM risks ORDER BY id")
        return {"requirements": reqs, "tests": tests, "risks": risks}

    def _text(self, path: Path, limit: int = 60000) -> str:
        return path.read_text(encoding="utf-8")[:limit] if path.exists() else ""

    def persona(self) -> dict:
        m = {}
        r = db.one(self.conn, "SELECT round FROM metrics ORDER BY round DESC LIMIT 1")
        if r:
            for row in db.rows(self.conn, "SELECT scope, name, value FROM metrics WHERE round=?", (r["round"],)):
                m.setdefault(row["scope"], {})[row["name"]] = _jload(row["value"], row["value"])
        return {"persona_md": self._text(self.p.persona), "metrics": m, "metrics_round": (r or {}).get("round"),
                "personalization_map": self._text(self.p.docs / "personalization-map.md"),
                "environment_md": self._text(self.p.docs / "environment.md"),
                "packaging_md": self._text(self.p.docs / "packaging.md"),
                "glossary": read_json(self.p.docs / "glossary.json", {}),
                "simulated": read_json(self.p.docs / "simulated-messages.json", [])}

    def debates(self) -> dict:
        rows = db.rows(self.conn, "SELECT * FROM debates ORDER BY id DESC")
        for r in rows:
            r["positions"] = _jload(r.get("positions"), [])
            r["minority"] = _jload(r.get("minority"), [])
        minutes = sorted((self.p.docs / "minutes").glob("*.md")) if (self.p.docs / "minutes").exists() else []
        return {"debates": rows, "minority_md": self._text(self.p.docs / "minority-opinions.md"),
                "stance_md": self._text(self.p.docs / "stance-history.md"),
                "minutes": [{"name": m.name, "text": self._text(m, 20000)} for m in minutes[-5:]]}

    def data(self) -> dict:
        assets = db.rows(self.conn, "SELECT * FROM data_assets ORDER BY id")
        reports = db.rows(self.conn, "SELECT path, agent, mode, summary FROM artifacts WHERE agent LIKE 'fde-data-%' ORDER BY mtime DESC LIMIT 40")
        return {"assets": assets, "reports": reports}

    def build(self) -> dict:
        tasks = db.rows(self.conn, "SELECT * FROM tasks ORDER BY id")
        for t in tasks:
            t["files"] = _jload(t.get("files"), [])
            t["requirements"] = _jload(t.get("requirements"), [])
            t["notes"] = _jload(t.get("notes"), {})
        adrs = db.rows(self.conn, "SELECT * FROM adrs ORDER BY id")
        for a in adrs:
            a["alternatives"] = _jload(a.get("alternatives"), [])
        releases = db.rows(self.conn, "SELECT * FROM releases ORDER BY created_at DESC")
        qa = db.rows(self.conn, "SELECT path, agent, mode, summary, run FROM artifacts WHERE mode IN ('qa','verdict','review','deploy','observe','release','rollback') ORDER BY mtime DESC LIMIT 60")
        # H-17: what the QA seats could not verify (probe limits, the real platform screen) — never counted as passed
        unverified = []
        for a in db.rows(self.conn, "SELECT run, agent, json FROM artifacts WHERE mode='qa' ORDER BY mtime DESC LIMIT 80"):
            extra = (_jload(a.get("json"), {}) or {}).get("extra") or {}
            for u in extra.get("unverified") or [] if isinstance(extra, dict) else []:
                unverified.append({"run": a["run"], "agent": a["agent"], "item": u if isinstance(u, str) else
                                   (u.get("item") or u.get("text") or json.dumps(u, ensure_ascii=False))})
        return {"tasks": tasks, "adrs": adrs, "releases": releases, "qa": qa, "unverified": unverified,
                "spec_md": self._text(self.p.spec)}

    def org(self) -> dict:
        disp = db.rows(self.conn, "SELECT id, run, stage, agent, mode, status, attempts, background, issued_at, done_at, summary, error "
                                  "FROM dispatches ORDER BY created_at DESC LIMIT 400")
        ko = {a.name: a.ko for a in roster.AGENTS}
        for d in disp:
            d["ko"] = ko.get(d["agent"], d["agent"])
        roster_rows = [{"name": a.name, "ko": a.ko, "division": a.division, "division_ko": roster.DIVISIONS[a.division].ko,
                        "team": a.team, "effort": a.effort, "modes": list(a.modes), "quick": a.quick, "head": a.head,
                        "independent": a.independent} for a in roster.AGENTS]
        return {"dispatches": disp, "roster": roster_rows}

    def events(self) -> list:
        rows = db.rows(self.conn, "SELECT * FROM events ORDER BY id DESC LIMIT 300")
        for r in rows:
            r["payload"] = _jload(r.get("payload"), r.get("payload"))
        return rows

    def transcript(self) -> list:
        rows = db.rows(self.conn, "SELECT id, seq, round, speaker, speaker_label, text, tags, area, qtype, parse_conf FROM utterances ORDER BY seq")
        for r in rows:
            r["tags"] = _jload(r.get("tags"), [])
        return rows

    def reports(self) -> list:
        out = []
        for r in db.rows(self.conn, "SELECT id, pipeline, round, finished_at FROM runs WHERE pipeline IN ('quick','debate','brief') "
                                    "AND status='done' ORDER BY finished_at DESC LIMIT 20"):
            f = self.p.runs / r["id"] / "report.md"
            if f.exists():
                out.append({**r, "text": self._text(f, 40000)})
        return out

    def board(self) -> dict:
        return {"board_md": self._text(self.p.board)}

    def file(self, rel: str) -> str:
        target = (self.p.work / rel).resolve()
        if not str(target).startswith(str(self.p.work.resolve())) or "sealed" in target.parts:
            raise PermissionError("허용되지 않은 경로")
        if target.suffix not in (".md", ".json", ".jsonl", ".txt"):
            raise PermissionError("텍스트 파일만")
        return self._text(target, 400000)


ENDPOINTS = {"overview", "cards", "decisions", "requirements", "persona", "debates", "data", "build", "org", "events",
             "transcript", "reports", "board"}
CONVO_GET = {"convo", "chat", "drafts", "notes", "gaps", "stages"}


def _num(qs: dict, key: str) -> int:
    try:
        return int((qs.get(key) or ["0"])[0] or 0)
    except ValueError:
        return 0


def convo_get(ctx: Ctx, name: str, qs: dict) -> Any:
    if name == "convo":
        return convo.convo_since(ctx, _num(qs, "since"), (qs.get("rsince") or [""])[0])
    if name == "chat":
        return convo.chat(ctx, _num(qs, "since"))
    if name == "drafts":
        return convo.drafts(ctx)
    if name == "notes":
        return convo.notes(ctx)
    if name == "stages":
        return stage_view(ctx)
    return convo.gaps(ctx)


def stage_view(ctx: Ctx) -> dict:
    """Stage map band and role panel: stages with gaps, the stage cards of each stage, engagement and role map."""
    from fde_mode import stage
    if not ctx.switch("stage_map"):
        return {"off": True}
    try:  # fail-open: an odd row hides the band and the panel, the rest of the page works
        s = stage.summary({**stage.compute(ctx), "stages": {r["id"]: r for r in db.rows(ctx.conn, "SELECT * FROM stages")}})
    except Exception as e:  # noqa: BLE001
        ctx.event("web.stage_error", "", {"error": repr(e)})
        return {"off": True, "error": repr(e)}
    cards: dict[str, list] = {}
    for q in db.rows(ctx.conn, "SELECT id, text, status, lens, evidence FROM questions WHERE lens LIKE '%\"stage\"%' ORDER BY id"):
        lens = json.loads(q["lens"] or "{}") or {}
        cards.setdefault(lens.get("stage", ""), []).append({"id": q["id"], "text": q["text"], "status": q["status"],
                                                            "evidence": json.loads(q["evidence"] or "[]")})
    for x in s["stages"]:
        x["cards"] = cards.get(x["id"], [])
    return s


def convo_write(ctx: Ctx, method: str, path: str, body: dict, qs: dict) -> tuple[Any, int]:
    """Chat-room drafts and notes. Nothing here talks to Claude Code."""
    if path == "/api/drafts/save" and method == "POST":
        return convo.save_drafts(ctx, body.get("ids")), 200
    if path == "/api/drafts":
        if method == "POST" and isinstance(body.get("split"), str):
            return {"turns": convo.split_paste(ctx, body["split"])}, 200
        if method == "POST" and isinstance(body.get("turns"), list):
            return convo.add_drafts(ctx, body["turns"]), 200
        if method == "POST":
            return convo.add_draft(ctx, str(body.get("speaker")), str(body.get("text") or "")), 200
        if method == "PUT" and isinstance(body.get("order"), list):
            return convo.reorder_drafts(ctx, [int(x) for x in body["order"]]), 200
        if method == "PUT":
            return convo.update_draft(ctx, int(body.get("id") or 0), body.get("speaker"), body.get("text")), 200
        if method == "DELETE":
            return convo.delete_draft(ctx, _num(qs, "id") or int(body.get("id") or 0)), 200
    if path == "/api/notes" and method in ("POST", "PUT"):
        if method == "PUT" and body.get("base") is None:
            raise ValueError("base(편집을 시작한 판 번호)가 필요합니다")
        nid = int(body["id"]) if method == "PUT" else None
        return convo.save_note(ctx, str(body.get("title") or ""), str(body.get("body") or ""), body.get("links"),
                               nid, body.get("base")), 200
    return {"error": "unknown"}, 404


class Handler(BaseHTTPRequestHandler):
    server_version = "fde-mode/" + __version__
    timeout = 15  # a client that announces more body than it sends cannot hold a thread forever

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet
        return

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return False
        return self.headers.get("Sec-Fetch-Site") != "cross-site"

    def _write_ok(self) -> bool:
        return (self._host_ok() and self._origin_ok() and self.headers.get("X-FDE") == "1"
                and hmac.compare_digest(self.headers.get("X-FDE-Token") or "", TOKEN))

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")  # no other page may frame the dashboard (clickjacking [저장])
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def _project(self, qs: dict) -> str | None:
        root = (qs.get("project") or [""])[0]
        known = [p["root"] for p in registry.projects()]
        if not root and known:
            return known[0]
        return root if root in known else None

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            page = (WEB / "index.html").read_text(encoding="utf-8").replace("__FDE_TOKEN__", TOKEN)
            return self._send(200, page.encode("utf-8"), TYPES[".html"])
        if u.path.startswith("/static/"):
            f = (WEB / u.path.removeprefix("/static/")).resolve()
            if f.parent != WEB.resolve() or not f.exists():
                return self._send(404, b"not found", "text/plain")
            return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
        if u.path.startswith("/api/") and not self._origin_ok():
            return self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
        if u.path == "/api/ping":
            return self._json({"ok": True, "version": __version__, "pid": os.getpid()})
        if u.path == "/api/projects":
            return self._json(registry.projects())
        if u.path.startswith("/api/"):
            name = u.path.removeprefix("/api/")
            root = self._project(qs)
            if not root:
                return self._json({"error": "프로젝트가 없습니다. /fde-mode 로 시작하세요."}, 404)
            api = Api(root)
            try:
                if name == "file":
                    return self._send(200, api.file((qs.get("path") or [""])[0]).encode("utf-8"), "text/plain; charset=utf-8")
                if name in ENDPOINTS:
                    return self._json(getattr(api, name)())
                if name in CONVO_GET:
                    ctx = Ctx(api.p, api.cfg, api.conn)
                    if not ctx.switch("conversation_view"):
                        return self._json({"error": "대화 화면이 꺼져 있습니다(스위치 conversation_view)"}, 404)
                    return self._json(convo_get(ctx, name, qs))
                return self._json({"error": "unknown endpoint"}, 404)
            except PermissionError as e:
                return self._json({"error": str(e)}, 403)
            finally:
                api.close()
        return self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        self._write("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._write("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._write("DELETE")

    def _write(self, method: str) -> None:
        if not self._write_ok():
            return self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
        u = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "bad length"}, 400)
        if length < 0:
            return self._json({"error": "bad length"}, 400)
        if length > MAX_BODY:
            return self._json({"error": "too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json({"error": "bad json"}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "bad json"}, 400)
        if u.path in ("/api/drafts", "/api/drafts/save", "/api/notes"):
            qs = parse_qs(u.query)
            root = self._project({"project": [body.get("project") or (qs.get("project") or [""])[0]]})
            if not root:
                return self._json({"error": "unknown project"}, 404)
            from fde_mode.state import open_ctx
            ctx = open_ctx(root)
            if ctx is None:
                return self._json({"error": "no db"}, 404)
            try:
                if not ctx.switch("conversation_view"):
                    return self._json({"error": "대화 화면이 꺼져 있습니다"}, 404)
                out, code = convo_write(ctx, method, u.path, body, qs)
                return self._json(out, code)
            except ValueError as e:
                return self._json({"error": str(e)}, 409 if str(e) == "conflict" else 400)
            except (KeyError, TypeError):
                return self._json({"error": "bad request"}, 400)
            finally:
                ctx.conn.close()
        if method != "POST":
            return self._json({"error": "unknown"}, 404)
        if u.path == "/api/question":
            root = self._project({"project": [body.get("project", "")]})
            if not root:
                return self._json({"error": "unknown project"}, 404)
            from fde_mode.state import open_ctx
            ctx = open_ctx(root)
            if ctx is None:
                return self._json({"error": "no db"}, 404)
            try:
                ok = asked.mark(ctx, str(body.get("id")), str(body.get("status")), "대시보드")
            except ValueError:
                return self._json({"error": "bad status"}, 400)
            finally:
                ctx.conn.close()
            return self._json({"ok": ok})
        return self._json({"error": "unknown"}, 404)


def serve(port: int = 0) -> None:
    port = port or _free_port(BASE_PORT)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    info = {"pid": os.getpid(), "port": port, "url": f"http://127.0.0.1:{port}/", "started": iso(), "version": __version__}
    _server_file().write_text(json.dumps(info), encoding="utf-8")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def _ping(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def status() -> dict:
    info = read_json(_server_file())
    if not info:
        return {"running": False}
    ping = _ping(int(info.get("port", 0)))
    if not ping:
        return {"running": False, "last": info}
    stale = ping.get("version") != __version__
    return {"running": True, **info, "stale": stale,
            "note": "플러그인이 업데이트됐습니다. `fde serve --stop` 후 다시 켜면 새 화면이 뜹니다" if stale else None}


def start_detached(port: int = 0) -> dict:
    st = status()
    if st.get("running"):
        return {**st, "reused": True}
    port = port or _free_port(BASE_PORT)
    log = global_dir() / "server.log"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    with open(log, "ab") as fh:
        subprocess.Popen([sys.executable, "-m", "fde_mode", "serve", "--port", str(port)], stdout=fh, stderr=fh,
                         stdin=subprocess.DEVNULL, start_new_session=True, env=env, cwd=str(global_dir()))
    for _ in range(40):
        time.sleep(0.15)
        if _ping(port):
            return {**status(), "reused": False}
    return {"running": False, "error": f"서버가 뜨지 않았습니다. 로그: {log}"}


def stop() -> dict:
    info = read_json(_server_file())
    if not info:
        return {"stopped": False, "note": "실행 중인 서버 기록이 없습니다"}
    try:
        os.kill(int(info["pid"]), signal.SIGTERM)
        return {"stopped": True, "pid": info["pid"]}
    except (ProcessLookupError, ValueError, KeyError):
        return {"stopped": False, "note": "이미 꺼져 있습니다"}
