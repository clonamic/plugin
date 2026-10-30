"""`fde next` — the workflow engine.

The organisation's flow is computed by code, not remembered by the model.
Pipelines are ordered stages. A stage first runs its deterministic scripts
(inside `fde next`, milliseconds) and then lists agent dispatches. The main
session (the director) launches exactly what `fde next` returns, then calls it
again. Outputs are files; a stage is complete when every dispatch has a valid
output (or failed twice). Several runs can be active at once (a quick round
while a debate round runs in the background, a build slice while data loads).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fde_mode import (asked, cite, config, db, decisions as D, metrics, rank, report, roster, sync,
                      transcript)
from fde_mode.paths import plugin_root
from fde_mode.roster import BY_NAME, CROSS_REVIEW, DIVISIONS
from fde_mode.state import Ctx, set_state, timeline
from fde_mode.util import iso, now, read_json, scrub, short, write_json

AGENT_PREFIX = os.environ.get("FDE_AGENT_PREFIX", "fde-mode:")
MAX_ATTEMPTS = 2


@dataclass
class Step:
    agent: str
    mode: str
    inputs: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    background: bool = True
    extra_writes: list[str] = field(default_factory=list)
    tag: str = ""  # disambiguates the same agent twice in one stage


@dataclass
class StageSpec:
    name: str
    scripts: list[Callable[[], None]] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    wait: dict | None = None
    goto: int | None = None          # jump to another stage index (loops: rework, next wave)
    end_status: str | None = None    # finish the run right here with this status


class Planner:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.p = ctx.p
        self.out: dict[str, Any] = {"dispatch": [], "ask": [], "notify": [], "waiting": [], "human": []}

    # ------------------------------------------------------------------ helpers
    def abs(self, rel: str | Path) -> str:
        return str((self.p.root / rel).resolve()) if not Path(rel).is_absolute() else str(rel)

    def rel(self, path: Path | str) -> str:
        return self.p.rel(path)

    def run_dir(self, run: dict) -> Path:
        d = self.p.runs / run["id"]
        d.mkdir(parents=True, exist_ok=True)
        return d

    def notify(self, text: str, kind: str = "info", ref: str = "") -> None:
        self.out["notify"].append({"kind": kind, "text": text, "ref": ref})
        self.ctx.event("notify", ref, {"kind": kind, "text": text})

    def on(self, switch: str) -> bool:
        return self.ctx.switch(switch)

    def division_on(self, key: str) -> bool:
        d = DIVISIONS.get(key)
        return True if (d is None or d.switch is None) else self.on(d.switch)

    def common_inputs(self, run: dict) -> dict[str, str]:
        snaps = report.snapshots(self.ctx)
        inputs = {
            "transcript": str(self.p.transcript),
            "board": str(self.p.board),
            "binding": str(self.p.binding),
            "requirements": snaps["requirements"],
            "questions": snaps["questions"],
            "decisions": snaps["decisions"],
            "assumptions": snaps["assumptions"],
        }
        if self.p.persona.exists():
            inputs["persona"] = str(self.p.persona)
        gl = self.p.docs / "glossary.json"
        if gl.exists():
            inputs["glossary"] = str(gl)
        for key, name in (("environment", "environment.md"), ("packaging", "packaging.md")):
            if (self.p.docs / name).exists():  # written by the 환경·패키징팀; every analyst designs inside it
                inputs[key] = str(self.p.docs / name)
        briefs = sorted(self.p.inbox.glob("*.brief.raw.md"))
        if briefs:
            inputs["brief"] = str(briefs[-1])
        m = self.latest_metrics()
        if m:
            inputs["metrics"] = m
        inputs["tests"] = snaps["tests"]
        inputs["risks"] = snaps["risks"]
        inputs["tasks"] = snaps["tasks"]
        smap = self.p.docs / "stage-map.json"
        if smap.exists() and self.on("stage_map"):  # stage map S1–S8, engagement type and role map (stage.check) — what each stage still lacks
            inputs["stage_map"] = str(smap)
        tfile = self.p.work / "snapshots" / "time.json"
        write_json(tfile, {"now": iso(), "timeline": timeline(self.ctx.cfg), "phase": self.ctx.state.get("phase"),
                           "round": self.ctx.state.get("round")})
        inputs["time"] = str(tfile)
        cost = db.one(self.ctx.conn, "SELECT output FROM dispatches WHERE agent='fde-cost-estimator' AND status='done' "
                                     "ORDER BY done_at DESC LIMIT 1")
        if cost:
            inputs["cost_estimates"] = self.abs(cost["output"])
        return inputs

    def stage_input(self) -> dict[str, str]:
        """docs/stage-map.json for the seats that do not get the common inputs (writer, sequencer, counter-arguer,
        engagement lead, design lead, release manager)."""
        f = self.p.docs / "stage-map.json"
        return {"stage_map": str(f)} if f.exists() and self.on("stage_map") else {}

    def notes_input(self) -> dict[str, str]:
        """The interviewer's own notes (dashboard) — only for the seats that compare them with the record (readback
        writer, doc auditor, interviewer coach). Never persona evidence."""
        f = self.p.docs / "interviewer-notes.md"
        return {"interviewer_notes": str(f)} if f.exists() else {}

    def latest_metrics(self) -> str | None:
        files = sorted(self.p.runs.glob("*/metrics.json"), key=lambda f: f.stat().st_mtime)
        return str(files[-1]) if files else None

    def outputs_of(self, run: dict, stage: int | None = None, mode: str | None = None,
                   agents: list[str] | None = None) -> dict[str, str]:
        q = "SELECT agent, mode, output, stage FROM dispatches WHERE run=? AND status='done'"
        rows = db.rows(self.ctx.conn, q, (run["id"],))
        res = {}
        for r in rows:
            if stage is not None and r["stage"] != stage:
                continue
            if mode and r["mode"] != mode:
                continue
            if agents and r["agent"] not in agents:
                continue
            key = f"{r['agent']}.{r['mode']}"
            n = 2
            while key in res:  # same agent+mode twice in a run (several tasks, retries): keep every output
                key = f"{r['agent']}.{r['mode']}.{n}"
                n += 1
            res[key] = self.abs(r["output"])
        return res

    def previous_output(self, agent: str, exclude_run: str) -> str | None:
        r = db.one(self.ctx.conn, "SELECT output FROM dispatches WHERE agent=? AND run<>? AND status='done' "
                                  "ORDER BY done_at DESC LIMIT 1", (agent, exclude_run))
        return self.abs(r["output"]) if r else None

    def round_range(self, rnd: str) -> str:
        r = db.one(self.ctx.conn, "SELECT first_u, last_u FROM rounds WHERE id=?", (rnd,))
        return f"{r['first_u']}–{r['last_u']}" if r else "-"

    # ------------------------------------------------------------------ runs
    def create_run(self, pipeline: str, rnd: str = "", run_id: str | None = None, **params: Any) -> str | None:
        rid = run_id or (f"{rnd}-{pipeline}" if rnd else pipeline.upper())
        if db.one(self.ctx.conn, "SELECT id FROM runs WHERE id=?", (rid,)):
            return None
        params.setdefault("materialized", [])
        params["started_at"] = iso()
        db.upsert(self.ctx.conn, "runs", {"id": rid, "pipeline": pipeline, "round": rnd, "status": "active", "stage": 0,
                                         "params": json.dumps(params, ensure_ascii=False), "created_at": iso(),
                                         "finished_at": None})
        self.ctx.event("run.created", rid, {"pipeline": pipeline, "round": rnd})
        return rid

    def save_run(self, run: dict) -> None:
        self.ctx.conn.execute("UPDATE runs SET stage=?, status=?, params=?, finished_at=? WHERE id=?",
                              (run["stage"], run["status"], json.dumps(run["params"], ensure_ascii=False),
                               run.get("finished_at"), run["id"]))

    def active_runs(self) -> list[dict]:
        rows = db.rows(self.ctx.conn, "SELECT * FROM runs WHERE status IN ('active','waiting') ORDER BY created_at")
        for r in rows:
            r["params"] = json.loads(r.get("params") or "{}")
        return rows

    # ------------------------------------------------------------------ triggers
    def triggers(self) -> None:
        st = self.ctx.refresh()
        if st.get("mode") != "on":
            return
        flags = st.get("flags") or {}
        # one analysis run per new round
        for r in db.rows(self.ctx.conn, "SELECT * FROM rounds WHERE status='new' ORDER BY n"):
            pipeline = {"brief": "brief", "note": "note", "transcript": "quick"}.get(r["kind"], "quick")
            if pipeline == "note":
                self.ctx.conn.execute("UPDATE rounds SET status='done', finished_at=? WHERE id=?", (iso(), r["id"]))
                continue
            if self.create_run(pipeline, r["id"]):
                self.ctx.conn.execute("UPDATE rounds SET status='analyzing' WHERE id=?", (r["id"],))
        # debate every N transcript rounds (after that round's quick run finished)
        every = int(self.ctx.cfg.get("interview", {}).get("debate_every", 3) or 0)
        if self.on("debate") and every > 0:
            done = db.rows(self.ctx.conn, "SELECT round FROM runs WHERE pipeline='quick' AND status='done'")
            tr = {r["id"]: r["n"] for r in db.rows(self.ctx.conn, "SELECT id, n FROM rounds WHERE kind='transcript'")}
            transcript_rounds = sorted(tr, key=lambda k: tr[k])
            for rd in done:
                pos = transcript_rounds.index(rd["round"]) + 1 if rd["round"] in transcript_rounds else 0
                if pos and pos % every == 0:
                    self.create_run("debate", rd["round"])
        # tech gate
        if self.on("tech_gate") and not flags.get("techgate_started") and st.get("phase") in ("P1", "P2"):
            if self.techgate_signal():
                if self.create_run("techgate", run_id="TG1"):
                    from fde_mode.state import set_state as _ss
                    _ss(self.ctx, flags={"techgate_started": True})
                    self.notify("핵심 요구사항이 안정돼 기술 결정 게이트를 엽니다(인터뷰는 계속).", "phase", "TG1")
        # freeze suggestion
        cooldown = int(flags.get("freeze_cooldown_round", -1))
        analysing = db.scalar(self.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline IN ('quick','brief') "
                                             "AND status IN ('active','waiting')", default=0)
        t_rounds = db.scalar(self.ctx.conn, "SELECT COUNT(*) FROM rounds WHERE kind='transcript' AND status='done'", default=0)
        min_rounds = int(self.ctx.cfg.get("interview", {}).get("min_rounds_before_freeze", 3))
        confirm = flags.get("core_freeze_confirm") or []
        done_at_defer = flags.get("freeze_cooldown_done")
        deferred = done_at_defer is not None or cooldown >= 0
        # a seat asked to start building early (`kind: build_start`, sync.not_executable): its decision is never asked
        # — the core freeze D1 is, at once (no round count, no cooldown), and the user hears why in one line. Once the
        # user has deferred ("인터뷰 계속") or asked to check cards first, a seat's request never overrides that choice:
        # one line, and the D1 comes back by the usual rule only
        req = flags.get("core_freeze_request") if not flags.get("core_frozen") else None
        if req and (deferred or confirm) and not flags.get("core_freeze_asked"):
            self.notify(f"제작은 핵심 동결 뒤에 시작됩니다 — '{short(req.get('title', ''), 60)}'({req.get('by', '')})은 실행하지 않습니다. "
                        "'제작 시작해도 될까요?'는 사용자가 고른 대로(다음 라운드 분석 뒤 / 확인 카드가 닫힌 뒤) 다시 묻습니다.", "phase")
            set_state(self.ctx, flags={"core_freeze_request": None})
            req = None
        elif flags.get("core_freeze_request") and (flags.get("core_frozen") or flags.get("core_freeze_asked")):
            if not flags.get("core_frozen"):
                self.notify(f"제작은 핵심 동결 뒤에 시작됩니다 — '{short(flags['core_freeze_request'].get('title', ''), 60)}'은 "
                            "실행하지 않습니다. 열려 있는 '제작 시작해도 될까요?'에 답해 주세요.", "phase")
            set_state(self.ctx, flags={"core_freeze_request": None})
            req = None
        elif req and not req.get("noted"):
            self.notify(f"제작은 핵심 동결 뒤에 시작됩니다 — '{short(req.get('title', ''), 60)}'({req.get('by', '')})은 실행하지 않고 "
                        "'제작 시작해도 될까요?'를 바로 묻습니다.", "phase")
            req = {**req, "noted": True}
            set_state(self.ctx, flags={"core_freeze_request": req})
        for v in flags.get("void_notices") or []:
            self.notify(f"실행하지 않는 결정으로 기록했습니다: '{short(str(v.get('title', '')), 60)}'({v.get('by', '')}) — "
                        "제작 시작과 다시 판단하는 시점은 '제작 시작해도 될까요?'와 플래너 규칙으로만 정해집니다.", "decision", v.get("decision", ""))
        if flags.get("void_notices"):
            set_state(self.ctx, flags={"void_notices": []})
        tl = timeline(self.ctx.cfg)
        # deferred ("인터뷰 계속"): judged again after the next interview round's analysis is done — counted in finished
        # transcript rounds, so a round already pasted when the user deferred is that next round
        round_ok = (t_rounds > int(done_at_defer)) if done_at_defer is not None else int(st.get("round") or 0) > cooldown
        # and once on the clock: the planned full-freeze time passed without a core freeze — asked again, never forced
        time_reask = (deferred and not flags.get("core_freeze_time_reasked")
                      and "full_freeze" in tl and tl["full_freeze"]["min_left"] <= 0)
        if (not flags.get("core_frozen") and not flags.get("core_freeze_asked") and st.get("phase") in ("P1", "P2")
                and (confirm or req or time_reask or round_ok) and not analysing):
            chk = report.freeze_check(self.ctx, "core")
            late = "core_freeze" in tl and tl["core_freeze"]["min_left"] <= 0
            confirmed = self.confirm_closed(confirm)
            if confirm and not confirmed and not late and not req:
                pass  # the user asked to check these first: no new freeze question until they are closed
            elif (chk["pass"] and t_rounds >= min_rounds and not confirm) or late or confirmed or req or time_reask:
                n = int(db.scalar(self.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline='freeze'", default=0)) + 1
                if self.create_run("freeze", run_id=f"FZ-core-{n}", level="core", forced_by_time=bool(late and not chk["pass"]),
                                   after_confirm=confirmed, requested=req, time_reask=bool(time_reask and not round_ok)):
                    set_state(self.ctx, flags={"core_freeze_asked": True, "core_freeze_confirm": [], "core_freeze_request": None,
                                               **({"core_freeze_time_reasked": True} if time_reask else {})})
        # full freeze is started by the user (`fde run freeze --level full`); "이것만 더 확인하고 동결" re-asks it here
        fconfirm = flags.get("full_freeze_confirm") or []
        if fconfirm and flags.get("core_frozen") and not flags.get("full_frozen") and not analysing:
            tl = timeline(self.ctx.cfg)
            if self.confirm_closed(fconfirm) or ("full_freeze" in tl and tl["full_freeze"]["min_left"] <= 0):
                n = int(db.scalar(self.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline='freeze'", default=0)) + 1
                if self.create_run("freeze", run_id=f"FZ-full-{n}", level="full", after_confirm=True):
                    set_state(self.ctx, flags={"full_freeze_confirm": []})
        # data: new raw files
        if self.division_on("data"):
            raw = self.p.root / (self.ctx.cfg.get("paths", {}).get("data_raw") or "data/raw")
            if raw.is_dir():
                known = {r["path"] for r in db.rows(self.ctx.conn, "SELECT path FROM data_assets")}
                new = [f for f in sorted(raw.rglob("*")) if f.is_file() and not f.name.startswith(".")
                       and self.rel(f) not in known]
                if new:
                    n = int(db.scalar(self.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline='data'", default=0)) + 1
                    rid = f"DATA-{n:02d}"
                    for f in new:
                        db.upsert(self.ctx.conn, "data_assets", {"id": db.next_id(self.ctx.conn, "data_assets", "DA-"),
                                                                "name": f.name, "path": self.rel(f), "kind": f.suffix.lstrip("."),
                                                                "source": "received", "status": "received", "rows": None,
                                                                "report": "", "notes": "", "updated_at": iso()})
                    self.create_run("data", run_id=rid, files=[self.rel(f) for f in new])
                    self.notify(f"새 데이터 파일 {len(new)}개 → 데이터 본부가 검증·정제·적재를 시작합니다 ({rid}).", "data", rid)
        # change control: frozen requirements changed or a new must appeared after core freeze
        pend = flags.get("pending_changes") or []
        if pend and st.get("phase") in ("P3", "P4", "P5"):
            n = int(db.scalar(self.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline='change'", default=0)) + 1
            text = "; ".join(f"{c['requirement']}: {c.get('before') or '(신규 must)'} → {c.get('after')}" for c in pend)[:1500]
            if self.create_run("change", run_id=f"CH-{n:02d}", text=text):
                set_state(self.ctx, flags={"pending_changes": []})
                self.notify(f"동결된 요구사항이 바뀌었거나 새 must가 생겼습니다 → 변경 영향 분석(CH-{n:02d})", "phase", f"CH-{n:02d}")
        # closing at feature freeze time — also when the core freeze never happened (P1/P2): whatever is deployed
        # now is what gets submitted, so final QA, the demo and the submission checklist must still run
        tl = timeline(self.ctx.cfg)
        if ("feature_freeze" in tl and tl["feature_freeze"]["min_left"] <= 0 and not flags.get("feature_frozen")
                and st.get("phase") in ("P1", "P2", "P3", "P4", "P5")):
            unfrozen = st.get("phase") in ("P1", "P2") and not flags.get("core_frozen")
            if self.create_run("closing", run_id="CLOSING", unfrozen=unfrozen):
                if unfrozen:
                    report.spec(self.ctx)  # final QA and the demo read spec.md; write it from today's requirements
                set_state(self.ctx, phase="P6", flags={"feature_frozen": True})
                self.notify("기능 동결 시각입니다. 마감 모드로 전환합니다: 새 기능 금지, 안정화·데모·제출 준비."
                            + (" 핵심 동결 없이 왔으므로 지금 배포돼 있는 것이 제출본입니다 — 최종 QA로 확인합니다." if unfrozen else ""),
                            "phase", "CLOSING")

    def confirm_closed(self, qids: list[str]) -> bool:
        """The "이것만 더 확인" cards are all closed (answered, assumed or dropped)."""
        return bool(qids) and not db.scalar(
            self.ctx.conn, f"SELECT COUNT(*) FROM questions WHERE status IN ('open','held') AND id IN ({','.join('?' * len(qids))})",
            tuple(qids), 0)

    def techgate_signal(self) -> bool:
        musts = db.rows(self.ctx.conn, "SELECT id, changed_round FROM requirements WHERE priority='must'")
        if len(musts) < 2:
            tl = timeline(self.ctx.cfg)
            return "core_freeze" in tl and tl["core_freeze"]["min_left"] <= 30
        last = int(self.ctx.state.get("round") or 0)
        changed = [m for m in musts if m.get("changed_round") and int(str(m["changed_round"]).lstrip("R") or 0) >= last - 1]
        tl = timeline(self.ctx.cfg)
        return (not changed and last >= 3) or ("core_freeze" in tl and tl["core_freeze"]["min_left"] <= 30)

    # ------------------------------------------------------------------ engine
    def step(self) -> dict[str, Any]:
        self.triggers()
        # a stage script may create runs (freeze → BUILDPLAN, change → replan, QA → fix slice): advance those in the
        # same call, or the director sees "idle" and stops while new work sits unlaunched until the next message
        advanced: set[str] = set()
        for second in (False, True):
            if second:
                # P-02 (problem 1): triggers ran only before the runs advanced, so a round whose analysis finished in
                # this call opened its freeze re-judgement (or the clock's re-ask) only on the next call — and an
                # unattended director stops at the first idle reply, after which the next paste is "analysing" again.
                # Look once more now; the triggers are idempotent (run ids and flags)
                self.triggers()
            for _ in range(6):
                fresh = [r for r in self.active_runs() if r["id"] not in advanced]
                if not fresh:
                    break
                for run in fresh:
                    advanced.add(run["id"])
                    self.advance(run)
        # decisions to ask now (D1 first). They stay 'new' until answered or deferred.
        pend = D.pending(self.ctx, statuses=("new",))
        for d in pend:
            self.ctx.conn.execute("UPDATE decisions SET blocking=blocking WHERE id=?", (d["id"],))
        self.out["ask"] = [{"id": d["id"], "grade": d["grade"], "title": d["title"], "context": d["context"],
                            "options": d["options"], "recommended": d["recommended"]} for d in pend[:4]]
        if pend:
            flags = self.ctx.refresh().get("flags") or {}
            surfaced = set(flags.get("surfaced_decisions") or []) | {d["id"] for d in pend[:4]}
            set_state(self.ctx, flags={"surfaced_decisions": sorted(surfaced)})
        self.out["idle"] = not (self.out["dispatch"] or self.out["ask"] or self.out["waiting"])
        self.out["active_runs"] = [{"id": r["id"], "pipeline": r["pipeline"], "stage": r["stage"]}
                                   for r in self.active_runs()]
        return self.out

    def advance(self, run: dict) -> None:
        stages = PIPELINES.get(run["pipeline"])
        if not stages:
            run["status"] = "failed"
            self.save_run(run)
            return
        guard = 0
        while guard < 40:
            guard += 1
            idx = run["stage"]
            if idx >= len(stages):
                run["status"], run["finished_at"] = "done", iso()
                self.save_run(run)
                self.finish(run)
                return
            mat = run["params"].setdefault("materialized", [])
            if idx not in mat:
                spec = stages[idx](self, run)
                if spec.wait:
                    run["status"] = "waiting"
                    self.save_run(run)
                    self.out["waiting"].append({"run": run["id"], **spec.wait})
                    return
                run["status"] = "active"
                for fn in spec.scripts:
                    fn()
                if spec.end_status:
                    run["status"], run["finished_at"] = spec.end_status, iso()
                    self.save_run(run)
                    self.finish(run)
                    return
                if spec.goto is not None:
                    run["stage"] = spec.goto
                    run["params"]["materialized"] = [m for m in mat if m < spec.goto]
                    self.save_run(run)
                    continue
                for i, s in enumerate(spec.steps):
                    self.add_dispatch(run, idx, s, i)
                mat.append(idx)
                run["params"].setdefault("stage_names", {})[str(idx)] = spec.name
                self.save_run(run)
            disp = db.rows(self.ctx.conn, "SELECT * FROM dispatches WHERE run=? AND stage=?", (run["id"], idx))
            for d in disp:
                if d["status"] == "issued":
                    self.check(d)
            disp = db.rows(self.ctx.conn, "SELECT * FROM dispatches WHERE run=? AND stage=?", (run["id"], idx))
            stale_min = int(self.ctx.cfg.get("interview", {}).get("stale_minutes", 25))
            for d in disp:
                if d["status"] == "issued" and d["issued_at"]:
                    age = (now() - __import__("datetime").datetime.fromisoformat(d["issued_at"])).total_seconds() / 60
                    if age > stale_min:
                        if d["attempts"] < MAX_ATTEMPTS:
                            self.ctx.conn.execute("UPDATE dispatches SET status='planned', error=? WHERE id=?",
                                                  ("출력이 오지 않아 다시 보냅니다(시간 초과)", d["id"]))
                        else:
                            self.ctx.conn.execute("UPDATE dispatches SET status='failed', error=? WHERE id=?",
                                                  ("시간 초과 2회", d["id"]))
            disp = db.rows(self.ctx.conn, "SELECT * FROM dispatches WHERE run=? AND stage=?", (run["id"], idx))
            for d in disp:
                if d["status"] == "planned":
                    self.issue(d)
            if all(d["status"] in ("done", "failed", "skipped") for d in disp):
                failed = [d for d in disp if d["status"] == "failed"]
                if failed:
                    self.notify(f"{run['id']} 단계 {idx}: {len(failed)}개 에이전트 출력 실패 → 건너뛰고 진행 "
                                f"({', '.join(d['agent'] for d in failed)})", "warn", run["id"])
                run["stage"] = idx + 1
                self.save_run(run)
                continue
            return

    def add_dispatch(self, run: dict, idx: int, s: Step, i: int) -> None:
        short = s.agent.removeprefix("fde-") + (f".{s.tag}" if s.tag else "") + (f".{s.mode}" if s.mode not in ("analyze",) else "")
        did = f"{run['id']}.{idx}.{short}"
        out = self.run_dir(run) / f"{idx:02d}-{short}.json"
        if out.exists():  # re-run of the same stage (rework, next wave): keep history, never reuse
            k = 1
            while out.with_suffix(f".prev{k}.json").exists():
                k += 1
            out.rename(out.with_suffix(f".prev{k}.json"))
        db.upsert(self.ctx.conn, "dispatches", {
            "id": did, "run": run["id"], "stage": idx, "agent": s.agent, "mode": s.mode, "output": self.rel(out),
            "status": "planned", "attempts": 0, "background": int(s.background), "issued_at": None, "done_at": None,
            "summary": None, "error": None, "inputs": json.dumps(s.inputs, ensure_ascii=False), "notes": s.notes,
            "extra_writes": json.dumps(s.extra_writes, ensure_ascii=False), "created_at": iso(),
        })

    def check(self, d: dict) -> None:
        data, errs = sync.load_output(self.ctx, d)
        if data is None:
            if errs == ["output file not written"]:
                return
            if d["attempts"] < MAX_ATTEMPTS:
                self.ctx.conn.execute("UPDATE dispatches SET status='planned', error=? WHERE id=?", ("; ".join(errs), d["id"]))
            else:
                self.ctx.conn.execute("UPDATE dispatches SET status='failed', error=? WHERE id=?", ("; ".join(errs), d["id"]))
            return
        try:
            sync.apply(self.ctx, d, data)
        except Exception as e:  # never let one bad file stop the organisation
            self.ctx.event("sync.error", d["id"], {"error": repr(e)})
        self.ctx.conn.execute("UPDATE dispatches SET status='done', done_at=?, summary=?, error=NULL WHERE id=?",
                              (iso(), scrub(data.get("summary_ko") or "")[:400], d["id"]))

    def issue(self, d: dict) -> None:
        self.ctx.conn.execute("UPDATE dispatches SET status='issued', attempts=attempts+1, issued_at=? WHERE id=?",
                              (iso(), d["id"]))
        a = BY_NAME.get(d["agent"])
        # Unattended runs (autopilot, headless `claude -p`) cannot rely on background notifications.
        autopilot = bool((self.ctx.state.get("flags") or {}).get("autopilot"))
        self.out["dispatch"].append({
            "id": d["id"],
            "subagent_type": AGENT_PREFIX + d["agent"],
            "agent": d["agent"],
            "title": f"{a.ko if a else d['agent']} · {d['mode']}",
            "background": bool(d["background"]) and not autopilot,
            "prompt": self.render(d),
        })

    def render(self, d: dict) -> str:
        a = BY_NAME.get(d["agent"])
        run = db.one(self.ctx.conn, "SELECT * FROM runs WHERE id=?", (d["run"],)) or {}
        inputs = json.loads(d.get("inputs") or "{}")
        refs = plugin_root() / "skills" / "fde-director" / "references"
        lines = [
            f"FDE DISPATCH {d['id']}",
            f"Role: {d['agent']} ({a.ko if a else ''}) · mode: {d['mode']} · run: {d['run']} ({run.get('pipeline', '')})"
            + (f" · round: {run.get('round')}" if run.get("round") else ""),
            f"Project root: {self.p.root}",
            "Read first (contract and rules — do not skip):",
            f"- {refs / 'contract.md'}",
            f"- {refs / 'rubric.md'}",
            f"- {config.profile_path(self.ctx.cfg)}",
            "Inputs:",
        ]
        for k, v in inputs.items():
            lines.append(f"- {k}: {v}")
        if run.get("round"):
            lines.append(f"New utterances this round: {self.round_range(run['round'])}")
        lines.append(f"Write exactly one JSON file: {self.abs(d['output'])}")
        lines.append(f'  envelope: {{"schema": "fde.out.v1", "agent": "{d["agent"]}", "mode": "{d["mode"]}", "run": "{d["run"]}", ...}}')
        stem = str(self.abs(d["output"])).removesuffix(".json")
        lines.append(f"Scratch files (optional: probe logs, collected replies): {stem}.<name> — next to the output, never elsewhere.")
        extra = json.loads(d.get("extra_writes") or "[]")
        if extra:
            lines.append("You may also write/overwrite (and only these): " + ", ".join(self.abs(x) for x in extra))
        if d.get("notes"):
            lines.append("Notes: " + d["notes"])
        if d.get("error"):
            lines.append(f"Your previous attempt was rejected: {d['error']}. Fix exactly that.")
        lines.append("Files: write the output and any document with the Write tool — never with a Bash heredoc or redirect "
                     "(`cat > … <<EOF`, `echo … >`, `tee`): the guard reads shell command text and may refuse it. "
                     "Give `rm`/`mv`/`git rm` paths relative to the project root, not absolute.")
        lines.append("Decisions: never raise one the planner cannot carry out — starting part of the build before the core freeze, "
                     "or a promise about when the freeze is judged again. To start early, mark it `\"kind\": \"build_start\"` "
                     "(it becomes the core freeze D1 '제작 시작해도 될까요?'); contract §2.")
        lines.append("Examples: " + EXAMPLE_RULE)
        lines.append("Reply to the director with at most 3 short Korean lines plus the output path. Never paste the JSON back.")
        return "\n".join(lines)

    def finish(self, run: dict) -> None:
        self.ctx.event("run.done", run["id"], {"pipeline": run["pipeline"]})
        if run["pipeline"] in ("quick", "debate", "brief") and run.get("round"):
            self.ctx.conn.execute("UPDATE rounds SET status='done', finished_at=? WHERE id=? AND status<>'done'",
                                  (iso(), run["round"]))


# ====================================================================== stages
# Each stage function returns a StageSpec. Scripts run once when the stage starts.

def _prep(pl: Planner, run: dict) -> StageSpec:
    def go() -> None:
        report.snapshots(pl.ctx)
        if run.get("round"):
            asked.detect(pl.ctx, run["round"])
            # early pass: marker counts and question types of THIS round (areas/tags fill in after tagging)
            metrics.compute(pl.ctx, run["round"], pl.run_dir(run) / "metrics.json")
    return StageSpec("준비", scripts=[go])


# ---------- quick round ----------

def q_scribe(pl: Planner, run: dict) -> StageSpec:
    low = db.scalar(pl.ctx.conn, "SELECT COUNT(*) FROM utterances WHERE round=? AND parse_conf < 0.7", (run["round"],), 0)
    if not low:
        return StageSpec("기록(생략: 화자 확실)")
    inputs = {"raw": pl.abs(db.scalar(pl.ctx.conn, "SELECT raw_path FROM rounds WHERE id=?", (run["round"],), "")),
              "transcript": str(pl.p.transcript), "questions": str(pl.p.work / "snapshots" / "questions.json")}
    return StageSpec("기록", steps=[Step("fde-scribe", "scribe", inputs, background=False,
                                       notes="Fix only speakers/splits of this round's low-confidence utterances (parse_conf < 0.7).")])


def q_analyze(pl: Planner, run: dict) -> StageSpec:
    base = pl.common_inputs(run)
    steps = [Step("fde-utterance-tagger", "tag", {"transcript": base["transcript"]}, background=False),
             Step("fde-topic-classifier", "topic", {"transcript": base["transcript"]}, background=False)]
    names = list(roster.QUICK_ANALYSTS)
    names.remove("fde-interviewer-coach")  # needs metrics → next stage
    data_hit = db.scalar(pl.ctx.conn, "SELECT COUNT(*) FROM utterances WHERE round=? AND (text LIKE '%데이터%' OR text LIKE '%엑셀%' "
                                      "OR text LIKE '%파일%' OR text LIKE '%자료%' OR text LIKE '%기록%' OR text LIKE '%장부%')",
                         (run["round"],), 0)
    if data_hit and pl.division_on("data"):
        names.append("fde-data-sourcing-planner")
    for n in names:
        if not pl.division_on(BY_NAME[n].division):
            continue
        inp = dict(base)
        prev = pl.previous_output(n, run["id"])
        if prev:
            inp["your_previous_output"] = prev
        extra = _EXTRA_WRITES(pl).get(n, [])
        steps.append(Step(n, "analyze", inp, background=False, extra_writes=extra))
    return StageSpec("빠른 분석", steps=steps)


def candidates_index(pl: Planner, run: dict) -> Path:
    """All raw candidates of this run (and of a reused quick run) with their database ids."""
    runs = [run["id"]]
    quick = db.one(pl.ctx.conn, "SELECT id FROM runs WHERE pipeline='quick' AND round=? AND id<>?", (run.get("round"), run["id"]))
    if run["pipeline"] == "debate" and quick and run["params"].get("reused"):
        runs.append(quick["id"])
    rows = []
    for r in runs:
        rows += db.rows(pl.ctx.conn, "SELECT id, agent, division, kind, area, gap, evidence, quote, question_draft, "
                                     "decision_at_stake, if_wrong, self_confidence, impact_guess, status FROM candidates "
                                     "WHERE run=? AND status='new' AND kind NOT IN ('risk','decision')", (r,))
    # questions the engagement lead derived from perspective conflicts last time: verified now, like everything else
    carry = db.rows(pl.ctx.conn, "SELECT id, agent, division, kind, area, gap, evidence, quote, question_draft, "
                                 "decision_at_stake, if_wrong, self_confidence, impact_guess, status FROM candidates "
                                 "WHERE status='carry'")
    for c in carry:
        pl.ctx.conn.execute("UPDATE candidates SET status='new', run=? WHERE id=?", (run["id"], c["id"]))
        c["status"] = "new"
    rows += carry
    for c in rows:
        c["evidence"] = json.loads(c.get("evidence") or "[]")
    path = pl.run_dir(run) / "candidates.json"
    write_json(path, {"run": run["id"], "count": len(rows), "candidates": rows})
    return path


def q_post(pl: Planner, run: dict) -> StageSpec:
    d = pl.run_dir(run)

    def go() -> None:
        metrics.compute(pl.ctx, run["round"], d / "metrics.json")
        asked.detect(pl.ctx, run["round"])
        report.snapshots(pl.ctx)
        candidates_index(pl, run)
    steps = []
    if pl.division_on("comms"):
        inp = {**pl.common_inputs(run), **pl.notes_input()}
        inp["metrics"] = str(d / "metrics.json")
        steps.append(Step("fde-interviewer-coach", "analyze", inp, background=False))
    steps.append(Step("fde-candidate-merger", "merge",
                      {"candidates": str(d / "candidates.json"),
                       "questions": str(pl.p.work / "snapshots" / "questions.json"),
                       "assumptions": str(pl.p.work / "snapshots" / "assumptions.json"),
                       "transcript": str(pl.p.transcript)},
                      background=False, notes="Use the ids from candidates.json in members. Every candidate must end up in exactly one group."))
    return StageSpec("지표·통합", scripts=[go], steps=steps)


def _verify_stage(pl: Planner, run: dict, background: bool, with_audit: bool = False) -> StageSpec:
    d = pl.run_dir(run)

    def go() -> None:
        cite.run(pl.ctx, run["round"], d / "cite.json")
        report.blind_pack(pl.ctx, run["id"], d / "blind.json")
    base = {"candidates": str(d / "blind.json"), "transcript": str(pl.p.transcript),
            "requirements": str(pl.p.work / "snapshots" / "requirements.json"),
            "questions": str(pl.p.work / "snapshots" / "questions.json"), "binding": str(pl.p.binding)}
    steps = [Step("fde-blind-verifier", "verify", dict(base), background=background,
                  notes="Independent seat: you get no debate records and no proposer identity. Judge every candidate."),
             Step("fde-counter-arguer", "counter", {**base, **pl.stage_input()}, background=background,
                  notes="Argue the strongest case for NOT asking each candidate. Judge every candidate.")]
    if with_audit:
        docs = {"persona": str(pl.p.persona), "requirements": base["requirements"],
                "spec": str(pl.p.spec), "glossary": str(pl.p.docs / "glossary.json"),
                "personalization_map": str(pl.p.docs / "personalization-map.md")}
        steps.append(Step("fde-doc-auditor", "audit", {**{k: v for k, v in docs.items() if Path(v).exists()},
                                                       **pl.notes_input()}, background=background))
    return StageSpec("독립 검증", scripts=[go], steps=steps)


def q_verify(pl: Planner, run: dict) -> StageSpec:
    return _verify_stage(pl, run, background=False)


def _cards_stage(pl: Planner, run: dict, background: bool, kind: str) -> StageSpec:
    d = pl.run_dir(run)
    top = int(pl.ctx.cfg.get("interview", {}).get("top_cards", 5))

    def go() -> None:
        rank.rank(pl.ctx, run["round"], run["id"], top, d / "ranked.json")
        report.snapshots(pl.ctx)
    style = pl.previous_output("fde-decision-style", "") or ""
    steps = []
    # question writing is never switched off: without it the user gets raw lens drafts
    inp = {"ranked": str(d / "ranked.json"), "transcript": str(pl.p.transcript)}
    if pl.p.persona.exists():
        inp["persona"] = str(pl.p.persona)
    if style:
        inp["decision_style"] = style
    if (pl.p.docs / "glossary.json").exists():
        inp["glossary"] = str(pl.p.docs / "glossary.json")
    steps.append(Step("fde-question-writer", "write", {**inp, **pl.stage_input()}, background=background))
    lead_in = {**pl.common_inputs(run), "ranked": str(d / "ranked.json")}
    if (d / "metrics.json").exists():
        lead_in["metrics"] = str(d / "metrics.json")
    lead_in.update({f"out:{k}": v for k, v in pl.outputs_of(run).items()
                    if any(x in k for x in ("coach", "position", "ruling", "registrar", "consistency", "scope"))})
    steps.append(Step("fde-engagement-lead", "opening" if kind == "brief" else "conclude", {**lead_in, **pl.stage_input()},
                      background=background))
    return StageSpec("질문 카드·결론", scripts=[go], steps=steps)


def q_cards(pl: Planner, run: dict) -> StageSpec:
    return _cards_stage(pl, run, background=False, kind="quick")


def _report_stage(pl: Planner, run: dict, kind_ko: str) -> StageSpec:
    d = pl.run_dir(run)

    def go() -> None:
        # decisions deferred with `fde defer` are asked again with this report ("다음 보고 때 다시 묻는다")
        n = pl.ctx.conn.execute("UPDATE decisions SET status='new' WHERE status='asked'").rowcount
        if n:
            pl.ctx.event("decision.reopened", run["id"], {"count": n})
        ranked = read_json(d / "ranked.json")
        if pl.on("stage_map"):  # round end: stage map, gap/depth cards, "go back?" D2 — never moves P
            try:
                from fde_mode import stage
                stage.check(pl.ctx, run["round"])
            except Exception as e:  # noqa: BLE001 — the round report must come out whatever the check does
                pl.ctx.event("stage.error", run["round"], {"error": repr(e)})
        text = report.round_report(pl.ctx, run["id"], run["round"], ranked, run["params"].get("started_at"),
                                   d / "report.md", kind_ko)
        report.board(pl.ctx)
        pl.out.setdefault("reports", []).append({"run": run["id"], "path": str(d / "report.md"), "text": text})
        pl.notify(f"{run['round']} {kind_ko} 보고서가 나왔습니다: {pl.rel(d / 'report.md')}", "report", run["id"])
    return StageSpec("보고", scripts=[go])


def q_report(pl: Planner, run: dict) -> StageSpec:
    return _report_stage(pl, run, "빠른 분석")


# ---------- debate round ----------

def _analysts(pl: Planner) -> list[str]:
    names = []
    for a in roster.AGENTS:
        if "analyze" not in a.modes or a.head or a.division in ("command", "verify", "intake"):
            continue
        if a.division in ("persona", "problem", "solution", "risk", "strategy", "comms", "data") and pl.division_on(a.division):
            names.append(a.name)
    return names


def d_analyze(pl: Planner, run: dict) -> StageSpec:
    base = pl.common_inputs(run)
    steps = []
    reused = []
    quick = db.one(pl.ctx.conn, "SELECT id FROM runs WHERE pipeline='quick' AND round=? AND status='done'", (run["round"],))
    for n in _analysts(pl):
        if quick and BY_NAME[n].quick:
            prev = db.one(pl.ctx.conn, "SELECT output FROM dispatches WHERE run=? AND agent=? AND status='done'", (quick["id"], n))
            if prev:
                reused.append((n, prev["output"]))
                continue
        inp = dict(base)
        prev = pl.previous_output(n, run["id"])
        if prev:
            inp["your_previous_output"] = prev
        extra = _EXTRA_WRITES(pl).get(n, [])
        steps.append(Step(n, "analyze", inp, background=True, extra_writes=extra))

    def reuse() -> None:
        run["params"]["reused"] = {n: o for n, o in reused}
    return StageSpec("개별 분석", scripts=[reuse], steps=steps)


def _EXTRA_WRITES(pl: Planner) -> dict[str, list[str]]:
    return {"fde-glossary-keeper": [pl.rel(pl.p.docs / "glossary.json")],
            "fde-personalization-strategist": [pl.rel(pl.p.docs / "personalization-map.md")],
            "fde-simulated-user-writer": [pl.rel(pl.p.docs / "simulated-messages.json")],
            "fde-demo-scenario": [pl.rel(pl.p.docs / "demo-scenario.md")],
            "fde-requirements-registrar": [pl.rel(pl.p.docs / "requirements.md")],
            "fde-environment-analyst": [pl.rel(pl.p.docs / "environment.md")],
            "fde-packaging-strategist": [pl.rel(pl.p.docs / "packaging.md")]}


def _run_outputs_for(pl: Planner, run: dict, agent: str) -> list[str]:
    outs = [v for k, v in pl.outputs_of(run).items() if k.startswith(agent + ".")]
    reused = (run["params"].get("reused") or {}).get(agent)
    if reused:
        outs.append(pl.abs(reused))
    return outs


def d_complement(pl: Planner, run: dict) -> StageSpec:
    if not pl.on("team_complement"):
        return StageSpec("팀 내 보완(꺼짐)")
    steps = []
    for n in _analysts(pl):
        mates = roster.team_mates(n)
        if not mates:
            continue
        own = _run_outputs_for(pl, run, n)
        if not own:
            continue
        inp = {"your_output": own[0], "transcript": str(pl.p.transcript)}
        for m in mates:
            for i, o in enumerate(_run_outputs_for(pl, run, m)):
                inp[f"teammate:{m}:{i}"] = o
        steps.append(Step(n, "complement", inp, background=True, extra_writes=_EXTRA_WRITES(pl).get(n, []),
                          notes="Read your teammates' outputs once. Add only what becomes visible when you combine them, "
                                "or revise your own items with a reason (\"revises\": \"<your earlier local id>\"). Never restate."))
    return StageSpec("팀 내 보완", steps=steps)


def d_position(pl: Planner, run: dict) -> StageSpec:
    steps = []
    for key in ("persona", "problem", "solution", "risk", "strategy", "comms", "data"):
        if not pl.division_on(key):
            continue
        head = DIVISIONS[key].head
        members = [a.name for a in roster.AGENTS if a.division == key and not a.head and "analyze" in a.modes]
        inp = {**pl.common_inputs(run)}
        for m in members:
            for i, o in enumerate(_run_outputs_for(pl, run, m)):
                inp[f"member:{m}:{i}"] = o
        extra = [pl.rel(pl.p.persona)] if key == "persona" else []
        steps.append(Step(head, "position", inp, background=True, extra_writes=extra,
                          notes="Integrate your teams into one division position. Show disagreements between your teams; do not hide them."))
    return StageSpec("본부 입장", steps=steps)


def _position_file(pl: Planner, run: dict, key: str) -> str | None:
    head = DIVISIONS[key].head
    outs = pl.outputs_of(run, mode="position", agents=[head])
    return next(iter(outs.values()), None)


def d_review(pl: Planner, run: dict) -> StageSpec:
    by_reviewer: dict[str, list[tuple[str, str]]] = {}
    for rev, tgt, q in CROSS_REVIEW:
        if not pl.division_on(rev):
            continue
        targets = [k for k in ("persona", "problem", "solution", "risk", "strategy", "data") if k != rev] if tgt == "*" else [tgt]
        for t in targets:
            if pl.division_on(t) and _position_file(pl, run, t):
                by_reviewer.setdefault(rev, []).append((t, q))
    steps = []
    for rev, items in by_reviewer.items():
        head = DIVISIONS[rev].head
        inp = {"transcript": str(pl.p.transcript)}
        own = _position_file(pl, run, rev)
        if own:
            inp["your_position"] = own
        for t, _ in items:
            inp[f"target:{t}"] = _position_file(pl, run, t) or ""
        qs = "; ".join(f"{t}: {q}" for t, q in items)
        steps.append(Step(head, "review", inp, background=True, tag="rev",
                          notes=f"Cross-review. Questions to answer per target — {qs}. Agreement must carry a reason and an addition."))
    return StageSpec("교차 검토", steps=steps)


def d_rebuttal(pl: Planner, run: dict) -> StageSpec:
    reviews = db.rows(pl.ctx.conn, "SELECT agent, output FROM dispatches WHERE run=? AND mode='review' AND status='done'", (run["id"],))
    steps = []
    for key in ("persona", "problem", "solution", "risk", "strategy", "data"):
        if not pl.division_on(key) or not _position_file(pl, run, key):
            continue
        inp = {"your_position": _position_file(pl, run, key), "transcript": str(pl.p.transcript)}
        for r in reviews:
            inp[f"review_by:{r['agent']}"] = pl.abs(r["output"])
        steps.append(Step(DIVISIONS[key].head, "rebuttal", inp, background=True, tag="reb",
                          extra_writes=[pl.rel(pl.p.persona)] if key == "persona" else [],
                          notes=f"Answer only the review points aimed at the '{key}' division: 수용 / 부분 수용 / 반론, each with evidence."))
    return StageSpec("반박 응답", steps=steps)


def d_ruling(pl: Planner, run: dict) -> StageSpec:
    files = db.rows(pl.ctx.conn, "SELECT agent, mode, output FROM dispatches WHERE run=? AND mode IN ('position','review','rebuttal') "
                                 "AND status='done'", (run["id"],))
    inp = {"transcript": str(pl.p.transcript), "board": str(pl.p.board)}
    for f in files:
        inp[f"{f['mode']}:{f['agent']}"] = pl.abs(f["output"])
    return StageSpec("중재", steps=[Step("fde-arbiter", "ruling", inp, background=True,
                                       extra_writes=[pl.rel(pl.p.docs / "minority-opinions.md")])])


def d_merge(pl: Planner, run: dict) -> StageSpec:
    d = pl.run_dir(run)
    inp = {"candidates": str(d / "candidates.json"), "questions": str(pl.p.work / "snapshots" / "questions.json"),
           "assumptions": str(pl.p.work / "snapshots" / "assumptions.json"), "transcript": str(pl.p.transcript)}
    for k, v in pl.outputs_of(run, mode="ruling").items():
        inp[f"ruling:{k}"] = v

    def go() -> None:
        report.snapshots(pl.ctx)
        candidates_index(pl, run)
    return StageSpec("후보 통합", scripts=[go],
                     steps=[Step("fde-candidate-merger", "merge", inp, background=True,
                                 notes="Use the ids from candidates.json in members. Rulings tell you which conflicts were settled.")])


def d_verify(pl: Planner, run: dict) -> StageSpec:
    return _verify_stage(pl, run, background=True, with_audit=True)


def d_cards(pl: Planner, run: dict) -> StageSpec:
    spec = _cards_stage(pl, run, background=True, kind="debate")
    n = int(pl.ctx.state.get("round") or 0)
    every = int(pl.ctx.cfg.get("interview", {}).get("readback_every", 3) or 0)
    if every and n % every == 0:
        spec.steps.append(Step("fde-readback-writer", "readback", {**pl.common_inputs(run), **pl.notes_input()},
                               background=True))
    rulings = pl.outputs_of(run, mode="ruling")
    clerk_in = {"transcript": str(pl.p.transcript), **{f"ruling:{k}": v for k, v in rulings.items()}}
    for m in ("position", "review", "rebuttal"):
        clerk_in.update({f"{m}:{k}": v for k, v in pl.outputs_of(run, mode=m).items()})
    spec.steps.append(Step("fde-chief-clerk", "minutes", clerk_in,
                           background=True, extra_writes=[pl.rel(pl.p.docs / "stance-history.md"),
                                                          pl.rel(pl.p.docs / "minutes" / f"{run['id']}.md")]))
    return spec


def d_sequence(pl: Planner, run: dict) -> StageSpec:
    d = pl.run_dir(run)
    inp = {"ranked": str(d / "ranked.json"), "questions": str(pl.p.work / "snapshots" / "questions.json"),
           "transcript": str(pl.p.transcript)}
    return StageSpec("질문 순서", scripts=[lambda: report.snapshots(pl.ctx)],
                     steps=[Step("fde-question-sequencer", "sequence", {**inp, **pl.stage_input()}, background=True)])


def d_report(pl: Planner, run: dict) -> StageSpec:
    return _report_stage(pl, run, "토론 라운드")


# ---------- brief (problem statement) ----------

def b_analyze(pl: Planner, run: dict) -> StageSpec:
    base = pl.common_inputs(run)
    raw = db.scalar(pl.ctx.conn, "SELECT raw_path FROM rounds WHERE id=?", (run["round"],), "")
    base["brief"] = pl.abs(raw)
    steps = [Step(n, "brief", dict(base), background=False, extra_writes=_EXTRA_WRITES(pl).get(n, [])) for n in
             ("fde-judge-perspective", "fde-domain-expert", "fde-scope-manager", "fde-platform-constraints",
              "fde-data-sourcing-planner", "fde-environment-analyst", "fde-packaging-strategist")
             if pl.division_on(BY_NAME[n].division)]
    return StageSpec("문제 설명 분석", steps=steps)


def b_merge(pl: Planner, run: dict) -> StageSpec:
    d = pl.run_dir(run)
    inp = {"candidates": str(d / "candidates.json"), "transcript": str(pl.p.transcript)}
    return StageSpec("후보 통합", scripts=[lambda: candidates_index(pl, run)],
                     steps=[Step("fde-candidate-merger", "merge", inp, background=False)])


def b_cards(pl: Planner, run: dict) -> StageSpec:
    return _cards_stage(pl, run, background=False, kind="brief")


def b_report(pl: Planner, run: dict) -> StageSpec:
    return _report_stage(pl, run, "문제 설명 분석")


# ---------- tech gate ----------

def t_items(pl: Planner, run: dict) -> StageSpec:
    d = pl.run_dir(run)

    def go() -> None:
        fixed = pl.ctx.cfg.get("runtime", {}).get("fixed_decisions") or []
        facts = pl.ctx.cfg.get("runtime", {}).get("facts") or {}
        open_items = pl.ctx.cfg.get("runtime", {}).get("open_items") or [
            "그래프 구조 변경 범위(기존 그래프에 노드·도구 추가 vs 새 분기)",
            "데이터 배치(표·문서·사람별 기억을 어디에)",
            "인물 데이터의 공용/전용 배치",
            "외부 API 추가 여부(당일 키 확보 가능성)",
            "대화 방식(버튼 중심 vs 자유 입력 중심)",
            "봇이 먼저 메시지 보내기(선제 발송) 사용 여부",
            "처음 들어온 사용자(심사자) 처리 방식",
        ]
        write_json(d / "items.json", {"fixed": fixed, "facts": facts, "open_items": open_items,
                                      "note": "fixed 항목은 다시 논의하지 않는다. open_items와 요구사항에서 나온 항목만 다룬다."})
        report.snapshots(pl.ctx)
    base = {**pl.common_inputs(run), "items": str(d / "items.json")}
    ctxdocs = pl.ctx.cfg.get("paths", {}).get("context_docs") or []
    for i, doc in enumerate(ctxdocs):
        base[f"context_doc:{i}"] = pl.abs(doc)
    steps = [Step(n, "tech", dict(base), background=True) for n in
             ("fde-runtime-architect", "fde-data-architect", "fde-integration-specialist", "fde-platform-constraints",
              "fde-cost-estimator", "fde-packaging-strategist")]
    return StageSpec("기술 제안", scripts=[go], steps=steps)


def t_challenge(pl: Planner, run: dict) -> StageSpec:
    inp = {f"proposal:{k}": v for k, v in pl.outputs_of(run, mode="tech").items()}
    inp["requirements"] = str(pl.p.work / "snapshots" / "requirements.json")
    return StageSpec("반대 위원 검토", steps=[Step("fde-tech-devils-advocate", "challenge", inp, background=True)])


def t_decide(pl: Planner, run: dict) -> StageSpec:
    inp = {f"{k}": v for k, v in pl.outputs_of(run).items()}
    inp["requirements"] = str(pl.p.work / "snapshots" / "requirements.json")
    inp["binding"] = str(pl.p.binding)
    return StageSpec("위원장 결정", steps=[Step("fde-tech-lead", "decide", inp, background=True,
                                           extra_writes=[pl.rel(pl.p.tech) + "/ADR-*.md"])])


def t_done(pl: Planner, run: dict) -> StageSpec:
    def go() -> None:
        pl.notify("기술 결정 기록(ADR)이 나왔습니다. D1/D2 기술 결정은 바로 여쭙겠습니다.", "phase", run["id"])
    return StageSpec("완료", scripts=[go])


# ---------- freeze ----------

def f_check(pl: Planner, run: dict) -> StageSpec:
    d = pl.run_dir(run)
    level = run["params"].get("level", "core")

    def go() -> None:
        chk = report.freeze_check(pl.ctx, level)
        chk["forced_by_time"] = bool(run["params"].get("forced_by_time"))  # the clock, not readiness, opened this run
        chk["requested"] = run["params"].get("requested")  # a seat asked to start building early
        chk["time_reask"] = bool(run["params"].get("time_reask"))
        chk["timing"] = round_timing(pl.ctx)  # this run's measured minutes, not a fixed guess
        write_json(d / "check.json", chk)
        report.spec(pl.ctx)
        report.snapshots(pl.ctx)
    inp = {**pl.common_inputs(run), "check": str(d / "check.json"), "spec_draft": str(pl.p.spec)}
    steps = [Step("fde-freeze-judge", "freeze", inp, background=False)]
    if pl.p.persona.exists():
        steps.append(Step("fde-doc-auditor", "audit", {"spec": str(pl.p.spec), "persona": str(pl.p.persona),
                                                       "requirements": inp["requirements"], **pl.notes_input()},
                          background=False))
    return StageSpec("동결 판단", scripts=[go], steps=steps)


# Industry neutrality (contract §2, fde-director): every dispatch carries the same sentence.
EXAMPLE_RULE = ("예시는 형식만 보여 준다. 예시의 업종·명사·기능을 가져오지 않는다. 기능·데이터·수치 제안은 인물 발화(U)·"
                "받은 자료(DA)·브리프에 근거하고, 근거 없는 업종 지식은 '추측'으로 표시하고, 설계를 바꾸면 확인 질문으로 올린다.")


# W4: the core freeze is asked as "may we start building?" with the organisation's confidence basis and the missing
# information; the user can also ask for the few items that would change the build to be checked first.
FREEZE_OPTIONS = {
    "core": ["제작 시작", "이것만 더 확인하고 시작", "인터뷰 계속", "막는 항목만 가정으로 처리하고 시작"],
    "full": ["전체 동결", "이것만 더 확인하고 동결", "인터뷰 계속", "막는 항목만 가정으로 처리하고 동결"],
}
FREEZE_REC = {"freeze": 0, "confirm_first": 1, "wait": 2, "freeze_with_assumptions": 3}
_FREEZE_WORDS = {"제작 시작", "제작 시작해", "제작 시작해요", "제작 시작할게요", "제작 시작해 주세요", "시작", "시작해",
                 "시작해요", "시작할게요", "네 시작", "예 시작", "전체 동결", "지금 동결", "동결", "동결해", "동결해요",
                 "동결할게요", "네 동결", "예 동결"}


def round_timing(ctx) -> dict[str, Any]:
    """Measured minutes of this run's interview rounds for the freeze judge: analysis (quick/brief run), and the gap
    between consecutive pasted transcript rounds (asking + pasting + waiting) — one more round costs about the larger."""
    def mins(a: str | None, b: str | None) -> float | None:
        try:
            return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60, 1)
        except (TypeError, ValueError):
            return None
    runs = db.rows(ctx.conn, "SELECT pipeline, created_at, finished_at FROM runs WHERE pipeline IN ('quick','brief') "
                             "AND status='done' ORDER BY created_at")
    quick = [m for r in runs if r["pipeline"] == "quick" for m in [mins(r["created_at"], r["finished_at"])] if m is not None][-3:]
    brief = [m for r in runs if r["pipeline"] == "brief" for m in [mins(r["created_at"], r["finished_at"])] if m is not None]
    pasted = [r["created_at"] for r in db.rows(ctx.conn, "SELECT created_at FROM rounds WHERE kind='transcript' ORDER BY n")]
    gaps = [m for a, b in zip(pasted, pasted[1:]) for m in [mins(a, b)] if m is not None][-3:]
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None  # noqa: E731
    qa, ga = avg(quick), avg(gaps)
    return {"quick_analysis_min": qa, "brief_analysis_min": brief[-1] if brief else None, "between_pastes_min": ga,
            "one_more_round_min": max([x for x in (qa, ga) if x is not None], default=None),
            "rounds_measured": len(quick)}


def _freeze_choice(ans: str) -> str | None:
    """Map the answer to the freeze decision onto its options ("(추천)" tails are ignored). Anything else is asked
    again — free text must never start the build by accident (H-03)."""
    a = " ".join((ans or "").replace("(추천)", " ").split()).strip(" .!")
    if a.startswith(("아직", "인터뷰 계속")):
        return "wait"
    if a.startswith(("막는 항목만", "막는 항목은")):
        return "freeze_assume"
    if a.startswith("이것만 더 확인"):
        return "confirm_first"
    if a in _FREEZE_WORDS or a.startswith("지금 동결 "):
        return "freeze"
    return None


def _freeze_context(verdict: dict, chk: dict) -> str:
    """The numbers behind the judge's confidence (code-counted where possible) and what is still missing."""
    basis = verdict.get("confidence_basis") if isinstance(verdict.get("confidence_basis"), dict) else {}
    conf = verdict.get("internal_confidence") or basis.get("internal_confidence")
    if conf not in ("확실", "가능성 높음", "추측"):
        conf = ("가능성 높음" if chk.get("pass") else "추측") + "(코드 추정)"
    musts = chk.get("must", 0)
    parts = [f"내부 확신 [{conf}]",
             f"must 근거 {chk.get('must_with_evidence', basis.get('must_with_evidence', '-'))}/{musts}",
             f"영향 높음 열린 질문 {chk.get('open_high_impact', basis.get('open_high_impact', '-'))}",
             f"지금 시작하면 가정으로 넘어갈 질문 {len(chk.get('would_assume_if_frozen') or [])}",
             f"막는 항목 {len(chk.get('blockers') or [])}"]
    by_view = basis.get("blockers_by_perspective")
    if isinstance(by_view, dict) and by_view:
        parts.append("관점별 막는 허점 " + ", ".join(f"{k} {v}" for k, v in list(by_view.items())[:5]))
    lines = [" · ".join(parts)]
    req = chk.get("requested") if isinstance(chk.get("requested"), dict) else None
    if req:
        lines.append(f"요청: {req.get('by', '')} — '{short(str(req.get('title', '')), 80)}'(그 결정은 실행하지 않고 이 질문으로 묻습니다)")
    if chk.get("time_reask"):
        lines.append("전체 동결 계획 시각이 지나 한 번 더 묻습니다(강제 동결 아님 — '인터뷰 계속'도 고를 수 있습니다)")
    if verdict.get("reason"):
        lines.append("판단: " + verdict["reason"])
    blockers = verdict.get("blockers") or chk.get("blockers") or []
    if blockers:
        lines.append("막는 항목: " + "; ".join(map(str, blockers[:5])))
    missing = [m for m in verdict.get("missing_info") or [] if isinstance(m, dict) and m.get("info")]
    if missing:
        lines.append("부족한 정보: " + "; ".join(f"{m['info']}(받으면: {m.get('would_change') or '-'})" for m in missing[:3]))
    return " / ".join(lines)


