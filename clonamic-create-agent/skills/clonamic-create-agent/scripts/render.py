"""Render a design document into the export file set. Same input -> byte-identical output."""

from __future__ import annotations

import json
import posixpath
import re

from checks import usage
from graph import END, START, agent_name, by_id, edge_name, find, full, link_name, node_name
from schema import EDGE_KINDS, FORMAT, VERSION, tool_name

WARNING = "clonamic-create-agent 편집기에서 만든 문서다. 고칠 때는 편집기에서 고친다."


def slug(text: str) -> str:
    """A file or folder name: no path or link characters, at most 40 characters (Hangul is 3 bytes each and
    a name may hold 255 bytes), and no trailing dot or space (Windows drops them, which would break links)."""
    text = re.sub(r'[\\/:*?"<>|#\[\]()\x00-\x1f]', "", text or "").strip()
    return re.sub(r"\s+", "_", text)[:40].rstrip(". _") or "이름없음"


class Md(str):
    """Markdown this renderer wrote (a link, a list of links): never escaped again."""


def esc(text, full: bool = True) -> str:
    """User text that must stay text: outside `code` spans, brackets stop forming links and < > stop forming tags.
    `full` (table cells) escapes every bracket; body text only the "](" that would start a link."""
    parts = str(text or "").split("`")
    for i in range(0, len(parts), 2):
        t = parts[i].replace("<", "&lt;").replace(">", "&gt;") if full else re.sub(r"<(?=[A-Za-z/!])", "&lt;", parts[i])
        parts[i] = t.replace("[", "\\[").replace("]", "\\]") if full else t.replace("](", "\\](")
    return "`".join(parts)


def para(text) -> str:
    return esc(str(text or "").strip(), full=False)


def cell(text) -> str:
    text = text if isinstance(text, Md) else esc(str(text or "").strip())
    return str(text).strip().replace("|", "\\|").replace("\n", "<br>")


def table(head: list[str], rows: list[list]) -> list[str]:
    """A markdown table, or nothing when there are no rows (an empty table says nothing)."""
    if not rows:
        return []
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return lines + ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]


def anchor(heading: str) -> str:
    """The id GitHub and most viewers give a heading: lower case, punctuation dropped, spaces as hyphens."""
    return re.sub(r"[^\w\- ]", "", str(heading).strip().lower()).replace(" ", "-")


def has_file(item: dict) -> bool:
    """A link or edge gets its own file only when it says more than its row in a table: a condition, a loop,
    or why it exists."""
    return item.get("kind") == "cond" or bool(item.get("loop_exit")) or bool(str(item.get("intent", "")).strip())


