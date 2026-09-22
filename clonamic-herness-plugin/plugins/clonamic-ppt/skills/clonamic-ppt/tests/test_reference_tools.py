from __future__ import annotations

import ast
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PLUGIN = ROOT.parent.parent
sys.path.insert(0, str(SCRIPTS))

from extract_design_dna import extract_design_dna
from measure_word_budget import measure_word_budget
from qa_static import qa_ir
from render_ir_svg import render_ir_svg
from template_contract import extract_template_contract
import ooxml_lib
import visual_qa


def write_reference_pptx(path: Path) -> None:
    files = {
        "[Content_Types].xml": "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
        "ppt/presentation.xml": """<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'><p:sldMasterIdLst><p:sldMasterId id='1' r:id='rId3'/></p:sldMasterIdLst><p:sldIdLst><p:sldId id='256' r:id='rId1'/><p:sldId id='257' r:id='rId2'/></p:sldIdLst><p:sldSz cx='12192000' cy='6858000'/></p:presentation>""",
        "ppt/_rels/presentation.xml.rels": """<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide' Target='slides/slide1.xml'/><Relationship Id='rId2' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide' Target='slides/slide2.xml'/><Relationship Id='rId3' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster' Target='slideMasters/slideMaster1.xml'/><Relationship Id='rId4' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme' Target='theme/theme1.xml'/></Relationships>""",
        "ppt/theme/theme1.xml": """<a:theme xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main' name='Measured Theme'><a:themeElements><a:clrScheme name='Measured'><a:dk1><a:srgbClr val='112233'/></a:dk1><a:accent1><a:srgbClr val='2F6FED'/></a:accent1></a:clrScheme><a:fontScheme name='Measured Fonts'><a:majorFont><a:latin typeface='Aptos Display'/></a:majorFont><a:minorFont><a:latin typeface='Aptos'/></a:minorFont></a:fontScheme></a:themeElements></a:theme>""",
        "ppt/slides/slide1.xml": """<p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id='2' name='Measured title'/><p:cNvSpPr/><p:nvPr><p:ph type='title' idx='1'/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x='548640' y='365760'/><a:ext cx='7315200' cy='640080'/></a:xfrm><a:solidFill><a:srgbClr val='445566'/></a:solidFill></p:spPr><p:txBody><a:bodyPr/><a:p><a:r><a:rPr typeface='Aptos Display'/><a:t>Measured title rhythm</a:t></a:r></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id='3' name='Body card'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x='548640' y='1371600'/><a:ext cx='4937760' cy='1828800'/></a:xfrm><a:solidFill><a:schemeClr val='accent1'/></a:solidFill></p:spPr><p:txBody><a:bodyPr/><a:p><a:r><a:rPr typeface='Aptos'/><a:t>short approved copy</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>""",
        "ppt/slides/slide2.xml": """<p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id='2' name='Density title'/><p:cNvSpPr/><p:nvPr><p:ph type='title' idx='1'/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x='548640' y='365760'/><a:ext cx='7315200' cy='640080'/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:p><a:r><a:t>Density includes tables</a:t></a:r></a:p></p:txBody></p:sp><p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id='4' name='Evidence table'/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x='548640' y='1371600'/><a:ext cx='4937760' cy='1828800'/></p:xfrm><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>Table evidence words</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>""",
        "ppt/slides/_rels/slide2.xml.rels": """<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId5' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart' Target='../charts/chart1.xml'/></Relationships>""",
        "ppt/charts/chart1.xml": """<c:chartSpace xmlns:c='http://schemas.openxmlformats.org/drawingml/2006/chart' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>Chart growth evidence</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea><c:barChart><c:ser><c:tx><c:strRef><c:strCache><c:pt><c:v>Revenue</c:v></c:pt></c:strCache></c:strRef></c:tx><c:cat><c:strRef><c:strCache><c:pt><c:v>Current year</c:v></c:pt></c:strCache></c:strRef></c:cat></c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>""",
        "ppt/slideMasters/slideMaster1.xml": """<p:sldMaster xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'><p:cSld name='Measured Master'><p:spTree><p:sp><p:nvSpPr><p:cNvPr id='9' name='Protected brand rail'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x='0' y='0'/><a:ext cx='182880' cy='6858000'/></a:xfrm><a:solidFill><a:srgbClr val='2F6FED'/></a:solidFill></p:spPr></p:sp></p:spTree></p:cSld><p:sldLayoutIdLst><p:sldLayoutId id='10' r:id='rId1'/></p:sldLayoutIdLst></p:sldMaster>""",
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": """<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout' Target='../slideLayouts/slideLayout1.xml'/></Relationships>""",
        "ppt/slideLayouts/slideLayout1.xml": """<p:sldLayout xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main' type='titleAndContent'><p:cSld name='Title and evidence'><p:spTree><p:sp><p:nvSpPr><p:cNvPr id='2' name='Title placeholder'/><p:cNvSpPr/><p:nvPr><p:ph type='title' idx='1'/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x='548640' y='365760'/><a:ext cx='7315200' cy='640080'/></a:xfrm></p:spPr></p:sp><p:sp><p:nvSpPr><p:cNvPr id='3' name='Body placeholder'/><p:cNvSpPr/><p:nvPr><p:ph type='body' idx='2'/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x='548640' y='1371600'/><a:ext cx='4937760' cy='3657600'/></a:xfrm></p:spPr></p:sp></p:spTree></p:cSld></p:sldLayout>""",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)


