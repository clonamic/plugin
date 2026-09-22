---
name: dumbify
description: Use ONLY on content the user asked to have written for publication (post, caption, script, newsletter, long-form) — never on my own work reports to the user, commit messages, code comments, or config docs. Use when writing or auditing content that has to be easy to follow — explainer reels, teaching carousels, how-to scripts, any piece that teaches or explains something — or when a draft feels dense, jargony, high-effort, or hard to follow. Lowers reading level and mental load so people keep watching and reading. Pairs with the other writing skills in this pack.
license: MIT
metadata:
  category: writing
  source: community
  source_repo: artemnovitckii/content-skills
  source_type: community
  date_added: "2026-08-02"
  author: artemnovitckii
  license_source: "https://github.com/artemnovitckii/content-skills/blob/master/LICENSE"
  local_changes: "scope guard (harness rules 4/8), Korean addendum on anti-ai-writing and dumbify"
---

# Dumbify

## Scope (harness rule — read before applying anything below)

**Applies ONLY to** content the user asked to have written or polished for publication: posts,
captions, carousels, reel/video scripts, newsletters, threads, long-form, landing copy.

**Never applies to** — the harness core rules own these, and this skill must leave them alone:

- the assistant's own work reports (core rule 8: ONE flat `- 항목 — 결과/수치` list). That em dash
  and that bullet list are the mandated report form, not the formatting tells this skill flags.
- commit messages, PR bodies, changelogs (core rule 4)
- code, code comments, config and meta/doc files (`rules/engineering.md`)
- design-gate text, refusals, apologies

If the request is about the harness or the codebase rather than a piece of content, this is the
wrong skill — report normally instead.

People don't churn because content is too simple. They churn because following it is **too much work.** Every bit of mental effort — a fancy word, a nested sentence, undefined jargon — is a reason to swipe away. This skill cuts that effort.

**Target: ~8th-grade reading level for the body, ~6th for hooks.** Easy to follow = low strain = high retention.

## Simple language, not simple ideas

You are lowering the **reading level**, not dumbing down the thinking. The idea can be sophisticated; the words shouldn't be. **Simple ≠ simplistic.** A sharp 13-year-old should be able to *follow* it — that doesn't mean the insight is for 13-year-olds.

## Where it earns its keep

- **High value:** explainers, educational/teaching content, how-to, anything on a technical, financial, or abstract topic. This is where dense writing kills retention.
- **Low value:** already-conversational captions, short hooks, casual personal stories — these come out simple naturally. Don't force this skill where there's nothing to simplify.

## The moves

1. **Cut jargon** — or swap it for the word you'd use telling a friend who isn't in the field. (Jargon the audience *shares* is fine — it's only friction when they don't have it. If you have an audience profile, respect the jargon they already know; a technical audience keeps its technical words.)
2. **One idea per sentence** — break nested clauses into separate sentences.
3. **Common words over fancy ones** — *use* not utilize, *help* not facilitate, *show* not demonstrate, *enough* not sufficient, *about* not approximately.
4. **Concrete over abstract** — "the export button" not "the relevant control"; "you'll save 2 hours" not "efficiency gains."
5. **Active voice** — "the model picks the next word," not "the next word is selected by the model."
6. **Cut filler** that adds no meaning — "basically," "in order to," "the fact that."
7. **Teach by example** — one concrete example lowers load more than a precise definition. Show it happening.

## Don't let it fight the other skills

- **Rhythm (storytelling):** simplify the **words and structure, not the length variety.** A long sentence is fine if it's made of simple words and reads in one breath. **Never flatten everything into short choppy sentences to "hit a grade level"** — that kills the music storytelling builds. Vary length; keep words plain.
- **Specificity (anti-ai-writing):** these *agree*. Concrete specifics — a number, a name, an example — make a piece easier to follow, not harder. "$1,000 becomes $10,000 in 30 years" is both more specific and more readable than "your money grows substantially."
- **Voice:** don't sand off your personality to simplify. Keep your words and your slang; cut the complexity *around* them.

## How to gauge the level (no tool needed)

- **Read it aloud.** Stumble, run out of breath, or have to re-read a sentence? Too dense — break it up.
- **The 13-year-old test.** Would a sharp 13-year-old follow it on the first pass?
- **Spot the load:** flag words over 3 syllables that have a plain substitute, sentences over ~25 words, more than one clause nested in a sentence, and any jargon the audience may not share.

## Writing mode

Draft normally first. Then do a load pass: find the two or three densest sentences and lighten them — plainer words, split the nests, add an example where a definition is doing the work.

## Audit mode

Flag each high-load spot with the **exact line**, then give the simpler rewrite. Keep the meaning and the voice intact.

```
SIMPLIFY AUDIT (target ~8th grade):
  Jargon:        FLAG — "returns compound on the principal" → "you earn money on the money you already earned"
  Nested clause: FLAG — "Because the gains, which accrue annually, are reinvested, the balance grows faster"
                 → "Each year's gains get added back in. So the next year, they earn too."
  Abstraction:   FLAG — "significant long-term growth" → "$1,000 becomes over $10,000 in 30 years"
  Reading level: ~11th grade → rewrite lands ~7th
  Rewrite: [plainer version, rhythm and voice preserved]
```

## Anti-overfitting

Don't baby-talk. Don't strip nuance the idea needs. Don't make every sentence short — that's flattening, not simplifying. Don't remove a technical term the audience knows and expects. The test: **could a smart person in the target audience follow this without effort, while still feeling it respects their intelligence?** If it reads as dumbed-down, you went too far.

## 한국어 원고 (addendum — not upstream)

The blocklists above are English. The diseases, the specificity ladder and the negative-parallelism
ban are language-independent and still apply; swap the vocab list for these when the piece is Korean.

- **부정 병렬** — "단순한 X가 아닙니다. Y입니다", "X가 아니라 Y다", "진짜 문제는 X가 아니라 Y다".
  영어판과 같은 규칙: B가 구체적(숫자·사례·메커니즘)이면 허용, 막연한 의미부여면 삭제.
- **번역투** — "~에 대해 알아보겠습니다", "~라고 할 수 있습니다", "~하는 것이 중요합니다", "~를 통해".
  바로 말한다.
- **과잉 완충** — "~인 것 같습니다", "~라고 볼 수 있을 것 같습니다". 입장을 정하거나 문장을 지운다.
- **의미 인플레** — 핵심, 필수, 혁신적, 획기적, 압도적, 게임체인저. 숫자가 있으면 숫자를, 없으면 주장을 낮춘다.
- **명사화 과잉** — "개선을 진행하였습니다" → "개선했습니다". 동사를 동사로 쓴다.
- **3항 강박** — 실제 항목이 2개나 4개인데 3개로 맞춘 목록. 진짜 개수는 고르지 않다.
- 서식 tell(이모지·해시태그 도배, 불릿 벽)은 영어판 그대로 적용.