def mlabel(text: str) -> str:
    """Text inside a Mermaid "label": entity codes for characters Mermaid would read as markup."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return "".join({"\"": "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;", "#": "#35;"}.get(c, c) for c in text)


class Paths:
    """Every file path in one place so links and file names never disagree. Paths hold numbers only (A6/,
    A6-N3.md, L20.md): renaming an agent or a step keeps every exported path and every link to it; the names
    live in the titles."""

    def __init__(self, doc: dict):
        self.doc = doc

    def agent_dir(self, a: dict) -> str:
        return a["id"]

    def agent(self, a: dict) -> str:
        return f"{self.agent_dir(a)}/README.md"

    def step(self, a: dict, s: dict) -> str:
        return f"{self.agent_dir(a)}/steps/{full(a, s['id'])}.md"

    def edge(self, a: dict, e: dict) -> str:
        return f"{self.agent_dir(a)}/edges/{full(a, e['id'])}.md"

    def link(self, link: dict) -> str:
        return f"edges/{link['id']}.md"


def path_for(doc: dict, target: str) -> str:
    """Export path of one document: project, glossary, L1, A1, A1-N1, A1-L1."""
    p = Paths(doc)
    if target in ("", "project"):
        return "README.md"
    if target == "glossary":
        return "GLOSSARY.md"
    if link := find(doc.get("links", []), target):
        return p.link(link)
    if target.startswith("L"):
        return ""
    aid, _, rest = target.partition("-")
    a = find(doc.get("agents", []), aid)
    if not a:
        return ""
    if not rest:
        return p.agent(a)
    if s := find(a.get("steps", []), rest):
        return p.step(a, s)
    if e := find(a.get("edges", []), rest):
        return p.edge(a, e)
    return ""


def rel(src: str, dst: str) -> str:
    return posixpath.relpath(dst, posixpath.dirname(src) or ".")


def md_link(text: str, src: str, dst: str, frag: str = "") -> Md:
    text = re.sub(r"\s+", " ", str(text)).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("<", "&lt;")
    return Md(f"[{text}]({rel(src, dst)}{'#' + frag if frag else ''})")


def data_link(name: str, src: str) -> Md:
    return md_link(name, src, "GLOSSARY.md", anchor(name))


def section(out: list[str], title: str, body: list[str]) -> None:
    """A titled part; skipped when it has nothing to say."""
    if any(str(x).strip() for x in body):
        out += ["", f"## {title}"] + body


def inner_edge(doc: dict, target: str) -> dict | None:
    """The inner edge a target like A1-L2 names, or None."""
    aid, _, rest = str(target).partition("-")
    a = find(doc.get("agents", []), aid)
    return find(a.get("edges", []), rest) if a and rest.startswith("L") else None


def render(doc: dict, changelog: list[dict], date: str, polished: bool, draft_errors: int = 0) -> dict[str, str]:
    """`draft_errors` > 0 marks the set as a draft exported with that many check errors."""
    p = Paths(doc)
    agents = by_id(doc.get("agents", []))
    links = by_id(doc.get("links", []))
    files = {"README.md": _project(doc, p, agents, links, date, polished, draft_errors),
             "GLOSSARY.md": _glossary(doc), "CHANGELOG.md": _changelog(changelog),
             "IMPLEMENTATION.md": _implementation(doc, p, agents, links)}
    for link in links:
        if has_file(link):
            files[p.link(link)] = _link(doc, p, link, links)
    for a in agents:
        files[p.agent(a)] = _agent(doc, p, a, links)
        for s in by_id(a.get("steps", [])):
            files[p.step(a, s)] = _step(doc, p, a, s)
        for e in by_id(a.get("edges", [])):
            if has_file(e):
                files[p.edge(a, e)] = _edge(p, a, e)
    files = {k: v.rstrip("\n") + "\n" for k, v in sorted(files.items())}
    design = {"format": FORMAT, "tool": "clonamic-create-agent", "version": VERSION, "exported": date,
              "files": sorted(files), "doc": doc}
    files["design.json"] = json.dumps(design, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return files


def _names(names: list[str], src: str) -> Md:
    return Md(", ".join(data_link(n, src) for n in names if n))


def link_ref(p, doc, x: dict, src: str) -> str:
    """A top-level link as a link to its file, or as plain text when it has none."""
    text = f"{x['id']} {link_name(doc, x)}"
    return md_link(text, src, p.link(x)) if has_file(x) else text


def edge_ref(p, a: dict, e: dict, src: str) -> str:
    text = f"{full(a, e['id'])} {edge_name(a, e)}"
    return md_link(text, src, p.edge(a, e)) if has_file(e) else text


def _shape(doc: dict, name: str) -> str:
    """One line of a data item's structure from the data dictionary: field: type, ..."""
    g = next((x for x in doc.get("glossary", []) if x.get("name") == name), None)
    fields = [f for f in (g or {}).get("fields", []) if str(f.get("name", "")).strip()]
    return ", ".join(f"{f['name'].strip()}: {str(f.get('type', '')).strip()}" + ("" if f.get("required", True) else "(선택)")
                     for f in fields)


def _io_table(doc: dict, src: str, rows: list[tuple[str, list[str]]]) -> list[str]:
    """input / output table: one row per data item with its structure."""
    body = [[kind, data_link(n, src), _shape(doc, n)] for kind, names in rows for n in names if n]
    return table(["구분", "데이터", "구조"], body)


