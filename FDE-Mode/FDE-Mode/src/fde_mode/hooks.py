"""Hook handlers. `fde hook <event>` reads the hook JSON from stdin.

Design rules
- Silent and fast when FDE was never started in this project (no database) or
  the mode is off: print nothing, exit 0.
- Deterministic work (saving a paste, syncing outputs, guarding commands)
  happens here so it never depends on the model remembering to do it.
- Injected context is short. The full playbook lives in the fde-director skill.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from fde_mode import config, db, decisions as D, guard, transcript
from fde_mode.paths import for_project
from fde_mode.state import PHASES, PHASE_SKILL, Ctx, effective_switches, get_state, is_on, next_milestone, open_ctx, set_state
from fde_mode.util import iso, read_json, short, write_text


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _context(event: str, text: str) -> None:
    _emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def _status_lines(ctx: Ctx) -> list[str]:
    st = ctx.refresh()
    ph = st.get("phase", "P0")
    lines = [f"[FDE-Mode ON] 단계 {ph} {PHASES.get(ph, '')} · 라운드 R{int(st.get('round') or 0):02d}"
             + (" · 리허설" if (st.get("flags") or {}).get("rehearsal") else "")]
    ms = next_milestone(ctx.cfg)
    if ms:
        lines[0] += f" · 다음 {ms[0]} {ms[1]}분 남음"
    pend = D.pending(ctx, statuses=("new",))
    planned = db.scalar(ctx.conn, "SELECT COUNT(*) FROM dispatches WHERE status='planned'", default=0)
    issued = db.scalar(ctx.conn, "SELECT COUNT(*) FROM dispatches WHERE status='issued'", default=0)
    new_rounds = db.scalar(ctx.conn, "SELECT COUNT(*) FROM rounds WHERE status='new'", default=0)
    bits = []
    if pend:
        bits.append("물어볼 결정 " + ", ".join(f"{d['id']}({d['grade']})" for d in pend[:4]))
    if planned or new_rounds:
        bits.append(f"실행 대기 작업 있음")
    if issued:
        bits.append(f"진행 중 에이전트 {issued}")
    if bits:
        lines.append("상태: " + " · ".join(bits))
    lines.append(f"너는 FDE 디렉터다. 스킬 fde-director(+단계 스킬 {PHASE_SKILL.get(ph, 'fde-interview')})를 따른다. "
                 "직접 분석하지 말고 `fde next` 결과대로 서브에이전트를 띄운다. 사용자 결정은 AskUserQuestion으로 묻는다.")
    return lines


def on_prompt(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if not is_on(ctx):
        return
    assert ctx is not None
    prompt = data.get("prompt") or ""
    auto = ctx.switch("auto_detect_paste")
    kind, body, score, reason = transcript.classify(prompt, ctx.cfg, auto=auto)
    marker_only, kind, body, score, reason = _pending_marker(ctx, prompt, kind, body, score, reason, data.get("session_id"))
    lines = _status_lines(ctx)
    try:  # conversation view: what was saved on the dashboard since the last prompt
        from fde_mode import convo
        saved = convo.take_web_saved(ctx)
        if saved:
            lines.insert(1, saved + " — `fde next`가 새 라운드를 처리한다(메모는 인물 발화가 아니다).")
    except Exception:  # noqa: BLE001 — the view must never change the prompt hook
        pass
    if kind != "none" and body.strip():
        summary = transcript.ingest(ctx, body, kind=kind, source=f"hook:{reason}")
        _PASTE.update({"kind": kind, "round": summary.get("round"), "count": summary.get("count", 0)})
        if summary.get("round"):
            label = {"transcript": "대화 원문", "brief": "문제 설명(브리프)", "note": "메모"}[kind]
            lines.insert(1, f"{label}을 {summary['round']}로 저장했다(발화 {summary['count']}개 {summary.get('speakers', {})}, "
                            f"판별 {reason}). 이 메시지를 직접 분석하지 말고 지금 `fde next`를 실행해 나온 작업을 띄워라.")
            if score < 1.0:
                lines.insert(2, "자동 판별이었다. 대화가 아니었다면 사용자에게 한 줄로 확인하고 `fde undo-paste " + summary["round"] + "`.")
            for w in summary.get("warnings") or []:
                lines.append(f"붙여넣기 경고: {w}")
        else:
            lines.insert(1, "붙여넣은 내용에서 새 발화를 찾지 못했다(이전 붙여넣기와 전부 겹침). 사용자에게 한 줄로 알린다.")
    elif marker_only:
        label = {"transcript": "대화", "brief": "문제 설명(브리프)", "note": "메모"}[marker_only]
        lines.insert(1, f"{label} 표지만 받았다(내용 없음). 사용자에게 한 줄로 알린다: \"표지를 받았습니다. 다음 메시지로 "
                        f"붙여 넣으면 {label}로 저장됩니다(10분 안).\" 이 메시지는 분석하지 않는다.")
    elif transcript.missed_paste(prompt):  # never a silent loss: the first brief must not vanish
        lines.insert(1, "이 붙여넣기는 저장하지 않았다(대화·문제 설명·메모 표지를 찾지 못했거나 내용이 비었다). 인물 대화·문제 "
                        "설명·메모였다면 사용자에게 한 줄로 알린다: \"저장 못 함 — 첫 줄에 >>(대화)·>>brief(문제 설명)·>>메모를 "
                        "직접 치고 다시 붙여 넣어 주세요.\"")
    _context("UserPromptSubmit", "\n".join(lines))


PENDING_MINUTES = 10  # a marker sent on its own waits this long for the paste that follows it


def _pending_marker(ctx: Ctx, prompt: str, kind: str, body: str, score: float, reason: str, session: str | None = None) -> tuple:
    """A marker line sent on its own (Enter after ">>brief") waits for the next prompt: if that one is a paste (Claude
    Code's wrapper, or two lines or more) within PENDING_MINUTES it is saved as that kind; anything else (other words,
    a command) cancels the wait. The wait belongs to the session that sent the marker: another Claude session on the
    same project neither uses nor cancels it. A paste saved this way is scored below 1.0, so the hook asks to confirm
    (undo-paste) like any guessed paste. Returns (kind of a marker that came alone or "", kind, body, score, reason)."""
    f = ctx.p.run_dir / "pending-marker.json"
    try:
        if kind != "none" and not body.strip():  # the marker alone: wait for the paste
            f.write_text(json.dumps({"kind": kind, "at": iso(), "reason": reason, "session": session}), encoding="utf-8")
            return kind, kind, body, score, reason
        if not f.exists():
            return "", kind, body, score, reason
        try:  # another session's prompt: leave that session's wait alone (a broken file falls through and is removed)
            other = json.loads(f.read_text(encoding="utf-8") or "{}").get("session")
            if other and session and other != session:
                return "", kind, body, score, reason
        except Exception:  # noqa: BLE001
            pass
        try:  # one prompt only: used or cancelled now — even an unreadable or broken file is gone after this
            raw = f.read_text(encoding="utf-8")
        finally:
            f.unlink(missing_ok=True)
        wait = json.loads(raw or "{}")
        from datetime import datetime
        age = (datetime.fromisoformat(iso()) - datetime.fromisoformat(wait["at"])).total_seconds()
        fresh = 0 <= age <= PENDING_MINUTES * 60  # a time in the future (clock or file) cancels
        text = transcript.unwrap(prompt).strip()
        pasted = bool(transcript.PASTE_WRAPPER.search(prompt)) or len([ln for ln in text.splitlines() if ln.strip()]) >= 2
        if kind == "none" and fresh and pasted and not text.startswith("/") and wait.get("kind") in ("transcript", "brief", "note"):
            return "", wait["kind"], text, 0.9, f"pending:{wait.get('reason', '')}"  # < 1.0: the hook asks to confirm
    except Exception as e:  # noqa: BLE001 — the wait is a convenience: it never stops the prompt hook (fail open)
        try:
            ctx.event("hook.pending_error", "", {"error": repr(e)})
        except Exception:  # noqa: BLE001
            pass
    return "", kind, body, score, reason


def on_session_start(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if not is_on(ctx):
        return
    assert ctx is not None
    lines = _status_lines(ctx)
    src = data.get("source", "")
    if src == "compact":
        snap = ctx.p.run_dir / "compact-snapshot.md"
        if snap.exists():
            lines.append("압축 직전 스냅숏: " + str(snap))
    lines.append(f"상황판: {ctx.p.board} · 대시보드 상태: `fde serve --status`")
    lines.append("세션이 다시 시작됐다. fde-director 스킬을 읽고 `fde next`부터 실행해 이어간다.")
    _context("SessionStart", "\n".join(lines))


def on_pre_compact(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if not is_on(ctx):
        return
    assert ctx is not None
    runs = db.rows(ctx.conn, "SELECT id, pipeline, stage, status FROM runs WHERE status IN ('active','waiting')")
    issued = db.rows(ctx.conn, "SELECT id, agent, mode FROM dispatches WHERE status='issued'")
    pend = D.pending(ctx, statuses=("new", "asked"))
    text = [f"# 압축 직전 스냅숏 {iso()}", "", *_status_lines(ctx), "", "## 진행 중 실행"]
    text += [f"- {r['id']} {r['pipeline']} 단계 {r['stage']} [{r['status']}]" for r in runs] or ["- 없음"]
    text += ["", "## 출력을 기다리는 에이전트"] + ([f"- {d['id']} ({d['agent']} {d['mode']})" for d in issued] or ["- 없음"])
    text += ["", "## 대기 중 결정"] + ([f"- {d['id']} [{d['grade']}] {d['title']}" for d in pend] or ["- 없음"])
    write_text(ctx.p.run_dir / "compact-snapshot.md", "\n".join(text) + "\n")
    set_state(ctx, flags={"compacted_at": iso(), "compact_trigger": data.get("trigger", "")})


def on_subagent_stop(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if ctx is None:
        return
    from fde_mode.planner import Planner
    pl = Planner(ctx)
    for d in db.rows(ctx.conn, "SELECT * FROM dispatches WHERE status='issued'"):
        pl.check(d)
    ctx.event("subagent.stop", data.get("agent_type") or data.get("agent_id") or "", None, actor="hook")


def on_stop(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if not is_on(ctx) or data.get("stop_hook_active"):
        return
    assert ctx is not None
    if not ctx.switch("stop_enforce"):
        return
    flags = ctx.refresh().get("flags") or {}
    # Block at most twice per user prompt, whatever the host reports, so a turn can always end.
    pid = str(data.get("prompt_id") or data.get("session_id") or "")
    blocked = flags.get("stop_blocks") or {}
    if pid and int(blocked.get(pid, 0)) >= 2:
        return
    surfaced = set(flags.get("surfaced_decisions") or [])
    unasked = [d for d in D.pending(ctx, statuses=("new",)) if d["id"] in surfaced]
    reasons = []
    if unasked:
        reasons.append("아직 사용자에게 묻지 않은 결정이 있다: "
                       + "; ".join(f"{d['id']}[{d['grade']}] {short(d['title'], 50)}" for d in unasked[:4])
                       + ". AskUserQuestion으로 묻고 `fde decide <id> <답>`으로 기록하라. 지금 물을 수 없으면 `fde defer <id>`.")
    planned = db.scalar(ctx.conn, "SELECT COUNT(*) FROM dispatches WHERE status='planned'", default=0)
    new_rounds = db.scalar(ctx.conn, "SELECT COUNT(*) FROM rounds WHERE status='new'", default=0)
    fg_ready = 0
    for d in db.rows(ctx.conn, "SELECT output FROM dispatches WHERE status='issued' AND background=0"):
        if (ctx.p.root / d["output"]).exists():
            fg_ready += 1
    if planned or new_rounds or fg_ready:
        reasons.append("`fde next`에 실행할 작업이 남아 있다(새 라운드 또는 끝난 포그라운드 단계). 지금 실행하고 나온 작업을 띄워라.")
    if reasons:
        if pid:
            blocked = {pid: int(blocked.get(pid, 0)) + 1}
            set_state(ctx, flags={"stop_blocks": blocked})
        _emit({"decision": "block", "reason": "[FDE] " + " ".join(reasons)})


def _seat_files(ctx, agent: str) -> set:
    """Path prefixes an independent seat may always open: the inputs and output of its own issued dispatches and
    scratch files next to the output (<output stem>.*). Both absolute and project-relative forms."""
    from pathlib import Path as _P
    name = agent.split(":")[-1]
    out: set = set()

    def add(p: "_P") -> None:
        out.add(str(p))
        try:
            out.add(str(p.relative_to(ctx.p.root.resolve())))
        except ValueError:
            pass
    for d in db.rows(ctx.conn, "SELECT inputs, output FROM dispatches WHERE agent=? AND status IN ('issued','planned')",
                     (name,)):
        for v in (json.loads(d.get("inputs") or "{}") or {}).values():
            if isinstance(v, str) and v and ("/" in v or v.endswith((".json", ".md", ".jsonl"))):
                try:
                    pv = _P(v)
                    add((pv if pv.is_absolute() else ctx.p.root / pv).resolve())
                except OSError:
                    pass
        o = d.get("output") or ""
        if o:
            po = _P(o)
            po = (po if po.is_absolute() else ctx.p.root / po).resolve()
            add(po)
            add(po.with_name(po.name.removesuffix(".json") + "."))
    return out


def on_pre_tool(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if not is_on(ctx):
        return
    assert ctx is not None
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    agent = str(data.get("agent_type") or "")
    allowed = _seat_files(ctx, agent) if guard.blind_seat(agent) else set()
    unsealed = bool((ctx.state.get("flags") or {}).get("unsealed")) or agent.endswith(
        ("fde-rehearsal-grader", "fde-mock-persona"))
    if tool == "Bash":
        decision, why = guard.check_command(ti.get("command", ""), ctx.cfg)
        if decision == "allow":  # rehearsal answers are sealed from the shell too (cat/grep of the sealed folder)
            decision, why = guard.check_sealed_command(ti.get("command", ""), ctx.cfg, ctx.p.root, agent,
                                                       guard.rehearsal_sealed_roots(ctx.p.work, unsealed))
        if decision == "allow":
            decision, why = guard.check_blind("Bash", ti.get("command", ""), agent, ctx.p.work, ctx.p.root, allowed)
    else:
        path = ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or ""
        decision, why = guard.check_file(tool, path, ctx.cfg, ctx.p.root, unsealed=unsealed)
        if decision == "allow":
            decision, why = guard.check_sealed_file(tool, path, ctx.cfg, ctx.p.root, agent)
        if decision == "allow":
            decision, why = guard.check_blind(tool, path, agent, ctx.p.work, ctx.p.root, allowed)
        if decision == "allow":
            decision, why = guard.check_agent_write(agent, tool, path, ctx.p.root)
    if decision == "allow":
        return
    ctx.event(f"guard.{decision}", tool, {"why": why, "input": short(json.dumps(ti, ensure_ascii=False), 200)}, actor="hook")
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                  "permissionDecisionReason": f"[FDE 가드] {why}"}})


def on_subagent_start(data: dict) -> None:
    agent = str(data.get("agent_type") or "")
    if not guard.is_fde_agent(agent):  # other plugins' agents (e.g. the arena teams) get no FDE card
        return
    ctx = open_ctx(data.get("cwd"))
    if not is_on(ctx):
        return
    assert ctx is not None
    st = ctx.refresh()
    from fde_mode.paths import plugin_root
    refs = plugin_root() / "skills" / "fde-director" / "references"
    card = (refs / "agent-card.md").read_text(encoding="utf-8") if (refs / "agent-card.md").exists() else ""
    head = (f"[FDE] 단계 {st.get('phase')} · 라운드 R{int(st.get('round') or 0):02d} · 프로젝트 {ctx.p.root}\n"
            f"계약 전문: {refs / 'contract.md'} · 판정 규칙: {refs / 'rubric.md'}")
    _context("SubagentStart", head + "\n" + card)


def on_session_end(data: dict) -> None:
    ctx = open_ctx(data.get("cwd"))
    if ctx is None:
        return
    ctx.event("session.end", data.get("reason", ""), None, actor="hook")


HANDLERS = {
    "prompt": on_prompt,
    "user-prompt-submit": on_prompt,
    "session-start": on_session_start,
    "pre-compact": on_pre_compact,
    "subagent-stop": on_subagent_stop,
    "subagent-start": on_subagent_start,
    "stop": on_stop,
    "pre-tool": on_pre_tool,
    "session-end": on_session_end,
}


_PASTE: dict[str, Any] = {}  # set by on_prompt when the prompt was a paste (the capture stores a chip, not the text)


def _capture(event: str, data: dict) -> None:
    """Conversation view: store the prompt / Claude's last reply. Runs after the handler has already written its
    output, prints nothing, and waits at most convo.CAPTURE_WAIT for the database; any failure is swallowed."""
    if event not in ("prompt", "user-prompt-submit", "stop"):
        return
    p = for_project(data.get("cwd"))
    if not p.db.exists():
        return
    from fde_mode import convo
    conn = convo.quick_conn(p.db)
    try:
        st = get_state(conn)
        if st.get("mode") != "on" or not effective_switches(config.load(p), st).get("capture_claude_turns", True):
            return
        if event == "stop":
            convo.capture_reply(conn, data)
        else:
            convo.capture_prompt(conn, data, dict(_PASTE) or None)
    except Exception as e:  # noqa: BLE001
        if "locked" in str(e):
            return  # waiting again to log it would double the delay; a busy database is expected now and then
        try:
            conn.execute("INSERT INTO events(ts, kind, actor, ref, payload) VALUES(?,?,?,?,?)",
                         (iso(), "convo.capture_error", "hook", event, json.dumps({"error": repr(e)[:300]})))
        except Exception:  # noqa: BLE001 — locked or broken database: drop silently
            pass
    finally:
        conn.close()


def main(event: str) -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    fn = HANDLERS.get(event)
    if fn is None:
        return 0
    try:
        fn(data)
    except Exception as e:  # a hook must never break the user's session
        try:
            ctx = open_ctx(data.get("cwd"))
            if ctx:
                ctx.event("hook.error", event, {"error": repr(e)}, actor="hook")
        except Exception:
            pass
    try:
        _capture(event, data)
    except Exception:  # noqa: BLE001 — capture is best effort; the handler's output and decision already stand
        pass
    return 0
