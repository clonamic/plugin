# FDE output contract (fde.out.v1)

Every FDE agent writes exactly **one JSON file** per dispatch, at the path the dispatch names. The planner validates it, `fde sync` folds it into the project database, and the dashboard shows it. A file that breaks this contract is rejected and the agent is re-dispatched once with the error.

## 1. Envelope (all modes)

```json
{
  "schema": "fde.out.v1",
  "agent": "fde-<name>",            // your own name, exactly
  "mode": "<mode from the dispatch>",
  "run": "<run id from the dispatch>",
  "covers_until": "U047",           // last utterance id you actually read (freshness check)
  "summary_ko": "2~3줄 한국어 요약",
  "...sections for your mode...": [],
  "extra": {}                       // anything specific to your role; kept and shown, never parsed
}
```

Hard rules
- Human-readable values are **Korean**. Keys, ids, enum values stay as written here.
- Evidence is utterance ids (`U012`). A `quote` must be a **verbatim substring** of that utterance; a deterministic checker compares it and downgrades the item to `추측` if it is not found. Use `…` between two verbatim pieces if you skip words.
- No evidence → say so: `"evidence": []`. Never invent an id or a quote.
- Write only the output file and the extra files the dispatch lists. Do not spawn subagents. Do not edit code unless your mode is `implement`, `clean`, `load`, `unblock`, `decide`, `plan` or `design` (prompt engineer only).
- Reply to the director with at most 3 Korean lines plus the output path. Never paste the JSON back.

## 2. Item shapes
> 예시는 형식만 보여 준다. 예시의 업종·명사·기능을 가져오지 않는다. 기능·데이터·수치 제안은 인물 발화(U)·받은 자료(DA)·브리프에 근거하고, 근거 없는 업종 지식은 '추측'으로 표시하고, 설계를 바꾸면 확인 질문으로 올린다.

**candidate** — something the organisation might ask, assume, propose, decide or watch.
```json
{"id": "C1",
 "kind": "question | proposal | assumption | decision | risk",
 "area": "문제 | 현재방식 | 사용맥락 | 여정 | 데이터 | 성공기준 | 예외 | 말투 | 우선순위 | 이해관계자",
 "gap": "무엇이 비어 있거나 충돌하는지 한 문장",
 "evidence": ["U012"], "quote": "U012의 원문 일부",
 "already_answered_check": "대화 전체에서 이미 답이 있었는지 확인한 결과",
 "question_draft": "인물에게 물을 질문 초안 (question / proposal)",
 "decision_at_stake": "답에 따라 바뀌는 설계 결정. 비어 있으면 question/proposal은 자동 탈락",
 "if_wrong": "이 빈틈을 틀리게 메웠을 때 생기는 일",
 "self_confidence": "확실 | 가능성 높음 | 추측",
 "impact_guess": "높음 | 중간 | 낮음",
 "grade": "D1 | D2 | D3", "options": ["..."], "recommended": "...", "blocking": ["core_freeze"]}
```
`grade/options/recommended/blocking` only for `kind: decision` (a choice for **the user**, not the persona). `proposal` = a feature to suggest to the persona and watch the reaction. `assumption` = proceed without asking. `risk` = something build/QA must watch.

**observation** `{"id": "O1", "text": "...", "evidence": ["U.."], "quote": "...", "confidence": "확실|가능성 높음|추측"}`

**requirement** (registrar keeps the full list; send the whole list every time)
```json
{"id": "R-001", "type": "기능 | 비기능 | 데이터 | 제약 | 선호 | 성공기준 | 제안된 해결책",
 "statement": "...", "status": "명시 | 추론 | 가정", "evidence": ["U.."], "quote": "...",
 "confidence": "확실 | 가능성 높음 | 추측", "priority": "must | should | could | 미정",
 "feasibility": "가능 | 주의 | 불가 | ", "feasibility_note": "...", "conflict": ["U044"], "confirmed": false}
```
`status` (did the persona say it) and `confidence` (did we understand it) are different axes. `confirmed: true` only after the persona confirmed it (readback or direct answer).

