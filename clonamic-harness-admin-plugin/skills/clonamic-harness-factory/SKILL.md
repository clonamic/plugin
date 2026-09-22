---
name: clonamic-harness-factory
description: "Team-architecture factory (clx fork of revfactory/harness v1.2.0) + vendored 100-harness library installer. Turn a domain/project description into agent definitions (.claude/agents/) and skills (.claude/skills/) using six team patterns, or install a ready-made team from ~/.agents/harness-library ('/harness list·use', '하네스 설치', '하네스 100', '하네스 라이브러리'). Use ONLY on explicit request — /harness, '하네스 구성/구축/설계/점검/감사', or an explicit ask to generate an agent team for a project. Never auto-load for ordinary tasks."
metadata:
  upstream: https://github.com/revfactory/harness (v1.2.0, Apache-2.0)
---

# clonamic-harness-factory — Agent Team & Skill Architect

Fork of revfactory/harness customized for this environment. Full upstream workflow (Phases 0–7, matrices, checklists): `references/upstream-workflow.md`. Deep references: `references/agent-design-patterns.md`, `orchestrator-template.md`, `team-examples.md`, `qa-agent-guide.md`, `skill-writing-guide.md`, `skill-testing-guide.md`.

## Local policy overrides (these WIN over upstream text)

1. **Orchestration caps from core AGENTS.md rule 1 apply to every generated design**: delegation depth ≤ 2 tiers below main (default 1 — generated agents work solo), concurrent agents ≤ 10. Reject or flatten upstream patterns that exceed this (e.g. deep Hierarchical Delegation → flatten to Supervisor with ≤2 tiers).
2. **Agent teams are NOT the default execution mode.** Default is main + solo subagents. Generate a team only when the domain genuinely needs ≥2 coordinated specialists, and say why in one line.
3. **Never edit CLAUDE.md / AGENTS.md automatically.** Upstream Phase 5 registers a pointer in CLAUDE.md — do not. Instead, output the suggested router row as text for the user to apply (config edits route through `clonamic-claude-config`).
4. **Lean bias applies** (core rule 3): fewest agents that cover the domain (1–7 typical, as in the design rule); no speculative agents/skills "for later"; every generated skill needs a concrete trigger.
5. Generated assets are project-scoped (`<project>/.claude/agents/`, `<project>/.claude/skills/`) — never write into `~/.claude/` globals.
6. Generated agents inherit the host session model (no model pins in frontmatter) and never invoke external CLIs (`grok`, `codex`, raw curl-to-LLM) — external delegation stays main-only per core rule 2.

## Workflow (summary — details in references/upstream-workflow.md)

- Phase 0 audit existing `<project>/.claude/{agents,skills}` + CLAUDE.md → new build / extension / maintenance branch.
- Phase 1 domain analysis → task types, stack, existing-asset conflicts.
- Phase 2 architecture: pick from Pipeline · Fan-out/Fan-in · Expert Pool · Producer-Reviewer · Supervisor · (flattened) Hierarchical — apply override 1–2.
- Phase 3 agent definitions (frontmatter: name, description with trigger examples, tools minimal — MCP tools must be listed explicitly in `tools`).
- Phase 4 skills with progressive disclosure (SKILL.md ≤200 lines, detail in references/).
- Phase 5 integration: data passing, error handling; router row as TEXT ONLY (override 3).
- Phase 6 validation: trigger tests, dry-run, with/without-skill comparison.
- Report outcome-first: what was generated, where, and the one suggested router row.

## Library mode (vendored harness-100)

`~/.agents/harness-library/` holds all 100 upstream ko harnesses (Apache-2.0, pinned commit in its README; PRISTINE — never edit library files). `list [keyword]` → grep the catalog table in `ko/README.md`, show matches + overlap badges from `INDEX.md`. `use <id>` → follow the install contract in `INDEX.md` verbatim: copy into the CURRENT project `.claude/` non-destructively (skip+report conflicts), rename `skills/*/skill.md` → `SKILL.md`, prepend the core-binding header to installed CLAUDE.md, warn on overlap badge. Local overrides 1–6 above apply to the installed team at runtime; do not rewrite the harness bodies.
