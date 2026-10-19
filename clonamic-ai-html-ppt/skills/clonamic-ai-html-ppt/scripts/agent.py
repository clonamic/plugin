"""LangGraph-style agent engine (stdlib) and the `edit` graph (format.md §9.2).

Code nodes run inside the server. AI nodes pause the run: the host AI reads `instruction`, then submits one JSON
object for that node. Every node transition is one checkpoint (runs + steps tables in the store's DB), so a run
resumes after a restart. `interrupt()` pauses for the user (the confirm card) until `Runner.resume`.

The tools a graph needs come in `ctx` (server.py builds it; tests pass fakes): store, commit(deck, ops, label),
say(deck, text, meta), snapshot(deck, page, rect=None, ids=None) → {path, w, h} | None, measure(deck, pages) →
dict | None, export(deck, pages, mode, dir) → [paths], amend(deck, seq, ops) → result | None, pins_changed(deck),
notify(deck), interrupted(run, payload).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable

import lint
import ops
import pdf

END = "end"
MAX_TRIES = 2  # verify/apply retries back to plan
CONFIRM_AT = 20  # deletions that need the user's OK


class Interrupt(Exception):
    def __init__(self, payload: dict):
        super().__init__("interrupt")
        self.payload = payload


class StepError(ValueError):
    """Submitted output that does not fit the node, or a call at the wrong node → HTTP 400."""


def interrupt(state: dict, payload: dict):
    """Pause for a human. When the run is resumed the node runs again and this returns the resume value."""
    if "resume" in state:
        return state.pop("resume")
    raise Interrupt(payload)


# ---- engine ---------------------------------------------------------------------------------------

class StateGraph:
    def __init__(self, name: str):
        self.name, self.nodes, self.edges, self.entry = name, {}, {}, None

    def add_node(self, name: str, fn: Callable | None = None, *, instruction: Callable | None = None,
                 accept: Callable | None = None) -> None:
        """Code node: fn(state, ctx) → updates. AI node: instruction(state) → text, accept(state, output, ctx) → updates."""
        self.nodes[name] = {"fn": fn, "instruction": instruction, "accept": accept}

    def add_edge(self, a: str, b: str) -> None:
        self.edges[a] = lambda state: b

    def add_conditional_edges(self, a: str, router: Callable[[dict], str]) -> None:
        self.edges[a] = router

    def set_entry_point(self, name: str) -> None:
        self.entry = name

    def is_ai(self, name: str) -> bool:
        return self.nodes.get(name, {}).get("accept") is not None

    def after(self, name: str, state: dict) -> str:
        nxt = self.edges[name](state)
        if nxt != END and nxt not in self.nodes:
            raise AssertionError(f"{self.name}: no node {nxt}")
        return nxt


class Checkpointer:
    """Runs and their steps in the store's SQLite DB."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def _run(r) -> dict:
        return {"id": r["id"], "deck": r["deck_id"], "graph": r["graph"], "node": r["node"], "status": r["status"],
                "state": json.loads(r["state"]), "label": r["label"], "tries": r["tries"], "message_id": r["message_id"],
                "created": r["created"], "updated": r["updated"]}

    @staticmethod
    def summary(run: dict | None) -> dict | None:
        return run and {k: run[k] for k in ("id", "node", "status", "label", "tries")}

    def create(self, deck: int, graph: str, node: str, state: dict, message_id: int | None, label: str) -> int:
        now = time.time()
        with self.store.write() as db:
            return db.execute("INSERT INTO runs (deck_id, graph, node, status, state, label, message_id, created, updated) "
                              "VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)",
                              (deck, graph, node, json.dumps(state, ensure_ascii=False), label, message_id, now, now)).lastrowid

    def load(self, run_id: int) -> dict | None:
        with self.store.read() as db:
            r = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return self._run(r) if r else None

    def save(self, run: dict, step: dict, notify: bool = False) -> None:
        now = time.time()
        with self.store.write() as db:
            n = db.execute("SELECT coalesce(max(n), 0) + 1 FROM steps WHERE run_id = ?", (run["id"],)).fetchone()[0]
            db.execute("UPDATE runs SET node = ?, status = ?, state = ?, label = ?, tries = ?, notify = ?, updated = ? WHERE id = ?",
                       (run["node"], run["status"], json.dumps(run["state"], ensure_ascii=False), run["label"], run["tries"],
                        int(notify), now, run["id"]))
            db.execute("INSERT INTO steps (run_id, n, node, status, detail, created) VALUES (?, ?, ?, ?, ?, ?)",
                       (run["id"], n, step["node"], step["status"], json.dumps(step.get("detail", {}), ensure_ascii=False), now))

    def steps(self, run_id: int) -> list[dict]:
        with self.store.read() as db:
            rows = db.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY n", (run_id,)).fetchall()
        return [{"n": r["n"], "node": r["node"], "status": r["status"], "detail": json.loads(r["detail"]), "created": r["created"]}
                for r in rows]

    def runs(self, deck: int, limit: int = 20) -> list[dict]:
        with self.store.read() as db:
            rows = db.execute("SELECT * FROM runs WHERE deck_id = ? ORDER BY id DESC LIMIT ?", (deck, limit)).fetchall()
        return [self.summary(self._run(r)) | {"message_id": r["message_id"], "created": r["created"], "updated": r["updated"]}
                for r in rows]

    def latest(self, deck: int) -> dict | None:
        rows = self.runs(deck, 1)
        return {k: rows[0][k] for k in ("id", "node", "status", "label", "tries")} if rows else None

    def for_message(self, message_id: int) -> int | None:
        with self.store.read() as db:
            r = db.execute("SELECT id FROM runs WHERE message_id = ?", (message_id,)).fetchone()
        return r["id"] if r else None

    def take_resume(self, deck: int) -> int | None:
        """A run the user just resumed (confirm card answered), once."""
        with self.store.write() as db:
            r = db.execute("SELECT id FROM runs WHERE deck_id = ? AND notify = 1 ORDER BY id LIMIT 1", (deck,)).fetchone()
            if r:
                db.execute("UPDATE runs SET notify = 0 WHERE id = ?", (r["id"],))
        return r["id"] if r else None


