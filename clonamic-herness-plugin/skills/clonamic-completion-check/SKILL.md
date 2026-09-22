---
name: clonamic-completion-check
description: Verify required results immediately before reporting non-trivial changed work complete. Skip read-only answers and trivial acknowledgements.
---

# Clonamic Completion Check

Re-read the request and compare every requirement with observable state after the final mutation.

## Gate

For every required item, record:

- delivered artifact or state;
- current evidence from this run;
- verdict: complete or unmet.

Fresh evidence is the exact required test, diff, remote state, installed state, or output. Exit status proves only process exit; pre-mutation evidence is stale.

Continue when an unmet item remains actionable. After three materially different failed corrections for the same item, report a blocker.

When available, build the manifest in [references/completion-manifest.md](references/completion-manifest.md) and run `clonamic verify <manifest>`.

Only a complete verdict permits `clonamic-report`.
