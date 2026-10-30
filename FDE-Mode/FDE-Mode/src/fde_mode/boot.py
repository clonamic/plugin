"""P0 boot checks. Generic checks here; project checks come from the binding:

[[boot.checks]]
name = "AWS 로그인"
cmd = "aws sts get-caller-identity --query Account --output text"
expect = "^\\d{12}$"          # regex on stdout (optional)
timeout = 30
on_fail = "D1"                  # D1 | D2 | warn
hint = "aws login 후 다시"
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Any

from fde_mode import decisions as D, envtool
from fde_mode.state import Ctx
from fde_mode.util import iso, short

SCRUB = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|KakaoAK\s+\S+|[A-Za-z0-9_\-]{32,})")


def _run(cmd: str, cwd: str, timeout: int) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "AWS_PAGER": ""})
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return r.returncode, SCRUB.sub("[가림]", out.strip())
    except subprocess.TimeoutExpired:
        return 124, f"시간 초과({timeout}s)"


def run(ctx: Ctx, quick: bool = False) -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, on_fail: str = "warn", hint: str = "") -> None:
        results.append({"name": name, "ok": ok, "detail": short(detail, 300), "on_fail": on_fail, "hint": hint})

    v = sys.version_info
    add("Python ≥ 3.12 (FDE 자체)", v >= (3, 12), f"{v.major}.{v.minor}.{v.micro}", "D1",
        "uv python install 3.12 또는 brew install python@3.12")
    add("프로젝트 바인딩", ctx.cfg.get("_binding_found", False), str(ctx.p.binding), "D2",
        "project.toml 이 없으면 기본값으로만 동작합니다(명령·가드 규칙 없음)")
    if shutil.which("git"):
        code, out = _run("git status --porcelain | head -20", str(ctx.p.root), 10)
        add("git 작업 트리", code == 0, out or "깨끗함", "warn", "커밋되지 않은 변경은 되돌리기 기준점이 없습니다")
        code, out = _run("git describe --tags --match 'fde-good-*' --abbrev=0 2>/dev/null || echo '(없음)'", str(ctx.p.root), 10)
        add("마지막 정상 릴리스 태그", True, out, "warn")
    secret_keys = [k for k in (ctx.cfg.get("runtime") or {}).get("required_env", [])]
    if secret_keys:
        st = envtool.check(ctx.p.root, secret_keys)
        missing = [k for k, s in st.items() if s != "set"]
        add(".env 필수 키(set/empty만)", not missing, ", ".join(f"{k}={s}" for k, s in st.items()), "D1",
            "비어 있는 키를 채워 주세요(값은 출력하지 않습니다)")
    if not quick:
        for c in (ctx.cfg.get("boot") or {}).get("checks") or []:
            code, out = _run(c.get("cmd", "true"), str(ctx.p.root), int(c.get("timeout", 60)))
            ok = code == 0
            if ok and c.get("expect"):
                ok = re.search(c["expect"], out, re.M) is not None
            add(c.get("name", c.get("cmd", "")), ok, out, c.get("on_fail", "warn"), c.get("hint", ""))
    for r in results:
        if not r["ok"] and r["on_fail"] in ("D1", "D2"):
            D.add(ctx, title=f"[부팅 점검 실패] {r['name']}", grade=r["on_fail"],
                  context=f"{r['detail']} / 조치: {r['hint']}",
                  options=["지금 고치고 다시 점검", "무시하고 진행", "FDE 모드 끄기"],
                  recommended="지금 고치고 다시 점검", source="boot", blocking=["deploy"] if r["on_fail"] == "D1" else [])
    ctx.event("boot.checked", "", {"ok": sum(1 for r in results if r["ok"]), "fail": sum(1 for r in results if not r["ok"])})
    return {"checked_at": iso(), "results": results, "ok": all(r["ok"] or r["on_fail"] == "warn" for r in results)}
