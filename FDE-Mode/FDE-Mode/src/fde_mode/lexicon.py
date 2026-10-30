"""Korean surface markers used by the pattern metrics.

Counting is done by code (LLMs miscount); interpretation is done by the
persona-division agents, who receive these numbers as evidence.
Lists are deliberately conservative: a false hit inflates a metric that an
agent may then over-interpret.
"""
from __future__ import annotations

import re

INTENSIFIERS = ["진짜", "정말", "너무", "완전", "항상", "맨날", "절대", "매우", "엄청", "되게", "무조건",
                "꼭", "반드시", "제일", "가장", "엄청나게", "늘", "언제나", "매번"]

VAGUE = ["적당히", "알아서", "대충", "어느 정도", "어느정도", "웬만하면", "나름", "약간", "뭔가", "그런 거",
         "그런거", "이런 거", "이런거", "등등", "같은 거", "같은거", "편하게", "쉽게", "깔끔하게", "똑똑하게",
         "빠르게", "간단하게", "적절히", "잘 좀", "좀 더", "그냥"]

AVOID = ["딱히", "글쎄", "잘 모르겠", "모르겠어요", "모르겠네요", "생각 안 해봤", "생각해본 적", "별로",
         "뭐 그냥", "그건 좀", "나중에", "상관없", "아무거나", "그때그때", "케이스 바이 케이스"]

CORRECTION = ["아니 그게", "그게 아니라", "아니요 그게", "다시 말하면", "정확히는", "정확히 말하면", "아 근데",
              "아 맞다", "말을 바꾸면", "정정", "아니 아니", "그 말이 아니라"]

HESITATION = ["음", "어…", "어...", "그러니까", "뭐랄까", "저기", "아마", "것 같아요", "것 같은데", "...", "…"]

EXAMPLE_MARKERS = ["예를 들어", "예를 들면", "예컨대", "가령", "이를테면", "예시로", "한 번은", "지난번에",
                   "저번에", "어제", "지난주"]

TIME_WORDS = ["새벽", "아침", "오전", "점심", "오후", "저녁", "밤", "출근", "퇴근", "주말", "평일", "월요일",
              "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "매일", "매주", "매달", "매월",
              "월말", "월초", "분기", "시즌", "성수기", "비수기", "명절", "방학", "하루", "일주일",
              "한 달", "한달", "격주", "가끔", "자주", "수시로"]

SOLUTION_WORDS = ["기능", "알림", "앱", "버튼", "자동으로", "봇이", "챗봇이", "해 드리면", "해드리면",
                  "하면 어떨까요", "추천해", "만들어 드", "보내 드", "보내드"]

# Other people: family, work roles and titles every field uses, and any honorific title ("〈직함〉님", HONORIFIC).
# An industry's own roles are learned from the conversation (glossary), never listed here.
OTHERS_WORDS = ["남편", "아내", "부인", "아들", "딸", "엄마", "아빠", "어머니", "아버지", "팀장",
                "대표", "직원", "동료", "고객", "손님", "회원", "주민", "선생님", "학생"]
def people(text: str) -> set[str]:
    """Other people named in one utterance, each once: "팀장님" is one person, not "팀장" + "팀장님"."""
    hon = set(HONORIFIC.findall(text or ""))
    return hon | {w for w in OTHERS_WORDS if w in (text or "") and w + "님" not in hon and w not in hon}


HONORIFIC = re.compile(r"(?<![가-힣])[가-힣]{1,5}님(?=[이은는을를께도의과와랑만한하에들,.?!~\s]|$)")

NUM_UNIT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:원|만원|천원|개|명|건|시|분|초|회|번|kg|g|톤|박스|상자|%|퍼센트|"
                      r"평|가구|마리|일|주|달|개월|년|km|m|리터|L)")
CLOCK = re.compile(r"\b\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?|\b\d{1,2}:\d{2}\b")

LEADING_PATTERNS = [
    re.compile(p) for p in (
        r"(좋|낫|편하|괜찮)(겠|지 않|잖)[^?？]*[?？]",
        r"(하시|이시|쓰시|되시)죠\s*[?？]",
        r"죠\s*[?？]\s*$",
        r"지 않(나요|을까요|으세요|습니까)\s*[?？]",
        r"당연히",
        r"(필요하|원하)시(겠|잖)",
    )
]
CHOICE_PATTERNS = [re.compile(p) for p in (r"아니면", r"\b또는\b", r"중에(서)?\s", r"\b(A|B)\b.*(A|B)", r"어느 (쪽|것|게)")]
OPEN_WORDS = ["무엇", "뭐가", "뭘", "어떻게", "왜", "어떤", "얼마나", "언제", "어디", "누가", "누구", "몇",
              "어떠", "어땠", "말씀해", "설명해", "얘기해", "알려주"]


def count_markers(text: str, words: list[str]) -> int:
    t = text or ""
    return sum(t.count(w) for w in words)


def question_type(text: str) -> str:
    """Interviewer question type: leading > choice > open > closed > statement."""
    t = (text or "").strip()
    if not t:
        return "statement"
    is_q = "?" in t or "？" in t or t.endswith(("까요", "나요", "가요", "세요", "습니까", "죠", "을까", "는지"))
    if any(p.search(t) for p in LEADING_PATTERNS):
        return "leading"
    if any(p.search(t) for p in CHOICE_PATTERNS) and is_q:
        return "choice"
    if any(w in t for w in OPEN_WORDS):
        return "open"
    if is_q:
        return "closed"
    return "statement"


def specificity(text: str) -> float:
    """0..1 rough concreteness: numbers, clock times, time words, examples, people/proper nouns."""
    t = text or ""
    if not t.strip():
        return 0.0
    hits = len(NUM_UNIT.findall(t)) * 2 + len(CLOCK.findall(t)) * 2
    hits += count_markers(t, TIME_WORDS) + count_markers(t, EXAMPLE_MARKERS) * 2 + len(people(t))
    hits += len(re.findall(r"[\"“'‘][^\"”'’]{2,30}[\"”'’]", t))  # quoted names/items
    length_norm = max(1.0, len(t) / 60.0)
    return round(min(1.0, hits / (3.0 * length_norm)), 3)