def f_ask(pl: Planner, run: dict) -> StageSpec:
    level = run["params"].get("level", "core")
    did = run["params"].get("decision")
    opts = FREEZE_OPTIONS["full" if level == "full" else "core"]
    if not did:
        judge = pl.outputs_of(run, mode="freeze")
        verdict = {}
        for p in judge.values():
            verdict = (read_json(p) or {}).get("freeze") or {}
        chk = read_json(pl.run_dir(run) / "check.json") or {}
        rec = opts[FREEZE_REC.get(verdict.get("recommend"), 2)]
        run["params"]["missing_info"] = [m for m in verdict.get("missing_info") or [] if isinstance(m, dict) and m.get("info")][:5]
        title = "제작 시작해도 될까요? (핵심 동결)" if level == "core" else "확장 기능까지 닫아도 될까요? (전체 동결)"
        did = D.add(pl.ctx, title=title, grade="D1", context=_freeze_context(verdict, chk), options=list(opts),
                    recommended=rec, source="fde-freeze-judge", blocking=[f"{level}_freeze"])
        run["params"]["decision"] = did
        pl.save_run(run)
    row = db.one(pl.ctx.conn, "SELECT * FROM decisions WHERE id=?", (did,))
    if not row or row["status"] not in ("answered",):
        return StageSpec("사용자 승인 대기", wait={"decision": did, "text": "제작 시작(동결) 여부 결정을 기다립니다"})
    ans = (row["answer"] or "").strip()
    choice = _freeze_choice(ans)
    if choice is None:  # free text ("조금 더 물어보고요") must never freeze by accident: ask again
        pl.ctx.conn.execute("UPDATE decisions SET status='new', answer=NULL, answered_at=NULL, context=? WHERE id=?",
                            (f"(앞의 답 '{ans[:60]}'은 선택지와 달라 다시 묻습니다) " + (row["context"] or ""), did))
        pl.ctx.event("decision.reasked", did, {"answer": ans}, actor="fde")
        return StageSpec("사용자 승인 대기", wait={"decision": did, "text": "제작 시작(동결) 여부를 선택지로 다시 묻습니다"})
    if choice == "wait":
        def no() -> None:
            done = db.scalar(pl.ctx.conn, "SELECT COUNT(*) FROM rounds WHERE kind='transcript' AND status='done'", default=0)
            set_state(pl.ctx, flags={f"{level}_freeze_asked": False, "freeze_cooldown_done": int(done),
                                     "freeze_cooldown_round": int(pl.ctx.refresh().get("round") or 0)})
            ff = (timeline(pl.ctx.cfg).get("full_freeze") or {}).get("at")
            pl.notify("제작 시작을 미뤘습니다. 인터뷰를 계속합니다 — 다음 판단은 다음 대화 라운드의 분석이 끝난 뒤"
                      + (f"(늦어도 전체 동결 계획 {ff}에 한 번 더 묻습니다)" if ff and level == "core" else "") + ".", "phase", run["id"])
        return StageSpec("동결 보류", scripts=[no])
    if choice == "confirm_first":
        def confirm() -> None:
            rnd = f"R{int(pl.ctx.refresh().get('round') or 0):02d}"
            made = []
            for i, m in enumerate(run["params"].get("missing_info") or [], 1):
                qid = db.next_id(pl.ctx.conn, "questions", "Q-")
                db.upsert(pl.ctx.conn, "questions", {
                    "id": qid, "round": rnd, "candidate": f"{run['id']}:missing:{i}", "text": m.get("question") or m["info"],
                    "confidence": m.get("confidence") or "가능성 높음", "impact": "높음", "bucket": "ask",
                    "flags": json.dumps(["제작 전 확인"], ensure_ascii=False), "evidence": "[]",
                    "decision_at_stake": m.get("would_change") or "", "lens": "{}", "verifier": "{}", "counter": "{}",
                    "ord": i, "status": "open", "asked_u": None, "answer_us": "[]", "updated_at": iso()})
                made.append((qid, m.get("question") or m["info"]))
                if i >= 3:
                    break
            deferral = {} if made else {  # no card to wait for: a plain deferral, not an immediate re-ask
                "freeze_cooldown_done": int(db.scalar(pl.ctx.conn, "SELECT COUNT(*) FROM rounds WHERE kind='transcript' "
                                                                   "AND status='done'", default=0)),
                "freeze_cooldown_round": int(pl.ctx.refresh().get("round") or 0)} if level == "core" else {}
            set_state(pl.ctx, flags={f"{level}_freeze_asked": False, f"{level}_freeze_confirm": [q for q, _ in made], **deferral})
            again = "제작 시작해도 될까요?" if level == "core" else "확장 기능까지 닫아도 될까요?"
            pl.notify((f"먼저 확인할 질문을 카드로 올렸습니다 — 답을 받으면 '{again}'를 다시 묻습니다: "
                       + " / ".join(f"{q} {short(t, 60)}" for q, t in made)) if made else
                      "판단관이 부족한 정보를 적지 않아 확인할 질문이 없습니다. 인터뷰를 계속합니다 — 다음 판단은 다음 대화 라운드의 분석이 끝난 뒤.",
                      "phase", run["id"])
        return StageSpec("제작 전 확인", scripts=[confirm])

    def yes() -> None:
        pl.ctx.event("freeze.applied", level, {"run": run["id"], "choice": choice, "decision": did})
        pl.ctx.conn.execute("UPDATE requirements SET frozen=1 WHERE priority IN ('must'" + (",'should'" if level == "full" else "") + ")")
        if choice == "freeze_assume":
            pl.ctx.conn.execute("UPDATE questions SET status='assumed' WHERE status IN ('open','held')")
        report.spec(pl.ctx)
        if level == "core":
            set_state(pl.ctx, phase="P4", flags={"core_frozen": True})
            if not pl.on("build"):  # H-13: the build organisation is switched off — spec only, nobody builds
                pl.notify("제작 시작(핵심 동결) → spec.md 확정. 구현 스위치(build)가 꺼져 있어 구현 조직은 출발하지 않습니다"
                          "(켜려면 fde switch build on 뒤 fde run buildplan).", "phase", run["id"])
                return
            pl.create_run("buildplan", run_id="BUILDPLAN")
            pl.notify("제작 시작(핵심 동결) → spec.md 확정, 구현 조직 출발. 인터뷰는 확장 기능 위주로 계속(P5)."
                      + (" 협업 모드: 조각마다 설계 확인·진행 확인을 여쭙니다." if _collab(pl) else " 자율 모드: 추천대로 진행합니다."),
                      "phase", run["id"])
        else:
            set_state(pl.ctx, flags={"full_frozen": True})
            pl.notify("전체 동결 완료. 이후 새 요구는 변경 통제로만 들어갑니다.", "phase", run["id"])
    return StageSpec("동결 적용", scripts=[yes])


