# Playbooks

`<home>` is `~/.claude` (Claude Code) or `~/.codex` (Codex); `<router>` is `CLAUDE.md` or `AGENTS.md`.

## A — New guide or rule

```bash
# On-demand policy → guide (first line after the title: "Load when: <triggers>")
#   <home>/guides/<meta|work>/<topic>.md, then one row in <router> → guide router table
# Path-scoped policy → rule (MUST have paths: frontmatter, else it loads every session)
#   <home>/rules/<topic>.md or rules/design/<topic>.md
rg '<topic>' <home>/<router> <home>/guides/ <home>/rules/   # verify wiring
```

Content: English bullet policy; no procedural scripts (those belong in skills).

## B — New skill

- Claude Code: `mkdir -p ~/.claude/skills/<name>` and write `SKILL.md`; packaged skills come from a plugin (`claude plugin install <plugin>@<marketplace>` or `/plugin`).
- Codex: copy to `~/.codex/skills/<name>/SKILL.md`, or install from GitHub with the system `skill-installer` skill.
- Both: one row in the `<router>` skill table; optionally a path-scoped rule that points to the skill.

```yaml
---
name: skill-name
description: "One line: when to use (shown in skill discovery)."
---
```

If the skill ships `scripts/` or `data/`, verify the paths after install (broken symlinks). For authoring from scratch, use the host's `skill-creator`.

## C — Enable a plugin

Claude Code:

```bash
claude plugin install <plugin>@<marketplace>   # writes enabledPlugins + extraKnownMarketplaces
claude plugin list | rg '<plugin>'             # verify the expected version
```

```json
"extraKnownMarketplaces": { "<marketplace>": { "source": { "source": "directory", "path": "/abs/dir" } } },
"enabledPlugins": { "<plugin>@<marketplace>": true }
```

Codex:

```bash
codex plugin add <plugin>@<marketplace>
codex plugin list | rg '<plugin>'
```

```toml
[plugins."<plugin>@<marketplace>"]
enabled = true
```

Add a `<router>` row only if the agent must load the plugin's skills for a workflow. Scaffold new plugins with `plugin-dev` (Claude Code) or `plugin-creator` (Codex).

## D — Router file change

Allowed: output language, precedence, always-on invariants, router tables, one-line chains, hooks reference. Forbidden: multi-paragraph policy, model troubleshooting, design bans, git prose (those live in rules or guides).

```markdown
| `<file-or-skill>` | <single-line load trigger> |
```

Keep the router lean (roughly under 70 lines for `AGENTS.md`) unless always-on invariants grow.

## E — Hook

1. Write `<home>/hooks/<name>.py|sh` and make it executable.
2. Register it: Claude Code in `settings.json` → `"hooks"` (event + matcher); Codex in `hooks.json`.
3. Test with a sample event: `echo '{"hook_event_name":"PreToolUse","tool_name":"..."}' | <home>/hooks/<name>.py`
4. One line in `<router>` § Hooks.

## F — Remove or deprecate

1. Remove the `<router>` row first (stops lazy loading).
2. Delete or archive the rule, guide, or skill.
3. Plugins: Claude Code `claude plugin uninstall <plugin>@<marketplace>` (or set its `enabledPlugins` value to `false`); Codex `enabled = false` in `config.toml`. Leave no orphan enabled entries; verify with `plugin list`.
4. Hooks: unregister before deleting the script, then re-run your hook checks.
