"""Deck checks for the agent's verify step (format.md §9.6): [{level, code, id, page, message}]."""

from __future__ import annotations

from typing import Callable

import ops

WHITE = "#FFFFFFFF"
UNKNOWN = "?"  # topmost paint is an image or gradient: no contrast verdict


def resolved(node: dict) -> dict:
    return ops.defaults(node["type"]) | node["props"]


def auto_sized(node: dict) -> tuple[bool, bool]:
    """(width, height) the renderer lays out itself: auto-resize text, HUG auto-layout frames/pages."""
    p = resolved(node)
    if node["type"] == "text":
        return p["autoResize"] == "WIDTH_AND_HEIGHT", p["autoResize"] in ("WIDTH_AND_HEIGHT", "HEIGHT")
    layout = p.get("layout") or {}
    return layout.get("sizingH") == "HUG", layout.get("sizingV") == "HUG"


def laid_out(node: dict) -> bool:
    """Auto layout places this container's children (render.js autoLayout)."""
    return ((node["props"].get("layout") or {}).get("dir") or "NONE") != "NONE"


def in_flow(by: dict, nid: str) -> bool:
    """The renderer positions this node or one of its ancestors by auto layout, so stored x, y are not where it is."""
    while nid in by and by[nid]["type"] != "page":
        n = by[nid]
        parent = by.get(n["parent"])
        if parent and laid_out(parent) and not (n["props"].get("layoutChild") or {}).get("absolute"):
            return True
        nid = n["parent"]
    return False


def boxes(nodes: list[dict]) -> dict[str, tuple[float, float, float, float, str | None]]:
    """id → (x, y, w, h, page id) in page coordinates (rotation ignored)."""
    by = {n["id"]: n for n in nodes}
    out: dict = {}

    def box(nid: str):
        if nid not in out:
            n, p = by[nid], resolved(by[nid])
            if n["type"] == "page":
                out[nid] = (0, 0, p["w"], p["h"], nid)
            else:
                parent = by.get(n["parent"])
                px, py, _, _, page = box(parent["id"]) if parent else (0, 0, 0, 0, None)
                out[nid] = (px + p["x"], py + p["y"], p["w"], p["h"], page)
        return out[nid]

    for nid in by:
        box(nid)
    return out


def top_paint(props: dict) -> str | None:
    """Color of the topmost visible fill if it is SOLID, UNKNOWN for other paints, None without fills."""
    shown = [f for f in props.get("fills", []) if f.get("visible", True)]
    if not shown:
        return None
    return shown[-1]["color"] if shown[-1]["type"] == "SOLID" else UNKNOWN


def text_color(props: dict) -> str | None:
    """Node text color: the first visible SOLID fill."""
    return next((f["color"] for f in props.get("fills", []) if f.get("visible", True) and f["type"] == "SOLID"), None)


def luminance(color: str) -> float:
    def channel(i: int) -> float:
        v = int(color[i:i + 2], 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def overlap(a, b) -> float:
    return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))


