# Korean patterns

Contextual candidates. Not authorship signals. One occurrence is not enough unless the table says otherwise.

Each row: trigger → exception → minimal repair. Word presence alone is not a `warning`.

Cut the empty frame. Keep the source claim. Do not invent a reason, number, or actor to “fill” the hole.

## Translationese and abstraction

| ID | Trigger | Exception | Repair |
|---|---|---|---|
| KO-TR-001 | `~에 대해` ≥3 / paragraph | contrast, definition, statute title | drop some; use object/topic noun |
| KO-TR-002 | `을/를 통해` or `통하여` repeated | channel/method *is* the news | actor + verb; keep the one that names the channel |
| KO-TR-003 | `에 있어서` / `관련하여` / `기반으로 하여` chain | contract/rule text, needed contrast | short particle, verb, or split |
| KO-TR-004 | `가지고 있다` / `보유하고 있다` as empty have | real rights, assets, inventory | `있다` / concrete verb |
| KO-TR-005 | `되어지다` or stacked `에 의해` | actor unknown/hidden; result is the topic | name the actor or keep one passive. Default `suggestion` |
| KO-TR-006 | `할 수 있다` on every conclusion | real permission/capability | `한다` / `하려면` / `필요하다` |
| KO-TR-007 | stacked future `것이다`, or empty formal `한 것이다` / `다는 것이다` / `다는 뜻이다` | official plan/legal force; a real definition | drop the wrapper or use present. Default 확인=아니오 for the empty wrapper |
| KO-TR-008 | `알아보겠습니다` / `살펴보겠습니다` / `에 대해 알아` as openers | a title, show, product name, or quoted invitation | start with the subject; drop the tour-guide frame |
| KO-TR-009 | empty close or stacked hedge: `라고 할 수 있습니다` / `라고 볼 수 있다` / `하는 것이 중요합니다` / `것 같습니다` stacked (`볼 수 있을 것 같습니다`) | one genuine uncertainty or a legal hedge | drop the wrappers; keep the claim’s real modality. Default 확인=아니오 |
| KO-TR-010 | empty nominalization: `개선을 진행하다` / `향상을 도모하다` / `제공을 하다` / `활용을 하다` | the noun is a defined deliverable | verb + object (`개선했다`). Default 확인=아니오 |
| KO-TR-011 | abstract subject + all-purpose verb: `시스템은 보여준다/제공한다/가져온다` with no named actor | the system *is* the actor; result is the topic | subject = who actually does it, only if that who is already in the source. Else drop the verb padding. Default 확인=아니오 |
| KO-ABS-001 | `전략적/혁신적/효과적` + noun stack | defined term or product name | restore actor, object, measurable result |
| KO-ABS-002 | `중요하다/핵심이다/필수적이다` with no why | title; reason in the next sentence | add reason or `[확인 필요]` — do not invent one |
| KO-ABS-003 | praise-only `획기적/패러다임/시너지/가치 창출/지속가능한 성장` with no number or named change | brand line; quoted slogan | cut the praise or `[확인 필요]`. Do not invent a metric. Default 확인=아니오 for the cut |
| KO-ABS-004 | padding `다양한/여러 가지/전반적으로/종합적으로/다각도로/면밀히` with no inventory | a real list follows | drop the pad or name the items. Default 확인=아니오 |
| KO-ABS-005 | `-성/-적/-화` chain with no referent (`전략적 효과성의 극대화`) | a defined technical term (`가용성`, `멱등성`) | verb + object from the source. Default 확인=아니오 |

Do not “improve” `사용자 경험의 향상에 기여` into “반복 입력을 줄여” unless the source said that.

## Hollow rhythm

These are machine-frame tells, not authorship scores. One earned contrast is not a hit.

