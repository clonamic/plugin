"""AI티 측정기 — deterministic signals that a Korean reply sounds generic or machine-made.

The AI-tell checker (agent) uses this to get reproducible numbers; its own judgement adds what a lexicon cannot
see (genericness, voice drift, answers that would fit any business). Honest disclosure that the bot is a bot is
never counted: hiding that is not the goal. The goal is replies that sound like they were written for this person.

Input: a list of replies (strings) or [{"input": ..., "output": ..., "provider": ...}].
Output: per-reply hits and a 0–100 score, plus cross-reply measures (template repetition, opener/closing rates).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fde_mode.util import ngrams


@dataclass(frozen=True)
class Cat:
    key: str
    ko: str
    weight: int
    where: str            # "start" (first 40 chars), "end" (last 60 chars) or "any"
    patterns: tuple[str, ...]
    major: bool = False   # one hit makes the reply FAIL


CATS: tuple[Cat, ...] = (
    Cat("opener", "상투 서두", 3, "start", (
        r"좋은\s*질문", r"^\s*물론(이죠|입니다|이에요)", r"^\s*네[,!.]?\s*(알겠습니다|물론|좋습니다|맞습니다)",
        r"궁금하셨군요", r"문의(해\s*주셔서|주셔서)\s*감사", r"^\s*안녕하세요[!.,]?\s*(저는|무엇을\s*도와)",
        r"말씀(하신|해\s*주신)\s*(내용|부분)", r"^\s*(아주|정말)\s*(좋은|훌륭한)")),
    Cat("closing", "상투 맺음", 3, "end", (
        r"더\s*(궁금한|필요한|알고\s*싶은)\s*(점|사항|것)", r"언제든(지|요)?\s*(말씀|물어|문의|편하게|연락)",
        r"도움이\s*(되셨|되었|됐)(길|으면|기를)", r"좋은\s*하루\s*(되세요|보내세요)", r"추가로\s*(궁금|필요)",
        r"(편하게|부담\s*없이)\s*(말씀|물어)", r"감사합니다[!.]?\s*$")),
    Cat("translationese", "번역투·문어체", 1, "any", (
        r"하는\s*것이\s*가능합니다", r"에\s*대(해|한)서?", r"를\s*통(해|하여)", r"다양한", r"효율적(으로|인)",
        r"최적(의|화)", r"제공(해\s*드립니다|합니다|해\s*드려요)", r"진행(해\s*드리|하)겠습니다", r"(^|\s)해당\s",
        r"확인\s*부탁드립니다", r"이용하실\s*수\s*있습니다", r"하시기\s*바랍니다", r"에\s*있어서", r"으?로\s*인해",
        r"것으로\s*보입니다", r"필요가\s*있습니다")),
    Cat("markdown", "서식 기호 노출", 4, "any", (
        r"\*\*[^*\n]+\*\*", r"(?m)^\s{0,3}#{1,6}\s", r"(?m)^\s*\|.*\|\s*$", r"```", r"(?m)^\s*[-*]\s+\*\*",
        r"(?m)^\s*-{3,}\s*$", r"\[[^\]]+\]\([^)]+\)"), major=True),
    Cat("disclaimer", "불필요한 고지", 4, "any", (
        r"(저는|제가)\s*AI(라서|이기\s*때문에|로서|이므로)", r"인공지능(이라서|으로서|이기\s*때문에)",
        r"정확하지\s*않을\s*수\s*있", r"실시간\s*정보(를|에)\s*(알|접근)", r"제\s*지식(은|으로는)",
        r"학습\s*데이터"), major=True),
    Cat("hedge", "얼버무림", 1, "any", (
        r"수\s*있습니다", r"참고하(시기|세요)", r"일반적으로", r"경우에\s*따라", r"것\s*같습니다", r"가능성이\s*있")),
    Cat("apology", "불필요한 사과", 2, "any", (
        r"죄송합니다만", r"불편을\s*드려", r"양해\s*(부탁|바랍)", r"혼란을\s*드려")),
    Cat("enthusiasm", "과장된 호응", 2, "any", (
        r"물론이죠", r"그럼요[!]", r"정말\s*좋(은|네요)", r"훌륭(한|해요|합니다)", r"완벽(한|해요|합니다)",
        r"멋진\s*(질문|생각|계획)", r"!{2,}")),
    Cat("loanword", "어색한 외래어", 1, "any", (
        r"케어", r"프로세스", r"솔루션", r"니즈", r"인사이트", r"서포트", r"퀄리티", r"컨텐츠|콘텐츠",
        r"커스터마이(징|즈)", r"옵션을\s*제공", r"리마인드", r"피드백을\s*주시")),
)

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕‼⁉〰〽]")
LIST_LINE = re.compile(r"(?m)^\s*(?:[-•*·▪︎]|\d+[.)]|[①-⑳])\s+\S")
SENT_SPLIT = re.compile(r"(?<=[.!?。？！])\s+|\n+")


def _norm(r: Any) -> dict[str, str]:
    if isinstance(r, str):
        return {"input": "", "output": r, "provider": ""}
    if isinstance(r, dict):
        out = r.get("output") or r.get("reply") or r.get("text") or ""
        if isinstance(out, list):
            out = "\n".join(str(x) for x in out)
        return {"input": str(r.get("input") or ""), "output": str(out), "provider": str(r.get("provider") or "")}
    return {"input": "", "output": str(r), "provider": ""}


def scan(text: str, allow: tuple[str, ...] = ()) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    t = text or ""
    for c in CATS:
        region = t[:40] if c.where == "start" else t[-60:] if c.where == "end" else t
        n = 0
        for pat in c.patterns:
            for m in re.finditer(pat, region):
                frag = m.group(0).strip()
                if any(a and a in frag for a in allow):
                    continue
                hits.append({"cat": c.key, "ko": c.ko, "match": frag})
                n += 1
                if n >= 3:
                    break
            if n >= 3:
                break
    lines = LIST_LINE.findall(t)
    if len(lines) >= 3 and len(t) < 400:
        hits.append({"cat": "structure", "ko": "짧은 답의 과잉 목록", "match": f"목록 {len(lines)}줄 / {len(t)}자"})
    return hits


def _penalty(hits: list[dict[str, str]]) -> int:
    w = {c.key: c.weight for c in CATS}
    w["structure"] = 2
    per: dict[str, int] = {}
    for h in hits:
        per[h["cat"]] = min(per.get(h["cat"], 0) + 1, 2)  # a category counts at most twice per reply
    return sum(w.get(k, 1) * n for k, n in per.items())


def _first_last(text: str) -> tuple[str, str]:
    parts = [p.strip() for p in SENT_SPLIT.split(text or "") if p.strip()]
    if not parts:
        return "", ""
    return parts[0], parts[-1]


def _sim(a: str, b: str) -> float:
    A, B = set(ngrams(a, 3)), set(ngrams(b, 3))
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def measure(replies: list[Any], allow: list[str] | None = None) -> dict[str, Any]:
    allow_t = tuple(allow or ())
    items = [_norm(r) for r in replies]
    per = []
    for i, it in enumerate(items, 1):
        text = it["output"]
        hits = scan(text, allow_t)
        pen = _penalty(hits)
        major = sorted({h["cat"] for h in hits if any(c.key == h["cat"] and c.major for c in CATS)})
        both_ends = any(h["cat"] == "opener" for h in hits) and any(h["cat"] == "closing" for h in hits)
        emoji = len(EMOJI.findall(text))
        verdict = "FAIL" if (major or both_ends or pen >= 8) else "PASS"
        per.append({"n": i, "input": it["input"][:80], "chars": len(text), "emoji": emoji, "provider": it["provider"],
                    "hits": hits, "penalty": pen, "score": max(0, 100 - 8 * pen), "verdict": verdict,
                    "reason": ("서식/고지 노출: " + ", ".join(major)) if major else
                              ("서두·맺음 상투구 동시" if both_ends else ("감점 누적" if pen >= 8 else ""))})
    # Template repetition: replies to different inputs that open or close the same way.
    firsts = [_first_last(it["output"]) for it in items]
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i]["input"] and items[i]["input"] == items[j]["input"]:
                continue
            s_open = _sim(firsts[i][0], firsts[j][0])
            s_close = _sim(firsts[i][1], firsts[j][1])
            if max(s_open, s_close) >= 0.6:
                pairs.append({"a": i + 1, "b": j + 1, "open": round(s_open, 2), "close": round(s_close, 2)})
    n = len(items) or 1
    rate = lambda cat: round(sum(1 for p in per if any(h["cat"] == cat for h in p["hits"])) / n, 2)
    base = sum(p["score"] for p in per) / n if per else 100.0
    template_pen = min(30, 5 * len(pairs))
    by_provider: dict[str, list[int]] = {}
    for p in per:
        if p["provider"]:
            by_provider.setdefault(p["provider"], []).append(p["score"])
    return {
        "replies": len(items),
        "score": round(max(0.0, base - template_pen), 1),
        "fail": sum(1 for p in per if p["verdict"] == "FAIL"),
        "rates": {"opener": rate("opener"), "closing": rate("closing"), "markdown": rate("markdown"),
                  "disclaimer": rate("disclaimer"), "translationese": rate("translationese"),
                  "enthusiasm": rate("enthusiasm")},
        "avg_chars": round(sum(p["chars"] for p in per) / n, 1),
        "emoji_per_reply": round(sum(p["emoji"] for p in per) / n, 2),
        "template_pairs": pairs,
        "by_provider": {k: round(sum(v) / len(v), 1) for k, v in by_provider.items()},
        "per_reply": per,
        "note": "어휘 신호만 잰 값이다. 일반론·말투 흔들림·이 사람에게 맞는지는 검사관이 직접 판단한다.",
    }
