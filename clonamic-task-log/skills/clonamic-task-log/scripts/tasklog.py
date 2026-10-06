#!/usr/bin/env python3
"""clonamic-task-log CLI. Standard library only, Python >= 3.12. Every command prints one JSON object.

  preflight        prerequisites (+ first-run defaults)          exit 0 ok, 1 a check failed
  profile          parse and validate profile.md
  prepare --on D   collect the commits AUTHORED on date/range D (default today) -> score -> progress -> redact;
                   D = YYYY-MM-DD | MM-DD | 오늘 | 어제 | 그제 | A~B. Prints the abstracted run, saves .run.json
  gate             check an entry file (--entry FILE or - for stdin) (leaks, entry contract, banned wording, numbers)   exit 2 blocked
  write            gate, then write <date>.md (replaces the same date), update state.json and index.md
  korean           run clonamic-korean's check_revision.py (draft mode) on an entry   exit 0/1/2, 4 not installed
  forget --date D  delete one day's entry, state and index line; prints the Notion page to trash by hand
  notion-set       record a Notion page id/url in state.json and refresh the table in notion.md
  status           stored cursors, days, Notion ids (no commit data)
  portfolio        roll-up data for the portfolio summary
  write-portfolio  gate (portfolio kind), then write portfolio.md
  rebind           accept that this same project (same remote) moved to a new root path
  save             write profile.md / notion.md / notion-template.md from stdin into log-part

Every command resolves the project from --repo (default: the working directory) and touches
only <project>/<agent-dir>/log-part. Exit 3 = usage or environment error.
"""

import sys

if sys.version_info < (3, 12):
    sys.stdout.write('{"ok": false, "error": "Python 3.12+ required", "fix": "uv python install 3.12"}\n')
    raise SystemExit(3)
sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
from datetime import date, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect  # noqa: E402
import gate  # noqa: E402
import korean  # noqa: E402
import preflight  # noqa: E402
import progress  # noqa: E402
import redact  # noqa: E402
import score  # noqa: E402
import write  # noqa: E402
from common import (RUN_FILE, SENSITIVE_PATHSPEC, TaskLogError, git, git_ok, load_profile, open_project,  # noqa: E402
                    parse_when, project_identity, read_json, repo_name, today_in, write_json, write_text_atomic, zone)


def emit(obj: dict, code: int = 0) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return code


def read_entry(arg: str) -> str:
    """`-` reads the draft from stdin (no temp file needed); anything else is a file path."""
    if arg == "-":
        text = sys.stdin.buffer.read().decode("utf-8")
        if not text.strip():
            raise TaskLogError("empty input", "초안을 표준 입력으로 넘기세요(heredoc).")
        return text
    return Path(arg).read_text(encoding="utf-8")


def with_repo_terms(repo: Path, profile, extra_paths: list[str]):
    listed = git(repo, "ls-files", "--", ".", *SENSITIVE_PATHSPEC).splitlines()
    profile.repo_terms = redact.repo_terms(listed + extra_paths, repo_name(repo))
    return profile


def cmd_preflight(args) -> int:
    result = preflight.run(Path(args.repo), args.agent_dir)
    return emit(result, 0 if result["ok"] else 1)


def cmd_profile(args) -> int:
    _, logs, _ = open_project(Path(args.repo), args.agent_dir)
    profile = load_profile(logs)
    problems = []
    texts = [profile.part] + [f.label for f in profile.features] + [t for f in profile.features for t, _ in f.milestones]
    for text in texts:
        for hit in redact.findings(text, None):
            problems.append({"text": text, "kind": hit["kind"]})
    return emit({"ok": True, "profile": {
        "part": profile.part, "identities": len(profile.identities), "timezone": profile.timezone,
        "scopes": profile.scopes, "exclude_paths": profile.exclude_paths,
        "work_unit": profile.work_unit.__dict__ if profile.work_unit else None,
        "features": [{"label": f.label, "paths": len(f.paths), "milestones": len(f.milestones)} for f in profile.features],
        "max_commits": profile.max_commits, "max_files": profile.max_files,
    }, "label_warnings": problems})


