"""Per-commit digest: change kinds and natural-language hints, scrubbed (no paths, file names, identifiers)."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from common import CONFIG_EXT, SENSITIVE_PATHSPEC, Profile, ext_of, git, is_doc, is_noise
from redact import MASK, scrub

ENDPOINT_DIRS = {"api", "apis", "routes", "router", "routers", "endpoints", "controllers", "handlers"}
MODEL_DIRS = {"models", "model", "schema", "schemas", "entities", "migrations"}
DOCSTRING = re.compile(r'"""(.+?)"""', re.DOTALL)
HEADING = re.compile(r"^#{1,3}\s+(\S.*)$")
MAX_HINTS, MAX_HINT_LEN = 5, 120


def kinds_of(files: list[dict], new_module: bool, tests_added: bool) -> list[str]:
    """New module / endpoint / model / test / doc / config, from file status and directory names."""
    out: list[str] = []
    added = [f for f in files if f["status"] == "A" and not is_noise(f["path"])]
    if new_module:
        out.append("새 모듈")
    if any(set(p.lower() for p in PurePosixPath(f["path"]).parts[:-1]) & ENDPOINT_DIRS for f in added):
        out.append("새 엔드포인트")
    if any(set(p.lower() for p in PurePosixPath(f["path"]).parts[:-1]) & MODEL_DIRS for f in added):
        out.append("새 모델")
    if tests_added:
        out.append("테스트 추가")
    if any(is_doc(f["path"]) for f in files):
        out.append("문서 변경")
    if any(ext_of(f["path"]) in CONFIG_EXT and not is_noise(f["path"]) for f in files):
        out.append("설정 변경")
    return out


def _clean(text: str, profile: Profile) -> str:
    text = " ".join(text.split())
    text = scrub(text, profile)
    if not text or MASK in text or len(text) < 6:
        return ""
    return text[:MAX_HINT_LEN]


def hints_of(repo: Path, commit: dict, profile: Profile) -> list[str]:
    """Body lines, added docstrings (first sentence) and added markdown headings, all scrubbed."""
    raw = list(commit["body"].splitlines())
    paths = [f["path"] for f in commit["files"] if not f.get("group")]
    if paths:
        patch = git(repo, "show", "--format=", "--unified=0", "--no-renames", "--no-ext-diff", "--no-textconv",
                    commit["sha"], "--", *paths, *SENSITIVE_PATHSPEC, check=False)
        added = "\n".join(ln[1:] for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        raw += [m.group(1).strip().split("\n")[0] for m in DOCSTRING.finditer(added)]
        raw += [m.group(1) for ln in added.splitlines() if (m := HEADING.match(ln))]
    out: list[str] = []
    for text in raw:
        if (hint := _clean(text, profile)) and hint not in out:
            out.append(hint)
    return out[:MAX_HINTS]
