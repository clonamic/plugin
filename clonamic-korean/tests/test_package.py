from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "clonamic-korean"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ALLOWED_KEYS = {"$schema", "name", "version", "description", "license", "author", "keywords", "homepage", "repository"}
REFERENCES = {
    "ai-tells.md",
    "field-lessons.md",
    "genres.md",
    "openings.md",
    "plain-korean.md",
    "preserve.md",
    "rewriting.md",
    "story.md",
    "voice.md",
}


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "SKILL.md needs YAML frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, match.group(2)


def hangul_ratio(text: str) -> float:
    prose = re.sub(r"```.*?```|`[^`]*`|\([^)]*\.md\)", "", text, flags=re.DOTALL)
    hangul = len(re.findall(r"[가-힣]", prose))
    latin = len(re.findall(r"[A-Za-z]", prose))
    return hangul / max(1, hangul + latin)


def local_links(text: str) -> list[str]:
    return [t for t in re.findall(r"\]\(([^)#\s]+)\)", text) if not re.match(r"[a-z]+:", t)]


class ManifestTests(unittest.TestCase):
    def test_root_manifest(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertLessEqual(set(manifest), ALLOWED_KEYS)
        self.assertEqual(manifest["$schema"], SCHEMA)
        self.assertEqual(manifest["name"], "clonamic-korean")
        self.assertEqual(manifest["name"], ROOT.name)
        self.assertEqual(manifest["version"], "2.0.0")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["author"], {"name": "Clonamic"})
        self.assertIn("/clonamic-korean", manifest["description"])
        for word in ("resume", "portfolio", "report"):
            self.assertIn(word, manifest["description"].lower())

    def test_license_and_notices_travel_with_the_skill(self) -> None:
        root_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
        skill_license = (SKILL / "LICENSE").read_text(encoding="utf-8")
        self.assertEqual(root_license, skill_license)
        for holder in ("epoko77-ai", "Artem Novitckii", "Clonamic"):
            self.assertIn(f"Copyright (c) 2026 {holder}", skill_license)
        self.assertIn("Permission is hereby granted", skill_license)
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for upstream in ("dumbify", "storytelling", "viral-hooks", "voice-dna", "anti-ai-writing", "humanize-korean"):
            self.assertIn(upstream, notices)
        for adapted in ("plain-korean.md", "story.md", "openings.md", "voice.md"):
            text = (SKILL / "references" / adapted).read_text(encoding="utf-8")
            self.assertIn("artemnovitckii/content-skills", text, adapted)
            self.assertIn("(../LICENSE)", text, adapted)


class StructureTests(unittest.TestCase):
    def test_single_skill_and_no_pseudo_skill_folders(self) -> None:
        folders = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())
        self.assertEqual(folders, ["clonamic-korean"])
        for folder in (ROOT / "skills").iterdir():
            if folder.is_dir():
                self.assertTrue((folder / "SKILL.md").is_file(), folder)

    def test_no_orchestration_leftovers(self) -> None:
        for removed in ("agents", "scripts", "skills/humanize-korean"):
            self.assertFalse((ROOT / removed).exists(), removed)
        self.assertEqual(sorted(p.name for p in (SKILL / "scripts").glob("*.py")), ["check_revision.py"])
        self.assertEqual({p.name for p in (SKILL / "references").iterdir()}, REFERENCES)

    def test_merged_plugins_are_gone(self) -> None:
        for merged in ("clonamic-writing-plugin", "clonamic-my-language-plugin"):
            self.assertFalse((ROOT.parent / merged).exists(), merged)


class SkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.fields, self.body = frontmatter(self.text)

    def test_explicit_command_frontmatter(self) -> None:
        self.assertEqual(self.fields["name"], "clonamic-korean")
        self.assertEqual(self.fields["disable-model-invocation"], "true")
        self.assertEqual(self.fields["user-invocable"], "true")
        self.assertIn("/clonamic-korean", self.fields["description"])
        self.assertIn("ONLY", self.fields["description"])
        policy = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", policy)

    def test_body_states_explicit_only(self) -> None:
        self.assertIn("`/clonamic-korean`을 직접 입력했을 때만 실행한다", self.body)

    def test_body_is_korean(self) -> None:
        self.assertGreater(hangul_ratio(self.body), 0.85)
        for ref in REFERENCES:
            text = (SKILL / "references" / ref).read_text(encoding="utf-8")
            self.assertGreater(hangul_ratio(text), 0.7, ref)

    def test_every_reference_is_linked_and_every_link_exists(self) -> None:
        linked = set()
        for path in [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]:
            for target in local_links(path.read_text(encoding="utf-8")):
                resolved = (path.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"{path.name} -> {target}")
                linked.add(resolved)
        for ref in REFERENCES:
            self.assertIn((SKILL / "references" / ref).resolve(), linked, ref)
        skill_links = {Path(t).name for t in local_links(self.body)}
        self.assertLessEqual(REFERENCES, skill_links)

    def test_modes_are_selected_by_natural_language(self) -> None:
        for phrase in ("가볍게", "깊게", "진단만", "써줘", "내 문체로", "쉽게", "이야기처럼", "첫 문장"):
            self.assertIn(phrase, self.body)

    def test_quality_bar_carries_field_lessons(self) -> None:
        for marker in ("100%", "원천 차단", "격상", "임팩트", "어필", "~로 적혀 있습니다", "전담(100%)", "CSS", "-하였-"):
            self.assertIn(marker, self.body)

    def test_portable_core(self) -> None:
        for claude_only in ("Agent 도구", "Task(", "CLAUDE_PLUGIN_ROOT", "~/.claude", "_workspace", "run_id", "Glob("):
            self.assertNotIn(claude_only, self.text)
        self.assertIn("python3 scripts/check_revision.py", self.body)
        self.assertIn("3.12", self.body)
        self.assertIn("수동 대조", self.body)

    def test_inactive_signals_stay_inactive(self) -> None:
        catalog = (SKILL / "references" / "ai-tells.md").read_text(encoding="utf-8")
        active, marker, inactive = catalog.partition("## 켜지 않는 신호")
        self.assertTrue(marker)
        self.assertNotIn("`를 통해`", active)
        self.assertIn("`를 통해`를 무조건 삭제하지 않는다", inactive)
        self.assertIn("것이다", inactive)

    def test_voice_mode_needs_no_private_runtime(self) -> None:
        voice = (SKILL / "references" / "voice.md").read_text(encoding="utf-8")
        self.assertIn("데이터베이스나 백그라운드 수집 없이", voice)
        self.assertIn("기본은 저장하지 않는다", voice)
        self.assertIn("TEMPLATE-UNFILLED", voice)
        for forbidden in ("sqlite", "~/.agents", "~/.claude", "~/.codex", "~/.grok"):
            self.assertNotIn(forbidden, voice)


if __name__ == "__main__":
    unittest.main()
