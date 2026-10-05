import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
AGENTS = ROOT / "agents"
EXPECTED_SKILLS = {"clonamic-intake", "clonamic-spec", "clonamic-team", "clonamic-finish"}
EXPECTED_AGENTS = {"clonamic-reviewer"}
MANIFEST_KEYS = {"$schema", "name", "version", "description", "license", "author", "keywords", "repository"}
FORMATS = {
    "work": SKILLS / "clonamic-spec" / "references" / "work-spec.md",
    "dev": SKILLS / "clonamic-spec" / "references" / "dev-spec.md",
    "report": SKILLS / "clonamic-finish" / "references" / "report.md",
}
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def frontmatter(text):
    if not text.startswith("---\n"):
        raise AssertionError("file must start with a frontmatter block")
    end = text.index("\n---\n", 4)
    fields = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            fields[key.strip()] = value.strip()
    return fields, text[end + 5 :]


def read(path):
    return path.read_text(encoding="utf-8")


class StructureTest(unittest.TestCase):
    def test_manifest(self):
        data = json.loads(read(ROOT / "plugin.json"))
        self.assertEqual(data["name"], ROOT.name)
        self.assertEqual(data["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(data["repository"], "https://github.com/clonamic/plugin")
        self.assertLessEqual(set(data), MANIFEST_KEYS)

    def test_exactly_four_stage_skills(self):
        folders = {p.name for p in SKILLS.iterdir() if p.is_dir()}
        self.assertEqual(folders, EXPECTED_SKILLS)
        for name in folders:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)

    def test_frontmatter_is_valid(self):
        for name in EXPECTED_SKILLS:
            fields, body = frontmatter(read(SKILLS / name / "SKILL.md"))
            self.assertEqual(fields.get("name"), name)
            self.assertRegex(name, r"^[a-z0-9-]+$")
            self.assertTrue(fields.get("description"), name)
            self.assertLessEqual(len(fields["description"]), 1024, name)
            self.assertTrue(body.strip(), name)

    def test_every_linked_reference_exists(self):
        for skill_md in SKILLS.glob("*/SKILL.md"):
            for target in LINK.findall(read(skill_md)):
                if "://" in target:
                    continue
                self.assertTrue((skill_md.parent / target).is_file(), f"{skill_md.parent.name}: {target}")

    def test_format_references_keep_their_contracts(self):
        texts = {key: read(path) for key, path in FORMATS.items()}
        for text in texts.values():
            self.assertNotIn("```규칙", text)
        self.assertIn("승인 대기 — 작업명세서", texts["work"])
        self.assertIn("승인 대기 — 개발명세서", texts["dev"])
        self.assertIn("결과1 [완료1]", texts["report"])
        for key in ("work", "dev"):
            self.assertIn("세 번째 승인은 어떤 경우에도 없다", texts[key], key)

    def test_spec_skill_caps_approvals_at_two(self):
        text = read(SKILLS / "clonamic-spec" / "SKILL.md")
        self.assertIn("at most two approvals", text)
        for removed in ("re-approval", "back to 작업명세서", "→ new 작업명세서"):
            self.assertNotIn(removed, text)
        approvals = [int(n) for n in re.findall(r"^\|[^\n]*\|\s*(\d+)\s*\|$", text, re.M)]
        self.assertTrue(approvals)
        self.assertLessEqual(max(approvals), 2)

    def test_reviewer_subagent(self):
        self.assertEqual({p.stem for p in AGENTS.glob("*.md")}, EXPECTED_AGENTS)
        fields, body = frontmatter(read(AGENTS / "clonamic-reviewer.md"))
        self.assertEqual(fields.get("name"), "clonamic-reviewer")
        self.assertEqual(fields.get("model"), "inherit")
        self.assertTrue(fields.get("description"))
        self.assertNotIn("Write", fields.get("tools", ""))
        self.assertNotIn("Edit", fields.get("tools", ""))
        for token in ("VERDICT: ACCEPT | REJECT", "rework:", "re-verify:"):
            self.assertIn(token, body)
        team = read(SKILLS / "clonamic-team" / "SKILL.md")
        self.assertIn("agents/clonamic-reviewer.md", team)
        self.assertIn("Codex", team)

    def test_self_contained(self):
        for path in [ROOT / "plugin.json", *SKILLS.rglob("*"), *AGENTS.rglob("*")]:
            if not path.is_file():
                continue
            text = read(path)
            self.assertNotIn("herness", text, path)
            for target in LINK.findall(text):
                if "://" not in target:
                    self.assertTrue((path.parent / target).resolve().is_relative_to(ROOT), f"{path}: {target}")

    def test_removed_machinery_stays_removed(self):
        for name in ("plugins", "catalog", "schemas", "clonamic.json", "clonamic-herness-plugin.md"):
            self.assertFalse((ROOT / name).exists(), name)
        self.assertEqual(list(SKILLS.rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
