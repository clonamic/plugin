import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED_SKILLS = {
    "clonamic-ui-design",
    "clonamic-ui-review",
    "clonamic-browser-qa",
    "clonamic-visual-art",
    "clonamic-sketch-diagram",
}
CONTRAST = SKILLS / "clonamic-ui-review" / "scripts" / "contrast.py"
CHECKER = SKILLS / "clonamic-sketch-diagram" / "scripts" / "check_excalidraw.py"
ALLOWED_SUFFIXES = {".md", ".py", ".yaml", ".json"}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    keys = {}
    for line in match.group(1).splitlines():
        if line and not line[0].isspace() and ":" in line:
            key, value = line.split(":", 1)
            keys[key] = value.strip()
    return keys


def package_files():
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or relative.parts[0] in {"tests"} or relative.parts[0].startswith("."):
            continue
        if "__pycache__" in relative.parts:
            continue
        yield path, relative


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )


class ManifestTest(unittest.TestCase):
    def test_root_manifest_is_minimal_mit_package(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {"$schema", "name", "version", "description", "license", "author", "keywords", "repository"},
            set(manifest),
        )
        self.assertEqual("https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", manifest["$schema"])
        self.assertEqual("clonamic-design", manifest["name"])
        self.assertEqual(ROOT.name, manifest["name"])
        self.assertEqual("2.0.0", manifest["version"])
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        self.assertEqual("https://github.com/clonamic/plugin", manifest["repository"])

    def test_single_root_mit_license(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 Clonamic", text)
        self.assertEqual(["LICENSE"], [p.name for p, _ in package_files() if "license" in p.name.casefold()])


class SkillStructureTest(unittest.TestCase):
    def test_skill_set_is_exact(self):
        folders = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(EXPECTED_SKILLS, folders)
        self.assertEqual(len(EXPECTED_SKILLS), len(list(SKILLS.rglob("SKILL.md"))))

    def test_frontmatter_and_codex_interface(self):
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
                meta = frontmatter(text)
                self.assertEqual({"name", "description"}, set(meta))
                self.assertEqual(name, meta["name"])
                self.assertGreater(len(meta["description"]), 80)
                self.assertNotIn("TODO", text)
                yaml = (SKILLS / name / "agents" / "openai.yaml").read_text(encoding="utf-8")
                self.assertIn(f"${name}", yaml)
                self.assertIn("allow_implicit_invocation: true", yaml)

    def test_reference_links_resolve_and_no_orphans(self):
        for name in EXPECTED_SKILLS:
            folder = SKILLS / name
            text = (folder / "SKILL.md").read_text(encoding="utf-8")
            linked = set(re.findall(r"\]\((references/[^)]+)\)", text))
            for link in linked:
                self.assertTrue((folder / link).is_file(), f"{name}: broken link {link}")
            present = {f"references/{p.name}" for p in (folder / "references").glob("*")}
            self.assertEqual(present, linked, f"{name}: references must all be linked from SKILL.md")
            for script in (folder / "scripts").glob("*"):
                self.assertIn(f"scripts/{script.name}", text, f"{name}: unused script {script.name}")

    def test_cross_skill_paths_and_names_resolve(self):
        for path, relative in package_files():
            if path.suffix != ".md":
                continue
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"((?:\.\./)+clonamic-[a-z-]+/[\w./-]+\.py)", text):
                self.assertTrue((path.parent / target).resolve().is_file(), f"{relative}: {target}")
            for mentioned in re.findall(r"`(clonamic-[a-z-]+)`|\((clonamic-[a-z-]+)\)", text):
                skill = next(m for m in mentioned if m)
                self.assertIn(skill, EXPECTED_SKILLS, f"{relative}: stale skill name {skill}")

    def test_user_facing_report_examples_are_korean(self):
        for name in EXPECTED_SKILLS:
            text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("## Report format (user-facing, Korean)", text, name)
            example = text.split("## Report format (user-facing, Korean)", 1)[1]
            self.assertRegex(example, r"[가-힣]{2,}", name)


