import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageTest(unittest.TestCase):
    def test_manifest_and_skills(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-harness-admin-plugin", manifest["name"])
        self.assertEqual(5, len(list((ROOT / "skills").glob("*/SKILL.md"))))
        for path in (ROOT / "skills").glob("*/SKILL.md"):
            self.assertIn(f"name: {path.parent.name}", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
