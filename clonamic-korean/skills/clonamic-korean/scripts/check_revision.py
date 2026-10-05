#!/usr/bin/env python3
"""Compare a Korean source text with its revision and flag what a reviser must not change.

Deterministic, stdlib only, Python >= 3.12. It does not judge style. It checks the
failure modes models reliably miss in their own output.

Revision mode (--before and --after)

  violations (exit 2: do not ship)
    empty_output         revision is blank
    number_injected      the revision contains a value absent from the source
    quote_altered        a quote attributed to a speaker was edited
    code_altered         a fenced code block is no longer verbatim
    placeholder_altered  a template placeholder or HTML tag from the source is gone
    link_injected        a URL or link target the source never had
    over_revised         character change rate >= 50% (warning instead with --deep)
    length_over          longer than --limit

  warnings (exit 1: check each item)
    change_rate          character change rate >= 30%
    number_dropped       a numeric value from the source disappeared
    term_dropped         a Latin-script name/term from the source disappeared
    term_added           a new Latin-script word appeared
    inline_code_dropped  an inline `code` span disappeared
    link_dropped         a URL or link target from the source disappeared
    placeholder_added    a new placeholder or HTML tag appeared
    modality_lost        fewer obligation or hedge markers than the source
    register_shift       dominant sentence ending changed, or '하였' increased
    hype_added           absolute or hype wording increased
    loanword_added       business loanwords increased
    cliche_added         boilerplate increased
    nominal_added        verb-to-noun chains increased
    translationese_added calqued particles, double passives, needless causatives increased
    observer_added       observer/hearsay voice about the author's own work increased
    unsourced_added      unsourced consensus or coined-concept framing increased
    spelling             an unambiguous misspelling (or -실게요) is present in the result
    format_added         bold, emoji, or numbered items increased
    heading_changed      a markdown heading was removed or added
    contrast_wiped       5+ contrast parallels in the source, none left

Draft mode (--after only): empty_output, length_over, spelling, and the wording
lists above counted as plain presence.

Every run reports the character count with and without whitespace.

Exit codes: 0 pass, 1 warnings, 2 violations, 3 input error.

Usage:
    python3 check_revision.py --before source.txt --after revised.txt [--deep] [--limit N] [--json]
    python3 check_revision.py --after draft.txt [--limit N [--no-spaces]] [--json]
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 12):  # pragma: no cover - interpreter policy guard
    sys.stderr.write(
        "check_revision.py needs Python 3.12 or newer. "
        "Install it (for example `uv python install 3.12`) and rerun.\n"
    )
    raise SystemExit(3)

import argparse
import difflib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

WARN_RATE = 0.30
STOP_RATE = 0.50


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str


# ----------------------------------------------------------------------------- text prep

FENCE = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace(" ", " ")
    return re.sub("[​-‍⁠﻿]", "", text)


def prose(text: str) -> str:
    """Text with fenced blocks and inline code removed."""
    return INLINE_CODE.sub(" ", FENCE.sub("", text))


def char_counts(text: str) -> tuple[int, int]:
    """(with whitespace, without whitespace). Leading/trailing blank space is ignored."""
    body = text.strip()
    return len(body), sum(1 for ch in body if not ch.isspace())


# ----------------------------------------------------------------------------- change rate
# Diff sentence units first, then words inside changed sentence runs, then characters
# inside changed word runs. Cheap on long documents, close to a character edit distance.

_SPLITTERS = (
    re.compile(r"[^\n.?!]*(?:[.?!]+\s*|\n+|$)"),
    re.compile(r"\s+|\S+\s*"),
)
_QUADRATIC_LIMIT = 1_000_000


def _cost(a: str, b: str, depth: int = 0) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    if depth < len(_SPLITTERS):
        units_a = [u for u in _SPLITTERS[depth].findall(a) if u]
        units_b = [u for u in _SPLITTERS[depth].findall(b) if u]
        if len(units_a) == 1 and len(units_b) == 1:
            return _cost(a, b, depth + 1)
        seq = difflib.SequenceMatcher(
            None, units_a, units_b, autojunk=len(units_a) * len(units_b) > _QUADRATIC_LIMIT
        )
        total = 0
        for tag, i1, i2, j1, j2 in seq.get_opcodes():
            if tag != "equal":
                total += _cost("".join(units_a[i1:i2]), "".join(units_b[j1:j2]), depth + 1)
        return total
    seq = difflib.SequenceMatcher(None, a, b, autojunk=len(a) * len(b) > _QUADRATIC_LIMIT)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in seq.get_opcodes() if tag != "equal")


def change_rate(before: str, after: str) -> float:
    """Approximate character edits divided by source length."""
    if not before:
        return 1.0 if after else 0.0
    return _cost(before, after) / len(before)


# ----------------------------------------------------------------------------- numbers
# "10,000원", "10000원" and "1만 원" are the same value. List numbering is not a value.

LIST_NUMBER = re.compile(r"^(\s*(?:#{1,6}\s*)?)\d+(?:\.\d+)*[.)]\s", re.MULTILINE)
NUMBER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?([십백천만억조]*)")
UNIT_VALUE = {"십": 10**1, "백": 10**2, "천": 10**3, "만": 10**4, "억": 10**8, "조": 10**12}


def number_values(text: str) -> set[str]:
    found: set[str] = set()
    for whole, frac, units in NUMBER.findall(LIST_NUMBER.sub(r"\1", prose(text))):
        value = float(whole.replace(",", "") + frac)
        for unit in units:
            value *= UNIT_VALUE[unit]
        found.add(f"{value:.6f}".rstrip("0").rstrip("."))
    return found


# ----------------------------------------------------------------------------- quotes
# A quote is fixed when the sentence around it attributes it to a speaker
# ("…"고 말했다, …에 따르면). A writer's own slogan in quotes may be edited.

QUOTE_PAIRS = (("“", "”"), ("「", "」"), ("『", "』"))
QUOTE_MIN = 8
SPEECH_STEMS = (
    "말했", "말한", "말하", "밝혔", "밝힌", "강조", "언급", "설명했", "설명한", "전했", "덧붙",
    "지적", "답했", "답변", "물었", "묻자", "따르면", "주장", "경고", "당부", "호소", "촉구",
    "발표", "회고", "털어놓", "토로",
)
QUOTATIVE_AFTER = re.compile(r"^\s*(?:이?라고|고)\s*[가-힣]")


def quotes(text: str) -> list[tuple[str, int, int]]:
    """(quote body, start, end) for every quote long enough to matter."""
    spans = []
    for open_, close in QUOTE_PAIRS:
        for m in re.finditer(re.escape(open_) + "([^" + close + "\n]+)" + re.escape(close), text):
            spans.append((m.group(1), m.start(), m.end()))
    for m in re.finditer(r'"([^"\n]+)"', text):
        spans.append((m.group(1), m.start(), m.end()))
    return [s for s in spans if len(s[0].strip()) >= QUOTE_MIN]


def attributed(text: str, start: int, end: int) -> bool:
    if QUOTATIVE_AFTER.match(text[end:end + 12]):
        return True
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start)) + 1
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    sentence = text[left:start] + " " + text[end:right]
    return any(stem in sentence for stem in SPEECH_STEMS)


# ----------------------------------------------------------------------------- protected tokens

LATIN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:[-_.+][A-Za-z0-9]+)*")
URL = re.compile(r"https?://[^\s<>()\"'”」]+")
LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
PLACEHOLDER = re.compile(
    r"\{\{[^{}\n]+\}\}"                     # {{count}}
    r"|\$\{[^{}\n]+\}"                      # ${user}
    r"|\{[A-Za-z_][\w.]*(?:,[^{}\n]*)?\}"   # {name}, {n, plural, ...}
    r"|%(?:\d+\$)?[sdf@]"                   # %s, %1$s
    r"|</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>\n]*)?/?>"  # HTML/JSX tags
)


def latin_terms(text: str) -> set[str]:
    stripped = URL.sub(" ", FENCE.sub("", text))
    return {t for t in LATIN.findall(stripped) if len(t) >= 2}


def links(text: str) -> set[str]:
    body = FENCE.sub("", text)
    found = {u.rstrip(".,;:!?") for u in URL.findall(body)}
    found |= set(LINK_TARGET.findall(body))
    return found


def placeholders(text: str) -> Counter[str]:
    return Counter(PLACEHOLDER.findall(prose(text)))


# ----------------------------------------------------------------------------- modality
# Obligation (당위) and hedge (추측) markers are counted per class. A revision may move
# them around or change their form, but the class totals must not fall.

def _open_syllable_with(char: str, vowels: str) -> bool:
    code = ord(char) - 0xAC00
    if not 0 <= code < 11172 or code % 28:
        return False
    return "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"[code % 588 // 28] in vowels


_YA = re.compile(r"([가-힣])야(?:만)?\s*(?:하|한|할|함|합|해|했|됩|된|돼)")
DEONTIC_FIXED = re.compile(
    r"필요(?:가|성이)?\s*있|필요(?:하다|합니다|해요|하며|하고|한다)"
    r"|요구(?:된다|됩니다)|바람직(?:하다|합니다|해요)|시급(?:하다|합니다|해요)"
    r"|마땅(?:하다|합니다)|않으면\s*안\s*(?:된|됩|돼)"
)
HEDGE = re.compile(
    r"수\s*(?:도\s*)?있"
    r"|[을ㄹ]?지도\s*모르|것\s*같|듯(?:하|싶|\s*싶|\s*하)"
    r"|(?:[로으]|것으로)\s*(?:보인다|보입니다|보이며|보이고|보여요|보인다는)"
    r"|(?:판단|추정|예상|전망|기대|우려|해석)(?:된다|됩니다|돼요|되며|되고|한다|합니다)"
    r"|여겨(?:진|집|져)|가능성[이도은을에]|여지[가도]?\s*있"
    r"|단정하기|배제할\s*수\s*없|아마도?\s"
)


def modality_counts(text: str) -> tuple[Counter[str], Counter[str]]:
    body = prose(text)
    deontic: Counter[str] = Counter()
    for m in _YA.finditer(body):
        if _open_syllable_with(m.group(1), "ㅏㅐㅓㅔㅕㅘㅙㅚㅝㅞ"):
            deontic["-야 하다"] += 1
    deontic.update(re.sub(r"\s+", " ", m.group(0)) for m in DEONTIC_FIXED.finditer(body))
    hedge = Counter(re.sub(r"\s+", " ", m.group(0)) for m in HEDGE.finditer(body))
    return deontic, hedge


# ----------------------------------------------------------------------------- register

SENTENCE = re.compile(r"[^.?!\n]+[.?!]?")
NOUNS_ENDING_IN_YO = {"필요", "중요", "주요", "개요", "수요", "소요", "강요", "요요", "동요", "풍요"}


def register_of(sentence: str) -> str | None:
    s = sentence.strip().rstrip(" \"'”’)]}.?!…")
    if not s or not "가" <= s[-1] <= "힣":
        return None
    if s.endswith(("니다", "니까")):
        return "합쇼체"
    if s.endswith("요"):
        return None if s[-2:] in NOUNS_ENDING_IN_YO else "해요체"
    if s.endswith("다"):
        return "한다체"
    return None


def dominant_register(text: str) -> str | None:
    tally = Counter(r for r in map(register_of, SENTENCE.findall(prose(text))) if r)
    if not tally:
        return None
    name, top = tally.most_common(1)[0]
    return name if top >= 3 and top * 2 > sum(tally.values()) else None


# ----------------------------------------------------------------------------- wording lists
# Increase-only in revision mode: what the source already had is never flagged.

WORDING: dict[str, tuple[str, ...]] = {
    "hype_added": (
        "100%", "100 %", "원천 차단", "원천적으로", "완벽하게", "완벽히", "완벽한", "격상",
        "극대화", "극심한", "치명적", "심각하게", "무결성", "혁신적", "획기적", "압도적",
        "폭발적", "파격적", "전례 없는", "게임체인저", "대폭", "비약적",
    ),
    "loanword_added": (
        "임팩트", "어필", "딥다이브", "딥 다이브", "인사이트", "시너지", "레버리지", "니즈",
        "퀵윈", "To-Be", "As-Is", "Deep Dive", "deep dive", "impact",
    ),
    "cliche_added": (
        "기록적인 성과", "괄목할 만한", "로 평가된다", "로 평가받", "주목받", "크게 기여",
        "중요한 역할을 한", "시사하는 바가 크", "의미가 크다", "새로운 장을 열", "지평을 열",
        "앞서 말씀드린", "앞서 설명했듯이", "다음과 같습니다",
    ),
    "nominal_added": (
        "로 인한", "으로 인한", "현상이 발생", "가 발생했", "이 발생했",
        "을 진행하였", "를 진행하였", "을 진행했", "를 진행했",
        "을 수행하였", "를 수행하였", "을 수행했", "를 수행했",
    ),
    "translationese_added": (
        "에 대해", "에 대하여", "에 관하여", "와 관련하여", "과 관련하여", "에 의해", "에 의하여",
        "에 있어", "가지고 있", "로부터의", "에서의", "으로의", "의 경우", "에 위치한", "에 위치하",
        "되어지", "되어진", "보여지", "쓰여지", "쓰여진", "닫혀지", "잊혀지", "불려지", "놓여지",
        "나뉘어지", "읽혀지", "개선시", "향상시", "발전시", "감소시", "증가시", "변화시", "설득시",
        "하는 중이", "중 하나이", "중 하나다", "중 하나입",
    ),
    "observer_added": (
        "로 적혀 있", "라고 적혀 있", "로 되어 있습니다", "라고 되어 있", "것으로 나타났",
        "것으로 확인되었", "것으로 알려져",
    ),
    "unsourced_added": (
        "일반적으로", "흔히", "널리 알려", "널리 쓰이", "전문가들은", "전문가들에 따르면",
        "많은 사람들이", "대부분의 사람", "업계에서는", "통상적으로", "연구에 따르면",
        "이른바", "소위", "이것이 바로",
    ),
}

# Forms with exactly one correct replacement (plus the always-wrong honorific -실게요).
# Ambiguous cases (에요/예요, 로서/로써, 바램) need context and are left to the reviser.
MISSPELLING: dict[str, str] = {
    "됬": "됐", "됀": "된", "되요": "돼요", "되서": "돼서", "뵈요": "봬요",
    "않되": "안 되", "않돼": "안 돼", "몇일": "며칠", "역활": "역할", "어의없": "어이없",
    "오랫만": "오랜만", "왠만": "웬만", "왠일": "웬일", "웬지": "왠지", "희안하": "희한하",
    "어떻해": "어떡해", "할께": "할게", "갈께": "갈게", "줄께": "줄게", "볼께": "볼게",
    "드릴께": "드릴게", "할려고": "하려고", "갈려고": "가려고", "볼려고": "보려고",
    "일일히": "일일이", "깨끗히": "깨끗이", "곰곰히": "곰곰이", "틈틈히": "틈틈이",
    "번번히": "번번이", "설겆이": "설거지", "컨텐츠": "콘텐츠", "메세지": "메시지",
    "캡쳐": "캡처", "리더쉽": "리더십", "멤버쉽": "멤버십", "스케쥴": "스케줄",
    "실게요": "-아 주세요 (높임 오류)",
}

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-⇿]")
BOLD = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
NUMBERED = re.compile(r"^\s*(?:#{1,6}\s*)?\d+(?:\.\d+)*[.)]\s", re.MULTILINE)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
CONTRAST = ("가 아니라", "이 아니라", "것이 아니라", "것은 아니다", "인가, ")


def tally(text: str, words: tuple[str, ...]) -> Counter[str]:
    return Counter({w: n for w in words if (n := text.count(w))})


def grown(before: str, after: str, words: tuple[str, ...]) -> list[str]:
    old, new = tally(before, words), tally(after, words)
    return [f"{w} {old.get(w, 0)}→{n}" for w, n in new.items() if n > old.get(w, 0)]


def spelling_findings(text: str) -> list[Finding]:
    hits = [f"{bad}→{good} ×{n}" for bad, good in MISSPELLING.items() if (n := prose(text).count(bad))]
    return [Finding("spelling", "맞춤법·높임 의심: " + ", ".join(hits))] if hits else []


def length_findings(text: str, limit: int | None, no_spaces: bool) -> list[Finding]:
    if limit is None:
        return []
    with_ws, without_ws = char_counts(text)
    size, label = (without_ws, "공백 제외") if no_spaces else (with_ws, "공백 포함")
    if size > limit:
        return [Finding("length_over", f"{label} {size}자 — 한도 {limit}자를 {size - limit}자 넘음")]
    return []


# ----------------------------------------------------------------------------- checks

def check(
    before: str,
    after: str,
    *,
    deep: bool = False,
    limit: int | None = None,
    no_spaces: bool = False,
) -> dict[str, object]:
    before, after = normalize(before), normalize(after)
    bad: list[Finding] = []
    warn: list[Finding] = []

    if not after.strip():
        bad.append(Finding("empty_output", "결과가 비어 있습니다"))
        return _result(0.0 if not before else 1.0, after, bad, warn)

    rate = change_rate(before, after)
    if rate >= STOP_RATE and not deep:
        bad.append(Finding("over_revised", f"변경률 {rate:.1%} — 다듬기 한도 50% 이상"))
    elif rate >= WARN_RATE:
        warn.append(Finding("change_rate", f"변경률 {rate:.1%} — 30% 이상, 과다 수정인지 확인"))

    src_nums, out_nums = number_values(before), number_values(after)
    if extra := sorted(out_nums - src_nums):
        bad.append(Finding("number_injected", "원문에 없던 수치: " + ", ".join(extra)))
    if gone := sorted(src_nums - out_nums):
        warn.append(Finding("number_dropped", "원문 수치가 사라짐: " + ", ".join(gone)))

    for body, start, end in quotes(before):
        if body not in after and attributed(before, start, end):
            bad.append(Finding("quote_altered", f"직접 인용이 바뀜: {body[:40]}"))

    for block in FENCE.findall(before):
        if block not in after:
            bad.append(Finding("code_altered", f"코드 블록이 바뀜: {block.splitlines()[0][:40]}"))

    src_ph, out_ph = placeholders(before), placeholders(after)
    if gone := sorted((src_ph - out_ph).elements()):
        bad.append(Finding("placeholder_altered", "자리표시자·태그가 사라지거나 바뀜: " + ", ".join(gone)))
    if extra := sorted((out_ph - src_ph).elements()):
        warn.append(Finding("placeholder_added", "새 자리표시자·태그: " + ", ".join(extra)))

    src_links, out_links = links(before), links(after)
    if extra := sorted(out_links - src_links):
        bad.append(Finding("link_injected", "원문에 없던 링크: " + ", ".join(extra)))
    if gone := sorted(src_links - out_links):
        warn.append(Finding("link_dropped", "원문 링크가 사라짐: " + ", ".join(gone)))

    src_code = set(INLINE_CODE.findall(FENCE.sub("", before)))
    if gone := sorted(c for c in src_code if c not in after):
        warn.append(Finding("inline_code_dropped", "인라인 코드가 사라짐: " + ", ".join(gone)))

    src_terms, out_terms = latin_terms(before), latin_terms(after)
    if gone := sorted(src_terms - out_terms):
        warn.append(Finding("term_dropped", "원문 영문 이름·용어가 사라짐: " + ", ".join(gone)))
    if extra := sorted(out_terms - src_terms):
        warn.append(Finding("term_added", "새 영문 표현: " + ", ".join(extra)))

    for label, old, new in zip(("당위", "추측"), modality_counts(before), modality_counts(after)):
        if new.total() < old.total():
            lost = [f"{m} {n}→{new.get(m, 0)}" for m, n in old.items() if new.get(m, 0) < n]
            warn.append(Finding(
                "modality_lost", f"{label} 표현 {old.total()}→{new.total()}: " + ", ".join(lost)
            ))

    src_reg, out_reg = dominant_register(before), dominant_register(after)
    if src_reg and out_reg and src_reg != out_reg:
        warn.append(Finding("register_shift", f"문체 높낮이 {src_reg} → {out_reg}"))
    if (n_after := after.count("하였")) > (n_before := before.count("하였")):
        warn.append(Finding("register_shift", f"'하였' {n_before}→{n_after} (격식 올림)"))

    for code, words in WORDING.items():
        if hits := grown(prose(before), prose(after), words):
            warn.append(Finding(code, ", ".join(hits)))

    warn += spelling_findings(after)

    fmt = []
    for label, pattern in (("굵은 글씨", BOLD), ("이모지", EMOJI), ("번호 항목", NUMBERED)):
        old_n, new_n = len(pattern.findall(before)), len(pattern.findall(after))
        if new_n > old_n:
            fmt.append(f"{label} {old_n}→{new_n}")
    if fmt:
        warn.append(Finding("format_added", ", ".join(fmt)))

    src_heads = [h.strip() for h in HEADING.findall(before)]
    out_heads = [h.strip() for h in HEADING.findall(after)]
    parts = []
    if removed := [h for h in src_heads if h not in out_heads]:
        parts.append("사라진 제목: " + ", ".join(removed))
    if added := [h for h in out_heads if h not in src_heads]:
        parts.append("새 제목: " + ", ".join(added))
    if parts:
        warn.append(Finding("heading_changed", " / ".join(parts)))

    contrast_before = sum(before.count(t) for t in CONTRAST)
    if contrast_before >= 5 and not any(t in after for t in CONTRAST):
        warn.append(Finding("contrast_wiped", f"대구 {contrast_before}→0 — 잘 쓴 대구 하나는 남긴다"))

    bad += length_findings(after, limit, no_spaces)
    return _result(rate, after, bad, warn)


def check_draft(text: str, *, limit: int | None = None, no_spaces: bool = False) -> dict[str, object]:
    """Self-check for a new draft: no source to compare, so wording lists count presence."""
    text = normalize(text)
    if not text.strip():
        return _result(None, text, [Finding("empty_output", "결과가 비어 있습니다")], [])
    warn = [Finding(code, ", ".join(hits)) for code, words in WORDING.items()
            if (hits := grown("", prose(text), words))]
    warn += spelling_findings(text)
    return _result(None, text, length_findings(text, limit, no_spaces), warn)


def _result(rate: float | None, text: str, bad: list[Finding], warn: list[Finding]) -> dict[str, object]:
    with_ws, without_ws = char_counts(text)
    return {
        "code": 2 if bad else 1 if warn else 0,
        "change_rate": None if rate is None else round(rate, 4),
        "chars": {"with_spaces": with_ws, "without_spaces": without_ws},
        "violations": [asdict(f) for f in bad],
        "warnings": [asdict(f) for f in warn],
    }


VERDICT = {0: "통과", 1: "확인 필요", 2: "채택 금지"}


def render(result: dict[str, object]) -> str:
    chars = result["chars"]
    lines = [f"판정: {VERDICT[result['code']]} ({result['code']})"]
    if result["change_rate"] is not None:
        lines.append(f"변경률: {result['change_rate']:.1%}")
    lines.append(f"글자 수: 공백 포함 {chars['with_spaces']} / 공백 제외 {chars['without_spaces']}")
    lines += [f"[위반] {f['code']}: {f['detail']}" for f in result["violations"]]
    lines += [f"[확인] {f['code']}: {f['detail']}" for f in result["warnings"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="원문과 고친 글을 대조한다. 원문 없이 주면 초안만 점검한다.")
    parser.add_argument("--before", help="원문 파일 (없으면 초안 점검)")
    parser.add_argument("--after", required=True, help="고친 글 또는 초안 파일")
    parser.add_argument("--deep", action="store_true", help="깊게 고치기: 변경률 50%%를 경고로만 본다")
    parser.add_argument("--limit", type=int, help="글자 수 한도 (기본은 공백 포함)")
    parser.add_argument("--no-spaces", action="store_true", help="--limit을 공백 제외 글자 수로 센다")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)
    try:
        after = Path(args.after).read_text(encoding="utf-8")
        before = Path(args.before).read_text(encoding="utf-8") if args.before else None
    except (OSError, UnicodeDecodeError) as error:
        print(f"입력 오류: {error}", file=sys.stderr)
        return 3
    if before is None:
        result = check_draft(after, limit=args.limit, no_spaces=args.no_spaces)
    else:
        result = check(before, after, deep=args.deep, limit=args.limit, no_spaces=args.no_spaces)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return int(result["code"])


if __name__ == "__main__":
    raise SystemExit(main())
