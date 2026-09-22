# AI Design Behavior Guide

Concrete behavior for an AI agent running this skill.

## 1. Conversation flow

### 1.1 Project intake
On a design request, do not write code — establish first: project name / one-liner, core
features, deployment target, stack preference, scale feel (S/M/L).
**Never re-ask what the user already provided.**

### 1.2 Tech-stack agreement — the only approval gate
Propose as a table (area / tech / why) and get one approval.
Everything after (hierarchy, specs, DESIGN.md) proceeds without approval and reports results.
Under an active goal/loop, replace even this gate with "propose + state chosen default + proceed".
Skipping the approval never hides refusals: every gate refusal (HTML/format, C0 denial,
DI, speculative variant) is stated in the same-turn report, not just the decision log.

### 1.3 Announce the scale verdict
State the Scale Gate verdict in one line before decomposing.
e.g. `[Scale: Small — decompose to Feature level only, no C0 to start]`

### 1.4 Decompose + decision log
Apply split gate / C0 review / merge signals while building the hierarchy tree, then the
Phase-4 library gates (extension gate, hidden-input sweep), and **accumulate every decision
as a log** (this becomes DESIGN.md's "Design Decision Log"):

```
[SPLIT  ] F1.3 CrawlVerifier out of F1.2 — 2 change reasons (crawl policy / validation rules) + independent test value
[KEEP   ] hash computation — stays a function (below module floor)
[LOCAL  ] http_fetch — stays in F1 (1 use site, fails rule of three)
[C0     ] C0.1 DatabaseGateway — 3 use sites (F1.5, F2.2, F3.4) + stable signature + domain-independent
[MERGE  ] F2.3+F2.4 — always called together, no independent use site
[VARIANT] ExporterContract {csv, parquet} — 2 real variants in requirements → registry at root
[LOCAL  ] "pdf export later" — 0 real variants today, fails extension gate
```

### 1.5 Detailed IN/OUT specs
This is specification, not implementation — write no code.
Types: Python projects use `list[Article]`, `Optional[float]`; TypeScript projects use
`Array<Article>`, `UserProfile | null`. OUT always to field level; IN always with source:

```
← C0.1.get_secret("DB_URL")     # common-module method
← F1.2.crawl() return            # previous module's OUT
← config.yaml["crawl"]["timeout"]   # loaded at composition root, passed as aux IN
← user_input                     # user input / API request
```

Each module card also lists its library boundary:

```
PUBLIC: crawl(), CrawlResult, CrawlError    # the only exports — internals private
REMOVE: delete f1_crawler/ + unwire in main.py; F2 loses its main IN (falls back: none)
```

### 1.6 Refactor mode (existing code)

Before any target design: inventory reality — `rg` the real call sites, file sizes,
`git log --stat` hot spots. The current-state map goes in DESIGN.md ("As-Is" section).
Then design the target with the same gates, and produce a **migration order**:
strangler sequence (which boundary moves first), what stays temporarily duplicated,
and a cutover check per step. Never design a target that ignores where the code is today.

### 1.7 Worked micro-example (gates in action — small currency-converter CLI)

```
[Scale] Small (~4 files) → Feature level only, no C0
[KEEP ] env reading, JSON parsing — functions/stdlib (below module floor)
[LOCAL] http fetch — 1 use site (fails rule of three)
[MERGE] fetcher+parser — always called together
[SPLIT] F1 RateProvider / F2 Converter — different change reasons + independent test value
→ 2 modules, 0 C0, no DI. Pipeline: [CLI] → F1 → F2 → [print]
   (legacy rules would have produced 6 modules + DI container)
```

## 2. DESIGN.md generation rules

The deliverable is a **single `DESIGN.md` at the project root**. Never generate HTML.

### 2.1 Required sections (in order)
1. **Header**: project, version, one-liner, date, module count, scale verdict
2. **Tech-stack table**: area / tech / why
3. **Folder tree**: with module-ID comments; mark each composition root (`main.py  # root`)
4. **Main pipeline**: straight flow + per-stage OUT→IN chain table; optional mermaid `graph LR`
5. **C0 modules** (if any): full specs + admission-review results + standalone-test note
6. **Extension points** (only if the extension gate passed): contract type, current
   variants, selection map location, one-sentence "to add a variant: ..."
7. **Feature modules**: per-feature section — internal pipeline, module IN/OUT specs,
   PUBLIC surface, internal logic, constraints, removal note
8. **Dependency table**: module × C0/events used
9. **Implementation checklist**: build order (checkboxes) — include one contract-test stub
   per module boundary (the smallest test that fails if the IN/OUT contract breaks)
10. **Design Decision Log**: the full log accumulated in 1.4 (including [VARIANT] entries)
11. **Migration plan** (refactor mode only): As-Is map, strangler order, cutover checks

Empty-section policy: **C0 is always present** — when empty, write "none" plus the
per-candidate denial reasons (that record is the design's value). **Extension points**
and **Migration plan** are omitted entirely when not applicable.

### 2.2 Never omit
- Per-stage OUT→IN chain (without it, data flow is unreadable)
- OUT field structures (never just "Result")
- IN source modules (unknown source = unimplementable)
- The decision log (a design without reasons cannot be reviewed)

### 2.3 Size management
- Keep a **single `DESIGN.md`** — no multi-file split, no numerical line cap
- Put an internal TOC at the top; use dense deduplicated tables; merge section-by-section
  drafts into that one file (never `docs/design/F{n}.md` shards)
- Large projects: write C0 → F1 → F2 ... sequentially, then merge into one DESIGN.md
- Progress marker: `[now: F2 done / next: F3 / total 3/7]`

### 2.4 Consistency
- Reuse exact type/variable/module names across phases
- Verify each OUT type matches the next module's IN type
- Verify every C0 reference points to an existing C0 module

## 3. Quality self-verification (after DESIGN.md)

Run SKILL.md's **"Mandatory verification before declaring the design done"** — that list
is the single canonical checklist (no separate list here). Conditional items (parallel
marks, refactor migration) count only when applicable. Append one line at the end of
DESIGN.md: `[self-check: N/N passed]` where N = the number of applicable items.
