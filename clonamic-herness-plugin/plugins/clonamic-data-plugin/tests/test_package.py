import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_manifest_and_skill_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-data-plugin", manifest["name"])
        self.assertEqual(["clonamic-dataset-work"], [p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")])

    def test_dataset_guidance_is_host_portable_and_secret_safe(self):
        skill = (ROOT / "skills/clonamic-dataset-work/SKILL.md").read_text(encoding="utf-8")
        for forbidden in (
            "df -g",
            "tmutil",
            "~/Documents",
            "claude.ai",
            "HF_TOKEN",
            "≥ 30G",
        ):
            self.assertNotIn(forbidden, skill)
        for required in (
            "shutil.disk_usage",
            "proportional safety margin",
            "explicitly supplied by the user",
            "Never request a token value",
        ):
            self.assertIn(required, skill)


if __name__ == "__main__":
    unittest.main()
