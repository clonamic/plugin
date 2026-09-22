#!/usr/bin/env python3
"""Explicit local memory and ontology operations."""

from __future__ import annotations

import argparse
import heapq
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000
DATABASE_MODE = 0o600
MAX_DEPTH = 4
MAX_NODES = 100
SOURCE_KINDS = ("user", "automation", "internal", "unverified")
SOURCE_KIND_SQL = ", ".join(f"'{value}'" for value in SOURCE_KINDS)

TABLES = (
    f"""
    CREATE TABLE IF NOT EXISTS prompt_sources (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence >= 0),
        source_kind TEXT NOT NULL CHECK (source_kind IN ({SOURCE_KIND_SQL})),
        body_sha256 TEXT NOT NULL CHECK (length(body_sha256) = 64),
        body_bytes INTEGER NOT NULL CHECK (body_bytes >= 0),
        expires_at TEXT,
        UNIQUE (session_id, sequence)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        tags TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        source_id TEXT REFERENCES prompt_sources(id) ON DELETE SET NULL,
        expires_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edges (
        source TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        target TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
        relation TEXT NOT NULL,
        source_id TEXT REFERENCES prompt_sources(id) ON DELETE SET NULL,
        expires_at TEXT,
        PRIMARY KEY (source, target, relation)
    )
    """,
    "CREATE INDEX IF NOT EXISTS edges_source ON edges(source)",
    "CREATE INDEX IF NOT EXISTS edges_target ON edges(target)",
    "CREATE INDEX IF NOT EXISTS memories_expires ON memories(expires_at)",
    "CREATE INDEX IF NOT EXISTS edges_expires ON edges(expires_at)",
    "CREATE INDEX IF NOT EXISTS prompt_sources_expires ON prompt_sources(expires_at)",
)

FTS = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(id UNINDEXED, content, tags)",
    """
    CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts (id, content, tags) VALUES (new.id, new.content, new.tags);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories BEGIN
        DELETE FROM memories_fts WHERE id = old.id;
        INSERT INTO memories_fts (id, content, tags) VALUES (new.id, new.content, new.tags);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
        DELETE FROM memories_fts WHERE id = old.id;
    END
    """,
)


