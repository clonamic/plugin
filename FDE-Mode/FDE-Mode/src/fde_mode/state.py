"""Mode, phase and switches. The single place that says "where are we"."""
from __future__ import annotations

import datetime as _dt
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from fde_mode import config, db
from fde_mode.paths import P, for_project
from fde_mode.util import dumps, iso, loads, now

PHASES: dict[str, str] = {
    "P0": "부팅·점검",
    "P1": "인터뷰 루프",
    "P2": "기술 결정 게이트",   # runs in parallel with P1; phase stays P1 while the gate is open
    "P3": "핵심 동결",
    "P4": "구현 루프",
    "P5": "확장 인터뷰(구현과 병행)",
    "P6": "마감 모드",
    "P7": "회고·보관",
}

PHASE_SKILL: dict[str, str] = {
    "P0": "fde-mode",
    "P1": "fde-interview",
    "P2": "fde-tech-gate",
    "P3": "fde-freeze",
    "P4": "fde-build",
    "P5": "fde-build",
    "P6": "fde-closing",
    "P7": "fde-closing",
}


@dataclass
class Ctx:
    p: P
    cfg: dict[str, Any]
    conn: sqlite3.Connection
    _state: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def state(self) -> dict[str, Any]:
        if self._state is None:
            self._state = get_state(self.conn)
        return self._state

    def refresh(self) -> dict[str, Any]:
        self._state = get_state(self.conn)
        return self._state

    def switch(self, name: str) -> bool:
        if name in config.SWITCHES_LOCKED:
            return True
        eff = effective_switches(self.cfg, self.state)
        return bool(eff.get(name, True))

    def event(self, kind: str, ref: str = "", payload: Any = None, actor: str = "fde") -> None:
        self.conn.execute("INSERT INTO events(ts, kind, actor, ref, payload) VALUES(?,?,?,?,?)",
                          (iso(), kind, actor, ref, dumps(payload) if payload is not None else None))


def open_ctx(start=None, create: bool = False) -> Ctx | None:
    """Open the project context. Returns None when FDE was never initialised here
    (the hooks rely on this to stay silent in unrelated projects)."""
    p = for_project(start)
    if not create and not p.db.exists():
        return None
    p.ensure()
    cfg = config.load(p)
    conn = db.connect(p.db)
    return Ctx(p, cfg, conn)


def get_state(conn: sqlite3.Connection) -> dict[str, Any]:
    r = db.one(conn, "SELECT * FROM state WHERE id=1") or {}
    for k in ("switches", "flags", "speakers"):
        r[k] = loads(r.get(k), {}) or {}
    return r


def set_state(ctx: Ctx, **fields: Any) -> dict[str, Any]:
    with db.write_txn(ctx.conn):  # read-modify-write under the write lock: never writes back a stale round or flag
        st = get_state(ctx.conn)
        for k, v in fields.items():
            if k in ("switches", "flags", "speakers") and isinstance(v, dict):
                merged = dict(st.get(k) or {})
                merged.update(v)
                v = merged
            st[k] = v
        ctx.conn.execute(
            "UPDATE state SET mode=?, phase=?, round=?, switches=?, flags=?, speakers=?, updated_at=? WHERE id=1",
            (st.get("mode", "off"), st.get("phase", "P0"), int(st.get("round") or 0),
             dumps(st.get("switches") or {}), dumps(st.get("flags") or {}), dumps(st.get("speakers") or {}), iso()),
        )
    ctx._state = st
    return st


def effective_switches(cfg: dict, st: dict) -> dict[str, bool]:
    eff = dict(cfg.get("switches") or {})
    eff.update(st.get("switches") or {})
    return eff


def is_on(ctx: Ctx | None) -> bool:
    return bool(ctx and ctx.state.get("mode") == "on")


# ---------- time budget ----------

def _at(cfg: dict, key: str) -> _dt.datetime | None:
    sch = cfg.get("schedule") or {}
    date = (sch.get("date") or "").strip()
    hhmm = (sch.get(key) or "").strip()
    if not date or not hhmm:
        return None
    try:
        return _dt.datetime.fromisoformat(f"{date}T{hhmm}").replace(tzinfo=now().tzinfo)
    except ValueError:
        return None


def timeline(cfg: dict) -> dict[str, Any]:
    """Minutes left until each milestone (negative = passed). Empty when no deadline is set."""
    t = now()
    out: dict[str, Any] = {"now": t.strftime("%H:%M")}
    for key in ("start", "core_freeze", "full_freeze", "feature_freeze", "submit_by", "end"):
        at = _at(cfg, key)
        if at:
            out[key] = {"at": at.strftime("%H:%M"), "min_left": int((at - t).total_seconds() // 60)}
    return out


def next_milestone(cfg: dict) -> tuple[str, int] | None:
    tl = timeline(cfg)
    future = [(k, v["min_left"]) for k, v in tl.items() if isinstance(v, dict) and v["min_left"] >= 0]
    return min(future, key=lambda kv: kv[1]) if future else None


def open_project(start=None) -> Ctx:
    ctx = open_ctx(start, create=True)
    assert ctx is not None
    return ctx
