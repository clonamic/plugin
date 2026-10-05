---
name: clonamic-team
description: Decide whether to work directly, use a worker+reviewer pair (with the clonamic-reviewer subagent), a lead with specialists, or a bounded multi-agent decision review — only when the value exceeds the coordination cost. Use before delegating to subagents or when the user asks for a team or an independent review.
---

# Clonamic Team

Default: do the work directly in one session. Choose the mode before execution; never upgrade it mid-task.

## 1. Choose the mode

| Mode | Use only when |
| --- | --- |
| Direct | Default. |
| Worker + reviewer | An independent check is worth the extra pass (high cost of a wrong result, hard-to-see defects). Independent pairs may run in parallel; pairs touching the same files run one after another. |
| Lead + specialists | At least three distinct specialties and a real coordination tier are needed. Main → lead → specialists. The lead only assigns, reviews, accepts, rejects, reassigns — never executes or integrates. One named specialist integrates. |
| Decision review | All four hold: two or more viable options, the choice affects a boundary (interface, architecture, data, public contract), repository evidence does not decide it, and a wrong choice is expensive to reverse. |

Not reasons to add agents: task size, file count, repetition, an importance label. A worker's defect or missing evidence is handled by rework, not by a bigger team. Use an external executor (another CLI or model) only when the user explicitly asks.

## 2. Assigning work

Give each agent one brief: goal, the approved IDs it owns, allowed files/targets, exclusions, the evidence it must return, and the return format. A subagent:

- works only within the intersection of the parent's approved boundary and its assignment, and never widens it;
- never asks the user for approval and never edits the parent's task state; it reports to the orchestrator;
- does not delegate further.

Writes to shared files are sequential: one writer at a time, then the next.

## 3. Review (worker + reviewer)

The reviewer is the `clonamic-reviewer` subagent shipped with this plugin ([../../agents/clonamic-reviewer.md](../../agents/clonamic-reviewer.md); Claude Code name `clonamic-harness:clonamic-reviewer`). It owns the review procedure and the ACCEPT/REJECT packet; do not restate or loosen it in the brief.

1. When the worker reports done, spawn `clonamic-reviewer` with: the approved IDs (요구N/완료N, 변경N/검증N), allowed targets and exclusions, changed paths or diff, and the worker's claimed evidence.
2. ACCEPT → the items are done; continue to `clonamic-finish`, which re-checks with its own fresh evidence.
3. REJECT → send only the rejected items and their direct dependencies back to the worker, then to the same reviewer with the same brief plus the new change.
4. Each retry must be a materially different strategy. After three distinct failed strategies on the same item, stop and report a blocker.

Fallback when the host cannot load plugin agents (Codex):

- If the host can spawn a generic subagent, spawn one with the full body of `agents/clonamic-reviewer.md` as its instructions plus the brief above.
- Otherwise run it sequentially: finish the work, then do a separate review pass yourself, following `agents/clonamic-reviewer.md` step by step and producing its packet. Say in one line that the review was not independent.

## 4. Decision review procedure

Read-only; it produces a recommendation, not an approval.

1. Give every reviewer the same question, live options, evidence, constraints, exclusions, and budget.
2. Collect positions independently before sharing any.
3. Each position states its evidence, its strongest objection, and what would falsify it.
4. Allow one rebuttal round, only for material disagreement.
5. Report `consensus` only when all positions agree for compatible reasons; otherwise `no_consensus` with the dissent preserved. If the budget runs out, `aborted` with partial positions and no recommendation.

No recursion and no retries of the review itself.

## 5. No subagents available

Keep the chosen mode as intent, do the work directly, then run the sequential review from §3. Say in one line that no independent review took place. Never simulate reviewer voices or claim a team was formed.
