"""Proposal cards as per-target patches: diff two documents into units (a project field, a tool, a data entry,
a link, an agent's own fields, a step, an inner edge) and apply chosen units onto the current document.

A unit applies only while its current value still equals the value the card was made from, so editing one
node never voids a card about another node.
"""

from __future__ import annotations

import copy

import schema

SECTIONS = ("agents", "links", "tools", "glossary", "layout", "format")
INNER = ("steps", "edges")


def _units(doc: dict) -> dict[str, tuple[str, str, object, int]]:
    """key -> (kind, target, value, index in its list)."""
    out: dict[str, tuple[str, str, object, int]] = {}
    for k, v in doc.items():
        if k not in SECTIONS:
            out[f"project.{k}"] = ("project", "project", v, 0)
    for i, t in enumerate(doc.get("tools", [])):
        out[f"tool:{t.get('id')}"] = ("tool", t.get("id", ""), t, i)
    for i, g in enumerate(doc.get("glossary", [])):
        out[f"glossary:{g.get('name')}"] = ("glossary", "project", g, i)
    for i, link in enumerate(doc.get("links", [])):
        out[f"link:{link.get('id')}"] = ("link", link.get("id", ""), link, i)
    for i, a in enumerate(doc.get("agents", [])):
        aid = a.get("id", "")
        out[f"agent:{aid}"] = ("agent", aid, {k: v for k, v in a.items() if k not in INNER}, i)
        for key, kind in (("steps", "step"), ("edges", "edge")):
            for j, x in enumerate(a.get(key, [])):
                out[f"{kind}:{aid}:{x.get('id')}"] = (kind, f"{aid}-{x.get('id')}", x, j)
    return out


def _label(doc: dict, key: str, kind: str, value) -> str:
    if kind == "project":
        k = key.split(".", 1)[1]
        return "프로젝트 · " + next((f[1] for f in schema.PROJECT if f[0] == k), k)
    if kind == "glossary":
        return "데이터 사전 · " + str(value.get("name", ""))
    if kind == "tool":
        return f"{value.get('id', '')} {schema.tool_name(doc, value)}".strip()
    if kind in ("step", "edge"):
        _, aid, xid = key.split(":")
        return f"{aid}-{xid} {value.get('name', '')}".strip()
    return f"{value.get('id', '')} {value.get('name', '')}".strip()


def diff(base: dict, new: dict) -> list[dict]:
    """Units that differ: {key, kind, target, label, op (add|change|remove), before, after, index}."""
    old, cur = _units(base), _units(new)
    gone = {k.split(":")[1] for k in old if k.startswith("agent:") and k not in cur}
    items = []
    for key in [*cur, *(k for k in old if k not in cur)]:
        before, after = old.get(key), cur.get(key)
        if before and after and before[2] == after[2]:
            continue
        unit = after or before
        assert unit
        kind, target, value, index = unit
        if kind in ("step", "edge") and not after and key.split(":")[1] in gone:
            continue  # removing the agent removes its steps and edges
        items.append({"key": key, "kind": kind, "target": target, "label": _label(new if after else base, key, kind, value),
                      "op": "add" if not before else "remove" if not after else "change",
                      "before": before[2] if before else None, "after": after[2] if after else None, "index": index})
    return items


def _place(items: list, match, value, index: int) -> None:
    at = next((i for i, x in enumerate(items) if match(x)), None)
    if value is None:
        if at is not None:
            items.pop(at)
    elif at is None:
        items.insert(min(index, len(items)), copy.deepcopy(value))
    else:
        items[at] = copy.deepcopy(value)


def _set(doc: dict, item: dict) -> None:
    key, kind, value = item["key"], item["kind"], item["after"]
    if kind == "project":
        k = key.split(".", 1)[1]
        if value is None:
            doc.pop(k, None)
        else:
            doc[k] = copy.deepcopy(value)
        return
    if kind in ("tool", "link"):
        lst = doc.setdefault("tools" if kind == "tool" else "links", [])
        return _place(lst, lambda x: x.get("id") == key.split(":")[1], value, item["index"])
    if kind == "glossary":
        return _place(doc.setdefault("glossary", []), lambda x: x.get("name") == key.split(":", 1)[1], value, item["index"])
    agents = doc.setdefault("agents", [])
    aid = key.split(":")[1]
    agent = next((a for a in agents if a.get("id") == aid), None)
    if kind == "agent":
        if value is None:
            _place(agents, lambda x: x.get("id") == aid, None, 0)
        elif agent is None:
            agents.insert(min(item["index"], len(agents)), {**copy.deepcopy(value), "steps": [], "edges": []})
        else:
            for k in [k for k in agent if k not in INNER]:
                del agent[k]
            agent.update(copy.deepcopy(value))
        return
    if agent is None:
        raise KeyError(f"{item['label']}: {aid} 에이전트가 없어 적용할 수 없습니다. 에이전트 항목도 함께 고르세요.")
    xid = key.split(":")[2]
    _place(agent.setdefault("steps" if kind == "step" else "edges", []), lambda x: x.get("id") == xid, value, item["index"])


def apply(doc: dict, items: list[dict]) -> tuple[dict, list[str]]:
    """New document with `items` applied, and the labels of items whose target changed since the card was made
    (when any conflict, nothing is applied). Raises KeyError when a chosen item needs an agent that is missing."""
    now = _units(doc)
    conflicts = [it["label"] for it in items if (now[it["key"]][2] if it["key"] in now else None) != it["before"]]
    if conflicts:
        return doc, conflicts
    out = copy.deepcopy(doc)
    for it in items:
        _set(out, it)
    return out, []
