#!/usr/bin/env python3
"""Reject non-document surfaces before Korean prose review."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SUPPORTED_EXTENSIONS = frozenset({"", ".md", ".markdown", ".txt", ".rst", ".adoc"})
EXCLUDED_KINDS = frozenset({"chat", "work-report", "code", "spreadsheet", "slide", "email"})
WORK_REPORT_NAME = re.compile(r"(?:work|completion)[-_ ]?report|작업[-_ ]?보고|완료[-_ ]?보고", re.I)


def assess(path: str | Path | None, text: str, kind: str = "document") -> dict[str, object]:
    normalized_kind = (kind or "document").strip().lower()
    name = str(path or "")
    suffix = Path(name).suffix.lower() if name else ""

    if normalized_kind in EXCLUDED_KINDS or normalized_kind != "document":
        return {"applicable": False, "reason": "excluded_surface", "kind": normalized_kind}
    if suffix not in SUPPORTED_EXTENSIONS:
        return {"applicable": False, "reason": "excluded_file_type", "kind": normalized_kind}
    if WORK_REPORT_NAME.search(Path(name).name):
        return {"applicable": False, "reason": "work_report", "kind": normalized_kind}
    if not (text or "").strip():
        return {"applicable": False, "reason": "empty", "kind": normalized_kind}
    if len(re.findall(r"[가-힣]", text)) < 4:
        return {"applicable": False, "reason": "not_korean_prose", "kind": normalized_kind}
    return {"applicable": True, "reason": "korean_document", "kind": normalized_kind}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--kind", default="document")
    args = parser.parse_args()

    path = Path(args.path) if args.path else None
    if path and (args.kind != "document" or path.suffix.lower() not in SUPPORTED_EXTENSIONS or WORK_REPORT_NAME.search(path.name)):
        record = assess(path, "검토 대상 문서", args.kind)
    else:
        try:
            text = path.read_text(encoding="utf-8") if path else sys.stdin.read()
        except OSError as exc:
            record = {"applicable": False, "reason": "read_error", "error": str(exc), "kind": args.kind}
        else:
            record = assess(path, text, args.kind)
    print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return 0 if record["applicable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
