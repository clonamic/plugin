#!/usr/bin/env python3
"""Compose IR, render PPTX, run static QA."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_motion import apply_motion
from compose_ir import compose_deck, enrich_specs_from_outline
from engine_lib import dump_json, load_json
from extract_design_dna import extract_design_dna
from measure_word_budget import measure_word_budget
from qa_static import qa_ir, qa_pptx
from render_ir_svg import render_ir_svg
from validate import validate_specs
from visual_qa import qa_visual_report


def _load_outline(specs_path: Path, outline_path: Path | None) -> dict | None:
    cand = outline_path
    if cand is None:
        sibling = specs_path.parent / "outline.json"
        cand = sibling if sibling.exists() else None
    return load_json(cand) if cand else None


def apply_motion_and_verify(pptx_path: Path, deck: dict) -> list[dict]:
    try:
        apply_motion(pptx_path, deck)
    except Exception as exc:
        print(f"motion skipped: {exc}", file=sys.stderr)
    return qa_pptx(pptx_path, len(deck.get("slides") or []))


def run(
    specs_path: Path,
    out_dir: Path,
    title: str | None,
    language: str | None,
    outline_path: Path | None = None,
    reference_paths: list[Path] | None = None,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = load_json(specs_path)
    outline = _load_outline(specs_path, outline_path)
    enrich_specs_from_outline(specs, outline)
    issues = validate_specs(specs, None, outline)
    blockers = [i for i in issues if i["severity"] == "blocker"]
    if blockers:
        dump_json(
            out_dir / "qa_report.json",
            {
                "pass": False,
                "blocker": len(blockers),
                "major": sum(1 for item in issues if item["severity"] == "major"),
                "visual_status": "unavailable",
                "issues": issues,
            },
        )
        for i in blockers:
            print(f"VALIDATE {i['code']}: {i['message']}", file=sys.stderr)
        return 2
    deck = compose_deck(specs, title=title, language=language)
    contracts: dict[str, object] = {}
    contract_dir = out_dir / "reference_contracts"
    if reference_paths:
        contract_dir.mkdir(parents=True, exist_ok=True)
        dna = extract_design_dna(reference_paths)
        budget = measure_word_budget(reference_paths)
        dump_json(contract_dir / "design_dna.json", dna)
        dump_json(contract_dir / "word_budget.json", budget)
        contracts.update(
            {
                "design_dna": str(contract_dir / "design_dna.json"),
                "word_budget": str(contract_dir / "word_budget.json"),
                "median_word_ceiling": budget["median_ceiling"],
            }
        )
    if contracts:
        deck["reference_contracts"] = contracts
    ir_path = out_dir / "deck_ir.json"
    dump_json(ir_path, deck)
    svg_dir = out_dir / "svg"
    render_ir_svg(deck, svg_dir)
    pptx_path = out_dir / "presentation.pptx"
    render = Path(__file__).resolve().parent / "render_deck.cjs"
    try:
        proc = subprocess.run(
            ["node", str(render), "--input", str(ir_path), "--out", str(pptx_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        proc = subprocess.CompletedProcess([], 1, "", f"renderer unavailable or timed out: {error}")
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        dump_json(
            out_dir / "qa_report.json",
            {
                "pass": False,
                "blocker": 1,
                "major": 0,
                "visual_status": "unavailable",
                "issues": [{"severity": "blocker", "code": "RND000", "message": proc.stderr[-2000:]}],
            },
        )
        return 3
    qa = list(issues)
    qa.extend(qa_ir(deck, deck.get("language") or "ko-KR"))
    qa.extend(qa_pptx(pptx_path, len(deck["slides"])))
    visual = qa_visual_report(pptx_path, deck, out_dir / "slides")
    qa.extend(visual["issues"])
    qa.extend(apply_motion_and_verify(pptx_path, deck))
    report = {
        "blocker": sum(1 for i in qa if i["severity"] == "blocker"),
        "major": sum(1 for i in qa if i["severity"] == "major"),
        "issues": qa,
        "pass": all(i["severity"] not in {"blocker", "major"} for i in qa),
        "visual_status": visual["visual_status"],
        "artifacts": {
            "deck_ir": str(ir_path),
            "pptx": str(pptx_path),
            "slides": str(out_dir / "slides"),
            "svg": str(svg_dir),
        },
    }
    dump_json(out_dir / "qa_report.json", report)
    print(f"wrote {pptx_path}")
    print(f"QA pass={report['pass']} blockers={report['blocker']} majors={report['major']}")
    return 0 if report["pass"] else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--specs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--title")
    p.add_argument("--language")
    p.add_argument("--outline")
    p.add_argument("--reference-pptx", action="append", default=[])
    args = p.parse_args()
    return run(
        Path(args.specs),
        Path(args.out),
        args.title,
        args.language,
        Path(args.outline) if args.outline else None,
        [Path(path) for path in args.reference_pptx],
    )


if __name__ == "__main__":
    raise SystemExit(main())
