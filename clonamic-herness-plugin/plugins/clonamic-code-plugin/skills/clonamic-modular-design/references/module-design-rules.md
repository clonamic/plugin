# Module Design Rules — Detailed Guide

Core premise: **modularization has a cost** (indirection, wiring code, file count, cognitive
load). Split or commonize only when evidence outweighs that cost, and log the evidence in
the design decision log.

These gates decide WHETHER a boundary exists. How each surviving boundary is shaped
(public surface, wiring, extension, removal) is `library-module-rules.md` — Phase 4.

## 1. Module definition and the floor

A module is a **cohesive responsibility unit worth testing independently**.

**Module floor (important)**: something that fits in one function is a function, not a module.
Hash computation, date formatting, env-var reading, JSON parsing — keep these as private
functions of their owning module or use the stdlib directly; never promote them to modules.

```
Good modules:
- ArticleDeduplicator: duplicate detection + hash management for collected articles
  (cohesive responsibility, independent test value)
- OrderExecutor: order build → validate → submit → handle result (one reason to change)

NOT modules (keep as functions):
- HashCalculator, DateFormatter, EnvLoader, JsonParser
```

## 2. Split gate (split ONLY when it passes)

A split candidate must satisfy ALL of:

```
[required] 2+ distinct reasons to change (SRP violation)
[AND at least one]
  - 2+ REAL reuse sites (no speculation — only call sites that exist in the code today)
  - independent test value (a boundary that cannot be verified without mocking otherwise)
  - clearly different change cadence or owner
```

Fails the gate → **keep it together**. Split later when evidence appears — splitting is easy
to do later, but a wrong boundary forces rewiring everything.

Secondary signals (advisory, only after the gate passes): expected code >200 lines,
description needs "and", calls 2+ external APIs.

## 3. Merge signals (ANY one → merge)

- The module only passes values through (pass-through)
- Two modules are always called together and never used independently
- IN/OUT are effectively identical
- No split justification exists in the decision log

## 4. C0 (common module) admission review

Nothing enters C0 by category ("it's DB", "it's HTTP"). **Precondition (Q0): the module
floor.** A candidate that fits in one function (HashUtil, DateUtil, JsonUtil, EnvUtil …)
is not reviewable — it stays a function regardless of how many call sites it has. Only
floor-passing candidates take the 3-question review:

```
Q1. Rule of three: is this the 3rd REAL use site?
    → Up to 2 sites, keep it feature-local. Duplication at this stage is allowed and
      cheaper than premature commonization.
Q2. Interface stability: low change frequency, stable signature?
    → Commonizing something that churns makes its blast radius the whole codebase.
Q3. Domain independence: pure infrastructure/utility with zero business rules?

All three YES → admit to C0. Any NO → stays feature-local.
```

**C0 deny-list** (never admitted regardless of review):
- Business logic (domain rules always belong to a feature)
- Helpers used by a single feature
- "Might need it later" speculative utilities (only real use sites count)

**DI (dependency injection)**: introduce a container/injection pattern only when C0 has
3+ modules — counting only floor-passing admitted modules (utils kept as functions never
inflate this count); before that, explicit parameter passing is enough. C0 lives in `src/common/`,
physically separated from features; no circular deps among C0 modules.

## 5. IN/OUT rules

### 5.1 OUT
- Exactly **one OUT** per module.
- A single result object with multiple fields (dataclass/DTO) counts as one OUT.
- Needing two unrelated results is the moment to re-run the split gate.

### 5.2 IN
- One main IN (previous pipeline module's OUT) + 0..N aux INs (C0, config, external).
- Every IN lists: parameter name, concrete type, source, one-line description.

### 5.3 Spec format
```
IN (main):
  - raw_articles: list[RawArticle]   ← F1.2.crawl() return — uncleaned article list
IN (aux):
  - db_session: AsyncSession         ← C0.2.get_session() — async DB session
OUT:
  - DeduplicationResult
    fields:
      - is_new: bool                 # new-article flag
      - article_hash: str            # SHA-256
      - duplicate_id: Optional[int]  # duplicate article id if any
```

### 5.4 Failure semantics (every module, mandatory)

Every OUT defines its failure form — an unspecified crash path is a spec bug:

```
OUT: CrawlResult          # success form (fields as usual)
FAIL: CrawlError          # Result-style {ok: false, reason, retryable: bool}
                          #  OR a declared exception type — pick ONE policy per project
PIPELINE POLICY: retry(2) → skip-and-log   # what the pipeline does when this stage fails
```

Pipeline failure policies (choose per stage): `halt` (critical), `retry(n)` (transient),
`skip-and-log` (per-item work). The whole-pipeline default is stated once in DESIGN.md.
A pure total function may declare `FAIL: none (total)` — its pipeline policy line is
still required.

### 5.5 Parallel marks and resource math

When the user states quantified resources (RAM, cores, "최대 병렬"), the design must show
the saturation math, not gesture at it:

```
F1.2 Crawler   parallel-safe: yes   workers = min(cores, RAM ÷ 250MB/worker)
F1.4 Persister parallel-safe: no    (single DB session — serialize)
```

Mark every module `parallel-safe: yes/no`; independent pipeline stages that are both
parallel-safe may fan out inside their feature orchestrator (the MAIN pipeline stays a
straight line — parallelism lives inside stages, not between features).

## 6. Hierarchy and naming

```
Level 0: project orchestration
 └─ Level 1 (Feature): F1, F2, ...      ← small projects stop here
      └─ Level 2 (Module): F1.1, F1.2   ← medium+ AND split-gate passes only
Side: C0.{n} (admission-review passes only)
```

Naming: `C0.{n}`, `F{feature}.{module}`, special features `F{letter}.{n}` (e.g. FW.1
WebSocketManager). Feature grouping: same data domain / changes together / same business
purpose. Consider splitting a feature past 15 modules.

## 7. Main pipeline rules

- Whole project: `[start] → F1 → F2 → ... → FN → [end]` — one branch-free straight line.
- Inside each feature likewise: `F1.1 → F1.2 → ... → F1.N (orchestrator)`.
- Conditionals live inside modules; the OUT type stays identical on every path.
- No direct feature-to-feature calls — the parent orchestrator passes OUT→IN, or use events.
- Allowed deps: Feature→C0, parent→child. Forbidden: Feature↔Feature direct, C0→Feature, cycles.

## 8. Design verification checklist

- [ ] Every split / commonization / merge has a logged reason
- [ ] No module-floor violations (no function-sized modules)
- [ ] Every C0 module passed the 3-question review (3+ sites, stable, domain-independent)
- [ ] No module matches a merge signal
- [ ] Every OUT exactly one, fields specified
- [ ] Every IN has type + source
- [ ] Pipeline straight (whole + per-feature)
- [ ] No circular deps, no direct feature-to-feature deps
- [ ] Module count within the Scale Gate bound
