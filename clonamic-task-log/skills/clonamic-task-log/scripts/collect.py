"""Collect the user's commits since the state cursor (or in an explicit window). Skips nothing."""

from __future__ import annotations

import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath

from common import (GIT_ENV, SENSITIVE_PATHSPEC, Profile, day_start, git, git_ok, is_bench, is_code, is_doc, is_mine,
                    is_noise, is_test, under, zone)

CONVENTIONAL = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<rest>.*)$")
TYPE_ALIASES = {
    "feat": "feat", "feature": "feat", "perf": "perf", "fix": "fix", "bugfix": "fix", "hotfix": "fix",
    "refactor": "refactor", "test": "test", "tests": "test", "docs": "docs", "doc": "docs",
    "chore": "chore", "build": "chore", "ci": "chore", "deps": "chore", "release": "chore",
    "style": "style", "revert": "revert",
}
KEYWORDS = [  # first match wins, checked against the lowercased subject
    ("revert", r"^revert\b|되돌"),
    ("perf", r"\b(perf|performance|optimi[sz]e|speed ?up|faster|latency|throughput)\b|최적화|성능|속도"),
    ("fix", r"\b(fix(es|ed)?|bug|resolve[sd]?|patch|crash|broken|hotfix)\b|수정|버그|고침|오류"),
    ("feat", r"\b(add(s|ed)?|implement(s|ed)?|introduce[sd]?|create[sd]?|support(s|ed)?|new|enable[sd]?)\b|추가|구현|도입|지원"),
    ("refactor", r"\b(refactor\w*|clean ?up|restructure\w*|rename[sd]?|move[sd]?|extract\w*|simplif\w*|regroup\w*|reorgani[sz]\w*)\b|리팩터|정리|구조"),
    ("test", r"\b(tests?|coverage|spec)\b|테스트"),
    ("docs", r"\b(docs?|readme|documentation|comment)\b|문서"),
    ("style", r"\b(format\w*|lint\w*|style|whitespace|prettier|typo)\b|서식|오타"),
    ("chore", r"\b(bump|deps?|dependenc\w*|chore|ci|build|config|release|version)\b|설정|배포"),
]
LEAD_VERBS = {
    "feat": {"add", "adds", "added", "implement", "implements", "introduce", "create", "support", "enable", "build",
             "derive", "bring", "provide", "allow"},
    "fix": {"fix", "fixes", "fixed", "resolve", "repair", "correct", "restore", "prevent", "handle"},
    "perf": {"optimize", "optimise", "speed", "accelerate", "cache"},
    "refactor": {"refactor", "clean", "cleanup", "restructure", "rename", "move", "extract", "simplify", "regroup",
                 "reorganize", "reorganise", "split", "remove", "drop", "delete", "retire", "replace", "unify"},
    "test": {"test", "tests", "cover"},
    "docs": {"document", "docs", "doc", "describe", "explain"},
    "chore": {"bump", "upgrade", "update", "release", "configure"},
    "style": {"format", "lint", "reformat"},
}
UNITS = r"(?:ms|µs|us|ns|s|sec|secs|seconds?|분|초|min|h|시간|kb|mb|gb|tb|%|x|배|건|개|회|rps|qps|req/s|ops/s|fps|줄|lines|점|원|명)"
NUM = r"(\d+(?:[.,]\d+)?)"
METRIC_RE = re.compile(
    rf"{NUM}\s*({UNITS})?\s*(?:->|→|=>|➜|to|에서)\s*{NUM}\s*({UNITS})?",
    re.IGNORECASE,
)
TRAILER = re.compile(r"^[A-Za-z-]+(-by|-to)?:\s|^This reverts commit", re.IGNORECASE)
SEP_REC, SEP_FIELD = "\x1e", "\x1f"


def infer_type(subject: str, files: list[dict]) -> tuple[str, str, bool, bool]:
    """Return (type, scope, breaking, conventional)."""
    if m := CONVENTIONAL.match(subject):
        kind = TYPE_ALIASES.get(m.group("type").lower())
        if kind:
            return kind, (m.group("scope") or "").strip().lower(), bool(m.group("bang")), True
    lowered = subject.lower()
    lead = re.sub(r"^[\w.-]{1,30}(?:\([^)]*\))?:\s+", "", lowered).split(maxsplit=1)
    for kind, verbs in LEAD_VERBS.items():
        if lead and lead[0] in verbs:
            return kind, "", False, False
    for kind, pattern in KEYWORDS:
        if re.search(pattern, lowered):
            return kind, "", False, False
    paths = [f["path"] for f in files]
    if paths and all(is_test(p) for p in paths):
        return "test", "", False, False
    if paths and all(is_doc(p) for p in paths):
        return "docs", "", False, False
    if any(f["status"] == "A" and is_code(f["path"]) and not is_test(f["path"]) for f in files):
        return "feat", "", False, False
    return "change", "", False, False


