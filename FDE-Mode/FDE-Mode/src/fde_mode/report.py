"""Files the agents read (snapshots, blinded packs) and files the user reads
(round report, board, spec). All Korean on the user-facing side."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fde_mode import db, rubric
from fde_mode.state import Ctx, PHASES, effective_switches, timeline
from fde_mode.util import iso, read_json, short, write_json, write_text


# ---------------- snapshots for agents ----------------

def snapshots(ctx: Ctx) -> dict[str, str]:
    """Write the current state of shared registries as JSON files agents can read."""
    snap = ctx.p.work / "snapshots"
    reqs = db.rows(ctx.conn, "SELECT * FROM requirements ORDER BY id")
    for r in reqs:
        for k in ("evidence", "conflict", "payload"):
            r[k] = json.loads(r.get(k) or ("{}" if k == "payload" else "[]"))
    qs = db.rows(ctx.conn, "SELECT id, round, text, confidence, impact, bucket, status, asked_u, answer_us, "
                           "decision_at_stake FROM questions ORDER BY id")
    for q in qs:
        q["answer_us"] = json.loads(q.get("answer_us") or "[]")
    decs = db.rows(ctx.conn, "SELECT id, grade, title, status, answer, recommended, round, source FROM decisions ORDER BY id")
    asm = db.rows(ctx.conn, "SELECT * FROM assumptions ORDER BY id")
    tests = db.rows(ctx.conn, "SELECT id, requirements, input, expected, fail_if, status FROM tests ORDER BY id")
    risks = db.rows(ctx.conn, "SELECT id, text, severity, status FROM risks ORDER BY id")
    tasks = db.rows(ctx.conn, "SELECT * FROM tasks ORDER BY id")
    for t in tasks:
        for k in ("requirements", "files", "depends"):
            t[k] = json.loads(t.get(k) or "[]")
        t["notes"] = json.loads(t.get("notes") or "{}")
    files = {
        "tasks": write_json(snap / "tasks.json", tasks),
        "requirements": write_json(snap / "requirements.json", reqs),
        "questions": write_json(snap / "questions.json", qs),
        "decisions": write_json(snap / "decisions.json", decs),
        "assumptions": write_json(snap / "assumptions.json", asm),
        "tests": write_json(snap / "acceptance-tests.json", tests),
        "risks": write_json(snap / "risks.json", risks),
    }
    return {k: str(v) for k, v in files.items()}


def blind_pack(ctx: Ctx, run: str, out_path: Path) -> dict[str, Any]:
    """What the independent seat may see: the gap, the drafted question and the
    evidence pointers. Never who proposed it, how sure they were, or how many agreed."""
    cands = db.rows(ctx.conn, "SELECT * FROM candidates WHERE run=? AND status='merged' AND kind NOT IN ('risk','decision')", (run,))
    if not cands:
        cands = db.rows(ctx.conn, "SELECT * FROM candidates WHERE run=? AND status='new' AND "
                                  "(merged_into IS NULL OR merged_into='') AND kind IN ('question','proposal','assumption')",
                        (run,))
    items = [{"candidate": c["id"], "kind": c["kind"], "gap": c["gap"], "question_draft": c["question_draft"],
              "evidence": json.loads(c.get("evidence") or "[]"), "quote": c.get("quote", ""),
              "cite_ok": c.get("cite_ok")} for c in cands]
    data = {"run": run, "candidates": items, "note": "출처 에이전트·자기 확신도·동의 수는 일부러 뺐습니다."}
    write_json(out_path, data)
    return data


# ---------------- round report ----------------

def _artifact_json(a: dict | None) -> dict:
    try:  # a stored output that does not parse must never stop the round report
        d = json.loads(a["json"]) if a else {}
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _lead_output(ctx: Ctx, run: str) -> dict:
    a = db.one(ctx.conn, "SELECT json FROM artifacts WHERE run=? AND agent='fde-engagement-lead' "
                         "ORDER BY mtime DESC LIMIT 1", (run,))
    return _artifact_json(a)


def _coach_output(ctx: Ctx, run: str, rnd: str = "") -> dict:
    a = db.one(ctx.conn, "SELECT json FROM artifacts WHERE run=? AND agent='fde-interviewer-coach' "
                         "ORDER BY mtime DESC LIMIT 1", (run,))
    if not a and rnd:  # a debate round reuses the coach output of that round's quick run
        a = db.one(ctx.conn, "SELECT json FROM artifacts WHERE round=? AND agent='fde-interviewer-coach' "
                             "ORDER BY mtime DESC LIMIT 1", (rnd,))
    return _artifact_json(a)


def _to_interviewer(coach: dict) -> dict:
    extra = coach.get("extra") if isinstance(coach.get("extra"), dict) else {}
    t = coach.get("to_interviewer") or extra.get("to_interviewer") or {}
    return t if isinstance(t, dict) else {}


def _items(v: Any) -> list:
    return v if isinstance(v, list) else ([v] if isinstance(v, (str, dict)) and v else [])


def _txt(v: Any) -> str:
    return v if isinstance(v, str) else ("" if v is None else str(v))


def _mistake_history(ctx: Ctx) -> dict[str, list[str]]:
    """Mistake kinds per round across every coach output so far — the code, not the coach's memory, says
    "the same mistake twice"."""
    seen: dict[str, set[str]] = {}
    for a in db.rows(ctx.conn, "SELECT round, json FROM artifacts WHERE agent='fde-interviewer-coach' ORDER BY mtime"):
        for m in _items(_to_interviewer(_artifact_json(a)).get("mistakes")):
            if isinstance(m, dict) and m.get("kind"):
                seen.setdefault(str(m["kind"]).strip(), set()).add(a["round"] or "")
    return {k: sorted(v) for k, v in seen.items()}


def _interviewer_section(ctx: Ctx, coach: dict, qs: list[dict], rnd: str) -> list[str]:
    """W3: what the user (the interviewer) should fix, ask and say next — first in every round report."""
    if not coach:  # the coach did not run (comms division off, a failed dispatch): still lead with what to ask next
        if not qs:
            return []
        return ["### 인터뷰어에게", "", "_(이번 라운드는 인터뷰어 코치 출력이 없어 지금 물어볼 카드로만 채웠습니다)_", "",
                "**빠진 질문**", *[f"- {q['id']} [{q['confidence']} | 영향 {q['impact']}] {short(q['text'], 60)} — 지금 물어야 하는 이유: "
                                  f"{q.get('decision_at_stake') or '답에 따라 설계가 바뀜'}" for q in qs[:3]], ""]
    t = _to_interviewer(coach)
    lines = ["### 인터뷰어에게", ""]
    mistakes = [m for m in _items(t.get("mistakes")) if isinstance(m, dict)][:3]
    history = _mistake_history(ctx)
    habits = [h for h in _items(t.get("habits")) if isinstance(h, (dict, str))]
    repeated = [(k, r) for k, r in history.items() if len(r) >= 2 and rnd in r]  # repeated, and again this round
    if mistakes:
        lines.append("**이번 라운드에서 고칠 점**")
        for i, m in enumerate(mistakes, 1):
            ids = ", ".join(_txt(e) for e in _items(m.get("evidence") or m.get("utterance")) if not isinstance(e, dict))
            conf = f" [{_txt(m['confidence'])}]" if m.get("confidence") else ""
            lines.append(f"{i}. {ids + ' · ' if ids else ''}{_txt(m.get('kind')) or '고칠 점'}{conf} — {_txt(m.get('why') or m.get('text'))}")
            if m.get("better"):
                lines.append(f"   → 이렇게: \"{_txt(m['better'])}\"")
        lines.append("")
    elif t:
        lines += ["이번 라운드는 고칠 점 없음.", ""]
    missing = [x for x in _items(t.get("missing_questions")) if isinstance(x, (dict, str))][:3]
    lines.append("**빠진 질문**")
    if missing:
        for x in missing:
            if isinstance(x, str):
                lines.append(f"- {x}")
            else:
                head = " ".join(v for v in (_txt(x.get("question") or x.get("id")), f"[{_txt(x['confidence'])} | 영향 {_txt(x.get('impact', '-'))}]" if x.get("confidence") else "") if v)
                lines.append(f"- {head} {_txt(x.get('text'))} — 지금 물어야 하는 이유: {_txt(x.get('why_now') or x.get('why')) or '-'}".replace("  ", " "))
    elif qs:
        for q in qs[:3]:
            lines.append(f"- {q['id']} [{q['confidence']} | 영향 {q['impact']}] {short(q['text'], 60)} — 지금 물어야 하는 이유: "
                         f"{q.get('decision_at_stake') or '답에 따라 설계가 바뀜'}")
    else:
        lines.append("- 지금 꼭 물어야 할 질문 없음")
    lines.append("")
    moves = [x for x in _items(t.get("next_moves")) if x][:3]
    if moves:
        lines.append("**다음 대화 제안**")
        lines += [f"- {_txt(x.get('say') or x.get('text')) + (' (' + _txt(x['why']) + ')' if x.get('why') else '') if isinstance(x, dict) else _txt(x)}"
                  for x in moves]
        lines.append("")
    if repeated or habits:
        lines.append("**반복 습관**")
        for k, rounds in repeated:
            lines.append(f"- **⚠ {k} — {len(rounds)}번째 라운드({'·'.join(r for r in rounds if r)})**")
        for h in habits[:3]:
            text = h if isinstance(h, str) else _txt(h.get("text") or h.get("habit"))
            if text and not any(k in text for k, _ in repeated):
                lines.append(f"- {text}")
        lines.append("")
    fb = (coach.get("extra") if isinstance(coach.get("extra"), dict) else {}).get("feedback")
    if fb and not t:  # an older coach output without to_interviewer: still show its lines here
        lines += ["**코치 의견**", *([f"- {fb}"] if isinstance(fb, str) else [f"- {x}" for x in fb]), ""]
    return lines


IMPACT_RANK = {"높음": 0, "중간": 1, "낮음": 2}


def _open_cards(ctx: Ctx, rnd: str, top_n: int) -> list[dict]:
    """The cards to ask now: this round's ask cards in the sequencer's order, then earlier rounds' still-open cards
    by impact, then this round's proposals. An earlier card always keeps one of the top_n places when one is open
    (problem 1: a data request opened in R02 was never shown again — a third of the lost hidden needs were lost
    at the card stage)."""
    rows = db.rows(ctx.conn, "SELECT * FROM questions WHERE bucket IN ('ask','propose') AND status='open'")
    now_ask = sorted((q for q in rows if q["round"] == rnd and q["bucket"] == "ask"), key=lambda q: q["ord"] or 0)
    now_prop = sorted((q for q in rows if q["round"] == rnd and q["bucket"] == "propose"), key=lambda q: q["ord"] or 0)
    older = sorted((q for q in rows if q["round"] != rnd),
                   key=lambda q: (IMPACT_RANK.get(q.get("impact"), 3), 0 if q["bucket"] == "ask" else 1,
                                  str(q["round"] or ""), q["ord"] or 0))
    # G4: this round's stage cards (no evidence, a guess) come after earlier 높음 analyst cards; only the type question
    # (ord −1, asked while the type is unknown) stays first
    now_stage = [q for q in now_ask if '"stage"' in (q.get("lens") or "") and (q.get("ord") or 0) >= 0]
    now_ask = [q for q in now_ask if q not in now_stage]
    out = (now_ask + [q for q in older if q.get("impact") == "높음"] + now_stage + now_prop
           + [q for q in older if q.get("impact") != "높음"])
    # the place is for an earlier analyst card first: a stage card (the type question left open) must not take it
    pool = [q for q in older if '"stage"' not in (q.get("lens") or "")] or older
    if pool and top_n >= 2 and not any(q in pool for q in out[:top_n]):
        out.remove(pool[0])
        out.insert(top_n - 1, pool[0])  # the best earlier card takes the last shown place
    return out


def _stage_lines(ctx: Ctx, rnd: str) -> list[str]:
    """Stage map S1–S8 in one line, a go-back recommendation when an earlier stage reopened, the top 3 gaps."""
    if not ctx.switch("stage_map"):
        return []
    try:
        from fde_mode import stage
        s = stage.summary({**stage.compute(ctx), "stages": {r["id"]: r for r in db.rows(ctx.conn, "SELECT * FROM stages")}})
    except Exception as e:  # noqa: BLE001
        ctx.event("report.stage_error", rnd, {"error": repr(e)})
        return []
    e = s["engagement"]
    kinds = ", ".join(f"{t['code']} {t['label']} [{t['confidence']}]" for t in e["types"] if not t.get("new"))
    out = [f"**단계 지도** {stage.line(s)}", f"- 의뢰 유형: {kinds or '모름'}"]
    for t in (t for t in e["types"] if t.get("new")):
        out.append(f"- 새 유형 신호: {t['code']} {t['label']} ({', '.join(t['evidence'][:3])}) — 확인 필요")
    lead = (e["types"] or [{}])[0].get("code")
    if lead in stage.MUST_KNOW and lead != "E8":
        out.append(f"- {lead} 꼭 알아야 할 것: {' · '.join(stage.MUST_KNOW[lead])}")
    # the role gaps the persona's words have not closed (inside judgement), named as pending the stakeholder seat
    pending = [stage.ROLE_SHORT[g["role"]] for x in s["stages"] if x["id"] == "S1" for g in x["gaps"] if g["key"].startswith("role:")]
    if pending:
        out.append(f"- 역할 확인 필요(이해관계자 좌석 판단 전): {', '.join(pending)}")
    back = [x for x in s["stages"] if x["status"] == "reopened"]
    askable = [g for g in (back[0]["gaps"] if back else []) if g.get("question") and not stage._panel_only(g)]
    if back and askable:
        out.append(f"- 되돌림 추천: {back[0]['id']} {back[0]['name']}로 돌아가 빈칸 {len(askable)}개를 묻는다"
                   " (협업 모드면 D2로 묻는다)")
    h = stage.holes(s, cards=stage.open_cards_by_gap(ctx))
    if h:
        out += ["- 허점 상위 3:", *[f"  {i}. {x}" for i, x in enumerate(h, 1)]]
    seen = []  # what the coach and the counter-arguer flagged per stage this round
    for a in db.rows(ctx.conn, "SELECT agent, json FROM artifacts WHERE round=? AND agent IN "
                               "('fde-interviewer-coach','fde-counter-arguer') ORDER BY mtime DESC", (rnd,)):
        try:  # a seat's output is data: any shape (extra as a list or a string, odd items) is skipped, never raised
            data = json.loads(a["json"] or "{}")
        except ValueError:
            continue
        extra = data.get("extra") if isinstance(data, dict) else None
        items = extra.get("stage_review") if isinstance(extra, dict) else None
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and it.get("text") and len(seen) < 3:
                kind = {"missed": "놓침", "assumption": "근거 없는 가정", "ask": "다음에 물을 것"}.get(
                    it["kind"] if isinstance(it.get("kind"), str) else "", "")
                ev = it.get("evidence") if isinstance(it.get("evidence"), list) else []
                st = it.get("stage") if isinstance(it.get("stage"), str) else ""
                seen.append(f"  - [{st}] {kind}: {short(str(it['text']), 90)}"
                            + (f" ({', '.join(map(str, ev))})" if ev else ""))
    if seen:
        out += ["- 좌석이 짚은 허점:", *seen]
    return out + [""]


def round_report(ctx: Ctx, run: str, rnd: str, ranked: dict | None, started: str | None, out_path: Path,
                 kind: str = "빠른 분석") -> str:
    lead = _lead_output(ctx, run).get("report") or {}
    coach = _coach_output(ctx, run, rnd)
    top_n = int(ctx.cfg.get("interview", {}).get("top_cards", 5))
    qs = _open_cards(ctx, rnd, top_n)
    held = db.rows(ctx.conn, "SELECT * FROM questions WHERE round=? AND bucket='hold'", (rnd,))
    utt = {u["id"]: u for u in db.rows(ctx.conn, "SELECT id, text FROM utterances")}
    lines = [f"## 라운드 {rnd} 분석 — {iso()[11:16]} ({kind})", ""]
    if started:
        lines.insert(1, f"_시작 {started[11:16]}_")
    note = db.scalar(ctx.conn, "SELECT note FROM rounds WHERE id=?", (rnd,), "{}")
    warns = (json.loads(note or "{}") or {}).get("warnings") or []
    try:  # an oddly shaped coach output must never stop the round report (the round would hang in 'analyzing')
        section = _interviewer_section(ctx, coach, qs, rnd)
    except Exception as e:  # noqa: BLE001
        ctx.event("report.coach_error", rnd, {"error": repr(e)})
        section = ["### 인터뷰어에게", "_코치 출력 형식이 맞지 않아 이 절을 만들지 못했습니다(대시보드 코치 출력 참고)._", ""]
    try:  # the stage lines are an overlay: whatever they meet, the round report still comes out
        smap = _stage_lines(ctx, rnd)
    except Exception as e:  # noqa: BLE001
        ctx.event("report.stage_error", rnd, {"error": repr(e)})
        smap = []
    if smap:  # stage map, go-back advice and the top 3 gaps lead "인터뷰어에게"
        section = (section[:2] if section else ["### 인터뷰어에게", ""]) + smap + section[2:]
    lines += section
    if warns:
        lines += ["**붙여넣기 경고**", *[f"- {w}" for w in warns], ""]
    try:  # N safety net (warning only): industry words FDE wrote that the persona, the brief and the data never said
        from fde_mode import convo
        dom = convo.domain_warnings(ctx)
    except Exception as e:  # noqa: BLE001 — never stops the round report
        ctx.event("report.domain_error", rnd, {"error": repr(e)})
        dom = []
    if dom:
        lines += ["**근거 없는 업종 낱말** — 인물 발화·브리프·받은 자료에 없습니다. 인물에게 묻거나 '가정'으로 표시하세요",
                  *[f"- 근거 없는 업종 낱말: {d['word']} ({', '.join(d['ids'][:5])})" for d in dom[:8]], ""]
    lines += [f"### 지금 물어볼 질문 ({min(top_n, len(qs))}개 / 후보 {len(qs)}개)", ""]
    for q in qs[:top_n]:
        flags = json.loads(q.get("flags") or "[]")
        lens = json.loads(q.get("lens") or "{}")
        ver = json.loads(q.get("verifier") or "{}")
        cnt = json.loads(q.get("counter") or "{}")
        tag = "제안" if q["bucket"] == "propose" else "질문"
        badge = (f"[{q['confidence']} | 영향 {q['impact']}" + (" | " + " · ".join(flags) if flags else "")
                 + (f" | 이전 라운드 {q['round']}" if q.get("round") != rnd else "") + "]")
        lines.append(f"**{q['id']}** {badge} ({tag})")
        lines.append(f"> {q['text']}")
        ev = json.loads(q.get("evidence") or "[]")
        if ev:
            quotes = "; ".join(f"{e} \"{short(utt.get(e, {}).get('text', ''), 50)}\"" for e in ev[:3])
            lines.append(f"- 근거: {quotes}")
        else:
            lines.append("- 근거: 발화 근거 없음")
        lines.append(f"- 답에 따라 바뀌는 것: {q.get('decision_at_stake') or '-'}")
        if "⚠ 렌즈·검증 불일치" in flags:
            lines.append(f"- 렌즈 판단: [{lens.get('confidence')}] / 검증관 판단: [{ver.get('confidence')}] — {ver.get('why') or ''}")
            lines.append("  → 직접 판단이 필요합니다")
        if cnt.get("verdict") in ("skip", "assume"):
            lines.append(f"- 반론관: {cnt.get('verdict')} — {cnt.get('why') or ''}")
        lines.append("")
    if len(qs) > top_n:
        lines.append(f"_나머지 {len(qs) - top_n}개는 대시보드 질문 카드에 있습니다._\n")
    if ranked:
        b = ranked["buckets"]
        if held:
            lines.append(f"### 보류 ({len(held)}개)")
            lines += [f"- {q['id']} [{q['confidence']}|{q['impact']}] {short(q['text'], 70)}" for q in held[:8]]
            lines.append("")
        if b["assume"]:
            lines.append(f"### 가정으로 처리 제안 ({len(b['assume'])}개) — 반대하면 말씀해 주세요")
            lines += [f"- {x.get('assumption', '')} {short(x.get('assumption_text') or x['gap'], 110)} ({x['reason']})"
                      for x in b["assume"][:8]]
            lines.append("")
        if b["drop"]:
            lines.append(f"### 억지·중복 판정으로 탈락 ({len(b['drop'])}개) — 잘못 버렸는지 확인용")
            lines += [f"- {short(x['gap'], 60)} → {x['reason']}" for x in b["drop"][:10]]
            lines.append("")
    if lead:
        if lead.get("opening_plan"):
            op = lead["opening_plan"]
            lines += ["### 인터뷰 첫 계획", op if isinstance(op, str) else "\n".join(f"- {x}" for x in op), ""]
        if lead.get("next_10min"):
            lines += ["### 다음 10분 인터뷰 전략", lead["next_10min"], ""]
        if lead.get("phase_advice"):
            lines += ["### 단계 조언", str(lead["phase_advice"]), ""]
        if lead.get("stale"):
            lines += ["### 그사이 낡은 항목(새 발화로 이미 답이 나왔거나 바뀜)", *[f"- {x}" for x in lead["stale"]], ""]
        if lead.get("conflicts"):
            lines += ["### 관점 충돌에서 나온 질문", *[f"- {c}" for c in lead["conflicts"]], ""]
        if lead.get("spec_changes"):
            lines += ["### 이번 라운드 스펙 변경", *[f"- {c}" for c in lead["spec_changes"]], ""]
        if lead.get("warnings"):
            lines += ["### 경고", *[f"- {w}" for w in lead["warnings"]], ""]
    rb = db.one(ctx.conn, "SELECT json FROM artifacts WHERE run=? AND agent='fde-readback-writer' ORDER BY mtime DESC LIMIT 1", (run,))
    if rb:
        text_rb = (json.loads(rb["json"]).get("readback") or {}).get("text")
        if text_rb:
            lines += ["### 확인 요약 — 인물에게 보여 주고 고쳐 달라고 해 보세요", f"> {text_rb}", ""]
    pend = db.rows(ctx.conn, "SELECT id, grade, title FROM decisions WHERE status IN ('new','asked') AND grade IN ('D1','D2')")
    if pend:
        lines += ["### 결정이 필요한 것", *[f"- {d['id']} [{d['grade']}] {d['title']}" for d in pend], ""]
    text = "\n".join(lines).rstrip() + "\n"
    write_text(out_path, text)
    return text


# ---------------- board ----------------

def board(ctx: Ctx) -> str:
    st = ctx.refresh()
    sw = effective_switches(ctx.cfg, st)
    tl = timeline(ctx.cfg)
    reqs = db.rows(ctx.conn, "SELECT id, statement, priority, status, confidence, feasibility FROM requirements "
                             "ORDER BY CASE priority WHEN 'must' THEN 0 WHEN 'should' THEN 1 WHEN 'could' THEN 2 ELSE 3 END, id")
    openq = db.scalar(ctx.conn, "SELECT COUNT(*) FROM questions WHERE status='open'", default=0)
    debates = db.rows(ctx.conn, "SELECT id, topic, status, ruling FROM debates ORDER BY id DESC LIMIT 8")
    decs = db.rows(ctx.conn, "SELECT id, grade, title, status, answer FROM decisions ORDER BY id DESC LIMIT 10")
    asm = db.rows(ctx.conn, "SELECT id, text, status FROM assumptions WHERE status IN ('active','proposed') ORDER BY id DESC LIMIT 10")
    lines = ["# 상황판", f"_갱신 {iso()[:16].replace('T', ' ')} · 단계 {st.get('phase')} {PHASES.get(st.get('phase'), '')} · 라운드 R{int(st.get('round') or 0):02d}_", ""]
    if len(tl) > 1:
        lines.append("**시간**: " + " · ".join(f"{k} {v['at']}({v['min_left']}분)" for k, v in tl.items() if isinstance(v, dict)))
        lines.append("")
    off = [k for k, v in sw.items() if v is False]
    if off:
        lines.append(f"**꺼진 스위치**: {', '.join(off)}\n")
    lines.append(f"## 요구사항 ({len(reqs)}) · 열린 질문 {openq}")
    for r in reqs[:30]:
        lines.append(f"- {r['id']} [{r['priority']}|{r['status']}|{r['confidence']}{'|' + r['feasibility'] if r['feasibility'] else ''}] {short(r['statement'], 90)}")
    lines.append("")
    if debates:
        lines.append("## 쟁점")
        lines += [f"- {d['id']} [{d['status']}] {short(d['topic'], 60)}" + (f" → {short(d['ruling'], 60)}" if d['ruling'] else "") for d in debates]
        lines.append("")
    if decs:
        lines.append("## 결정")
        lines += [f"- {d['id']} [{d['grade']}|{d['status']}] {short(d['title'], 70)}" + (f" → {short(d['answer'] or '', 40)}" if d['answer'] else "") for d in decs]
        lines.append("")
    if asm:
        lines.append("## 가정")
        lines += [f"- {a['id']} [{a['status']}] {short(a['text'], 90)}" for a in asm]
        lines.append("")
    heads = db.rows(ctx.conn, "SELECT agent, summary FROM artifacts WHERE mode='position' ORDER BY mtime DESC LIMIT 7")
    if heads:
        lines.append("## 본부별 현재 관심사")
        lines += [f"- {h['agent'].removeprefix('fde-')}: {short(h['summary'], 120)}" for h in heads]
    text = "\n".join(lines).rstrip() + "\n"
    write_text(ctx.p.board, text)
    return text


# ---------------- spec ----------------

def spec(ctx: Ctx) -> str:
    """The contract handed to the build organisation at freeze time."""
    reqs = db.rows(ctx.conn, "SELECT * FROM requirements ORDER BY id")
    tests = db.rows(ctx.conn, "SELECT * FROM tests ORDER BY id")
    asm = db.rows(ctx.conn, "SELECT * FROM assumptions WHERE status IN ('active','proposed','confirmed') ORDER BY id")
    decs = db.rows(ctx.conn, "SELECT * FROM decisions WHERE status IN ('answered','auto') ORDER BY id")
    adrs = db.rows(ctx.conn, "SELECT * FROM adrs ORDER BY id")
    risks = db.rows(ctx.conn, "SELECT * FROM risks WHERE status='open' ORDER BY id")
    assets = db.rows(ctx.conn, "SELECT * FROM data_assets ORDER BY id")
    persona = ctx.p.persona.read_text(encoding="utf-8") if ctx.p.persona.exists() else "(persona.md 없음)"
    pmap = ctx.p.docs / "personalization-map.md"
    lines = ["# 구현 명세 (spec.md)", f"_생성 {iso()[:16].replace('T', ' ')} · FDE-Mode가 DB에서 만든 문서. 손으로 고치지 말고 요구사항을 고칠 것_", ""]
    for pr in ("must", "should", "could", "미정"):
        rs = [r for r in reqs if (r.get("priority") or "미정") == pr]
        if not rs:
            continue
        lines.append(f"## 요구사항 — {pr}")
        for r in rs:
            ev = ", ".join(json.loads(r.get("evidence") or "[]"))
            lines.append(f"- **{r['id']}** [{r['type']}|{r['status']}|{r['confidence']}] {r['statement']}")
            if r.get("feasibility"):
                lines.append(f"  - 실현 가능성: {r['feasibility']} {r.get('feasibility_note') or ''}")
            if ev:
                lines.append(f"  - 근거: {ev}" + (f' — "{short(r.get("quote") or "", 80)}"' if r.get("quote") else ""))
        lines.append("")
    lines += ["## 인물 모델 (요약)", persona[:4000], ""]
    if pmap.exists():
        lines += ["## 개인화 표 (인물 패턴 → 봇 동작)", pmap.read_text(encoding="utf-8")[:4000], ""]
    if tests:
        lines.append("## 수용 테스트")
        lines += [f"- {t['id']} ({', '.join(json.loads(t.get('requirements') or '[]'))}) 입력: {short(t['input'], 80)} → 기대: {short(t['expected'], 80)}"
                  + (f" / 실패 기준: {short(t['fail_if'], 60)}" if t.get("fail_if") else "") for t in tests]
        lines.append("")
    if adrs:
        lines.append("## 기술 결정 (ADR)")
        lines += [f"- {a['id']} {a['title']}: {short(a['decision'], 120)} [{a['status']}]" for a in adrs]
        lines.append("")
    if decs:
        lines.append("## 사용자 결정")
        lines += [f"- {d['id']} {d['title']} → {d['answer']}" for d in decs]
        lines.append("")
    if asm:
        lines.append("## 묻지 않고 가정한 것")
        lines += [f"- {a['id']} {a['text']} ({a.get('reason') or ''})" for a in asm]
        lines.append("")
    if assets:
        lines.append("## 데이터 자산")
        lines += [f"- {a['id']} {a['name']} [{a['status']}] {a.get('path')}" for a in assets]
        lines.append("")
    if risks:
        lines.append("## 열린 위험")
        lines += [f"- {r['id']} [{r['severity']}] {r['text']}" for r in risks]
    text = "\n".join(lines).rstrip() + "\n"
    write_text(ctx.p.spec, text)
    return text


# ---------------- freeze gate ----------------

def freeze_check(ctx: Ctx, level: str = "core") -> dict[str, Any]:
    reqs = db.rows(ctx.conn, "SELECT * FROM requirements")
    must = [r for r in reqs if r.get("priority") == "must"]
    should = [r for r in reqs if r.get("priority") == "should"]
    tests = db.rows(ctx.conn, "SELECT requirements FROM tests")
    covered = {x for t in tests for x in json.loads(t.get("requirements") or "[]")}
    openq = db.rows(ctx.conn, "SELECT * FROM questions WHERE status IN ('open','held')")
    blockers: list[str] = []
    if not must:
        blockers.append("must 요구사항이 아직 없습니다")
    for r in must:
        if r.get("status") == "가정" and not r.get("confirmed"):
            blockers.append(f"{r['id']} must인데 근거 없는 가정 상태")
        if r.get("feasibility") == "불가":
            blockers.append(f"{r['id']} must인데 플랫폼상 불가(대안 합의 필요)")
        if r["id"] not in covered:
            blockers.append(f"{r['id']} must인데 수용 테스트가 없음")
        if json.loads(r.get("conflict") or "[]"):
            blockers.append(f"{r['id']} 발화 충돌 미해결")
    hi = [q for q in openq if q.get("impact") == "높음" and q.get("confidence") in ("확실", "가능성 높음")]
    blockers += [f"{q['id']} 영향 높음 질문이 열려 있음" for q in hi]
    from fde_mode import decisions as D
    blockers += [f"{d['id']} D1 결정 대기: {d['title']}" for d in D.blocking_open(ctx, f"{level}_freeze")]
    if level == "full":
        blockers += [f"{r['id']} should 우선순위 미확정" for r in should if r.get("status") == "가정"]
        blockers += [f"{q['id']} 영향 높음 질문 열림(전체 동결 기준)" for q in openq if q.get("impact") == "높음" and q not in hi]
    would_assume = [q["id"] for q in openq if q not in hi]
    return {"level": level, "pass": not blockers, "blockers": blockers, "must": len(must),
            "must_with_tests": sum(1 for r in must if r["id"] in covered),
            "must_with_evidence": sum(1 for r in must if json.loads(r.get("evidence") or "[]")),
            "open_high_impact": len(hi), "open_questions": len(openq),
            "would_assume_if_frozen": would_assume, "checked_at": iso()}
