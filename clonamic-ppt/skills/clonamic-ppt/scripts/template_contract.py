#!/usr/bin/env python3
"""Extract semantic master, layout, placeholder, and exemplar geometry contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from ooxml_lib import NS, bbox, relationship_targets, shape_name, shapes, slide_names, texts, xml


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unnamed"


def _element(element) -> dict:
    name = shape_name(element)
    placeholder = element.find(".//p:ph", NS)
    row = {
        "key": _slug(name),
        "name": name,
        "kind": element.tag.rsplit("}", 1)[-1],
        "bbox": bbox(element),
    }
    if placeholder is not None:
        ptype = placeholder.get("type", "body")
        idx = placeholder.get("idx", "0")
        row["placeholder"] = {"type": ptype, "idx": idx, "key": f"{ptype}:{idx}"}
    value = " ".join(texts(element))
    if value:
        row["text_preview"] = value[:120]
    return row


def extract_template_contract(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        presentation = xml(archive, "ppt/presentation.xml")
        size = presentation.find("p:sldSz", NS)
        masters = []
        layouts = []
        master_names = sorted(
            name for name in archive.namelist() if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", name)
        )
        for name in master_names:
            root = xml(archive, name)
            c_sld = root.find("p:cSld", NS)
            protected = [_element(element) for element in shapes(root) if element.find(".//p:ph", NS) is None]
            masters.append(
                {
                    "key": _slug((c_sld.get("name", "") if c_sld is not None else "") or Path(name).stem),
                    "name": c_sld.get("name", "") if c_sld is not None else "",
                    "protected_regions": protected,
                }
            )
            for target in relationship_targets(archive, name, "slideLayout"):
                layout = xml(archive, target)
                layout_c_sld = layout.find("p:cSld", NS)
                placeholders = []
                for element in shapes(layout):
                    parsed = _element(element)
                    if "placeholder" in parsed:
                        placeholders.append(
                            {
                                "key": parsed["placeholder"]["key"],
                                "name": parsed["name"],
                                "type": parsed["placeholder"]["type"],
                                "idx": parsed["placeholder"]["idx"],
                                "bbox": parsed["bbox"],
                            }
                        )
                priority = {"title": 0, "ctrTitle": 0, "subTitle": 1, "body": 2, "obj": 3}
                placeholders.sort(
                    key=lambda item: (priority.get(item["type"], 9), int(item["idx"]))
                )
                layouts.append(
                    {
                        "key": _slug((layout_c_sld.get("name", "") if layout_c_sld is not None else "") or Path(target).stem),
                        "name": layout_c_sld.get("name", "") if layout_c_sld is not None else "",
                        "type": layout.get("type", "custom"),
                        "placeholders": placeholders,
                    }
                )
        exemplars = []
        for number, name in enumerate(slide_names(archive), 1):
            elements = [_element(element) for element in shapes(xml(archive, name))]
            elements.sort(
                key=lambda item: (
                    (item["bbox"] or {}).get("y", 99),
                    (item["bbox"] or {}).get("x", 99),
                    item["name"],
                )
            )
            exemplars.append({"slide": number, "elements": elements})
        return {
            "schema_version": 1,
            "source": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
            "canvas": {
                "width_in": round(int(size.get("cx", "0")) / 914400, 4) if size is not None else None,
                "height_in": round(int(size.get("cy", "0")) / 914400, 4) if size is not None else None,
            },
            "masters": masters,
            "layouts": layouts,
            "exemplars": exemplars,
            "fill_policy": "match placeholder key or semantic name; never select by shape position",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = extract_template_contract(Path(args.pptx))
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
