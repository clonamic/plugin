"""Small shared helpers: time, JSON I/O, Korean-aware text normalisation."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

KST = _dt.timezone(_dt.timedelta(hours=9))


def now(tz: _dt.tzinfo | None = None) -> _dt.datetime:
    override = os.environ.get("FDE_NOW")  # tests and rehearsals can pin the clock
    if override:
        dt = _dt.datetime.fromisoformat(override)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz or KST)
    return _dt.datetime.now(tz or KST)


def iso(dt: _dt.datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default


def write_json(path: str | Path, data: Any) -> Path:
    """Atomic write so the dashboard never reads half a file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=p.suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, p)
    return p


def write_text(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=p.suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, p)
    return p


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def loads(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


_PUNCT = re.compile(r"[\s​\.,!?~…·:;'\"“”‘’()\[\]{}<>\-_/\\|*#@^`=+]+")


def norm(text: str) -> str:
    """Normalise for fuzzy comparison: NFC, lower-case, strip spaces/punctuation."""
    t = unicodedata.normalize("NFC", text or "").lower()
    return _PUNCT.sub("", t)


def ngrams(text: str, n: int = 3) -> set[str]:
    t = norm(text)
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def jaccard(a: str, b: str, n: int = 3) -> float:
    ga, gb = ngrams(a, n), ngrams(b, n)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def containment(small: str, big: str, n: int = 3) -> float:
    """Share of `small`'s n-grams that appear in `big` (1.0 = fully contained)."""
    gs, gb = ngrams(small, n), ngrams(big, n)
    if not gs:
        return 0.0
    return len(gs & gb) / len(gs)


# Key-shaped strings: provider keys, auth headers, and long mixed-case+digit tokens. A lowercase hex run (commit SHA,
# uuid) is not a secret and stays readable.
SECRET = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|KakaoAK\s+[A-Za-z0-9._\-]+|Bearer\s+[A-Za-z0-9._\-]{16,}|"
                    r"(?i:(?:token|api[_-]?key|secret|password)\s*[=:]\s*['\"]?[A-Za-z0-9._\-]{16,})|"
                    r"(?<![A-Za-z0-9_\-])(?=[A-Za-z0-9_\-]*[A-Z])(?=[A-Za-z0-9_\-]*[a-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{32,}")


def scrub(text: str) -> str:
    return SECRET.sub("[가림]", text or "")


def scrub_values(obj: Any) -> Any:
    """`scrub` every string inside a JSON value — never the serialised text, whose quotes a pattern could swallow."""
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, list):
        return [scrub_values(v) for v in obj]
    if isinstance(obj, dict):
        return {k: scrub_values(v) for k, v in obj.items()}
    return obj


def short(text: str, limit: int = 80) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[: limit - 1] + "…"


def slug(text: str) -> str:
    t = re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", t) or "x"
