# Story sequences

Pick one purpose and keep the chain. Do not emit a generic agenda unless the deck is longer than 10 slides. 언어는 한국어가 기본이고, 영어는 요청될 때만 쓴다.

| purpose | sequence | required ending |
|---|---|---|
| decide | problem → evidence → options → recommendation → request | decision + owner |
| pitch | pain → solution → why now → proof → ask | concrete ask |
| report | summary → method → findings → implication → next | next action |
| teach | goal → concept → how it works → example → apply | what the audience can now do |
| inform | context → core → evidence → summary | what to remember |
| persuade | current cost → alternative → feasibility → action | why now |

Every slide after the first needs a reason it follows the previous one (`bridge_type`: answer, evidence, contrast, zoom_in, zoom_out, implication).

Split a slide when it contains two independent conclusions. Merge when two slides share the same takeaway.

## Outline is the design (write this before specs)

```json
{
  "title": "…",
  "purpose": "decide",
  "narrative_arc": "problem → evidence → options → recommendation → request",
  "slides": [
    {
      "sequence": 1,
      "slide_id": "s01",
      "role": "title",
      "title": "implication, not a topic label",
      "job": "what this slide must accomplish",
      "takeaway": "one conclusion the audience can repeat",
      "must_show": ["item the eye must land on", "second required item"],
      "visual": "hero_assertion",
      "bridge_type": null
    }
  ]
}
```

`visual` is chosen from the slide's job, not rotated for variety. Engine `design.py` uses the same first-match order — do not invent a second table.

1. decide/pitch **last page** → `recommendation`
2. teach **last page** → `proof_grid` (청중이 다시 말할 네 문장). recommendation 금지
3. report **last page** → `recommendation` (다음 조치)
4. 사용자가 준 시계열/막대 숫자 → `chart_focus`
5. **두 선택** (중 무엇, vs, 대비, 대신, A or B) → `comparison_2col`. 첫 장의 결정 질문도 여기. quote 금지
6. **3–6 순서** (단계, 루프, 게이트, 1·2·3) → `process_flow`
7. **조회 칸** (표, 열, 조건×증거, status×sign-off) → `table_focus`
8. 숫자 사실이 **둘 이상** → `metric_strip`
9. **이름 있는 주장 3–6개** (원인, 가드레일, 미결 항목) → `proof_grid`. hero 금지
10. teach **첫 장** 원칙 한 문장 → `quote_proof` (덱당 최대 2)
11. 첫 장 + **숫자 하나** → `hero_assertion`
12. 그 외 첫 장/한 주장 → `hero_assertion`
13. 중간 장에 이름 있는 항목이 둘 이상이면 `proof_grid`. 숫자 하나여도 두 번째 hero를 만들지 않는다.

같은 visual을 세 장 연속 쓰지 않는다. 2×2는 네 장에 한 번이 기본이다.

목적별 첫 장:

| purpose | 첫 장이 맞는 경우 | 쓰지 말 것 |
|---|---|---|
| decide | 두 선택이면 comparison. 숫자 하나면 hero | 선택 질문을 quote로 꾸미기 |
| pitch | 숫자 둘이면 metric_strip. 가역 선택이면 hero | 첫 장을 process로 시작 |
| teach | 원칙 한 문장이면 quote | 마지막을 recommendation |
| report | 미결 항목 3개면 proof_grid 또는 table | 얇은 숫자 하나 hero |

`must_show` is the payload, not decoration. Specs implement those items as structured blocks. On `quote_proof` they become extras under the quote, not a second thesis. Do not add a second thesis on the same slide.

`takeaway` must add a consequence or kill-criterion. It cannot repeat the title or the last `action`. 2×2 bodies are two-line reasons, not a short clause. Last decide/pitch extras (`owner` / `timing` / `success_metric`) are clauses, not one word.
