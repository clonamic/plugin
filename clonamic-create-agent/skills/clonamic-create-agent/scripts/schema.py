"""Document fields: one source for the editor form, the renderer, and the required-field check."""

from __future__ import annotations

import re

FORMAT = 1
STEP_TYPES = ["판단", "처리", "외부 연동", "사람 확인"]
EDGE_KINDS = {"always": "항상", "cond": "조건"}
JUDGES = ["정해진 규칙", "AI 판단", "사람"]
COLORS = ["#0066CC", "#B34700", "#1E7B3C", "#7A3FC4", "#C0262D", "#0E7480", "#8A5A2B", "#A21C6B"]  # white text >= 4.5:1
TOOL_KINDS = ["MCP 서버", "내부 에이전트", "파일·스크립트", "외부 API", "웹 검색", "데이터베이스", "모델", "기타"]
PROCESS_UNITS = ["파일", "모듈", "클래스", "함수", "외부 호출", "사람 작업", "기타"]

DATA_TYPES = ["문자열", "숫자", "정수", "참/거짓", "날짜", "날짜와 시각", "목록", "객체", "파일", "기타"]

# (key, label, kind, required, extra)
# kind: line | text | lines | names | table | select | ref | color | tools (catalog) | toolrefs | process | glossary
# Labels are what the editor and the exported documents show; keys never change.
PROJECT = [
    ("name", "프로젝트 이름", "line", True, None),
    ("summary", "요약", "line", True, None),
    ("want", "요구사항", "text", True, None),
    ("background", "배경", "text", False, None),
    ("success", "성공 기준", "lines", True, None),
    ("inputs", "input", "table", True, [("item", "데이터"), ("desc", "설명")]),
    ("outputs", "output", "table", True, [("item", "데이터"), ("desc", "설명")]),
    ("not_doing", "범위 밖", "text", False, None),
    ("constraints", "제약", "lines", False, None),
    ("tools", "도구 목록", "tools", True, None),
    ("human_points", "사람 확인 지점", "table", False,
     [("point", "지점"), ("does", "사람이 하는 일"), ("meanwhile", "그동안 흐름")]),
    ("scenarios", "검증 시나리오", "table", True,
     [("name", "시나리오"), ("input", "input"), ("path", "경로"), ("expected", "기대 결과"), ("criteria", "확인하는 성공 기준")]),
    ("decisions", "설계 결정", "table", False, [("decision", "결정"), ("why", "이유"), ("rejected", "버린 대안")]),
    ("open", "미결 사항", "lines", False, None),
    ("glossary", "데이터 사전", "glossary", False, None),
]
AGENT = [
    ("name", "이름", "line", True, None),
    ("color", "색", "color", False, None),
    ("role", "역할", "line", True, None),
    ("intent", "필요한 이유", "text", True, None),
    ("not_doing", "범위 밖", "text", False, None),
    ("fixed", "지켜야 할 것", "text", False, None),
    ("discretion", "구현자가 정할 것", "text", False, None),
    ("paths", "정상·예외 흐름", "text", False, None),
    ("notes", "공통 제약", "text", False, None),
]
STEP = [
    ("name", "이름", "line", True, None),
    ("type", "유형", "select", True, STEP_TYPES),
    ("summary", "요약", "line", True, None),
    ("intent", "필요한 이유", "text", True, None),
    ("inputs", "input", "names", True, None),
    ("process", "과정", "process", True, None),
    ("outputs", "output", "names", True, None),
    ("criteria", "판단 기준", "lines", False, None),
    ("prompt", "AI 지시", "text", False, None),
    ("tools", "도구", "toolrefs", False, None),
    ("done", "완료 기준", "lines", True, None),
    ("example", "예시", "text", True, None),
    ("on_fail", "실패 처리", "text", False, None),
    ("fixed", "지켜야 할 것", "text", False, None),
    ("discretion", "구현자가 정할 것", "text", False, None),
    ("cautions", "주의점", "text", False, None),
]
EDGE = [
    ("name", "이름", "line", False, None),
    ("kind", "종류", "select", True, list(EDGE_KINDS)),
    ("condition", "조건", "text", False, None),
    ("judge", "판단 방식", "select", False, JUDGES),
    ("loop_limit", "최대 반복 횟수", "line", False, None),
    ("loop_exit", "한도를 넘으면 갈 연결", "ref", False, None),
    ("intent", "필요한 이유", "text", False, None),
    ("passes", "전달 데이터", "names", True, None),
]
LINK = EDGE
COND_REQUIRED = ("name", "condition", "judge", "intent")
# A step's type decides what else an implementer needs: an AI judgement needs its criteria, its instructions,
# and what happens when it fails; a call to an outside system or a person needs a failure path.
TYPE_REQUIRED = {"판단": ("criteria", "prompt", "on_fail"), "외부 연동": ("on_fail",), "사람 확인": ("on_fail",)}

SCHEMA = {"project": PROJECT, "agent": AGENT, "step": STEP, "edge": EDGE, "link": LINK,
          "step_types": STEP_TYPES, "edge_kinds": EDGE_KINDS, "judges": JUDGES, "colors": COLORS,
          "tool_kinds": TOOL_KINDS, "process_units": PROCESS_UNITS, "data_types": DATA_TYPES,
          "cond_required": COND_REQUIRED, "type_required": TYPE_REQUIRED}


def label(kind: str, key: str) -> str:
    return next(f[1] for f in SCHEMA[kind] if f[0] == key)


