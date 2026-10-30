"""Project binding (<project>/.claude/fde-mode/project.toml) and plugin defaults.

The plugin is generic. Everything project-specific (commands, paths, guard
rules, schedule, facts that are already decided) lives in the binding so the
same organisation can be reused after the competition.
"""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from fde_mode.paths import P, plugin_root

DEFAULTS: dict[str, Any] = {
    "project": {
        "name": "",
        "profile": "generic",
        # When the event/customer fixes the delivery surface (e.g. "kakao-chatbot"), the packaging strategist designs
        # inside it and records the tensions; when empty, packaging is an open D1 decision of the tech gate.
        "packaging_fixed": "",
        "timezone": "Asia/Seoul",
        "language": "ko",
    },
    "schedule": {
        # Empty date = no deadline (time-budget logic switches off).
        "date": "",
        "start": "10:00",
        "end": "15:00",
        "core_freeze": "11:10",
        "full_freeze": "13:30",
        "feature_freeze": "14:15",
        "submit_by": "14:50",
    },
    "interview": {
        "interviewer_aliases": ["나", "me", "Me", "You", "you", "user", "User", "Q", "질문",
                                "인터뷰어", "참가자", "Interviewer"],
        "persona_aliases": [],
        "debate_every": 3,
        "top_cards": 5,
        "readback_every": 3,
        "stale_minutes": 25,
        "min_rounds_before_freeze": 3,
    },
    "switches": {
        "debate": True,
        "team_complement": True,
        "dashboard": True,
        "tech_gate": True,
        "auto_detect_paste": True,
        "stop_enforce": True,
        "build": True,
        "division_persona": True,
        "division_problem": True,
        "division_solution": True,
        "division_risk": True,
        "division_strategy": True,
        "division_comms": True,
        "division_data": True,
        # Off = collaboration mode (default): the user co-decides the build — a design check per slice, design questions
        # raised while implementing, a progress check after each slice, a confirm before the first deploy. On only when
        # the user explicitly says so (`/fde-mode auto on`, "자율 모드로 해"); then D2 decisions take the recommendation.
        "autonomy": False,
        # Conversation view (dashboard tab "대화"): the tab itself, and the hooks that store the user's prompts and
        # Claude's replies for it. Off = nothing is captured; the rest of FDE is unchanged.
        "conversation_view": True,
        "capture_claude_turns": True,
        # Stage map S1–S8 + engagement profile: the round-end check, its gap/depth cards and "go back?" D2. Off =
        # those stop; the flow (P0–P7) never depended on them.
        "stage_map": True,
    },
    "collab": {
        # collaboration questions (D2) per slice before the recommendation is taken (D3). 0 or less = no cap (default):
        # every design question is asked until the user turns autonomy on (user 10/30 01:20)
        "max_questions": 0,
    },
    "commands": {
        "test": "",
        "deploy": "",
        "health": "",
        "logs_snapshot": "",
        "status": "",
        "probe_local": "",
        "probe_remote": "",
        "probe_wipe": "",
        "ingest_table_local": "",
        "ingest_table_remote": "",
        "ingest_docs": "",
        "myip": "",
    },
    "boot": {"checks": []},
    "guard": {
        "deny": [],
        "ask": [],
        "secret_files": [".env"],
        "env_editable": [],
        "protected_paths": [],
        # Folders nobody on the FDE side may read (rehearsal/arena answer keys). Absolute or project-relative.
        "sealed_paths": [],
        # Agent-type prefixes that may read sealed paths (e.g. the arena's persona actor and evaluators).
        "sealed_readers": [],
    },
    "paths": {
        "context_docs": [],
        "system_prompt": "",
        "requirements_dir": "",
        "tools_dir": "",
        "graph": "",
        "data_raw": "data/raw",
        "docs_dir": "data",
        "status_doc": "",
        "checklist": "",
    },
    "skills": {},
    "runtime": {"facts": {}, "fixed_decisions": []},
    "submission": {"checklist": []},
}

SWITCHES_LOCKED = {"verify"}  # the independent verification seat can never be switched off


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(p: P) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if p.binding.exists():
        with p.binding.open("rb") as fh:
            data = tomllib.load(fh)
    cfg = _merge(DEFAULTS, data)
    cfg["_binding_found"] = p.binding.exists()
    return cfg


def profile_path(cfg: dict) -> Path:
    name = (cfg.get("project") or {}).get("profile") or "generic"
    path = plugin_root() / "profiles" / f"{name}.md"
    return path if path.exists() else plugin_root() / "profiles" / "generic.md"


def template_binding(name: str, profile: str = "generic") -> str:
    """Starter project.toml written by `fde on` when a project has none."""
    return f'''# FDE-Mode project binding. Edit freely; the plugin reads it on every command.
[project]
name = "{name}"
profile = "{profile}"          # profiles/<name>.md inside the plugin
timezone = "Asia/Seoul"

[schedule]                     # leave date empty when there is no deadline
date = ""
start = "10:00"
end = "15:00"
core_freeze = "11:10"
full_freeze = "13:30"
feature_freeze = "14:15"
submit_by = "14:50"

[commands]                     # shell commands the build/QA/data agents may run
test = ""
deploy = ""
health = ""
logs_snapshot = ""

[guard]                        # regexes. deny = blocked, ask = needs your confirmation
deny = []
ask = []
secret_files = [".env"]
env_editable = []

[paths]
context_docs = ["README.md"]
'''
