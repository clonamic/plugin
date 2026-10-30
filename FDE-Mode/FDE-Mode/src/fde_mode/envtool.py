""".env without exposure: report set/empty, change allow-listed non-secret keys.

Values are never printed. Keys that look secret can never be set through here,
even if the binding lists them by mistake.
"""
from __future__ import annotations

import re
from pathlib import Path

SECRETISH = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|DATABASE_URL|QDRANT_URL)", re.I)
LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def check(root: Path, keys: list[str] | None = None, file: str = ".env") -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in _read(root / file):
        m = LINE.match(ln)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
        if keys and k not in keys:
            continue
        out[k] = "set" if v else "empty"
    for k in keys or []:
        out.setdefault(k, "missing")
    return out


def set_value(root: Path, key: str, value: str, allowed: list[str], file: str = ".env") -> str:
    if key not in (allowed or []):
        raise PermissionError(f"{key} 는 project.toml [guard].env_editable 에 없습니다")
    if SECRETISH.search(key):
        raise PermissionError(f"{key} 는 비밀값처럼 보여 여기서 바꾸지 않습니다(직접 수정)")
    if "#" in value or "\n" in value:
        raise ValueError("값에 # 이나 줄바꿈을 넣지 않습니다(systemd EnvironmentFile 규칙)")
    path = root / file
    lines = _read(path)
    done = False
    for i, ln in enumerate(lines):
        m = LINE.match(ln)
        if m and m.group(1) == key:
            lines[i] = f"{key}={value}"
            done = True
    if not done:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "updated" if done else "added"