def missing(kind: str, obj: dict) -> list[str]:
    """Labels of required fields that are empty: the * fields, plus name/condition/judge/intent on a conditional
    edge and the TYPE_REQUIRED fields of a step's type."""
    keys = [f[0] for f in SCHEMA[kind] if f[3]]
    if kind in ("edge", "link") and obj.get("kind") == "cond":
        keys += list(COND_REQUIRED)
    if kind == "step":
        keys += list(TYPE_REQUIRED.get(obj.get("type", ""), ()))
        keys = [k for k in keys if k != "process"]  # a process needs at least one named item
        if not any(str(p.get("name", "")).strip() for p in obj.get("process", []) if isinstance(p, dict)):
            keys.append("process")
    return [label(kind, k) for k in dict.fromkeys(keys) if k == "process" or not filled(obj.get(k))]


def filled(value) -> bool:
    if isinstance(value, list):
        return any(filled(v) for v in value)
    if isinstance(value, dict):
        return any(filled(v) for v in value.values())
    return bool(str(value or "").strip())


TEXT_KINDS = {"line", "text", "select", "ref", "color"}
ID = re.compile(r"^[A-Z]\d+$")


def shape_error(doc) -> str:
    """Why a document may not be stored ('' when it may). Everything that reads it later (checks, render, the editor)
    relies on these types and on unique ids, so a bad `put`, card, or imported file is refused at the door."""
    if not isinstance(doc, dict):
        return "문서가 JSON 객체가 아닙니다."

    def fields(kind: str, obj, where: str) -> str:
        if not isinstance(obj, dict):
            return f"{where}가 객체가 아닙니다."
        for key, _, k, _, _ in SCHEMA[kind]:
            if key not in obj:
                continue
            v = obj[key]
            if k in TEXT_KINDS and not isinstance(v, str):
                return f"{where}의 {key}는 문자열이어야 합니다."
            if k in ("lines", "names", "toolrefs") and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
                return f"{where}의 {key}는 문자열 목록이어야 합니다."
            if k in ("table", "tools", "process", "glossary") and not (isinstance(v, list) and all(isinstance(x, dict) for x in v)):
                return f"{where}의 {key}는 객체 목록이어야 합니다."
        return ""

    def ids(items, where: str) -> str:
        seen = set()
        for x in items:
            i = x.get("id") if isinstance(x, dict) else None
            if not isinstance(i, str) or not ID.match(i):
                return f"{where}에 번호(예: A1)가 없거나 형식이 틀린 항목이 있습니다."
            if i in seen:
                return f"{where}에 같은 번호 {i}가 둘 있습니다."
            seen.add(i)
        return ""

    for key in ("agents", "links"):
        if not isinstance(doc.get(key, []), list):
            return f"{key}는 목록이어야 합니다."
    err = fields("project", doc, "프로젝트") or ids(doc.get("agents", []), "에이전트") or ids(doc.get("links", []), "에이전트 연결")
    err = err or ids(doc.get("tools", []), "도구 목록")
    if err:
        return err
    for g in doc.get("glossary", []):
        if not (isinstance(g.get("fields", []), list) and all(isinstance(x, dict) for x in g.get("fields", []))):
            return f"데이터 사전의 {g.get('name', '')} 필드는 객체 목록이어야 합니다."
    for link in doc.get("links", []):
        err = err or fields("link", link, link["id"])
    for a in doc.get("agents", []):
        err = err or fields("agent", a, a["id"])
        for key in ("steps", "edges"):
            if not (isinstance(a.get(key, []), list) and all(isinstance(x, dict) for x in a.get(key, []))):
                return f"{a['id']}의 {key}는 객체 목록이어야 합니다."
        err = err or ids(a.get("steps", []), f"{a['id']}의 단계") or ids(a.get("edges", []), f"{a['id']}의 연결")
        for s in a.get("steps", []):
            err = err or fields("step", s, f"{a['id']}-{s['id']}")
        for e in a.get("edges", []):
            err = err or fields("edge", e, f"{a['id']}-{e['id']}")
    return err


def new_project(name: str) -> dict:
    doc = {"format": FORMAT, "agents": [], "links": []}
    for key, _, kind, _, _ in PROJECT:
        doc[key] = [] if kind in ("lines", "names", "table", "tools", "glossary") else ""
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
    - agent "exits" (named endings) -> inner edges end at "end"; the exit name and its "when" move to the
      agent-level link that left through it (name, condition); several links from one agent become conditional
    - glossary rows get a "fields" list (the data structure)
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
    _drop_exits(doc)
    for g in doc.get("glossary", []):
        if isinstance(g, dict):
            g.setdefault("fields", [])
    return doc


def _drop_exits(doc: dict) -> None:
    links = doc.get("links", [])
    for agent in doc.get("agents", []):
        if "exits" not in agent:
            continue
        exits = [x for x in agent.pop("exits") or [] if isinstance(x, dict)]
        when = {x.get("name", ""): x.get("when", "") for x in exits}
        for e in agent.get("edges", []):
            if str(e.get("to", "")).startswith("exit:"):
                name = e["to"][5:]
                e["to"] = "end"
                if len(exits) > 1 and not str(e.get("name", "")).strip():
                    e["name"] = name
        layout = (doc.get("layout") or {}).get(agent.get("id"), {})
        for key in [k for k in layout if k.startswith("exit:")]:
            del layout[key]
        out = [link for link in links if link.get("from") == agent.get("id")]
        for link in out:
            name = link.get("exit", "")
            if name and not str(link.get("name", "")).strip():
                link["name"] = name
            if when.get(name) and not str(link.get("condition", "")).strip():
                link["condition"] = when[name]
            if len(out) > 1:
                link["kind"] = "cond"
    for link in links:
        link.pop("exit", None)
