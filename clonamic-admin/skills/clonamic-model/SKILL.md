---
name: clonamic-model
description: "View or change model ids and efforts in ~/.agents/models.toml, the single model registry (nothing else may hardcode model names). Runs only on the explicit /clonamic-model command or a request such as '모델 설정', '모델 변경'. Pipeline: validate availability, update registry, propagate machine settings, re-verify, back up."
disable-model-invocation: true
user-invocable: true
---

# clonamic-model — Model Registry Pipeline

Runs only on the explicit `/clonamic-model` command or an explicit model-change request; never automatically or on a schedule.

**View** (no args): print `~/.agents/models.toml` as a table — role | model | effort | transports.

**Change** (`/clonamic-model grok_exec=<id|cli-default>` or natural language):

1. **VALIDATE before writing** — run `~/.claude/hooks/model-registry-check.py --list`; the model must exist on its backend:
   - `grok_exec` → `cli-default` resolves the default shown by `~/.grok/bin/grok models`; an explicit id must be listed.
   - `gpt_exec` → the Codex model catalog (`~/.codex/config.toml` provider catalog / a cheap read-only `codex exec` probe when usage allows) must accept it.
   - `code_delegate` / `test_agent` → must be a valid Agent-tool tier (opus / sonnet / haiku / fable) or a full `claude-*` id.
   - Unknown or unlisted → REFUSE and show the available list. Never write an unvalidated id.
2. **UPDATE** `~/.agents/models.toml` — preserve comments and structure; one role per change unless the user batches.
3. **PROPAGATE only machine settings that consume the role.** Grok direct config stores
   `default_reasoning_effort` but no model default; its wrapper resolves `cli-default` per call. Do not
   propagate `gpt_exec` to `~/.codex/config.toml`: those are interactive Codex defaults.
4. **RE-VERIFY**: `model-registry-check.py` must end clean; if any selftest contract pins model behavior, run and repin in the same session. `config-doctor.py` is owner-only and is NOT shipped — skip it when absent.
5. **BACKUP**: `~/.claude/hooks/backup-to-git.sh`. Report outcome-first: role, old → new, validation evidence.

Rules: model selectors/ids live ONLY in the registry — refuse any request to hardcode one elsewhere
(core rule 2). An explicit id stays pinned; `cli-default` deliberately follows the backend default.
Do not propagate `gpt_exec` to `~/.codex/config.toml`. A model the USER names for a specific call wins
for that call without rewriting the registry.
Effort policy: `xhigh` when the backend supports it, else `high`. Explicit request only; never scheduled.