class Runner:
    def __init__(self, graph: StateGraph, saver: Checkpointer, ctx):
        self.graph, self.saver, self.ctx = graph, saver, ctx
        self.lock = threading.RLock()  # ponytail: one lock for all runs; per-run locks if decks start waiting on each other

    def start(self, deck: int, state: dict, message_id: int | None = None, label: str = "") -> int:
        run_id = self.saver.create(deck, self.graph.name, self.graph.entry, state, message_id, label)
        run = self.saver.load(run_id)
        run["state"] |= {"deck": deck, "run": run_id}
        self.saver.save(run, {"node": "start", "status": "ok"})
        self.ctx.notify(deck)
        return run_id

    def _get(self, run_id: int) -> dict:
        run = self.saver.load(run_id)
        if run is None:
            raise KeyError(f"없는 실행입니다: {run_id}")
        return run

    def view(self, run: dict) -> dict:
        node = {"done": END, "failed": END, "waiting_user": "waiting_user"}.get(run["status"], run["node"])
        spec = self.graph.nodes.get(run["node"], {})
        text = spec["instruction"](run["state"]) if node == run["node"] and self.graph.is_ai(node) else None
        return {"run": run["id"], "node": node, "status": run["status"], "instruction": text, "state": run["state"]}

    def _checkpoint(self, run: dict, name: str, updates: dict, status: str, notify: bool = False) -> None:
        state = run["state"]
        state.update(updates)
        if run["status"] == "active":
            run["node"] = self.graph.after(name, state)
            if run["node"] == END:
                run["status"] = "done"
        run["label"] = (state.get("plan") or {}).get("label") or run["label"]
        run["tries"] = state.get("tries", 0)
        detail = {"next": run["node"], "keys": sorted(updates)} | ({"issues": updates["issues"]} if updates.get("issues") else {})
        self.saver.save(run, {"node": name, "status": "issues" if updates.get("issues") else status, "detail": detail}, notify)
        self.ctx.notify(run["deck"])

    def next(self, run_id: int) -> dict:
        """Run code nodes until an AI node, an interrupt, or the end."""
        with self.lock:
            run = self._get(run_id)
            for _ in range(100):  # a graph without a loop guard must never spin the server
                if run["status"] != "active" or self.graph.is_ai(run["node"]):
                    break
                name = run["node"]
                try:
                    updates = self.graph.nodes[name]["fn"](run["state"], self.ctx) or {}
                except Interrupt as exc:
                    run["status"] = "waiting_user"
                    self.saver.save(run, {"node": name, "status": "interrupt", "detail": exc.payload})
                    self.ctx.notify(run["deck"])
                    self.ctx.interrupted(run, exc.payload)
                    break
                except Exception as exc:  # noqa: BLE001 - a broken step ends the run visibly instead of hanging it
                    run["status"] = "failed"
                    run["node"] = END
                    run["state"]["error"] = f"{type(exc).__name__}: {exc}"
                    self.saver.save(run, {"node": name, "status": "failed", "detail": {"error": run["state"]["error"]}})
                    self.ctx.notify(run["deck"])
                    break
                self._checkpoint(run, name, updates, "ok")
            return self.view(run)

    def submit(self, run_id: int, node: str, output) -> dict:
        """Record an AI node's output and advance."""
        with self.lock:
            run = self._get(run_id)
            if run["status"] != "active" or run["node"] != node or not self.graph.is_ai(node):
                raise StepError(f"지금 제출할 단계는 {self.view(run)['node']}입니다.")
            updates = self.graph.nodes[node]["accept"](run["state"], output, self.ctx)
            self._checkpoint(run, node, updates, "submitted")
            return self.next(run_id)

    def resume(self, run_id: int, value) -> dict:
        """Answer an interrupt; the waiting AI gets {status: "resume", run}."""
        with self.lock:
            run = self._get(run_id)
            if run["status"] != "waiting_user":
                raise StepError("확인을 기다리는 실행이 아닙니다.")
            run["state"]["resume"] = value
            run["status"] = "active"
            self.saver.save(run, {"node": run["node"], "status": "resumed", "detail": {"value": value}}, notify=True)
            self.ctx.notify(run["deck"])
            return self.view(run)


