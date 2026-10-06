"""Idempotent local write: dated entry file, state.json, index.md, Notion ids, portfolio roll-up."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from common import TaskLogError, members, project_identity, remote_url, write_json, write_text_atomic

TITLE = re.compile(r"^# (\d{4}-\d{2}-\d{2}(?:~\d{4}-\d{2}-\d{2})?) · (.+)$")
NOTION_KINDS = {"root", "container", "project", "log", "progress", "portfolio", "day"}


def evidence_fingerprint(run_date: str, key: str, commits: list[dict], excluded: list[dict]) -> str:
    """sha256 over normalized evidence: date, key, and per commit (sha, date, lines, files, exclusion)."""
    reasons = {e["sha"]: e["reason"] for e in excluded}
    rows = sorted(
        [c["sha"], c["date"], c["added"], c["deleted"], c["file_count"], reasons.get(c["sha"], "")] for c in commits
    )
    payload = json.dumps({"date": run_date, "key": key, "commits": rows}, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def body_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def headline(entry: str) -> str:
    """The 대표 성과 in the title line."""
    m = TITLE.match(entry.strip().splitlines()[0]) if entry.strip() else None
    return m.group(2).strip() if m else ""


WORKSPACE_FILE = "workspace.md"


def bind_project(repo: Path, logs: Path, state: dict) -> dict:
    """Record, on every save, which repositories this log-part belongs to: the identity in state.json and,
    for a workspace, workspace.md listing every bound repository. The caller writes state.json."""
    state["project"] = project_identity(repo)
    parts = [(prefix.rstrip("/"), path) for prefix, path in members(repo) if prefix]
    if not parts:
        return {}
    rows = [f"| {name} | {remote_url(path) or '(원격 없음)'} |" for name, path in parts]
    write_text_atomic(logs / WORKSPACE_FILE, "\n".join([
        "# 묶인 저장소",
        "",
        "이 기록 폴더는 아래 저장소들을 하나의 프로젝트로 묶어 씁니다. /clonamic-task-log 가 저장할 때마다 다시 씁니다.",
        "기능 경로와 범위·제외 경로는 `저장소 폴더/경로` 형태로 적습니다(예: `plugin/scripts`). 저장소 폴더 이름만 쓰면 그 저장소 전체입니다.",
        "",
        f"- 루트: {repo}",
        f"- 저장소: {len(parts)}개 (상한 20개)",
        "",
        "| 저장소 폴더 | 원격 |",
        "|---|---|",
        *rows,
    ]) + "\n")
    return {"workspace": [name for name, _ in parts], "workspace_file": str(logs / WORKSPACE_FILE)}


def write_entry(repo: Path, logs: Path, state: dict, run: dict, entry: str) -> dict:
    """Write <date>.md whole (an entry carries no metadata). The entry date must be the prepared run's date."""
    run_date, key, fingerprint = run["date"], run["key"], run["fingerprint"]
    m = TITLE.match(entry.strip().splitlines()[0]) if entry.strip() else None
    if not m or m.group(1) != run_date:
        raise TaskLogError(
            f"entry date {m.group(1) if m else '(none)'} does not match the prepared run {run_date}",
            f"기록 제목을 '# {run_date} · 대표 성과'로 쓰거나, 이 날짜로 prepare 를 다시 실행하세요.",
        )
    body = entry.strip() + "\n"
    digest = body_hash(body)
    day = state["days"].setdefault(run_date, {"blocks": {}})
    old = day["blocks"].get(key)
    path = logs / f"{run_date}.md"
    if old and old.get("fingerprint") == fingerprint and old.get("body_sha") == digest and path.is_file():
        return {"status": "unchanged", "file": str(path)}
    write_text_atomic(path, body)

    bind_project(repo, logs, state)
    day["blocks"][key] = {
        "fingerprint": fingerprint,
        "body_sha": digest,
        "headline": headline(body),
        "period": run["period"],
        "considered": run["considered"],
        "patches": run.get("patches", []),
        "types": run["types"],
        "notion_title": run["notion_title"],
        "collected_at": run["generated_at"],
        "features": run.get("touched_features", []),
    }
    state["processed"] = sorted(set(state["processed"]) | set(run["considered"]))
    state["processed_patches"] = sorted(set(state.get("processed_patches", [])) | set(run.get("patches", [])))
    updated = run["period"]["to"]
    live = {item["feature"] for item in run["progress"]}
    for gone in [label for label in state["features"] if label not in live]:
        del state["features"][gone]  # features whose paths no longer exist are dropped
    for item in run["progress"]:
        old_feature = state["features"].get(item["feature"], {})
        same_day = old_feature.get("updated") == updated
        prev = old_feature.get("prev") if same_day else old_feature.get("pct")
        done_prev = old_feature.get("done_prev", old_feature.get("done")) if same_day else old_feature.get("done")
        state["features"][item["feature"]] = {"pct": item["pct"], "basis": item["basis"], "updated": updated,
                                              "prev": prev, "milestones": item.get("milestones"),
                                              "shown": item.get("shown"), "done": item.get("done", []),
                                              **({"done_prev": done_prev} if done_prev is not None else {})}
    completed = [c for c in state.get("completed", []) if c.get("date") != run_date]
    state["completed"] = completed + [{"date": run_date, "target": c["target"], "kind": c["kind"]}
                                      for c in run.get("completions", [])]
    if run.get("work_unit"):
        state["work_unit"] = {k: run["work_unit"].get(k) for k in ("label", "start", "end", "pct", "commits")}
    kept = [m for m in state["metrics"] if not (m["date"] == run_date and m.get("key") == key)]
    state["metrics"] = kept + [m | {"date": run_date, "key": key} for m in run["metrics"]]
    state["last_run"] = run["generated_at"]
    write_json(logs / "state.json", state)
    write_text_atomic(logs / "index.md", render_index(state, run["project"]))
    return {"status": "written", "file": str(path), "fingerprint": fingerprint}


