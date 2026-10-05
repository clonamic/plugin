#!/usr/bin/env python3
"""Structural check for a hand-written .excalidraw file.

Usage:
    python3 check_excalidraw.py FILE [--json]

Errors (exit 1): not an Excalidraw scene, missing/duplicate ids, missing geometry, dangling
container/bound/arrow references, arrows without at least two points.
Warnings (exit 0): soft-deleted elements, shapes that overlap without one containing the other,
text that likely overflows its container, text bound to a shape that does not list it back.
Exit 2: unreadable file or invalid JSON. Standard library only; requires Python 3.12+.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

if sys.version_info < (3, 12):
    sys.exit("check_excalidraw.py needs Python 3.12+; install it (for example `uv python install 3.12`).")

SHAPES = {"rectangle", "ellipse", "diamond", "frame", "image"}
LINEAR = {"arrow", "line", "freedraw"}
GEOMETRY = ("x", "y", "width", "height")


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def text_width(text: str, font_size: float) -> float:
    """Estimate the widest line: full-width (CJK/Hangul) glyphs ~1.0em, others ~0.6em."""
    widest = 0.0
    for line in text.split("\n"):
        ems = sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.6 for ch in line)
        widest = max(widest, ems * font_size)
    return widest


def box(element: dict) -> tuple[float, float, float, float]:
    x, y, w, h = (float(element[key]) for key in GEOMETRY)
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    return x, y, x + w, y + h


def contains(outer: tuple, inner: tuple) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def overlaps(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check(scene: object) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(scene, dict) or scene.get("type") != "excalidraw":
        return ["root: expected an object with \"type\": \"excalidraw\""], warnings
    elements = scene.get("elements")
    if not isinstance(elements, list) or not elements:
        return ["root: \"elements\" must be a non-empty list"], warnings

    by_id: dict[str, dict] = {}
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            errors.append(f"elements[{index}]: not an object")
            continue
        element_id = element.get("id")
        label = element_id if isinstance(element_id, str) and element_id else f"elements[{index}]"
        if not isinstance(element_id, str) or not element_id:
            errors.append(f"{label}: missing id")
        elif element_id in by_id:
            errors.append(f"{label}: duplicate id")
        else:
            by_id[element_id] = element
        if not isinstance(element.get("type"), str):
            errors.append(f"{label}: missing type")
        missing = [key for key in GEOMETRY if not is_number(element.get(key))]
        if missing:
            errors.append(f"{label}: missing numeric {', '.join(missing)}")
        if element.get("type") in LINEAR:
            points = element.get("points")
            if not isinstance(points, list) or len(points) < 2:
                errors.append(f"{label}: {element.get('type')} needs at least two points")
        if element.get("isDeleted") is True:
            warnings.append(f"{label}: soft-deleted element left in the file")

    live = {key: value for key, value in by_id.items() if value.get("isDeleted") is not True}
    for element_id, element in live.items():
        container_id = element.get("containerId")
        if container_id is not None:
            container = live.get(container_id)
            if container is None:
                errors.append(f"{element_id}: containerId {container_id!r} not found")
            else:
                listed = {ref.get("id") for ref in container.get("boundElements") or [] if isinstance(ref, dict)}
                if element_id not in listed:
                    warnings.append(f"{element_id}: container {container_id!r} does not list it in boundElements")
                if element.get("type") == "text" and container.get("type") in SHAPES and is_number(container.get("width")):
                    size = element.get("fontSize") if is_number(element.get("fontSize")) else 20
                    needed = text_width(str(element.get("text", "")), float(size))
                    if needed > abs(float(container["width"])) - 10:
                        warnings.append(
                            f"{element_id}: text needs ~{needed:.0f}px but container {container_id!r} "
                            f"is {abs(float(container['width'])):.0f}px wide"
                        )
        for ref in element.get("boundElements") or []:
            ref_id = ref.get("id") if isinstance(ref, dict) else None
            if ref_id not in live:
                errors.append(f"{element_id}: boundElements references missing {ref_id!r}")
        for side in ("startBinding", "endBinding"):
            binding = element.get(side)
            if isinstance(binding, dict) and binding.get("elementId") not in live:
                errors.append(f"{element_id}: {side} references missing {binding.get('elementId')!r}")

    shapes = [
        (element_id, box(element))
        for element_id, element in live.items()
        if element.get("type") in SHAPES - {"frame"} and all(is_number(element.get(k)) for k in GEOMETRY)
    ]
    for i, (first_id, first) in enumerate(shapes):
        for second_id, second in shapes[i + 1 :]:
            if overlaps(first, second) and not (contains(first, second) or contains(second, first)):
                warnings.append(f"{first_id}: overlaps {second_id}")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check an .excalidraw file's structure.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        scene = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    errors, warnings = check(scene)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False))
    else:
        for line in errors:
            print(f"ERROR {line}")
        for line in warnings:
            print(f"WARN  {line}")
        count = len(scene.get("elements", [])) if isinstance(scene, dict) else 0
        print(f"{'OK' if not errors else 'FAIL'}: {count} elements, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
