"""Conversation view (dashboard tab "대화"): what the left chat room, the centre
"나 ↔ Claude" column, the notes and the "놓친 것" strip read and write.

- The user keeps pasting into the Claude Code session they opened; the hooks only
  record that conversation here (capture_*). Capture never prints, never raises
  into the hook, and waits at most CAPTURE_WAIT for the database.
- Turns typed in the web chat room stay drafts until [저장]; saving makes them a
  round through the same `transcript.ingest` as a paste (source=web), so fde.db
  stays the one record.
- Notes are the interviewer's own memo: never persona evidence (U).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from fde_mode import db, domain, transcript
from fde_mode.lexicon import CLOCK, NUM_UNIT
from fde_mode.state import Ctx, set_state
from fde_mode.util import iso, scrub, short, write_text

CAPTURE_WAIT = 0.05  # seconds a capture may wait for the database lock; then it gives up silently
TAIL_BYTES = 64 * 1024
MAX_TEXT = 200_000
PASTE_LABEL = {"transcript": "대화 원문", "brief": "문제 설명(브리프)", "note": "메모"}
SPEAKER = {"persona": ("P", "인물"), "me": ("I", "나")}
# A persona line that carries a need, a pain or a constraint (tagger tag / topic area)
NEED_TAGS = {"요청"}
NEED_AREAS = {"문제", "예외", "성공기준", "우선순위"}
DATE = re.compile(r"\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{1,2}/\d{1,2}")
QUOTED = re.compile(r"[\"“'‘「『]([^\"”'’」』\n]{2,30})[\"”'’」』]")


# ---------- capture (hooks) ----------

def quick_conn(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=CAPTURE_WAIT, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={int(CAPTURE_WAIT * 1000)}")
    return conn


def _add(conn: sqlite3.Connection, role: str, kind: str, text: str, rnd: str | None, session: str, meta: dict) -> None:
    conn.execute("INSERT INTO convo(ts, role, kind, text, round, session_id, meta) VALUES(?,?,?,?,?,?,?)",
                 (iso(), role, kind, scrub(text)[:MAX_TEXT], rnd, session, json.dumps(meta, ensure_ascii=False)))


def capture_prompt(conn: sqlite3.Connection, data: dict, paste: dict | None) -> None:
    """One user prompt. A pasted interview/brief/memo is stored as a chip (kind=paste + round), not its text."""
    session = str(data.get("session_id") or "")
    if paste:
        label = PASTE_LABEL.get(paste.get("kind", ""), "붙여넣기")
        rnd = paste.get("round")
        text = f"{label} {rnd} · 발화 {paste.get('count', 0)}" if rnd else f"{label} · 새 발화 없음(겹침)"
        _add(conn, "me", "paste", text, rnd, session, {"paste_kind": paste.get("kind"), "count": paste.get("count", 0)})
    else:
        prompt = str(data.get("prompt") or "")
        if prompt.strip():
            _add(conn, "me", "prompt", prompt, None, session, {})


def last_reply(transcript_path: str) -> tuple[str, str]:
    """Claude's visible text since the last real user prompt, from the end of the session transcript (≤64KB)."""
    p = Path(transcript_path)
    with p.open("rb") as fh:
        size = p.stat().st_size
        fh.seek(max(0, size - TAIL_BYTES))
        raw = fh.read().decode("utf-8", errors="ignore")
    lines = raw.split("\n")
    if size > TAIL_BYTES:
        lines = lines[1:]  # first line is cut
    texts: list[str] = []
    uid = ""
    for ln in reversed(lines):
        try:
            e = json.loads(ln)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        msg = e.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if e.get("type") == "assistant":
            parts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
            if parts:
                texts.insert(0, "\n".join(parts))
                uid = uid or str(e.get("uuid") or "")
        elif e.get("type") == "user":
            if isinstance(content, str) or any(isinstance(c, dict) and c.get("type") == "text" for c in content or []):
                break  # the prompt that started this turn
    return "\n\n".join(t for t in texts if t.strip()).strip(), uid


