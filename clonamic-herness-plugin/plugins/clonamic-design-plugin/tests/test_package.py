import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SKILL_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def top_level_frontmatter_keys(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"missing frontmatter: {path}")
    keys: set[str] = set()
    for line in lines[1:]:
        if line == "---":
            return keys
        if line and not line[0].isspace() and ":" in line:
            keys.add(line.split(":", 1)[0])
    raise AssertionError(f"unterminated frontmatter: {path}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackageTest(unittest.TestCase):
    def test_manifest_and_skills_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-design-plugin", manifest["name"])
        self.assertEqual("1.0.0", manifest["version"])
        self.assertEqual(
            "MIT AND Apache-2.0 AND CC-BY-4.0 AND LGPL-2.1-only",
            manifest["license"],
        )
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 10)
        self.assertEqual(skills, sorted((ROOT / "skills").rglob("SKILL.md")))

    def test_design_sources_are_revision_locked(self):
        lock = json.loads((ROOT / "design-sources.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(1, lock["schema_version"])
        self.assertEqual(10, len(lock["sources"]))
        self.assertEqual(1, len(lock["bundles"]))
        for source in lock["sources"]:
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(source["repository"].startswith("https://"))
            self.assertTrue(source["license"])
        bundle = lock["bundles"][0]
        self.assertEqual("p5.js", bundle["name"])
        for key in ("runtime_sha256", "source_sha256", "license_sha256"):
            self.assertRegex(bundle[key], r"^[0-9a-f]{64}$")

        ui_source = next(source for source in lock["sources"] if source["name"] == "ui-ux-pro-max-skill")
        vendored_root = ROOT / "skills/clonamic-frontend-design/references/ui-ux-pro-max"
        self.assertEqual(
            {relative: sha256(vendored_root / relative) for relative in ui_source["vendored_files"]},
            ui_source["vendored_files"],
        )

    def test_skill_frontmatter_uses_agent_skills_keys_only(self):
        for skill_path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=skill_path.parent.name):
                keys = top_level_frontmatter_keys(skill_path)
                self.assertLessEqual(keys, ALLOWED_SKILL_KEYS)
                self.assertTrue({"name", "description"}.issubset(keys))

    def test_optional_browser_and_design_runtime_never_self_install(self):
        playwright = (ROOT / "skills/clonamic-playwright/scripts/playwright_cli.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("npx", playwright)
        self.assertNotIn("--yes", playwright)
        self.assertIn("never downloads packages", playwright)

        impeccable = ROOT / "skills/clonamic-impeccable"
        self.assertFalse((impeccable / "reference/hooks.md").exists())
        self.assertFalse((impeccable / "scripts/hook-admin.mjs").exists())
        skill = (impeccable / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("does not install or activate editor hooks", skill)

        astryx = ROOT / "skills/clonamic-astryx"
        astryx_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(astryx.rglob("*.md"))
        )
        self.assertNotIn("npx ", astryx_text)
        self.assertIn("npm install --save-exact", astryx_text)
        self.assertIn("@<approved-version>", astryx_text)
        self.assertNotIn("npm install @astryx", astryx_text)

    def test_impeccable_is_host_neutral_read_only_by_default_and_pruned(self):
        root = ROOT / "skills/clonamic-impeccable"
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        critique = (root / "reference/critique.md").read_text(encoding="utf-8")
        self.assertIn("subordinate technique notes", skill)
        self.assertIn("Critique is read-only by default", critique)
        for forbidden in (
            "CLAUDE.md",
            "AskUserQuestion",
            "critique-storage",
            ".clonamic-impeccable/critique",
        ):
            self.assertNotIn(forbidden, skill + critique)
        for retired in ("codex", "craft", "shape", "init", "live", "document", "extract"):
            self.assertFalse((root / f"reference/{retired}.md").exists())
        scripts = {
            path.relative_to(root / "scripts").as_posix()
            for path in (root / "scripts").rglob("*")
            if path.is_file()
        }
        self.assertTrue(scripts)
        self.assertTrue(
            all(
                path == "detect.mjs"
                or path.startswith("detector/")
                or path in {"lib/impeccable-config.mjs", "lib/target-args.mjs"}
                for path in scripts
            ),
            sorted(scripts),
        )


if __name__ == "__main__":
    unittest.main()