| ID | Trigger | Exception | Repair |
|---|---|---|---|
| KO-RHY-001 | hollow negative parallel: `단순한 X가 아닙니다. Y입니다` / `X가 아니라 Y` / `진짜 문제는 X가 아니라` when Y is abstract (`마음가짐`, `본질`, `패러다임`) | Y is a number, named actor, channel, or concrete alternative | drop the rejected half; write the positive claim. Default 확인=아니오 |
| KO-RHY-002 | throat-clear before the first fact: `본 문서에서는` / `이번 글에서는` / `먼저 ~를 살펴보면` / `주목할 점은` / `이 점에서` / `이 관점에서` | abstract, agenda, talk invite | start with the fact. Overlaps KO-TR-008 — cite both only if both fire independently; else the opener rule |
| KO-RHY-003 | slogan close `~할 때입니다` / `지금이야말로` with no named action | a dated call to action the source already states | drop the slogan; keep the action if present. Default 확인=아니오 |

Word presence of `아니라` or a lone `이는` is not a hit.

## Structure

| ID | Trigger | Exception | Repair |
|---|---|---|---|
| KO-STRUCT-001 | one sentence mixes condition + contrast + conclusion (어절 수는 참고일 뿐) | statute; meaning needs one sentence | split claim vs condition |
| KO-STRUCT-002 | paragraph-opener run: `또한/그리고/더 나아가/아울러/따라서/즉` or repeated `이는` | intended list rhythm; logical therefore | name delete/contrast/cause/order, or drop the opener |
| KO-STRUCT-003 | whole passage is mechanically even in sentence length, **or** four+ identical sentence endings in running prose | tables, checklists, command lists | `info` only; do not rewrite for variety |
| KO-STRUCT-004 | forced three-item lists that are not independent | three real categories | merge or reorder |
| KO-STRUCT-005 | every paragraph ends `요약하면/결론적으로` | real conclusion section | drop the label; state the next fact/action |
| KO-STRUCT-006 | title is only abstract nouns | fixed academic/legal title | title that states the information or action |
| KO-STRUCT-007 | repeated `먼저`–`반면`–`결국` (or `첫째`–`둘째`–`셋째` with no independent items) as a paragraph template | a real three-step procedure | drop the labels; keep the three facts in source order. Default 확인=아니오 |

`KO-STRUCT-003` is `info` only.

## Register

| ID | Trigger | Exception | Repair |
|---|---|---|---|
| KO-REG-001 | `-합니다/-해요/-한다` mixed in one paragraph | speaker/quote/UI changed | unify to the source target; do not randomize endings |
| KO-REG-002 | honorific padding blows up length | formality is required | keep honorific; cut extra hedges |
| KO-REG-003 | banmal/colloquial in a formal doc | quote or intentionally informal passage | mark the boundary or unify |
| KO-REG-004 | sudden first-person experience not in the source | — | delete or `[확인 필요]`; never invent feeling |

Dialect, informal voice, and intentional 반말 are not defects.

## Form

| ID | Trigger | Exception | Repair |
|---|---|---|---|
| KO-FORM-001 | clear typo / spacing error (`않됩니다`→`안 됩니다`; 시계를 `맞혔다`→`맞췄다`) | quote; already-standard `안 됩니다`; 정답을 `맞혔다` | suggest with reason; default 확인=예 |
| KO-FORM-002 | comma right after a connective ending (`-고,` `-며,` `-지만,` `-면서,`) with no needed pause | a real list comma; legal enumeration | drop that comma. Default 확인=아니오 |
| KO-FORM-004 | romanization/product spelling drift | apply only with a glossary | show every site; do not invent a spelling |

Do not enforce “통계상 흔한 띄어쓰기” or comma *counts*. `KO-FORM-002` is only the connective-plus-comma tell.

## Before/after

One notice, several frames, one edit. Numbers stay. No new metric.

Before:

> 본 문서에서는 배포에 대해 알아보겠습니다. 먼저 시스템은 개선을 보여줍니다. 반면 전략적 효과성의 극대화가 중요하다고 볼 수 있을 것 같습니다. 결국 지금이야말로 움직일 때입니다. 팀은 소통을 통해, 리뷰를 통해 진행하고, API를 통해 결제 상태를 조회합니다. 처리 건수는 128건입니다.

After (edit):

> 팀은 소통과 리뷰로 진행합니다. API를 통해 결제 상태를 조회합니다. 처리 건수는 128건입니다.