def capture_reply(conn: sqlite3.Connection, data: dict) -> None:
    """Claude's reply of this turn. The Stop hook input carries it (`last_assistant_message`); the session transcript
    is only a fallback — when Stop fires, the reply is often not written to that file yet (seen in a live session)."""
    text, uid = "", ""
    if isinstance(data.get("last_assistant_message"), str) and data["last_assistant_message"].strip():
        text = data["last_assistant_message"]
        uid = f"{data.get('prompt_id') or data.get('session_id') or ''}:{hashlib.sha1(text.encode()).hexdigest()[:12]}"
    elif data.get("transcript_path"):
        text, uid = last_reply(str(data["transcript_path"]))
    if not text.strip():
        return
    prev = conn.execute("SELECT text, meta FROM convo WHERE role='claude' ORDER BY id DESC LIMIT 1").fetchone()
    if prev and (json.loads(prev["meta"] or "{}").get("uuid") == uid if uid else prev["text"] == scrub(text)[:MAX_TEXT]):
        return  # the same reply seen by a second Stop (e.g. after a blocked stop); a new reply with the same words is kept
    _add(conn, "claude", "reply", text, None, str(data.get("session_id") or ""), {"uuid": uid})


# ---------- read model ----------

def _evidence_counts(ctx: Ctx) -> Counter:
    """How many cards/candidates/requirements cite each utterance."""
    n: Counter = Counter()
    for table in ("candidates", "questions", "requirements"):
        for r in db.rows(ctx.conn, f"SELECT evidence FROM {table}"):
            try:
                ev = json.loads(r["evidence"] or "[]")
            except json.JSONDecodeError:
                continue
            for e in ev if isinstance(ev, list) else []:
                n[str(e)] += 1
    return n


def convo_since(ctx: Ctx, since: int = 0, rsince: str = "", limit: int = 400) -> dict:
    """Centre column: prompts/replies after convo id `since`, round reports finished after `rsince`, all D1/D2."""
    rows = db.rows(ctx.conn, "SELECT * FROM convo WHERE id>? ORDER BY id LIMIT ?", (since, limit))
    for r in rows:
        r["meta"] = json.loads(r.get("meta") or "{}")
    reports = db.rows(ctx.conn, "SELECT id, pipeline, round, finished_at FROM runs WHERE pipeline IN ('quick','debate','brief') "
                                "AND status='done' AND finished_at>? ORDER BY finished_at DESC LIMIT 20", (rsince or "",))
    reports.reverse()
    out_reports = []
    for r in reports:
        f = ctx.p.runs / r["id"] / "report.md"
        if f.exists():
            out_reports.append({**r, "text": f.read_text(encoding="utf-8")[:40000]})
    decisions = db.rows(ctx.conn, "SELECT id, grade, title, context, options, recommended, status, answer, created_at "
                                  "FROM decisions WHERE grade IN ('D1','D2') ORDER BY created_at")
    for d in decisions:
        d["options"] = json.loads(d.get("options") or "[]")
    return {"items": rows, "cursor": rows[-1]["id"] if rows else since, "reports": out_reports,
            "rcursor": out_reports[-1]["finished_at"] if out_reports else rsince, "decisions": decisions}


def chat(ctx: Ctx, since: int = 0) -> dict:
    utts = db.rows(ctx.conn, "SELECT id, seq, round, speaker, speaker_label, text, tags, area, created_at FROM utterances "
                             "WHERE seq>? ORDER BY seq", (since,))
    for u in utts:
        u["tags"] = json.loads(u.get("tags") or "[]")
    counts = _evidence_counts(ctx)
    rounds = db.rows(ctx.conn, "SELECT r.id, r.n, r.kind, r.status, r.created_at, r.note, COUNT(u.id) AS count "
                               "FROM rounds r LEFT JOIN utterances u ON u.round=r.id GROUP BY r.id ORDER BY r.n")
    for r in rounds:
        r["source"] = (json.loads(r.pop("note") or "{}") or {}).get("source", "")
    all_ids = [r["id"] for r in db.rows(ctx.conn, "SELECT id FROM utterances")]
    return {"utterances": utts, "cursor": utts[-1]["seq"] if utts else since, "rounds": rounds,
            "reflected": {u: counts.get(u, 0) for u in all_ids}, "drafts": drafts(ctx)}


