"""Pre-export checks. Each issue: {"code", "target", "message"}; an empty list means the design may be exported."""

from __future__ import annotations

import re
from collections import defaultdict

import schema
from graph import END, START, back_pairs, by_id, full, reachable


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
    _loops(agents, links, add)
    _data(doc, agents, links, add)
    _glossary(doc, agents, links, add)
    _tools(doc, agents, add)
    _process_chain(doc, agents, add)
    _step_kinds(doc, agents, add)
    _scenarios(doc, agents, links, add)
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
            for i, row in enumerate(s.get("process", []), 1):
                if str(row.get("name", "")).strip() and not str(row.get("does", "")).strip():
                    add("required", full(a, s["id"]), f"{full(a, s['id'])} 과정 {i}행 ‘{row['name']}’에 하는 일이 없습니다.")
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
        steps = {s["id"] for s in a.get("steps", [])}
        ends = {"from": {START} | steps, "to": steps | {END}}
        for e in a.get("edges", []):
            for side in ("from", "to"):
                if e.get(side) not in ends[side]:
                    add("reference", full(a, e["id"]), f"{full(a, e['id'])}의 {'출발' if side == 'from' else '도착'}이 없습니다.")


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
        if END not in inside:
            add("flow", a["id"], f"{a['id']} 안에서 끝으로 가는 연결이 없습니다.")


def _branches(agents, links, add) -> None:
    groups: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
    for a in agents:
        for e in a.get("edges", []):
            groups[(a["id"], e.get("from", ""))].append((full(a, e["id"]), e))
    for link in links:
        groups[("", link.get("from", ""))].append((link["id"], link))
    for (_, source), group in groups.items():
        ids = ", ".join(i for i, _ in group)
        kinds = {e.get("kind") for _, e in group}
        if len(group) > 1 and kinds != {"cond"}:
            add("branch", group[0][0], f"같은 곳에서 나가는 연결({ids})이 여럿이면 모두 조건 연결이어야 합니다.")
        if len(group) == 1 and kinds == {"cond"}:
            add("branch", group[0][0], f"{ids}는 조건 연결이 하나뿐이라, 조건이 맞지 않을 때 갈 곳이 없습니다.")


def _loops(agents, links, add) -> None:
    def scan(edges: list[dict], prefix) -> None:
        back = back_pairs(START, _pairs(edges))
        known = {e["id"]: e for e in edges}
        for e in edges:
            if (e.get("from"), e.get("to")) not in back:
                continue
            target = prefix(e["id"])
            out = known.get(e.get("loop_exit") or "")
            if not out or not str(e.get("loop_limit", "")).strip():
                add("loop", target, f"{target}는 되돌아가는 연결이라 최대 반복 횟수와 한도를 넘으면 갈 연결이 있어야 합니다.")
            elif out is e or out.get("from") != e.get("from"):
                add("loop", target, f"{target}의 한도를 넘으면 갈 연결은 같은 곳에서 나가는 다른 연결이어야 합니다.")
            elif not str(e["loop_limit"]).strip().isdigit():
                add("loop", target, f"{target}의 최대 반복 횟수는 숫자여야 합니다.")

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
                    add("data", target, f"{target}의 input ‘{name}’을(를) 만드는 곳이 없습니다.")
            for name in s.get("outputs", []):
                if name and name not in consumed:
                    add("data", target, f"{target}의 output ‘{name}’을(를) 쓰는 곳이 없습니다.")
    step_outputs = {n for a in agents for s in a.get("steps", []) for n in s.get("outputs", [])}
    for r in doc.get("outputs", []):
        if agents and r.get("item") and r["item"] not in step_outputs:
            add("data", "project", f"프로젝트 output ‘{r['item']}’을(를) 만드는 단계가 없습니다.")


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
    """Every data name has an entry in the data dictionary with its structure, so an implementer can build it."""
    entries = {g.get("name", ""): g for g in doc.get("glossary", [])}
    names = set(usage(doc)) | {r.get("item", "") for r in doc.get("inputs", []) + doc.get("outputs", [])}
    for name in sorted(n for n in names if n):
        g = entries.get(name)
        if not g:
            add("glossary", "project", f"데이터 ‘{name}’이(가) 데이터 사전에 없습니다.")
        elif not any(str(f.get("name", "")).strip() and str(f.get("type", "")).strip() for f in g.get("fields", [])):
            add("glossary", "project", f"데이터 ‘{name}’의 구조(필드 이름과 형식)가 없습니다.")
    # ponytail: only catches names that differ by spacing or case; meaning-level look-alikes are the reviewer's job
    seen: dict[str, str] = {}
    for name in sorted(set(entries) | names):
        key = "".join(name.split()).lower()
        if key and key in seen and seen[key] != name:
            add("glossary", "project", f"‘{seen[key]}’와 ‘{name}’은 같은 이름으로 보입니다. 하나로 맞추세요.")
        seen.setdefault(key, name)


