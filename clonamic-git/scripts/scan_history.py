#!/usr/bin/env python3
"""Scan git history for AI attribution: trailers/footers in messages and AI or bot author/committer identities.

Usage:
  scan_history.py [--repo DIR] [--range "REV..REV"] [--all] [--json]
  scan_history.py [--repo DIR] --check-identity [--json]

Default range: unpushed commits, i.e. `@{upstream}..HEAD`, or `HEAD --not --remotes` when there is no upstream.
--all scans every ref plus annotated tag messages. --check-identity checks the identity the next commit would use
(`git var GIT_AUTHOR_IDENT` / `GIT_COMMITTER_IDENT`, so GIT_AUTHOR_* / GIT_COMMITTER_* overrides count).
Extra message patterns come from `git config --get-all clonamic.aiPattern` and --pattern.
Exit codes: 0 clean, 1 AI trace found (or identity missing/AI), 2 git or usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 12):
    sys.exit("scan_history.py needs Python 3.12+; install it (for example `uv python install 3.12`).")

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin folder
sys.path.insert(0, str(Path(__file__).resolve().parent))
from strip_ai_trailers import compile_patterns, is_ai_identity, strip_message  # noqa: E402

FIELD, RECORD = "\x1f", "\x1e"
IDENT_LINE = re.compile(r"^(?P<name>.*?)\s*<(?P<email>[^<>]*)>")


class GitError(RuntimeError):
    pass


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def default_range(repo: str) -> list[str]:
    try:
        git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        return ["@{upstream}..HEAD"]
    except GitError:
        return ["HEAD", "--not", "--remotes"]


def has_head(repo: str) -> bool:
    try:
        git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
        return True
    except GitError:
        return False


def identity_issues(kind: str, name: str, email: str) -> list[dict[str, str]]:
    if is_ai_identity(name, email):
        return [{"kind": kind, "reason": "ai-identity", "value": f"{name} <{email}>"}]
    return []


def message_issues(message: str, extra: list[re.Pattern[str]]) -> list[dict[str, str]]:
    _, removed = strip_message(message, extra)
    return [{"kind": "message", "reason": reason, "value": line.strip()} for reason, line in removed]


def scan_commits(repo: str, rev_args: list[str], extra: list[re.Pattern[str]]) -> tuple[int, list[dict]]:
    fmt = FIELD.join(["%H", "%an", "%ae", "%cn", "%ce", "%B"]) + RECORD
    out = git(repo, "log", "--no-color", f"--format={fmt}", *rev_args)
    findings: list[dict] = []
    count = 0
    for record in out.split(RECORD):
        record = record.lstrip("\n")
        if not record:
            continue
        sha, an, ae, cn, ce, body = record.split(FIELD, 5)
        count += 1
        issues = identity_issues("author", an, ae) + identity_issues("committer", cn, ce)
        issues += message_issues(body, extra)
        if issues:
            subject = body.splitlines()[0] if body.strip() else ""
            findings.append({"commit": sha, "subject": subject, "issues": issues})
    return count, findings


def scan_tags(repo: str, extra: list[re.Pattern[str]]) -> list[dict]:
    fmt = FIELD.join(["%(objecttype)", "%(refname:short)", "%(taggername)", "%(taggeremail)", "%(contents)"]) + RECORD
    out = git(repo, "for-each-ref", f"--format={fmt}", "refs/tags")
    findings: list[dict] = []
    for record in out.split(RECORD):
        record = record.lstrip("\n")
        if not record:
            continue
        otype, name, tname, temail, contents = record.split(FIELD, 4)
        if otype != "tag":
            continue
        issues = identity_issues("tagger", tname, temail.strip("<>")) + message_issues(contents, extra)
        if issues:
            findings.append({"tag": name, "issues": issues})
    return findings


def check_identity(repo: str) -> dict:
    result: dict = {"clean": True, "author": None, "committer": None, "issues": []}
    for kind, var in (("author", "GIT_AUTHOR_IDENT"), ("committer", "GIT_COMMITTER_IDENT")):
        try:
            line = git(repo, "var", var).strip()
        except GitError as exc:
            result["clean"] = False
            result["issues"].append({"kind": kind, "reason": "identity-missing", "value": str(exc)})
            continue
        m = IDENT_LINE.match(line)
        name, email = (m.group("name"), m.group("email")) if m else (line, "")
        result[kind] = f"{name} <{email}>"
        issues = identity_issues(kind, name, email)
        if issues:
            result["clean"] = False
            result["issues"] += issues
    return result


def print_text(report: dict) -> None:
    if "commits_scanned" in report:
        print(f"range: {report['range']}  commits: {report['commits_scanned']}")
        for item in report["findings"]:
            print(f"{item['commit'][:12]} {item['subject']}")
            for issue in item["issues"]:
                print(f"  {issue['kind']}: {issue['reason']}: {issue['value']}")
        for item in report.get("tags", []):
            print(f"tag {item['tag']}")
            for issue in item["issues"]:
                print(f"  {issue['kind']}: {issue['reason']}: {issue['value']}")
    else:
        print(f"author: {report['author']}\ncommitter: {report['committer']}")
        for issue in report["issues"]:
            print(f"  {issue['kind']}: {issue['reason']}: {issue['value']}")
    print("clean" if report["clean"] else "AI trace found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan git history for AI attribution.")
    parser.add_argument("--repo", default=".", help="repository directory (default: current)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--range", help='revision range, e.g. "origin/main..HEAD" (rev-list syntax)')
    group.add_argument("--all", action="store_true", help="scan every ref and annotated tag")
    group.add_argument("--check-identity", action="store_true", help="check the identity the next commit uses")
    parser.add_argument("--pattern", action="append", default=[], help="extra message regex (repeatable)")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    args = parser.parse_args(argv)

    try:
        git(args.repo, "rev-parse", "--git-dir")
        if args.check_identity:
            report = check_identity(args.repo)
        else:
            raw = list(args.pattern)
            try:
                raw += [p for p in git(args.repo, "config", "--get-all", "clonamic.aiPattern").splitlines() if p.strip()]
            except GitError:
                pass
            extra = compile_patterns(raw)
            rev_args = ["--all"] if args.all else (shlex.split(args.range) if args.range else default_range(args.repo))
            count, findings = scan_commits(args.repo, rev_args, extra) if (args.all or has_head(args.repo)) else (0, [])
            tags = scan_tags(args.repo, extra) if args.all else []
            report = {
                "range": " ".join(rev_args),
                "commits_scanned": count,
                "findings": findings,
                "tags": tags,
                "clean": not findings and not tags,
            }
    except (GitError, re.error) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"clonamic-git: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
