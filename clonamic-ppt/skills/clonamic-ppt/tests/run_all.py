#!/usr/bin/env python3
"""Isolation + engine + hard-case suite. Exit 0 only if all required checks pass."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PLUGIN = ROOT.parent.parent
sys.path.insert(0, str(SCRIPTS))

from engine_lib import BANNED_DESC_WORDS, description_has_banned_words  # noqa: E402
from validate import validate_brief, validate_outline, validate_specs  # noqa: E402
from compose_ir import compose_deck  # noqa: E402
from qa_static import qa_ir, qa_pptx  # noqa: E402
import visual_qa  # noqa: E402
import run_engine  # noqa: E402


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        failures.append(name)


def test_isolation() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    check("isolation.direct_skill", "spawn" not in skill.lower() and "subagent" not in skill.lower())
    check("isolation.no_model_lock", "model" not in skill.lower())
    check("isolation.skill_name", "name: clonamic-ppt" in skill)
    check("isolation.description_scan", description_has_banned_words("clonamic-ppt") == [])
    manifest = load(PLUGIN / "plugin.json")
    check("isolation.schema", manifest.get("$schema", "").endswith("plugin.schema.json"))
    check("isolation.manifest_name", manifest.get("name") == "clonamic-ppt")
    check("isolation.license", manifest.get("license") == "MIT")
    extra = set(manifest) - {
        "$schema",
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "extensions",
    }
    check("isolation.closed_manifest", not extra, str(extra))
    check("isolation.no_mcp", not (PLUGIN / "mcp.json").exists())
    # description of plugin.json should not use banned auto-trigger words either if possible
    # allow nothing from BANNED in skill description; plugin desc already clean


def test_visual_renderer_safety() -> None:
    with mock.patch.object(visual_qa.platform, "system", return_value="Darwin"):
        with mock.patch.dict(visual_qa.os.environ, {}, clear=True):
            check("visual.macos_auto_disabled", visual_qa._soffice() is None)
        with mock.patch.dict(
            visual_qa.os.environ, {"CLONAMIC_ALLOW_MACOS_SOFFICE": "1"}, clear=True
        ):
            with mock.patch.object(visual_qa.shutil, "which", return_value="/tmp/soffice"):
                check("visual.macos_explicit_opt_in", visual_qa._soffice() == "/tmp/soffice")
    source = (SCRIPTS / "visual_qa.py").read_text(encoding="utf-8")
    check("visual.isolated_profile", "-env:UserInstallation=" in source)
    check("visual.timeout", "timeout=30" in source)


def test_local_node_dependencies() -> None:
    ignore = PLUGIN / ".gitignore"
    check("deps.node_modules_ignored", ignore.is_file() and "/node_modules/" in ignore.read_text(encoding="utf-8"))
    source = (SCRIPTS / "render_deck.cjs").read_text(encoding="utf-8")
    check("deps.no_pptxgen_fallback", 'return require("pptxgenjs")' not in source)
    check("deps.image_size_guard", "vendor/image-size" in source and "realpathSync" in source)
    probe = subprocess.run(
        [
            "node",
            "-e",
            (
                "const fs=require('fs'),p=require('path'),r=process.argv[1];"
                "const ppt=fs.realpathSync(require.resolve('pptxgenjs',{paths:[r]}));"
                "const img=fs.realpathSync(require.resolve('image-size',{paths:[r]}));"
                "console.log(JSON.stringify({ppt,img}));"
            ),
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
    )
    check("deps.resolve_exit", probe.returncode == 0, probe.stderr)
    if probe.returncode == 0:
        resolved = json.loads(probe.stdout)
        check("deps.pptxgen_local", str(Path(resolved["ppt"])).startswith(str(PLUGIN / "node_modules")), resolved["ppt"])
        check(
            "deps.image_size_vendor",
            Path(resolved["img"]).resolve() == (PLUGIN / "vendor/image-size/index.js").resolve(),
            resolved["img"],
        )


def test_post_motion_integrity_guard() -> None:
    check("motion.guard_api", hasattr(run_engine, "apply_motion_and_verify"))
    if not hasattr(run_engine, "apply_motion_and_verify"):
        return
    import zipfile

    with tempfile.TemporaryDirectory() as td:
        pptx = Path(td) / "one.pptx"
        with zipfile.ZipFile(pptx, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("ppt/presentation.xml", "<p:presentation/>")
            z.writestr("ppt/slides/slide1.xml", "<p:sld/>")
        original = run_engine.apply_motion
        try:
            run_engine.apply_motion = lambda path, deck: path.write_bytes(b"broken")
            issues = run_engine.apply_motion_and_verify(pptx, {"slides": [{}]})
        finally:
            run_engine.apply_motion = original
        check(
            "motion.corruption_blocked",
            any(item.get("severity") == "blocker" and item.get("code") == "RND004" for item in issues),
            str(issues),
        )


def test_golden() -> None:
    specs = load(ROOT / "assets/fixtures/decide_pilot_8/slide_specs.json")
    brief = load(ROOT / "assets/fixtures/decide_pilot_8/brief.json")
    outline = load(ROOT / "assets/fixtures/decide_pilot_8/outline.json")
    issues = validate_brief(brief) + validate_outline(outline, brief) + validate_specs(specs, brief, outline)
    blockers = [i for i in issues if i["severity"] == "blocker"]
    check("golden.validate", not blockers, str(blockers))
    deck = compose_deck(specs)
    check("golden.slide_count", len(deck["slides"]) == 8)
    families = {s["layout_family"] for s in deck["slides"]}
    check("golden.family_variety", len(families) >= 3, str(families))
    qa = qa_ir(deck)
    blockers = [i for i in qa if i["severity"] == "blocker"]
    check("golden.ir_qa", not blockers, str(blockers))


def test_hard_cases() -> None:
    # topic title must fail
    bad = {
        "title": "x",
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "assertion",
                "takeaway": "이것은 충분히 긴 테이크어웨이 문장이다",
                "title": "시장 분석",
                "content_blocks": [{"type": "paragraph", "text": "본문"}],
            }
        ],
    }
    issues = validate_specs(bad)
    check("hard.topic_title_blocked", any(i["code"] == "SPC005" for i in issues), str(issues))

    # decide without action ending
    no_action = {
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "assertion",
                "takeaway": "첫 장의 결론을 한 문장으로 적는다",
                "title": "병목이 일정 리스크를 키운다",
                "content_blocks": [{"type": "paragraph", "text": "설명"}],
            },
            {
                "slide_id": "s02",
                "sequence": 2,
                "role": "assertion",
                "takeaway": "둘째 장도 결론형 문장으로 적는다",
                "title": "데이터가 우선순위를 가리킨다",
                "content_blocks": [{"type": "paragraph", "text": "설명"}],
            },
        ]
    }
    issues = validate_specs(no_action, {"purpose": "decide"})
    check("hard.decide_needs_action", any(i["code"] == "SPC015" for i in issues))

    # long Korean title still composes inside canvas
    long_title = "우선 공략 세그먼트는 성장률보다 전환 비용이 낮은 중견 고객이며 지금 결정해야 한다"
    spec = {
        "language": "ko-KR",
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "assertion",
                "takeaway": long_title[:80],
                "title": long_title[:90],
                "importance": "hero",
                "content_blocks": [{"type": "paragraph", "text": "근거 문장입니다."}],
            }
        ],
    }
    deck = compose_deck(spec)
    qa = [i for i in qa_ir(deck) if i["severity"] == "blocker"]
    check("hard.long_korean_title_no_blocker", not qa, str(qa))

    word_metric = {
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "data",
                "takeaway": "병목은 반복 작성과 검토 대기에 있다",
                "title": "병목은 반복 작성과 검토 대기에 있다",
                "content_blocks": [
                    {"type": "metric_card", "value": "반복 작성", "label": "낭비"},
                    {"type": "metric_card", "value": "12주", "label": "기간"},
                    {"type": "metric_card", "value": "3팀", "label": "범위"},
                ],
            }
        ]
    }
    issues = validate_specs(word_metric)
    check("hard.word_metric_flagged", any(i["code"] == "SPC016" for i in issues), str(issues))
    deck = compose_deck(word_metric)
    check("hard.word_metric_not_strip", deck["slides"][0]["layout_family"] != "metric_strip", deck["slides"][0]["layout_family"])

    # 4 metrics
    cards = [{"type": "metric_card", "value": f"{i}0%", "label": f"지표{i}", "supporting_text": "설명"} for i in range(4)]
    spec = {
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "data",
                "takeaway": "네 지표가 같은 우선순위를 가리킨다",
                "title": "네 지표가 같은 우선순위를 가리킨다",
                "content_blocks": cards,
            }
        ]
    }
    deck = compose_deck(spec)
    check("hard.four_metrics_family", deck["slides"][0]["layout_family"] == "metric_strip")
    qa = [i for i in qa_ir(deck) if i["severity"] == "blocker"]
    check("hard.four_metrics_no_blocker", not qa, str(qa))

    four_bullets = {
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "assertion",
                "takeaway": "네 가지 증거가 같은 결론을 가리킨다",
                "title": "네 가지 증거가 같은 결론을 가리킨다",
                "content_blocks": [
                    {
                        "type": "bullets",
                        "items": [
                            "대기 — 핸드오프에서 멈춘다",
                            "재작성 — 같은 문장을 다시 쓴다",
                            "버전 — 최종본이 불명확하다",
                            "범위 — 팀이 양식을 나눈다",
                        ],
                    }
                ],
            }
        ]
    }
    deck = compose_deck(four_bullets)
    check("hard.proof_grid", deck["slides"][0]["layout_family"] == "proof_grid", deck["slides"][0]["layout_family"])

    chart = {
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "data",
                "takeaway": "검증 단계가 다른 단계보다 길다",
                "title": "검증 단계가 다른 단계보다 길다",
                "content_blocks": [
                    {
                        "type": "chart",
                        "chart_type": "bar",
                        "categories": ["접수", "검토", "검증", "완료"],
                        "series": [{"name": "시간", "values": [2, 3, 8, 1]}],
                        "conclusion": "검증에 시간을 몰아주는 것이 맞다",
                    }
                ],
            }
        ]
    }
    issues = [i for i in validate_specs(chart) if i["severity"] == "blocker"]
    check("hard.chart_validate", not issues, str(issues))
    deck = compose_deck(chart)
    check("hard.chart_family", deck["slides"][0]["layout_family"] == "chart_focus")

    golden = load(ROOT / "assets/fixtures/decide_pilot_8/slide_specs.json")
    deck = compose_deck(golden)
    from engine_lib import THEME as _THEME

    surface = {_THEME["surface"].upper(), _THEME["surface_muted"].upper()}
    for slide in deck["slides"]:
        fam = slide["layout_family"]
        if fam not in {"metric_strip", "process_flow", "comparison_2col", "proof_grid", "hero_assertion", "recommendation"}:
            continue
        for el in slide["elements"]:
            if el.get("kind") != "shape":
                continue
            fill = str((el.get("fill") or {}).get("color") or "").upper()
            if fill not in surface:
                continue
            h = float(el["bbox"]["h"])
            if fam == "recommendation":
                if el["element_id"].endswith("_spine"):
                    check(f"hard.rec_spine_hug.{el['element_id']}", 0.60 < h < 1.10, str(h))
                elif "_chip" in el["element_id"]:
                    check(f"hard.no_echo_chip.{el['element_id']}", False, "echo chips are not production")
                else:
                    check(f"hard.rec_extra.{el['element_id']}", 0.90 < h < 3.60, str(h))
            elif fam == "comparison_2col" and el["element_id"].endswith(("_col0", "_col1")):
                check(f"hard.cmp_planted.{el['element_id']}", 2.0 < h < 5.25, f"{fam} {h}")
            elif fam == "process_flow" and re.search(r"_p\d+$", el["element_id"]):
                w = float(el["bbox"]["w"])
                if w > 10:
                    check(f"hard.proc_hug.{el['element_id']}", 0.85 < h < 1.55, f"{fam} {h}")
                else:
                    check(f"hard.proc_hug.{el['element_id']}", 1.45 < h < 2.50, f"{fam} {h}")
            elif el["element_id"].endswith("_spine"):
                check(f"hard.spine_hug.{el['element_id']}", 0.60 < h < 1.15, str(h))
            elif fam == "hero_assertion" and el["element_id"].endswith("_ms"):
                check(f"hard.card_not_stretched.{el['element_id']}", 1.10 < h < 2.50, f"{fam} {h}")
            elif fam == "hero_assertion" and re.search(r"_pr\d+$", el["element_id"]):
                check(f"hard.hero_claim.{el['element_id']}", 0.70 < h < 2.20, f"{fam} {h}")
            else:
                check(f"hard.card_not_stretched.{el['element_id']}", h < 3.45, f"{fam} {h}")
    hero = deck["slides"][0]
    check("hard.hero_is_hero", hero["layout_family"] == "hero_assertion")
    ms = next(e for e in hero["elements"] if e["element_id"].endswith("_ms"))
    check("hard.hero_metric_banner_wide", float(ms["bbox"]["w"]) > 10, ms["bbox"])
    check("hard.hero_metric_banner_short", 1.10 < float(ms["bbox"]["h"]) < 2.50, ms["bbox"])

    mix = load(ROOT / "assets/fixtures/mix_families/slide_specs.json")
    mix_issues = [i for i in validate_specs(mix) if i["severity"] == "blocker"]
    check("hard.mix_validate", not mix_issues, str(mix_issues))
    mix_deck = compose_deck(mix)
    mix_fams = [s["layout_family"] for s in mix_deck["slides"]]
    check(
        "hard.mix_families",
        mix_fams == ["chart_focus", "table_focus", "quote_proof", "recommendation"],
        str(mix_fams),
    )
    mix_qa = [i for i in qa_ir(mix_deck) if i["severity"] in {"blocker", "major"}]
    check("hard.mix_qa", not mix_qa, str(mix_qa))


def test_render() -> None:
    specs = load(ROOT / "assets/fixtures/decide_pilot_8/slide_specs.json")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_engine.py"),
                "--specs",
                str(ROOT / "assets/fixtures/decide_pilot_8/slide_specs.json"),
                "--out",
                str(out),
                "--title",
                specs["title"],
            ],
            capture_output=True,
            text=True,
        )
        check("render.engine_exit", proc.returncode == 0, proc.stderr[-500:] if proc.stderr else proc.stdout[-500:])
        pptx = out / "presentation.pptx"
        check("render.pptx_exists", pptx.exists())
        if pptx.exists():
            deck = load(out / "deck_ir.json")
            issues = qa_pptx(pptx, len(deck["slides"]))
            check("render.pptx_zip", not issues, str(issues))
            qa = load(out / "qa_report.json")
            check("render.golden_no_major", qa.get("major", 1) == 0 and qa.get("blocker", 1) == 0, qa)
            import zipfile
            with zipfile.ZipFile(pptx) as z:
                s1 = z.read("ppt/slides/slide1.xml").decode("utf-8")
            check("render.fade_transition", "<p:transition" in s1 and "<p:fade" in s1)
        mix_out = out / "mix"
        proc2 = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_engine.py"),
                "--specs",
                str(ROOT / "assets/fixtures/mix_families/slide_specs.json"),
                "--out",
                str(mix_out),
                "--title",
                "mix",
            ],
            capture_output=True,
            text=True,
        )
        check("render.mix_exit", proc2.returncode == 0, proc2.stderr[-400:] if proc2.stderr else proc2.stdout[-400:])
        if (mix_out / "qa_report.json").exists():
            qa2 = load(mix_out / "qa_report.json")
            check("render.mix_no_major", qa2.get("major", 1) == 0 and qa2.get("blocker", 1) == 0, qa2)


def test_empty_args_spec_still_valid_shape() -> None:
    # help-style inform deck used when user typed slash with no brief
    spec = {
        "title": "요청 방법",
        "language": "ko-KR",
        "slides": [
            {
                "slide_id": "s01",
                "sequence": 1,
                "role": "title",
                "takeaway": "슬래시 뒤에 청중과 결정을 적어야 덱이 만들어진다",
                "title": "슬래시 뒤에 청중과 결정을 적어야 한다",
                "content_blocks": [{"type": "paragraph", "text": "목적, 청중, 원하는 결정을 한 줄로 적는다."}],
            }
        ],
    }
    issues = [i for i in validate_specs(spec) if i["severity"] == "blocker"]
    check("empty.help_deck_valid", not issues, str(issues))


def main() -> int:
    test_isolation()
    test_visual_renderer_safety()
    test_local_node_dependencies()
    test_post_motion_integrity_guard()
    test_golden()
    test_hard_cases()
    test_render()
    test_empty_args_spec_still_valid_shape()
    deeper = subprocess.run([sys.executable, str(ROOT / "tests/hard_deeper.py")], capture_output=True, text=True)
    check("deeper.suite", deeper.returncode == 0, (deeper.stdout or deeper.stderr)[-400:])
    reference = subprocess.run(
        [sys.executable, str(ROOT / "tests/test_reference_tools.py")],
        capture_output=True,
        text=True,
    )
    check(
        "reference_contracts.suite",
        reference.returncode == 0,
        (reference.stdout + reference.stderr)[-800:],
    )
    print(f"\n{len(failures)} failed" if failures else "\nALL PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
