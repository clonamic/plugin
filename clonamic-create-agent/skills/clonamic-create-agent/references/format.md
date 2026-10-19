# Design document format (agent contract)

`cagent.py get` returns `{"doc": ..., "version": N, ...}`. Edit a copy of `doc` and send it back whole with `put --version N`. Keep every key; unknown keys are kept as-is. Never touch `layout` (canvas positions; the editor fills it).

If the document changed after your `get`, `put` merges your changes onto the current version when the two touched different units (a project field, a tool, a data entry, a link, an agent's own fields, a step, an inner edge) and answers `merged: true`. When both changed the same unit differently it answers 409 with `conflicts` (their labels): `get` again and redo your change on the new document.

```jsonc
{
  "format": 1,
  "name": "프로젝트 이름", "summary": "요약",
  "want": "요구사항", "background": "", "success": ["성공 기준"],
  "inputs":  [{"item": "데이터 이름", "desc": "설명"}],          // project input
  "outputs": [{"item": "데이터 이름", "desc": "설명"}],          // project output
  "not_doing": "범위 밖", "constraints": ["제약"],
  "tools": [{"id": "T1", "kind": "MCP 서버|내부 에이전트|파일·스크립트|외부 API|웹 검색|데이터베이스|모델|기타",
             "name": "지도 MCP", "purpose": "장소 검색", "location": "maps 서버, 토큰 인증 / tools/plan.py / https://…", "alternative": "",
             "ref": "A3 (kind가 내부 에이전트일 때만: 가리키는 에이전트 id, 이름은 그 에이전트를 따른다)"}],
  "human_points": [{"point": "A2-N1", "does": "후보 선택", "meanwhile": "멈춰 기다림"}],
  "scenarios": [{"name": "정상", "input": "실제 값", "path": "A1 → L2 → A2", "expected": "…", "criteria": "확인하는 성공 기준"}],
  "decisions": [{"decision": "", "why": "", "rejected": ""}],
  "open": ["미결 사항과 추천 값"],
  "glossary": [{"name": "데이터 이름", "meaning": "뜻", "contents": "필드로 담지 못한 규칙",
                "fields": [{"name": "필드", "type": "문자열|숫자|정수|참/거짓|날짜|날짜와 시각|목록|객체|파일|기타",
                            "required": true, "desc": "단위, 허용 값, 안에 든 것", "example": "예"}]}],
  "agents": [{
    "id": "A1", "name": "여행 계획", "color": "", "role": "역할", "intent": "필요한 이유",
    "not_doing": "", "fixed": "지켜야 할 것", "discretion": "구현자가 정할 것", "paths": "정상·예외 흐름", "notes": "공통 제약",
    "steps": [{
      "id": "N1", "name": "짧은 기능명", "type": "판단|처리|외부 연동|사람 확인", "summary": "요약",
      "intent": "필요한 이유", "inputs": ["데이터 이름"], "outputs": ["데이터 이름"],
      "process": [{"unit": "파일|모듈|클래스|함수|외부 호출|사람 작업|기타", "name": "minutes_loader.py", "does": "1. 파일을 UTF-8로 읽는다\n2. 비어 있으면 '빈 회의록'으로 멈춘다",
                   "input": "회의록", "output": "회의록 본문", "tool": "T1 또는 빈 값"}],
      "criteria": ["판단 기준 (판단 단계)"], "prompt": "AI 지시 (판단 단계)",
      "tools": ["T1"], "done": ["완료 기준"], "example": "정상 input: … → output: …\n예외 input: … → 처리: …", "on_fail": "실패 처리",
      "fixed": "", "discretion": "", "cautions": ""
    }],
    "edges": [{
      "id": "L1", "from": "start | N1", "to": "N2 | end", "kind": "always | cond",
      "name": "조건 요약(조건 연결)", "condition": "", "judge": "정해진 규칙|AI 판단|사람",
      "loop_limit": "2", "loop_exit": "L6", "intent": "", "passes": ["데이터 이름"]
    }]
  }],
  "links": [{
    "id": "L1", "from": "start | A1", "to": "A2 | end",
    "kind": "always | cond", "name": "", "condition": "", "judge": "", "loop_limit": "", "loop_exit": "",
    "intent": "", "passes": ["데이터 이름"]
  }]
}
```

Inside an agent the flow runs from `start` to `end`; an agent finishes at `end` and its outgoing links (with conditions) decide where the work goes next. There is no separate "exit" object. Older documents with `exits` and `exit:<name>` are converted automatically when read or written (the exit name becomes the link name and its "when" the link condition).

Rules the checks enforce (see `cagent.py check`). Every issue has a `level`: `error` blocks export (the user can still export a draft), `warning` only points at a likely mistake. `check` is `ok` when there is no error.

- Ids: agents `A1…`, steps `N1…` and edges `L1…` inside each agent, links `L1…` at the agent level, tools `T1…`. Number in flow order from the start; never reuse an id. `put` refuses a document with a missing, malformed, or repeated id, or a field of the wrong type (text fields are strings, list fields are lists; never `null`).
- Flow: every agent is reachable from `start` and some link reaches `end`; every agent has steps; inside an agent every step is reachable from `start`, has an outgoing edge (no dead end), and some edge reaches `end`. Edges leave `start` or a step and arrive at a step or `end`.
- Several edges or links out of the same node must all be `cond`; a single `cond` one alone is an error (no path when the condition fails). Conditional ones need `name`, `condition`, `judge`, `intent`.
- An edge or link that returns to an earlier node needs `loop_limit` (a whole number) and `loop_exit` (another edge leaving the same node).
- Required fields: the `*` marks in the editor. Steps also need, by type: 판단 → `criteria`, `prompt`, `on_fail`; 외부 연동 and 사람 확인 → `on_fail`. Every step needs `example`, at least one named `process` item, and every named process item needs `does` (one procedure line per line; the export lists each line under the item). Project needs `scenarios` and `tools` (at least one; an LLM-only step uses a `모델` tool). Every edge and link needs `passes`.
- `tools`: every referenced id exists, every catalog tool has a name and is used by a step or process item, an internal-agent tool points at an existing agent.
- Data: every step `inputs` name is produced somewhere (a project input or a step output); every output is consumed (a step input, an edge/link `passes`, or a project output).
- Data dictionary: every data name used anywhere is in `glossary` with at least one field that has a name and a type. Names that differ only by spacing or case are flagged as the same name.
- Process chain: when process rows name their input/output, a row may only use a data name the step receives or an earlier row made, and every step output must come out of some row (free text that is not a data name is not checked).
- Step kinds: a 판단 step uses a tool of kind `모델`; a 사람 확인 step is listed in `human_points` (as `A1-N3`).
- Scenario paths: every number written in a scenario `path` (A1, L2, A1-N3, A1-L4) exists.
- No edge or link goes from a node to itself (a retry belongs in `on_fail`, or goes through another step).
- Warnings: a glossary entry nobody uses; a `목록`/`객체` field without a `desc` of what it holds; two agents (or two steps in one agent) with the same name; a number like `S1-N2` in any text that is not a real step or edge id (write the real ids).
- `color` is empty or `#rrggbb`.
- Process names and tool locations may be implementation names (files, modules, classes, functions, endpoints); every other field stays in plain language.