# ---------- collaboration mode (default; `autonomy` on only when the user says so) ----------

def _collab(pl: Planner) -> bool:
    return not pl.on("autonomy")


def _answered(pl: Planner, did: str) -> dict | None:
    row = db.one(pl.ctx.conn, "SELECT * FROM decisions WHERE id=?", (did,))
    return row if row and row["status"] in ("answered", "auto") else None


def _opt(o: Any) -> str:
    return str(o.get("option") or o.get("label") or o.get("title") or json.dumps(o, ensure_ascii=False)) if isinstance(o, dict) else str(o)


def _collab_ask(pl: Planner, run: dict, title: str, options: list, recommended: str, context: str = "",
                grade: str = "D2", capped: bool = True) -> str:
    """One collaboration question of this slice. By default every one is asked (no cap: the user decides until they
    turn autonomy on). A positive `[collab].max_questions` lets design questions past that many D2s take the
    recommendation (D3, listed); 0, a negative or an unreadable value means no cap. D1 and the slice's own checkpoints
    (first deploy, progress — `capped=False`) are always asked."""
    try:
        cap = int(pl.ctx.cfg.get("collab", {}).get("max_questions") or 0)
    except (TypeError, ValueError):
        cap = 0
    asked = run["params"].setdefault("collab_asked", [])
    if grade != "D1" and capped and cap > 0 and len(asked) >= cap:
        grade = "D3"
    did = D.add(pl.ctx, title=title, grade=grade, context=context[:600], options=[_opt(o) for o in options],
                recommended=recommended, source="planner")
    if grade == "D3":
        run["params"].setdefault("auto_recommended", []).append(f"{did} {title} → {recommended}")
        pl.notify(f"질문 상한({cap}개)을 넘어 추천으로 진행합니다: {title} → {recommended} ({did}, 바꾸려면 말씀해 주세요)",
                  "decision", did)
    elif grade == "D2" and capped and did not in asked:
        asked.append(did)
    return did


