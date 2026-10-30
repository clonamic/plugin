"""Agent output files → database.

Every agent writes exactly one JSON file in the `fde.out.v1` envelope. This
module validates it against the dispatch it answers and folds each section
into the right table. Sections are optional; unknown sections are kept in
`artifacts` so nothing an agent wrote is ever lost.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fde_mode import SCHEMA, db, decisions as D, rubric, transcript
from fde_mode.roster import BY_NAME
from fde_mode.state import Ctx, set_state
from fde_mode.util import dumps, iso, read_json, scrub, scrub_values, write_text

# mode -> sections that must be present (as lists/objects; empty list is allowed)
REQUIRED: dict[str, tuple[str, ...]] = {
    "scribe": ("utterance_updates",),
    "tag": ("utterance_updates",),
    "topic": ("utterance_updates",),
    "analyze": ("observations", "candidates"),
    "complement": ("candidates",),
    "brief": ("candidates",),
    "opening": ("report",),
    "position": ("position",),
    "review": ("debate",),
    "rebuttal": ("debate",),
    "ruling": ("debate",),
    "merge": ("merged",),
    "verify": ("verdicts",),
    "counter": ("verdicts",),
    "audit": ("findings",),
    "write": ("cards",),
    "sequence": ("sequence",),
    "readback": ("readback",),
    "conclude": ("report",),
    "minutes": ("minutes",),
    "freeze": ("freeze",),
    "change": ("change",),
    "tech": ("proposals",),
    "challenge": ("challenges",),
    "decide": ("adrs",),
    "plan": ("plan",),
    "replan": ("plan",),
    "dataplan": ("data_report",),
    "datareport": ("data_report",),
    "codereview": ("review",),
    "design": ("design",),
    "trace": ("trace",),
    "implement": ("implementation",),
    "unblock": ("implementation",),
    "deploy": ("deploy",),
    "release": ("release",),
    "rollback": ("release",),
    "observe": ("observations",),
    "qa": ("qa",),
    "verdict": ("qa_verdict",),
    "validate": ("data_report",),
    "consistency": ("data_report",),
    "clean": ("data_report",),
    "load": ("data_report",),
    "retro": ("lessons",),
    "create": ("mock",),
    "grade": ("grade",),
    "final": ("final",),
}


def validate(data: Any, dispatch: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["output is not a JSON object"]
    if data.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA}")
    agent = str(data.get("agent", ""))
    if agent and agent.removeprefix("fde-mode:") != dispatch["agent"]:
        errs.append(f"agent mismatch: {agent} != {dispatch['agent']}")
    for key in REQUIRED.get(dispatch["mode"], ()):
        if key not in data:
            errs.append(f"missing section '{key}' for mode {dispatch['mode']}")
    if not isinstance(data.get("summary_ko", ""), str):
        errs.append("summary_ko must be a string")
    return errs


def _short(agent: str) -> str:
    return agent.removeprefix("fde-")


NOT_EXECUTED = {
    "build_start": "실행 안 됨 — 제작은 핵심 동결('제작 시작해도 될까요?') 뒤에만 시작됩니다. 그 D1로 묻습니다",
    "freeze_judge": "실행 안 됨 — 동결 판단관은 결정을 내지 않습니다. 제작 시작은 이 동결 run의 D1로, 다시 판단하는 시점은 "
                    "플래너 규칙(분석이 끝난 다음 대화 라운드 뒤, 또는 전체 동결 시각)으로 정해집니다",
}


def not_executable(ctx: Ctx, agent: str, d: dict, rnd: str) -> str:
    """A decision the planner cannot carry out (part of the build before the core freeze — `kind: build_start` — or
    anything the freeze judge raises beside its recommendation, e.g. "1라운드 뒤 다시 판단"). Answered, it used to do
    nothing while other seats read it as done ("이미 시작됨"). It is never asked: it is recorded as 실행 안 됨 so every
    snapshot and the board say so, and an early-start request becomes the core freeze D1 (planner.triggers)."""
    build = d.get("kind") == "build_start"
    did = db.next_id(ctx.conn, "decisions", "D-")
    db.upsert(ctx.conn, "decisions", {
        "id": did, "grade": d.get("grade", "D2"), "title": d["title"], "context": d.get("context", ""),
        "options": dumps(d.get("options") or []), "recommended": d.get("recommended", ""), "status": "void",
        "answer": NOT_EXECUTED["build_start" if build else "freeze_judge"], "source": agent, "round": rnd,
        "blocking": "[]", "created_at": iso(), "answered_at": None})
    flags = ctx.refresh().get("flags") or {}
    if not build:  # the planner says it in the chat (one line each): the board alone is not where the user looks
        set_state(ctx, flags={"void_notices": list(flags.get("void_notices") or []) + [{"title": d["title"], "by": agent,
                                                                                         "decision": did}]})
    if build and not flags.get("core_frozen"):
        set_state(ctx, flags={"core_freeze_request": {"by": agent, "title": d["title"], "why": d.get("context", ""),
                                                      "round": rnd, "decision": did}})
    ctx.event("decision.not_executed", did, {"by": agent, "title": d["title"], "build_start": build})
    return did


def settle_cards(ctx: Ctx, did: str, qids: Any) -> int:
    """P-08 (problem 1): a decision taken by its recommendation without asking (D3, or D2 under autonomy) left the
    cards it settled open — and earlier rounds' open cards are shown again in the round report. The decision names
    them (`questions`); they close as assumed (the decision's answer is the assumption)."""
    row = db.one(ctx.conn, "SELECT status, answer FROM decisions WHERE id=?", (did,)) or {}
    ids = [str(q) for q in qids or [] if isinstance(q, str) and q.startswith("Q-")] if isinstance(qids, list) else []
    if row.get("status") != "auto" or not ids:
        return 0
    n = ctx.conn.execute(f"UPDATE questions SET status='assumed', updated_at=? WHERE id IN ({','.join('?' * len(ids))}) "
                         "AND status IN ('open','held')", (iso(), *ids)).rowcount
    if n:
        ctx.event("questions.settled", did, {"questions": ids, "answer": row.get("answer")})
    return n


def _engagement(ctx: Ctx, eng: dict) -> None:
    """The stakeholder mapper's engagement judgement (types E1–E8 with confidence and U ids, role map) replaces the
    signal-based guess in stage.detect."""
    from fde_mode import stage
    types = [{"code": t["code"], "label": stage.ENGAGEMENT[t["code"]], "confidence": rubric.conf_norm(t.get("confidence")),
              "evidence": [str(x) for x in (t.get("evidence") if isinstance(t.get("evidence"), list) else [])]}
             for t in eng["types"] if isinstance(t, dict) and t.get("code") in stage.ENGAGEMENT]
    if not types:
        return
    roles = {}  # only what the seat named (its 모름 too: it overrules a signal); stage.detect fills the rest
    given = eng.get("roles") if isinstance(eng.get("roles"), dict) else {}
    for key, _ in stage.ROLES:
        r = given.get(key)
        if isinstance(r, dict) and str(r.get("who") or "").strip():
            roles[key] = {"who": str(r["who"]), "evidence": [str(x) for x in (r.get("evidence") if isinstance(r.get("evidence"), list) else [])]}
    best = min((t["confidence"] for t in types), key=lambda c: stage.CONF_RANK.get(c, 3))
    ctx.conn.execute("INSERT INTO engagement(id, types, roles, confidence, evidence, source, updated_at) VALUES(1,?,?,?,?,?,?) "
                     "ON CONFLICT(id) DO UPDATE SET types=excluded.types, roles=excluded.roles, confidence=excluded.confidence, "
                     "evidence=excluded.evidence, source=excluded.source, updated_at=excluded.updated_at",
                     (dumps(types), dumps(roles), best, dumps(sorted({x for t in types for x in t["evidence"]})), "seat", iso()))


def apply(ctx: Ctx, dispatch: dict, data: dict) -> dict[str, int]:
    """Fold one validated output into the database. Returns counts per section."""
    run = dispatch["run"]
    rnd = db.scalar(ctx.conn, "SELECT round FROM runs WHERE id=?", (run,), "") or ""
    agent = dispatch["agent"]
    division = BY_NAME[agent].division if agent in BY_NAME else ""
    counts: dict[str, int] = {}

    if data.get("utterance_updates"):
        counts["utterances"] = transcript.apply_updates(ctx, data["utterance_updates"])

    for i_c, c in enumerate(data.get("candidates") or [], 1):
        if not isinstance(c, dict):
            continue
        cid = f"{run}:{_short(agent)}:{dispatch['mode']}:{c.get('id') or i_c}"
        if c.get("revises"):
            # a complement revision replaces the agent's own earlier item (this run or the reused quick run)
            ctx.conn.execute("UPDATE candidates SET status='revised' WHERE agent=? AND round=? AND status='new' "
                             "AND id LIKE ?", (agent, rnd, f"%:{c['revises']}"))
        kind = c.get("kind") or "question"
        status = "new"
        if kind in ("question", "proposal") and not (c.get("decision_at_stake") or "").strip():
            status = "rejected:no-stake"  # rule: no decision at stake → not worth asking
        if kind == "risk":
            rid = db.next_id(ctx.conn, "risks", "K-")
            db.upsert(ctx.conn, "risks", {"id": rid, "text": c.get("gap") or c.get("if_wrong") or "", "severity":
                                          {"높음": "높음", "중간": "중간", "낮음": "낮음"}.get(c.get("impact_guess", ""), "중간"),
                                          "source": agent, "round": rnd, "status": "open", "payload": dumps(c)})
            status = "routed:risk"
        if kind == "decision":
            D.add(ctx, title=c.get("gap") or c.get("question_draft") or "결정 필요", grade=c.get("grade", "D2"),
                  context=c.get("decision_at_stake", ""), options=c.get("options") or [],
                  recommended=c.get("recommended", ""), source=agent, round_id=rnd,
                  blocking=c.get("blocking") or [])
            status = "routed:decision"
        db.upsert(ctx.conn, "candidates", {
            "id": cid, "round": rnd, "run": run, "agent": agent, "division": division, "kind": kind,
            "area": c.get("area", ""), "gap": c.get("gap", ""), "evidence": dumps(c.get("evidence") or []),
            "quote": c.get("quote", ""), "question_draft": c.get("question_draft", ""),
            "decision_at_stake": c.get("decision_at_stake", ""), "if_wrong": c.get("if_wrong", ""),
            "self_confidence": rubric.conf_norm(c.get("self_confidence")),
            "impact_guess": rubric.impact_norm(c.get("impact_guess")), "merged_into": None, "cite_ok": None,
            "status": status, "payload": dumps(c),
        })
        counts["candidates"] = counts.get("candidates", 0) + 1

    for r in data.get("requirements") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        prev = db.one(ctx.conn, "SELECT * FROM requirements WHERE id=?", (r["id"],))
        prio = r.get("priority") or ""
        if prio in ("", "미정") and prev and prev.get("priority") not in (None, "", "미정"):
            prio = prev["priority"]  # never lose a priority someone set because the registrar left it blank
        feas = r.get("feasibility") or (prev or {}).get("feasibility") or ""
        feas_note = r.get("feasibility_note") or (prev or {}).get("feasibility_note") or ""
        if prev and prev.get("frozen") and (prev.get("statement") != r.get("statement", prev.get("statement"))
                                             or prev.get("priority") != (prio or prev.get("priority"))):
            from fde_mode.state import set_state as _ss
            pend = list((ctx.refresh().get("flags") or {}).get("pending_changes") or [])
            pend.append({"requirement": r["id"], "before": prev.get("statement"), "after": r.get("statement"), "round": rnd})
            _ss(ctx, flags={"pending_changes": pend})
        if not prev and (r.get("priority") == "must") and (ctx.refresh().get("flags") or {}).get("core_frozen"):
            from fde_mode.state import set_state as _ss
            pend = list((ctx.state.get("flags") or {}).get("pending_changes") or [])
            pend.append({"requirement": r["id"], "before": None, "after": r.get("statement"), "round": rnd, "new_must": True})
            _ss(ctx, flags={"pending_changes": pend})
        db.upsert(ctx.conn, "requirements", {
            "id": r["id"], "type": r.get("type", ""), "statement": r.get("statement", ""),
            "status": r.get("status", "가정"), "evidence": dumps(r.get("evidence") or []), "quote": r.get("quote", ""),
            "confidence": rubric.conf_norm(r.get("confidence")), "priority": prio or "미정",
            "feasibility": feas, "feasibility_note": feas_note,
            "conflict": dumps(r.get("conflict") or []), "since_round": (prev or {}).get("since_round") or r.get("since_round") or rnd,
            "changed_round": rnd if (prev is None or (prev.get("statement") != r.get("statement") or prev.get("priority") != (prio or "미정"))) else (prev or {}).get("changed_round"),
            "confirmed": int(bool(r.get("confirmed"))), "frozen": (prev or {}).get("frozen") or 0, "payload": dumps(r),
        })
        counts["requirements"] = counts.get("requirements", 0) + 1

    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
    eng = extra.get("engagement")
    if agent == "fde-stakeholder-mapper" and isinstance(eng, dict) and isinstance(eng.get("types"), list):
        try:  # an oddly shaped engagement block must never cost the seat's other output
            _engagement(ctx, eng)
        except Exception as e:  # noqa: BLE001
            ctx.event("sync.engagement_error", run, {"error": repr(e)})
    if agent == "fde-release-manager":  # S8: the operator's guide and (outsourced / public service) the handover
        for key, name, title in (("operations", "operations.md", "운영 안내"), ("handover", "handover.md", "인수인계")):
            v = extra.get(key)
            if isinstance(v, (str, list)) and v:
                body = v if isinstance(v, str) else "\n".join(f"- {x}" for x in v)
                write_text(ctx.p.docs / name, f"# {title}\n\n{scrub(body)}\n")
    for f in extra.get("feasibility") or []:  # platform constraints inspector → requirement feasibility
        if isinstance(f, dict) and f.get("requirement") and f.get("verdict") in ("가능", "주의", "불가"):
            note = " / ".join(x for x in (f.get("why"), ("대안: " + f["alternative"]) if f.get("alternative") else "") if x)
            ctx.conn.execute("UPDATE requirements SET feasibility=?, feasibility_note=? WHERE id=?",
                             (f["verdict"], note, f["requirement"]))
    for led in extra.get("ledger") or []:  # scope manager → priority only where nobody set one yet
        if isinstance(led, dict) and str(led.get("req", "")).startswith("R-") and led.get("proposed") in ("must", "should", "could"):
            ctx.conn.execute("UPDATE requirements SET priority=? WHERE id=? AND (priority IS NULL OR priority IN ('', '미정'))",
                             (led["proposed"], led["req"]))
    for i_n, nc in enumerate(extra.get("next_round_candidates") or [], 1):  # lead's conflict questions → next round
        if isinstance(nc, dict) and nc.get("gap"):
            db.upsert(ctx.conn, "candidates", {
                "id": f"{run}:{_short(agent)}:carry:N{i_n}", "round": rnd, "run": run, "agent": agent, "division": division,
                "kind": "question", "area": nc.get("area", ""), "gap": nc["gap"], "evidence": dumps(nc.get("evidence") or []),
                "quote": nc.get("quote", ""), "question_draft": nc.get("question_draft", ""),
                "decision_at_stake": nc.get("decision_at_stake") or nc.get("why", ""), "if_wrong": nc.get("if_wrong", ""),
                "self_confidence": rubric.conf_norm(nc.get("self_confidence") or "추측"),
                "impact_guess": rubric.impact_norm(nc.get("impact_guess") or "중간"), "merged_into": None, "cite_ok": None,
                "status": "carry", "payload": dumps(nc)})

    for d in data.get("decisions") or []:
        if isinstance(d, dict) and d.get("title") and (d.get("kind") == "build_start" or agent == "fde-freeze-judge"):
            not_executable(ctx, agent, d, rnd)
            counts["not_executed"] = counts.get("not_executed", 0) + 1
            continue
        if isinstance(d, dict) and d.get("title"):
            did = D.add(ctx, title=d["title"], grade=d.get("grade", "D2"), context=d.get("context", ""),
                        options=d.get("options") or [], recommended=d.get("recommended", ""), source=agent,
                        round_id=rnd, blocking=d.get("blocking") or [],
                        authoritative=agent in ("fde-engagement-lead", "fde-tech-lead"))
            settle_cards(ctx, did, d.get("questions"))
            counts["decisions"] = counts.get("decisions", 0) + 1

    for a in data.get("assumptions") or []:
        if isinstance(a, dict) and a.get("text"):
            aid = a.get("id") or db.next_id(ctx.conn, "assumptions", "A-")
            db.upsert(ctx.conn, "assumptions", {"id": aid, "text": a["text"], "reason": a.get("reason", ""),
                                                "related": dumps(a.get("related") or []), "round": rnd,
                                                "status": a.get("status", "proposed")})
            counts["assumptions"] = counts.get("assumptions", 0) + 1

    for t in data.get("tests") or []:
        if isinstance(t, dict) and (t.get("input") or t.get("expected")):
            tid = t.get("id") if str(t.get("id", "")).startswith("T-") else db.next_id(ctx.conn, "tests", "T-")
            db.bump(ctx.conn, "tests", "T-", tid)
            db.upsert(ctx.conn, "tests", {"id": tid, "requirements": dumps(t.get("requirements") or []),
                                          "input": t.get("input", ""), "expected": t.get("expected", ""),
                                          "fail_if": t.get("fail_if", ""), "source": dumps(t.get("source") or []),
                                          "status": t.get("status", "draft"), "payload": dumps(t)})
            counts["tests"] = counts.get("tests", 0) + 1

    for rk in data.get("risks") or []:
        if isinstance(rk, dict) and rk.get("text"):
            rid = rk.get("id") if str(rk.get("id", "")).startswith("K-") else db.next_id(ctx.conn, "risks", "K-")
            db.upsert(ctx.conn, "risks", {"id": rid, "text": rk["text"], "severity": rk.get("severity", "중간"),
                                          "source": agent, "round": rnd, "status": rk.get("status", "open"),
                                          "payload": dumps(rk)})

    for v in data.get("verdicts") or []:
        if not isinstance(v, dict) or not v.get("candidate"):
            continue
        source = "counter" if dispatch["mode"] == "counter" else "verify"
        db.upsert(ctx.conn, "verdicts", {
            "candidate": v["candidate"], "round": rnd, "source": source,
            "confidence": rubric.conf_norm(v.get("confidence")) if v.get("confidence") else None,
            "impact": rubric.impact_norm(v.get("impact")) if v.get("impact") else None,
            "already_answered": int(bool(v.get("already_answered"))), "forced": int(bool(v.get("forced"))),
            "verdict": v.get("verdict", ""), "reason": v.get("reason", ""), "payload": dumps(v),
        }, key=("candidate", "round", "source"))
        counts["verdicts"] = counts.get("verdicts", 0) + 1

    for m in data.get("merged") or []:
        if not isinstance(m, dict):
            continue
        members = [x for x in m.get("members") or [] if isinstance(x, str)]
        if m.get("drop_reason"):
            for x in members:
                ctx.conn.execute("UPDATE candidates SET status=? WHERE id=?", (f"dropped:{m['drop_reason']}", x))
            continue
        mid = db.next_id(ctx.conn, "candidates", f"M-{rnd}-", width=2)
        base = db.one(ctx.conn, "SELECT * FROM candidates WHERE id=?", (members[0],)) if members else None
        evidence = sorted({e for x in members for e in json.loads((db.one(ctx.conn, "SELECT evidence FROM candidates WHERE id=?", (x,)) or {}).get("evidence") or "[]")} | set(m.get("evidence") or []))
        db.upsert(ctx.conn, "candidates", {
            "id": mid, "round": rnd, "run": run, "agent": "fde-candidate-merger", "division": "command",
            "kind": m.get("kind") or (base or {}).get("kind") or "question", "area": m.get("area") or (base or {}).get("area", ""),
            "gap": m.get("gap") or (base or {}).get("gap", ""), "evidence": dumps(evidence),
            "quote": m.get("quote") or (base or {}).get("quote", ""),
            "question_draft": m.get("question_draft") or (base or {}).get("question_draft", ""),
            "decision_at_stake": m.get("decision_at_stake") or (base or {}).get("decision_at_stake", ""),
            "if_wrong": m.get("if_wrong") or (base or {}).get("if_wrong", ""),
            "self_confidence": rubric.conf_norm(m.get("self_confidence") or (base or {}).get("self_confidence")),
            "impact_guess": rubric.impact_norm(m.get("impact_guess") or (base or {}).get("impact_guess")),
            "merged_into": None, "cite_ok": None, "status": "merged",
            "payload": dumps({"members": members, "sources": len(members), "divisions": m.get("divisions") or []}),
        })
        for x in members:
            ctx.conn.execute("UPDATE candidates SET merged_into=? WHERE id=?", (mid, x))
        counts["merged"] = counts.get("merged", 0) + 1

    for card in data.get("cards") or []:
        if not isinstance(card, dict):
            continue
        qid = card.get("question") or card.get("id")
        if qid and card.get("text"):
            ctx.conn.execute("UPDATE questions SET text=?, ord=COALESCE(?, ord), updated_at=? WHERE id=?",
                             (card["text"].strip(), card.get("order"), iso(), qid))
            counts["cards"] = counts.get("cards", 0) + 1

    for s in data.get("sequence") or []:
        if isinstance(s, dict) and s.get("question"):
            ctx.conn.execute("UPDATE questions SET ord=? WHERE id=?", (int(s.get("order") or 0), s["question"]))

    debate = data.get("debate")
    if isinstance(debate, dict):
        def _did(ref: str) -> str:
            # "<agent>:<local id>" (agent with or without the plugin prefix / fde-) → the stored issue id
            ref = str(ref or "").removeprefix("fde-mode:")
            if ref.startswith(f"{run}:"):
                return ref
            ag, _, loc = ref.rpartition(":") if ref.count(":") >= 1 else (ref, "", "1")
            short = _short(ag.split(":")[-1])
            hit = db.one(ctx.conn, "SELECT id FROM debates WHERE id LIKE ? ORDER BY CASE WHEN id LIKE ? THEN 0 ELSE 1 END LIMIT 1",
                         (f"{run}:{short}:%:{loc}", f"{run}:{short}:review:{loc}"))
            return hit["id"] if hit else f"{run}:{short}:review:{loc or '1'}"

        def _append(did: str, topic: str, text: str, stance: str, evidence: list, extra: dict | None = None) -> None:
            prev = db.one(ctx.conn, "SELECT * FROM debates WHERE id=?", (did,))
            positions = json.loads((prev or {}).get("positions") or "[]")
            positions.append({"by": agent, "mode": dispatch["mode"], "text": text, "stance": stance,
                              "evidence": evidence or [], **(extra or {})})
            db.upsert(ctx.conn, "debates", {
                "id": did, "round": rnd, "topic": topic or (prev or {}).get("topic", ""), "positions": dumps(positions),
                "ruling": (prev or {}).get("ruling"), "minority": (prev or {}).get("minority") or "[]",
                "status": (prev or {}).get("status") or "open"})

        for i, item in enumerate(debate.get("issues") or [], 1):
            if isinstance(item, dict):
                did = f"{run}:{_short(agent)}:{dispatch['mode']}:{item.get('id') or ('X' + str(i))}"
                _append(did, item.get("topic", ""), item.get("position", ""), item.get("stance", ""),
                        item.get("evidence") or [], {"target": item.get("target", "")})
        for item in debate.get("responses") or []:
            if isinstance(item, dict) and item.get("replies_to"):
                _append(_did(item["replies_to"]), item.get("topic", ""), item.get("position", ""),
                        item.get("stance", ""), item.get("evidence") or [])
        for i, item in enumerate(debate.get("rulings") or [], 1):
            if not isinstance(item, dict):
                continue
            did = _did(item["issue"]) if item.get("issue") else f"{run}:{_short(agent)}:ruling:R{i}"
            prev = db.one(ctx.conn, "SELECT * FROM debates WHERE id=?", (did,))
            db.upsert(ctx.conn, "debates", {
                "id": did, "round": rnd, "topic": item.get("topic") or (prev or {}).get("topic", ""),
                "positions": (prev or {}).get("positions") or "[]", "ruling": item.get("ruling", ""),
                "minority": dumps(item.get("minority") or []), "status": item.get("status") or "ruled"})

    for t in (data.get("plan") or {}).get("tasks", []) if isinstance(data.get("plan"), dict) else []:
        if isinstance(t, dict) and t.get("title"):
            tid = t.get("id") if str(t.get("id", "")).startswith("B-") else db.next_id(ctx.conn, "tasks", "B-")
            db.bump(ctx.conn, "tasks", "B-", tid)
            db.upsert(ctx.conn, "tasks", {"id": tid, "kind": t.get("kind", "build"), "title": t["title"],
                                          "requirements": dumps(t.get("requirements") or []), "files": dumps(t.get("files") or []),
                                          "owner": t.get("owner", "fde-tool-developer"), "status": "todo",
                                          "depends": dumps(t.get("depends") or []), "loops": 0, "created_at": iso(),
                                          "done_at": None, "notes": dumps({"slice": t.get("slice", 1), "acceptance": t.get("acceptance", ""),
                                                                           "designers": t.get("designers") or []})})

    for a in data.get("adrs") or []:
        if isinstance(a, dict) and a.get("title"):
            aid = a.get("id") if str(a.get("id", "")).startswith("ADR-") else db.next_id(ctx.conn, "adrs", "ADR-")
            db.bump(ctx.conn, "adrs", "ADR-", aid)
            db.upsert(ctx.conn, "adrs", {"id": aid, "title": a["title"], "decision": a.get("decision", ""),
                                         "alternatives": dumps(a.get("alternatives") or []), "dissent": a.get("dissent", ""),
                                         "requirements": dumps(a.get("requirements") or []), "rollback": a.get("rollback", ""),
                                         "grade": a.get("grade", "D2"), "status": a.get("status", "proposed"),
                                         "path": a.get("path", "")})
            if a.get("grade") in ("D1", "D2") and a.get("status", "proposed") == "proposed":
                D.add(ctx, title=f"[기술] {a['title']}", grade=a.get("grade", "D2"), context=a.get("decision", ""),
                      options=[a.get("decision", "")] + [x.get("option", str(x)) if isinstance(x, dict) else str(x)
                                                        for x in a.get("alternatives") or []],
                      recommended=a.get("decision", ""), source=agent, round_id=rnd, blocking=a.get("blocking") or [])

    rel = data.get("release")
    if isinstance(rel, dict) and not rel.get("tag") and rel.get("good") is False:
        rel = {**rel, "id": f"{run}-fail"}  # H-19: a failed slice has no tag but belongs in the release history too
    if isinstance(rel, dict) and (rel.get("tag") or rel.get("id")):
        db.upsert(ctx.conn, "releases", {"id": rel.get("tag") or rel["id"], "tag": rel.get("tag") or "", "commit_sha": rel.get("commit", ""),
                                         "created_at": iso(), "test": rel.get("test", ""), "deploy": rel.get("deploy", ""),
                                         "health": rel.get("health", ""), "qa": rel.get("qa", ""),
                                         "good": int(bool(rel.get("good"))), "notes": rel.get("notes", "")})

    for asset in (data.get("data_report") or {}).get("assets", []) if isinstance(data.get("data_report"), dict) else []:
        if isinstance(asset, dict) and asset.get("path"):
            known = db.one(ctx.conn, "SELECT id FROM data_assets WHERE path=?", (asset["path"],))
            aid = (known or {}).get("id") or asset.get("id") or db.next_id(ctx.conn, "data_assets", "DA-")
            db.upsert(ctx.conn, "data_assets", {"id": aid, "name": asset.get("name", Path(asset["path"]).name),
                                                "path": asset["path"], "kind": asset.get("kind", ""),
                                                "source": asset.get("source", ""), "status": asset.get("status", ""),
                                                "rows": asset.get("rows"), "report": asset.get("report", ""),
                                                "notes": asset.get("notes", ""), "updated_at": iso()})

    if isinstance(data.get("implementation"), dict):
        for tid in data["implementation"].get("tasks_done") or []:
            ctx.conn.execute("UPDATE tasks SET status='done', done_at=? WHERE id=?", (iso(), tid))
        for b in data["implementation"].get("tasks_blocked") or []:
            # "B-003", or {"task": "B-003", "reason", "design_question": {"title","options","recommended"}} — a design
            # choice the developer must not make alone; the slice raises it to the user (planner.s_impl_questions)
            tid = b.get("task") if isinstance(b, dict) else b
            if not isinstance(tid, str):
                continue
            ctx.conn.execute("UPDATE tasks SET status='blocked' WHERE id=?", (tid,))
            q = b.get("design_question") if isinstance(b, dict) else None
            if isinstance(q, dict) and q.get("title"):
                notes = json.loads(db.scalar(ctx.conn, "SELECT notes FROM tasks WHERE id=?", (tid,), "{}") or "{}")
                notes["design_question"] = q
                notes.pop("design_decision", None)
                ctx.conn.execute("UPDATE tasks SET notes=? WHERE id=?", (dumps(notes), tid))

    db.upsert(ctx.conn, "artifacts", {"path": dispatch["output"], "run": run, "agent": agent, "mode": dispatch["mode"],
                                      "round": rnd, "mtime": Path(ctx.p.root / dispatch["output"]).stat().st_mtime
                                      if (ctx.p.root / dispatch["output"]).exists() else 0,
                                      "summary": scrub(data.get("summary_ko") or "")[:500], "json": dumps(scrub_values(data))},
              key="path")  # H-30: a command tail with a key never reaches the dashboard
    return counts


def load_output(ctx: Ctx, dispatch: dict) -> tuple[dict | None, list[str]]:
    path = ctx.p.root / dispatch["output"]
    if not path.exists():
        return None, ["output file not written"]
    data = read_json(path)
    if data is None:
        return None, ["output is not valid JSON"]
    errs = validate(data, dispatch)
    return (data if not errs else None), errs
