# Lean change

Read the task and every file the change touches, and trace the real flow end to end, before simplifying anything. Then stop at the first rung that holds:

1. omit work that has no current requirement (say so in one line);
2. reuse an existing project helper or pattern;
3. use the standard library;
4. use a native platform feature (CSS over JS, a DB constraint over app code);
5. use an already installed dependency; never add one for what a few lines can do;
6. write the smallest tested implementation.

Rules:

- A bug fix targets the root cause: find every caller; one guard in the shared function beats a guard in each caller.
- No unrequested abstractions: no interface with one implementation, no factory for one product, no config for a constant.
- Prefer deletion over addition, boring over clever, fewest files, shortest working diff in the right place.
- Mark a deliberate shortcut with a known ceiling in a comment (`yagni: global lock; per-account locks if throughput matters`).
- Never simplify away validation at trust boundaries, authorization, durability, data-loss-preventing error handling, security, accessibility, recovery, or anything explicitly requested.
- A non-trivial branch or parser leaves one runnable regression check. Record a deferred limit only when the limit is real today.
