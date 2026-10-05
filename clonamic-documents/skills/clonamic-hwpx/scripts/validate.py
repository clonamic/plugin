#!/usr/bin/env python3
"""Validate an HWPX file or unpacked directory (standard library only).

Checks: ZIP layout (mimetype first, stored, correct value), required parts,
XML well-formedness, manifest vs BinData, binaryItemIDRef vs manifest ids,
and stale <hp:linesegarray> layout caches (info).

Usage: python3 validate.py document.hwpx | unpacked_dir/  [-q]
Exit code 0 = no errors.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

MIMETYPE = b"application/hwp+zip"
REQUIRED = ("mimetype", "Contents/header.xml", "Contents/content.hpf")


@dataclass
class ValidationResult:
    level: str  # ERROR | WARNING | INFO
    check: str
    message: str
    file: str = ""
    line: int = 0

    def __str__(self) -> str:
        loc = f" ({self.file}{f':{self.line}' if self.line else ''})" if self.file else ""
        return f"[{self.level}] {self.check}{loc}: {self.message}"


@dataclass
class ValidationReport:
    results: list[ValidationResult] = field(default_factory=list)

    def add(self, level: str, check: str, message: str, file: str = "", line: int = 0) -> None:
        self.results.append(ValidationResult(level, check, message, file, line))

    def error(self, check: str, message: str, file: str = "", line: int = 0) -> None:
        self.add("ERROR", check, message, file, line)

    def warning(self, check: str, message: str, file: str = "") -> None:
        self.add("WARNING", check, message, file)

    def info(self, check: str, message: str, file: str = "") -> None:
        self.add("INFO", check, message, file)

    @property
    def errors(self) -> list[ValidationResult]:
        return [r for r in self.results if r.level == "ERROR"]

    @property
    def warnings(self) -> list[ValidationResult]:
        return [r for r in self.results if r.level == "WARNING"]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def print_report(self, quiet: bool = False) -> None:
        shown = self.errors if quiet else self.results
        for result in shown:
            print(result)
        print(f"Summary: {len(self.errors)} errors, {len(self.warnings)} warnings")


class HWPXValidator:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.report = ValidationReport()
        self.work_dir: Path | None = None

    def validate(self) -> ValidationReport:
        if self.path.is_file():
            with tempfile.TemporaryDirectory() as temporary:
                try:
                    with zipfile.ZipFile(self.path) as zf:
                        self._check_zip_layout(zf)
                        zf.extractall(temporary)
                except zipfile.BadZipFile as exc:
                    self.report.error("ZIP", f"Invalid ZIP file: {exc}")
                    return self.report
                self.work_dir = Path(temporary)
                self._run_checks()
        elif self.path.is_dir():
            self.work_dir = self.path
            self._run_checks()
        else:
            self.report.error("INPUT", f"Not an HWPX file or directory: {self.path}")
        return self.report

    def _run_checks(self) -> None:
        self._check_required_files()
        self._check_xml_wellformedness()
        self._check_manifest_consistency()
        self._check_image_references()
        self._check_linesegarray()

    def _sections(self) -> list[Path]:
        return sorted((self.work_dir / "Contents").glob("section*.xml"))

    def _check_zip_layout(self, zf: zipfile.ZipFile) -> None:
        infos = zf.infolist()
        if not infos or infos[0].filename != "mimetype":
            self.report.error("ZIP", "mimetype must be the first entry")
            return
        if infos[0].compress_type != zipfile.ZIP_STORED:
            self.report.error("ZIP", "mimetype must be stored uncompressed")
        if zf.read("mimetype").strip() != MIMETYPE:
            self.report.error("ZIP", f"mimetype must be {MIMETYPE.decode()}")

    def _check_required_files(self) -> None:
        for name in REQUIRED:
            if not (self.work_dir / name).exists():
                self.report.error("REQUIRED_FILE", f"Missing required file: {name}")
        if not self._sections():
            self.report.error("REQUIRED_FILE", "No section*.xml files found in Contents/")

    def _check_xml_wellformedness(self) -> None:
        for xml_file in [*self.work_dir.rglob("*.xml"), *self.work_dir.rglob("*.hpf")]:
            try:
                ElementTree.parse(xml_file)
            except ElementTree.ParseError as exc:
                line = exc.position[0] if exc.position else 0
                self.report.error("XML_WELLFORMED", str(exc), str(xml_file.relative_to(self.work_dir)), line)

    def _manifest_items(self) -> list[ElementTree.Element] | None:
        manifest = self.work_dir / "Contents" / "content.hpf"
        if not manifest.exists():
            return None
        try:
            root = ElementTree.parse(manifest).getroot()
        except ElementTree.ParseError as exc:
            self.report.error("MANIFEST", f"Failed to parse manifest: {exc}")
            return None
        return [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "item"]

    def _check_manifest_consistency(self) -> None:
        items = self._manifest_items()
        if items is None:
            return
        listed = set()
        for item in items:
            href, item_id = item.get("href") or "", item.get("id")
            if href.startswith("BinData/"):
                listed.add(href.removeprefix("BinData/"))
                if not (self.work_dir / href).exists() and not (self.work_dir / "Contents" / href).exists():
                    self.report.error("MANIFEST", f"Manifest references missing file: {href} (id={item_id})")
        bindata = self.work_dir / "BinData"
        if bindata.is_dir():
            for file in bindata.iterdir():
                if file.name not in listed:
                    self.report.warning("MANIFEST", f"File not in manifest: BinData/{file.name}")

    def _check_image_references(self) -> None:
        items = self._manifest_items()
        if items is None:
            return
        ids = {item.get("id") for item in items}
        for section in self._sections():
            text = section.read_text(encoding="utf-8", errors="replace")
            for ref in re.findall(r'binaryItemIDRef="([^"]+)"', text):
                if ref not in ids:
                    self.report.error("IMAGE_REF", f'binaryItemIDRef="{ref}" not found in manifest', str(section.relative_to(self.work_dir)))

    def _check_linesegarray(self) -> None:
        for section in self._sections():
            count = section.read_text(encoding="utf-8", errors="replace").count("<hp:linesegarray")
            if count:
                self.report.info(
                    "LINESEGARRAY",
                    f"{count} linesegarray elements; remove the one in every paragraph whose text you edited.",
                    str(section.relative_to(self.work_dir)),
                )


def validate_hwpx(path: str) -> ValidationReport:
    return HWPXValidator(path).validate()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an HWPX file or unpacked directory")
    parser.add_argument("path")
    parser.add_argument("-q", "--quiet", action="store_true", help="show errors only")
    args = parser.parse_args()
    report = validate_hwpx(args.path)
    report.print_report(quiet=args.quiet)
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        sys.exit("Python 3.12+ is required")
    raise SystemExit(main())
