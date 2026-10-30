"""SQLite store. One database per project: <project>/.claude/fde-mode/fde.db.

Agents never write the database. They write JSON files; `fde sync` (called by
the planner and by the SubagentStop hook) folds those files into these tables.
The dashboard reads, and writes only the conversation-view tables (notes, drafts) and
web-saved interview turns. WAL mode lets both run at the same time.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  mode TEXT NOT NULL DEFAULT 'off',          -- on | off
  phase TEXT NOT NULL DEFAULT 'P0',          -- P0..P7
  round INTEGER NOT NULL DEFAULT 0,          -- last transcript round number
  switches TEXT NOT NULL DEFAULT '{}',
  flags TEXT NOT NULL DEFAULT '{}',          -- rehearsal, core_frozen, full_frozen, feature_frozen ...
  speakers TEXT NOT NULL DEFAULT '{}',       -- learned speaker labels
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, actor TEXT, ref TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS rounds (
  id TEXT PRIMARY KEY, n INTEGER, kind TEXT, status TEXT, raw_path TEXT,
  first_u TEXT, last_u TEXT, created_at TEXT, finished_at TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS utterances (
  id TEXT PRIMARY KEY, seq INTEGER, round TEXT, speaker TEXT, speaker_label TEXT, text TEXT,
  tags TEXT DEFAULT '[]', area TEXT DEFAULT '', qtype TEXT DEFAULT '', parse_conf REAL DEFAULT 1.0,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, pipeline TEXT, round TEXT, status TEXT, stage INTEGER DEFAULT 0,
  params TEXT DEFAULT '{}', created_at TEXT, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS dispatches (
  id TEXT PRIMARY KEY, run TEXT, stage INTEGER, agent TEXT, mode TEXT, output TEXT,
  status TEXT, attempts INTEGER DEFAULT 0, background INTEGER DEFAULT 1,
  issued_at TEXT, done_at TEXT, summary TEXT, error TEXT, inputs TEXT DEFAULT '{}',
  notes TEXT DEFAULT '', extra_writes TEXT DEFAULT '[]', created_at TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY, round TEXT, run TEXT, agent TEXT, division TEXT, kind TEXT, area TEXT,
  gap TEXT, evidence TEXT, quote TEXT, question_draft TEXT, decision_at_stake TEXT,
  if_wrong TEXT, self_confidence TEXT, impact_guess TEXT, merged_into TEXT,
  cite_ok INTEGER, status TEXT DEFAULT 'new', payload TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
  candidate TEXT, round TEXT, source TEXT, confidence TEXT, impact TEXT,
  already_answered INTEGER, forced INTEGER, verdict TEXT, reason TEXT, payload TEXT,
  PRIMARY KEY (candidate, round, source)
);
CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY, round TEXT, candidate TEXT, text TEXT, confidence TEXT, impact TEXT,
  bucket TEXT, flags TEXT DEFAULT '[]', evidence TEXT DEFAULT '[]', decision_at_stake TEXT,
  lens TEXT, verifier TEXT, counter TEXT, ord INTEGER DEFAULT 0, status TEXT DEFAULT 'open',
  asked_u TEXT, answer_us TEXT DEFAULT '[]', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS requirements (
  id TEXT PRIMARY KEY, type TEXT, statement TEXT, status TEXT, evidence TEXT, quote TEXT,
  confidence TEXT, priority TEXT, feasibility TEXT, feasibility_note TEXT, conflict TEXT,
  since_round TEXT, changed_round TEXT, confirmed INTEGER DEFAULT 0, frozen INTEGER DEFAULT 0,
  payload TEXT
);
CREATE TABLE IF NOT EXISTS assumptions (
  id TEXT PRIMARY KEY, text TEXT, reason TEXT, related TEXT, round TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY, grade TEXT, title TEXT, context TEXT, options TEXT, recommended TEXT,
  status TEXT, answer TEXT, source TEXT, round TEXT, blocking TEXT, created_at TEXT,
  answered_at TEXT
);
CREATE TABLE IF NOT EXISTS debates (
  id TEXT PRIMARY KEY, round TEXT, topic TEXT, positions TEXT, ruling TEXT, minority TEXT,
  status TEXT
);
CREATE TABLE IF NOT EXISTS tests (
  id TEXT PRIMARY KEY, requirements TEXT, input TEXT, expected TEXT, fail_if TEXT,
  source TEXT, status TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS adrs (
  id TEXT PRIMARY KEY, title TEXT, decision TEXT, alternatives TEXT, dissent TEXT,
  requirements TEXT, rollback TEXT, grade TEXT, status TEXT, path TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, requirements TEXT, files TEXT, owner TEXT,
  status TEXT, depends TEXT, loops INTEGER DEFAULT 0, created_at TEXT, done_at TEXT,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS releases (
  id TEXT PRIMARY KEY, tag TEXT, commit_sha TEXT, created_at TEXT, test TEXT, deploy TEXT,
  health TEXT, qa TEXT, good INTEGER DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS data_assets (
  id TEXT PRIMARY KEY, name TEXT, path TEXT, kind TEXT, source TEXT, status TEXT,
  rows INTEGER, report TEXT, notes TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS risks (
  id TEXT PRIMARY KEY, text TEXT, severity TEXT, source TEXT, round TEXT, status TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
  round TEXT, scope TEXT, name TEXT, value TEXT, PRIMARY KEY (round, scope, name)
);
CREATE TABLE IF NOT EXISTS artifacts (
  path TEXT PRIMARY KEY, run TEXT, agent TEXT, mode TEXT, round TEXT, mtime REAL, summary TEXT,
  json TEXT
);
-- Conversation view: the user's prompts and Claude's replies (hooks), the interviewer's notes and the chat-room
-- turns typed on the dashboard before [저장] (web). Written by the hooks and the dashboard, never by agents.
CREATE TABLE IF NOT EXISTS convo (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, role TEXT, kind TEXT, text TEXT, round TEXT, session_id TEXT,
  meta TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, updated_at TEXT, title TEXT, body TEXT,
  links TEXT DEFAULT '[]', checks TEXT DEFAULT '[]', rev INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, seq INTEGER, speaker TEXT, text TEXT, created_at TEXT
);
-- Stage map S1–S8 (an overlay on P0–P7, written by stage.check at the end of every analysed round) and the
-- engagement profile (who asks, who uses, who runs, who decides — E1–E8 and the role map).
CREATE TABLE IF NOT EXISTS stages (
  id TEXT PRIMARY KEY, status TEXT, opened_at TEXT, closed_at TEXT, reopened INTEGER DEFAULT 0, gaps TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS engagement (
  id INTEGER PRIMARY KEY CHECK (id = 1), types TEXT DEFAULT '[]', roles TEXT DEFAULT '{}', confidence TEXT,
  evidence TEXT DEFAULT '[]', source TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_utt_round ON utterances(round);
CREATE INDEX IF NOT EXISTS ix_disp_run ON dispatches(run, stage);
CREATE INDEX IF NOT EXISTS ix_cand_round ON candidates(round);
CREATE INDEX IF NOT EXISTS ix_q_status ON questions(status);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(DDL)
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
    conn.execute("INSERT OR IGNORE INTO state(id) VALUES (1)")
    return conn


@contextmanager
def write_txn(conn: sqlite3.Connection) -> Iterator[None]:
    """One write transaction (BEGIN IMMEDIATE: read-then-write without another writer in between), unless the
    caller already holds one. The hooks, the planner and the dashboard write the same database."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def rows(conn: sqlite3.Connection, sql: str, args: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, tuple(args)).fetchall()]


