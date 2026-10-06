"""Publish gate for a written entry: leaks, entry contract, banned wording, numbers backed by the run.

Any finding blocks the local write and the Notion sync.
"""

from __future__ import annotations

import re

from difflib import SequenceMatcher

from common import Profile
from redact import findings

CONTRACT = "task-log:v4"
SECTIONS = ["핵심 요약", "한 일", "완료 정리", "다음 할 일"]
REQUIRED = {"핵심 요약", "한 일"}
REMOVED_SECTIONS = {"포트폴리오 문장": "portfolio-section", "진행 상황": "progress-section",
                    "기술 판단": "removed-section", "오늘 변화": "removed-section", "문제 해결": "removed-section"}
ITEM_FIELDS = ["배경", "접근", "결과"]
ITEM_ORDERS = (["배경", "접근", "결과"], ["배경", "접근", "전후", "결과"])  # 전후 (before -> after example) is optional
DONE_FIELDS = ["만든 것", "거쳐 온 길", "남은 한계"]
DETAIL_MIN, DETAIL_MAX, DETAIL_LEN = 2, 4, 120  # indented detail lines under 접근: one concrete change each
DETAIL_LINE = re.compile(r"^\s{2,}-\s+\S")
LIST_CHAIN = 3  # commas in one sentence; 3 or more means a list of 4+
DUP_RATIO = 0.6  # sentence similarity that counts as saying the same thing twice
SENTENCE_END_RE = re.compile(r"다[.!)\]]*$")  # every prose line ends in the 합쇼체 '~다'
VAGUE_TITLE_RE = re.compile(r"(?:개선|정리|강화|고도화|보완|정비)$")
NOTE_FIELD_NAMES = ("이전 상태", "영향", "사실", "판단", "검증", "전달")
DEFAULT_INTERNAL = ["게이트", "작업 메모", "리더", "작성자", "에이전트 폴더", "하네스", "프리플라이트"]
UNIT_NUMBER_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(개|건|회|번|배|초|분|시간)")  # counted facts: must come from the notes
MAX_ITEMS = 3  # '### ' work items in 한 일 (the final '- 그 밖에 —' bullet is not an item)
VERIFIED_RE = re.compile(r"확인|검증|통과")
LONE_DASH_RE = re.compile(r"(?:^\s*\|(?:[^|\n]*\|)*?\s*-\s*(?=\|))|(?:—\s*-\s*(?:\||$))|(?:^\s*-\s+-\s*$)|(?:^\s*-\s*$)")
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
MAX_LINES = 70  # non-empty lines in an entry
MAX_FIELD = 160  # characters in one 배경/접근/전후/결과 line
MAX_OTHERS = 3  # items in '- 그 밖에 — …'
PRIOR_CUES = ("기존|이전|없었|없는|없이|비어|하나로|통째로|수동|매번|모든|의존|섞여|달랐|않았|않고|지 않|못했|못하|막혀|따로|직접"
              "|반복|부족|느렸|느려|실패했|일찍|했는데|였는데|던 |뒤에|되어 있|돼 있|있었|있던")
