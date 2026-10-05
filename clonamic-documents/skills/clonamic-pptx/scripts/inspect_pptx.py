#!/usr/bin/env python3
"""Static layout check and summary for a .pptx file (standard library only).

Errors (exit 1): OUT_OF_BOUNDS, TEXT_OVERLAP, BROKEN_FILE.
Warnings: SMALL_FONT, LIKELY_OVERFLOW, EMPTY_PLACEHOLDER.
"""

from __future__ import annotations

import argparse
import json
import math
import posixpath
import re
import statistics
import sys
import unicodedata
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EMU_PER_IN = 914400
DEFAULT_PT = 18.0
TOLERANCE_IN = 0.01
OVERLAP_MIN_SHARE = 0.02


def q(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


def slide_paths(zf: zipfile.ZipFile) -> list[str]:
    """Slides in presentation order (sldIdLst + rels), falling back to numeric file order."""
    names = set(zf.namelist())
    try:
        pres = ET.fromstring(zf.read("ppt/presentation.xml"))
        rels = ET.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels.iter(q("rel:Relationship"))}
        ordered = []
        for sld in pres.iter(q("p:sldId")):
            target = targets.get(sld.get(q("r:id")), "")
            path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("ppt", target))
            if path in names:
                ordered.append(path)
        if ordered:
            return ordered
    except (KeyError, ET.ParseError):
        pass
    found = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
    return sorted(found, key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))


def slide_size(zf: zipfile.ZipFile) -> tuple[float, float]:
    try:
        size = ET.fromstring(zf.read("ppt/presentation.xml")).find(q("p:sldSz"))
        return int(size.get("cx")) / EMU_PER_IN, int(size.get("cy")) / EMU_PER_IN
    except (KeyError, AttributeError, TypeError, ET.ParseError):
        return 13.333, 7.5


def bbox(shape: ET.Element) -> tuple[float, float, float, float] | None:
    xfrm = shape.find(".//" + q("a:xfrm"))
    if xfrm is None:
        xfrm = shape.find(".//" + q("p:xfrm"))
    if xfrm is None:
        return None
    off, ext = xfrm.find(q("a:off")), xfrm.find(q("a:ext"))
    if off is None or ext is None:
        return None
    x, y = int(off.get("x", 0)) / EMU_PER_IN, int(off.get("y", 0)) / EMU_PER_IN
    return x, y, int(ext.get("cx", 0)) / EMU_PER_IN, int(ext.get("cy", 0)) / EMU_PER_IN


def resolve(zf: zipfile.ZipFile, part: str, kind: str) -> str | None:
    """Follow a part's relationship of the given kind (slideLayout, slideMaster) to its path."""
    for target in _rels_targets(zf, part):
        if kind in target:
            return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
    return None


def placeholder_boxes(zf: zipfile.ZipFile, part: str | None) -> dict[tuple[str, str], tuple[float, float, float, float]]:
    """Placeholder frames of a layout or master, keyed by ("idx", n) and ("type", t)."""
    boxes: dict[tuple[str, str], tuple[float, float, float, float]] = {}
    if not part:
        return boxes
    try:
        root = ET.fromstring(zf.read(part))
    except (KeyError, ET.ParseError):
        return boxes
    for shape in root.iter(q("p:sp")):
        ph = shape.find(".//" + q("p:nvPr") + "/" + q("p:ph"))
        box = bbox(shape)
        if ph is None or box is None:
            continue
        boxes.setdefault(("idx", ph.get("idx", "0")), box)
        boxes.setdefault(("type", ph.get("type", "body")), box)
    return boxes


def inherited_box(ph: ET.Element, layout: dict, master: dict) -> tuple[float, float, float, float] | None:
    kind = ph.get("type", "body")
    for table in (layout, master):
        for key in (("idx", ph.get("idx", "0")), ("type", kind)):
            if key in table and (key[0] == "type" or kind not in ("title", "ctrTitle")):
                return table[key]
    if kind == "ctrTitle":
        return master.get(("type", "title"))
    return None


def paragraphs(shape: ET.Element) -> list[tuple[str, list[float]]]:
    result = []
    body = shape.find(q("p:txBody"))
    if body is None:
        return result
    for para in body.iter(q("a:p")):
        text = "".join(t.text or "" for t in para.iter(q("a:t")))
        sizes = [int(rpr.get("sz")) / 100 for rpr in para.iter() if rpr.tag in (q("a:rPr"), q("a:endParaRPr")) and rpr.get("sz")]
        result.append((text, sizes))
    return result


def text_width_em(text: str) -> float:
    return sum(1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.55 for ch in text)


def estimated_height_in(paras: list[tuple[str, list[float]]], width_in: float) -> float:
    usable = max(width_in - 0.2, 0.1)  # default left/right insets 0.1 in
    total = 0.0
    for text, sizes in paras:
        size = max(sizes) if sizes else DEFAULT_PT
        line_width = usable * 72 / size  # em per line
        lines = max(1, math.ceil(text_width_em(text) / line_width)) if text else 1
        total += lines * size * 1.2 / 72
    return total + 0.1  # default top/bottom insets 0.05 in


