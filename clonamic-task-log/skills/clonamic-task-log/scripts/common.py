"""Shared helpers: git runner, storage paths, JSON state, profile parser, file classes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path, PurePosixPath

STATE_VERSION = 1
RUN_FILE = ".run.json"


class TaskLogError(Exception):
    """Expected failure with a fix message for the user."""

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


# ---------------------------------------------------------------- git

GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0"}
# Read boundary: these never reach any read (diff, grep, listing), even when tracked.
SENSITIVE_PATHSPEC = [
    ":(exclude,glob)**/.env*", ":(exclude,glob)**/*credential*", ":(exclude,glob)**/*secret*",
    ":(exclude,glob)**/*.pem", ":(exclude,glob)**/*.key", ":(exclude,glob)**/id_rsa*", ":(exclude,glob)**/id_ed25519*",
    ":(exclude,glob)**/node_modules/**", ":(exclude,glob)**/vendor/**", ":(exclude,glob)**/.venv/**",
    ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/models/**", ":(exclude,glob)**/checkpoints/**",
    ":(exclude,glob)**/*.ckpt", ":(exclude,glob)**/*.safetensors",
]


def git(repo: Path, *args: str, stdin: str | None = None, check: bool = True) -> str:
    """Run a read-only git command (callers never pass a writing subcommand)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=stdin,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise TaskLogError(f"git {args[0]} failed: {proc.stderr.strip()}")
    return proc.stdout


def git_ok(repo: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=GIT_ENV).returncode == 0


def repo_root(start: Path) -> Path:
    return Path(git(start, "rev-parse", "--show-toplevel").strip())


def repo_name(repo: Path) -> str:
    for remote in git(repo, "remote", check=False).split():
        url = git(repo, "remote", "get-url", remote, check=False).strip()
        if url:
            name = re.split(r"[/:]", url.rstrip("/"))[-1]
            return name.removesuffix(".git") or repo.name
    return repo.name


# ---------------------------------------------------------------- storage

def log_dir(repo: Path, agent_dir: str) -> Path:
    base = Path(agent_dir)
    if not base.is_absolute():
        base = repo / base
    return base / "log-part"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def write_json(path: Path, data) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def remote_url(repo: Path) -> str:
    remotes = git(repo, "remote", check=False).split()
    for remote in (["origin"] if "origin" in remotes else []) + remotes:
        url = git(repo, "remote", "get-url", remote, check=False).strip()
        if url:
            return url
    return ""


def project_identity(repo: Path) -> dict:
    url = re.sub(r"\.git/?$", "", remote_url(repo).strip().rstrip("/")).lower()
    return {
        "remote_hash": hashlib.sha256(url.encode()).hexdigest()[:16] if url else "",
        "root": str(repo.resolve()),
    }


def open_project(start: Path, agent_dir: str) -> tuple[Path, Path, dict]:
    """Resolve the project from the working directory and load ONLY its own log-part.

    Refuses outside a git repository and refuses a log-part whose recorded identity
    belongs to another project (copied or moved folder).
    """
    if not git_ok(start, "rev-parse", "--show-toplevel"):
        raise TaskLogError("not inside a git repository", "기록할 프로젝트 폴더(git 저장소) 안에서 실행하세요.")
    repo = repo_root(start)
    logs = log_dir(repo, agent_dir)
    state = load_state(logs)
    recorded = state.get("project")
    if recorded:
        current = project_identity(repo)
        if recorded.get("remote_hash") != current["remote_hash"]:
            raise TaskLogError(
                "log-part belongs to another project (remote differs)",
                f"{logs} 는 다른 프로젝트의 기록입니다. 이 프로젝트용으로 쓰려면 폴더를 옮기거나 지우고 첫 실행 설정을 다시 하세요.",
            )
        if recorded.get("root") != current["root"]:
            raise TaskLogError(
                "log-part was recorded at another project root",
                f"기록 위치가 {recorded.get('root')} 에서 바뀌었습니다. 같은 프로젝트를 옮긴 것이 맞으면 'tasklog.py rebind'로 확인하세요.",
            )
    return repo, logs, state


def load_state(logs: Path) -> dict:
    state = read_json(logs / "state.json", {})
    state.setdefault("version", STATE_VERSION)
    for key, empty in (("cursors", {}), ("processed", []), ("days", {}), ("features", {}),
                       ("metrics", []), ("notion", {})):
        state.setdefault(key, empty)
    return state


# ---------------------------------------------------------------- profile

@dataclass
class Feature:
    label: str
    paths: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    milestones: list[tuple[str, bool]] = field(default_factory=list)


@dataclass
class WorkUnit:
    name: str
    mode: str  # cadence | tag | branch
    days: int = 0
    start: str = ""
    pattern: str = ""


