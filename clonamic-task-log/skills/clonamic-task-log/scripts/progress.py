"""Deterministic implementation-progress estimate per owned feature and per work unit."""

from __future__ import annotations

import fnmatch
import re
from datetime import date, timedelta
from pathlib import Path

from common import (SENSITIVE_PATHSPEC, day_start, Feature, Profile, WorkUnit, git, is_code, is_test, is_workspace, members,
                    split_paths)

TODO_ERE = r"(TODO|FIXME|XXX|HACK)([^A-Za-z]|$)|NotImplementedError|unimplemented!|todo!\("


def round5(value: float) -> int:
    return int(5 * round(value / 5))


def feature_signals(repo: Path, feature: Feature, profile: Profile) -> dict:
    authors = ["--fixed-strings", *[f"--author={who}" for who in profile.identities]]
    signals: dict = {"milestones": [sum(done for _, done in feature.milestones), len(feature.milestones)]}
    if not feature.paths:
        return signals | {"paths": False}
    files: list[str] = []
    commits = todos = 0
    for member, paths in split_paths(repo, feature.paths):  # a workspace feature may span several repositories
        files += git(member, "ls-files", "--", *paths, *SENSITIVE_PATHSPEC).splitlines()
        commits += int(git(member, "rev-list", "--count", "--branches", "--no-merges", *authors, "--", *paths).strip() or 0)
        todos += len(git(member, "grep", "-I", "-n", "-E", TODO_ERE, "--", *paths, *SENSITIVE_PATHSPEC, check=False).splitlines())
    return signals | {
        "paths": True,
        "code_files": sum(1 for f in files if is_code(f) and not is_test(f)),
        "test_files": sum(1 for f in files if is_test(f)),
        "commits": commits,
        "todos": todos,
    }


def estimate(signals: dict) -> tuple[int, str]:
    """Return (percent, Korean basis phrase).

    with milestones M (done/total):  70*M + 10*A + 10*T + 10*D   (no paths: 90*M + 10*A)
    without milestones:              35*E + 25*A + 15*T + 10*D   (capped at 85)
      A = min(1, my commits touching the paths / 10), T = test files exist, D = 1 - min(1, TODO count / 10),
      E = non-test code files exist. Not 100 until every milestone is checked; 90+ once they all are.
    """
    done, total = signals["milestones"]
    activity = min(1.0, signals.get("commits", 0) / 10)
    tests = 1.0 if signals.get("test_files", 0) else 0.0
    debt = 1.0 - min(1.0, signals.get("todos", 0) / 10)
    exists = 1.0 if signals.get("code_files", 0) else 0.0
    basis = []
    if total:
        m = done / total
        pct = 70 * m + 10 * activity + 10 * tests + 10 * debt if signals["paths"] else 90 * m + 10 * activity
        pct = max(pct, 90) if done == total else min(pct, 95)
        basis.append(f"마일스톤 {done}/{total}")
    else:
        pct = 35 * exists + 25 * activity + 15 * tests + 10 * debt if signals["paths"] else 0
        basis.append("마일스톤 없음")
    if signals["paths"]:
        basis.append(f"내 커밋 {signals['commits']}건")
        basis.append("테스트 있음" if tests else "테스트 없음")
        basis.append(f"미완 표시 {signals['todos']}건")
    return round5(pct), " · ".join(basis)


def unit_window(repo: Path, unit: WorkUnit, today: date) -> dict | None:
    if unit.mode == "cadence":
        start = date.fromisoformat(unit.start)
        if today < start:
            return None
        index = (today - start).days // unit.days
        begin = start + timedelta(days=index * unit.days)
        end = begin + timedelta(days=unit.days - 1)
        return {"label": f"{unit.name} {index + 1}", "start": begin.isoformat(), "end": end.isoformat(),
                "time_pct": round5(100 * ((today - begin).days + 1) / unit.days)}
    if is_workspace(repo):  # tags and branches belong to one repository; a workspace counts by days only
        return None
    if unit.mode == "tag":
        rows = git(repo, "for-each-ref", "refs/tags", "--sort=-creatordate",
                   "--format=%(refname:short) %(creatordate:short)", check=False).splitlines()
        hits = [r.split() for r in rows if r.split() and fnmatch.fnmatch(r.split()[0], unit.pattern)]
        if not hits:
            return None
        number = re.search(r"(\d+)$", hits[0][0])
        label = f"{unit.name} {int(number.group(1)) + 1}" if number else f"{unit.name} (최근 태그 이후)"
        return {"label": label, "start": hits[0][1], "end": "", "time_pct": None}
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
    if not fnmatch.fnmatch(branch, unit.pattern) and not fnmatch.fnmatch(branch.split("/")[-1], unit.pattern):
        return None
    base = ""
    for candidate in ("main", "master", "develop"):
        base = git(repo, "merge-base", candidate, "HEAD", check=False).strip()
        if base:
            break
    started = git(repo, "show", "-s", "--format=%cs", base or "HEAD", check=False).strip()
    number = re.search(r"(\d+)$", branch)
    label = f"{unit.name} {number.group(1)}" if number else f"{unit.name} (현재 브랜치)"
    return {"label": label, "start": started, "end": "", "time_pct": None}


