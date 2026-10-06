from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "clonamic-task-log"
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ALLOWED_KEYS = {"$schema", "name", "version", "description", "license", "author", "keywords", "homepage", "repository"}


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


class ManifestTests(unittest.TestCase):
    def test_root_manifest(self) -> None:
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertLessEqual(set(manifest), ALLOWED_KEYS)
        self.assertEqual(manifest["$schema"], SCHEMA)
        self.assertEqual(manifest["name"], "clonamic-task-log")
        self.assertEqual(manifest["name"], ROOT.name)
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["author"], {"name": "Clonamic"})
        self.assertEqual(manifest["repository"], "https://github.com/clonamic/plugin")
        self.assertNotIn("homepage", manifest)
        self.assertIn("/clonamic-task-log", manifest["description"])

    def test_single_mit_license_and_no_external_attribution(self) -> None:
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Permission is hereby granted", text)
        self.assertEqual(re.findall(r"^Copyright .*$", text, re.MULTILINE), ["Copyright (c) 2026 Clonamic"])
        banned = re.compile(r"hermes|ktb|kakaotech|adapted from|fork of|inspired by", re.I)
        for path in ROOT.rglob("*"):
            if path.is_file() and "tests" not in path.parts and path.suffix in {".md", ".py", ".json", ".yaml"}:
                self.assertIsNone(banned.search(path.read_text(encoding="utf-8")), path)


