"""Prerequisite checks and first-run defaults. Never edits .gitignore or any project file."""

from __future__ import annotations

import re
import os
import shutil
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path, PurePosixPath

from common import TaskLogError, git, git_ok, log_dir, repo_name

CONTAINER_DIRS = {"src", "lib", "app", "apps", "packages", "pkg", "internal", "source", "services", "modules", "plugin", "plugins"}
SPRINT_RE = re.compile(r"(?i)^(?:.*/)?((?:sprint|iteration|iter|milestone|week|wk)[-_]?)\d+$")
RELEASE_RE = re.compile(r"^(v?)\d+\.\d+(?:\.\d+)?$")


def check(name: str, ok: bool, detail: str, fix: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": "" if ok else fix}


HOST_NAMES = {".claude": "Claude Code", ".codex": "Codex", ".cursor": "Cursor", ".grok": "Grok"}


def write_fix(agent_dir: str, repo: Path, logs: Path) -> str:
    """Host-specific, human-applied fix. Nothing here edits any host config."""
    top = Path(agent_dir).name if Path(agent_dir).is_absolute() else Path(agent_dir).parts[0]
    host = HOST_NAMES.get(top, "")
    if host == "Claude Code":
        return (f"Claude Code가 {top}/ 쓰기를 막고 있습니다. 설정에서 Edit({top}/log-part/**) 를 허용하거나, "
                "쓰기 확인창이 뜨면 승인하세요. 설정은 자동으로 고치지 않습니다.")
    if host == "Codex":
        return (f"Codex 샌드박스가 {top}/ 쓰기를 막고 있습니다. 이 세션에만 적용되는 옵션으로 다시 실행하세요: "
                f"codex -c 'sandbox_workspace_write.writable_roots=[\"{repo}/{top}\"]' "
                "(대화형이면 CLI 쓰기 명령의 권한 상승 요청을 승인해도 됩니다). 설정 파일은 자동으로 고치지 않습니다.")
    if host:
        return f"{host}가 {logs} 쓰기를 막고 있습니다. 쓰기 확인창이 뜨면 승인하세요. 설정은 자동으로 고치지 않습니다."
    return f"{logs} 에 쓸 수 없습니다. 폴더 권한을 확인하거나 호스트의 쓰기 확인창을 승인하세요."


def probe_writable(logs: Path) -> str:
    """Create and remove a probe file inside log-part (the only place the CLI writes). Returns '' or the error."""
    probe = logs / f".write-probe-{os.getpid()}"
    try:
        logs.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return f"{type(exc).__name__}: {exc.strerror or exc}"
    return ""


def run_checks(start: Path, agent_dir: str) -> tuple[list[dict], Path | None]:
    checks = [check("python", sys.version_info >= (3, 12), sys.version.split()[0], "uv python install 3.12")]
    if not shutil.which("git"):
        checks.append(check("git", False, "git not found", "git을 설치하세요(macOS: xcode-select --install, 그 밖: OS 패키지 관리자)."))
        return checks, None
    checks.append(check("git", True, "found"))
    if not git_ok(start, "rev-parse", "--show-toplevel"):
        checks.append(check("repository", False, "not inside a git repository", "기록할 프로젝트 폴더(git 저장소) 안에서 실행하세요."))
        return checks, None
    repo = Path(git(start, "rev-parse", "--show-toplevel").strip())
    checks.append(check("repository", True, repo.name))
    remotes = git(repo, "remote", check=False).split()
    checks.append(check("remote", bool(remotes), ", ".join(remotes) or "none",
                        "원격 저장소를 연결하세요: git remote add origin <원격 주소>"))
    name = git(repo, "config", "user.name", check=False).strip()
    email = git(repo, "config", "user.email", check=False).strip()
    checks.append(check("identity", bool(name and email), "set" if name and email else "missing",
                        'git config user.name "이름" && git config user.email "메일" 로 커밋 신원을 설정하세요.'))
    logs = log_dir(repo, agent_dir)
    try:
        rel = logs.resolve().relative_to(repo.resolve())
    except ValueError:
        checks.append(check("agent-dir-ignored", True, "outside the repository (dry run only)"))
    else:
        probe = (PurePosixPath(rel.as_posix()) / "index.md").as_posix()
        ignored = git_ok(repo, "check-ignore", "-q", "--", probe)
        top = PurePosixPath(rel.as_posix()).parts[0]
        checks.append(check("agent-dir-ignored", ignored, f"{top}/ ignored" if ignored else f"{top}/ not ignored",
                            f"프로젝트 .gitignore(공유) 또는 .git/info/exclude(나만)에 '{top}/' 한 줄을 직접 추가하세요. 자동으로 고치지 않습니다."))
    problem = probe_writable(logs)
    checks.append(check("log-part-writable", not problem, "writable" if not problem else problem,
                        write_fix(agent_dir, repo, logs)))
    checks.append(check("notion-mcp", True, "agent must verify its own tool list"))
    return checks, repo


def detect_work_unit(repo: Path) -> list[dict]:
    found: list[dict] = []
    tags = [line.split() for line in git(repo, "for-each-ref", "refs/tags", "--sort=creatordate",
                                          "--format=%(refname:short) %(creatordate:short)", check=False).splitlines() if line.strip()]
    sprint = Counter(m.group(1) for t in tags if (m := SPRINT_RE.match(t[0])))
    if sprint:
        prefix, count = sprint.most_common(1)[0]
        found.append({"name": "스프린트", "basis": f"태그 {prefix}*", "evidence": f"tags {count}"})
    releases = [date.fromisoformat(t[1]) for t in tags if len(t) > 1 and RELEASE_RE.match(t[0])]
    if len(releases) >= 3:
        gaps = [(b - a).days for a, b in zip(releases, releases[1:]) if (b - a).days > 0]
        if gaps:
            cadence = int(statistics.median(gaps))
            found.append({"name": "릴리스", "basis": f"기간 {cadence}일, {releases[-1].isoformat()} 시작",
                          "evidence": f"release tags {len(releases)}, median gap {cadence}d"})
    branches = git(repo, "for-each-ref", "refs/heads", "refs/remotes", "--format=%(refname:short)", check=False).split()
    bprefix = Counter(m.group(1) for b in branches if (m := SPRINT_RE.match(b)))
    if bprefix:
        prefix, count = bprefix.most_common(1)[0]
        found.append({"name": "스프린트", "basis": f"브랜치 {prefix}*", "evidence": f"branches {count}"})
    return found


def detect_features(repo: Path, emails: list[str], limit: int = 6) -> list[dict]:
    args = ["log", "--branches", "--since=90.days", "--no-merges", "--fixed-strings", "--format=", "--name-only"]
    args += [f"--author={e}" for e in emails]
    counts: Counter[str] = Counter()
    for path in git(repo, *args, check=False).splitlines():
        parts = PurePosixPath(path.strip()).parts
        if len(parts) < 2:
            continue
        depth = 2 if parts[0].lower() in CONTAINER_DIRS and len(parts) > 2 else 1
        counts["/".join(parts[:depth])] += 1
    return [{"path": p, "file_changes": n} for p, n in counts.most_common(limit)]


def defaults(repo: Path) -> dict:
    email = git(repo, "config", "user.email", check=False).strip().lower()
    emails = [email] if email else []
    return {
        "project": repo_name(repo),
        "identities": emails,
        "work_unit_candidates": detect_work_unit(repo),
        "feature_candidates": detect_features(repo, emails) if emails else [],
        "notion_path": f"개인 페이지 / {repo_name(repo)} / 작업로그",
        "first_window_days": 7,
    }


def run(start: Path, agent_dir: str) -> dict:
    checks, repo = run_checks(start, agent_dir)
    ok = all(c["ok"] for c in checks)
    result = {"ok": ok, "checks": checks}
    if repo is not None:
        logs = log_dir(repo, agent_dir)
        result["repo"] = str(repo)
        result["log_dir"] = str(logs)
        result["first_run"] = not (logs / "profile.md").is_file()
        if result["first_run"] and ok:
            result["defaults"] = defaults(repo)
    if not ok:
        result["fixes"] = [c["fix"] for c in checks if not c["ok"]]
    return result


__all__ = ["run", "defaults", "TaskLogError"]