def render_index(state: dict, project: str) -> str:
    days = sorted(state["days"], reverse=True)
    lines = ["# 작업 기록 색인", "", "## 한눈에 보기", f"- 프로젝트 — {project}",
             f"- 기록 — {len(days)}일" + (f", 최근 {days[0]}" if days else ""), "", "## 타임라인"]
    for day in days:
        for key, block in sorted(state["days"][day]["blocks"].items()):
            suffix = "" if key == "daily" else f" ({block['period'].get('from', '')}~{block['period'].get('to', '')})"
            lines.append(f"- [{day}]({day}.md){suffix} — {block.get('headline') or '기록'}")
    if state["features"]:
        lines += ["", "## 기능별 진행 정도 (추정)", "", "| 기능 | 진행 | 근거 | 갱신 |", "|---|---|---|---|"]
        for label, item in sorted(state["features"].items()):
            shown = item.get("shown") or ("마일스톤 미설정" if "마일스톤 없음" in item["basis"] else f"약 {item['pct']}%")
            lines.append(f"| {label} | {shown} | {item['basis']} | {item['updated']} |")
    if state.get("completed"):
        lines += ["", "## 완료 기록"] + [f"- {c['date']} — {c['target']}" for c in state["completed"]]
    if unit := state.get("work_unit"):
        lines += ["", "## 작업 단위", f"- {unit['label']} — {unit.get('start', '')}~{unit.get('end') or ''}"
                  + (f", 진행 {unit['pct']}% (추정)" if unit.get("pct") is not None else "")]
    return "\n".join(lines) + "\n"


NOTION_START = "<!-- tasklog:pages:start -->"
NOTION_END = "<!-- tasklog:pages:end -->"
NOTION_ROLES = (("root", "루트", "개인페이지", "(워크스페이스 개인 영역)"),
                ("container", "프로젝트 모음", "project", ""),
                ("project", "프로젝트", "", ""),
                ("log", "작업로그", "작업로그", ""),
                ("progress", "진행 현황", "진행 현황", ""),
                ("portfolio", "포트폴리오 요약", "포트폴리오 요약", "(포트폴리오 정리 때 생성)"))
NOTION_TEMPLATE = """# Notion 위치

- 경로: 개인페이지 / project / {project} / 작업로그
- 루트 페이지: 개인페이지
- 템플릿: notion-template.md

## 페이지

{block}

## 구조

작업로그
├── 진행 현황        기능별 진행(마일스톤이 있는 기능만 %)·최근 변화·남은 일, 실행마다 갱신
├── 포트폴리오 요약   `포트폴리오 정리` 때 만들고 갱신
├── 2026-10-05       날짜 기록(제목은 날짜만)
└── 0928~1002        기간 기록(제목은 MMDD~MMDD)
"""


