import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED_SKILLS = {"clonamic-modular-design", "clonamic-safe-patch"}


def frontmatter(text):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return match.group(1) if match else ""


class CodePackageTest(unittest.TestCase):
    def test_root_manifest_is_minimal_mit_package(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", manifest["$schema"])
        self.assertEqual(
            {"$schema", "name", "version", "description", "license", "author", "keywords", "repository"},
            set(manifest),
        )
        self.assertEqual("clonamic-code", manifest["name"])
        self.assertEqual(ROOT.name, manifest["name"])
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        for absent in ("mcp.json", ".mcp.json", "bin", "commands"):
            self.assertFalse((ROOT / absent).exists(), absent)

    def test_skills_are_complete_and_self_contained(self):
        folders = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(EXPECTED_SKILLS, folders)
        self.assertEqual(len(EXPECTED_SKILLS), len(list(SKILLS.rglob("SKILL.md"))))
        for name in EXPECTED_SKILLS:
            folder = SKILLS / name
            text = (folder / "SKILL.md").read_text(encoding="utf-8")
            meta = frontmatter(text)
            self.assertRegex(meta, rf"(?m)^name: {re.escape(name)}$")
            self.assertRegex(meta, r"(?m)^description: .+$")
            self.assertTrue((folder / "agents" / "openai.yaml").is_file())
            self.assertNotIn("TODO", text)
            for link in re.findall(r"\]\((references/[^)]+)\)", text):
                self.assertTrue((folder / link).is_file(), f"{name}: broken link {link}")
            for reference in (folder / "references").glob("*"):
                self.assertNotIn("---\nname:", reference.read_text(encoding="utf-8")[:20], reference)

    def test_package_has_no_external_runtime_or_forbidden_branding(self):
        forbidden = (
            "super" + "powers",
            "clu" + "xion",
            "cl" + "x-",
            "cod" + "ex exec",
            "clau" + "de",
            "gr" + "ok",
            "her" + "mes",
            "mcp" + "Servers",
            "ultra" + "code",
            "code-" + "router",
            "super" + "coder",
        )
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or "tests" in path.parts
                or "__pycache__" in path.parts
                or path.parts[len(ROOT.parts)].startswith(".")
            ):
                continue
            text = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                self.assertNotIn(token.casefold(), text, f"{token} in {path.relative_to(ROOT)}")

    def test_failure_semantics_are_declared_once_per_skill(self):
        expected = {
            "clonamic-modular-design": {"blocked_missing_evidence", "invalid_contract"},
            "clonamic-safe-patch": {
                "capability_missing",
                "stale_file",
                "ambiguous_match",
                "syntax_rejected",
                "verification_failed",
            },
        }
        for skill, statuses in expected.items():
            text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
            failure = text.split("## Failure", 1)[1]
            for status in statuses:
                self.assertIn(f"`{status}`", failure, f"{skill}: {status}")

    def test_safe_patch_requires_explicit_invocation_on_codex(self):
        yaml = (SKILLS / "clonamic-safe-patch" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", yaml)
        self.assertIn("$clonamic-safe-patch", yaml)


if __name__ == "__main__":
    unittest.main()