def _agent_io(links: list[dict], aid: str) -> tuple[list[str], list[str]]:
    got = list(dict.fromkeys(n for x in links if x.get("to") == aid for n in x.get("passes", [])))
    gave = list(dict.fromkeys(n for x in links if x.get("from") == aid for n in x.get("passes", [])))
    return got, gave


def _cond_text(item: dict) -> str:
    return (item.get("condition", "") or item.get("name", "")).strip() if item.get("kind") == "cond" else "항상"


def _project(doc, p, agents, links, date, polished, draft_errors=0) -> str:
    src = "README.md"
    head = f"> {WARNING} 내보낸 날짜 {date}" + ("" if polished else " · 다듬기 미적용")
    if draft_errors:
        head += f" · 초안 · 검사 오류 {draft_errors}개"
    out = [f"# {para(doc.get('name', ''))}", head, "", para(doc.get("summary", "")), "",
           f"처음 읽는다면 이 문서 → {md_link('데이터 사전', src, 'GLOSSARY.md')} → {md_link('구현 순서', src, 'IMPLEMENTATION.md')} → "
           "에이전트 문서(A1부터) 순서로 본다. 구현은 데이터 구조 → 도구 → 단계 순서로 한다."]
    need = [f"- 요구사항: {para(doc.get('want', ''))}"]
    if doc.get("background", "").strip():
        need.append(f"- 배경: {para(doc['background'])}")
    need.append("- 성공 기준:")
    need += [f"  - {para(x)}" for x in doc.get("success", []) if x.strip()]
    section(out, "요구사항", need)
    rows = [["input", data_link(r.get("item", ""), src) if r.get("item") else "", r.get("desc"), _shape(doc, r.get("item", ""))]
            for r in doc.get("inputs", [])]
    rows += [["output", data_link(r.get("item", ""), src) if r.get("item") else "", r.get("desc"), _shape(doc, r.get("item", ""))]
             for r in doc.get("outputs", [])]
    section(out, "input / output", table(["구분", "데이터", "설명", "구조"], rows))
    scope = []
    if doc.get("not_doing", "").strip():
        scope.append(f"- 범위 밖: {para(doc['not_doing'])}")
    if [x for x in doc.get("constraints", []) if x.strip()]:
        scope.append("- 제약:")
        scope += [f"  - {para(x)}" for x in doc["constraints"] if x.strip()]
    if scope:
        section(out, "범위와 제약", scope)
    section(out, "전체 흐름", ["```mermaid", *_agent_mermaid(doc, agents, links), "```"])
    section(out, "에이전트", table(["번호", "이름", "역할", "input", "output"],
                                [[md_link(a["id"], src, p.agent(a)), a.get("name"), a.get("role"),
                                  *(_names(x, src) for x in _agent_io(links, a["id"]))] for a in agents]))
    section(out, "연결", table(["번호", "출발 → 도착", "조건", "전달 데이터"],
                             [[md_link(x["id"], src, p.link(x)) if has_file(x) else x["id"], _link_route(doc, x), _cond_text(x),
                               _names(x.get("passes", []), src)] for x in links]))
    users = tool_users(doc)
    section(out, "도구", table(["번호", "종류", "이름", "용도", "위치·접속", "쓰는 곳", "대안"],
                             [[t.get("id"), t.get("kind"), tool_name(doc, t), t.get("purpose"), t.get("location"),
                               ", ".join(users.get(t.get("id"), [])), t.get("alternative")] for t in doc.get("tools", [])]))
    if doc.get("human_points"):
        section(out, "사람 확인 지점", table(["지점", "사람이 하는 일", "그동안 흐름"],
                                       [[r.get("point"), r.get("does"), r.get("meanwhile")] for r in doc["human_points"]]))
    section(out, "검증 시나리오", table(["시나리오", "input", "경로", "기대 결과", "확인하는 성공 기준"],
                                  [[r.get("name"), r.get("input"), r.get("path"), r.get("expected"), r.get("criteria")]
                                   for r in doc.get("scenarios", [])]))
    if doc.get("decisions"):
        section(out, "설계 결정", table(["결정", "이유", "버린 대안"],
                                    [[r.get("decision"), r.get("why"), r.get("rejected")] for r in doc["decisions"]]))
    if [x for x in doc.get("open", []) if x.strip()]:
        section(out, "미결 사항", [f"- [ ] {para(x)}" for x in doc["open"] if x.strip()])
    return "\n".join(out)


