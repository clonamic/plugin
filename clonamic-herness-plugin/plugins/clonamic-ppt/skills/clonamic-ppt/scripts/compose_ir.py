#!/usr/bin/env python3
"""Deterministic SlideSpec → DeckIR composer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_lib import (  # noqa: E402
    THEME,
    BBox,
    apply_theme,
    dump_json,
    estimate_text_height_in,
    load_json,
)

CONTENT_TOP = 1.88
CONTENT_BOTTOM = 7.02
LEFT = 0.56
WIDTH = 12.21
_PUNCT = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u00a0": " ",
})


def clean_text(text: str) -> str:
    return str(text).translate(_PUNCT)


def content_origin(block_h: float) -> float:
    leftover = CONTENT_BOTTOM - CONTENT_TOP - block_h
    if leftover <= 0.45:
        return CONTENT_TOP
    return CONTENT_TOP + leftover * 0.38


def text_el(
    eid: str,
    text: str,
    bbox: BBox,
    *,
    size: float,
    weight: int = 400,
    color: str | None = None,
    align: str = "left",
    valign: str = "top",
    z: int = 20,
    order: int = 1,
    token: str | None = None,
) -> dict[str, Any]:
    return {
        "element_id": eid,
        "kind": "text",
        "bbox": bbox.as_dict(),
        "z_index": z,
        "reading_order": order,
        "token_ref": token,
        "text": clean_text(text),
        "style": {
            "font_family": THEME["heading_font"] if size >= 20 else THEME["body_font"],
            "font_size_pt": size,
            "color": color or THEME["text_primary"],
            "weight": weight,
            "italic": False,
            "align": align,
            "valign": valign,
            "line_height": 1.05 if size >= 20 else 1.22,
            "margin_in": 0.0,
            "fit_policy": "none",
        },
    }


def shape_el(
    eid: str,
    bbox: BBox,
    fill: str,
    *,
    order: int = 0,
    z: int = 10,
    radius: float | None = None,
    shape_type: str = "round_rect",
    stroke: bool = True,
) -> dict[str, Any]:
    r = 0.0 if radius == 0 else (THEME["radius"] if radius is None else radius)
    st = "rect" if shape_type == "round_rect" and r == 0 else shape_type
    return {
        "element_id": eid,
        "kind": "shape",
        "bbox": bbox.as_dict(),
        "z_index": z,
        "reading_order": order,
        "shape_type": st,
        "fill": {"color": fill, "transparency": 0},
        "stroke": {"color": THEME["border"], "width_pt": 0.6} if stroke else {"color": fill, "width_pt": 0},
        "radius_in": r,
    }


def accent_bar(eid: str, card: BBox, order: int) -> dict[str, Any] | None:
    if THEME.get("card_rail"):
        return shape_el(
            eid,
            BBox(card.x, card.y, 0.07, card.h),
            THEME["accent"],
            order=order,
            z=12,
            radius=0,
            stroke=False,
        )
    if THEME.get("accent_bar"):
        return shape_el(
            eid,
            BBox(card.x, card.y, card.w, 0.06),
            THEME["accent"],
            order=order,
            z=12,
            radius=0.02,
            stroke=False,
        )
    return None


def maybe_chrome(els: list, eid: str, card: BBox, order: int) -> None:
    bar = accent_bar(eid, card, order)
    if bar:
        els.append(bar)


def rec_label(key: str, language: str) -> str:
    ko = language.lower().startswith("ko")
    table = {
        "owner": ("담당", "Owner"),
        "timing": ("시점", "When"),
        "success": ("성공", "Success"),
        "next": ("다음", "Next"),
        "read": ("이렇게 읽는다", "Read this as"),
    }
    pair = table.get(key, (key, key))
    return pair[0] if ko else pair[1]


def title_size(text: str, width: float, language: str, hero: bool, max_h: float = 0.96) -> float:
    size = THEME["title_hero"] if hero else THEME["title_standard"]
    while size > THEME["min_title"]:
        h = estimate_text_height_in(text, width, size, 1.05, language, 0.04)
        if h <= max_h:
            return size
        size -= 1
    return THEME["min_title"]


def add_title(els: list, spec: dict, language: str, *, hero: bool = False) -> None:
    has_sub = bool(spec.get("subtitle"))
    indent = 0.16 if THEME.get("title_rule") == "left" else 0.0
    box = BBox(LEFT + indent, 0.28, WIDTH - indent, 1.08 if has_sub else 1.28)
    size = title_size(spec["title"], box.w, language, hero or spec.get("importance") == "hero", max_h=box.h - 0.02)
    if THEME.get("title_rule") == "left":
        cpl = max(1.0, (box.w * 72) / (size * 0.78))
        lines = 1 if len(spec["title"]) <= cpl else 2
        rule_h = 0.46 if lines == 1 else min(box.h - 0.18, 0.88)
        els.append(
            shape_el(
                f"{spec['slide_id']}_trule",
                BBox(LEFT, 0.32, 0.07, rule_h),
                THEME["accent"],
                order=0,
                z=12,
                radius=0,
                stroke=False,
            )
        )
    elif THEME.get("title_rule") == "underline":
        els.append(
            shape_el(
                f"{spec['slide_id']}_trule",
                BBox(LEFT, box.y + box.h - 0.04, WIDTH, 0.025),
                THEME["border"],
                order=0,
                z=12,
                radius=0,
                stroke=False,
            )
        )
    els.append(text_el(f"{spec['slide_id']}_title", spec["title"], box, size=size, weight=600, order=1, token="title"))
    if has_sub:
        els.append(
            text_el(
                f"{spec['slide_id']}_sub",
                spec["subtitle"],
                BBox(LEFT, 1.48, WIDTH, 0.34),
                size=THEME["subtitle"],
                color=THEME["text_secondary"],
                order=2,
                token="subtitle",
            )
        )


def footer_source(spec: dict[str, Any]) -> str | None:
    labels = spec.get("source_labels") or []
    return " · ".join(labels)[:160] if labels else None


def add_source(els: list, spec: dict) -> None:
    src = footer_source(spec)
    if not src:
        return
    els.append(
        text_el(
            f"{spec['slide_id']}_src",
            src,
            BBox(LEFT, 7.16, 8.40, 0.22),
            size=THEME["footnote"],
            color=THEME["text_secondary"],
            order=90,
            token="source",
        )
    )


def _is_numeric_metric(block: dict[str, Any]) -> bool:
    return block.get("type") == "metric_card" and bool(re.search(r"\d", str(block.get("value") or "")))


def _bullet_items(spec: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for b in spec.get("content_blocks") or []:
        if b.get("type") == "bullets":
            items.extend(str(x) for x in (b.get("items") or []))
        elif b.get("type") == "paragraph" and b.get("text"):
            items.append(str(b["text"]))
    return items[:6]


def enrich_specs_from_outline(specs: dict[str, Any], outline: dict[str, Any] | None) -> dict[str, Any]:
    """Copy outline must_show onto specs so compose can plant extras without a second story."""
    if not outline or not isinstance(outline.get("slides"), list):
        return specs
    by_id = {s.get("slide_id"): s for s in outline["slides"] if s.get("slide_id")}
    for s in specs.get("slides") or []:
        os = by_id.get(s.get("slide_id")) or {}
        if not (s.get("must_show") or s.get("must_include")) and (os.get("must_show") or os.get("must_include")):
            s["must_show"] = list(os.get("must_show") or os.get("must_include") or [])
    return specs


def _payload_items(spec: dict[str, Any], *banned: str) -> list[str]:
    """Bullets first; outline/spec must_show fills quote/hero extras when the child omitted them."""
    extra = [str(x).strip() for x in (spec.get("must_show") or spec.get("must_include") or []) if str(x).strip()]
    out: list[str] = []
    seen: set[str] = set()
    for it in _bullet_items(spec) + extra:
        raw = it.strip()
        key = _norm_txt(raw)
        if not raw or not key or key in seen:
            continue
        if _echo(raw, *banned, *out):
            continue
        seen.add(key)
        out.append(raw)
    return out[:6]


def _qa_text_need(text: str, width: float, size: float, language: str, padding: float = 0.10) -> float:
    """Same estimator QA005 uses (line 1.2). Footer fit must pass padding=0.02."""
    return estimate_text_height_in(text, width, size, 1.2, language, padding)


def _norm_txt(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", (text or "").strip().lower())


def _distinct(text: str, *others: str) -> bool:
    t = _norm_txt(text)
    if len(t) < 8:
        return False
    for o in others:
        n = _norm_txt(o)
        if not n:
            continue
        if t == n:
            return False
        if (t in n or n in t) and min(len(t), len(n)) / max(len(t), len(n)) > 0.72:
            return False
    return True


def _echo(text: str, *others: str) -> bool:
    """True when `text` restates something already on the slide."""
    if not _distinct(text, *others):
        return True
    latin = set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))
    for o in others:
        if not (o or "").strip():
            continue
        other_l = set(re.findall(r"[a-z0-9]{3,}", o.lower()))
        if latin and other_l:
            inter = latin & other_l
            if inter and len(inter) / min(len(latin), len(other_l)) >= 0.55:
                return True
        t, n = _norm_txt(text), _norm_txt(o)
        if len(t) >= 10 and len(n) >= 10:
            windows = {t[i : i + 4] for i in range(len(t) - 3)}
            hit = sum(1 for i in range(len(n) - 3) if n[i : i + 4] in windows)
            if hit / min(len(t), len(n)) > 0.32:
                return True
    return False


def _ellipsize(text: str, width: float, size: float, language: str, max_h: float = 0.26) -> str:
    raw = clean_text(text).strip()
    if not raw or _qa_text_need(raw, width, size, language, 0.02) <= max_h + 1e-6:
        return raw
    words = raw.split(" ")
    keep: list[str] = []
    for w in words:
        trial = (" ".join(keep + [w])).rstrip() + "…"
        if _qa_text_need(trial, width, size, language, 0.02) > max_h + 1e-6:
            break
        keep.append(w)
    if keep:
        return " ".join(keep).rstrip(".,;:") + "…"
    for i in range(len(raw), 0, -1):
        trial = raw[:i].rstrip() + "…"
        if _qa_text_need(trial, width, size, language, 0.02) <= max_h + 1e-6:
            return trial if i >= 4 else (raw[:8] + "…")
    return raw[:8] + "…"


def _footer_title(title: str, language: str) -> tuple[str, float, float, float]:
    """Full title when possible. Never a lone ellipsis. Returns text, size, w, h."""
    raw = clean_text(title or "").strip()
    width = 9.55
    if not raw:
        return "", 10.0, width, 0.30
    for size in (10.0, 9.0):
        if _qa_text_need(raw, width, size, language, 0.02) <= 0.28:
            return raw, size, width, 0.30
    if _qa_text_need(raw, width, 9.0, language, 0.02) <= 0.46:
        return raw, 9.0, width, 0.44
    return _ellipsize(raw, width, 9.0, language, 0.44), 9.0, width, 0.44


def _proof_chrome(has_body: bool) -> float:
    numbered = bool(THEME.get("number_proofs", True))
    if numbered and THEME.get("proof_dots"):
        return 0.86 if has_body else 0.72
    if numbered:
        return 1.10 if has_body else 0.90
    return 0.86 if has_body else 0.68


def _statement_band(text: str, width: float, language: str, *, min_size: float = 18, max_size: float = 22) -> tuple[float, float]:
    """Return (font_size, card_h) hugged to the line, preferring larger type over a tall empty card."""
    raw = (text or "").strip()
    if not raw:
        return min_size, 0.72
    size = max_size
    need = _qa_text_need(raw, width, size, language, 0.10)
    while size > min_size and need > 1.05:
        size -= 1
        need = _qa_text_need(raw, width, size, language, 0.10)
    return size, min(1.35, max(0.72, need + 0.34))


def _closer_h(text: str, language: str) -> float:
    raw = (text or "").strip()
    if not raw:
        return 0.0
    need = _qa_text_need(raw, WIDTH - 0.56, 17, language, 0.10)
    return min(1.10, max(0.72, need + 0.28))


def _distinct_takeaway(spec: dict[str, Any], *banned: str) -> str:
    tw = (spec.get("takeaway") or "").strip()
    if _distinct(tw, spec.get("title") or "", spec.get("subtitle") or "", *banned):
        return tw
    return ""


def _plant_evidence_row(
    els: list,
    spec: dict[str, Any],
    items: list[str],
    language: str,
    y: float,
    *already_shown: str,
) -> float:
    """Full-width evidence chips under a hugged hero. Returns the next y."""
    items = [it for it in items if (it or "").strip()][:3]
    if not items or y + 0.70 > CONTENT_BOTTOM:
        return y
    gap = 0.14
    n = len(items)
    cw = (WIDTH - gap * (n - 1)) / n
    eh = min(
        1.20,
        max(0.78, max(_qa_text_need(it, cw - 0.36, 14, language, 0.10) for it in items) + 0.32),
    )
    eh = min(eh, max(0.70, CONTENT_BOTTOM - y - 0.04))
    for i, it in enumerate(items):
        x = LEFT + i * (cw + gap)
        els.append(shape_el(f"{spec['slide_id']}_pr{i}", BBox(x, y, cw, eh), THEME["surface_muted"], order=40 + i))
        els.append(
            text_el(
                f"{spec['slide_id']}_prt{i}",
                it,
                BBox(x + 0.16, y + 0.14, cw - 0.32, eh - 0.26),
                size=14,
                weight=600,
                valign="middle",
                order=50 + i,
                token="body",
            )
        )
    by = y + eh + 0.12
    closer = _distinct_takeaway(spec, *items, *already_shown)
    if closer and CONTENT_BOTTOM - by >= 0.60:
        _conclusion_band(els, spec, closer, [], by, language)
        return CONTENT_BOTTOM
    return by


def _conclusion_band(
    els: list,
    spec: dict[str, Any],
    text: str,
    chips: list[str],
    y: float,
    language: str,
    bottom: float = CONTENT_BOTTOM,
    height: float | None = None,
) -> None:
    """One compact closer at the bottom. chips are ignored — echoing labels is slop."""
    raw = (text or "").strip()
    hug = height if height else _closer_h(raw, language)
    if hug < 0.60 or bottom - y < 0.60:
        return
    bh = min(hug, bottom - y)
    by = y
    band = BBox(LEFT, by, WIDTH, bh)
    els.append(shape_el(f"{spec['slide_id']}_spine", band, THEME["surface_muted"], order=70))
    maybe_chrome(els, f"{spec['slide_id']}_spinea", band, 71)
    els.append(
        text_el(
            f"{spec['slide_id']}_spinet",
            raw,
            BBox(LEFT + 0.28, by + 0.12, WIDTH - 0.56, bh - 0.22),
            size=17,
            weight=600,
            valign="middle",
            order=72,
            token="body",
        )
    )


def _place_extra_cards(
    els: list,
    spec: dict[str, Any],
    extras: list[tuple[str, str]],
    language: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    lab_color: str | None = None,
    val_color: str | None = None,
    id0: str = "meta",
    layout: str = "auto",
) -> None:
    extras = extras[:4]
    n = max(1, len(extras))
    gap = 0.16
    if layout == "row" or n <= 3:
        cols, rows = n, 1
    else:
        cols, rows = (2, 2) if n >= 4 else (n, 1)
    cw = (w - gap * (cols - 1)) / cols
    ch = (h - gap * (rows - 1)) / rows
    lab_color = lab_color or THEME["accent"]
    val_color = val_color or THEME["text_primary"]
    for i, (lab, val) in enumerate(extras):
        r, c = divmod(i, cols)
        xx = x + c * (cw + gap)
        yy = y + r * (ch + gap)
        eid = f"{spec['slide_id']}_{id0}" if i == 0 else f"{spec['slide_id']}_xc{i}"
        els.append(shape_el(eid, BBox(xx, yy, cw, ch), THEME["surface"], order=10 + i))
        maybe_chrome(els, f"{spec['slide_id']}_xca{i}", BBox(xx, yy, cw, ch), 11 + i)
        els.append(
            text_el(
                f"{spec['slide_id']}_rl{i}",
                lab,
                BBox(xx + 0.22, yy + 0.16, cw - 0.44, 0.28),
                size=12,
                weight=600,
                color=lab_color,
                order=20 + i,
            )
        )
        room = max(0.40, ch - 0.52)
        vsize = 16
        while vsize > 13 and _qa_text_need(val, cw - 0.44, vsize, language, 0.10) > room + 1e-6:
            vsize -= 1
        evh = min(room, max(0.42, _qa_text_need(val, cw - 0.44, vsize, language, 0.10)))
        els.append(
            text_el(
                f"{spec['slide_id']}_rv{i}",
                val,
                BBox(xx + 0.22, yy + 0.48, cw - 0.44, evh),
                size=vsize,
                weight=600,
                color=val_color,
                order=30 + i,
                token="body",
            )
        )


def _is_cjk_lang(language: str) -> bool:
    return (language or "").lower().startswith(("ko", "ja", "zh"))


def _extra_thin(val: str, language: str) -> bool:
    v = (val or "").strip()
    if not v:
        return True
    if _is_cjk_lang(language):
        return len(v) < 14
    return len(v) < 45 or len(v.split()) < 8


def _place_extra_strip(
    els: list,
    spec: dict[str, Any],
    extras: list[tuple[str, str]],
    language: str,
    *,
    y: float,
    h: float = 0.86,
    id0: str = "meta",
) -> None:
    extras = extras[:4]
    n = max(1, len(extras))
    gap = 0.12
    cw = (WIDTH - gap * (n - 1)) / n
    for i, (lab, val) in enumerate(extras):
        x = LEFT + i * (cw + gap)
        eid = f"{spec['slide_id']}_{id0}" if i == 0 else f"{spec['slide_id']}_xc{i}"
        els.append(shape_el(eid, BBox(x, y, cw, h), THEME["surface"], order=10 + i))
        maybe_chrome(els, f"{spec['slide_id']}_xca{i}", BBox(x, y, cw, h), 11 + i)
        els.append(
            text_el(
                f"{spec['slide_id']}_rl{i}",
                lab,
                BBox(x + 0.16, y + 0.10, cw - 0.32, 0.28),
                size=11,
                weight=600,
                color=THEME["accent"],
                order=20 + i,
            )
        )
        els.append(
            text_el(
                f"{spec['slide_id']}_rv{i}",
                val,
                BBox(x + 0.16, y + 0.42, cw - 0.32, max(0.50, h - 0.54)),
                size=13,
                weight=600,
                order=30 + i,
                token="body",
            )
        )


def _size_to_fit(text: str, width: float, start: float, min_size: float, max_h: float, language: str) -> float:
    size = start
    while size > min_size and _qa_text_need(text, width, size, language) > max_h + 1e-6:
        size -= 1
    return size


def select_family(spec: dict[str, Any], index: int = 1) -> str:
    blocks = spec.get("content_blocks") or []
    types = [b.get("type") for b in blocks]
    role = spec.get("role")
    n_metric = sum(1 for b in blocks if _is_numeric_metric(b))
    n_fake = sum(1 for b in blocks if b.get("type") == "metric_card" and not _is_numeric_metric(b))
    items = _bullet_items(spec)
    payload = _payload_items(spec, spec.get("title") or "")
    if "chart" in types:
        return "chart_focus"
    if "table" in types:
        return "table_focus"
    if "quote" in types and role in {None, "assertion", "case_study", "title"}:
        return "quote_proof"
    if n_metric >= 2 and n_fake == 0:
        return "metric_strip"
    if "comparison" in types or role == "comparison":
        return "comparison_2col"
    if "process_steps" in types or role == "process":
        return "process_flow"
    if "recommendation" in types:
        return "recommendation"
    if n_metric <= 1 and 3 <= len(items) <= 6:
        return "proof_grid"
    # Mid-deck second number is named claims, not another hero stamp.
    if index > 1 and n_metric <= 1 and len(payload) >= 2:
        return "proof_grid"
    if role in {"recommendation", "summary"}:
        return "recommendation"
    return "hero_assertion"


def _grid_items(spec: dict[str, Any]) -> list[str]:
    items = [it.strip() for it in _bullet_items(spec) if str(it).strip()]
    if len(items) >= 3:
        return items[:6]
    seen = {_norm_txt(it) for it in items}
    for it in _payload_items(spec, spec.get("title") or ""):
        key = _norm_txt(it)
        if key and key not in seen:
            items.append(it)
            seen.add(key)
    if len(items) < 3:
        banned = [spec.get("title") or "", *items]
        for b in spec.get("content_blocks") or []:
            if b.get("type") != "metric_card":
                continue
            for cand in (b.get("supporting_text"),):
                t = str(cand or "").strip()
                if t and _distinct(t, *banned) and not _echo(t, *banned):
                    items.append(t)
                    banned.append(t)
        tw = (spec.get("takeaway") or "").strip()
        if tw and _distinct(tw, spec.get("title") or "", *items):
            items.append(tw)
    return items[:6]


def _split_item(text: str) -> tuple[str, str]:
    for sep in (" — ", " – ", ": ", "：", " - "):
        if sep in text:
            a, b = text.split(sep, 1)
            return a.strip(), b.strip()
    return text.strip(), ""


def compose_proof_grid(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    items = _grid_items(spec)
    if not items:
        items = [spec.get("takeaway") or spec["title"]]
    items = [it for it in items if str(it).strip()][:6]
    n = max(1, len(items))
    gap = 0.18
    if n <= 2:
        rows, cols = n, 1
    elif n == 3:
        rows, cols = 3, 1
    elif n == 4:
        rows, cols = 2, 2
    else:
        rows, cols = 2, 3
    cw = (WIDTH - gap * (cols - 1)) / cols
    parsed = [_split_item(it) for it in items]
    has_body = any(body for _, body in parsed)
    top = CONTENT_TOP
    tw = spec.get("takeaway") or ""
    if tw and tw not in {spec.get("title"), spec.get("subtitle")} and spec.get("role") == "title":
        # Takeaway is the closer, not a second thesis line above the cards.
        pass
    usable_h = CONTENT_BOTTOM - top
    closer = _distinct_takeaway(spec, *items)
    reserve = _closer_h(closer, language)
    plant_h = usable_h - (reserve + 0.12 if reserve else 0.0)
    body_pt = 16
    body_need = max(
        (
            estimate_text_height_in(body, cw - 0.44, body_pt, 1.22, language, 0.10)
            if body
            else 0.0
        )
        for _, body in parsed
    )
    used_est = _proof_chrome(has_body) + (body_need if has_body else 0.28)
    natural = min(1.58, used_est)
    spans = []
    for _head, body in parsed:
        if body:
            bn = estimate_text_height_in(body, cw - 0.44, body_pt, 1.22, language, 0.10)
            spans.append(0.40 + 0.08 + bn)
        else:
            spans.append(0.40)
    min_span = min(spans) if spans else 0.40
    row_cap = (plant_h - gap * (rows - 1)) / rows
    max_ch = max(natural * 0.92, min_span / 0.44)
    stacked = cols == 1 and n <= 3
    pair_top = stacked and n == 3 and not has_body
    item_box: list[tuple[float, float, float, float]] = []
    if pair_top:
        top_w = (WIDTH - gap) / 2
        h0 = min(1.45, max(0.90, _qa_text_need(parsed[0][0], top_w - 0.44, 20, language, 0.10) + 0.44))
        h1 = min(1.45, max(0.90, _qa_text_need(parsed[1][0], top_w - 0.44, 20, language, 0.10) + 0.44))
        h2 = min(1.55, max(0.95, _qa_text_need(parsed[2][0], WIDTH - 0.44, 22, language, 0.10) + 0.44))
        top_h = max(h0, h1)
        item_box = [
            (LEFT, top, top_w, top_h),
            (LEFT + top_w + gap, top, top_w, top_h),
            (LEFT, top + top_h + gap, WIDTH, h2),
        ]
        ch = top_h
        row_hs = [top_h, top_h, h2]
        y_cursor = top + top_h + gap + h2 + gap
    elif stacked:
        if has_body:
            ch = min(row_cap, max(1.10, natural + 0.12), 1.72)
            row_hs = [ch] * n
        else:
            row_hs = []
            for head, _body in parsed:
                row_hs.append(
                    min(
                        1.45,
                        max(0.90, _qa_text_need(head, cw - 0.44, 20, language, 0.10) + 0.44),
                    )
                )
            ch = max(row_hs)
        y_cursor = top
    else:
        ch = min(row_cap, max_ch, 1.72)
        row_hs = [ch] * n
        y_cursor = top
    for i, raw in enumerate(items):
        r, c = divmod(i, cols)
        if n == 5 and i == 4:
            c = 1
        if pair_top:
            x, y, cw, ch = item_box[i]
        elif stacked:
            x = LEFT
            y = y_cursor
            ch = row_hs[i]
            y_cursor += ch + gap
        else:
            x = LEFT + c * (cw + gap)
            y = top + r * (ch + gap)
        card = BBox(x, y, cw, ch)
        els.append(shape_el(f"{spec['slide_id']}_g{i}", card, THEME["surface"], order=10 + i))
        maybe_chrome(els, f"{spec['slide_id']}_ga{i}", card, 11 + i)
        head, body = parsed[i]
        numbered = bool(THEME.get("number_proofs", True))
        if numbered and THEME.get("proof_dots"):
            els.append(
                shape_el(
                    f"{spec['slide_id']}_gd{i}",
                    BBox(x + 0.18, y + 0.22, 0.32, 0.32),
                    THEME["accent"],
                    order=19 + i,
                    z=12,
                    radius=0,
                    shape_type="ellipse",
                    stroke=False,
                )
            )
            els.append(
                text_el(
                    f"{spec['slide_id']}_gn{i}",
                    str(i + 1),
                    BBox(x + 0.18, y + 0.22, 0.32, 0.32),
                    size=11,
                    weight=700,
                    color=THEME["text_inverse"],
                    align="center",
                    valign="middle",
                    order=20 + i,
                )
            )
            text_x, text_w = x + 0.58, cw - 0.76
            head_top = y + 0.18
        elif numbered:
            els.append(
                text_el(
                    f"{spec['slide_id']}_gn{i}",
                    f"{i + 1:02d}",
                    BBox(x + 0.22, y + 0.18, cw - 0.44, 0.28),
                    size=12,
                    weight=700,
                    color=THEME["accent"],
                    order=20 + i,
                )
            )
            text_x, text_w = x + 0.22, cw - 0.44
            head_top = y + 0.50
        else:
            text_x, text_w = x + 0.22, cw - 0.44
            head_top = y + 0.22
        if body:
            head_h = 0.40
        elif stacked:
            head_h = min(
                ch - (head_top - y) - 0.14,
                max(0.40, _qa_text_need(head, text_w, 20, language, 0.10)),
            )
        else:
            head_h = ch - (head_top - y) - 0.14
        els.append(
            text_el(
                f"{spec['slide_id']}_gh{i}",
                head,
                BBox(text_x, head_top, text_w, head_h),
                size=20 if stacked and not body else 16,
                weight=600,
                valign="top",
                order=30 + i,
                token="body",
            )
        )
        if body:
            body_y = head_top + head_h + 0.08
            room = max(0.36, ch - (body_y - y) - 0.10)
            bsize = body_pt
            need = estimate_text_height_in(body, text_w, bsize, 1.22, language, 0.10)
            while bsize > 12 and need > room + 1e-6:
                bsize -= 1
                need = estimate_text_height_in(body, text_w, bsize, 1.22, language, 0.10)
            body_box = min(need, room)
            els.append(
                text_el(
                    f"{spec['slide_id']}_gb{i}",
                    body,
                    BBox(text_x, body_y, text_w, max(0.32, body_box)),
                    size=bsize,
                    color=THEME["text_secondary"],
                    order=40 + i,
                )
            )
    if stacked:
        grid_bottom = y_cursor - gap
    else:
        grid_bottom = top + rows * ch + gap * max(0, rows - 1)
    if reserve and closer:
        _conclusion_band(els, spec, closer, [], grid_bottom + 0.10, language)
    add_source(els, spec)
    return els


def compose_hero(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language, hero=True)
    y = CONTENT_TOP
    metrics = [b for b in spec.get("content_blocks") or [] if _is_numeric_metric(b)]
    items = _bullet_items(spec)
    banned = [spec.get("takeaway") or "", spec.get("title") or ""]
    if metrics:
        m0 = metrics[0]
        banned.extend(
            [
                str(m0.get("value") or ""),
                str(m0.get("label") or ""),
                str(m0.get("supporting_text") or ""),
            ]
        )
    proofs = _payload_items(spec, *banned)[:4]
    if metrics:
        m = metrics[0]
        support = str(m.get("supporting_text") or "")
        if not support:
            tw = spec.get("takeaway") or ""
            if tw and tw not in {spec.get("title"), str(m.get("label") or "")}:
                support = tw
        tw = (spec.get("takeaway") or "").strip()
        used = {spec.get("title"), support, str(m.get("label") or "")}
        inner = tw if tw and tw not in used else (support if support and support not in used else "")
        billboard = not proofs
        text_w = WIDTH - 0.72
        if billboard:
            val_size, lab_size = 56, 22
            val_w = 4.20
            lab_w = WIDTH - val_w - 0.84
            val_h = max(0.92, _qa_text_need(str(m.get("value") or ""), val_w, val_size, language, 0.10))
            lab_h = max(0.50, _qa_text_need(str(m.get("label") or ""), lab_w, lab_size, language, 0.10))
            claims: list[str] = []
            if support and support != inner:
                claims.append(support)
            if inner:
                claims.append(inner)
            bar_h = max(val_h, lab_h) + 0.40
            y = CONTENT_TOP
            card = BBox(LEFT, y, WIDTH, bar_h)
            els.append(shape_el(f"{spec['slide_id']}_ms", card, THEME["surface"], order=3))
            maybe_chrome(els, f"{spec['slide_id']}_ma", card, 4)
            els.append(
                text_el(
                    f"{spec['slide_id']}_mv",
                    str(m.get("value", "")),
                    BBox(card.x + 0.36, card.y + 0.18, val_w, bar_h - 0.32),
                    size=val_size,
                    weight=700,
                    color=THEME["accent"],
                    valign="middle",
                    order=5,
                    token="metric",
                )
            )
            els.append(
                text_el(
                    f"{spec['slide_id']}_ml",
                    str(m.get("label", "")),
                    BBox(card.x + 0.36 + val_w + 0.16, card.y + 0.18, lab_w, bar_h - 0.32),
                    size=lab_size,
                    weight=600,
                    valign="middle",
                    order=6,
                )
            )
            if claims:
                gap = 0.12
                cy = y + bar_h + 0.12
                for i, it in enumerate(claims):
                    csize, rh = _statement_band(it, WIDTH - 0.56, language, min_size=18, max_size=22)
                    els.append(shape_el(f"{spec['slide_id']}_pr{i}", BBox(LEFT, cy, WIDTH, rh), THEME["surface_muted"], order=40 + i))
                    els.append(
                        text_el(
                            f"{spec['slide_id']}_prt{i}",
                            it,
                            BBox(LEFT + 0.28, cy + 0.12, WIDTH - 0.56, rh - 0.22),
                            size=csize,
                            weight=600,
                            valign="middle",
                            order=50 + i,
                            token="body",
                        )
                    )
                    cy += rh + gap
        else:
            val_size, lab_size, sup_size, inn_size = 42, 22, 16, 18
            right_w = WIDTH - 3.90
            lab_h = max(0.50, _qa_text_need(str(m.get("label") or ""), right_w, lab_size, language, 0.10))
            sup_h = max(0.44, _qa_text_need(support, right_w, sup_size, language, 0.10)) if support and support != inner else 0.0
            inn_h = max(0.58, _qa_text_need(inner, text_w, inn_size, language, 0.10)) if inner else 0.0
            val_h = 1.48
            top_row = max(val_h, lab_h + (0.10 + sup_h if sup_h else 0.0))
            card_h = min(
                CONTENT_BOTTOM - CONTENT_TOP - 1.00,
                max(3.15 if inner else 2.20, 0.32 + top_row + (0.20 + inn_h if inner else 0.16) + 0.22),
            )
            y = CONTENT_TOP
            card = BBox(LEFT, y, WIDTH, card_h)
            els.append(shape_el(f"{spec['slide_id']}_ms", card, THEME["surface"], order=3))
            maybe_chrome(els, f"{spec['slide_id']}_ma", card, 4)
            els.append(
                text_el(
                    f"{spec['slide_id']}_mv",
                    str(m.get("value", "")),
                    BBox(card.x + 0.36, card.y + 0.28, 2.90, val_h),
                    size=val_size,
                    weight=700,
                    color=THEME["accent"],
                    valign="middle",
                    order=5,
                    token="metric",
                )
            )
            lab_y = card.y + 0.32
            els.append(
                text_el(
                    f"{spec['slide_id']}_ml",
                    str(m.get("label", "")),
                    BBox(card.x + 3.44, lab_y, right_w, lab_h),
                    size=lab_size,
                    weight=600,
                    order=6,
                )
            )
            if sup_h:
                els.append(
                    text_el(
                        f"{spec['slide_id']}_msup",
                        support,
                        BBox(card.x + 3.44, lab_y + lab_h + 0.08, right_w, sup_h),
                        size=sup_size,
                        color=THEME["text_secondary"],
                        order=7,
                    )
                )
            if inner:
                inn_y = card.y + 0.32 + top_row + 0.16
                els.append(
                    text_el(
                        f"{spec['slide_id']}_mta",
                        inner,
                        BBox(card.x + 0.36, inn_y, text_w, min(inn_h, card_h - (inn_y - card.y) - 0.18)),
                        size=inn_size,
                        weight=600,
                        order=8,
                        token="body",
                    )
                )
        if proofs:
            _plant_evidence_row(els, spec, proofs[:2], language, y + card_h + 0.14, inner, support)
    elif items:
        # single-column stacked evidence cards, not a floating list
        gap = 0.14
        n = min(4, len(items))
        ph = min(
            1.28,
            max(
                0.92,
                max(_qa_text_need(it, WIDTH - 1.40, 16, language, 0.04) for it in items[:n]) + 0.36,
            ),
        )
        for i, it in enumerate(items[:n]):
            py = y + i * (ph + gap)
            box = BBox(LEFT, py, WIDTH, ph)
            els.append(shape_el(f"{spec['slide_id']}_row{i}", box, THEME["surface"], order=10 + i))
            els.append(
                text_el(
                    f"{spec['slide_id']}_rn{i}",
                    f"{i + 1:02d}",
                    BBox(LEFT + 0.24, py + 0.16, 0.70, ph - 0.28),
                    size=16,
                    weight=700,
                    color=THEME["accent"],
                    valign="middle",
                    order=20 + i,
                )
            )
            need = min(
                ph - 0.28,
                max(0.40, _qa_text_need(it, WIDTH - 1.40, 16, language, 0.04)),
            )
            els.append(
                text_el(
                    f"{spec['slide_id']}_rt{i}",
                    it,
                    BBox(LEFT + 1.05, py + 0.16, WIDTH - 1.40, need),
                    size=16,
                    weight=600,
                    valign="top",
                    order=30 + i,
                    token="body",
                )
            )
        by = y + n * ph + gap * max(0, n - 1) + 0.12
        closer = (spec.get("takeaway") or "").strip()
        if not _distinct(closer, spec.get("title") or ""):
            closer = " · ".join(items[:n])
        if CONTENT_BOTTOM - by >= 0.50:
            _conclusion_band(els, spec, closer, [_split_item(it)[0] for it in items[:n]], by, language)
    add_source(els, spec)
    return els


def compose_metrics(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    cards = [b for b in spec.get("content_blocks") or [] if _is_numeric_metric(b)][:4]
    n = min(4, max(2, len(cards) or 2))
    while len(cards) < n:
        cards.append({"value": "—", "label": "TBD", "supporting_text": ""})
    cards = cards[:n]
    gap = 0.20
    cw = (WIDTH - gap * (n - 1)) / n
    sups = [str(m.get("supporting_text") or "") for m in cards]
    sup_need = max(
        (estimate_text_height_in(s, cw - 0.44, THEME["body"], 1.22, language, 0.10) if s else 0.0) for s in sups
    )
    h = min(CONTENT_BOTTOM - CONTENT_TOP, max(2.20, 2.18 + (sup_need if any(sups) else 0.28)))
    closer = _distinct_takeaway(spec)
    reserve = _closer_h(closer, language) if closer else 0.0
    y = content_origin(h + (reserve + 0.12 if reserve else 0.0))
    for i, m in enumerate(cards):
        x = LEFT + i * (cw + gap)
        card = BBox(x, y, cw, h)
        els.append(shape_el(f"{spec['slide_id']}_c{i}", card, THEME["surface"], order=10 + i))
        maybe_chrome(els, f"{spec['slide_id']}_ca{i}", card, 11 + i)
        els.append(
            text_el(
                f"{spec['slide_id']}_v{i}",
                str(m.get("value", "")),
                BBox(x + 0.22, y + 0.28, cw - 0.44, 1.05),
                size=32,
                weight=700,
                color=THEME["accent"],
                order=20 + i,
                token="metric",
            )
        )
        els.append(
            text_el(
                f"{spec['slide_id']}_l{i}",
                str(m.get("label", "")),
                BBox(x + 0.22, y + 1.42, cw - 0.44, 0.48),
                size=15,
                weight=600,
                order=30 + i,
            )
        )
        sup = sups[i]
        if sup:
            els.append(
                text_el(
                    f"{spec['slide_id']}_s{i}",
                    sup,
                    BBox(x + 0.22, y + 1.98, cw - 0.44, max(0.36, h - 2.10)),
                    size=THEME["body"],
                    color=THEME["text_secondary"],
                    order=40 + i,
                )
            )
    if closer:
        _conclusion_band(els, spec, closer, [], y + h + 0.10, language)
    add_source(els, spec)
    return els


def compose_comparison(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    comp = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "comparison"), None)
    cols = (comp or {}).get("columns") or [{"title": "A", "items": []}, {"title": "B", "items": []}]
    cols = (list(cols) + [{"title": "B", "items": []}])[:2]
    criteria = (comp or {}).get("criteria") or []
    gap = 0.56
    cw = (WIDTH - gap) / 2
    col_items: list[list[str]] = []
    for col in cols:
        items = col.get("items") or col.get("points") or []
        if criteria and not items:
            items = [str(c) for c in criteria]
        col_items.append([str(it) for it in items[:6]])
    max_items = max((len(it) for it in col_items), default=3) or 3
    item_size = 15
    text_w = cw - 0.56
    gap_y = 0.10
    header = 0.92
    pad = 0.18
    closer = _distinct_takeaway(spec)
    reserve = _closer_h(closer, language) if closer else 0.0
    usable = CONTENT_BOTTOM - CONTENT_TOP - (reserve + 0.12 if reserve else 0.0)

    def row_heights(size: float) -> list[float]:
        out: list[float] = []
        for j in range(max_items):
            need = 0.36
            for items in col_items:
                if j < len(items):
                    need = max(need, _qa_text_need(f"•  {items[j]}", text_w, size, language))
            out.append(need)
        return out

    row_hs = row_heights(item_size)
    body_h = sum(row_hs) + gap_y * max(0, max_items - 1)
    while item_size > 12 and header + body_h + pad > usable:
        item_size -= 1
        row_hs = row_heights(item_size)
        body_h = sum(row_hs) + gap_y * max(0, max_items - 1)
    packed = header + body_h + pad
    slack = max(0.0, usable - packed)
    if slack > 0.08 and max_items:
        extra = min(0.14, slack / max_items)
        row_hs = [h + extra for h in row_hs]
        body_h = sum(row_hs) + gap_y * max(0, max_items - 1)
    h = min(usable, header + body_h + pad)
    y0 = CONTENT_TOP
    for i, col in enumerate(cols):
        x = LEFT + i * (cw + gap)
        fill = THEME["surface"] if i == 0 else THEME["surface_muted"]
        card = BBox(x, y0, cw, h)
        els.append(shape_el(f"{spec['slide_id']}_col{i}", card, fill, order=10 + i))
        maybe_chrome(els, f"{spec['slide_id']}_cola{i}", card, 11 + i)
        els.append(
            text_el(
                f"{spec['slide_id']}_ct{i}",
                str(col.get("title") or col.get("name") or f"Option {i + 1}"),
                BBox(x + 0.28, y0 + 0.20, cw - 0.56, 0.42),
                size=18,
                weight=700,
                order=20 + i,
            )
        )
        items = col_items[i] or ["—"]
        y_cursor = y0 + 0.72
        for j, it in enumerate(items):
            ih = row_hs[j] if j < len(row_hs) else 0.36
            els.append(
                text_el(
                    f"{spec['slide_id']}_cb{i}_{j}",
                    f"•  {it}",
                    BBox(x + 0.28, y_cursor, cw - 0.56, ih),
                    size=item_size,
                    order=30 + i * 10 + j,
                    token="body",
                )
            )
            y_cursor += ih + gap_y
    if THEME.get("compare_vs", True):
        vs_x = LEFT + cw + (gap - 0.32) / 2
        vs_y = y0 + max(0.20, h / 2 - 0.16)
        els.append(
            shape_el(
                f"{spec['slide_id']}_vs",
                BBox(vs_x, vs_y, 0.32, 0.32),
                THEME["accent"],
                order=80,
                z=16,
                radius=0,
                shape_type="ellipse",
                stroke=False,
            )
        )
        els.append(
            text_el(
                f"{spec['slide_id']}_vst",
                "vs",
                BBox(vs_x, vs_y, 0.32, 0.32),
                size=11,
                weight=700,
                color=THEME["text_inverse"],
                align="center",
                valign="middle",
                order=81,
            )
        )
    else:
        rx = LEFT + cw + gap / 2 - 0.015
        els.append(
            shape_el(
                f"{spec['slide_id']}_vs",
                BBox(rx, y0 + 0.20, 0.03, max(0.80, h - 0.40)),
                THEME["accent"],
                order=80,
                z=16,
                radius=0,
                shape_type="rect",
                stroke=False,
            )
        )
    if reserve and closer:
        _conclusion_band(els, spec, closer, [], y0 + h + 0.10, language)
    add_source(els, spec)
    return els


def _process_mark(els: list, spec: dict[str, Any], i: int, x: float, y: float) -> float:
    mark = THEME.get("process_mark", "disc")
    if mark == "none":
        return 0.0
    if mark == "index":
        els.append(
            text_el(
                f"{spec['slide_id']}_pn{i}",
                f"{i + 1:02d}",
                BBox(x + 0.18, y + 0.16, 0.56, 0.28),
                size=12,
                weight=700,
                color=THEME["accent"],
                order=20 + i,
            )
        )
        return 0.36
    els.append(
        shape_el(
            f"{spec['slide_id']}_pb{i}",
            BBox(x + 0.18, y + 0.16, 0.32, 0.32),
            THEME["accent"],
            order=19 + i,
            z=12,
            radius=0,
            shape_type="ellipse",
            stroke=False,
        )
    )
    els.append(
        text_el(
            f"{spec['slide_id']}_pn{i}",
            str(i + 1) if THEME.get("proof_dots") else f"{i + 1:02d}",
            BBox(x + 0.18, y + 0.16, 0.32, 0.32),
            size=11,
            weight=700,
            color=THEME["text_inverse"],
            align="center",
            valign="middle",
            order=20 + i,
        )
    )
    return 0.40


def compose_process(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    proc = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "process_steps"), None)
    steps = (proc or {}).get("steps") or [{"label": f"Step {i}"} for i in range(1, 4)]
    steps = steps[:6]
    n = len(steps)
    details = [(st.get("detail") if isinstance(st, dict) else "") or "" for st in steps]
    closer = _distinct_takeaway(spec)
    reserve = _closer_h(closer, language)
    stack = THEME.get("process_layout") == "stack" and n <= 4
    y = CONTENT_TOP
    if stack:
        gap = 0.12
        text_w = WIDTH - 1.70
        cursor = y
        last_b = y
        for i, st in enumerate(steps):
            dw = WIDTH - 1.70
            dneed = (
                estimate_text_height_in(details[i], dw, THEME["body"], 1.22, language, 0.10)
                if details[i]
                else 0.28
            )
            ch = min(1.42, max(0.92, 0.16 + 0.40 + 0.08 + dneed))
            py = cursor
            card = BBox(LEFT, py, WIDTH, ch)
            els.append(shape_el(f"{spec['slide_id']}_p{i}", card, THEME["surface"], order=10 + i))
            maybe_chrome(els, f"{spec['slide_id']}_pa{i}", card, 11 + i)
            _process_mark(els, spec, i, LEFT, py)
            label = st.get("label") if isinstance(st, dict) else str(st)
            lab_x = LEFT + (1.02 if THEME.get("process_mark") == "index" else 0.62)
            els.append(
                text_el(
                    f"{spec['slide_id']}_pl{i}",
                    str(label),
                    BBox(lab_x, py + 0.12, WIDTH - (lab_x - LEFT) - 0.28, 0.40),
                    size=16,
                    weight=600,
                    order=30 + i,
                    token="body",
                )
            )
            if details[i]:
                dh = min(ch - 0.64, max(0.32, dneed))
                dw = WIDTH - (lab_x - LEFT) - 0.28
                els.append(
                    text_el(
                        f"{spec['slide_id']}_pd{i}",
                        details[i],
                        BBox(lab_x, py + 0.58, dw, dh),
                        size=THEME["body"],
                        color=THEME["text_secondary"],
                        order=40 + i,
                    )
                )
            cursor = py + ch + gap
            last_b = py + ch
        if reserve and closer:
            _conclusion_band(els, spec, closer, [], last_b + 0.10, language)
        add_source(els, spec)
        return els
    arrow_w = 0.20 if n <= 4 else 0.14
    arrow_pad = 0.08 if n <= 4 else 0.05
    arrows_total = (n - 1) * (arrow_w + 2 * arrow_pad)
    cw = (WIDTH - arrows_total) / n
    detail_need = max(
        (
            estimate_text_height_in(d, cw - 0.36, THEME["body"], 1.22, language, 0.10) if d else 0.0
            for d in details
        ),
        default=0.0,
    )
    h = min(2.70, max(1.52, 1.14 + (detail_need if any(details) else 0.28)))
    y = content_origin(h + (reserve + 0.12 if reserve else 0.0))
    for i, st in enumerate(steps):
        x = LEFT + i * (cw + arrow_w + 2 * arrow_pad)
        card = BBox(x, y, cw, h)
        els.append(shape_el(f"{spec['slide_id']}_p{i}", card, THEME["surface"], order=10 + i))
        maybe_chrome(els, f"{spec['slide_id']}_pa{i}", card, 11 + i)
        mark_h = _process_mark(els, spec, i, x, y)
        label = st.get("label") if isinstance(st, dict) else str(st)
        lab_y = y + (0.56 if mark_h else 0.16)
        els.append(
            text_el(
                f"{spec['slide_id']}_pl{i}",
                str(label),
                BBox(x + 0.18, lab_y, cw - 0.36, 0.40),
                size=16,
                weight=600,
                order=30 + i,
                token="body",
            )
        )
        if details[i]:
            dy = lab_y + 0.44
            dh = min(h - (dy - y) - 0.12, max(0.32, estimate_text_height_in(details[i], cw - 0.36, THEME["body"], 1.22, language, 0.10)))
            els.append(
                text_el(
                    f"{spec['slide_id']}_pd{i}",
                    details[i],
                    BBox(x + 0.18, dy, cw - 0.36, dh),
                    size=THEME["body"],
                    color=THEME["text_secondary"],
                    order=40 + i,
                )
            )
        if i < n - 1:
            ax = x + cw + arrow_pad
            ay = y + min(h, 1.70) / 2 - 0.11
            els.append(
                shape_el(
                    f"{spec['slide_id']}_arr{i}",
                    BBox(ax, ay, arrow_w, 0.22),
                    THEME["accent"],
                    order=50 + i,
                    z=12,
                    radius=0,
                    shape_type="arrow",
                    stroke=False,
                )
            )
    if reserve and closer:
        _conclusion_band(els, spec, closer, [], y + h + 0.10, language)
    add_source(els, spec)
    return els


def compose_recommendation(spec: dict[str, Any], language: str, *, closing: bool = True) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    rec = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "recommendation"), None)
    bullets = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "bullets"), None)
    action = (rec or {}).get("action") or spec.get("takeaway") or ""
    extras: list[tuple[str, str]] = []
    if rec:
        if rec.get("owner"):
            extras.append((rec_label("owner", language), str(rec["owner"])))
        if rec.get("timing"):
            extras.append((rec_label("timing", language), str(rec["timing"])))
        if rec.get("success_metric"):
            extras.append((rec_label("success", language), str(rec["success_metric"])))
    elif bullets:
        for it in (bullets.get("items") or [])[:4]:
            head, body = _split_item(str(it))
            extras.append((head or rec_label("next", language), body or head))
    extras = extras[:4] or [(rec_label("next", language), spec.get("takeaway") or "Decide the next action.")]
    tw = (spec.get("takeaway") or "").strip()
    n = len(extras)
    val_w = (WIDTH - 0.16 * max(0, n - 1)) / n - 0.44
    val_need = max(_qa_text_need(v, val_w, 16, language, 0.10) for _, v in extras)
    thin_n = sum(1 for _, v in extras if _extra_thin(v, language))
    thin = n >= 3 and thin_n >= 1
    if thin:
        strip_need = max(_qa_text_need(v, val_w + 0.12, 13, language, 0.10) for _, v in extras)
        row_h = min(1.32, max(1.04, 0.58 + strip_need))
    else:
        row_h = min(1.55, max(1.16, 0.62 + val_need))
    if closing:
        ask_need = _qa_text_need(action, WIDTH - 0.72, 18, language, 0.06)
        closer_pre = tw if _distinct(tw, action) else ""
        reserve_pre = _closer_h(closer_pre, language)
        ask_h = CONTENT_BOTTOM - CONTENT_TOP - row_h - (reserve_pre + 0.26 if reserve_pre else 0.14)
        ask_h = min(2.35, max(1.45, max(ask_need + 0.36, ask_h)))
        banner = BBox(LEFT, CONTENT_TOP, WIDTH, ask_h)
        els.append(
            shape_el(
                f"{spec['slide_id']}_ban",
                banner,
                THEME["accent_dark"],
                order=2,
                radius=THEME["radius"],
                stroke=False,
            )
        )
        act_size = _size_to_fit(action, WIDTH - 0.72, 20, 14, ask_h - 0.32, language)
        els.append(
            text_el(
                f"{spec['slide_id']}_act",
                action,
                BBox(LEFT + 0.36, CONTENT_TOP + 0.16, WIDTH - 0.72, ask_h - 0.28),
                size=act_size,
                weight=600,
                color=THEME["text_inverse"],
                valign="middle",
                order=3,
            )
        )
        card_y = CONTENT_TOP + ask_h + 0.14
        closer = closer_pre
        reserve = reserve_pre
        extra_h = row_h
        if thin:
            _place_extra_strip(els, spec, extras, language, y=card_y, h=extra_h, id0="meta")
        else:
            _place_extra_cards(
                els,
                spec,
                extras,
                language,
                x=LEFT,
                y=card_y,
                w=WIDTH,
                h=extra_h,
                id0="meta",
                layout="row",
            )
        if reserve and closer:
            _conclusion_band(els, spec, closer, [], card_y + extra_h + 0.10, language)
        add_source(els, spec)
        return els
    els.append(
        text_el(
            f"{spec['slide_id']}_act",
            action,
            BBox(LEFT, CONTENT_TOP, WIDTH, 0.72),
            size=20,
            weight=600,
            order=3,
        )
    )
    card_y = CONTENT_TOP + 0.84
    closer = tw if _distinct(tw, action) else ""
    reserve = _closer_h(closer, language)
    extra_h = row_h
    if thin:
        _place_extra_strip(els, spec, extras, language, y=card_y, h=extra_h, id0="meta")
    else:
        _place_extra_cards(
            els,
            spec,
            extras,
            language,
            x=LEFT,
            y=card_y,
            w=WIDTH,
            h=extra_h,
            id0="meta",
            layout="row",
        )
    if reserve and closer:
        _conclusion_band(els, spec, closer, [], card_y + extra_h + 0.10, language)
    add_source(els, spec)
    return els


def compose_table(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    tbl = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "table"), None) or {}
    cols = [str(c) for c in (tbl.get("columns") or ["A", "B"])][:6]
    rows = tbl.get("rows") or []
    rows = [list(map(str, r))[: len(cols)] for r in rows[:7]]
    closer = _distinct_takeaway(spec)
    reserve = _closer_h(closer, language) if closer else 0.0
    th = CONTENT_BOTTOM - CONTENT_TOP - (reserve + 0.12 if reserve else 0.0)
    tw = WIDTH
    els.append(
        {
            "element_id": f"{spec['slide_id']}_table",
            "kind": "table",
            "bbox": BBox(LEFT, CONTENT_TOP, tw, th).as_dict(),
            "z_index": 15,
            "reading_order": 5,
            "columns": cols,
            "rows": rows,
            "header": True,
            "header_fill": THEME["text_primary"],
            "header_color": THEME["text_inverse"] if THEME["id"] != "ink-ask" else THEME["canvas"],
            "body_fill": THEME["surface"],
            "alt_fill": THEME["surface_muted"],
            "body_color": THEME["text_primary"],
            "border_color": THEME["border"],
        }
    )
    if closer:
        _conclusion_band(els, spec, closer, [], CONTENT_TOP + th + 0.10, language)
    add_source(els, spec)
    return els


def compose_quote(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    q = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "quote"), None) or {}
    text = str(q.get("text") or spec.get("takeaway") or "")
    who = str(q.get("attribution") or q.get("source") or "")
    extras = _payload_items(spec, text, who)[:3]
    closer_q = _distinct_takeaway(spec, text, *extras)
    extra_room = (0.92 * len(extras) + 0.24) if extras else 0.0
    inner_ta = closer_q if closer_q and not extras else ""
    q_size = 34 if len(text) <= 80 else (28 if len(text) <= 120 else 22)
    ta_h = max(0.48, _qa_text_need(inner_ta, WIDTH - 1.70, 18, language, 0.08)) if inner_ta else 0.0
    plant_q = CONTENT_BOTTOM - CONTENT_TOP - extra_room
    txt_h = max(0.46, _qa_text_need(text, WIDTH - 1.70, q_size, language, 0.04))
    who_h = 0.32 if who else 0.0
    hug = 0.28 + txt_h + (0.08 + who_h if who else 0.10) + (0.12 + ta_h if inner_ta else 0.14)
    qh = min(plant_q, hug)
    qy = CONTENT_TOP
    box = BBox(LEFT, qy, WIDTH, qh)
    els.append(shape_el(f"{spec['slide_id']}_qbox", box, THEME["surface"], order=3))
    maybe_chrome(els, f"{spec['slide_id']}_qa", box, 4)
    els.append(
        text_el(
            f"{spec['slide_id']}_qmark",
            "“",
            BBox(LEFT + 0.28, qy + 0.12, 0.72, 0.50),
            size=26,
            weight=700,
            color=THEME["accent"],
            order=5,
        )
    )
    els.append(
        text_el(
            f"{spec['slide_id']}_qtxt",
            text,
            BBox(LEFT + 1.10, qy + 0.16, WIDTH - 1.70, txt_h),
            size=q_size,
            weight=600,
            order=6,
            token="body",
        )
    )
    cursor = qy + 0.16 + txt_h + 0.06
    if who:
        els.append(
            text_el(
                f"{spec['slide_id']}_qwho",
                who,
                BBox(LEFT + 1.10, cursor, WIDTH - 1.70, who_h),
                size=14,
                color=THEME["text_secondary"],
                order=7,
            )
        )
        cursor += who_h + 0.10
    if inner_ta:
        els.append(
            text_el(
                f"{spec['slide_id']}_qta",
                inner_ta,
                BBox(LEFT + 1.10, min(cursor, qy + qh - ta_h - 0.14), WIDTH - 1.70, ta_h),
                size=18,
                color=THEME["text_secondary"],
                order=8,
                token="body",
            )
        )
    if extras:
        ey = qy + qh + 0.12
        fill_h = 0.0
        if len(extras) <= 2:
            gap = 0.12
            for i, it in enumerate(extras):
                csize, eh = _statement_band(it, WIDTH - 0.56, language, min_size=17, max_size=20)
                els.append(shape_el(f"{spec['slide_id']}_qe{i}", BBox(LEFT, ey, WIDTH, eh), THEME["surface_muted"], order=10 + i))
                els.append(
                    text_el(
                        f"{spec['slide_id']}_qet{i}",
                        it,
                        BBox(LEFT + 0.28, ey + 0.12, WIDTH - 0.56, eh - 0.22),
                        size=csize,
                        weight=600,
                        valign="middle",
                        order=20 + i,
                        token="body",
                    )
                )
                ey += eh + gap
        else:
            gap = 0.14
            n = len(extras)
            cw = (WIDTH - gap * (n - 1)) / n
            eh = min(
                1.20,
                max(0.78, max(_qa_text_need(it, cw - 0.36, 14, language, 0.10) for it in extras) + 0.32),
            )
            for i, it in enumerate(extras):
                x = LEFT + i * (cw + gap)
                els.append(shape_el(f"{spec['slide_id']}_qe{i}", BBox(x, ey, cw, eh), THEME["surface_muted"], order=10 + i))
                els.append(
                    text_el(
                        f"{spec['slide_id']}_qet{i}",
                        it,
                        BBox(x + 0.16, ey + 0.14, cw - 0.32, eh - 0.26),
                        size=14,
                        weight=600,
                        valign="middle",
                        order=20 + i,
                        token="body",
                    )
                )
            ey += eh + 0.12
        if closer_q:
            hug_c = fill_h if fill_h else _closer_h(closer_q, language)
            _conclusion_band(
                els,
                spec,
                closer_q,
                [],
                ey,
                language,
                bottom=min(CONTENT_BOTTOM, ey + hug_c),
                height=hug_c,
            )
    add_source(els, spec)
    return els


def compose_chart(spec: dict[str, Any], language: str) -> list[dict[str, Any]]:
    els: list[dict[str, Any]] = []
    add_title(els, spec, language)
    ch = next((b for b in spec.get("content_blocks") or [] if b.get("type") == "chart"), None) or {}
    cats = [str(c) for c in (ch.get("categories") or [])]
    series = ch.get("series") or []
    els.append(
        {
            "element_id": f"{spec['slide_id']}_chart",
            "kind": "chart",
            "bbox": BBox(LEFT, CONTENT_TOP, 8.15, CONTENT_BOTTOM - CONTENT_TOP).as_dict(),
            "z_index": 15,
            "reading_order": 5,
            "chart_type": ch.get("chart_type") or "bar",
            "categories": cats,
            "series": series,
            "highlight": ch.get("highlight_categories") or [],
            "accent": THEME["accent"],
            "accent_dark": THEME["accent_dark"],
        }
    )
    callout = ch.get("conclusion") or spec.get("takeaway") or ""
    call_h = min(2.35, max(1.85, estimate_text_height_in(callout, 3.42, 16, 1.22, language, 0.20) + 0.80))
    box = BBox(8.95, CONTENT_TOP, 3.82, call_h)
    els.append(shape_el(f"{spec['slide_id']}_cc", box, THEME["surface"], order=8))
    maybe_chrome(els, f"{spec['slide_id']}_cca", box, 9)
    els.append(
        text_el(
            f"{spec['slide_id']}_cl",
            rec_label("read", language),
            BBox(9.15, CONTENT_TOP + 0.22, 3.42, 0.32),
            size=12,
            weight=600,
            color=THEME["accent"],
            order=10,
        )
    )
    els.append(
        text_el(
            f"{spec['slide_id']}_ct",
            callout,
            BBox(9.15, CONTENT_TOP + 0.64, 3.42, box.h - 0.88),
            size=16,
            weight=600,
            order=10,
            token="body",
        )
    )
    add_source(els, spec)
    return els


COMPOSERS = {
    "hero_assertion": compose_hero,
    "metric_strip": compose_metrics,
    "comparison_2col": compose_comparison,
    "process_flow": compose_process,
    "recommendation": compose_recommendation,
    "proof_grid": compose_proof_grid,
    "table_focus": compose_table,
    "quote_proof": compose_quote,
    "chart_focus": compose_chart,
}


def compose_slide(
    spec: dict[str, Any],
    language: str,
    *,
    index: int = 1,
    total: int = 1,
    deck_title: str = "",
) -> dict[str, Any]:
    family = select_family(spec, index=index)
    if family == "recommendation":
        els = compose_recommendation(spec, language, closing=(index == total))
    else:
        els = COMPOSERS[family](spec, language)
    meta = next((e for e in els if (e.get("element_id") or "").endswith("_meta")), None)
    flush = bool(meta) and float(meta["bbox"]["y"]) + float(meta["bbox"]["h"]) >= 7.35
    label, fsize, fw, fh = _footer_title(deck_title, language)
    foot_y = 7.18 if flush else (7.48 - fh)
    foot_color = THEME["text_inverse"] if flush else THEME["text_secondary"]
    if not footer_source(spec) and label:
        els.append(
            text_el(
                f"{spec['slide_id']}_deck",
                label,
                BBox(LEFT, foot_y, fw, fh if not flush else 0.28),
                size=fsize,
                color=THEME["text_inverse"] if flush else THEME["text_secondary"],
                valign="middle",
                order=91,
                token="source",
            )
        )
    els.append(
        text_el(
            f"{spec['slide_id']}_pg",
            f"{index:02d}  /  {total:02d}",
            BBox(11.20, foot_y, 1.56, max(0.26, fh if not flush else 0.26)),
            size=10,
            color=foot_color,
            align="right",
            valign="middle",
            order=92,
            token="source",
        )
    )
    return {
        "slide_id": spec["slide_id"],
        "sequence": spec.get("sequence"),
        "layout_family": family,
        "background_color": THEME["canvas"],
        "elements": els,
        "notes": spec.get("speaker_notes"),
        "source_labels": spec.get("source_labels") or [],
    }


def compose_deck(specs: dict[str, Any], title: str | None = None, language: str | None = None) -> dict[str, Any]:
    apply_theme(specs=specs)
    language = language or specs.get("language") or "ko-KR"
    slides_in = specs.get("slides") or specs
    if isinstance(slides_in, dict):
        slides_in = slides_in.get("slides") or []
    deck_title = title or specs.get("title") or ""
    total = len(slides_in)
    slides = [
        compose_slide(s, language, index=i + 1, total=total, deck_title=deck_title)
        for i, s in enumerate(slides_in)
    ]
    raw = json.dumps(specs, ensure_ascii=False, sort_keys=True)
    deck_id = "deck_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return {
        "schema_version": "1.0",
        "deck_id": deck_id,
        "title": title or specs.get("title") or "Untitled",
        "language": language,
        "page_size": "LAYOUT_WIDE",
        "theme_id": THEME["id"],
        "purpose": specs.get("purpose"),
        "slides": slides,
        "assets_manifest_uri": "",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--specs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--title")
    p.add_argument("--language")
    args = p.parse_args()
    specs = load_json(Path(args.specs))
    deck = compose_deck(specs, title=args.title, language=args.language)
    dump_json(Path(args.out), deck)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