# ---- the edit graph -------------------------------------------------------------------------------

PLAN_TEXT = """\
You are the editing agent of an HTML slide/document editor. The user's request (usually Korean) is state.message.text; \
state.meta has {{page, selection, mode, focus}}. Context: state.context.outline is the current page as indented lines \
`type id "name" x,y wxh ... rev=N`; state.context.nodes is the full JSON of the selected nodes and their subtrees; \
state.context.snapshot is a PNG of the current page (open it: that is what the user sees); \
state.context.focus lists pinned regions with a `snapshot` PNG path (open it); state.context.pages lists page ids in order. \
For other pages run `ppt.py outline --deck {deck} --page <id>` or `ppt.py get --deck {deck} --ids a,b`.

Submit exactly one JSON object on stdin:
  ppt.py agent submit --deck {deck} --run {run} --node plan
One of:
  {{"kind": "edit", "ops": [<op>, ...], "label": "<short Korean label for undo history, e.g. 제목 색 변경>", "note": "<optional>"}}
  {{"kind": "answer"}}  (a question or chat, nothing to change; you write the answer in the reply step)
  {{"kind": "pdf", "pdf": {{"pages": [<page ids>, or [] for all], "mode": "single" | "each", "dir": "~/Downloads"}}}}
  {{"kind": "check", "pages": [<page ids>, or [] for all]}}  (a review with nothing to change yet: measure and lint those pages; on errors you plan again with state.issues)
No other keys.

Op batch rules (the batch is atomic: one invalid op rejects all of it):
- {{"op": "add", "node": {{"id": "<new id>", "type": "<type>", "parent": "<container id>", "props": {{...}}}}}}  (omit "z" to put it on top)
- {{"op": "set", "id": "<id>", "props": {{"<key>": <value> or null}}, "rev": <rev>}}  shallow merge; null resets the key to its default; arrays and objects are replaced whole
- {{"op": "del", "id": "<id>", "rev": <rev>}}  deletes the node and its whole subtree
- {{"op": "move", "id": "<id>", "parent": "<container id>", "rev": <rev>}}  coordinates are not converted; add a set of x/y in the same batch
- {{"op": "deck", "props": {{"name": "<deck name>"}}}}
- Always send "rev" on set/del/move: the node's current rev (rev=N in the outline, "rev" in nodes JSON). A stale rev fails with a conflict that lists the current node; plan again from it.
- New ids match [A-Za-z0-9_-]{{1,32}} and are unique: type prefix + "_" + 8 random letters/digits, e.g. "t_9fK2mQx1".
- Types: page frame section group boolean rect ellipse line polygon star vector text video table. A parent is a container (page frame section group boolean); a section sits only directly in a page; a page has parent null.
- props are sparse and only use keys schema.json defines for that type; unknown keys and extra keys inside nested objects are rejected. x, y are relative to the parent's top-left; 1 unit = 1 CSS px = 1 pt in PDF. Colors are uppercase "#RRGGBBAA". Fill: "fills": [{{"type": "SOLID", "color": "#1E3A8AFF"}}]. Text: "runs": [{{"t": "..."}}] (a run may add "s" style overrides, "fill", "link"), base style in "style": {{"font", "weight", "size", "lineHeight", ...}}; text color = the node's first SOLID fill. Groups and booleans keep x, y, w, h equal to their children's union box.
- Deleting {confirm_at} or more nodes, or any page, asks the user to confirm before it is applied.
{inline}{issues}"""

