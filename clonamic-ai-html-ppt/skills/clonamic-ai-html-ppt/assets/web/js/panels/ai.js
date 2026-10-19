// AI sidebar (format.md §9): connection badge, live agent-graph strip, confirm card, chat with
// context chips and quick requests, focus pins, run history. Also inline AI on the canvas (⌘J).
// All text is plain (textContent); "추천: …" lines in the latest AI message become buttons.

import * as S from "../select.js";
import { el, toast, ICON } from "../ui.js";
import { STATUS_LABEL } from "../focus.js";

const QUICK = /^추천\s*:\s*(.+)$/;
const NODE_LABEL = { intake: "이해", plan: "계획", confirm: "확인", apply: "적용", verify: "검증", export: "내보내기", reply: "답변" };
const HOST_LABEL = { "claude-code": "Claude Code", codex: "Codex", cursor: "Cursor", grok: "Grok", other: "AI" };
const CODE_LABEL = { small_text: "작은 글자", contrast: "명암비", overlap_text: "글 상자 겹침", near_miss: "2px 어긋남" };
const RUN_STATUS = { active: "진행 중", waiting_user: "확인 필요", done: "완료", failed: "실패" };
const QUICK_REQ = [
  ["이 페이지 다듬기", "이 페이지의 디자인을 다듬어 주세요. 정렬, 간격, 글자 크기 위계를 정리해 주세요."],
  ["정렬 맞추기", "이 페이지(또는 선택한 요소)의 정렬과 간격을 맞춰 주세요."],
  ["맞춤법 확인", "이 페이지 텍스트의 맞춤법과 띄어쓰기를 확인해서 고쳐 주세요."],
  ["선택 요소 개선", "선택한 요소를 더 보기 좋게 개선해 주세요."],
  ["이 페이지 PDF", "이 페이지를 PDF로 내보내 주세요."],
];

