---
name: clonamic-code-router
description: Route coding or architecture work among native, modular-design, conservative-patch, and bounded native-review stages; keep ordinary work native.
---

# Clonamic Code Router

Choose the smallest stage that materially reduces risk; default to native.

## Route

Read [references/activation-contract.json](references/activation-contract.json), then return one `DevelopmentRoute`:

```text
DevelopmentRoute {
  stages: list[native | modular-design | supercoder | ultracode],
  reasons: list[str],
  degraded: list[str],
  ultracode: not_eligible | active | unavailable
}
```

When multiple stages qualify, order them:

1. `modular-design` for architecture, a new system, or a large refactor.
2. `supercoder` for an approved non-trivial write with stale or ambiguous patch risk.
3. `ultracode` only when all four gates pass and native isolated agents exist.

Size, file count, repetition, or importance alone never activates Ultracode. If eligible but unavailable, set `ultracode: unavailable`; do not simulate consensus.

Read [references/ownership-contract.json](references/ownership-contract.json) before specialist handoff. This plugin may consume `approved_scope`; it cannot create authorization, decide completion, format reports, install components, or select external executors.

## Failure

Missing or contradictory evidence returns native with the uncertainty in `degraded`. Routing is read-only.
