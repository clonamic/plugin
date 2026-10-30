"""Industry words (업종 낱말) — the one dictionary and its checks.

FDE-Mode serves whatever the persona actually needs, so nothing it ships may lean
to one industry, and nothing it writes during a contest may bring in an industry
the persona never mentioned. `domain_words.json` (next to this file) is the
original; the arena plugins keep byte-identical copies, checked by their tests.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

WORDS_FILE = Path(__file__).resolve().parent / "domain_words.json"


@lru_cache(maxsize=4)
def load(path: str = str(WORDS_FILE)) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def pattern(path: str = str(WORDS_FILE)) -> re.Pattern:
    words = [w for ws in load(path)["words"].values() for w in ws]
    return re.compile("|".join(f"(?:{w})" for w in sorted(words, key=len, reverse=True)))


def find(text: str, path: str = str(WORDS_FILE)) -> list[str]:
    """Every industry-word match in `text`, in order (repeats kept)."""
    return [m.group(0) for m in pattern(path).finditer(text or "")]


OK_FILE = Path(__file__).resolve().parent / "run_time_ok.json"  # phrases with a platform or technical sense (run time only)


# How many phrases the run-time exception list may hold: the file must not become a way to hide industry words (ofkit
# domain skips it like the dictionary itself — M32, 10/30 18:3x). Which words it may carry is pinned by the product test
# (tests/test_domain_neutral.py), so a patch that widens it fails there.
RUN_TIME_OK_MAX = 10


def run_time_ok_problems(phrases: list[dict], allowed: set | frozenset | None = None) -> list[str]:
    """Why a run-time exception list is not acceptable (empty = fine): too many phrases, a phrase with no reason, with
    no dictionary word (useless) or — when `allowed` is given — with a dictionary word outside it."""
    out = [f"too many phrases: {len(phrases)} > {RUN_TIME_OK_MAX}"] if len(phrases) > RUN_TIME_OK_MAX else []
    for p in phrases:
        phrase = str(p.get("phrase") or "")
        words = set(find(phrase))
        if not str(p.get("why") or "").strip():
            out.append(f"no reason: {phrase}")
        if not words:
            out.append(f"no dictionary word: {phrase}")
        elif allowed is not None and words - set(allowed):
            out.append(f"other dictionary word {sorted(words - set(allowed))}: {phrase}")
    return out


@lru_cache(maxsize=1)
def _ok() -> re.Pattern:
    phrases = json.loads(OK_FILE.read_text(encoding="utf-8"))["phrases"]
    # fail closed: a list over the limit is not used at all, and a phrase that breaks the rule is not skipped
    keep = [] if len(phrases) > RUN_TIME_OK_MAX else [p["phrase"] for p in phrases if not run_time_ok_problems([p])]
    return re.compile("|".join(map(re.escape, sorted(keep, key=len, reverse=True))) or r"(?!x)x")


def unsupported(items: dict[str, str], evidence: str, path: str = str(WORDS_FILE)) -> list[dict]:
    """Industry words that FDE wrote (cards, requirements, spec, slice designs) but the persona, the brief and the
    received data never said. `items`: {id: text}. Returns [{word, ids}] — a warning only, never a block.
    One such word is enough to warn; only the phrases in run_time_ok.json (a platform or technical sense) are
    skipped. The shipped-text checks (`scan`, `ofkit domain`) do not use that list."""
    seen = set(find(evidence, path))
    out: dict[str, list[str]] = {}
    for iid, text in items.items():
        for w in dict.fromkeys(find(_ok().sub(" ", text or ""), path)):
            if w not in seen:
                out.setdefault(w, []).append(iid)
    return [{"word": w, "ids": ids} for w, ids in sorted(out.items(), key=lambda kv: -len(kv[1]))]


SCAN_DIRS = ("agents", "skills", "src", "hooks", "profiles", "web", "bin")
SCAN_SUFFIXES = (".md", ".py", ".js", ".json", ".html", ".toml", ".css")


def scan(plugin_root: Path | str, name: str, path: str = str(WORDS_FILE)) -> list[dict]:
    """Industry words in one plugin's README, agents, skills, references and code, minus the allow list.
    Returns [{file, line, word}] (empty = neutral)."""
    root = Path(plugin_root)
    allow = {(a["file"], a["word"]) for a in load(path).get("allow", []) if a.get("plugin") == name}
    rx = pattern(path)
    out = []
    for f in [root / "README.md", *(f for d in SCAN_DIRS for f in sorted((root / d).rglob("*")))]:
        rel = f.relative_to(root).as_posix()
        # the two dictionary files by exact path (M32): a file of the same name anywhere else is scanned
        if (not f.is_file() or "__pycache__" in f.parts or rel in ("src/fde_mode/domain_words.json", "src/fde_mode/run_time_ok.json")
                or (f.suffix and f.suffix not in SCAN_SUFFIXES)):
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for i, ln in enumerate(lines, 1):
            for m in rx.finditer(ln):
                if (rel, m.group(0)) not in allow:
                    out.append({"file": rel, "line": i, "word": m.group(0)})
    return out
