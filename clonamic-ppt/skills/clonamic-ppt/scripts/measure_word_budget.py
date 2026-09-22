#!/usr/bin/env python3
"""Measure all visible slide, table, and linked-chart words in PPTX files."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import zipfile
from pathlib import Path

from ooxml_lib import NS, relationship_targets, slide_names, words, xml


def measure_word_budget(paths: list[Path]) -> dict:
    rows = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for number, name in enumerate(slide_names(archive), 1):
                root = xml(archive, name)
                table_nodes = {
                    id(node)
                    for table in root.findall(".//a:tbl", NS)
                    for node in table.findall(".//a:t", NS)
                }
                table_text = [
                    node.text.strip()
                    for table in root.findall(".//a:tbl", NS)
                    for node in table.findall(".//a:t", NS)
                    if node.text and node.text.strip()
                ]
                box_text = [
                    node.text.strip()
                    for node in root.findall(".//a:t", NS)
                    if id(node) not in table_nodes and node.text and node.text.strip()
                ]
                chart_text = []
                for target in relationship_targets(archive, name, "chart"):
                    chart = xml(archive, target)
                    chart_text.extend(
                        node.text.strip()
                        for query in (".//a:t", ".//c:v")
                        for node in chart.findall(query, NS)
                        if node.text and node.text.strip()
                    )
                row = {
                    "source": str(path),
                    "slide": number,
                    "text_box_words": words(box_text),
                    "table_words": words(table_text),
                    "chart_words": words(chart_text),
                }
                row["total_words"] = row["text_box_words"] + row["table_words"] + row["chart_words"]
                rows.append(row)
    totals = [row["total_words"] for row in rows]
    ceiling = math.ceil(statistics.median(totals)) if totals else 0
    for row in rows:
        row["split_required"] = row["total_words"] > ceiling
    return {
        "schema_version": 1,
        "median_ceiling": ceiling,
        "slides": rows,
        "densest": sorted(rows, key=lambda row: (-row["total_words"], row["source"], row["slide"]))[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", nargs="+")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = measure_word_budget([Path(path) for path in args.pptx])
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
