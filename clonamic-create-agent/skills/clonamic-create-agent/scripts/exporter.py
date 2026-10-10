"""Write an export into the user's folder, touching only files this tool made; read design.json back."""

from __future__ import annotations

import json
from pathlib import Path

from schema import FORMAT
from store import data_dir

MARK = "clonamic-create-agent"


class ExportError(Exception):
    pass


def resolve(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise ExportError("저장 경로는 절대 경로나 ~로 시작해야 합니다.")
    target = target.resolve()
    home = Path.home().resolve()
    if target in (Path(target.anchor), home) or target in home.parents:
        raise ExportError("홈 폴더나 최상위 폴더에는 바로 내보낼 수 없습니다. 하위 폴더를 지정하세요.")
    if target == data_dir().resolve() or data_dir().resolve() in target.parents:
        raise ExportError("편집기 데이터 폴더 안에는 내보낼 수 없습니다.")
    if target.exists() and not target.is_dir():
        raise ExportError("저장 경로가 폴더가 아닙니다.")
    return target


def inside(target: Path, rel) -> bool:
    """A relative path that stays under target (no absolute paths, no .., no symlink escapes)."""
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        return False
    return target in (target / rel).resolve().parents


def previous(target: Path) -> list[str]:
    """Files listed by an earlier export's design.json; [] when the folder holds no export of ours.
    design.json may have been edited or come from elsewhere, so entries pointing outside the folder are dropped."""
    try:
        design = json.loads((target / "design.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(design, dict) or design.get("tool") != MARK or not isinstance(design.get("files"), list):
        return []
    return [rel for rel in design["files"] if inside(target, rel)] + ["design.json"]


def plan(path: str, files: dict[str, str]) -> dict:
    target = resolve(path)
    old = set(previous(target))
    existing = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()} if target.exists() else set()
    foreign = sorted(existing - old)
    clash = sorted(set(files) & set(foreign))
    return {"path": str(target), "foreign": foreign, "clash": clash, "remove": sorted(old - set(files))}


def write(path: str, files: dict[str, str]) -> dict:
    info = plan(path, files)
    if info["clash"]:
        raise ExportError("이 도구가 만들지 않은 같은 이름의 파일이 있어 덮어쓰지 않습니다: " + ", ".join(info["clash"]))
    target = Path(info["path"])
    if bad := [rel for rel in files if not inside(target, rel)]:
        raise ExportError("폴더 밖을 가리키는 파일 이름이 있어 내보내지 않습니다: " + ", ".join(bad))
    for rel in info["remove"]:
        (target / rel).unlink(missing_ok=True)
    for rel, text in files.items():
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    for folder in sorted({(target / r).parent for r in info["remove"]}, key=lambda p: len(p.parts), reverse=True):
        while folder != target and folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
            folder = folder.parent
    return {"path": info["path"], "written": len(files), "removed": info["remove"], "untouched": info["foreign"]}


def load_design(text: str) -> dict:
    """The doc inside an exported design.json, or the doc itself when given a bare document."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ExportError("design.json을 읽을 수 없습니다.") from exc
    doc = data.get("doc", data) if isinstance(data, dict) else None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("agents"), list):
        raise ExportError("이 편집기에서 내보낸 design.json이 아닙니다.")
    return doc
