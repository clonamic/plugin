---
name: clonamic-my-language-review
description: Review one draft against a derived Clonamic style profile only inside an active explicit my-language invocation.
disable-model-invocation: true
user-invocable: false
---

# Clonamic My Language Review

This is a portable review contract, not an independently routed command. The explicit main skill
owns the review pass. A host may bind this contract to the package's native child-agent adapter;
a host without that adapter runs the same check sequentially in the main command.

Inputs are the current draft, the current derived profile, and the review contract from the main
skill, plus `active_command=/clonamic-my-language`. Refuse as `refused_inactive_invocation` when
that exact active command is absent. Check observable style fit only after confirming that facts, quoted text, numbers,
identifiers, code, and requested structure remain unchanged. Use no raw historical prompt and
persist nothing.

Return the draft unchanged when it passes. Otherwise return one corrected draft without analysis
or commentary. Never broaden the task or imitate unsupported quirks.