class NoVendoredMaterialTest(unittest.TestCase):
    def test_only_own_text_and_script_files(self):
        for path, relative in package_files():
            if relative == Path("LICENSE"):
                continue
            with self.subTest(path=str(relative)):
                self.assertIn(path.suffix, ALLOWED_SUFFIXES)
                self.assertLess(path.stat().st_size, 20_000)
                self.assertNotRegex(path.name.casefold(), r"notice|third_party|\.lock\.|\.min\.")
        self.assertFalse(list(ROOT.rglob("node_modules")))

    def test_no_attribution_or_source_names(self):
        forbidden = [
            "adapted from", "inspired by", "fork of", "upstream", "provenance", "copyright",
            "source_repo", "license_source", "vendored", "apache", "cc by", "lgpl",
            "ver" + "cel", "meo" + "dai", "kowal" + "ski", "pro-" + "max", "impec" + "cable",
            "ast" + "ryx", "anthro" + "pic", "design" + "skills", "fresh" + "tech",
            "navaneetha", "excalidraw." + "com", "ae" + "won", "notion." + "site",
        ]
        for path, relative in package_files():
            if relative == Path("LICENSE"):
                continue
            text = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                self.assertFalse(token in text, f"{token!r} in {relative}")
            for url in re.findall(r"https?://[^\s\"'`)<>]+", text):
                self.assertTrue(
                    url.startswith(("https://agent-plugins.org/", "https://github.com/clonamic/plugin",
                                    "https://cdn.jsdelivr.net/npm/", "http://localhost")),
                    f"unexpected link {url} in {relative}",
                )


class ContrastScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load(CONTRAST, "contrast")

    def test_known_ratios(self):
        rgb = lambda h: self.mod.parse_hex(h)[:3]
        self.assertAlmostEqual(21.0, self.mod.ratio(rgb("#000"), rgb("#fff")), places=2)
        self.assertAlmostEqual(4.48, round(self.mod.ratio(rgb("#777777"), rgb("#ffffff")), 2))
        self.assertAlmostEqual(1.0, self.mod.ratio(rgb("#3366cc"), rgb("#3366cc")))

    def test_exit_codes_and_fix(self):
        self.assertEqual(0, run(CONTRAST, "#000000", "#ffffff").returncode)
        self.assertEqual(2, run(CONTRAST, "nothex", "#ffffff").returncode)
        self.assertEqual(2, run(CONTRAST, "#000", "#ffffff80").returncode)
        result = run(CONTRAST, "#9AA0A6", "#FFFFFF", "--fix", "fg", "--json")
        self.assertEqual(1, result.returncode)
        data = json.loads(result.stdout)
        self.assertFalse(data["meets_target"])
        self.assertGreaterEqual(data["fix"]["ratio"], 4.5)
        fixed = self.mod.parse_hex(data["fix"]["value"])[:3]
        self.assertGreaterEqual(self.mod.ratio(fixed, (1.0, 1.0, 1.0)), 4.5)

    def test_fix_crosses_over_when_needed(self):
        data = json.loads(run(CONTRAST, "#FFFF00", "#FFFFFF", "--fix", "bg", "--json").stdout)
        self.assertGreaterEqual(data["fix"]["ratio"], 4.5)

    def test_translucent_foreground_is_composited(self):
        data = json.loads(run(CONTRAST, "#ffffff80", "#000000", "--json").stdout)
        self.assertEqual("#808080", data["fg"])

    def test_documented_starter_themes_are_true(self):
        table = (SKILLS / "clonamic-ui-design/references/color-and-theme.md").read_text(encoding="utf-8")
        rows = [line for line in table.splitlines() if line.startswith("| ") and "`#" in line]
        self.assertEqual(7, len(rows))
        rgb = lambda h: self.mod.parse_hex(h)[:3]
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            bg = re.search(r"#[0-9A-F]{6}", cells[2]).group(0)
            for cell, against in ((cells[3], bg), (cells[4], bg), (cells[5], bg)):
                color, claimed = re.match(r"`(#[0-9A-F]{6})` ([\d.]+)", cell).groups()
                measured = self.mod.ratio(rgb(color), rgb(against))
                self.assertGreaterEqual(measured, 4.5, row)
                self.assertAlmostEqual(float(claimed), measured, delta=0.06, msg=row)
            accent = re.match(r"`(#[0-9A-F]{6})`", cells[5]).group(1)
            label, claimed = re.match(r"`(#[0-9A-F]{6})` ([\d.]+)", cells[6]).groups()
            self.assertAlmostEqual(float(claimed), self.mod.ratio(rgb(label), rgb(accent)), delta=0.06)


