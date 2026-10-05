from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "skills" / "clonamic-korean"
SCRIPT = SKILL / "scripts" / "check_revision.py"
LESSONS = SKILL / "references" / "field-lessons.md"

spec = importlib.util.spec_from_file_location("check_revision", SCRIPT)
cr = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["check_revision"] = cr  # dataclasses resolve string annotations via sys.modules
spec.loader.exec_module(cr)


def codes(result: dict) -> set[str]:
    return {f["code"] for f in result["violations"] + result["warnings"]}


def violations(result: dict) -> set[str]:
    return {f["code"] for f in result["violations"]}


class NumberTests(unittest.TestCase):
    def test_injected_number_is_a_violation(self) -> None:
        result = cr.check("응답 시간이 3.2초에서 0.83초로 줄었습니다.", "응답 시간을 74% 단축(3.85배)했습니다.", deep=True)
        self.assertEqual(result["code"], 2)
        self.assertIn("number_injected", violations(result))
        self.assertIn("74", result["violations"][0]["detail"])

    def test_notation_changes_are_not_injection(self) -> None:
        result = cr.check("매출은 10,000원, 사용자는 1만 명입니다.", "매출은 10000원, 사용자는 10,000명입니다.")
        self.assertNotIn("number_injected", codes(result))

    def test_list_numbering_is_not_a_number(self) -> None:
        result = cr.check("속도를 개선했습니다.\n배포를 자동화했습니다.", "1. 속도를 개선했습니다.\n2. 배포를 자동화했습니다.")
        self.assertNotIn("number_injected", codes(result))
        self.assertIn("format_added", codes(result))

    def test_dropped_number_is_a_warning(self) -> None:
        result = cr.check("기여 5:5로 설계를 맡았습니다.", "설계를 맡았습니다.", deep=True)
        self.assertIn("number_dropped", codes(result))
        self.assertNotEqual(result["code"], 2)


class FidelityTests(unittest.TestCase):
    def test_attributed_quote_is_immutable(self) -> None:
        source = '그는 "이번 분기 목표는 반드시 지킨다"고 말했다.'
        result = cr.check(source, '그는 "이번 분기 목표는 꼭 지킨다"고 말했다.')
        self.assertIn("quote_altered", violations(result))

    def test_rhetorical_quote_can_change(self) -> None:
        source = '우리 팀의 원칙은 "빨리 만들고 자주 고친다"였다.'
        result = cr.check(source, '우리 팀의 원칙은 "빨리 만들고 자주 고치자"였다.')
        self.assertNotIn("quote_altered", codes(result))

    def test_code_block_is_immutable(self) -> None:
        source = "설치합니다.\n\n```bash\nuv sync\n```\n"
        result = cr.check(source, "설치합니다.\n\n```bash\nuv sync --frozen\n```\n")
        self.assertIn("code_altered", violations(result))

    def test_terms_dropped_and_added(self) -> None:
        result = cr.check(
            "모델은 vLLM으로 서빙하고 RAG로 검색을 붙였습니다.",
            "모델은 서빙 엔진으로 돌리고 Deep Dive 검색을 붙였습니다.",
        )
        self.assertIn("term_dropped", codes(result))
        self.assertIn("term_added", codes(result))

    def test_modality_loss(self) -> None:
        result = cr.check("이 방식이 더 빠를 수 있습니다. 위험은 낮은 것으로 판단된다.", "이 방식이 더 빠릅니다. 위험은 낮은 수치다.")
        self.assertIn("modality_lost", codes(result))

    def test_modality_kept(self) -> None:
        result = cr.check("규정을 고쳐야 한다. 효과가 클 수 있다.", "규정을 고쳐야 한다. 효과가 클 수도 있다.")
        self.assertNotIn("modality_lost", codes(result))

    def test_noun_ya_is_not_obligation(self) -> None:
        self.assertEqual(cr.DEONTIC_RE.findall("이 분야 해설서를 읽었다."), [])
        self.assertTrue(cr.DEONTIC_RE.findall("손봐야 한다."))


class RegisterAndWordingTests(unittest.TestCase):
    def test_register_shift(self) -> None:
        source = "배포했습니다. 고쳤습니다. 줄였습니다. 붙였습니다."
        result = cr.check(source, "배포했다. 고쳤다. 줄였다. 붙였다.", deep=True)
        self.assertIn("register_shift", codes(result))

    def test_hayeot_increase(self) -> None:
        result = cr.check("검토했다.", "검토하였다.")
        self.assertIn("register_shift", codes(result))

    def test_increase_only_wording(self) -> None:
        source = "엔지니어링 임팩트를 정리했습니다."
        self.assertNotIn("loanword_added", codes(cr.check(source, source)))
        result = cr.check("XSS를 막았습니다.", "XSS를 원천 차단해 무결성을 확보했습니다.", deep=True)
        self.assertIn("hype_added", codes(result))
        result = cr.check("다음 강의에 못 넘어갑니다.", "응답 지연으로 인한 학습 단절 현상이 발생합니다.", deep=True)
        self.assertIn("nominal_added", codes(result))
        result = cr.check("배포하지 않기로 했습니다.", "배포 불가로 적혀 있습니다.", deep=True)
        self.assertIn("observer_added", codes(result))

    def test_heading_change(self) -> None:
        result = cr.check("## 기술 선택\n\n본문입니다.", "## Tech Decisions\n\n본문입니다.")
        self.assertIn("heading_changed", codes(result))

    def test_contrast_wiped(self) -> None:
        source = "A가 아니라 B다. C가 아니라 D다. E가 아니라 F다. G가 아니라 H다. I가 아니라 J다."
        result = cr.check(source, "B다. D다. F다. H다. J다.", deep=True)
        self.assertIn("contrast_wiped", codes(result))


