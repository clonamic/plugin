import json
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "skills" / "clonamic-hwpx" / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"clonamic_hwpx_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackageTest(unittest.TestCase):
    def test_manifest_and_skill_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-documents-plugin", manifest["name"])
        self.assertEqual(["clonamic-hwpx"], [p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")])

    def test_text_and_table_extraction_use_only_the_standard_library(self):
        text = load_script("extract_text.py")
        tables = load_script("extract_tables.py")
        section = b'''<?xml version="1.0" encoding="UTF-8"?>
        <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
          <hp:p><hp:run><hp:t>Hello</hp:t></hp:run></hp:p>
          <hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>Cell</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>
        </hp:section>'''
        self.assertEqual(["Hello", "Cell"], text.extract_text_from_section(section))
        self.assertEqual([[["Cell"]]], tables.extract_tables_from_section(section))

    def test_unsupported_libreoffice_conversion_is_not_shipped(self):
        skill_root = ROOT / "skills/clonamic-hwpx"
        self.assertFalse((skill_root / "scripts/convert_hwp.py").exists())
        self.assertFalse((skill_root / "scripts/convert_to_pdf.py").exists())
        self.assertFalse((skill_root / "scripts/office/soffice.py").exists())
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("does not claim a portable HWPX→PDF", skill)
        self.assertNotIn("--convert-to hwpx", skill)
        self.assertNotIn("--convert-to pdf", skill)

    def test_manifest_validation_fails_closed_without_third_party_parsers(self):
        validate = load_script("validate.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents = root / "Contents"
            contents.mkdir()
            (contents / "content.hpf").write_text(
                '<package xmlns="http://www.idpf.org/2007/opf">'
                '<manifest><item id="image1" href="BinData/missing.png"/></manifest>'
                '</package>',
                encoding="utf-8",
            )
            validator = validate.HWPXValidator(str(root))
            validator.work_dir = root
            validator._check_manifest_consistency()
            self.assertTrue(
                any(result.check == "MANIFEST" for result in validator.report.errors)
            )
        source = (
            ROOT / "skills/clonamic-hwpx/scripts/validate.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("BeautifulSoup", source)
        self.assertNotIn("lxml", source)

    def test_hwpx_runtime_is_explicit_pinned_and_buffer_bounded(self):
        skill = (ROOT / "skills/clonamic-hwpx/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("npx hwpxjs", skill)
        self.assertNotIn("npm install @ssabrojs/hwpxjs", skill)
        self.assertIn("./node_modules/.bin/hwpxjs", skill)
        self.assertIn("--save-exact @ssabrojs/hwpxjs@<approved-version>", skill)
        self.assertIn("fileBuffer.byteOffset + fileBuffer.byteLength", skill)
        self.assertNotIn("loadFromArrayBuffer(fileBuffer.buffer)", skill)
        self.assertNotIn("pass `fileBuffer.buffer`", skill)

    def test_bundled_helpers_are_root_qualified_from_foreign_cwd(self):
        skill_root = ROOT / "skills/clonamic-hwpx"
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [skill_root / "SKILL.md", *sorted((skill_root / "references").glob("*.md"))]
        )
        self.assertIn("HWPX_SKILL_ROOT", text)
        self.assertNotIn("python scripts/", text)


if __name__ == "__main__":
    unittest.main()