# ---------- drafts (chat room before [저장]) ----------

def drafts(ctx: Ctx) -> list[dict]:
    return db.rows(ctx.conn, "SELECT id, seq, speaker, text, created_at FROM drafts ORDER BY seq, id")


def add_draft(ctx: Ctx, speaker: str, text: str) -> list[dict]:
    return add_drafts(ctx, [{"speaker": speaker, "text": text}])


def split_paste(ctx: Ctx, text: str) -> list[dict]:
    """A whole conversation pasted into the chat box → speaker-guessed turns for the user to confirm (not saved)."""
    utts, _ = transcript.parse(text, ctx.cfg, ctx.refresh().get("speakers") or {})
    return [{"speaker": "me" if u["speaker"] == "I" else "persona", "text": u["text"], "label": u["label"],
             "sure": u["conf"] >= 0.7} for u in utts if u["speaker"] in ("I", "P", "?")]


def add_drafts(ctx: Ctx, turns: list) -> list[dict]:
    """Append turns as drafts in one go (a confirmed split of a pasted conversation can be thousands of turns)."""
    rows = []
    for t in turns:
        if not isinstance(t, dict) or t.get("speaker") not in SPEAKER:
            raise ValueError("각 턴은 speaker(persona|me)와 text가 있어야 합니다")
        if str(t.get("text") or "").strip():
            rows.append((t["speaker"], str(t["text"]).strip()[:MAX_TEXT]))
    if not rows:
        raise ValueError("내용이 있는 턴이 없습니다")
    with db.write_txn(ctx.conn):
        seq0 = int(db.scalar(ctx.conn, "SELECT MAX(seq) FROM drafts", default=0))
        now = iso()
        ctx.conn.executemany("INSERT INTO drafts(seq, speaker, text, created_at) VALUES(?,?,?,?)",
                             [(seq0 + i, sp, tx, now) for i, (sp, tx) in enumerate(rows, 1)])
    return drafts(ctx)


def update_draft(ctx: Ctx, did: int, speaker: str | None = None, text: str | None = None) -> list[dict]:
    if speaker is not None:
        if speaker not in SPEAKER:
            raise ValueError("speaker는 persona 또는 me")
        ctx.conn.execute("UPDATE drafts SET speaker=? WHERE id=?", (speaker, did))
    if text is not None and text.strip():
        ctx.conn.execute("UPDATE drafts SET text=? WHERE id=?", (text.strip()[:MAX_TEXT], did))
    return drafts(ctx)


def reorder_drafts(ctx: Ctx, order: list[int]) -> list[dict]:
    for i, did in enumerate(order, 1):
        ctx.conn.execute("UPDATE drafts SET seq=? WHERE id=?", (i, int(did)))
    return drafts(ctx)


def delete_draft(ctx: Ctx, did: int) -> list[dict]:
    ctx.conn.execute("DELETE FROM drafts WHERE id=?", (did,))
    return drafts(ctx)


def save_drafts(ctx: Ctx, ids: list[int] | None = None) -> dict:
    """[저장]: the drafts the user saw become one round, atomically. Two clicks (or two tabs) never save twice:
    the second finds the drafts already gone."""
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, int) for i in ids)):
        raise ValueError("ids는 정수 목록이어야 합니다")
    with db.write_txn(ctx.conn):
        rows = drafts(ctx)
        if ids is not None:
            rows = [r for r in rows if r["id"] in set(ids)]
        if not rows:
            return {"round": None, "count": 0}
        utts = [{"speaker": SPEAKER[r["speaker"]][0], "label": SPEAKER[r["speaker"]][1], "text": r["text"], "conf": 1.0}
                for r in rows]
        body = "\n".join(f"{u['label']}: {u['text']}" for u in utts)
        summary = transcript.ingest(ctx, body, kind="transcript", source="web", utts=utts)
        ctx.conn.executemany("DELETE FROM drafts WHERE id=?", [(r["id"],) for r in rows])
    try:
        _note_web_save(ctx, turns=summary.get("count", 0))
    except Exception:  # noqa: BLE001 — the round is saved; only the next prompt's notice line is lost
        pass
    return summary


