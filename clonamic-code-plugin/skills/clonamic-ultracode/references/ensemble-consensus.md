---
name: clonamic-ultracode
description: Run bounded readonly adversarial debate, orchestrator consensus, and authorized same-turn implementation with verification. Use for explicit 3-model consensus, 앙상블, 다관점 토론, material reversible high-stakes ambiguity after spec lock, or a work/intent INTERNAL_GATE decision.
---

# Ensemble Consensus

Use the host's Clonamic routing guide. Implementation is orchestrator-direct for light work or one
write-capable worker for heavy work — never spawn an implementer for debate.

## Roles — always 3, parallel readonly Task subagents

| Lens | Debate focus | Verify focus |
|------|--------------|--------------|
| Builder | feasibility, minimal diff, ship path | impl matches consensus |
| Skeptic | risks, edge cases, false agreement | claims vs diff/tests |
| Operator | proof, rollback, observability | commands run, tests pass |

Orchestrator (main session) merges, owns `<consensus_decision>` and the reply.

## Pipeline (same-turn gates)

```
[ ] 1 DEBATE    — 3 parallel readonly subagents, adversarial cross-critique
[ ] 2 CONSENSUS — <consensus_decision>: decision, scope(files/behavior/out-of-scope),
                  rationale, resolved disagreements, verify plan
[ ] 3 EXECUTE   — implement SAME TURN (direct or one Task subagent, spec carried verbatim)
[ ] 4 VERIFY    — 3 parallel readonly subagents vs diff/tests
[ ] 5 GAP-FILL  — fix verified gaps only
[ ] 6 RE-VERIFY — one final 3-lens pass; remaining gaps become one blocker/question
```

Debate, review, or consensus alone does not authorize implementation. Steps 3–6 run only when
implementation was already authorized and the candidate still satisfies DIRECT; otherwise consensus
is the result or one USER_ONLY question is asked. Ending after step 2 or 4 without implementing is a
failed turn only for already-authorized implementation work.
The full pipeline allows at most two verification rounds (steps 4 and 6). Never invoke this
skill recursively or retry a failed consensus.

## INTERNAL_GATE mode

Each lens returns `SAFE | ASK | BLOCK` plus the exact action, rollback, side effects, and
evidence. Only **3/3 SAFE** verdicts naming the identical candidate action, rollback, side effects,
and evidence permit same-turn execution when implementation was already authorized and the candidate
still satisfies DIRECT. Run one debate round and one
post-implementation verification round. On disagreement or UNKNOWN, ask one consolidated
question; do not debate again. Use actual distinct transports when explicitly requested and available.
If a requested transport is unavailable, report the blocker and never silently substitute 3-lens;
otherwise call it a 3-lens gate, never 3-model. The single implementer follows `work/models`;
meta-config remains orchestrator-direct.

## Debate prompt shape (each lens)

Give: task, locked spec (quantities verbatim — see `work/intent`), repo paths, the lens role,
and "critique the other lenses' likely positions; end with your single recommended plan".

## Verification artifact

`<ensemble_verification>`: per-lens verdict + evidence, numbered file-scoped gaps, re-verify yes/no.

## Bans

- Permission asks after consensus for already-authorized DIRECT work ("진행해도 될까요?")
- Calling 3-lens output "3-model" or claiming implementation without a same-turn code change
- Multiple parallel implementers for one change set

## Skip when

Obvious one-liner/typo the user specified; explain-only; question-only turns.
