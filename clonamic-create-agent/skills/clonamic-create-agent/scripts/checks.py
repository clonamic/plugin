"""Pre-export checks. Each issue: {"code", "target", "message"}; an empty list means the design may be exported."""

from __future__ import annotations

from collections import defaultdict

import schema
from graph import END, EXIT, START, back_pairs, by_id, full, reachable


def run(doc: dict) -> list[dict]:
    issues: list[dict] = []

    def add(code: str, target: str, message: str) -> None:
        issues.append({"code": code, "target": target, "message": message})

    agents = by_id(doc.get("agents", []))
    links = by_id(doc.get("links", []))
    _required(doc, agents, links, add)
    _references(agents, links, add)
    _flow(doc, agents, links, add)
    _branches(agents, links, add)
    _exits(agents, links, add)
    _loops(agents, links, add)
    _data(doc, agents, links, add)
    _glossary(doc, agents, links, add)
    return issues


def _required(doc, agents, links, add) -> None:
    if fields := schema.missing("project", doc):
        add("required", "project", "프로젝트의 필수 항목이 비었습니다: " + ", ".join(fields))
    for a in agents:
        if fields := schema.missing("agent", a):
            add("required", a["id"], f"{a['id']}의 필수 항목이 비었습니다: " + ", ".join(fields))
        for s in a.get("steps", []):
            if fields := schema.missing("step", s):
                add("required", full(a, s["id"]), f"{full(a, s['id'])}의 필수 항목이 비었습니다: " + ", ".join(fields))
        for e in a.get("edges", []):
            if fields := schema.missing("edge", e):
                add("required", full(a, e["id"]), f"{full(a, e['id'])}의 필수 항목이 비었습니다: " + ", ".join(fields))
    for link in links:
        if fields := schema.missing("link", link):
            add("required", link["id"], f"{link['id']}의 필수 항목이 비었습니다: " + ", ".join(fields))


def _references(agents, links, add) -> None:
    agent_ids = {a["id"] for a in agents}
    for link in links:
        if link.get("from") not in agent_ids | {START}:
            add("reference", link["id"], f"{link['id']}의 출발 에이전트가 없습니다.")
        if link.get("to") not in agent_ids | {END}:
            add("reference", link["id"], f"{link['id']}의 도착 에이전트가 없습니다.")
    for a in agents:
        nodes = _agent_nodes(a)
        for e in a.get("edges", []):
            for side in ("from", "to"):
                if e.get(side) not in nodes:
                    add("reference", full(a, e["id"]), f"{full(a, e['id'])}의 {'출발' if side == 'from' else '도착'}이 없습니다.")


def _agent_nodes(a: dict) -> set[str]:
    return {START} | {s["id"] for s in a.get("steps", [])} | {EXIT + x.get("name", "") for x in a.get("exits", [])}


def _pairs(edges: list[dict]) -> list[tuple[str, str]]:
    return [(e.get("from", ""), e.get("to", "")) for e in edges]


def _flow(doc, agents, links, add) -> None:
    if not agents:
        add("flow", "project", "에이전트가 없습니다.")
        return
    seen = reachable(START, _pairs(links))
    for a in agents:
        if a["id"] not in seen:
            add("flow", a["id"], f"{a['id']} {a.get('name', '')}에 시작에서 닿을 수 없습니다.")
    if END not in seen:
        add("flow", "project", "끝으로 가는 에이전트 연결이 없습니다.")
    for a in agents:
        steps = a.get("steps", [])
        if not steps:
            add("flow", a["id"], f"{a['id']}에 단계가 없습니다.")
            continue
        edges = a.get("edges", [])
        inside = reachable(START, _pairs(edges))
        for s in by_id(steps):
            target = full(a, s["id"])
            if s["id"] not in inside:
                add("flow", target, f"{target} {s.get('name', '')}에 시작에서 닿을 수 없습니다.")
            if not any(e.get("from") == s["id"] for e in edges):
                add("flow", target, f"{target} {s.get('name', '')}은(는) 나가는 연결이 없는 막다른 단계입니다.")
        for x in a.get("exits", []):
            if EXIT + x.get("name", "") not in inside:
                add("flow", a["id"], f"{a['id']}의 출구「{x.get('name', '')}」로 가는 연결이 없습니다.")


