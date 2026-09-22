---
name: clonamic-context-integrity
description: >
  Context-integrity doctrine to minimize hallucination in long sessions — verify-before-assert,
  high-context checkpointing, post-compaction staleness rules, importance-based double-pass
  compaction. Use in long sessions, when context feels saturated, after compaction, or when
  the user mentions 환각/hallucination/컨텍스트/압축.
---

# Anti-Hallucination (Context Integrity)

> Hallucination risk scales with context saturation and survives through lossy compaction.
> The defense: verify instead of recall, checkpoint before saturation, compress with a
> double pass.

## 1. Verify-before-assert

- Any fact recalled from >30 turns ago, or from before a compaction: **re-verify** via
  `rg`/Read before stating it or acting on it. Recalled line numbers are always stale.
- State verified vs assumed explicitly. An unverified claim is labeled UNVERIFIED, never
  presented as fact.
- Never fabricate CLI flags, API signatures, or file contents — check `--help`/source first
  (cheaper than one wrong command).

## 2. High-context protocol (before saturation)

- When the session is long/heavy, keep one bounded checkpoint of the active task spec, locked
  quantities, decisions and reasons, touched targets, open blockers, and verification state.
- Persist that checkpoint only through a trusted host-provided session state that is already
  authorized for the current task. Never create a scratchpad, memory row, or checkpoint file merely
  because this skill loaded.
- If the host exposes no authorized state interface, keep the bounded checkpoint in the current
  conversation and reconstruct only from visible evidence after compaction.
- Prefer re-reading a source snippet over trusting memory of it. Reads are cheap;
  wrong recall is not.
- Big multi-phase work records a compact N/N phase state in the same selected checkpoint mode; it
  never opens a second state mechanism.

## 3. Compaction (double-pass — mirrors hooks/precompact-guard.sh)

PASS 1 — extract must-keep verbatim: task spec + quantities + item states, user decisions
and reasons, file paths + key line refs, UNVERIFIED claims, open blockers, session invariants.
PASS 2 — re-scan the original: anything referenced later but missing from the summary goes
back in. Drop narration and raw tool logs first; never drop failures or corrections.

## 4. Post-compaction rules

- Treat everything recalled through a summary as **stale-by-default**: re-verify paths,
  line numbers, and progress state before the next action.
- First action after compaction on a task: re-read the trusted host checkpoint when one exists;
  otherwise reconcile the bounded conversation checkpoint against current source evidence.

## Host integration

- A host may automate the double-pass or provide a session-bound state handle. Treat either as
  available only after inspecting the current host contract.
- Without that measured capability, apply §3 manually and use the conversation fallback. Never
  install hooks, create files, or write memory as an implicit compatibility fallback.