PRIOR_RE = re.compile(PRIOR_CUES)
# descriptive past-state ending (~했고 ~였고 ~었습니다 ~했습니다 ...) combined with a condition/limitation word
PAST_END_RE = re.compile(r"(?:았|었|였|했|겼|졌|됐|렸|왔)(?:고|습니다|는데|으며|으나)")
CONDITION_RE = re.compile(r"(?<![가-힣])(?:그대로|이후)|(?:뿐|만)(?![가-힣])|채(?=워|로|\s|,|$)")
GOAL_END_RE = re.compile(r"(?:야\s*(?:했|하였|합)(?:습니다|다)|필요(?:했|하였|합)(?:습니다|다)|하려면|했어야\s*합니다)[.\s]*$|(?:어려운|힘든)\s*경우를\s*\S+\s*(?:했습니다|해야 했습니다)[.\s]*$")
NOTE_FACT_MIN = 15
NOTE_VERIFY_MIN = 10
NO_VERIFICATION = "없음"
NOTE_LABELS = ("이전 상태", "영향", "사실", "전달", "판단", "검증", "전후", "완료")  # 전달 = a fact the user stated outside git
NOTE_LINE = re.compile(r"^-\s*(이전 상태|영향|사실|전달|판단|검증|전후|완료)\s*:\s*(.*)$")
TITLE_MAX = 30  # characters after '· '
TITLE_CHAIN_RE = re.compile(r"\s(?:및|그리고)\s")
MECHANICS = ["정규식", "해시", "익명화", "하한", "상한값"]  # implementation jargon an outsider cannot follow
MECHANICS_RE = re.compile("|".join(map(re.escape, MECHANICS)))
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
        if LONE_DASH_RE.search(line):
            add("empty-cell", "a lone '-' is not content: write the value or drop the line/cell", number)
        for m in HEDGE_RE.finditer(line):
            add("hedging", f"hedging '{m.group()}': state what was done", number)
        for m in MECHANICS_RE.finditer(line):
            add("mechanics", f"implementation jargon '{m.group()}': say what it does for the reader in plain words", number)
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


def goal_only(text: str) -> bool:
    """True when a 배경/이전 상태 line names no prior state or only states the goal."""
    body = text.strip()
    if GOAL_END_RE.search(body):
        return True
    if PRIOR_RE.search(body):
        return False
    return not (PAST_END_RE.search(body) and CONDITION_RE.search(body))


def _norm(text: str) -> str:
    return re.sub(r"[\s.,·]+", "", text)


def _near_duplicate(a: str, b: str) -> bool:
    x, y = _norm(a), _norm(b)
    return x in y or y in x or SequenceMatcher(None, x, y).ratio() >= 0.8


def notes_problems(text: str, profile: Profile | None = None) -> dict:
    """Validate leader WORK NOTES: '### <목표·성과 단위>' items with 이전 상태 x1, 영향 x1, 사실+전달 x2+, 판단 x1+, 검증 x1.

    '- 전달:' lines carry facts the user stated outside git (real runs, comparisons); they count as facts."""
    problems: list[dict] = []

    def add(rule: str, detail: str, line: int = 0, item: str = "") -> None:
        problems.append({"kind": "notes", "token": rule, "item": item, "detail": detail, "line": line})

    items: list[dict] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("### "):
            items.append({"name": line[4:].strip(), "line": number, "rows": []})
        elif not items:
            add("format", "text before the first '### <목표·성과 단위>' item", number)
        elif m := NOTE_LINE.match(line):
            items[-1]["rows"].append((m.group(1), m.group(2).strip(), number))
        else:
            add("format", "line must be '- 이전 상태:', '- 영향:', '- 사실:', '- 전달:', '- 판단:', '- 검증:', "
                "'- 전후:' or '- 완료:'", number, items[-1]["name"])
    if not items:
        add("format", "notes need at least one '### <목표·성과 단위>' work item")
    if len(items) > MAX_ITEMS:
        add("too-many-items", f"notes have {len(items)} items; group sub-changes of the same goal/outcome into at most {MAX_ITEMS}")
    for it in items:
        name, rows = it["name"], it["rows"]
        if not name:
            add("format", "empty item heading", it["line"])
        by = {label: [r for r in rows if r[0] == label] for label in NOTE_LABELS}
        prior = by["이전 상태"]
        facts = sorted(by["사실"] + by["전달"], key=lambda r: r[2])
        for label in ("이전 상태", "영향", "검증"):
            if len(by[label]) != 1:
                add("prior-state" if label == "이전 상태" else f"{label}-count",
                    f"needs exactly one '- {label}:' (found {len(by[label])})", it["line"], name)
        if not by["판단"]:
            add("judgment-missing", "needs at least one '- 판단: <선택> — <이유>'", it["line"], name)
        for _, body, number in prior:
            if goal_only(body):
                add("prior-state-goal", "이전 상태 must describe what existed or was wrong before (기존/이전/없었/비어/하나로/통째로/"
                    "수동/매번/모든/의존/섞여 …, or a past-state ending with 만/뿐/그대로/채/이후), not restate the goal", number, name)
        if len(facts) < 2:
            add("facts-missing", f"needs at least 2 '- 사실:' or '- 전달:' lines (found {len(facts)})", it["line"], name)
        for i, (_, body, number) in enumerate(facts):
            if len(body) < NOTE_FACT_MIN:
                add("fact-short", f"사실/전달 must be at least {NOTE_FACT_MIN} characters of concrete detail", number, name)
            for _, other, _ in facts[:i]:
                if _near_duplicate(body, other):
                    add("fact-duplicate", "사실 repeats another 사실 of this item; give a different concrete fact", number, name)
                    break
        for label, body, number in rows:
            if not body:
                add("empty", f"'- {label}:' is empty", number, name)
            elif label == "판단" and " — " not in body:
                add("judgment-format", "판단 must be '<선택> — <이유>'", number, name)
            elif label == "전후" and "→" not in body:
                add("before-after-format", "전후 must be '<바뀌기 전> → <바뀐 뒤>'", number, name)
            elif label == "완료" and " — " not in body:
                add("done-format", "완료 must be '<끝난 기능·마일스톤·작업> — <무엇을 할 수 있게 됐는지>'", number, name)
            elif label == "검증" and body.strip() != NO_VERIFICATION and len(body) < NOTE_VERIFY_MIN:
                add("verify-vague", f"검증 must name concrete evidence (tests passed, a real run, a comparison; at least "
                    f"{NOTE_VERIFY_MIN} characters) or be exactly '{NO_VERIFICATION}'", number, name)
    for hit in findings(text, profile):
        token = hit["token"][:4] + "…" if hit["kind"] == "secret" else hit["token"]
        problems.append({"kind": hit["kind"], "token": token, "item": "", "detail": "leak: use feature words only",
                         "line": hit["line"]})
    summary = [{"feature": it["name"], "prior": sum(r[0] == "이전 상태" for r in it["rows"]),
                "facts": sum(r[0] in ("사실", "전달") for r in it["rows"]),
                "delivered": sum(r[0] == "전달" for r in it["rows"]),
                "verified": any(r[0] == "검증" and r[1].strip() != NO_VERIFICATION for r in it["rows"])} for it in items]
    return {"ok": not problems, "items": summary, "blocked": problems}


