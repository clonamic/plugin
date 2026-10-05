from __future__ import annotations

import ast
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "clonamic-executor"
SKILL = "clonamic-delegate"
SKILL_DIR = ROOT / "skills" / SKILL
CALL = SKILL_DIR / "scripts" / "call.py"

FAKE_SOURCE = (
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
    "if os.environ.get('FAKE_MODE') == 'fail':\n"
    "    print('failed', file=sys.stderr)\n"
    "    raise SystemExit(7)\n"
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


class ProviderCase:
    """Shared contract; each subclass pins one provider's command line and prompt transport."""

    PROVIDER = ""
    EXPECTED_ARGV: list[str] = []

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.bin = Path(self.temp.name)
        if os.name == "nt":
            (self.bin / "fake_executor.py").write_text(FAKE_SOURCE, encoding="utf-8")
            fake = self.bin / f"{self.PROVIDER}.cmd"
            fake.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0fake_executor.py" %*\r\n', encoding="utf-8")
        else:
            fake = self.bin / self.PROVIDER
            fake.write_text(f"#!{sys.executable}\n{FAKE_SOURCE}", encoding="utf-8")
            fake.chmod(0o755)
        self.env = os.environ.copy()
        self.env.pop("CLONAMIC_EXECUTOR_ACTIVE", None)
        self.env["PATH"] = f"{self.bin}{os.pathsep}{self.env.get('PATH', '')}"
        for name in ("TMPDIR", "TMP", "TEMP"):
            self.env[name] = str(self.bin)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, *args: str, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict]:
        proc = subprocess.run(
            [sys.executable, str(CALL), "--provider", self.PROVIDER, *args],
            text=True,
            capture_output=True,
            env=env or self.env,
            timeout=10,
            check=False,
        )
        return proc, json.loads(proc.stdout)

    def assert_no_prompt_files(self) -> None:
        self.assertEqual([], list(self.bin.glob("clonamic-prompt-*.txt")))

    def argv_line(self, output: str) -> str:
        return next(line for line in output.splitlines() if line.startswith("argv="))

    def test_success_is_json_redacted_and_uses_read_only_command(self) -> None:
        proc, result = self.call("--cli-arg=--model", "--cli-arg=test-model", "--", "hello")
        self.assertEqual(proc.returncode, 0, result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], self.PROVIDER)
        self.assertFalse(result["timed_out"])
        self.assert_command(self.argv_line(result["output"]), result["output"])
        rendered = json.dumps(result)
        for secret in (
            "open ai secret value",
            "anthropic multi word key",
            "xai-provider-secret",
            "hermes-provider-secret",
            "bare token with spaces",
            "multi word password",
            "bearer-secret",
        ):
            self.assertNotIn(secret, rendered)
        self.assertIn("<redacted>", rendered)
        self.assert_no_prompt_files()

    def assert_command(self, argv_line: str, output: str) -> None:
        self.assertEqual(argv_line, "argv=" + repr(self.EXPECTED_ARGV))
        self.assertIn("prompt='hello'", output)

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
            "--cli-arg=--effort", "--cli-arg=high", "--cli-arg=--output-format=json", "--cli-arg=--json", "hello"
        )
        self.assertEqual(proc.returncode, 0, result)
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

    def test_upstream_failure_is_reported_and_cleaned_up(self) -> None:
        env = self.env.copy()
        env["FAKE_MODE"] = "fail"
        proc, result = self.call("hello", env=env)
        self.assertEqual(7, proc.returncode)
        self.assertEqual("upstream_error", result["error"]["code"])
        self.assert_no_prompt_files()

    def test_active_executor_blocks_recursion(self) -> None:
        env = self.env.copy()
        env["CLONAMIC_EXECUTOR_ACTIVE"] = "existing"
        proc, result = self.call("hello", env=env)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "recursion_blocked")

    def test_missing_cli_is_reported(self) -> None:
        env = self.env.copy()
        env["PATH"] = str(self.bin / "empty")
        proc, result = self.call("hello", env=env)
        self.assertEqual(proc.returncode, 127)
        self.assertEqual(result["error"]["code"], "missing_cli")

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
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], text=True, capture_output=True, check=False
            )
            rows = csv.reader(listing.stdout.splitlines())
            self.assertFalse(any(len(row) > 1 and row[1].strip() == str(pid) for row in rows))
        else:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        self.assert_no_prompt_files()

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


class ClaudeProviderTests(ProviderCase, unittest.TestCase):
    PROVIDER = "claude"
    EXPECTED_ARGV = ["-p", "--no-session-persistence", "--permission-mode", "plan", "--tools", "", "--model", "test-model"]


class GrokProviderTests(ProviderCase, unittest.TestCase):
    PROVIDER = "grok"

    def assert_command(self, argv_line: str, output: str) -> None:
        if os.name == "posix":
            self.assertEqual("prompt_file_mode=0o600", output.splitlines()[0])
        argv = ast.literal_eval(argv_line.removeprefix("argv="))
        prompt_file = argv[argv.index("--prompt-file") + 1]
        self.assertEqual(
            argv,
            ["--permission-mode", "plan", "--disable-web-search", "--no-subagents", "--tools", "",
             "--model", "test-model", "--prompt-file", prompt_file],
        )
        self.assertNotIn("hello", argv_line)
        self.assertIn("prompt='hello'", output)


class HermesProviderTests(ProviderCase, unittest.TestCase):
    PROVIDER = "hermes"
    EXPECTED_ARGV = ["--model", "test-model", "--ignore-rules", "-z", "hello", "-t", ""]

    def assert_command(self, argv_line: str, output: str) -> None:
        # Hermes takes the prompt as an argv value (disclosed in SKILL.md), not on stdin.
        self.assertEqual(argv_line, "argv=" + repr(self.EXPECTED_ARGV))
        self.assertIn("prompt=''", output)


class PackageTests(unittest.TestCase):
    def test_package_shape(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(manifest["name"], PLUGIN)
        self.assertEqual(manifest["name"], ROOT.name)
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["author"], {"name": "Clonamic"})
        self.assertEqual([p.name for p in (ROOT / "skills").iterdir() if p.is_dir()], [SKILL])
        self.assertIn(f"name: {SKILL}", (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))

    def test_unknown_provider_is_a_usage_error(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(CALL), "--provider", "codex", "hello"], text=True, capture_output=True, check=False
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["error"]["code"], "usage")

    def test_windows_termination_uses_kill_on_close_job(self) -> None:
        source = CALL.read_text(encoding="utf-8")
        self.assertIn("_windows_job", source)
        self.assertIn("0x00002000", source)
        self.assertNotIn('"taskkill"', source)

    def test_skill_forbids_self_hosting_and_discloses_argv_visibility(self) -> None:
        skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Never call this Claude wrapper from Claude itself", skill)
        self.assertIn("process inspection", skill)
        self.assertIn("CLONAMIC_EXECUTOR_ACTIVE", skill)


if __name__ == "__main__":
    unittest.main()