def _cell(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def render_notion_block(state: dict, project: str) -> str:
    notion = state.get("notion", {})
    rows = ["| 역할 | 제목 | ID | URL |", "|---|---|---|---|"]
    for key, role, title, placeholder in NOTION_ROLES:
        rec = notion.get(key) or {}
        shown = rec.get("title") or (project if key == "project" else title)
        rows.append(f"| {role} | {_cell(shown)} | {_cell(rec.get('id') or placeholder)} | {_cell(rec.get('url'))} |")
    for day, rec in sorted(notion.get("days", {}).items()):
        shown = rec.get("title") or day
        rows.append(f"| 날짜 기록 | {_cell(shown)} | {_cell(rec.get('id'))} | {_cell(rec.get('url'))} |")
    return "\n".join([NOTION_START, *rows, NOTION_END])


def sync_notion_md(logs: Path, state: dict, project: str) -> str:
    """Rewrite only the location table in notion.md; user text outside the table block is kept."""
    path = logs / "notion.md"
    block = render_notion_block(state, project)
    if not path.is_file():
        text = NOTION_TEMPLATE.format(project=project, block=block)
    else:
        text = path.read_text(encoding="utf-8")
        if NOTION_START in text and NOTION_END in text[text.index(NOTION_START):]:
            head, rest = text.split(NOTION_START, 1)
            text = head + block + rest.split(NOTION_END, 1)[1]
        else:
            lines = text.split("\n")
            start = next((i for i, ln in enumerate(lines) if re.match(r"^\|\s*역할\s*\|", ln)), None)
            if start is not None:
                end = start
                while end < len(lines) and lines[end].lstrip().startswith("|"):
                    end += 1
                lines[start:end] = block.split("\n")
                text = "\n".join(lines)
            else:
                text = text.rstrip("\n") + "\n\n## 페이지\n\n" + block + "\n"
    write_text_atomic(path, text)
    return str(path)


def set_notion(repo: Path, logs: Path, state: dict, kind: str, page_id: str, url: str = "", day: str = "",
               title: str = "", project: str = "") -> dict:
    if kind not in NOTION_KINDS:
        raise TaskLogError(f"unknown notion kind {kind!r}", f"--kind 는 {sorted(NOTION_KINDS)} 중 하나입니다.")
    record = {"id": page_id, "url": url, "title": title}
    bind_project(repo, logs, state)
    if kind == "day":
        if not day:
            raise TaskLogError("--date is required for kind=day")
        state["notion"].setdefault("days", {})[day] = record
    else:
        state["notion"][kind] = record
    write_json(logs / "state.json", state)
    result = {"status": "recorded", "kind": kind}
    try:
        result["notion_md"] = sync_notion_md(logs, state, project or logs.parent.parent.name)
    except OSError as exc:  # state.json is the source of truth; a guarded folder must not fail the record
        result["notion_md_error"] = f"{type(exc).__name__}: {exc.strerror or exc}"
    return result


def forget_day(logs: Path, state: dict, day: str, project: str) -> dict:
    """Delete one entry file, its state and index line. Notion pages cannot be trashed by the MCP: report the page."""
    if day not in state["days"]:
        raise TaskLogError(f"no recorded entry for {day}", "tasklog.py status 로 기록된 날짜를 확인하세요.")
    path = logs / f"{day}.md"
    removed = path.is_file()
    if removed:
        path.unlink()
    del state["days"][day]
    state["metrics"] = [m for m in state["metrics"] if m.get("date") != day]
    page = state["notion"].get("days", {}).pop(day, None)
    notes = notes_file(logs, day)
    if notes.is_file():
        notes.unlink()
    state.get("notes", {}).pop(day, None)
    write_json(logs / "state.json", state)
    write_text_atomic(logs / "index.md", render_index(state, project))
    result = {"status": "forgotten", "date": day, "file_removed": removed, "notion": page}
    if page:
        result["user_action"] = (f"Notion 페이지 {page.get('url') or page.get('id')} 는 Notion MCP로 휴지통에 보낼 수 없습니다. "
                                 "사용자가 직접 삭제하세요.")
    return result


def portfolio_rollup(state: dict, project: str, part: str) -> dict:
    days = sorted(state["days"])
    types: Counter[str] = Counter()
    highlights = []
    for day in days:
        for key, block in sorted(state["days"][day]["blocks"].items()):
            types.update(block.get("types", {}))
            if block.get("headline"):
                highlights.append({"date": day, "headline": block["headline"]})
    return {
        "project": project,
        "part": part,
        "period": {"from": days[0] if days else "", "to": days[-1] if days else ""},
        "days": len(days),
        "work_by_type": dict(types.most_common()),
        "features": [{"feature": k} | v for k, v in sorted(state["features"].items())],
        "metrics": state["metrics"],
        "highlights": highlights,
        "completed": state.get("completed", []),
        "work_unit": state.get("work_unit"),
        "notion": state["notion"].get("portfolio"),
    }


# ---------------------------------------------------------------- saved work notes

def notes_file(logs: Path, run_date: str) -> Path:
    return logs / "notes" / f"{run_date}.md"


def save_notes(repo: Path, logs: Path, state: dict, run: dict, text: str) -> dict:
    """Persist checked notes for the prepared date, tied to its evidence fingerprint (kept in state.json only)."""
    path = notes_file(logs, run["date"])
    bind_project(repo, logs, state)
    write_text_atomic(path, text.strip() + "\n")
    state.setdefault("notes", {})[run["date"]] = {"fingerprint": run["fingerprint"], "saved_at": run["generated_at"]}
    write_json(logs / "state.json", state)
    return {"file": str(path), "fingerprint": run["fingerprint"]}


def saved_notes(logs: Path, state: dict, run_date: str, fingerprint: str, redo: bool = False) -> dict:
    """status: reuse (same evidence, use as is) | stale (evidence changed: revise only what changed) | redo | none."""
    path = notes_file(logs, run_date)
    record = state.get("notes", {}).get(run_date)
    if not record or not path.is_file():
        return {"status": "none", "text": ""}
    text = path.read_text(encoding="utf-8")
    if redo:
        return {"status": "redo", "text": ""}
    return {"status": "reuse" if record.get("fingerprint") == fingerprint else "stale", "text": text}
