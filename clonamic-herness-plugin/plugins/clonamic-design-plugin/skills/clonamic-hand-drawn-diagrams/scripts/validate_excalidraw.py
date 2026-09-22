"""Validate an Excalidraw JSON file before encoding or rendering.

Exit 0 = valid (prints OK summary)
Exit 1 = invalid (prints all errors found, each with element id)

Usage:
    cd {skill-root}/scripts
    uv run python validate_excalidraw.py "/absolute/path/to/file.excalidraw"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _id_map(elements: list[dict]) -> dict[str, dict]:
    return {el["id"]: el for el in elements if isinstance(el, dict) and "id" in el}


def _estimate_text_px_width(text: str, font_size: float) -> float:
    """Rough single-line width estimate: average char ≈ 0.55× font size."""
    longest_line = max((len(ln) for ln in text.split("\n")), default=0)
    return longest_line * font_size * 0.55


# ---------------------------------------------------------------------------
# Individual checks  (each returns a list of error strings)
# ---------------------------------------------------------------------------

def check_file_structure(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["FAIL: root JSON value is not an object"]
    if data.get("type") != "excalidraw":
        errors.append('FAIL: root "type" is not "excalidraw"')
    if "elements" not in data:
        errors.append('FAIL: file has no "elements" key')
    elif not isinstance(data["elements"], list):
        errors.append('FAIL: "elements" is not a list')
    elif len(data["elements"]) == 0:
        errors.append("FAIL: elements array is empty — diagram was never written")
    return errors


def check_element_shapes(elements: list[dict]) -> list[str]:
    """Reject malformed element records before semantic checks access their fields."""
    errors: list[str] = []
    numeric = (int, float)
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            errors.append(f"FAIL: element at index {index} is not an object")
            continue
        eid = element.get("id", f"index:{index}")
        for field in ("x", "y"):
            value = element.get(field)
            if field in element and (isinstance(value, bool) or not isinstance(value, numeric)):
                errors.append(f'FAIL: element "{eid}" {field} is not numeric')
        for field in ("width", "height"):
            if field not in element:
                continue
            value = element[field]
            if isinstance(value, bool) or not isinstance(value, numeric):
                errors.append(f'FAIL: element "{eid}" {field} is not numeric')
            elif value < 0:
                errors.append(f'FAIL: element "{eid}" {field} is negative')
    return errors


def check_deleted_elements(elements: list[dict]) -> list[str]:
    """Deleted elements should not appear in a freshly generated file."""
    errors: list[str] = []
    deleted = [el.get("id", "?") for el in elements if el.get("isDeleted") is True]
    for eid in deleted:
        errors.append(
            f'FAIL: element "{eid}" has isDeleted:true — remove it from the output'
        )
    return errors


def check_unique_ids(elements: list[dict]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, int] = {}
    for el in elements:
        eid = el.get("id", "MISSING_ID")
        seen[eid] = seen.get(eid, 0) + 1
    for eid, count in seen.items():
        if count > 1:
            errors.append(f'FAIL: id "{eid}" appears {count} times — ids must be unique')
    return errors


def check_container_bindings(elements: list[dict], id_map: dict) -> list[str]:
    """Every containerId must resolve; container's boundElements must list the text back."""
    errors: list[str] = []
    for el in elements:
        eid = el.get("id", "?")
        cid = el.get("containerId")
        if cid and cid not in id_map:
            errors.append(
                f'FAIL: element "{eid}" has containerId "{cid}" '
                f"but no element with that id exists"
            )
        # If this element is a container, verify its boundElements reference real ids
        bound = el.get("boundElements") or []
        for ref in bound:
            ref_id = ref.get("id") if isinstance(ref, dict) else ref
            if ref_id and ref_id not in id_map:
                errors.append(
                    f'FAIL: container "{eid}" boundElements references "{ref_id}" '
                    f"which does not exist"
                )
    return errors


def check_arrow_bindings(elements: list[dict], id_map: dict) -> list[str]:
    """startBinding / endBinding must point to real elements."""
    errors: list[str] = []
    for el in elements:
        if el.get("type") != "arrow":
            continue
        eid = el.get("id", "?")
        for side in ("startBinding", "endBinding"):
            binding = el.get(side)
            if binding and isinstance(binding, dict):
                target = binding.get("elementId")
                if target and target not in id_map:
                    errors.append(
                        f'FAIL: arrow "{eid}" {side}.elementId="{target}" '
                        f"does not exist"
                    )
    return errors