def cmd_prepare(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    profile = load_profile(logs)
    today = today_in(profile.timezone)
    if args.since or args.until:
        since = date.fromisoformat(args.since or args.until)
        start, end = since, date.fromisoformat(args.until) if args.until else today
    else:
        start, end = parse_when(args.on, today)
    run_date = start.isoformat() if start == end else f"{start}~{end}"
    key = "daily" if start == end else "range"
    previous = state["days"].get(run_date, {}).get("blocks", {}).get(key, {})
    shas = collect.revs_for_window(repo, profile, start)
    shas += [s for s in previous.get("considered", []) if s not in shas]  # rerun of the same date merges
    found = [c for c in collect.details(repo, shas, profile)
             if c["sha"] in previous.get("considered", []) or collect.in_window(c, start, end)]
    collect.attach_patch_ids(repo, found)
    pids = [c.get("patch_id") for c in found]
    on_head = {c["sha"] for c in found if c.get("patch_id") and pids.count(c["patch_id"]) > 1
               and git_ok(repo, "merge-base", "--is-ancestor", c["sha"], "HEAD")}
    duplicates = score.duplicate_shas(found, set(), on_head)
    primary, status = collect.limit([c for c in found if c["sha"] not in duplicates], profile)
    commits = sorted(primary + [c for c in found if c["sha"] in duplicates], key=lambda c: c["date"])
    scored = score.run(commits, profile, repo, duplicates)
    with_repo_terms(repo, profile, [f["path"] for c in commits for f in c["files"]])
    prog = progress.run(repo, profile, scored["included"], state, end)
    period = {"from": start.isoformat(), "to": end.isoformat()}
    project = repo_name(repo)
    meta = {"date": run_date, "key": key, "period": period, "project": project}
    abstract = redact.abstract_run(scored, prog, profile, meta, repo)
    fingerprint = write.evidence_fingerprint(run_date, key, commits, scored["excluded"])
    collected_at = datetime.now(zone(profile.timezone)).isoformat(timespec="seconds")
    abstract["evidence"] = {
        "level": "A" if commits else "",
        "level_note": "A = git 저자 일치 커밋",
        "collected_at": collected_at,
        "fingerprint": fingerprint,
        "complete": status["complete"],
        "found": status["found"],
        "kept": status["kept"],
        "file_changes": sum(c["file_count"] for c in commits),
        "file_entries": sum(len(c["files"]) for c in commits),
        "contract": gate.CONTRACT,
    }
    touched = [p["feature"] for p in prog["features"] if p["touched_now"]]
    abstract["touched_features"] = touched
    abstract["entry_file"] = f"{run_date}.md"
    abstract["notion_title"] = run_date if start == end else f"{start:%m%d}~{end:%m%d}"
    abstract["empty"] = not scored["included"]
    abstract["previous_block"] = bool(previous)
    run = {
        "date": run_date, "key": key, "period": period, "project": project, "fingerprint": fingerprint,
        "generated_at": collected_at, "considered": [c["sha"] for c in commits],
        "patches": sorted({c["patch_id"] for c in commits if c.get("patch_id")}),
        "types": abstract["counts"]["by_type"],
        "progress": [{"feature": p["feature"], "pct": p["pct"], "basis": p["basis"],
                      "prev": p["pct"] - p["delta"] if p["delta"] is not None else None} for p in prog["features"]],
        "touched_features": touched, "work_unit": prog["work_unit"], "metrics": abstract["metrics"], "repo_terms": profile.repo_terms,
        "notion_title": abstract["notion_title"], "identity": project_identity(repo),
    }
    write_json(logs / RUN_FILE, run)
    return emit({"ok": True} | abstract)


def load_run(repo: Path, logs: Path) -> dict:
    run = read_json(logs / RUN_FILE, None)
    if run is None:
        raise TaskLogError("no prepared run", "먼저 prepare 를 실행하세요.")
    if run.get("identity", {}).get("remote_hash") != project_identity(repo)["remote_hash"]:
        raise TaskLogError("prepared run belongs to another project", "이 프로젝트에서 prepare 를 다시 실행하세요.")
    return run


def cmd_gate(args) -> int:
    repo, logs, _ = open_project(Path(args.repo), args.agent_dir)
    profile = load_profile(logs)
    text = read_entry(args.entry)
    if args.kind == "entry":
        run = load_run(repo, logs)
        profile.repo_terms = run["repo_terms"]
        result = gate.check(text, profile, run, "entry")
    else:
        with_repo_terms(repo, profile, [])
        result = gate.check(text, profile, None, args.kind)
    return emit(result, 0 if result["ok"] else 2)


def cmd_write(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    profile = load_profile(logs)
    run = load_run(repo, logs)
    profile.repo_terms = run["repo_terms"]
    text = read_entry(args.entry)
    result = gate.check(text, profile, run, "entry")
    if not result["ok"]:
        return emit({"ok": False, "status": "blocked"} | result, 2)
    done = write.write_entry(repo, logs, state, run, text)
    return emit({"ok": True} | done)


def cmd_forget(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    return emit({"ok": True} | write.forget_day(logs, state, args.date, repo_name(repo)))


def cmd_korean(args) -> int:
    if args.entry == "-":
        result, code = korean.check(None, text=read_entry("-"))
    else:
        result, code = korean.check(Path(args.entry) if args.entry else None)
    return emit(result, code)


def cmd_notion_set(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    return emit({"ok": True} | write.set_notion(repo, logs, state, args.kind, args.id, args.url, args.date, args.title, repo_name(repo)))


def cmd_status(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    return emit({
        "ok": True,
        "project": repo_name(repo),
        "log_dir": str(logs),
        "first_run": not (logs / "profile.md").is_file(),
        "last_run": state.get("last_run"),
        "days": {d: sorted(v["blocks"]) for d, v in sorted(state["days"].items())},
        "notion": state["notion"],
        "features": state["features"],
    })


def cmd_portfolio(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    profile = load_profile(logs)
    return emit({"ok": True} | write.portfolio_rollup(state, repo_name(repo), profile.part))


def cmd_write_portfolio(args) -> int:
    repo, logs, _ = open_project(Path(args.repo), args.agent_dir)
    profile = with_repo_terms(repo, load_profile(logs), [])
    text = read_entry(args.entry)
    result = gate.check(text, profile, None, "portfolio")
    if not result["ok"]:
        return emit({"ok": False, "status": "blocked"} | result, 2)
    write_text_atomic(logs / "portfolio.md", text.strip() + "\n")
    return emit({"ok": True, "status": "written", "file": str(logs / "portfolio.md")})


def cmd_rebind(args) -> int:
    from common import git_ok, load_state, log_dir, repo_root

    start = Path(args.repo)
    if not git_ok(start, "rev-parse", "--show-toplevel"):
        raise TaskLogError("not inside a git repository", "기록할 프로젝트 폴더 안에서 실행하세요.")
    repo = repo_root(start)
    logs = log_dir(repo, args.agent_dir)
    state = load_state(logs)
    current = project_identity(repo)
    recorded = state.get("project")
    if recorded and recorded.get("remote_hash") != current["remote_hash"]:
        raise TaskLogError("remote differs; this log-part belongs to another project", "다른 프로젝트의 기록은 다시 묶을 수 없습니다.")
    state["project"] = current
    write_json(logs / "state.json", state)
    return emit({"ok": True, "status": "rebound", "root": current["root"]})


SAVE_NAMES = ("profile.md", "notion.md", "notion-template.md")


def cmd_save(args) -> int:
    """Write a setup file from stdin into log-part, so hosts that guard their agent folder need only this command."""
    from common import log_dir, repo_root

    start = Path(args.repo)
    if not git_ok(start, "rev-parse", "--show-toplevel"):
        raise TaskLogError("not inside a git repository", "기록할 프로젝트 폴더 안에서 실행하세요.")
    if args.name not in SAVE_NAMES:
        raise TaskLogError(f"save accepts only {', '.join(SAVE_NAMES)}", "기록 본문은 write로 저장하세요.")
    text = sys.stdin.read()
    if not text.strip():
        raise TaskLogError("empty input", "저장할 내용을 표준 입력으로 넘기세요.")
    logs = log_dir(repo_root(start), args.agent_dir)
    logs.mkdir(parents=True, exist_ok=True)
    write_text_atomic(logs / args.name, text.rstrip() + "\n")
    return emit({"ok": True, "status": "saved", "file": str(logs / args.name)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tasklog.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="any path inside the project (default: working directory)")
    parser.add_argument("--agent-dir", default=".claude",
                        help="host folder inside the project: .claude, .codex, .cursor, .grok (absolute = dry runs only)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight").set_defaults(func=cmd_preflight)
    sub.add_parser("profile").set_defaults(func=cmd_profile)
    p = sub.add_parser("prepare")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--on", default="", help="work date: YYYY-MM-DD, MM-DD, 오늘/어제/그제, or a range A~B (default: today)")
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("gate")
    p.add_argument("--entry", required=True, help="draft file, or - to read it from stdin")
    p.add_argument("--kind", choices=["entry", "portfolio"], default="entry")
    p.set_defaults(func=cmd_gate)
    p = sub.add_parser("write")
    p.add_argument("--entry", required=True, help="draft file, or - to read it from stdin")
    p.add_argument("--replace-past", action="store_true", help="ignored; kept so older commands still run")
    p.set_defaults(func=cmd_write)
    p = sub.add_parser("forget")
    p.add_argument("--date", required=True, help="entry key: YYYY-MM-DD, or the range key YYYY-MM-DD~YYYY-MM-DD")
    p.set_defaults(func=cmd_forget)
    p = sub.add_parser("korean")
    p.add_argument("--entry", help="draft file or - (stdin) to check; without it, only locate clonamic-korean")
    p.set_defaults(func=cmd_korean)
    p = sub.add_parser("notion-set")
    p.add_argument("--kind", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--url", default="")
    p.add_argument("--date", default="")
    p.add_argument("--title", default="")
    p.set_defaults(func=cmd_notion_set)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("portfolio").set_defaults(func=cmd_portfolio)
    p = sub.add_parser("write-portfolio")
    p.add_argument("--entry", required=True, help="draft file, or - to read it from stdin")
    p.set_defaults(func=cmd_write_portfolio)
    sub.add_parser("rebind").set_defaults(func=cmd_rebind)
    p = sub.add_parser("save")
    p.add_argument("--name", required=True, choices=SAVE_NAMES)
    p.set_defaults(func=cmd_save)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TaskLogError as exc:
        return emit({"ok": False, "error": str(exc), "fix": exc.fix}, 3)


if __name__ == "__main__":
    raise SystemExit(main())