def _branches(agents, links, add) -> None:
    groups: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
    for a in agents:
        for e in a.get("edges", []):
            groups[(a["id"], e.get("from", ""))].append((full(a, e["id"]), e))
    for link in links:
        groups[("", link.get("from", "") + "/" + link.get("exit", ""))].append((link["id"], link))
    for (_, source), group in groups.items():
        ids = ", ".join(i for i, _ in group)
        kinds = {e.get("kind") for _, e in group}
        if len(group) > 1 and kinds != {"cond"}:
            add("branch", group[0][0], f"같은 곳에서 나가는 연결({ids})이 여럿이면 모두 조건 연결이어야 합니다.")
        if len(group) == 1 and kinds == {"cond"}:
            add("branch", group[0][0], f"{ids}는 조건 연결이 하나뿐이라, 조건이 맞지 않을 때 갈 곳이 없습니다.")


def _exits(agents, links, add) -> None:
    for a in agents:
        names = [x.get("name", "") for x in a.get("exits", [])]
        for name in names:
            count = sum(1 for link in links if link.get("from") == a["id"] and link.get("exit") == name)
            if count != 1:
                add("exit", a["id"], f"{a['id']}의 출구「{name}」에 이어진 에이전트 연결이 {count}개입니다. 1개여야 합니다.")
        for link in links:
            if link.get("from") == a["id"] and link.get("exit") not in names:
                add("exit", link["id"], f"{link['id']}가 {a['id']}에 없는 출구「{link.get('exit', '')}」에서 나갑니다.")


def _loops(agents, links, add) -> None:
    def scan(edges: list[dict], prefix) -> None:
        back = back_pairs(START, _pairs(edges))
        known = {e["id"] for e in edges}
        for e in edges:
            if (e.get("from"), e.get("to")) not in back:
                continue
            target = prefix(e["id"])
            if not e.get("loop_exit") or e["loop_exit"] not in known or not str(e.get("loop_limit", "")).strip():
                add("loop", target, f"{target}는 되돌아가는 연결이라 반복 탈출 연결과 횟수가 있어야 합니다.")

    scan(links, lambda i: i)
    for a in agents:
        scan(a.get("edges", []), lambda i, a=a: full(a, i))


def _data(doc, agents, links, add) -> None:
    produced = {r.get("item", "") for r in doc.get("inputs", [])}
    consumed = {r.get("item", "") for r in doc.get("outputs", [])}
    for a in agents:
        for s in a.get("steps", []):
            produced.update(s.get("outputs", []))
            consumed.update(s.get("inputs", []))
        for e in a.get("edges", []):
            consumed.update(e.get("passes", []))
    for link in links:
        consumed.update(link.get("passes", []))
    for a in by_id(agents):
        for s in by_id(a.get("steps", [])):
            target = full(a, s["id"])
            for name in s.get("inputs", []):
                if name and name not in produced:
                    add("data", target, f"{target}가 받는「{name}」을(를) 내놓는 곳이 없습니다.")
            for name in s.get("outputs", []):
                if name and name not in consumed:
                    add("data", target, f"{target}가 내놓는「{name}」을(를) 받는 곳이 없습니다.")
    step_outputs = {n for a in agents for s in a.get("steps", []) for n in s.get("outputs", [])}
    for r in doc.get("outputs", []):
        if agents and r.get("item") and r["item"] not in step_outputs:
            add("data", "project", f"프로젝트가 내놓는「{r['item']}」을(를) 만드는 단계가 없습니다.")


def usage(doc: dict) -> dict[str, dict[str, list[str]]]:
    """Data name -> {"made": [targets], "used": [targets]} across step, edge, and link files."""
    use: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"made": [], "used": []})
    for a in by_id(doc.get("agents", [])):
        for s in by_id(a.get("steps", [])):
            for n in s.get("outputs", []):
                use[n]["made"].append(full(a, s["id"]))
            for n in s.get("inputs", []):
                use[n]["used"].append(full(a, s["id"]))
        for e in by_id(a.get("edges", [])):
            for n in e.get("passes", []):
                use[n]["used"].append(full(a, e["id"]))
    for link in by_id(doc.get("links", [])):
        for n in link.get("passes", []):
            use[n]["used"].append(link["id"])
    return use


def _glossary(doc, agents, links, add) -> None:
    listed = {g.get("name", "") for g in doc.get("glossary", [])}
    use = usage(doc)
    for name, where in sorted(use.items()):
        if name and len(set(where["made"] + where["used"])) >= 2 and name not in listed:
            add("glossary", "project", f"「{name}」은(는) 여러 문서에서 쓰여 용어 사전에 있어야 합니다.")
    # ponytail: only catches names that differ by spacing or case; meaning-level look-alikes are the reviewer's job
    seen: dict[str, str] = {}
    for name in sorted(listed | set(use)):
        key = "".join(name.split()).lower()
        if key and key in seen and seen[key] != name:
            add("glossary", "project", f"「{seen[key]}」와「{name}」은 같은 이름으로 보입니다. 하나로 맞추세요.")
        seen.setdefault(key, name)
