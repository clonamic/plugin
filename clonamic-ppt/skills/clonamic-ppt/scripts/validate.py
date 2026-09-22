#!/usr/bin/env python3
"""Validate brief / outline / slide_specs before compose."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from design import recommend_visual, spec_block_matches_visual, visual_allowed
from engine_lib import is_topic_title, load_json

PURPOSES = {"inform", "persuade", "decide", "teach", "report", "pitch"}
ROLES = {
    "title",
    "agenda",
    "section",
    "assertion",
    "comparison",
    "process",
    "data",
    "case_study",
    "recommendation",
    "summary",
    "appendix",
}
BLOCK_TYPES = {
    "paragraph",
    "bullets",
    "metric_card",
    "comparison",
    "process_steps",
    "quote",
    "table",
    "recommendation",
    "chart",
}
VISUALS = {
    "proof_grid",
    "hero_assertion",
    "metric_strip",
    "comparison_2col",
    "process_flow",
    "recommendation",
    "table_focus",
    "chart_focus",
    "quote_proof",
}
BRIDGES = {"answer", "evidence", "contrast", "zoom_in", "zoom_out", "implication"}


def issue(sev: str, code: str, msg: str, slide: str | None = None) -> dict:
    return {"severity": sev, "code": code, "message": msg, "slide_id": slide}


def validate_brief(brief: dict) -> list[dict]:
    out = []
    if brief.get("purpose") not in PURPOSES:
        out.append(issue("blocker", "BRF001", f"invalid purpose: {brief.get('purpose')}"))
    thesis = brief.get("single_sentence_thesis") or ""
    if not (1 <= len(thesis) <= 180):
        out.append(issue("blocker", "BRF002", "single_sentence_thesis must be 1–180 chars"))
    count = brief.get("slide_count_target")
    if not isinstance(count, int) or not (3 <= count <= 20):
        out.append(issue("blocker", "BRF003", "slide_count_target must be 3–20"))
    return out


def validate_outline(outline: dict, brief: dict | None = None) -> list[dict]:
    """Deck design must exist before specs. Each slide names its job, payload, and visual."""
    out = []
    if not isinstance(outline, dict):
        return [issue("blocker", "OUT001", "outline must be an object")]
    purpose = outline.get("purpose")
    if purpose not in PURPOSES:
        out.append(issue("blocker", "OUT002", f"invalid outline purpose: {purpose}"))
    if brief and brief.get("purpose") and purpose != brief.get("purpose"):
        out.append(issue("blocker", "OUT003", "outline.purpose must match brief.purpose"))
    arc = (outline.get("narrative_arc") or outline.get("storyline") or "").strip()
    if len(arc) < 12:
        out.append(issue("blocker", "OUT004", "narrative_arc/storyline must say the chain in one sentence"))
    slides = outline.get("slides")
    if not isinstance(slides, list) or not slides:
        return out + [issue("blocker", "OUT005", "outline.slides must be a non-empty list")]
    for i, s in enumerate(slides):
        sid = s.get("slide_id") or f"s{i + 1:02d}"
        role = s.get("role")
        if role not in ROLES:
            out.append(issue("blocker", "OUT006", f"invalid role {role!r}", sid))
        job = (s.get("job") or s.get("takeaway") or "").strip()
        if len(job) < 12:
            out.append(issue("blocker", "OUT007", "each slide needs job or takeaway (≥12 chars)", sid))
        title = (s.get("title") or "").strip()
        if not (3 <= len(title) <= 90):
            out.append(issue("blocker", "OUT008", "outline title length 3–90", sid))
        elif is_topic_title(title) and role not in {"agenda", "section"}:
            out.append(issue("blocker", "OUT009", f"topic-label title: {title!r}", sid))
        show = s.get("must_show") or s.get("must_include") or []
        if not isinstance(show, list) or not (2 <= len(show) <= 6):
            out.append(issue("blocker", "OUT010", "must_show must list 2–6 things the audience sees", sid))
        visual = s.get("visual")
        if visual not in VISUALS:
            out.append(issue("blocker", "OUT011", f"visual must be a layout family, got {visual!r}", sid))
        if i > 0 and s.get("bridge_type") not in BRIDGES:
            out.append(issue("major", "OUT012", "bridge_type required after slide 1", sid))
    visuals = [s.get("visual") for s in slides]
    used: list[str] = []
    for i, s in enumerate(slides):
        sid = s.get("slide_id") or f"s{i + 1:02d}"
        rec, why = recommend_visual(s, purpose or "", index=i + 1, total=len(slides), used=used)
        chosen = s.get("visual")
        if chosen in VISUALS and not visual_allowed(chosen, rec):
            out.append(
                issue(
                    "major",
                    "OUT018",
                    f"visual {chosen!r} does not fit this case (use {rec}: {why})",
                    sid,
                )
            )
        used.append(chosen or rec)
    for i in range(2, len(visuals)):
        if visuals[i] and visuals[i] == visuals[i - 1] == visuals[i - 2]:
            out.append(issue("major", "OUT016", "do not repeat the same visual three times in a row", slides[i].get("slide_id")))
    if visuals.count("quote_proof") > 2:
        out.append(issue("major", "OUT017", "quote_proof at most twice in a deck"))
    if purpose in {"decide", "pitch"} and slides:
        if slides[-1].get("role") not in {"recommendation", "summary"}:
            out.append(issue("blocker", "OUT013", "decide/pitch outline must end on recommendation/summary"))
        rec_vis = sum(1 for s in slides if s.get("visual") == "recommendation")
        if rec_vis > 1:
            out.append(issue("major", "OUT014", "only the last slide should be the ask visual"))
    if purpose == "teach" and slides and slides[-1].get("visual") == "recommendation":
        out.append(issue("major", "OUT019", "teach last slide is recall cards, not an ask"))
    return out


def validate_specs(data: dict, brief: dict | None = None, outline: dict | None = None) -> list[dict]:
    out = []
    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        return [issue("blocker", "SPC001", "slides must be a non-empty list")]

    ids = []
    seqs = []
    for i, s in enumerate(slides):
        sid = s.get("slide_id") or f"idx{i}"
        ids.append(sid)
        seqs.append(s.get("sequence"))
        role = s.get("role")
        if role not in ROLES:
            out.append(issue("blocker", "SPC002", f"invalid role {role!r}", sid))
        takeaway = s.get("takeaway") or ""
        if not (12 <= len(takeaway) <= 130):
            out.append(issue("blocker", "SPC003", f"takeaway length {len(takeaway)} not in 12–130", sid))
        title = s.get("title") or ""
        if not (3 <= len(title) <= 90):
            out.append(issue("blocker", "SPC004", f"title length {len(title)} not in 3–90", sid))
        elif is_topic_title(title) and role not in {"agenda", "section"}:
            out.append(issue("blocker", "SPC005", f"topic-label title: {title!r}", sid))
        blocks = s.get("content_blocks") or []
        if not (1 <= len(blocks) <= 8):
            out.append(issue("major", "SPC006", f"content_blocks count {len(blocks)} not in 1–8", sid))
        for b in blocks:
            bt = b.get("type")
            if bt not in BLOCK_TYPES:
                out.append(issue("blocker", "SPC007", f"unknown block type {bt!r}", sid))
            if bt == "bullets":
                items = b.get("items") or []
                if len(items) > 5:
                    out.append(issue("major", "SPC008", f"too many bullets ({len(items)})", sid))
                if len(blocks) == 1 and len(items) == 4:
                    for it in items:
                        head, body = (str(it).split(" — ", 1) + [""])[:2] if " — " in str(it) else (str(it), "")
                        if not body or len(body) < 12:
                            out.append(
                                issue(
                                    "major",
                                    "SPC019",
                                    "2×2 item needs 주장 — 이유 with a real body",
                                    sid,
                                )
                            )
                            break
            if bt == "recommendation":
                lang = str((data.get("language") or (brief or {}).get("language") or "ko-KR")).lower()
                cjk = lang.startswith(("ko", "ja", "zh"))
                floors = {"owner": (10, 24), "timing": (10, 24), "success_metric": (16, 36)}
                for key in ("owner", "timing", "success_metric"):
                    val = str(b.get(key) or "").strip()
                    if not val or val.lower() in {"tbd", "n/a", "지정 필요"}:
                        out.append(issue("major", "SPC020", f"recommendation.{key} is empty or placeholder", sid))
                    elif key in floors:
                        need = floors[key][0] if cjk else floors[key][1]
                        if len(val) < need:
                            out.append(issue("major", "SPC023", f"recommendation.{key} too thin ({len(val)}<{need})", sid))
                act = str(b.get("action") or "").strip()
                if act and takeaway and re.sub(r"\s+", "", act.lower()) == re.sub(r"\s+", "", takeaway.lower()):
                    out.append(issue("major", "SPC021", "takeaway restates recommendation.action", sid))
                if takeaway and title and re.sub(r"\s+", "", takeaway.lower()) == re.sub(r"\s+", "", title.lower()):
                    out.append(issue("major", "SPC022", "takeaway repeats the title", sid))
            if bt == "metric_card":
                val = str(b.get("value") or "")
                if not val:
                    out.append(issue("blocker", "SPC009", "metric_card missing value", sid))
                elif not re.search(r"\d", val):
                    out.append(issue("major", "SPC016", f"metric_card value needs a digit: {val!r}", sid))
            if bt == "comparison":
                cols = b.get("columns") or []
                if len(cols) != 2:
                    out.append(issue("major", "SPC010", "comparison must have exactly 2 columns", sid))
            if bt == "process_steps":
                steps = b.get("steps") or []
                if not (3 <= len(steps) <= 6):
                    out.append(issue("major", "SPC011", f"process_steps count {len(steps)} not in 3–6", sid))
            if bt == "table":
                rows = b.get("rows") or []
                cols = b.get("columns") or []
                if len(cols) > 6 or len(rows) > 7:
                    out.append(issue("major", "SPC012", "table exceeds 6×7", sid))
            if bt == "chart":
                cats = b.get("categories") or []
                series = b.get("series") or []
                if len(cats) < 2 or not series:
                    out.append(issue("blocker", "SPC017", "chart needs ≥2 categories and a series", sid))
                else:
                    for s in series:
                        vals = s.get("values") or []
                        if len(vals) != len(cats) or any(not isinstance(v, (int, float)) for v in vals):
                            out.append(issue("blocker", "SPC018", "chart series values must match categories", sid))

    if len(ids) != len(set(ids)):
        out.append(issue("blocker", "SPC013", "duplicate slide_id"))
    if seqs != list(range(1, len(slides) + 1)) and sorted(x or 0 for x in seqs) != list(range(1, len(slides) + 1)):
        out.append(issue("major", "SPC014", "sequence should be 1..n unique"))

    purpose = (brief or {}).get("purpose") or data.get("purpose")
    if purpose in {"decide", "pitch"} and len(slides) >= 2:
        tail_roles = {slides[-1].get("role"), slides[-2].get("role")}
        tail_types = []
        for s in slides[-2:]:
            tail_types.extend(b.get("type") for b in (s.get("content_blocks") or []))
        if not (tail_roles & {"recommendation", "summary"} or "recommendation" in tail_types):
            out.append(issue("blocker", "SPC015", "decide/pitch must end with recommendation or action"))
    if outline and isinstance(outline.get("slides"), list):
        by_id = {s.get("slide_id"): s for s in outline["slides"] if s.get("slide_id")}
        for s in slides:
            sid = s.get("slide_id")
            vis = (by_id.get(sid) or {}).get("visual")
            if vis and not spec_block_matches_visual(s, vis):
                out.append(
                    issue(
                        "major",
                        "SPC024",
                        f"specs block type does not implement outline visual {vis!r}",
                        sid,
                    )
                )
            if vis == "quote_proof":
                n_bullets = sum(
                    len(b.get("items") or [])
                    for b in (s.get("content_blocks") or [])
                    if b.get("type") == "bullets"
                )
                show = (by_id.get(sid) or {}).get("must_show") or s.get("must_show") or []
                if isinstance(show, list) and len(show) >= 2 and n_bullets < 2:
                    out.append(
                        issue(
                            "major",
                            "SPC025",
                            "quote_proof must implement must_show as 2–3 extras",
                            sid,
                        )
                    )
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--brief")
    p.add_argument("--outline")
    p.add_argument("--specs", required=True)
    args = p.parse_args()
    issues: list[dict] = []
    brief = load_json(Path(args.brief)) if args.brief else None
    outline = load_json(Path(args.outline)) if args.outline else None
    if brief:
        issues.extend(validate_brief(brief))
    if outline:
        issues.extend(validate_outline(outline, brief))
    specs = load_json(Path(args.specs))
    issues.extend(validate_specs(specs, brief, outline))
    blockers = [i for i in issues if i["severity"] == "blocker"]
    for i in issues:
        loc = f" [{i['slide_id']}]" if i.get("slide_id") else ""
        print(f"{i['severity'].upper()} {i['code']}{loc}: {i['message']}")
    if not issues:
        print("OK")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