def one(conn: sqlite3.Connection, sql: str, args: Iterable[Any] = ()) -> dict | None:
    r = conn.execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def scalar(conn: sqlite3.Connection, sql: str, args: Iterable[Any] = (), default: Any = None) -> Any:
    r = conn.execute(sql, tuple(args)).fetchone()
    return r[0] if r and r[0] is not None else default


def upsert(conn: sqlite3.Connection, table: str, data: dict, key: str | tuple[str, ...] = "id") -> None:
    cols = list(data)
    keys = (key,) if isinstance(key, str) else key
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in keys)
    sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({placeholders})"
    sql += f" ON CONFLICT({','.join(keys)}) DO " + (f"UPDATE SET {updates}" if updates else "NOTHING")
    conn.execute(sql, tuple(data[c] for c in cols))


def next_id(conn: sqlite3.Connection, table: str, prefix: str, width: int = 3) -> str:
    """Next human-friendly id like Q-007. Ids are never reused."""
    key = f"seq:{table}:{prefix}"
    cur = scalar(conn, "SELECT value FROM meta WHERE key=?", (key,), "0")
    n = int(cur) + 1
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(n)))
    return f"{prefix}{n:0{width}d}"


def bump(conn: sqlite3.Connection, table: str, prefix: str, explicit_id: str) -> None:
    """An agent chose an id itself (e.g. ADR-004): make sure generated ids never collide with it."""
    tail = str(explicit_id).removeprefix(prefix)
    if not tail.isdigit():
        return
    key = f"seq:{table}:{prefix}"
    cur = int(scalar(conn, "SELECT value FROM meta WHERE key=?", (key,), "0"))
    if int(tail) > cur:
        conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, str(int(tail))))
