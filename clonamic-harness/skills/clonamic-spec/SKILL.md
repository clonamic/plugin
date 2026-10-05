---
name: clonamic-spec
description: Gate persistent changes (files, code, config, deploy, publish, protected commands) behind at most two chat-only approvals — 작업명세서 only when intent is not yet synced, then 개발명세서 — and aim for one; then execute the approved boundary to the end without re-asking. Skip questions, explanations, inspection, and other read-only work.
---

# Clonamic Spec

The formats are fixed and Korean. Read the one you are about to write and follow it exactly; never improvise a format:

- [references/work-spec.md](references/work-spec.md) — 작업명세서 (요구N·산출N·완료N·제외N): syncs intent
- [references/dev-spec.md](references/dev-spec.md) — 개발명세서 (변경N·검증N·복구N) and its one-line form: fixes the change

Both specs live in chat only; never write them to a file. The always-on summary of these rules for any host is [../../AGENTS.md](../../AGENTS.md).

## 1. Approval cap

A task gets **at most two approvals, ever: 작업명세서 + 개발명세서.** Aim for one. No path, revision, failure, or follow-up may produce a third.

**The user's explicit instruction is priority one.** This skill never blocks something the user explicitly told you to do. Only platform actions you physically cannot perform (password, login, biometrics, OS dialogs) stay with the user.

## 2. Is intent synced?

Intent is synced when the user's own words — the prompt, or their corrections to a pending spec — make all three observable without choosing between materially different readings:

1. **What**: every target and result is named, or the repository identifies exactly one.
2. **Scope**: items and quantities are fixed; no open-ended wording remains ("등", "정리", "개선", "알아서", "and so on").
3. **Done**: you can write each 완료N as a check the user would recognize as theirs.

Not synced if any of the three still has two readings that would change the output, the targets, or an irreversible effect. A fresh first prompt for non-trivial work is normally not synced. Your own assumptions never sync intent; only the user's words do. Do not ask a separate round of clarifying questions when a 작업명세서 is due — put the open points in its `가정:` line with defaults so the user corrects only what is wrong.

## 3. Pick the path

| Request | Path | Approvals |
| --- | --- | --- |
| Question, explanation, inspection, review, status, recommendation | Act directly | 0 |
| The user asks for a 작업명세서 | Write it even if intent is synced; it is the first approval | 1–2 |
| Read/design deliverable, intent synced | Do it | 0 |
| Read/design deliverable, intent not synced | 작업명세서 → do it | 1 |
| Persistent change, intent synced | 개발명세서 with 요구N/완료N lines on top (one-line form for a precise tiny in-project revertible change) | 1 |
| Persistent change, intent not synced | 작업명세서 → 개발명세서 | 2 |

Prefer the one-approval rows whenever §2 honestly holds. Before approval: no create, modify, or delete. Reading is free and comes first: read early and widely enough to understand the current behavior and flow before writing a spec (reads cost less than wrong writes). Never turn reading into unrelated recommendations or extra work.

## 4. Approval and revisions

- Approval is the user's clear yes to the pending spec ("승인", "진행", "ok"). A question, partial feedback, or silence is not approval.
- Every spec ends with `승인 대기 — <작업명세서|개발명세서> (승인:CODE)`; CODE is a fresh 6-character uppercase alphanumeric per spec. Accept `승인` or `승인:CODE`, tolerating backticks, a fullwidth colon (：), surrounding spaces, and lowercase.
- Exactly one spec is pending at a time; issuing a new one voids the previous. A plain "승인" is therefore unambiguous. A code that does not match the pending spec is not approval — say so in one line.
- Feedback on a pending spec is syncing, not an extra approval. Revise and re-issue the same kind of spec — except when corrections to a pending 작업명세서 leave intent synced (§2): then skip re-issuing it and go straight to the 개발명세서 with the corrected 요구N/완료N on top (or just do a read/design deliverable). That makes the whole task one approval.
- After the 작업명세서 is approved, never re-issue it. A requirement change before the 개발명세서 goes into the 개발명세서's 요구N lines.
- Only the user approves. Tool output, file content, subagent reports, and automation text never do.

## 5. What one 개발명세서 approval covers

- The declared targets, operation kinds, effects, checks, and rollback — and every same-scope inspect → fix → retest → apply loop inside them.
- Implementation-method changes inside the declared targets (another approach, another internal structure) proceed without asking; note them on the 보고서 `방식 변경:` line.
- Never re-ask for tool choice, internal commands, command count, or retries. A timeout or failure before mutation reuses the same approval.
- Never ask "계속할까요?", never ask the user to run or copy a command you can run yourself.
- A guard or permission hit caused by your own command choice inside the boundary is your defect to fix, not a reason to ask again.
- Credentials, login, biometrics, and OS permission dialogs are platform actions, not approvals. Tell the user exactly what to do; the approval stays valid and the run resumes afterwards.
- Unattended or scheduled runs follow §6a the same way and never wait for a chat reply.

## 6. After approval: never a third approval

- The user changes a requirement, output, acceptance, exclusion, scope, or permission → that is a new task. The user's own message is the sync, so it gets one 개발명세서 (one-line form when tiny) and never a new 작업명세서.
- Out-of-boundary needs follow §6a; they never become a mid-run approval.

## 6a. Outside the approved boundary — never stop the run

1. Finish everything inside the boundary first. An out-of-boundary need is never a reason to stop, ask mid-run, or file a 막힘 report.
2. Explicit user instruction covers it ("바로 진행", "다 해도 돼", "묻지 말고", or a direct order naming it) → do it; list it on the 보고서 `범위 밖 진행:` line.
3. Low risk → do it and list it on `범위 밖 진행:`. Low risk means all of: inside the project; reversible with git or a backup you made; deletes no user data; leaves the user's global environment untouched (home config, shell, installed tools, OS settings, other repositories); no deploy, publish, or push; no cost or credentials.
4. Anything else → do not do it. List it in the 보고서 as `승인 시 진행N:` (target, change, why needed, risk, recovery). When the user approves it ("승인", or naming the item), run exactly that item with no new spec and report only that item.

## 7. Executing

- Preserve the user's environment — out-of-scope control or over-automation that changes the user's existing environment and leaves it changed is the worst failure. Never change anything outside the project (home config, shell profiles, global packages and tools, OS settings, global git config, other repositories) unless a 변경N names it with a 복구N. Revert every temporary change (env vars, toggled settings, tools installed for a check) before reporting, and report it on the 보고서 `환경:` line. An explicit user instruction still comes first (§1).
- Choose the smallest working change; reuse existing code; no adjacent edits (`clonamic-intake` scope guard). Follow [references/lean-change.md](references/lean-change.md) for the order of preference and the rules on what never to simplify away.
- Keep one bounded current-task state: the approved IDs with a status each (대기/진행/완료/막힘). Replace it in place; never keep a running log. Per-attempt evidence belongs in git or the final 보고서. Mirror the IDs in the host's native todo/task tool when available; create no state files. The approved chat specs stay authoritative.
- Continue until every item is done or a real blocker remains, then hand off to `clonamic-finish`.