# ---------- notes ----------

def _evidence_text(ctx: Ctx) -> str:
    parts = [r["text"] or "" for r in db.rows(ctx.conn, "SELECT text FROM utterances WHERE speaker IN ('P','I','B')")]
    parts += [f"{r['name'] or ''} {r['notes'] or ''}" for r in db.rows(ctx.conn, "SELECT name, notes FROM data_assets")]
    return "\n".join(parts)


def note_checks(body: str, evidence: str) -> list[dict]:
    """Numbers, dates/times and quoted names in a note that the conversation and the data never mention.
    ponytail: surface match only (no unit conversion, "50통" ≠ "오십 통"); a warning, never a block."""
    ev = re.sub(r"\s+", "", evidence)
    found: list[tuple[str, str]] = []
    for kind, rx in (("숫자", NUM_UNIT), ("시각", CLOCK), ("날짜", DATE)):
        found += [(kind, m.group(0)) for m in rx.finditer(body)]
    found += [("고유명", m.group(1)) for m in QUOTED.finditer(body)]
    out, seen = [], set()
    for kind, s in found:
        key = re.sub(r"\s+", "", s)
        if key and key not in seen and key not in ev:
            seen.add(key)
            out.append({"kind": kind, "text": s})
    return out


def notes(ctx: Ctx) -> list[dict]:
    rows = db.rows(ctx.conn, "SELECT * FROM notes ORDER BY updated_at DESC, id DESC")
    for r in rows:
        r["links"] = json.loads(r.get("links") or "[]")
        r["checks"] = json.loads(r.get("checks") or "[]")
    return rows


def save_note(ctx: Ctx, title: str, body: str, links: list | None = None, nid: int | None = None,
              base: int | None = None) -> dict:
    """Create (nid None) or update a note. `base` = the revision the editor started from: another tab that saved in
    between raised it → ValueError("conflict") instead of overwriting that save."""
    links = [str(x) for x in (links or []) if str(x).strip()][:200]
    checks = note_checks(f"{title}\n{body}", _evidence_text(ctx))
    now = iso()
    if nid is None:
        cur = ctx.conn.execute("INSERT INTO notes(created_at, updated_at, title, body, links, checks) VALUES(?,?,?,?,?,?)",
                               (now, now, title.strip()[:200], body[:MAX_TEXT], json.dumps(links, ensure_ascii=False),
                                json.dumps(checks, ensure_ascii=False)))
        nid = int(cur.lastrowid or 0)
    else:
        cur = ctx.conn.execute("UPDATE notes SET updated_at=?, title=?, body=?, links=?, checks=?, rev=rev+1 WHERE id=?"
                               + (" AND rev=?" if base is not None else ""),
                               (now, title.strip()[:200], body[:MAX_TEXT], json.dumps(links, ensure_ascii=False),
                                json.dumps(checks, ensure_ascii=False), nid, *([int(base)] if base is not None else [])))
        if cur.rowcount == 0:
            raise ValueError("conflict" if db.one(ctx.conn, "SELECT id FROM notes WHERE id=?", (nid,)) else "not found")
    export_notes(ctx)
    try:
        _note_web_save(ctx, notes=1)
    except Exception:  # noqa: BLE001
        pass
    return next(n for n in notes(ctx) if n["id"] == nid)