INLINE_TEXT = """\
- INLINE MODE: change only the selected nodes {selection} and their descendants; add new nodes only under them; no deck op. Any other op fails.
"""

ISSUES_TEXT = """\
- Your previous attempt has problems listed in state.issues (op index, key, lint code, message). Batches already applied \
stay applied (state.applied); send only the ops that fix the problems. Retries left after this one: {left}.
"""

REPLY_TEXT = """\
Write the chat reply for the user and submit exactly one JSON object on stdin:
  ppt.py agent submit --deck {deck} --run {run} --node reply
  {{"text": "<reply in Korean, plain text, no markdown>", "resolved_focus": [<focus pin ids you handled>], "suggestions": ["<short Korean next step>", ...]}}
Facts to report: state.plan (what you planned); state.applied (seq and revs when ops were applied); state.confirm \
(ok false = the user declined, nothing was changed); state.issues (errors still unresolved after retries: say what is still \
wrong); state.warnings (lint warnings worth mentioning); state.export (PDF files, or an error; fallback "print" means \
Chrome is missing, so tell the user to use the browser's print dialog); state.snapshots (PNG paths of the changed pages: \
look at them before you claim success). resolved_focus: ids from state.meta.focus this run handled (they are marked \
resolved). suggestions: 0 to 3 items; each becomes a line "추천: <item>" in the chat.
"""


def _strict(output, allowed: set, what: str) -> dict:
    if not isinstance(output, dict):
        raise StepError(f"{what} 출력은 JSON 객체입니다.")
    if extra := set(output) - allowed:
        raise StepError(f"{what} 출력에 없는 키입니다: {', '.join(sorted(extra))}")
    return output


def intake(state: dict, ctx) -> dict:
    deck, store = state["deck"], ctx.store
    meta = state["message"].get("meta") or {}
    data = store.deck(deck)
    pages = [p["id"] for p in store.pages(deck)]
    page = meta.get("page") if meta.get("page") in pages else (pages[0] if pages else None)
    ids = {n["id"] for n in data["nodes"]}
    selection = [i for i in meta.get("selection") or [] if isinstance(i, str) and i in ids]
    focus = [i for i in meta.get("focus") or [] if isinstance(i, int) and not isinstance(i, bool)]
    pins = store.pins(deck, focus) if focus else []
    for pin in pins:
        store.update_pin(deck, pin["id"], status="sent")
        shot = ctx.snapshot(deck, pin["page"], rect=pin["rect"], ids=pin["ids"] or None)
        pin["status"], pin["snapshot"] = "sent", shot and shot["path"]
    if pins:
        ctx.pins_changed(deck)
    shot = ctx.snapshot(deck, page) if page else None
    return {
        "meta": {"page": page, "selection": selection, "mode": "inline" if meta.get("mode") == "inline" else "chat",
                 "focus": [p["id"] for p in pins]},
        "context": {"deck": data["deck"], "page": page, "pages": pages,
                    "outline": ops.outline(data["deck"], data["nodes"], page) if page else ops.outline(data["deck"], []),
                    "nodes": store.nodes(deck, pages=selection)["nodes"], "focus": pins, "snapshot": shot and shot["path"]},
        "tries": 0, "issues": [], "warnings": [],
    }


