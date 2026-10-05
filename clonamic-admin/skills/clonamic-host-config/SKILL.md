---
name: clonamic-host-config
description: Maintain the global agent setup of Claude Code (~/.claude) or Codex (~/.codex) — router file (CLAUDE.md / AGENTS.md), path-scoped rules, on-demand guides, skills, plugins, hooks, and settings.json / config.toml. Use when adding, editing, wiring, or removing global guidance, rules, guides, skills, plugins, or hooks.
---

# Clonamic Host Config

Procedure for changes to a host's global configuration. Pick the host section, then follow the shared steps.

## Hosts

| | Claude Code | Codex |
|---|---|---|
| Home | `~/.claude/` | `$CODEX_HOME` (`~/.codex/`) |
| Router file | `CLAUDE.md` | `AGENTS.md` |
| Policy gates | `guides/meta/meta-governance.md`, `guides/meta/claude-layout.md` | `guides/meta/meta-governance.md`, `guides/meta/codex-layout.md` |
| Settings | `settings.json` (JSON: `enabledPlugins`, `extraKnownMarketplaces`, `hooks`) | `config.toml` (`[plugins."<id>"] enabled = true`) |
| Hooks registry | `settings.json` → `"hooks"` (no `hooks.json`) | `hooks.json` (`PreToolUse` / `PostToolUse` + matcher) |
| Plugin CLI | `claude plugin install/uninstall/list`, `/plugin` | `codex plugin add/list` |
| Authoring skills | `skill-creator`, `plugin-dev` | `skill-creator`, `skill-installer`, `plugin-creator` |

Layer rule (both hosts): `rules/*.md` without `paths:` frontmatter are loaded at every session start. Only path-scoped rules belong in `rules/`; everything on-demand belongs in `guides/`, reached through the router file and never preloaded.

## Before any edit

1. Read the host's layout guide and `meta-governance.md` (the policy gates above), if present.
2. State intent: **add** | **edit** | **wire** | **remove**.
3. Read [references/playbooks.md](references/playbooks.md) for the matching playbook: A guide/rule · B skill · C plugin · D router file · E hook · F remove/deprecate.

## Checklist (before finishing)

- [ ] Single source of truth: no text duplicated between the router file and rules.
- [ ] A router row exists for every new rule, skill, or plugin trigger.
- [ ] Meta files in English; the user's chat language unchanged (Korean).
- [ ] Layout / governance guides updated if a convention changed.
- [ ] Shared core edits applied identically to `~/.agents/AGENTS.md` and `~/.codex/AGENTS.md` (diff the two core sections).
- [ ] After an intentional policy change, re-run your own contract checks in the same session and repin stale assertions (contracts follow config, never the reverse).
- [ ] Plugin listing verified (`plugin list` shows the expected version; never trust the exit code alone).
- [ ] User told when a host restart is needed (skills, plugins, hooks).

Report to the user in Korean: what changed, where, how it was verified, and whether a restart is needed.
