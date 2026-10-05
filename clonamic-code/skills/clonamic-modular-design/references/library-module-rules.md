# Library Module Rules — Boundary Discipline

Premise: the analysis gates (`module-design-rules.md`) decide WHETHER a module exists.
These rules decide HOW its boundary is shaped so every surviving module behaves like a
small library — adding, changing, removing, and reusing it stays cheap. Every rule here
is itself evidence-gated: structure without a present driver is banned.

## 1. Public surface (exactly one)

- Each module exports **one entry point** (function or class) plus the IN/OUT types that
  entry needs. Nothing else leaves the module.
- Mechanics: Python — re-export in the package `__init__.py`, internals `_`-prefixed or
  under `_internal/`; TypeScript — `index.ts` re-exports; Rust — `pub` only on the surface.
- Consumers import from the module root only, never from internal files
  (`from f1_crawler import crawl`, not `from f1_crawler.session_pool import ...`).
- Variant packages (extension gate passed): each variant module keeps one entry; the
  package root re-exports the contract type + the variants so the composition root's
  selection map imports from one place.
- The public surface IS the contract: what DESIGN.md specs is exactly what the module
  exports — no undocumented exports, no spec-less parameters.
- Wanting two unrelated entry points is the signal to re-run the split gate.

## 2. Composition root (single wiring point)

- Exactly one place — `main.py` / the top orchestrator — constructs modules and passes
  each OUT to the next IN. Feature-internal orchestrators do the same for their submodules.
- Modules never instantiate or import sibling modules; collaborators arrive as aux IN.
- **Type-only exception**: importing an upstream module's public OUT types (the types your
  main IN consumes) from that module's root IS the pipeline chain and is allowed —
  invocation wiring is what stays at the root.
- Effect: adding, removing, or swapping a module edits **one file plus the module folder**.

## 3. Extension gate (registry / plugin pattern)

Adding a variant should cost "new module + one registration line" — but ONLY once
variance is real:

```
[required] 2+ REAL variants of the same contract exist in today's requirements
→ then: one shared contract type + variant modules + a selection map at the composition root
0–1 variants → NO interface, NO registry — direct call (YAGNI)
```

- The selection map is data (dict / match at the root), never if/elif chains inside modules.
  It may select one variant or fan out to several active variants — either way the active
  set lives at the root as data.
- "We might add X later" fails the gate — log it as `[LOCAL]`; extracting the contract
  later is one mechanical refactor precisely because of rules 1–2. This holds even when
  the contract already exists: a speculative extra variant of an admitted contract is
  still refused — the Extension Points section lists today's variants only.
- Gate passed → DESIGN.md gains an **Extension Points** section: contract, current
  variants, and a one-sentence "to add a variant: ...".

## 4. Hidden-input ban (portability)

A module may consume ONLY what its IN spec declares:

- No module-level env reads, global singletons, or implicit config/file reads inside a
  feature module. Config values arrive as aux IN, loaded once at the composition root
  (or via a C0 config module).
- Side effects (DB, network, fs) are visible in the spec — as the OUT/failure semantics
  or as a declared aux collaborator.
- The composition root and a C0 config loader are the only environment-touching places.
- Effect: the module runs wherever its IN types exist — testable without monkey-patching,
  portable to another project as-is.

## 5. Reuse rules

- Reuse direction: Feature → C0 only. Sideways reuse (feature importing feature) means
  either lift the shared part through the C0 admission review or duplicate it (allowed
  under the rule of three).
- **C0 standalone test**: every C0 module must be usable in a different project with only
  stdlib + its declared external deps — zero imports from features, zero domain terms in
  its contract. Fails → it is feature logic; keep it local.
- Measure reusability at the contract: if reuse elsewhere would force field renames or
  stripping domain vocabulary, it is not C0 material yet.

## 6. Contract stability (modify)

- Additive changes (new optional field, new default) are preferred; breaking changes
  (rename / remove / retype) are design changes → same-turn DESIGN.md update +
  decision-log entry + re-run the OUT→IN type-chain check over all consumers.
- Internals change freely — that freedom is the payoff of a single public surface.

## 7. Delete test (remove)

Removal of any module must reduce to: **delete the module folder + remove its wiring
lines at the composition root** (+ its registry entry if one exists). If deletion would
orphan shared state, break another module's import, or require edits inside a sibling,
the boundary is wrong — fix the design now, not at deletion time.

Each DESIGN.md feature card carries a one-line **removal note**: what disappears from
the pipeline and which consumers of its OUT must react.

## 8. What this is NOT

- Not permission to sprinkle interfaces / registries / DI — every structure passes its gate.
- Not microservice or packaging advice — modules are folders in one repo until deployment
  reality demands otherwise.
- Not a wrapper factory — wrapping one stdlib call in a module still violates the module floor.
