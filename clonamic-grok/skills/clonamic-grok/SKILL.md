---
name: clonamic-grok
description: Run one bounded installed Grok CLI request only when explicitly asked; never use for recursive or cross-executor delegation.
---

# Grok Executor

Run one local wrapper call:

```bash
python3 "$CLONAMIC_GROK_ROOT/scripts/call.py" --timeout 120 -- "<prompt>"
```

Resolve `CLONAMIC_GROK_ROOT` to the host-provided directory containing this `SKILL.md`; never scan vendor homes or execute a project-relative `scripts/call.py`. The wrapper enforces read-only, no-tools execution. Forward only explicit model, effort, or output options through `--cli-arg`; it rejects permission, sandbox, tool, bypass, and yolo flags.

Return its JSON unchanged. Do not retry, chain, treat output as completion evidence, or apply edits. Stop when `CLONAMIC_EXECUTOR_ACTIVE` is present.
On a Grok host, execute the request natively. Never call this Grok wrapper from Grok itself.
