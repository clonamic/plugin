from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "clonamic-writing-plugin"
SKILLS = [
    "anti-ai-writing",
    "clonamic-unslop",
    "dumbify",
    "storytelling",
    "viral-hooks",
    "voice-dna",
]


class PackageTests(unittest.TestCase):
    def test_agent_plugin_shape(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        )
        self.assertEqual(manifest["name"], PLUGIN)
        self.assertEqual(manifest["version"], "1.0.1")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["skills"], "./skills/")
        found = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
        self.assertEqual(found, SKILLS)
        self.assertFalse((ROOT / "skills" / "clonamic-korean").exists())

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