def _end(doc, ref: str) -> str:
    return agent_name(doc, ref) if ref in (START, END) else f"{ref} {agent_name(doc, ref)}"


def _link_route(doc, link) -> str:
    return f"{_end(doc, link.get('from', ''))} → {_end(doc, link.get('to', ''))}"


def _agent_mermaid(doc, agents, links) -> list[str]:
    out = ["flowchart LR", "  S([시작])"]
    out += [f'  {a["id"]}["{mlabel(a["id"] + " " + a.get("name", ""))}"]' for a in agents]
    out.append("  E((끝))")
    ids = {START: "S", END: "E"}
    for x in links:
        label = x["id"] + (f": {link_name(doc, x)}" if x.get("kind") == "cond" else "")
        out.append(f'  {ids.get(x.get("from"), x.get("from"))} -- "{mlabel(label)}" --> {ids.get(x.get("to"), x.get("to"))}')
    return out


def _inner_mermaid(a: dict) -> list[str]:
    out = ["flowchart LR", "  S([시작])"]
    out += [f'  {s["id"]}["{mlabel(s["id"] + " " + s.get("name", ""))}"]' for s in by_id(a.get("steps", []))]
    out.append("  E((끝))")
    ids = {START: "S", END: "E"}
    for e in by_id(a.get("edges", [])):
        label = e["id"] + (f": {edge_name(a, e)}" if e.get("kind") == "cond" else "")
        out.append(f'  {ids.get(e.get("from"), e.get("from"))} -- "{mlabel(label)}" --> {ids.get(e.get("to"), e.get("to"))}')
    return out


def _agent(doc, p, a, links) -> str:
    src = p.agent(a)
    out = [f"# {a['id']} · {para(a.get('name', ''))}", para(a.get("role", ""))]
    section(out, "필요한 이유", [para(a.get("intent", ""))])
    if a.get("not_doing", "").strip():
        section(out, "범위 밖", [para(a["not_doing"])])
    got, gave = _agent_io(links, a["id"])
    section(out, "input / output", _io_table(doc, src, [("input", got), ("output", gave)]))
    incoming = [x for x in links if x.get("to") == a["id"]]
    outgoing = [x for x in links if x.get("from") == a["id"]]
    section(out, "들어오는 연결", table(["연결", "출발", "전달 데이터"],
                                  [[link_ref(p, doc, x, src), _end(doc, x.get("from", "")),
                                    _names(x.get("passes", []), src)] for x in incoming]))
    section(out, "다음 연결", table(["연결", "도착", "조건", "전달 데이터"],
                                [[link_ref(p, doc, x, src), _end(doc, x.get("to", "")),
                                  _cond_text(x), _names(x.get("passes", []), src)] for x in outgoing]))
    section(out, "내부 흐름", ["```mermaid", *_inner_mermaid(a), "```"])
    steps = by_id(a.get("steps", []))
    order = flow_order([s["id"] for s in steps], [(e.get("from", ""), e.get("to", "")) for e in a.get("edges", [])])
    section(out, "단계", table(["번호", "이름", "유형", "요약"],  # in the order the flow reaches them
                             [[md_link(full(a, s["id"]), src, p.step(a, s)), s.get("name"), s.get("type"), s.get("summary")]
                              for s in (find(steps, sid) for sid in order)]))
    section(out, "연결", table(["번호", "출발 → 도착", "조건"],
                             [[md_link(full(a, e["id"]), src, p.edge(a, e)) if has_file(e) else full(a, e["id"]),
                               f"{node_name(a, e.get('from', ''))} → {node_name(a, e.get('to', ''))}", _cond_text(e)]
                              for e in by_id(a.get("edges", []))]))
    users = tool_users(doc)
    used = [t for t in doc.get("tools", []) if any(u.startswith(f"{a['id']}-") for u in users.get(t.get("id"), []))]
    if used:
        section(out, "도구", table(["번호", "종류", "이름", "쓰는 단계"],
                                 [[t["id"], t.get("kind"), tool_name(doc, t),
                                   ", ".join(u for u in users[t["id"]] if u.startswith(f"{a['id']}-"))] for t in used]))
    _fixed(out, a)
    if a.get("paths", "").strip():
        section(out, "정상·예외 흐름", [para(a["paths"])])
    if a.get("notes", "").strip():
        section(out, "공통 제약", [para(a["notes"])])
    return "\n".join(out)