def parse_notes(text: str) -> list[dict]:
    """Saved notes -> [{'name', '검증', '완료'}] (keeps 결과 honest; 완료 lines demand a 완료 정리)."""
    items: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            items.append({"name": line[4:].strip(), "검증": "", "완료": []})
        elif items and (m := NOTE_LINE.match(line)) and m.group(1) in ("검증", "완료"):
            if m.group(1) == "검증":
                items[-1]["검증"] = m.group(2).strip()
            else:
                items[-1]["완료"].append(m.group(2).strip())
    return items


def _bullets(lines: list[str]) -> list[tuple[int, str]]:
    return [(offset, line.strip()) for offset, line in enumerate(lines, 1) if line.strip().startswith("- ")]


def _action_tail(bullet: str, labels: list[str]) -> str:
    text = re.sub(r"[.\s]+$", "", bullet[2:].strip())
    for label in labels:
        if text.startswith(label):
            return text[len(label):].strip()
    words = text.split()
    return " ".join(words[-2:]) if len(words) >= 3 else text  # unknown feature name: compare the last two words


def add_todo_problems(lines: list[str], number: int, labels: list[str], add) -> None:
    seen: dict[str, int] = {}
    for offset, bullet in _bullets(lines):
        tail = _action_tail(bullet, labels)
        if tail in seen:
            add("todo-repeat", f"다음 할 일 repeats the action '{tail}'; merge into one line (e.g. '세 기능의 …')",
                number + offset)
        seen.setdefault(tail, offset)


def _items(lines: list[str], number: int) -> list[tuple[str, int, list[str]]]:
    items: list[tuple[str, int, list[str]]] = []
    for offset, line in enumerate(lines, 1):
        if line.startswith("### "):
            items.append((line[4:].strip(), number + offset, []))
        elif items:
            items[-1][2].append(line)
    return items


