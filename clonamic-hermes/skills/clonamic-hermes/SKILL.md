---
name: clonamic-hermes
description: Run one bounded installed Hermes CLI request only when explicitly asked; never use for recursive or cross-executor delegation.
---

# Hermes Executor

Hermes currently receives the bounded prompt as a command-line value, so same-host process inspection can see it while the call runs. Never send credentials or secret values through this wrapper. Codex and Claude use stdin; Grok uses a private prompt file.

Run one local wrapper call:

```bash
python3 "$CLONAMIC_HERMES_ROOT/scripts/call.py" --timeout 120 -- "<prompt>"
```

Resolve `CLONAMIC_HERMES_ROOT` to the host-provided directory containing this `SKILL.md`; never scan vendor homes or execute a project-relative `scripts/call.py`. The wrapper enforces read-only, no-tools execution. Forward only explicit model, effort, or output options through `--cli-arg`; it rejects permission, sandbox, tool, bypass, and yolo flags.

Return its JSON unchanged. Do not retry, chain, treat output as completion evidence, or apply edits. Stop when `CLONAMIC_EXECUTOR_ACTIVE` is present.
On a Hermes host, execute the request natively. Never call this Hermes wrapper from Hermes itself.