class RateTests(unittest.TestCase):
    def test_identical_text_passes(self) -> None:
        text = "결제 모듈을 리팩터링해 장애 건수를 줄였습니다."
        result = cr.check(text, text)
        self.assertEqual(result, {"code": 0, "change_rate": 0.0, "violations": [], "warnings": []})

    def test_thresholds(self) -> None:
        self.assertAlmostEqual(cr.change_rate("가나다라마바사아자차", "가나다라마바사아자타"), 0.1)
        self.assertEqual(cr.check("가나다라마바사아자차", "가나다라마바사아자타")["code"], 0)
        heavy = cr.check("가나다라마바사아자차", "타파하거너더러머버서")
        self.assertIn("over_revised", violations(heavy))
        deep = cr.check("가나다라마바사아자차", "타파하거너더러머버서", deep=True)
        self.assertNotIn("over_revised", codes(deep))
        self.assertIn("change_rate", codes(deep))

    def test_empty_output(self) -> None:
        self.assertIn("empty_output", violations(cr.check("본문", "  \n")))

    def test_long_document_is_fast_enough(self) -> None:
        import time

        sentence = "사용자 입력을 검증하고 결과를 기록했습니다. "
        source = "".join(f"{i}번째 단계에서 {sentence}" for i in range(400))
        revised = source.replace("기록했습니다", "남겼습니다")
        start = time.perf_counter()
        rate = cr.change_rate(source, revised)
        self.assertLess(time.perf_counter() - start, 10)
        self.assertGreater(rate, 0)
        self.assertLess(rate, 0.3)


class CliTests(unittest.TestCase):
    def run_cli(self, before: str, after: str, *extra: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "before.txt", Path(tmp) / "after.txt"
            src.write_text(before, encoding="utf-8")
            out.write_text(after, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--before", str(src), "--after", str(out), *extra],
                capture_output=True, text=True, check=False,
            )

    def test_exit_codes_and_output(self) -> None:
        ok = self.run_cli("원문입니다.", "원문입니다.")
        self.assertEqual(ok.returncode, 0)
        self.assertIn("판정: 통과", ok.stdout)
        bad = self.run_cli("응답이 빨라졌습니다.", "응답이 74% 빨라졌습니다.", "--json")
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(json.loads(bad.stdout)["violations"][0]["code"], "number_injected")

    def test_missing_input(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--before", "/nonexistent/a", "--after", "/nonexistent/b"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 3)

    def test_stdlib_only_and_python_floor(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 12)", source)
        imports = set(re.findall(r"^(?:import|from) ([a-z_]+)", source, re.MULTILINE))
        self.assertLessEqual(imports, set(sys.stdlib_module_names) | {"__future__"})


class FieldLessonRegressionTests(unittest.TestCase):
    """Every bad fix in field-lessons.md must be flagged; no good fix may be blocked."""

    def cases(self) -> list[tuple[str, dict[str, str]]]:
        text = LESSONS.read_text(encoding="utf-8")
        found = []
        for section in re.split(r"^### ", text, flags=re.MULTILINE)[1:]:
            title = section.splitlines()[0]
            examples = dict(re.findall(r"\*\*(원문|나쁜 수정|좋은 수정)\*\*\n```text\n(.*?)\n```", section, re.DOTALL))
            found.append((title, examples))
        return found

    def test_lessons_have_complete_examples(self) -> None:
        cases = self.cases()
        self.assertGreaterEqual(len(cases), 12)
        for title, examples in cases:
            self.assertEqual(set(examples), {"원문", "나쁜 수정", "좋은 수정"}, title)

    def test_bad_fixes_are_flagged_and_good_fixes_pass(self) -> None:
        for title, ex in self.cases():
            with self.subTest(case=title):
                bad = cr.check(ex["원문"], ex["나쁜 수정"], deep=True)
                good = cr.check(ex["원문"], ex["좋은 수정"], deep=True)
                self.assertGreaterEqual(bad["code"], 1)
                self.assertEqual(good["violations"], [])
                self.assertTrue(codes(bad) - codes(good), "bad fix must trip something the good fix does not")

    def test_named_field_failures_are_caught(self) -> None:
        cases = dict(self.cases())
        expect = {
            "3. 사용자 가이드를 다른 모양으로 어기기": "number_injected",
            "4. 근거 없는 절대 표현": "hype_added",
            "5. 계산해서 만든 숫자": "number_injected",
            "6. 쉬운 입말을 명사 사슬로 바꾸기": "nominal_added",
            "7. 외래어 업무 용어와 기술 용어": "term_dropped",
            "8. 서식 과잉": "format_added",
            "9. 범위 넘기": "heading_changed",
            "12. 유보를 단정으로": "modality_lost",
        }
        for title, code in expect.items():
            ex = cases[title]
            self.assertIn(code, codes(cr.check(ex["원문"], ex["나쁜 수정"], deep=True)), title)


if __name__ == "__main__":
    unittest.main()
