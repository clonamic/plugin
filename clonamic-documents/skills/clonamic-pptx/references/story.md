# Story and outline

Pick one purpose and keep its chain. Do not add a generic agenda slide unless the deck is longer than 10 slides.

| purpose | sequence | required ending |
|---|---|---|
| decide | problem → evidence → options → recommendation → request | decision + owner |
| pitch | pain → solution → why now → proof → ask | concrete ask |
| report | summary → method → findings → implication → next | next action |
| teach | goal → concept → how it works → example → apply | what the audience can now do |
| inform | context → core → evidence → summary | what to remember |
| persuade | current cost → alternative → feasibility → action | why now |

Every slide after the first needs a reason it follows the previous one (`bridge`: answer, evidence, contrast, zoom_in, zoom_out, implication). Split a slide that holds two independent conclusions; merge two slides that share one takeaway.

## Outline shape

```json
{
  "title": "…",
  "purpose": "decide",
  "slides": [
    {
      "id": "s01",
      "title": "implication, not a topic label",
      "job": "what this slide must accomplish",
      "takeaway": "one conclusion the audience can repeat",
      "must_show": ["item the eye must land on", "second required item"],
      "visual": "hero_assertion",
      "bridge": null
    }
  ]
}
```

## Choosing the visual (first match wins)

Choose `visual` from the slide's job, not for variety. Families are described in [layout.md](layout.md).

1. Last slide of decide / pitch / report → `recommendation` (the ask or next action).
2. Last slide of teach → `proof_grid` (four sentences the audience can repeat); never `recommendation`.
3. A user-supplied numeric series → `chart_focus`.
4. Two alternatives (vs, 대비, 대신, A or B, a decision question) → `comparison_2col`; never a quote.
5. 3–6 ordered steps (단계, gate, loop, 1·2·3) → `process_flow`.
6. Lookup grid (rows × columns, condition × evidence) → `table_focus`.
7. Two or more numeric facts → `metric_strip`.
8. 3–6 named claims (causes, guardrails, open items) → `proof_grid`; not a hero.
9. Teach opening with one principle → `quote_proof` (at most two per deck).
10. Opening slide with one number, or any other single assertion → `hero_assertion`.
11. Mid-deck slide with two or more named items → `proof_grid`; never a second hero.

Never use the same visual three slides in a row. At most one 2×2 grid per four slides.

## Content rules

- `title`: 3–90 chars, states the implication. Banned as titles: 개요, 현황, 소개, 솔루션, 시장 분석, 다음 단계, Overview, Introduction, Solution, Analysis, Next Steps, Agenda (agenda allowed only as a navigator in 10+ slide decks).
- `takeaway`: 12–130 chars, adds a consequence or kill criterion; never repeats the title or the ask.
- `must_show` items are the payload. Each becomes a structured element (card, row, step), never a bare two-word label. Card body pattern: `짧은 주장 — 두 줄 이유` (em dash, roughly 28+ CJK or 70+ Latin chars).
- Proof grid alone on a slide: 4 items (3 leaves the board half empty).
- Comparison: 2 columns, 3–5 items each, same criteria order, one line per item.
- Process: 3–6 steps; label 2–8 chars, detail is a full sentence (not `4주 · API`).
- Table: at most 6 columns × 7 rows; only when the audience needs lookup.
- Metric: the value contains a digit. "반복 작성" is a bullet, not a metric.
- Quote: text + attribution + 2–3 bullets implementing `must_show` under it.
- Recommendation (last decide/pitch slide): `action`, `owner`, `timing`, `success_metric`, each a clause. `owner` is a role plus what they own (`재무책임자가 한도와 집행 기록을 맡는다`), never `TBD` or one token. If unknown: `오늘 회의에서 지정하고 회의록에 적는다`.
- Only the last decide/pitch slide is an ask; the slide before it is evidence.
- Speaker notes: 60–500 chars per slide when the user wants notes.
- Never put the same sentence twice on one slide (sidebar + closer, ask + takeaway).

## Empty request

If the user only says "make slides" with no content, build a 6-slide `inform` how-to on what a good brief contains, ending with a call to action. Titles are still conclusions.
