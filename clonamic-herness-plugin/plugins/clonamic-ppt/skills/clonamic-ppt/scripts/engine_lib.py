#!/usr/bin/env python3
"""Shared theme, grid, measurement, and title heuristics."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SLIDE_W = 13.333
SLIDE_H = 7.5
SAFE_LEFT = 0.56
SAFE_RIGHT = 0.56
SAFE_TOP = 0.42
SAFE_BOTTOM = 0.34
HEADER_H = 0.78
FOOTER_H = 0.28

_TYPE = {
    "title_hero": 28,
    "title_standard": 22,
    "subtitle": 14,
    "body": 15,
    "body_small": 12,
    "metric": 28,
    "metric_label": 12,
    "footnote": 8,
    "min_title": 20,
    "min_body": 11,
}

THEMES: dict[str, dict] = {
    "clarity-neutral": {
        "id": "clarity-neutral",
        **_TYPE,
        "canvas": "FFFFFF",
        "surface": "F7F8FA",
        "surface_muted": "EEF1F4",
        "text_primary": "111827",
        "text_secondary": "59636E",
        "text_inverse": "FFFFFF",
        "border": "EEF1F4",
        "accent": "2F6FED",
        "accent_dark": "174EA6",
        "heading_font": "Apple SD Gothic Neo",
        "body_font": "AppleGothic",
        "radius": 0.10,
        "accent_bar": True,
        "card_rail": False,
        "title_rule": "none",
        "number_proofs": True,
        "proof_dots": False,
        "ask_fullbleed": False,
        "process_layout": "row",
        "process_mark": "index",
        "compare_vs": True,
    },
    "boardroom-pine": {
        "id": "boardroom-pine",
        **_TYPE,
        "canvas": "F4F1EA",
        "surface": "FFFCF6",
        "surface_muted": "E7E2D6",
        "text_primary": "171412",
        "text_secondary": "5C564C",
        "text_inverse": "F4F1EA",
        "border": "D8D2C4",
        "accent": "1F4E3D",
        "accent_dark": "16382C",
        "heading_font": "Apple SD Gothic Neo",
        "body_font": "AppleGothic",
        "radius": 0.04,
        "accent_bar": False,
        "card_rail": True,
        "title_rule": "left",
        "number_proofs": False,
        "proof_dots": False,
        "ask_fullbleed": False,
        "process_layout": "row",
        "process_mark": "disc",
        "compare_vs": True,
    },
    "ink-ask": {
        "id": "ink-ask",
        **_TYPE,
        "canvas": "EFEAE1",
        "surface": "F7F3EB",
        "surface_muted": "E4DCCE",
        "text_primary": "171412",
        "text_secondary": "5A5348",
        "text_inverse": "EFEAE1",
        "border": "C9C0B0",
        "accent": "7C6542",
        "accent_dark": "171412",
        "heading_font": "AppleMyungjo",
        "body_font": "AppleGothic",
        "radius": 0.0,
        "accent_bar": False,
        "card_rail": False,
        "title_rule": "none",
        "number_proofs": False,
        "proof_dots": False,
        "ask_fullbleed": False,
        "process_layout": "row",
        "process_mark": "none",
        "compare_vs": True,
    },
    "studio-lesson": {
        "id": "studio-lesson",
        **_TYPE,
        "canvas": "FFF8F3",
        "surface": "FFF1E6",
        "surface_muted": "F3E0D0",
        "text_primary": "2A211C",
        "text_secondary": "6B5A4E",
        "text_inverse": "FFFFFF",
        "border": "EBD4C2",
        "accent": "C45C26",
        "accent_dark": "9A4519",
        "heading_font": "Apple SD Gothic Neo",
        "body_font": "AppleGothic",
        "radius": 0.10,
        "accent_bar": False,
        "card_rail": False,
        "title_rule": "none",
        "number_proofs": True,
        "proof_dots": True,
        "ask_fullbleed": False,
        "process_layout": "stack",
        "process_mark": "dot",
        "compare_vs": True,
    },
    "logbook": {
        "id": "logbook",
        **_TYPE,
        "canvas": "EDF0F3",
        "surface": "FFFFFF",
        "surface_muted": "E2E6EA",
        "text_primary": "2B3138",
        "text_secondary": "5A636C",
        "text_inverse": "EDF0F3",
        "border": "C5CCD3",
        "accent": "0D70B3",
        "accent_dark": "2B3138",
        "heading_font": "AppleGothic",
        "body_font": "AppleGothic",
        "radius": 0.0,
        "accent_bar": False,
        "card_rail": False,
        "title_rule": "underline",
        "number_proofs": False,
        "proof_dots": False,
        "ask_fullbleed": False,
        "process_layout": "row",
        "process_mark": "index",
        "compare_vs": False,
    },
}

PURPOSE_THEME = {
    "decide": "boardroom-pine",
    "persuade": "boardroom-pine",
    "inform": "boardroom-pine",
    "pitch": "ink-ask",
    "teach": "studio-lesson",
    "report": "logbook",
}

THEME: dict = dict(THEMES["boardroom-pine"])


def resolve_theme_id(specs: dict | None = None, brief: dict | None = None, theme_id: str | None = None) -> str:
    if theme_id and theme_id in THEMES:
        return theme_id
    src = specs or {}
    if src.get("theme_id") in THEMES:
        return src["theme_id"]
    purpose = src.get("purpose") or (brief or {}).get("purpose")
    if purpose in PURPOSE_THEME:
        return PURPOSE_THEME[purpose]
    return "boardroom-pine"


def apply_theme(theme_id: str | None = None, *, specs: dict | None = None, brief: dict | None = None) -> dict:
    tid = resolve_theme_id(specs, brief, theme_id)
    THEME.clear()
    THEME.update(THEMES[tid])
    return THEME

TOPIC_TITLES = {
    "시장 분석",
    "솔루션",
    "개요",
    "현황",
    "다음 단계",
    "소개",
    "목차",
    "요약",
    "결론",
    "overview",
    "solution",
    "next steps",
    "introduction",
    "analysis",
    "agenda",
    "summary",
    "conclusion",
    "background",
    "problem",
    "opportunity",
}

BANNED_DESC_WORDS = (
    "ppt",
    "pptx",
    "slides",
    "slide",
    "deck",
    "presentation",
    "powerpoint",
)


@dataclass
class BBox:
    x: float
    y: float
    w: float
    h: float

    def right(self) -> float:
        return self.x + self.w

    def bottom(self) -> float:
        return self.y + self.h

    def as_dict(self) -> dict[str, Any]:
        return {"x": round(self.x, 3), "y": round(self.y, 3), "w": round(self.w, 3), "h": round(self.h, 3), "unit": "in"}


class Grid:
    def __init__(self) -> None:
        self.slide_w = SLIDE_W
        self.slide_h = SLIDE_H
        self.left = SAFE_LEFT
        self.right = SAFE_RIGHT
        self.top = 1.20
        self.bottom = 0.62
        self.cols = 12
        self.rows = 10
        self.gutter_x = 0.20
        self.gutter_y = 0.16

    @property
    def usable_w(self) -> float:
        return self.slide_w - self.left - self.right

    @property
    def usable_h(self) -> float:
        return self.slide_h - self.top - self.bottom

    @property
    def col_w(self) -> float:
        return (self.usable_w - self.gutter_x * (self.cols - 1)) / self.cols

    @property
    def row_h(self) -> float:
        return (self.usable_h - self.gutter_y * (self.rows - 1)) / self.rows

    def bbox(self, col: int, row: int, col_span: int, row_span: int) -> BBox:
        x = self.left + col * (self.col_w + self.gutter_x)
        y = self.top + row * (self.row_h + self.gutter_y)
        w = col_span * self.col_w + (col_span - 1) * self.gutter_x
        h = row_span * self.row_h + (row_span - 1) * self.gutter_y
        return BBox(x=x, y=y, w=w, h=h)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def estimate_text_height_in(
    text: str,
    box_width_in: float,
    font_size_pt: float,
    line_height: float = 1.2,
    language: str = "ko",
    padding: float = 0.10,
) -> float:
    if not text:
        return padding
    cjk = language.lower().startswith(("ko", "ja", "zh"))
    char_factor = 0.95 if cjk else 0.52
    chars_per_line = max(1.0, (box_width_in * 72) / (font_size_pt * char_factor))
    # Heading-size CJK is ~1em; the 1.75 body factor was inflating quote cards.
    cjk_w = 1.20 if font_size_pt >= 20 else 1.75
    effective = sum(1.0 if ord(ch) < 128 else cjk_w for ch in text)
    # honor explicit newlines
    extra_breaks = text.count("\n")
    line_count = max(1, math.ceil(effective / chars_per_line) + extra_breaks)
    return (line_count * font_size_pt * line_height / 72.0) + padding


def is_topic_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if t.lower() in TOPIC_TITLES or t in TOPIC_TITLES:
        return True
    # very short noun-only labels without a predicate-like ending
    if len(t) <= 6 and not re.search(r"(다|요|까|인가|한다|이다)$", t):
        if " " not in t and not re.search(r"[.!?]", t):
            # Korean 2-4 char labels like 현황, 소개
            if re.fullmatch(r"[가-힣]{2,4}", t):
                return True
    if re.fullmatch(r"[A-Za-z][A-Za-z /-]{0,18}", t) and " " in t and not re.search(
        r"\b(is|are|will|must|should|can|cannot|don't|not)\b", t, re.I
    ):
        # "Market Analysis", "Next Steps"
        if t.lower() in TOPIC_TITLES or all(w.istitle() or w.isupper() for w in t.split()):
            words = t.split()
            if 1 <= len(words) <= 3:
                return True
    return False


def description_has_banned_words(text: str) -> list[str]:
    # The product name contains "-ppt" on purpose; strip it before scanning.
    low = re.sub(r"clonamic-ppt", "", text.lower())
    found = []
    for w in BANNED_DESC_WORDS:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low):
            found.append(w)
    return found


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def plugin_root() -> Path:
    return skill_root().parent.parent
