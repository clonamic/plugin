---
name: clonamic-supercoder
description: Guard an approved non-trivial code patch against stale files and ambiguous targets. Skip read-only work, exact small edits, and out-of-scope writes.
---

# Clonamic Supercoder

Use native file and terminal tools under the patch contract.

Read only the reference matching the present stage:

- [lean-discipline.md](references/lean-discipline.md) before choosing scope or dependencies;
- [development-cycle.md](references/development-cycle.md) for a feature or refactor;
- [debugging.md](references/debugging.md) after an actual failure;
- [delivery.md](references/delivery.md) before merge, deployment, or release.

## Patch contract

Read [references/patch-contract.json](references/patch-contract.json), then:

1. Confirm the target and intended change are inside `approved_scope`.
2. Read the complete target in a bounded window; capture a hash when supported.
3. Require one exact old-content match; never guess or widen scope.
4. Without a stale check, re-read before mutation and report `capability_missing` rather than claiming hash verification.
5. Apply the smallest patch. Reject syntax-invalid candidates; restore an unexpected invalid write only when its unchanged post-image is proven.
6. After the last mutation, run the narrowest relevant syntax, lint, and test checks. Mark unsupported checks unrun.

Return one `CodeEvidence`: status, changed files, patch results, run and unrun checks, and risks. The consumer owns completion and reporting.

## Failure

- `stale_file` — target changed; re-read.
- `ambiguous_match` — multiple matches; add exact context or stop.
- `syntax_rejected` — invalid candidate; preserve the pre-image.
- `verification_failed` — required check failed; retain output.
- `capability_missing` — deterministic guard unavailable; do not claim it ran.

Never choose an external executor, create authorization, decide completion, or format reports. Native isolated reviewers are optional only when independent verification is worth their coordination cost.
