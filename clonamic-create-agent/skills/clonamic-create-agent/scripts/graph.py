"""Graph helpers shared by checks and render.

Agent level: nodes are "start", agent ids ("A1"), and "end". A link leaves an agent through one of its exits.
Inside an agent: nodes are "start", step ids ("N1"), and "exit:<exit name>".
"""

from __future__ import annotations

import re

START, END, EXIT = "start", "end", "exit:"


def nkey(ident: str) -> tuple:
    """Natural sort: A2 before A10, A1-N2 before A1-N10."""
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", ident))


def by_id(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: nkey(x.get("id", "")))


def find(items: list[dict], ident: str) -> dict | None:
    return next((x for x in items if x.get("id") == ident), None)


def full(agent: dict, ident: str) -> str:
    return f"{agent['id']}-{ident}"


def node_name(agent: dict, ref: str) -> str:
    if ref == START:
        return "시작"
    if ref.startswith(EXIT):
        return ref[len(EXIT):]
    step = find(agent.get("steps", []), ref)
    return step.get("name", "") if step else ref


def agent_name(doc: dict, ref: str) -> str:
    if ref == START:
        return "시작"
    if ref == END:
        return "끝"
    agent = find(doc.get("agents", []), ref)
    return agent.get("name", "") if agent else ref


def edge_name(agent: dict, edge: dict) -> str:
    """Condition summary for conditional edges, destination name for 'always' edges."""
    if edge.get("name", "").strip():
        return edge["name"].strip()
    return node_name(agent, edge.get("to", ""))


def link_name(doc: dict, link: dict) -> str:
    if link.get("name", "").strip():
        return link["name"].strip()
    return link.get("exit") or agent_name(doc, link.get("to", ""))


def reachable(start: str, pairs: list[tuple[str, str]]) -> set[str]:
    seen, todo = {start}, [start]
    while todo:
        node = todo.pop()
        for u, v in pairs:
            if u == node and v not in seen:
                seen.add(v)
                todo.append(v)
    return seen


def back_pairs(start: str, pairs: list[tuple[str, str]]) -> set[tuple[str, str]]:
    """Edges that return to a node already on the current path from start: each one closes a loop."""
    back, done, path = set(), set(), []

    def visit(node: str) -> None:
        path.append(node)
        for u, v in pairs:
            if u != node:
                continue
            if v in path:
                back.add((u, v))
            elif v not in done:
                visit(v)
        path.pop()
        done.add(node)

    visit(start)
    return back
