---
name: clonamic-modular-design
description: Design an evidence-based new system or large refactor with justified modules, explicit contracts, and migration order. Skip small edits and structure questions.
---

# Clonamic Modular Design

Inventory the current system; evidence must justify modularization.

For a full architecture or large refactor, read
[module-design-rules.md](references/module-design-rules.md) and
[library-module-rules.md](references/library-module-rules.md). Read
[ai-behavior-guide.md](references/ai-behavior-guide.md) only when producing the final design artifact.

## Boundary gates

- Split only with two independent reasons to change plus independent test value, multiple consumers, or distinct cadence.
- Keep function-sized behavior with its owner.
- Commonize only with three real uses, a stable contract, and domain independence.
- Merge pass-through or inseparable boundaries and equivalent contracts.

Give each module one public entry point and typed inputs/outputs. One composition root owns wiring; siblings do not construct each other. Configuration enters as input. Removal means deleting the module and unwiring the root.

## Result

Read [references/module-contract.json](references/module-contract.json). Return one `DesignResult` with:

- current evidence and scale verdict;
- a straight main pipeline;
- field-level input and output contracts;
- declared failure behavior per module;
- dependencies and removal notes;
- decisions for splits, merges, commonization, and rejected abstractions;
- migration order and a cutover check per refactor step.

Write one `DESIGN.md` only when requested inside `approved_scope`; otherwise return the design in chat.

## Failure

Return `blocked_missing_evidence` when inspection cannot justify boundaries. Return `invalid_contract` for incompatible I/O, cycles, missing failure behavior, or ambiguous public surfaces. Do not assume missing evidence.

This skill cannot authorize writes, patch code, decide completion, or format reports.
