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
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True

import gate  # noqa: E402
import progress  # noqa: E402
import redact  # noqa: E402
from common import parse_profile  # noqa: E402

ME = "me@example.com"
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


def tearDownModule() -> None:
    _TMP.cleanup()


def now_iso(offset_minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)).isoformat(timespec="seconds")


class Repo:
    def __init__(self, base: Path, name: str, remote: str | None = None) -> None:
        self.path = base / name
        self.path.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", ME)
        self.git("config", "user.name", "Me")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", remote or f"git@github.com:me/{name}.git")
        self.write(".gitignore", ".claude/\n")
        self.write("README.md", f"# {name}\n")  # distinct history per project
        self.minutes = 300
        self.commit("chore: init", who=("Me", ME))

    def git(self, *args: str, env: dict | None = None) -> str:
        return subprocess.run(["git", "-C", str(self.path), *args], check=True, capture_output=True, text=True,
                              env=env or GIT_ENV).stdout

    def write(self, rel: str, text: str) -> None:
        path = self.path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str, who: tuple[str, str] = ("Me", ME)) -> str:
        self.minutes -= 5
        stamp = now_iso(self.minutes)
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


def run(repo: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(TASKLOG), "--repo", str(repo), "--agent-dir", ".claude", *args],
                          capture_output=True, text=True, env=GIT_ENV | {"PYTHONDONTWRITEBYTECODE": "1"})
    return proc.returncode, json.loads(proc.stdout)


def build_payments(repo: Repo) -> dict[str, str]:
    shas = {}
    repo.write("src/payments/core_pay.py", "def pay(amount):\n    return amount\n")
    repo.write("src/payments/refund.py", "def refund():\n    raise NotImplementedError\n")
    shas["feat"] = repo.commit("feat(payments): add payment request API (latency 120ms -> 80ms)")
    repo.write("tests/test_pay.py", "def test_pay():\n    assert True\n")
    shas["test"] = repo.commit("test: cover payment flow PAY-12")
    repo.write("src/payments/core_pay.py", "def pay(amount):\n    # keep amounts in cents\n    return amount\n")
    shas["comment"] = repo.commit("chore: explain units")
    repo.write("src/payments/core_pay.py", "def pay(amount):\n    # keep amounts in cents\n    return  amount\n\n")
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
    repo.git("merge", "-q", "--no-ff", "side", "-m", "Merge branch side", env=GIT_ENV | {
        "GIT_AUTHOR_DATE": now_iso(1), "GIT_COMMITTER_DATE": now_iso(1)})
    return shas


def entry_for(result: dict) -> str:
    fp = result["evidence"]["fingerprint"]
    day = result["date"]
    return f"""# {day} 작업 기록

## 한눈에 보기
- 날짜 — {day}
- 파트 — 백엔드 개발
- 핵심 성과 — 결제 요청 API를 새로 만들고 응답 시간을 줄였습니다 [측정]

## 작업 상세

### 결제 모듈
- 목표 — 결제 요청을 처리하는 첫 API를 만들었습니다.
- 실행 — 결제 모듈을 새로 구성하고 흐름 테스트를 추가했습니다.
- 결과 — 결제 요청 API와 테스트가 생겼습니다 [측정] 새 코드 파일 2개
- 근거 — 근거 수준 A, 기능 커밋 2건 [측정]

## 검증·측정 결과
- [측정] 결제 요청 응답 시간 120ms → 80ms (33.3% 단축)

## 근거·신뢰도
- 근거 수준 — A: git 저자 일치 커밋
- 수집 범위 — 커밋 {result['counts']['collected']}건 중 {result['counts']['included']}건 반영 [측정]
- 수집 시점 — {result['evidence']['collected_at']}
- 증거 지문 — {fp}
"""


class CollectScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(tempfile.mkdtemp(dir=_TMP.name))
        cls.repo = Repo(cls.base, "shop")
        cls.shas = build_payments(cls.repo)
        cls.repo.profile()
        cls.code, cls.result = run(cls.repo.path, "prepare")
        cls.run_file = json.loads((cls.repo.path / ".claude/log-part/.run.json").read_text(encoding="utf-8"))

    def test_prepare_succeeds(self) -> None:
        self.assertEqual(self.code, 0, self.result)
        self.assertTrue(self.result["ok"])

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

    def test_abstracted_output_has_no_internal_names(self) -> None:
        text = json.dumps({k: v for k, v in self.result.items() if k not in {"evidence", "mask"}}, ensure_ascii=False)
        for raw in ("core_pay", "src/payments", "test_pay", "PAY-12", ME, self.shas["feat"][:7], "package-lock"):
            self.assertNotIn(raw, text)


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
        code, result = run(repo.path, "prepare")
        self.assertEqual(result["counts"]["excluded"].get("다른 브랜치의 같은 변경"), 1, result["counts"])
        run_file = json.loads((repo.path / ".claude/log-part/.run.json").read_text(encoding="utf-8"))
        self.assertIn(kept, run_file["considered"])

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


class EntryContractTests(unittest.TestCase):
    FP = "sha256:" + "a" * 64

    def entry(self, **swap: str) -> str:
        text = entry_for({"evidence": {"fingerprint": self.FP, "collected_at": "2026-10-05T09:00:00+09:00"},
                          "date": "2026-10-05", "counts": {"collected": 3, "included": 2}})
        for old, new in swap.items():
            text = text.replace(old.replace("_", " "), new)
        return text

    def kinds(self, text: str) -> list[str]:
        return [b["token"] for b in gate.check(text, parse_profile(PROFILE), self.FP)["blocked"]]

    def test_valid_entry_passes(self) -> None:
        self.assertEqual(gate.check(self.entry(), parse_profile(PROFILE), self.FP)["blocked"], [])

    def test_unlabeled_number_blocks(self) -> None:
        self.assertIn("unlabeled", self.kinds(self.entry(**{"새 코드 파일 2개": "", "기능 커밋 2건 [측정]": "기능 커밋 2건"})))

    def test_unknown_label_and_placeholder_block(self) -> None:
        self.assertIn("label", self.kinds(self.entry(**{"[측정] 결제": "[추측] 결제"})))
        self.assertIn("placeholder", self.kinds(self.entry(**{"첫 API를": "{{기능}}을"})))

    def test_structure_rules(self) -> None:
        moved = self.entry().replace("## 한눈에 보기", "## 목표·맥락\n- 작업 목적 — 결제\n\n## 한눈에 보기")
        self.assertIn("section", self.kinds(moved))
        self.assertIn("field", self.kinds(self.entry(**{"- 결과 — ": "- 산출 — "})))
        self.assertIn("fingerprint", self.kinds(self.entry().replace(self.FP, "sha256:" + "b" * 64)))


class WriteIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(dir=_TMP.name))

    def prepared(self, name: str) -> tuple[Repo, dict]:
        repo = Repo(self.base, name)
        build_payments(repo)
        repo.profile()
        code, result = run(repo.path, "prepare")
        self.assertEqual(code, 0, result)
        return repo, result

    def test_write_is_idempotent_and_merges_same_day(self) -> None:
        repo, result = self.prepared("shop")
        entry = repo.path / ".claude/log-part/.draft.md"
        entry.write_text(entry_for(result), encoding="utf-8")
        code, first = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual((code, first["status"]), (0, "written"), first)
        day_file = repo.path / f".claude/log-part/{result['date']}.md"
        day_file.write_text(day_file.read_text(encoding="utf-8") + "\n내가 직접 쓴 메모\n", encoding="utf-8")
        code, second = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(second["status"], "unchanged")
        code, again = run(repo.path, "prepare")
        self.assertEqual(again["evidence"]["fingerprint"], result["evidence"]["fingerprint"])
        self.assertTrue(again["previous_block"])
        repo.write("src/payments/refund.py", "def refund():\n    return 0\n")
        repo.commit("feat(payments): implement refund")
        code, merged = run(repo.path, "prepare")
        self.assertNotEqual(merged["evidence"]["fingerprint"], result["evidence"]["fingerprint"])
        self.assertEqual(merged["counts"]["included"], result["counts"]["included"] + 1)
        entry.write_text(entry_for(merged), encoding="utf-8")
        code, third = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(third["status"], "written")
        text = day_file.read_text(encoding="utf-8")
        self.assertEqual(text.count("task-log:begin key=daily"), 1)
        self.assertIn("내가 직접 쓴 메모", text)
        state = json.loads((repo.path / ".claude/log-part/state.json").read_text(encoding="utf-8"))
        self.assertIn("main", state["cursors"])
        self.assertTrue((repo.path / ".claude/log-part/index.md").is_file())

    def test_blocked_entry_writes_nothing(self) -> None:
        repo, result = self.prepared("shop")
        entry = repo.path / ".claude/log-part/.draft.md"
        entry.write_text(entry_for(result).replace("첫 API를", "core_pay.py API를"), encoding="utf-8")
        code, out = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(code, 2)
        self.assertFalse((repo.path / f".claude/log-part/{result['date']}.md").exists())

    def test_past_date_is_not_overwritten(self) -> None:
        repo, _ = self.prepared("shop")
        past = (date.today() - timedelta(days=3)).isoformat()
        code, result = run(repo.path, "prepare", "--date", past, "--since", past)
        entry = repo.path / ".claude/log-part/.draft.md"
        entry.write_text(entry_for(result), encoding="utf-8")
        self.assertEqual(run(repo.path, "write", "--entry", str(entry))[1]["status"], "written")
        entry.write_text(entry_for(result).replace("새로 만들고", "처음 만들고"), encoding="utf-8")
        code, out = run(repo.path, "write", "--entry", str(entry))
        self.assertEqual(code, 3)
        self.assertIn("past dates", out["error"])
        code, out = run(repo.path, "write", "--entry", str(entry), "--replace-past")
        self.assertEqual(out["status"], "written")

    def test_two_projects_keep_separate_state(self) -> None:
        a, result_a = self.prepared("alpha")
        b, result_b = self.prepared("beta")
        for repo, result in ((a, result_a), (b, result_b)):
            entry = repo.path / ".claude/log-part/.draft.md"
            entry.write_text(entry_for(result), encoding="utf-8")
            self.assertEqual(run(repo.path, "write", "--entry", str(entry))[0], 0)
        state_a = json.loads((a.path / ".claude/log-part/state.json").read_text(encoding="utf-8"))
        state_b = json.loads((b.path / ".claude/log-part/state.json").read_text(encoding="utf-8"))
        self.assertNotEqual(state_a["project"]["remote_hash"], state_b["project"]["remote_hash"])
        self.assertFalse(set(state_a["processed"]) & set(state_b["processed"]))
        self.assertEqual(result_a["project"], "alpha")
        self.assertEqual(result_b["project"], "beta")
        self.assertFalse((_HOME / ".claude").exists())

    def test_log_part_copied_from_another_project_is_rejected(self) -> None:
        a, result = self.prepared("alpha")
        entry = a.path / ".claude/log-part/.draft.md"
        entry.write_text(entry_for(result), encoding="utf-8")
        run(a.path, "write", "--entry", str(entry))
        b = Repo(self.base, "beta")
        shutil.copytree(a.path / ".claude", b.path / ".claude")
        code, out = run(b.path, "prepare")
        self.assertEqual(code, 3)
        self.assertIn("another project", out["error"])

    def test_moved_project_needs_rebind(self) -> None:
        a, result = self.prepared("alpha")
        entry = a.path / ".claude/log-part/.draft.md"
        entry.write_text(entry_for(result), encoding="utf-8")
        run(a.path, "write", "--entry", str(entry))
        moved = self.base / "alpha-moved"
        a.path.rename(moved)
        code, out = run(moved, "prepare")
        self.assertEqual(code, 3)
        self.assertEqual(run(moved, "rebind")[1]["status"], "rebound")
        self.assertEqual(run(moved, "prepare")[0], 0)


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


if __name__ == "__main__":
    unittest.main()


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
