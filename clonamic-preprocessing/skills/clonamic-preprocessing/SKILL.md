---
name: clonamic-preprocessing
description: Normalize fuzzy or multi-item input, clarify, queue independent work, and run loop_auto only by explicit opt-in. Skip precise single-item requests.
---

# Clonamic Preprocessing

Use only when normalization, material clarification, or a queue helps. Keep precise single items native.

## Runtime

Use `scripts/preprocessing.py`; read [references/runtime-contract.json](references/runtime-contract.json) before queue persistence.

- `normalize_text(text)` — derive a compact comparison and display view. Never execute this view.
- `clarification_contract(text, missing_fields)` — ask only for caller-identified material gaps.
- `enqueue`, `claim_next`, `record`, `queue_state` — operate a priority/FIFO queue at an explicit path.
- `run_loop_auto(path, executor, enabled=True)` — drain queued items through a caller-supplied callable.

The queue stores the byte-for-byte caller text in `text` and a separate `normalized_text` view, plus priority, sequence, state, claim token, attempts, and result. Executors receive `text`; normalization never replaces code, literals, spacing, or other actionable payload. Mutations use bounded locking and atomic replacement. Reclaimed stale work invalidates its old token.

## Explicit loop_auto

Run only when the user request or accepted packet sets `loop_auto=true`; never infer it from size or queue length. The caller owns the executor and each item.

Stop on executor error or step limit, preserve the failed item, and leave later items pending. Disabled means no calls or mutation.

## Result

Return one `PreprocessingResult` with normalized input, questions, queued IDs, loop status, and runtime error. The caller owns execution and response.
