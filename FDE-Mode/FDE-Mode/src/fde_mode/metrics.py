"""Pattern metrics. Code counts, agents interpret.

Persona metrics feed the persona division (language, emotion, routine, decision
style). Interviewer metrics feed the interviewer coach ("what did I miss").
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from fde_mode import db, lexicon as L
from fde_mode.state import Ctx
from fde_mode.util import write_json

AREAS = ["문제", "현재방식", "사용맥락", "여정", "데이터", "성공기준", "예외", "말투", "우선순위", "이해관계자"]


def _utts(ctx: Ctx, upto_round: str | None = None) -> list[dict]:
    rows = db.rows(ctx.conn, "SELECT * FROM utterances WHERE speaker IN ('I','P') ORDER BY seq")
    if upto_round:
        rows = [r for r in rows if r["round"] <= upto_round]
    for r in rows:
        r["tags"] = json.loads(r.get("tags") or "[]")
    return rows


def persona_metrics(utts: list[dict]) -> dict[str, Any]:
    P = [u for u in utts if u["speaker"] == "P"]
    by_area: dict[str, list[dict]] = defaultdict(list)
    for u in P:
        by_area[u.get("area") or "미분류"].append(u)
    topic = {}
    for area, items in by_area.items():
        topic[area] = {
            "count": len(items),
            "first_round": min(i["round"] for i in items),
            "last_round": max(i["round"] for i in items),
            "avg_len": round(sum(len(i["text"]) for i in items) / len(items), 1),
            "intensifiers": sum(L.count_markers(i["text"], L.INTENSIFIERS) for i in items),
            "vague": sum(L.count_markers(i["text"], L.VAGUE) for i in items),
            "avoid": sum(L.count_markers(i["text"], L.AVOID) for i in items),
            "specificity": round(sum(L.specificity(i["text"]) for i in items) / len(items), 3),
        }
    words = Counter()
    for u in P:
        for w in L.INTENSIFIERS + L.VAGUE + L.AVOID:
            c = u["text"].count(w)
            if c:
                words[w] += c
    time_mentions = []
    for u in P:
        hits = [w for w in L.TIME_WORDS if w in u["text"]] + L.CLOCK.findall(u["text"])
        if hits:
            time_mentions.append({"id": u["id"], "hits": sorted(set(hits))})
    others = Counter()
    for u in P:
        for w in L.people(u["text"]):
            others[w] += 1  # once per utterance and person
    corrections = [u["id"] for u in P if L.count_markers(u["text"], L.CORRECTION)]
    hesitations = [u["id"] for u in P if L.count_markers(u["text"], L.HESITATION) >= 2]
    return {
        "utterances": len(P),
        "total_chars": sum(len(u["text"]) for u in P),
        "avg_len": round(sum(len(u["text"]) for u in P) / max(1, len(P)), 1),
        "by_area": topic,
        "marker_words": dict(words.most_common(25)),
        "time_mentions": time_mentions,
        "others_mentioned": dict(others.most_common(15)),
        "corrections": corrections,
        "hesitations": hesitations,
        "emoji_or_laugh": sum(1 for u in P if any(x in u["text"] for x in ("ㅋㅋ", "ㅎㅎ", "^^", "😂", "😊", "ㅠ"))),
    }


def interviewer_metrics(utts: list[dict]) -> dict[str, Any]:
    I = [u for u in utts if u["speaker"] == "I"]
    qtypes = Counter((u.get("qtype") or L.question_type(u["text"])) for u in I)
    coverage = Counter(u.get("area") or "미분류" for u in I)
    for a in AREAS:
        coverage.setdefault(a, 0)
    # answer specificity by the question type that triggered it
    spec_by_q: dict[str, list[float]] = defaultdict(list)
    follow_total = follow_done = 0
    for i, u in enumerate(utts):
        if u["speaker"] != "I":
            continue
        answer = next((x for x in utts[i + 1:] if x["speaker"] == "P"), None)
        if answer:
            spec_by_q[u.get("qtype") or L.question_type(u["text"])].append(L.specificity(answer["text"]))
    for i, u in enumerate(utts):
        if u["speaker"] != "P" or not L.count_markers(u["text"], L.VAGUE + L.AVOID):
            continue
        nxt = next((x for x in utts[i + 1:] if x["speaker"] == "I"), None)
        if nxt is None:
            continue
        follow_total += 1
        same_area = (nxt.get("area") and nxt.get("area") == u.get("area"))
        echoes = any(w in nxt["text"] for w in L.VAGUE + L.AVOID if w in u["text"])
        if same_area or echoes or "구체" in nxt["text"] or "예를 들" in nxt["text"]:
            follow_done += 1
    solution_first = [u["id"] for u in I if L.count_markers(u["text"], L.SOLUTION_WORDS) and
                      L.question_type(u["text"]) in ("leading", "closed", "choice")]
    i_chars = sum(len(u["text"]) for u in I)
    p_chars = sum(len(u["text"]) for u in utts if u["speaker"] == "P")
    streak = 0
    longest = (None, 0)
    prev_area = None
    for u in I:
        a = u.get("area") or "미분류"
        streak = streak + 1 if a == prev_area else 1
        prev_area = a
        if streak > longest[1]:
            longest = (a, streak)
    return {
        "questions": len(I),
        "qtype": dict(qtypes),
        "coverage": dict(coverage),
        "untouched_areas": [a for a in AREAS if coverage.get(a, 0) == 0],
        "followup_rate": round(follow_done / follow_total, 2) if follow_total else None,
        "followup_checked": follow_total,
        "talk_ratio_i_to_p": round(i_chars / max(1, p_chars), 2),
        "solution_first": solution_first,
        "answer_specificity_by_qtype": {k: round(sum(v) / len(v), 3) for k, v in spec_by_q.items() if v},
        "longest_same_area_streak": {"area": longest[0], "length": longest[1]},
        "recent5_areas": [u.get("area") or "미분류" for u in I[-5:]],
    }


def compute(ctx: Ctx, round_id: str, out_path=None) -> dict[str, Any]:
    utts = _utts(ctx)
    data = {"round": round_id, "persona": persona_metrics(utts), "interviewer": interviewer_metrics(utts)}
    for scope in ("persona", "interviewer"):
        for name, value in data[scope].items():
            db.upsert(ctx.conn, "metrics", {"round": round_id, "scope": scope, "name": name,
                                            "value": json.dumps(value, ensure_ascii=False)},
                      key=("round", "scope", "name"))
    if out_path:
        write_json(out_path, data)
    return data
