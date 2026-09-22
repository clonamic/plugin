---
name: clonamic-write-control
description: Gate persistent writes with one proportional specification and reusable approval; skip read-only work.
---

# Clonamic Write Control

Read-only work leaves immediately without workflow state. For writes:

- clear: one chat-only development specification and approval;
- material ambiguity: one work specification, approved inspection, then one development specification;
- precise tiny change: one line with target, change, verification, rollback, and code.

Return only when scope, authority, output, or risk materially changes; implementation detail never adds a gate.

## Approval

`승인:ABC123` is a correlation code. Accept one backtick pair, fullwidth colon, whitespace, and lowercase. Plain `승인` selects the sole pending packet in the session's one approval-state directory; hosts must colocate those packets, and multiple packets require the code. One development approval authorizes the declared target boundary, operation classes, effects, checks, and rollback. Tool choice, internal executable prefixes, command count, and same-scope inspect-fix-retest-apply-deploy-backup retries are implementation details, not new gates.

An active run never asks for a CMD code, terminal command, or repeated approval. Reuse the same authorization idempotently after a timeout or pre-execution failure. A guard intervenes only for work outside the approved boundary, catastrophic effects, credentials, or a platform-owned action. Password, OAuth, biometric, and platform permission remain platform actions and do not consume the run.

For automation, apply [references/automation-contract.json](references/automation-contract.json). Host metadata creates only a candidate; a matching persisted claim grants authority. Claimed runs never wait conversationally. Replay is rejected, changes return `needs_authorization`, and credentials return `waiting_platform_action` without consuming the run.

The write packet contains only target and change, observable output, verification, effects or credentials, rollback, and project-convention conflicts. The request defines scope: choose the smallest working change, reuse existing code, and reject adjacent work. Read [references/write-contract.md](references/write-contract.md) for non-trivial or outside-project writes.

Use the `clonamic` binary when available; otherwise enforce the same contract model-side and disclose only a consequential fallback. After approval, continue autonomously until required results pass or a user-only/external blocker remains. A guard hit caused only by an internal command mismatch is a contract defect to correct inside the active run, never a reason to ask the user again.