def plan_instruction(state: dict) -> str:
    meta = state.get("meta", {})
    inline = INLINE_TEXT.format(selection=json.dumps(meta.get("selection", []))) if meta.get("mode") == "inline" else ""
    issues = ISSUES_TEXT.format(left=MAX_TRIES - state.get("tries", 0)) if state.get("issues") else ""
    return PLAN_TEXT.format(deck=state["deck"], run=state["run"], confirm_at=CONFIRM_AT, inline=inline, issues=issues)


def accept_plan(state: dict, output, ctx) -> dict:
    out = _strict(output, {"kind", "ops", "label", "pdf", "pages", "note"}, "plan")
    kind = out.get("kind")
    if kind not in ("edit", "answer", "pdf", "check"):
        raise StepError('kind는 "edit", "answer", "pdf", "check" 중 하나입니다.')
    plan = {"kind": kind, "note": str(out.get("note") or "")}
    if kind == "check":
        pages = out.get("pages") or []
        if not isinstance(pages, list) or not all(isinstance(p, str) for p in pages):
            raise StepError("check의 pages는 page id 목록입니다([]는 전체).")
        plan["pages"] = pages
    if kind == "edit":
        batch, label = out.get("ops"), out.get("label") or "AI 편집"
        if not isinstance(batch, list) or not batch:
            raise StepError("edit에는 ops 배열(1개 이상)이 필요합니다.")
        if not isinstance(label, str) or len(label) > 200:
            raise StepError("label은 200자 이하 문자열입니다.")
        plan |= {"ops": batch, "label": label}
    if kind == "pdf":
        spec = out.get("pdf") or {}
        if not isinstance(spec, dict) or not isinstance(spec.get("pages", []), list) or spec.get("mode", "single") not in ("single", "each"):
            raise StepError('pdf는 {"pages": [...], "mode": "single"|"each", "dir": "..."}입니다.')
        plan["pdf"] = {"pages": spec.get("pages", []), "mode": spec.get("mode", "single"), "dir": str(spec.get("dir") or "~/Downloads")}
    count, pages = 0, []
    for op in plan.get("ops", []):
        if isinstance(op, dict) and op.get("op") == "del" and isinstance(op.get("id"), str):
            rows = ctx.store.nodes(state["deck"], pages=[op["id"]])["nodes"]  # the node and its subtree
            count += len(rows)
            pages += [r["id"] for r in rows[:1] if r["type"] == "page"]
    return {"plan": plan, "deletions": {"count": count, "pages": pages}, "issues": []}


def route_plan(state: dict) -> str:
    kind = state["plan"]["kind"]
    if kind == "check":
        return "verify"
    if kind != "edit":
        return "reply" if kind == "answer" else "export"
    gone = state["deletions"]
    return "confirm" if gone["count"] >= CONFIRM_AT or gone["pages"] else "apply"


def confirm(state: dict, ctx) -> dict:
    gone = state["deletions"]
    ok = interrupt(state, {"kind": "confirm", "deletions": gone["count"], "pages": gone["pages"], "label": state["plan"]["label"]})
    return {"confirm": {"ok": bool(ok), "deletions": gone["count"], "pages": gone["pages"]}}


def scope_violation(batch: list, allowed: set[str]) -> int | None:
    """Index of the first op that reaches outside the selection's subtrees (inline mode), else None."""
    allowed = set(allowed)

    def inside(v) -> bool:
        return isinstance(v, str) and v in allowed

    for i, op in enumerate(batch):
        kind = op.get("op") if isinstance(op, dict) else None
        node = op.get("node") if kind == "add" else None
        if kind == "add" and isinstance(node, dict) and inside(node.get("parent")) and isinstance(node.get("id"), str):
            allowed.add(node["id"])
        elif not (kind in ("set", "del") and inside(op.get("id"))
                  or kind == "move" and inside(op.get("id")) and inside(op.get("parent"))):
            return i
    return None


