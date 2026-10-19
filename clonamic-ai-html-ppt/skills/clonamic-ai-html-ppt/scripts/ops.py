"""Op batches: validate against assets/web/schema.json, apply inside the caller's transaction, build the inverse.

Also the fractional z keys and the compact AI outline (format.md §1, §2, §5).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

SCHEMA = json.loads((Path(__file__).resolve().parent.parent / "assets" / "web" / "schema.json").read_text(encoding="utf-8"))
ENUMS: dict[str, list] = SCHEMA["enums"]
MAX_OPS = 5000
ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
Z = re.compile(r"[0-9A-Za-z]{1,256}")
COLOR_RE = re.compile(r"#[0-9A-F]{8}")
HASH = re.compile(r"[0-9a-f]{64}")
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"  # ASCII order


class OpError(Exception):
    """A batch that breaks the contract → HTTP 400 {error, index, key}."""

    def __init__(self, index: int | None, key: str, message: str):
        super().__init__(message)
        self.index, self.key = index, key


class Conflict(Exception):
    """A `rev` guard no longer matches → HTTP 409 {error, conflicts}."""

    def __init__(self, conflicts: list[dict]):
        super().__init__("다른 곳에서 먼저 바뀌었습니다.")
        self.conflicts = conflicts


class Bad(Exception):
    """A value that does not fit its spec; `path` points inside the prop."""

    def __init__(self, path: str, message: str):
        super().__init__(message)
        self.path = path


# ---- value specs: a tiny declarative shape language --------------------------------------------

def num(lo=None, hi=None): return ("num", lo, hi)
def integer(lo=None, hi=None): return ("int", lo, hi)
def enum(name): return ("enum", ENUMS[name])
def one_of(*values): return ("enum", list(values))
def text(limit): return ("str", limit)
def listof(spec, lo=0, hi=10000): return ("list", spec, lo, hi)
def obj(fields, required=()): return ("obj", fields, set(required))
def nullable(spec): return ("null", spec)


BOOL, COLOR, HASH_SPEC, NUM = ("bool",), ("color",), ("hash",), num()
UNIT = num(0, 1)
STOPS = listof(obj({"p": UNIT, "color": COLOR}, ("p", "color")), 2, 64)
PAINT_BASE = {"type": enum("paint"), "visible": BOOL, "opacity": UNIT, "blend": enum("blend")}
GRADIENT = {"stops": STOPS, "cx": UNIT, "cy": UNIT}
PAINTS = {
    "SOLID": obj(PAINT_BASE | {"color": COLOR}, ("type", "color")),
    "LINEAR": obj(PAINT_BASE | {"stops": STOPS, "angle": NUM}, ("type", "stops")),
    "RADIAL": obj(PAINT_BASE | GRADIENT | {"rx": UNIT, "ry": UNIT}, ("type", "stops")),
    "DIAMOND": obj(PAINT_BASE | GRADIENT | {"rx": UNIT, "ry": UNIT}, ("type", "stops")),
    "ANGULAR": obj(PAINT_BASE | GRADIENT | {"angle": NUM}, ("type", "stops")),
    "IMAGE": obj(PAINT_BASE | {
        "asset": HASH_SPEC, "mode": enum("imageMode"), "scale": num(0), "rotation": one_of(0, 90, 180, 270),
        "crop": obj({k: UNIT for k in "xywh"}),
        "filters": obj({k: num(-1, 1) for k in ("exposure", "contrast", "saturation", "temperature", "tint", "highlights", "shadows")}),
    }, ("type", "asset")),
}
SHADOW = {"type": enum("effect"), "visible": BOOL, "color": COLOR, "x": NUM, "y": NUM, "blur": num(0), "spread": NUM,
          "blend": enum("blend")}
EFFECTS = {
    "DROP_SHADOW": obj(SHADOW | {"showBehind": BOOL}, ("type",)),
    "INNER_SHADOW": obj(SHADOW, ("type",)),
    "LAYER_BLUR": obj({"type": enum("effect"), "visible": BOOL, "radius": num(0), "progressive": obj(
        {"startRadius": num(0), "start": listof(UNIT, 2, 2), "end": listof(UNIT, 2, 2)})}, ("type",)),
    "BACKGROUND_BLUR": obj({"type": enum("effect"), "visible": BOOL, "radius": num(0)}, ("type",)),
}
EFFECT_LIMIT = {"DROP_SHADOW": 8, "INNER_SHADOW": 8, "LAYER_BLUR": 1, "BACKGROUND_BLUR": 1}
STROKE = obj({
    "weight": num(0), "align": enum("strokeAlign"), "sides": nullable(obj({k: num(0) for k in "trbl"})),
    "dash": listof(num(0), 0, 64), "dashCap": enum("dashCap"), "join": enum("join"), "miterLimit": num(0),
    "capStart": enum("cap"), "capEnd": enum("cap"),
})
LAYOUT = nullable(obj({
    "dir": enum("layoutDir"), "wrap": BOOL, "gap": NUM, "gapCross": NUM, "pad": listof(NUM, 4, 4),
    "alignMain": enum("alignMain"), "alignCross": enum("alignCross"), "sizingH": enum("sizing"), "sizingV": enum("sizing"),
    "strokesIncluded": BOOL, "reverseZ": BOOL,
}))
RADIUS = ("radius",)
STYLE = obj({
    "font": text(200), "weight": integer(100, 900), "italic": BOOL, "size": num(1),
    "lineHeight": obj({"unit": enum("unit"), "value": NUM}, ("unit",)),
    "letterSpacing": obj({"unit": one_of("PX", "PERCENT"), "value": NUM}, ("unit",)),
    "decoration": enum("decoration"), "case": enum("textCase"),
})
RUNS = listof(obj({"t": text(100000), "s": STYLE, "fill": COLOR, "link": text(2000)}, ("t",)))
# Object/array props of schema.json, by key; any other object/array key only has to be JSON of that type.
NAMED = {
    "constraints": obj({"h": enum("constraintH"), "v": enum("constraintV")}),
    "layoutChild": obj({"sizingH": enum("sizing"), "sizingV": enum("sizing"), "absolute": BOOL,
                        **{k: nullable(num(0)) for k in ("minW", "maxW", "minH", "maxH")}}),
    "arc": obj({"start": NUM, "end": NUM, "inner": UNIT}),
    "style": STYLE,
    "runs": RUNS,
    "paras": listof(obj({"list": enum("list"), "level": integer(0, 8)})),
    "guides": listof(obj({"type": enum("guide"), "count": integer(0), "size": num(0), "gutter": num(0), "margin": NUM,
                          "offset": NUM, "align": enum("guideAlign"), "color": COLOR, "visible": BOOL}, ("type",)), 0, 100),
    "paths": listof(obj({"closed": BOOL, "pts": listof(obj({k: NUM for k in ("x", "y", "ix", "iy", "ox", "oy")}, ("x", "y")), 0, 100000)},
                        ("pts",))),
    "cols": listof(num(0), 1, 1000),
    "rows": listof(num(0), 1, 1000),
    "cells": ("map", re.compile(r"\d{1,4},\d{1,4}"), obj({"runs": RUNS, "style": STYLE, "fill": COLOR,
                                                       "alignH": enum("alignH"), "alignV": enum("alignV")})),
    "border": obj({"color": COLOR, "weight": num(0)}),
    "asset": ("hash?",), "poster": ("hash?",),
}


def is_num(v) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(float(v))
    except OverflowError:
        return False


def check(v, spec: tuple, path: str) -> None:
    """Raise Bad when `v` does not fit `spec`."""
    kind = spec[0]
    if kind in ("num", "int"):
        if not is_num(v) or (kind == "int" and float(v) != int(v)):
            raise Bad(path, "정수가 아닙니다." if kind == "int" else "유한한 숫자가 아닙니다.")
        if (spec[1] is not None and v < spec[1]) or (spec[2] is not None and v > spec[2]):
            raise Bad(path, f"범위 {spec[1]}..{spec[2]} 밖입니다.")
    elif kind == "bool":
        if not isinstance(v, bool):
            raise Bad(path, "true/false가 아닙니다.")
    elif kind == "str":
        if not isinstance(v, str) or len(v) > spec[1]:
            raise Bad(path, f"{spec[1]}자 이하 문자열이 아닙니다.")
    elif kind == "enum":
        if isinstance(v, bool) or v not in spec[1]:
            raise Bad(path, f"허용 값이 아닙니다: {', '.join(map(str, spec[1]))}")
    elif kind == "color":
        if not isinstance(v, str) or not COLOR_RE.fullmatch(v):
            raise Bad(path, "색은 대문자 #RRGGBBAA입니다.")
    elif kind in ("hash", "hash?"):
        if not isinstance(v, str) or not (HASH.fullmatch(v) or (kind == "hash?" and v == "")):
            raise Bad(path, "에셋 해시는 소문자 16진수 64자입니다.")
    elif kind == "null":
        if v is not None:
            check(v, spec[1], path)
    elif kind == "list":
        if not isinstance(v, list) or not spec[2] <= len(v) <= spec[3]:
            raise Bad(path, f"항목 {spec[2]}~{spec[3]}개 배열이 아닙니다.")
        for i, item in enumerate(v):
            check(item, spec[1], f"{path}[{i}]")
    elif kind == "obj":
        if not isinstance(v, dict):
            raise Bad(path, "객체가 아닙니다.")
        for key in spec[2] - v.keys():
            raise Bad(f"{path}.{key}", "필수 값이 없습니다.")
        for key, item in v.items():
            if key not in spec[1]:
                raise Bad(f"{path}.{key}", "알 수 없는 키입니다.")
            check(item, spec[1][key], f"{path}.{key}")
    elif kind == "map":
        if not isinstance(v, dict):
            raise Bad(path, "객체가 아닙니다.")
        for key, item in v.items():
            if not spec[1].fullmatch(key):
                raise Bad(f"{path}.{key}", '키는 "행,열"입니다.')
            check(item, spec[2], f"{path}.{key}")
    elif kind == "radius":
        if isinstance(v, list):
            check(v, listof(num(0), 4, 4), path)
        else:
            check(v, num(0), path)
    elif kind in ("paints", "effects"):
        table = PAINTS if kind == "paints" else EFFECTS
        if not isinstance(v, list) or len(v) > 64:
            raise Bad(path, "64개 이하 배열이 아닙니다.")
        counts: dict[str, int] = {}
        for i, item in enumerate(v):
            kind_of = item.get("type") if isinstance(item, dict) else None
            if kind_of not in table:
                raise Bad(f"{path}[{i}].type", f"허용 값이 아닙니다: {', '.join(table)}")
            check(item, table[kind_of], f"{path}[{i}]")
            counts[kind_of] = counts.get(kind_of, 0) + 1
            if kind == "effects" and counts[kind_of] > EFFECT_LIMIT[kind_of]:
                raise Bad(path, f"{kind_of}는 최대 {EFFECT_LIMIT[kind_of]}개입니다.")
    elif kind == "json":
        if not isinstance(v, spec[1]):
            raise Bad(path, "객체가 아닙니다." if spec[1] is dict else "배열이 아닙니다.")
    else:  # pragma: no cover - a spec typo
        raise AssertionError(kind)


def spec_of(key: str, field: dict) -> tuple:
    """schema.json field → value spec."""
    kind = field["kind"]
    if key in NAMED and kind in ("object", "array", "string"):
        return NAMED[key]
    return {
        "string": lambda: text(field.get("max", 100000)),
        "number": lambda: num(field.get("min"), field.get("max")),
        "int": lambda: integer(field.get("min"), field.get("max")),
        "bool": lambda: BOOL,
        "enum": lambda: enum(field["enum"]),
        "paints": lambda: ("paints",), "effects": lambda: ("effects",),
        "stroke": lambda: STROKE, "radius": lambda: RADIUS, "layout": lambda: LAYOUT,
        "object": lambda: ("json", dict), "array": lambda: ("json", list),
    }[kind]()


SPECS = {t: {k: spec_of(k, f) for k, f in (SCHEMA["common"] | SCHEMA["props"][t]).items()} for t in SCHEMA["types"]}
CONTAINERS = set(SCHEMA["containers"])
SIDES_OK = {"rect", "frame", "page"}


def defaults(node_type: str) -> dict:
    """Resolved defaults: typeDefaults over props[type] over common."""
    out = {k: f["default"] for k, f in SCHEMA["common"].items()}
    out |= {k: f["default"] for k, f in SCHEMA["props"][node_type].items()}
    return out | SCHEMA["typeDefaults"].get(node_type, {})


def check_props(node_type: str, props, index: int, allow_null: bool) -> None:
    if not isinstance(props, dict):
        raise OpError(index, "props", "props는 객체입니다.")
    specs = SPECS[node_type]
    for key, value in props.items():
        if key not in specs:
            raise OpError(index, key, f"{node_type}에 없는 속성입니다: {key}")
        if value is None and allow_null:
            continue
        try:
            check(value, specs[key], key)
        except Bad as exc:
            raise OpError(index, key, f"{exc.path}: {exc}") from None
        if key == "stroke" and value.get("sides") is not None and node_type not in SIDES_OK:
            raise OpError(index, key, "stroke.sides는 rect/frame/page만 씁니다.")


# ---- fractional z keys ----------------------------------------------------------------------------

def _mid(a: str, b: str | None) -> str:
    """Key strictly between digit strings a < b (b None = +inf); keys never end in "0"."""
    if b is not None:
        n = 0
        while n < len(b) and (a[n] if n < len(a) else "0") == b[n]:
            n += 1
        if n:
            if n == len(b):
                raise ValueError("두 z 사이에 키가 없습니다.")
            return b[:n] + _mid(a[n:], b[n:])
    da = DIGITS.index(a[0]) if a else 0
    db = DIGITS.index(b[0]) if b is not None else len(DIGITS)
    if db - da > 1:
        return DIGITS[(da + db) // 2]
    if b is not None and len(b) > 1:
        return b[0]
    return DIGITS[da] + _mid(a[1:], None)


def z_between(a: str | None, b: str | None) -> str:
    """A base62 key k with a < k < b in plain string order; None = open end."""
    if a is not None and b is not None and not a < b:
        raise ValueError("z_between needs a < b")
    return _mid(a or "", b)


# ---- applying a batch -----------------------------------------------------------------------------

def node_dict(row) -> dict:
    return {"id": row["id"], "type": row["type"], "parent": row["parent"], "z": row["z"], "rev": row["rev"],
            "props": json.loads(row["props"])}


def _get(db: sqlite3.Connection, deck: int, nid):
    if not isinstance(nid, str):
        return None
    return db.execute("SELECT * FROM nodes WHERE deck_id = ? AND id = ?", (deck, nid)).fetchone()


def subtree(db: sqlite3.Connection, deck: int, nid: str) -> list:
    """The node and all descendants, parents before children."""
    return db.execute("""
        WITH RECURSIVE t(id, depth) AS (
            SELECT id, 0 FROM nodes WHERE deck_id = ?1 AND id = ?2
            UNION ALL SELECT n.id, t.depth + 1 FROM nodes n JOIN t ON n.deck_id = ?1 AND n.parent = t.id)
        SELECT n.* FROM t JOIN nodes n ON n.deck_id = ?1 AND n.id = t.id ORDER BY t.depth, n.z""", (deck, nid)).fetchall()


def _top_z(db, deck: int, parent, exclude: str | None = None) -> str:
    row = db.execute("SELECT max(z) FROM nodes WHERE deck_id = ? AND parent IS ? AND id IS NOT ?",
                     (deck, parent, exclude)).fetchone()
    return z_between(row[0], None)


def _fields(op: dict, i: int, allowed: set, required: set) -> None:
    for key in op.keys() - allowed:
        raise OpError(i, key, f"{op.get('op')} 연산에 없는 필드입니다: {key}")
    for key in required - op.keys():
        raise OpError(i, key, f"필수 필드가 없습니다: {key}")


def _need(db, deck: int, op: dict, i: int):
    row = _get(db, deck, op.get("id"))
    if row is None:
        raise OpError(i, "id", f"없는 노드입니다: {op.get('id')}")
    return row


def _z(op: dict, i: int):
    z = op.get("z")
    if z is not None and not (isinstance(z, str) and Z.fullmatch(z)):
        raise OpError(i, "z", "z는 [0-9A-Za-z]+ 문자열입니다.")
    return z


def _parent(db, deck: int, node_type: str, parent, i: int, moving: str | None = None) -> None:
    """Page ↔ null parent; otherwise an existing container; section only in a page; no cycle."""
    if node_type == "page":
        if parent is not None:
            raise OpError(i, "parent", "page의 parent는 null입니다.")
        return
    row = _get(db, deck, parent)
    if row is None:
        raise OpError(i, "parent", f"없는 부모입니다: {parent}")
    if row["type"] not in CONTAINERS:
        raise OpError(i, "parent", f"{row['type']}는 컨테이너가 아닙니다.")
    if node_type == "section" and row["type"] != "page":
        raise OpError(i, "parent", "section은 page 바로 아래에만 둡니다.")
    while moving is not None and row is not None:
        if row["id"] == moving:
            raise OpError(i, "parent", "자기 자신이나 자손 아래로 옮길 수 없습니다.")
        row = _get(db, deck, row["parent"])


def _add(db, deck: int, op: dict, seq: int, i: int):
    _fields(op, i, {"op", "node"}, {"node"})
    node = op["node"]
    if not isinstance(node, dict):
        raise OpError(i, "node", "node는 객체입니다.")
    for key in node.keys() - {"id", "type", "parent", "z", "props"}:
        raise OpError(i, key, f"node에 없는 필드입니다: {key}")
    nid, node_type, parent = node.get("id"), node.get("type"), node.get("parent")
    if not isinstance(nid, str) or not ID.fullmatch(nid):
        raise OpError(i, "id", "id는 [A-Za-z0-9_-]{1,32}입니다.")
    if node_type not in SPECS:
        raise OpError(i, "type", f"알 수 없는 type입니다: {node_type}")
    props = node.get("props", {})
    check_props(node_type, props, i, allow_null=False)
    _parent(db, deck, node_type, parent, i)
    if _get(db, deck, nid) is not None:
        raise OpError(i, "id", f"이미 있는 id입니다: {nid}")
    z = _z(node, i) or _top_z(db, deck, parent)
    db.execute("INSERT INTO nodes (deck_id, id, parent, z, type, props, rev) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (deck, nid, parent, z, node_type, json.dumps(props, ensure_ascii=False), seq))
    applied = {"op": "add", "node": {"id": nid, "type": node_type, "parent": parent, "z": z, "rev": seq, "props": props}}
    return applied, [{"op": "del", "id": nid}]


def _set(db, deck: int, op: dict, seq: int, i: int):
    _fields(op, i, {"op", "id", "props", "rev"}, {"id", "props"})
    row = _need(db, deck, op, i)
    check_props(row["type"], op["props"], i, allow_null=True)
    props = json.loads(row["props"])
    inverse = {"op": "set", "id": row["id"], "props": {k: props.get(k) for k in op["props"]}}
    for key, value in op["props"].items():
        if value is None:
            props.pop(key, None)
        else:
            props[key] = value
    db.execute("UPDATE nodes SET props = ?, rev = ? WHERE deck_id = ? AND id = ?",
               (json.dumps(props, ensure_ascii=False), seq, deck, row["id"]))
    return {"op": "set", "id": row["id"], "props": op["props"], "rev": seq}, [inverse]


def _del(db, deck: int, op: dict, seq: int, i: int):
    _fields(op, i, {"op", "id", "rev"}, {"id"})
    row = _need(db, deck, op, i)
    rows = subtree(db, deck, row["id"])
    db.execute("DELETE FROM nodes WHERE deck_id = ? AND id = ?", (deck, row["id"]))  # children go by FK cascade
    inverse = [{"op": "add", "node": {k: n[k] for k in ("id", "type", "parent", "z")} | {"props": json.loads(n["props"])}}
               for n in rows]
    return {"op": "del", "id": row["id"], "rev": seq}, inverse, [n["id"] for n in rows]


def _move(db, deck: int, op: dict, seq: int, i: int):
    _fields(op, i, {"op", "id", "parent", "z", "rev"}, {"id", "parent"})
    row = _need(db, deck, op, i)
    parent = op["parent"]
    _parent(db, deck, row["type"], parent, i, moving=row["id"])
    z = _z(op, i) or _top_z(db, deck, parent, exclude=row["id"])
    db.execute("UPDATE nodes SET parent = ?, z = ?, rev = ? WHERE deck_id = ? AND id = ?", (parent, z, seq, deck, row["id"]))
    applied = {"op": "move", "id": row["id"], "parent": parent, "z": z, "rev": seq}
    return applied, [{"op": "move", "id": row["id"], "parent": row["parent"], "z": row["z"]}]


def _deck(db, deck: int, op: dict, seq: int, i: int):
    _fields(op, i, {"op", "props"}, {"props"})
    props = op["props"]
    if not isinstance(props, dict) or set(props) != {"name"}:
        raise OpError(i, "props", "deck 연산은 props.name만 바꿉니다.")
    try:
        check(props["name"], text(200), "name")
    except Bad as exc:
        raise OpError(i, "name", f"name: {exc}") from None
    old = db.execute("SELECT name FROM decks WHERE id = ?", (deck,)).fetchone()["name"]
    db.execute("UPDATE decks SET name = ? WHERE id = ?", (props["name"], deck))
    return {"op": "deck", "props": {"name": props["name"]}}, [{"op": "deck", "props": {"name": old}}]


APPLY = {"add": _add, "set": _set, "del": _del, "move": _move, "deck": _deck}


def check_revs(db, deck: int, batch: list) -> None:
    """Every `rev` guard is checked against the state before the batch."""
    conflicts, seen = [], set()
    for i, op in enumerate(batch):
        if not isinstance(op, dict) or "rev" not in op or op.get("op") not in ("set", "del", "move"):
            continue
        rev = op["rev"]
        if isinstance(rev, bool) or not isinstance(rev, int):
            raise OpError(i, "rev", "rev는 정수입니다.")
        row = _get(db, deck, op.get("id"))
        if (row is None or row["rev"] != rev) and op.get("id") not in seen:
            seen.add(op.get("id"))
            conflicts.append({"id": op.get("id"), "rev": row["rev"] if row else None, "node": node_dict(row) if row else None})
    if conflicts:
        raise Conflict(conflicts)


def apply(db: sqlite3.Connection, deck: int, batch, seq: int) -> tuple[list, list, dict]:
    """Apply `batch` as op `seq` inside the caller's open transaction.

    Returns (applied ops with z/rev filled in, inverse batch, {id: rev}). Raises OpError or Conflict; the caller
    rolls back, so nothing applies.
    """
    if not isinstance(batch, list) or not 1 <= len(batch) <= MAX_OPS:
        raise OpError(None, "ops", f"ops는 1~{MAX_OPS}개 연산의 배열입니다.")
    check_revs(db, deck, batch)
    applied, inverses, touched = [], [], {}
    for i, op in enumerate(batch):
        if not isinstance(op, dict) or op.get("op") not in APPLY:
            raise OpError(i, "op", f"op는 {', '.join(APPLY)} 중 하나입니다.")
        result = APPLY[op["op"]](db, deck, op, seq, i)
        applied.append(result[0])
        inverses.append(result[1])
        if op["op"] == "del":
            for nid in result[2]:
                touched.pop(nid, None)
        elif op["op"] != "deck":
            touched[result[0].get("id") or result[0]["node"]["id"]] = seq
    inverse = [inv for group in reversed(inverses) for inv in group]
    return applied, inverse, touched


def strip_revs(batch: list) -> list:
    """Applied ops without their rev fields, so they can be applied again (redo)."""
    out = []
    for op in batch:
        op = {k: v for k, v in op.items() if k != "rev"}
        if "node" in op:
            op["node"] = {k: v for k, v in op["node"].items() if k != "rev"}
        out.append(op)
    return out


# ---- AI outline (format.md §5) --------------------------------------------------------------------

def _n(v) -> str:
    v = round(float(v), 2)
    return str(int(v)) if v == int(v) else str(v)


def _q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _line(node: dict) -> str:
    p, own = defaults(node["type"]) | node["props"], node["props"]
    if node["type"] == "page":
        return f'page {node["id"]} {_q(p["name"])} {_n(p["w"])}x{_n(p["h"])} {p["preset"]} {p["orientation"]} rev={node["rev"]}'
    parts = [node["type"], node["id"], _q(p["name"]), f'{_n(p["x"])},{_n(p["y"])}', f'{_n(p["w"])}x{_n(p["h"])}']
    if "fills" in own:
        shown = [f for f in own["fills"] if f.get("visible", True)]
        parts.append("fill=" + ("none" if not shown else shown[0].get("color") if shown[0]["type"] == "SOLID" else shown[0]["type"]))
    if node["type"] == "text":
        if "size" in own.get("style", {}):
            parts.append(f'size={_n(own["style"]["size"])}')
        body = "".join(r.get("t", "") for r in p["runs"])
        parts.append(_q(body if len(body) <= 80 else body[:79] + "…"))
    if own.get("layout"):
        parts.append(f'layout={own["layout"].get("dir", "NONE")}')
        if "gap" in own["layout"]:
            parts.append(f'gap={_n(own["layout"]["gap"])}')
    if own.get("rotation"):
        parts.append(f'rot={_n(own["rotation"])}')
    if own.get("visible") is False:
        parts.append("hidden")
    return " ".join(parts) + f' rev={node["rev"]}'


def outline(deck: dict, nodes: list[dict], page: str | None = None) -> str:
    """Line-based tree in render order, two spaces per depth."""
    kids: dict = {}
    for n in nodes:
        kids.setdefault(n["parent"], []).append(n)
    lines = [f'deck {deck["id"]} {_q(deck["name"])} seq={deck["seq"]}']

    def walk(parent, depth: int) -> None:
        for n in sorted(kids.get(parent, []), key=lambda n: (n["z"], n["id"])):
            if depth == 0 and page is not None and n["id"] != page:
                continue
            lines.append("  " * depth + _line(n))
            walk(n["id"], depth + 1)

    walk(None, 0)
    return "\n".join(lines) + "\n"
