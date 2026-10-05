---
name: clonamic-safe-patch
description: Guard an approved non-trivial code patch against stale files, ambiguous targets, and unverified results; covers the feature, debugging, and delivery stages of that patch. Skip read-only work, exact small edits, and out-of-scope writes.
---

# Clonamic Safe Patch

Use the host's native file and terminal tools. Inputs: the approved scope, target files, intended change, and fresh file evidence.

Read only the reference matching the present stage:

- [lean-discipline.md](references/lean-discipline.md) before choosing scope or dependencies;
- [development-cycle.md](references/development-cycle.md) for a feature or refactor;
- [debugging.md](references/debugging.md) after an actual failure;
- [delivery.md](references/delivery.md) before merge, deployment, or release.

## Patch procedure

1. Confirm the target and intended change are inside the approved scope.
2. Read the complete target in a bounded window; capture a hash when supported.
3. Require one exact old-content match; never guess or widen scope.
4. Without a stale check, re-read before mutation and report `capability_missing` rather than claiming hash verification.
5. Apply the smallest patch. Reject syntax-invalid candidates; restore an unexpected invalid write only when its unchanged post-image is proven.
6. After the last mutation, run the narrowest relevant syntax, lint, and test checks. Mark unsupported checks unrun.
7. Never resend an unchanged failed patch; re-read and narrow the edit before one new attempt.

Return one evidence block: status, changed files, patch results, checks run, checks unrun, and residual risks. The caller owns completion and reporting.

## Failure

- `stale_file` — target changed; re-read.
- `ambiguous_match` — multiple matches; add exact context or stop.
- `syntax_rejected` — invalid candidate; preserve the pre-image.
- `verification_failed` — required check failed; retain output.
- `capability_missing` — deterministic guard unavailable; do not claim it ran.

Never create authorization, decide completion, or format the user report. Native isolated reviewers are optional, only when independent verification is worth their coordination cost.