def affected_pages(batch: list, nodes: list[dict]) -> list[str]:
    parent = {n["id"]: n["parent"] for n in nodes}
    kind = {n["id"]: n["type"] for n in nodes}
    for op in batch:
        node = op.get("node") if isinstance(op, dict) and op.get("op") == "add" else None
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            parent[node["id"]], kind[node["id"]] = node.get("parent"), node.get("type")

    def page_of(nid):
        for _ in range(1000):
            if not isinstance(nid, str) or nid not in kind:
                return None
            if kind[nid] == "page":
                return nid
            nid = parent[nid]
        return None

    found: dict[str, None] = {}
    for op in batch:
        if not isinstance(op, dict):
            continue
        targets = [(op.get("node") or {}).get("id") if op.get("op") == "add" else op.get("id")]
        targets += [op.get("parent")] if op.get("op") == "move" else []
        for t in targets:
            if page := page_of(t):
                found[page] = None
    return list(found)


def _failed(state: dict, issues: list[dict]) -> dict:
    retry = state.get("tries", 0) < MAX_TRIES
    return {"issues": issues, "retry": retry, "tries": state.get("tries", 0) + int(retry)}


def apply(state: dict, ctx) -> dict:
    deck, plan, store = state["deck"], state["plan"], ctx.store
    batch = plan["ops"]
    if state["meta"]["mode"] == "inline":
        allowed = {n["id"] for n in store.nodes(deck, pages=state["meta"]["selection"])["nodes"]}
        bad = scope_violation(batch, allowed)
        if bad is not None:
            return _failed(state, [{"code": "scope", "index": bad,
                                    "message": f"인라인 편집은 선택한 요소와 그 안쪽만 바꿀 수 있습니다(op {bad})."}])
    pages = affected_pages(batch, store.deck(deck)["nodes"])
    try:
        result = ctx.commit(deck, batch, plan["label"])
    except ops.OpError as exc:
        return _failed(state, [{"code": "invalid", "index": exc.index, "key": exc.key, "message": str(exc)}])
    except ops.Conflict as exc:
        return _failed(state, [{"code": "conflict", "message": str(exc), "conflicts": exc.conflicts}])
    return {"applied": {"seq": result["seq"], "revs": result["revs"]}, "applied_seqs": state.get("applied_seqs", []) + [result["seq"]],
            "affected": pages, "issues": [], "retry": False}


def route_apply(state: dict) -> str:
    if state["issues"]:
        return "plan" if state["retry"] else "reply"
    return "verify"


def check(ctx, deck: int, pages: list[str], seq: int | None = None, ids: set[str] | None = None) -> dict:
    """Measure `pages`, write the rendered box of auto-sized nodes, lint. The boxes go into batch `seq` for `ids`
    (verify after apply), or as a new "자동 크기 맞춤" batch for every node there (a check without edits)."""
    store = ctx.store
    existing = [p["id"] for p in store.pages(deck)]
    pages = [p for p in pages if p in existing]
    measured = ctx.measure(deck, pages) if pages else {}
    nodes = store.deck(deck)["nodes"]
    fixes = autosize_fixes(nodes, measured or {}, ids if ids is not None else {n["id"] for n in nodes})
    rev = {n["id"]: n["rev"] for n in nodes}
    batch = [{"op": "set", "id": i, "props": p} | ({} if seq is not None else {"rev": rev[i]}) for i, p in fixes.items()]
    try:
        wrote = bool(fixes) and bool(ctx.amend(deck, seq, batch) if seq is not None else ctx.commit(deck, batch, "자동 크기 맞춤"))
    except (ops.OpError, ops.Conflict):  # the user edited one of them meanwhile
        wrote = False
    if wrote:
        nodes = store.deck(deck)["nodes"]
    else:  # someone edited after the batch: judge the measured boxes without writing them
        nodes = [n | {"props": n["props"] | fixes[n["id"]]} if n["id"] in fixes else n for n in nodes]
    found = lint.lint(nodes, pages, measured, store.has_asset)
    notes = [] if measured is not None else ["Chrome이 없어 글자 넘침은 확인하지 못했습니다."]
    return {"pages": pages, "issues": [f for f in found if f["level"] == "error"], "warnings": [f for f in found if f["level"] != "error"],
            "verify_notes": notes, "autosized": sorted(fixes)}


