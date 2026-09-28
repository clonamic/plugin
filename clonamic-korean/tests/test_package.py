from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "clonamic-korean"
SCRIPT = SKILL / "scripts" / "check_bounds.py"
BANNED = ("humani" + "ze", "humani" + "ze-korean", "humani" + "ze-redo", "humani" + "ze-scan")


def load_bounds():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ko_bounds", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackageTests(unittest.TestCase):
    def test_manifest_and_single_explicit_skill(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        )
        self.assertEqual(manifest["name"], "clonamic-korean")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["skills"], "./skills/")
        skills = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(skills, ["clonamic-korean"])
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: clonamic-korean", skill)
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("/clonamic-korean", skill)
        self.assertIn("choose", skill.lower())
        policy = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", policy)

    def test_readme_stays_to_the_problem(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("/clonamic-korean", readme)
        for banned in ("참고", "설치", "github.com", "http://", "https://"):
            self.assertNotIn(banned, readme)

    def test_upstream_command_names_are_absent(self) -> None:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            blob = path.relative_to(ROOT).as_posix().lower()
            if path.suffix in {".md", ".py", ".json", ".yaml", ".yml"}:
                blob += "\n" + path.read_text(encoding="utf-8").lower()
            for name in BANNED:
                self.assertNotIn(name, blob, path)

    def test_rejected_signals_are_not_active_rules(self) -> None:
        catalog = (SKILL / "references" / "catalog.md").read_text(encoding="utf-8")
        active, marker, inactive = catalog.partition("## 켜지 않는 신호")
        self.assertTrue(marker)
        self.assertNotIn("`를 통해`", active)
        self.assertNotIn("무조건 평서", active)
        self.assertIn("`를 통해`를 무조건 삭제하지 않는다", inactive)
        self.assertIn("것이다", inactive)
        self.assertIn("대명사", inactive)

    def test_bounds_script_warns_and_stops(self) -> None:
        short = "가나다라마바사아자차"
        mild = "가나다라마바사아자타"
        heavy = "타파하거너더러머버서"
        self.assertEqual(0, self._run(short, mild))
        self.assertEqual(2, self._run(short, heavy))

    def _run(self, before: str, after: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "before.txt"
            revised = folder / "after.txt"
            source.write_text(before, encoding="utf-8")
            revised.write_text(after, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--before", str(source), "--after", str(revised)],
                capture_output=True,
                text=True,
                check=False,
            )
        return proc.returncode


if __name__ == "__main__":
    unittest.main()