def parse_number(text: str) -> float:
    return float(text.replace(",", ""))


def extract_metrics(message: str) -> list[dict]:
    out = []
    for line in message.splitlines():
        for m in METRIC_RE.finditer(line):
            before, unit_a, after, unit_b = m.group(1), m.group(2), m.group(3), m.group(4)
            unit = (unit_b or unit_a or "").lower()
            if not unit:  # bare numbers are too ambiguous to call a measurement
                continue
            if unit_a and unit_b and unit_a.lower() != unit_b.lower():
                continue
            out.append({"before": parse_number(before), "after": parse_number(after), "unit": unit, "line": line.strip()})
    return out


def author_args(profile: Profile) -> list[str]:
    return ["--fixed-strings", *[f"--author={who}" for who in profile.identities]]


def revs_for_window(repo: Path, profile: Profile, start: date) -> list[str]:
    """Candidate shas by author, newest first. The committer date is never earlier than the author date,
    so one day of slack before `start` is enough; callers then filter by author date (`in_window`)."""
    since = day_start(start - timedelta(days=1), profile.timezone)
    return git(repo, "rev-list", "--branches", *author_args(profile), f"--since={since}").split()


def in_window(commit: dict, start: date, end: date) -> bool:
    """Author date, in the profile time zone (details() already converted it)."""
    return start <= date.fromisoformat(commit["date"][:10]) <= end


def parse_stats(block: str) -> list[dict]:
    files: dict[str, dict] = {}
    for line in block.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if m := re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line):
            binary = m.group(1) == "-"
            files[m.group(3)] = {"path": m.group(3), "status": "M", "binary": binary,
                                 "added": 0 if binary else int(m.group(1)),
                                 "deleted": 0 if binary else int(m.group(2))}
        elif m := re.match(r"^\s*(create|delete) mode \d+ (.+)$", line):
            if m.group(2) in files:
                files[m.group(2)]["status"] = "A" if m.group(1) == "create" else "D"
    return list(files.values())


COLLAPSE_AT = 25


def collapse(files: list[dict]) -> list[dict]:
    """Fold more than 25 changed files in one generated/noise directory into a single group entry."""
    groups: dict[str, list[dict]] = {}
    for f in files:
        if is_noise(f["path"]):
            groups.setdefault(str(PurePosixPath(f["path"]).parent), []).append(f)
    big = {d for d, members in groups.items() if len(members) > COLLAPSE_AT}
    out = [f for f in files if not (is_noise(f["path"]) and str(PurePosixPath(f["path"]).parent) in big)]
    for d in sorted(big):
        members = groups[d]
        statuses = {m["status"] for m in members}
        out.append({"path": d + "/**", "status": statuses.pop() if len(statuses) == 1 else "M", "binary": False,
                    "added": sum(m["added"] for m in members), "deleted": sum(m["deleted"] for m in members),
                    "group": len(members)})
    return out


def details(repo: Path, shas: list[str], profile: Profile) -> list[dict]:
    if not shas:
        return []
    fmt = SEP_REC + SEP_FIELD.join(["%H", "%P", "%an", "%ae", "%aI", "%s", "%b"]) + SEP_FIELD
    out = git(repo, "log", "--no-walk=unsorted", "--stdin", "--no-renames", "--numstat", "--summary",
              f"--format={fmt}", stdin="\n".join(shas) + "\n")
    tz = zone(profile.timezone)
    commits = []
    for record in out.split(SEP_REC)[1:]:
        sha, parents, name, email, when, subject, body, stats = record.split(SEP_FIELD, 7)
        if not is_mine(name, email, profile.identities):
            continue
        files = parse_stats(stats)
        kept = [f for f in files if not any(under(f["path"], x) for x in profile.exclude_paths)]
        in_scope = [f for f in kept if not profile.scopes or any(under(f["path"], s) for s in profile.scopes)]
        entries = collapse(in_scope)
        kind, scope, breaking, conventional = infer_type(subject, in_scope)
        body_lines = [ln for ln in body.strip().splitlines() if ln.strip() and not TRAILER.match(ln.strip())]
        revert_of = re.search(r"This reverts commit ([0-9a-f]{7,40})", body)
        local = datetime.fromisoformat(when).astimezone(tz)
        commits.append({
            "sha": sha,
            "parents": len(parents.split()),
            "author": name,
            "email": email.lower(),
            "date": local.isoformat(),
            "subject": subject.strip(),
            "body": "\n".join(body_lines[:6]),
            "type": kind,
            "scope": scope,
            "breaking": breaking,
            "conventional": conventional,
            "files": entries,
            "file_count": len(in_scope),
            "excluded_path": bool(files) and not kept,
            "out_of_scope": bool(kept) and not in_scope,
            "added": sum(f["added"] for f in in_scope),
            "deleted": sum(f["deleted"] for f in in_scope),
            "tests_touched": any(is_test(f["path"]) for f in in_scope),
            "tests_added": any(is_test(f["path"]) and (f["status"] == "A" or f["added"] > 0) for f in in_scope),
            "bench_touched": any(is_bench(f["path"]) for f in in_scope),
            "metrics": extract_metrics(subject + "\n" + body),
            "revert_of": revert_of.group(1) if revert_of else "",
        })
    commits.sort(key=lambda c: c["date"])
    return commits


