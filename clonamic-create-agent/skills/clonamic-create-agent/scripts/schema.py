"""Document fields: one source for the editor form, the renderer, and the required-field check."""

from __future__ import annotations

FORMAT = 1
STEP_TYPES = ["판단", "처리", "외부 연동", "사람 확인"]
EDGE_KINDS = {"always": "항상", "cond": "조건"}
JUDGES = ["정해진 규칙", "AI 판단", "사람"]
COLORS = ["#0066CC", "#B34700", "#1E7B3C", "#7A3FC4", "#C0262D", "#0E7480", "#8A5A2B", "#A21C6B"]  # white text >= 4.5:1
TOOL_KINDS = ["MCP 서버", "내부 에이전트", "파일·스크립트", "외부 API", "웹 검색", "데이터베이스", "모델", "기타"]
PROCESS_UNITS = ["파일", "모듈", "클래스", "함수", "외부 호출", "사람 작업", "기타"]

# (key, label, kind, required, extra)
# kind: line | text | lines | names | table | select | ref | exit | color | tools (catalog) | toolrefs | process
PROJECT = [
    ("name", "프로젝트 이름", "line", True, None),
    ("summary", "목적 한 줄", "line", True, None),
    ("want", "원하는 것", "text", True, None),
    ("background", "배경", "text", False, None),
    ("success", "성공 기준", "lines", True, None),
    ("inputs", "입력", "table", True, [("item", "항목"), ("desc", "설명")]),
    ("outputs", "출력", "table", True, [("item", "항목"), ("desc", "설명")]),
    ("not_doing", "하지 않는 것", "text", False, None),
    ("constraints", "제약", "lines", False, None),
    ("tools", "도구 목록", "tools", True, None),
    ("human_points", "사람 개입 지점", "table", False,
     [("point", "지점"), ("does", "사람이 하는 일"), ("meanwhile", "그동안 흐름은")]),
    ("scenarios", "검증 시나리오", "table", True,
     [("name", "시나리오"), ("input", "입력"), ("path", "거치는 경로"), ("expected", "기대 결과")]),
    ("decisions", "설계 결정", "table", False, [("decision", "결정"), ("why", "이유"), ("rejected", "버린 대안")]),
    ("open", "미결 사항", "lines", False, None),
    ("glossary", "용어 사전", "table", False, [("name", "이름"), ("meaning", "뜻"), ("contents", "담기는 내용")]),
]
AGENT = [
    ("name", "이름", "line", True, None),
    ("color", "색", "color", False, None),
    ("role", "역할 한 줄", "line", True, None),
    ("intent", "의도", "text", True, None),
    ("not_doing", "맡지 않는 것", "text", False, None),
    ("exits", "출력", "table", True, [("name", "출력"), ("when", "언제")]),
    ("fixed", "고정", "text", False, None),
    ("discretion", "재량", "text", False, None),
    ("paths", "주요 경로", "text", False, None),
    ("notes", "공통 주의점", "text", False, None),
]
STEP = [
    ("name", "이름", "line", True, None),
    ("type", "유형", "select", True, STEP_TYPES),
    ("summary", "한 줄 요약", "line", True, None),
    ("intent", "의도", "text", True, None),
    ("inputs", "입력", "names", True, None),
    ("process", "과정", "process", True, None),
    ("outputs", "출력", "names", True, None),
    ("tools", "도구", "toolrefs", False, None),
    ("done", "완료 기준", "lines", True, None),
    ("fixed", "고정", "text", False, None),
    ("discretion", "재량", "text", False, None),
    ("example", "예시", "line", False, None),
    ("cautions", "주의점", "text", False, None),
    ("on_fail", "실패 시", "text", False, None),
]
EDGE = [
    ("name", "이름", "line", False, None),
    ("kind", "종류", "select", True, list(EDGE_KINDS)),
    ("condition", "조건", "text", False, None),
    ("judge", "판단 주체", "select", False, JUDGES),
    ("loop_exit", "반복 탈출 연결", "ref", False, None),
    ("loop_limit", "반복 탈출 횟수", "line", False, None),
    ("intent", "의도", "text", False, None),
    ("passes", "넘기는 것", "names", True, None),
]
LINK = [("exit", "출발 출력", "exit", True, None)] + EDGE
COND_REQUIRED = ("name", "condition", "judge", "intent")

