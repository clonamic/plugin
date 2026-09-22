---
name: clonamic-claude-config
description: Maintain Claude Code global setup — CLAUDE.md router, ~/.claude/rules/ (path-scoped, auto-load), ~/.claude/guides/ (on-demand), skills, plugins, hooks, and settings.json. Use when adding, editing, or wiring global guidance, rules, guides, skills, plugins, or hooks.
---

# Claude Code Config Maintainer

Procedural skill for changes to `~/.claude/`. Policy gates: `~/.claude/guides/meta/meta-governance.md`, `~/.claude/guides/meta/claude-layout.md`.

CRITICAL layer distinction: `rules/*.md` WITHOUT `paths:` frontmatter are eager-loaded by the harness at every session start. Only path-scoped rules belong in `rules/`; everything on-demand belongs in `guides/` (read via CLAUDE.md router, never preloaded).

## Before any edit

1. Read `~/.claude/guides/meta/claude-layout.md` (structure).
2. Read `~/.claude/guides/meta/meta-governance.md` (where content belongs).
3. State intent: **add** | **edit** | **wire** | **remove**.

## Playbooks

Read `references/playbooks.md` on demand for the exact procedures: A new guide/rule · B new skill · C enable plugin · D CLAUDE.md change · E hook · F remove/deprecate.

## Checklist (run before finishing)

- [ ] Single source of truth — no duplicate text in CLAUDE.md and rules
- [ ] Router row exists for every new rule/skill/plugin trigger
- [ ] English in meta files; user chat language unchanged (Korean)
- [ ] `meta-governance.md` / `claude-layout.md` updated if conventions changed
- [ ] Core edits applied identically to `~/.agents/AGENTS.md` AND `~/.codex/AGENTS.md` (diff the two Core sections; the owner's config-doctor automates this and is not shipped)
- [ ] After any intentional policy change: re-run your own contract tests in the SAME session and repin stale assertions immediately (contracts follow config, never the reverse). The owner's `hooks-selftest.sh` is not shipped — it is hardwired to their layout; write your own checks as you add policy.
- [ ] User told if Claude Code restart needed (skills/plugins)

## Related system skills

| Skill | Use |
|-------|-----|
| `skill-creator` | Authoring new skills |
| `plugin-dev` | Scaffold plugins, agents, commands, hooks, marketplace entries |

Install existing skills/plugins via `/plugin` or `claude plugin install <plugin>@<marketplace>`.

## Related guides

| Guide | Use |
|-------|-----|
| `~/.claude/guides/meta/claude-layout.md` | Directory tree and layer roles |
| `~/.claude/guides/meta/meta-governance.md` | Decision tree and edit discipline |