def check_canvas_bounds(elements: list[dict]) -> list[str]:
    """Elements with very negative coordinates are effectively off-canvas."""
    errors: list[str] = []
    for el in elements:
        if el.get("type") in ("arrow", "line"):
            continue  # points-based, skip simple x/y check
        eid = el.get("id", "?")
        x = el.get("x", 0)
        y = el.get("y", 0)
        if x < -200:
            errors.append(
                f'FAIL: element "{eid}" x={x} is far off-canvas (< -200)'
            )
        if y < -200:
            errors.append(
                f'FAIL: element "{eid}" y={y} is far off-canvas (< -200)'
            )
    return errors


def check_coordinate_spread(elements: list[dict]) -> list[str]:
    """If all non-arrow shapes are within a 200×200 box they are probably stacked."""
    errors: list[str] = []
    containers = [
        el for el in elements
        if el.get("type") in ("rectangle", "ellipse", "diamond", "frame", "text")
        and el.get("containerId") is None  # skip bound text
    ]
    if len(containers) < 3:
        return errors
    xs = [el.get("x", 0) for el in containers]
    ys = [el.get("y", 0) for el in containers]
    spread_x = max(xs) - min(xs)
    spread_y = max(ys) - min(ys)
    if spread_x < 200 and spread_y < 200:
        errors.append(
            f"FAIL: all top-level shapes are within a {spread_x:.0f}×{spread_y:.0f}px area "
            f"— elements are likely stacked on top of each other. "
            f"Spread them across the canvas (aim for ≥400px in at least one axis)."
        )
    return errors


def check_coordinate_collisions(elements: list[dict]) -> list[str]:
    """Reject identical or substantially intersecting top-level shape bounds."""
    errors: list[str] = []
    shapes: list[dict] = []
    for el in elements:
        if el.get("type") in ("arrow", "line", "text", "frame"):
            continue
        if el.get("containerId") or el.get("frameId"):
            continue
        if (el.get("customData") or {}).get("clxAllowOverlap") is True:
            continue
        if any(el.get(field) is None for field in ("x", "y", "width", "height")):
            continue
        shapes.append(el)
    for index, left in enumerate(shapes):
        lx, ly, lw, lh = (float(left[field]) for field in ("x", "y", "width", "height"))
        if lw <= 0 or lh <= 0:
            continue
        for right in shapes[index + 1:]:
            if set(left.get("groupIds") or ()) & set(right.get("groupIds") or ()):
                continue
            rx, ry, rw, rh = (float(right[field]) for field in ("x", "y", "width", "height"))
            if rw <= 0 or rh <= 0:
                continue
            overlap_w = max(0.0, min(lx + lw, rx + rw) - max(lx, rx))
            overlap_h = max(0.0, min(ly + lh, ry + rh) - max(ly, ry))
            ratio = overlap_w * overlap_h / min(lw * lh, rw * rh)
            if ratio > 0.0:
                errors.append(
                    f'FAIL: elements "{left.get("id", "?")}" and "{right.get("id", "?")}" '
                    f'overlap {ratio:.0%} of the smaller shape — separate them or mark an '
                    f'intentional reviewed overlap with customData.clxAllowOverlap=true'
                )
    return errors


def check_text_overflow(elements: list[dict], id_map: dict) -> list[str]:
    """Estimate whether text is wider than its container or its own declared width."""
    errors: list[str] = []
    for el in elements:
        if el.get("type") != "text":
            continue
        eid = el.get("id", "?")
        text = el.get("text") or el.get("originalText") or ""
        font_size = el.get("fontSize", 16)
        declared_width = el.get("width", 9999)
        estimated = _estimate_text_px_width(text, font_size)

        # Check against declared text width (only flags obviously wrong values)
        if el.get("autoResize") is not True and estimated > declared_width * 1.4:
            errors.append(
                f'FAIL: text "{eid}" estimated width {estimated:.0f}px '
                f'exceeds declared width {declared_width}px '
                f'(text: "{text[:40]}..."). '
                f'Either set autoResize:true or widen the container.'
            )

        # Check against container width
        cid = el.get("containerId")
        if cid and cid in id_map:
            container = id_map[cid]
            container_width = container.get("width", 9999)
            if estimated > container_width * 1.3:
                errors.append(
                    f'FAIL: text "{eid}" estimated width {estimated:.0f}px '
                    f'likely overflows container "{cid}" '
                    f'(container width: {container_width}px). '
                    f'Shorten the text or widen the container.'
                )
    return errors


