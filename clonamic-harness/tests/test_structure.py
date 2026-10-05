import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
TEMPLATE = ROOT.parents[1] / "template"
EXPECTED_SKILLS = {"clonamic-intake", "clonamic-spec", "clonamic-team", "clonamic-finish"}
MANIFEST_KEYS = {"$schema", "name", "version", "description", "license", "author", "keywords", "homepage", "repository"}
COPIES = {
    "작업명세서.md": SKILLS / "clonamic-spec" / "references" / "work-spec.md",
    "개발명세서.md": SKILLS / "clonamic-spec" / "references" / "dev-spec.md",
    "보고서.md": SKILLS / "clonamic-finish" / "references" / "report.md",
}
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def frontmatter(text):
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md must start with a frontmatter block")
    end = text.index("\n---\n", 4)
    fields = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            fields[key.strip()] = value.strip()
    return fields, text[end + 5 :]


class StructureTest(unittest.TestCase):
    def test_manifest(self):
        data = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], ROOT.name)
        self.assertEqual(data["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertLessEqual(set(data), MANIFEST_KEYS)

    def test_exactly_four_stage_skills(self):
        folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertEqual(folders, EXPECTED_SKILLS)
        for name in folders:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)

    def test_frontmatter_is_valid(self):
        for name in EXPECTED_SKILLS:
            fields, body = frontmatter((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(fields.get("name"), name)
            self.assertRegex(name, r"^[a-z0-9-]+$")
            self.assertTrue(fields.get("description"), name)
            self.assertLessEqual(len(fields["description"]), 1024, name)
            self.assertTrue(body.strip(), name)

    def test_every_linked_reference_exists(self):
        for skill_md in SKILLS.glob("*/SKILL.md"):
            for target in LINK.findall(skill_md.read_text(encoding="utf-8")):
                if "://" in target:
                    continue
                self.assertTrue((skill_md.parent / target).is_file(), f"{skill_md.parent.name}: {target}")

    def test_template_copies_exist_with_their_contracts(self):
        for copy in COPIES.values():
            self.assertTrue(copy.is_file(), copy)
            self.assertNotIn("```규칙", copy.read_text(encoding="utf-8"))
        self.assertIn("승인 대기 — 작업명세서", COPIES["작업명세서.md"].read_text(encoding="utf-8"))
        self.assertIn("승인 대기 — 개발명세서", COPIES["개발명세서.md"].read_text(encoding="utf-8"))
        self.assertIn("결과1 [완료1]", COPIES["보고서.md"].read_text(encoding="utf-8"))

    @unittest.skipUnless(TEMPLATE.is_dir(), "template repository not checked out next to the plugin repo")
    def test_template_copies_are_byte_identical(self):
        for source, copy in COPIES.items():
            self.assertEqual((TEMPLATE / source).read_bytes(), copy.read_bytes(), source)

    def test_removed_machinery_stays_removed(self):
        for name in ("plugins", "catalog", "schemas", "clonamic.json", "clonamic-herness-plugin.md"):
            self.assertFalse((ROOT / name).exists(), name)
        self.assertEqual(list(SKILLS.rglob("*.json")), [])
        for path in SKILLS.rglob("*"):
            if path.is_file():
                self.assertNotIn("herness", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main()
