"""Decisions that belong to the user (not to the persona).

D1 필수 승인 : 되돌리기 어렵거나, 취향의 문제이거나, 30분 이상 차이 → 답이 올 때까지 그 일을 멈춘다
D2 확인 요청 : 되돌릴 수 있지만 영향이 큼 → 추천안으로 진행하면서 묻는다(다른 답이면 되돌린다)
D3 알림      : 되돌리기 쉽고 영향이 작음 → 자동 결정, 보고서에 한 줄
"""
from __future__ import annotations

import json
from typing import Any

from fde_mode import db
from fde_mode.state import Ctx
from fde_mode.util import iso, jaccard

GRADES = ("D1", "D2", "D3")


def add(ctx: Ctx, title: str, grade: str = "D2", context: str = "", options: list | None = None,
        recommended: str = "", source: str = "", round_id: str = "", blocking: list | None = None,
        authoritative: bool = False) -> str:
    grade = grade if grade in GRADES else "D2"
    open_rows = db.rows(ctx.conn, "SELECT * FROM decisions WHERE status IN ('new','asked')")
    for r in open_rows:
        if jaccard(r["title"], title) >= 0.8:
            # Same decision raised again: keep the stricter grade, merge options. The engagement lead and the
            # tech lead grade authoritatively (they own "at most two D1 per round").
            g = grade if authoritative else min(r["grade"], grade)
            opts = json.loads(r["options"] or "[]")
            for o in options or []:
                if o not in opts:
                    opts.append(o)
            ctx.conn.execute("UPDATE decisions SET grade=?, options=?, context=? WHERE id=?",
                             (g, json.dumps(opts, ensure_ascii=False), context or r["context"], r["id"]))
            return r["id"]
    did = db.next_id(ctx.conn, "decisions", "D-")
    # autonomy (only when the user switched it on): D2 goes ahead with the recommendation instead of being asked
    auto = grade == "D3" or (grade == "D2" and bool(recommended) and ctx.switch("autonomy"))
    db.upsert(ctx.conn, "decisions", {
        "id": did, "grade": grade, "title": title, "context": context,
        "options": json.dumps(options or [], ensure_ascii=False), "recommended": recommended,
        "status": "auto" if auto else "new", "answer": recommended if auto else None, "source": source,
        "round": round_id, "blocking": json.dumps(blocking or [], ensure_ascii=False),
        "created_at": iso(), "answered_at": iso() if auto else None,
    })
    ctx.event("decision.added", did, {"grade": grade, "title": title, "source": source})
    return did


def pending(ctx: Ctx, statuses=("new",)) -> list[dict[str, Any]]:
    q = ",".join("?" for _ in statuses)
    rows = db.rows(ctx.conn, f"SELECT * FROM decisions WHERE status IN ({q}) AND grade IN ('D1','D2') "
                             "ORDER BY grade, created_at", statuses)
    for r in rows:
        r["options"] = json.loads(r["options"] or "[]")
        r["blocking"] = json.loads(r["blocking"] or "[]")
    return rows


def mark_asked(ctx: Ctx, ids: list[str]) -> None:
    for i in ids:
        ctx.conn.execute("UPDATE decisions SET status='asked' WHERE id=? AND status='new'", (i,))


FOLLOW_RECOMMENDATION = ("추천대로", "추천", "추천안", "추천안으로", "추천대로 해", "추천대로 해요", "추천대로요",
                         "추천대로 할게요", "추천대로 진행", "추천대로 진행해")


def answer(ctx: Ctx, did: str, choice: str) -> bool:
    if " ".join((choice or "").split()) in FOLLOW_RECOMMENDATION:  # "추천대로" = the recommended label, not free text
        rec = db.scalar(ctx.conn, "SELECT recommended FROM decisions WHERE id=?", (did,), "")
        choice = rec or choice
    cur = ctx.conn.execute("UPDATE decisions SET status='answered', answer=?, answered_at=? WHERE id=?",
                           (choice, iso(), did))
    if cur.rowcount:
        ctx.event("decision.answered", did, {"answer": choice}, actor="user")
    return bool(cur.rowcount)


def autonomy_on(ctx: Ctx) -> int:
    """The user just switched autonomy on: the open D2s go ahead with their recommendation too."""
    n = ctx.conn.execute("UPDATE decisions SET status='auto', answer=recommended, answered_at=? WHERE grade='D2' "
                         "AND status IN ('new','asked') AND COALESCE(recommended,'')<>''", (iso(),)).rowcount
    if n:
        ctx.event("decision.autonomy", "", {"closed": n}, actor="user")
    return n


def blocking_open(ctx: Ctx, tag: str) -> list[dict]:
    """D1 decisions that block a given gate (e.g. 'core_freeze', 'deploy')."""
    rows = db.rows(ctx.conn, "SELECT * FROM decisions WHERE grade='D1' AND status IN ('new','asked')")
    return [r for r in rows if tag in json.loads(r.get("blocking") or "[]")]