def export_notes(ctx: Ctx) -> Path:
    """docs/interviewer-notes.md — the readback writer, doc auditor and interviewer coach compare it with the record."""
    path = ctx.p.docs / "interviewer-notes.md"
    lines = ["# 인터뷰어 메모 (인물 발화 아님 — 근거(U)로 쓰지 않는다)", ""]
    for n in reversed(notes(ctx)):
        lines += [f"## N{n['id']} {n['title'] or '(제목 없음)'} — {n['updated_at'][:16]}", n["body"].rstrip(), ""]
        if n["links"]:
            lines.append("연결한 기록: " + ", ".join(n["links"]))
        if n["checks"]:
            lines.append("기록에 없는 것: " + ", ".join(c["text"] for c in n["checks"]))
        lines.append("")
    write_text(path, "\n".join(lines))
    return path


def _note_web_save(ctx: Ctx, turns: int = 0, notes: int = 0) -> None:
    """The next prompt's status line says what was saved on the web (hooks.on_prompt reads and clears it)."""
    cur = (ctx.refresh().get("flags") or {}).get("web_saved") or {}
    set_state(ctx, flags={"web_saved": {"turns": int(cur.get("turns", 0)) + turns,
                                        "notes": int(cur.get("notes", 0)) + notes}})


def take_web_saved(ctx: Ctx) -> str:
    ws = (ctx.state.get("flags") or {}).get("web_saved") or {}
    if not (ws.get("turns") or ws.get("notes")):
        return ""
    set_state(ctx, flags={"web_saved": {}})
    return f"웹 저장: 인터뷰 턴 {int(ws.get('turns', 0))}·메모 {int(ws.get('notes', 0))}"


# ---------- 놓친 것 ----------

def domain_warnings(ctx: Ctx) -> list[dict]:
    """N safety net: industry words in cards, requirements, the spec or slice designs that the persona, the brief and
    the data never mentioned."""
    items: dict[str, str] = {}
    for q in db.rows(ctx.conn, "SELECT id, text FROM questions WHERE status NOT IN ('dropped')"):
        items[q["id"]] = q["text"] or ""
    for r in db.rows(ctx.conn, "SELECT id, statement FROM requirements"):
        items[r["id"]] = r["statement"] or ""
    for t in db.rows(ctx.conn, "SELECT id, title, notes FROM tasks"):
        items[t["id"]] = f"{t['title'] or ''} {t['notes'] or ''}"
    if ctx.p.spec.exists():
        items["spec.md"] = ctx.p.spec.read_text(encoding="utf-8")[:200000]
    return domain.unsupported(items, _evidence_text(ctx))


def gaps(ctx: Ctx) -> dict:
    qs = db.rows(ctx.conn, "SELECT id, text, impact, status, answer_us, round FROM questions")
    unasked = [{"id": q["id"], "text": short(q["text"], 80)} for q in qs if q["status"] == "open" and q["impact"] == "높음"]
    unanswered = [{"id": q["id"], "text": short(q["text"], 80)} for q in qs
                  if q["status"] == "asked" and not json.loads(q.get("answer_us") or "[]")]
    counts = _evidence_counts(ctx)
    unreflected = []
    for u in db.rows(ctx.conn, "SELECT u.id, u.text, u.tags, u.area, u.round FROM utterances u JOIN rounds r ON r.id=u.round "
                               "WHERE u.speaker='P' AND r.status='done' ORDER BY u.seq"):
        tags = set(json.loads(u.get("tags") or "[]"))
        if (tags & NEED_TAGS or u["area"] in NEED_AREAS) and not counts.get(u["id"]):
            unreflected.append({"id": u["id"], "round": u["round"], "text": short(u["text"], 80)})
    ungrounded = [{"id": n["id"], "title": n["title"], "checks": n["checks"]} for n in notes(ctx) if n["checks"]]
    try:  # a warning list must never take the "놓친 것" band down
        words = domain_warnings(ctx)
    except Exception as e:  # noqa: BLE001
        ctx.event("convo.domain_error", "", {"error": repr(e)})
        words = []
    return {"unasked_high": unasked, "asked_unanswered": unanswered, "unreflected": unreflected,
            "ungrounded_notes": ungrounded, "domain_words": words,
            "counts": {"unasked_high": len(unasked), "asked_unanswered": len(unanswered), "unreflected": len(unreflected),
                       "ungrounded_notes": len(ungrounded), "domain_words": len(words)}}
