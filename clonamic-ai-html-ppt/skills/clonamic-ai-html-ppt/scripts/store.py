"""SQLite store under ~/.clonamic/ai-html-ppt/: decks, nodes, the op log with undo data, assets, chat messages.

WAL: one write connection behind a lock, pooled read connections that run alongside it.
"""

from __future__ import annotations

import hashlib
import json
import queue
import secrets
import sqlite3
import struct
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import ops

HISTORY = 100  # undoable batches kept per deck
REPLAY = 1000  # newest op batches kept per deck for SSE replay (undoable ones are always kept)
UNDONE_NO, UNDONE_YES, UNDONE_DEAD = 0, 1, 2  # ops.undone: active, on the redo stack, not undoable

SQL = """
CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, seq INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS nodes (
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    id TEXT NOT NULL, parent TEXT, z TEXT NOT NULL, type TEXT NOT NULL, props TEXT NOT NULL, rev INTEGER NOT NULL,
    PRIMARY KEY (deck_id, id),
    FOREIGN KEY (deck_id, parent) REFERENCES nodes(deck_id, id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(deck_id, parent, z);
CREATE TABLE IF NOT EXISTS ops (
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE, seq INTEGER NOT NULL,
    actor TEXT NOT NULL, client TEXT NOT NULL, label TEXT NOT NULL, ops TEXT NOT NULL, inverse TEXT,
    undone INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, PRIMARY KEY (deck_id, seq));
CREATE TABLE IF NOT EXISTS assets (hash TEXT PRIMARY KEY, mime TEXT NOT NULL, w INTEGER, h INTEGER, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    role TEXT NOT NULL, text TEXT NOT NULL, meta TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS messages_deck ON messages(deck_id, status, id);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE, graph TEXT NOT NULL,
    node TEXT NOT NULL, status TEXT NOT NULL, state TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', tries INTEGER NOT NULL DEFAULT 0,
    message_id INTEGER, notify INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS runs_deck ON runs(deck_id, id);
CREATE TABLE IF NOT EXISTS steps (
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE, n INTEGER NOT NULL, node TEXT NOT NULL,
    status TEXT NOT NULL, detail TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY (run_id, n));
CREATE TABLE IF NOT EXISTS focus (
    id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE, page TEXT NOT NULL,
    ids TEXT NOT NULL, rect TEXT, note TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
"""
FOCUS_STATUS = ("open", "sent", "resolved")


def data_dir() -> Path:
    return Path.home() / ".clonamic" / "ai-html-ppt"


class NotFound(Exception):
    """No such deck."""


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, autocommit=True, check_same_thread=False, timeout=10)
    db.row_factory = sqlite3.Row
    for pragma in ("journal_mode=WAL", "synchronous=NORMAL", "foreign_keys=ON", "busy_timeout=10000"):
        db.execute("PRAGMA " + pragma)
    return db


