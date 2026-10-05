import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SYNC = REPO / "scripts" / "sync_manifests.py"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def plugins() -> list[Path]:
    found = [p.parent for p in REPO.glob("clonamic-*/plugin.json")]
    found += [p.parent for p in REPO.glob("clonamic-herness-plugin/plugins/*/plugin.json")]
    return sorted(found)


class ManifestSyncTest(unittest.TestCase):
    def test_derived_manifests_are_current_and_valid(self):
        proc = subprocess.run(
            [sys.executable, str(SYNC), "--check"], capture_output=True, text=True, check=False
        )
        self.assertEqual(0, proc.returncode, proc.stderr)

    def test_every_plugin_has_standard_root_and_claude_manifest(self):
        for plugin in plugins():
            with self.subTest(plugin=plugin.relative_to(REPO).as_posix()):
                root = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
                self.assertEqual(SCHEMA, root["$schema"])
                self.assertNotIn("skills", root)
                claude = json.loads((plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
                self.assertEqual(root["name"], claude["name"])
                self.assertEqual(root.get("version"), claude.get("version"))

    def test_marketplaces_list_the_same_plugins(self):
        claude = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        codex = json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        names = [entry["name"] for entry in claude["plugins"]]
        self.assertEqual(names, [entry["name"] for entry in codex["plugins"]])
        for entry in claude["plugins"]:
            self.assertTrue((REPO / entry["source"] / "plugin.json").is_file(), entry)


if __name__ == "__main__":
    unittest.main()
