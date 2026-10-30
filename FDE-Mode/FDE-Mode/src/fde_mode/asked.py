"""Question tracking without extra clicks.

When the user copies a question card into the persona chat, that question shows
up in the next paste as an interviewer line. We match it back to the card and
link the persona's reply, so nobody has to mark cards as asked by hand and the
organisation never re-asks something that was already answered.
"""
from __future__ import annotations

import json
from typing import Any

from fde_mode import db
from fde_mode.state import Ctx
from fde_mode.util import containment, iso, jaccard

THRESHOLD = 0.55


def similarity(card: str, line: str) -> float:
    return max(containment(card, line), containment(line, card) * 0.9, jaccard(card, line))


def detect(ctx: Ctx, round_id: str) -> dict[str, Any]:
    utts = db.rows(ctx.conn, "SELECT * FROM utterances ORDER BY seq")
    new = [u for u in utts if u["round"] == round_id]
    open_q = db.rows(ctx.conn, "SELECT * FROM questions WHERE status IN ('open','held','asked')")
    linked = []
    for q in open_q:
        best, best_u = 0.0, None
        for u in new:
            if u["speaker"] != "I":
                continue
            s = similarity(q["text"] or "", u["text"])
            if s > best:
                best, best_u = s, u
        if best_u is None or best < THRESHOLD:
            continue
        idx = next(i for i, u in enumerate(utts) if u["id"] == best_u["id"])
        answers = []
        for u in utts[idx + 1:]:
            if u["speaker"] == "I":
                break
            if u["speaker"] == "P":
                answers.append(u["id"])
        status = "answered" if answers else "asked"
        prev = json.loads(q.get("answer_us") or "[]")
        ctx.conn.execute("UPDATE questions SET status=?, asked_u=?, answer_us=?, updated_at=? WHERE id=?",
                         (status, best_u["id"], json.dumps(sorted(set(prev + answers))), iso(), q["id"]))
        linked.append({"question": q["id"], "asked_u": best_u["id"], "answers": answers, "score": round(best, 2)})
    if linked:
        ctx.event("questions.linked", round_id, linked)
    return {"round": round_id, "linked": linked}


def mark(ctx: Ctx, qid: str, status: str, note: str = "") -> bool:
    if status not in ("open", "asked", "answered", "assumed", "dropped", "held"):
        raise ValueError(status)
    cur = ctx.conn.execute("UPDATE questions SET status=?, updated_at=? WHERE id=?", (status, iso(), qid))
    if cur.rowcount:
        ctx.event("question.status", qid, {"status": status, "note": note}, actor="user")
        if status == "assumed":
            q = db.one(ctx.conn, "SELECT * FROM questions WHERE id=?", (qid,))
            aid = db.next_id(ctx.conn, "assumptions", "A-")
            db.upsert(ctx.conn, "assumptions", {"id": aid, "text": (q or {}).get("decision_at_stake") or (q or {}).get("text"),
                                                "reason": note or "사용자가 가정으로 처리", "related": json.dumps([qid]),
                                                "round": (q or {}).get("round"), "status": "active"})
    return bool(cur.rowcount)
