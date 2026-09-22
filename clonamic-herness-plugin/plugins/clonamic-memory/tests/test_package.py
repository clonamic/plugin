import importlib.util
import errno
import io
import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MANIFEST_FIELDS = {"$schema", "name", "version", "description", "license", "author", "keywords"}


def load_runtime(root):
    path = Path(root) / "skills" / "clonamic-memory" / "scripts" / "memory.py"
    if not path.is_file():
        raise AssertionError("skill-relative memory runtime is missing")
    spec = importlib.util.spec_from_file_location(f"clonamic_memory_{os.getpid()}_{id(path)}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class MemoryPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.package = ROOT
        self.runtime = load_runtime(self.package)

    def tearDown(self):
        self.temp.cleanup()

    def database_path(self):
        return self.root / "state" / "memory.sqlite3"

    def record_source(self, database, source_id="p1", *, sequence=1, expires_at=None):
        return self.runtime.record_source(
            database,
            source_id,
            "session-1",
            sequence,
            "user",
            "a" * 64,
            42,
            expires_at=expires_at,
        )

    def store(self, database, memory_id, content, tags=(), *, source_id="p1", expires_at=None):
        return self.runtime.store(
            database,
            memory_id,
            content,
            tags,
            source_id=source_id,
            expires_at=expires_at,
        )

    def test_closed_manifest_and_single_direct_skill(self):
        manifest = json.loads((self.package / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(SCHEMA, manifest["$schema"])
        self.assertEqual(MANIFEST_FIELDS, set(manifest))
        self.assertEqual("clonamic-memory", manifest["name"])
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        skills = list((self.package / "skills").glob("*/SKILL.md"))
        self.assertEqual(["clonamic-memory"], [path.parent.name for path in skills])
        self.assertTrue((skills[0].parent / "agents" / "openai.yaml").is_file())
        self.assertFalse((self.package / "scripts").exists())

    def test_explicit_store_recall_and_forget(self):
        database = self.database_path()
        self.record_source(database)
        self.store(database, "m1", "Module boundaries need evidence", ["architecture"])
        self.store(database, "m2", "Queue work by priority", ["queue"])
        rows = self.runtime.recall(database, "module evidence", limit=5)
        self.assertEqual("m1", rows[0]["id"])
        self.assertTrue(self.runtime.forget(database, "m1"))
        self.assertEqual([], self.runtime.recall(database, "module evidence", limit=5))
        self.assertFalse(self.runtime.forget(database, "missing"))

    def test_store_updates_existing_id_without_duplication(self):
        database = self.database_path()
        self.record_source(database)
        self.store(database, "m1", "old value", [])
        self.store(database, "m1", "new value", ["current"])
        rows = self.runtime.recall(database, "new value", limit=5)
        self.assertEqual(1, len(rows))
        self.assertEqual(["current"], rows[0]["tags"])

    def test_graph_is_bounded_cycle_safe_and_forget_cascades_edges(self):
        database = self.database_path()
        self.record_source(database)
        for memory_id in ("a", "b", "c"):
            self.store(database, memory_id, f"node {memory_id}", [])
        self.runtime.link(database, "a", "b", "relates_to", source_id="p1")
        self.runtime.link(database, "b", "c", "supports", source_id="p1")
        self.runtime.link(database, "c", "a", "revises", source_id="p1")
        graph = self.runtime.graph(database, "a", depth=2, limit=10)
        self.assertEqual({"a", "b", "c"}, {row["id"] for row in graph["nodes"]})
        self.assertEqual(3, len(graph["edges"]))
        self.runtime.forget(database, "b")
        graph = self.runtime.graph(database, "a", depth=2, limit=10)
        self.assertEqual({"a", "c"}, {row["id"] for row in graph["nodes"]})
        self.assertTrue(all("b" not in (edge["source"], edge["target"]) for edge in graph["edges"]))

    def test_link_rejects_missing_nodes_and_self_edges(self):
        database = self.database_path()
        self.record_source(database)
        self.store(database, "a", "node a", [])
        with self.assertRaises(KeyError):
            self.runtime.link(database, "a", "missing", "relates_to", source_id="p1")
        with self.assertRaises(ValueError):
            self.runtime.link(database, "a", "a", "relates_to", source_id="p1")

    def test_every_public_operation_closes_before_database_reuse(self):
        runtime = self.runtime
        real_connect = runtime.sqlite3.connect
        opened = []

        class TrackingConnection(runtime.sqlite3.Connection):
            closed = False

            def close(self):
                self.closed = True
                return super().close()

        def tracked_connect(*args, **kwargs):
            kwargs["factory"] = TrackingConnection
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection

        def assert_closed_and_reusable(database):
            self.assertTrue(opened)
            self.assertTrue(all(connection.closed for connection in opened))
            opened.clear()
            moved = database.with_suffix(".moved")
            database.replace(moved)
            moved.replace(database)

        database = self.database_path()
        runtime.sqlite3.connect = tracked_connect
        try:
            self.record_source(database)
            assert_closed_and_reusable(database)
            self.store(database, "a", "node a", [])
            assert_closed_and_reusable(database)
            self.store(database, "b", "node b", [])
            assert_closed_and_reusable(database)
            runtime.recall(database, "node", limit=5)
            assert_closed_and_reusable(database)
            runtime.link(database, "a", "b", "relates_to", source_id="p1")
            assert_closed_and_reusable(database)
            runtime.graph(database, "a", depth=1, limit=5)
            assert_closed_and_reusable(database)
            runtime.forget(database, "b")
            assert_closed_and_reusable(database)
            database.unlink()
        finally:
            runtime.sqlite3.connect = real_connect
            for connection in opened:
                connection.close()

    def test_database_context_rolls_back_and_closes_on_exception(self):
        database = self.database_path()
        with self.assertRaises(RuntimeError):
            with self.runtime._database(database) as connection:
                connection.execute(
                    "INSERT INTO memories (id, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("transient", "discard me", "[]", "now", "now"),
                )
                raise RuntimeError("stop")
        self.assertEqual([], self.runtime.recall(database, "discard", limit=5))
        moved = database.with_suffix(".moved")
        database.replace(moved)
        moved.unlink()

    def test_legacy_schema_migrates_with_backup_and_user_version(self):
        database = self.database_path()
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                CREATE TABLE memories (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL, tags TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE edges (
                    source TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    target TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL, PRIMARY KEY (source, target, relation)
                );
                INSERT INTO memories VALUES ('legacy', 'old row', '[]', 'now', 'now');
                """
            )
        self.record_source(database)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(1, connection.execute("PRAGMA user_version").fetchone()[0])
            memory_columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)")}
            edge_columns = {row[1] for row in connection.execute("PRAGMA table_info(edges)")}
        self.assertTrue({"source_id", "expires_at"} <= memory_columns)
        self.assertTrue({"source_id", "expires_at"} <= edge_columns)
        backup = database.with_name(f"{database.name}.pre-v1.bak")
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(0, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual("ok", connection.execute("PRAGMA quick_check").fetchone()[0])

    def test_legacy_migration_replaces_an_invalid_stale_backup(self):
        database = self.database_path()
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                CREATE TABLE memories (
                    id TEXT PRIMARY KEY, content TEXT NOT NULL, tags TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE edges (
                    source TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    target TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL, PRIMARY KEY (source, target, relation)
                );
                """
            )
        backup = database.with_name(f"{database.name}.pre-v1.bak")
        backup.write_bytes(b"stale")
        self.record_source(database)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual("ok", connection.execute("PRAGMA quick_check").fetchone()[0])
            self.assertEqual(0, connection.execute("PRAGMA user_version").fetchone()[0])

    def test_unknown_newer_schema_fails_closed(self):
        database = self.database_path()
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA user_version = 99")
        before = database.read_bytes()
        before_mode = database.stat().st_mode & 0o777
        with self.assertRaises(sqlite3.DatabaseError):
            self.record_source(database)
        self.assertEqual(before, database.read_bytes())
        self.assertEqual(before_mode, database.stat().st_mode & 0o777)

    def test_provenance_is_required_and_stores_no_prompt_text_or_authority(self):
        database = self.database_path()
        source = self.record_source(database)
        self.assertEqual("p1", source["id"])
        with self.assertRaises(KeyError):
            self.runtime.store(database, "missing-source", "value", [], source_id="missing")
        self.store(database, "a", "node a")
        self.store(database, "b", "node b")
        edge = self.runtime.link(database, "a", "b", "supports", source_id="p1")
        self.assertEqual("p1", edge["source_id"])
        with closing(sqlite3.connect(database)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(prompt_sources)")}
            row = connection.execute("SELECT * FROM prompt_sources WHERE id = 'p1'").fetchone()
        self.assertEqual(
            {"id", "session_id", "sequence", "source_kind", "body_sha256", "body_bytes", "expires_at"},
            columns,
        )
        self.assertNotIn("Module boundaries", repr(row))
        self.assertFalse({"body", "content", "path", "authority"} & columns)

    def test_fts_candidates_match_fallback_for_korean_and_operator_input(self):
        database = self.database_path()
        self.record_source(database)
        self.store(database, "ko", "한글 검색과 C++ 연산자", ["자료"])
        self.store(database, "ko-glued", "한글검색 경계 없는 낱말", ["자료"])
        self.store(database, "sql", "SQL OR 표현식", ["operator"])
        queries = ("한글", "한글 + 검색", "C++ OR SQL", "operator")
        expected = [[row["id"] for row in self.runtime.recall(database, query)] for query in queries]
        self.assertIn("ko-glued", expected[0])
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                DROP TRIGGER IF EXISTS memories_fts_insert;
                DROP TRIGGER IF EXISTS memories_fts_update;
                DROP TRIGGER IF EXISTS memories_fts_delete;
                DROP TABLE IF EXISTS memories_fts;
                """
            )
        actual = [[row["id"] for row in self.runtime.recall(database, query)] for query in queries]
        self.assertEqual(expected, actual)

    def test_fts_candidates_include_non_ascii_rows_for_ascii_casefold_queries(self):
        database = self.database_path()
        self.record_source(database)
        self.store(database, "sharp-s", "Straße route", ["address"])
        self.store(database, "ascii", "strasse separated-token", ["address"])
        queries = ("ss", "strasse")
        expected = [[row["id"] for row in self.runtime.recall(database, query)] for query in queries]
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                DROP TRIGGER IF EXISTS memories_fts_insert;
                DROP TRIGGER IF EXISTS memories_fts_update;
                DROP TRIGGER IF EXISTS memories_fts_delete;
                DROP TABLE IF EXISTS memories_fts;
                """
            )
        actual = [[row["id"] for row in self.runtime.recall(database, query)] for query in queries]
        self.assertEqual(actual, expected)
        self.assertEqual(["sharp-s", "ascii"], expected[0])
        self.assertEqual(["sharp-s", "ascii"], expected[1])

    def test_non_ascii_candidate_superset_streams_into_bounded_top_k(self):
        database = self.database_path()
        self.record_source(database)
        for index in range(160):
            self.store(database, f"decoy-{index:03d}", f"Straße decoy {index}", ["address"])
        limit = 7
        real_candidates = self.runtime._recall_candidates
        real_nsmallest = self.runtime.heapq.nsmallest
        observed = []

        def streaming_candidates(*args, **kwargs):
            rows = real_candidates(*args, **kwargs)
            self.assertNotIsInstance(rows, (list, tuple))
            return rows

        def bounded_top_k(count, rows, *, key):
            result = real_nsmallest(count, rows, key=key)
            observed.append((count, len(result)))
            return result

        self.runtime._recall_candidates = streaming_candidates
        self.runtime.heapq.nsmallest = bounded_top_k
        try:
            expected = [row["id"] for row in self.runtime.recall(database, "strasse", limit=limit)]
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(
                    """
                    DROP TRIGGER IF EXISTS memories_fts_insert;
                    DROP TRIGGER IF EXISTS memories_fts_update;
                    DROP TRIGGER IF EXISTS memories_fts_delete;
                    DROP TABLE IF EXISTS memories_fts;
                    """
                )
            actual = [row["id"] for row in self.runtime.recall(database, "strasse", limit=limit)]
        finally:
            self.runtime._recall_candidates = real_candidates
            self.runtime.heapq.nsmallest = real_nsmallest
        self.assertEqual(expected, actual)
        self.assertEqual(limit, len(actual))
        self.assertEqual([(limit, limit), (limit, limit)], observed)

    def test_graph_uses_one_recursive_query_and_deterministic_breadth_order(self):
        database = self.database_path()
        self.record_source(database)
        for memory_id in ("a", "b", "c", "d"):
            self.store(database, memory_id, f"node {memory_id}")
        for source, target in (("a", "c"), ("a", "b"), ("b", "d"), ("d", "a")):
            self.runtime.link(database, source, target, "relates", source_id="p1")
        statements = []
        real_connect = self.runtime.sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        self.runtime.sqlite3.connect = traced_connect
        try:
            result = self.runtime.graph(database, "a", depth=2, limit=4)
        finally:
            self.runtime.sqlite3.connect = real_connect
        self.assertEqual(["a", "b", "c", "d"], [row["id"] for row in result["nodes"]])
        self.assertEqual(1, sum("WITH RECURSIVE" in statement.upper() for statement in statements))
        graph_selects = [statement for statement in statements if "FROM edges" in statement]
        self.assertLessEqual(len(graph_selects), 2)

    def test_graph_route_does_not_confuse_commas_inside_node_ids(self):
        database = self.database_path()
        self.record_source(database)
        self.store(database, "a,b", "anchor")
        self.store(database, "a", "neighbor")
        self.runtime.link(database, "a,b", "a", "contains", source_id="p1")
        result = self.runtime.graph(database, "a,b", depth=1)
        self.assertEqual(["a,b", "a"], [row["id"] for row in result["nodes"]])

    def test_dense_cyclic_graph_deduplicates_before_limit(self):
        database = self.database_path()
        self.record_source(database)
        node_ids = [f"n{index:02d}" for index in range(19)]
        for node_id in node_ids:
            self.store(database, node_id, f"node {node_id}")
        for node_id in node_ids[1:9]:
            self.runtime.link(database, "n00", node_id, "dense", source_id="p1")
        dense = node_ids[1:17]
        for index, source in enumerate(dense):
            for target in dense[index + 1 :]:
                self.runtime.link(database, source, target, "dense", source_id="p1")
        self.runtime.link(database, "n16", "n17", "bridge", source_id="p1")
        self.runtime.link(database, "n17", "n18", "bridge", source_id="p1")
        result = self.runtime.graph(database, "n00", depth=4, limit=20)
        self.assertEqual(node_ids, [row["id"] for row in result["nodes"]])

    def test_prune_removes_expired_nodes_edges_and_sources(self):
        database = self.database_path()
        expired = "2020-01-01T00:00:00+00:00"
        active = "2099-01-01T00:00:00+00:00"
        self.record_source(database, "old-source", sequence=1, expires_at=expired)
        self.record_source(database, "new-source", sequence=2, expires_at=active)
        self.store(database, "old", "expired node", source_id="old-source", expires_at=expired)
        self.store(database, "new", "active node", source_id="new-source", expires_at=active)
        self.runtime.link(database, "old", "new", "old edge", source_id="old-source", expires_at=expired)
        result = self.runtime.prune(database, before="2021-01-01T00:00:00+00:00")
        self.assertEqual({"memories": 1, "edges": 1, "prompt_sources": 1}, result)
        self.assertEqual([], self.runtime.recall(database, "expired"))
        self.assertEqual(["new"], [row["id"] for row in self.runtime.recall(database, "active")])

    def test_prune_keeps_expired_provenance_while_an_active_row_references_it(self):
        database = self.database_path()
        self.record_source(database, expires_at="2020-01-01T00:00:00+00:00")
        self.store(database, "active", "still active")
        result = self.runtime.prune(database, before="2021-01-01T00:00:00+00:00")
        self.assertEqual(0, result["prompt_sources"])
        self.assertEqual("p1", self.runtime.recall(database, "active")[0]["source_id"])

    def test_concurrent_writers_lose_no_rows(self):
        database = self.database_path()
        self.record_source(database)

        def write(index):
            self.store(database, f"m{index:02d}", f"concurrent value {index}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(32)))
        self.assertEqual(32, len(self.runtime.recall(database, "concurrent", limit=100)))

    def test_runtime_enables_wal_busy_timeout_and_immediate_writes(self):
        database = self.database_path()
        statements = []
        real_connect = self.runtime.sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        self.runtime.sqlite3.connect = traced_connect
        try:
            self.record_source(database)
        finally:
            self.runtime.sqlite3.connect = real_connect
        normalized = [statement.upper() for statement in statements]
        self.assertTrue(any("PRAGMA JOURNAL_MODE = WAL" in statement for statement in normalized))
        self.assertTrue(any("PRAGMA BUSY_TIMEOUT = 5000" in statement for statement in normalized))
        self.assertTrue(any("BEGIN IMMEDIATE" in statement for statement in normalized))

    def test_file_sync_uses_a_writable_descriptor_and_directory_sync_is_best_effort(self):
        path = self.root / "sync.sqlite3"
        with mock.patch.object(self.runtime.os, "open", return_value=73) as open_file:
            with mock.patch.object(self.runtime.os, "fsync") as sync_file:
                with mock.patch.object(self.runtime.os, "close") as close_file:
                    self.runtime._fsync(path)
        open_file.assert_called_once_with(path, os.O_RDWR)
        sync_file.assert_called_once_with(73)
        close_file.assert_called_once_with(73)

        with mock.patch.object(self.runtime.os, "name", "nt"):
            with mock.patch.object(self.runtime.os, "open", return_value=74):
                with mock.patch.object(
                    self.runtime.os,
                    "fsync",
                    side_effect=OSError(errno.EBADF, "unsupported"),
                ):
                    with mock.patch.object(self.runtime.os, "close") as close_directory:
                        self.runtime._fsync_directory(path.parent)
        close_directory.assert_called_once_with(74)

        with mock.patch.object(self.runtime.os, "name", "posix"):
            with mock.patch.object(self.runtime.os, "open", return_value=75):
                with mock.patch.object(
                    self.runtime.os, "fsync", side_effect=OSError(errno.EIO, "write failed")
                ):
                    with mock.patch.object(self.runtime.os, "close") as close_directory:
                        with self.assertRaises(OSError):
                            self.runtime._fsync_directory(path.parent)
        close_directory.assert_called_once_with(75)

        with mock.patch.object(self.runtime.os, "name", "posix"):
            with mock.patch.object(
                self.runtime.os, "open", side_effect=OSError(errno.EIO, "open failed")
            ):
                with self.assertRaises(OSError):
                    self.runtime._fsync_directory(path.parent)

    def test_backup_restore_and_refusals_preserve_destination(self):
        database = self.database_path()
        backup = self.root / "backups" / "memory.sqlite3"
        self.record_source(database)
        self.store(database, "m1", "before backup")
        self.runtime.backup(database, backup)
        self.store(database, "m1", "after backup")
        self.runtime.restore(database, backup)
        self.assertEqual("before backup", self.runtime.recall(database, "before")[0]["content"])

        corrupt = self.root / "backups" / "corrupt.sqlite3"
        corrupt.write_bytes(b"not sqlite")
        before = database.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            self.runtime.restore(database, corrupt)
        self.assertEqual(before, database.read_bytes())

        newer = self.root / "backups" / "newer.sqlite3"
        with closing(sqlite3.connect(newer)) as connection:
            connection.execute("PRAGMA user_version = 99")
        with self.assertRaises(sqlite3.DatabaseError):
            self.runtime.restore(database, newer)
        self.assertEqual(before, database.read_bytes())

    def test_database_is_lazy_private_and_rejects_symlinks(self):
        database = self.database_path()
        self.assertFalse(database.exists())
        self.record_source(database)
        if os.name == "posix":
            self.assertEqual(0o600, database.stat().st_mode & 0o777)
        alias = database.with_name("alias.sqlite3")
        alias.symlink_to(database)
        with self.assertRaises(OSError):
            self.runtime.recall(alias, "anything")

    def test_database_backup_and_restore_reject_symlink_ancestors(self):
        real = self.root / "real-state"
        alias = self.root / "state-alias"
        real.mkdir()
        alias.symlink_to(real, target_is_directory=True)
        database = alias / "memory.sqlite3"
        with self.assertRaises(OSError):
            self.record_source(database)

        safe_database = self.database_path()
        snapshot = self.root / "backups" / "memory.sqlite3"
        self.record_source(safe_database)
        self.runtime.backup(safe_database, snapshot)
        real_database = real / "source.sqlite3"
        self.record_source(real_database)
        with self.assertRaises(OSError):
            self.runtime.backup(alias / real_database.name, self.root / "source-copy.sqlite3")
        with self.assertRaises(OSError):
            self.runtime.backup(safe_database, alias / "backup.sqlite3")
        snapshot_alias = self.root / "backup-alias"
        snapshot_alias.symlink_to(snapshot.parent, target_is_directory=True)
        with self.assertRaises(OSError):
            self.runtime.restore(self.root / "restored.sqlite3", snapshot_alias / snapshot.name)
        with self.assertRaises(OSError):
            self.runtime.restore(alias / "restored.sqlite3", snapshot)

    def test_restore_rejects_symlink_target_without_leaking_snapshot_handle(self):
        database = self.database_path()
        snapshot = self.root / "backups" / "memory.sqlite3"
        self.record_source(database)
        self.runtime.backup(database, snapshot)
        alias = database.with_name("restore-alias.sqlite3")
        alias.symlink_to(database)
        opened = []
        real_connect = self.runtime.sqlite3.connect

        class TrackingConnection(self.runtime.sqlite3.Connection):
            closed = False

            def close(self):
                self.closed = True
                return super().close()

        def tracked_connect(*args, **kwargs):
            kwargs["factory"] = TrackingConnection
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection

        self.runtime.sqlite3.connect = tracked_connect
        leaked = []
        try:
            with self.assertRaises(OSError):
                self.runtime.restore(alias, snapshot)
        finally:
            self.runtime.sqlite3.connect = real_connect
            leaked = [connection for connection in opened if not connection.closed]
            for connection in opened:
                if not connection.closed:
                    connection.close()
        self.assertEqual([], leaked)

    def test_distribution_contains_no_sqlite_runtime_files(self):
        forbidden_suffixes = (".sqlite", ".sqlite3", ".db", "-wal", "-shm")
        files = [path for path in self.package.rglob("*") if path.is_file()]
        self.assertFalse([path for path in files if path.name.endswith(forbidden_suffixes)])

    def test_cli_records_source_then_stores_and_recalls(self):
        database = self.database_path()

        def run(*arguments):
            output = io.StringIO()
            with redirect_stdout(output):
                status = self.runtime.main(list(arguments))
            return status, json.loads(output.getvalue())

        status, payload = run(
            "record-source",
            "--db",
            str(database),
            "--id",
            "p1",
            "--session-id",
            "s1",
            "--sequence",
            "1",
            "--source-kind",
            "automation",
            "--body-sha256",
            "b" * 64,
            "--body-bytes",
            "12",
        )
        self.assertEqual((0, True), (status, payload["ok"]))
        status, payload = run(
            "store",
            "--db",
            str(database),
            "--id",
            "m1",
            "--content",
            "CLI memory",
            "--source-id",
            "p1",
        )
        self.assertEqual((0, "p1"), (status, payload["result"]["source_id"]))
        status, payload = run("recall", "--db", str(database), "--query", "CLI")
        self.assertEqual((0, ["m1"]), (status, [row["id"] for row in payload["result"]]))

    def test_production_surface_excludes_automatic_or_cross_package_state(self):
        forbidden = (
            "hot_" + "inject",
            "prompt " + "injection",
            "pre" + "processing",
            "app" + "roval",
            "mo" + "del",
            "au" + "th_",
            "creden" + "tials",
        )
        for path in self.package.rglob("*"):
            if not path.is_file() or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                self.assertNotIn(token, text, f"{token} in {path.relative_to(self.package)}")


if __name__ == "__main__":
    unittest.main()