DESIGN_GO, DESIGN_CHANGE, DESIGN_HOLD = "이대로 구현", "설계 수정 요청(무엇을 바꿀지 적어 주세요)", "보류(이 조각은 지금 만들지 않음)"
# only "보류…" holds the slice (a held slice ends and is not revived); a bare no or a pause ("아니요", "잠깐만요") says
# neither what to change nor to drop it — asked again with the three options. Anything else goes back to the designers
DESIGN_UNCLEAR = {"아니요", "아니오", "아니", "아뇨", "안 돼요", "안돼요", "잠깐", "잠깐만", "잠깐만요", "잠시만", "잠시만요",
                  "멈춰", "멈춰 주세요", "중지", "그만"}


def s_design_confirm(pl: Planner, run: dict) -> StageSpec:
    """Collaboration: the designers' decision points (options, trade-offs, minutes, recommendation) go to the user
    before anyone implements. Autonomy takes the recommendations. Either way the choices reach the developers."""
    s = run["params"].get("slice")
    choices = pl.run_dir(run) / "design-choices.json"
    ids = run["params"].get("design_decisions")
    if ids is None:
        points = []
        for path in pl.outputs_of(run, mode="design").values():
            design = (read_json(path) or {}).get("design") or {}
            points += [x for x in design.get("decision_points") or [] if isinstance(x, dict) and x.get("title") and x.get("options")]
        if not _collab(pl):
            write_json(choices, {"slice": s, "mode": "autonomy", "choices": [
                {"title": x["title"], "answer": _opt(x.get("recommended") or x["options"][0]), "by": "추천(자율 모드)"} for x in points]})
            return StageSpec(f"설계 확인(자율 모드: 추천 {len(points)}개 적용)")
        ids = []
        for x in points:
            ctx_txt = " · ".join(t for t in (str(x.get("tradeoffs") or ""), f"예상 {x['effort_min']}분" if x.get("effort_min") else "") if t)
            ids.append(_collab_ask(pl, run, f"[설계·조각 {s}] {x['title']}", x["options"], _opt(x.get("recommended") or x["options"][0]),
                                   context=ctx_txt, grade="D1" if x.get("grade") == "D1" else "D2"))
        if not points:  # no fork left open: one go/no-go on the slice design itself, with the redesign door open
            lead = next(((read_json(p) or {}).get("design") or {} for k, p in pl.outputs_of(run, mode="design").items()
                         if k.startswith("fde-design-lead.")), {})
            gist = " · ".join(t for t in (str(lead.get("goal") or ""), f"파일 {len(lead.get('files') or [])}개" if lead.get("files") else "") if t)
            run["params"]["design_check"] = _collab_ask(
                pl, run, f"[설계·조각 {s}] 이 설계대로 구현할까요?", [DESIGN_GO, DESIGN_CHANGE, DESIGN_HOLD], DESIGN_GO,
                context=(gist or "설계 결정점 없음") + " — 바꿀 점이 있으면 한 문장으로 적어 주세요",
                capped=not run["params"].get("design_feedback"))  # asking again after a redesign does not use the cap
            ids.append(run["params"]["design_check"])
        run["params"]["design_decisions"] = ids
        pl.save_run(run)
    waiting = [i for i in ids if not _answered(pl, i)]
    if waiting:
        return StageSpec("설계 확인 대기", wait={"decision": waiting[0], "text": f"조각 {s} 설계 결정 {len(waiting)}개의 답을 기다립니다"})

    check = run["params"].get("design_check")
    if check in ids:
        row = _answered(pl, check)
        ans = " ".join((row["answer"] or "").replace("(추천)", "").split()).strip(" .!")
        if ans in (DESIGN_CHANGE, "설계 수정 요청"):  # the label alone says nothing to change: ask again for the words
            pl.ctx.conn.execute("UPDATE decisions SET status='new', answer=NULL, answered_at=NULL, context=? WHERE id=?",
                                ("(무엇을 바꿀지 한 문장으로 적어 주세요) " + (row["context"] or ""), check))
            return StageSpec("설계 확인 대기", wait={"decision": check, "text": "바꿀 점을 기다립니다"})
        if ans in DESIGN_UNCLEAR:
            pl.ctx.conn.execute("UPDATE decisions SET status='new', answer=NULL, answered_at=NULL, context=? WHERE id=?",
                                (f"(앞의 답 '{ans}'은 이대로 구현·수정 요청·보류 중 어느 것인지 알 수 없어 다시 묻습니다 — "
                                 "바꿀 점이 있으면 한 문장으로) " + (row["context"] or ""), check))
            return StageSpec("설계 확인 대기", wait={"decision": check, "text": "설계 확인을 선택지로 다시 묻습니다"})
        if ans.startswith("보류"):
            def hold() -> None:
                pl.notify(f"조각 {s} 설계를 보류했습니다({row['answer']}). 이 조각은 만들지 않고 지금 배포된 버전을 유지합니다. "
                          "다시 하려면 변경 통제로 말씀해 주세요.", "phase", run["id"])
            return StageSpec("설계 보류(사용자)", scripts=[hold], end_status="failed")
        if ans not in (DESIGN_GO, "이대로", "진행", "구현", "네", "예") and len(run["params"].get("design_feedback") or []) >= 2:
            pl.notify(f"조각 {s} 설계 수정은 두 번까지입니다 — 이번 요청은 다시 설계하지 않고 개발자에게 설계 메모로 넘깁니다: "
                      f"'{short(ans, 60)}'", "decision", check)
        if ans not in (DESIGN_GO, "이대로", "진행", "구현", "네", "예") and len(run["params"].get("design_feedback") or []) < 2:
            def redesign() -> None:  # the user's own words go back to the designers (at most twice per slice)
                run["params"].setdefault("design_feedback", []).append(ans.removeprefix("설계 수정 요청").strip(" :()"))
                run["params"]["design_decisions"] = None
                run["params"].pop("design_check", None)
            return StageSpec("설계 수정 요청 → 다시 설계", scripts=[redesign], goto=PIPELINES["slice"].index(s_design))

    def go() -> None:
        rows = [_answered(pl, i) for i in ids]
        write_json(choices, {"slice": s, "mode": "collaboration", "choices": [
            {"decision": r["id"], "title": r["title"], "answer": r["answer"], "by": "사용자" if r["status"] == "answered" else "추천(질문 상한)"}
            for r in rows if r]})
    return StageSpec(f"설계 확인({len(ids)}개)" if ids else "설계 확인(결정점 없음)", scripts=[go])


