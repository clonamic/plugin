---
name: clonamic-finish
description: Before reporting changed work as done, check every requirement against fresh evidence gathered after the last change, keep working while anything actionable remains, then write the Korean 보고서 (outcome first, failures and unverified items first). Skip ordinary answers and progress updates.
---

# Clonamic Finish

## 1. Completion check

Re-read the request and the approved specs. For every required item (완료N, every enumerated item and quantity):

- what was delivered (file, state, output);
- fresh evidence from this run, gathered after the final mutation: the exact required test, diff, remote or installed state, or output;
- verdict: 완료, 미완, or 미검증.

- Environment: every temporary change is reverted, and anything changed outside the project matches a declared 변경N/복구N. An unreverted change is 미완 until restored.

Rules:

- Judge each item separately. "Mostly done" is 미완.
- An exit code proves only that the process exited. Evidence from before the last change is stale.
- After a context compaction, treat recalled progress as stale: re-check paths, line numbers, and item status from current files before any claim. When compacting, keep task spec, quantities, decisions, paths, unverified claims, and blockers; drop narration and raw logs first; never drop failures.
- Optional: if the `clonamic` CLI is installed, `clonamic verify <manifest.json>` checks a manifest such as `{"items":[{"id":"결과1","required":true,"complete":true,"evidence":"npm test 14/14"}]}` and exits non-zero while any required item is incomplete or lacks evidence.

## 2. Loop until done

- Any item 미완 and still actionable → fix it now, inside the approved boundary, then re-check. Do not stop or ask.
- While any item remains, never ask "이어서 할까요?", "계속할까요?", "진행할까요?". Continuing is the default.
- A needed target outside the approved boundary is not a blocker: handle it by `clonamic-spec` §6a (do it when the user explicitly instructed it or it is low risk; otherwise list it as `승인 시 진행N:`) and finish everything else.
- Write a 막힘 report only when an in-boundary item cannot be finished: three materially different failed strategies, a missing credential, or an unavailable external system. Name what is needed on the `다음 행동:` line. Never ask for a new approval mid-run.
- Only an all-완료 check permits a completion report.

## 3. 보고서

Write it once, in Korean, following [references/report.md](references/report.md) exactly. Essentials:

- First line: `결과: 완료 N/N` or `결과: 막힘 n/N` with the key number or cause.
- Failures and unverified items next, before anything else (`미검증·실패: 없음` when none).
- `결과N [완료N]` per item with verdict and fresh evidence.
- Method change inside the approved targets (`방식 변경:`), out-of-boundary work done (`범위 밖 진행:`), items awaiting approval (`승인 시 진행N:`), apply/deploy/backup, residual risk, and user-only next action only when they apply.
- Numbers over adjectives. No tool narration, request restatement, repeated conclusions, or offers to do more.
