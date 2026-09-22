from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/clonamic_migrate.py"


class MigrationToolTest(unittest.TestCase):
    def run_tool(self, command: str, home: Path, backup: Path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), command, "--home", str(home), "--backup", str(backup)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_apply_verify_and_rollback_are_reversible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            backup = root / "backup"
            (home / ".agents").mkdir(parents=True)
            (home / ".codex/skills/clx-model").mkdir(parents=True)
            (home / ".local/bin").mkdir(parents=True)
            (home / ".agents/AGENTS.md").write_text(
                "Use clx-supercoder and /clx-model.\n", encoding="utf-8"
            )
            old_cli = home / ".local/bin/clx-supercoder"
            old_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            old_cli.chmod(0o755)

            applied = self.run_tool("apply", home, backup)
            self.assertEqual(0, applied.returncode, applied.stderr)
            self.assertIn(
                "clonamic-supercoder",
                (home / ".agents/AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertTrue((home / ".local/bin/clonamic-supercoder").is_file())
            self.assertFalse((home / ".codex/skills/clx-model").exists())
            manifest = json.loads((backup / "migration/manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["files"])
            self.assertTrue(manifest["moves"])

            verified = self.run_tool("verify", home, backup)
            self.assertEqual(0, verified.returncode, verified.stderr)

            rolled_back = self.run_tool("rollback", home, backup)
            self.assertEqual(0, rolled_back.returncode, rolled_back.stderr)
            self.assertEqual(
                "Use clx-supercoder and /clx-model.\n",
                (home / ".agents/AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertTrue((home / ".codex/skills/clx-model").is_dir())
            self.assertFalse((home / ".local/bin/clonamic-supercoder").exists())


if __name__ == "__main__":
    unittest.main()
