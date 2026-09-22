#!/usr/bin/env python3
"""Add slide fade + purpose-aware object entrance after visual QA.

Static PNG export stays fully visible because this runs after visual QA.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine_lib import load_json  # noqa: E402

STAY = ("_title", "_trule", "_sub", "_src")


def _ids(xml: str) -> list[tuple[str, str]]:
    return re.findall(r'<p:cNvPr id="(\d+)" name="([^"]*)"', xml)


def _group(name: str, family: str) -> tuple[str, int] | None:
    if not name or name.endswith(STAY):
        return None
    if family == "process_flow":
        m = re.search(r"_(?:p|pa|pb|pn|pl|pd|arr)(\d+)$", name)
        return ("step", int(m.group(1))) if m else ("body", 0)
    if family == "comparison_2col":
        if "_vs" in name or name.endswith("_vst"):
            return ("vs", 1)
        m = re.search(r"_(?:col|cola|ct)(\d+)$", name) or re.search(r"_cb(\d+)_", name)
        return ("col", int(m.group(1)) * 2) if m else ("body", 0)
    if family == "proof_grid":
        m = re.search(r"_g[abndh]?(\d+)$", name)
        if m:
            return ("row", int(m.group(1)) // 2)
        return ("body", 0)
    if family == "recommendation":
        if name.endswith(("_ban", "_act")):
            return ("ask", 0)
        return ("meta", 1)
    if family == "metric_strip":
        return ("metrics", 0)
    if family == "table_focus":
        return ("side", 1) if re.search(r"_t[clta]$", name) or "_tt" in name else ("table", 0)
    if family == "hero_assertion":
        return ("thesis", 1) if name.endswith("_thesis") else ("hero", 0)
    return ("body", 0)


def _click(node_id: int, shape_ids: list[str], *, onclick: bool, delay_ms: int) -> tuple[str, int]:
    nid = node_id
    cond = '<p:cond delay="indefinite"/>' if onclick else f'<p:cond delay="{delay_ms}"/>'
    effects = []
    for sid in shape_ids:
        nid += 1
        eid = nid
        effects.append(
            f'<p:animEffect transition="in" filter="fade"><p:cBhvr>'
            f'<p:cTn id="{eid}" dur="400"/><p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl>'
            f"</p:cBhvr></p:animEffect>"
        )
    nid += 1
    inner = nid
    nid += 1
    outer = nid
    xml = (
        f'<p:par><p:cTn id="{outer}" fill="hold"><p:stCondLst>{cond}</p:stCondLst>'
        f'<p:childTnLst><p:par><p:cTn id="{inner}" fill="hold">'
        f'<p:stCondLst><p:cond delay="0"/></p:stCondLst>'
        f'<p:childTnLst>{"".join(effects)}</p:childTnLst>'
        f"</p:cTn></p:par></p:childTnLst></p:cTn></p:par>"
    )
    return xml, nid


def _timing(groups: list[list[str]], *, onclick: bool) -> str:
    if not groups:
        return ""
    parts = []
    nid = 2
    for i, g in enumerate(groups):
        if not g:
            continue
        xml, nid = _click(nid, g, onclick=onclick if i > 0 or onclick else False, delay_ms=280 if i else 120)
        parts.append(xml)
    if not parts:
        return ""
    return (
        '<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
        '<p:childTnLst><p:seq concurrent="1" nextAc="seek">'
        f'<p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>{"".join(parts)}</p:childTnLst></p:cTn>'
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        "</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>"
    )


def _patch_slide(xml: str, family: str, purpose: str) -> str:
    trans = '<p:transition spd="med"><p:fade/></p:transition>'
    if "<p:transition" in xml:
        out = xml
    else:
        out = xml.replace("</p:sld>", trans + "</p:sld>", 1)
    if purpose == "report":
        return out
    named = [(i, n) for i, n in _ids(xml) if n and n != ""]
    buckets: dict[tuple[str, int], list[str]] = {}
    for sid, name in named:
        key = _group(name, family)
        if key is None:
            continue
        buckets.setdefault(key, []).append(sid)
    groups = [buckets[k] for k in sorted(buckets, key=lambda x: (x[1], x[0]))]
    onclick = purpose in {"decide", "pitch", "persuade"}
    timing = _timing(groups, onclick=onclick)
    if timing and "<p:timing" not in out:
        out = out.replace("</p:sld>", timing + "</p:sld>", 1)
    return out


def apply_motion(pptx: Path, ir: dict) -> None:
    slides = ir.get("slides") or []
    purpose = ir.get("purpose") or ""
    if ir.get("theme_id") == "studio-lesson":
        purpose = purpose or "teach"
    elif ir.get("theme_id") == "logbook":
        purpose = purpose or "report"
    elif ir.get("theme_id") == "ink-ask":
        purpose = purpose or "pitch"
    elif ir.get("theme_id") == "boardroom-pine":
        purpose = purpose or "decide"
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with zipfile.ZipFile(pptx, "r") as zin:
            zin.extractall(tmp)
        slide_dir = tmp / "ppt" / "slides"
        for i, spec in enumerate(slides, start=1):
            path = slide_dir / f"slide{i}.xml"
            if not path.exists():
                continue
            xml = path.read_text(encoding="utf-8")
            path.write_text(_patch_slide(xml, spec.get("layout_family") or "", purpose), encoding="utf-8")
        out = pptx.with_suffix(".motion.pptx")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for f in tmp.rglob("*"):
                if f.is_file():
                    zout.write(f, f.relative_to(tmp).as_posix())
        out.replace(pptx)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pptx", required=True)
    p.add_argument("--ir", required=True)
    args = p.parse_args()
    apply_motion(Path(args.pptx), load_json(Path(args.ir)))
    print(args.pptx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
