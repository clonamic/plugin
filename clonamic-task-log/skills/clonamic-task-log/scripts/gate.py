"""Publish gate for a written entry: leaks, entry contract, banned wording, numbers backed by the run.

Any finding blocks the local write and the Notion sync.
"""

from __future__ import annotations

import re

from common import Profile
from redact import findings

CONTRACT = "task-log:v2"
SECTIONS = ["핵심 요약", "한 일", "기술 판단", "문제 해결", "진행 상황", "다음 할 일", "포트폴리오 문장"]
REQUIRED = {"핵심 요약", "한 일", "포트폴리오 문장"}  # 진행 상황 is also required when the profile has features
ITEM_FIELDS = ["문제", "한 일", "결과"]
TITLE_RE = re.compile(r"^# (\d{4}-\d{2}-\d{2}(?:~\d{4}-\d{2}-\d{2})?) · \S")
FIELD_LINE = re.compile(r"^\s*-\s*([^\s—:\[][^—:]*?)\s*(?:—|:)\s*")
LABEL_RE = re.compile(r"\[[^\[\]\n]*[가-힣][^\[\]\n]*\]")  # any bracket label: [측정] [판단] [전달] [가정] [미확인] ...
HEDGES = ["것으로 보입니다", "것 같습니다", "로 보입니다", "추정됩니다", "듯합니다", "것으로 판단됩니다"]
HEDGE_RE = re.compile("|".join(map(re.escape, HEDGES)))
COUNT_RE = re.compile(r"커밋\s*\d+\s*건|파일\s*\d+\s*개|\d[\d,]*\s*줄\s*(?:추가|삭제)|\d+\s*건\s*반영|변경\s*\d+")
PLACEHOLDER_RE = re.compile(
    r"\{\{|\}\}|\[확인 필요|\bTBD\b|\bTODO\b|<[^>\n]*[가-힣][^>\n]*>|‹비공개›|(?<![\w])[NX]{1,2}\s?(?:건|개|%)|○○|△△"
    r"|(?:^[\s\-*|]*|—\s*)(?:…|\.\.\.)\s*(?:\||$)"
)
MEASURED_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*[%A-Za-zµ가-힣/]{0,6}\s*\(측정\)")
PERCENT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*%(?!p)")


def _sections(text: str) -> list[tuple[str, int, list[str]]]:
    out: list[tuple[str, int, list[str]]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            out.append((line[3:].strip(), number, []))
        elif out:
            out[-1][2].append(line)
    return out


def _fields(lines: list[str]) -> list[str]:
    return [m.group(1).strip() for line in lines if (m := FIELD_LINE.match(line))]


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def run_numbers(run: dict) -> tuple[set[float], set[float]]:
    """(numbers allowed after (측정), percentages allowed anywhere) from the prepared run."""
    measured: set[float] = set()
    for m in run.get("metrics", []):
        for key in ("before", "after", "change_pct"):
            if m.get(key) is not None:
                measured |= {float(m[key]), abs(float(m[key]))}
    percents = set(measured)
    for p in run.get("progress", []):
        percents |= {float(p[k]) for k in ("pct", "prev") if p.get(k) is not None}
    return measured, percents


def wording_problems(text: str, run: dict | None) -> list[dict]:
    problems: list[dict] = []

    def add(rule: str, detail: str, line: int) -> None:
        problems.append({"kind": "contract", "token": rule, "detail": detail, "line": line})

    measured, percents = run_numbers(run) if run is not None else (set(), set())
    for number, line in enumerate(text.splitlines(), 1):
        if "<!--" in line:
            add("comment", "HTML comments and metadata are not allowed in an entry", number)
        for m in LABEL_RE.finditer(line):
            add("label", f"bracket label {m.group()} is not allowed", number)
        if m := PLACEHOLDER_RE.search(line):
            add("placeholder", f"placeholder {m.group().strip()!r}", number)
        for m in HEDGE_RE.finditer(line):
            add("hedging", f"hedging '{m.group()}': state what was done", number)
        for m in COUNT_RE.finditer(line):
            add("count", f"git statistic '{m.group()}': describe the change instead", number)
        if run is None:
            continue
        for m in MEASURED_RE.finditer(line):
            if _num(m.group(1)) not in measured:
                add("measured", f"{m.group(1)} is marked (측정) but is not a measured number of this run", number)
        for m in PERCENT_RE.finditer(line):
            if _num(m.group(1)) not in percents:
                add("percent", f"{m.group(1)}% is not in this run's progress or metrics", number)
    return problems


def contract_problems(text: str, profile: Profile | None, run: dict | None, kind: str = "entry") -> list[dict]:
    problems = wording_problems(text, run)
    if kind != "entry":
        return problems

    def add(rule: str, detail: str, line: int = 0) -> None:
        problems.append({"kind": "contract", "token": rule, "detail": detail, "line": line})

    first = next(((n, ln) for n, ln in enumerate(text.splitlines(), 1) if ln.strip()), (1, ""))
    if not TITLE_RE.match(first[1]):
        add("title", "first line must be '# YYYY-MM-DD · 대표 성과' (range: '# YYYY-MM-DD~YYYY-MM-DD · 대표 성과')", first[0])
    sections = _sections(text)
    titles = [t for t, _, _ in sections]
    for t in titles:
        if t not in SECTIONS:
            add("section", f"unknown section '{t}'")
    known = [t for t in titles if t in SECTIONS]
    if len(set(known)) != len(known):
        add("section", "a section appears more than once")
    elif known != sorted(known, key=SECTIONS.index):
        add("section", "sections out of order: " + " > ".join(SECTIONS))
    required = REQUIRED | ({"진행 상황"} if profile and profile.features else set())
    for need in SECTIONS:
        if need in required and need not in titles:
            add("section", f"missing required section '## {need}'")
    for title, number, lines in sections:
        if title != "한 일":
            continue
        items: list[tuple[str, int, list[str]]] = []
        for offset, line in enumerate(lines, 1):
            if line.startswith("### "):
                items.append((line[4:].strip(), number + offset, []))
            elif items:
                items[-1][2].append(line)
        if not items:
            add("field", "한 일 needs at least one '### 기능 — 한 줄 성과' item", number)
        for name, at, body in items:
            if " — " not in name:
                add("field", f"한 일 / {name}: heading must be '### 기능 — 한 줄 성과'", at)
            got = [f for f in _fields(body) if f in ITEM_FIELDS]
            if got != ITEM_FIELDS:
                add("field", f"한 일 / {name}: needs '- 문제 —', '- 한 일 —', '- 결과 —' once each, in that order", at)
    return problems


def check(text: str, profile: Profile | None, run: dict | None = None, kind: str = "entry") -> dict:
    leaks = findings(text, profile)
    for hit in leaks:
        if hit["kind"] == "secret":
            hit["token"] = hit["token"][:4] + "…"
    blocked = leaks + contract_problems(text, profile, run, kind)
    return {"ok": not blocked, "blocked": blocked}
