---
name: clonamic-team-control
description: Choose direct work, a worker-reviewer pair, or a specialist lead when value exceeds coordination cost.
---

# Clonamic Team Control

Use router-loaded [guidance](../../clonamic-herness-plugin.md), or read it once. Apply [team-contract.json](references/team-contract.json). Select prospectively; size, repetition, importance, later defects, and missing evidence do not promote the mode.

- `paired`: one direct worker, then an independent reviewer after result and fresh evidence. Isolated pairs may run in parallel; shared files stay sequential.
- `lead_workers`: at least three specialists and a necessary coordination tier. Main → lead → specialists; the lead only assigns and reviews, one specialist integrates, colliding writes serialize, and all results precede review.
- unavailable native subagents: preserve intended mode, set `actual_team: false`, run a local sequential second pass, and do not claim independent review.

Internal assignments require exact parent ID and session, then consume only the scope intersection. Apply [references/review-contract.json](references/review-contract.json): `ACCEPT` needs every result, fresh evidence, and preserved intent; otherwise return a complete rejection packet and bounded same-reviewer rework. Three distinct failed strategies produce a blocker.

UX evaluation uses [evaluation-contract.json](references/evaluation-contract.json); fixture metadata is not evidence.
