"""SQLite store under ~/.clonamic/create-agent/. One project = one JSON document + a version number."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import schema


HISTORY = 100  # saved versions kept per project (the editor autosaves, so this is the last stretch of editing)


def data_dir() -> Path:
    return Path.home() / ".clonamic" / "create-agent"


class Conflict(Exception):
    """The document changed since the caller read it."""


class Store:
    def __init__(self, path: Path | None = None):
        path = path or data_dir() / "create-agent.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock, self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY, doc TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                    export_path TEXT NOT NULL DEFAULT '', polished_version INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, role TEXT NOT NULL, kind TEXT NOT NULL,
                    body TEXT NOT NULL, status TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    project_id INTEGER NOT NULL, version INTEGER NOT NULL, doc TEXT NOT NULL,
                    PRIMARY KEY (project_id, version));
                CREATE TABLE IF NOT EXISTS changelog (
                    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, date TEXT NOT NULL,
                    what TEXT NOT NULL, why TEXT NOT NULL, affected TEXT NOT NULL);
            """)

    # projects
    # One connection is shared by the server's threads, so reads take the same lock as writes
    # (an unlocked read during a write can come back empty).
    def read(self, sql: str, args: tuple = ()) -> list:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def projects(self) -> list[dict]:
        rows = self.read("SELECT id, doc, updated FROM projects ORDER BY updated DESC")
        return [{"id": r["id"], "name": json.loads(r["doc"]).get("name", ""), "updated": r["updated"]} for r in rows]

    def create(self, name: str, doc: dict | None = None) -> int:
        doc = schema.migrate(doc) if doc else schema.new_project(name)
        now = time.time()
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO projects (doc, created, updated) VALUES (?, ?, ?)",
                                  (json.dumps(doc, ensure_ascii=False), now, now))
        return cur.lastrowid

    def get(self, pid: int) -> dict | None:
        rows = self.read("SELECT * FROM projects WHERE id = ?", (pid,))
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "doc": schema.migrate(json.loads(r["doc"])), "version": r["version"], "export_path": r["export_path"],
                "polished": r["polished_version"] == r["version"]}

    def save(self, pid: int, doc: dict, version: int, polished: bool = False) -> int:
        with self.lock, self.db:
            r = self.db.execute("SELECT version FROM projects WHERE id = ?", (pid,)).fetchone()
            if not r:
                raise KeyError(pid)
            if r["version"] != version:
                raise Conflict(r["version"])
            new = version + 1
            text = json.dumps(doc, ensure_ascii=False)
            self.db.execute("UPDATE projects SET doc = ?, version = ?, updated = ?"
                            + (", polished_version = ?" if polished else "") + " WHERE id = ?",
                            (text, new, time.time(), *([new] if polished else []), pid))
            # Recent versions let a proposal made from a slightly older read still be turned into a patch.
            self.db.execute("INSERT OR REPLACE INTO history (project_id, version, doc) VALUES (?, ?, ?)", (pid, new, text))
            self.db.execute("DELETE FROM history WHERE project_id = ? AND version <= ?", (pid, new - HISTORY))
        return new

    def at_version(self, pid: int, version: int) -> dict | None:
        """The document as it was at `version` (current or one of the last HISTORY saves), or None."""
        proj = self.get(pid)
        if proj and proj["version"] == version:
            return proj["doc"]
        rows = self.read("SELECT doc FROM history WHERE project_id = ? AND version = ?", (pid, version))
        return schema.migrate(json.loads(rows[0]["doc"])) if rows else None

    def set_export_path(self, pid: int, path: str) -> None:
        with self.lock, self.db:
            self.db.execute("UPDATE projects SET export_path = ? WHERE id = ?", (path, pid))

    def delete(self, pid: int) -> None:
        with self.lock, self.db:
            for table in ("messages", "changelog", "history"):
                self.db.execute(f"DELETE FROM {table} WHERE project_id = ?", (pid,))
            self.db.execute("DELETE FROM projects WHERE id = ?", (pid,))

    # messages: role user|ai|system, kind text|card|notice|polish; user text status new|taken, card pending|applied|dismissed
    def add_message(self, pid: int, role: str, kind: str, body: dict, status: str = "") -> int:
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO messages (project_id, role, kind, body, status, created) VALUES (?, ?, ?, ?, ?, ?)",
                                  (pid, role, kind, json.dumps(body, ensure_ascii=False), status, time.time()))
        return cur.lastrowid

    def messages(self, pid: int, after: int = 0) -> list[dict]:
        rows = self.read("SELECT * FROM messages WHERE project_id = ? AND id > ? ORDER BY id", (pid, after))
        return [self._message(r) for r in rows]

    def message(self, mid: int) -> dict | None:
        rows = self.read("SELECT * FROM messages WHERE id = ?", (mid,))
        return self._message(rows[0]) if rows else None

    @staticmethod
    def _message(r) -> dict:
        return {"id": r["id"], "project_id": r["project_id"], "role": r["role"], "kind": r["kind"],
                "body": json.loads(r["body"]), "status": r["status"], "created": r["created"]}

    def take(self, pid: int) -> dict | None:
        """Oldest message the AI has not handled yet (user text or a polish request), marked as taken."""
        with self.lock, self.db:
            r = self.db.execute("SELECT * FROM messages WHERE project_id = ? AND status = 'new' ORDER BY id LIMIT 1",
                                (pid,)).fetchone()
            if r:
                self.db.execute("UPDATE messages SET status = 'taken' WHERE id = ?", (r["id"],))
        return self._message(r) if r else None

    def set_status(self, mid: int, status: str) -> None:
        with self.lock, self.db:
            self.db.execute("UPDATE messages SET status = ? WHERE id = ?", (status, mid))

    # changelog
    def log(self, pid: int, date: str, what: str, why: str, affected: str) -> None:
        with self.lock, self.db:
            self.db.execute("INSERT INTO changelog (project_id, date, what, why, affected) VALUES (?, ?, ?, ?, ?)",
                            (pid, date, what, why, affected))

    def changelog(self, pid: int) -> list[dict]:
        rows = self.read("SELECT * FROM changelog WHERE project_id = ? ORDER BY id", (pid,))
        return [dict(r) for r in rows]
