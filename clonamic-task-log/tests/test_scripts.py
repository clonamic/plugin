from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "clonamic-task-log" / "scripts"
TASKLOG = SCRIPTS / "tasklog.py"
KOREAN_SKILL = ROOT.parent / "clonamic-korean" / "skills" / "clonamic-korean"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True

import gate  # noqa: E402
import progress  # noqa: E402
import redact  # noqa: E402
from common import TaskLogError, parse_profile, parse_when  # noqa: E402

ME = "me@example.com"
KST = timezone(timedelta(hours=9))
DAY = "2026-09-29"
PROFILE = """# 작업 프로필

- 파트: 백엔드 개발
- 신원: me@example.com
- 작업 단위: 없음
- 시간대: Asia/Seoul

## 기능

### 결제 모듈
- 경로: src/payments, tests
- 키: payments
- 마일스톤:
  - [x] 결제 요청 API
  - [ ] 환불 처리
"""
_TMP = tempfile.TemporaryDirectory()
_HOME = Path(_TMP.name) / "home"
_HOME.mkdir()
(_HOME / ".gitconfig").write_text("", encoding="utf-8")
GIT_ENV = {**os.environ, "HOME": str(_HOME), "GIT_CONFIG_GLOBAL": str(_HOME / ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
GIT_ENV.pop("CLONAMIC_KOREAN_ROOT", None)


def tearDownModule() -> None:
    _TMP.cleanup()


class Repo:
    def __init__(self, base: Path, name: str, remote: str | None = None,
                 start: datetime = datetime(2026, 9, 29, 9, 0, tzinfo=KST)) -> None:
        self.path = base / name
        self.path.mkdir(parents=True)
        self.clock = start
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", ME)
        self.git("config", "user.name", "Me")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", remote or f"git@github.com:me/{name}.git")
        self.write(".gitignore", ".claude/\n")
        self.write("README.md", f"# {name}\n")  # distinct history per project
        self.commit("chore: init", who=("Me", ME))

    def git(self, *args: str, env: dict | None = None) -> str:
        return subprocess.run(["git", "-C", str(self.path), *args], check=True, capture_output=True, text=True,
                              env=env or GIT_ENV).stdout

    def write(self, rel: str, text: str) -> None:
        path = self.path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def stamp(self, at: datetime | None = None) -> str:
        """Author/committer date: explicit `at`, else five minutes after the previous commit."""
        self.clock = at or self.clock + timedelta(minutes=5)
        return self.clock.isoformat(timespec="seconds")

    def commit(self, message: str, who: tuple[str, str] = ("Me", ME), at: datetime | None = None) -> str:
        stamp = self.stamp(at)
        env = GIT_ENV | {"GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1], "GIT_AUTHOR_DATE": stamp,
                         "GIT_COMMITTER_DATE": stamp}
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message, env=env)
        return self.git("rev-parse", "HEAD").strip()

    def profile(self, text: str = PROFILE) -> Path:
        logs = self.path / ".claude" / "log-part"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "profile.md").write_text(text, encoding="utf-8")
        return logs

    def run_file(self) -> dict:
        return json.loads((self.path / ".claude/log-part/.run.json").read_text(encoding="utf-8"))

    def state(self) -> dict:
        return json.loads((self.path / ".claude/log-part/state.json").read_text(encoding="utf-8"))