def sniff(data: bytes) -> tuple[str, int | None, int | None] | None:
    """(mime, w, h) for PNG/JPEG/GIF/WebP (dims) and MP4/WebM (no dims); anything else (SVG too) is None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return ("image/png", *struct.unpack(">II", data[16:24]))
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ("image/gif", *struct.unpack("<HH", data[6:10]))
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 ":
            w, h = struct.unpack("<HH", data[26:30])
            return "image/webp", w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return "image/webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            return "image/webp", int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
        return None
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 <= len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01, 0xFF) or 0xD0 <= marker <= 0xD7:
                i += 1 if marker == 0xFF else 2
                continue
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "image/jpeg", w, h
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        return None
    if data[4:8] == b"ftyp":
        return "video/mp4", None, None
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm", None, None
    return None


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "ppt.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = connect(self.path)
        self.db.executescript(SQL)
        self.readers: queue.SimpleQueue = queue.SimpleQueue()

    def close(self) -> None:
        with self.lock:
            self.db.close()
            while not self.readers.empty():
                self.readers.get_nowait().close()

    @contextmanager
    def write(self):
        """The one write transaction at a time; rolls back on any error."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")

    @contextmanager
    def read(self):
        """A consistent snapshot on a pooled read connection (WAL: never waits for the writer)."""
        try:
            db = self.readers.get_nowait()
        except queue.Empty:
            db = connect(self.path)
        try:
            db.execute("BEGIN")
            try:
                yield db
            finally:
                db.execute("COMMIT")
        finally:
            self.readers.put(db)

    # decks
    def decks(self) -> list[dict]:
        with self.read() as db:
            rows = db.execute("""SELECT d.id, d.name, d.updated,
                (SELECT count(*) FROM nodes n WHERE n.deck_id = d.id AND n.parent IS NULL) AS pages
                FROM decks d ORDER BY d.updated DESC, d.id DESC""").fetchall()
        return [dict(r) for r in rows]

    def create_deck(self, name: str, preset: str = "SLIDE_16_9") -> int:
        w, h = ops.SCHEMA["presets"][preset]
        props = {"name": "페이지 1", "preset": preset, "w": w, "h": h, "orientation": "landscape" if w >= h else "portrait"}
        now = time.time()
        with self.write() as db:
            deck = db.execute("INSERT INTO decks (name, created, updated) VALUES (?, ?, ?)", (name, now, now)).lastrowid
            db.execute("INSERT INTO nodes (deck_id, id, parent, z, type, props, rev) VALUES (?, ?, NULL, ?, 'page', ?, 0)",
                       (deck, "p_" + secrets.token_hex(4), ops.z_between(None, None), json.dumps(props, ensure_ascii=False)))
        return deck

    def delete_deck(self, deck: int) -> None:
        with self.write() as db:
            if not db.execute("DELETE FROM decks WHERE id = ?", (deck,)).rowcount:
                raise NotFound(deck)

    @staticmethod
    def _deck_row(db, deck: int) -> dict:
        row = db.execute("SELECT id, name, seq FROM decks WHERE id = ?", (deck,)).fetchone()
        if row is None:
            raise NotFound(deck)
        return dict(row)

    def deck(self, deck: int) -> dict:
        """{deck:{id, name, seq}, nodes:[...]} from one snapshot."""
        with self.read() as db:
            head = self._deck_row(db, deck)
            rows = db.execute("SELECT * FROM nodes WHERE deck_id = ?", (deck,)).fetchall()
        return {"deck": head, "nodes": [ops.node_dict(r) for r in rows]}

    def pages(self, deck: int) -> list[dict]:
        """Pages in order: [{id, name}]."""
        with self.read() as db:
            self._deck_row(db, deck)
            rows = db.execute("SELECT * FROM nodes WHERE deck_id = ? AND parent IS NULL ORDER BY z, id", (deck,)).fetchall()
        return [{"id": r["id"], "name": json.loads(r["props"]).get("name", "Page")} for r in rows]

    def nodes(self, deck: int, ids: list[str] | None = None, pages: list[str] | None = None) -> dict:
        """{deck, seq, nodes}: the given ids, or the given pages with their subtrees."""
        with self.read() as db:
            head = self._deck_row(db, deck)
            rows = []
            for nid in ids or []:
                rows += db.execute("SELECT * FROM nodes WHERE deck_id = ? AND id = ?", (deck, nid)).fetchall()
            for page in pages or []:
                rows += ops.subtree(db, deck, page)
        return {"deck": head, "seq": head["seq"], "nodes": [ops.node_dict(r) for r in rows]}

    # op log
    def _log(self, db, deck: int, seq: int, meta: dict, applied: list, inverse: list | None, undone: int) -> None:
        db.execute("INSERT INTO ops (deck_id, seq, actor, client, label, ops, inverse, undone, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (deck, seq, meta["actor"], meta["client"], meta["label"], json.dumps(applied, ensure_ascii=False),
                    None if inverse is None else json.dumps(inverse, ensure_ascii=False), undone, time.time()))
        db.execute("UPDATE decks SET seq = ?, updated = ? WHERE id = ?", (seq, time.time(), deck))
        # Undo depth: drop the inverse of everything older than the newest HISTORY undoable batches.
        cut = db.execute("SELECT seq FROM ops WHERE deck_id = ? AND inverse IS NOT NULL ORDER BY seq DESC LIMIT 1 OFFSET ?",
                         (deck, HISTORY)).fetchone()
        if cut:
            db.execute("UPDATE ops SET inverse = NULL, undone = ? WHERE deck_id = ? AND inverse IS NOT NULL AND seq <= ?",
                       (UNDONE_DEAD, deck, cut[0]))
        db.execute("DELETE FROM ops WHERE deck_id = ? AND seq <= ? AND inverse IS NULL", (deck, seq - REPLAY))

    def _next(self, db, deck: int) -> int:
        return self._deck_row(db, deck)["seq"] + 1

    @staticmethod
    def _event(seq: int, meta: dict, applied: list, revs: dict) -> dict:
        return {"seq": seq, "revs": revs, "event": {"seq": seq, **meta, "ops": applied}}

    def commit(self, deck: int, batch, meta: dict) -> dict:
        """Apply a new batch; clears the redo stack. meta = {actor, client, label}."""
        with self.write() as db:
            seq = self._next(db, deck)
            applied, inverse, revs = ops.apply(db, deck, batch, seq)
            db.execute("UPDATE ops SET undone = ?, inverse = NULL WHERE deck_id = ? AND undone = ?", (UNDONE_DEAD, deck, UNDONE_YES))
            self._log(db, deck, seq, meta, applied, inverse, UNDONE_NO)
        return self._event(seq, meta, applied, revs)

    def _undo_row(self, db, deck: int, row, meta: dict) -> dict:
        seq = self._next(db, deck)
        applied, _, revs = ops.apply(db, deck, json.loads(row["inverse"]), seq)
        db.execute("UPDATE ops SET undone = ? WHERE deck_id = ? AND seq = ?", (UNDONE_YES, deck, row["seq"]))
        self._log(db, deck, seq, meta | {"label": "undo"}, applied, None, UNDONE_DEAD)
        return self._event(seq, meta | {"label": "undo"}, applied, revs)

    def _undoable(self, db, deck: int, limit: int) -> list:
        return db.execute("SELECT seq, inverse FROM ops WHERE deck_id = ? AND undone = ? AND inverse IS NOT NULL "
                          "ORDER BY seq DESC LIMIT ?", (deck, UNDONE_NO, limit)).fetchall()

    def undo(self, deck: int, meta: dict) -> dict | None:
        """Apply the inverse of the newest batch not yet undone (any actor); None when there is none."""
        with self.write() as db:
            self._deck_row(db, deck)
            rows = self._undoable(db, deck, 1)
            return self._undo_row(db, deck, rows[0], meta) if rows else None

    def undo_run(self, deck: int, seqs: list[int], meta: dict) -> list[dict] | None:
        """Undo exactly these batches in one transaction, only if they are the newest undoable ones; else None."""
        with self.write() as db:
            self._deck_row(db, deck)
            rows = self._undoable(db, deck, len(seqs)) if seqs else []
            if not rows or sorted(r["seq"] for r in rows) != sorted(seqs):
                return None
            return [self._undo_row(db, deck, r, meta) for r in rows]

    def amend(self, deck: int, seq: int, batch: list) -> dict | None:
        """Fold extra ops into batch `seq` (still the newest, not undone): same seq and history entry, one undo reverts
        both. None when something else came after it."""
        with self.write() as db:
            head = self._deck_row(db, deck)
            row = db.execute("SELECT * FROM ops WHERE deck_id = ? AND seq = ? AND undone = ? AND inverse IS NOT NULL",
                             (deck, seq, UNDONE_NO)).fetchone()
            if row is None or head["seq"] != seq:
                return None
            applied, inverse, revs = ops.apply(db, deck, batch, seq)
            db.execute("UPDATE ops SET ops = ?, inverse = ? WHERE deck_id = ? AND seq = ?",
                       (json.dumps(json.loads(row["ops"]) + applied, ensure_ascii=False),
                        json.dumps(inverse + json.loads(row["inverse"]), ensure_ascii=False), deck, seq))
            db.execute("UPDATE decks SET updated = ? WHERE id = ?", (time.time(), deck))
        meta = {"actor": row["actor"], "client": row["client"], "label": row["label"]}
        return {"seq": seq, "revs": revs, "event": {"seq": seq, **meta, "ops": applied, "amend": True}}

    def redo(self, deck: int, meta: dict) -> dict | None:
        """Re-apply the most recently undone batch; None when the redo stack is empty."""
        with self.write() as db:
            seq = self._next(db, deck)
            row = db.execute("SELECT seq, ops FROM ops WHERE deck_id = ? AND undone = ? ORDER BY seq LIMIT 1",
                             (deck, UNDONE_YES)).fetchone()
            if row is None:
                return None
            applied, inverse, revs = ops.apply(db, deck, ops.strip_revs(json.loads(row["ops"])), seq)
            db.execute("UPDATE ops SET undone = ?, inverse = ? WHERE deck_id = ? AND seq = ?",
                       (UNDONE_NO, json.dumps(inverse, ensure_ascii=False), deck, row["seq"]))
            self._log(db, deck, seq, meta | {"label": "redo"}, applied, None, UNDONE_DEAD)
        return self._event(seq, meta | {"label": "redo"}, applied, revs)

    def replay(self, deck: int, after: int) -> list[dict] | None:
        """ops events after seq `after`, or None when some are gone (the client must reset)."""
        with self.read() as db:
            head = self._deck_row(db, deck)
            if not 0 <= after <= head["seq"]:
                return None
            rows = db.execute("SELECT * FROM ops WHERE deck_id = ? AND seq > ? ORDER BY seq", (deck, after)).fetchall()
        if len(rows) != head["seq"] - after:
            return None
        return [{"seq": r["seq"], "actor": r["actor"], "client": r["client"], "label": r["label"], "ops": json.loads(r["ops"])}
                for r in rows]

    # assets
    def put_asset(self, data: bytes) -> dict:
        """Store image/video bytes once (by sha256). ValueError for anything that is not PNG/JPEG/GIF/WebP/MP4/WebM."""
        kind = sniff(data)
        if kind is None:
            raise ValueError("PNG, JPEG, GIF, WebP 이미지나 MP4, WebM 동영상만 받습니다(SVG는 받지 않습니다).")
        mime, w, h = kind
        digest = hashlib.sha256(data).hexdigest()
        with self.write() as db:
            db.execute("INSERT OR IGNORE INTO assets (hash, mime, w, h, data) VALUES (?, ?, ?, ?, ?)", (digest, mime, w, h, data))
        return {"hash": digest, "mime": mime} | ({"w": w, "h": h} if w is not None else {})

    def asset(self, digest: str) -> dict | None:
        with self.read() as db:
            row = db.execute("SELECT mime, data FROM assets WHERE hash = ?", (digest,)).fetchone()
        return dict(row) if row else None

    def has_asset(self, digest: str) -> bool:
        with self.read() as db:
            return db.execute("SELECT 1 FROM assets WHERE hash = ?", (digest,)).fetchone() is not None

    # focus pins (format.md §9.4): not nodes, never rendered
    @staticmethod
    def _pin(r) -> dict:
        return {"id": r["id"], "page": r["page"], "ids": json.loads(r["ids"]), "rect": json.loads(r["rect"]) if r["rect"] else None,
                "note": r["note"], "status": r["status"], "created": r["created"], "updated": r["updated"]}

    def pins(self, deck: int, ids: list[int] | None = None) -> list[dict]:
        with self.read() as db:
            self._deck_row(db, deck)
            rows = db.execute("SELECT * FROM focus WHERE deck_id = ? ORDER BY id", (deck,)).fetchall()
        return [self._pin(r) for r in rows if ids is None or r["id"] in ids]

    def add_pin(self, deck: int, page: str, ids: list[str], rect: dict | None, note: str) -> int:
        now = time.time()
        with self.write() as db:
            self._deck_row(db, deck)
            return db.execute("INSERT INTO focus (deck_id, page, ids, rect, note, status, created, updated) VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
                              (deck, page, json.dumps(ids), None if rect is None else json.dumps(rect), note, now, now)).lastrowid

    def update_pin(self, deck: int, pin: int, note: str | None = None, status: str | None = None) -> bool:
        with self.write() as db:
            return bool(db.execute("UPDATE focus SET note = coalesce(?, note), status = coalesce(?, status), updated = ? "
                                   "WHERE deck_id = ? AND id = ?", (note, status, time.time(), deck, pin)).rowcount)

    def delete_pin(self, deck: int, pin: int) -> bool:
        with self.write() as db:
            return bool(db.execute("DELETE FROM focus WHERE deck_id = ? AND id = ?", (deck, pin)).rowcount)

    # messages: user text status new|taken (the AI's queue); ai text has no status
    def add_message(self, deck: int, role: str, text: str, meta: dict) -> dict:
        now = time.time()
        status = "new" if role == "user" else ""
        with self.write() as db:
            self._deck_row(db, deck)
            mid = db.execute("INSERT INTO messages (deck_id, role, text, meta, status, created) VALUES (?, ?, ?, ?, ?, ?)",
                             (deck, role, text, json.dumps(meta, ensure_ascii=False), status, now)).lastrowid
        return {"id": mid, "role": role, "text": text, "meta": meta, "status": status, "created": now}

    def messages(self, deck: int, limit: int = 200) -> list[dict]:
        with self.read() as db:
            self._deck_row(db, deck)
            rows = db.execute("SELECT * FROM messages WHERE deck_id = ? ORDER BY id DESC LIMIT ?", (deck, limit)).fetchall()
        return [self._message(r) for r in reversed(rows)]

    @staticmethod
    def _message(r) -> dict:
        return {"id": r["id"], "role": r["role"], "text": r["text"], "meta": json.loads(r["meta"]), "status": r["status"],
                "created": r["created"]}

    def take(self, deck: int) -> dict | None:
        """Oldest user message the AI has not handled yet, marked taken."""
        with self.write() as db:
            r = db.execute("SELECT * FROM messages WHERE deck_id = ? AND status = 'new' ORDER BY id LIMIT 1", (deck,)).fetchone()
            if r:
                db.execute("UPDATE messages SET status = 'taken' WHERE id = ?", (r["id"],))
        return self._message(r) | {"status": "taken"} if r else None
