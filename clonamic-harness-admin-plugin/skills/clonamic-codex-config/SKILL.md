---
name: clonamic-codex-config
description: Maintain Codex global setup — AGENTS.md router, ~/.codex/rules/ (path-scoped, auto-load), ~/.codex/guides/ (on-demand), skills, plugins, hooks, and config.toml. Use when adding, editing, or wiring global guidance, rules, guides, skills, plugins, or hooks.
---

# Codex Config Maintainer

Procedural skill for changes to `$CODEX_HOME` (~/.codex). Policy gates: `~/.codex/guides/meta/meta-governance.md`, `~/.codex/guides/meta/codex-layout.md`.

CRITICAL layer distinction: `rules/*.md` WITHOUT `paths:` frontmatter are eager-loaded at session start. Only path-scoped rules belong in `rules/`; everything on-demand belongs in `guides/` (read via AGENTS.md router, never preloaded).

## Before any edit

1. Read `~/.codex/guides/meta/codex-layout.md` (structure).
2. Read `~/.codex/guides/meta/meta-governance.md` (where content belongs).
3. State intent: **add** | **edit** | **wire** | **remove**.

## Playbooks

Read `references/playbooks.md` on demand for the exact procedures: A new guide/rule · B new skill · C enable plugin · D AGENTS.md change · E hook · F remove/deprecate.

## Checklist (run before finishing)

- [ ] Single source of truth — no duplicate text in AGENTS.md and rules
- [ ] Router row exists for every new rule/skill/plugin trigger
- [ ] English in meta files; user chat language unchanged (Korean)
- [ ] `meta-governance.md` / `codex-layout.md` updated if conventions changed
- [ ] User told if Codex restart needed (skills/plugins)

## Related system skills

| Skill | Use |
|-------|-----|
| `skill-creator` | Authoring new skills |
| `skill-installer` | Install from GitHub / curated lists |
| `plugin-creator` | Scaffold plugins + marketplace entries |

## Related guides

| Guide | Use |
|-------|-----|
| `~/.codex/guides/meta/codex-layout.md` | Directory tree and layer roles |
| `~/.codex/guides/meta/meta-governance.md` | Decision tree and edit discipline |
