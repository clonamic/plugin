#!/usr/bin/env python3
"""Static geometry / schema QA on DeckIR (and optional PPTX zip)."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_lib import THEME, SLIDE_H, SLIDE_W, dump_json, estimate_text_height_in, load_json


def issue(sev: str, code: str, msg: str, slide: str | None = None, el: str | None = None) -> dict:
    return {
        "severity": sev,
        "code": code,
        "message": msg,
        "slide_id": slide,
        "element_id": el,
    }


def overlaps(a: dict, b: dict, eps: float = 0.03) -> bool:
    ax1, ay1 = a["x"] - eps, a["y"] - eps
    ax2, ay2 = a["x"] + a["w"] + eps, a["y"] + a["h"] + eps
    bx1, by1 = b["x"] - eps, b["y"] - eps
    bx2, by2 = b["x"] + b["w"] + eps, b["y"] + b["h"] + eps
    return max(ax1, bx1) + 1e-6 < min(ax2, bx2) and max(ay1, by1) + 1e-6 < min(ay2, by2)


def qa_ir(deck: dict, language: str | None = None) -> list[dict]:
    language = language or deck.get("language") or "ko-KR"
    issues: list[dict] = []
    ids: set[str] = set()
    slides = deck.get("slides") or []
    if not slides:
        issues.append(issue("blocker", "QA000", "no slides"))
        return issues
    for s in slides:
        sid = s.get("slide_id")
        els = s.get("elements") or []
        texts = [e for e in els if e.get("kind") == "text"]
        shapes = [e for e in els if e.get("kind") == "shape"]
        for el in els:
            eid = el.get("element_id")
            if eid in ids:
                issues.append(issue("blocker", "QA001", "duplicate element_id", sid, eid))
            ids.add(eid)
            bb = el.get("bbox") or {}
            try:
                x, y, w, h = float(bb["x"]), float(bb["y"]), float(bb["w"]), float(bb["h"])
            except Exception:
                issues.append(issue("blocker", "QA002", "invalid bbox", sid, eid))
                continue
            if x < -0.01 or y < -0.01 or x + w > SLIDE_W + 0.01 or y + h > SLIDE_H + 0.01:
                issues.append(issue("blocker", "QA003", "out of canvas", sid, eid))
            if el.get("kind") == "text":
                size = float((el.get("style") or {}).get("font_size_pt") or 0)
                token = el.get("token_ref") or ""
                floor = THEME["footnote"] if token == "source" else (
                    THEME["min_title"] if token == "title" else THEME["min_body"]
                )
                if token == "source":
                    floor = 7
                elif token == "title":
                    floor = THEME["min_title"]
                else:
                    floor = THEME["min_body"]
                if size + 1e-6 < floor:
                    issues.append(issue("major", "QA004", f"font {size}pt < {floor}pt", sid, eid))
                needed = estimate_text_height_in(el.get("text") or "", w, size, 1.2, language)
                if needed > h * 1.08:
                    issues.append(
                        issue("major", "QA005", f"text overflow ~{needed:.2f}in into {h:.2f}in", sid, eid)
                    )
        # shape vs text overlap is allowed (card surface). text vs text is not.
        for i, a in enumerate(texts):
            for b in texts[i + 1 :]:
                if overlaps(a["bbox"], b["bbox"], eps=0.02):
                    issues.append(
                        issue("major", "QA006", f"text overlap {a.get('element_id')} / {b.get('element_id')}", sid)
                    )
        if not any(e.get("token_ref") == "title" or (e.get("element_id") or "").endswith("_title") for e in texts):
            issues.append(issue("major", "QA007", "missing title text", sid))
        card_fills = {THEME["surface"].upper(), THEME["surface_muted"].upper()}
        for sh in shapes:
            fill = str((sh.get("fill") or {}).get("color") or "").replace("#", "").upper()
            if fill not in card_fills:
                continue
            bb = sh.get("bbox") or {}
            try:
                sx, sy, sw, shh = float(bb["x"]), float(bb["y"]), float(bb["w"]), float(bb["h"])
            except Exception:
                continue
            if shh < 1.05 or sw < 0.80:
                continue
            inner = []
            for t in texts:
                tb = t.get("bbox") or {}
                try:
                    cx = float(tb["x"]) + float(tb["w"]) / 2
                    cy = float(tb["y"]) + float(tb["h"]) / 2
                except Exception:
                    continue
                if sx - 0.02 <= cx <= sx + sw + 0.02 and sy - 0.02 <= cy <= sy + shh + 0.02:
                    inner.append(t)
            if not inner:
                continue
            used = max(float(t["bbox"]["y"]) + float(t["bbox"]["h"]) for t in inner) - min(
                float(t["bbox"]["y"]) for t in inner
            )
            if used < 0.42 * shh:
                issues.append(
                    issue(
                        "major",
                        "QA009",
                        f"stretched empty card h={shh:.2f} used={used:.2f}",
                        sid,
                        sh.get("element_id"),
                    )
                )
        if not any((e.get("element_id") or "").endswith("_pg") for e in texts):
            issues.append(issue("major", "QA010", "missing slide index", sid))
        content_shapes = []
        for sh in shapes:
            fill = str((sh.get("fill") or {}).get("color") or "").replace("#", "").upper()
            if fill in card_fills or fill == str(THEME["accent_dark"]).upper():
                try:
                    yy = float(sh["bbox"]["y"])
                except Exception:
                    continue
                if yy < 6.0:
                    content_shapes.append(yy)
        if content_shapes and min(content_shapes) > 4.05:
            issues.append(issue("major", "QA011", f"content floats too low y={min(content_shapes):.2f}", sid))
        fam = s.get("layout_family") or ""
        if fam in {"proof_grid", "recommendation", "table_focus"}:
            bottoms = []
            for sh in els:
                if sh.get("kind") not in {"shape", "table"}:
                    continue
                bb = sh.get("bbox") or {}
                try:
                    sw = float(bb["w"])
                    sy = float(bb["y"])
                    shh = float(bb["h"])
                except Exception:
                    continue
                if sw < 1.0 or sy > 6.9:
                    continue
                bottoms.append(sy + shh)
            floor = 4.40 if fam == "proof_grid" else 5.20
            if bottoms and max(bottoms) < floor:
                issues.append(
                    issue("major", "QA013", f"last-ask / grid canvas empty bottom={max(bottoms):.2f}", sid)
                )
        for t in texts:
            eid = t.get("element_id") or ""
            if not (eid.endswith("_deck") or eid.endswith("_src")):
                continue
            tx = (t.get("text") or "").strip()
            if tx in {"", "…", "..."}:
                issues.append(issue("major", "QA014", "footer title collapsed to ellipsis", sid, eid))
    return issues


def qa_pptx(path: Path, slide_count: int) -> list[dict]:
    issues = []
    if not path.exists():
        return [issue("blocker", "RND001", f"missing pptx: {path}")]
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                issues.append(issue("blocker", "RND002", "not a valid pptx zip"))
            n = len([n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
            if n != slide_count:
                issues.append(issue("blocker", "RND003", f"pptx slide count {n} != ir {slide_count}"))
    except zipfile.BadZipFile:
        issues.append(issue("blocker", "RND004", "pptx is not a zip"))
    return issues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ir", required=True)
    p.add_argument("--pptx")
    p.add_argument("--out")
    args = p.parse_args()
    deck = load_json(Path(args.ir))
    issues = qa_ir(deck, deck.get("language") or "ko-KR")
    if args.pptx:
        issues.extend(qa_pptx(Path(args.pptx), len(deck.get("slides") or [])))
    blockers = sum(1 for i in issues if i["severity"] == "blocker")
    majors = sum(1 for i in issues if i["severity"] == "major")
    report = {
        "blocker": blockers,
        "major": majors,
        "minor": sum(1 for i in issues if i["severity"] == "minor"),
        "issues": issues,
        "pass": blockers == 0 and majors == 0,
    }
    if args.out:
        dump_json(Path(args.out), report)
    print(f"QA blockers={blockers} majors={majors} pass={report['pass']}")
    for i in issues:
        loc = i.get("slide_id") or ""
        print(f"  {i['severity']} {i['code']} {loc}: {i['message']}")
    return 0 if blockers == 0 and majors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
