---
name: clonamic-session-intent
description: Session-scoped intent and DoD maintenance. Load for explicit session-scoped requirements, a missing or conflicting intent state, unfinished-session resume, ambiguous completion evidence, or temptation to ask whether to continue while work remains. Use one host-provided state when available and a bounded conversation fallback otherwise; do not load this body on every prompt or turn. Triggers — 세션 지시, 요구사항 변경 기록, resume 상태 충돌, 완료 판정 진단, DoD ambiguity, 의도 추적 요청.
---

# clonamic-session-intent
One mechanism, two halves: a bounded current intent state and a completion-loop gate that decides whether a turn may end. Both run silently — never narrate them.

## 1. One bounded state per logical session

When a host injects state every prompt, every line is paid every turn. Keep one lean,
state-only core rather than growing a transcript or adding another session-state object.

Use the first available mode and never fabricate the other:

- **Host-state mode** — use only a trusted path or state handle supplied by the current host for
  this logical session. Accept a full host session identifier, never cwd or a guessed transcript
  path. Overwrite only that state. Never enumerate sibling sessions or assume a vendor home path.
- **Portable fallback** — if the host supplies no session-state interface, keep the same compact
  state in the current conversation context. Do not create a file, claim cross-restart persistence,
  or require a private hook. Reconstruct only from visible approved chat packets after compaction.

**Ownership:** state is written only by its logical session's orchestrator. A delegated subagent or
external CLI must never search for, read, infer, or write the parent's state. Its subtask never
replaces the parent's user-level Task or DoD. Without its own trusted host state, it reports only to
the orchestrator.

The state target is **~20 lines / ~1.5 KB**, with a 2.5 KB ceiling. It holds only the
metadata and compact current ID rows below, plus session-specific overrides and one explicit
handoff/checkpoint pointer when needed. Include only applicable rows. Replace it; never append.

```md
# Session Core
State: <pending|executing|blocked|closed>
Approval: <current approval state>
ID: <session UUID>
Time: <started> / <updated>
Token: <measured input/output/total|unavailable>

## 작업명세서 [ACTIVE|CLOSED]
- W1: <requirement>
- O1: <output>
- A1: <acceptance>
- X1: <exclusion>

## 개발명세서 [N/A|PENDING|APPROVED|CLOSED]
- D1 [W1]: <change>
- V1 [A1]: <verification>
- R1 [D1]: <outside-project recovery; omit when inapplicable>

## 보고명세서 [PENDING|FINAL]
- Status: <final-stage only|ID verdicts>
- Apply/deploy/backup: <applicable status>
- Unverified/blocker: <none|item>
- Risk/issue: <none|item>
- Next action: <none|user-only unblock>
```

The real lever is STATE-ONLY with ZERO running history. A State item tracks STATE ("streak 0/5", "cycle-4 running"), never a running log. Per-cycle evidence (what each sweep found/fixed, test counts, commit hashes) belongs in git history or an explicitly authorized project handoff/checkpoint, NOT here — the file may hold only a bare pointer ("latest: X closed, selftest N/0"). If it nears its cap, compress before adding. When a task needs a Definition of Done, put it in the State block as verifiable checkboxes (each names its check — "works well" is not a DoD item).

Use stable W/O/A/X and D/V IDs plus conditional R rows from the approved chat packets, but compress each into one state row;
the chat packets remain the authoritative detail. Use development `N/A` when the task has no
implementation stage. While executing, keep the report section to one pending line. After the final
chat report, retain the compact `closed` snapshot until the next task overwrites it. Never store
approval prose, the Manifest body, command output, per-cycle evidence, or revision history in the core. Record tokens
only from a measured runtime value; otherwise write `unavailable` rather than estimate.

## 2. Per-prompt update judgment

On each user prompt, judge once: is this a new task, approval transition, material direction change,
blocker, or final closure?
- Yes → overwrite only the affected current rows, update `Time`, then work.
- No (question, "go on", ack, small nudge, ordinary execution milestone) → leave the file untouched.

**Directive-target gate** (classify BEFORE acting; default scope = session):
- **HOW-I-WORK** — model/tool choice, verify-method, delegation, tone, ordering (no explicit artifact operation) → record in this session's core ONLY. Never write it into host/global root guidance, configuration, a rule, a guide, a skill, or a hook.
- **CHANGE-A-THING** — a concrete edit to code or host configuration that the user names → act on it (that operation only).
- **Ambiguous** → ask one line ("이번 세션만, 아니면 앞으로 항상?"); default to session; make no persistent global write.

Classify by the directive's DIRECT OBJECT (an explicit artifact operation), NOT persistence words like "always / use / avoid" — inferring globalization from a general-sounding directive is the over-application to avoid. Promote a working-method into global guidance/rule/skill ONLY on explicit say-so ("앞으로 항상", "글로벌 규칙으로", "make this standing").

## 3. Completion loop — run before ending ANY working turn

1. Read the DoD plus the request's per-item list (every enumerated item, quantity, file).
2. Judge EACH item individually: met-with-evidence or unmet. Never batch-judge — "mostly done" means unmet. Evidence rules live in skill `clonamic-completion-check`; do not re-derive them here.
3. All items met → check them off, report per `clonamic-report`. The turn may end.
4. Any item unmet and no external blocker → adjust approach and CONTINUE in this same turn. Do not stop; do not ask. Loop back to step 1 (bound: if 3 adjust cycles fail on the same item, treat it as a blocker).
5. Real external blocker only (missing credential, user-only decision, hard failure after retries) → state the blocker, what is done, what remains. Naming a blocker is the ONLY sanctioned early stop.

## 4. Hard prohibition

While any DoD item is unmet: NEVER emit "이어서 할까요?", "계속할까요?", "진행할까요?", or any continue-permission question. Continuation is the default, not a request. Asking permission to finish assigned work is a completion-loop failure, not politeness.

## 5. Host integration

- A host adapter may supply one session-bound state handle, inject the bounded state, preserve it
  during compaction, and warn above the ceiling. Those capabilities are optional and must be
  measured before claiming structural enforcement.
- Without those capabilities, use the portable conversation fallback in §1. The behavioral DoD
  and completion loop remain active; persistence and automatic reinjection do not.
- A host may preserve a closed snapshot only through an explicit memory operation. The portable package performs no implicit archive, recall, promotion, TTL sweep, or session-end database write. A completed task stays as one compact `closed` snapshot until a new task overwrites it.
- Evidence discipline: `clonamic-completion-check`. Report form: `clonamic-report`.

## 6. Hard bans (do not add)

No assumed vendor path, implicit index or DB write, locks/stamps, automatic hook installation,
legacy attribution, mtime mapping, seed inheritance, archive deletion, or GC daemon.
