---
name: clonamic-anti-overengineering
description: "Portable over-engineering guard for writing, refactoring, fixing, reviewing, and dependency choices. Also use on explicit 오버엔지니어링, YAGNI, 최소로, 단순하게 requests."
---

# clonamic-anti-overengineering — The Lean Ladder

The best code is the code never written. Stop at the first rung that holds:

1. **Does this need to exist at all?** Speculative need = skip it, say so in one line.
2. **Already in this codebase?** Reuse the existing helper/util/pattern; look before you write.
3. **Stdlib does it?** Use it.
4. **Native platform feature covers it?** CSS over JS, DB constraint over app code, `<input type="date">` over a picker lib.
5. **Already-installed dependency solves it?** Never add a new one for what a few lines can do.
6. **Can it be one line?** One line.
7. **Only then:** the minimum code that works.

The ladder runs AFTER understanding: read the task and every file the change touches, trace the real flow end to end, then climb. Laziness never applies to comprehension.

## Rules

- Bug fix = root cause, not symptom: grep all callers; one guard in the shared function beats a guard in every caller.
- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a constant.
- Deletion over addition; boring over clever; fewest files; shortest working diff — in the RIGHT place.
- Deliberate shortcut with a known ceiling → mark it: `// yagni: global lock — per-account locks if throughput matters`.
- Non-trivial logic leaves ONE runnable check (smallest assert/demo/test that fails if it breaks). Trivial one-liners need none.
- Never simplify away: trust-boundary validation, data-loss-preventing error handling, security, accessibility, anything explicitly requested.

## Output

Code first, then ≤3 short lines: what was skipped, when to add it. If the explanation outgrows the code, delete the explanation.