def _fixed(out: list[str], obj: dict) -> None:
    for key, title in (("fixed", "지켜야 할 것"), ("discretion", "구현자가 정할 것")):
        if obj.get(key, "").strip():
            section(out, title, [para(obj[key])])


def _node_link(p, a, ref: str, src: str) -> str:
    step = find(a.get("steps", []), ref)
    if step:
        return md_link(f"{full(a, ref)} {step.get('name', '')}", src, p.step(a, step))
    return node_name(a, ref)


def tool_users(doc: dict) -> dict[str, list[str]]:
    """Tool id -> step ids (A1-N2) that use it directly or in one of their process items."""
    users: dict[str, list[str]] = {}
    for a in by_id(doc.get("agents", [])):
        for s in by_id(a.get("steps", [])):
            refs = list(s.get("tools", [])) + [x.get("tool") for x in s.get("process", []) if x.get("tool")]
            for r in dict.fromkeys(refs):
                users.setdefault(r, []).append(full(a, s["id"]))
    return users


def _tool_label(doc: dict, tid: str) -> str:
    t = find(doc.get("tools", []), tid)
    return f"{tid} {tool_name(doc, t)}" if t else tid


def _step(doc, p, a, s) -> str:
    src = p.step(a, s)
    out = [f"# {full(a, s['id'])} · {para(s.get('name', ''))}",
           f"`{s.get('type', '')}` · 소속 {md_link(a['id'] + ' ' + a.get('name', ''), src, p.agent(a))}",
           para(s.get("summary", ""))]
    section(out, "필요한 이유", [para(s.get("intent", ""))])
    section(out, "input / output", _io_table(doc, src, [("input", s.get("inputs", [])), ("output", s.get("outputs", []))]))
    steps = [x for x in s.get("process", []) if str(x.get("name", "")).strip()]
    # One item per row: a head line (unit, name, input → output, tool), then the procedure lines of `does` under it.
    rows = []
    for i, x in enumerate(steps, 1):
        unit = f"`{x['unit']}` " if x.get("unit") else ""
        io = f" — {para(x.get('input', ''))} → {para(x.get('output', ''))}" if x.get("input") or x.get("output") else ""
        tool = f" · 도구 {_tool_label(doc, x['tool'])}" if x.get("tool") else ""
        rows.append(f"{i}. {unit}**{para(x['name'])}**{io}{tool}")
        rows += [f"   - {para(line.strip().removeprefix('- '))}" for line in str(x.get("does", "")).splitlines() if line.strip()]
    section(out, "과정", rows)
    if [x for x in s.get("criteria", []) if x.strip()]:
        section(out, "판단 기준", [f"- {para(x)}" for x in s["criteria"] if x.strip()])
    if s.get("prompt", "").strip():
        section(out, "AI 지시", [para(s["prompt"])])
    if s.get("tools"):
        section(out, "도구", [f"- {_tool_label(doc, t)}" for t in s["tools"]])
    section(out, "완료 기준", [f"- [ ] {para(x)}" for x in s.get("done", []) if x.strip()])
    nxt = [e for e in by_id(a.get("edges", [])) if e.get("from") == s["id"]]
    section(out, "다음 연결", table(["연결", "도착", "조건", "전달 데이터"],
                                [[edge_ref(p, a, e, src), _node_link(p, a, e.get("to", ""), src), _cond_text(e),
                                  _names(e.get("passes", []), src)] for e in nxt]))
    for key, title in (("example", "예시"), ("on_fail", "실패 처리")):
        if s.get(key, "").strip():
            section(out, title, [para(s[key])])
    _fixed(out, s)
    if s.get("cautions", "").strip():
        section(out, "주의점", [para(s["cautions"])])
    return "\n".join(out)