def _match_notes(name: str, index: int, count: int, notes: list[dict]) -> dict | None:
    """Notes item for an entry item: by shared title text, else by position when both lists are the same length."""
    full, head = _norm(name), _norm(name.split(" — ")[0])
    for note in notes:
        title = _norm(note["name"])
        if title and (title in full or (head and head in title)):
            return note
    return notes[index] if len(notes) == count and index < len(notes) else None


def _top(lines: list[str]) -> list[tuple[int, str, str]]:
    """Top-level '- 필드 — 본문' lines of an item: (offset, field, body). Indented detail lines are not fields."""
    out = []
    for offset, line in enumerate(lines, 1):
        if line.startswith("- ") and (m := FIELD_LINE.match(line)):
            body = line.split("—", 1)[1].strip() if "—" in line else line.split(":", 1)[-1].strip()
            out.append((offset, m.group(1).strip(), body))
    return out


def _details(lines: list[str]) -> list[tuple[int, str]]:
    """Indented lines right under '- 접근 —' (until the next top-level line)."""
    out, inside = [], False
    for offset, line in enumerate(lines, 1):
        if line.startswith("- "):
            inside = FIELD_LINE.match(line) is not None and FIELD_LINE.match(line).group(1).strip() == "접근"
        elif inside and DETAIL_LINE.match(line):
            out.append((offset, line.strip()[2:].strip()))
    return out


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x.strip()]


def _unit_numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", "") + m.group(2) for m in UNIT_NUMBER_RE.finditer(text)}


