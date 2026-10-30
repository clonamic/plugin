"""`fde` command line. Every command prints JSON (machine) or short Korean text
(human, with --text). The director and the hooks only ever talk to the
organisation through these commands."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from fde_mode import (__version__, asked, boot, config, db, decisions as D, envtool, guard, hooks, metrics,
                      planner, registry, report, roster, transcript)
from fde_mode.paths import for_project, plugin_root
from fde_mode.state import PHASES, Ctx, effective_switches, open_ctx, open_project, set_state, timeline
from fde_mode.util import iso, now, read_json, write_text


def _print(obj) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _need(args) -> Ctx:
    ctx = open_ctx(args.project)
    if ctx is None:
        sys.stderr.write("FDE가 이 프로젝트에서 시작된 적이 없습니다. /fde-mode 로 켜세요.\n")
        sys.exit(2)
    return ctx


# ------------------------------------------------------------------ commands

def cmd_on(args) -> int:
    ctx = open_project(args.project)
    if not ctx.p.binding.exists():
        write_text(ctx.p.binding, config.template_binding(ctx.p.root.name, args.profile or "generic"))
        ctx.cfg = config.load(ctx.p)
    st = ctx.refresh()
    flags = {}
    if args.rehearsal:
        flags["rehearsal"] = True
    if args.autopilot:
        flags["autopilot"] = True
    first = st.get("mode") != "on" and int(st.get("round") or 0) == 0 and st.get("phase") == "P0"
    set_state(ctx, mode="on", phase=st.get("phase") if st.get("phase") not in (None, "", "P0") else "P0", flags=flags)
    registry.touch(ctx.p.root, ctx.cfg.get("project", {}).get("name") or ctx.p.root.name)
    ctx.event("mode.on", "", {"first": first, "rehearsal": bool(args.rehearsal), "autopilot": bool(args.autopilot)}, actor="user")
    report.board(ctx)
    _print({"mode": "on", "project": str(ctx.p.root), "work": str(ctx.p.work), "binding": str(ctx.p.binding),
            "binding_found": ctx.cfg.get("_binding_found"), "phase": ctx.state.get("phase"),
            "first_time": first, "plugin": str(plugin_root()), "version": __version__})
    return 0


def cmd_off(args) -> int:
    ctx = _need(args)
    set_state(ctx, mode="off")
    ctx.event("mode.off", "", None, actor="user")
    _print({"mode": "off", "kept": str(ctx.p.work)})
    return 0


def cmd_status(args) -> int:
    ctx = _need(args)
    st = ctx.refresh()
    c = lambda sql: db.scalar(ctx.conn, sql, default=0)  # noqa: E731
    data = {
        "mode": st.get("mode"), "phase": st.get("phase"), "phase_ko": PHASES.get(st.get("phase"), ""),
        "round": st.get("round"), "flags": st.get("flags"), "switches": effective_switches(ctx.cfg, st),
        "timeline": timeline(ctx.cfg),
        "counts": {"utterances": c("SELECT COUNT(*) FROM utterances"),
                   "requirements": c("SELECT COUNT(*) FROM requirements"),
                   "open_questions": c("SELECT COUNT(*) FROM questions WHERE status='open'"),
                   "pending_decisions": c("SELECT COUNT(*) FROM decisions WHERE status IN ('new','asked') AND grade IN ('D1','D2')"),
                   "active_runs": c("SELECT COUNT(*) FROM runs WHERE status IN ('active','waiting')"),
                   "agents_running": c("SELECT COUNT(*) FROM dispatches WHERE status='issued'")},
        "runs": db.rows(ctx.conn, "SELECT id, pipeline, stage, status FROM runs WHERE status IN ('active','waiting') ORDER BY created_at"),
        "dashboard": read_json(ctx.p.run_dir / "server.json") or read_json(_server_file()),
    }
    _print(data)
    return 0


def cmd_next(args) -> int:
    ctx = _need(args)
    st = ctx.refresh()
    if st.get("mode") != "on":
        _print({"idle": True, "note": "FDE 모드가 꺼져 있습니다"})
        return 0
    if st.get("phase") == "P0":
        set_state(ctx, phase="P1")
    out = planner.next_actions(ctx)
    _print(out)
    return 0


def cmd_sync(args) -> int:
    ctx = _need(args)
    pl = planner.Planner(ctx)
    n = 0
    for d in db.rows(ctx.conn, "SELECT * FROM dispatches WHERE status='issued'"):
        pl.check(d)
        n += 1
    _print({"checked": n})
    return 0


def cmd_wait(args) -> int:
    """Block until the issued dispatches this turn must wait for have written their output files.

    The Agent tool can hand back "Async agent launched" even for run_in_background=false (seen in a real
    round on 2026-10-30), so the director cannot rely on the call itself to wait. `fde wait` waits on the
    files instead; `fde next` then ingests them. Exit 0 when nothing is pending, 3 on timeout."""
    import time as _time
    ctx = _need(args)
    autopilot = bool((ctx.refresh().get("flags") or {}).get("autopilot"))
    t0 = _time.monotonic()
    pending: list[dict] = []
    while True:
        rows = db.rows(ctx.conn, "SELECT id, run, agent, output, background, issued_at FROM dispatches WHERE status='issued'"
                       + (" AND run=?" if args.run else ""), (args.run,) if args.run else ())
        pending = [d for d in rows if (args.all or autopilot or not d["background"])
                   and not (ctx.p.root / d["output"]).exists()]
        if not pending or _time.monotonic() - t0 >= args.timeout:
            break
        _time.sleep(max(1.0, args.interval))
    _print({"pending": [{"id": d["id"], "agent": d["agent"], "issued_at": d["issued_at"]} for d in pending],
            "waited_s": round(_time.monotonic() - t0), "next": "fde next"})
    return 0 if not pending else 3


def cmd_ingest(args) -> int:
    ctx = _need(args)
    body = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    _print(transcript.ingest(ctx, body, kind=args.kind, source="cli"))
    return 0


def cmd_undo_paste(args) -> int:
    ctx = _need(args)
    r = db.one(ctx.conn, "SELECT * FROM rounds WHERE id=?", (args.round,))
    if not r:
        _print({"ok": False, "error": "없는 라운드"})
        return 1
    started = db.scalar(ctx.conn, "SELECT COUNT(*) FROM runs WHERE round=? AND stage>0", (args.round,), 0)
    ctx.conn.execute("DELETE FROM utterances WHERE round=?", (args.round,))
    ctx.conn.execute("UPDATE rounds SET status='undone' WHERE id=?", (args.round,))
    ctx.conn.execute("UPDATE runs SET status='cancelled' WHERE round=? AND status IN ('active','waiting')", (args.round,))
    ctx.conn.execute("UPDATE dispatches SET status='skipped' WHERE run IN (SELECT id FROM runs WHERE round=?) AND status IN ('planned','issued')", (args.round,))
    transcript.export(ctx)
    ctx.event("paste.undone", args.round, None, actor="user")
    _print({"ok": True, "round": args.round, "analysis_already_started": bool(started),
            "note": "원문 파일(inbox)은 기록으로 남겨 둡니다"})
    return 0


def cmd_decide(args) -> int:
    ctx = _need(args)
    ok = D.answer(ctx, args.id, " ".join(args.choice))
    _print({"ok": ok, "id": args.id})
    return 0 if ok else 1


def cmd_defer(args) -> int:
    ctx = _need(args)
    ok = bool(ctx.conn.execute("UPDATE decisions SET status='asked' WHERE id=? AND status='new'", (args.id,)).rowcount)
    flags = ctx.refresh().get("flags") or {}
    surfaced = [x for x in (flags.get("surfaced_decisions") or []) if x != args.id]
    set_state(ctx, flags={"surfaced_decisions": surfaced})
    ctx.event("decision.deferred", args.id, None, actor="director")
    _print({"ok": ok, "id": args.id, "note": "다음 라운드 보고 때 다시 묻습니다"})
    return 0


def cmd_reask(args) -> int:
    ctx = _need(args)
    n = ctx.conn.execute("UPDATE decisions SET status='new' WHERE status='asked'").rowcount
    _print({"reopened": n})
    return 0


def cmd_decisions(args) -> int:
    ctx = _need(args)
    q = "SELECT * FROM decisions" + (" WHERE status IN ('new','asked') AND grade IN ('D1','D2')" if args.pending else "") + " ORDER BY id"
    rows = db.rows(ctx.conn, q)
    for r in rows:
        r["options"] = json.loads(r["options"] or "[]")
    _print(rows)
    return 0


def cmd_question(args) -> int:
    ctx = _need(args)
    ok = asked.mark(ctx, args.id, args.status, " ".join(args.note or []))
    _print({"ok": ok, "id": args.id, "status": args.status})
    return 0 if ok else 1


def cmd_switch(args) -> int:
    ctx = _need(args)
    if args.name in config.SWITCHES_LOCKED:
        _print({"ok": False, "error": "독립 검증은 끌 수 없습니다"})
        return 1
    known = set((ctx.cfg.get("switches") or {}).keys())
    if args.name not in known:
        _print({"ok": False, "error": f"없는 스위치. 가능: {sorted(known)}"})
        return 1
    set_state(ctx, switches={args.name: args.value == "on"})
    ctx.event("switch", args.name, {"value": args.value}, actor="user")
    closed = D.autonomy_on(ctx) if args.name == "autonomy" and args.value == "on" else 0
    _print({"ok": True, "switches": effective_switches(ctx.cfg, ctx.refresh()), **({"d2_auto": closed} if closed else {})})
    return 0


def cmd_run(args) -> int:
    ctx = _need(args)
    params = {}
    if args.round:
        params["round"] = args.round
    if args.level:
        params["level"] = args.level
    if args.text:
        params["text"] = args.text
    if args.theme:
        params["theme"] = args.theme
    if args.pipeline == "debate" and not args.round:
        params["round"] = f"R{int(ctx.state.get('round') or 0):02d}"
    if args.pipeline == "rehearsal-grade":
        set_state(ctx, flags={"unsealed": True})
    rid = planner.start(ctx, args.pipeline, **params)
    _print({"ok": bool(rid), "run": rid, "note": None if rid else "이미 같은 실행이 있습니다"})
    return 0


def cmd_speakers(args) -> int:
    ctx = _need(args)
    if args.label and args.as_:
        set_state(ctx, speakers={args.label: args.as_})
        if args.round:
            ctx.conn.execute("UPDATE utterances SET speaker=?, parse_conf=1.0 WHERE round=? AND speaker_label=?",
                             (args.as_, args.round, args.label))
            transcript.export(ctx)
    _print({"speakers": ctx.refresh().get("speakers")})
    return 0


def cmd_show(args) -> int:
    ctx = _need(args)
    what = args.what
    if what == "report":
        r = db.one(ctx.conn, "SELECT id FROM runs WHERE pipeline IN ('quick','debate','brief') AND status='done' ORDER BY finished_at DESC LIMIT 1")
        path = ctx.p.runs / r["id"] / "report.md" if r else None
        sys.stdout.write(path.read_text(encoding="utf-8") if path and path.exists() else "아직 보고서가 없습니다\n")
    elif what == "board":
        sys.stdout.write(report.board(ctx))
    elif what == "spec":
        sys.stdout.write(report.spec(ctx))
    elif what == "cards":
        rows = db.rows(ctx.conn, "SELECT id, text, confidence, impact, bucket, status, flags FROM questions "
                                 "WHERE status IN ('open','held') ORDER BY bucket, ord")
        _print(rows)
    elif what == "paths":
        _print({"plugin": str(plugin_root()), "project": str(ctx.p.root), "work": str(ctx.p.work),
                "references": str(plugin_root() / "skills" / "fde-director" / "references"),
                "profile": str(config.profile_path(ctx.cfg)), "binding": str(ctx.p.binding)})
    else:
        _print({"error": "report | board | spec | cards | paths"})
    return 0


def cmd_freeze_check(args) -> int:
    ctx = _need(args)
    _print(report.freeze_check(ctx, args.level))
    return 0


def cmd_metrics(args) -> int:
    ctx = _need(args)
    rnd = args.round or f"R{int(ctx.state.get('round') or 0):02d}"
    _print(metrics.compute(ctx, rnd))
    return 0


def cmd_boot(args) -> int:
    ctx = _need(args)
    res = boot.run(ctx, quick=args.quick)
    _print(res)
    return 0


def cmd_env(args) -> int:
    ctx = _need(args)
    if args.action == "check":
        keys = args.keys or (ctx.cfg.get("runtime") or {}).get("required_env") or None
        _print(envtool.check(ctx.p.root, keys))
    else:
        allowed = (ctx.cfg.get("guard") or {}).get("env_editable") or []
        try:
            res = envtool.set_value(ctx.p.root, args.keys[0], args.keys[1], allowed)
            ctx.event("env.set", args.keys[0], {"result": res}, actor="director")
            _print({"ok": True, "key": args.keys[0], "result": res})
        except (PermissionError, ValueError, IndexError) as e:
            _print({"ok": False, "error": str(e)})
            return 1
    return 0


def cmd_guard_test(args) -> int:
    """Check a command (or with --file, a path) against the guard, using the project binding even when FDE is off."""
    p = for_project(args.project)
    cfg = config.load(p)
    if args.file:
        decision, why = guard.check_file(args.tool, args.file, cfg, p.root)
        if decision == "allow":
            decision, why = guard.check_sealed_file(args.tool, args.file, cfg, p.root, "")
    else:
        # argparse REMAINDER keeps the `--` of the documented form `fde guard-test -- <command>`; left in, it would sit in
        # front of the command and every rule anchored at the start (cat .env, make down …) would miss — a false allow
        words = args.command[1:] if args.command[:1] == ["--"] else args.command
        cmd = " ".join(words)
        decision, why = guard.check_command(cmd, cfg)
        if decision == "allow":
            decision, why = guard.check_sealed_command(cmd, cfg, p.root, "", guard.rehearsal_sealed_roots(p.work, False))
    _print({"decision": decision, "reason": why, "binding": str(p.binding) if cfg.get("_binding_found") else None})
    return 0


def cmd_hook(args) -> int:
    return hooks.main(args.event)


def _server_file() -> Path:
    from fde_mode.paths import global_dir
    return global_dir() / "server.json"


def cmd_serve(args) -> int:
    from fde_mode import server
    if args.stop:
        _print(server.stop())
    elif args.status:
        _print(server.status())
    elif args.detach:
        ctx = open_ctx(args.project)
        if ctx is not None and not ctx.switch("dashboard"):  # H-13: the project switched its dashboard off
            _print({"ok": True, "skipped": "dashboard 스위치가 꺼져 있어 대시보드를 띄우지 않습니다(fde switch dashboard on)"})
            return 0
        _print(server.start_detached(args.port))
    else:
        server.serve(args.port)
    return 0


def cmd_archive(args) -> int:
    ctx = _need(args)
    stamp = now().strftime("%Y%m%d-%H%M%S")
    dest = ctx.p.archive / stamp
    dest.mkdir(parents=True, exist_ok=True)
    ctx.conn.close()
    moved = []
    for item in list(ctx.p.work.iterdir()):
        if item.name in ("archive", "project.toml"):
            continue
        shutil.move(str(item), str(dest / item.name))
        moved.append(item.name)
    _print({"ok": True, "archived_to": str(dest), "moved": moved, "note": "project.toml 은 그대로 둡니다. 다시 /fde-mode 로 시작"})
    return 0


def cmd_doctor(args) -> int:
    root = plugin_root()
    agents = sorted((root / "agents").glob("*.md"))
    names = {a.stem for a in agents}
    missing = [a.name for a in roster.AGENTS if a.name not in names]
    extra = sorted(names - {a.name for a in roster.AGENTS})
    _print({"version": __version__, "python": sys.version.split()[0], "plugin": str(root),
            "agents": len(agents), "roster": len(roster.AGENTS), "missing_agent_files": missing, "unknown_agent_files": extra,
            "skills": sorted(p.name for p in (root / "skills").iterdir() if (p / "SKILL.md").exists()),
            "profiles": sorted(p.stem for p in (root / "profiles").glob("*.md"))})
    return 0 if not missing else 1


def cmd_aitell(args) -> int:
    from fde_mode import aitell
    if args.text:
        replies = list(args.text)
    else:
        src = Path(args.file).read_text(encoding="utf-8") if args.file and args.file != "-" else sys.stdin.read()
        try:
            data = json.loads(src)
        except json.JSONDecodeError:
            data = [b for b in src.split("\n\n") if b.strip()]
        if isinstance(data, dict):
            data = data.get("replies") or data.get("qa") or data.get("items") or []
        replies = data
    _print(aitell.measure(replies, allow=args.allow or []))
    return 0


def cmd_roster(args) -> int:
    if getattr(args, "md", False):
        from fde_mode.paths import plugin_root
        path = plugin_root() / "skills" / "fde-director" / "references" / "org-chart.md"
        path.write_text(roster.org_chart_md(), encoding="utf-8")
        _print({"written": str(path), "agents": len(roster.AGENTS)})
        return 0
    rows = [{"name": a.name, "ko": a.ko, "division": a.division, "team": a.team, "effort": a.effort,
             "modes": list(a.modes), "quick": a.quick, "head": a.head, "independent": a.independent} for a in roster.AGENTS]
    _print(rows)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fde", description="FDE-Mode organisation engine")
    ap.add_argument("--project", default=None, help="project root (default: CLAUDE_PROJECT_DIR or cwd)")
    ap.add_argument("--version", action="version", version=__version__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("on"); p.add_argument("--profile"); p.add_argument("--rehearsal", action="store_true")
    p.add_argument("--autopilot", action="store_true", help="unattended run: every dispatch in the foreground, decisions by the pilot's operator")
    p.set_defaults(fn=cmd_on)
    sp.add_parser("off").set_defaults(fn=cmd_off)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    sp.add_parser("next").set_defaults(fn=cmd_next)
    sp.add_parser("sync").set_defaults(fn=cmd_sync)
    p = sp.add_parser("wait", help="기다려야 할 디스패치의 출력 파일이 생길 때까지 대기(Agent 가 비동기로 바뀌었을 때)")
    p.add_argument("--run"); p.add_argument("--timeout", type=float, default=540.0)
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--all", action="store_true", help="백그라운드 디스패치까지 기다림")
    p.set_defaults(fn=cmd_wait)
    p = sp.add_parser("ingest"); p.add_argument("--kind", default="transcript", choices=["transcript", "brief", "note"])
    p.add_argument("--file"); p.set_defaults(fn=cmd_ingest)
    p = sp.add_parser("undo-paste"); p.add_argument("round"); p.set_defaults(fn=cmd_undo_paste)
    p = sp.add_parser("decide"); p.add_argument("id"); p.add_argument("choice", nargs="+"); p.set_defaults(fn=cmd_decide)
    p = sp.add_parser("defer"); p.add_argument("id"); p.set_defaults(fn=cmd_defer)
    sp.add_parser("reask").set_defaults(fn=cmd_reask)
    p = sp.add_parser("decisions"); p.add_argument("--pending", action="store_true"); p.set_defaults(fn=cmd_decisions)
    p = sp.add_parser("question"); p.add_argument("id")
    p.add_argument("status", choices=["open", "asked", "answered", "assumed", "dropped", "held"])
    p.add_argument("note", nargs="*"); p.set_defaults(fn=cmd_question)
    p = sp.add_parser("switch"); p.add_argument("name"); p.add_argument("value", choices=["on", "off"]); p.set_defaults(fn=cmd_switch)
    p = sp.add_parser("run"); p.add_argument("pipeline", choices=sorted(planner.PIPELINES))
    p.add_argument("--round"); p.add_argument("--level", choices=["core", "full"]); p.add_argument("--text"); p.add_argument("--theme")
    p.set_defaults(fn=cmd_run)
    p = sp.add_parser("speakers"); p.add_argument("label", nargs="?"); p.add_argument("as_", nargs="?", choices=["I", "P"])
    p.add_argument("--round"); p.set_defaults(fn=cmd_speakers)
    p = sp.add_parser("show"); p.add_argument("what"); p.set_defaults(fn=cmd_show)
    p = sp.add_parser("freeze-check"); p.add_argument("level", nargs="?", default="core", choices=["core", "full"]); p.set_defaults(fn=cmd_freeze_check)
    p = sp.add_parser("metrics"); p.add_argument("--round"); p.set_defaults(fn=cmd_metrics)
    p = sp.add_parser("boot"); p.add_argument("--quick", action="store_true"); p.set_defaults(fn=cmd_boot)
    p = sp.add_parser("env"); p.add_argument("action", choices=["check", "set"]); p.add_argument("keys", nargs="*"); p.set_defaults(fn=cmd_env)
    p = sp.add_parser("guard-test", help='fde guard-test -- <명령…>  |  fde guard-test --file <경로> [--tool Read|Write]')
    p.add_argument("--file"); p.add_argument("--tool", default="Write")
    p.add_argument("command", nargs=argparse.REMAINDER); p.set_defaults(fn=cmd_guard_test)
    p = sp.add_parser("hook"); p.add_argument("event"); p.set_defaults(fn=cmd_hook)
    p = sp.add_parser("serve"); p.add_argument("--port", type=int, default=0); p.add_argument("--detach", action="store_true")
    p.add_argument("--stop", action="store_true"); p.add_argument("--status", action="store_true"); p.set_defaults(fn=cmd_serve)
    sp.add_parser("archive").set_defaults(fn=cmd_archive)
    sp.add_parser("doctor").set_defaults(fn=cmd_doctor)
    p = sp.add_parser("roster"); p.add_argument("--md", action="store_true", help="regenerate references/org-chart.md")
    p.set_defaults(fn=cmd_roster)
    p = sp.add_parser("aitell", help="AI티 측정(어휘 신호): --file replies.json | --text ...")
    p.add_argument("--file"); p.add_argument("--text", nargs="*"); p.add_argument("--allow", nargs="*",
                   help="이 인물이 실제로 쓰는 표현(감점 제외)")
    p.set_defaults(fn=cmd_aitell)
    return ap


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        sys.stderr.write(f"FDE-Mode는 Python 3.12 이상이 필요합니다(현재 {sys.version.split()[0]}). "
                         "uv python install 3.12 또는 brew install python@3.12\n")
        return 3
    args = build_parser().parse_args(argv)
    if args.project:  # an explicit --project beats FDE_PROJECT / CLAUDE_PROJECT_DIR inherited from a session
        os.environ["FDE_PROJECT"] = str(Path(args.project).expanduser().resolve())
    return int(args.fn(args) or 0)