SCHEMA = {"project": PROJECT, "agent": AGENT, "step": STEP, "edge": EDGE, "link": LINK,
          "step_types": STEP_TYPES, "edge_kinds": EDGE_KINDS, "judges": JUDGES, "colors": COLORS,
          "tool_kinds": TOOL_KINDS, "process_units": PROCESS_UNITS}


def label(kind: str, key: str) -> str:
    return next(f[1] for f in SCHEMA[kind] if f[0] == key)


def missing(kind: str, obj: dict) -> list[str]:
    """Labels of required fields that are empty. Conditional edges also need name, condition, judge, intent."""
    keys = [f[0] for f in SCHEMA[kind] if f[3]]
    if kind in ("edge", "link") and obj.get("kind") == "cond":
        keys += list(COND_REQUIRED)
    if kind == "link" and obj.get("from") == "start":
        keys.remove("exit")
    if kind == "step":  # a process needs at least one named item
        keys = [k for k in keys if k != "process"]
        if not any(str(p.get("name", "")).strip() for p in obj.get("process", []) if isinstance(p, dict)):
            keys.append("process")
    return [label(kind, k) for k in dict.fromkeys(keys) if k == "process" or not filled(obj.get(k))]


def filled(value) -> bool:
    if isinstance(value, list):
        return any(filled(v) for v in value)
    if isinstance(value, dict):
        return any(filled(v) for v in value.values())
    return bool(str(value or "").strip())


def new_project(name: str) -> dict:
    doc = {"format": FORMAT, "agents": [], "links": []}
    for key, _, kind, _, _ in PROJECT:
        doc[key] = [] if kind in ("lines", "names", "table", "tools") else ""
    doc["name"] = name
    return doc


def tool_name(doc: dict, tool: dict) -> str:
    """Display name; an internal-agent tool follows the agent's current name."""
    if tool.get("kind") == "내부 에이전트" and tool.get("ref"):
        agent = next((a for a in doc.get("agents", []) if a.get("id") == tool["ref"]), None)
        if agent:
            return f"{agent['id']} {agent.get('name', '')}".strip()
    return tool.get("name", "")


def migrate(doc: dict) -> dict:
    """Bring older documents to the current shape in place (idempotent).

    - project tools rows {capability, used_in, recommended, alternative} -> catalog {id, kind, name, purpose, location, alternative}
    - step tools rows and agent tools rows -> references to catalog ids
    - step "does" lines -> "process" items
    """
    tools = doc.setdefault("tools", [])
    by_name: dict[str, str] = {}
    for i, t in enumerate(list(tools)):
        if "id" not in t:
            t = {"id": "", "kind": "기타", "name": t.get("recommended") or t.get("capability", ""),
                 "purpose": t.get("capability", "") if t.get("recommended") else "", "location": "",
                 "alternative": t.get("alternative", "")}
            tools[i] = t
    used = {t["id"] for t in tools if t.get("id")}
    n = 0
    for t in tools:
        if not t.get("id"):
            while f"T{n + 1}" in used:
                n += 1
            n += 1
            t["id"] = f"T{n}"
            used.add(t["id"])
        by_name.setdefault(t.get("name", ""), t["id"])

    def ensure(name: str) -> str:
        nonlocal n
        name = (name or "").strip()
        if not name:
            return ""
        if name not in by_name:
            while f"T{n + 1}" in used:
                n += 1
            n += 1
            tid = f"T{n}"
            used.add(tid)
            tools.append({"id": tid, "kind": "기타", "name": name, "purpose": "", "location": "", "alternative": ""})
            by_name[name] = tid
        return by_name[name]

    for agent in doc.get("agents", []):
        for row in agent.pop("tools", []) or []:
            if isinstance(row, dict):
                ensure(row.get("recommended") or row.get("capability", ""))
        for step in agent.get("steps", []):
            if "does" in step:
                if not step.get("process"):
                    step["process"] = [{"unit": "기타", "name": x, "does": "", "tool": ""} for x in step["does"] if str(x).strip()]
                step.pop("does")
            step.setdefault("process", [])
            refs = []
            for row in step.get("tools", []) or []:
                tid = ensure(row.get("recommended") or row.get("capability", "")) if isinstance(row, dict) else row
                if tid and tid not in refs:
                    refs.append(tid)
            step["tools"] = refs
    return doc
