import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {"clonamic-harness-factory", "clonamic-host-config", "clonamic-model", "clonamic-repo-backup"}
EXPLICIT = {"clonamic-harness-factory", "clonamic-model", "clonamic-repo-backup"}


def frontmatter(path: Path) -> str:
    match = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return match.group(1) if match else ""


class PackageTest(unittest.TestCase):
    def test_manifest(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-admin", manifest["name"])
        self.assertEqual(ROOT.name, manifest["name"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        self.assertEqual(
            {"$schema", "name", "version", "description", "license", "author", "keywords", "repository"}, set(manifest)
        )

    def test_skills_are_complete(self):
        self.assertEqual(EXPECTED, {p.name for p in SKILLS.iterdir() if p.is_dir()})
        for name in EXPECTED:
            skill = SKILLS / name / "SKILL.md"
            meta = frontmatter(skill)
            self.assertRegex(meta, rf"(?m)^name: {name}$")
            for link in re.findall(r"\]\((references/[^)]+)\)", skill.read_text(encoding="utf-8")):
                self.assertTrue((SKILLS / name / link).is_file(), f"{name}: {link}")

    def test_explicit_command_skills_cannot_auto_load(self):
        for name in EXPLICIT:
            meta = frontmatter(SKILLS / name / "SKILL.md")
            self.assertIn("disable-model-invocation: true", meta, name)
            self.assertIn("user-invocable: true", meta, name)
            self.assertIn("Runs only on the explicit", (SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))

    def test_host_config_covers_both_hosts(self):
        text = "\n".join(p.read_text(encoding="utf-8") for p in (SKILLS / "clonamic-host-config").rglob("*.md"))
        for token in ("~/.claude", "~/.codex", "settings.json", "config.toml", "hooks.json", "CLAUDE.md", "AGENTS.md"):
            self.assertIn(token, text)

    def test_factory_has_no_vendored_library(self):
        skill = SKILLS / "clonamic-harness-factory"
        self.assertFalse((skill / "references").exists())
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("harness-library", text)
        self.assertIn("Never edit `CLAUDE.md` / `AGENTS.md` automatically", text)


if __name__ == "__main__":
    unittest.main()
