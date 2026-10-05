"""Minimal filter (exclude only with a clear reason) and 0-100 importance score."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path, PurePosixPath

from collect import trivial_diff
from common import Profile, is_code, is_doc, is_noise, is_test, under

TYPE_WEIGHT = {"feat": 40, "perf": 40, "fix": 30, "refactor": 22, "change": 20, "test": 18,
               "docs": 10, "revert": 8, "chore": 6, "style": 4}
SIZE_CAP, SIZE_FULL_AT = 25, 1000
CORE_DIRS = {"src", "lib", "core", "app", "server", "api", "pkg", "internal", "domain", "engine", "services"}
BOT_RE = re.compile(r"\[bot\]|dependabot|renovate|github-actions|greenkeeper|snyk-bot|semantic-release-bot", re.I)
EXCLUDE_REASONS = ("merge", "duplicate", "bot", "revert_pair", "excluded_path", "out_of_scope", "empty", "generated_only", "whitespace_only", "comment_only")


def exclusion(commit: dict, reverted: set[str], repo: Path | None, duplicates: set[str] = frozenset()) -> str:
    if commit["parents"] > 1:
        return "merge"
    if commit["sha"] in duplicates:
        return "duplicate"
    if BOT_RE.search(commit["author"]) or BOT_RE.search(commit["email"]):
        return "bot"
    if commit["sha"] in reverted:
        return "revert_pair"
    if commit["excluded_path"]:
        return "excluded_path"
    if commit["out_of_scope"]:
        return "out_of_scope"
    if not commit["files"]:
        return "empty"
    if all(is_noise(f["path"]) for f in commit["files"]):
        return "generated_only"
    if repo is not None:
        kind = trivial_diff(repo, commit)
        if kind:
            return f"{kind}_only"
    return ""


def revert_pairs(commits: list[dict]) -> set[str]:
    shas = [c["sha"] for c in commits]
    out: set[str] = set()
    for commit in commits:
        target = commit["revert_of"]
        if not target:
            continue
        match = next((s for s in shas if s.startswith(target)), None)
        if match:
            out.update({match, commit["sha"]})
    return out


def feature_of(path: str, profile: Profile) -> str:
    best, best_len = "", -1
    for feature in profile.features:
        for prefix in feature.paths:
            if under(path, prefix) and len(prefix) > best_len:
                best, best_len = feature.label, len(prefix)
    return best


def commit_features(commit: dict, profile: Profile) -> list[str]:
    counts: Counter[str] = Counter()
    for f in commit["files"]:
        if label := feature_of(f["path"], profile):
            counts[label] += f["added"] + f["deleted"] + 1
    for feature in profile.features:
        if commit["scope"] and commit["scope"] in feature.keys:
            return [feature.label] + [label for label, _ in counts.most_common() if label != feature.label]
    total = sum(f["added"] + f["deleted"] + 1 for f in commit["files"])
    ranked = [label for label, _ in counts.most_common()]
    if ranked and counts[ranked[0]] * 2 < total:
        commit["cross_cutting"] = True  # no single feature holds half the change
    return ranked


def new_module(commit: dict) -> bool:
    by_dir: dict[str, list[str]] = {}
    for f in commit["files"]:
        by_dir.setdefault(str(PurePosixPath(f["path"]).parent), []).append(f["status"])
    return any(len(st) >= 2 and all(s == "A" for s in st) for st in by_dir.values())


def importance(commit: dict, profile: Profile) -> tuple[int, dict]:
    real = [f for f in commit["files"] if not is_noise(f["path"])]
    lines = sum(f["added"] + f["deleted"] for f in real)
    parts = {
        "type": TYPE_WEIGHT.get(commit["type"], 20),
        "size": min(SIZE_CAP, round(SIZE_CAP * math.log10(1 + lines) / math.log10(1 + SIZE_FULL_AT))),
        "new": 0, "core": 0, "tests": 0, "metric": 0,
    }
    new_code = any(f["status"] == "A" and is_code(f["path"]) and not is_test(f["path"]) for f in real)
    if new_module(commit):
        parts["new"] = 10
    elif new_code:
        parts["new"] = 6
    if commit.get("features"):
        parts["core"] = 8
    elif any(PurePosixPath(f["path"]).parts[0].lower() in CORE_DIRS for f in real if "/" in f["path"]):
        parts["core"] = 5
    has_prod = any(not is_test(f["path"]) and not is_doc(f["path"]) for f in real)
    if commit["tests_added"] and has_prod:
        parts["tests"] = 7
    if commit["metrics"]:
        parts["metric"] = 10
    return min(100, sum(parts.values())), parts


def duplicate_shas(commits: list[dict], seen_patches: set[str], on_head: set[str]) -> set[str]:
    """Same patch id seen before (earlier run) or on another branch: keep one, prefer the current branch."""
    dup: set[str] = set()
    by_pid: dict[str, list[dict]] = {}
    for commit in commits:
        if pid := commit.get("patch_id"):
            by_pid.setdefault(pid, []).append(commit)
    for pid, group in by_pid.items():
        if pid in seen_patches:
            dup.update(c["sha"] for c in group)
            continue
        keep = sorted(group, key=lambda c: (c["sha"] not in on_head, c["date"]))[0]
        dup.update(c["sha"] for c in group if c is not keep)
    return dup


def run(commits: list[dict], profile: Profile, repo: Path | None, duplicates: set[str] = frozenset()) -> dict:
    reverted = revert_pairs(commits)
    included, excluded = [], []
    for commit in commits:
        reason = exclusion(commit, reverted, repo, duplicates)
        if reason:
            excluded.append({"sha": commit["sha"], "reason": reason})
            continue
        commit["features"] = commit_features(commit, profile)
        commit["score"], commit["score_parts"] = importance(commit, profile)
        included.append(commit)
    included.sort(key=lambda c: (-c["score"], c["date"]))
    detailed_n = len(included) if len(included) <= 7 else 5 + sum(1 for c in included[5:7] if c["score"] >= 60)
    reasons = Counter(e["reason"] for e in excluded)
    return {
        "included": included,
        "excluded": excluded,
        "detailed_count": detailed_n,
        "excluded_by_reason": {r: reasons[r] for r in EXCLUDE_REASONS if reasons[r]},
    }
