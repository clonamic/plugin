from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "clonamic-writing-plugin"
SKILL_NAME = "clonamic-korean"
SKILL = ROOT / "skills" / SKILL_NAME
SCOPE_SCRIPT = SKILL / "scripts" / "scope.py"


def load_scope():
    if not SCOPE_SCRIPT.is_file():
        raise AssertionError("scope.py is missing")
    spec = importlib.util.spec_from_file_location("clonamic_korean_scope", SCOPE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackageTests(unittest.TestCase):
    def test_agent_plugin_shape(self) -> None:
        manifest_path = ROOT / "plugin.json"
        self.assertTrue(manifest_path.is_file(), "plugin.json is missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(manifest["name"], PLUGIN)
        self.assertEqual(manifest["license"], "MIT")
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(f"name: {SKILL_NAME}", skill)
        self.assertTrue((SKILL / "references" / "korean-patterns.md").is_file())
        self.assertGreaterEqual(len(list((ROOT / "skills").glob("*/SKILL.md"))), 7)

    def test_plain_documents_are_supported(self) -> None:
        scope = load_scope()
        for path in ("notice.md", "policy.txt", "guide.rst", "manual.adoc"):
            with self.subTest(path=path):
                result = scope.assess(path, "이 문서는 배포 절차를 설명합니다.", "document")
                self.assertTrue(result["applicable"], result)

    def test_non_document_surfaces_are_rejected(self) -> None:
        scope = load_scope()
        for kind in ("chat", "work-report", "code", "spreadsheet", "slide", "email"):
            with self.subTest(kind=kind):
                result = scope.assess("input.txt", "검토할 내용", kind)
                self.assertFalse(result["applicable"], result)

    def test_excluded_file_types_are_not_read_as_documents(self) -> None:
        scope = load_scope()
        for path in ("main.py", "data.csv", "book.xlsx", "deck.pptx", "message.eml"):
            with self.subTest(path=path):
                result = scope.assess(path, "검토할 내용", "document")
                self.assertFalse(result["applicable"], result)

    def test_work_report_names_are_rejected(self) -> None:
        scope = load_scope()
        for path in ("work-report.md", "completion-report.txt", "작업보고.md", "완료보고.txt"):
            with self.subTest(path=path):
                result = scope.assess(path, "검증 결과", "document")
                self.assertFalse(result["applicable"], result)

    def test_preservation_contract_keeps_high_risk_spans_and_consistency(self) -> None:
        contract = (SKILL / "references" / "preservation.md").read_text(encoding="utf-8")
        for phrase in (
            "link fragments",
            "masked personal data",
            "conflict markers",
            "legal, medical, and financial duties",
            "Do not convert units",
            "Lost citations or links invalidate",
            "Contradictions between headings, prose, tables, diagrams, or counts",
        ):
            self.assertIn(phrase, contract)

    def test_active_writing_skills_have_no_vendor_home_profile_path(self) -> None:
        for skill_path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            text = skill_path.read_text(encoding="utf-8")
            with self.subTest(skill=skill_path.parent.name):
                for forbidden in ("~/.agents", "~/.claude", "~/.codex", "~/.grok"):
                    self.assertNotIn(forbidden, text)
        voice = (ROOT / "skills/voice-dna/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("explicit private profile path supplied by the caller", voice)
        self.assertIn("do not persist it automatically", voice)


if __name__ == "__main__":
    unittest.main()
