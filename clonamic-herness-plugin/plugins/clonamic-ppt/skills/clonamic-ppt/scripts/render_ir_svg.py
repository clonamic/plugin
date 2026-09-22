#!/usr/bin/env python3
"""Render bounded, dependency-free DeckIR SVG previews for QA only."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


PX = 100
WIDTH = 1333
HEIGHT = 750


def _box(element: dict) -> tuple[float, float, float, float]:
    box = element.get("bbox") or {}
    x = max(0.0, min(float(box.get("x", 0)) * PX, WIDTH))
    y = max(0.0, min(float(box.get("y", 0)) * PX, HEIGHT))
    w = max(0.0, min(float(box.get("w", 0)) * PX, WIDTH - x))
    h = max(0.0, min(float(box.get("h", 0)) * PX, HEIGHT - y))
    return x, y, w, h


def _color(value: object, fallback: str = "FFFFFF") -> str:
    raw = str(value or "").removeprefix("#").upper()
    safe_fallback = str(fallback).removeprefix("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", safe_fallback):
        safe_fallback = "FFFFFF"
    return f"#{raw}" if re.fullmatch(r"[0-9A-F]{6}", raw) else f"#{safe_fallback}"


def _text(element: dict) -> str:
    if element.get("kind") == "table":
        values = list(element.get("columns") or [])
        values.extend(str(cell) for row in element.get("rows") or [] for cell in row)
        return " · ".join(values)
    if element.get("kind") == "chart":
        values = list(element.get("categories") or [])
        for series in element.get("series") or []:
            values.append(str(series.get("name", "")))
            values.extend(str(value) for value in series.get("values") or [])
        return " · ".join(values)
    return str(element.get("text") or "")


def _render_element(element: dict) -> str:
    x, y, w, h = _box(element)
    eid = html.escape(str(element.get("element_id") or "element"), quote=True)
    kind = element.get("kind")
    if kind == "shape":
        fill = _color((element.get("fill") or {}).get("color"))
        if element.get("shape_type") == "ellipse":
            return f'<ellipse id="{eid}" cx="{x + w / 2:.2f}" cy="{y + h / 2:.2f}" rx="{w / 2:.2f}" ry="{h / 2:.2f}" fill="{fill}"/>'
        return f'<rect id="{eid}" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="6" fill="{fill}"/>'
    stroke = "#D1D5DB" if kind in {"table", "chart"} else "none"
    frame = f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="none" stroke="{stroke}"/>'
    style = element.get("style") or {}
    size = max(8.0, min(float(style.get("font_size_pt", 14)) * 1.33, 72.0))
    color = _color(style.get("color"), "111827")
    value = html.escape(_text(element))
    text = f'<text x="{x + 4:.2f}" y="{min(y + size, y + h):.2f}" font-size="{size:.2f}" fill="{color}">{value}</text>'
    return f'<g id="{eid}">{frame}{text}</g>'


def render_ir_svg(deck: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    slides = sorted(deck.get("slides") or [], key=lambda slide: slide.get("sequence", 0))
    for number, slide in enumerate(slides, 1):
        background = _color(slide.get("background_color"), "FFFFFF")
        elements = sorted(slide.get("elements") or [], key=lambda element: element.get("z_index", 0))
        body = "".join(_render_element(element) for element in elements)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1333" height="750" viewBox="0 0 1333 750">'
            f'<rect width="1333" height="750" fill="{background}"/>{body}</svg>\n'
        )
        path = out_dir / f"slide-{number:03d}.svg"
        path.write_text(svg, encoding="utf-8")
        rows.append(
            {
                "slide_id": slide.get("slide_id"),
                "sequence": slide.get("sequence"),
                "path": str(path),
                "element_count": len(elements),
            }
        )
    manifest = {"schema_version": 1, "qa_only": True, "slides": rows}
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    deck = json.loads(Path(args.ir).read_text(encoding="utf-8"))
    render_ir_svg(deck, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
