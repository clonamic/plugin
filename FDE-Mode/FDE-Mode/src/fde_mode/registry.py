"""~/.clonamic/fde-mode/registry.json — which projects have FDE state, so one
dashboard can switch between them. Project data itself never leaves the project."""
from __future__ import annotations

from pathlib import Path

from fde_mode.paths import global_dir
from fde_mode.util import iso, read_json, write_json


def _file() -> Path:
    return global_dir() / "registry.json"


def load() -> dict:
    return read_json(_file(), {"projects": []}) or {"projects": []}


def touch(root: Path, name: str) -> None:
    data = load()
    root_s = str(root.resolve())
    items = [p for p in data["projects"] if p.get("root") != root_s]
    items.insert(0, {"root": root_s, "name": name or Path(root_s).name, "last_used": iso()})
    data["projects"] = items[:50]
    write_json(_file(), data)


def projects() -> list[dict]:
    return [p for p in load()["projects"] if (Path(p["root"]) / ".claude" / "fde-mode" / "fde.db").exists()]