def verify(state: dict, ctx) -> dict:
    deck, plan = state["deck"], state["plan"]
    if plan["kind"] == "check":
        found = check(ctx, deck, plan["pages"] or [p["id"] for p in ctx.store.pages(deck)])
    else:
        found = check(ctx, deck, state.get("affected", []), state["applied"]["seq"], set(state["applied"]["revs"]))
    shots = [s["path"] for s in (ctx.snapshot(deck, p) for p in found.pop("pages")) if s]
    retry = bool(found["issues"]) and state.get("tries", 0) < MAX_TRIES
    return found | {"snapshots": shots, "retry": retry, "tries": state.get("tries", 0) + int(retry)}


def autosize_fixes(nodes: list[dict], measured: dict, ids: set[str]) -> dict[str, dict]:
    """{id: {w?, h?, x?}} for auto-sized nodes among `ids` whose stored box differs from the rendered one."""
    box = lint.boxes(nodes)
    fixes = {}
    for n in nodes:
        m = measured.get(n["id"])
        if n["id"] not in ids or not m:
            continue
        wide, tall = lint.auto_sized(n)
        p, props = lint.resolved(n), {}
        if wide and abs(m["w"] - p["w"]) > 0.5:
            props["w"] = round(m["w"], 2)
        if tall and abs(m["h"] - p["h"]) > 0.5:
            props["h"] = round(m["h"], 2)
        if wide and n["type"] == "text" and p["alignH"] in ("CENTER", "RIGHT"):  # the renderer keeps the anchor; x moves
            x = round(m["x"] - (box[n["id"]][0] - p["x"]), 2)
            if abs(x - p["x"]) > 0.5:
                props["x"] = x
        if props:
            fixes[n["id"]] = props
    return fixes


def route_verify(state: dict) -> str:
    return "plan" if state["issues"] and state["retry"] else "reply"


def export(state: dict, ctx) -> dict:
    spec = state["plan"]["pdf"]
    try:
        return {"export": {"files": ctx.export(state["deck"], spec["pages"], spec["mode"], spec["dir"])}}
    except pdf.ChromeMissing as exc:
        return {"export": {"error": str(exc), "fallback": "print"}}
    except (pdf.PdfError, ValueError) as exc:
        return {"export": {"error": str(exc)}}


def reply_instruction(state: dict) -> str:
    return REPLY_TEXT.format(deck=state["deck"], run=state["run"])


def accept_reply(state: dict, output, ctx) -> dict:
    out = _strict(output, {"text", "resolved_focus", "suggestions"}, "reply")
    text, resolved, tips = out.get("text"), out.get("resolved_focus") or [], out.get("suggestions") or []
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise StepError("text는 비어 있지 않은 20000자 이하 문자열입니다.")
    if not isinstance(resolved, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in resolved):
        raise StepError("resolved_focus는 핀 id(정수) 목록입니다.")
    if not isinstance(tips, list) or len(tips) > 5 or not all(isinstance(t, str) and 0 < len(t) <= 200 for t in tips):
        raise StepError("suggestions는 200자 이하 문자열 5개 이하입니다.")
    body = text.strip() + ("\n\n" + "\n".join(f"추천: {t}" for t in tips) if tips else "")
    msg = ctx.say(state["deck"], body, {"run": state["run"], "suggestions": tips})
    done = [i for i in resolved if ctx.store.update_pin(state["deck"], i, status="resolved")]
    if done:
        ctx.pins_changed(state["deck"])
    return {"reply": {"text": body, "message": msg["id"], "resolved_focus": done, "suggestions": tips}}


def edit_graph() -> StateGraph:
    g = StateGraph("edit")
    g.add_node("intake", intake)
    g.add_node("plan", instruction=plan_instruction, accept=accept_plan)
    g.add_node("confirm", confirm)
    g.add_node("apply", apply)
    g.add_node("verify", verify)
    g.add_node("export", export)
    g.add_node("reply", instruction=reply_instruction, accept=accept_reply)
    g.set_entry_point("intake")
    g.add_edge("intake", "plan")
    g.add_conditional_edges("plan", route_plan)
    g.add_conditional_edges("confirm", lambda s: "apply" if s["confirm"]["ok"] else "reply")
    g.add_conditional_edges("apply", route_apply)
    g.add_conditional_edges("verify", route_verify)
    g.add_edge("export", "reply")
    g.add_edge("reply", END)
    return g
