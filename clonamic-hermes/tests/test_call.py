from __future__ import annotations

import importlib.util
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "clonamic-hermes"
CALL = ROOT / "skills" / PLUGIN / "scripts" / "call.py"
EXECUTABLE = "hermes"


class CallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.bin = Path(self.temp.name)
        fake_source = (
            "import os, subprocess, sys, time\n"
            "if os.environ.get('FAKE_MODE') == 'sleep':\n"
            "    open(os.environ['PID_FILE'], 'w').write(str(os.getpid()))\n"
            "    time.sleep(60)\n"
            "prompt = sys.stdin.read()\n"
            "if '--prompt-file' in sys.argv:\n"
            "    path = sys.argv[sys.argv.index('--prompt-file') + 1]\n"
            "    prompt = open(path, encoding='utf-8').read()\n"
            "    print('prompt_file_mode=' + oct(os.stat(path).st_mode & 0o777))\n"
            "if os.environ.get('FAKE_MODE') == 'orphan':\n"
            "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "    open(os.environ['PID_FILE'], 'w').write(str(child.pid))\n"
            "if os.environ.get('FAKE_MODE') == 'large':\n"
            "    print('A' * 200000)\n"
            "    print('B' * 200000, file=sys.stderr)\n"
            "    raise SystemExit(0)\n"
            "print('argv=' + repr(sys.argv[1:]))\n"
            "print('prompt=' + repr(prompt))\n"
            "print('OPENAI_API_KEY=\"open ai secret value\"')\n"
            "print(\"ANTHROPIC_API_KEY='anthropic multi word key'\")\n"
            "print('XAI_API_KEY=xai-provider-secret')\n"
            "print('HERMES_API_KEY=hermes-provider-secret')\n"
            "print('token bare token with spaces')\n"
            "print('password: \"multi word password\"')\n"
            "print('Authorization: Bearer bearer-secret', file=sys.stderr)\n"
        )
        if os.name == "nt":
            helper = self.bin / "fake_executor.py"
            helper.write_text(fake_source, encoding="utf-8")
            fake = self.bin / f"{EXECUTABLE}.cmd"
            fake.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0fake_executor.py" %*\r\n', encoding="utf-8")
        else:
            fake = self.bin / EXECUTABLE
            fake.write_text(f"#!{sys.executable}\n{fake_source}", encoding="utf-8")
            fake.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin}{os.pathsep}{self.env.get('PATH', '')}"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, *args: str, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        if not CALL.is_file():
            self.fail("scripts/call.py is missing")
        proc = subprocess.run(
            [sys.executable, str(CALL), *args], text=True, capture_output=True,
            env=env or self.env, timeout=5, check=False,
        )
        return proc, json.loads(proc.stdout)

    def test_package_shape(self) -> None:
        self.assertTrue(CALL.is_file())
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(manifest["name"], PLUGIN)
        self.assertEqual(manifest["license"], "MIT")
        skill = ROOT / "skills" / PLUGIN / "SKILL.md"
        self.assertIn(f"name: {PLUGIN}", skill.read_text(encoding="utf-8"))

    def test_success_is_json_and_redacted(self) -> None:
        proc, result = self.call("--cli-arg=--model", "--cli-arg=test-model", "--", "hello")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(result["executor"], PLUGIN)
        self.assertTrue(result["ok"])
        self.assertFalse(result["timed_out"])
        self.assertEqual(
            result["output"].splitlines()[0],
            "argv=['--model', 'test-model', '--ignore-rules', '-z', 'hello', '-t', '']",
        )
        rendered = json.dumps(result)
        self.assertNotIn("open ai secret value", rendered)
        self.assertNotIn("anthropic multi word key", rendered)
        self.assertNotIn("xai-provider-secret", rendered)
        self.assertNotIn("hermes-provider-secret", rendered)
        self.assertNotIn("bare token with spaces", rendered)
        self.assertNotIn("multi word password", rendered)
        self.assertNotIn("bearer-secret", rendered)
        self.assertIn("<redacted>", rendered)

    def test_rejects_permission_and_tool_flags(self) -> None:
        for value in (
            "--permission-mode",
            "--sandbox",
            "--tools",
            "--dangerously-skip-permissions",
            "--bypass",
            "--yolo",
            "--unknown",
        ):
            with self.subTest(value=value):
                proc, result = self.call(f"--cli-arg={value}", "hello")
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(result["error"]["code"], "cli_arg_rejected")

    def test_allows_benign_effort_and_output_flags(self) -> None:
        proc, result = self.call(
            "--cli-arg=--effort",
            "--cli-arg=high",
            "--cli-arg=--output-format=json",
            "--cli-arg=--json",
            "hello",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("'--effort', 'high', '--output-format=json', '--json'", result["output"])

    def test_output_capture_is_bounded(self) -> None:
        env = self.env.copy()
        env["FAKE_MODE"] = "large"
        proc, result = self.call("hello", env=env)
        self.assertEqual(proc.returncode, 0)
        self.assertLess(len(result["output"]), 70000)
        self.assertLess(len(result["stderr"]), 70000)
        self.assertIn("[output truncated]", result["output"])
        self.assertIn("[output truncated]", result["stderr"])

    def test_active_executor_blocks_recursion(self) -> None:
        env = self.env.copy()
        env["CLONAMIC_EXECUTOR_ACTIVE"] = "existing"
        proc, result = self.call("hello", env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "recursion_blocked")

    def test_timeout_terminates_process(self) -> None:
        pid_file = self.bin / "pid"
        env = self.env.copy()
        env["FAKE_MODE"] = "sleep"
        env["PID_FILE"] = str(pid_file)
        proc, result = self.call("--timeout", "1.5", "hello", env=env)
        self.assertEqual(proc.returncode, 124)
        self.assertTrue(result["timed_out"])
        pid = int(pid_file.read_text(encoding="utf-8"))
        if os.name == "nt":
            listing = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                text=True,
                capture_output=True,
                check=False,
            )
            rows = csv.reader(listing.stdout.splitlines())
            self.assertFalse(any(len(row) > 1 and row[1].strip() == str(pid) for row in rows))
        else:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_normal_exit_cleans_descendant_process_tree(self) -> None:
        pid_file = self.bin / "orphan-pid"
        env = self.env.copy()
        env["FAKE_MODE"] = "orphan"
        env["PID_FILE"] = str(pid_file)
        proc, result = self.call("hello", env=env)
        self.assertEqual(0, proc.returncode, result)
        pid = int(pid_file.read_text(encoding="utf-8"))
        if os.name != "nt":
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_windows_termination_uses_kill_on_close_job(self) -> None:
        spec = importlib.util.spec_from_file_location("clonamic_hermes_call", CALL)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        source = CALL.read_text(encoding="utf-8")
        self.assertIn("_windows_job", source)
        self.assertIn("0x00002000", source)
        self.assertNotIn('"taskkill"', source)

    def test_skill_discloses_prompt_argv_visibility(self) -> None:
        skill = (ROOT / "skills" / PLUGIN / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("process inspection", skill)

    def test_skill_forbids_self_hosting(self) -> None:
        skill = (ROOT / "skills" / PLUGIN / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Never call this Hermes wrapper from Hermes itself", skill)


if __name__ == "__main__":
    unittest.main()
