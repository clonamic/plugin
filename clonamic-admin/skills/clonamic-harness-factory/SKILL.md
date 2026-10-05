---
name: clonamic-harness-factory
description: "Design a project-scoped agent team: turn a domain or project description into agent definitions (.claude/agents/) and skills (.claude/skills/). Runs only on the explicit /clonamic-harness-factory command or an explicit request such as '하네스 구성/설계/점검'."
disable-model-invocation: true
user-invocable: true
---

# Clonamic Harness Factory

Runs only on the explicit slash command or an explicit request to design or audit an agent team for a project. Never for ordinary tasks.

## Policy

1. Default is the main agent plus solo subagents. Generate a team only when the domain needs two or more coordinated specialists; say why in one line.
2. Delegation depth at most 2 tiers below main (default 1); at most 10 concurrent agents. Flatten deeper designs into a supervisor with at most 2 tiers.
3. Fewest agents that cover the domain (typically 1–7). No speculative agents or skills; every skill needs a concrete trigger.
4. Write only inside the target project (`<project>/.claude/agents/`, `<project>/.claude/skills/`), never into global homes.
5. Never edit `CLAUDE.md` / `AGENTS.md` automatically. Output the suggested router row as text; global config changes go through `clonamic-host-config`.
6. Generated agents inherit the session model (no model pins) and never call external CLIs or raw LLM APIs.

## Procedure

1. **Audit.** Read `<project>/.claude/{agents,skills}` and the project router file. Branch: new build, extension (only the needed steps), or maintenance (audit, fix drift, sync agents and skills).
2. **Domain analysis.** Task types, stack, inputs and outputs, conflicts with existing assets.
3. **Architecture.** Pick the smallest pattern that fits:

   | Pattern | Use when |
   |---|---|
   | Pipeline | stages run in a fixed order, each consuming the previous output |
   | Fan-out / fan-in | independent parallel work merged by one owner |
   | Expert pool | a router picks one specialist per request |
   | Producer–reviewer | output needs an independent check before acceptance |
   | Supervisor | a lead assigns, reviews, and reassigns; specialists execute |

4. **Agents.** One file per agent: frontmatter `name`, `description` with trigger examples, minimal `tools` (list MCP tools explicitly). Body: role, inputs, outputs (file paths), done criteria, what it must not do.
5. **Skills.** Use the host's `skill-creator` for authoring. Keep `SKILL.md` under ~200 lines with details in `references/`. If the team needs an orchestrator skill, it states the phases, the data passed between agents (files under a work directory), error handling (retry once, then report), and one normal and one failure test scenario.
6. **QA design.** A reviewer compares both sides of every boundary (API response vs client types, routes vs links, state transitions), runs right after each module rather than at the end, and has write access only to its report.
7. **Validate.** Check that each trigger fires the right agent or skill, dry-run one task, and compare with and without the new skill.
8. **Report** (Korean, outcome first): generated files and paths, the pattern and why, and the one suggested router row.