def record_source(
    path: str | Path,
    source_id: str,
    session_id: str,
    sequence: int,
    source_kind: str,
    body_sha256: str,
    body_bytes: int,
    *,
    expires_at: str | None = None,
) -> dict[str, Any]:
    resolved_id = _required(source_id, "source_id")
    resolved_session = _required(session_id, "session_id")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")
    resolved_kind = _required(source_kind, "source_kind")
    if resolved_kind not in SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {', '.join(sorted(SOURCE_KINDS))}")
    if not isinstance(body_sha256, str) or re.fullmatch(r"[0-9a-fA-F]{64}", body_sha256) is None:
        raise ValueError("body_sha256 must be 64 hexadecimal characters")
    if isinstance(body_bytes, bool) or not isinstance(body_bytes, int) or body_bytes < 0:
        raise ValueError("body_bytes must be a non-negative integer")
    resolved_expiry = _timestamp(expires_at, "expires_at")
    with _database(path) as connection:
        connection.execute(
            """
            INSERT INTO prompt_sources
                (id, session_id, sequence, source_kind, body_sha256, body_bytes, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_id,
                resolved_session,
                sequence,
                resolved_kind,
                body_sha256.lower(),
                body_bytes,
                resolved_expiry,
            ),
        )
        row = connection.execute("SELECT * FROM prompt_sources WHERE id = ?", (resolved_id,)).fetchone()
    return dict(row)


def store(
    path: str | Path,
    memory_id: str,
    content: str,
    tags: Iterable[str],
    *,
    source_id: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    resolved_id = _required(memory_id, "id")
    resolved_content = _required(content, "content")
    resolved_tags = _tags(tags)
    resolved_source = _required(source_id, "source_id")
    resolved_expiry = _timestamp(expires_at, "expires_at")
    now = _now()
    with _database(path) as connection:
        _require_source(connection, resolved_source)
        connection.execute(
            """
            INSERT INTO memories (id, content, tags, created_at, updated_at, source_id, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                tags = excluded.tags,
                updated_at = excluded.updated_at,
                source_id = excluded.source_id,
                expires_at = excluded.expires_at
            """,
            (
                resolved_id,
                resolved_content,
                json.dumps(resolved_tags, ensure_ascii=False),
                now,
                now,
                resolved_source,
                resolved_expiry,
            ),
        )
        row = connection.execute("SELECT * FROM memories WHERE id = ?", (resolved_id,)).fetchone()
    return _memory(row)


def recall(path: str | Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    resolved_query = _required(query, "query")
    terms = set(_tokens(resolved_query))
    _bounded(limit, "limit", 1, MAX_NODES)
    with _database(path, write=False) as connection:
        rows = _recall_candidates(connection, resolved_query, terms)
        scored = _rank_candidates(rows, resolved_query, terms, limit)
    output = []
    for score, _, row in scored:
        item = _memory(row)
        item["score"] = score
        output.append(item)
    return output


def _rank_candidates(
    rows: Iterable[sqlite3.Row], query: str, terms: set[str], limit: int
) -> list[tuple[int, str, sqlite3.Row]]:
    folded_query = query.casefold()

    def matches():
        for row in rows:
            tags = json.loads(row["tags"])
            haystack = f"{row['content']} {' '.join(tags)}".casefold()
            overlap = len(terms.intersection(_tokens(haystack)))
            score = overlap * 10 + (5 if folded_query in haystack else 0)
            if score:
                yield score, row["updated_at"], row

    return heapq.nsmallest(
        limit,
        matches(),
        key=lambda entry: (-entry[0], entry[1], entry[2]["id"]),
    )


def forget(path: str | Path, memory_id: str) -> bool:
    resolved_id = _required(memory_id, "id")
    with _database(path) as connection:
        cursor = connection.execute("DELETE FROM memories WHERE id = ?", (resolved_id,))
    return cursor.rowcount == 1


def link(
    path: str | Path,
    source: str,
    target: str,
    relation: str,
    *,
    source_id: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    resolved_source = _required(source, "source")
    resolved_target = _required(target, "target")
    resolved_relation = _required(relation, "relation")
    resolved_provenance = _required(source_id, "source_id")
    resolved_expiry = _timestamp(expires_at, "expires_at")
    if resolved_source == resolved_target:
        raise ValueError("self edges are not allowed")
    with _database(path) as connection:
        _require_source(connection, resolved_provenance)
        existing = {
            row["id"]
            for row in connection.execute(
                "SELECT id FROM memories WHERE id IN (?, ?)",
                (resolved_source, resolved_target),
            )
        }
        missing = {resolved_source, resolved_target} - existing
        if missing:
            raise KeyError(",".join(sorted(missing)))
        connection.execute(
            """
            INSERT INTO edges (source, target, relation, source_id, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, target, relation) DO UPDATE SET
                source_id = excluded.source_id,
                expires_at = excluded.expires_at
            """,
            (resolved_source, resolved_target, resolved_relation, resolved_provenance, resolved_expiry),
        )
    return {
        "source": resolved_source,
        "target": resolved_target,
        "relation": resolved_relation,
        "source_id": resolved_provenance,
        "expires_at": resolved_expiry,
    }


def graph(path: str | Path, anchor: str, *, depth: int = 2, limit: int = 20) -> dict[str, Any]:
    resolved_anchor = _required(anchor, "anchor")
    _bounded(depth, "depth", 0, MAX_DEPTH)
    _bounded(limit, "limit", 1, MAX_NODES)
    with _database(path, write=False) as connection:
        if connection.execute("SELECT 1 FROM memories WHERE id = ?", (resolved_anchor,)).fetchone() is None:
            raise KeyError(resolved_anchor)
        nodes = connection.execute(
            """
            WITH RECURSIVE walk(id, depth) AS (
                SELECT ? AS id, 0 AS depth
                UNION
                SELECT
                    CASE WHEN edges.source = walk.id THEN edges.target ELSE edges.source END AS id,
                    walk.depth + 1 AS depth
                FROM walk
                JOIN edges ON edges.source = walk.id OR edges.target = walk.id
                WHERE walk.depth < ?
            ), ranked AS (
                SELECT id, MIN(depth) AS depth FROM walk GROUP BY id
            )
            SELECT memories.*, ranked.depth
            FROM ranked JOIN memories ON memories.id = ranked.id
            ORDER BY ranked.depth, memories.id
            LIMIT ?
            """,
            (resolved_anchor, depth, limit),
        ).fetchall()
        order = [row["id"] for row in nodes]
        placeholders = ",".join("?" for _ in order)
        edges = connection.execute(
            f"""
            SELECT source, target, relation, source_id, expires_at FROM edges
            WHERE source IN ({placeholders}) AND target IN ({placeholders})
            ORDER BY source, target, relation
            """,
            tuple(order) + tuple(order),
        ).fetchall()
    return {
        "nodes": [_memory(row) for row in nodes],
        "edges": [dict(row) for row in edges],
    }


def prune(path: str | Path, *, before: str | None = None) -> dict[str, int]:
    cutoff = _timestamp(before, "before") if before is not None else _now()
    with _database(path) as connection:
        edges = connection.execute(
            "DELETE FROM edges WHERE expires_at IS NOT NULL AND expires_at <= ?", (cutoff,)
        ).rowcount
        memories = connection.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?", (cutoff,)
        ).rowcount
        sources = connection.execute(
            """
            DELETE FROM prompt_sources
            WHERE expires_at IS NOT NULL AND expires_at <= ?
              AND NOT EXISTS (SELECT 1 FROM memories WHERE memories.source_id = prompt_sources.id)
              AND NOT EXISTS (SELECT 1 FROM edges WHERE edges.source_id = prompt_sources.id)
            """,
            (cutoff,),
        ).rowcount
    return {"memories": memories, "edges": edges, "prompt_sources": sources}


def backup(path: str | Path, destination: str | Path) -> dict[str, Any]:
    source_path = _existing_path(path)
    target = _path(destination)
    if source_path.resolve() == target.resolve(strict=False):
        raise ValueError("backup destination must differ from database path")
    connection = _connect(source_path)
    try:
        _atomic_backup(connection, target)
    finally:
        connection.close()
    return {"path": str(target), "bytes": target.stat().st_size}


def restore(path: str | Path, snapshot: str | Path) -> dict[str, Any]:
    target = _path(path)
    source_path = _existing_path(snapshot)
    if source_path.resolve() == target.resolve(strict=False):
        raise ValueError("restore source must differ from database path")
    temp = _temporary_path(target)
    try:
        source = sqlite3.connect(source_path)
        try:
            _check_snapshot(source)
            _copy_database(source, temp)
        finally:
            source.close()
        migrated = _connect(temp, backup_legacy=False)
        try:
            _quick_check(migrated)
        finally:
            migrated.close()
        _fsync(temp)
        _reject_symlink(target)
        os.replace(temp, target)
        os.chmod(target, DATABASE_MODE)
        _remove_sidecars(target)
        _fsync_directory(target.parent)
    finally:
        _remove_database_files(temp)
    return {"path": str(target), "bytes": target.stat().st_size}


def _connect(path: str | Path, *, backup_legacy: bool = True) -> sqlite3.Connection:
    target = _database_path(path)
    connection = sqlite3.connect(target, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA foreign_keys = ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"database schema {version} is newer than supported schema {SCHEMA_VERSION}"
            )
        os.chmod(target, DATABASE_MODE)
        if version == 0:
            _migrate(connection, target, backup_legacy=backup_legacy)
        _validate_current_schema(connection)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection
    except BaseException:
        connection.close()
        raise


@contextmanager
def _database(path: str | Path, *, write: bool = True):
    connection = _connect(path)
    try:
        if write:
            connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            if write:
                connection.rollback()
            raise
        else:
            if write:
                connection.commit()
    finally:
        connection.close()


def _migrate(connection: sqlite3.Connection, target: Path, *, backup_legacy: bool) -> None:
    existing = _table_names(connection)
    legacy = bool({"memories", "edges"} & existing)
    if legacy:
        _validate_legacy_schema(connection)
        if backup_legacy:
            backup_path = target.with_name(f"{target.name}.pre-v{SCHEMA_VERSION}.bak")
            _atomic_backup(connection, backup_path)
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"database schema {version} is newer than supported schema {SCHEMA_VERSION}"
            )
        if version == SCHEMA_VERSION:
            connection.commit()
            return
        existing = _table_names(connection)
        if {"memories", "edges"} & existing:
            _validate_legacy_schema(connection)
            connection.execute(TABLES[0])
            _add_column(connection, "memories", "source_id", "TEXT REFERENCES prompt_sources(id) ON DELETE SET NULL")
            _add_column(connection, "memories", "expires_at", "TEXT")
            _add_column(connection, "edges", "source_id", "TEXT REFERENCES prompt_sources(id) ON DELETE SET NULL")
            _add_column(connection, "edges", "expires_at", "TEXT")
            for statement in TABLES[3:]:
                connection.execute(statement)
        else:
            for statement in TABLES:
                connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        _create_fts(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _create_fts(connection: sqlite3.Connection) -> None:
    try:
        for statement in FTS:
            connection.execute(statement)
        connection.execute("DELETE FROM memories_fts")
        connection.execute("INSERT INTO memories_fts (id, content, tags) SELECT id, content, tags FROM memories")
    except sqlite3.OperationalError as exc:
        if "fts5" not in str(exc).casefold():
            raise


def _recall_candidates(
    connection: sqlite3.Connection, query: str, terms: set[str]
) -> Iterable[sqlite3.Row]:
    has_fts = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memories_fts'"
    ).fetchone()
    if not terms or has_fts is None or not query.isascii():
        return connection.execute("SELECT * FROM memories")
    match = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in sorted(terms))
    return connection.execute(
        """
        SELECT * FROM memories WHERE id IN (
            SELECT id FROM memories_fts WHERE memories_fts MATCH ?
            UNION
            SELECT id FROM memories
            WHERE instr(lower(content || ' ' || tags), lower(?)) > 0
            UNION
            SELECT id FROM memories
            WHERE length(CAST(content AS BLOB)) > length(content)
               OR length(CAST(tags AS BLOB)) > length(tags)
        )
        """,
        (match, query),
    )


def _require_source(connection: sqlite3.Connection, source_id: str) -> None:
    if connection.execute("SELECT 1 FROM prompt_sources WHERE id = ?", (source_id,)).fetchone() is None:
        raise KeyError(source_id)


def _validate_legacy_schema(connection: sqlite3.Connection) -> None:
    expected = {
        "memories": {"id", "content", "tags", "created_at", "updated_at"},
        "edges": {"source", "target", "relation"},
    }
    existing = _table_names(connection)
    if set(expected) - existing:
        raise sqlite3.DatabaseError("legacy database is missing required tables")
    for table, columns in expected.items():
        if columns - _columns(connection, table):
            raise sqlite3.DatabaseError(f"legacy table {table} is missing required columns")


def _validate_current_schema(connection: sqlite3.Connection) -> None:
    expected = {
        "prompt_sources": {
            "id",
            "session_id",
            "sequence",
            "source_kind",
            "body_sha256",
            "body_bytes",
            "expires_at",
        },
        "memories": {"id", "content", "tags", "created_at", "updated_at", "source_id", "expires_at"},
        "edges": {"source", "target", "relation", "source_id", "expires_at"},
    }
    existing = _table_names(connection)
    if set(expected) - existing:
        raise sqlite3.DatabaseError("database is missing required tables")
    for table, columns in expected.items():
        if columns - _columns(connection, table):
            raise sqlite3.DatabaseError(f"table {table} is missing required columns")


def _check_snapshot(connection: sqlite3.Connection) -> None:
    _quick_check(connection)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise sqlite3.DatabaseError(
            f"database schema {version} is newer than supported schema {SCHEMA_VERSION}"
        )
    if version == 0:
        _validate_legacy_schema(connection)
    else:
        _validate_current_schema(connection)


def _quick_check(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA quick_check").fetchone()
    if row is None or row[0] != "ok":
        raise sqlite3.DatabaseError("database quick_check failed")


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column(connection: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    if column not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _path(path: str | Path) -> Path:
    if not isinstance(path, (str, os.PathLike)) or not str(path).strip():
        raise ValueError("database path is required")
    return Path(path)


def _database_path(path: str | Path) -> Path:
    target = _path(path)
    _prepare_parent(target)
    _reject_symlink(target)
    if target.exists() and not target.is_file():
        raise OSError("database path must be a file")
    if not target.exists():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target, flags, DATABASE_MODE)
        os.close(descriptor)
    return target


def _existing_path(path: str | Path) -> Path:
    target = _path(path)
    _reject_symlink(target)
    if not target.is_file():
        raise FileNotFoundError(target)
    return target


def _prepare_parent(target: Path) -> None:
    _reject_symlink(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink(target)


def _reject_symlink(target: Path) -> None:
    absolute = Path(os.path.abspath(target))
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise OSError("symbolic link database paths are not allowed")


def _temporary_path(target: Path) -> Path:
    _prepare_parent(target)
    _reject_symlink(target)
    return target.with_name(f".{target.name}.{uuid4().hex}.tmp")


def _atomic_backup(source: sqlite3.Connection, target: Path) -> None:
    temp = _temporary_path(target)
    try:
        _copy_database(source, temp)
        _fsync(temp)
        _reject_symlink(target)
        os.replace(temp, target)
        os.chmod(target, DATABASE_MODE)
        _fsync_directory(target.parent)
    finally:
        _remove_database_files(temp)


def _copy_database(source: sqlite3.Connection, target: Path) -> None:
    destination = sqlite3.connect(_database_path(target))
    try:
        source.backup(destination)
        _quick_check(destination)
    finally:
        destination.close()


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDWR)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        if os.name == "posix":
            raise
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            if os.name == "posix":
                raise
    finally:
        os.close(descriptor)


def _remove_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _remove_database_files(path: Path) -> None:
    path.unlink(missing_ok=True)
    _remove_sidecars(path)


def _required(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    resolved = " ".join(value.split())
    if not resolved:
        raise ValueError(f"{field} must not be empty")
    resolved.encode("utf-8")
    return resolved


def _tags(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        tag = _required(str(value), "tag")
        if tag not in output:
            output.append(tag)
    return output


def _tokens(value: str) -> list[str]:
    return re.findall(r"\w+", value.casefold(), flags=re.UNICODE)


def _timestamp(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    resolved = _required(value, field)
    try:
        parsed = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _bounded(value: int, field: str, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "content": row["content"],
        "tags": json.loads(row["tags"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "source_id": row["source_id"],
        "expires_at": row["expires_at"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clonamic-memory")
    sub = parser.add_subparsers(dest="action", required=True)
    provenance = sub.add_parser("record-source")
    provenance.add_argument("--db", required=True)
    provenance.add_argument("--id", required=True)
    provenance.add_argument("--session-id", required=True)
    provenance.add_argument("--sequence", required=True, type=int)
    provenance.add_argument("--source-kind", required=True, choices=sorted(SOURCE_KINDS))
    provenance.add_argument("--body-sha256", required=True)
    provenance.add_argument("--body-bytes", required=True, type=int)
    provenance.add_argument("--expires-at")
    save = sub.add_parser("store")
    save.add_argument("--db", required=True)
    save.add_argument("--id", required=True)
    save.add_argument("--content", required=True)
    save.add_argument("--tag", action="append", default=[])
    save.add_argument("--source-id", required=True)
    save.add_argument("--expires-at")
    search = sub.add_parser("recall")
    search.add_argument("--db", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)
    remove = sub.add_parser("forget")
    remove.add_argument("--db", required=True)
    remove.add_argument("--id", required=True)
    edge = sub.add_parser("link")
    edge.add_argument("--db", required=True)
    edge.add_argument("--source", required=True)
    edge.add_argument("--target", required=True)
    edge.add_argument("--relation", required=True)
    edge.add_argument("--source-id", required=True)
    edge.add_argument("--expires-at")
    view = sub.add_parser("graph")
    view.add_argument("--db", required=True)
    view.add_argument("--anchor", required=True)
    view.add_argument("--depth", type=int, default=2)
    view.add_argument("--limit", type=int, default=20)
    prune_parser = sub.add_parser("prune")
    prune_parser.add_argument("--db", required=True)
    prune_parser.add_argument("--before")
    backup_parser = sub.add_parser("backup")
    backup_parser.add_argument("--db", required=True)
    backup_parser.add_argument("--output", required=True)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--db", required=True)
    restore_parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "record-source":
            output: Any = record_source(
                args.db,
                args.id,
                args.session_id,
                args.sequence,
                args.source_kind,
                args.body_sha256,
                args.body_bytes,
                expires_at=args.expires_at,
            )
        elif args.action == "store":
            output = store(
                args.db,
                args.id,
                args.content,
                args.tag,
                source_id=args.source_id,
                expires_at=args.expires_at,
            )
        elif args.action == "recall":
            output = recall(args.db, args.query, limit=args.limit)
        elif args.action == "forget":
            output = {"removed": forget(args.db, args.id)}
        elif args.action == "link":
            output = link(
                args.db,
                args.source,
                args.target,
                args.relation,
                source_id=args.source_id,
                expires_at=args.expires_at,
            )
        elif args.action == "graph":
            output = graph(args.db, args.anchor, depth=args.depth, limit=args.limit)
        elif args.action == "prune":
            output = prune(args.db, before=args.before)
        elif args.action == "backup":
            output = backup(args.db, args.output)
        else:
            output = restore(args.db, args.input)
        print(json.dumps({"ok": True, "result": output}, ensure_ascii=False, sort_keys=True))
        return 0
    except (TypeError, ValueError, KeyError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
