---
name: clonamic-intent-guard
description: Reject scope drift, adjacent work, duplication, speculative abstraction, and reasoning beyond sufficient evidence before non-trivial execution.
---

# Clonamic Intent Guard

Use router-loaded [guidance](../../clonamic-herness-plugin.md), or read it once. Apply [intent-contract.json](references/intent-contract.json) and return one `IntentVerdict`; rejection removes excess work and gives bounded rework.

For session display state, apply [references/session-contract.json](references/session-contract.json). Internal prompts never replace Last User Prompt. This skill is read-only: it grants no write, delegation, installation, or completion authority.