def _design_choices(pl: Planner, run: dict) -> dict[str, str]:
    f = pl.run_dir(run) / "design-choices.json"
    return {"design_choices": str(f)} if f.exists() else {}


def s_impl_questions(pl: Planner, run: dict) -> StageSpec:
    """A developer who meets a design choice parks the task (`tasks_blocked` with a `design_question`) instead of
    deciding alone. Raise each as a collaboration question, wait, then send the task back with the answer."""
    parked = []
    for t in _slice_tasks(pl, run):
        notes = json.loads(t.get("notes") or "{}")
        if t["status"] == "blocked" and isinstance(notes.get("design_question"), dict):
            parked.append((t, notes))
    if not parked:
        return StageSpec("구현 중 설계 질문 없음")
    for t, notes in parked:
        if not notes.get("design_decision"):
            q = notes["design_question"]
            opts = q.get("options") or ["추천안대로", "다른 방법(적어 주세요)"]
            # a task that keeps parking itself is not asked a third time: the recommendation decides (D3, listed)
            third = len(notes.get("design_answers") or []) >= 2
            notes["design_decision"] = _collab_ask(
                pl, run, f"[구현 중 설계·{t['id']}] {q['title']}", opts, _opt(q.get("recommended") or opts[0]),
                context=f"{t['title']} — {q.get('why') or q.get('tradeoffs') or '개발자가 혼자 정하지 않고 묻습니다'}",
                grade="D3" if third else "D2")
            pl.ctx.conn.execute("UPDATE tasks SET notes=? WHERE id=?", (json.dumps(notes, ensure_ascii=False), t["id"]))
    pl.save_run(run)
    waiting = [n["design_decision"] for _, n in parked if not _answered(pl, n["design_decision"])]
    if waiting:
        return StageSpec("구현 중 설계 질문 대기", wait={"decision": waiting[0], "text": f"구현 중 설계 질문 {len(waiting)}개의 답을 기다립니다"})

    def back() -> None:
        review = run["params"].setdefault("review_notes", {})
        for t, notes in parked:
            row = _answered(pl, notes["design_decision"])
            review[t["id"]] = (f"사용자 설계 답({row['id']}): {notes['design_question']['title']} → {row['answer']}"
                               + (" — 이 작업은 이미 두 번 물었습니다. 남은 갈림길은 추천안으로 정하고 다시 막지 마세요."
                                  if len(notes.get("design_answers") or []) >= 1 else ""))
            notes.setdefault("design_answers", []).append({"decision": row["id"], "answer": row["answer"]})
            notes.pop("design_question", None)
            notes.pop("design_decision", None)
            pl.ctx.conn.execute("UPDATE tasks SET status='rework', notes=? WHERE id=?",
                                (json.dumps(notes, ensure_ascii=False), t["id"]))
    return StageSpec("설계 답 반영 → 다시 구현", scripts=[back], goto=PIPELINES["slice"].index(s_implement))