def _tools(doc, agents, add) -> None:
    catalog = {t.get("id"): t for t in doc.get("tools", [])}
    agent_ids = {a["id"] for a in agents}
    used = set()
    for a in by_id(agents):
        for s in by_id(a.get("steps", [])):
            target = full(a, s["id"])
            refs = list(s.get("tools", [])) + [x.get("tool") for x in s.get("process", []) if x.get("tool")]
            for r in dict.fromkeys(refs):
                used.add(r)
                if r not in catalog:
                    add("tool", target, f"{target}가 쓰는 도구 {r}이(가) 도구 목록에 없습니다.")
    for t in doc.get("tools", []):
        name = schema.tool_name(doc, t).strip()
        if not name:
            add("tool", "project", f"도구 목록의 {t.get('id', '')}에 이름이 없습니다.")
        if t.get("kind") == "내부 에이전트" and t.get("ref") not in agent_ids:
            add("tool", "project", f"도구 ‘{name or t.get('id')}’가 가리키는 에이전트가 없습니다.")
        if t.get("id") not in used:
            add("tool", "project", f"도구 ‘{name or t.get('id')}’를 쓰는 단계가 없습니다.")


def names(text) -> list[str]:
    """Data names in a process row's input/output text ("여행 조건, 지역 정보")."""
    return [x.strip() for x in str(text or "").split(",") if x.strip()]


def _process_chain(doc, agents, add) -> None:
    """The process rows must carry a step from its input to its output: a row may only use data the step receives
    or an earlier row made, and every step output must come out of some row. Free text that is not a data name
    (a setting, a file path) is not checked."""
    known = {g.get("name", "") for g in doc.get("glossary", [])}
    for a in by_id(agents):
        for s in by_id(a.get("steps", [])):
            rows = [r for r in s.get("process", []) if str(r.get("name", "")).strip()]
            if not any(names(r.get("input")) or names(r.get("output")) for r in rows):
                continue
            target, have = full(a, s["id"]), set(s.get("inputs", []))
            for i, r in enumerate(rows, 1):
                for n in names(r.get("input")):
                    if n in known and n not in have:
                        add("process", target, f"{target} 과정 {i}행이 쓰는 ‘{n}’은(는) 단계 input에도 앞 행 output에도 없습니다.")
                have.update(names(r.get("output")))
            for n in s.get("outputs", []):
                if n and n not in have:
                    add("process", target, f"{target}의 output ‘{n}’을(를) 만드는 과정 행이 없습니다.")


def _step_kinds(doc, agents, add) -> None:
    """A judgement step needs a model to judge with; a person step must be listed among the human checkpoints."""
    kinds = {t.get("id"): t.get("kind") for t in doc.get("tools", [])}
    points = {str(r.get("point", "")).strip() for r in doc.get("human_points", [])}
    for a in by_id(agents):
        for s in by_id(a.get("steps", [])):
            target = full(a, s["id"])
            used = list(s.get("tools", [])) + [r.get("tool") for r in s.get("process", []) if r.get("tool")]
            if s.get("type") == "판단" and "모델" not in {kinds.get(t) for t in used}:
                add("kind", target, f"{target}은(는) 판단 단계인데 종류가 모델인 도구를 쓰지 않습니다.")
            if s.get("type") == "사람 확인" and target not in points:
                add("kind", target, f"{target}은(는) 사람 확인 단계인데 사람 확인 지점에 없습니다.")


def _scenarios(doc, agents, links, add) -> None:
    """Numbers written in a scenario path must exist (A1, L2, A1-N3, A1-L4)."""
    ids = {x["id"] for x in agents} | {x["id"] for x in links}
    ids |= {full(a, x["id"]) for a in agents for x in a.get("steps", []) + a.get("edges", [])}
    for r in doc.get("scenarios", []):
        for ref in re.findall(r"\b[AL]\d+(?:-[NL]\d+)?\b", str(r.get("path", ""))):
            if ref not in ids:
                add("scenario", "project", f"검증 시나리오 ‘{r.get('name', '')}’의 경로에 없는 번호 {ref}가 있습니다.")