export function mountAI(box, C, { onUnread, focus } = {}) {
  let status = null;                 // {connected, host, seen_s, run}
  let viewRun = null;                // run id shown in the strip
  const details = new Map();         // run id -> {run, state, steps}
  const runs = new Map();            // run id -> summary (+created)
  const lastStatus = new Map();      // run id -> status seen
  const watch = new Set();           // runs this tab started or saw go live (polled until they end)
  const affected = new Map();        // run id -> Set(node ids) from live `ops` events
  const busy = new Map();            // run id -> [ids] (inline edits in progress)
  const msgs = new Map();
  const openGroups = new Set();      // warning kinds the user opened (kept across repaints)
  const off ={ sel: false, page: false, pins: false };

  // ---- DOM ----
  const badge = el("div", { class: "ai-badge", role: "status", "aria-live": "polite" });
  const hint = el("div", { class: "ai-hint" });
  const strip = el("div", { class: "ai-strip", "aria-label": "AI 작업 단계" });
  const confirmSlot = el("div", { class: "ai-confirm-slot" });
  const list = el("div", { class: "chat-list", role: "log", "aria-label": "대화" });
  const pinsBox = el("details", { class: "ai-sec" });
  const runsBox = el("details", { class: "ai-sec" });
  const chips = el("div", { class: "ctx-chips", "aria-label": "함께 보낼 내용" });
  const quick = el("div", { class: "quick-req", role: "group", "aria-label": "빠른 요청" },
    ...QUICK_REQ.map(([label, text]) => el("button", { type: "button", on: { click: () => send(text) } }, label)));
  const input = el("textarea", { rows: "3", placeholder: "AI에게 요청 (Enter 보내기, Shift+Enter 줄바꿈)", "aria-label": "메시지" });
  const sendBtn = el("button", { type: "submit", class: "primary" }, "보내기");
  const form = el("form", { class: "chat-form" }, chips, quick, input, el("div", { class: "row end" }, sendBtn));
  box.replaceChildren(el("div", { class: "ai-head" }, badge, hint), strip, confirmSlot, list, pinsBox, runsBox, form);

  // ---- status badge ----
  function paintStatus() {
    const s = status;
    const running = s?.run && (s.run.status === "active");
    badge.dataset.state = !s?.connected ? "off" : running ? "busy" : "on";
    badge.replaceChildren(el("span", { class: "ai-dot", "aria-hidden": "true" }),
      el("span", {}, !s?.connected ? "연결 안 됨" : running ? "응답 대기 중…" : `연결됨 · ${HOST_LABEL[s.host] || s.host || "AI"}`));
    hint.hidden = !!s?.connected;
    if (!s?.connected) {
      const cmd = "/clonamic-ai-html-ppt";
      hint.replaceChildren(el("span", {}, "터미널에서 실행하면 연결됩니다"), el("code", {}, cmd),
        el("button", { type: "button", class: "small", "aria-label": "명령 복사", on: { click: () => navigator.clipboard?.writeText(cmd).then(() => toast("복사했습니다."), () => toast(cmd)) } }, "복사"));
    }
  }

  // ---- runs ----
  async function fetchDetail(id) {
    const r = await C.api.run(C.deckId, id);
    if (r.ok && r.data) { details.set(id, r.data); if (r.data.run) runs.set(id, { ...(runs.get(id) || {}), ...r.data.run }); }
    paintRun(); paintRuns();
    return details.get(id);
  }
  let detailT = 0;
  function onRunSummary(sum) {
    if (!sum || sum.id == null) return;
    runs.set(sum.id, { ...(runs.get(sum.id) || {}), ...sum });
    const prev = lastStatus.get(sum.id);
    lastStatus.set(sum.id, sum.status);
    if (viewRun == null || sum.status === "active" || sum.status === "waiting_user" || viewRun === sum.id) viewRun = sum.id;
    clearTimeout(detailT);
    detailT = setTimeout(() => fetchDetail(sum.id), 150);
    if (prev && prev !== sum.status && (sum.status === "done" || sum.status === "failed")) onRunEnd(sum);
    paintRun(); paintRuns(); S.requestDraw();
  }
  // Undo everything a run applied (server endpoint); deck-wide undo only where the endpoint is missing.
  async function undoRun(id) {
    const r = await C.api.undoRun(C.deckId, id);
    if (r.ok) { toast("AI 변경을 되돌렸습니다.", { timeout: 2500 }); return; }
    if (r.status === 404 || r.status === 405) { C.store.undo(); return; }
    toast(r.data?.error || "되돌리지 못했습니다.", { kind: "error", timeout: 7000 });
  }
  async function onRunEnd(sum) {
    const wasInline = busy.has(sum.id);
    busy.delete(sum.id);
    S.requestDraw();
    const d = await fetchDetail(sum.id);
    if (sum.status === "failed") { toast(`AI 작업 실패: ${d?.state?.error || sum.label || ""}`.trim(), { kind: "error", timeout: 8000 }); return; }
    // Only runs that really applied batches get the change toast (state.applied_seqs).
    const st = d?.state || {};
    const applied = Array.isArray(st.applied_seqs) ? st.applied_seqs.length > 0 : !!st.applied;
    const declined = (d?.steps || []).some((x) => x.node === "confirm" && x.status === "resumed" && x.detail?.value === false) || (st.deletions && !applied);
    if (applied) {
      toast(`AI가 바꾼 내용${sum.label ? ` · ${String(sum.label).slice(0, 40)}` : ""}`, {
        timeout: 9000, onClick: () => selectAffected(sum.id),
        actions: [{ label: "되돌리기", run: () => undoRun(sum.id) }],
      });
    } else if (declined) toast("취소했습니다 · 바뀐 것 없음", { timeout: 4000 });
    else if (wasInline) toast("AI가 바꾼 것이 없습니다.", { timeout: 4000 });
  }
  function affectedIds(id) {
    const live = [...(affected.get(id) || [])];
    const plan = details.get(id)?.state?.plan;
    const fromPlan = (plan?.ops || []).map((o) => o.id || o.node?.id).filter(Boolean);
    return [...new Set([...live, ...fromPlan])].filter((x) => C.store.get(x));
  }
  async function selectAffected(id) {
    if (!details.has(id)) await fetchDetail(id);
    const ids = affectedIds(id);
    const nodes = ids.filter((x) => C.store.get(x).type !== "page");
    const top = S.topLevel(nodes);
    if (top.length) { C.selection.set(top); C.viewport.fitSelection(); }
    else if (ids.length) C.viewport.zoomToPage(ids[0]);
    else toast("바뀐 요소를 찾지 못했습니다.");
  }
  C.store.on("remote", (ev) => {
    if (ev.actor !== "ai") return;
    const run = status?.run && (status.run.status === "active" || status.run.status === "waiting_user") ? status.run.id : null;
    const ids = (ev.ops || []).map((o) => o.id || o.node?.id).filter(Boolean);
    if (run != null) {
      if (!affected.has(run)) affected.set(run, new Set());
      ids.forEach((x) => affected.get(run).add(x));
    } else {
      // AI edits outside a run (CLI ops): one toast per batch.
      toast(`AI가 바꾼 내용${ev.label ? ` · ${String(ev.label).slice(0, 40)}` : ""}`, {
        timeout: 8000, actions: [{ label: "되돌리기", run: () => C.store.undo() }],
        onClick: () => { const t = S.topLevel(ids.filter((x) => C.store.get(x) && C.store.get(x).type !== "page")); if (t.length) { C.selection.set(t); C.viewport.fitSelection(); } },
      });
    }
  });

  function paintRun() {
    const sum = viewRun != null ? runs.get(viewRun) : null;
    strip.hidden = !sum;
    confirmSlot.replaceChildren();
    if (!sum) return;
    const d = details.get(sum.id);
    const visited = new Set((d?.steps || []).map((s) => s.node));
    const order = ["intake", "plan", ...(visited.has("confirm") || sum.node === "confirm" ? ["confirm"] : []),
      ...(visited.has("export") || sum.node === "export" ? ["export"] : ["apply", "verify"]), "reply"];
    const live = sum.status === "active" || sum.status === "waiting_user";
    const cur = live ? sum.node : null;
    const failedAt = sum.status === "failed" ? sum.node : null;
    const nodes = order.map((n, i) => el("li", { class: `step${n === cur ? " cur" : ""}${visited.has(n) && n !== cur ? " done" : ""}${n === failedAt ? " fail" : ""}`, "aria-current": n === cur ? "step" : null },
      el("span", {}, NODE_LABEL[n] || n), i < order.length - 1 ? el("span", { class: "arrow", "aria-hidden": "true" }, "→") : null));
    const head = el("div", { class: "strip-head" },
      el("span", { class: "strip-label" }, sum.label || `실행 ${sum.id}`),
      el("span", { class: `run-st st-${sum.status}` }, RUN_STATUS[sum.status] || sum.status),
      sum.tries ? el("span", { class: "tries" }, `재시도 ${sum.tries}`) : null);
    // errors one by one; warnings grouped by kind with a count, each group opens to its items
    const item = (w) => el("li", {}, el("button", { type: "button", class: `warn ${w.level === "error" ? "err" : ""}`, on: { click: () => {
      if (w.id && C.store.get(w.id)) { C.selection.set([w.id]); C.viewport.fitSelection(); }
      else if (w.page && C.store.get(w.page)) C.viewport.zoomToPage(w.page);
    } } }, w.level === "error" ? "오류 · " : "", String(w.message || w.code || "").slice(0, 200)));
    const errors = (d?.state?.issues || []).map((x) => ({ ...x, level: "error" }));
    const groups = new Map();
    for (const w of d?.state?.warnings || []) groups.set(w.code, [...(groups.get(w.code) || []), w]);
    const warn = errors.length || groups.size ? el("ul", { class: "warn-list" }, ...errors.slice(0, 50).map(item),
      ...[...groups].map(([code, ws]) => el("li", {}, el("details", { class: "warn-group", open: openGroups.has(code),
        on: { toggle: (e) => openGroups[e.target.open ? "add" : "delete"](code) } },
        el("summary", { class: "warn" }, `주의 · ${CODE_LABEL[code] || code} ${ws.length}건`),
        el("ul", {}, ...ws.slice(0, 100).map(item)))))) : null;
    strip.replaceChildren(...[head, el("ol", { class: "steps" }, ...nodes), warn].filter(Boolean));
    if (sum.status === "waiting_user") confirmSlot.append(confirmCard(sum, d));
  }
  function confirmCard(sum, d) {
    const del = d?.state?.deletions || {};
    const pages = (del.pages || []).map((id) => C.store.get(id)?.props.name || id);
    const yes = el("button", { type: "button", class: "danger" }, "진행");
    const no = el("button", { type: "button", class: "ghost" }, "취소");
    const answer = async (ok) => {
      yes.disabled = no.disabled = true;
      const r = await C.api.confirmRun(C.deckId, sum.id, ok);
      if (!r.ok) { yes.disabled = no.disabled = false; toast(r.data?.error || "응답을 보내지 못했습니다.", { kind: "error" }); }
    };
    yes.addEventListener("click", () => answer(true));
    no.addEventListener("click", () => answer(false));
    return el("div", { class: "confirm-card", role: "alertdialog", "aria-label": "삭제 확인" },
      el("div", { class: "panel-title" }, "AI가 지우려고 합니다"),
      el("p", {}, `요소 ${del.count ?? "여러"}개${pages.length ? `, 페이지 ${pages.length}개` : ""}를 지웁니다.`),
      pages.length ? el("ul", { class: "del-pages" }, ...pages.slice(0, 10).map((n) => el("li", {}, n))) : null,
      el("div", { class: "row end" }, no, yes));
  }
  function paintRuns() {
    const all = [...runs.values()].sort((a, b) => b.id - a.id).slice(0, 10);
    runsBox.hidden = !all.length;
    const open = runsBox.open;
    runsBox.replaceChildren(el("summary", {}, `최근 실행 (${all.length})`),
      el("ul", { class: "run-list" }, ...all.map((r) => el("li", {}, el("button", { type: "button", class: viewRun === r.id ? "on" : "", on: { click: () => { viewRun = r.id; fetchDetail(r.id); selectAffected(r.id); } } },
        el("span", { class: `run-st st-${r.status}` }, RUN_STATUS[r.status] || r.status),
        el("span", { class: "run-label" }, r.label || `실행 ${r.id}`),
        el("span", { class: "dim" }, r.tries ? `재시도 ${r.tries}` : ""))))));
    runsBox.open = open;
  }

  // ---- messages ----
  function paintMsgs() {
    const all = [...msgs.values()].sort((a, b) => (a.created || 0) - (b.created || 0) || (a.id - b.id));
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
    const last = all[all.length - 1];
    list.replaceChildren(...(all.length ? all.map((m) => item(m, m === last && m.role === "ai")) : [el("div", { class: "chat-empty" }, "AI에게 슬라이드 작업을 부탁하세요. 선택한 요소, 현재 페이지, 열린 핀이 함께 전달됩니다.")]));
    if (atBottom || last?.role === "user") list.scrollTop = list.scrollHeight;
  }
  function item(m, withQuick) {
    const text = String(m.text || "");
    const ctx = [];
    if (m.meta?.mode === "inline") ctx.push("캔버스에서");
    if (m.meta?.selection?.length) ctx.push(`선택 ${m.meta.selection.length}개`);
    if (m.meta?.focus?.length) ctx.push(`핀 ${m.meta.focus.length}개`);
    const bubble = el("div", { class: `msg ${m.role === "ai" ? "ai" : "user"}${m.meta?.kind === "confirm" ? " confirm" : ""}` },
      el("div", { class: "who" }, m.role === "ai" ? "AI" : "나", ctx.length ? el("span", { class: "dim" }, ` · ${ctx.join(" · ")}`) : null),
      el("div", { class: "body" }, text.split("\n").filter((l) => !(withQuick && QUICK.test(l.trim()))).join("\n")));
    if (!withQuick) return bubble;
    const picks = text.split("\n").map((l) => l.trim().match(QUICK)?.[1].trim()).filter(Boolean);
    return picks.length ? el("div", { class: "msg-wrap" }, bubble,
      el("div", { class: "quick", role: "group", "aria-label": "추천 답" }, ...picks.map((p) => el("button", { type: "button", on: { click: () => send(p) } }, p)))) : bubble;
  }

  // ---- context chips ----
  const openPins = () => (focus?.pins || []).filter((p) => p.status === "open");
  function paintChips() {
    const sel = C.selection.ids.filter((id) => C.store.get(id));
    const page = C.currentPage();
    const items = [];
    const chip = (key, label) => el("span", { class: "ctx-chip" }, label,
      el("button", { type: "button", "aria-label": `${label} 빼기`, title: "빼기", html: ICON.close, on: { click: () => { off[key] = true; paintChips(); } } }));
    if (sel.length && !off.sel) items.push(chip("sel", `선택 ${sel.length}개`));
    if (page && !off.page) items.push(chip("page", `${C.store.get(page)?.props.name || "페이지"}`));
    const pins = openPins();
    if (pins.length && !off.pins) items.push(chip("pins", `핀 ${pins.length}개`));
    chips.replaceChildren(...items);
    chips.hidden = !items.length;
  }
  C.selection.on(() => { off.sel = false; paintChips(); });
  C.onPageChange(() => { off.page = false; paintChips(); });
  focus?.onChange(() => { paintChips(); paintPins(); });

  // ---- send ----
  async function send(text, extra = {}) {
    text = String(text || "").trim();
    if (!text) return false;
    const meta = {};
    const page = extra.page || (!off.page ? C.currentPage() : null);
    if (page) meta.page = page;
    const sel = extra.selection || (!off.sel ? C.selection.ids.filter((id) => C.store.get(id)) : []);
    if (sel.length) meta.selection = sel.slice(0, 1000);
    const pins = extra.focus || (!off.pins ? openPins().map((p) => p.id) : []);
    if (pins.length) meta.focus = pins;
    if (extra.mode) meta.mode = extra.mode;
    sendBtn.disabled = true;
    const r = await C.api.postMessage(C.deckId, { role: "user", text: text.slice(0, 100000), meta });
    sendBtn.disabled = false;
    if (!r.ok) { toast(`보내지 못했습니다: ${r.data?.error || r.status}`, { kind: "error" }); return false; }
    const id = r.data?.id;
    if (id != null && !msgs.has(id)) msgs.set(id, { id, role: "user", text, meta, status: "pending", created: Date.now() / 1000 });
    const run = r.data?.run;
    if (run != null) {
      watch.add(run);
      if (extra.mode === "inline") busy.set(run, sel);
      onRunSummary({ id: run, node: "intake", status: "active", label: text.slice(0, 40), tries: 0 });
    }
    off.sel = off.page = off.pins = false;
    paintMsgs(); paintChips(); S.requestDraw();
    if (!status?.connected) toast("AI가 연결되어 있지 않습니다. 터미널에서 /clonamic-ai-html-ppt 를 실행하면 이어서 처리합니다.", { timeout: 7000 });
    return true;
  }
  form.addEventListener("submit", async (e) => { e.preventDefault(); if (await send(input.value)) input.value = ""; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); form.requestSubmit(); }
  });

  // ---- pins list ----
  function paintPins() {
    const all = focus?.pins || [];
    pinsBox.hidden = !focus;
    if (!focus) return;
    const shown = all.filter((p) => focus.showResolved || p.status !== "resolved");
    const open = pinsBox.open;
    const toggle = el("label", { class: "check-row" }, el("input", { type: "checkbox", checked: focus.showResolved || null, on: { change: (e) => focus.setShowResolved(e.target.checked) } }), "해결된 핀 보기");
    pinsBox.replaceChildren(el("summary", {}, `포커스 핀 (${all.filter((p) => p.status !== "resolved").length})`),
      shown.length ? el("ul", { class: "pin-list" }, ...shown.map((p) => el("li", { class: `pin-row st-${p.status}` },
        el("button", { type: "button", class: "pin-num", "aria-label": `핀 ${focus.number(p.id)} 보기`, on: { click: () => focus.selectPin(p.id) } }, String(focus.number(p.id))),
        el("button", { type: "button", class: "pin-note", on: { click: () => focus.open(p.id) } }, p.note || "메모 없음"),
        el("span", { class: "pin-st" }, STATUS_LABEL[p.status] || p.status),
        el("button", { type: "button", class: "small", title: "AI에게 보내기", on: { click: () => focus.send([p.id]) } }, "보내기"),
        el("button", { type: "button", class: "icon-btn sm", "aria-label": "핀 삭제", title: "삭제", html: ICON.trash, on: { click: () => focus.remove(p.id) } })))) :
        el("p", { class: "hint" }, "핀 도구(⌘⇧J)로 요소를 누르거나 영역을 끌어 AI에게 짚어 줄 곳을 표시하세요."),
      toggle);
    pinsBox.open = open || !!all.filter((p) => p.status === "open").length;
  }

  // ---- inline AI on canvas ----
  const fab = el("button", { type: "button", class: "ai-fab", title: "AI로 수정 (⌘J)", "aria-label": "AI로 수정", html: `${ICON.sparkle}<span>AI</span>`, on: { click: (e) => { e.stopPropagation(); openInline(); } } });
  fab.addEventListener("pointerdown", (e) => e.stopPropagation());
  C.aiLayer.append(fab);
  let inline = null;
  function selBox() { const ids = C.selection.ids.filter((id) => C.store.get(id)); return ids.length ? S.selectionBounds(ids) : null; }
  S.addDrawer((svg, { toS, s }) => {
    // The floating AI button sits centered under the size badge: >= 30 px below every corner, so it is
    // always outside the resize handles and the 20 px rotate zones, at any zoom.
    const b = selBox();
    const show = b && !inline && !S.dragging() && !C.textEdit && !S.vectorEditing() && (C.tool === "move" || C.tool === "scale");
    fab.hidden = !show;
    if (show) { const p = toS({ x: b.x + b.w / 2, y: b.y + b.h }); fab.style.transform = `translate(${Math.round(p.x - (fab.offsetWidth || 40) / 2)}px, ${Math.round(p.y + 30)}px)`; }
    if (inline) { const p = b ? toS({ x: b.x + b.w / 2, y: b.y + b.h }) : { x: 200, y: 40 }; inline.style.transform = `translate(${Math.round(Math.max(8, p.x - (inline.offsetWidth || 340) / 2))}px, ${Math.round(p.y + 30)}px)`; }
    // busy outlines for running inline edits
    for (const [, ids] of busy) for (const id of ids) {
      if (!C.store.get(id)) continue;
      const q = S.cornersOf(id).map(toS);
      svg.append(s("polygon", { points: q.map((p) => `${p.x},${p.y}`).join(" "), class: "ov-busy" }));
    }
  });
  function openInline() {
    const ids = C.selection.ids.filter((id) => C.store.get(id));
    if (!ids.length) { toast("먼저 고칠 요소를 선택하세요."); return; }
    closeInline();
    const field = el("input", { type: "text", placeholder: "선택한 요소를 어떻게 바꿀까요?", "aria-label": "AI 요청", maxlength: "2000" });
    const go = el("button", { type: "button", class: "primary small", "aria-label": "보내기" }, "보내기");
    inline = el("div", { class: "ai-inline", role: "dialog", "aria-label": "AI로 수정" }, el("span", { class: "spark", html: ICON.sparkle }), field, go);
    inline.addEventListener("pointerdown", (e) => e.stopPropagation());
    const submit = async () => {
      const text = field.value.trim();
      if (!text) return;
      field.disabled = go.disabled = true;
      const ok = await send(text, { mode: "inline", selection: ids, page: C.store.pageIdOf(ids[0]) });
      if (ok) closeInline(); else { field.disabled = go.disabled = false; field.focus(); }
    };
    field.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.isComposing || e.keyCode === 229) return;
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      if (e.key === "Escape") { e.preventDefault(); closeInline(); C.container.focus(); }
    });
    go.addEventListener("click", submit);
    C.aiLayer.append(inline);
    S.requestDraw();
    setTimeout(() => field.focus(), 0);
  }
  function closeInline() { inline?.remove(); inline = null; S.requestDraw(); }
  C.selection.on(() => { if (inline) closeInline(); });

  // ---- load + live ----
  async function load() {
    const [a, rs, ms] = await Promise.all([C.api.aiStatus(C.deckId), C.api.runs(C.deckId, 10), C.api.messages(C.deckId)]);
    if (rs.ok && Array.isArray(rs.data)) for (const r of rs.data) { runs.set(r.id, r); lastStatus.set(r.id, r.status); }
    if (ms.ok && Array.isArray(ms.data)) for (const m of ms.data) msgs.set(m.id, m);
    if (a.ok && a.data) { status = a.data; if (status.run) { viewRun = status.run.id; lastStatus.set(status.run.id, status.run.status); fetchDetail(status.run.id); } }
    paintStatus(); paintRun(); paintRuns(); paintMsgs(); paintChips(); paintPins();
  }
  // While a run is live, poll it: SSE `ai` events can be missed or coalesced, and the end of a run
  // drives the busy outline and the change toast.
  let polling = false;
  setInterval(async () => {
    if (polling) return;
    const live = [...watch].filter((id) => { const st = lastStatus.get(id); return st === "active" || st === "waiting_user"; });
    if (!live.length) return;
    polling = true;
    try {
      for (const id of live.slice(-3)) {
        const r = await C.api.run(C.deckId, id);
        const sum = r.ok && r.data?.run;
        if (sum && (sum.status !== lastStatus.get(id) || sum.node !== runs.get(id)?.node || sum.tries !== runs.get(id)?.tries)) onRunSummary(sum);
      }
    } finally { polling = false; }
  }, 1500);
  // Safety poll: the server announces changes over SSE, this only covers a missed event.
  setInterval(async () => { const a = await C.api.aiStatus(C.deckId); if (a.ok && a.data) api.onAI(a.data); }, 15000);

  const api = {
    onAI(s) {
      if (!s) return;
      const changed = JSON.stringify(s) !== JSON.stringify(status);
      status = s;
      if (changed) paintStatus();
      if (s.run) {
        if (s.run.status === "active" || s.run.status === "waiting_user") watch.add(s.run.id);
        onRunSummary(s.run);
      }
    },
    receive(m) {
      if (!m || m.id == null) return;
      const isNew = !msgs.has(m.id);
      msgs.set(m.id, { ...(msgs.get(m.id) || {}), ...m });
      paintMsgs();
      if (isNew && m.role === "ai") onUnread?.();
      if (m.meta?.kind === "confirm" && m.meta.run != null) fetchDetail(m.meta.run);
    },
    send, openInline, closeInline,
    focus: () => input.focus(),
    get connected() { return !!status?.connected; },
  };
  load();
  return api;
}
