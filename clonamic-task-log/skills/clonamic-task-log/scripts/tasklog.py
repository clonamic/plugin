#!/usr/bin/env python3
"""clonamic-task-log CLI. Standard library only, Python >= 3.12. Every command prints one JSON object.

  preflight        prerequisites (+ first-run defaults)          exit 0 ok, 1 a check failed
  profile          parse and validate profile.md
  prepare          collect -> score -> progress -> redact; prints the abstracted run, saves .run.json
  gate             check an entry file (leaks, contract, labels)   exit 2 blocked
  write            gate, then merge the entry into <date>.md, update state.json and index.md
  notion-set       record a Notion page id/url in state.json
  status           stored cursors, days, Notion ids (no commit data)
  portfolio        roll-up data for the portfolio summary
  write-portfolio  gate (portfolio kind), then write portfolio.md
  rebind           accept that this same project (same remote) moved to a new root path

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
import preflight  # noqa: E402
import progress  # noqa: E402
import redact  # noqa: E402
import score  # noqa: E402
import write  # noqa: E402
from common import (RUN_FILE, SENSITIVE_PATHSPEC, TaskLogError, git, git_ok, load_profile, open_project,  # noqa: E402
                    project_identity, read_json, repo_name, today_in, write_json, write_text_atomic, zone)


def emit(obj: dict, code: int = 0) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return code


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
    run_date = args.date or today.isoformat()
    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None
    key = "daily" if not (since or until) else f"range:{since or ''}..{until or ''}"
    shas, heads = collect.revs_for_run(repo, profile, state, since, until, today)
    previous = state["days"].get(run_date, {}).get("blocks", {}).get(key, {})
    shas += [s for s in previous.get("considered", []) if s not in shas]  # same-day rerun merges
    found = collect.details(repo, shas, profile)
    collect.attach_patch_ids(repo, found)
    pids = [c.get("patch_id") for c in found]
    on_head = {c["sha"] for c in found if c.get("patch_id") and pids.count(c["patch_id"]) > 1
               and git_ok(repo, "merge-base", "--is-ancestor", c["sha"], "HEAD")}
    seen_patches = set(state.get("processed_patches", [])) - set(previous.get("patches", []))
    duplicates = score.duplicate_shas(found, seen_patches, on_head)
    primary, status = collect.limit([c for c in found if c["sha"] not in duplicates], profile)
    commits = sorted(primary + [c for c in found if c["sha"] in duplicates], key=lambda c: c["date"])
    scored = score.run(commits, profile, repo, duplicates)
    with_repo_terms(repo, profile, [f["path"] for c in commits for f in c["files"]])
    prog = progress.run(repo, profile, scored["included"], state, today)
    dates = sorted(c["date"][:10] for c in commits)
    period = {"from": str(since or (dates[0] if dates else run_date)), "to": str(until or (dates[-1] if dates else run_date))}
    project = repo_name(repo)
    meta = {"date": run_date, "key": key, "period": period, "project": project}
    abstract = redact.abstract_run(scored, prog, profile, meta)
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
    abstract["notion_title"] = run_date if key == "daily" else f"{period['from']}~{period['to']}"
    abstract["empty"] = not scored["included"]
    abstract["previous_block"] = bool(previous)
    run = {
        "date": run_date, "key": key, "period": period, "project": project, "fingerprint": fingerprint,
        "generated_at": collected_at, "considered": [c["sha"] for c in commits], "heads": heads,
        "patches": sorted({c["patch_id"] for c in commits if c.get("patch_id")}),
        "types": abstract["counts"]["by_type"],
        "progress": [{"feature": p["feature"], "pct": p["pct"], "basis": p["basis"]} for p in prog["features"]],
        "work_unit": prog["work_unit"], "metrics": abstract["metrics"], "repo_terms": profile.repo_terms,
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
    text = Path(args.entry).read_text(encoding="utf-8")
    if args.kind == "entry":
        run = load_run(repo, logs)
        profile.repo_terms = run["repo_terms"]
        result = gate.check(text, profile, run["fingerprint"], "entry")
    else:
        with_repo_terms(repo, profile, [])
        result = gate.check(text, profile, "", args.kind)
    return emit(result, 0 if result["ok"] else 2)


def cmd_write(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    profile = load_profile(logs)
    run = load_run(repo, logs)
    profile.repo_terms = run["repo_terms"]
    text = Path(args.entry).read_text(encoding="utf-8")
    result = gate.check(text, profile, run["fingerprint"], "entry")
    if not result["ok"]:
        return emit({"ok": False, "status": "blocked"} | result, 2)
    done = write.write_entry(repo, logs, state, run, text, today_in(profile.timezone), args.replace_past)
    return emit({"ok": True} | done)


def cmd_notion_set(args) -> int:
    repo, logs, state = open_project(Path(args.repo), args.agent_dir)
    return emit({"ok": True} | write.set_notion(repo, logs, state, args.kind, args.id, args.url, args.date, args.title))


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
    text = Path(args.entry).read_text(encoding="utf-8")
    result = gate.check(text, profile, "", "portfolio")
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
    p.add_argument("--date", help="entry date (default: today in the profile time zone)")
    p.set_defaults(func=cmd_prepare)
    p = sub.add_parser("gate")
    p.add_argument("--entry", required=True)
    p.add_argument("--kind", choices=["entry", "portfolio"], default="entry")
    p.set_defaults(func=cmd_gate)
    p = sub.add_parser("write")
    p.add_argument("--entry", required=True)
    p.add_argument("--replace-past", action="store_true")
    p.set_defaults(func=cmd_write)
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
    p.add_argument("--entry", required=True)
    p.set_defaults(func=cmd_write_portfolio)
    sub.add_parser("rebind").set_defaults(func=cmd_rebind)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TaskLogError as exc:
        return emit({"ok": False, "error": str(exc), "fix": exc.fix}, 3)


if __name__ == "__main__":
    raise SystemExit(main())
