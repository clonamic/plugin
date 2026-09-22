---
name: clonamic-flow-map
description: >
  Draw the RUNTIME execution flow of existing code — branches, fan-out, joins, loops, and
  post-response work — as ASCII plus a branch table whose conditions are quoted from source.
  Use when asked to show how a request or turn actually travels through a codebase:
  "흐름 시각화", "분기 다이어그램", "어떻게 동작하는지", "한눈에 보이게", "경로별로 그려줘",
  flow diagram, execution walkthrough, graph routing explanation.
  Do not use for: a single function's bug, a file/directory tree, static import or dependency
  structure, designing a system that does not exist yet, or hand-drawn/sketch art.
---

# clonamic-flow-map

Read the code, not the docs, and answer one question: **where does a request go, and what decides.**

## Format is decided by destination, never guessed

| Destination | Format |
|---|---|
| Chat (the default) | **ASCII only.** No mermaid fence. |
| A file the user named (`README`, `docs/*.md`) | Mermaid — the renderer is there |
| A published HTML artifact | Mermaid |

Terminals render mermaid as raw source, every time. "Emit both in case it breaks" prints the
unreadable copy first and doubles the length. Ask which file, or assume chat.

## Procedure

1. **Entry.** Workflow graph → `StateGraph`, `add_conditional_edges`, `compile()`. Server →
   route decorators, job/webhook handlers. CLI → `__main__`, subcommands. Frontend → router,
   page mount, polling client. Batch → cron, worker, queue consumer.
2. **Edges.** List every unconditional edge, conditional edge, fan-out, join, loop, subflow, and
   after-response background step. Naming convention gives them away: `pick`, `route`, `after_*`,
   `_after_prepare`. Ambiguous? Re-read that function — never infer the condition.
3. **Branch table** — the deliverable, and it is never optional at any size:

   | Point | Condition (as written in code) | Next | Note |

4. **Draw**, at the size the code earns (below).
5. **Verify**: every conditional edge appears in the table; loops state their exit condition;
   parallel regions say whether siblings can see each other's writes; work that happens after the
   user's response is drawn outside the main box.

## Size follows branch count, not enthusiasm

- **≤5 branch points** → three sections: ASCII flow, branch table, path list. Stop there.
- **more, or 2+ parallel regions / subflows** → add the layer table, sub-loops, background work,
  state-field map, and a closing one-page summary.
- Never emit a section with nothing in it. A three-file script does not get a ten-section wall.

## Drawing

```
A → B        sequence          ├ └   branch
A ‖ B        same step         ↺     loop
▷            subflow, expanded below            END
```

Boxes: readable alignment only, no padding to force column widths. One turn goes in one box;
background work goes outside it. Scenario paths are one-line chains: `A → B → C`.
Mermaid, when the destination earns it: English node ids, ≤15 nodes per diagram, split a shared
`END` into `END1`/`END2` so the arrows stay legible.

## Do not

- Draw from the README. It is a cross-check; the code is the answer, and a difference is worth one
  line of its own.
- Dump the file tree. Only the paths the flow actually touches.
- Hide a condition inside a diagram. If it is a branch, it is in the table.

## References — read only when they apply

- `references/graph-frameworks.md` — conditional-edge enumeration, fan-out/join semantics, and the
  sibling-write trap. Load for graph/workflow frameworks only.
- `references/example.md` — one worked example, for output density.