def _condition(out, item, siblings, link_to, loop_target) -> None:
    rows = []
    if item.get("kind") == "cond":
        rows += [["조건", item.get("condition", "").strip()], ["판단 방식", item.get("judge", "")]]
    if item.get("loop_exit") and loop_target:
        rows += [["최대 반복 횟수", str(item.get("loop_limit", "")).strip()], ["한도 초과 시", loop_target]]
    others = [x for x in siblings if x["id"] != item["id"]]
    if item.get("kind") == "cond" and others:
        rows.append(["같은 출발의 다른 연결", ", ".join(f"{link_to(x)} ({_cond_text(x)})" for x in others)])
    if rows:
        section(out, "조건", table(["항목", "내용"], rows))
    if item.get("intent", "").strip():
        section(out, "필요한 이유", [para(item["intent"])])


def _edge(p, a, e) -> str:
    src = p.edge(a, e)
    out = [f"# {full(a, e['id'])} · {node_name(a, e.get('from', ''))} → {node_name(a, e.get('to', ''))}", ""]
    out += table(["출발", "도착", "종류"], [[_node_link(p, a, e.get("from", ""), src), _node_link(p, a, e.get("to", ""), src),
                                         EDGE_KINDS.get(e.get("kind"), "")]])
    siblings = [x for x in by_id(a.get("edges", [])) if x.get("from") == e.get("from")]
    target = find(a.get("edges", []), e.get("loop_exit", ""))

    def link_to(x: dict) -> str:
        return edge_ref(p, a, x, src)

    _condition(out, e, siblings, link_to, link_to(target) if target else "")
    section(out, "전달 데이터", [f"- {data_link(n, src)}" for n in e.get("passes", []) if n])
    return "\n".join(out)


def _link(doc, p, link, links) -> str:
    src = p.link(link)

    def end(ref: str) -> str:
        a = find(doc.get("agents", []), ref)
        return md_link(f"{ref} {a.get('name', '')}", src, p.agent(a)) if a else agent_name(doc, ref)

    out = [f"# {link['id']} · {agent_name(doc, link.get('from', ''))} → {agent_name(doc, link.get('to', ''))}", ""]
    out += table(["출발", "도착", "종류"], [[end(link.get("from", "")), end(link.get("to", "")), EDGE_KINDS.get(link.get("kind"), "")]])
    siblings = [x for x in links if x.get("from") == link.get("from")]
    target = find(links, link.get("loop_exit", ""))

    def link_to(x: dict) -> str:
        return link_ref(p, doc, x, src)

    _condition(out, link, siblings, link_to, link_to(target) if target else "")
    section(out, "전달 데이터", [f"- {data_link(n, src)}" for n in link.get("passes", []) if n])
    return "\n".join(out)


def _glossary(doc) -> str:
    use = usage(doc)
    inputs = {r.get("item") for r in doc.get("inputs", [])}
    out = ["# 데이터 사전", ""]
    rows = []
    for g in doc.get("glossary", []):
        name = g.get("name", "")
        made = use.get(name, {}).get("made", [])
        first = "프로젝트 input" if name in inputs else (made[0] if made else "")
        used = list(dict.fromkeys(use.get(name, {}).get("used", [])))
        rows.append([name, g.get("meaning"), first, ", ".join(used)])
    out += table(["이름", "뜻", "처음 생기는 곳", "쓰이는 곳"], rows)
    for g in doc.get("glossary", []):
        fields = [f for f in g.get("fields", []) if str(f.get("name", "")).strip()]
        section(out, g.get("name", ""), [para(g.get("meaning", "")), *([""] + [para(g["contents"])] if g.get("contents", "").strip() else []), "",
                                         *table(["필드", "형식", "필수", "설명", "예"],
                                                [[f.get("name"), f.get("type"), "예" if f.get("required", True) else "아니오",
                                                  f.get("desc"), f.get("example")] for f in fields])])
    return "\n".join(out)