NO_MILESTONES = "마일스톤 미설정"


def feature_history(state: dict, label: str, before: str) -> list[dict]:
    """Earlier dated entries that touched the feature: [{date, headline}] for a 완료 정리's '거쳐 온 길'."""
    rows = []
    for day, value in sorted(state.get("days", {}).items()):
        if day[:10] >= before[:10]:
            continue
        rows += [{"date": day, "headline": block.get("headline", "")} for block in value.get("blocks", {}).values()
                 if label in block.get("features", [])]
    return rows


def completions(profile: Profile, state: dict, live: list[str], updated: str) -> list[dict]:
    """Milestones checked since the last recorded run, and features whose milestones are now all checked.

    A feature with no recorded checklist yet is the baseline (its checked milestones are not new), and a rerun of
    the same date compares against the checklist from before that date, so the answer stays the same."""
    out: list[dict] = []
    for feature in profile.features:
        old = state.get("features", {}).get(feature.label)
        if feature.label not in live or not old or "done" not in old:
            continue
        base = old.get("done_prev", old["done"]) if old.get("updated") == updated else old["done"]
        done = [text for text, checked in feature.milestones if checked]
        history = feature_history(state, feature.label, updated)
        out += [{"kind": "milestone", "feature": feature.label, "target": f"{feature.label} — {text}", "history": history}
                for text in done if text not in base]
        if feature.milestones and len(done) == len(feature.milestones) and len(base) < len(feature.milestones):
            out.append({"kind": "feature", "feature": feature.label, "target": feature.label, "history": history})
    return out


def paths_exist(repo: Path, paths: list[str]) -> bool:
    """A feature whose paths are all gone from the repo no longer exists (features without paths stay)."""
    if not paths:
        return True
    return any((repo / p).exists() for p in paths) or any(
        git(member, "ls-files", "--", *inner, check=False).strip() for member, inner in split_paths(repo, paths))


def run(repo: Path, profile: Profile, included: list[dict], state: dict, today: date) -> dict:
    features = []
    previous = state.get("features", {})
    for feature in profile.features:
        if not paths_exist(repo, feature.paths):
            continue
        signals = feature_signals(repo, feature, profile)
        pct, basis = estimate(signals)
        last = previous.get(feature.label, {})
        base = last.get("prev") if last.get("updated") == today.isoformat() else last.get("pct")
        features.append({
            "feature": feature.label,
            "pct": pct,
            "milestones": signals["milestones"],
            "shown": f"약 {pct}%" if signals["milestones"][1] else NO_MILESTONES,  # % only where milestones exist
            "basis": basis,
            "delta": pct - base if base is not None else None,
            "touched_now": any(feature.label in c.get("features", []) for c in included),
            "next_milestones": [text for text, done in feature.milestones if not done][:3],
            "done": [text for text, done in feature.milestones if done],
            "label": "추정",
        })
    unit = None
    if profile.work_unit and (window := unit_window(repo, profile.work_unit, today)):
        authors = ["--fixed-strings", *[f"--author={who}" for who in profile.identities]]
        since = day_start(date.fromisoformat(window["start"]), profile.timezone)
        args = ["log", "--branches", "--no-merges", *authors, f"--since={since}", "--format=%H", "--name-only"]
        touched: set[str] = set()
        commits = 0
        lines = [(prefix, line) for prefix, member in members(repo) for line in git(member, *args).splitlines()]
        for prefix, line in lines:
            if re.fullmatch(r"[0-9a-f]{40}", line):
                commits += 1
            elif line.strip():
                line = prefix + line
                for feature in profile.features:
                    if any(line == p or line.startswith(p + "/") for p in feature.paths):
                        touched.add(feature.label)
        in_unit = [f for f in features if f["feature"] in touched]
        unit = window | {
            "commits": commits,
            "features": [{"feature": f["feature"], "pct": f["pct"]} for f in in_unit],
            "pct": round5(sum(f["pct"] for f in in_unit) / len(in_unit)) if in_unit else None,
            "label_kind": "추정",
        }
    return {"features": features, "work_unit": unit}
