"""Render a design document into the export file set. Same input -> byte-identical output."""

from __future__ import annotations

import json
import posixpath
import re

from checks import usage
from graph import END, EXIT, START, agent_name, by_id, edge_name, find, full, link_name, node_name
from schema import EDGE_KINDS, FORMAT

WARNING = "도구가 생성한 문서입니다. 수정은 편집기에서 하세요."


def slug(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|#\[\]()]', "", text or "").strip()
    return re.sub(r"\s+", "_", text) or "이름없음"


def cell(text) -> str:
    return str(text or "").strip().replace("|", "\\|").replace("\n", "<br>")


def table(head: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return lines + ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]


def mlabel(text: str) -> str:
    return str(text).replace('"', "'").replace("\n", " ")


class Paths:
    """Every file path in one place so links and file names never disagree."""

    def __init__(self, doc: dict):
        self.doc = doc

    def agent_dir(self, a: dict) -> str:
        return f"{a['id']}_{slug(a.get('name', ''))}"

    def agent(self, a: dict) -> str:
        return f"{self.agent_dir(a)}/README.md"

    def step(self, a: dict, s: dict) -> str:
        return f"{self.agent_dir(a)}/steps/{full(a, s['id'])}_{slug(s.get('name', ''))}.md"

    def edge(self, a: dict, e: dict) -> str:
        return f"{self.agent_dir(a)}/edges/{full(a, e['id'])}_{slug(edge_name(a, e))}.md"

    def link(self, link: dict) -> str:
        return f"edges/{link['id']}_{slug(link_name(self.doc, link))}.md"


def path_for(doc: dict, target: str) -> str:
    """Export path of one document: project, glossary, L1, A1, A1-N1, A1-L1."""
    p = Paths(doc)
    if target in ("", "project"):
        return "README.md"
    if target == "glossary":
        return "GLOSSARY.md"
    if link := find(doc.get("links", []), target):
        return p.link(link)
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


def md_link(text: str, src: str, dst: str) -> str:
    return f"[{text}]({rel(src, dst)})"


def section(out: list[str], title: str, body: list[str]) -> None:
    out += ["", f"## {title}"] + body


def render(doc: dict, changelog: list[dict], date: str, polished: bool) -> dict[str, str]:
    p = Paths(doc)
    agents = by_id(doc.get("agents", []))
    links = by_id(doc.get("links", []))
    files = {"README.md": _project(doc, p, agents, links, date, polished),
             "GLOSSARY.md": _glossary(doc), "CHANGELOG.md": _changelog(changelog)}
    for link in links:
        files[p.link(link)] = _link(doc, p, link, links)
    for a in agents:
        files[p.agent(a)] = _agent(doc, p, a, links)
        for s in by_id(a.get("steps", [])):
            files[p.step(a, s)] = _step(p, a, s)
        for e in by_id(a.get("edges", [])):
            files[p.edge(a, e)] = _edge(p, a, e)
    files = {k: v.rstrip("\n") + "\n" for k, v in sorted(files.items())}
    design = {"format": FORMAT, "tool": "clonamic-create-agent", "exported": date,
              "files": sorted(files), "doc": doc}
    files["design.json"] = json.dumps(design, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return files


def _names(names: list[str], src: str) -> str:
    return ", ".join(md_link(n, src, "GLOSSARY.md") for n in names if n)


def _project(doc, p, agents, links, date, polished) -> str:
    src = "README.md"
    head = f"> {WARNING} · 내보낸 날짜 {date}" + ("" if polished else " · 다듬기 미적용")
    out = [f"# {doc.get('name', '')}", head, "", doc.get("summary", "")]
    intent = [f"- 원하는 것: {doc.get('want', '').strip()}"]
    if doc.get("background", "").strip():
        intent.append(f"- 배경: {doc['background'].strip()}")
    intent.append("- 성공 기준:")
    intent += [f"  - {x}" for x in doc.get("success", []) if x.strip()]
    section(out, "의도", intent)
    rows = [["받는 것", r.get("item"), r.get("desc")] for r in doc.get("inputs", [])]
    rows += [["내놓는 것", r.get("item"), r.get("desc")] for r in doc.get("outputs", [])]
    section(out, "받는 것 / 내놓는 것", table(["구분", "항목", "설명"], rows))
    scope = []
    if doc.get("not_doing", "").strip():
        scope.append(f"- 하지 않는 것: {doc['not_doing'].strip()}")
    if [x for x in doc.get("constraints", []) if x.strip()]:
        scope.append("- 제약:")
        scope += [f"  - {x}" for x in doc["constraints"] if x.strip()]
    if scope:
        section(out, "범위와 제약", scope)
    section(out, "전체 흐름", ["```mermaid", *_agent_mermaid(doc, agents, links), "```"])
    section(out, "에이전트", table(["번호", "이름", "역할"],
                                [[md_link(a["id"], src, p.agent(a)), a.get("name"), a.get("role")] for a in agents]))
    section(out, "연결", table(["번호", "출발 → 도착", "종류", "조건 요약"],
                             [[md_link(x["id"], src, p.link(x)), _link_route(doc, x), EDGE_KINDS.get(x.get("kind"), ""),
                               link_name(doc, x) if x.get("kind") == "cond" else (x.get("exit") or "항상")] for x in links]))
    section(out, "도구", table(["필요한 능력", "쓰는 곳", "추천 도구", "대안"],
                             [[r.get("capability"), r.get("used_in"), r.get("recommended"), r.get("alternative")]
                              for r in doc.get("tools", [])]))
    if doc.get("human_points"):
        section(out, "사람 개입 지점", table(["지점", "사람이 하는 일", "그동안 흐름은"],
                                       [[r.get("point"), r.get("does"), r.get("meanwhile")] for r in doc["human_points"]]))
    section(out, "검증 시나리오", table(["시나리오", "입력", "거치는 경로", "기대 결과"],
                                  [[r.get("name"), r.get("input"), r.get("path"), r.get("expected")]
                                   for r in doc.get("scenarios", [])]))
    if doc.get("decisions"):
        section(out, "설계 결정", table(["결정", "이유", "버린 대안"],
                                    [[r.get("decision"), r.get("why"), r.get("rejected")] for r in doc["decisions"]]))
    if [x for x in doc.get("open", []) if x.strip()]:
        section(out, "미결 사항", [f"- [ ] {x}" for x in doc["open"] if x.strip()])
    return "\n".join(out)


def _link_route(doc, link) -> str:
    start = agent_name(doc, link.get("from", ""))
    if link.get("from") not in (START, END) and link.get("exit"):
        start = f"{link['from']} {start} 출구「{link['exit']}」"
    end = agent_name(doc, link.get("to", ""))
    if link.get("to") not in (START, END):
        end = f"{link['to']} {end}"
    return f"{start} → {end}"


def _agent_mermaid(doc, agents, links) -> list[str]:
    out = ["flowchart TD", "  S([시작])"]
    out += [f'  {a["id"]}["{mlabel(a["id"] + " " + a.get("name", ""))}"]' for a in agents]
    out.append("  E((끝))")
    ids = {START: "S", END: "E"}
    for x in links:
        label = x["id"] + (f": {link_name(doc, x)}" if x.get("kind") == "cond" or x.get("exit") else "")
        out.append(f'  {ids.get(x.get("from"), x.get("from"))} -- "{mlabel(label)}" --> {ids.get(x.get("to"), x.get("to"))}')
    return out


def _inner_mermaid(a: dict) -> list[str]:
    exits = {EXIT + x.get("name", ""): f"X{i + 1}" for i, x in enumerate(a.get("exits", []))}
    out = ["flowchart TD", "  S([시작])"]
    out += [f'  {s["id"]}["{mlabel(s["id"] + " " + s.get("name", ""))}"]' for s in by_id(a.get("steps", []))]
    out += [f'  {mid}(("{mlabel(ref[len(EXIT):])}"))' for ref, mid in exits.items()]
    ids = {START: "S", **exits}
    for e in by_id(a.get("edges", [])):
        label = e["id"] + (f": {edge_name(a, e)}" if e.get("kind") == "cond" else "")
        out.append(f'  {ids.get(e.get("from"), e.get("from"))} -- "{mlabel(label)}" --> {ids.get(e.get("to"), e.get("to"))}')
    return out


def _agent(doc, p, a, links) -> str:
    src = p.agent(a)
    out = [f"# {a['id']} · {a.get('name', '')}", a.get("role", "")]
    section(out, "의도", [a.get("intent", "")])
    if a.get("not_doing", "").strip():
        section(out, "맡지 않는 것", [a["not_doing"]])
    incoming = [x for x in links if x.get("to") == a["id"]]
    outgoing = [x for x in links if x.get("from") == a["id"]]
    got = list(dict.fromkeys(n for x in incoming for n in x.get("passes", [])))
    gave = list(dict.fromkeys(n for x in outgoing for n in x.get("passes", [])))
    body = table(["구분", "항목"], [["받는 것", _names(got, src)], ["내놓는 것", _names(gave, src)]])
    if incoming:
        body += ["", "들어오는 연결: " + ", ".join(md_link(f"{x['id']} {link_name(doc, x)}", src, p.link(x)) for x in incoming)]
    section(out, "주고받는 것", body)
    rows = []
    for x in a.get("exits", []):
        link = next((y for y in outgoing if y.get("exit") == x.get("name")), None)
        rows.append([x.get("name"), x.get("when"), md_link(f"{link['id']} {link_name(doc, link)}", src, p.link(link)) if link else ""])
    section(out, "출구", table(["출구", "언제", "이어지는 연결"], rows))
    section(out, "내부 흐름", ["```mermaid", *_inner_mermaid(a), "```"])
    section(out, "단계", table(["번호", "이름", "유형", "하는 일 한 줄"],
                             [[md_link(full(a, s["id"]), src, p.step(a, s)), s.get("name"), s.get("type"), s.get("summary")]
                              for s in by_id(a.get("steps", []))]))
    section(out, "연결", table(["번호", "출발 → 도착", "종류", "조건 요약"],
                             [[md_link(full(a, e["id"]), src, p.edge(a, e)),
                               f"{node_name(a, e.get('from', ''))} → {node_name(a, e.get('to', ''))}",
                               EDGE_KINDS.get(e.get("kind"), ""), edge_name(a, e) if e.get("kind") == "cond" else "항상"]
                              for e in by_id(a.get("edges", []))]))
    if a.get("tools"):
        section(out, "도구", table(["필요한 능력", "쓰는 단계"], [[r.get("capability"), r.get("used_in")] for r in a["tools"]]))
    _fixed(out, a)
    if a.get("paths", "").strip():
        section(out, "주요 경로", [a["paths"]])
    if a.get("notes", "").strip():
        section(out, "공통 주의점", [a["notes"]])
    return "\n".join(out)


def _fixed(out: list[str], obj: dict) -> None:
    body = [f"- {label}: {obj[key].strip()}" for key, label in (("fixed", "고정"), ("discretion", "재량"))
            if obj.get(key, "").strip()]
    if body:
        section(out, "고정과 재량", body)


def _node_link(p, a, ref: str, src: str) -> str:
    step = find(a.get("steps", []), ref)
    if step:
        return md_link(f"{full(a, ref)} {step.get('name', '')}", src, p.step(a, step))
    if ref.startswith(EXIT):
        return f"출구「{ref[len(EXIT):]}」"
    return node_name(a, ref)


def _step(p, a, s) -> str:
    src = p.step(a, s)
    out = [f"# {full(a, s['id'])} · {s.get('name', '')}",
           f"`{s.get('type', '')}` · 소속 {md_link(a['id'] + ' ' + a.get('name', ''), src, p.agent(a))}",
           s.get("summary", "")]
    section(out, "의도", [s.get("intent", "")])
    section(out, "하는 일", [f"{i}. {x}" for i, x in enumerate([x for x in s.get("does", []) if x.strip()], 1)])
    section(out, "받는 것 / 내놓는 것", table(["구분", "항목"], [["받는 것", _names(s.get("inputs", []), src)],
                                                         ["내놓는 것", _names(s.get("outputs", []), src)]]))
    if s.get("tools"):
        section(out, "도구", table(["필요한 능력", "용도", "추천 도구"],
                                 [[r.get("capability"), r.get("purpose"), r.get("recommended")] for r in s["tools"]]))
    section(out, "완료 기준", [f"- [ ] {x}" for x in s.get("done", []) if x.strip()])
    nxt = [e for e in by_id(a.get("edges", [])) if e.get("from") == s["id"]]
    section(out, "다음 연결", table(["연결", "조건 요약"],
                                [[md_link(f"{full(a, e['id'])} {edge_name(a, e)}", src, p.edge(a, e)),
                                  edge_name(a, e) if e.get("kind") == "cond" else "항상"] for e in nxt]))
    _fixed(out, s)
    for key, title in (("example", "예시"), ("cautions", "주의점"), ("on_fail", "실패 시")):
        if s.get(key, "").strip():
            section(out, title, [s[key].strip()])
    return "\n".join(out)


def _condition(out, item, siblings, link_to, loop_target) -> None:
    body = []
    if item.get("kind") == "cond":
        body += [item.get("condition", "").strip(), f"판단: {item.get('judge', '')}"]
    if item.get("loop_exit") and loop_target:
        body.append(f"이 되돌림이 {str(item.get('loop_limit', '')).strip()}번째면 대신 {loop_target}로 간다.")
    others = [x for x in siblings if x["id"] != item["id"]]
    if item.get("kind") == "cond" and others:
        body.append("같은 출발의 다른 연결: " + ", ".join(f"{link_to(x)} ({x.get('name', '') or '항상'})" for x in others))
    if body:
        section(out, "조건", [line for b in body for line in (b, "")][:-1])
    if item.get("kind") == "cond" and item.get("intent", "").strip():
        section(out, "의도", [item["intent"].strip()])


def _edge(p, a, e) -> str:
    src = p.edge(a, e)
    out = [f"# {full(a, e['id'])} · {node_name(a, e.get('from', ''))} → {node_name(a, e.get('to', ''))}", ""]
    out += table(["출발", "도착", "종류"], [[_node_link(p, a, e.get("from", ""), src), _node_link(p, a, e.get("to", ""), src),
                                         EDGE_KINDS.get(e.get("kind"), "")]])
    siblings = [x for x in by_id(a.get("edges", [])) if x.get("from") == e.get("from")]
    target = find(a.get("edges", []), e.get("loop_exit", ""))

    def link_to(x: dict) -> str:
        return md_link(f"{full(a, x['id'])} {edge_name(a, x)}", src, p.edge(a, x))

    _condition(out, e, siblings, link_to, link_to(target) if target else "")
    section(out, "넘기는 것", [f"- {md_link(n, src, 'GLOSSARY.md')}" for n in e.get("passes", []) if n])
    return "\n".join(out)


def _link(doc, p, link, links) -> str:
    src = p.link(link)

    def end(ref: str) -> str:
        a = find(doc.get("agents", []), ref)
        return md_link(f"{ref} {a.get('name', '')}", src, p.agent(a)) if a else agent_name(doc, ref)

    start = end(link.get("from", "")) + (f" 출구「{link['exit']}」" if link.get("exit") else "")
    out = [f"# {link['id']} · {agent_name(doc, link.get('from', ''))} → {agent_name(doc, link.get('to', ''))}", ""]
    out += table(["출발", "도착", "종류"], [[start, end(link.get("to", "")), EDGE_KINDS.get(link.get("kind"), "")]])
    siblings = [x for x in links if x.get("from") == link.get("from") and x.get("exit") == link.get("exit")]
    target = find(links, link.get("loop_exit", ""))

    def link_to(x: dict) -> str:
        return md_link(f"{x['id']} {link_name(doc, x)}", src, p.link(x))

    _condition(out, link, siblings, link_to, link_to(target) if target else "")
    section(out, "넘기는 것", [f"- {md_link(n, src, 'GLOSSARY.md')}" for n in link.get("passes", []) if n])
    return "\n".join(out)


def _glossary(doc) -> str:
    use = usage(doc)
    inputs = {r.get("item") for r in doc.get("inputs", [])}
    rows = []
    for g in doc.get("glossary", []):
        name = g.get("name", "")
        made = use.get(name, {}).get("made", [])
        first = "프로젝트 입력" if name in inputs else (made[0] if made else "")
        used = list(dict.fromkeys(use.get(name, {}).get("used", [])))
        rows.append([name, g.get("meaning"), g.get("contents"), first, ", ".join(used)])
    return "\n".join(["# 용어 사전", "", *table(["이름", "뜻", "담기는 내용", "처음 생기는 곳", "쓰이는 곳"], rows)])


def _changelog(rows: list[dict]) -> str:
    ordered = sorted(rows, key=lambda r: (r.get("date", ""), r.get("id", 0)), reverse=True)
    return "\n".join(["# 변경 이력", "", *table(["날짜", "무엇을", "왜", "영향"],
                                             [[r.get("date"), r.get("what"), r.get("why"), r.get("affected")] for r in ordered])])