@dataclass
class Profile:
    part: str = ""
    identities: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    work_unit: WorkUnit | None = None
    first_window_days: int = 7
    timezone: str = "Asia/Seoul"
    exclude_paths: list[str] = field(default_factory=list)
    max_commits: int = 200
    max_files: int = 2000
    public_terms: list[str] = field(default_factory=list)
    private_terms: list[str] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    repo_terms: list[str] = field(default_factory=list)  # filled at run time, never parsed


NONE_WORDS = {"", "없음", "(없음)", "(전체)", "전체", "none", "-"}
KEY_LINE = re.compile(r"^\s*-\s*([^:\[\]]+?)\s*:\s*(.*)$")
MILESTONE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+?)\s*$")


def split_list(value: str) -> list[str]:
    if value.strip().lower() in NONE_WORDS:
        return []
    return [part.strip().strip("`") for part in re.split(r"[,\s]+", value) if part.strip().strip("`")]


def split_terms(value: str) -> list[str]:
    if value.strip().lower() in NONE_WORDS:
        return []
    return [part.strip().strip("`") for part in value.split(",") if part.strip().strip("`")]


def parse_work_unit(name: str, basis: str) -> WorkUnit | None:
    if name.strip().lower() in NONE_WORDS:
        return None
    if m := re.search(r"태그\s+(\S+)", basis):
        return WorkUnit(name.strip(), "tag", pattern=m.group(1).strip("`"))
    if m := re.search(r"브랜치\s+(\S+)", basis):
        return WorkUnit(name.strip(), "branch", pattern=m.group(1).strip("`"))
    days = re.search(r"(\d+)\s*일", basis)
    start = re.search(r"(\d{4}-\d{2}-\d{2})", basis)
    if days and start:
        return WorkUnit(name.strip(), "cadence", days=int(days.group(1)), start=start.group(1))
    raise TaskLogError(
        f"work unit basis not understood: {basis!r}",
        "profile.md의 '작업 단위 기준'을 '기간 14일, 2026-09-28 시작', '태그 sprint-*', '브랜치 sprint-*' 중 하나로 적으세요.",
    )


def parse_profile(text: str) -> Profile:
    profile = Profile()
    fields: dict[str, str] = {}
    current: Feature | None = None
    in_features = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_features = line[3:].strip() == "기능"
            current = None
            continue
        if in_features and line.startswith("### "):
            current = Feature(label=line[4:].strip())
            profile.features.append(current)
            continue
        if in_features and current is not None:
            if m := MILESTONE.match(line):
                current.milestones.append((m.group(2), m.group(1).lower() == "x"))
            elif m := KEY_LINE.match(line):
                key, value = m.group(1).strip(), m.group(2)
                if key == "경로":
                    current.paths = [p.strip("/") for p in split_list(value)]
                elif key == "키":
                    current.keys = [k.lower() for k in split_list(value)]
            continue
        if not in_features and (m := KEY_LINE.match(line)):
            fields[m.group(1).strip()] = m.group(2).strip()
    profile.part = fields.get("파트", "")
    profile.identities = [e.lower() for e in split_terms(fields.get("신원", ""))]
    profile.scopes = [p.strip("/") for p in split_list(fields.get("범위", ""))]
    if fields.get("작업 단위"):
        profile.work_unit = parse_work_unit(fields["작업 단위"], fields.get("작업 단위 기준", ""))
    if m := re.search(r"\d+", fields.get("첫 기록 범위", "")):
        profile.first_window_days = int(m.group())
    profile.timezone = fields.get("시간대", "").strip() or "Asia/Seoul"
    profile.exclude_paths = [p.strip("/") for p in split_list(fields.get("제외 경로", ""))]
    for key, attr in (("최대 커밋", "max_commits"), ("최대 파일", "max_files")):
        if m := re.search(r"\d+", fields.get(key, "")):
            setattr(profile, attr, int(m.group()))
    profile.public_terms = split_terms(fields.get("공개 용어", ""))
    profile.private_terms = split_terms(fields.get("비공개 용어", ""))
    if not profile.identities:
        raise TaskLogError("profile has no identities", "profile.md의 '신원'에 커밋 이메일이나 이름을 하나 이상 적으세요.")
    zone(profile.timezone)
    return profile


def zone(name: str) -> tzinfo:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:
        fixed = {"Asia/Seoul": 9, "Asia/Tokyo": 9, "UTC": 0, "Etc/UTC": 0}
        if name in fixed:
            return timezone(timedelta(hours=fixed[name]))
        raise TaskLogError(f"unknown timezone {name!r}", "profile.md의 '시간대'를 Asia/Seoul 같은 IANA 이름으로 적으세요.")


def today_in(name: str) -> date:
    return datetime.now(zone(name)).date()


WHEN_WORDS = {"오늘": 0, "어제": 1, "그제": 2}


