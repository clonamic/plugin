from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "clonamic-task-log"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ALLOWED_KEYS = {"$schema", "name", "version", "description", "license", "author", "keywords", "homepage", "repository"}


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "SKILL.md needs YAML frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, match.group(2)


def hangul_ratio(text: str) -> float:
    prose = re.sub(r"```.*?```|`[^`]*`|\([^)]*\.md\)", "", text, flags=re.DOTALL)
    hangul = len(re.findall(r"[가-힣]", prose))
    latin = len(re.findall(r"[A-Za-z]", prose))
    return hangul / max(1, hangul + latin)


class ManifestTests(unittest.TestCase):
    def test_root_manifest(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertLessEqual(set(manifest), ALLOWED_KEYS)
        self.assertEqual(manifest["$schema"], SCHEMA)
        self.assertEqual(manifest["name"], "clonamic-task-log")
        self.assertEqual(manifest["name"], ROOT.name)
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["author"], {"name": "Clonamic"})
        self.assertEqual(manifest["repository"], "https://github.com/clonamic/plugin")
        self.assertNotIn("homepage", manifest)
        self.assertIn("/clonamic-task-log", manifest["description"])

    def test_single_mit_license_and_no_external_attribution(self) -> None:
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", text)
        self.assertEqual(re.findall(r"^Copyright .*$", text, re.MULTILINE), ["Copyright (c) 2026 Clonamic"])
        banned = re.compile(r"hermes|ktb|kakaotech|adapted from|fork of|inspired by", re.I)
        for path in ROOT.rglob("*"):
            if path.is_file() and "tests" not in path.parts and path.suffix in {".md", ".py", ".json", ".yaml"}:
                self.assertIsNone(banned.search(path.read_text(encoding="utf-8")), path)


class StructureTests(unittest.TestCase):
    def test_one_skill_with_scripts_inside(self) -> None:
        self.assertEqual(sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir()), ["clonamic-task-log"])
        self.assertTrue((SKILL / "SKILL.md").is_file())
        scripts = sorted(p.name for p in (SKILL / "scripts").glob("*.py"))
        self.assertEqual(scripts, ["collect.py", "common.py", "gate.py", "preflight.py", "progress.py", "redact.py",
                                   "score.py", "tasklog.py", "write.py"])
        for path in ROOT.rglob("*"):
            self.assertNotIn(path.name, {"__pycache__", ".venv", "node_modules"}, path)

    def test_explicit_command_frontmatter_and_korean_body(self) -> None:
        fields, body = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(fields["name"], "clonamic-task-log")
        self.assertEqual(fields["disable-model-invocation"], "true")
        self.assertEqual(fields["user-invocable"], "true")
        self.assertIn("/clonamic-task-log", fields["description"])
        self.assertIn("/clonamic-task-log`를 직접 입력했을 때만", body)
        self.assertGreater(hangul_ratio(body), 0.6)

    def test_writer_subagent(self) -> None:
        fields, body = frontmatter((ROOT / "agents" / "clonamic-task-logger.md").read_text(encoding="utf-8"))
        self.assertEqual(fields["name"], "clonamic-task-logger")
        self.assertEqual(fields["model"], "sonnet")
        self.assertTrue(fields["description"])
        self.assertIn("파일을 만들거나 고치지 않는다", body)
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("clonamic-task-log:clonamic-task-logger", skill)
        self.assertIn("`luna`", skill)
        self.assertIn("서브에이전트를 쓸 수 없음", skill)
        self.assertIn("리더가 같은 본문을 따라 차례로 직접 쓰고", skill)

    def test_readme_is_korean_and_top_down(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(headings[0], "## 핵심 요약")
        self.assertGreater(hangul_ratio(text), 0.5)
        for topic in ("log-part", "개인 페이지 / <프로젝트명> / 작업로그", "clonamic-task-logger", "[측정]", "rebind"):
            self.assertIn(topic, text)

    def test_codex_policy_is_explicit_only(self) -> None:
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", text)
        self.assertIn("$clonamic-task-log", text)

    def test_local_links_resolve(self) -> None:
        for doc in [SKILL / "SKILL.md", *(SKILL / "references").glob("*.md")]:
            for target in re.findall(r"\]\(([^)#\s]+)\)", doc.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target) or target.endswith(".md") and re.match(r"\d{4}-", target):
                    continue
                self.assertTrue((doc.parent / target).exists(), f"{doc.name} -> {target}")

    def test_scripts_guard_python_version(self) -> None:
        text = (SKILL / "scripts" / "tasklog.py").read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 12)", text)
        self.assertIn("uv python install 3.12", text)


if __name__ == "__main__":
    unittest.main()