class ReferenceToolTest(unittest.TestCase):
    def test_extracts_actual_design_dna_and_word_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            pptx = Path(temporary) / "reference.pptx"
            write_reference_pptx(pptx)
            dna = extract_design_dna([pptx])
            self.assertIn("445566", dna["colors"]["slide_usage"])
            self.assertIn("2F6FED", dna["colors"]["slide_usage"])
            self.assertIn("Aptos Display", dna["fonts"]["slide_usage"])
            self.assertIn("112233", [row["value"] for row in dna["colors"]["theme_ranked"]])
            self.assertIn("Aptos", [row["value"] for row in dna["fonts"]["theme_ranked"]])
            self.assertGreater(dna["layout_rhythm"]["median_left_in"], 0)
            budget = measure_word_budget([pptx])
            self.assertEqual(2, len(budget["slides"]))
            self.assertGreater(budget["slides"][1]["table_words"], 0)
            self.assertGreater(budget["slides"][1]["chart_words"], 0)
            totals = [row["total_words"] for row in budget["slides"]]
            self.assertEqual(math.ceil(statistics.median(totals)), budget["median_ceiling"])
            self.assertTrue(budget["slides"][1]["split_required"])

    def test_template_contract_uses_semantics_not_shape_indices(self):
        with tempfile.TemporaryDirectory() as temporary:
            pptx = Path(temporary) / "template.pptx"
            write_reference_pptx(pptx)
            contract = extract_template_contract(pptx)
            self.assertEqual(["title:1", "body:2"], [p["key"] for p in contract["layouts"][0]["placeholders"]])
            self.assertEqual("Protected brand rail", contract["masters"][0]["protected_regions"][0]["name"])
            self.assertNotIn("shape_index", json.dumps(contract))
            self.assertEqual("Measured title", contract["exemplars"][0]["elements"][0]["name"])

    def test_svg_preview_matches_ir_and_editable_pptx(self):
        deck_path = ROOT / "assets/fixtures/reference_contract/deck_ir.json"
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            manifest = render_ir_svg(deck, out / "svg")
            self.assertEqual(len(deck["slides"]), len(manifest["slides"]))
            for slide, row in zip(deck["slides"], manifest["slides"]):
                svg = Path(row["path"]).read_text(encoding="utf-8")
                self.assertIn('viewBox="0 0 1333 750"', svg)
                self.assertEqual(len(slide["elements"]), row["element_count"])
                for element in slide["elements"]:
                    self.assertIn(element["element_id"], svg)
            pptx = out / "editable.pptx"
            proc = subprocess.run(
                ["node", str(SCRIPTS / "render_deck.cjs"), "--input", str(deck_path), "--out", str(pptx)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            with zipfile.ZipFile(pptx) as archive:
                slides = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
                text = " ".join(archive.read(name).decode("utf-8") for name in slides)
                first = ET.fromstring(archive.read(slides[0]))
            self.assertEqual(len(deck["slides"]), len(slides))
            self.assertIn("Evidence beats decoration &amp; guesswork", text)
            namespaces = {
                "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
            }
            title = next(
                shape
                for shape in first.findall(".//p:sp", namespaces)
                if shape.find(".//p:cNvPr", namespaces).get("name") == "ref-01-title"
            )
            offset = title.find(".//a:xfrm/a:off", namespaces)
            extent = title.find(".//a:xfrm/a:ext", namespaces)
            self.assertAlmostEqual(0.6, int(offset.get("x")) / 914400, places=3)
            self.assertAlmostEqual(8.2, int(extent.get("cx")) / 914400, places=3)
            svg = Path(manifest["slides"][0]["path"]).read_text(encoding="utf-8")
            self.assertIn('x="60.00"', svg)
            self.assertIn('width="820.00"', svg)

    def test_svg_preview_rejects_non_hex_color_payloads(self):
        deck = {
            "slides": [
                {
                    "slide_id": "unsafe-color",
                    "sequence": 1,
                    "background_color": '"><',
                    "elements": [
                        {
                            "element_id": "shape-1",
                            "kind": "shape",
                            "shape_type": "rect",
                            "bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
                            "fill": {"color": "ZZZZZZ"},
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            manifest = render_ir_svg(deck, Path(temporary))
            svg = Path(manifest["slides"][0]["path"]).read_text(encoding="utf-8")
            ET.parse(manifest["slides"][0]["path"])
        self.assertNotIn("script", svg.casefold())
        fills = re.findall(r'fill="([^"]+)"', svg)
        self.assertTrue(fills)
        self.assertTrue(all(re.fullmatch(r"#[0-9A-F]{6}|none", fill) for fill in fills), fills)
        self.assertIn("#FFFFFF", fills)

    def test_notices_source_lock_and_forbidden_sources(self):
        lock = json.loads((ROOT / "references/upstreams.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "Microsoft Resource2Skill": "7f101b4cfe214cc496d085a34efac528a17cc375",
                "deck-dna": "a77a3dbc7cd007a3f6add610f6a5f8aa893d7a2f",
                "PPTX-Template-Skills": "e3139a08b4bf96bb2cda0046b8d3627e69737f11",
            },
            {row["name"]: row["commit"] for row in lock["sources"]},
        )
        self.assertTrue(all(row["license"] == "MIT" for row in lock["sources"]))
        notices = (PLUGIN / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for owner in ("Microsoft Corporation", "Omri Pitaru", "JerryChou"):
            self.assertIn(owner, notices)
        new_scripts = (
            "extract_design_dna.py",
            "measure_word_budget.py",
            "template_contract.py",
            "render_ir_svg.py",
            "ooxml_lib.py",
        )
        production = "\n".join(
            (ROOT / "scripts" / name).read_text(encoding="utf-8") for name in new_scripts
        )
        for forbidden in ("anthropic", "poplar", "agentbuff"):
            self.assertNotIn(forbidden, production.casefold())
        for dependency in ("from pptx", "import pptx", "from PIL", "import numpy"):
            self.assertNotIn(dependency, production)

    def test_fixture_has_no_major_static_qa(self):
        deck = json.loads((ROOT / "assets/fixtures/decide_pilot_8/slide_specs.json").read_text(encoding="utf-8"))
        from compose_ir import compose_deck

        issues = qa_ir(compose_deck(deck))
        self.assertFalse([issue for issue in issues if issue["severity"] in {"blocker", "major"}], issues)

    def test_engine_emits_svg_qa_without_flattening_pptx(self):
        specs = ROOT / "assets/fixtures/mix_families/slide_specs.json"
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_engine.py"), "--specs", str(specs), "--out", str(out)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            report = json.loads((out / "qa_report.json").read_text(encoding="utf-8"))
            manifest = json.loads((out / "svg" / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["qa_only"])
            self.assertEqual(
                len(
                    json.loads(
                        (out / "deck_ir.json").read_text(encoding="utf-8")
                    )["slides"]
                ),
                len(manifest["slides"]),
            )
            self.assertEqual(str(out / "svg"), report["artifacts"]["svg"])
            self.assertTrue((out / "presentation.pptx").is_file())

    def test_engine_accepts_reference_inputs_and_keeps_template_extraction_only(self):
        specs = ROOT / "assets/fixtures/mix_families/slide_specs.json"
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "out"
            reference = Path(temporary) / "reference.pptx"
            write_reference_pptx(reference)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_engine.py"),
                    "--specs",
                    str(specs),
                    "--out",
                    str(out),
                    "--reference-pptx",
                    str(reference),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            contracts = json.loads(
                (out / "deck_ir.json").read_text(encoding="utf-8")
            )["reference_contracts"]
            self.assertGreater(contracts["median_word_ceiling"], 0)
            for name in ("design_dna.json", "word_budget.json"):
                self.assertTrue((out / "reference_contracts" / name).is_file())
            rejected = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_engine.py"),
                    "--specs",
                    str(specs),
                    "--out",
                    str(out / "rejected"),
                    "--template-pptx",
                    str(reference),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("unrecognized arguments", rejected.stderr)

    def test_relationships_reject_external_and_archive_traversal(self):
        cases = {
            "external": "<Relationship Id='r1' Type='x/chart' Target='https://example.test/a.xml' TargetMode='External'/>",
            "traversal": "<Relationship Id='r1' Type='x/chart' Target='../../../outside.xml'/>",
        }
        for name, relationship in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "hostile.pptx"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("ppt/slides/slide1.xml", "<p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>")
                    archive.writestr(
                        "ppt/slides/_rels/slide1.xml.rels",
                        f"<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>{relationship}</Relationships>",
                    )
                with zipfile.ZipFile(path) as archive:
                    with self.assertRaises(ValueError):
                        ooxml_lib.relationship_targets(archive, "ppt/slides/slide1.xml", "chart")

    def test_archive_xml_reads_are_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bounded.pptx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", "<x>1234567890</x>")
                archive.writestr("ppt/slides/slide2.xml", "<x>abcdefghij</x>")
                archive.writestr("ppt/slides/slide3.xml", "<x/>")
            with zipfile.ZipFile(path) as archive:
                with mock.patch.object(ooxml_lib, "MAX_ARCHIVE_ENTRIES", 2):
                    with self.assertRaises(ValueError):
                        ooxml_lib.slide_names(archive)
            with zipfile.ZipFile(path) as archive:
                with mock.patch.object(ooxml_lib, "MAX_XML_MEMBER_BYTES", 8):
                    with self.assertRaises(ValueError):
                        ooxml_lib.xml(archive, "ppt/slides/slide1.xml")
            with zipfile.ZipFile(path) as archive:
                with mock.patch.object(ooxml_lib, "MAX_XML_TOTAL_BYTES", 20):
                    with self.assertRaises(ValueError):
                        ooxml_lib.xml(archive, "ppt/slides/slide1.xml")

    def test_xml_declarations_are_rejected_for_every_supported_encoding(self):
        entity_body = "<!DOCTYPE x [<!ENTITY a 'expanded'>]><x>&a;</x>"
        nested_body = "<!DOCTYPE x [<!ENTITY a 'a'><!ENTITY b '&a;&a;'>]><x>&b;</x>"
        variants = {
            "utf8": ("<?xml version='1.0' encoding='UTF-8'?>" + entity_body).encode("utf-8"),
            "utf16-bom": ("<?xml version='1.0' encoding='UTF-16'?>" + entity_body).encode("utf-16"),
            "utf16le-bom": b"\xff\xfe" + entity_body.encode("utf-16-le"),
            "utf16be-bom": b"\xfe\xff" + entity_body.encode("utf-16-be"),
            "utf16le-no-bom": ("<?xml version='1.0' encoding='UTF-16LE'?>" + entity_body).encode("utf-16-le"),
            "utf16be-no-bom": ("<?xml version='1.0' encoding='UTF-16BE'?>" + entity_body).encode("utf-16-be"),
            "mixed-case-invalid": b"<!DoCtYpE x [<!EnTiTy a 'expanded'>]><x>&a;</x>",
            "nested": nested_body.encode("utf-8"),
        }
        for name, payload in variants.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "entities.pptx"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("ppt/slides/slide1.xml", payload)
                with zipfile.ZipFile(path) as archive:
                    with self.assertRaises(ValueError):
                        ooxml_lib.xml(archive, "ppt/slides/slide1.xml")

    def test_each_slide_resolves_its_own_theme_relationship(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "themes.pptx"
            with zipfile.ZipFile(path, "w") as archive:
                for number in (1, 2):
                    archive.writestr(
                        f"ppt/slides/slide{number}.xml",
                        "<p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id='2' name='Accent'/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:solidFill><a:schemeClr val='accent1'/></a:solidFill></p:spPr></p:sp></p:spTree></p:cSld></p:sld>",
                    )
                    archive.writestr(
                        f"ppt/slides/_rels/slide{number}.xml.rels",
                        f"<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='r1' Type='x/slideLayout' Target='../slideLayouts/slideLayout{number}.xml'/></Relationships>",
                    )
                    archive.writestr(f"ppt/slideLayouts/slideLayout{number}.xml", "<p:sldLayout xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>")
                    archive.writestr(
                        f"ppt/slideLayouts/_rels/slideLayout{number}.xml.rels",
                        f"<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='r1' Type='x/slideMaster' Target='../slideMasters/slideMaster{number}.xml'/></Relationships>",
                    )
                    archive.writestr(f"ppt/slideMasters/slideMaster{number}.xml", "<p:sldMaster xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>")
                    archive.writestr(
                        f"ppt/slideMasters/_rels/slideMaster{number}.xml.rels",
                        f"<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='r1' Type='x/theme' Target='../theme/theme{number}.xml'/></Relationships>",
                    )
                    color = "AA0000" if number == 1 else "00BB00"
                    archive.writestr(
                        f"ppt/theme/theme{number}.xml",
                        f"<a:theme xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><a:themeElements><a:clrScheme name='x'><a:accent1><a:srgbClr val='{color}'/></a:accent1></a:clrScheme></a:themeElements></a:theme>",
                    )
            dna = extract_design_dna([path])
            self.assertEqual(
                [["AA0000"], ["00BB00"]],
                [row["colors"] for row in dna["colors"]["per_slide"]],
            )

    def test_svg_chart_contains_all_categories_names_and_values_and_parses(self):
        deck = json.loads(
            (ROOT / "assets/fixtures/reference_contract/deck_ir.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest = render_ir_svg(deck, Path(temporary))
            for row in manifest["slides"]:
                ET.parse(row["path"])
            chart_svg = Path(manifest["slides"][1]["path"]).read_text(encoding="utf-8")
        for value in ("Low", "High", "Words", "18", "52"):
            self.assertIn(value, chart_svg)

    def test_every_renderer_subprocess_has_a_timeout(self):
        for name in ("run_engine.py", "visual_qa.py"):
            tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
            calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and node.func.attr in {"run", "Popen"}
            ]
            self.assertTrue(calls, name)
            for call in calls:
                self.assertIn("timeout", {keyword.arg for keyword in call.keywords}, name)

    def test_major_issue_makes_qa_fail(self):
        deck = {
            "language": "en-US",
            "slides": [
                {
                    "slide_id": "major-only",
                    "elements": [
                        {
                            "element_id": "major-only_title",
                            "kind": "text",
                            "token_ref": "title",
                            "text": "Readable title",
                            "bbox": {"x": 0.5, "y": 0.5, "w": 6, "h": 1},
                            "style": {"font_size_pt": 8},
                        },
                        {
                            "element_id": "major-only_pg",
                            "kind": "text",
                            "text": "1",
                            "bbox": {"x": 12, "y": 7, "w": 0.5, "h": 0.2},
                            "style": {"font_size_pt": 11},
                        },
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            ir = Path(temporary) / "ir.json"
            report = Path(temporary) / "qa.json"
            ir.write_text(json.dumps(deck), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "qa_static.py"), "--ir", str(ir), "--out", str(report)],
                text=True,
                capture_output=True,
                timeout=10,
            )
            payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertNotEqual(0, proc.returncode)
        self.assertGreater(payload["major"], 0)
        self.assertFalse(payload["pass"])

    def test_visual_status_is_explicit_and_never_claims_verification_when_unavailable(self):
        deck = {"slides": [{"slide_id": "s1", "elements": []}]}
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(visual_qa, "render_pngs", return_value=[]):
                unavailable = visual_qa.qa_visual_report(
                    Path(temporary) / "deck.pptx", deck, Path(temporary) / "png"
                )
            self.assertEqual("unavailable", unavailable["visual_status"])
            self.assertNotIn("verified", json.dumps(unavailable).casefold())
            fake = Path(temporary) / "slide.png"
            fake.write_bytes(b"png")
            with mock.patch.object(visual_qa, "render_pngs", return_value=[fake]), mock.patch.object(
                visual_qa, "ink_ratio", return_value=0.2
            ):
                rendered = visual_qa.qa_visual_report(
                    Path(temporary) / "deck.pptx", deck, Path(temporary) / "png"
                )
            self.assertEqual("rendered", rendered["visual_status"])


if __name__ == "__main__":
    unittest.main()