def parse_when(text: str, today: date) -> tuple[date, date]:
    """Work-date argument -> (start, end), both inclusive.

    '', 오늘, 어제, 그제, YYYY-MM-DD, MM-DD (this year), and ranges 'A~B' of the date forms.
    """
    text = (text or "").strip()
    fix = "날짜는 2026-09-29, 09-29, 오늘, 어제, 그제 또는 09-28~10-02 형식으로 적으세요."

    def one(part: str) -> date:
        part = part.strip()
        try:
            if part in WHEN_WORDS:
                return today - timedelta(days=WHEN_WORDS[part])
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", part):
                return date.fromisoformat(part)
            if re.fullmatch(r"\d{1,2}-\d{1,2}", part):
                month, day = part.split("-")
                return date(today.year, int(month), int(day))
        except ValueError:
            pass
        raise TaskLogError(f"cannot parse date {part!r}", fix)

    if not text:
        return today, today
    first, sep, last = text.partition("~")
    start = one(first)
    end = one(last) if sep else start
    if start > end:
        raise TaskLogError(f"range start is after its end: {text!r}", fix)
    return start, end


def day_start(day: date, name: str) -> str:
    """ISO timestamp of local midnight, for git --since/--until."""
    return datetime(day.year, day.month, day.day, tzinfo=zone(name)).isoformat()


def is_mine(commit_name: str, commit_email: str, identities: list[str]) -> bool:
    return commit_email.lower() in identities or commit_name.lower() in identities


def load_profile(logs: Path) -> Profile:
    path = logs / "profile.md"
    if not path.is_file():
        raise TaskLogError("profile.md missing", "첫 실행 설정을 먼저 진행하세요(/clonamic-task-log 설정).")
    return parse_profile(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- file classes

CODE_EXT = {
    "py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "go", "rs", "java", "kt", "kts", "swift", "rb", "php",
    "c", "h", "cc", "cpp", "hpp", "cs", "m", "mm", "scala", "dart", "lua", "r", "pl", "sh", "bash", "zsh",
    "sql", "vue", "svelte", "ex", "exs", "erl", "hs", "clj", "zig", "nim", "jl", "ps1", "html", "css",
    "scss", "sass", "less", "proto", "graphql", "tf", "ipynb",
}
DOC_EXT = {"md", "mdx", "rst", "adoc", "txt"}
CONFIG_EXT = {"json", "yaml", "yml", "toml", "ini", "cfg", "conf", "xml", "gradle", "properties", "env", "lock"}
LOCK_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "cargo.lock",
    "gemfile.lock", "composer.lock", "go.sum", "pipfile.lock", "bun.lockb", "flake.lock", "podfile.lock",
    "packages.lock.json", "mix.lock", "pubspec.lock",
}
VENDOR_DIRS = {"vendor", "node_modules", "third_party", "thirdparty", "third-party", "bower_components", ".yarn"}
GENERATED_DIRS = {"dist", "build", "generated", "__generated__", "gen", "out", ".next", "target", "coverage"}
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", "_pb2.py", "_pb2_grpc.py", ".pb.go", ".g.dart", ".snap")
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "testing"}
BENCH_DIRS = {"bench", "benches", "benchmark", "benchmarks", "perf"}


def ext_of(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    return name.rsplit(".", 1)[-1] if "." in name.lstrip(".") else ""


def is_test(path: str) -> bool:
    p = PurePosixPath(path.lower())
    name = p.name
    return (
        any(part in TEST_DIRS for part in p.parts[:-1])
        or name.startswith("test_")
        or re.search(r"(_test|\.test|\.spec|_spec)\.[a-z0-9]+$", name) is not None
        or re.search(r"[a-z0-9]Tests?\.(java|kt|cs|swift|scala)$", PurePosixPath(path).name) is not None
    )


def is_bench(path: str) -> bool:
    p = PurePosixPath(path.lower())
    return any(part in BENCH_DIRS for part in p.parts[:-1]) or re.search(r"(^|_)bench", p.name) is not None


def is_doc(path: str) -> bool:
    p = PurePosixPath(path.lower())
    return ext_of(path) in DOC_EXT or "docs" in p.parts[:-1] or p.name in {"license", "changelog", "readme"}


def is_code(path: str) -> bool:
    return ext_of(path) in CODE_EXT


def is_noise(path: str) -> str:
    """Return 'lock', 'vendor', 'generated' or '' for a path."""
    p = PurePosixPath(path.lower())
    if p.name in LOCK_NAMES:
        return "lock"
    if any(part in VENDOR_DIRS for part in p.parts[:-1]):
        return "vendor"
    if any(part in GENERATED_DIRS for part in p.parts[:-1]) or p.name.endswith(GENERATED_SUFFIXES):
        return "generated"
    return ""


def under(path: str, prefix: str) -> bool:
    prefix = prefix.strip("/")
    return not prefix or path == prefix or path.startswith(prefix + "/")
