#!/usr/bin/env python3
"""Extract text or tables from an HWPX file (standard library only).

Usage:
  python3 extract.py text document.hwpx [-o out.txt]
  python3 extract.py tables document.hwpx [-o tables_dir/]   # one CSV per table
"""

from __future__ import annotations

import argparse
import csv
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def _local(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def extract_text_from_section(xml_content: bytes) -> list[str]:
    root = ElementTree.fromstring(xml_content)
    return [e.text.strip() for e in root.iter() if _local(e) == "t" and e.text and e.text.strip()]


def extract_tables_from_section(xml_content: bytes) -> list[list[list[str]]]:
    root = ElementTree.fromstring(xml_content)
    tables = []
    for tbl in (e for e in root.iter() if _local(e) == "tbl"):
        rows = []
        for tr in (e for e in tbl.iter() if _local(e) == "tr"):
            cells = [
                " ".join(t.text.strip() for t in tc.iter() if _local(t) == "t" and t.text)
                for tc in tr
                if _local(tc) == "tc"
            ]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def sections(path: str) -> list[bytes]:
    with zipfile.ZipFile(path) as zf:
        names = sorted(
            (n for n in zf.namelist() if n.startswith("Contents/section") and n.endswith(".xml")),
            key=lambda n: int("".join(ch for ch in n if ch.isdigit()) or 0),
        )
        return [zf.read(n) for n in names]


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text or tables from an HWPX file")
    parser.add_argument("mode", choices=("text", "tables"))
    parser.add_argument("hwpx_file")
    parser.add_argument("-o", "--output", help="text: output file; tables: output directory for CSV files")
    args = parser.parse_args()

    if args.mode == "text":
        text = "\n".join(line for xml in sections(args.hwpx_file) for line in extract_text_from_section(xml))
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0

    tables = [table for xml in sections(args.hwpx_file) for table in extract_tables_from_section(xml)]
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        for index, table in enumerate(tables, start=1):
            with (out / f"table_{index}.csv").open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerows(table)
        print(f"Saved {len(tables)} tables to {out}")
    else:
        for index, table in enumerate(tables, start=1):
            print(f"=== Table {index} ({len(table)} rows) ===")
            for row in table:
                print(" | ".join(row))
    return 0


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        sys.exit("Python 3.12+ is required")
    raise SystemExit(main())
