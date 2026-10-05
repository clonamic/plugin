---
name: clonamic-team
description: Decide whether to work directly, use a worker+reviewer pair, a lead with specialists, or a bounded multi-agent decision review — only when the value exceeds the coordination cost. Use before delegating to subagents or when the user asks for a team or an independent review.
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

## 3. Review

- ACCEPT requires every required result present, fresh evidence produced after the last change, and the user's intent preserved. Missing or stale evidence is always REJECT.
- REJECT must list reasons, evidence, missing requirements, rework scope, and the condition for re-verification. An empty rejection is invalid.
- Rework covers only the rejected items and their direct dependencies, and goes back to the same reviewer.
- Each retry must be a materially different strategy. After three distinct failed strategies on the same item, stop and report a blocker.

## 4. Decision review procedure

Read-only; it produces a recommendation, not an approval.

1. Give every reviewer the same question, live options, evidence, constraints, exclusions, and budget.
2. Collect positions independently before sharing any.
3. Each position states its evidence, its strongest objection, and what would falsify it.
4. Allow one rebuttal round, only for material disagreement.
5. Report `consensus` only when all positions agree for compatible reasons; otherwise `no_consensus` with the dissent preserved. If the budget runs out, `aborted` with partial positions and no recommendation.

No recursion and no retries of the review itself.

## 5. No subagents available

Keep the chosen mode as intent, do the work directly, then run a separate local second pass against the same review rules. Say in one line that no independent review took place. Never simulate reviewer voices or claim a team was formed.
