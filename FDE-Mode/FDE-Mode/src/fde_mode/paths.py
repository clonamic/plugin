"""Where things live.

Plugin code  : <plugin root>/            (read-only, replaced on update)
Project state: <project>/.claude/fde-mode/ (per project, isolated)
Global state : ~/.clonamic/fde-mode/      (project registry, dashboard server, lessons)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

WORK_DIRNAME = ".claude/fde-mode"


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    here = Path(__file__).resolve().parents[2]
    if env and (Path(env) / "src" / "fde_mode").exists():
        return Path(env).resolve()
    return here


def global_dir() -> Path:
    base = os.environ.get("FDE_HOME")
    p = Path(base) if base else Path.home() / ".clonamic" / "fde-mode"
    p.mkdir(parents=True, exist_ok=True)
    return p


def project_root(start: str | Path | None = None) -> Path:
    """Resolve the project the session works on.

    Priority: FDE_PROJECT > CLAUDE_PROJECT_DIR > nearest ancestor that already has
    .claude/fde-mode > nearest ancestor with .git > the start directory itself.
    """
    for key in ("FDE_PROJECT", "CLAUDE_PROJECT_DIR"):
        v = os.environ.get(key)
        if v and Path(v).is_dir():
            return Path(v).resolve()
    cur = Path(start or os.getcwd()).resolve()
    for d in (cur, *cur.parents):
        if (d / WORK_DIRNAME).is_dir():
            return d
    for d in (cur, *cur.parents):
        if (d / ".git").exists():
            return d
    return cur


@dataclass(frozen=True)
class P:
    """All per-project paths in one place (so agents and the dashboard agree)."""

    root: Path

    @property
    def work(self) -> Path:
        return self.root / WORK_DIRNAME

    @property
    def db(self) -> Path:
        return self.work / "fde.db"

    @property
    def binding(self) -> Path:
        return self.work / "project.toml"

    @property
    def inbox(self) -> Path:
        return self.work / "inbox"

    @property
    def runs(self) -> Path:
        return self.work / "runs"

    @property
    def transcript(self) -> Path:
        return self.work / "transcript.jsonl"

    @property
    def board(self) -> Path:
        return self.work / "board.md"

    @property
    def persona(self) -> Path:
        return self.work / "persona.md"

    @property
    def spec(self) -> Path:
        return self.work / "spec.md"

    @property
    def docs(self) -> Path:
        """Living documents written by agents (persona.md lives one level up for history)."""
        return self.work / "docs"

    @property
    def tech(self) -> Path:
        return self.work / "tech"

    @property
    def data(self) -> Path:
        return self.work / "data"

    @property
    def rehearsal(self) -> Path:
        return self.work / "rehearsal"

    @property
    def sealed(self) -> Path:
        return self.work / "rehearsal" / "sealed"

    @property
    def run_dir(self) -> Path:
        return self.work / "run"

    @property
    def archive(self) -> Path:
        return self.work / "archive"

    def rel(self, path: Path | str) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(path)

    def ensure(self) -> "P":
        for d in (self.work, self.inbox, self.runs, self.docs, self.tech, self.data, self.run_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def for_project(start: str | Path | None = None) -> P:
    return P(project_root(start))
