"""Turn verified candidates into question cards, assumptions and drops.

Inputs per merged candidate: the proposing lens's self-confidence, the
citation check, the blind verifier's confidence/impact/answered/forced, and the
counter-arguer's ask/assume/skip. Output: buckets the user can act on, with
every disagreement shown instead of hidden.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fde_mode import db, rubric
from fde_mode.state import Ctx
from fde_mode.util import iso, write_json


def _verdict(ctx: Ctx, cid: str, rnd: str, source: str) -> dict | None:
    v = db.one(ctx.conn, "SELECT * FROM verdicts WHERE candidate=? AND round=? AND source=?", (cid, rnd, source))
    if v:
        v["payload"] = json.loads(v.get("payload") or "{}")
    return v


def decide_bucket(c: dict, ver: dict | None, cnt: dict | None) -> tuple[str, str, list[str], str, str]:
    """Return (bucket, reason, flags, final_conf, final_impact)."""
    flags: list[str] = []
    lens_conf = rubric.conf_norm(c.get("self_confidence"))
    conf = rubric.conf_norm((ver or {}).get("confidence") or lens_conf)
    impact = rubric.impact_norm((ver or {}).get("impact") or c.get("impact_guess"))
    if ver is None:
        flags.append("검증 누락")
    if c.get("cite_ok") == 0:
        conf = "추측"
        flags.append("인용 불일치")
    if ver and rubric.mismatch(lens_conf, ver.get("confidence")):
        flags.append("⚠ 렌즈·검증 불일치")
    kind = c.get("kind") or "question"
    if ver and ver.get("already_answered"):
        ans = (ver.get("payload") or {}).get("answered_by") or []
        return "drop", f"이미 답함 {', '.join(ans)}".strip(), flags, conf, impact
    if kind == "assumption":
        return "assume", "가정 제안 후보", flags, conf, impact
    base = rubric.bucket(conf, impact)
    reason = f"{conf}×{impact}"
    if ver and ver.get("forced"):
        why = (ver.get("payload") or {}).get("forced_reason") or ver.get("reason") or ""
        if impact == "높음" and (cnt or {}).get("verdict") == "ask":
            flags.append("억지 의심")
            base, reason = "hold", f"억지 의심이지만 영향 높음·반론관도 물어야 한다고 봄 ({why})"
        else:
            return "drop", f"억지 판정: {why}", flags, conf, impact
    cv = (cnt or {}).get("verdict")
    if cv == "skip":
        if impact != "높음":
            if base in ("ask", "hold"):
                base = "assume" if conf != "추측" else "drop"
                reason += " · 반론관: 묻지 않아도 됨"
        else:
            flags.append("반론 있음")
    elif cv == "assume" and base == "ask" and impact != "높음":
        base, reason = "assume", reason + " · 반론관: 가정으로 충분"
    if kind == "proposal" and base in ("ask", "hold"):
        base = "propose"
    if conf == "추측" and impact == "높음" and base == "ask":
        flags.append("확인용")
    return base, reason, flags, conf, impact


_DEFAULT_RE = re.compile(r"기본(?:값|안)\s*(?:[:：]|은|는|으로|로)?\s*(.+?)(?:(?<=[다요음함임됨])\.|[.。](?=\s|$)|$)", re.S)


def assumption_text(c: dict, cnt: dict | None) -> str:
    """The statement the user is asked to veto: the counter-arguer's `default`, a 기본값 sentence in its reason,
    the candidate's own wording when it was proposed as an assumption, else "묻지 않고 진행" + the gap.
    Never the decision at stake — that says what would change, not what we assume (seen in a real round)."""
    payload = (cnt or {}).get("payload") or {}
    d = str(payload.get("default") or "").strip()
    if d:
        return d
    if (c.get("kind") or "") == "assumption":
        return str(c.get("question_draft") or c.get("gap") or "").strip()
    m = _DEFAULT_RE.search(str((cnt or {}).get("reason") or ""))
    if m and len(m.group(1).strip()) >= 4:
        return m.group(1).strip().rstrip(".")
    return f"묻지 않고 진행(기본값 미기재) — {c.get('gap') or ''}".strip()


def rank(ctx: Ctx, rnd: str, run: str, top_n: int = 5, out_path=None) -> dict[str, Any]:
    cands = db.rows(ctx.conn, "SELECT * FROM candidates WHERE run=? AND status='merged' AND kind NOT IN ('risk','decision')", (run,))
    if not cands:  # merger did not run or produced nothing: fall back to raw candidates
        cands = db.rows(ctx.conn, "SELECT * FROM candidates WHERE run=? AND status='new' AND "
                                  "(merged_into IS NULL OR merged_into='') AND kind IN ('question','proposal','assumption')",
                        (run,))
    buckets: dict[str, list[dict]] = {"ask": [], "hold": [], "assume": [], "drop": [], "propose": []}
    for c in cands:
        ver = _verdict(ctx, c["id"], rnd, "verify")
        cnt = _verdict(ctx, c["id"], rnd, "counter")
        b, reason, flags, conf, impact = decide_bucket(c, ver, cnt)
        payload = json.loads(c.get("payload") or "{}")
        sources = int(payload.get("sources") or 1)
        item = {"candidate": c["id"], "gap": c["gap"], "draft": c["question_draft"], "conf": conf, "impact": impact,
                "lens_conf": c["self_confidence"], "reason": reason, "flags": flags, "sources": sources,
                "evidence": json.loads(c.get("evidence") or "[]"), "decision_at_stake": c["decision_at_stake"],
                "if_wrong": c.get("if_wrong", ""), "kind": c["kind"], "area": c.get("area", ""),
                "lens": {"agents": payload.get("members") or [c["agent"]], "confidence": c["self_confidence"]},
                "verifier": {"confidence": (ver or {}).get("confidence"), "why": (ver or {}).get("reason")},
                "counter": {"verdict": (cnt or {}).get("verdict"), "why": (cnt or {}).get("reason")}}
        if b == "assume":
            item["assumption_text"] = assumption_text(c, cnt)
        buckets[b].append(item)
        ctx.conn.execute("UPDATE candidates SET status=? WHERE id=?", (f"ranked:{b}", c["id"]))
    for k in ("ask", "hold", "propose"):
        buckets[k].sort(key=lambda x: rubric.rank_key(x["conf"], x["impact"], x["sources"]))
    # Persist cards so asked-detection and the dashboard can follow them.
    for k in ("ask", "hold", "propose"):
        for i, item in enumerate(buckets[k], 1):
            existing = db.one(ctx.conn, "SELECT id FROM questions WHERE candidate=?", (item["candidate"],))
            qid = existing["id"] if existing else db.next_id(ctx.conn, "questions", "Q-")
            item["question"] = qid
            db.upsert(ctx.conn, "questions", {
                "id": qid, "round": rnd, "candidate": item["candidate"], "text": item["draft"] or item["gap"],
                "confidence": item["conf"], "impact": item["impact"], "bucket": k,
                "flags": json.dumps(item["flags"], ensure_ascii=False), "evidence": json.dumps(item["evidence"]),
                "decision_at_stake": item["decision_at_stake"], "lens": json.dumps(item["lens"], ensure_ascii=False),
                "verifier": json.dumps(item["verifier"], ensure_ascii=False),
                "counter": json.dumps(item["counter"], ensure_ascii=False), "ord": i,
                "status": "open" if k != "hold" else "held", "asked_u": None, "answer_us": "[]", "updated_at": iso(),
            })
    for item in buckets["assume"]:
        aid = db.next_id(ctx.conn, "assumptions", "A-")
        why = item["reason"] + (f" · 틀리면: {item['decision_at_stake']}" if item.get("decision_at_stake") else "")
        db.upsert(ctx.conn, "assumptions", {"id": aid, "text": item["assumption_text"],
                                            "reason": why, "related": json.dumps([item["candidate"]]),
                                            "round": rnd, "status": "proposed"})
        item["assumption"] = aid
    result = {"round": rnd, "run": run, "top_n": top_n, "buckets": buckets,
              "counts": {k: len(v) for k, v in buckets.items()}}
    if out_path:
        write_json(out_path, result)
    return result
