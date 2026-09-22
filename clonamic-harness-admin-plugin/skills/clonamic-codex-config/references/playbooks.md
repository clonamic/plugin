## Playbook A — New guide or rule

```bash
# On-demand policy → guide
# ~/.codex/guides/<meta|work>/<topic>.md   (first line after title: Load when: <triggers>)
# Wire: one row in AGENTS.md → Guide router table

# Path-scoped policy → rule (MUST have paths: frontmatter, else it eager-loads every session)
# ~/.codex/rules/<topic>.md or rules/design/<topic>.md

# Verify
rg '<topic>' ~/.codex/AGENTS.md ~/.codex/guides/ ~/.codex/rules/
```

Content: English, bullet policy, no procedural scripts (those belong in skills).

## Playbook B — New skill

```bash
# Install from GitHub
cd ~/.codex/skills/.system/skill-installer/scripts
python3 install-skill-from-github.py --repo <owner>/<repo> --path <path/in/repo> --name <skill-name>

# Or copy manually to ~/.codex/skills/<name>/SKILL.md

# Wire AGENTS.md skill router (one row)
# Optional: rules/<topic>.md with Load when → points to this skill
```

Frontmatter required:

```yaml
---
name: skill-name
description: "One line: when to use (shown in skill discovery)."
---
```

If skill has `data/` or `scripts/`, verify paths after install (fix broken symlinks — config-doctor's symlink check catches these).

For authoring quality, also read `skill-creator` skill when writing from scratch.

## Playbook C — Enable plugin

```bash
codex plugin add <plugin>@claude-plugins-official   # example marketplace
# Edit ~/.codex/config.toml:
# [plugins."<plugin>@claude-plugins-official"]
# enabled = true

codex plugin list | rg '<plugin>'
```

Add AGENTS.md router row if agent must load plugin skills for a workflow.

For scaffolding new plugins, read `plugin-creator` skill.

## Playbook D — AGENTS.md change

**Allowed in AGENTS.md:** output language, precedence, always-on invariants, router tables, one-line chains, hooks reference.

**Forbidden:** multi-paragraph policy, model troubleshooting detail, design bans, git prose — those live in rules.

Template for new router row:

```markdown
| `<file-or-skill>` | <single-line load trigger> |
```

After edit, line count check: AGENTS.md should stay **under ~70 lines** unless always-on invariants grow.

## Playbook E — Hook (structural enforcement)

```bash
# 1. Write ~/.codex/hooks/<name>.py|sh (executable)
# 2. Register in ~/.codex/hooks.json PreToolUse/PostToolUse + matcher
# 3. Test:
echo '{"hook_event_name":"PreToolUse","tool_name":"..."}' | ~/.codex/hooks/<name>.py
# 4. One line in AGENTS.md § Hooks
```

## Playbook F — Remove / deprecate

1. Remove router row from AGENTS.md first (stops lazy load).
2. Delete or archive rule/skill file.
3. `config.toml`: `enabled = false` for plugins; do not leave orphan enabled entries.
4. Hooks: remove from `hooks.json` before deleting script.