class StructureTests(unittest.TestCase):
    def test_one_skill_with_scripts_inside(self) -> None:
        self.assertEqual(sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir()), ["clonamic-task-log"])
        self.assertTrue((SKILL / "SKILL.md").is_file())
        scripts = sorted(p.name for p in (SKILL / "scripts").glob("*.py"))
        self.assertTrue({"collect.py", "common.py", "gate.py", "preflight.py", "progress.py", "redact.py",
                         "score.py", "tasklog.py", "write.py"} <= set(scripts), scripts)
        for path in ROOT.rglob("*"):
            self.assertNotIn(path.name, {"__pycache__", ".venv", "node_modules"}, path)

    def test_explicit_command_frontmatter_and_korean_body(self) -> None:
        fields, body = frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(fields["name"], "clonamic-task-log")
        self.assertEqual(fields["disable-model-invocation"], "true")
        self.assertEqual(fields["user-invocable"], "true")
        self.assertIn("/clonamic-task-log", fields["description"])
        self.assertIn("/clonamic-task-log`를 직접 입력했을 때만", body)
        self.assertGreater(hangul_ratio(body), 0.6)

    def test_writer_subagent(self) -> None:
        fields, body = frontmatter((ROOT / "agents" / "clonamic-task-logger.md").read_text(encoding="utf-8"))
        self.assertEqual(fields["name"], "clonamic-task-logger")
        self.assertEqual(fields["model"], "sonnet")
        self.assertTrue(fields["description"])
        self.assertIn("파일을 만들거나 고치지 않는다", body)
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("clonamic-task-log:clonamic-task-logger", skill)
        self.assertIn("gpt-6-luna", skill)
        self.assertIn("서브에이전트를 쓸 수 없음", skill)
        self.assertIn("리더가 같은 본문을 따라 차례로 직접 쓰고", skill)

    def test_skill_contract_1_1(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("/clonamic-task-log [날짜]", "prepare", "--on", "korean", "gate", "write", "notion-set", "save",
                       "gpt-6-luna", "https://github.com/clonamic/plugin", "WORK NOTES", "작업 메모",
                       "claude plugin install clonamic-korean@clonamic", "codex plugin add clonamic-korean@clonamic",
                       "grok plugin enable clonamic-korean", "~/.cursor/plugins/local/clonamic-korean"):
            self.assertIn(needle, skill)
        self.assertLess(skill.index("korean"), skill.index("prepare --on"))
        self.assertNotRegex(skill, r"HTML 주석[을를]? (넣|쓴|남긴)")
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.2.1")
        for sub in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            path = ROOT / sub / "plugin.json"
            if path.is_file():
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], "1.2.1", sub)

    def test_entry_template_headings(self) -> None:
        text = (SKILL / "references" / "entry.md").read_text(encoding="utf-8")
        for heading in ("## 핵심 요약", "## 한 일", "## 기술 판단", "## 문제 해결", "## 오늘 변화", "## 다음 할 일",
                        "- 배경 —", "- 접근 —", "- 결과 —", "- 그 밖에 —", "(측정)", "내부 용어", "- 영향:", "- 검증:"):
            self.assertIn(heading, text)
        self.assertGreaterEqual(text.count("# 20"), 3)
        examples_only = "\n".join(re.findall(r"````text\n(.*?)````", text, re.DOTALL))
        self.assertNotIn("\n## 포트폴리오 문장", examples_only)
        self.assertNotIn("\n## 진행 상황", examples_only)
        for old in ("근거·신뢰도", "목표·맥락", "기여·영향", "한눈에 보기", "증거 지문"):
            self.assertNotIn(old, text)
        examples = "\n".join(re.findall(r"````text\n(.*?)````", text, re.DOTALL))
        self.assertIn("## 핵심 요약", examples)
        for label in ("[측정]", "[판단]", "[전달]", "[가정]", "[미확인]", "<!--"):
            self.assertNotIn(label, examples)

    def test_notion_and_portfolio_references(self) -> None:
        refs = SKILL / "references"
        notion = (refs / "notion.md").read_text(encoding="utf-8") + (refs / "notion-template.md").read_text(encoding="utf-8")
        self.assertIn("MMDD~MMDD", notion)
        self.assertIn("대표 성과", notion)
        self.assertNotIn("증거 지문", notion)
        self.assertNotRegex(notion, r"<!--")
        portfolio = (refs / "portfolio.md").read_text(encoding="utf-8")
        for part in ("역할 한 줄", "대표 성과", "기능별 기여", "사용 기술", "문제 해결 사례"):
            self.assertIn(part, portfolio)

    def test_writer_agent_contract(self) -> None:
        body = (ROOT / "agents" / "clonamic-task-logger.md").read_text(encoding="utf-8")
        for needle in ("WORK NOTES", "ai-tells.md", "(측정)", "것으로 보입니다", "숫자는 입력", "기록 본문 마크다운만"):
            self.assertIn(needle, body)

    def test_readme_is_korean_and_top_down(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(headings[0], "## 핵심 요약")
        self.assertGreater(hangul_ratio(text), 0.5)
        for topic in ("log-part", "개인페이지 / project / <프로젝트명> / 작업로그", "clonamic-task-logger", "(측정)", "rebind",
                      "1.1.0", "1.2.1", "[날짜]", "다시 정리", "마일스톤 미설정"):
            self.assertIn(topic, text)

    def test_no_portfolio_sentence_section_anywhere_and_new_default_path(self) -> None:
        for doc in [ROOT / "README.md", ROOT / "agents" / "clonamic-task-logger.md", SKILL / "SKILL.md",
                    *(SKILL / "references").glob("*.md")]:
            text = doc.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"^## 포트폴리오 문장", doc.name)
            if doc.name != "README.md":  # the README changelog quotes the old default on purpose
                self.assertNotIn("개인 페이지 /", text, doc.name)
        self.assertIn("개인페이지 / project /", (SKILL / "references" / "setup.md").read_text(encoding="utf-8"))
        self.assertIn("개인페이지 / project /", (SKILL / "references" / "notion.md").read_text(encoding="utf-8"))

    def test_entry_examples_pass_the_gate(self) -> None:
        import sys
        sys.path.insert(0, str(SKILL / "scripts"))
        sys.dont_write_bytecode = True
        import gate
        from common import parse_profile

        text = (SKILL / "references" / "entry.md").read_text(encoding="utf-8")
        examples = re.findall(r"## 예시 \d[^\n]*\n\n````text\n(.*?)````", text, re.DOTALL)
        self.assertEqual(len(examples), 2)
        profile = parse_profile("- 신원: me@example.com\n- 내부 용어: 게이트, 작업 메모, 지문\n")
        run = {"metrics": [], "touched_features": ["기록 저장", "사진 업로드", "로그인"],
               "progress": [{"feature": "기록 저장", "pct": 70, "prev": 60, "milestones": [2, 3]},
                            {"feature": "사진 업로드", "pct": 35, "prev": 30, "milestones": [0, 0]}]}
        for example in examples:
            result = gate.check(example, profile, run)
            self.assertEqual(result["blocked"], [], example[:40])
        self.assertEqual(sum(1 for ln in examples[0].splitlines() if ln.strip()) <= 40, True)

    def test_skill_documents_notes_reuse_and_grouping(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("notes --check --save", "saved_notes", "다시 정리", "최대 3개", "검증: ", "`unknown`", "영향:",
                       "내부 용어"):
            self.assertIn(needle, skill)
        agent = (ROOT / "agents" / "clonamic-task-logger.md").read_text(encoding="utf-8")
        for needle in ("- 배경 —", "- 접근 —", "- 결과 —", "검증", "없음", "내부 매개변수", "게이트가 대괄호 꼬리표를 막게 했습니다"):
            self.assertIn(needle, agent)

    def test_codex_policy_is_explicit_only(self) -> None:
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: false", text)
        self.assertIn("$clonamic-task-log", text)

    def test_local_links_resolve(self) -> None:
        for doc in [SKILL / "SKILL.md", *(SKILL / "references").glob("*.md")]:
            for target in re.findall(r"\]\(([^)#\s]+)\)", doc.read_text(encoding="utf-8")):
                if re.match(r"[a-z]+:", target) or target.endswith(".md") and re.match(r"\d{4}-", target):
                    continue
                self.assertTrue((doc.parent / target).exists(), f"{doc.name} -> {target}")

    def test_scripts_guard_python_version(self) -> None:
        text = (SKILL / "scripts" / "tasklog.py").read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 12)", text)
        self.assertIn("uv python install 3.12", text)


if __name__ == "__main__":
    unittest.main()