def flow_order(nodes: list[str], pairs: list[tuple[str, str]]) -> list[str]:
    """Nodes in the order the flow reaches them from start (breadth first, links back to earlier nodes ignored);
    nodes the flow never reaches come last in id order."""
    order, seen, todo = [], {START}, [START]
    while todo:
        node = todo.pop(0)
        for u, v in pairs:
            if u == node and v not in seen and v in nodes:
                seen.add(v)
                order.append(v)
                todo.append(v)
    return order + [n for n in nodes if n not in seen]


def _implementation(doc, p, agents, links) -> str:
    """One page that tells an implementer where to start and in which order to build and test."""
    src = "IMPLEMENTATION.md"
    out = ["# 구현 순서", "", "위에서 아래로 만든다. 단계마다 예시를 첫 테스트로 쓰고, 완료 기준을 통과하면 다음으로 간다."]
    n = iter(range(1, 10))
    if [x for x in doc.get("open", []) if x.strip()]:  # what must be settled comes before any building
        section(out, f"{next(n)}. 구현 전에 정할 것", [f"- [ ] {para(x)}" for x in doc["open"] if x.strip()])
    data = [g for g in doc.get("glossary", []) if g.get("name")]
    section(out, f"{next(n)}. 데이터 구조", table(["데이터", "구조"], [[data_link(g["name"], src), _shape(doc, g["name"])] for g in data]))
    section(out, f"{next(n)}. 도구 준비", table(["번호", "종류", "이름", "위치·접속"],
                                    [[t.get("id"), t.get("kind"), tool_name(doc, t), t.get("location")] for t in doc.get("tools", [])]))
    order = flow_order([a["id"] for a in agents], [(x.get("from", ""), x.get("to", "")) for x in links])
    body, part = [], next(n)
    for k, aid in enumerate(order, 1):
        a = find(agents, aid)
        steps = flow_order([s["id"] for s in a.get("steps", [])], [(e.get("from", ""), e.get("to", "")) for e in a.get("edges", [])])
        body += ["", f"### {part}.{k} {md_link(a['id'] + ' ' + a.get('name', ''), src, p.agent(a))}", ""]
        body += table(["순서", "단계", "유형", "input → output", "첫 테스트(예시)", "완료 기준"],
                      [[i, md_link(f"{full(a, sid)} {s.get('name', '')}", src, p.step(a, s)), s.get("type"),
                        f"{', '.join(s.get('inputs', []))} → {', '.join(s.get('outputs', []))}", s.get("example"),
                        "; ".join(x for x in s.get("done", []) if x.strip())]
                       for i, sid in enumerate(steps, 1) for s in [find(a.get("steps", []), sid)]])
    section(out, f"{part}. 에이전트와 단계", body[1:])
    if doc.get("scenarios"):
        section(out, f"{next(n)}. 전체 검증", [f"{md_link('README의 검증 시나리오', src, 'README.md', anchor('검증 시나리오'))}를 "
                                             "모두 통과하면 끝난다. 시나리오마다 input을 넣고 경로와 기대 결과를 확인한다."])
    return "\n".join(out)


def _changelog(rows: list[dict]) -> str:
    ordered = sorted(rows, key=lambda r: (r.get("date", ""), r.get("id", 0)), reverse=True)
    return "\n".join(["# 변경 이력", "", *table(["날짜", "무엇을", "왜", "영향"],
                                             [[r.get("date"), r.get("what"), r.get("why"), r.get("affected")] for r in ordered])])
