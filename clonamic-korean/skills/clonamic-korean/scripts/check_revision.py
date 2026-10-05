#!/usr/bin/env python3
"""Compare a Korean source text with its revision and flag what a reviser must not change.

Deterministic, stdlib only, Python >= 3.12. It does not judge style. It checks the
failure modes that models reliably miss in their own output:

violations (exit 2: do not ship the revision)
    empty_output       revision is blank
    number_injected    a numeric value appears that the source never had
    quote_altered      a direct quote with a speech/attribution marker is no longer verbatim
    code_altered       a fenced code block is no longer verbatim
    over_revised       character change rate >= 50% (warning instead with --deep)

warnings (exit 1: check each item before shipping)
    change_rate        character change rate >= 30%
    number_dropped     a numeric value from the source disappeared
    term_dropped       a Latin-script name/term from the source disappeared
    term_added         a new Latin-script word appeared (Konglish headings, "Deep Dive")
    inline_code_dropped an inline `code` span disappeared
    modality_lost      fewer obligation/hedge markers than the source
    register_shift     dominant sentence ending changed, or '하였' increased
    hype_added         absolute/hype wording increased ("100%", "원천 차단", "격상")
    loanword_added     business loanwords increased ("임팩트", "어필", "딥다이브")
    cliche_added       boilerplate increased ("시사하는 바가 크다", "로 평가된다")
    nominal_added      nominalized translationese increased ("로 인한", "현상이 발생")
    observer_added     observer/hearsay voice increased ("~로 적혀 있습니다")
    format_added       bold, emoji, or numbered items increased
    heading_changed    a markdown heading was removed or added
    contrast_wiped     5+ contrast parallels in the source, none left

Exit codes: 0 pass, 1 warnings, 2 violations, 3 input error.

Usage:
    python3 check_revision.py --before source.txt --after revised.txt [--deep] [--json]
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


# --------------------------------------------------------------------------- text prep

_FENCE_RE = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
_LIST_MARKER_RE = re.compile(r"^(\s*(?:#{1,6}\s*)?)\d+(?:\.\d+)*[.)]\s", re.MULTILINE)
_NUM_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
_KO_UNIT = {"백": 100, "천": 1_000, "만": 10_000, "억": 100_000_000, "조": 1_000_000_000_000}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\u00a0", " ")
    return re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)


def fenced_blocks(text: str) -> list[str]:
    return _FENCE_RE.findall(text)


def without_fences(text: str) -> str:
    return _FENCE_RE.sub("", text)


# --------------------------------------------------------------------------- change rate

# Hierarchical diff: sentences, then words, then characters, each level only inside
# blocks the level above found changed. Concatenating the units restores the text.
_LEVELS = (
    re.compile(r"[^\n.?!]*(?:[.?!]+\s*|\n+|$)"),
    re.compile(r"\s+|\S+\s*"),
)
_BLOCK_LIMIT = 1_000_000  # len(a) * len(b) above this: let difflib use its junk heuristic


def _distance(a: str, b: str, level: int = 0) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    if level < len(_LEVELS):
        a_units = [u for u in _LEVELS[level].findall(a) if u]
        b_units = [u for u in _LEVELS[level].findall(b) if u]
        if len(a_units) == 1 and len(b_units) == 1:
            return _distance(a, b, level + 1)
        big = len(a_units) * len(b_units) > _BLOCK_LIMIT
        matcher = difflib.SequenceMatcher(None, a_units, b_units, autojunk=big)
        return sum(
            _distance("".join(a_units[i1:i2]), "".join(b_units[j1:j2]), level + 1)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        )
    big = len(a) * len(b) > _BLOCK_LIMIT
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=big)
    return sum(
        max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"
    )


def change_rate(before: str, after: str) -> float:
    """Approximate character edit distance / source length."""
    if not before:
        return 0.0 if not after else 1.0
    return _distance(before, after) / len(before)


# --------------------------------------------------------------------------- numbers

def number_values(text: str) -> set[str]:
    """Canonical numeric values. Ordered-list/heading numbering is ignored."""
    text = _LIST_MARKER_RE.sub(r"\1", text)
    values: set[str] = set()
    for match in _NUM_TOKEN.finditer(text):
        token = match.group(0).replace(",", "")
        mult = _KO_UNIT.get(text[match.end():match.end() + 1])
        try:
            value = float(token)
        except ValueError:
            values.add(token)
            continue
        if mult:
            value *= mult
        values.add(str(int(value)) if value == int(value) else repr(value))
    return values


# --------------------------------------------------------------------------- quotes

_MIN_QUOTE = 8
_SPEECH_MARK_RE = re.compile(
    r"말했|말한다|밝혔|밝힌|강조했|강조한|언급|설명했|설명한다|전했|덧붙"
    r"|지적했|지적한다|답했|묻자|물었|따르면|촉구|당부|호소|주장했|경고했"
)
_ATTRIB_AFTER_RE = re.compile(
    r"^[\"”」』]?\s*(?:[이으]?라고|고|[으]?로)\s*[가-힣]{1,8}(?:하|했|한다|된다|였|입니다)"
)


def extract_quotes(text: str) -> list[str]:
    quotes: list[str] = []
    for opening, closing in (("「", "」"), ("『", "』"), ("“", "”")):
        quotes += re.findall(re.escape(opening) + "([^" + closing + "]+)" + re.escape(closing), text)
    parts = text.split('"')
    if len(parts) % 2 == 1:
        quotes += parts[1::2]
    return [q for q in quotes if len(q.strip()) >= _MIN_QUOTE]


def is_attributed(source: str, quote: str) -> bool:
    """Speech-marked quotes are immutable; a writer's own rhetorical quotes are not."""
    index = source.find(quote)
    if index < 0:
        return True
    before = source[max(0, index - 30):index]
    cut = before.rfind(". ")
    if cut >= 0:
        before = before[cut + 1:]
    after = source[index + len(quote):index + len(quote) + 24]
    cut = after.find(". ")
    if cut >= 0:
        after = after[:cut + 1]
    if _ATTRIB_AFTER_RE.search(after):
        return True
    return bool(_SPEECH_MARK_RE.search(before) or _SPEECH_MARK_RE.search(after))


