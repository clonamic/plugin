# Design document format (agent contract)

`cagent.py get` returns `{"doc": ..., "version": N, ...}`. Edit a copy of `doc` and send it back whole with `put --version N`. Keep every key; unknown keys are kept as-is. Never touch `layout` (canvas positions; the editor fills it).

```jsonc
{
  "format": 1,
  "name": "프로젝트 이름", "summary": "목적 한 줄",
  "want": "원하는 것", "background": "", "success": ["성공 기준"],
  "inputs":  [{"item": "데이터 이름", "desc": "설명"}],
  "outputs": [{"item": "데이터 이름", "desc": "설명"}],
  "not_doing": "", "constraints": ["제약"],
  "tools": [{"id": "T1", "kind": "MCP 서버|내부 에이전트|파일·스크립트|외부 API|웹 검색|데이터베이스|모델|기타",
             "name": "지도 MCP", "purpose": "장소 검색", "location": "maps 서버 / tools/plan.py / https://…", "alternative": "",
             "ref": "A3 (kind가 내부 에이전트일 때만: 가리키는 에이전트 id, 이름은 그 에이전트를 따른다)"}],
  "human_points": [{"point": "A2-N1", "does": "후보 선택", "meanwhile": "멈춰 기다림"}],
  "scenarios": [{"name": "정상", "input": "…", "path": "A1 → L2 → A2", "expected": "…"}],
  "decisions": [{"decision": "", "why": "", "rejected": ""}],
  "open": ["미결 사항"],
  "glossary": [{"name": "데이터 이름", "meaning": "뜻", "contents": "담기는 내용"}],
  "agents": [{
    "id": "A1", "name": "여행 계획", "color": "", "role": "역할 한 줄", "intent": "왜 따로 나눴나",
    "not_doing": "", "exits": [{"name": "완료", "when": "언제"}],  // shown as 출력 (outcomes) in the editor and documents
    "fixed": "", "discretion": "", "paths": "", "notes": "",
    "steps": [{
      "id": "N1", "name": "짧은 기능명", "type": "판단|처리|외부 연동|사람 확인", "summary": "한 줄",
      "intent": "", "inputs": ["데이터 이름"], "outputs": ["데이터 이름"],
      "process": [{"unit": "파일|모듈|클래스|함수|외부 호출|사람 작업|기타", "name": "minutes_loader.py", "does": "회의록을 읽는다", "tool": "T1 또는 빈 값"}],
      "tools": ["T1"], "done": ["완료 기준"],
      "fixed": "", "discretion": "", "example": "받음: … → 내놓음: …", "cautions": "", "on_fail": ""
    }],
    "edges": [{
      "id": "L1", "from": "start | N1", "to": "N2 | exit:<출력 이름>", "kind": "always | cond",
      "name": "조건 요약(조건 연결)", "condition": "", "judge": "정해진 규칙|AI 판단|사람",
      "loop_exit": "L6", "loop_limit": "2", "intent": "", "passes": ["데이터 이름"]
    }]
  }],
  "links": [{
    "id": "L1", "from": "start | A1", "exit": "<from 에이전트의 출력 이름, start면 비움>", "to": "A2 | end",
    "kind": "always | cond", "name": "", "condition": "", "judge": "", "loop_exit": "", "loop_limit": "",
    "intent": "", "passes": ["데이터 이름"]
  }]
}
```

Rules the checks enforce (see `cagent.py check`):

- Ids: agents `A1…`, steps `N1…` and edges `L1…` inside each agent, links `L1…` at the agent level. Number in flow order from the start; never reuse an id.
- `tools` is the project's tool catalog; steps and process items reference catalog ids. Every referenced id must exist, every catalog tool must be used by some step or process item, and an internal-agent tool must point at an existing agent.
- A step needs at least one named `process` item. Process names and tool locations may be implementation names (files, modules, classes, functions, endpoints); every other field stays in plain language.
- Every exit (출력) of an agent has exactly one link leaving through it; every link from an agent names one of its exits.
- Several edges out of the same node must all be `cond`; a single `cond` edge alone is an error (no path when the condition fails).
- An edge that returns to an earlier node needs `loop_exit` (another edge id in the same list) and `loop_limit`.
- Every step `inputs` name is produced somewhere (a project input or a step output); every output is consumed (a step input, an edge/link `passes`, or a project output).
- A data name used in two or more documents must be in `glossary`.
- Required fields: see the `*` marks in the editor; conditional edges also need `name`, `condition`, `judge`, `intent`.
- Older documents (`does` lines, tool rows with `capability`/`recommended`) are converted automatically when read; always write the current shape.
