import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "skills" / "clonamic-my-language" / "scripts" / "my_language.py"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MANIFEST_FIELDS = {"$schema", "name", "version", "description", "license", "author", "keywords"}


def load_runtime():
    spec = importlib.util.spec_from_file_location(f"clonamic_my_language_{os.getpid()}", RUNTIME_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def tree_bytes(path):
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


class MyLanguagePackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / "data" / "style.sqlite3"
        self.runtime = load_runtime()

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, payload):
        raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        return self.runtime.capture(raw, path=self.database)

    def test_closed_manifest_version_and_three_explicit_skills(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(SCHEMA, manifest["$schema"])
        self.assertEqual(MANIFEST_FIELDS, set(manifest))
        self.assertEqual("clonamic-my-language-plugin", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        skill_names = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(
            ["clonamic-my-language", "clonamic-my-language-export", "clonamic-my-language-review"],
            skill_names,
        )
        for name in skill_names:
            skill = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            openai = (ROOT / "skills" / name / "agents" / "openai.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("disable-model-invocation: true", skill)
            self.assertIn("allow_implicit_invocation: false", openai)

    def test_review_is_owned_by_explicit_main_and_refuses_every_other_path(self):
        main_skill = (ROOT / "skills" / "clonamic-my-language" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        review_skill = (
            ROOT / "skills" / "clonamic-my-language-review" / "SKILL.md"
        ).read_text(encoding="utf-8")
        native_agent = (ROOT / "agents" / "clonamic-my-language-review.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Run exactly one review pass", main_skill)
        self.assertIn("This main command owns that pass", main_skill)
        self.assertIn("Never run the review path outside", main_skill)
        self.assertIn("disable-model-invocation: true", review_skill)
        self.assertIn("user-invocable: false", review_skill)
        self.assertIn("refused_inactive_invocation", review_skill)
        self.assertIn("active_command", native_agent)
        self.assertIn("refused_inactive_invocation", native_agent)
        self.assertIn("tools: []", native_agent)

    def test_byte_exact_korean_emoji_and_newlines_are_stored_as_blob(self):
        payload = "첫 줄 그대로 😀\n\n- 둘째 줄\n마지막 줄".encode("utf-8")
        result = self.capture(payload)
        self.assertEqual(len(payload), result["byte_count"])
        with closing(sqlite3.connect(self.database)) as connection:
            stored, storage_type = connection.execute(
                "SELECT raw_prompt, typeof(raw_prompt) FROM prompt_samples"
            ).fetchone()
        self.assertEqual(payload, stored)
        self.assertEqual("blob", storage_type)

    def test_cli_reads_payload_only_from_stdin_without_argv_echo(self):
        payload = "명령 뒤의 입력만 저장해줘 😀\n둘째 줄".encode("utf-8")
        process = subprocess.run(
            [sys.executable, str(RUNTIME_PATH), "capture", "--database", str(self.database)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, process.returncode, process.stderr.decode())
        result = json.loads(process.stdout)
        self.assertNotIn("명령 뒤의 입력", process.stdout.decode("utf-8"))
        self.assertEqual(len(payload), result["byte_count"])
        with closing(sqlite3.connect(self.database)) as connection:
            stored = connection.execute("SELECT raw_prompt FROM prompt_samples").fetchone()[0]
        self.assertEqual(payload, stored)

    def test_non_user_or_non_explicit_sources_are_rejected_without_creating_rows(self):
        roles = ("system", "developer", "assistant", "tool")
        for role in roles:
            with self.assertRaises(PermissionError):
                self.runtime.capture(b"must not persist", path=self.database, source_role=role)
        with self.assertRaises(PermissionError):
            self.runtime.capture(
                b"ordinary chat", path=self.database, explicit_command="/ordinary-chat"
            )
        self.assertFalse(self.database.exists())

    def test_analysis_contains_observable_fields_but_no_raw_text(self):
        payload = '["이건 과하게 바꾸지 말고 확인해줘"] -> 목록으로 정리해.'.encode("utf-8")
        self.capture(payload)
        with closing(sqlite3.connect(self.database)) as connection:
            document = connection.execute("SELECT analysis_json FROM prompt_analyses").fetchone()[0]
        analysis = json.loads(document)
        self.assertNotIn(payload.decode("utf-8"), document)
        self.assertEqual(
            {
                "aversion_markers",
                "code_switching",
                "korean_endings",
                "language",
                "list_habits",
                "paragraph_rhythm",
                "punctuation_formatting",
                "request_style",
                "schema_version",
                "sentence_rhythm",
                "stable_quirk_candidates",
            },
            set(analysis),
        )
        self.assertIn("quoted-square-payload", analysis["stable_quirk_candidates"])
        self.assertIn("arrow-transition", analysis["stable_quirk_candidates"])

    def test_duplicate_events_are_preserved_but_do_not_weight_profile_or_threshold(self):
        first = self.capture("같은 입력은 사건으로 남겨줘.")
        for _ in range(8):
            last = self.capture("같은 입력은 사건으로 남겨줘.")
        self.assertEqual(9, last["total_events"])
        self.assertEqual(1, last["unique_samples"])
        self.assertEqual(1, last["profile"]["evidence_counts"]["unique_samples"])
        self.assertEqual(8, last["profile"]["evidence_counts"]["duplicate_events"])
        self.assertIsNone(last["checkpoint_id"])
        self.assertEqual(first["profile"]["sentence_rhythm"], last["profile"]["sentence_rhythm"])

    def test_checkpoint_updates_every_five_new_unique_samples(self):
        results = [self.capture(f"서로 다른 요청 {index}번을 처리해줘.") for index in range(1, 5)]
        self.assertTrue(all(result["checkpoint_id"] is None for result in results))
        fifth = self.capture("서로 다른 요청 5번을 처리해줘.")
        self.assertTrue(fifth["checkpoint_updated"])
        self.assertEqual(1, fifth["checkpoint_id"])
        self.assertEqual("updated-checkpoint", fifth["profile_state"])
        self.capture("서로 다른 요청 1번을 처리해줘.")
        for index in range(6, 10):
            pending = self.capture(f"서로 다른 요청 {index}번을 처리해줘.")
            self.assertFalse(pending["checkpoint_updated"])
            self.assertEqual("checkpoint", pending["profile_state"])
        tenth = self.capture("서로 다른 요청 10번을 처리해줘.")
        self.assertTrue(tenth["checkpoint_updated"])
        self.assertEqual(2, tenth["checkpoint_id"])

    def test_multilingual_profiles_are_kept_in_separate_groups(self):
        for payload in (
            "이 작업은 짧게 정리해줘.",
            "결과부터 말하고 목록으로 적어줘.",
            "Please keep the answer short and direct.",
            "List the measured result first.",
            "한국어 report 형식으로 바로 정리해줘.",
        ):
            result = self.capture(payload)
        profile = result["profile"]
        self.assertEqual({"en", "ko", "mixed"}, set(profile["by_language"]))
        self.assertEqual({"en": 2, "ko": 2, "mixed": 1}, profile["language"]["unique_sample_counts"])
        self.assertEqual(5, profile["confidence"]["unique_samples"])

    def test_repeated_observable_quirks_and_aversions_need_repeated_evidence(self):
        self.capture('["첫 지시"] -> 과한 표현은 하지 말고 정리해줘.')
        result = self.capture('["둘째 지시"] -> 불필요한 설명은 하지 말고 줄여줘.')
        quirks = {item["name"]: item["evidence_samples"] for item in result["profile"]["stable_repeated_quirks"]}
        aversions = {item["name"]: item["evidence_count"] for item in result["profile"]["aversions"]}
        self.assertEqual(2, quirks["arrow-transition"])
        self.assertEqual(2, quirks["quoted-square-payload"])
        self.assertEqual(2, aversions["excess-rejection-ko"])
        self.assertEqual(2, aversions["negative-imperative-ko"])

    def test_export_is_deterministic_and_contains_no_raw_phrase_path_database_or_session(self):
        sentinel = "NEVER_EXPORT_이_문장은_원문에만_존재_938417"
        self.capture(f"{sentinel}\n결과부터 짧게 정리해줘.")
        first = self.root / "first-profile"
        second = self.root / "second-profile"
        first_result = self.runtime.export_checkpoint(first, path=self.database)
        second_result = self.runtime.export_checkpoint(second, path=self.database)
        self.assertEqual(first_result["profile_sha256"], second_result["profile_sha256"])
        self.assertEqual(tree_bytes(first), tree_bytes(second))
        exported = b"\n".join(tree_bytes(first).values()).decode("utf-8")
        self.assertNotIn(sentinel, exported)
        self.assertNotIn(str(self.root), exported)
        self.assertNotIn("style.sqlite3", exported)
        self.assertNotIn("session", exported.casefold())
        self.assertFalse(any(path.suffix == ".sqlite3" for path in first.rglob("*")))
        manifest = json.loads((first / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(SCHEMA, manifest["$schema"])
        self.assertEqual("clonamic-my-language-profile", manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual(8, first_result["file_count"])
        exported_main = tree_bytes(first)["skills/clonamic-my-language/SKILL.md"].decode("utf-8")
        exported_agent = tree_bytes(first)["agents/clonamic-my-language-review.md"].decode("utf-8")
        self.assertIn("Run exactly one review pass", exported_main)
        self.assertIn("active_command=/clonamic-my-language", exported_agent)
        self.assertIn("refused_inactive_invocation", exported_agent)

    def test_export_refuses_overwrite_and_empty_database(self):
        with self.assertRaises(ValueError):
            self.runtime.export_checkpoint(self.root / "empty-export", path=self.database)
        self.capture("내보낼 데이터를 만들어줘.")
        output = self.root / "profile"
        self.runtime.export_checkpoint(output, path=self.database)
        before = tree_bytes(output)
        with self.assertRaises(FileExistsError):
            self.runtime.export_checkpoint(output, path=self.database)
        self.assertEqual(before, tree_bytes(output))

    def test_lazy_schema_creation_permissions_and_environment_default(self):
        data_home = self.root / "configured-home"
        with mock.patch.dict(os.environ, {"CLONAMIC_DATA_HOME": str(data_home)}):
            result = self.runtime.capture("환경 경로로 저장해줘.".encode("utf-8"))
            database = data_home / "my-language" / "style.sqlite3"
        self.assertEqual("captured", result["status"])
        self.assertTrue(database.is_file())
        self.assertEqual(0o600, database.stat().st_mode & 0o777)
        self.assertEqual(0o700, database.parent.stat().st_mode & 0o777)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(1, connection.execute("PRAGMA user_version").fetchone()[0])

    def test_corrupt_unversioned_and_future_databases_fail_closed(self):
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        before = corrupt.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            self.runtime.inspect(corrupt)
        self.assertEqual(before, corrupt.read_bytes())

        legacy = self.root / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy)) as connection:
            connection.execute("CREATE TABLE legacy_data (value TEXT)")
        with self.assertRaises(sqlite3.DatabaseError):
            self.runtime.inspect(legacy)
        with closing(sqlite3.connect(legacy)) as connection:
            self.assertEqual(0, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertIsNotNone(
                connection.execute("SELECT name FROM sqlite_master WHERE name = 'legacy_data'").fetchone()
            )

        future = self.root / "future.sqlite3"
        with closing(sqlite3.connect(future)) as connection:
            connection.execute("PRAGMA user_version = 99")
        with self.assertRaises(sqlite3.DatabaseError):
            self.runtime.inspect(future)
        with closing(sqlite3.connect(future)) as connection:
            self.assertEqual(99, connection.execute("PRAGMA user_version").fetchone()[0])

    def test_long_korean_end_to_end_profile_and_portable_review_contract(self):
        payload = """결론부터 짧게 말해줘. 내가 요청한 범위 안에서만 작업하고 과한 설명은 하지 말아줘.

- 첫째, 측정한 결과를 먼저 적어줘.
- 둘째, 확인하지 않은 내용은 사실처럼 쓰지 말아줘.
- 셋째, 코드와 숫자와 인용문은 절대 바꾸지 말아줘.

한국어를 기본으로 하되 API, SQLite, UTF-8 같은 식별자는 그대로 유지해. 작업이 끝나면 핵심 결과만 목록으로 정리해줘."""
        result = self.capture(payload)
        profile = result["profile"]
        self.assertEqual("ko", profile["language"]["dominant"])
        self.assertGreater(profile["sentence_rhythm"]["mean_sentences_per_sample"], 4)
        self.assertEqual(1, profile["list_habits"]["bullet_samples"])
        self.assertGreater(profile["code_switching"]["mean_latin_token_ratio"], 0)
        output = self.root / "portable"
        self.runtime.export_checkpoint(output, path=self.database)
        apply_skill = (output / "skills" / "clonamic-my-language" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        review_skill = (
            output / "skills" / "clonamic-my-language-review" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Run exactly one review pass", apply_skill)
        self.assertIn("otherwise apply the same preservation checks sequentially", apply_skill)
        for preserved in ("facts", "quoted text", "numbers", "identifiers", "code"):
            self.assertIn(preserved, review_skill)

    def test_runtime_has_no_background_network_server_or_nonstdlib_contract(self):
        source = RUNTIME_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "import requests",
            "import httpx",
            "import chromadb",
            "import watchdog",
            "import fastapi",
            "import flask",
            "subprocess.Popen",
            "docker",
            "cron",
        ):
            self.assertNotIn(forbidden, source.casefold())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("No command watches files", readme)


if __name__ == "__main__":
    unittest.main()