def run(repo: Path, *args: str, env: dict | None = None) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(TASKLOG), "--repo", str(repo), "--agent-dir", ".claude", *args],
                          capture_output=True, text=True, env=(env or GIT_ENV) | {"PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, json.loads(proc.stdout)


def prepare(repo: Repo, on: str = DAY) -> dict:
    code, result = run(repo.path, "prepare", "--on", on)
    assert code == 0, result
    return result


def build_payments(repo: Repo) -> dict[str, str]:
    shas = {}
    repo.write("src/payments/core_pay.py", 'def pay(amount):\n    """Create a payment request."""\n    return amount\n')
    repo.write("src/payments/refund.py", "def refund():\n    raise NotImplementedError\n")
    shas["feat"] = repo.commit("feat(payments): add payment request API (latency 120ms -> 80ms)\n\n"
                               "Handle repeated payment requests so retries do not charge twice.")
    repo.write("tests/test_pay.py", "def test_pay():\n    assert True\n")
    shas["test"] = repo.commit("test: cover payment flow PAY-12")
    repo.write("src/payments/core_pay.py", 'def pay(amount):\n    """Create a payment request."""\n    # keep amounts in cents\n    return amount\n')
    shas["comment"] = repo.commit("chore: explain units")
    repo.write("src/payments/core_pay.py", 'def pay(amount):\n    """Create a payment request."""\n    # keep amounts in cents\n    return  amount\n\n')
    shas["space"] = repo.commit("style: spacing")
    repo.write("package-lock.json", '{"lockfileVersion": 3}\n')
    shas["lock"] = repo.commit("chore: refresh lock")
    repo.write("src/payments/flag.py", "ENABLED = True\n")
    shas["bad"] = repo.commit("feat: experimental flag")
    (repo.path / "src/payments/flag.py").unlink()
    shas["revert"] = repo.commit(f'Revert "feat: experimental flag"\n\nThis reverts commit {shas["bad"]}.')
    repo.write("docs/guide.md", "# Guide\n\nHow payments work.\n")
    shas["other"] = repo.commit("docs: payments guide", who=("Someone", "else@example.com"))
    repo.git("checkout", "-q", "-b", "side")
    repo.write("src/payments/side.py", "def side():\n    return 2\n")
    repo.commit("feat: side helper")
    repo.git("checkout", "-q", "main")
    stamp = repo.stamp()
    repo.git("merge", "-q", "--no-ff", "side", "-m", "Merge branch side",
             env=GIT_ENV | {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
    return shas


def entry_for(result: dict, day: str | None = None) -> str:
    """A valid new-format entry; numbers are copied from the prepared run."""
    day = day or result["date"]
    pct = result["progress"][0]["pct"]
    return f"""# {day} · 결제 요청 API 신설

## 핵심 요약
- 결제 요청 API를 새로 만들고 응답 시간을 줄였습니다.

## 한 일
### 결제 모듈 — 결제 요청 처리 흐름을 새로 구성
- 문제 — 결제 요청을 처리하는 진입점이 없었습니다.
- 한 일 — 요청 처리 흐름을 만들고 흐름 테스트를 추가했습니다.
- 결과 — 응답 시간이 120ms(측정)에서 80ms(측정)로 줄었습니다.

## 진행 상황
| 기능 | 진행률 | 오늘 변화 | 남은 일 |
|---|---|---|---|
| 결제 모듈 | 약 {pct}% | 요청 처리 흐름 구성 | 환불 처리 |

## 다음 할 일
- 환불 처리를 구현합니다.

## 포트폴리오 문장
- 결제 요청 처리 흐름을 새로 만들어 응답 시간을 120ms(측정)에서 80ms(측정)로 줄였습니다.
"""


class WhenTests(unittest.TestCase):
    TODAY = date(2026, 10, 6)

    def when(self, text: str) -> tuple[str, str]:
        start, end = parse_when(text, self.TODAY)
        return start.isoformat(), end.isoformat()

    def test_single_dates(self) -> None:
        self.assertEqual(self.when(""), ("2026-10-06", "2026-10-06"))
        self.assertEqual(self.when("2026-09-29"), ("2026-09-29", "2026-09-29"))
        self.assertEqual(self.when("09-29"), ("2026-09-29", "2026-09-29"))
        self.assertEqual(self.when("9-5"), ("2026-09-05", "2026-09-05"))

    def test_relative_words(self) -> None:
        self.assertEqual(self.when("오늘"), ("2026-10-06", "2026-10-06"))
        self.assertEqual(self.when("어제"), ("2026-10-05", "2026-10-05"))
        self.assertEqual(self.when("그제"), ("2026-10-04", "2026-10-04"))
        self.assertEqual(parse_when("어제", date(2026, 3, 1))[0], date(2026, 2, 28))

    def test_ranges(self) -> None:
        self.assertEqual(self.when("09-28~10-02"), ("2026-09-28", "2026-10-02"))
        self.assertEqual(self.when("2025-12-30~2026-01-02"), ("2025-12-30", "2026-01-02"))
        self.assertEqual(self.when("09-28 ~ 09-28"), ("2026-09-28", "2026-09-28"))

    def test_invalid_is_an_error(self) -> None:
        for bad in ("내일", "2026-13-01", "02-30", "9월 29일", "10-02~09-28", "2026-09-29~", "a~b", "2026/09/29"):
            with self.assertRaises(TaskLogError, msg=bad):
                parse_when(bad, self.TODAY)

    def test_cli_rejects_invalid_date(self) -> None:
        repo = Repo(Path(tempfile.mkdtemp(dir=_TMP.name)), "when")
        repo.profile()
        code, out = run(repo.path, "prepare", "--on", "내일")
        self.assertEqual(code, 3)
        self.assertIn("cannot parse", out["error"])


class CollectScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(tempfile.mkdtemp(dir=_TMP.name))
        cls.repo = Repo(cls.base, "shop")
        cls.shas = build_payments(cls.repo)
        cls.repo.profile()
        cls.code, cls.result = run(cls.repo.path, "prepare", "--on", DAY)
        cls.run_file = cls.repo.run_file()

    def test_prepare_succeeds(self) -> None:
        self.assertEqual(self.code, 0, self.result)
        self.assertTrue(self.result["ok"])
        self.assertEqual((self.result["date"], self.result["key"]), (DAY, "daily"))
        self.assertEqual(self.result["notion_title"], DAY)
        self.assertEqual(self.result["entry_file"], f"{DAY}.md")

    def test_only_my_commits_are_collected(self) -> None:
        self.assertNotIn(self.shas["other"], self.run_file["considered"])
        self.assertIn(self.shas["feat"], self.run_file["considered"])

    def test_minimal_filter_reports_reasons(self) -> None:
        excluded = self.result["counts"]["excluded"]
        self.assertEqual(excluded.get("병합 커밋"), 1)
        self.assertEqual(excluded.get("되돌림 쌍"), 2)
        self.assertEqual(excluded.get("주석만"), 1)
        self.assertEqual(excluded.get("공백만"), 1)
        self.assertEqual(excluded.get("생성·잠금·외부 파일만"), 1)
        self.assertEqual(self.result["counts"]["included"], 4)  # init, feat, test, side helper

    def test_importance_order_and_parts(self) -> None:
        top = self.result["detailed"][0]
        self.assertEqual(top["type"], "feat")
        self.assertEqual(top["score_parts"]["metric"], 10)
        self.assertEqual(top["score_parts"]["new"], 10)
        self.assertEqual(top["feature"], "결제 모듈")
        scores = [d["score"] for d in self.result["detailed"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_metric_carries_both_sides_and_change(self) -> None:
        metric = self.result["metrics"][0]
        self.assertEqual((metric["before"], metric["after"], metric["unit"]), (120.0, 80.0, "ms"))
        self.assertEqual(metric["change_pct"], -33.3)

    def test_progress_estimate_with_basis(self) -> None:
        item = self.result["progress"][0]
        self.assertEqual(item["label"], "추정")
        self.assertIn("마일스톤 1/2", item["basis"])
        self.assertIn("미완 표시 1건", item["basis"])
        self.assertEqual(item["next_milestones"], ["환불 처리"])

    def test_work_item_digest_has_feature_kinds_and_scrubbed_hints(self) -> None:
        item = next(w for w in self.result["work_items"] if w["title"] == "결제 모듈")
        digest = item["digest"]
        self.assertEqual(digest["feature"], "결제 모듈")
        self.assertIn("새 모듈", digest["kinds"])
        self.assertIn("테스트 추가", digest["kinds"])
        self.assertIn("Handle repeated payment requests so retries do not charge twice.", digest["hints"])
        self.assertIn("Create a payment request.", digest["hints"])

    def test_abstracted_output_has_no_internal_names(self) -> None:
        text = json.dumps({k: v for k, v in self.result.items() if k not in {"evidence", "mask"}}, ensure_ascii=False)
        for raw in ("core_pay", "src/payments", "test_pay", "PAY-12", ME, self.shas["feat"][:7], "package-lock"):
            self.assertNotIn(raw, text)


class AuthorDateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(dir=_TMP.name))

    def seoul(self, day: int, hour: int, minute: int, month: int = 9) -> datetime:
        return datetime(2026, month, day, hour, minute, tzinfo=KST)

    def considered(self, repo: Repo, on: str) -> set[str]:
        prepare(repo, on)
        return set(repo.run_file()["considered"])

    def test_day_boundary_follows_the_profile_time_zone(self) -> None:
        repo = Repo(self.base, "edge", start=self.seoul(29, 8, 0))
        repo.profile()
        late = repo.commit("feat: late work", at=self.seoul(29, 23, 30))
        early = repo.commit("feat: after midnight", at=self.seoul(30, 0, 30))  # 15:30 UTC on the 29th
        on29, on30 = self.considered(repo, "2026-09-29"), self.considered(repo, "2026-09-30")
        self.assertIn(late, on29)
        self.assertNotIn(early, on29)
        self.assertEqual(on30, {early})

    def test_author_date_not_committer_date(self) -> None:
        repo = Repo(self.base, "amend", start=self.seoul(29, 8, 0))
        repo.profile()
        sha = repo.commit("feat: worked on the 29th", at=self.seoul(29, 10, 0))
        env = GIT_ENV | {"GIT_COMMITTER_DATE": self.seoul(30, 11, 0).isoformat()}
        repo.git("commit", "-q", "--amend", "--no-edit", "--allow-empty", env=env)
        new = repo.git("rev-parse", "HEAD").strip()
        self.assertNotEqual(sha, new)
        self.assertIn(new, self.considered(repo, "2026-09-29"))
        self.assertNotIn(new, self.considered(repo, "2026-09-30"))

    def test_range_collects_every_day_and_names_files_and_titles(self) -> None:
        repo = Repo(self.base, "span", start=self.seoul(27, 9, 0))
        repo.profile()
        a = repo.commit("feat: a", at=self.seoul(28, 10, 0))
        b = repo.commit("feat: b", at=self.seoul(30, 10, 0))
        c = repo.commit("feat: c", at=self.seoul(10, 10, 0, month=10))
        result = prepare(repo, "09-28~10-02".replace("09-28", "2026-09-28").replace("10-02", "2026-10-02"))
        got = set(repo.run_file()["considered"])
        self.assertTrue({a, b} <= got)
        self.assertNotIn(c, got)
        self.assertEqual((result["date"], result["key"]), ("2026-09-28~2026-10-02", "range"))
        self.assertEqual(result["notion_title"], "0928~1002")
        self.assertEqual(result["entry_file"], "2026-09-28~2026-10-02.md")
        self.assertEqual(result["period"], {"from": "2026-09-28", "to": "2026-10-02"})

    def test_since_until_still_work(self) -> None:
        repo = Repo(self.base, "legacy", start=self.seoul(29, 9, 0))
        repo.profile()
        code, result = run(repo.path, "prepare", "--since", DAY, "--until", DAY)
        self.assertEqual((code, result["date"]), (0, DAY))


class DuplicateAndTypeTests(unittest.TestCase):
    def test_same_change_on_two_branches_counts_once(self) -> None:
        repo = Repo(Path(tempfile.mkdtemp(dir=_TMP.name)), "dup")
        repo.profile()
        repo.git("checkout", "-q", "-b", "copy")
        repo.write("src/payments/core_pay.py", "def pay():\n    return 1\n")
        repo.commit("feat: payment core")
        repo.git("checkout", "-q", "main")
        repo.write("src/payments/core_pay.py", "def pay():\n    return 1\n")
        kept = repo.commit("feat: payment core (rewritten copy)")
        result = prepare(repo)
        self.assertEqual(result["counts"]["excluded"].get("다른 브랜치의 같은 변경"), 1, result["counts"])
        self.assertIn(kept, repo.run_file()["considered"])

    def test_leading_verb_beats_keywords(self) -> None:
        import collect

        self.assertEqual(collect.infer_type("Add exporter, retire safe-patch", [])[0], "feat")
        self.assertEqual(collect.infer_type("Harness: restore missing rules", [])[0], "fix")
        self.assertEqual(collect.infer_type("Clean the series: add caps", [])[0], "refactor")
        self.assertEqual(collect.infer_type("결제 API 추가", [])[0], "feat")


class ProgressFormulaTests(unittest.TestCase):
    def test_milestones_dominate_and_cap(self) -> None:
        full = {"milestones": [3, 3], "paths": True, "commits": 0, "test_files": 0, "todos": 9, "code_files": 1}
        self.assertEqual(progress.estimate(full)[0], 90)
        half = {"milestones": [1, 2], "paths": True, "commits": 10, "test_files": 1, "todos": 0, "code_files": 1}
        self.assertEqual(progress.estimate(half)[0], 65)

    def test_without_milestones_caps_at_85(self) -> None:
        best = {"milestones": [0, 0], "paths": True, "commits": 50, "test_files": 3, "todos": 0, "code_files": 9}
        pct, basis = progress.estimate(best)
        self.assertEqual(pct, 85)
        self.assertIn("마일스톤 없음", basis)


class RedactGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = parse_profile(PROFILE)
        self.profile.private_terms = ["고객사A"]
        self.profile.repo_terms = ["core-pay"]

    def test_scrub_masks_identifiers_even_with_korean_particles(self) -> None:
        text = ("fix parse_args를 src/auth/login.py에서 고침, see https://jira.corp.local/X-1 by a@b.io "
                "on 10.0.0.12 with DATABASE_URL and token=abc123 PAY-77 #42 deadbeef1 for 고객사A in core-pay")
        out = redact.scrub(text, self.profile)
        for raw in ("parse_args", "src/auth", "login.py", "https", "a@b.io", "10.0.0.12", "DATABASE_URL",
                    "abc123", "PAY-77", "#42", "deadbeef1", "고객사A", "core-pay"):
            self.assertNotIn(raw, out)

    def test_gate_allows_common_terms(self) -> None:
        text = "CI/CD와 UTF-8, Node.js, GitHub, 마일스톤 3/5, 120ms → 80ms, 2026-10-05"
        self.assertEqual(redact.findings(text, self.profile), [])

    def test_gate_blocks_leaks(self) -> None:
        for leak in ("config.yaml을 고쳤습니다", "보고서.docx", "src/payments", "me@example.com", "https://x.dev",
                     "192.168.0.1", "ghp_" + "a" * 36, "API_KEY", "PROJ-12", "abc1234", "get_user", "getUserById",
                     ".env", "고객사A", "core-pay"):
            kinds = [h["kind"] for h in redact.findings(f"내용 {leak} 끝", self.profile)]
            self.assertTrue(kinds, leak)


class GateTests(unittest.TestCase):
    RUN = {"metrics": [{"before": 120.0, "after": 80.0, "change_pct": -33.3}],
           "progress": [{"feature": "결제 모듈", "pct": 65, "prev": 50}]}
    RESULT = {"date": DAY, "progress": [{"pct": 65}]}

    def entry(self, *swaps: tuple[str, str]) -> str:
        text = entry_for(self.RESULT)
        for old, new in swaps:
            self.assertIn(old, text)
            text = text.replace(old, new)
        return text

    def tokens(self, text: str, profile=None) -> list[str]:
        result = gate.check(text, profile or parse_profile(PROFILE), self.RUN)
        return [b["token"] for b in result["blocked"]]

    def blocked(self, token: str, *swaps: tuple[str, str]) -> None:
        self.assertIn(token, self.tokens(self.entry(*swaps)), swaps)

    def test_valid_new_format_entry_passes(self) -> None:
        self.assertEqual(self.tokens(self.entry()), [])
        self.assertEqual(self.tokens(self.entry(("# 2026-09-29 ·", "# 2026-09-28~2026-09-29 ·"))), [])

    def test_progress_section_only_required_with_features(self) -> None:
        no_progress = self.entry().split("## 진행 상황")[0] + "## 포트폴리오 문장" + self.entry().split("## 포트폴리오 문장")[1]
        self.assertIn("section", self.tokens(no_progress))
        bare = parse_profile(PROFILE.split("## 기능")[0])
        self.assertEqual(self.tokens(no_progress, bare), [])

    def test_each_hedging_phrase_blocks(self) -> None:
        for phrase in ("것으로 보입니다", "것 같습니다", "로 보입니다", "추정됩니다", "듯합니다", "것으로 판단됩니다"):
            self.blocked("hedging", ("- 환불 처리를 구현합니다.", f"- 환불 처리가 필요한 {phrase}."))

    def test_each_count_phrase_blocks(self) -> None:
        for phrase in ("커밋 3건", "파일 12개", "1,006줄 추가", "40줄 삭제", "5건 반영", "변경 7"):
            self.blocked("count", ("- 환불 처리를 구현합니다.", f"- 이번에는 {phrase}을 했습니다."))

    def test_bracket_labels_block(self) -> None:
        for label in ("측정", "판단", "전달", "가정", "미확인"):
            self.blocked("label", ("- 환불 처리를 구현합니다.", f"- 환불 처리를 구현합니다 [{label}]"))

    def test_html_comment_and_metadata_block(self) -> None:
        self.blocked("comment", ("# 2026-09-29 · 결제 요청 API 신설", "# 2026-09-29 · 결제 요청 API 신설\n<!-- task-log:begin -->"))

    def test_placeholders_block(self) -> None:
        for bad in ("{{기능}}", "TBD", "TODO", "[확인 필요]", "N건"):
            self.blocked("placeholder", ("- 환불 처리를 구현합니다.", f"- {bad}"))
        self.blocked("placeholder", ("- 환불 처리를 구현합니다.", "- …"))
        self.blocked("placeholder", ("- 결과 — 응답 시간이 120ms(측정)에서 80ms(측정)로 줄었습니다.", "- 결과 — …"))

    def test_measured_number_must_come_from_the_run(self) -> None:
        self.blocked("measured", ("120ms(측정)에서 80ms(측정)로 줄었습니다", "120ms(측정)에서 95ms(측정)로 줄었습니다"))
        self.assertEqual(self.tokens(self.entry(("줄였습니다.\n\n## 한 일", "줄였습니다. 33.3%(측정) 단축했습니다.\n\n## 한 일"))), [])

    def test_percentage_must_be_in_progress_or_metrics(self) -> None:
        self.blocked("percent", ("약 65%", "약 99%"))
        self.blocked("percent", ("- 결제 요청 API를 새로 만들고", "- 성공률 97%로 결제 요청 API를 새로 만들고"))
        self.assertEqual(self.tokens(self.entry(("약 65%", "약 50%"))), [])  # previous value is allowed

    def test_missing_portfolio_sentence_blocks(self) -> None:
        text = self.entry().split("## 포트폴리오 문장")[0]
        self.assertIn("section", self.tokens(text))

    def test_missing_or_duplicate_result_field_blocks(self) -> None:
        self.blocked("field", ("- 결과 — 응답 시간이 120ms(측정)에서 80ms(측정)로 줄었습니다.\n", ""))
        self.blocked("field", ("- 결과 — 응답", "- 결과 — 응답 시간입니다.\n- 결과 — 응답"))

    def test_wrong_field_order_blocks(self) -> None:
        self.blocked("field", ("- 문제 — 결제 요청을 처리하는 진입점이 없었습니다.\n", ""),
                     ("- 결과 —", "- 문제 — 결제 요청을 처리하는 진입점이 없었습니다.\n- 결과 —"))

    def test_wrong_section_order_blocks(self) -> None:
        text = self.entry()
        moved = text.replace("## 다음 할 일\n- 환불 처리를 구현합니다.\n\n", "").replace(
            "## 한 일", "## 다음 할 일\n- 환불 처리를 구현합니다.\n\n## 한 일")
        self.assertIn("section", self.tokens(moved))
        self.assertIn("section", self.tokens(text + "\n## 한눈에 보기\n- x\n"))

    def test_title_format_is_required(self) -> None:
        self.blocked("title", ("# 2026-09-29 · 결제 요청 API 신설", "# 2026-09-29 작업 기록"))

    def test_old_format_is_rejected(self) -> None:
        self.assertIn("section", self.tokens("# 2026-09-29 작업 기록\n\n## 한눈에 보기\n- 날짜 — 2026-09-29\n"))

    def test_leak_in_entry_blocks(self) -> None:
        result = gate.check(self.entry(("진입점이", "core_pay.py 진입점이")), parse_profile(PROFILE), self.RUN)
        self.assertIn("filename", [b["kind"] for b in result["blocked"]])

    def test_portfolio_kind_checks_wording_only(self) -> None:
        text = "# 포트폴리오\n\n- 결제 요청을 처리했습니다. 커밋 3건 [측정]\n"
        tokens = [b["token"] for b in gate.check(text, parse_profile(PROFILE), None, "portfolio")["blocked"]]
        self.assertIn("count", tokens)
        self.assertIn("label", tokens)
        self.assertNotIn("section", tokens)


class WriteIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(dir=_TMP.name))

    def prepared(self, name: str) -> tuple[Repo, dict]:
        repo = Repo(self.base, name)
        build_payments(repo)
        repo.profile()
        return repo, prepare(repo)

    def draft(self, repo: Repo, text: str) -> Path:
        entry = repo.path / ".claude/log-part/.draft.md"
        entry.write_text(text, encoding="utf-8")
        return entry

    def test_write_is_idempotent_and_rerun_updates_the_same_entry(self) -> None:
        repo, result = self.prepared("shop")
        entry = self.draft(repo, entry_for(result))
        code, first = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual((code, first["status"]), (0, "written"), first)
        day_file = repo.path / f".claude/log-part/{DAY}.md"
        self.assertEqual(run(repo.path, "write", "--entry", str(entry))[1]["status"], "unchanged")
        again = prepare(repo)
        self.assertEqual(again["evidence"]["fingerprint"], result["evidence"]["fingerprint"])
        self.assertTrue(again["previous_block"])
        self.assertEqual(run(repo.path, "write", "--entry", str(entry))[1]["status"], "unchanged")
        repo.write("src/payments/refund.py", "def refund():\n    return 0\n")
        repo.commit("feat(payments): implement refund")
        merged = prepare(repo)
        self.assertNotEqual(merged["evidence"]["fingerprint"], result["evidence"]["fingerprint"])
        self.assertEqual(merged["counts"]["included"], result["counts"]["included"] + 1)
        entry = self.draft(repo, entry_for(merged))
        code, third = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual((third["status"], Path(third["file"]).resolve()), ("written", day_file.resolve()))
        self.assertEqual(sorted(p.name for p in day_file.parent.glob("2026-*.md")), [f"{DAY}.md"])
        self.assertEqual(run(repo.path, "write", "--entry", str(entry))[1]["status"], "unchanged")
        self.assertTrue((repo.path / ".claude/log-part/index.md").is_file())

    def test_entry_file_has_no_metadata_and_fingerprint_lives_in_state_and_run(self) -> None:
        repo, result = self.prepared("shop")
        run(repo.path, "write", "--entry", str(self.draft(repo, entry_for(result))))
        text = (repo.path / f".claude/log-part/{DAY}.md").read_text(encoding="utf-8")
        fp = result["evidence"]["fingerprint"]
        for banned in ("<!--", "sha256", fp, "task-log:", "수집 시점"):
            self.assertNotIn(banned, text)
        self.assertTrue(text.startswith(f"# {DAY} · 결제 요청 API 신설"))
        self.assertEqual(repo.run_file()["fingerprint"], fp)
        self.assertEqual(repo.state()["days"][DAY]["blocks"]["daily"]["fingerprint"], fp)
        self.assertEqual(repo.state()["days"][DAY]["blocks"]["daily"]["headline"], "결제 요청 API 신설")

    def test_range_entry_is_written_under_the_range_name(self) -> None:
        repo, _ = self.prepared("shop")
        result = prepare(repo, f"{DAY}~2026-10-02")
        entry = self.draft(repo, entry_for(result))
        code, out = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(code, 0, out)
        self.assertTrue((repo.path / f".claude/log-part/{DAY}~2026-10-02.md").is_file())

    def test_entry_date_must_match_the_prepared_run(self) -> None:
        repo, result = self.prepared("shop")
        entry = self.draft(repo, entry_for(result, day="2026-09-28"))
        code, out = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(code, 3)
        self.assertIn("does not match", out["error"])
        self.assertFalse((repo.path / ".claude/log-part/2026-09-28.md").exists())

    def test_blocked_entry_writes_nothing(self) -> None:
        repo, result = self.prepared("shop")
        entry = self.draft(repo, entry_for(result).replace("결제 요청 처리 흐름을 새로 구성", "core_pay.py 흐름"))
        code, out = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(code, 2)
        self.assertFalse((repo.path / f".claude/log-part/{DAY}.md").exists())

    def test_gate_command_uses_the_run(self) -> None:
        repo, result = self.prepared("shop")
        entry = self.draft(repo, entry_for(result).replace("80ms(측정)로 줄었습니다.", "95ms(측정)로 줄었습니다."))
        code, out = run(repo.path, "gate", "--entry", str(entry))
        self.assertEqual(code, 2)
        self.assertIn("measured", [b["token"] for b in out["blocked"]])

    def test_past_date_can_be_rewritten_without_a_flag(self) -> None:
        repo, result = self.prepared("shop")
        entry = self.draft(repo, entry_for(result))
        self.assertEqual(run(repo.path, "write", "--entry", str(entry))[1]["status"], "written")
        entry = self.draft(repo, entry_for(result).replace("새로 만들고", "처음 만들고"))
        self.assertEqual(run(repo.path, "write", "--entry", str(entry))[1]["status"], "written")

    def test_two_projects_keep_separate_state(self) -> None:
        a, result_a = self.prepared("alpha")
        b, result_b = self.prepared("beta")
        for repo, result in ((a, result_a), (b, result_b)):
            self.assertEqual(run(repo.path, "write", "--entry", str(self.draft(repo, entry_for(result))))[0], 0)
        state_a, state_b = a.state(), b.state()
        self.assertNotEqual(state_a["project"]["remote_hash"], state_b["project"]["remote_hash"])
        self.assertFalse(set(state_a["processed"]) & set(state_b["processed"]))
        self.assertEqual(result_a["project"], "alpha")
        self.assertEqual(result_b["project"], "beta")
        self.assertFalse((_HOME / ".claude").exists())

    def test_log_part_copied_from_another_project_is_rejected(self) -> None:
        a, result = self.prepared("alpha")
        run(a.path, "write", "--entry", str(self.draft(a, entry_for(result))))
        b = Repo(self.base, "beta")
        shutil.copytree(a.path / ".claude", b.path / ".claude")
        code, out = run(b.path, "prepare")
        self.assertEqual(code, 3)
        self.assertIn("another project", out["error"])

    def test_moved_project_needs_rebind(self) -> None:
        a, result = self.prepared("alpha")
        run(a.path, "write", "--entry", str(self.draft(a, entry_for(result))))
        moved = self.base / "alpha-moved"
        a.path.rename(moved)
        code, out = run(moved, "prepare")
        self.assertEqual(code, 3)
        self.assertEqual(run(moved, "rebind")[1]["status"], "rebound")
        self.assertEqual(run(moved, "prepare")[0], 0)

    def test_notion_set_records_day_ids(self) -> None:
        repo, result = self.prepared("shop")
        code, out = run(repo.path, "notion-set", "--kind", "day", "--id", "abc", "--date", DAY, "--title", DAY)
        self.assertEqual((code, out["status"]), (0, "recorded"))
        self.assertEqual(repo.state()["notion"]["days"][DAY]["id"], "abc")


class KoreanCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(dir=_TMP.name))
        self.repo = Repo(self.base, "kr")
        self.repo.profile()
        result = prepare(self.repo)
        self.entry = self.repo.path / ".claude/log-part/.draft.md"
        self.entry.write_text(entry_for(result), encoding="utf-8")

    def test_runs_check_revision_in_draft_mode_when_found(self) -> None:
        if not (KOREAN_SKILL / "scripts/check_revision.py").is_file():
            self.skipTest("clonamic-korean is not next to this plugin")
        env = GIT_ENV | {"CLONAMIC_KOREAN_ROOT": str(KOREAN_SKILL)}
        code, out = run(self.repo.path, "korean", "--entry", str(self.entry), env=env)
        self.assertTrue(out["found"])
        self.assertEqual(out["path"], str(KOREAN_SKILL / "scripts/check_revision.py"))
        self.assertEqual(code, out["exit_code"])
        self.assertIn(code, (0, 1))
        self.assertIsInstance(out["report"], dict)

    def test_without_entry_only_locates(self) -> None:
        if not (KOREAN_SKILL / "scripts/check_revision.py").is_file():
            self.skipTest("clonamic-korean is not next to this plugin")
        code, out = run(self.repo.path, "korean", env=GIT_ENV | {"CLONAMIC_KOREAN_ROOT": str(KOREAN_SKILL)})
        self.assertEqual((code, out["found"]), (0, True))
        self.assertTrue(out["path"].endswith("check_revision.py"))
        code, out = run(self.repo.path, "korean")
        self.assertEqual((code, out["found"]), (4, False))

    def test_exit_2_is_propagated(self) -> None:
        if not (KOREAN_SKILL / "scripts/check_revision.py").is_file():
            self.skipTest("clonamic-korean is not next to this plugin")
        self.entry.write_text("", encoding="utf-8")  # empty_output is a violation
        env = GIT_ENV | {"CLONAMIC_KOREAN_ROOT": str(KOREAN_SKILL)}
        code, out = run(self.repo.path, "korean", "--entry", str(self.entry), env=env)
        self.assertEqual((code, out["exit_code"]), (2, 2), out)

    def test_not_found_returns_install_commands_and_exit_4(self) -> None:
        empty = self.base / "empty"
        empty.mkdir()
        for env in (GIT_ENV | {"CLONAMIC_KOREAN_ROOT": str(empty)}, GIT_ENV):  # override miss, then isolated HOME
            code, out = run(self.repo.path, "korean", "--entry", str(self.entry), env=env)
            self.assertEqual(code, 4)
            self.assertFalse(out["found"])
            self.assertEqual(set(out["install"]), {"claude", "codex", "cursor", "grok"})
            self.assertEqual(out["install"]["claude"], ["claude plugin marketplace add clonamic/plugin",
                                                        "claude plugin install clonamic-korean@clonamic"])
            self.assertEqual(out["install"]["codex"][1], "codex plugin add clonamic-korean@clonamic")
            self.assertIn("~/.cursor/plugins/local/clonamic-korean", out["install"]["cursor"][0])
            self.assertEqual(out["install"]["grok"][1], "grok plugin enable clonamic-korean")

    def test_finds_an_installed_copy_under_home(self) -> None:
        home = self.base / "home2"
        script = home / ".claude/plugins/cache/clonamic/clonamic-korean/1.0.0/skills/clonamic-korean/scripts/check_revision.py"
        script.parent.mkdir(parents=True)
        script.write_text("import json, sys\nprint(json.dumps({'ok': True}))\n", encoding="utf-8")
        code, out = run(self.repo.path, "korean", "--entry", str(self.entry), env=GIT_ENV | {"HOME": str(home)})
        self.assertEqual((code, out["found"], out["report"]), (0, True, {"ok": True}))


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(dir=_TMP.name))

    def test_outside_repo_fails(self) -> None:
        code, out = run(self.base, "preflight")
        self.assertEqual(code, 1)
        self.assertIn("repository", [c["name"] for c in out["checks"] if not c["ok"]])

    def test_agent_dir_must_be_ignored_and_never_auto_fixed(self) -> None:
        repo = Repo(self.base, "plain")
        (repo.path / ".gitignore").write_text("", encoding="utf-8")
        code, out = run(repo.path, "preflight")
        self.assertEqual(code, 1)
        failed = {c["name"]: c for c in out["checks"] if not c["ok"]}
        self.assertIn("agent-dir-ignored", failed)
        self.assertIn(".claude/", failed["agent-dir-ignored"]["fix"])
        self.assertEqual((repo.path / ".gitignore").read_text(encoding="utf-8"), "")

    def test_first_run_defaults(self) -> None:
        repo = Repo(self.base, "fresh")
        repo.write("src/search/index.py", "x = 1\n")
        repo.commit("feat: search index")
        repo.git("tag", "sprint-1")
        code, out = run(repo.path, "preflight")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["first_run"])
        self.assertEqual(out["defaults"]["identities"], [ME])
        self.assertEqual(out["defaults"]["notion_path"], "개인 페이지 / fresh / 작업로그")
        self.assertEqual(out["defaults"]["work_unit_candidates"][0]["basis"], "태그 sprint-*")
        self.assertEqual(out["defaults"]["feature_candidates"][0]["path"], "src/search")


class SaveCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(dir=_TMP.name))

    def _save(self, repo: Path, name: str, text: str) -> tuple[int, dict]:
        proc = subprocess.run([sys.executable, str(TASKLOG), "--repo", str(repo), "--agent-dir", ".claude",
                               "save", "--name", name], input=text, capture_output=True, text=True,
                              env=GIT_ENV | {"PYTHONDONTWRITEBYTECODE": "1"})
        return proc.returncode, json.loads(proc.stdout) if proc.stdout.strip() else {}

    def test_save_writes_setup_files_into_log_part(self) -> None:
        repo = Repo(self.base, "saver")
        code, out = self._save(repo.path, "notion.md", "# Notion\n- 루트 — 작업로그\n")
        self.assertEqual(code, 0, out)
        self.assertEqual((repo.path / ".claude/log-part/notion.md").read_text(encoding="utf-8"),
                         "# Notion\n- 루트 — 작업로그\n")

    def test_save_rejects_other_names_and_empty_input(self) -> None:
        repo = Repo(self.base, "saver2")
        proc = subprocess.run([sys.executable, str(TASKLOG), "--repo", str(repo.path), "save", "--name", "state.json"],
                              input="{}", capture_output=True, text=True, env=GIT_ENV)
        self.assertNotEqual(proc.returncode, 0)
        code, out = self._save(repo.path, "profile.md", "   \n")
        self.assertEqual(code, 3)
        self.assertFalse((repo.path / ".claude/log-part/profile.md").exists())


class WorkItemTotalsTests(unittest.TestCase):
    def test_totals_are_precomputed_per_work_item(self) -> None:
        sys.path.insert(0, str(TASKLOG.parent))
        import redact
        detailed = [
            {"rank": 1, "score": 70, "type_ko": "기능", "feature": "결제", "cross_cutting": False, "areas": ["결제"],
             "files": {"added": 2, "modified": 1, "deleted": 0}, "lines": {"added": 40, "deleted": 5}, "tests_added": True},
            {"rank": 2, "score": 50, "type_ko": "수정", "feature": "결제", "cross_cutting": False, "areas": ["결제"],
             "files": {"added": 0, "modified": 3, "deleted": 1}, "lines": {"added": 10, "deleted": 20}, "tests_added": False},
        ]
        [item] = redact.work_items(detailed)
        self.assertEqual(item["totals"], {"commits": 2, "files_added": 2, "files_modified": 4, "files_deleted": 1,
                                          "lines_added": 50, "lines_deleted": 25, "commits_with_tests": 1})
