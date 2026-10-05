"""Publish gate for a written entry: leaks, entry contract, evidence labels, placeholders.

Any finding blocks the local write and the Notion sync.
"""

from __future__ import annotations

import re

from common import Profile
from redact import findings

CONTRACT = "task-log:v1"
SECTIONS = ["한눈에 보기", "목표·맥락", "포트폴리오 하이라이트", "작업 상세", "기술적 의사결정", "문제 해결 기록",
            "검증·측정 결과", "진행 정도", "기여·영향", "회고·다음 작업", "근거·신뢰도"]
ITEM_FIELDS = {  # section: (ordered fields, required fields)
    "작업 상세": (["목표", "시작 상태", "실행", "변경점", "선택 이유", "결과", "근거"], {"목표", "실행", "결과", "근거"}),
    "기술적 의사결정": (["선택", "대안", "근거", "영향"], {"선택", "근거"}),
    "문제 해결 기록": (["증상", "확인 원인", "조치", "재검증", "재발 방지"], {"증상", "확인 원인", "조치", "재검증"}),
}
SUMMARY_FIELDS = ["날짜", "파트", "핵심 성과"]
EVIDENCE_FIELDS = ["근거 수준", "수집 범위", "수집 시점", "증거 지문"]
LABELS = {"측정", "판단", "전달", "가정", "미확인"}
FIELD_LINE = re.compile(r"^\s*-\s*([^\s—:\[][^—:]*?)\s*(?:—|:)\s*")
LABEL_RE = re.compile(r"\[([^\[\]\n]*[가-힣][^\[\]\n]*)\]")
FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.+-]+)?|\d{1,2}월\s*\d{1,2}일|\d{4}년")
QUANTITY_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%p|%|ms|초|분|시간|배|MB|KB|GB|건|개|줄|회|명|원|점|일|주|req/s|rps|qps|fps|x\b|s\b)"
    r"|\d+\s*/\s*\d+|\d\s*(?:→|->|=>)\s*\d"
)
PLACEHOLDER_RE = re.compile(
    r"\{\{|\}\}|\[확인 필요|\bTBD\b|\bTODO\b|<[^>\n]*[가-힣][^>\n]*>|‹비공개›|(?<![\w])[NX]{1,2}\s?(?:건|개|%)|○○|△△"
)


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


def contract_problems(text: str, fingerprint: str = "", kind: str = "entry") -> list[dict]:
    problems: list[dict] = []

    def add(rule: str, detail: str, line: int = 0) -> None:
        problems.append({"kind": "contract", "token": rule, "detail": detail, "line": line})

    for number, line in enumerate(text.splitlines(), 1):
        for m in LABEL_RE.finditer(line):
            if m.group(1) not in LABELS:
                add("label", f"unsupported label [{m.group(1)}]", number)
        if m := PLACEHOLDER_RE.search(line):
            add("placeholder", f"placeholder {m.group()!r}", number)
    sections = _sections(text)
    for title, number, lines in sections:
        if kind == "entry" and title == "근거·신뢰도":
            continue  # evidence metadata lines carry their own basis
        for offset, line in enumerate(lines, 1):
            if line.lstrip().startswith(("#", "- 날짜", "- 파트")) or not line.strip():
                continue
            if QUANTITY_RE.search(DATE_RE.sub("", line)) and not any(f"[{lab}]" in line for lab in LABELS):
                add("unlabeled", "quantitative claim without [측정]/[판단]/[전달]/[가정]/[미확인]", number + offset)
    if kind != "entry":
        return problems
    titles = [t for t, _, _ in sections]
    unknown = [t for t in titles if t not in SECTIONS]
    for t in unknown:
        add("section", f"unknown section '{t}'")
    known = [t for t in titles if t in SECTIONS]
    if len(set(known)) != len(known):
        add("section", "a section appears more than once")
    if known != sorted(known, key=SECTIONS.index):
        add("section", "sections out of order")
    if not known or known[0] != "한눈에 보기":
        add("section", "first section must be 한눈에 보기")
    if not known or known[-1] != "근거·신뢰도":
        add("section", "last section must be 근거·신뢰도")
    for title, number, lines in sections:
        if title == "한눈에 보기":
            got = _fields(lines)
            for need in SUMMARY_FIELDS:
                if need not in got:
                    add("field", f"한눈에 보기 needs '- {need} —'", number)
        if title == "근거·신뢰도":
            got = _fields(lines)
            for need in EVIDENCE_FIELDS:
                if got.count(need) != 1:
                    add("field", f"근거·신뢰도 needs exactly one '- {need} —'", number)
            prints = FINGERPRINT_RE.findall("\n".join(lines))
            if fingerprint and prints != [fingerprint]:
                add("fingerprint", "증거 지문 must equal the run fingerprint", number)
        if title in ITEM_FIELDS:
            order, required = ITEM_FIELDS[title]
            items: list[tuple[str, list[str]]] = []
            for line in lines:
                if line.startswith("### "):
                    items.append((line[4:].strip(), []))
                elif items:
                    items[-1][1].append(line)
            if not items:
                add("field", f"{title} needs at least one '### ' item", number)
            for name, body in items:
                if title == "작업 상세" and name.startswith("기타"):
                    continue
                got = [f for f in _fields(body) if f in order]
                for need in sorted(required - set(got), key=order.index):
                    add("field", f"{title} / {name}: missing '- {need} —'", number)
                if len(set(got)) != len(got):
                    add("field", f"{title} / {name}: duplicate field", number)
                elif got != sorted(got, key=order.index):
                    add("field", f"{title} / {name}: fields out of order", number)
    return problems


def check(text: str, profile: Profile | None, fingerprint: str = "", kind: str = "entry") -> dict:
    leak_text = FINGERPRINT_RE.sub("sha256:지문", text)
    leaks = findings(leak_text, profile)
    for hit in leaks:
        if hit["kind"] == "secret":
            hit["token"] = hit["token"][:4] + "…"
    blocked = leaks + contract_problems(text, fingerprint, kind)
    return {"ok": not blocked, "blocked": blocked}