def check_required_fields(elements: list[dict]) -> list[str]:
    """Every element must have type, id, x, y."""
    errors: list[str] = []
    required = ("type", "id", "x", "y")
    for i, el in enumerate(elements):
        for field in required:
            if field not in el:
                eid = el.get("id", f"index:{i}")
                errors.append(
                    f'FAIL: element "{eid}" is missing required field "{field}"'
                )
    return errors


def check_font_family(elements: list[dict]) -> list[str]:
    """Text elements should use fontFamily:1 (Virgil hand-drawn font)."""
    errors: list[str] = []
    for el in elements:
        if el.get("type") == "text":
            eid = el.get("id", "?")
            ff = el.get("fontFamily")
            if ff is not None and ff != 1:
                errors.append(
                    f'WARN: text "{eid}" uses fontFamily:{ff} '
                    f"— should be 1 (Virgil) for hand-drawn style"
                )
    return errors


def check_roughness(elements: list[dict]) -> list[str]:
    """All non-text elements should use roughness:1."""
    errors: list[str] = []
    for el in elements:
        if el.get("type") == "text":
            continue
        eid = el.get("id", "?")
        r = el.get("roughness")
        if r is not None and r == 0 and el.get("type") != "frame":
            errors.append(
                f'WARN: element "{eid}" (type:{el.get("type")}) has roughness:0 '
                f"— use roughness:1 for hand-drawn style"
            )
    return errors


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def validate(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). errors = must-fix. warnings = should-fix."""
    errors: list[str] = []
    warnings: list[str] = []

    # Load file
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"FAIL: file not found: {path}"], []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"FAIL: invalid JSON — {exc}"], []

    # Structure check first; if elements are missing we cannot do further checks
    struct_errors = check_file_structure(data)
    if struct_errors:
        return struct_errors, []

    elements: list[dict] = data["elements"]
    shape_errors = check_element_shapes(elements)
    if shape_errors:
        return shape_errors, []
    id_map = _id_map(elements)

    # Hard errors
    errors += check_required_fields(elements)
    errors += check_unique_ids(elements)
    errors += check_deleted_elements(elements)
    errors += check_container_bindings(elements, id_map)
    errors += check_arrow_bindings(elements, id_map)
    errors += check_canvas_bounds(elements)
    errors += check_coordinate_spread(elements)
    errors += check_coordinate_collisions(elements)
    errors += check_text_overflow(elements, id_map)

    # Style warnings
    warnings += check_font_family(elements)
    warnings += check_roughness(elements)

    return errors, warnings


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python validate_excalidraw.py <file.excalidraw>")
        sys.exit(1)

    path = Path(sys.argv[1])
    errors, warnings = validate(path)

    element_count = 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        element_count = len(data.get("elements", []))
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"Validating: {path.name}")
    print(f"{'='*60}")

    if warnings:
        print(f"\n⚠  {len(warnings)} style warning(s):")
        for w in warnings:
            print(f"   {w}")

    if errors:
        print(f"\n✗  {len(errors)} error(s) — diagram must be fixed before encoding:\n")
        for e in errors:
            print(f"   {e}")
        print(f"\n{'='*60}")
        print("RESULT: INVALID — fix errors above then re-run validate_excalidraw.py")
        print(f"{'='*60}\n")
        sys.exit(1)
    else:
        print(f"\n✓  {element_count} elements, 0 errors")
        if warnings:
            print("   (style warnings above are non-blocking)")
        print(f"\n{'='*60}")
        print("RESULT: STRUCTURALLY VALID — rendered visual review is still required")
        print(f"{'='*60}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
