"""Confidence × impact rules. The same table is written out for agents in
skills/fde-director/references/rubric.md — keep them identical."""
from __future__ import annotations

CONF = ["추측", "가능성 높음", "확실"]
IMPACT = ["낮음", "중간", "높음"]

# (confidence, impact) -> bucket
MATRIX = {
    ("확실", "높음"): "ask", ("확실", "중간"): "ask", ("확실", "낮음"): "assume",
    ("가능성 높음", "높음"): "ask", ("가능성 높음", "중간"): "hold", ("가능성 높음", "낮음"): "assume",
    ("추측", "높음"): "ask", ("추측", "중간"): "assume", ("추측", "낮음"): "drop",
}

BUCKET_KO = {"ask": "지금 물어볼 질문", "hold": "보류", "assume": "가정으로 처리 제안", "drop": "버림",
             "propose": "인물에게 제안해 보기"}


def conf_norm(value: str | None) -> str:
    v = (value or "").strip().strip("[]")
    if v in CONF:
        return v
    aliases = {"certain": "확실", "high": "가능성 높음", "likely": "가능성 높음", "guess": "추측",
               "speculative": "추측", "확신": "확실", "높음": "가능성 높음", "가능성높음": "가능성 높음"}
    return aliases.get(v.lower(), "추측")


def impact_norm(value: str | None) -> str:
    v = (value or "").strip()
    if v in IMPACT:
        return v
    aliases = {"high": "높음", "mid": "중간", "medium": "중간", "low": "낮음", "상": "높음", "중": "중간", "하": "낮음"}
    return aliases.get(v.lower(), "중간")


def bucket(conf: str, impact: str) -> str:
    return MATRIX[(conf_norm(conf), impact_norm(impact))]


def gap(a: str | None, b: str | None) -> int:
    return abs(CONF.index(conf_norm(a)) - CONF.index(conf_norm(b)))


def mismatch(a: str | None, b: str | None) -> bool:
    """Two-step disagreement (확실 vs 추측) is shown to the user as ⚠."""
    return gap(a, b) >= 2


def rank_key(conf: str, impact: str, sources: int = 1) -> tuple:
    return (-IMPACT.index(impact_norm(impact)), -CONF.index(conf_norm(conf)), -sources)