def attach_patch_ids(repo: Path, commits: list[dict]) -> None:
    """Stable patch ids, so the same change on two branches (cherry-pick, rewritten copy) counts once."""
    if not commits:
        return
    patch = git(repo, "log", "--no-walk=unsorted", "--stdin", "-p", "--no-renames", "--no-ext-diff", "--no-textconv",
                "--format=commit %H", stdin="\n".join(c["sha"] for c in commits) + "\n")
    out = subprocess.run(["git", "-C", str(repo), "patch-id", "--stable"], input=patch, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", env=GIT_ENV).stdout
    ids = {sha: pid for pid, sha in (line.split() for line in out.splitlines() if len(line.split()) == 2)}
    for commit in commits:
        commit["patch_id"] = ids.get(commit["sha"], "")


def limit(commits: list[dict], profile: Profile) -> tuple[list[dict], dict]:
    """Apply max_commits / max_files (newest kept). Report truncation instead of hiding it."""
    kept, files = [], 0
    for commit in sorted(commits, key=lambda c: c["date"], reverse=True):
        if len(kept) >= profile.max_commits or files + commit["file_count"] > profile.max_files and kept:
            break
        kept.append(commit)
        files += commit["file_count"]
    kept.sort(key=lambda c: c["date"])
    status = {"complete": len(kept) == len(commits), "kept": len(kept), "found": len(commits),
              "max_commits": profile.max_commits, "max_files": profile.max_files}
    return kept, status


COMMENT_PREFIX = {
    "#": {"py", "sh", "bash", "zsh", "rb", "r", "pl", "yaml", "yml", "toml", "ex", "exs", "tf", "jl", "ps1", "nim"},
    "//": {"js", "jsx", "ts", "tsx", "mjs", "cjs", "go", "rs", "java", "kt", "kts", "swift", "c", "h", "cc", "cpp",
           "hpp", "cs", "m", "mm", "scala", "dart", "php", "proto", "zig", "scss", "less", "vue", "svelte"},
    "--": {"sql", "lua", "hs"},
}
BLOCK_COMMENT = ("/*", "*", "*/", "<!--", "-->")


def comment_line(text: str, ext: str) -> bool:
    s = text.strip()
    for prefix, exts in COMMENT_PREFIX.items():
        if ext in exts and s.startswith(prefix):
            return True
    return ext in COMMENT_PREFIX["//"] | {"css", "html"} and s.startswith(BLOCK_COMMENT)


def trivial_diff(repo: Path, commit: dict) -> str:
    """Return 'whitespace', 'comment' or '' by reading the whitespace-insensitive patch."""
    files = commit["files"]
    if not files or any(f["status"] != "M" or f["binary"] or f.get("group") for f in files):
        return ""
    patch = git(repo, "show", "--format=", "-w", "--ignore-blank-lines", "--unified=0", "--no-renames",
                "--no-ext-diff", "--no-textconv", commit["sha"], "--", *[f["path"] for f in files],
                *SENSITIVE_PATHSPEC, check=False)
    changed: list[tuple[str, str]] = []
    current_ext = ""
    for line in patch.splitlines():
        if line.startswith("+++ "):
            current_ext = line[6:].rsplit(".", 1)[-1].lower() if "." in line[6:] else ""
        elif line.startswith("--- ") or line.startswith("diff ") or line.startswith("@@") or line.startswith("index "):
            continue
        elif line[:1] in "+-" and line.strip() not in {"+", "-"}:
            changed.append((line[1:], current_ext))
    if not changed:
        return "whitespace"
    if all(is_code("x." + ext) for _, ext in changed) and all(comment_line(text, ext) for text, ext in changed):
        return "comment"
    return ""
