---
name: clonamic-bracket-payload
description: The user's actionable-payload convention — content wrapped in ["..."] is the reference / quote / work-instruction to ACT ON; unwrapped text is casual framing/context, not a literal command (a clear unwrapped request still counts). Load when a message contains ["..."] wrappers, when wrapped-vs-unwrapped changes what to act on, or when the user asks to define/apply/troubleshoot the bracket convention. Composes with clonamic-session-intent §2 (directive-target gate), not a replacement.
---

# clonamic-bracket-payload
A conservative **interpretation heuristic**, not a strict parser. It sharpens intent when the user uses it; it never blocks or ignores a clear instruction when they don't. Runs silently.

## 1. The rule
- **Wrapped `["…"]`** = the operative payload the user wants acted on: a work-instruction, a quotation, or reference text/image. High-confidence "use this / do this."
- **Unwrapped text** = casual framing, context, thinking-aloud. Read it to understand — do NOT treat it as a literal command to execute a new task or change.
- The signature is prose-level `["` … `"]` (a bracket with a double-quote hugging it). Whitespace and smart-quote variants (`[ "…"]`, `［“…”］`) count when intent is obvious.

## 2. Inside the wrapper is not all instruction
Split wrapped content into **directive** (imperative / requested action) vs **reference-data** (quoted material to use). An image inside a wrapper is reference by default; what to do with it comes from the directive in the same wrapper.

## 3. Nesting
Read outside-in: the outer wrapper is the container/task, an inner `["…"]` is **reference-data subordinate to it** — never promoted to a separate top-level command unless the outer directive explicitly says to run it. Multiple top-level wrappers combine, in order, into one payload set.

## 4. Edge cases (robust, never fail-closed)
- **Unbalanced / unclosed brackets** → do NOT reject or block; fall back to reading the message as plain natural language. The convention is a hint, not a hard gate.
- **Markdown `[link](url)`** → not the protocol (no quote hugging the bracket). Ignore.
- **Code / JSON `["a","b"]`** → inside a code fence or obvious code/JSON context this is a literal array, NOT a wrapper. The convention applies at PROSE level only; surrounding context wins.
- **No wrapper at all** → read normally; a clear instruction is still honored (see §6). "No wrapper" ≠ "ignore everything."
- **Whole message wrapped** → the whole thing is payload; act on it. If it is only reference-data with no directive, do not invent a task.

## 5. Composition with the directive-target gate (orthogonal)
Two independent axes:
- **This skill** decides *what is the operative payload* (actionable vs casual).
- **`clonamic-session-intent` §2** decides *where a found directive applies* (HOW-I-WORK / session vs CHANGE-A-THING / project).
Every wrapped **directive** still passes through §2 — wrapping does NOT make something automatically project/global; classify it by its direct object as usual. Reference-data does not go through the gate.

## 6. Failure guard — do not over-suppress (the important one)
The biggest risk is ignoring a real instruction the user simply forgot to wrap — users are informal and WILL forget. So:
- **A clear unwrapped request still counts.** The wrapper raises confidence; it never suppresses clarity. Unwrapped + unmistakable command/request → still do it.
- Unwrapped + genuinely ambiguous (aside vs command) + **irreversible/outward** action → one-line confirm before acting, or treat as context.
- Wrapped → high-confidence, act.
- Never turn a false-positive wrapper (code array, pasted markdown) into a task; when a real change hinges on it, confirm in one line.

Guard in one line: **when ambiguous, no silent action + one-line confirmation — never drop the user's intent.**
