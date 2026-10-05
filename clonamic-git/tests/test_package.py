import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED = {"clonamic-commit", "clonamic-git-clean", "clonamic-git-setup"}
EXPLICIT = {"clonamic-git-clean", "clonamic-git-setup"}


def frontmatter(path: Path) -> str:
    match = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return match.group(1) if match else ""


class PackageTest(unittest.TestCase):
    def test_manifest(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(ROOT.name, manifest["name"])
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        self.assertEqual("https://github.com/clonamic/plugin", manifest["repository"])
        self.assertEqual(
            {"$schema", "name", "version", "description", "license", "author", "keywords", "repository"}, set(manifest)
        )
        self.assertIn("Copyright (c) 2026 Clonamic", (ROOT / "LICENSE").read_text(encoding="utf-8"))

    def test_skills(self):
        self.assertEqual(EXPECTED, {p.name for p in SKILLS.iterdir() if p.is_dir()})
        for name in EXPECTED:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            meta = frontmatter(SKILLS / name / "SKILL.md")
            self.assertRegex(meta, rf"(?m)^name: {name}$")
            explicit = name in EXPLICIT
            self.assertEqual(explicit, "disable-model-invocation: true" in meta, name)
            self.assertEqual(explicit, "user-invocable: true" in meta, name)
            self.assertEqual(explicit, "Runs only on the explicit" in text, name)
            for script in re.findall(r"scripts/([a-z_]+\.py)", text):
                self.assertTrue((ROOT / "scripts" / script).is_file(), f"{name}: {script}")

    def test_setup_names_every_host_switch(self):
        text = (SKILLS / "clonamic-git-setup" / "SKILL.md").read_text(encoding="utf-8")
        for token in ('"attribution"', "attributeCommitsToAgent", "attributePRsToAgent", "commit_attribution",
                      "Grok Build", "cli-config.json"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
