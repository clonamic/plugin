---
name: clonamic-delegate
description: Send one bounded, read-only request to another installed agent CLI (claude, grok, or hermes) and return its JSON result. Use only when the user explicitly asks for a second opinion or answer from that named CLI; never for recursive or chained delegation.
---

# Clonamic Delegate

Run exactly one wrapper call through the named provider:

```bash
python3 "$CLONAMIC_DELEGATE_ROOT/scripts/call.py" --provider <claude|grok|hermes> --timeout 120 -- "<prompt>"
```

- Resolve `CLONAMIC_DELEGATE_ROOT` to the host-provided directory containing this `SKILL.md`. Never scan vendor homes or run a project-relative `scripts/call.py`.
- Requires Python 3.12+. If `python3` is older, install 3.12 (`uv python install 3.12`, or the OS package manager) and run the script with it; do not fall back to an older interpreter.
- The wrapper runs the CLI read-only with tools disabled, bounds the timeout (max 600 s) and the captured output (64 KiB per stream), redacts secrets, and stops on `CLONAMIC_EXECUTOR_ACTIVE` (recursion guard).
- Forward only explicit model, effort, or output options through `--cli-arg` (for example `--cli-arg=--model --cli-arg=<id>`). Permission, sandbox, tool, approval, bypass, dangerous, and yolo flags are rejected.

## Providers

| Provider | CLI | Prompt transport |
|---|---|---|
| `claude` | `claude -p --permission-mode plan --tools ""` | stdin |
| `grok` | `grok --permission-mode plan --no-subagents --tools ""` | private temp file (mode 0600, deleted after the call) |
| `hermes` | `hermes --ignore-rules -z <prompt> -t ""` | command-line value |

Hermes receives the prompt as a command-line value, so same-host process inspection can see it while the call runs. Never send credentials or secret values to the `hermes` provider.

## Rules

- Never call a provider from its own host. Never call this Claude wrapper from Claude itself (`--provider claude` on a Claude host): do the work natively. The same applies to `grok` on Grok and `hermes` on Hermes.
- Return the JSON unchanged (`ok`, `provider`, `output`, `stderr`, `error`, `exit_code`, `timed_out`, `duration_ms`).
- Do not retry, chain providers, apply edits from the output, or treat the output as evidence that work is done.
