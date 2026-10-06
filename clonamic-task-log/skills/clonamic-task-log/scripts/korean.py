"""Locate clonamic-korean's check_revision.py and run it in draft mode on an entry."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = "skills/clonamic-korean/scripts/check_revision.py"
HOME_GLOBS = [
    f".claude/plugins/cache/*/clonamic-korean/*/{SCRIPT}",
    f".codex/plugins/cache/*/clonamic-korean/*/{SCRIPT}",
    f".cursor/plugins/local/clonamic-korean/{SCRIPT}",
    f".grok/installed-plugins/**/clonamic-korean/{SCRIPT}",
]
REPO = "https://github.com/clonamic/plugin"
INSTALL = {
    "claude": ["claude plugin marketplace add clonamic/plugin", "claude plugin install clonamic-korean@clonamic"],
    "codex": ["codex plugin marketplace add clonamic/plugin", "codex plugin add clonamic-korean@clonamic"],
    "cursor": [f"git clone --depth 1 {REPO} /tmp/clonamic-plugin && "
               "cp -R /tmp/clonamic-plugin/clonamic-korean ~/.cursor/plugins/local/clonamic-korean"],
    "grok": [f"grok plugin install {REPO}#clonamic-korean --trust", "grok plugin enable clonamic-korean"],
}


def locate() -> Path | None:
    """CLONAMIC_KOREAN_ROOT (the skill folder, or a plugin folder holding it) wins; else the newest install."""
    if root := os.environ.get("CLONAMIC_KOREAN_ROOT"):
        for candidate in (Path(root) / "scripts/check_revision.py", Path(root) / SCRIPT):
            if candidate.is_file():
                return candidate
        return None
    home = Path.home()
    hits = [p for pattern in HOME_GLOBS for p in home.glob(pattern) if p.is_file()]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def check(entry: Path | None) -> tuple[dict, int]:
    """With an entry: run draft mode. Without: only report where the checker is (or how to install it)."""
    script = locate()
    if script is None:
        return {"ok": False, "found": False, "repo": REPO, "install": INSTALL}, 4
    if entry is None:
        return {"ok": True, "found": True, "path": str(script), "skill_dir": str(script.parent.parent)}, 0
    proc = subprocess.run([sys.executable, str(script), "--after", str(entry), "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        report = {"raw": (proc.stdout or proc.stderr).strip()}
    return {"ok": proc.returncode < 2, "found": True, "path": str(script), "exit_code": proc.returncode,
            "report": report}, proc.returncode