# --------------------------------------------------------------------------- terms

_LATIN_TERM = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:[-_.+][A-Za-z0-9]+)*")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_URL = re.compile(r"https?://\S+")


def latin_terms(text: str) -> set[str]:
    text = _URL.sub(" ", without_fences(text))
    return {t for t in _LATIN_TERM.findall(text) if len(t) >= 2}


# --------------------------------------------------------------------------- modality
# Obligation (당위) and hedge (추측) markers. Tuned against real revisions:
# the deontic stem allows only open syllables that form -아/어야 (있어야, 손봐야),
# so nouns such as "분야 해설" do not match.

_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_DEONTIC_STEM = "".join(
    chr(0xAC00 + c)
    for c in range(11172)
    if c % 28 == 0 and _JUNG[(c // 28) % 21] in "ㅏㅐㅓㅔㅕㅘㅙㅚㅝㅞ"
)
DEONTIC_RE = re.compile(
    rf"[{_DEONTIC_STEM}]야\s*(?:한다|합니다|했다|하며|하고|하는|할|함"
    r"|했어요|했어|해요|해서|해도|하지요|하죠|해)"
    rf"|[{_DEONTIC_STEM}]야만"
    r"|필요가\s*있|필요하다|필요합니다|요구된다|요구됩니다"
    r"|시급하다|시급합니다|바람직하다|바람직합니다|촉구한다|당부한다"
    r"|[가-힣]지\s*않으면\s*안\s*(?:된다|됩니다|되며|돼|되)"
)
HEDGE_RE = re.compile(
    r"수\s*(?:있다|있습니다|있을)"
    r"|것으로\s*(?:보인다|보입니다|전망|판단|추정|알려)"
    r"|가능성[이도은을에]"
    r"|[을ㄹ]\s*수도|수도\s*있"
    r"|[로으]\s*보인다|[로으]\s*보입니다"
    r"|판단된다|판단됩니다|여겨진다|여겨집니다"
    r"|해석된다|추정된다|기대된다|우려된다"
    r"|듯하|듯\s*싶|것\s*같다|것\s*같습니다"
    r"|전망(?:이다|된다|한다|했다|입니다|이며|하고)"
    r"|예상(?:된다|이다|한다|했다|됩니다)"
    r"|단정하기|여지(?:도|가)?\s*있|배제할\s*수\s*없"
)

# --------------------------------------------------------------------------- register

_SENT_END = re.compile(r"[^.?!\n]+[.?!]?")
_YO_NOUN_HEADS = "필중개수주소강동풍"


def ending_class(sentence: str) -> str | None:
    s = sentence.strip().rstrip(" \"'”’)]}")
    s = s.rstrip(".?!…")
    if not s or not re.search(r"[가-힣]$", s):
        return None
    if s.endswith(("니다", "니까")):
        return "합쇼체"
    if s.endswith("요") and (len(s) < 2 or s[-2] not in _YO_NOUN_HEADS):
        return "해요체"
    if s.endswith("다"):
        return "한다체"
    return None


def dominant_register(text: str) -> str | None:
    counts = Counter(c for c in map(ending_class, _SENT_END.findall(without_fences(text))) if c)
    if not counts:
        return None
    name, top = counts.most_common(1)[0]
    if top >= 3 and top * 2 > sum(counts.values()):
        return name
    return None


# --------------------------------------------------------------------------- injected wording
# Increase-only lists: keeping what the source already had is never flagged.

HYPE = (
    "100%", "100 %", "원천 차단", "원천적으로", "완벽하게", "완벽히", "완벽한", "격상",
    "극대화", "극심한", "치명적", "심각하게", "무결성", "혁신적", "획기적", "압도적",
    "폭발적", "파격적", "전례 없는", "게임체인저", "대폭", "비약적",
)
LOANWORDS = (
    "임팩트", "어필", "딥다이브", "딥 다이브", "인사이트", "시너지", "레버리지", "니즈",
    "퀵윈", "To-Be", "As-Is", "Deep Dive", "deep dive", "impact",
)
CLICHES = (
    "기록적인 성과", "괄목할 만한", "로 평가된다", "로 평가받", "주목받", "크게 기여",
    "중요한 역할을 한다", "시사하는 바가 크", "의미가 크다", "새로운 장을 열", "지평을 열",
)
NOMINAL = (
    "로 인한", "으로 인한", "현상이 발생", "가 발생했", "이 발생했", "을 진행하였",
    "를 진행하였", "을 수행하였", "를 수행하였", "에 있어", "되어지", "에서의", "으로의",
)
OBSERVER = (
    "로 적혀 있", "라고 적혀 있", "로 되어 있습니다", "라고 되어 있", "것으로 나타났",
    "것으로 확인되었", "것으로 알려져",
)
CONTRAST = ("가 아니라", "이 아니라", "것이 아니라", "것은 아니다", "인가, ")

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2194-\u21FF]")
_BOLD = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
_NUMBERED = re.compile(r"^\s*(?:#{1,6}\s*)?\d+(?:\.\d+)*[.)]\s", re.MULTILINE)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def count_terms(text: str, terms: tuple[str, ...]) -> Counter[str]:
    return Counter({t: text.count(t) for t in terms if text.count(t)})


def increased(before: str, after: str, terms: tuple[str, ...]) -> list[str]:
    b, a = count_terms(before, terms), count_terms(after, terms)
    return [f"{t} {b.get(t, 0)}→{n}" for t, n in a.items() if n > b.get(t, 0)]


# --------------------------------------------------------------------------- main check

def check(before: str, after: str, *, deep: bool = False) -> dict[str, object]:
    before, after = normalize(before), normalize(after)
    violations: list[Finding] = []
    warnings: list[Finding] = []

    if not after.strip():
        violations.append(Finding("empty_output", "결과가 비어 있습니다"))
        return _result(0.0 if not before else 1.0, violations, warnings)

    rate = change_rate(before, after)
    if rate >= STOP_RATE and not deep:
        violations.append(Finding("over_revised", f"변경률 {rate:.1%} — 다듬기 한도 50% 이상"))
    elif rate >= WARN_RATE:
        warnings.append(Finding("change_rate", f"변경률 {rate:.1%} — 30% 이상, 과다 수정인지 확인"))

    src_nums, out_nums = number_values(before), number_values(after)
    if added := sorted(out_nums - src_nums):
        violations.append(Finding("number_injected", "원문에 없던 수치: " + ", ".join(added)))
    if dropped := sorted(src_nums - out_nums):
        warnings.append(Finding("number_dropped", "원문 수치가 사라짐: " + ", ".join(dropped)))

    for quote in extract_quotes(before):
        if quote not in after and is_attributed(before, quote):
            violations.append(Finding("quote_altered", f"직접 인용이 바뀜: {quote[:40]}"))

    for block in fenced_blocks(before):
        if block not in after:
            first = block.splitlines()[0] if block else ""
            violations.append(Finding("code_altered", f"코드 블록이 바뀜: {first[:40]}"))

    src_code = set(_INLINE_CODE.findall(without_fences(before)))
    if lost := sorted(c for c in src_code if f"`{c}`" not in after and c not in after):
        warnings.append(Finding("inline_code_dropped", "인라인 코드가 사라짐: " + ", ".join(lost)))

    src_terms, out_terms = latin_terms(before), latin_terms(after)
    if lost := sorted(src_terms - out_terms):
        warnings.append(Finding("term_dropped", "원문 영문 이름·용어가 사라짐: " + ", ".join(lost)))
    if new := sorted(out_terms - src_terms):
        warnings.append(Finding("term_added", "새 영문 표현: " + ", ".join(new)))

    for name, pattern in (("당위", DEONTIC_RE), ("추측", HEDGE_RE)):
        b, a = Counter(pattern.findall(before)), Counter(pattern.findall(after))
        if sum(a.values()) < sum(b.values()):
            lost_marks = [f"{m} {n}→{a.get(m, 0)}" for m, n in b.items() if a.get(m, 0) < n]
            warnings.append(Finding(
                "modality_lost",
                f"{name} 표현 {sum(b.values())}→{sum(a.values())}: " + ", ".join(lost_marks),
            ))

    src_reg, out_reg = dominant_register(before), dominant_register(after)
    if src_reg and out_reg and src_reg != out_reg:
        warnings.append(Finding("register_shift", f"문체 높낮이 {src_reg} → {out_reg}"))
    if after.count("하였") > before.count("하였"):
        warnings.append(Finding(
            "register_shift", f"'하였' {before.count('하였')}→{after.count('하였')} (격식 올림)",
        ))

    for code, terms in (
        ("hype_added", HYPE),
        ("loanword_added", LOANWORDS),
        ("cliche_added", CLICHES),
        ("nominal_added", NOMINAL),
        ("observer_added", OBSERVER),
    ):
        if hits := increased(before, after, terms):
            warnings.append(Finding(code, ", ".join(hits)))

    fmt = []
    for label, pattern in (("굵은 글씨", _BOLD), ("이모지", _EMOJI), ("번호 항목", _NUMBERED)):
        b, a = len(pattern.findall(before)), len(pattern.findall(after))
        if a > b:
            fmt.append(f"{label} {b}→{a}")
    if fmt:
        warnings.append(Finding("format_added", ", ".join(fmt)))

    src_heads = [h.strip() for h in _HEADING.findall(before)]
    out_heads = [h.strip() for h in _HEADING.findall(after)]
    removed = [h for h in src_heads if h not in out_heads]
    added_heads = [h for h in out_heads if h not in src_heads]
    if removed or added_heads:
        parts = []
        if removed:
            parts.append("사라진 제목: " + ", ".join(removed))
        if added_heads:
            parts.append("새 제목: " + ", ".join(added_heads))
        warnings.append(Finding("heading_changed", " / ".join(parts)))

    b_contrast = sum(before.count(t) for t in CONTRAST)
    if b_contrast >= 5 and sum(after.count(t) for t in CONTRAST) == 0:
        warnings.append(Finding("contrast_wiped", f"대구 {b_contrast}→0 — 잘 쓴 대구 하나는 남긴다"))

    return _result(rate, violations, warnings)


def _result(rate: float, violations: list[Finding], warnings: list[Finding]) -> dict[str, object]:
    code = 2 if violations else 1 if warnings else 0
    return {
        "code": code,
        "change_rate": round(rate, 4),
        "violations": [asdict(f) for f in violations],
        "warnings": [asdict(f) for f in warnings],
    }


VERDICT = {0: "통과", 1: "확인 필요", 2: "채택 금지"}


def render(result: dict[str, object]) -> str:
    lines = [f"판정: {VERDICT[result['code']]} ({result['code']})", f"변경률: {result['change_rate']:.1%}"]
    lines += [f"[위반] {f['code']}: {f['detail']}" for f in result["violations"]]
    lines += [f"[확인] {f['code']}: {f['detail']}" for f in result["warnings"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="원문과 고친 글을 대조한다.")
    parser.add_argument("--before", required=True, help="원문 파일")
    parser.add_argument("--after", required=True, help="고친 글 파일")
    parser.add_argument("--deep", action="store_true", help="깊게 고치기: 변경률 50%%를 경고로만 본다")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)
    try:
        before = Path(args.before).read_text(encoding="utf-8")
        after = Path(args.after).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"입력 오류: {error}", file=sys.stderr)
        return 3
    result = check(before, after, deep=args.deep)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return int(result["code"])


if __name__ == "__main__":
    raise SystemExit(main())
