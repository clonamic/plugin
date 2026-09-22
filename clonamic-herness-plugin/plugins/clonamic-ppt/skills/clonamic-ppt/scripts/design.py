#!/usr/bin/env python3
"""Case-based visual pick. Validate and the specialist share these rules."""

from __future__ import annotations

import re

VISUALS = {
    "proof_grid",
    "hero_assertion",
    "metric_strip",
    "comparison_2col",
    "process_flow",
    "recommendation",
    "table_focus",
    "chart_focus",
    "quote_proof",
}

BLOCK_FOR_VISUAL = {
    "proof_grid": "bullets",
    "comparison_2col": "comparison",
    "process_flow": "process_steps",
    "recommendation": "recommendation",
    "table_focus": "table",
    "chart_focus": "chart",
    "quote_proof": "quote",
    "metric_strip": "metric_card",
    "hero_assertion": None,
}

_TWO = re.compile(
    r"(vs\.?|versus|대비|대조|아니면|둘 중|중 무엇|rather than|"
    r"instead of|A vs B|two (choices|options|paths))",
    re.I,
)
_TWO_KO = re.compile(r"(와|과)\s+.{2,24}\s+중")
_STEPS = re.compile(
    r"(단계|게이트|루프|순서|폐루프|then |after that|step |gate |loop |→|->)",
    re.I,
)
_LOOKUP = re.compile(
    r"(표|열\s|조건\s*[×x]|조회|기준표|column|lookup|\brows?\b|칸)",
    re.I,
)
_SERIES = re.compile(r"(시계열|막대|bar chart|line chart|series|categories)", re.I)
_PRINCIPLE = re.compile(r"(원칙|한 질문|principle|what this (class|lesson)|기억할 한 )", re.I)


def _show(slide: dict) -> list[str]:
    raw = slide.get("must_show") or slide.get("must_include") or []
    return [str(x).strip() for x in raw if str(x).strip()]


def _blob(slide: dict) -> str:
    parts = [
        slide.get("title") or "",
        slide.get("job") or "",
        slide.get("takeaway") or "",
        " ".join(_show(slide)),
    ]
    return " ".join(str(p) for p in parts)


def _n_numeric(items: list[str]) -> int:
    return sum(1 for t in items if re.search(r"\d|\b(one|two|three|four)\b", t, re.I))


def is_two_options(slide: dict) -> bool:
    blob = _blob(slide)
    if _TWO.search(blob) or _TWO_KO.search(blob):
        return True
    role = slide.get("role")
    if role == "comparison":
        return True
    return False


def is_ordered_steps(slide: dict) -> bool:
    show = _show(slide)
    if slide.get("role") == "process":
        return True
    if not (3 <= len(show) <= 6):
        return False
    numbered = sum(1 for t in show if re.match(r"^\s*\d", t))
    stepish = sum(1 for t in show if _STEPS.search(t))
    return numbered >= 3 or stepish >= 2


def is_lookup(slide: dict) -> bool:
    if slide.get("role") == "data" and _LOOKUP.search(_blob(slide)):
        return True
    return bool(_LOOKUP.search(_blob(slide))) and len(_show(slide)) >= 3


def recommend_visual(
    slide: dict,
    purpose: str,
    *,
    index: int,
    total: int,
    used: list[str] | None = None,
) -> tuple[str, str]:
    """Return (visual, reason). First matching case wins."""
    used = list(used or [])
    last = index >= total
    first = index == 1
    show = _show(slide)
    blob = _blob(slide)
    quotes_used = used.count("quote_proof")

    if last and purpose in {"decide", "pitch"}:
        return "recommendation", "last decide/pitch is the ask"
    if last and purpose == "teach":
        return "proof_grid", "teach last is four recall sentences"
    if last and purpose == "report":
        return "recommendation", "report last is the next action"

    if _SERIES.search(blob) and _n_numeric(show) >= 2:
        return "chart_focus", "user-supplied series"

    if is_two_options(slide):
        return "comparison_2col", "two alternatives on the same criteria"

    if is_ordered_steps(slide):
        return "process_flow", "3–6 ordered steps"

    if is_lookup(slide):
        return "table_focus", "lookup grid, not a story"

    if _n_numeric(show) >= 2:
        return "metric_strip", "two or more numeric facts"

    if 3 <= len(show) <= 6 and not is_ordered_steps(slide):
        return "proof_grid", "three or more named claims"

    if first and purpose == "teach" and quotes_used < 2:
        return "quote_proof", "teach opens on the principle"
    if first and purpose == "pitch" and _n_numeric(show) == 0 and quotes_used < 2 and _PRINCIPLE.search(blob):
        return "quote_proof", "pitch opens on the pain question"
    if first and _PRINCIPLE.search(blob) and quotes_used < 2 and not is_two_options(slide):
        return "quote_proof", "one principle, not two choices"

    if first and _n_numeric(show) == 1:
        return "hero_assertion", "one number frames the deck"

    if first:
        return "hero_assertion", "opening assertion"

    if len(show) >= 2:
        return "proof_grid", "mid-deck named claims, not a second hero"

    return "hero_assertion", "single leftover assertion"


def visual_allowed(chosen: str, recommended: str) -> bool:
    if chosen == recommended:
        return True
    aliases = {
        "hero_assertion": {"quote_proof", "metric_strip"},
        "quote_proof": {"hero_assertion"},
        "proof_grid": {"table_focus", "metric_strip"},
        "table_focus": {"proof_grid"},
        "metric_strip": {"hero_assertion", "proof_grid"},
    }
    if recommended == "comparison_2col":
        return chosen == "comparison_2col"
    if recommended == "process_flow":
        return chosen == "process_flow"
    if recommended == "recommendation":
        return chosen == "recommendation"
    if recommended == "chart_focus":
        return chosen == "chart_focus"
    return chosen in aliases.get(recommended, set())


def spec_block_matches_visual(spec: dict, visual: str) -> bool:
    types = [b.get("type") for b in (spec.get("content_blocks") or [])]
    need = BLOCK_FOR_VISUAL.get(visual)
    if visual == "hero_assertion":
        return True
    if visual == "metric_strip":
        return types.count("metric_card") >= 2
    if visual == "proof_grid":
        return "bullets" in types
    if need:
        return need in types
    return True
