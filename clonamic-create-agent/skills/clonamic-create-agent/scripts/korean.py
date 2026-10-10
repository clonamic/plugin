"""Locate the installed clonamic-korean skill (rules + checker) on this machine, or say how to install it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = "skills/clonamic-korean/SKILL.md"
HOME_GLOBS = [
    f".claude/plugins/cache/*/clonamic-korean/*/{SKILL}",
    f".codex/plugins/cache/*/clonamic-korean/*/{SKILL}",
    f".cursor/plugins/local/clonamic-korean/{SKILL}",
    f".grok/installed-plugins/*clonamic-korean*/{SKILL}",
]
REPO = "https://github.com/clonamic/plugin"
INSTALL = {
    "claude": ["claude plugin marketplace add clonamic/plugin", "claude plugin install clonamic-korean@clonamic"],
    "codex": ["codex plugin marketplace add clonamic/plugin", "codex plugin add clonamic-korean@clonamic"],
    "cursor": [f"git clone --depth 1 {REPO} /tmp/clonamic-plugin && "
               "cp -R /tmp/clonamic-plugin/clonamic-korean ~/.cursor/plugins/local/clonamic-korean"],
    "grok": [f"grok plugin install {REPO}#clonamic-korean --trust", "grok plugin enable clonamic-korean"],
}
RULES = ["ai-tells.md", "rewriting.md", "preserve.md", "norms.md", "plain-korean.md"]


def locate() -> Path | None:
    """The clonamic-korean skill folder. CLONAMIC_KOREAN_ROOT wins; else the newest install under the home folder."""
    if root := os.environ.get("CLONAMIC_KOREAN_ROOT"):
        for candidate in (Path(root), Path(root) / "skills/clonamic-korean"):
            if (candidate / "SKILL.md").is_file():
                return candidate
        return None
    home = Path.home()
    hits = {p for pattern in HOME_GLOBS for p in home.glob(pattern) if p.is_file()}
    return max(hits, key=lambda p: p.stat().st_mtime).parent if hits else None


def check(text: str | None = None) -> tuple[dict, int]:
    """Without text: where the skill and its rule files are (or how to install). With text: run its draft checker."""
    skill = locate()
    if skill is None:
        return {"ok": False, "found": False, "repo": REPO, "install": INSTALL}, 4
    rules = [str(skill / "references" / r) for r in RULES if (skill / "references" / r).is_file()]
    info = {"ok": True, "found": True, "skill_dir": str(skill), "skill": str(skill / "SKILL.md"), "rules": rules}
    if text is None:
        return info, 0
    script = skill / "scripts" / "check_revision.py"
    if not script.is_file():
        return info | {"checked": False}, 0
    with tempfile.TemporaryDirectory(prefix="cagent-korean-") as tmp:  # removed when the check ends
        draft = Path(tmp) / "draft.md"
        draft.write_text(text, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script), "--after", str(draft), "--json"],
                              capture_output=True, text=True, encoding="utf-8")
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        report = {"raw": (proc.stdout or proc.stderr).strip()}
    return info | {"checked": True, "exit_code": proc.returncode, "report": report}, proc.returncode