def overlap_share(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min(a[2] * a[3], b[2] * b[3]) or 1e-9
    return w * h / smaller


def inspect(path: str, min_font: float) -> dict:
    issues: list[dict] = []
    slides: list[dict] = []
    fonts: Counter[str] = Counter()
    sizes: Counter[float] = Counter()
    colors: Counter[str] = Counter()
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return {"file": path, "slides": [], "issues": [{"level": "error", "code": "BROKEN_FILE", "slide": None, "message": str(exc)}]}
    with zf:
        width, height = slide_size(zf)
        for index, name in enumerate(slide_paths(zf), start=1):
            sid = f"s{index:02d}"

            def add(level: str, code: str, message: str) -> None:
                issues.append({"level": level, "code": code, "slide": sid, "message": message})

            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError as exc:
                add("error", "BROKEN_FILE", f"{name}: {exc}")
                continue
            tree = root.find(q("p:cSld")).find(q("p:spTree"))
            layout_part = resolve(zf, name, "slideLayout")
            layout = placeholder_boxes(zf, layout_part)
            master = placeholder_boxes(zf, resolve(zf, layout_part, "slideMaster") if layout_part else None)
            title, words, texts = "", 0, []
            # Top-level shapes only; a group is checked by its own frame.
            for shape in list(tree):
                if shape.tag not in (q("p:sp"), q("p:pic"), q("p:graphicFrame"), q("p:grpSp"), q("p:cxnSp")):
                    continue
                nv = shape.find(".//" + q("p:cNvPr"))
                label = (nv.get("name") if nv is not None else None) or shape.tag.split("}")[1]
                box = bbox(shape)
                ph = shape.find(".//" + q("p:nvPr") + "/" + q("p:ph"))
                if box is None and ph is not None:
                    box = inherited_box(ph, layout, master)
                if box and (box[0] < -TOLERANCE_IN or box[1] < -TOLERANCE_IN
                            or box[0] + box[2] > width + TOLERANCE_IN or box[1] + box[3] > height + TOLERANCE_IN):
                    add("error", "OUT_OF_BOUNDS", f"'{label}' at x={box[0]:.2f} y={box[1]:.2f} w={box[2]:.2f} h={box[3]:.2f} in")
                for el in shape.iter():
                    if el.tag in (q("a:latin"), q("a:ea")) and el.get("typeface") and not el.get("typeface").startswith("+"):
                        fonts[el.get("typeface")] += 1
                    elif el.tag == q("a:srgbClr") and el.get("val"):
                        colors[el.get("val").upper()] += 1
                if shape.tag != q("p:sp"):
                    continue
                paras = paragraphs(shape)
                text = "\n".join(t for t, _ in paras).strip()
                if ph is not None and ph.get("type") in ("title", "ctrTitle") and not title:
                    title = text
                if ph is not None and not text:
                    add("warning", "EMPTY_PLACEHOLDER", f"'{label}' has no text")
                if not text:
                    continue
                words += len(text.split())
                for _, run_sizes in paras:
                    for size in run_sizes:
                        sizes[size] += 1
                        if size < min_font:
                            add("warning", "SMALL_FONT", f"'{label}' uses {size:g}pt (< {min_font:g}pt)")
                if box:
                    texts.append((label, box))
                    body_pr = shape.find(".//" + q("a:bodyPr"))
                    if body_pr is not None and body_pr.get("wrap") == "none":
                        longest = max(text_width_em(t) * (max(z) if z else DEFAULT_PT) / 72 for t, z in paras)
                        if longest > box[2] - 0.2:
                            add("warning", "LIKELY_OVERFLOW", f"'{label}' unwrapped line ~{longest:.2f} in wide, box is {box[2]:.2f} in")
                    else:
                        need = estimated_height_in(paras, box[2])
                        if need > box[3] * 1.1:
                            add("warning", "LIKELY_OVERFLOW", f"'{label}' needs ~{need:.2f} in, box is {box[3]:.2f} in")
            for i, (la, a) in enumerate(texts):
                for lb, b in texts[i + 1:]:
                    if overlap_share(a, b) > OVERLAP_MIN_SHARE:
                        add("error", "TEXT_OVERLAP", f"'{la}' overlaps '{lb}'")
            notes = any("notesSlide" in n for n in _rels_targets(zf, name))
            slides.append({"slide": sid, "title": title, "words": words, "text_boxes": len(texts), "notes": notes})
    word_counts = [s["words"] for s in slides]
    return {
        "file": path,
        "slide_size_in": [round(width, 3), round(height, 3)],
        "slide_count": len(slides),
        "median_words_per_slide": math.ceil(statistics.median(word_counts)) if word_counts else 0,
        "fonts": dict(fonts.most_common(6)),
        "font_sizes_pt": dict(sorted(sizes.items())),
        "colors": dict(colors.most_common(8)),
        "slides": slides,
        "issues": issues,
    }


def _rels_targets(zf: zipfile.ZipFile, slide: str) -> list[str]:
    rels = posixpath.join(posixpath.dirname(slide), "_rels", posixpath.basename(slide) + ".rels")
    try:
        return [r.get("Target", "") for r in ET.fromstring(zf.read(rels)).iter(q("rel:Relationship"))]
    except (KeyError, ET.ParseError):
        return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pptx")
    parser.add_argument("--min-font", type=float, default=10.0, help="warn below this size in pt (default 10)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)
    report = inspect(args.pptx, args.min_font)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"{report['file']}: {report.get('slide_count', 0)} slides, size {report.get('slide_size_in')}")
        for slide in report["slides"]:
            print(f"  {slide['slide']}  words={slide['words']:<4} {slide['title'][:60]}")
        for item in report["issues"]:
            print(f"  [{item['level']}] {item['code']} {item['slide'] or ''} {item['message']}")
        errors = sum(1 for i in report["issues"] if i["level"] == "error")
        print(f"errors={errors} warnings={len(report['issues']) - errors}")
    return 1 if any(i["level"] == "error" for i in report["issues"]) else 0


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        sys.exit("Python 3.12+ is required")
    raise SystemExit(main())
