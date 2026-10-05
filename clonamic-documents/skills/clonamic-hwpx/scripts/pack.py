#!/usr/bin/env python3
"""Pack an unpacked HWPX directory into a .hwpx file.

Writes `mimetype` first and uncompressed (OWPML/ODF container rule), copies every
other file byte-for-byte, and refuses to pack when validation finds errors.

Usage: python3 pack.py unpacked/ output.hwpx [--force]
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate import validate_hwpx  # noqa: E402


def pack_hwpx(input_dir: str, output_path: str, force: bool = False) -> bool:
    source = Path(input_dir)
    if not (source / "mimetype").is_file():
        print(f"Error: {source}/mimetype is missing", file=sys.stderr)
        return False
    report = validate_hwpx(str(source))
    report.print_report()
    if not report.is_valid and not force:
        print("Validation failed; fix the errors (or pass --force).", file=sys.stderr)
        return False
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.name != ".DS_Store")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in files:
            name = path.relative_to(source).as_posix()
            if name != "mimetype":
                zf.write(path, name)
    print(f"Created {output_path} ({len(files)} files)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack a directory into an HWPX file with validation")
    parser.add_argument("input_dir")
    parser.add_argument("output_path")
    parser.add_argument("--force", "-f", action="store_true", help="pack even if validation fails")
    args = parser.parse_args()
    return 0 if pack_hwpx(args.input_dir, args.output_path, args.force) else 1


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        sys.exit("Python 3.12+ is required")
    raise SystemExit(main())