def lint(nodes: list[dict], pages: list[str], measure: dict | None = None,
         has_asset: Callable[[str], bool] = lambda h: True) -> list[dict]:
    by = {n["id"]: n for n in nodes}
    box = boxes(nodes)
    kids: dict = {}
    for n in sorted(nodes, key=lambda n: (n["z"], n["id"])):
        kids.setdefault(n["parent"], []).append(n)
    props = {n["id"]: resolved(n) for n in nodes}
    shown = [n for n in nodes if n["type"] != "page" and box[n["id"]][4] in pages and props[n["id"]]["visible"]]
    visible_ids = {n["id"] for n in shown}
    issues: list[dict] = []

    def add(level: str, code: str, n: dict, message: str) -> None:
        issues.append({"level": level, "code": code, "id": n["id"], "page": box[n["id"]][4], "message": message})

    def background(nid: str) -> str:
        """Nearest solid fill under the node: an overlapping sibling below, else the parent, going up."""
        target, cur = box[nid], nid
        while by[cur]["parent"] is not None:
            parent = by[cur]["parent"]
            # a text's fills color its glyphs, not a backdrop; auto layout lays siblings side by side
            below = [] if laid_out(by[parent]) else [s for s in kids[parent] if (s["z"], s["id"]) < (by[cur]["z"], cur) and s["type"] != "text"]
            for s in reversed(below):
                if props[s["id"]]["visible"] and overlap(box[s["id"]], target) > 0 and top_paint(props[s["id"]]):
                    return top_paint(props[s["id"]])
            if top_paint(props[parent]):
                return top_paint(props[parent])
            cur = parent
        return WHITE

    for n in shown:
        p, (x, y, w, h, page) = props[n["id"]], box[n["id"]]
        pw, ph = props[page]["w"], props[page]["h"]
        inside = overlap((x, y, w, h), (0, 0, pw, ph))
        if w * h > 0 and inside < w * h * 0.9:
            add("error", "outside", n, "페이지 밖에 있습니다." if inside == 0 else "10% 넘게 페이지 밖으로 나갔습니다.")
        elif w * h == 0 and (x + w < 0 or y + h < 0 or x > pw or y > ph):
            add("error", "outside", n, "페이지 밖에 있습니다.")
        hashes = [f.get("asset") for f in p.get("fills", []) + p.get("strokes", []) if f.get("type") == "IMAGE"]
        hashes += [p[k] for k in ("asset", "poster") if n["type"] == "video" and p.get(k)]
        for missing in [a for a in hashes if not has_asset(a)][:1]:
            add("error", "missing_asset", n, f"이미지/동영상 에셋이 없습니다: {missing[:12]}…")
        m = (measure or {}).get(n["id"])
        if m and (n["type"] == "table" or p.get("autoResize") in ("NONE", "HEIGHT")):
            wide, tall = m["sw"] > m["w"] + 1, m["sh"] > m["h"] + 1
            if wide or (tall and (n["type"] == "table" or p["autoResize"] == "NONE")):
                add("error", "overflow", n, "글자가 고정된 상자 밖으로 넘칩니다.")
        if n["type"] != "text":
            continue
        if not "".join(r.get("t", "") for r in p["runs"]).strip():
            add("error", "empty_text", n, "빈 텍스트입니다.")
        slide = str(props[page]["preset"]).startswith("SLIDE")
        least = 18 if slide else 8
        size = min([n["props"].get("style", {}).get("size", ops.defaults("text")["style"]["size"])]
                   + [r["s"]["size"] for r in p["runs"] if "size" in r.get("s", {})])
        if size < least:
            add("warning", "small_text", n, f"글자 크기 {size:g}가 {'슬라이드 18px' if slide else '문서 8pt'}보다 작습니다.")
        under = background(n["id"])
        colors = {r["fill"] for r in p["runs"] if r.get("fill")}
        if text_color(p) and not all(r.get("fill") for r in p["runs"]):  # the node color only paints runs without their own
            colors.add(text_color(p))
        # WCAG large text gets 3:1: 18 pt, or 14 pt bold (1 unit = 1 pt on paper, 1 px = 0.75 pt on slides)
        weight = min([(p.get("style") or {}).get("weight", 400)] + [r["s"]["weight"] for r in p["runs"] if "weight" in r.get("s", {})])
        pt = size * (0.75 if slide else 1)
        large = pt >= 18 or (pt >= 14 and weight >= 700)
        need = 3 if large else 4.5
        if under != UNKNOWN:
            for color in sorted(colors):
                if contrast(color, under) < need:
                    add("warning", "contrast", n, f"글자({color})와 배경({under})의 명암비가 {contrast(color, under):.1f}:1로 "
                        f"{'큰 글자 기준 3' if large else '기준 4.5'}:1보다 낮습니다.")
                    break

    texts = [n for n in shown if n["type"] == "text"]
    # rendered boxes where measured; a node placed by auto layout without one has no known position
    real = {n["id"]: (m["x"], m["y"], m["w"], m["h"], box[n["id"]][4]) if (m := (measure or {}).get(n["id"])) else box[n["id"]]
            for n in texts if (measure or {}).get(n["id"]) or not in_flow(by, n["id"])}
    texts = [n for n in texts if n["id"] in real]
    for i, a in enumerate(texts):  # ponytail: O(n²) per deck, fine for slide-sized pages
        for b in texts[i + 1:]:
            if real[a["id"]][4] == real[b["id"]][4] and overlap(real[a["id"]], real[b["id"]]) > 0:
                add("warning", "overlap_text", b, f"텍스트 상자가 {a['id']}와 겹칩니다.")
    for parent, group in kids.items():
        if parent in by and laid_out(by[parent]):  # auto layout spaces these siblings itself
            continue
        group = [s for s in group if s["id"] in visible_ids]
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                pa, pb = props[a["id"]], props[b["id"]]
                xs = [pa["x"] - e for e in (pb["x"], pb["x"] + pb["w"])] + [pa["x"] + pa["w"] - e for e in (pb["x"], pb["x"] + pb["w"])]
                ys = [pa["y"] - e for e in (pb["y"], pb["y"] + pb["h"])] + [pa["y"] + pa["h"] - e for e in (pb["y"], pb["y"] + pb["h"])]
                if any(0 < abs(d) < 2 for d in xs + ys):
                    add("warning", "near_miss", b, f"{a['id']}와 가장자리가 2px 안쪽으로 어긋나 있습니다.")
    return issues
