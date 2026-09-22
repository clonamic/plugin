#!/usr/bin/env python3
"""Adversarial engine cases. Exit 0 only if required checks pass."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compose_ir import compose_deck  # noqa: E402
from design import recommend_visual, spec_block_matches_visual, visual_allowed  # noqa: E402
from engine_lib import THEME, resolve_theme_id  # noqa: E402
from qa_static import qa_ir  # noqa: E402
from validate import validate_outline, validate_specs  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        failures.append(name)


def slide(i: int, **kw) -> dict:
    base = {
        "slide_id": f"s{i:02d}",
        "sequence": i,
        "role": "assertion",
        "takeaway": kw.pop("takeaway", f"이것은 {i:02d}번째 슬라이드의 결론 문장이다"),
        "title": kw.pop("title", f"이것은 {i:02d}번째 슬라이드의 결론형 제목이다"),
        "content_blocks": kw.pop("content_blocks", [{"type": "bullets", "items": ["원인 — 설명이 붙는다", "대기 — 큐에서 멈춘다", "손실 — 맥락이 끊긴다"]}]),
    }
    base.update(kw)
    return base


def blockers(spec) -> list:
    return [i for i in validate_specs(spec) if i["severity"] == "blocker"]


def majors(spec) -> list:
    return [i for i in validate_specs(spec) if i["severity"] == "major"]


def ir_bad(deck) -> list:
    return [i for i in qa_ir(deck) if i["severity"] in {"blocker", "major"}]


def test_design_pick() -> None:
    two = {
        "role": "title",
        "title": "요금과 누수 중 무엇을 먼저 잠글지가 현금흐름을 가른다",
        "job": "두 선택을 같은 자리에 둔다",
        "must_show": ["요금 인상", "누수 보수"],
        "visual": "quote_proof",
    }
    rec, why = recommend_visual(two, "decide", index=1, total=7)
    check("des.two_options", rec == "comparison_2col", f"{rec} {why}")
    check("des.two_not_quote", not visual_allowed("quote_proof", rec))

    three = {
        "role": "title",
        "title": "두 미결 서명이 위생 점검을 열어 둔다",
        "job": "열린 항목 세 개를 이름 그대로 보여 준다",
        "must_show": ["가스켓 서명", "타이머 서명", "이름 없는 세 번째 항목"],
        "visual": "hero_assertion",
    }
    rec, why = recommend_visual(three, "report", index=1, total=7)
    check("des.three_named", rec == "proof_grid", f"{rec} {why}")
    check("des.three_not_hero", not visual_allowed("hero_assertion", rec))

    teach_last = {
        "role": "summary",
        "title": "이 네 문장을 설명할 수 있으면 마감을 가르칠 수 있다",
        "job": "복습 네 문장",
        "must_show": ["기록", "단계", "조건", "서명"],
        "visual": "recommendation",
    }
    rec, _ = recommend_visual(teach_last, "teach", index=8, total=8)
    check("des.teach_last", rec == "proof_grid")
    issues = validate_outline(
        {
            "purpose": "teach",
            "narrative_arc": "goal → concept → how it works → example → apply",
            "slides": [
                {
                    "sequence": 1,
                    "slide_id": "s01",
                    "role": "title",
                    "title": "순환실사는 기록이 닫힐 때 끝난다",
                    "job": "원칙을 한 문장으로 기억하게 한다",
                    "must_show": ["교육 논지", "기록의 연결"],
                    "visual": "quote_proof",
                },
                {**teach_last, "sequence": 2, "slide_id": "s02", "bridge_type": "answer"},
            ],
        }
    )
    check("des.out019", any(i["code"] in {"OUT018", "OUT019"} for i in issues), str(issues))

    last_ask = {
        "role": "recommendation",
        "title": "오늘 한도와 책임자를 회의록에 적는다",
        "job": "한도와 책임자를 오늘 적으라고 요청한다",
        "must_show": ["담당 역할과 소유", "오늘 회의가 끝나기 전"],
        "visual": "recommendation",
    }
    rec, _ = recommend_visual(last_ask, "decide", index=2, total=2)
    check("des.last_decide", rec == "recommendation")
    check(
        "des.spec_match",
        spec_block_matches_visual(
            {"content_blocks": [{"type": "recommendation", "action": "적는다"}]},
            "recommendation",
        ),
    )
    check(
        "des.spec_mismatch",
        not spec_block_matches_visual({"content_blocks": [{"type": "quote", "text": "x"}]}, "comparison_2col"),
    )

    hero = compose_deck(
        {
            "purpose": "decide",
            "slides": [
                slide(
                    1,
                    importance="hero",
                    content_blocks=[{"type": "metric_card", "value": "12주", "label": "검증 기간", "supporting_text": "되돌릴 수 있는 게이트"}],
                )
            ],
        }
    )
    ms = next(e for e in hero["slides"][0]["elements"] if e["element_id"].endswith("_ms"))
    spine = [e for e in hero["slides"][0]["elements"] if e["element_id"].endswith("_spine")]
    check("des.hero_no_distant_closer", not spine, [e["element_id"] for e in spine])
    check("des.hero_banner_hug", 1.10 < float(ms["bbox"]["h"]) < 2.50, ms["bbox"])
    rows = [e for e in hero["slides"][0]["elements"] if e.get("kind") == "shape" and re.search(r"_pr\d+$", e["element_id"])]
    check("des.hero_claim_rows", len(rows) >= 1, [e["element_id"] for e in rows])
    if rows:
        last = max(float(e["bbox"]["y"]) + float(e["bbox"]["h"]) for e in rows)
        check("des.hero_floor_filled", last >= 5.10, last)

    quote = compose_deck(
        {
            "purpose": "teach",
            "slides": [
                slide(
                    1,
                    role="title",
                    content_blocks=[{"type": "quote", "text": "실사는 수량이 아니라 기록이 닫힐 때 끝난다.", "attribution": "교육 원칙"}],
                )
            ],
        }
    )
    qspine = [e for e in quote["slides"][0]["elements"] if e["element_id"].endswith("_spine")]
    check("des.quote_no_distant_closer", not qspine, [e["element_id"] for e in qspine])
    qbox = next(e for e in quote["slides"][0]["elements"] if e["element_id"].endswith("_qbox"))
    check("des.quote_hug", float(qbox["bbox"]["h"]) < 2.80, qbox["bbox"])

    hero_ms = compose_deck(
        {
            "purpose": "pitch",
            "slides": [
                slide(
                    1,
                    importance="hero",
                    must_show=[
                        "Saturday crews stay on the existing shift",
                        "No new vehicle lease is signed during the window",
                    ],
                    content_blocks=[
                        {
                            "type": "metric_card",
                            "value": "90 days",
                            "label": "reversible field test",
                            "supporting_text": "Hold the purchase until curbside demand is observed",
                        }
                    ],
                )
            ],
        }
    )
    proofs = [
        e
        for e in hero_ms["slides"][0]["elements"]
        if e.get("kind") == "shape" and re.search(r"_pr\d+$", e["element_id"])
    ]
    check("des.hero_must_show_proofs", len(proofs) >= 2, [e["element_id"] for e in proofs])
    echo_hero = compose_deck(
        {
            "purpose": "pitch",
            "slides": [
                slide(
                    1,
                    importance="hero",
                    must_show=["A reversible 90-day trial", "Hold fleet approval until set-out demand is observed"],
                    content_blocks=[
                        {
                            "type": "metric_card",
                            "value": "90 days",
                            "label": "reversible field test",
                            "supporting_text": "Hold fleet approval until curbside set-out demand is observed",
                        }
                    ],
                )
            ],
        }
    )
    echo_txt = " ".join(e.get("text") or "" for e in echo_hero["slides"][0]["elements"] if e.get("kind") == "text")
    check("des.hero_no_echo_chips", "A reversible 90-day trial" not in echo_txt, echo_txt[:180])
    mid = compose_deck(
        {
            "purpose": "pitch",
            "slides": [
                slide(
                    1,
                    importance="hero",
                    content_blocks=[{"type": "metric_card", "value": "90 days", "label": "trial", "supporting_text": "Hold the purchase"}],
                ),
                slide(
                    2,
                    must_show=["One route as the bounded operating scope", "The Saturday collection window already exists"],
                    content_blocks=[
                        {
                            "type": "metric_card",
                            "value": "1 route",
                            "label": "bounded operating scope",
                            "supporting_text": "Collection fits within the Saturday window that already exists",
                        }
                    ],
                ),
            ],
        }
    )
    check("des.mid_metric_is_grid", mid["slides"][1]["layout_family"] == "proof_grid", mid["slides"][1]["layout_family"])


def test_outline_design() -> None:
    good = {
        "purpose": "decide",
        "narrative_arc": "problem → evidence → options → request",
        "slides": [
            {
                "sequence": 1,
                "slide_id": "s01",
                "role": "title",
                "title": "오늘 한도와 책임자를 적지 않으면 열면 안 된다",
                "job": "첫 장에서 결론과 오늘 결정할 칸을 먼저 둔다",
                "must_show": ["한도", "책임자"],
                "visual": "hero_assertion",
            },
            {
                "sequence": 2,
                "slide_id": "s02",
                "role": "recommendation",
                "title": "오늘 한도와 책임자를 회의록에 적는다",
                "job": "한도와 책임자를 오늘 적으라고 요청한다",
                "must_show": ["담당", "오늘"],
                "visual": "recommendation",
                "bridge_type": "answer",
            },
        ],
    }
    check("out.good", not [i for i in validate_outline(good) if i["severity"] == "blocker"], str(validate_outline(good)))
    thin = {"purpose": "decide", "slides": [{"role": "title", "title": "제목만"}]}
    check("out.requires_design", any(i["code"] == "OUT010" for i in validate_outline(thin)))


def test_theme_purpose() -> None:
    check("theme.decide", resolve_theme_id({"purpose": "decide"}) == "boardroom-pine")
    check("theme.pitch", resolve_theme_id({"purpose": "pitch"}) == "ink-ask")
    check("theme.teach", resolve_theme_id({"purpose": "teach"}) == "studio-lesson")
    check("theme.report", resolve_theme_id({"purpose": "report"}) == "logbook")
    deck = compose_deck({"purpose": "decide", "slides": [slide(1)]})
    check("theme.applied", deck["theme_id"] == "boardroom-pine", deck["theme_id"])
    check("theme.canvas", deck["slides"][0]["background_color"] == "F4F1EA")
    pitch = compose_deck(
        {
            "purpose": "pitch",
            "slides": [
                slide(
                    1,
                    role="recommendation",
                    takeaway="오늘 필요한 결정은 유료 파트너를 여는 것이다",
                    title="오늘 필요한 결정은 유료 파트너를 여는 것이다",
                    content_blocks=[{"type": "recommendation", "action": "유료 디자인 파트너를 연다", "owner": "GP", "timing": "today", "success_metric": "서명"}],
                )
            ],
        }
    )
    check("theme.pitch_id", pitch["theme_id"] == "ink-ask")
    check("theme.pitch_ask_banner", any(e["element_id"].endswith("_ban") for e in pitch["slides"][0]["elements"]))
    check(
        "theme.pitch_no_flush_bar",
        not any(
            e["element_id"].endswith("_meta") and float(e["bbox"]["y"]) + float(e["bbox"]["h"]) >= 7.35
            for e in pitch["slides"][0]["elements"]
            if e.get("kind") == "shape"
        ),
    )
    teach = compose_deck(
        {
            "purpose": "teach",
            "slides": [slide(1, content_blocks=[{"type": "bullets", "items": ["원인 — 설명이다", "대기 — 설명이다", "손실 — 설명이다"]}])],
        }
    )
    check("theme.teach_dots", any(e.get("shape_type") == "ellipse" for e in teach["slides"][0]["elements"]))
    teach_proc = compose_deck(
        {
            "purpose": "teach",
            "slides": [
                slide(
                    1,
                    role="process",
                    content_blocks=[
                        {
                            "type": "process_steps",
                            "steps": [{"label": f"단{i}", "detail": f"{i}번째 단계에서 범위를 잠그고 실패하면 중단한다"} for i in range(1, 5)],
                        }
                    ],
                )
            ],
        }
    )
    tp = [e for e in teach_proc["slides"][0]["elements"] if e.get("kind") == "shape" and e["element_id"].endswith("_p0")]
    check("theme.teach_stack", tp and float(tp[0]["bbox"]["w"]) > 10, tp[0]["bbox"] if tp else None)
    report_cmp = compose_deck(
        {
            "purpose": "report",
            "slides": [
                slide(
                    1,
                    role="comparison",
                    content_blocks=[
                        {
                            "type": "comparison",
                            "columns": [
                                {"title": "A", "items": ["기준 1 — 설명이 한 줄이다", "기준 2 — 설명이 한 줄이다", "기준 3 — 설명이 한 줄이다"]},
                                {"title": "B", "items": ["기준 1 — 다른 설명이 한 줄이다", "기준 2 — 다른 설명이 한 줄이다", "기준 3 — 다른 설명이 한 줄이다"]},
                            ],
                        }
                    ],
                )
            ],
        }
    )
    vs = next(e for e in report_cmp["slides"][0]["elements"] if e["element_id"].endswith("_vs"))
    check("theme.report_rule", vs.get("shape_type") == "rect", vs.get("shape_type"))


def test_volume() -> None:
    slides = []
    for i in range(1, 21):
        slides.append(slide(i, role="recommendation" if i >= 19 else "assertion"))
    spec = {"title": "20장", "language": "ko-KR", "slides": slides}
    deck = compose_deck(spec)
    check("vol.20_composes", len(deck["slides"]) == 20)
    check("vol.20_no_ir_blocker", not [i for i in qa_ir(deck) if i["severity"] == "blocker"], str(ir_bad(deck)[:3]))


def test_family_priority() -> None:
    both = {
        "slides": [
            slide(
                1,
                role="data",
                content_blocks=[
                    {"type": "chart", "chart_type": "bar", "categories": ["A", "B"], "series": [{"name": "n", "values": [1, 2]}]},
                    {"type": "table", "columns": ["A", "B"], "rows": [["1", "2"]]},
                ],
            )
        ]
    }
    deck = compose_deck(both)
    check("prio.chart_over_table", deck["slides"][0]["layout_family"] == "chart_focus")

    quote = {
        "slides": [
            slide(
                1,
                role="case_study",
                content_blocks=[
                    {"type": "quote", "text": "승인을 기다리는 시간이 더 길다.", "attribution": "운영 리드"},
                    {"type": "bullets", "items": ["대기 — 길다", "승인 — 막힌다", "최종 — 불명확"]},
                ],
            )
        ]
    }
    check("prio.quote", compose_deck(quote)["slides"][0]["layout_family"] == "quote_proof")


def test_process_and_metrics() -> None:
    steps = [{"label": f"단계{i}", "detail": f"{i}번째 게이트에서 범위를 잠그고 실패하면 중단한다"} for i in range(1, 7)]
    spec = {"slides": [slide(1, role="process", content_blocks=[{"type": "process_steps", "steps": steps}])]}
    deck = compose_deck(spec)
    check("proc.six_family", deck["slides"][0]["layout_family"] == "process_flow")
    arrows = [e for e in deck["slides"][0]["elements"] if "arr" in e["element_id"]]
    check("proc.five_arrows", len(arrows) == 5, str(len(arrows)))
    check("proc.six_no_major", not ir_bad(deck), str(ir_bad(deck)[:4]))

    cards = [{"type": "metric_card", "value": f"{i}0%", "label": f"지표{i}", "supporting_text": "파일럿 대상 워크플로 중앙값"} for i in range(1, 5)]
    spec = {"slides": [slide(1, role="data", content_blocks=cards)]}
    deck = compose_deck(spec)
    check("met.four", deck["slides"][0]["layout_family"] == "metric_strip")
    for el in deck["slides"][0]["elements"]:
        if el.get("kind") == "shape" and str((el.get("fill") or {}).get("color", "")).upper() in {
            THEME["surface"].upper(),
            THEME["surface_muted"].upper(),
        }:
            check(f"met.h.{el['element_id']}", float(el["bbox"]["h"]) < 3.45, el["bbox"]["h"])


def test_odd_grids() -> None:
    five = ["대기 — 설명이다", "재작성 — 설명이다", "버전 — 설명이다", "범위 — 설명이다", "인수 — 설명이다"]
    spec = {"slides": [slide(1, content_blocks=[{"type": "bullets", "items": five}])]}
    deck = compose_deck(spec)
    check("grid.five", deck["slides"][0]["layout_family"] == "proof_grid")
    check("grid.five_qa", not ir_bad(deck), str(ir_bad(deck)))

    one_bullet = {"slides": [slide(1, content_blocks=[{"type": "bullets", "items": ["하나만 있다"]}])]}
    fam = compose_deck(one_bullet)["slides"][0]["layout_family"]
    check("grid.one_not_forced_grid", fam in {"hero_assertion", "proof_grid"}, fam)


def test_bilingual_and_long() -> None:
    spec = {
        "language": "en-US",
        "slides": [
            slide(
                1,
                title="The priced seed should wait until one workflow is paid",
                takeaway="A priced seed should wait until one workflow is paid",
                content_blocks=[{"type": "bullets", "items": ["Cash first — a user pays before equity is priced", "Three people — enough to deliver one workflow", "Miss is cheap — a failed partner is a contract, not a round"]}],
            )
        ],
    }
    deck = compose_deck(spec, language="en-US")
    check("en.compose", not ir_bad(deck), str(ir_bad(deck)))

    long_ko = "우선 공략 세그먼트는 성장률보다 전환 비용이 낮은 중견 고객이며 지금 이 자리에서 결정해야 한다"
    spec = {"language": "ko-KR", "slides": [slide(1, title=long_ko[:90], takeaway=long_ko[:80], importance="hero", content_blocks=[{"type": "paragraph", "text": "근거 문장입니다."}])]}
    check("ko.long_title", not [i for i in qa_ir(compose_deck(spec)) if i["severity"] == "blocker"])


def test_validation_edges() -> None:
    topic = {"slides": [slide(1, title="시장 분석")]}
    check("val.topic", any(i["code"] == "SPC005" for i in validate_specs(topic)))
    word = {"slides": [slide(1, content_blocks=[{"type": "metric_card", "value": "반복 작성", "label": "낭비"}])]}
    check("val.word_metric", any(i["code"] == "SPC016" for i in majors(word)))
    short_chart = {"slides": [slide(1, content_blocks=[{"type": "chart", "categories": ["A"], "series": []}])]}
    check("val.chart_short", any(i["code"] == "SPC017" for i in blockers(short_chart)))
    decide = validate_specs({"slides": [slide(1), slide(2)]}, {"purpose": "decide"})
    check("val.decide_tail", any(i["code"] == "SPC015" for i in decide))
    huge = {
        "slides": [
            slide(
                1,
                content_blocks=[{"type": "table", "columns": list("ABCDEFG"), "rows": [[str(i)] * 7 for i in range(8)]}],
            )
        ]
    }
    check("val.table_cap", any(i["code"] == "SPC012" for i in majors(huge)))
    empty = {"slides": [slide(1, content_blocks=[])]}
    check("val.empty_blocks", any(i["code"] == "SPC006" for i in majors(empty)))
    qonly = {
        "slides": [
            slide(
                1,
                role="case_study",
                content_blocks=[{"type": "quote", "text": "원칙은 기록이 닫힐 때 끝난다.", "attribution": "강사"}],
            )
        ]
    }
    qout = {
        "slides": [
            {
                "slide_id": "s01",
                "visual": "quote_proof",
                "must_show": ["기록이 닫힌다", "수량이 기준이 아니다"],
            }
        ]
    }
    check(
        "val.spc025",
        any(i["code"] == "SPC025" for i in validate_specs(qonly, None, qout)),
        str(validate_specs(qonly, None, qout)),
    )


def test_comparison_and_quote() -> None:
    items = [f"기준 {i} — 설명이 한 줄이다" for i in range(1, 6)]
    spec = {
        "slides": [
            slide(
                1,
                role="comparison",
                content_blocks=[{"type": "comparison", "columns": [{"title": "A", "items": items}, {"title": "B", "items": items}]}],
            )
        ]
    }
    deck = compose_deck(spec)
    check("cmp.family", deck["slides"][0]["layout_family"] == "comparison_2col")
    check("cmp.qa", not ir_bad(deck), str(ir_bad(deck)))
    for el in deck["slides"][0]["elements"]:
        if el.get("kind") == "shape" and str((el.get("fill") or {}).get("color", "")).upper() in {
            THEME["surface"].upper(),
            THEME["surface_muted"].upper(),
        }:
            check("cmp.not_over_canvas", float(el["bbox"]["h"]) < 5.25, el["bbox"]["h"])

    q = {
        "slides": [
            slide(
                1,
                role="case_study",
                content_blocks=[
                    {
                        "type": "quote",
                        "text": "같은 문장을 다시 쓰는 것보다 승인을 기다리는 시간이 더 길고, 그 대기가 품질을 떨어뜨린다.",
                        "attribution": "운영 리드 · 2026-07",
                    }
                ],
            )
        ]
    }
    qdeck = compose_deck(q)
    check("quo.qa", not ir_bad(qdeck), str(ir_bad(qdeck)))
    qbox = next(e for e in qdeck["slides"][0]["elements"] if e["element_id"].endswith("_qbox"))
    check("quo.hug", float(qbox["bbox"]["h"]) < 3.25, qbox["bbox"])
    who = next(e for e in qdeck["slides"][0]["elements"] if e["element_id"].endswith("_qwho"))
    ta = next(e for e in qdeck["slides"][0]["elements"] if e["element_id"].endswith("_qta"))
    gap = float(ta["bbox"]["y"]) - (float(who["bbox"]["y"]) + float(who["bbox"]["h"]))
    check("quo.no_well", gap < 0.30, f"gap={gap:.2f}")

    filled = {
        "slides": [
            slide(
                1,
                role="case_study",
                must_show=["대기 구간이 승인보다 길다", "최종본이 사람마다 다르다"],
                content_blocks=[
                    {
                        "type": "quote",
                        "text": "같은 문장을 다시 쓰는 것보다 승인을 기다리는 시간이 더 길고, 그 대기가 품질을 떨어뜨린다.",
                        "attribution": "운영 리드 · 2026-07",
                    }
                ],
            )
        ]
    }
    fd = compose_deck(filled)
    extras = [e for e in fd["slides"][0]["elements"] if e.get("kind") == "shape" and re.search(r"_qe\d+$", e["element_id"])]
    check("quo.must_show_extras", len(extras) == 2, [e["element_id"] for e in extras])
    fq = next(e for e in fd["slides"][0]["elements"] if e["element_id"].endswith("_qbox"))
    check("quo.filled_hug", float(fq["bbox"]["h"]) < 2.80, fq["bbox"])
    check("quo.filled_qa", not ir_bad(fd), str(ir_bad(fd)))


def test_injection_and_punct() -> None:
    nasty = '<script>alert(1)</script> & "인용" · — 한글'
    spec = {"slides": [slide(1, title="스크립트는 제목이 아니라 텍스트로만 남는다", takeaway="스크립트는 제목이 아니라 텍스트로만 남는다", content_blocks=[{"type": "paragraph", "text": nasty}])]}
    deck = compose_deck(spec)
    blob = json.dumps(deck, ensure_ascii=False)
    check("inj.keeps_text", "script" in blob.lower())
    check("inj.no_ir_blocker", not [i for i in qa_ir(deck) if i["severity"] == "blocker"])


def test_pitch_overflow_and_family() -> None:
    bullets = {
        "purpose": "pitch",
        "language": "en-US",
        "slides": [
            slide(
                1,
                role="recommendation",
                title="Begin the priced seed only when the evidence travels",
                takeaway="The priced seed should begin only after customer evidence survives outside the founding team.",
                content_blocks=[
                    {
                        "type": "bullets",
                        "items": [
                            "Paid commitment — A buyer allocates budget to the defined problem and outcome",
                            "Operational use — The product enters a real workflow and creates observable learning",
                            "Repeatable pain — The same wedge resonates beyond a single bespoke engagement",
                            "Reference value — A partner can explain the product’s importance in their own words",
                        ],
                    }
                ],
            )
        ],
    }
    deck = compose_deck(bullets, language="en-US")
    check("fam.rec_bullets_are_grid", deck["slides"][0]["layout_family"] == "proof_grid", deck["slides"][0]["layout_family"])
    check("fam.rec_bullets_qa", not ir_bad(deck), str(ir_bad(deck)))

    long_cmp = {
        "purpose": "pitch",
        "language": "en-US",
        "slides": [
            slide(
                1,
                role="comparison",
                title="Pricing now makes investors absorb uncertainty customers can resolve",
                takeaway="Pricing now asks investors to absorb uncertainty that paid customers can resolve first.",
                content_blocks=[
                    {
                        "type": "comparison",
                        "columns": [
                            {
                                "title": "Priced seed now",
                                "items": [
                                    "Urgency is presented as a claim rather than a purchase",
                                    "Product scope is debated before live workflow use",
                                    "Risk is transferred into financing terms",
                                    "The seed narrative depends on forecasted behavior",
                                ],
                            },
                            {
                                "title": "Paid partners first",
                                "items": [
                                    "Budget commitment reveals which pain is urgent",
                                    "Live use forces a narrow product boundary",
                                    "Customer evidence reduces financing uncertainty",
                                    "The seed narrative begins with observed behavior",
                                ],
                            },
                        ],
                    }
                ],
            ),
            slide(
                2,
                role="recommendation",
                title="Back the sequence and help recruit the right partners",
                takeaway="The two GPs can strengthen the next raise by backing the sequence and opening the right customer doors now.",
                content_blocks=[
                    {
                        "type": "recommendation",
                        "action": "Open the paid design-partner round before starting the priced seed process",
                        "owner": "Founding team, with GP sponsorship",
                        "timing": "Before the priced seed",
                        "success_metric": "Agreed evidence gate, focused partner profile, and qualified introductions",
                    }
                ],
            ),
        ],
    }
    deck = compose_deck(long_cmp, language="en-US")
    check("pitch.cmp_family", deck["slides"][0]["layout_family"] == "comparison_2col")
    check("pitch.ask_family", deck["slides"][1]["layout_family"] == "recommendation")
    check("pitch.theme", deck["theme_id"] == "ink-ask", deck["theme_id"])
    check("pitch.no_major", not ir_bad(deck), str(ir_bad(deck)))
    meta = next(e for e in deck["slides"][1]["elements"] if e["element_id"].endswith("_meta"))
    check("pitch.meta_rect", meta.get("shape_type") == "rect", meta.get("shape_type"))
    check("pitch.meta_is_card", float(meta["bbox"]["y"]) < 5.4, meta["bbox"])
    card = next(e for e in deck["slides"][0]["elements"] if e["element_id"].endswith("_col0"))
    check("pitch.card_rect", card.get("shape_type") == "rect", card.get("shape_type"))
    rec_ban = next((e for e in compose_deck({"purpose": "report", "slides": [slide(1, role="recommendation", content_blocks=[{"type": "recommendation", "action": "Keep the scope line", "owner": "COO", "timing": "this week", "success_metric": "named owners"}])]}, language="en-US")["slides"][0]["elements"] if e["element_id"].endswith("_ban")), None)
    check("report.ban_rect", rec_ban and rec_ban.get("shape_type") == "rect", rec_ban)
    exec_deck = compose_deck(
        {
            "purpose": "decide",
            "title": "한도와 책임자",
            "slides": [
                slide(1, content_blocks=[{"type": "bullets", "items": ["범위 — 한 흐름만", "권한 — 최소 허용", "중단 — 신호와 조치"]}]),
                slide(2, role="recommendation", content_blocks=[{"type": "recommendation", "action": "오늘 한도를 적는다", "owner": "COO", "timing": "오늘", "success_metric": "회의록"}]),
            ],
        }
    )
    check("exec.page_index", any(e["element_id"].endswith("_pg") for e in exec_deck["slides"][0]["elements"]))
    cut = compose_deck(
        {
            "purpose": "decide",
            "title": "Keep Capacity Flexible Until Demand Is Proven at the Plant",
            "language": "en-US",
            "slides": [
                slide(
                    1,
                    content_blocks=[
                        {"type": "bullets", "items": ["Staff — cost locks in", "Hours — coverage expands", "Handoff — more layers", "Unwind — slower than overtime"]}
                    ],
                ),
                slide(
                    2,
                    role="recommendation",
                    takeaway="Hold the second shift until overtime rules and one owner exist",
                    content_blocks=[
                        {
                            "type": "recommendation",
                            "action": "Do not add a second shift this quarter",
                            "owner": "COO",
                            "timing": "this quarter",
                            "success_metric": "one production owner",
                        }
                    ],
                ),
            ],
        },
        title="Keep Capacity Flexible Until Demand Is Proven at the Plant",
        language="en-US",
    )
    foot = next(e["text"] for e in cut["slides"][0]["elements"] if e["element_id"].endswith("_deck"))
    check("exec.footer_word", not foot.rstrip("…").endswith(("Pro", "Is")), foot)
    check("exec.footer_not_ellipsis", foot not in {"…", "..."} and len(foot) >= 12, foot)
    from compose_ir import _ellipsize, _footer_title

    check("exec.ellipsize_never_lone", _ellipsize("Buy certainty before permanent capacity", 8.40, 10, "en-US", 0.26) != "…")
    long_en = "Keep Capacity Flexible Until Demand Is Proven at the Plant and the Cost Base Stays Variable"
    ft_txt, _, _, _ = _footer_title(long_en, "en-US")
    check("exec.footer_long_en", "Capacity" in ft_txt and ft_txt not in {"…", "..."}, ft_txt)
    ft_ko, _, _, _ = _footer_title("내부거래 승인과 증빙을 한 장에서 다시 설명할 수 있게 남기는 법", "ko-KR")
    check("exec.footer_long_ko", len(ft_ko) >= 8 and ft_ko not in {"…", "..."}, ft_ko)
    last = cut["slides"][1]
    rec_bottom = max(
        float(e["bbox"]["y"]) + float(e["bbox"]["h"])
        for e in last["elements"]
        if e.get("kind") == "shape"
    )
    check("exec.closing_fills", rec_bottom > 5.2, rec_bottom)
    four = [e for e in cut["slides"][0]["elements"] if e.get("kind") == "shape" and str((e.get("fill") or {}).get("color", "")).upper() == THEME["surface"].upper() and "_g" in e["element_id"]]
    if four:
        check("exec.tight_2x2", all(0.9 < float(e["bbox"]["h"]) < 2.6 for e in four), [e["bbox"]["h"] for e in four])
    cards = [
        e
        for e in exec_deck["slides"][0]["elements"]
        if e.get("kind") == "shape" and str((e.get("fill") or {}).get("color", "")).upper() in {THEME["surface"].upper(), THEME["surface_muted"].upper()}
    ]
    check("exec.top_anchor", cards and min(float(e["bbox"]["y"]) for e in cards) < 2.85, cards[0]["bbox"] if cards else None)


def test_render_adversarial() -> None:
    gates = [{"label": f"G{i}", "detail": f"{i}주 차에 중단 여부를 숫자로 판정한다"} for i in range(1, 7)]
    spec = {
        "title": "adversarial",
        "language": "ko-KR",
        "slides": [
            slide(
                1,
                role="data",
                takeaway="검증이 다른 단계보다 길다",
                title="검증이 다른 단계보다 길다",
                content_blocks=[
                    {
                        "type": "chart",
                        "chart_type": "bar",
                        "categories": ["접수", "검토", "검증", "완료", "보류", "재작업"],
                        "series": [{"name": "시간", "values": [2, 3, 8, 1, 4, 5]}],
                        "conclusion": "검증이 가장 길다",
                    }
                ],
            ),
            slide(
                2,
                role="process",
                takeaway="여섯 게이트로 범위를 잠근다",
                title="여섯 게이트로 범위를 잠근다",
                content_blocks=[{"type": "process_steps", "steps": gates}],
            ),
            slide(
                3,
                role="comparison",
                takeaway="관리형이 오늘 결정에 맞다",
                title="관리형이 오늘 결정에 맞다",
                content_blocks=[
                    {
                        "type": "comparison",
                        "columns": [
                            {"title": "내부", "items": ["착수가 늦다", "범위가 커진다", "회수가 어렵다"]},
                            {"title": "관리형", "items": ["착수가 빠르다", "범위가 고정된다", "게이트에서 끊는다"]},
                        ],
                    }
                ],
            ),
            slide(
                4,
                role="recommendation",
                takeaway="운영 총괄이 오늘 한도를 확정하면 검증을 시작할 수 있다",
                title="오늘 한도와 책임자를 확정해야 실행이 시작된다",
                content_blocks=[
                    {
                        "type": "recommendation",
                        "action": "한도와 책임자를 오늘 적는다",
                        "owner": "운영 총괄과 제품 책임자",
                        "timing": "오늘 의사결정 회의 종료 전",
                        "success_metric": "승인 한도와 검증 책임자가 회의록에 모두 기록된다",
                    }
                ],
            ),
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "specs.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out = Path(td) / "out"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_engine.py"), "--specs", str(p), "--out", str(out), "--title", "adv"],
            capture_output=True,
            text=True,
        )
        check("adv.engine", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
        if (out / "qa_report.json").exists():
            qa = json.loads((out / "qa_report.json").read_text(encoding="utf-8"))
            check("adv.no_blocker", qa.get("blocker", 1) == 0, qa)
            check("adv.no_major", qa.get("major", 1) == 0, qa.get("issues"))


def main() -> int:
    test_design_pick()
    test_outline_design()
    test_theme_purpose()
    test_volume()
    test_family_priority()
    test_process_and_metrics()
    test_odd_grids()
    test_bilingual_and_long()
    test_validation_edges()
    test_comparison_and_quote()
    test_injection_and_punct()
    test_pitch_overflow_and_family()
    test_render_adversarial()
    print(f"\n{len(failures)} failed" if failures else "\nALL PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