**decision** `{"title": "...", "grade": "D1|D2|D3", "context": "...", "options": ["..."], "recommended": "...", "blocking": ["core_freeze" | "full_freeze" | "deploy"], "questions": ["Q-007"]}`

`questions` (optional): the open question cards this decision settles. A decision taken by its recommendation without asking (D3, or D2 when the user turned autonomy on) closes them as `assumed`, so they do not come back in "지금 물어볼 질문".

Only raise a decision the planner can carry out. Starting part of the build before the core freeze ("배선 코드만 먼저 시작" and the like) and a promise about when the freeze will be judged again ("1라운드 뒤 다시 판단") cannot be carried out: answered, they used to change nothing while other seats read them as done. To say the build should start early, add `"kind": "build_start"` to the decision — it is never asked; the planner records it as `실행 안 됨` (status `void` in the decisions snapshot and the board) and raises the core freeze D1 "제작 시작해도 될까요?" at once (a smaller frozen scope is that D1's "막는 항목만 가정으로 처리하고 시작"). The freeze judge raises no decisions at all: its `recommend` becomes the D1; anything else it raises is recorded as `실행 안 됨`. When re-judging happens is the planner's rule: after the next interview round's analysis is finished, and once more when the planned full-freeze time passes without a core freeze.

Write files (the output, documents, scratch) with the Write tool, never with a Bash heredoc or redirect: the guard reads shell command text, so a heredoc can be refused for words inside it. Give `rm`/`mv`/`git rm` paths relative to the project root: a project rule that names a folder can match an absolute path's parent folders.
**assumption** `{"text": "...", "reason": "...", "related": ["R-003", "Q-007"]}`
**test** `{"requirements": ["R-001"], "input": "인물 말투 그대로의 메시지", "expected": "...", "fail_if": "...", "source": ["U.."]}`
**risk** `{"text": "...", "severity": "높음|중간|낮음"}`

Any mode may add `decisions`, `assumptions`, `tests`, `risks` lists.

## 3. Sections per mode

| mode | who | required section(s) | shape |
|---|---|---|---|
| `scribe` | fde-scribe | `utterance_updates` | `[{"id": "U007", "speaker": "I|P"}]` — speaker fixes only |
| `tag` | fde-utterance-tagger | `utterance_updates` | `[{"id", "tags": ["사실","의견","감정","요청","해결책 제안","망설임","회피","앞말 정정","되묻기","예시 제공","숫자·시간 포함","질문"], "qtype": "open|closed|choice|leading|statement" (interviewer lines)}]` |
| `topic` | fde-topic-classifier | `utterance_updates` | `[{"id", "area": "<10 areas>"}]` |
| `analyze` | analysts | `observations`, `candidates` | registrar adds `requirements`; acceptance designer adds `tests`; interviewer coach adds `to_interviewer` `{"mistakes": [{"kind","evidence","confidence","why","better"}], "missing_questions": [{"question","text","confidence","impact","why_now"}], "next_moves": [str or {"say","why"}], "habits": [str or {"text"}]}` — rendered first in the round report as "인터뷰어에게"; nothing to fix → `"mistakes": []` (never padded) |
| `complement` | analysts | `candidates` | only new or revised items; a revision carries `"revises": "C3"` and a reason in `gap` |
| `brief` | brief analysts | `candidates`, `observations` | opening questions from the problem statement |
| `position` | division heads | `position` | `{"stance", "key_findings": [{"text","evidence","from": ["agent"]}], "team_disagreements": [...], "priorities": [...]}` + optional `debate.issues`, `candidates` |
| `review` | division heads | `debate` | `{"issues": [{"id": "X1", "target": "<division>", "topic", "position", "stance": "agree|partial|disagree", "evidence"}]}` + optional `candidates` |
| `rebuttal` | division heads | `debate` | `{"responses": [{"replies_to": "<reviewer agent>:<X id>", "topic", "position", "stance": "accept|partial|rebut", "evidence"}]}` |
| `ruling` | fde-arbiter | `debate` | `{"rulings": [{"issue": "<agent>:<X id>", "topic", "ruling", "minority": [{"by","text"}], "status": "ruled"}]}` + optional `candidates`, `decisions` |
| `merge` | fde-candidate-merger | `merged` | `[{"members": ["<db ids>"], "kind","area","gap","question_draft","decision_at_stake","if_wrong","self_confidence","impact_guess","divisions": [...]}]` or `{"members": [...], "drop_reason": "이미 물어봄 Q-003 | 이미 가정 A-002 | 중복 | 결정사항으로 이동"}` |
| `verify` | fde-blind-verifier | `verdicts` | `[{"candidate", "confidence", "impact", "already_answered": bool, "answered_by": ["U.."], "forced": bool, "forced_reason": "일반론|답과 무관|범위 밖|과잉 해석", "reason"}]` |
| `counter` | fde-counter-arguer | `verdicts` | `[{"candidate", "verdict": "ask|assume|skip", "reason", "default"(assume·skip), "residual_risk"}]` |
| `audit` | fde-doc-auditor | `findings` | `[{"docs": [...], "issue", "severity", "fix"}]` |
| `write` | fde-question-writer | `cards` | `[{"question": "Q-001", "text", "order", "style": "선택지형|열린형|예시 제시형", "why_this_form"}]` |
| `sequence` | fde-question-sequencer | `sequence` | `[{"question", "order", "group", "reason"}]` |
| `readback` | fde-readback-writer | `readback` | `{"text", "uncertain_points": [...], "covers_until"}` |
| `conclude` / `opening` | fde-engagement-lead | `report` | `{"next_10min", "conflicts": [...], "spec_changes": [...], "warnings": [...], "stale": [...], "phase_advice", "opening_plan" (opening)}` + graded `decisions` |
| `minutes` / `final` | fde-chief-clerk | `minutes` / `final` | `{"text", "stance_changes": [...]}` / `{"text", "links": [...]}` |
| `freeze` | fde-freeze-judge | `freeze` | `{"recommend": "freeze|confirm_first|wait|freeze_with_assumptions", "reason", "blockers": [...], "assumptions_if_frozen": [...], "risks": [...], "internal_confidence": "확실|가능성 높음|추측", "confidence_basis": {"must_with_evidence","open_high_impact","blockers_by_perspective": {}}, "missing_info": [{"info","would_change","question","confidence"}]}` — `recommend` picks the default of the D1 "제작 시작해도 될까요?"; the top 3 `missing_info` become cards on "이것만 더 확인하고 시작" |
| `change` | fde-change-analyst | `change` | `{"summary", "affected": {"requirements","files","tasks"}, "effort_min", "recommend": "accept|defer|reject", "grade"}` + `decisions` |
| `tech` | tech committee | `proposals` | `[{"item", "options": [{"option","pros","cons","effort_min","fits_requirements"}], "recommend", "confidence"}]` |
| `challenge` | fde-tech-devils-advocate | `challenges` | `[{"item", "against", "simpler_alternative", "verdict": "accept|simplify|reject"}]` |
| `decide` | fde-tech-lead | `adrs` | `[{"title","decision","alternatives": [{"option","why_not"}],"dissent","requirements","rollback","grade","status": "proposed","path"}]` |
| `plan` / `replan` | fde-tech-lead | `plan` | `{"slices": [{"n","goal"}], "tasks": [{"title","slice","files","owner","designers","requirements","acceptance"}]}` |
| `design` | build designers | `design` | `{"slice","decisions","files","graph_changes","prompts","schema","risks"}`; the detail designer adds `detail` (state × copy matrix, input variants, formats, terms, resume, copy rules, acceptance hints); the design lead adds `decision_points` `[{"title","options","tradeoffs","effort_min","recommended","grade"}]` — real forks only (2–4, `[]` when none), asked to the user in collaboration mode before anyone implements |
| `trace` | fde-spec-tracer | `trace` | `{"links": [{"requirement","design_element","test"}], "gaps": [...]}` |
| `implement` / `unblock` | developers | `implementation` | `{"tasks_done","tasks_blocked","files_changed","tests_added","commands_run": [{"cmd","exit","tail"}],"notes"}`; a `tasks_blocked` item is a task id or `{"task","reason","design_question": {"title","options","recommended","why"}}` — in collaboration mode developers follow input `design_choices` and park real design choices this way instead of deciding alone |
| `codereview` | reviewers | `review` | `{"verdict": "ACCEPT|REJECT", "items": [...], "rework": [{"task","fix"}]}` |
| `deploy` | fde-deploy-operator | `deploy` | `{"ok", "steps": [{"cmd","exit","tail"}], "commit", "health"}` |
| `release` / `rollback` | fde-release-manager | `release` | `{"tag","commit","good","test","deploy","health","qa","notes"}` |
| `observe` | fde-observability | `observations` | `[{"text","evidence","severity"}]` + `risks` |
| `qa` | QA testers, fit judge, UX and AI-tell checkers | `qa` | `[{"test","input","output","verdict": "PASS|FAIL","reason","latency_s"}]` + `extra.unverified`; UX adds `extra.metrics` (tasks, completed, avg_turns, ideal_turns, dead_ends, repeat_asks, recoveries), AI-tell adds `extra.meter` (from `fde aitell`) and `extra.findings` with rewrites |
| `verdict` | fde-qa-lead | `qa_verdict` | `{"verdict": "PASS|FAIL","blocking","fix_tasks": [{"title","files","owner","requirements"}],"human_checks": [...],"severity": "critical|major|minor|none","rollback": bool}` — `rollback: true` only for `critical` (worse than the last good release on the live platform); the engine then starts `RB-<slice>` automatically (H-05) |
| `dataplan` / `validate` / `consistency` / `clean` / `load` / `audit`(data) / `datareport` | data division | `data_report` | `{"assets": [{"path","name","kind","rows","status","report","notes"}], "issues", "rules", "commands_run"}` (data audit uses `findings` too) |
| `final` | release manager / demo writer | `final` | `{"text", ...}` |
| `retro` | fde-retro-analyst | `lessons` | `[{"lesson","evidence","apply_next_time"}]` |
| `create` | fde-mock-persona | `mock` | `{"public_brief","roleplay_prompt_path","sealed_paths"}` |
| `grade` | fde-rehearsal-grader | `grade` | `{"recall","found","missed","forced_rate","reasked","timings","advice"}` |

Note: the data provenance auditor runs in mode `audit` and must provide `findings` (and may add `data_report`).

Extra fields of note: `fde-environment-analyst` → `extra.environment` (matrix rows) + `extra.constraints`, and it rewrites `docs/environment.md`; `fde-packaging-strategist` → `extra.packaging` (`situation`, `fixed_form`, `surface_needs`, `options`, `fit_gap`, `companions`, `portability`), and it rewrites `docs/packaging.md`. Both documents are passed to every analyst as inputs `environment` / `packaging` once they exist.

## 4. Probe policy (QA seats, data loader, QA lead)

The project binding names `probe_local`, `probe_remote` and `probe_wipe` (placeholders `{user}`, `{message}`, optional `{conv}`; shell-quote the message with single quotes, inner `'` as `'\''`). The probe runs the real pipeline once without sending anything to the platform and prints one JSON line last: `bubbles`, `quick_replies`, `elapsed_s`, `provider`, `onboarding`, `fallback`, `response` (raw platform payload), `error`, and where available `trace`, `profile_after`, `memories_after`, `extract_s`, `mode`.

- **Bulk on `probe_local`**: same code, isolated test store; different test keys may run at the same time. The `mode` field says whether retrieval ran (`rag: local|server|off`) — report it; never FAIL retrieval behaviour that the probe could not exercise (put it in `extra.unverified`).
- **`probe_remote` sparingly**: it runs on the live server, one at a time (others queue). At most 3 per seat per dispatch, chosen to prove the deployment (must-requirement paths, real latency). Empty → local only.
- **Keys**: `qa-<run id lower>-<seat>-<n>`; one key per simulated person/conversation; never the real persona's key. Wipe every key you used with `probe_wipe` before writing your output, and list them in `extra.users_wiped`.
- **What a probe cannot prove**: the real platform screen, the webhook/reply-token path, console settings. Those go to the QA lead's `human_checks`.
