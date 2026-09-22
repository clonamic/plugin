#!/usr/bin/env python3
"""Extract measured colors, fonts, and geometry rhythm from PPTX OOXML."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import zipfile
from collections import Counter
from pathlib import Path

from ooxml_lib import (
    bbox,
    color_counts,
    font_counts,
    shapes,
    slide_names,
    slide_theme_target,
    theme_palette,
    xml,
)


def _rank(counter: Counter[str]) -> list[dict[str, object]]:
    return [{"value": value, "uses": uses} for value, uses in counter.most_common()]


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def extract_design_dna(paths: list[Path]) -> dict:
    slide_colors: Counter[str] = Counter()
    theme_colors: Counter[str] = Counter()
    slide_fonts: Counter[str] = Counter()
    theme_fonts: Counter[str] = Counter()
    lefts: list[float] = []
    tops: list[float] = []
    widths: list[float] = []
    heights: list[float] = []
    gaps: list[float] = []
    sources = []
    slide_count = 0
    per_slide = []
    for path in paths:
        sources.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        with zipfile.ZipFile(path) as archive:
            palette: dict[str, str] = {}
            for name in archive.namelist():
                if name.startswith("ppt/theme/") and name.endswith(".xml"):
                    root = xml(archive, name)
                    theme_colors.update(color_counts(root))
                    theme_fonts.update(font_counts(root))
                    palette.update(theme_palette(root))
            for name in slide_names(archive):
                slide_count += 1
                root = xml(archive, name)
                target = slide_theme_target(archive, name)
                slide_palette = theme_palette(xml(archive, target)) if target else palette
                measured_colors = color_counts(root, slide_palette)
                slide_colors.update(measured_colors)
                slide_fonts.update(font_counts(root))
                per_slide.append(
                    {
                        "source": str(path),
                        "slide": slide_count,
                        "theme_part": target,
                        "colors": [value for value, _ in measured_colors.most_common()],
                    }
                )
                boxes = [box for element in shapes(root) if (box := bbox(element))]
                lefts.extend(box["x"] for box in boxes)
                tops.extend(box["y"] for box in boxes)
                widths.extend(box["w"] for box in boxes)
                heights.extend(box["h"] for box in boxes)
                ordered = sorted(boxes, key=lambda item: (item["y"], item["x"]))
                gaps.extend(
                    round(right["y"] - (left["y"] + left["h"]), 4)
                    for left, right in zip(ordered, ordered[1:])
                    if right["y"] >= left["y"] + left["h"]
                )
    return {
        "schema_version": 1,
        "sources": sources,
        "slide_count": slide_count,
        "colors": {
            "slide_usage": [row["value"] for row in _rank(slide_colors)],
            "slide_ranked": _rank(slide_colors),
            "theme_ranked": _rank(theme_colors),
            "per_slide": per_slide,
        },
        "fonts": {
            "slide_usage": [row["value"] for row in _rank(slide_fonts)],
            "slide_ranked": _rank(slide_fonts),
            "theme_ranked": _rank(theme_fonts),
        },
        "layout_rhythm": {
            "median_left_in": _median(lefts),
            "median_top_in": _median(tops),
            "median_width_in": _median(widths),
            "median_height_in": _median(heights),
            "median_vertical_gap_in": _median(gaps),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", nargs="+")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = extract_design_dna([Path(path) for path in args.pptx])
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
