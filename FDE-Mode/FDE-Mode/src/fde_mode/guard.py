"""Safety guard for tool calls while FDE mode is on (PreToolUse hook).

deny : the command never runs from Claude (destroys infrastructure or data,
       rewrites history, or prints secrets). The user can still run it in a
       terminal on purpose.
ask  : Claude Code shows the user a confirmation prompt first (rotating
       secrets, re-creating indexes, pushing, changing firewall rules).
The project binding adds its own patterns on top of these defaults.
"""
from __future__ import annotations

import re
from pathlib import Path

ENV_FILE = r"(?:^|[\s'\"=/])\.env(?=$|[\s'\";&|)<>])"

DEFAULT_DENY: list[tuple[str, str]] = [
    (r"\bmake\s+(?:-\S+\s+)*down\b", "인프라 전체 삭제(make down)는 대회 모드에서 막혀 있습니다"),
    (r"deploy/down\.sh", "인프라 삭제 스크립트는 막혀 있습니다"),
    (r"\bFORCE=1\b", "확인 프롬프트를 건너뛰는 FORCE=1은 막혀 있습니다"),
    (r"\baws\s+.*\b(terminate-instances|delete-security-group|delete-key-pair|delete-volume|release-address|"
     r"delete-db-instance|delete-bucket|deregister-image|delete-snapshot|delete-stack)\b", "AWS 리소스 삭제는 막혀 있습니다"),
    (r"\brm\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*[rR][A-Za-z]*\s+(?:/|~|\$HOME|\.|\*|\./\*)(?:\s|$)", "광범위한 rm -r 은 막혀 있습니다"),
    (r"\bgit\s+push\b.*(?:--force\b|--force-with-lease\b|\s-f\b)", "강제 push는 막혀 있습니다"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard 는 막혀 있습니다(되돌리기는 릴리스 태그로)"),
    (r"\bgit\s+clean\s+-[A-Za-z]*f", "git clean -f 는 막혀 있습니다"),
    (r"\b(?:DROP\s+(?:TABLE|DATABASE|SCHEMA)|TRUNCATE\s+(?:TABLE\s+)?\w)", "DB 테이블 삭제는 막혀 있습니다"),
    (r"\bdocker\s+(?:volume\s+(?:rm|prune)|system\s+prune|compose\s+down\s+.*-v)", "도커 볼륨 삭제는 막혀 있습니다"),
    (r"(?:^|[;&|(]\s*)(?:cat|less|more|head|tail|bat|nl|strings|xxd|od|tac|view)\b[^|;&]*" + ENV_FILE,
     ".env 내용을 화면에 출력하는 것은 막혀 있습니다(비밀값 노출). set/empty 확인은 `fde env check`"),
    (r"\bprintenv\b", "환경변수 전체 출력은 막혀 있습니다(비밀값 노출)"),
    (r"(?:^|[;&|]\s*)env\s*(?:$|[;&|])", "환경변수 전체 출력은 막혀 있습니다(비밀값 노출)"),
    (r"\bexport\s+-p\b", "환경변수 전체 출력은 막혀 있습니다(비밀값 노출)"),
    (r"\becho\s+[^|;&]*\$\{?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\b", "비밀값을 출력하는 echo는 막혀 있습니다"),
]

DEFAULT_ASK: list[tuple[str, str]] = [
    (r"\bRECREATE=1\b|--recreate\b", "벡터 컬렉션 재생성(기억 벡터도 지워짐) — 정말 실행할까요?"),
    (r"\bmake\s+(?:up|setup|token|secret|harden|harden-hosts|harden-data|caddy|myip)\b", "인프라·비밀값을 바꾸는 명령입니다"),
    (r"\bgit\s+push\b", "원격 저장소로 push 합니다"),
    (r"\bgit\s+(?:checkout\s+--\s+\.|restore\s+\.)", "작업 중인 변경을 모두 버립니다"),
    (r"\baws\s+ec2\s+(?:authorize|revoke)-security-group", "방화벽(보안 그룹) 규칙을 바꿉니다"),
    (r"\bgrep\b[^|;&]*" + ENV_FILE, ".env 를 grep 하면 값이 출력될 수 있습니다"),
    (r"\bsudo\b", "관리자 권한 명령입니다"),
    (r"\bcurl\b[^|]*\|\s*(?:ba|z)?sh\b", "인터넷 스크립트를 바로 실행합니다"),
]


def _compile(pairs: list) -> list[tuple[re.Pattern, str]]:
    out = []
    for item in pairs:
        if isinstance(item, (list, tuple)):
            pat, why = item[0], (item[1] if len(item) > 1 else "프로젝트 규칙")
        else:
            pat, why = str(item), "프로젝트 규칙"
        try:
            out.append((re.compile(pat, re.I), why))
        except re.error:
            continue
    return out


def check_command(cmd: str, cfg: dict) -> tuple[str, str]:
    """Return ('deny'|'ask'|'allow', reason)."""
    g = cfg.get("guard") or {}
    for pat, why in _compile(DEFAULT_DENY + list(g.get("deny") or [])):
        if pat.search(cmd or ""):
            return "deny", why
    for pat, why in _compile(DEFAULT_ASK + list(g.get("ask") or [])):
        if pat.search(cmd or ""):
            return "ask", why
    return "allow", ""


def check_file(tool: str, path: str, cfg: dict, project_root: Path, unsealed: bool = False) -> tuple[str, str]:
    if not path:
        return "allow", ""
    p = Path(path)
    name = p.name
    secrets = set((cfg.get("guard") or {}).get("secret_files") or [".env"])
    if name in secrets or str(p) in secrets:
        if tool in ("Read", "Grep", "NotebookRead"):
            return "deny", f"{name} 은 비밀값 파일이라 읽지 않습니다. set/empty 확인은 `fde env check`"
        if tool in ("Edit", "Write", "MultiEdit"):
            return "ask", f"{name}(비밀값 파일)을 수정합니다. 값이 화면에 남지 않게 `fde env set`을 권장합니다"
    try:
        rel = p.resolve().relative_to(project_root.resolve())
    except (ValueError, OSError):
        rel = p
    if "rehearsal/sealed" in str(rel).replace("\\", "/") and tool in ("Read", "Grep", "Glob") and not unsealed:
        return "deny", "리허설 봉인 파일입니다(숨은 요구사항). 채점 단계에서만 열립니다"
    protected = (cfg.get("guard") or {}).get("protected_paths") or []
    for pp in protected:
        if str(rel).startswith(pp) and tool in ("Edit", "Write", "MultiEdit"):
            return "deny", f"{pp} 는 보호된 경로입니다(프로젝트 규칙)"
    return "allow", ""


# Agents allowed to change project files (code, prompts, data). Everyone else may
# write only inside .claude/fde-mode/ (their output file and declared documents).
CODE_AGENTS = {
    "fde-tech-lead", "fde-prompt-engineer", "fde-dev-lead", "fde-graph-developer", "fde-tool-developer",
    "fde-platform-integrator", "fde-data-cleaner", "fde-data-loader",
}


def is_fde_agent(agent_type: str) -> bool:
    """Only FDE-Mode's own organisation (roster names, with or without the `fde-mode:` prefix). Agents of other
    plugins whose names also start with "fde-" (the arena's exam/eval/feedback/pilot teams) are not ours."""
    if not agent_type:
        return False
    plugin, _, name = agent_type.rpartition(":")
    if plugin and plugin != "fde-mode":
        return False
    from fde_mode.roster import BY_NAME
    return name in BY_NAME


def check_agent_write(agent_type: str, tool: str, path: str, project_root: Path) -> tuple[str, str]:
    if not is_fde_agent(agent_type) or tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit") or not path:
        return "allow", ""
    name = agent_type.split(":")[-1]
    if name in CODE_AGENTS:
        return "allow", ""
    try:
        rel = Path(path).resolve().relative_to(project_root.resolve())
    except (ValueError, OSError):
        rel = None
    if rel is not None and str(rel).replace("\\", "/").startswith(".claude/fde-mode/"):
        return "allow", ""
    if name in ("fde-retro-analyst",):
        from fde_mode.paths import global_dir
        try:
            if Path(path).resolve() == (global_dir() / "lessons.md").resolve():
                return "allow", ""
        except OSError:
            pass
    return "deny", f"{name} 는 분석 담당이라 .claude/fde-mode/ 밖의 파일을 고치지 않습니다"


# Independent seats: what each one must not see, so that its judgement stays independent of the rest of the
# organisation. Paths are relative to the work folder (.claude/fde-mode/). The files named in the seat's own
# issued dispatch (its inputs and its output) are always allowed, even when they live under a blocked folder.
BLIND_SEATS: dict[str, tuple[tuple[str, ...], str]] = {
    "fde-blind-verifier": (("runs", "board.md", "fde.db", "snapshots/debates.json"),
                           "블라인드 검증관은 다른 렌즈의 확신도·토론 기록을 보지 않습니다(받은 입력 파일만)"),
    "fde-counter-arguer": (("runs", "board.md", "fde.db", "snapshots/debates.json"),
                           "반론관은 다른 에이전트의 판단을 보지 않고 반론합니다(받은 입력 파일만)"),
    "fde-fit-judge": (("spec.md", "docs/requirements.md", "runs", "board.md", "fde.db", "snapshots"),
                      "맞춤 적합성 심사관은 명세·토론을 보지 않고 실제 답변만 봅니다"),
    "fde-ai-tell-checker": (("spec.md", "docs/requirements.md", "runs", "board.md", "fde.db", "snapshots"),
                            "AI티 검사관은 명세를 보지 않고 실제 답변만 봅니다"),
    "fde-rehearsal-grader": (("runs", "board.md"), "리허설 채점관은 토론 기록이 아니라 결과물로 채점합니다"),
}


def blind_seat(agent_type: str) -> tuple[tuple[str, ...], str] | None:
    return BLIND_SEATS.get((agent_type or "").split(":")[-1]) if is_fde_agent(agent_type) else None


def check_blind(tool: str, target: str, agent_type: str, work: Path, project_root: Path,
                allowed: set[str]) -> tuple[str, str]:
    """Read isolation for independent seats. `target` is a path (Read/Grep/Glob) or a command (Bash).
    `allowed` holds absolute and project-relative path prefixes the seat may always open (its own inputs, its
    output and its scratch files next to the output)."""
    seat = blind_seat(agent_type)
    if not seat:
        return "allow", ""
    blocked, why = seat
    roots = [(work / b).resolve() for b in blocked]
    if tool == "Bash":
        text = target or ""
        for b, root in zip(blocked, roots):
            token = f".claude/fde-mode/{b}"
            if token in text or str(root) in text:
                rest = text
                for a in sorted(allowed, key=len, reverse=True):
                    rest = rest.replace(a, "")
                if token in rest or str(root) in rest:
                    return "deny", why
        return "allow", ""
    if tool not in ("Read", "Grep", "Glob", "NotebookRead"):
        return "allow", ""
    try:
        t = (Path(target) if target and Path(target).is_absolute() else project_root / (target or ".")).resolve()
    except OSError:
        return "allow", ""
    if any(str(t).startswith(a) for a in allowed if a.startswith("/")):
        return "allow", ""
    for root in roots:
        if t == root or root in t.parents:
            return "deny", why
        if tool in ("Grep", "Glob") and t in root.parents:
            return "deny", why + " — 검색은 받은 입력 파일로 좁혀 주세요"
    return "allow", ""


def _sealed_roots(cfg: dict, project_root: Path) -> list[Path]:
    roots = []
    for sp in (cfg.get("guard") or {}).get("sealed_paths") or []:
        p = Path(sp)
        roots.append((p if p.is_absolute() else project_root / p).resolve())
    return roots


def rehearsal_sealed_roots(work: Path, unsealed: bool) -> list[Path]:
    """The rehearsal's hidden requirements: sealed from the solver side until grading (shell included)."""
    d = work / "rehearsal" / "sealed"
    return [d.resolve()] if not unsealed and d.is_dir() else []


def sealed_reader(cfg: dict, agent_type: str) -> bool:
    readers = (cfg.get("guard") or {}).get("sealed_readers") or []
    return bool(agent_type) and any(agent_type.startswith(r) for r in readers)


def _outside(project_root: Path, p: Path) -> bool:
    pr = project_root.resolve()
    return not (p == pr or pr in p.parents)


def _sealed_hit(target: Path, roots: list[Path], project_root: Path, searching: bool) -> bool:
    """Inside a sealed root, or (for searches and shell paths) an ancestor of one that lies outside the project:
    `grep -r .. ` from an answer folder would read the sealed problem next to it."""
    for root in roots:
        if target == root or root in target.parents:
            return True
        if searching and target in root.parents and _outside(project_root, target):
            return True
    return False


def check_sealed_file(tool: str, path: str, cfg: dict, project_root: Path, agent_type: str) -> tuple[str, str]:
    if tool not in ("Read", "Grep", "Glob", "NotebookRead") or sealed_reader(cfg, agent_type):
        return "allow", ""
    if not path and tool == "Read":
        return "allow", ""
    try:
        target = (Path(path) if path and Path(path).is_absolute() else project_root / (path or ".")).resolve()
    except OSError:
        return "allow", ""
    roots = _sealed_roots(cfg, project_root)
    if _sealed_hit(target, roots, project_root, searching=tool in ("Grep", "Glob")):
        return "deny", "봉인된 출제·답안 폴더입니다. 수행 측은 읽지 않습니다(실전과 같은 조건)"
    return "allow", ""


_GLOB = re.compile(r"[*?\[{]")


def _path_tokens(cmd: str) -> list[str]:
    import shlex
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    out: list[str] = []
    for t in toks:
        for part in re.split(r"[=:,]", t) if ("=" in t or ":" in t) and not t.startswith("/") else [t]:
            part = part.strip().strip("'\"")
            if not part or part.startswith("-") and "/" not in part:
                continue
            m = _GLOB.search(part)
            if m:
                part = part[:m.start()] or "."
            if "/" in part or part in (".", "..") or part.startswith("~"):
                out.append(part)
    return out


def check_sealed_command(cmd: str, cfg: dict, project_root: Path, agent_type: str,
                         extra_roots: list[Path] | tuple = ()) -> tuple[str, str]:
    """Shell access to sealed folders: absolute or relative paths that resolve into a sealed root, `..`-style
    paths to a folder that contains one, and recursive reads of the project when a sealed root lives inside it.
    `extra_roots`: the rehearsal's sealed folder while it is still sealed (the caller decides)."""
    text = cmd or ""
    roots = ([] if sealed_reader(cfg, agent_type) else _sealed_roots(cfg, project_root)) + list(extra_roots)
    if not roots:
        return "allow", ""
    for root in roots:  # absolute path in the text, as a whole path component (…/sample1 must not match …/sample12)
        if re.search(re.escape(str(root)) + r"(?=$|[/\s'\";&|)<>])", text):
            return "deny", "봉인된 출제·답안 폴더를 셸로 읽을 수 없습니다(실전과 같은 조건)"
    for tok in _path_tokens(text):
        try:
            p = Path(tok).expanduser()
            t = (p if p.is_absolute() else project_root / p).resolve()
        except (OSError, RuntimeError):
            continue
        if _sealed_hit(t, roots, project_root, searching=True):
            return "deny", "봉인된 출제·답안 폴더(또는 그것을 담은 상위 폴더)를 셸로 읽을 수 없습니다"
    # Recursive reads that ignore .gitignore (rg and the Grep tool respect it, so they stay allowed).
    recursive = (re.search(r"\b(?:grep|egrep|fgrep)\b[^|;&]*(?:\s-[A-Za-z]*[rR][A-Za-z]*\b|--recursive|--dereference-recursive)", text)
                 or re.search(r"\bfind\b[^|;&]*(?:-exec|-ok)\b|\bfind\b[^;&]*\|\s*xargs\b", text)
                 or re.search(r"\b(?:tar|zip|rsync)\b|\bcp\s+(?:-[A-Za-z]*[rR]|--recursive)", text))
    inside = [r for r in roots if not _outside(project_root, r)]
    if recursive and inside:
        import shlex
        try:
            words = shlex.split(text, posix=True)
        except ValueError:
            words = text.split()
        toks = [w for w in words if not w.startswith("-") and ("/" in w or w in (".", "..") or (project_root / w).exists())]
        toks = toks or ["."]
        for tok in toks:
            try:
                t = (project_root / tok).resolve() if not Path(tok).is_absolute() else Path(tok).resolve()
            except OSError:
                continue
            if any(t in r.parents for r in inside):
                return "deny", ("프로젝트 안에 봉인 폴더가 있어 전체를 재귀로 읽을 수 없습니다 — Grep 도구(.gitignore 존중)를 쓰거나 "
                                "봉인 폴더를 제외하세요")
    return "allow", ""
