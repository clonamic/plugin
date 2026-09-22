# Specialist procedure

Produce an editable 16:9 widescreen file plus IR and QA directly.

Skill root = the directory that contains `SKILL.md` next to this `references/` directory.
Engine = `python3 "$SKILL_ROOT/scripts/run_engine.py"`.

## Order (do not skip)

**Design first.** Do not write `slide_specs.json` until `outline.json` exists and validates. The outline is the deck design: what each slide is for, what must appear, which visual, why it follows the previous slide.

1. Normalize the request into `brief.json`. Read `references/story.md`.
2. If audience, purpose, and thesis are all missing, write assumptions and design a 6-slide how-to deck. Prefer a finished deck over asking when the user demanded a full run.
3. Write `outline.json` (design). Every slide needs `job`, `must_show` (2–6 concrete items), `visual` (picked from `story.md` 케이스 표 — 두 선택이면 comparison, 3–6 이름이면 proof_grid, 첫 장 결정 질문을 quote로 쓰지 말 것), and after slide 1 `bridge_type`. Then write `slide_specs.json` that **implements** that outline — do not invent a second story. Put `purpose` on the specs root (`decide|pitch|teach|report|inform|persuade`). The engine picks color/type/layout from that. Specs block type must match the outline visual (comparison visual → comparison block, process → process_steps, table → table, 2×2 → 4 bullets, metric_strip → 숫자 metric_card 둘 이상). Never a lone paragraph. Never three recommendation slides in a row. Never three identical visuals in a row. `OUT018` / `SPC024` = 케이스와 visual이 안 맞거나 specs가 outline을 안 따른다. `SPC025` = quote 장에 must_show extras가 없다.
4. `python3 "$SKILL_ROOT/scripts/validate.py" --brief brief.json --outline outline.json --specs slide_specs.json`
5. Fix validation errors in the JSON. Do not hand-edit coordinates.
6. `python3 "$SKILL_ROOT/scripts/run_engine.py" --specs slide_specs.json --out "$OUT" --title "..." --language <brief.language>`
7. Read `qa_report.json`. If `blocker` or `major` remain, edit **slide_specs.json** (change block type, add a fourth proof card, shorten titles, turn labels into `주장 — 이유`) and rerun. At most 2 repair rounds. `VIS003` / `QA009` means the block is too thin — add body text or switch family. Open PNGs under `$OUT/slides` when they exist and reject a slide that is mostly empty card.
8. Return absolute paths of `presentation.pptx`, `deck_ir.json`, `qa_report.json` and the issue list.

Never write x/y/w/h, raw HEX, or PptxGenJS yourself.

## Brief fields

```json
{
  "purpose": "inform|persuade|decide|teach|report|pitch",
  "audience": "string",
  "audience_level": "executive|general|expert",
  "central_question": "string",
  "desired_decision_or_action": "string or null",
  "single_sentence_thesis": "<=180 chars",
  "must_include": [],
  "must_avoid": [],
  "language": "ko-KR",
  "slide_count_target": 8,
  "time_limit_minutes": null,
  "evidence_mode": "none|best_effort|strict",
  "assumptions": [],
  "unanswered_questions": []
}
```

언어는 **한국어가 기본**, 영어는 요청될 때만. `language`를 빼면 `ko-KR`. 영어 청중/원문이 없으면 한국어로 쓴다.

Default counts when silent: inform 7, decide 8, pitch 10, teach 12, report 9. Clamp 3–20.
`decide` / `pitch`: **only the last slide** uses a `recommendation` block. The slide before it is evidence (comparison, process, or 4 proof cards), not a second ask.

## SlideSpec rules

- `takeaway`: 12–130 chars, one conclusion.
- `title`: 3–90 chars, implication, not a topic label. Banned: 시장 분석, 솔루션, 개요, 현황, 다음 단계, 소개, Overview, Solution, Next Steps, Introduction, Analysis, Agenda (except navigator on 10+ decks).
- `content_blocks` 1–8. Types: `paragraph`, `bullets`, `metric_card`, `comparison`, `process_steps`, `quote`, `table`, `recommendation`, `chart`.
- Do not invent numbers. Qualitative wording if the user gave none.
- `metric_card.value` must contain a digit. “반복 작성” is a bullet, not a metric.
- `bullets`: **4 items** when that is the only block (2×2). 3 items leave the board half empty. Each item MUST be `짧은 주장 — 두 줄 이유` (em dash). Body min ~28 CJK / ~70 Latin chars. Two-word labels become empty cards and fail QA009.
- `comparison`: 2 columns, 3–5 items each, same criteria order. Each item is a claim, not a noun. Keep each item to one line (~70 Latin / ~28 CJK chars).
- Last `decide`/`pitch` slide must use a `recommendation` block (`action`, `owner`, `timing`, `success_metric`). A `recommendation` role with only bullets becomes proof cards, not the ask. `owner` / `timing` / `success_metric`는 절이다. 한국어 `오늘`/`COO`/`서명` 한 토큰은 실패. 예: `재무책임자가 한도와 집행 기록을 맡는다`. 영어는 요청 시에만, 그때도 한 단어 금지 (`The trial ends before fleet approval` 미만은 너무 짧다). `takeaway`는 킬 조건이지 `action`/제목 반복이 아니다.
- `process_steps`: 3–6 steps. `label` is 2–8 chars. `detail` is a full sentence, not `4주 · API`.
- `table`: ≤6×7. Use when the user needs lookup, not a story.
- `chart`: only with user-supplied series. `{chart_type: bar|line, categories:[], series:[{name, values:[]}], conclusion}`.
- `quote`: `text` + `attribution` **and 2–3 bullets that implement `must_show`**. Quote-only leaves a hollow card (`SPC025`). The engine will plant `must_show` as extras if you omit the bullets, but write the bullets.
- `speaker_notes`: 60–500 chars.

Vary structure across the deck. Do not emit three consecutive slides of the same block type (bullets or process_steps).

## Quality bar (CEO / CTO room)

The file must be submittable without restyling. Score the PNGs yourself against this:

- A stranger understands the conclusion in 5 seconds.
- One idea per slide. Title is the implication. `must_show` items are specific enough to fill the block (never a two-word label with no reason).
- Structure is the story, not a domain costume. Do not assume a pilot, SaaS, or any one industry. Use only the user's facts.
- Vary families. At most one 2×2 proof grid per four slides.
- Last decide/pitch slide: `owner` is a role plus what they own, never `TBD` / `지정 필요` / a bare title. If unknown, write `오늘 회의에서 지정하고 회의에 적는다`.
- `QA013` = leftover empty canvas under the last block. `QA014` = footer collapsed to `…`. Both are must-fix.
- No decorative images. No invented numbers.
- After engine, `blocker=0`. Treat `major` as must-fix unless it is `VIS000` skip.
- Reject a slide that looks like empty cards floating in the middle of the canvas. Change the block or add `주장 — 이유` body.
- Do not repeat the same sentence twice on one page (sidebar + closer, ask + takeaway). Do not add label chips that only echo the cards already on the page.

## Empty slash

Build a 6-slide `inform` how-to: what a brief must contain, then CTA. Still conclusion titles. Still the engine.