def scene(*elements):
    return {"type": "excalidraw", "version": 2, "source": "test", "elements": list(elements), "appState": {}, "files": {}}


def shape(element_id, x, y, w=160, h=80, bound=()):
    return {"id": element_id, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "boundElements": [{"id": b, "type": t} for b, t in bound]}


def text(element_id, container, value, x=0, y=0, size=20):
    return {"id": element_id, "type": "text", "x": x, "y": y, "width": 100, "height": 25,
            "text": value, "fontSize": size, "containerId": container}


class ExcalidrawCheckerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load(CHECKER, "check_excalidraw")

    def write(self, data) -> str:
        handle = tempfile.NamedTemporaryFile("w", suffix=".excalidraw", delete=False, encoding="utf-8")
        with handle:
            handle.write(data if isinstance(data, str) else json.dumps(data))
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def valid_scene(self):
        arrow = {"id": "a1", "type": "arrow", "x": 160, "y": 40, "width": 140, "height": 0,
                 "points": [[0, 0], [140, 0]],
                 "startBinding": {"elementId": "api", "focus": 0, "gap": 4},
                 "endBinding": {"elementId": "db", "focus": 0, "gap": 4}}
        return scene(
            shape("api", 0, 0, bound=[("t1", "text"), ("a1", "arrow")]), text("t1", "api", "API"),
            shape("db", 300, 0, bound=[("t2", "text"), ("a1", "arrow")]), text("t2", "db", "DB"),
            arrow,
        )

    def test_valid_scene_passes_cleanly(self):
        errors, warnings = self.mod.check(self.valid_scene())
        self.assertEqual(([], []), (errors, warnings))
        self.assertEqual(0, run(CHECKER, self.write(self.valid_scene())).returncode)

    def test_reference_and_identity_errors(self):
        data = self.valid_scene()
        data["elements"][4]["endBinding"]["elementId"] = "ghost"
        data["elements"].append(shape("api", 600, 0))
        errors, _ = self.mod.check(data)
        self.assertTrue(any("ghost" in e for e in errors))
        self.assertTrue(any("duplicate id" in e for e in errors))
        self.assertEqual(1, run(CHECKER, self.write(data)).returncode)
        self.assertTrue(self.mod.check({"type": "other"})[0])
        self.assertTrue(self.mod.check(scene({"id": "l", "type": "line", "x": 0, "y": 0, "width": 0, "height": 0, "points": [[0, 0]]}))[0])

    def test_layout_warnings(self):
        data = scene(
            shape("a", 0, 0, bound=[("t", "text")]), text("t", "a", "아주 긴 한국어 라벨입니다"),
            shape("b", 100, 40),
        )
        errors, warnings = self.mod.check(data)
        self.assertEqual([], errors)
        self.assertTrue(any("overlaps" in w for w in warnings))
        self.assertTrue(any("text needs" in w for w in warnings))

    def test_invalid_json_is_usage_error(self):
        self.assertEqual(2, run(CHECKER, self.write("{not json")).returncode)


if __name__ == "__main__":
    unittest.main()
