import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HWPX = ROOT / "skills" / "clonamic-hwpx"
PPTX = ROOT / "skills" / "clonamic-pptx"


def load_script(skill: Path, name: str):
    path = skill / "scripts" / name
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(f"{skill.name.replace('-', '_')}_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(path.parent))


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(script), *args], text=True, capture_output=True, check=False, timeout=30
    )


class PackageTest(unittest.TestCase):
    def test_manifest_and_skills(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-documents", manifest["name"])
        self.assertEqual(ROOT.name, manifest["name"])
        self.assertEqual("https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", manifest["$schema"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        self.assertEqual(
            ["clonamic-hwpx", "clonamic-pptx"],
            sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")),
        )
        for skill in (HWPX, PPTX):
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertRegex(text, rf"(?m)^name: {skill.name}$")
            for link in re.findall(r"\]\((references/[^)#]+)\)", text):
                self.assertTrue((skill / link).is_file(), f"{skill.name}: broken link {link}")

    def test_no_vendored_engine_or_node_runtime(self):
        for name in ("package.json", "package-lock.json", "vendor", "node_modules"):
            self.assertEqual([], list(ROOT.rglob(name)), name)
        scripts = sorted(p.name for p in ROOT.rglob("scripts/*") if p.is_file() and p.suffix in {".py", ".js", ".cjs"})
        self.assertEqual(["create_blank.py", "extract.py", "inspect_pptx.py", "pack.py", "validate.py"], scripts)

    def test_scripts_use_only_the_standard_library(self):
        third_party = re.compile(r"^\s*(?:import|from)\s+(lxml|bs4|pptx|PIL|numpy)\b", re.M)
        for script in ROOT.rglob("scripts/*.py"):
            self.assertIsNone(third_party.search(script.read_text(encoding="utf-8")), script.name)

    def test_helpers_are_root_qualified(self):
        for skill, var in ((HWPX, "HWPX_SKILL_ROOT"), (PPTX, "PPTX_SKILL_ROOT")):
            text = "\n".join(p.read_text(encoding="utf-8") for p in [skill / "SKILL.md", *(skill / "references").glob("*.md")])
            self.assertIn(var, text)
            self.assertNotIn("python scripts/", text)
            self.assertNotIn("python3 scripts/", text)


class HwpxTest(unittest.TestCase):
    def test_text_and_table_extraction(self):
        extract = load_script(HWPX, "extract.py")
        section = b'''<?xml version="1.0" encoding="UTF-8"?>
        <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
          <hp:p><hp:run><hp:t>Hello</hp:t></hp:run></hp:p>
          <hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>Cell</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>
        </hp:section>'''
        self.assertEqual(["Hello", "Cell"], extract.extract_text_from_section(section))
        self.assertEqual([[["Cell"]]], extract.extract_tables_from_section(section))

    def test_blank_pack_validate_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            created = run(HWPX / "scripts" / "create_blank.py", str(tmp / "a.hwpx"), "--title", "A & B", "--text", "안녕 <표> & 끝")
            self.assertEqual(0, created.returncode, created.stderr)
            self.assertEqual(0, run(HWPX / "scripts" / "validate.py", str(tmp / "a.hwpx")).returncode)
            with zipfile.ZipFile(tmp / "a.hwpx") as zf:
                zf.extractall(tmp / "un")
            packed = run(HWPX / "scripts" / "pack.py", str(tmp / "un"), str(tmp / "b.hwpx"))
            self.assertEqual(0, packed.returncode, packed.stdout + packed.stderr)
            with zipfile.ZipFile(tmp / "b.hwpx") as zf:
                first = zf.infolist()[0]
                self.assertEqual(("mimetype", zipfile.ZIP_STORED), (first.filename, first.compress_type))
                for name in zf.namelist():
                    self.assertEqual((tmp / "un" / name).read_bytes(), zf.read(name), name)
            text = run(HWPX / "scripts" / "extract.py", "text", str(tmp / "b.hwpx"))
            self.assertEqual("안녕 <표> & 끝", text.stdout.strip())

    def test_validator_rejects_bad_container_and_missing_manifest_files(self):
        validate = load_script(HWPX, "validate.py")
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            bad = tmp / "bad.hwpx"
            with zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("Contents/content.hpf", '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                            '<item id="image1" href="BinData/missing.png"/></manifest></package>')
                zf.writestr("mimetype", "application/hwp+zip")
            report = validate.validate_hwpx(str(bad))
            checks = {r.check for r in report.errors}
            self.assertIn("ZIP", checks)
            self.assertIn("MANIFEST", checks)
            self.assertIn("REQUIRED_FILE", checks)
            self.assertFalse(report.is_valid)

    def test_pack_refuses_invalid_xml(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            run(HWPX / "scripts" / "create_blank.py", str(tmp / "a.hwpx"))
            with zipfile.ZipFile(tmp / "a.hwpx") as zf:
                zf.extractall(tmp / "un")
            section = tmp / "un" / "Contents" / "section0.xml"
            section.write_text(section.read_text(encoding="utf-8").replace("</hs:sec>", ""), encoding="utf-8")
            packed = run(HWPX / "scripts" / "pack.py", str(tmp / "un"), str(tmp / "b.hwpx"))
            self.assertEqual(1, packed.returncode)
            self.assertFalse((tmp / "b.hwpx").exists())

    def test_skill_keeps_safety_rules(self):
        skill = (HWPX / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("does not claim a portable HWPX→PDF", skill)
        self.assertNotIn("--convert-to hwpx", skill)
        self.assertNotIn("npx hwpxjs", skill)
        self.assertIn("--save-exact @ssabrojs/hwpxjs@<approved-version>", skill)
        self.assertIn("fileBuffer.byteOffset + fileBuffer.byteLength", skill)
        self.assertIn("linesegarray", skill)


def write_pptx(path: Path, shapes: list[str]) -> None:
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rel = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{p}" xmlns:r="{r}"><p:sldIdLst>'
                    f'<p:sldId id="256" r:id="rId2"/></p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/></p:presentation>')
        zf.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships xmlns="{rel}">'
                    '<Relationship Id="rId2" Type="slide" Target="slides/slide1.xml"/></Relationships>')
        zf.writestr("ppt/slides/slide1.xml", f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree>'
                    + "".join(shapes) + "</p:spTree></p:cSld></p:sld>")


def text_box(name: str, x: float, y: float, w: float, h: float, text: str, size: int = 1800) -> str:
    emu = lambda v: int(v * 914400)  # noqa: E731
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="1" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:p><a:r><a:rPr sz="{size}"/><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>')


class PptxInspectTest(unittest.TestCase):
    def inspect(self, shapes: list[str]) -> dict:
        module = load_script(PPTX, "inspect_pptx.py")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "deck.pptx"
            write_pptx(path, shapes)
            return module.inspect(str(path), 10.0)

    def codes(self, report: dict) -> set[str]:
        return {issue["code"] for issue in report["issues"]}

    def test_clean_slide_has_no_issues(self):
        report = self.inspect([text_box("Title", 0.6, 0.4, 12, 0.8, "결론을 말하는 제목"), text_box("Body", 0.6, 1.4, 12, 3, "근거 — 이유")])
        self.assertEqual([], report["issues"])
        self.assertEqual([13.333, 7.5], report["slide_size_in"])
        self.assertEqual(1, report["slide_count"])

    def test_detects_out_of_bounds_overlap_small_font_and_overflow(self):
        report = self.inspect([
            text_box("A", 1, 1, 3, 1, "겹치는 상자"),
            text_box("B", 2, 1.2, 3, 1, "다른 상자"),
            text_box("Off", 12, 6.8, 2, 1, "밖", size=800),
            text_box("Tall", 1, 4, 2, 0.4, "가나다라마바사아자차카타파하" * 5),
        ])
        self.assertEqual({"TEXT_OVERLAP", "OUT_OF_BOUNDS", "SMALL_FONT", "LIKELY_OVERFLOW"}, self.codes(report))

    def test_cli_exit_code_reflects_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "deck.pptx"
            write_pptx(path, [text_box("A", 1, 1, 3, 1, "a"), text_box("B", 1, 1, 3, 1, "b")])
            self.assertEqual(1, run(PPTX / "scripts" / "inspect_pptx.py", str(path)).returncode)
            write_pptx(path, [text_box("A", 1, 1, 3, 1, "a")])
            result = run(PPTX / "scripts" / "inspect_pptx.py", str(path), "--json")
            self.assertEqual(0, result.returncode)
            self.assertEqual(1, json.loads(result.stdout)["slide_count"])

    def test_broken_file_is_an_error(self):
        module = load_script(PPTX, "inspect_pptx.py")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "deck.pptx"
            path.write_text("not a zip", encoding="utf-8")
            self.assertEqual({"BROKEN_FILE"}, self.codes(module.inspect(str(path), 10.0)))


if __name__ == "__main__":
    unittest.main()