def s_progress(pl: Planner, run: dict) -> StageSpec:
    """Collaboration: after a slice passes QA the user says how to go on — next slice, a fix request (in their own
    words → change control), or a design review (→ replan) — before the next slice starts. Autonomy skips it."""
    if not _collab(pl) or not run["params"].get("qa_pass"):
        return StageSpec("진행 확인(생략)")
    s = run["params"].get("slice")
    did = run["params"].get("progress_decision")
    nxt = db.scalar(pl.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline='slice' AND status IN ('active','waiting') AND id<>?",
                    (run["id"],), 0)
    go_on = "다음 조각 진행" if nxt else "이대로 유지(남은 조각 없음)"
    fix = "수정 요청(무엇을 고칠지 적어 주세요)"
    if not did:
        did = _collab_ask(pl, run, f"조각 {s} 배포·QA 통과. 다음은 어떻게 할까요?", [go_on, fix, "설계 재검토"], go_on,
                          context=f"사람 확인: {' / '.join(run['params'].get('human_checks') or []) or '-'}", capped=False)
        run["params"]["progress_decision"] = did
        pl.save_run(run)
    row = _answered(pl, did)
    if not row:
        return StageSpec("진행 확인 대기", wait={"decision": did, "text": f"조각 {s} 다음 진행 방법을 기다립니다"})
    ans = " ".join((row["answer"] or "").replace("(추천)", "").split()).strip(" .!")
    if ans in (go_on, "다음 조각 진행", "이대로 유지(남은 조각 없음)", "다음 조각", "다음 조각으로", "계속", "진행", "이대로", "이대로 유지"):
        return StageSpec("진행 확인: 계속")
    if ans in ("설계 재검토", "설계 재검토해", "설계 재검토해 주세요"):
        return StageSpec("진행 확인: 설계 재검토", scripts=[lambda: pl.create_run(
            "replan", run_id=f"RP-{run['id']}-review", source=run["id"], design_review=True)])
    if ans in (fix, "수정 요청"):  # the label alone says nothing to fix: ask again for the words
        pl.ctx.conn.execute("UPDATE decisions SET status='new', answer=NULL, answered_at=NULL, context=? WHERE id=?",
                            ("(무엇을 고칠지 한 문장으로 적어 주세요) " + (row["context"] or ""), did))
        return StageSpec("진행 확인 대기", wait={"decision": did, "text": "고칠 내용을 기다립니다"})

    def change() -> None:
        n = int(db.scalar(pl.ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline='change'", default=0)) + 1
        rid = pl.create_run("change", run_id=f"CH-{n:02d}", text=f"조각 {s} 뒤 사용자 수정 요청: {ans.removeprefix('수정 요청').strip(' :()')}"[:1500])
        pl.notify(f"수정 요청을 변경 통제로 넘깁니다({rid}): {short(ans, 80)}", "phase", rid or "")
    return StageSpec("진행 확인: 수정 요청", scripts=[change])


_DEPLOY_YES = {"배포", "배포해", "배포해요", "배포할게요", "배포해 주세요", "네 배포", "예 배포", "네", "예", "응", "좋아요", "진행", "진행해"}


def _deploy_confirm(pl: Planner, run: dict) -> StageSpec | None:
    """Collaboration: the first deploy, and the first deploy after a rollback, wait for the user's go."""
    if not _collab(pl):
        return None
    last_deploy = db.scalar(pl.ctx.conn, "SELECT MAX(done_at) FROM dispatches WHERE agent='fde-deploy-operator' AND status='done'")
    last_rb = db.scalar(pl.ctx.conn, "SELECT MAX(finished_at) FROM runs WHERE pipeline='rollback' AND status='done'")
    if last_deploy and not (last_rb and last_rb >= last_deploy) and not run["params"].get("deploy_decision"):
        return None
    s = run["params"].get("slice")
    did = run["params"].get("deploy_decision")
    if not did:
        why = "첫 배포" if not last_deploy else "되돌린 뒤 첫 배포"
        cmd = pl.ctx.cfg.get("commands", {}).get("deploy") or "(바인딩 deploy 명령)"
        did = _collab_ask(pl, run, f"조각 {s}을 배포할까요? ({why})", ["배포", "보류(이유를 적어 주세요)"], "배포",
                          context=f"리뷰 통과. 배포 명령: {cmd} → 헬스 확인 → QA 7석", capped=False)
        run["params"]["deploy_decision"] = did
        pl.save_run(run)
    row = _answered(pl, did)
    if not row:
        return StageSpec("배포 확인 대기", wait={"decision": did, "text": f"조각 {s} 배포 여부를 기다립니다"})
    ans = " ".join((row["answer"] or "").replace("(추천)", "").split()).strip(" .!")
    if ans in _DEPLOY_YES:
        return None
    if not ans.startswith("보류"):  # neither option: never deploy, never drop the slice by accident — ask again
        pl.ctx.conn.execute("UPDATE decisions SET status='new', answer=NULL, answered_at=NULL, context=? WHERE id=?",
                            (f"(앞의 답 '{ans[:60]}'은 선택지와 달라 다시 묻습니다) " + (row["context"] or ""), did))
        return StageSpec("배포 확인 대기", wait={"decision": did, "text": "배포 여부를 선택지로 다시 묻습니다"})
    if ans.startswith("보류"):
        def hold() -> None:
            pl.notify(f"조각 {s} 배포를 보류했습니다({row['answer']}). 지금 배포된 버전을 유지합니다. 다시 하려면 변경 통제로 말씀해 주세요.",
                      "phase", run["id"])
        return StageSpec("배포 보류(사용자)", scripts=[hold], end_status="failed")
    return None


# ---------- build ----------

def bp_plan(pl: Planner, run: dict) -> StageSpec:
    inp = {"spec": str(pl.p.spec), "binding": str(pl.p.binding), **pl.common_inputs(run)}
    for i, doc in enumerate(pl.ctx.cfg.get("paths", {}).get("context_docs") or []):
        inp[f"context_doc:{i}"] = pl.abs(doc)
    adrs = sorted(pl.p.tech.glob("ADR-*.md"))
    for a in adrs:
        inp[f"adr:{a.stem}"] = str(a)
    return StageSpec("구현 계획", steps=[Step("fde-tech-lead", "plan", inp, background=True,
                                          notes="Slice 1 must be a thin end-to-end path deployed and usable on the real platform.")])


def bp_slices(pl: Planner, run: dict) -> StageSpec:
    def go() -> None:
        tasks = db.rows(pl.ctx.conn, "SELECT * FROM tasks WHERE status='todo'")
        slices = sorted({json.loads(t.get("notes") or "{}").get("slice", 1) for t in tasks})
        for s in slices:
            pl.create_run("slice", run_id=f"S{int(s):02d}", slice=int(s))
        pl.notify(f"구현 계획: 조각 {len(slices)}개, 작업 {len(tasks)}개. 조각 1부터 끝까지 배포합니다.", "build", run["id"])
    return StageSpec("조각 생성", scripts=[go])


def _build_refs(pl: Planner) -> dict[str, str]:
    snaps = report.snapshots(pl.ctx)
    refs = {"tasks": snaps["tasks"], "spec": str(pl.p.spec), "binding": str(pl.p.binding)}
    for a in sorted(pl.p.tech.glob("ADR-*.md")):
        refs[f"adr:{a.stem}"] = str(a)
    for i, doc in enumerate(pl.ctx.cfg.get("paths", {}).get("context_docs") or []):
        refs[f"context_doc:{i}"] = pl.abs(doc)
    return refs


def _slice_tasks(pl: Planner, run: dict) -> list[dict]:
    s = run["params"].get("slice", 1)
    rows = db.rows(pl.ctx.conn, "SELECT * FROM tasks ORDER BY id")
    return [t for t in rows if json.loads(t.get("notes") or "{}").get("slice", 1) == s]


def s_wait_prev(pl: Planner, run: dict) -> StageSpec:
    s = run["params"].get("slice", 1)
    if s > 1:
        prev = db.one(pl.ctx.conn, "SELECT status FROM runs WHERE id=?", (f"S{s - 1:02d}",))
        if prev and prev["status"] not in ("done", "failed"):
            return StageSpec("이전 조각 대기", wait={"text": f"조각 {s - 1} 완료를 기다립니다"})
    return StageSpec("시작")


def s_design(pl: Planner, run: dict) -> StageSpec:
    tasks = _slice_tasks(pl, run)
    designers = sorted({d for t in tasks for d in json.loads(t.get("notes") or "{}").get("designers", [])})
    inp = {**_build_refs(pl), "slice_tasks": ", ".join(t["id"] for t in tasks)}
    pm = pl.p.docs / "personalization-map.md"
    if pm.exists():
        inp["personalization_map"] = str(pm)
    if pl.p.persona.exists():
        inp["persona"] = str(pl.p.persona)
    for key, name in (("environment", "environment.md"), ("packaging", "packaging.md")):  # H-16: designers get them
        if (pl.p.docs / name).exists():                                                    # as inputs, not by search
            inp[key] = str(pl.p.docs / name)
    asks = run["params"].get("design_feedback") or []
    notes = ("The user reviewed the previous design of this slice and asked: " + " / ".join(f"'{a}'" for a in asks)
             + ". Redesign accordingly; keep what they did not mention.") if asks else ""
    steps = [Step("fde-design-lead", "design", {**inp, **pl.stage_input()}, background=True, notes=notes),
             Step("fde-detail-designer", "design", dict(inp), background=True, notes=notes)]
    for dn in designers:
        if dn in BY_NAME and "design" in BY_NAME[dn].modes and dn not in ("fde-design-lead", "fde-detail-designer"):
            steps.append(Step(dn, "design", dict(inp), background=True, notes=notes))
    return StageSpec(f"설계(조각 {run['params'].get('slice')})", steps=steps)


def s_trace(pl: Planner, run: dict) -> StageSpec:
    inp = {**_build_refs(pl), **{k: v for k, v in pl.outputs_of(run, mode="design").items()}, **_design_choices(pl, run)}
    return StageSpec("명세 추적", steps=[Step("fde-spec-tracer", "trace", inp, background=True)])


def s_implement(pl: Planner, run: dict) -> StageSpec:
    tasks = [t for t in _slice_tasks(pl, run) if t["status"] in ("todo", "rework")]
    waves: list[list[dict]] = []
    for t in tasks:
        files = set(json.loads(t.get("files") or "[]"))
        for w in waves:
            if not any(files & set(json.loads(x.get("files") or "[]")) for x in w):
                w.append(t)
                break
        else:
            waves.append([t])
    wave = waves[0] if waves else []
    design = pl.outputs_of(run, mode="design")
    trace = pl.outputs_of(run, mode="trace")
    steps = []
    implementers = {a.name for a in roster.AGENTS if "implement" in a.modes}
    for t in wave:
        if t["owner"] not in implementers:  # the plan named an agent that cannot implement → safe default
            pl.ctx.conn.execute("UPDATE tasks SET owner='fde-tool-developer' WHERE id=?", (t["id"],))
            t["owner"] = "fde-tool-developer"
        inp = {"task": t["id"], **_build_refs(pl), **design, **trace, **_design_choices(pl, run)}
        rev = run["params"].get("review_notes", {}).get(t["id"])
        notes = f"Task {t['id']}: {t['title']}. Touch only: {', '.join(json.loads(t.get('files') or '[]')) or 'files named in the design'}."
        if _collab(pl):
            notes += (" Collaboration mode: follow design_choices; when the design leaves a real choice open, do not decide it"
                      " alone — report the task in tasks_blocked as {\"task\", \"design_question\": {\"title\", \"options\", \"recommended\", \"why\"}}.")
        if rev:
            notes += f" Reviewer findings to fix: {rev}"
        steps.append(Step(t["owner"], "implement", inp,
                          background=True, tag=t["id"], notes=notes))
        pl.ctx.conn.execute("UPDATE tasks SET status='doing' WHERE id=?", (t["id"],))
    if len(waves) > 1:
        run["params"]["more_waves"] = True
    return StageSpec("구현", steps=steps)


def s_review(pl: Planner, run: dict) -> StageSpec:
    if run["params"].pop("more_waves", False):
        # next wave of tasks whose files overlapped the previous wave
        return StageSpec("다음 작업 묶음으로", goto=PIPELINES["slice"].index(s_implement))
    impl = pl.outputs_of(run, mode="implement")
    inp = {**_build_refs(pl), **impl, "run_dir": str(pl.run_dir(run))}
    return StageSpec("독립 리뷰", steps=[Step("fde-code-reviewer", "codereview", dict(inp), background=True),
                                       Step("fde-spec-conformance", "codereview", dict(inp), background=True)])


def s_review_gate(pl: Planner, run: dict) -> StageSpec:
    reviews = [read_json(p) or {} for p in pl.outputs_of(run, mode="codereview").values()]
    rejected: dict[str, str] = {}
    for r in reviews:
        rv = r.get("review") or {}
        if rv.get("verdict") == "REJECT":
            items = [i for i in (rv.get("rework") or []) if isinstance(i, dict) and i.get("task")]
            if not items:  # a REJECT without task-level rework still rejects the whole slice
                items = [{"task": t["id"], "fix": "; ".join(map(str, rv.get("items") or []))[:400]} for t in _slice_tasks(pl, run)]
            for item in items:
                rejected[item["task"]] = (rejected.get(item["task"], "") + " " + item.get("fix", "")).strip()
    loops = run["params"].get("review_loops", 0)
    if rejected and loops < 2:
        def back() -> None:
            for tid in rejected:
                pl.ctx.conn.execute("UPDATE tasks SET status='rework', loops=loops+1 WHERE id=?", (tid,))
            run["params"]["review_loops"] = loops + 1
            run["params"]["review_notes"] = rejected
        return StageSpec("리뷰 반려 → 재작업", scripts=[back], goto=PIPELINES["slice"].index(s_implement))
    if rejected:
        did = D.add(pl.ctx, title=f"조각 {run['params'].get('slice')} 리뷰가 2번 반려됐습니다. 어떻게 할까요?", grade="D1",
                    context="; ".join(f"{k}: {v}" for k, v in rejected.items())[:600],
                    options=["개발 본부장이 직접 해결", "이 작업을 빼고 배포", "마지막 정상 버전 유지"],
                    recommended="개발 본부장이 직접 해결", source="planner", blocking=["deploy"])
        run["params"]["escalation"] = {"decision": did, "tasks": sorted(rejected)}
        inp = {**_build_refs(pl), **pl.outputs_of(run, mode="codereview"), **pl.outputs_of(run, mode="implement"),
               **pl.outputs_of(run, mode="design"), "run_dir": str(pl.run_dir(run))}
        return StageSpec("에스컬레이션", steps=[Step("fde-dev-lead", "unblock", inp, background=True,
                                                  notes=f"Decision {did} raised to the user; fix what you can now. Tasks: {', '.join(sorted(rejected))}.")],
                         goto=None)
    return StageSpec("리뷰 통과")


def s_escalation_answer(pl: Planner, run: dict) -> StageSpec:
    """After the dev lead tried to unblock: wait for the user's D1 and act on it."""
    esc = run["params"].get("escalation")
    if not esc:
        return StageSpec("에스컬레이션 없음")
    if esc:  # waiting for the user's answer to "리뷰가 2번 반려" (D1)
        row = db.one(pl.ctx.conn, "SELECT status, answer FROM decisions WHERE id=?", (esc["decision"],))
        if not row or row["status"] != "answered":
            return StageSpec("에스컬레이션 결정 대기", wait={"decision": esc["decision"], "text": "리뷰 반려 처리 방법을 기다립니다"})
        ans = row["answer"] or ""
        run["params"].pop("escalation")
        if "빼고" in ans:
            def drop() -> None:
                for tid in esc["tasks"]:
                    pl.ctx.conn.execute("UPDATE tasks SET status='skipped' WHERE id=?", (tid,))
            return StageSpec("반려 작업 제외하고 진행", scripts=[drop])
        if "정상 버전" in ans:
            return StageSpec("마지막 정상 버전 유지(조각 중단)", end_status="failed")
        run["params"]["review_loops"] = 1  # the dev lead's fix gets one more review pass
        return StageSpec("개발 본부장 수정 후 다시 리뷰", goto=PIPELINES["slice"].index(s_review))
    return StageSpec("통과")


def s_deploy(pl: Planner, run: dict) -> StageSpec:
    busy = db.one(pl.ctx.conn, "SELECT id FROM dispatches WHERE agent='fde-deploy-operator' AND status IN ('issued','planned') AND run<>?", (run["id"],))
    busy = busy or db.one(pl.ctx.conn, "SELECT id FROM runs WHERE pipeline='rollback' AND status IN ('active','waiting')")
    if busy:
        return StageSpec("배포 대기", wait={"text": "다른 조각이 배포 중입니다"})
    if D.blocking_open(pl.ctx, "deploy"):
        return StageSpec("배포 보류", wait={"text": "배포를 막는 D1 결정이 있습니다"})
    confirm = _deploy_confirm(pl, run)
    if confirm:
        return confirm
    cmds = pl.ctx.cfg.get("commands", {})
    return StageSpec("배포", steps=[Step("fde-deploy-operator", "deploy", {"binding": str(pl.p.binding)}, background=True,
                                       notes=f"Run in order and stop at the first failure: test=`{cmds.get('test')}` → deploy=`{cmds.get('deploy')}` → health=`{cmds.get('health')}`.")])


def s_qa(pl: Planner, run: dict) -> StageSpec:
    dep = [read_json(p) or {} for p in pl.outputs_of(run, mode="deploy").values()]
    ok = any((x.get("deploy") or {}).get("ok") for x in dep)
    if not ok:
        def fail() -> None:
            pl.create_run("rollback", run_id=f"RB-{run['id']}", source=run["id"])
            pl.notify(f"조각 {run['params'].get('slice')} 배포 실패 → 릴리스 관리자가 마지막 정상 버전으로 되돌립니다.", "warn", run["id"])
        return StageSpec("배포 실패", scripts=[fail], end_status="failed")
    return StageSpec("QA", scripts=[lambda: report.snapshots(pl.ctx)], steps=_qa_steps(pl))


def _qa_steps(pl: Planner, tag: str = "") -> list[Step]:
    """The QA seats. Each seat gets only what its perspective needs: the fit judge and the AI-tell checker never
    read spec.md (they judge how the bot sounds to this person, not whether it matches our own document)."""
    inp = {"spec": str(pl.p.spec), "binding": str(pl.p.binding),
           "tests": str(pl.p.work / "snapshots" / "acceptance-tests.json")}
    sim = pl.p.docs / "simulated-messages.json"
    if sim.exists():
        inp["simulated_messages"] = str(sim)
    persona = {"persona": str(pl.p.persona)} if pl.p.persona.exists() else {}
    env = {"environment": str(pl.p.docs / "environment.md")} if (pl.p.docs / "environment.md").exists() else {}
    glossary = {"glossary": str(pl.p.docs / "glossary.json")} if (pl.p.docs / "glossary.json").exists() else {}
    steps = [Step(n, "qa", dict(inp), background=True, tag=tag) for n in
             ("fde-scenario-tester", "fde-simulated-user-tester", "fde-latency-checker", "fde-display-checker")]
    steps.append(Step("fde-ux-checker", "qa", {**inp, **persona, **env}, background=True, tag=tag))
    blind = {"binding": str(pl.p.binding), **persona, **glossary}
    if sim.exists():
        blind["simulated_messages"] = str(sim)
    steps.append(Step("fde-ai-tell-checker", "qa", dict(blind), background=True, tag=tag,
                      notes="You must NOT read spec.md. Judge only whether real bot replies sound generic or machine-made."))
    # no persona.md yet (it is written by the persona modeler in a debate — a short run, e.g. a closing on the clock
    # after two rounds, may never have one): the interview itself, so the closing QA still judges fit (F2, problem 1)
    fit_src = persona or ({"transcript": str(pl.p.transcript)} if pl.p.transcript.exists() else {})
    steps.append(Step("fde-fit-judge", "qa", {**fit_src, "binding": str(pl.p.binding)}, background=True, tag=tag,
                      notes="You must NOT read spec.md. Judge only persona fit of real bot replies."
                            + ("" if persona else " persona.md does not exist yet: judge from the persona's own lines in "
                                                  "`transcript` (speaker P) and mark extra.persona_source = transcript.")))
    return steps


def s_verdict(pl: Planner, run: dict) -> StageSpec:
    inp = {k: v for k, v in pl.outputs_of(run, mode="qa").items()}
    return StageSpec("QA 판정", steps=[Step("fde-qa-lead", "verdict", inp, background=True)])


def s_release(pl: Planner, run: dict) -> StageSpec:
    inp = {**pl.outputs_of(run, mode="verdict"), **pl.outputs_of(run, mode="deploy"), "binding": str(pl.p.binding)}
    return StageSpec("릴리스", steps=[Step("fde-release-manager", "release", {**inp, **pl.stage_input()}, background=True,
                                         notes=f"Tag naming: fde-good-{run['id'].lower()} only when QA verdict is PASS."),
                                    Step("fde-observability", "observe", {"binding": str(pl.p.binding)}, background=True)])


def s_after(pl: Planner, run: dict) -> StageSpec:
    def go() -> None:
        v = {}
        for p in pl.outputs_of(run, mode="verdict").values():
            v = (read_json(p) or {}).get("qa_verdict") or {}
        run["params"]["qa_pass"] = v.get("verdict") == "PASS"
        run["params"]["human_checks"] = (v.get("human_checks") or [])[:3]
        if v.get("verdict") == "PASS":
            pl.notify(f"조각 {run['params'].get('slice')} 배포·QA 통과. 카톡에서 직접 확인해 주세요: "
                      + " / ".join((v.get("human_checks") or [])[:3]), "human", run["id"])
            pl.out["human"].append({"run": run["id"], "checks": v.get("human_checks") or []})
        else:
            fixes = v.get("fix_tasks") or []
            for f in fixes:
                if isinstance(f, dict) and f.get("title"):
                    tid = db.next_id(pl.ctx.conn, "tasks", "B-")
                    db.upsert(pl.ctx.conn, "tasks", {"id": tid, "kind": "fix", "title": f["title"],
                                                     "requirements": json.dumps(f.get("requirements") or []),
                                                     "files": json.dumps(f.get("files") or []), "owner": f.get("owner", "fde-tool-developer"),
                                                     "status": "todo", "depends": "[]", "loops": 0, "created_at": iso(),
                                                     "done_at": None, "notes": json.dumps({"slice": 90 + int(run['params'].get('slice', 1))})})
            if fixes:
                pl.create_run("slice", run_id=f"S{90 + int(run['params'].get('slice', 1)):02d}", slice=90 + int(run['params'].get('slice', 1)))
            else:
                pl.create_run("replan", run_id=f"RP-{run['id']}", source=run["id"])
            if v.get("rollback") or v.get("severity") == "critical":
                pl.create_run("rollback", run_id=f"RB-{run['id']}", source=run["id"])
            pl.notify(f"조각 {run['params'].get('slice')} QA 미통과 → 수정 작업 {len(fixes)}개"
                      + (" · 치명적이라 마지막 정상 버전으로 되돌립니다" if v.get("rollback") or v.get("severity") == "critical" else ""),
                      "warn", run["id"])
    return StageSpec("마무리", scripts=[go])


def rp_replan(pl: Planner, run: dict) -> StageSpec:
    inp = {**_build_refs(pl), **pl.common_inputs(run)}
    src = run["params"].get("source")
    if run["params"].get("change_decision"):  # an answered change decision (change pipeline)
        inp["change_run_dir"] = str(pl.p.runs / src)
        notes = (f"Change control: the user answered '{run['params'].get('change_answer', '')}' to "
                 f"'{run['params'].get('change_title', '')}' ({run['params']['change_decision']}). If the answer accepts "
                 "the change (now or after the current slice), add only the tasks it needs, in new slices numbered above "
                 "every existing slice, keeping the shipped release safe. If it defers or rejects it, add no tasks and say "
                 "so in summary_ko.")
    elif run["params"].get("design_review"):  # collaboration progress check: the user asked to review the design
        inp["slice_run_dir"] = str(pl.p.runs / src)
        notes = ("The user asked for a design review after this slice passed. Re-check the remaining slices against "
                 "spec.md and the user's design choices; add or reorder tasks only where the review changes them, in "
                 "slices numbered above every existing slice, and raise real choices as graded decisions.")
    else:
        if src:
            inp["failed_run_dir"] = str(pl.p.runs / src)
        notes = "Re-plan the remaining work after a failure; new tasks continue the slice numbering."
    return StageSpec("재계획", steps=[Step("fde-tech-lead", "replan", inp, background=True, notes=notes)])


def rp_slices(pl: Planner, run: dict) -> StageSpec:
    def go() -> None:
        existing = {r["id"] for r in db.rows(pl.ctx.conn, "SELECT id FROM runs WHERE pipeline='slice'")}
        tasks = db.rows(pl.ctx.conn, "SELECT * FROM tasks WHERE status='todo'")
        for s in sorted({json.loads(t.get("notes") or "{}").get("slice", 1) for t in tasks}):
            rid = f"S{int(s):02d}"
            if rid not in existing:
                pl.create_run("slice", run_id=rid, slice=int(s))
    return StageSpec("재계획 조각 생성", scripts=[go])


def rb_rollback(pl: Planner, run: dict) -> StageSpec:
    return StageSpec("되돌리기", steps=[Step("fde-release-manager", "rollback", {"binding": str(pl.p.binding)}, background=True,
                                            notes="Roll back to the newest fde-good-* tag with the binding's deploy command; never run destructive infra commands.")])


# ---------- data ----------

def da_plan(pl: Planner, run: dict) -> StageSpec:
    files = run["params"].get("files") or []
    inp = {**pl.common_inputs(run), "files": json.dumps(files, ensure_ascii=False)}
    return StageSpec("데이터 계획", steps=[Step("fde-data-lead", "dataplan", inp, background=True)])


def _data_writes(pl: Planner, run: dict, agent: str) -> list[str]:
    return [pl.rel(pl.p.data / f"{run['id']}-{agent.removeprefix('fde-')}.md")]


def da_validate(pl: Planner, run: dict) -> StageSpec:
    files = run["params"].get("files") or []
    plan = pl.outputs_of(run, mode="dataplan")
    inp = {"files": json.dumps(files, ensure_ascii=False), "binding": str(pl.p.binding), **plan,
           "transcript": str(pl.p.transcript), "requirements": str(pl.p.work / "snapshots" / "requirements.json")}
    return StageSpec("검증·대조", steps=[Step("fde-data-validator", "validate", dict(inp), background=True,
                                            extra_writes=_data_writes(pl, run, "fde-data-validator")),
                                       Step("fde-data-consistency-checker", "consistency", dict(inp), background=True,
                                            extra_writes=_data_writes(pl, run, "fde-data-consistency-checker"))])


def da_clean(pl: Planner, run: dict) -> StageSpec:
    inp = {**pl.outputs_of(run), "binding": str(pl.p.binding)}
    return StageSpec("정제", steps=[Step("fde-data-cleaner", "clean", inp, background=True,
                                       extra_writes=_data_writes(pl, run, "fde-data-cleaner"))])


def da_load(pl: Planner, run: dict) -> StageSpec:
    inp = {**pl.outputs_of(run, mode="clean"), "binding": str(pl.p.binding)}
    return StageSpec("적재", steps=[Step("fde-data-loader", "load", inp, background=True,
                                       extra_writes=_data_writes(pl, run, "fde-data-loader"))])


def da_audit(pl: Planner, run: dict) -> StageSpec:
    snaps = report.snapshots(pl.ctx)
    inp = {**pl.outputs_of(run), "binding": str(pl.p.binding), "transcript": str(pl.p.transcript),
           "tests": snaps["tests"], "decisions": snaps["decisions"], "requirements": snaps["requirements"]}
    return StageSpec("출처 감사", steps=[Step("fde-data-provenance-auditor", "audit", inp, background=True,
                                          extra_writes=_data_writes(pl, run, "fde-data-provenance-auditor"))])


def da_report(pl: Planner, run: dict) -> StageSpec:
    inp = {**pl.outputs_of(run), "requirements": str(pl.p.work / "snapshots" / "requirements.json")}
    return StageSpec("데이터 보고", steps=[Step("fde-data-lead", "datareport", inp, background=True)])


# ---------- change control ----------

def ch_analyze(pl: Planner, run: dict) -> StageSpec:
    inp = {**pl.common_inputs(run), "spec": str(pl.p.spec), "change": run["params"].get("text", "")}
    return StageSpec("변경 영향", steps=[Step("fde-change-analyst", "change", inp, background=True)])


def ch_decide(pl: Planner, run: dict) -> StageSpec:
    """Wait for the user's answer to the analyst's decision, then hand it to the tech lead (replan) — who adds
    tasks when the answer accepts the change and none when it defers or rejects it. No decision = clarification."""
    did = run["params"].get("decision")
    if not did:
        row = db.one(pl.ctx.conn, "SELECT id FROM decisions WHERE source='fde-change-analyst' AND created_at >= ? "
                                  "ORDER BY created_at LIMIT 1", (run.get("created_at") or "",))
        if not row:
            pl.notify(f"{run['id']}: 변경이 아니라 확인(명확화)으로 판단돼 추가 작업이 없습니다.", "phase", run["id"])
            return StageSpec("결정 없음(명확화)", end_status="done")
        did = row["id"]
        run["params"]["decision"] = did
        pl.save_run(run)
    row = db.one(pl.ctx.conn, "SELECT * FROM decisions WHERE id=?", (did,))
    if not row or row["status"] not in ("answered", "auto"):
        return StageSpec("사용자 결정 대기", wait={"decision": did, "text": "변경을 반영할지 결정을 기다립니다"})

    def go() -> None:
        if pl.create_run("replan", run_id=f"RP-{run['id']}", source=run["id"], change_decision=did,
                         change_answer=row["answer"] or "", change_title=row["title"]):
            pl.notify(f"{run['id']} 결정 '{row['answer']}' → 테크 리드가 남은 작업을 다시 짭니다(반영이면 새 조각).",
                      "phase", run["id"])
    return StageSpec("재계획 요청", scripts=[go])


# ---------- closing / retro / rehearsal ----------

def c_sweep(pl: Planner, run: dict) -> StageSpec:
    return StageSpec("최종 QA", scripts=[lambda: report.snapshots(pl.ctx)], steps=_qa_steps(pl, tag="final"))


def c_verdict(pl: Planner, run: dict) -> StageSpec:
    return StageSpec("최종 판정·데모", steps=[
        Step("fde-qa-lead", "verdict", {**pl.outputs_of(run, mode="qa")}, background=True, tag="final"),
        Step("fde-demo-scenario", "final", {**pl.common_inputs(run), "spec": str(pl.p.spec)}, background=True,
             extra_writes=[pl.rel(pl.p.docs / "demo-scenario.md")])])


def c_final(pl: Planner, run: dict) -> StageSpec:
    inp = {**pl.outputs_of(run), "binding": str(pl.p.binding), "spec": str(pl.p.spec)}
    return StageSpec("최종 릴리스·기록", steps=[
        Step("fde-release-manager", "final", {**inp, **pl.stage_input()}, background=True),
        Step("fde-chief-clerk", "final", dict(inp), background=True, extra_writes=[pl.rel(pl.p.docs / "final-report.md")])])


def c_submit(pl: Planner, run: dict) -> StageSpec:
    def go() -> None:
        items = pl.ctx.cfg.get("submission", {}).get("checklist") or []
        pl.out["human"].append({"run": run["id"], "checks": items})
        pl.notify("제출 체크리스트를 확인하고 직접 제출해 주세요: " + " / ".join(items[:6]), "human", run["id"])
    return StageSpec("제출 안내", scripts=[go])


def _export_events(pl: Planner, run: dict) -> str:
    rows = db.rows(pl.ctx.conn, "SELECT * FROM events ORDER BY id")
    runs = db.rows(pl.ctx.conn, "SELECT id, pipeline, round, status, created_at, finished_at FROM runs ORDER BY created_at")
    decs = db.rows(pl.ctx.conn, "SELECT id, grade, title, status, round, created_at, answered_at FROM decisions ORDER BY id")
    disp = db.rows(pl.ctx.conn, "SELECT id, run, stage, agent, mode, status, attempts, issued_at, done_at FROM dispatches")
    path = pl.run_dir(run) / "events.json"
    write_json(path, {"events": rows, "runs": runs, "decisions": decs, "dispatches": disp})
    return str(path)


def r_retro(pl: Planner, run: dict) -> StageSpec:
    from fde_mode.paths import global_dir
    inp = {**pl.common_inputs(run), "spec": str(pl.p.spec), "events": _export_events(pl, run),
           "lessons_global": str(global_dir() / "lessons.md")}
    # H-15: the retro is phase P7 (stored, so the hooks point at the closing skill's retro part, not P6)
    return StageSpec("회고", scripts=[lambda: set_state(pl.ctx, phase="P7")],
                     steps=[Step("fde-retro-analyst", "retro", inp, background=True,
                                 extra_writes=[pl.rel(pl.p.docs / "retro.md"), str(global_dir() / "lessons.md")])])


def rh_create(pl: Planner, run: dict) -> StageSpec:
    pl.p.sealed.mkdir(parents=True, exist_ok=True)
    return StageSpec("가짜 인물 생성", steps=[Step("fde-mock-persona", "create", {"binding": str(pl.p.binding),
                                                                              "theme": run["params"].get("theme", "")},
                                                background=False,
                                                notes="Everything the role-player needs (including hidden requirements) goes to sealed/. "
                                                      "Only the participant-facing problem statement goes to rehearsal/public-brief.md.",
                                                extra_writes=[pl.rel(pl.p.sealed / "persona-secret.md"),
                                                              pl.rel(pl.p.sealed / "hidden-requirements.json"),
                                                              pl.rel(pl.p.sealed / "roleplay-prompt.md"),
                                                              pl.rel(pl.p.rehearsal / "public-brief.md")])])


def rh_grade(pl: Planner, run: dict) -> StageSpec:
    report.snapshots(pl.ctx)
    inp = {"sealed_requirements": str(pl.p.sealed / "hidden-requirements.json"), **pl.common_inputs(run),
           "events": _export_events(pl, run)}
    return StageSpec("리허설 채점", steps=[Step("fde-rehearsal-grader", "grade", inp, background=False,
                                             extra_writes=[pl.rel(pl.p.rehearsal / "grade.md")])])


PIPELINES: dict[str, list[Callable[[Planner, dict], StageSpec]]] = {
    "quick": [_prep, q_scribe, q_analyze, q_post, q_verify, q_cards, q_report],
    "debate": [_prep, d_analyze, d_complement, d_position, d_review, d_rebuttal, d_ruling, d_merge, d_verify,
               d_cards, d_sequence, d_report],
    "brief": [_prep, b_analyze, b_merge, q_verify, b_cards, b_report],
    "techgate": [t_items, t_challenge, t_decide, t_done],
    "freeze": [f_check, f_ask],
    "buildplan": [bp_plan, bp_slices],
    "slice": [s_wait_prev, s_design, s_design_confirm, s_trace, s_implement, s_impl_questions, s_review, s_review_gate,
              s_escalation_answer, s_deploy, s_qa, s_verdict, s_release, s_after, s_progress],
    "rollback": [rb_rollback],
    "replan": [rp_replan, rp_slices],
    "data": [da_plan, da_validate, da_clean, da_load, da_audit, da_report],
    "change": [ch_analyze, ch_decide],
    "closing": [c_sweep, c_verdict, c_final, c_submit],
    "retro": [r_retro],
    "rehearsal": [rh_create],
    "rehearsal-grade": [rh_grade],
}


def next_actions(ctx: Ctx) -> dict[str, Any]:
    return Planner(ctx).step()


def start(ctx: Ctx, pipeline: str, **params: Any) -> str | None:
    pl = Planner(ctx)
    n = int(db.scalar(ctx.conn, "SELECT COUNT(*) FROM runs WHERE pipeline=?", (pipeline,), 0)) + 1
    rnd = params.pop("round", "") or ""
    rid = params.pop("run_id", None) or (f"{rnd}-{pipeline}" if rnd else f"{pipeline.upper()}-{n:02d}")
    return pl.create_run(pipeline, rnd, rid, **params)