def contract_problems(text: str, profile: Profile | None, run: dict | None, kind: str = "entry",
                      notes: str | None = None) -> list[dict]:
    problems = wording_problems(text, run)
    if kind != "entry":
        return problems

    def add(rule: str, detail: str, line: int = 0) -> None:
        problems.append({"kind": "contract", "token": rule, "detail": detail, "line": line})

    first = next(((n, ln) for n, ln in enumerate(text.splitlines(), 1) if ln.strip()), (1, ""))
    if not TITLE_RE.match(first[1]):
        add("title", "first line must be '# YYYY-MM-DD · 대표 성과' (range: '# YYYY-MM-DD~YYYY-MM-DD · 대표 성과')", first[0])
    else:
        outcome = first[1].split(" · ", 1)[1].strip()
        if len(outcome) > TITLE_MAX:
            add("title-length", f"title outcome is {len(outcome)} characters; keep it to {TITLE_MAX} or fewer", first[0])
        if TITLE_CHAIN_RE.search(outcome):
            add("title-chain", "title names one outcome: drop ' 및 ' / ' 그리고 ' and keep the most important result", first[0])
        if VAGUE_TITLE_RE.search(outcome.rstrip(".")):
            add("title-vague", "title must name the outcome with a verb ('~로 기록', '~를 막음'), not end in 개선/정리/강화",
                first[0])
    sections = _sections(text)
    titles = [t for t, _, _ in sections]
    for t, number, _ in sections:
        if t in REMOVED_SECTIONS:
            add(REMOVED_SECTIONS[t], f"'## {t}' is removed: decisions go in 접근, progress in the Notion progress page, "
                "portfolio value in 배경/접근/결과", number)
        elif t not in SECTIONS:
            add("section", f"unknown section '{t}'", number)
    known = [t for t in titles if t in SECTIONS]
    if len(set(known)) != len(known):
        add("section", "a section appears more than once")
    elif known != sorted(known, key=SECTIONS.index):
        add("section", "sections out of order: " + " > ".join(SECTIONS))
    for need in SECTIONS:
        if need in REQUIRED and need not in titles:
            add("section", f"missing required section '## {need}'")
    saved = parse_notes(notes) if notes else []
    completions = (run or {}).get("completions") or []
    noted_done = [d for n in saved for d in n["완료"]]
    if (completions or noted_done) and "완료 정리" not in titles:
        names = [c.get("target", "") for c in completions] + [d.split(" — ")[0] for d in noted_done]
        add("done-missing", "this run completed " + ", ".join(n for n in names if n) + ": add '## 완료 정리'")
    if not (completions or noted_done) and "완료 정리" in titles:
        add("done-unexpected", "nothing was completed in this run (no checked milestone, no '- 완료:' in the notes): "
            "drop '## 완료 정리'", next(n for t, n, _ in sections if t == "완료 정리"))
    non_empty = sum(1 for ln in text.splitlines() if ln.strip())
    if non_empty > MAX_LINES:
        add("length", f"entry has {non_empty} non-empty lines; keep it to {MAX_LINES} or fewer")
    names = {p["feature"] for p in (run or {}).get("progress", [])} | ({f.label for f in profile.features} if profile else set())
    allowed = names | set((run or {}).get("labels", []))
    labels = sorted(names, key=len, reverse=True)
    prose: list[tuple[int, str]] = []  # (line, text) of every sentence-bearing line, for endings/lists/duplicates
    for title, number, lines in sections:
        if title == "다음 할 일":
            add_todo_problems(lines, number, labels, add)
        if title == "핵심 요약" or title in REMOVED_SECTIONS:  # removed sections are still read for style
            prose += [(number + offset, b[2:].strip()) for offset, b in _bullets(lines)]
        if title == "완료 정리":
            headings = [name for name, _, _ in _items(lines, number)]
            for target in [c.get("target", "") for c in completions] + [d.split(" — ")[0].strip() for d in noted_done]:
                if target and not any(h.startswith(target) for h in headings):
                    add("done-missing", f"'## 완료 정리' needs '### {target} — 완료'", number)
            for name, at, body in _items(lines, number):
                if " — " not in name:
                    add("done-format", f"완료 정리 / {name}: heading must be '### <기능 또는 마일스톤> — 완료'", at)
                top = _top(body)
                if [f for _, f, _ in top] != DONE_FIELDS:
                    add("done-format", f"완료 정리 / {name}: needs '- 만든 것 —', '- 거쳐 온 길 —', '- 남은 한계 —' "
                        "once each, in that order", at)
                prose += [(at + off, b) for off, _, b in top]
        if title != "한 일":
            continue
        items = _items(lines, number)
        if not items:
            add("field", "한 일 needs at least one '### <기능> — <한 줄 성과>' item", number)
        if len(items) > MAX_ITEMS:
            add("too-many-items", f"한 일 has {len(items)} items; one problem per item, at most {MAX_ITEMS} "
                "(the rest goes in one '- 그 밖에 —' line)", items[MAX_ITEMS][1])
        for offset, line in enumerate(lines, 1):
            m = FIELD_LINE.match(line) if line.startswith("- ") else None
            if m and m.group(1).strip() in ITEM_FIELDS + ["전후"] and len(line.strip()) > MAX_FIELD:
                add("field-length", f"{m.group(1).strip()} line is {len(line.strip())} characters; keep it to "
                    f"{MAX_FIELD} or fewer and move details into the lines under 접근", number + offset)
            if m and m.group(1).strip() == "그 밖에":
                body = line.split("—", 1)[1] if "—" in line else ""
                count = len([x for x in re.split(r",\s|·", body) if x.strip()])
                if count > MAX_OTHERS:
                    add("others", f"'그 밖에' lists {count} items; keep it to {MAX_OTHERS} or fewer", number + offset)
        for index, (name, at, body) in enumerate(items):
            if " — " not in name:
                add("field", f"한 일 / {name}: heading must be '### <기능> — <한 줄 성과>'", at)
            elif allowed and name.split(" — ")[0].strip() not in allowed:
                add("item-feature", f"한 일 / {name}: start the heading with a feature name from the profile or this "
                    f"run ({', '.join(sorted(allowed))})", at)
            top = _top(body)
            fields = [f for _, f, _ in top if f in ITEM_FIELDS + ["전후"]]
            if fields not in ITEM_ORDERS:
                add("field", f"한 일 / {name}: needs '- 배경 —', '- 접근 —', (optional '- 전후 —'), '- 결과 —' once each, "
                    "in that order", at)
            for off, field_name, text_ in top:
                if field_name == "배경" and goal_only(text_):
                    add("problem-goal-only", f"한 일 / {name}: 배경 must state the prior state and what it caused "
                        "(기존/이전/없었/비어/하나로/통째로/수동/매번/모든/의존/섞여 …), not the goal", at)
                if field_name in ITEM_FIELDS + ["전후"]:
                    prose.append((at + off, text_))
            details = _details(body)
            if not DETAIL_MIN <= len(details) <= DETAIL_MAX:
                add("detail-count", f"한 일 / {name}: write {DETAIL_MIN}-{DETAIL_MAX} indented '  - ' lines under 접근, "
                    f"one concrete change each (found {len(details)})", at)
            for off, detail in details:
                if len(detail) > DETAIL_LEN:
                    add("detail-length", f"한 일 / {name}: a detail line holds one fact; keep it to {DETAIL_LEN} "
                        "characters", at + off)
                prose.append((at + off, detail))
            note = _match_notes(name, index, len(items), saved) if saved else None
            if note and note["검증"] == NO_VERIFICATION:
                for _, field_name, text_ in top:
                    if field_name == "결과" and VERIFIED_RE.search(text_):
                        add("unverified-claim", f"한 일 / {name}: the notes say 검증 없음, so 결과 must not use "
                            "확인/검증/통과; state what changed without claiming it was verified", at)
    for number, body in prose:
        if not SENTENCE_END_RE.search(body.strip()):
            add("noun-ending", "write a full 합쇼체 sentence ending in '~다' (no '~함', '~음', noun endings)", number)
        for sentence in _sentences(body):
            if sentence.count(",") >= LIST_CHAIN:
                add("list-chain", "a sentence lists four or more things: keep the one that matters or split the "
                    "details into lines under 접근", number)
                break
    seen: list[tuple[int, str]] = []
    for number, body in prose:
        for sentence in _sentences(body):
            key = _norm(sentence)
            if len(key) >= 15 and any(_near_duplicate(sentence, other) or
                                      SequenceMatcher(None, key, _norm(other)).ratio() >= DUP_RATIO
                                      for n, other in seen if n != number):
                add("duplicate-line", "this sentence repeats an earlier one: say each fact once "
                    "(common verification belongs once in 핵심 요약)", number)
                break
            seen.append((number, sentence))
    sources = _unit_numbers(notes or "")
    for number, line in enumerate(text.splitlines(), 1):
        if sum(1 for label in NOTE_FIELD_NAMES if label in line) >= 3:
            add("notes-leak", "the notes' field names are internal; describe what was done instead", number)
        for value in _unit_numbers(line) - sources:
            add("unsourced-number", f"'{value}' is not in the saved notes; copy counts only from the notes", number)
    return problems


def internal_term_problems(text: str, profile: Profile | None) -> list[dict]:
    """Profile 내부 용어 plus this plugin's defaults (a 공개 용어 entry switches a default off)."""
    out: list[dict] = []
    public = {t.lower() for t in (profile.public_terms if profile else [])}
    terms = [t for t in (profile.internal_terms if profile else []) if t]
    terms += [t for t in DEFAULT_INTERNAL if t.lower() not in public and t not in terms]
    for number, line in enumerate(text.splitlines(), 1):
        low = line.lower().replace("게이트웨이", "")
        for term in terms:
            if term.lower() in low:
                out.append({"kind": "internal-term", "token": term, "line": number,
                            "detail": "internal vocabulary: describe it in words an outsider understands"})
    return out


def check(text: str, profile: Profile | None, run: dict | None = None, kind: str = "entry",
          notes: str | None = None) -> dict:
    leaks = findings(text, profile)
    for hit in leaks:
        if hit["kind"] == "secret":
            hit["token"] = hit["token"][:4] + "…"
    blocked = leaks + internal_term_problems(text, profile) + contract_problems(text, profile, run, kind, notes)
    return {"ok": not blocked, "blocked": blocked}
