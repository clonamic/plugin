#!/usr/bin/env python3
"""Small OOXML helpers shared by reference-contract tools."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import xml.parsers.expat as expat
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EMU = 914400
RID = f"{{{NS['r']}}}id"
MAX_ARCHIVE_ENTRIES = 4096
MAX_XML_MEMBER_BYTES = 4 * 1024 * 1024
MAX_XML_TOTAL_BYTES = 32 * 1024 * 1024


def validate_archive(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ValueError(f"PPTX has too many archive entries: {len(infos)}")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise ValueError("PPTX contains duplicate archive members")
    xml_infos = [info for info in infos if info.filename.endswith((".xml", ".rels"))]
    oversized = [info.filename for info in xml_infos if info.file_size > MAX_XML_MEMBER_BYTES]
    if oversized:
        raise ValueError(f"PPTX XML member exceeds limit: {oversized[0]}")
    expanded = sum(info.file_size for info in xml_infos)
    if expanded > MAX_XML_TOTAL_BYTES:
        raise ValueError(f"PPTX expanded XML exceeds limit: {expanded}")


def xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    validate_archive(archive)
    if name.startswith("/") or ".." in PurePosixPath(name).parts:
        raise ValueError(f"unsafe archive member: {name}")
    data = archive.read(name)
    parser = expat.ParserCreate()

    def reject(*_args) -> None:
        raise ValueError(f"XML declarations are not allowed: {name}")

    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.UnparsedEntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    try:
        parser.Parse(data, True)
    except ValueError:
        raise
    except expat.ExpatError as error:
        raise ValueError(f"invalid XML member: {name}") from error
    return ET.fromstring(data)


def natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def slide_names(archive: zipfile.ZipFile) -> list[str]:
    validate_archive(archive)
    return sorted(
        (
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ),
        key=natural_key,
    )


def relationship_targets(archive: zipfile.ZipFile, part: str, kind: str | None = None) -> list[str]:
    validate_archive(archive)
    part_path = PurePosixPath(part)
    rel_name = str(part_path.parent / "_rels" / f"{part_path.name}.rels")
    if rel_name not in archive.namelist():
        return []
    root = xml(archive, rel_name)
    targets = []
    for rel in root.findall("pr:Relationship", NS):
        if kind and not rel.get("Type", "").endswith(f"/{kind}"):
            continue
        if rel.get("TargetMode", "Internal") != "Internal":
            raise ValueError("external OOXML relationship is not allowed")
        target = rel.get("Target", "")
        if not target or target.startswith(("/", "\\")) or "://" in target or "\\" in target:
            raise ValueError(f"unsafe OOXML relationship target: {target}")
        resolved = PurePosixPath(part_path.parent, target)
        clean: list[str] = []
        for item in resolved.parts:
            if item == "..":
                if clean:
                    clean.pop()
                else:
                    raise ValueError(f"OOXML relationship escapes archive: {target}")
            elif item != ".":
                clean.append(item)
        normalized = "/".join(clean)
        if part.startswith("ppt/") and not normalized.startswith("ppt/"):
            raise ValueError(f"OOXML relationship leaves ppt/: {target}")
        if normalized not in archive.namelist():
            raise ValueError(f"OOXML relationship target is missing: {normalized}")
        targets.append(normalized)
    return targets


def slide_theme_target(archive: zipfile.ZipFile, slide: str) -> str | None:
    layouts = relationship_targets(archive, slide, "slideLayout")
    if layouts:
        masters = relationship_targets(archive, layouts[0], "slideMaster")
        if masters:
            themes = relationship_targets(archive, masters[0], "theme")
            if themes:
                return themes[0]
    themes = relationship_targets(archive, "ppt/presentation.xml", "theme")
    return themes[0] if themes else None


def bbox(element: ET.Element) -> dict[str, float] | None:
    transform = element.find(".//a:xfrm", NS)
    if transform is None:
        transform = element.find(".//p:xfrm", NS)
    if transform is None:
        return None
    off = transform.find("a:off", NS)
    ext = transform.find("a:ext", NS)
    if off is None or ext is None:
        return None
    try:
        return {
            "x": round(int(off.get("x", "0")) / EMU, 4),
            "y": round(int(off.get("y", "0")) / EMU, 4),
            "w": round(int(ext.get("cx", "0")) / EMU, 4),
            "h": round(int(ext.get("cy", "0")) / EMU, 4),
            "unit": "in",
        }
    except ValueError:
        return None


def shape_name(element: ET.Element) -> str:
    node = element.find(".//p:cNvPr", NS)
    return node.get("name", "") if node is not None else ""


def texts(element: ET.Element) -> list[str]:
    return [node.text.strip() for node in element.findall(".//a:t", NS) if node.text and node.text.strip()]


def words(values: list[str]) -> int:
    return sum(len(re.findall(r"[^\W_]+(?:['’.-][^\W_]+)*", value, re.UNICODE)) for value in values)


def theme_palette(root: ET.Element) -> dict[str, str]:
    palette = {}
    scheme = root.find(".//a:clrScheme", NS)
    if scheme is None:
        return palette
    for slot in scheme:
        name = slot.tag.rsplit("}", 1)[-1]
        color = slot.find("a:srgbClr", NS)
        if color is not None and color.get("val"):
            palette[name] = color.get("val", "").upper()
            continue
        system = slot.find("a:sysClr", NS)
        if system is not None and system.get("lastClr"):
            palette[name] = system.get("lastClr", "").upper()
    return palette


def color_counts(root: ET.Element, palette: dict[str, str] | None = None) -> Counter[str]:
    out: Counter[str] = Counter()
    for node in root.findall(".//a:srgbClr", NS):
        value = node.get("val", "").upper()
        if re.fullmatch(r"[0-9A-F]{6}", value):
            out[value] += 1
    for node in root.findall(".//a:schemeClr", NS):
        value = (palette or {}).get(node.get("val", ""), "")
        if re.fullmatch(r"[0-9A-F]{6}", value):
            out[value] += 1
    return out


def font_counts(root: ET.Element) -> Counter[str]:
    out: Counter[str] = Counter()
    for node in root.iter():
        value = node.get("typeface", "").strip()
        if value:
            out[value] += 1
    return out


def shapes(root: ET.Element) -> list[ET.Element]:
    tags = {f"{{{NS['p']}}}{name}" for name in ("sp", "pic", "graphicFrame", "cxnSp")}
    return [element for element in root.iter() if element.tag in tags]
