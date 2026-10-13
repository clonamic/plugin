"use strict";

// ---------- state ----------
const S = {
  schema: null, projects: [], pid: null, doc: null, version: 0, polished: false, exportPath: "", defaultPath: "",
  level: "agents", sel: null, dirty: false, saving: false, saveTimer: null, savedAt: 0,
  msgs: [], lastMsg: 0, tab: "doc", unread: false, aiSeen: null, draw: false, preview: false,
  undo: [], redo: [], lastKey: null, lastAt: 0, issues: [], fitNext: true,
};
const $ = (id) => document.getElementById(id);
let cy = null;

// ---------- api ----------
async function api(method, path, body, keepalive = false) {
  let res;
  try {
    res = await fetch(path, {
      method, headers: { "Content-Type": "application/json", "X-Clonamic": "1" }, keepalive,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (_) {
    return { ok: false, status: 0, data: { error: "편집기 서버에 연결할 수 없습니다." } };  // server stopped or page reloading
  }
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty body */ }
  return { ok: res.ok, status: res.status, data };
}

// ---------- helpers ----------
function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "on") for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
    else if (k === "text") node.textContent = v;
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) node.append(kid.nodeType ? kid : document.createTextNode(kid));
  return node;
}
const nextId = (items, prefix) => prefix + (Math.max(0, ...items.map((x) => parseInt(String(x.id).slice(prefix.length), 10) || 0)) + 1);
const agentOf = (aid) => S.doc.agents.find((a) => a.id === aid);
const curAgent = () => (S.level === "agents" ? null : agentOf(S.level));
function nodeName(a, ref) {
  if (ref === "start") return "시작";
  if (ref === "end") return "끝";
  const item = (a ? a.steps : S.doc.agents).find((x) => x.id === ref);
  return item ? item.name : ref;
}
// Only a #rrggbb value reaches inline styles (an imported file could hold anything).
function colorOf(a) {
  return /^#[0-9a-f]{6}$/i.test(a.color || "") ? a.color : S.schema.colors[S.doc.agents.indexOf(a) % S.schema.colors.length];
}
function layout(level) {
  S.doc.layout = S.doc.layout || {};
  S.doc.layout[level] = S.doc.layout[level] || {};
  return S.doc.layout[level];
}

// ---------- undo / redo ----------
// Call before mutating S.doc. Typing in the same field within a short pause is one step.
function snapshot(key = null) {
  const now = Date.now();
  if (key && key === S.lastKey && now - S.lastAt < 1200) { S.lastAt = now; return; }
  S.lastKey = key; S.lastAt = now;
  S.undo.push(JSON.stringify(S.doc));
  if (S.undo.length > 100) S.undo.shift();
  $("toast").querySelector("button")?.remove();  // its undo would now undo this newer edit
  S.redo = [];
  renderHistoryButtons();
}
function restore(from, to) {
  if (!from.length) return;
  to.push(JSON.stringify(S.doc));
  S.doc = JSON.parse(from.pop());
  S.lastKey = null;
  if (S.level !== "agents" && !agentOf(S.level)) { S.level = "agents"; S.fitNext = true; }
  if (S.sel && !selected()) S.sel = null;
  markDirty();
  renderAll();
}
const undo = () => restore(S.undo, S.redo);
const redo = () => restore(S.redo, S.undo);
function renderHistoryButtons() {
  const u = $("btn-undo"), r = $("btn-redo");
  if (u) u.disabled = !S.undo.length;
  if (r) r.disabled = !S.redo.length;
}

function icon(d) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", d);
  svg.append(path);
  return svg;
}

// ---------- text measuring ----------
// Explicit line breaks keep each box exactly as large as its text, so nothing spills or overlaps.
const ctx2d = document.createElement("canvas").getContext("2d");
function wrapText(text, max, font) {
  ctx2d.font = font;
  const lines = [];
  for (const para of String(text).split("\n")) {
    let line = "";
    for (const word of para.split(/(\s+)/)) {
      if (!word) continue;
      if (ctx2d.measureText(line + word).width <= max) { line += word; continue; }
      if (line.trim()) { lines.push(line.trim()); line = ""; }
      for (const ch of word.trim()) {
        if (ctx2d.measureText(line + ch).width > max && line) { lines.push(line); line = ""; }
        line += ch;
      }
    }
    lines.push(line.trim());
  }
  const width = Math.max(...lines.map((l) => ctx2d.measureText(l).width));
  return { text: lines.join("\n"), width, count: lines.length };
}

const mod = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";

// ---------- modal ----------
// Focus starts on the first field or the main button; a delete dialog starts on 취소, so Enter never deletes by accident.
let modalOpener = null;
function modal(title, body, actions) {
  closeMenu();
  const box = $("modal").firstElementChild;
  if ($("modal").hidden) modalOpener = document.activeElement;
  box.replaceChildren(el("h2", { text: title }), ...[body].flat(),
    el("div", { class: "row" }, ...actions.map(([label, fn, cls]) => el("button", { type: "button", class: cls, on: { click: fn } }, label))));
  $("modal").hidden = false;
  const first = box.querySelector("input, textarea, button.primary") || box.querySelector(".row button:not(.danger)") || box.querySelector("button");
  if (first) first.focus();
}
function closeModal() {
  $("modal").hidden = true;
  if (modalOpener?.isConnected) modalOpener.focus({ preventScroll: true });
  modalOpener = null;
}
$("modal").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); closeModal(); return; }
  if (e.key !== "Tab") return;  // keep Tab inside the dialog
  const list = [...$("modal").querySelectorAll("input, textarea, select, button:not(:disabled)")];
  const i = list.indexOf(document.activeElement);
  if (e.shiftKey && i <= 0) { e.preventDefault(); list.at(-1)?.focus(); }
  else if (!e.shiftKey && i === list.length - 1) { e.preventDefault(); list[0]?.focus(); }
});

// ---------- projects ----------
async function loadProjects() {
  const { ok, data } = await api("GET", "/api/projects");
  if (!ok) return;
  S.projects = data;
  const list = $("projects");
  list.replaceChildren(...data.map((p) => el("li", { class: p.id === S.pid ? "active" : null },
    el("button", { class: "open", type: "button", title: p.name, "aria-current": p.id === S.pid ? "true" : null, on: { click: () => openProject(p.id) } },
      el("span", { class: "name" }, p.name || "(이름 없음)"), el("span", { class: "when" }, ago(p.updated))),
    el("button", { class: "more", type: "button", "aria-label": `${p.name || "프로젝트"} 삭제`, title: "삭제", on: { click: () => askDelete(p) } }, "⋯"))));
}

function ago(sec) {
  const d = Date.now() / 1000 - sec;
  if (d < 60) return "방금 수정";
  if (d < 3600) return `${Math.floor(d / 60)}분 전 수정`;
  if (d < 86400) return `${Math.floor(d / 3600)}시간 전 수정`;
  const t = new Date(sec * 1000);
  return `${t.getMonth() + 1}월 ${t.getDate()}일 수정`;
}
function askDelete(p) {
  const input = el("input", { placeholder: p.name });
  modal("프로젝트 삭제", [el("p", {}, `편집기에서 '${p.name}' 프로젝트를 지웁니다. 이미 내보낸 문서 폴더는 그대로 남습니다. 확인하려면 프로젝트 이름을 입력하세요.`), input], [
    ["삭제", async () => {
      if (input.value.trim() !== p.name) { input.focus(); return; }
      await api("DELETE", `/api/projects/${p.id}`);
      closeModal();
      if (S.pid === p.id) { clearTimeout(S.saveTimer); S.dirty = false; S.pid = null; S.doc = null; location.hash = ""; renderAll(); }
      loadProjects();
    }, "danger"],
    ["취소", closeModal],
  ]);
}

$("new-project").addEventListener("click", () => {
  const input = el("input", { placeholder: "예: 여행 일정 도우미" });
  const create = async () => {
    const { data } = await api("POST", "/api/projects", { name: input.value.trim() || "새 프로젝트" });
    closeModal();
    await loadProjects();
    openProject(data.id);
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) create(); });
  modal("새 프로젝트", [input], [["만들기", create, "primary"], ["취소", closeModal]]);
});

$("import-project").addEventListener("click", () => $("import-file").click());
$("import-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  const res = await api("POST", "/api/projects/import", { text: await file.text() });
  if (!res.ok) { modal("가져오기 실패", [el("p", {}, res.data.error || "가져오지 못했습니다.")], [["닫기", closeModal]]); return; }
  await loadProjects();
  openProject(res.data.id);
});

async function openProject(pid) {
  await flushSave();
  const { ok, data } = await api("GET", `/api/projects/${pid}`);
  if (!ok) return;
  S.pid = pid; S.doc = data.doc; S.version = data.version; S.polished = data.polished;
  S.exportPath = data.export_path; S.defaultPath = data.default_path; S.aiSeen = data.ai_seen;
  S.level = "agents"; S.sel = null; S.msgs = []; S.lastMsg = 0; S.msgsLoaded = false; S.preview = false;
  S.undo = []; S.redo = []; S.lastKey = null; S.fitNext = true;
  $("toast").hidden = true;  // a toast belongs to the project it was shown in
  if (location.hash !== `#${pid}`) history.replaceState(null, "", `#${pid}`);
  loadProjects();
  await loadMessages();
  renderAll();
  refreshIssues();
  setTab(S.doc.agents.length ? "doc" : "chat");
}

// ---------- save ----------
function setSave(text) { $("save-state").textContent = text; }
function markDirty() {
  S.dirty = true;
  setSave("저장 중…");
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(save, 600);
}
// S.saving holds the request in flight, so flushSave() can wait for it before switching projects or exporting.
function save() {
  if (S.saving) return S.saving;
  if (!S.dirty || !S.pid) return Promise.resolve();
  S.dirty = false;
  return (S.saving = saveNow(S.pid).finally(() => { S.saving = null; if (S.dirty) markDirty(); }));
}
async function saveNow(pid) {
  const res = await api("PUT", `/api/projects/${pid}`, { doc: S.doc, version: S.version });
  if (pid !== S.pid) return;
  if (res.ok) {
    S.version = res.data.version; S.polished = false; S.savedAt = Date.now();
    setSave("저장됨 · 방금");
    refreshIssues();
  } else if (res.status === 409) {
    S.dirty = false;
    await reloadDoc();
    setSave("다른 곳에서 바뀌어 최신 내용을 다시 불러왔습니다");
  } else {
    S.dirty = true;
    setSave("저장 실패 · 다시 시도합니다");
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(save, 2000);
  }
}
async function flushSave() {
  clearTimeout(S.saveTimer);
  if (S.saving) await S.saving;
  clearTimeout(S.saveTimer);
  await save();
}
async function reloadDoc() {
  const { ok, data } = await api("GET", `/api/projects/${S.pid}`);
  if (!ok) return;
  if (JSON.stringify(data.doc) !== JSON.stringify(S.doc)) snapshot();  // AI edits and applied cards can be undone too
  S.doc = data.doc; S.version = data.version; S.polished = data.polished; S.aiSeen = data.ai_seen;
  S.exportPath = data.export_path;
  if (S.level !== "agents" && !agentOf(S.level)) { S.level = "agents"; S.fitNext = true; }
  if (S.sel && !selected()) S.sel = null;
  renderAll();
  refreshIssues();
}
async function refreshIssues() {
  if (!S.pid) return;
  const { ok, data } = await api("GET", `/api/projects/${S.pid}/check`);
  if (ok) { S.issues = data.issues; renderIssueButton(); }
}
function renderIssueButton() {
  const b = $("btn-issues");
  if (!b) return;
  b.textContent = S.issues.length ? `검사 ${S.issues.length}` : "검사 통과";
  b.classList.toggle("warn", S.issues.length > 0);
}
function openIssues() {
  modal("검사 결과", S.issues.length
    ? [el("p", {}, `고칠 항목 ${S.issues.length}개입니다. 누르면 그 위치로 갑니다.`), issueList(S.issues)]
    : [el("p", { class: "ok" }, "검사에 걸린 항목이 없습니다.")], [["닫기", closeModal]]);
}
function issueList(issues) {
  return el("ul", { class: "issues" }, ...issues.map((i) => el("li", {},
    el("button", { type: "button", on: { click: () => { closeModal(); goTo({ glossary: "glossary", tool: i.target === "project" ? "tools" : i.target }[i.code] || i.target); } } }, i.message))));
}
setInterval(() => {
  if (S.savedAt && !S.dirty && !S.saving) {
    const min = Math.floor((Date.now() - S.savedAt) / 60000);
    setSave(min < 1 ? "저장됨 · 방금" : `저장됨 · ${min}분 전`);
  }
}, 30000);
// keepalive lets the last edit reach the server while the tab closes (browsers cap such a body at 64 KB).
window.addEventListener("beforeunload", () => { if (S.dirty && S.pid) api("PUT", `/api/projects/${S.pid}`, { doc: S.doc, version: S.version }, true); });

// ---------- events from server ----------
function listen() {
  const source = new EventSource("/api/events");
  source.onmessage = async (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "projects") loadProjects();
    if (ev.project !== S.pid) return;
    if (ev.type === "project" && !S.dirty && !S.saving) {
      const { data } = await api("GET", `/api/projects/${S.pid}`);
      if (data.version > S.version) reloadDoc();
    }
    if (ev.type === "message") loadMessages();
  };
}

// ---------- canvas ----------
// Cytoscape draws the links and does hit-testing, layout, and pan/zoom on transparent node boxes.
// The visible cards are HTML laid over those boxes. A card reads top to bottom: input → 과정 → output → 다음;
// every 다음 row has a port the link leaves from, so no text ever sits on a line.
const CARD_W = 236, PILL_W = 132, LINE_H = 18;
const FONT_STACK = getComputedStyle(document.documentElement).getPropertyValue("--font").trim() || "system-ui, sans-serif";
const TITLE_FONT = `600 13px ${FONT_STACK}`, ROW_FONT = `12px ${FONT_STACK}`;
const TYPE_ICON = { "판단": "◇", "처리": "□", "외부 연동": "⇄", "사람 확인": "◉" };
const TOOL_ICON = { "MCP 서버": "🔌", "내부 에이전트": "🤖", "파일·스크립트": "📄", "외부 API": "🌐", "웹 검색": "🔍", "데이터베이스": "🗄", "모델": "🧠", "기타": "⋯" };
let specs = new Map(), cardEls = new Map();
try { S.detail = localStorage.getItem("cagent-detail") !== "0"; } catch (_) { S.detail = true; }

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function luminance(hex) {
  const v = hex.replace("#", "").match(/.{2}/g).map((h) => { const c = parseInt(h, 16) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
}
const onColor = (hex) => (1.05 / (luminance(hex) + 0.05) >= 4.5 ? "#ffffff" : "#1d1d1f");
const lines = (text, max, font, cap = 2) => Math.min(cap, Math.max(1, wrapText(text || "", max, font).count));
const toolOf = (id) => (S.doc.tools || []).find((t) => t.id === id);
function toolLabel(t) {
  if (!t) return "";
  if (t.kind === "내부 에이전트" && t.ref) { const a = agentOf(t.ref); if (a) return `${a.id} ${a.name || ""}`.trim(); }
  return t.name || t.id;
}
function issueCount(nodeId) {
  const a = curAgent();
  return S.issues.filter((i) => {
    const t = i.target || "";
    if (!a) return t === nodeId || t.startsWith(`${nodeId}-`);
    if (t === `${a.id}-${nodeId}`) return true;
    const e = a.edges.find((x) => `${a.id}-${x.id}` === t);
    return !!e && e.from === nodeId;
  }).length;
}

function outgoing(id) {
  const a = curAgent();
  return a ? a.edges.filter((e) => e.from === id) : S.doc.links.filter((l) => l.from === id);
}
const rowText = (r) => r.label + (r.data && r.data.length ? ` · ${r.data.join(", ")}` : "");
const uniq = (list) => [...new Set(list.filter(Boolean))];

// One card = a stack of fixed-height parts, so heights, ports, and click areas all come from the same numbers.
function buildSpecs() {
  const a = curAgent(), list = [];
  const destName = (e) => nodeName(a, e.to);
  // 다음 rows: where each link goes ("condition → destination" for a conditional one) and the data it carries.
  const edgeRows = (id, always) => {
    const outs = outgoing(id);
    if (!outs.length) return always ? [{ edge: null, label: "연결 없음", empty: true }] : [];
    return outs.map((e) => ({ edge: e, label: e.kind === "cond" ? `${e.name || "조건"} → ${destName(e)}` : destName(e), data: e.passes || [] }));
  };
  if (!a) {
    list.push({ id: "start", kind: "start", title: "시작", rows: outgoing("start").length > 1 ? edgeRows("start") : [], headOut: true });
    for (const x of S.doc.agents) {
      const n = issueCount(x.id);
      // An agent's input and output are what its links bring in and carry on.
      list.push({ id: x.id, kind: "agent", title: x.name, badge: x.id, color: colorOf(x), sub: x.role,
        chips: [x.steps.length ? `단계 ${x.steps.length}` : "단계 없음", n ? `⚠ ${n}` : null].filter(Boolean),
        input: uniq(S.doc.links.filter((l) => l.to === x.id).flatMap((l) => l.passes || [])),
        output: uniq(outgoing(x.id).flatMap((l) => l.passes || [])),
        rows: edgeRows(x.id, true), headOut: true, headIn: true });
    }
    list.push({ id: "end", kind: "end", title: "끝", rows: [], headIn: true });
  } else {
    list.push({ id: "start", kind: "start", title: "시작", rows: outgoing("start").length > 1 ? edgeRows("start") : [], headOut: true });
    for (const st of a.steps) {
      const n = issueCount(st.id);
      list.push({ id: st.id, kind: "step", title: st.name, badge: st.id, color: colorOf(a), sub: st.summary,
        chips: [`${TYPE_ICON[st.type] || "□"} ${st.type || "유형 없음"}`, n ? `⚠ ${n}` : null].filter(Boolean),
        input: st.inputs || [], process: (st.process || []).filter((p) => (p.name || "").trim()), output: st.outputs || [],
        tools: [...new Set([...(st.tools || []), ...(st.process || []).map((p) => p.tool).filter(Boolean)])].map(toolOf).filter(Boolean),
        rows: edgeRows(st.id, true), headOut: true, headIn: true, tip: st });
    }
    list.push({ id: "end", kind: "end", title: "끝", rows: [], headIn: true });
  }
  for (const sp of list) measure(sp);
  specs = new Map(list.map((sp) => [sp.id, sp]));
  return list;
}

function measure(sp) {
  const pill = ["start", "end"].includes(sp.kind), detail = S.detail;
  sp.w = pill ? PILL_W : CARD_W;
  sp.bt = sp.kind === "agent" ? 3 : 1;
  const parts = [];
  sp.lines = lines(sp.title, pill ? sp.w - 28 : sp.w - 24 - 36 - 8, TITLE_FONT);
  const headH = pill ? 16 + sp.lines * LINE_H + (sp.sub ? 16 : 0) : 10 + sp.lines * LINE_H + (sp.chips?.length ? 22 : 0) + 6;
  parts.push({ type: "head", h: headH });
  if (!pill && detail && sp.sub) parts.push({ type: "sub", h: 20 });
  if (!pill && detail && sp.input?.length) parts.push({ type: "input", h: 26 });
  if (!pill && detail && sp.process?.length) parts.push({ type: "process", h: 26 });
  if (!pill && detail && sp.output?.length) parts.push({ type: "output", h: 26 });
  if (sp.rows.length) {
    if (!pill) parts.push({ type: "outlabel", h: 20 });
    sp.rows.forEach((r, i) => { r.lines = lines(rowText(r), sp.w - 12 - 30, ROW_FONT); parts.push({ type: "row", i, h: r.lines === 1 ? 28 : 44 }); });
  }
  if (!pill && detail && sp.tools?.length) parts.push({ type: "tools", h: 28 });
  let y = sp.bt;
  for (const part of parts) { part.y = y; y += part.h; }
  sp.parts = parts;
  sp.headH = headH;
  sp.h = y + 1 + (pill ? 0 : 4);
}
const partOf = (sp, type, i) => sp.parts.find((x) => x.type === type && (i === undefined || x.i === i));

// Where a link attaches: the right edge of its 다음 row (or the header), and the left edge of the target header.
function endpoints(edge, sourceId, targetId) {
  const s = specs.get(sourceId), t = specs.get(targetId);
  if (!s || !t) return null;
  const i = s.rows.findIndex((r) => r.edge === edge);
  const part = i >= 0 ? partOf(s, "row", i) : partOf(s, "head");
  const sy = part.y + part.h / 2, ty = t.bt + t.headH / 2;  // from the card top
  return { sy, ty, src: `${s.w / 2}px ${sy - s.h / 2}px`, dst: `${-t.w / 2}px ${ty - t.h / 2}px` };
}

// Node.append() turns null into the text "null"; skip empty parts instead.
const add = (parent, ...kids) => parent.append(...kids.filter((k) => k !== null && k !== undefined && k !== false));
function nodeCardEl(sp) {
  const pill = ["start", "end"].includes(sp.kind);
  const node = el("div", { class: `node ${sp.kind}${pill ? " pill" : ""}${pill && sp.rows.length ? " has-rows" : ""}`, "data-id": sp.id,
    style: `width:${sp.w}px;height:${sp.h}px;--c:${sp.color || "var(--edge)"};--on-c:${sp.color ? onColor(sp.color) : "#fff"}` });
  for (const part of sp.parts) {
    const box = el("div", { class: `part ${part.type}`, style: `top:${part.y - sp.bt}px;height:${part.h}px` });
    if (part.type === "head") {
      const title = el("div", { class: "title", style: `-webkit-line-clamp:${sp.lines}` }, sp.title || "(이름 없음)");
      if (pill) add(box, title, sp.sub ? el("div", { class: "pill-sub" }, sp.sub) : null);
      else add(box, el("div", { class: "title-row" }, el("span", { class: "badge" }, sp.badge), title),
        sp.chips?.length ? el("div", { class: "chips" }, ...sp.chips.map((c) => el("span", { class: `chip${c.startsWith("⚠") ? " warn" : ""}` }, c))) : null);
    } else if (part.type === "sub") add(box, el("div", { class: "line muted" }, sp.sub));
    else if (part.type === "input" || part.type === "output") add(box, el("span", { class: "tag" }, part.type), el("span", { class: "line" }, sp[part.type].join(" · ")));
    else if (part.type === "process") add(box, el("span", { class: "tag" }, `과정 ${sp.process.length}`),
      el("span", { class: "line" }, ...sp.process.flatMap((p, i) => [i ? el("span", { class: "arrow" }, " → ") : null, p.name])));
    else if (part.type === "outlabel") add(box, el("span", { class: "tag" }, "다음"));
    else if (part.type === "row") {
      const r = sp.rows[part.i];
      box.classList.toggle("empty", !!r.empty);
      add(box, el("span", { class: "row-text", style: `-webkit-line-clamp:${r.lines}` },
        el("span", { class: "rname" }, r.label), r.data?.length ? el("span", { class: "rdata" }, ` · ${r.data.join(", ")}`) : null));
    } else if (part.type === "tools") add(box, ...sp.tools.slice(0, 4).map((t) => el("span", { class: "tool-chip", title: `${t.kind} · ${toolLabel(t)}` }, `${TOOL_ICON[t.kind] || "⋯"} ${toolLabel(t)}`)),
      sp.tools.length > 4 ? el("span", { class: "tool-chip" }, `+${sp.tools.length - 4}`) : null);
    add(node, box);
  }
  const head = partOf(sp, "head");
  if (sp.headIn) add(node, el("span", { class: "port in", style: `top:${head.y - sp.bt + head.h / 2 - 5}px` }));
  if (sp.headOut) add(node, el("span", { class: "port out head-out", "data-row": "-1", title: "끌어서 새 연결", style: `top:${head.y - sp.bt + head.h / 2 - 5}px` }));
  // Row ports sit on the card edge (outside the clipped row box) so the whole dot can be grabbed.
  for (const part of sp.parts.filter((x) => x.type === "row"))
    add(node, el("span", { class: "port out", "data-row": part.i, title: sp.rows[part.i].edge ? "끌어서 도착지 바꾸기" : "끌어서 연결", style: `top:${part.y - sp.bt + part.h / 2 - 5}px` }));
  node.querySelectorAll(".port.out").forEach((pt) => pt.addEventListener("pointerdown", (e) => startPortDrag(e, sp.id, Number(pt.dataset.row))));
  return node;
}

const STYLE = () => [
  { selector: "node", style: { shape: "round-rectangle", width: "data(w)", height: "data(h)", "background-opacity": 0, "border-width": 0, label: "" } },
  { selector: "edge", style: {
    width: 1.6, "line-color": css("--edge"), "target-arrow-color": css("--edge"), "target-arrow-shape": "triangle", "arrow-scale": 0.9,
    "curve-style": "straight", label: "" } },  // markBack() sets each link's segments
  { selector: "edge.back", style: { "line-style": "dashed", "line-dash-pattern": [6, 4] } },
  { selector: "edge.sel", style: { "line-color": css("--accent"), "target-arrow-color": css("--accent"), width: 2.6, "z-index": 9 } },
  { selector: "edge.hl", style: { "line-color": css("--hl"), "target-arrow-color": css("--hl"), width: 3, "z-index": 9 } },
];

function elements() {
  const a = curAgent(), items = [];
  buildSpecs();
  for (const sp of specs.values()) items.push({ group: "nodes", data: { id: sp.id, w: sp.w, h: sp.h } });  // one node per id, even for a hand-edited file
  const edges = a ? a.edges.map((e) => [`edge:${e.id}`, e]) : S.doc.links.map((l) => [`link:${l.id}`, l]);
  for (const [id, e] of edges) {
    const ends = endpoints(e, e.from, e.to);
    if (ends) items.push({ group: "edges", data: { id, source: e.from, target: e.to, se: ends.src, te: ends.dst, sy: ends.sy } });
  }
  return items;
}

function renderGraph() {
  hideTip();
  if (!S.doc) { if (cy) cy.elements().remove(); $("cards-inner").replaceChildren(); return; }
  if (!cy) {
    // Box selection needs a modifier (Shift) because dragging the empty canvas pans.
    cy = cytoscape({ container: $("cy"), style: STYLE(), wheelSensitivity: 0.3, boxSelectionEnabled: true, selectionType: "single", minZoom: 0.2, maxZoom: 2.5 });
    cy.on("tap", "node", (e) => tapNode(e.target, e.position));
    cy.on("dbltap", (e) => { if (e.target === cy) quickAdd(e); });
    cy.on("cxttap", (e) => {
      const o = e.originalEvent;
      if (e.target === cy) canvasMenu(o.clientX, o.clientY, e.position);
      else if (e.target.isNode()) nodeMenu(o.clientX, o.clientY, e.target.id());
      else edgeMenu(o.clientX, o.clientY, e.target.id());
    });
    cy.on("select unselect", () => markMulti());
    cy.on("tap", "edge", (e) => select(curAgent() ? "edge" : "link", e.target.id().split(":")[1]));
    // A tap on empty canvas keeps the last opened document; the 검토 tab is one click away.
    cy.on("dbltap", "node", (e) => { if (!curAgent() && agentOf(e.target.id())) enter(e.target.id()); });
    cy.on("dragfree", "node", (e) => {
      snapshot();
      if (!S.alt && !e.originalEvent?.altKey) {  // Alt keeps the exact drop position
        const moved = e.target.selected() ? cy.$("node:selected") : e.target;
        moved.forEach((n) => n.position({ x: snap(n.position("x")), y: snap(n.position("y")) }));
      }
      resolveOverlaps(); savePositions(); markDirty(); markBack();
    });
    cy.on("position", "node", (e) => { placeCard(e.target); routeSoon(); });
    cy.on("viewport", () => { syncView(); hideTip(); });
    cy.on("mousemove", "node", (e) => hoverNode(e.target, e.position));
    cy.on("mouseout", "node", () => clearHover());
    cy.on("mouseover", "edge", (e) => hoverEdge(e.target, true));
    cy.on("mouseout", "edge", (e) => hoverEdge(e.target, false));
  }
  const pos = layout(S.level);
  cy.elements().remove();
  cy.add(elements());
  cy.edges().forEach((e) => e.style({ "source-endpoint": e.data("se"), "target-endpoint": e.data("te") }));
  cardEls = new Map([...specs.values()].map((sp) => [sp.id, nodeCardEl(sp)]));
  $("cards-inner").replaceChildren(...cardEls.values());
  // Positions saved before the card layout (version 2) were made for small top-to-bottom boxes: lay those out again.
  const stale = Object.keys(pos).some((k) => k !== "_v") && pos._v !== 2;
  const missing = [];
  cy.nodes().forEach((n) => { if (!stale && pos[n.id()]) n.position(pos[n.id()]); else missing.push(n); placeCard(n); });
  // A whole new level (or one the AI mostly rewrote) is laid out; a few new cards go next to what they link to.
  if (stale || missing.length * 2 > cy.nodes().length) { if (stale) snapshot(); arrange(false); }
  else {
    if (missing.length) placeNear(missing);
    if (resolveOverlaps() || missing.length) { savePositions(); markDirty(); }
    if (S.fitNext) openView();
  }
  S.fitNext = false;
  markBack();
  markSelection();
  markMulti();
  syncView();
  renderCanvasEmpty();
}

function placeCard(n) {
  const c = cardEls.get(n.id()), sp = specs.get(n.id());
  if (!c || !sp) return;
  const p = n.position();
  c.style.left = `${p.x - sp.w / 2}px`;
  c.style.top = `${p.y - sp.h / 2}px`;
}
function syncView() {
  if (!cy) return;
  const z = cy.zoom(), p = cy.pan();
  $("cards-inner").style.transform = `translate(${p.x}px, ${p.y}px) scale(${z})`;
  const stage = $("stage");
  stage.style.backgroundSize = `${20 * z}px ${20 * z}px`;
  stage.style.backgroundPosition = `${p.x}px ${p.y}px`;
}
// Every link is drawn as right-angle segments from its 다음 port to the target's input port. Cytoscape's own
// "taxi" routing turns at card centres, which bends the last part diagonally, so the corners are computed here
// and handed over as segment points relative to the two ports (edge-distances: endpoints).
//   forward link: right, then up or down, then right. Links leaving one card turn at staggered distances
//     (going down, the upper row turns later), so their vertical parts never lie on top of each other.
//   link that skips a column: runs along the nearest height that is free of cards between (its row's height
//     when the layout left a lane there), and turns just before its target.
//   link back to the left (a loop): dashed, around the cards above or below, whichever is nearer.
function markBack() {
  const box = (n) => { const sp = specs.get(n.id()), p = n.position(); return { x1: p.x - sp.w / 2, x2: p.x + sp.w / 2, y1: p.y - sp.h / 2, y2: p.y + sp.h / 2, sp }; };
  const boxes = new Map(cy.nodes().map((n) => [n.id(), box(n)]));
  const info = new Map();
  cy.edges().forEach((e) => {
    const s = boxes.get(e.source().id()), t = boxes.get(e.target().id());
    if (!s || !t) return;
    const S = { x: s.x2, y: s.y1 + e.data("sy") }, T = { x: t.x1, y: t.y1 + t.sp.bt + t.sp.headH / 2 };
    const back = T.x <= S.x + 16, long = !back && T.x - S.x > CARD_W + 1.5 * RANK_SEP;
    e.toggleClass("back", back).toggleClass("long", long);
    info.set(e.id(), { e, S, T, back, long, src: e.source().id() });
  });
  const turns = new Map();
  const bySource = new Map();
  for (const v of info.values()) if (!v.back && !v.long) (bySource.get(v.src) || bySource.set(v.src, []).get(v.src)).push(v);
  for (const list of bySource.values()) {
    const down = list.filter((v) => v.T.y > v.S.y + 1).sort((p, q) => p.S.y - q.S.y);
    const up = list.filter((v) => v.T.y < v.S.y - 1).sort((p, q) => q.S.y - p.S.y);
    for (const group of [down, up]) group.forEach((v, i) => turns.set(v.e.id(), 18 + 12 * (group.length - 1 - i)));
  }
  for (const v of info.values()) {
    const { e, S, T } = v;
    let pts;
    if (v.back) {
      const lo = Math.min(S.x, T.x) - 30, hi = Math.max(S.x, T.x) + 30;
      const span = [...boxes.values()].filter((b) => b.x2 > lo && b.x1 < hi);
      const above = Math.min(...span.map((b) => b.y1)) - 26, below = Math.max(...span.map((b) => b.y2)) + 26;
      const mid = (S.y + T.y) / 2, y = mid - above < below - mid ? above : below;
      pts = [[S.x + 18, S.y], [S.x + 18, y], [T.x - 18, y], [T.x - 18, T.y]];
    } else if (Math.abs(T.y - S.y) < 1) pts = [];
    else if (v.long) {
      const y = freeRow(S, T, boxes, e);
      pts = y === S.y ? [[T.x - 26, S.y], [T.x - 26, T.y]] : y === T.y ? [[S.x + 18, S.y], [S.x + 18, T.y]]
        : [[S.x + 18, S.y], [S.x + 18, y], [T.x - 26, y], [T.x - 26, T.y]];
    } else {
      const x = Math.max(S.x + 8, Math.min(T.x - 10, S.x + (turns.get(e.id()) ?? 18)));
      pts = [[x, S.y], [x, T.y]];
    }
    const dx = T.x - S.x, dy = T.y - S.y, L2 = dx * dx + dy * dy || 1, L = Math.sqrt(L2);
    const weights = pts.map(([x, y]) => ((x - S.x) * dx + (y - S.y) * dy) / L2);
    const dists = pts.map(([x, y]) => (-(x - S.x) * dy + (y - S.y) * dx) / L);
    e.style(pts.length
      ? { "curve-style": "round-segments", "edge-distances": "endpoints", "segment-weights": weights, "segment-distances": dists, "segment-radii": 10 }
      : { "curve-style": "straight" });
  }
}
// Nearest height to the start port where a horizontal run from S to T crosses no card (the target's height is tried second).
function freeRow(S, T, boxes, e) {
  const others = [...boxes.entries()].filter(([id, b]) => id !== e.source().id() && id !== e.target().id() && b.x2 > S.x + 18 && b.x1 < T.x - 26).map(([, b]) => b);
  const free = (y) => others.every((b) => y < b.y1 - 6 || y > b.y2 + 6);
  if (free(S.y)) return S.y;
  if (free(T.y)) return T.y;
  for (let k = 1; k < 200; k++) for (const y of [S.y + k * 8, S.y - k * 8]) if (free(y)) return y;
  return S.y;
}
let routeFrame = 0;
const routeSoon = () => { if (!routeFrame) routeFrame = requestAnimationFrame(() => { routeFrame = 0; if (cy) markBack(); }); };
// Push cards down until none overlap (cards grow when rows or details are added). Returns whether anything moved.
function resolveOverlaps() {
  const nodes = cy.nodes().toArray();
  let moved = false;
  for (let pass = 0; pass < 60; pass++) {
    let any = false;
    nodes.sort((p, q) => p.position("y") - q.position("y"));
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i].boundingBox(), b = nodes[j].boundingBox(), gap = 18;
        if (a.x2 + gap <= b.x1 || b.x2 + gap <= a.x1 || a.y2 + gap <= b.y1 || b.y2 + gap <= a.y1) continue;
        nodes[j].position("y", nodes[j].position("y") + (a.y2 + gap - b.y1));
        any = moved = true;
      }
    }
    if (!any) break;
  }
  return moved;
}
function quickAdd(e) {
  const o = e.originalEvent, a = curAgent();
  openMenu(o.clientX, o.clientY, a
    ? [{ label: "단계", action: () => createAt("step", e.position) }]
    : [{ label: "에이전트", action: () => createAt("agent", e.position) }], "여기에 추가");
}
function markMulti() {
  const ids = new Set(cy.$("node:selected").map((n) => n.id()));
  cardEls.forEach((c, id) => c.classList.toggle("msel", ids.has(id) && ids.size > 1));
}
function markSelection() {
  cardEls.forEach((c) => c.classList.remove("sel"));
  cy.edges().removeClass("sel");
  if (!S.sel) return;
  const id = cyId(S.sel.kind, S.sel.id), n = cy.$id(id);
  cardEls.get(id)?.classList.add("sel");
  n.addClass("sel");
  // Keep Cytoscape's selection (used by arrows, delete, Shift-select) on what the panel shows.
  // Checked after Cytoscape has handled the tap, so a Shift+tap that adds to the selection is left alone.
  setTimeout(() => { const m = cy.$id(id); if (m.length && !m.selected() && S.sel && cyId(S.sel.kind, S.sel.id) === id) { cy.elements().unselect(); m.select(); } });
}

const RANK_SEP = 96;
// Lay the level out with layered() (layout.js): columns left to right, each card lined up with the 다음 row it comes from.
function arrange(save = true) {
  if (save) snapshot();
  const nodes = cy.nodes().map((n) => {
    const sp = specs.get(n.id());
    return { id: n.id(), w: sp.w, h: sp.h, inY: sp.bt + sp.headH / 2, role: n.id() === "start" ? "start" : sp.kind === "end" ? "end" : "" };
  });
  const edges = cy.edges().map((e) => ({ source: e.data("source"), target: e.data("target"), outY: e.data("sy") }));
  const pos = layered(nodes, edges, { rankSep: RANK_SEP });
  cy.nodes().forEach((n) => { if (pos[n.id()]) n.position(pos[n.id()]); });
  resolveOverlaps(); savePositions(); markDirty(); markBack(); openView();
}
function savePositions() {
  const pos = layout(S.level);
  for (const k of Object.keys(pos)) delete pos[k];
  pos._v = 2;
  cy.nodes().forEach((n) => { const p = n.position(); pos[n.id()] = { x: Math.round(p.x), y: Math.round(p.y) }; });
}
function cyId(kind, id) {
  if (kind === "edge") return `edge:${id}`;
  if (kind === "link") return `link:${id}`;
  return id;
}
function zoomBy(f) {
  const r = $("cy").getBoundingClientRect();
  cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: r.width / 2, y: r.height / 2 } });
}
const fitView = () => { if (cy) { cy.resize(); cy.fit(undefined, 60); } };
// First view of a level: everything if it is still readable, otherwise readable size starting from the left (the start).
function openView() {
  cy.resize();
  cy.fit(undefined, 60);
  if (cy.zoom() >= 0.7) return;
  const box = cy.nodes().boundingBox();
  cy.zoom(0.7);
  cy.pan({ x: 60 - box.x1 * 0.7, y: cy.height() / 2 - ((box.y1 + box.y2) / 2) * 0.7 });
}

// ---------- card interaction ----------
function hitAt(node, position) {
  const sp = specs.get(node.id());
  if (!sp || !position) return null;  // keyboard or programmatic taps carry no position
  const y = position.y - (node.position("y") - sp.h / 2);
  return sp.parts.find((p) => y >= p.y && y < p.y + p.h) || null;
}
function tapNode(node, position) {
  const id = node.id(), sp = specs.get(id), part = hitAt(node, position), a = curAgent();
  if (part?.type === "row") {
    const r = sp.rows[part.i];
    if (r.edge) return select(a ? "edge" : "link", r.edge.id);
  }
  if (id === "start" || id === "end") return;
  const focus = a ? { input: "inputs", output: "outputs", process: "process", tools: "tools", sub: "summary" }[part?.type]
    : { sub: "role" }[part?.type];
  select(a ? "step" : "agent", id, focus);
}
function hoverNode(node, position) {
  const part = hitAt(node, position), sp = specs.get(node.id()), card = cardEls.get(node.id());
  clearHover(node.id());
  card?.classList.add("hover");
  if (part?.type === "row" && sp.rows[part.i].edge) {
    const r = sp.rows[part.i];
    cy.$id(cyId(curAgent() ? "edge" : "link", r.edge.id)).addClass("hl");
    card.querySelector(`.part.row[style*="top:${part.y - sp.bt}px"]`)?.classList.add("hover");
  }
  if (sp?.tip && !S.portDrag) showTip(node, sp.tip);
}
function clearHover(keep) {
  cardEls.forEach((c, id) => { if (id !== keep) c.classList.remove("hover"); c.querySelectorAll(".part.row.hover").forEach((r) => r.classList.remove("hover")); });
  if (cy) cy.edges(".hl").removeClass("hl");
  if (!keep) hideTip();
}
function hoverEdge(edge, on) {
  edge.toggleClass("hl", on);
  for (const n of [edge.source(), edge.target()]) cardEls.get(n.id())?.classList.toggle("hl", on);
}
function showTip(node, st) {
  const tip = $("tip"), r = node.renderedBoundingBox(), stage = $("stage").getBoundingClientRect();
  tip.replaceChildren(el("div", {}, el("strong", {}, "input "), (st.inputs || []).join(", ") || "없음"),
    el("div", {}, el("strong", {}, "output "), (st.outputs || []).join(", ") || "없음"));
  tip.hidden = false;
  tip.style.left = `${Math.min(r.x2 + 10, stage.width - 260)}px`;
  tip.style.top = `${Math.max(8, r.y1)}px`;
}
function hideTip() { const t = $("tip"); if (t) t.hidden = true; }

// Drag from a port to a card: a new link, or a new target for the link that row already has.
function startPortDrag(e, nodeId, rowIndex) {
  if (e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  hideTip();
  const stage = $("stage").getBoundingClientRect(), from = e.target.getBoundingClientRect();
  const x0 = from.left + from.width / 2 - stage.left, y0 = from.top + from.height / 2 - stage.top;
  const svg = $("drag-line"), path = svg.querySelector("path");
  svg.hidden = false;
  S.portDrag = { nodeId, rowIndex, target: null, moved: 0, x: e.clientX, y: e.clientY, empty: null };
  const toModel = (ev) => ({ x: (ev.clientX - stage.left - cy.pan().x) / cy.zoom(), y: (ev.clientY - stage.top - cy.pan().y) / cy.zoom() });
  const move = (ev) => {
    const x1 = ev.clientX - stage.left, y1 = ev.clientY - stage.top, dx = Math.max(40, Math.abs(x1 - x0) / 2);
    path.setAttribute("d", `M${x0},${y0} C${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`);
    const m = toModel(ev);
    const hit = cy.nodes().filter((n) => { const b = n.boundingBox(); return m.x >= b.x1 && m.x <= b.x2 && m.y >= b.y1 && m.y <= b.y2; })[0];
    const ok = hit && canDrop(nodeId, hit.id());
    cardEls.forEach((c) => c.classList.remove("drop", "nodrop"));
    if (hit && hit.id() !== nodeId) cardEls.get(hit.id())?.classList.add(ok ? "drop" : "nodrop");
    S.portDrag.target = ok ? hit.id() : null;
    S.portDrag.empty = hit ? null : m;
    S.portDrag.moved = Math.max(S.portDrag.moved, Math.hypot(ev.clientX - S.portDrag.x, ev.clientY - S.portDrag.y));
  };
  const end = (ev) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", cancel);
    window.removeEventListener("keydown", esc);
    svg.hidden = true;
    path.setAttribute("d", "");
    cardEls.forEach((c) => c.classList.remove("drop", "nodrop"));
    const drag = S.portDrag;
    S.portDrag = null;
    if (!ev || !drag) return;
    if (drag.target) return dropLink(drag.nodeId, drag.rowIndex, drag.target);
    if (drag.moved < 6) return addNext(drag.nodeId, drag.rowIndex);  // a click on a port adds the next node
    if (drag.empty) {  // dropped on empty canvas: make a node there and connect to it
      snapshot();
      const [kind, id] = createAt(curAgent() ? "step" : "agent", { x: drag.empty.x + CARD_W / 2, y: drag.empty.y }, { noSnapshot: true, quiet: true });
      dropLink(drag.nodeId, drag.rowIndex, id, { noSnapshot: true });
      select(kind, id, "name");
      toast("새로 만들고 연결했습니다");
    }
  };
  const esc = (ev) => { if (ev.key === "Escape") end(null); };
  const cancel = () => end(null);
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", cancel);
  window.addEventListener("keydown", esc);
  move(e);
}
function canDrop(src, dst) {
  return src !== dst && dst !== "start" && src !== "end";
}
function dropLink(src, rowIndex, dst, opts = {}) {
  const a = curAgent(), sp = specs.get(src), row = rowIndex >= 0 ? sp.rows[rowIndex] : null;
  if (!opts.noSnapshot) snapshot();
  if (row?.edge) {
    row.edge.to = dst;
    return after(a ? "edge" : "link", row.edge.id);
  }
  // A second way out of the same card is a branch: every link out of it becomes conditional and needs its condition.
  const list = a ? a.edges : S.doc.links, siblings = list.filter((x) => x.from === src);
  const e = { id: nextId(list, "L"), from: src, to: dst, kind: siblings.length ? "cond" : "always", name: "", passes: [] };
  if (siblings.length && siblings.some((x) => x.kind !== "cond")) {
    siblings.forEach((x) => { x.kind = "cond"; });
    toast("갈래가 둘이 되어 모두 조건 연결로 바꿨습니다. 조건을 채우세요.", false);
  }
  list.push(e);
  after(a ? "edge" : "link", e.id, e.kind === "cond" ? "name" : null);
}
function after(kind, id, focus = null) {
  markDirty();
  renderGraph();
  select(kind, id, focus);
  const n = cy.$id(cyId(kind, id));
  if (n.length && n.isNode()) {
    const p = n.position(), e = cy.extent();
    if (p.x < e.x1 || p.x > e.x2 || p.y < e.y1 || p.y > e.y2) fitView();  // keep the rest in view too
  }
}

function enter(aid) { S.level = aid; S.sel = null; S.fitNext = true; renderAll(); }
function back() { S.level = "agents"; S.sel = null; S.fitNext = true; renderAll(); }

function renderCanvasEmpty() {
  const box = $("canvas-empty"), a = curAgent();
  const empty = S.doc && (a ? !a.steps.length : !S.doc.agents.length);
  box.hidden = !empty;
  if (!empty) return;
  box.replaceChildren(
    el("h2", {}, a ? `${a.id} ${a.name || ""}에 단계가 없습니다` : "아직 에이전트가 없습니다"),
    el("p", {}, a ? "이 에이전트가 맡은 역할을 이루는 단계를 추가하세요. 빈 곳을 두 번 누르면 그 자리에 만듭니다." : "직접 에이전트를 추가하거나, 검토 탭에서 AI와 인터뷰로 시작하세요. 빈 곳을 두 번 누르면 그 자리에 만듭니다."),
    el("div", { class: "row" },
      el("button", { type: "button", class: "primary", on: { click: a ? addStep : addAgent } }, a ? "단계 추가" : "에이전트 추가"),
      a ? null : el("button", { type: "button", on: { click: () => { setTab("chat"); $("chat-input").focus(); } } }, "AI와 인터뷰")));
}
function toggleDetail() {
  S.detail = !S.detail;
  try { localStorage.setItem("cagent-detail", S.detail ? "1" : "0"); } catch (_) { /* storage off */ }
  renderTop();
  renderGraph();
}

// ---------- toolbar / crumb ----------
const I = {
  undo: "M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3", redo: "m15 14 5-5-5-5M20 9H10a6 6 0 0 0 0 12h3",
  plus: "M12 5v14M5 12h14", minus: "M5 12h14", fit: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  detail: "M4 6h16M4 12h16M4 18h10", compact: "M4 8h16M4 16h16",
};
function ibtn(path, label, fn, extra = {}) {
  const svg = icon(path);
  svg.setAttribute("class", "i");
  return el("button", { type: "button", class: "icon", "aria-label": label, title: label, on: { click: fn }, ...extra }, svg);
}
function renderTop() {
  const has = !!S.doc;
  $("empty").hidden = has;
  $("project-name").disabled = !has;
  $("project-name").value = has ? S.doc.name || "" : "";
  for (const id of ["crumb", "tools", "actions", "zoom", "history"]) $(id).replaceChildren();
  for (const id of ["tools", "zoom", "history"]) $(id).hidden = !has;
  if (!has) return;
  const a = curAgent();
  const crumb = $("crumb");
  crumb.append(a ? el("button", { type: "button", on: { click: back } }, S.doc.name || "프로젝트")
    : el("span", { text: `${S.doc.name || "프로젝트"} · 에이전트 지도` }));
  if (a) crumb.append(el("span", { "aria-hidden": "true" }, "›"), el("span", { text: `${a.id} ${a.name || ""}` }));
  const tools = $("tools");
  const btn = (label, fn, extra = {}) => tools.append(el("button", { type: "button", on: { click: fn }, ...extra }, label));
  const sep = () => tools.append(el("span", { class: "sep", "aria-hidden": "true" }));
  if (!a) btn("+ 에이전트", addAgent);
  else btn("+ 단계", addStep);
  btn("자동 정렬", () => arrange(true), { title: "배치를 새로 계산합니다" });
  sep();
  btn("프로젝트 문서", () => select("project", ""));
  btn("도구 목록", () => select("project", "", "tools"));
  btn("데이터 사전", () => select("glossary", ""));
  $("zoom").append(ibtn(I.plus, "확대 (+)", () => zoomBy(1.2)), ibtn(I.minus, "축소 (-)", () => zoomBy(1 / 1.2)), ibtn(I.fit, "화면 맞춤 (0)", fitView),
    ibtn(S.detail ? I.compact : I.detail, S.detail ? "간단히 보기" : "자세히 보기", toggleDetail, { id: "btn-detail" }));
  const undoBtn = el("button", { type: "button", id: "btn-undo", title: `되돌리기 (${mod}Z)`, on: { click: undo } }, icon(I.undo), " 되돌리기");
  undoBtn.firstChild.setAttribute("class", "i");
  $("history").append(undoBtn, ibtn(I.redo, `다시 실행 (${mod}Shift+Z)`, redo, { id: "btn-redo" }));
  $("actions").append(el("button", { type: "button", id: "btn-issues", on: { click: openIssues } }, "검사"),
    el("button", { type: "button", class: "primary", on: { click: openExport } }, "내보내기"));
  renderHistoryButtons();
  renderIssueButton();
}
$("project-name").addEventListener("input", (e) => { snapshot("project-name"); S.doc.name = e.target.value; markDirty(); renderCrumbOnly(); });
function renderCrumbOnly() {
  const first = $("crumb").firstElementChild;
  if (first) first.textContent = curAgent() ? S.doc.name || "프로젝트" : `${S.doc.name || "프로젝트"} · 에이전트 지도`;
}

// ---------- create & place ----------
const GRID = 20;
const snap = (v) => Math.round(v / GRID) * GRID;
function newAgent() {
  const id = nextId(S.doc.agents, "A");
  const color = S.schema.colors[S.doc.agents.length % S.schema.colors.length];
  S.doc.agents.push({ id, name: "새 에이전트", color, role: "", intent: "", not_doing: "",
    fixed: "", discretion: "", paths: "", notes: "", steps: [], edges: [] });
  return id;
}
function newStep(a) {
  const id = nextId(a.steps, "N");
  a.steps.push({ id, name: "새 단계", type: "처리", summary: "", intent: "", inputs: [], process: [], outputs: [], criteria: [], prompt: "",
    tools: [], done: [], example: "", on_fail: "", fixed: "", discretion: "", cautions: "" });
  return id;
}
// Nearest free, grid-aligned spot to a wished position (model coordinates) for a card of the given size.
// Moving up or down is preferred over sideways, so a card stays in its column.
function freeSpot(want, w = CARD_W, h = 120, skip = new Set()) {
  const boxes = cy.nodes().filter((n) => !skip.has(n.id())).map((n) => n.boundingBox());
  const free = (x, y) => boxes.every((b) => x + w / 2 + 16 <= b.x1 || x - w / 2 - 16 >= b.x2 || y + h / 2 + 16 <= b.y1 || y - h / 2 - 16 >= b.y2);
  const x0 = snap(want.x), y0 = snap(want.y);
  let best = null, bestD = Infinity;
  for (let i = -6; i <= 6; i++) for (let j = -40; j <= 40; j++) {
    const x = x0 + i * GRID * 2, y = y0 + j * GRID, d = (3 * i * GRID * 2) ** 2 + (j * GRID) ** 2;
    if (d < bestD && free(x, y)) { best = { x, y }; bestD = d; }
  }
  return best || { x: x0, y: y0 };
}
// Cards that have no saved position yet: right of the card linking to them (lined up with that 다음 row),
// else left of the card they link to, else below everything.
function placeNear(list) {
  const left = new Set(list.map((n) => n.id()));
  const inOf = (n) => { const sp = specs.get(n.id()); return sp.bt + sp.headH / 2 - sp.h / 2; };
  for (let round = 0; round < list.length && left.size; round++) {
    for (const n of list) {
      if (!left.has(n.id())) continue;
      const sp = specs.get(n.id());
      const from = n.incomers("edge").filter((e) => !left.has(e.source().id()))[0];
      const to = n.outgoers("edge").filter((e) => !left.has(e.target().id()))[0];
      let want = null;
      if (from) { const s = from.source(); want = { x: s.position("x") + s.data("w") / 2 + RANK_SEP + sp.w / 2, y: s.position("y") - s.data("h") / 2 + from.data("sy") - inOf(n) }; }
      else if (to) { const t = to.target(); want = { x: t.position("x") - t.data("w") / 2 - RANK_SEP - sp.w / 2, y: t.position("y") + inOf(t) - (to.data("sy") - sp.h / 2) }; }
      else if (round < list.length - 1 && list.some((m) => m !== n && left.has(m.id()) && m.edgesWith(n).length)) continue;  // wait for a linked neighbour
      else { const b = cy.nodes().filter((m) => !left.has(m.id())).boundingBox(); want = { x: (b.x1 || 0) + sp.w / 2, y: (b.y2 || 0) + 60 + sp.h / 2 }; }
      const exact = freeSpot(want, sp.w, sp.h, left);
      left.delete(n.id());
      // keep the exact row alignment when that spot is free; otherwise the nearest free grid spot
      n.position(Math.abs(exact.y - snap(want.y)) < 1 && Math.abs(exact.x - snap(want.x)) < 1 ? want : exact);
      placeCard(n);
    }
  }
}
const viewCenter = () => { const e = cy.extent(); return { x: (e.x1 + e.x2) / 2, y: (e.y1 + e.y2) / 2 }; };
// Create a node of the current level at a position; returns [kind, id] after selecting it with its name field focused.
function createAt(what, pos, opts = {}) {
  if (!opts.noSnapshot) snapshot();
  const a = curAgent();
  let kind, id, nodeId;
  if (what === "agent") { id = newAgent(); kind = "agent"; nodeId = id; }
  else { id = newStep(a); kind = "step"; nodeId = id; }
  layout(S.level)[nodeId] = freeSpot(pos, CARD_W, 130);
  markDirty();
  renderGraph();
  select(kind, id, "name");
  ensureVisible(nodeId);
  if (!opts.quiet) toast(`${{ agent: "에이전트", step: "단계" }[what]}를 추가했습니다`);
  return [kind, id];
}
function ensureVisible(nodeId) {
  const n = cy.$id(nodeId);
  if (!n.length) return;
  const b = n.boundingBox(), e = cy.extent();
  if (b.x1 < e.x1 || b.x2 > e.x2 || b.y1 < e.y1 || b.y2 > e.y2) cy.animate({ center: { eles: n }, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 200 });
}
const addAgent = () => createAt("agent", viewCenter());
const addStep = () => createAt("step", viewCenter());
// A new node to the right of a card, already connected from the given port.
function addNext(srcId, rowIndex) {
  const n = cy.$id(srcId), sp = specs.get(srcId);
  if (!n.length || !sp || !canDrop(srcId, "x")) return;
  const part = rowIndex >= 0 ? partOf(sp, "row", rowIndex) : partOf(sp, "head");
  const y = n.position("y") - sp.h / 2 + part.y + part.h / 2;
  snapshot();
  const [kind, id] = createAt(curAgent() ? "step" : "agent", { x: n.position("x") + sp.w / 2 + 90 + CARD_W / 2, y }, { noSnapshot: true, quiet: true });
  dropLink(srcId, rowIndex, id, { noSnapshot: true });
  select(kind, id, "name");
  toast("다음 단계를 이어서 만들었습니다");
}
// Split a link: A → new → B.
function insertBetween(kind, id) {
  const a = curAgent();
  const e = kind === "edge" ? a.edges.find((x) => x.id === id) : S.doc.links.find((x) => x.id === id);
  if (!e || e.from === e.to) return;
  const s = cy.$id(e.from), t = cy.$id(e.to);
  snapshot();
  const mid = { x: (s.position("x") + t.position("x")) / 2, y: (s.position("y") + t.position("y")) / 2 };
  const target = e.to;
  const [nk, nid] = createAt(a ? "step" : "agent", mid, { noSnapshot: true, quiet: true });
  e.to = nid;
  const list = a ? a.edges : S.doc.links;
  list.push({ id: nextId(list, "L"), from: nid, to: target, kind: "always", name: "", passes: [...(e.passes || [])] });
  markDirty();
  renderGraph();
  select(nk, nid, "name");
  toast(`${a ? "단계" : "에이전트"}를 연결 중간에 넣었습니다`);
}
function duplicateSelected() {
  if (!S.sel || !["agent", "step"].includes(S.sel.kind)) return;
  const a = curAgent(), src = selected();
  if (!src) return;
  snapshot();
  const copy = JSON.parse(JSON.stringify(src));
  copy.name = `${src.name || ""} 사본`.trim();
  let nodeId;
  if (S.sel.kind === "agent") {
    copy.id = nextId(S.doc.agents, "A");
    copy.color = S.schema.colors[S.doc.agents.length % S.schema.colors.length];
    S.doc.agents.push(copy);
    if (S.doc.layout?.[src.id]) layout(copy.id), Object.assign(S.doc.layout[copy.id], JSON.parse(JSON.stringify(S.doc.layout[src.id])));
    nodeId = copy.id;
  } else {
    copy.id = nextId(a.steps, "N");
    a.steps.push(copy);
    nodeId = copy.id;
  }
  const n = cy.$id(src.id), sp = specs.get(src.id);
  layout(S.level)[nodeId] = freeSpot({ x: n.position("x") + 40, y: n.position("y") + (sp?.h || 120) + 40 }, CARD_W, sp?.h || 120);
  markDirty();
  renderGraph();
  select(S.sel.kind, copy.id, "name");
  toast(`${copy.id}로 복제했습니다`);
}

// ---------- selection & delete ----------
function select(kind, id, focus = null) {
  S.sel = { kind, id };
  S.preview = false;
  S.focusField = focus;
  if (cy) markSelection();
  renderDoc();
  setTab("doc");
}
function selected() {
  if (!S.sel || !S.doc) return null;
  const { kind, id } = S.sel, a = curAgent();
  if (kind === "project" || kind === "glossary") return S.doc;
  if (kind === "agent") return agentOf(id);
  if (kind === "link") return S.doc.links.find((x) => x.id === id);
  if (!a) return null;
  if (kind === "step") return a.steps.find((x) => x.id === id);
  if (kind === "edge") return a.edges.find((x) => x.id === id);
  return null;
}
// Remove nodes and links by canvas id (agent id, step id, edge:/link:<id>).
function removeIds(ids) {
  const a = curAgent();
  for (const cid of ids) {
    if (cid.startsWith("link:")) S.doc.links = S.doc.links.filter((x) => x.id !== cid.slice(5));
    else if (cid.startsWith("edge:")) a.edges = a.edges.filter((x) => x.id !== cid.slice(5));
    else if (cid === "start" || cid === "end") continue;
    else if (!a) {
      S.doc.agents = S.doc.agents.filter((x) => x.id !== cid);
      S.doc.links = S.doc.links.filter((l) => l.from !== cid && l.to !== cid);
      if (S.doc.layout) delete S.doc.layout[cid];
    } else {
      a.steps = a.steps.filter((x) => x.id !== cid);
      a.edges = a.edges.filter((e) => e.from !== cid && e.to !== cid);
    }
    delete layout(S.level)[cid];
  }
  // Nothing may keep pointing at what is gone (a later item could reuse the number).
  const edgeIds = new Set(S.doc.links.map((l) => l.id));
  S.doc.links.forEach((l) => { if (l.loop_exit && !edgeIds.has(l.loop_exit)) l.loop_exit = ""; });
  S.doc.agents.forEach((ag) => { const ids = new Set(ag.edges.map((e) => e.id)); ag.edges.forEach((e) => { if (e.loop_exit && !ids.has(e.loop_exit)) e.loop_exit = ""; }); });
  (S.doc.tools || []).forEach((t) => { if (t.ref && !agentOf(t.ref)) t.ref = ""; });
}
function removeSelected() {
  snapshot();
  const many = multiIds();
  const ids = many.length > 1 ? many : [cyId(S.sel.kind, S.sel.id)];
  removeIds(ids);
  S.sel = null;
  markDirty();
  renderAll();
  toast(ids.length > 1 ? `${ids.length}개를 지웠습니다` : "지웠습니다");
}
const multiIds = () => (cy ? cy.$(":selected").map((x) => x.id()).filter((id) => id !== "start" && id !== "end") : []);
function askRemove() {
  const many = multiIds();
  if (many.length > 1) {
    modal("삭제", [el("p", {}, `선택한 ${many.length}개와 거기에 이어진 연결을 지웁니다.`)], [["삭제", () => { closeModal(); removeSelected(); }, "danger"], ["취소", closeModal]]);
    return;
  }
  if (!S.sel || ["project", "glossary"].includes(S.sel.kind)) return;
  const label = { agent: "에이전트와 거기에 이어진 연결", step: "단계와 거기에 이어진 연결", edge: "연결", link: "에이전트 연결" }[S.sel.kind];
  modal("삭제", [el("p", {}, `${label}을 지웁니다.`)], [["삭제", () => { closeModal(); removeSelected(); }, "danger"], ["취소", closeModal]]);
}
function nudge(dx, dy) {
  const ids = multiIds().filter((id) => !id.startsWith("edge:") && !id.startsWith("link:"));
  const nodes = ids.length ? ids : (S.sel && !["edge", "link", "project", "glossary"].includes(S.sel.kind) ? [cyId(S.sel.kind, S.sel.id)] : []);
  if (!nodes.length) return false;
  snapshot("nudge");
  for (const id of nodes) { const n = cy.$id(id); n.position({ x: n.position("x") + dx, y: n.position("y") + dy }); }
  savePositions();
  markDirty();
  markBack();
  return true;
}

// ---------- menus ----------
// One floating menu for quick add, right-click on canvas, cards, and links. Keyboard: arrows, Enter, Esc.
function openMenu(x, y, items, title) {
  closeMenu();
  const menu = el("div", { id: "menu", role: "menu", "aria-label": title || "메뉴" },
    title ? el("div", { class: "menu-title" }, title) : null,
    ...items.filter(Boolean).map((it) => it === "-" ? el("div", { class: "menu-sep", role: "separator" })
      : el("button", { type: "button", role: "menuitem", class: it.danger ? "danger" : null, disabled: it.disabled ? true : null,
        on: { click: () => { closeMenu(); it.action(); } } }, el("span", {}, it.label), it.key ? el("kbd", {}, it.key) : null)));
  document.body.append(menu);
  const r = menu.getBoundingClientRect();
  menu.style.left = `${Math.min(x, window.innerWidth - r.width - 8)}px`;
  menu.style.top = `${Math.min(y, window.innerHeight - r.height - 8)}px`;
  const buttons = () => [...menu.querySelectorAll("button:not(:disabled)")];
  buttons()[0]?.focus();
  menu.addEventListener("keydown", (e) => {
    const list = buttons(), i = list.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); list[(i + 1) % list.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); list[(i - 1 + list.length) % list.length].focus(); }
    if (e.key === "Escape") { e.preventDefault(); closeMenu(); $("cy").focus(); }
    if (e.key === "Tab") closeMenu();
  });
  setTimeout(() => document.addEventListener("pointerdown", outside, true));
}
function outside(e) { if (!$("menu")?.contains(e.target)) closeMenu(); }
function closeMenu() { $("menu")?.remove(); document.removeEventListener("pointerdown", outside, true); }
function canvasMenu(x, y, pos) {
  const a = curAgent();
  openMenu(x, y, [
    !a ? { label: "여기에 에이전트 추가", action: () => createAt("agent", pos) } : null,
    a ? { label: "여기에 단계 추가", action: () => createAt("step", pos) } : null,
    "-",
    { label: "자동 정렬", action: () => arrange(true) },
    { label: "화면 맞춤", key: "0", action: fitView },
  ], "여기에 추가");
}
function nodeMenu(x, y, id) {
  const a = curAgent();
  if (id === "end") return;
  if (id === "start") return openMenu(x, y, [{ label: a ? "다음 단계 추가" : "다음 에이전트 추가", action: () => addNext("start", -1) }], "시작");
  const kind = a ? "step" : "agent";
  select(kind, id);
  openMenu(x, y, [
    { label: "이름 바꾸기", key: "Enter", action: () => select(kind, id, "name") },
    !a ? { label: "안으로 들어가기", action: () => enter(id) } : null,
    { label: a ? "다음 단계 추가" : "다음 에이전트 추가", action: () => addNext(id, -1) },
    { label: "연결할 곳 고르기…", action: () => pickTarget(id) },
    { label: "복제", key: `${mod}D`, action: duplicateSelected },
    "-",
    { label: "삭제", key: "⌫", danger: true, action: askRemove },
  ], `${id} ${specs.get(id)?.title || ""}`);
}
function edgeMenu(x, y, cid) {
  const a = curAgent(), kind = a ? "edge" : "link", id = cid.split(":")[1];
  const e = a ? a.edges.find((v) => v.id === id) : S.doc.links.find((v) => v.id === id);
  if (!e) return;
  select(kind, id);
  openMenu(x, y, [
    { label: e.kind === "cond" ? "항상 연결로 바꾸기" : "조건 연결로 바꾸기", action: () => { snapshot(); e.kind = e.kind === "cond" ? "always" : "cond"; markDirty(); renderGraph(); select(kind, id, e.kind === "cond" ? "name" : null); } },
    { label: a ? "중간에 단계 넣기" : "중간에 에이전트 넣기", action: () => insertBetween(kind, id) },
    "-",
    { label: "삭제", key: "⌫", danger: true, action: askRemove },
  ], `${a ? `${a.id}-` : ""}${id}`);
}
// Keyboard way to link to an existing card (the mouse way is dragging a port).
function pickTarget(src) {
  const items = specs.size ? [...specs.values()].filter((sp) => canDrop(src, sp.id)) : [];
  modal("연결할 곳", [el("div", { class: "find-list", role: "listbox" }, ...items.map((sp) => el("button", { type: "button", role: "option",
    on: { click: () => { closeModal(); dropLink(src, -1, sp.id); toast("연결했습니다"); } } }, el("span", {}, `${sp.badge || ""} ${sp.title || ""}`.trim()))))],
  [["취소", closeModal]]);
  $("modal").querySelector(".find-list button")?.focus();
}
function menuForSelection() {
  if (!S.sel) return;
  const id = cyId(S.sel.kind, S.sel.id), n = cy.$id(id);
  if (!n.length) return;
  const r = n.renderedBoundingBox(), c = $("cy").getBoundingClientRect();
  const x = c.left + (n.isNode() ? r.x2 : (r.x1 + r.x2) / 2), y = c.top + (n.isNode() ? r.y1 : (r.y1 + r.y2) / 2);
  if (n.isEdge()) edgeMenu(x, y, id); else nodeMenu(x, y, id);
}

// ---------- find, toast, shortcuts ----------
function openFind() {
  const items = [];
  S.doc.agents.forEach((a) => {
    items.push({ label: `${a.id} ${a.name || ""}`, sub: "에이전트", go: () => goTo(a.id) });
    a.steps.forEach((s) => items.push({ label: `${a.id}-${s.id} ${s.name || ""}`, sub: `단계 · ${s.summary || ""}`, go: () => goTo(`${a.id}-${s.id}`) }));
    a.edges.forEach((e) => items.push({ label: `${a.id}-${e.id} ${e.name || nodeName(a, e.to)}`, sub: "연결", go: () => goTo(`${a.id}-${e.id}`) }));
  });
  S.doc.links.forEach((l) => items.push({ label: `${l.id} ${l.name || nodeName(null, l.to)}`, sub: "에이전트 연결", go: () => goTo(l.id) }));
  (S.doc.tools || []).forEach((t) => items.push({ label: `${t.id} ${toolLabel(t)}`, sub: `도구 · ${t.kind}`, go: () => select("project", "", "tools") }));
  const input = el("input", { placeholder: "번호나 이름으로 찾기 (예: A2, 질문 생성, T1)", "aria-label": "찾기", role: "combobox", "aria-expanded": "true", "aria-controls": "find-list" });
  const list = el("div", { id: "find-list", class: "find-list", role: "listbox" });
  let hits = [], at = 0;
  const draw = () => {
    const q = input.value.trim().toLowerCase();
    hits = items.filter((it) => !q || it.label.toLowerCase().includes(q) || it.sub.toLowerCase().includes(q)).slice(0, 30);
    at = Math.min(at, Math.max(0, hits.length - 1));
    list.replaceChildren(...hits.map((it, i) => el("button", { type: "button", role: "option", "aria-selected": i === at ? "true" : "false",
      on: { click: () => { closeModal(); it.go(); } } }, el("span", {}, it.label), el("span", { class: "muted" }, it.sub))),
      hits.length ? null : el("p", { class: "muted" }, "찾는 항목이 없습니다."));
  };
  input.addEventListener("input", () => { at = 0; draw(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); at = Math.min(at + 1, hits.length - 1); draw(); }
    if (e.key === "ArrowUp") { e.preventDefault(); at = Math.max(at - 1, 0); draw(); }
    if (e.key === "Enter" && !e.isComposing && hits[at]) { e.preventDefault(); closeModal(); hits[at].go(); }
  });
  modal("찾기", [input, list], [["닫기", closeModal]]);
  draw();
  input.focus();
}
let toastTimer = null;
// The undo button undoes the toast's own action only: after any later edit it disappears.
function toast(text, withUndo = true) {
  const box = $("toast"), mark = S.undo.length;
  box.replaceChildren(el("span", {}, text), withUndo ? el("button", { type: "button", on: { click: () => { if (S.undo.length === mark) undo(); box.hidden = true; } } }, "되돌리기") : null);
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, 5000);
}
function hideToast() { if ($("toast").matches(":hover, :focus-within")) toastTimer = setTimeout(hideToast, 1500); else $("toast").hidden = true; }
function openShortcuts() {
  const rows = [["빈 곳 두 번 누르기", "그 자리에 추가"], ["오른쪽 클릭", "카드·연결·빈 곳 메뉴"], ["점을 빈 곳에 놓기", "새 카드를 만들고 연결"],
    ["점 누르기", "오른쪽에 다음 단계"], ["Shift + 끌기 / Shift + 누르기", "여러 개 선택"], ["화살표 (Shift)", "선택한 카드 옮기기 1칸 (5칸)"],
    ["Alt + 놓기", "격자에 맞추지 않기"], ["Enter, F2", "이름 바꾸기"], [`${mod}D`, "복제"], ["Delete, ⌫", "삭제"], [`${mod}K`, "찾기"],
    [`${mod}Z / ${mod}Shift+Z`, "되돌리기 / 다시 실행"], ["+ − 0", "확대 · 축소 · 화면 맞춤"], ["Shift+F10, 메뉴 키", "선택한 것의 메뉴"], ["?", "이 안내"]];
  modal("단축키", [el("dl", { class: "keys" }, ...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]))], [["닫기", closeModal]]);
}

document.addEventListener("keydown", (e) => {
  const act = document.activeElement;
  const typing = /INPUT|TEXTAREA|SELECT/.test(act?.tagName) || act?.isContentEditable;
  const free = !typing && $("modal").hidden && !$("menu") && S.doc && cy;
  // Single keys act on the canvas only; on a focused button, Enter and Delete keep their usual meaning.
  const onCanvas = !act || act === document.body || $("cy").contains(act);
  const cmd = e.metaKey || e.ctrlKey;
  S.alt = e.altKey;
  if (e.key === "Escape" && !$("modal").hidden) { closeModal(); return; }
  if (cmd && (e.key === "k" || e.key === "K") && S.doc && $("modal").hidden) { e.preventDefault(); openFind(); return; }
  if (!free) return;
  if (cmd && (e.key === "z" || e.key === "Z" || e.key === "y")) { e.preventDefault(); if (e.shiftKey || e.key === "y") redo(); else undo(); return; }
  if (cmd && (e.key === "d" || e.key === "D")) { e.preventDefault(); duplicateSelected(); return; }
  if (cmd || !onCanvas) return;
  if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomBy(1.2); return; }
  if (e.key === "-") { e.preventDefault(); zoomBy(1 / 1.2); return; }
  if (e.key === "0") { e.preventDefault(); fitView(); return; }
  if (e.key === "?") { e.preventDefault(); openShortcuts(); return; }
  if ((e.key === "Enter" || e.key === "F2") && S.sel && !["project", "glossary", "edge", "link"].includes(S.sel.kind)) { e.preventDefault(); select(S.sel.kind, S.sel.id, "name"); return; }
  if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) { e.preventDefault(); menuForSelection(); return; }
  const step = e.shiftKey ? GRID * 5 : GRID;
  const dir = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
  if (dir && nudge(...dir)) { e.preventDefault(); return; }
  if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); askRemove(); }
});
document.addEventListener("keyup", (e) => { S.alt = e.altKey; });

// ---------- document form ----------
function fieldsFor(kind) {
  if (kind === "glossary") return S.schema.project.filter((f) => f[0] === "glossary");
  if (kind === "project") return S.schema.project.filter((f) => f[0] !== "glossary");
  return S.schema[kind];
}
function titleFor(kind, obj) {
  const a = curAgent();
  if (kind === "project") return "프로젝트 문서";
  if (kind === "glossary") return "데이터 사전";
  if (kind === "agent") return `${obj.id} · ${obj.name || ""}`;
  if (kind === "step") return `${a.id}-${obj.id} · ${obj.name || ""}`;
  if (kind === "edge") return `${a.id}-${obj.id} · ${nodeName(a, obj.from)} → ${nodeName(a, obj.to)}`;
  return `${obj.id} · ${nodeName(null, obj.from)} → ${nodeName(null, obj.to)}`;
}
function previewTarget() {
  const { kind, id } = S.sel, a = curAgent();
  if (kind === "project") return "project";
  if (kind === "glossary") return "glossary";
  if (kind === "agent" || kind === "link") return id;
  return `${a.id}-${id}`;
}
// Every data name the design uses: project input/output, step input/output, and what links carry.
function usedData() {
  const names = new Set();
  [...(S.doc.inputs || []), ...(S.doc.outputs || [])].forEach((r) => names.add(r.item));
  S.doc.agents.forEach((a) => {
    a.steps.forEach((s) => [...(s.inputs || []), ...(s.outputs || [])].forEach((n) => names.add(n)));
    a.edges.forEach((e) => (e.passes || []).forEach((n) => names.add(n)));
  });
  S.doc.links.forEach((l) => (l.passes || []).forEach((n) => names.add(n)));
  return [...names].filter(Boolean).sort();
}
const allNames = () => [...new Set([...(S.doc.glossary || []).map((g) => g.name), ...usedData()])].filter(Boolean).sort();
// What to write in a field, shown as its placeholder (the full guidance is in references/templates.md).
const HINT = {
  "project.summary": "무엇을 받아 무엇을 내놓는지 한 줄", "project.want": "사용자가 원하는 결과를 사용자 말에 가깝게",
  "project.success": "완성 여부를 판별할 수 있는 기준, 한 줄에 하나", "project.constraints": "응답 시간, 비용 한도, 개인정보, 언어처럼 꼭 지킬 조건",
  "agent.role": "이 에이전트가 맡는 역할 하나", "agent.intent": "다른 에이전트와 합치지 않고 나눈 이유",
  "step.summary": "이 단계가 하는 일 한 줄", "step.intent": "이 단계가 없으면 무엇이 깨지는지",
  "step.criteria": "AI가 지킬 기준, 한 줄에 하나 (예: 하루 이동 시간 3시간 이하)",
  "step.prompt": "AI에게 줄 역할, 받는 input, 지킬 것, 내야 할 output 형식",
  "step.done": "다음으로 넘어가도 되는 조건, 판별할 수 있게",
  "step.example": "input: 실제 값 → output: 실제 값 (한 건)",
  "step.on_fail": "실패 종류마다 다시 시도, 대체 값, 멈춤 중 무엇을 하는지",
  "edge.condition": "데이터로 판별할 수 있는 규칙 (예: 후보 수가 2개 이상)", "edge.name": "조건을 짧게 (예: 후보 부족)",
  "edge.intent": "이 갈래가 왜 필요한지", "edge.loop_limit": "숫자 (예: 2)",
};

function renderDoc() {
  const panel = $("panel-doc");
  const obj = selected();
  if (!obj) {
    panel.replaceChildren(S.doc ? el("ul", { class: "hint-list muted" },
      el("li", {}, "카드나 연결선을 누르면 그 문서가 열립니다. 카드의 input, 과정, output 줄을 누르면 그 칸으로 바로 갑니다. 빈 곳을 눌러도 마지막 문서는 그대로 남습니다."),
      el("li", {}, "에이전트 카드를 두 번 누르면 안의 단계로 들어갑니다."),
      el("li", {}, "빈 곳을 두 번 누르면 그 자리에 만듭니다. 오른쪽 클릭으로 카드·연결·빈 곳 메뉴를 엽니다."),
      el("li", {}, "카드 오른쪽의 점을 끌어 다른 카드에 놓으면 연결, 빈 곳에 놓으면 새로 만들고 연결합니다. 점을 누르기만 하면 오른쪽에 다음 단계가 생깁니다."),
      el("li", {}, `Shift를 누른 채 끌면 여러 개를 고릅니다. ${mod}K로 찾고, ?로 단축키를 봅니다.`),
      el("li", {}, "왼쪽 아래 버튼으로 카드를 간단히 보거나 자세히 봅니다."),
      el("li", {}, "확대·축소는 +와 -, 화면 맞춤은 0, 되돌리기는 ⌘Z(Windows는 Ctrl+Z)입니다.")) : "");
    return;
  }
  const kind = S.sel.kind;
  const head = el("div", { class: "doc-head" }, el("h2", { text: titleFor(kind, obj) }),
    el("div", { class: "row" },
      el("button", { type: "button", "aria-pressed": S.preview ? "true" : "false", on: { click: togglePreview } }, "미리보기"),
      ["project", "glossary"].includes(kind) ? null : el("button", { type: "button", class: "danger", on: { click: askRemove } }, "삭제"),
      kind === "agent" ? el("button", { type: "button", on: { click: () => enter(obj.id) } }, "안으로") : null));
  if (S.preview) {
    const pre = el("pre", { class: "preview" }, "불러오는 중…");
    panel.replaceChildren(head, pre);
    flushSave().then(() => api("GET", `/api/projects/${S.pid}/preview?target=${encodeURIComponent(previewTarget())}`))
      .then(({ ok, data }) => { pre.textContent = ok ? data.text || "(아직 만들 내용이 없습니다)" : data.error || "미리보기를 만들지 못했습니다."; });
    return;
  }
  const kids = [head];
  if (kind === "edge" || kind === "link") {
    const a = curAgent();
    kids.push(el("div", { class: "route" }, `${nodeName(a, obj.from)} → ${nodeName(a, obj.to)}`));
  }
  kids.push(el("datalist", { id: "names" }, ...allNames().map((n) => el("option", { value: n }))),
    el("datalist", { id: "data-types" }, ...S.schema.data_types.map((n) => el("option", { value: n }))));
  // Required fields first; optional ones fold away until they hold something (or the user opens them).
  // A conditional link needs its condition; a step's type adds what an implementer needs for that kind of work.
  const fields = fieldsFor(kind);
  const need = (f) => f[3] || ((kind === "edge" || kind === "link") && obj.kind === "cond" && S.schema.cond_required.includes(f[0]))
    || (kind === "step" && (S.schema.type_required[obj.type] || []).includes(f[0]));
  const main = kind === "glossary" ? fields : fields.filter(need), rest = kind === "glossary" ? [] : fields.filter((f) => !need(f));
  if (main.length) kids.push(el("div", { class: "group" }, ...main.map((f) => fieldEl(kind, obj, need(f) ? [...f.slice(0, 3), true, f[4]] : f))));
  if (rest.length) {
    const filled = rest.filter((f) => hasValue(obj[f[0]])).length;
    const open = S.optOpen ?? filled > 0;
    const box = el("details", { class: "group", open: open ? true : null },
      el("summary", {}, `선택 항목 ${rest.length}개${filled ? ` · ${filled}개 작성됨` : ""}`), ...rest.map((f) => fieldEl(kind, obj, f)));
    // Remember only what the user chose; the toggle event also fires when the box is created open.
    box.querySelector("summary").addEventListener("click", () => { S.optOpen = !box.open; });
    box.addEventListener("toggle", () => { if (box.open) fitAreas(); });
    kids.push(box);
  }
  panel.replaceChildren(...kids);
  fitAreas();
  if (S.focusField) {
    const f = $(`field-${S.focusField}`);
    S.focusField = null;
    if (f) {
      const box = f.closest("details");
      if (box) box.open = true;
      requestAnimationFrame(() => {
        f.scrollIntoView({ block: "center" });
        const input = f.querySelector("input, textarea, select, button");
        input?.focus({ preventScroll: true });
        if (input && "select" in input && input.tagName === "INPUT") input.select();
      });
    }
  }
}
function hasValue(v) {
  if (Array.isArray(v)) return v.some(hasValue);
  if (v && typeof v === "object") return Object.values(v).some(hasValue);
  return String(v ?? "").trim() !== "";
}
function fitAreas() { requestAnimationFrame(() => $("panel-doc").querySelectorAll("textarea").forEach(autosize)); }
function autosize(t) { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 2}px`; }
function togglePreview() { S.preview = !S.preview; renderDoc(); }

// Typing redraws the canvas once per short pause, not on every key.
let graphTimer = null;
function changed(kind, obj, key) {
  markDirty();
  if (["name", "color", "kind", "process", "tools", "inputs", "outputs", "passes", "summary", "role", "type"].includes(key)) {
    clearTimeout(graphTimer);
    graphTimer = setTimeout(() => { if (S.doc) { renderGraph(); renderTop(); } }, 120);
    const h = $("panel-doc").querySelector(".doc-head h2");
    if (h) h.textContent = titleFor(kind, obj);
  }
}
function fieldEl(kind, obj, [key, label, type, required, extra]) {
  const id = `f-${key}`;
  const lab = el("label", { for: id }, label, required ? el("span", { class: "req" }, " *") : null);
  const ident = obj.id || "";
  const set = (v) => { snapshot(`${kind}:${ident}:${key}`); obj[key] = v; changed(kind, obj, key); };
  const placeholder = HINT[`${kind === "link" ? "edge" : kind}.${key}`];
  let input;
  if (type === "line") input = el("input", { id, value: obj[key] ?? "", placeholder, on: { input: (e) => set(e.target.value) } });
  else if (type === "text") input = el("textarea", { id, rows: 2, placeholder, on: { input: (e) => { autosize(e.target); set(e.target.value); } } }, obj[key] ?? "");
  else if (type === "lines") {
    input = el("textarea", { id, rows: 2, placeholder, on: { input: (e) => { autosize(e.target); set(e.target.value.split("\n").map((x) => x.trim()).filter(Boolean)); } } }, (obj[key] || []).join("\n"));
    lab.append(el("span", { class: "hint" }, " 한 줄에 하나"));
  } else if (type === "names") {
    input = el("input", { id, list: "names", value: (obj[key] || []).join(", "),
      on: { input: (e) => set(e.target.value.split(",").map((x) => x.trim()).filter(Boolean)) } });
    lab.append(el("span", { class: "hint" }, " 쉼표로 구분, 데이터 사전의 이름"));
  } else if (type === "select") {
    const names = kind === "edge" || kind === "link" ? (key === "kind" ? S.schema.edge_kinds : null) : null;
    const opts = Array.isArray(extra) ? extra : [];
    input = el("select", { id, on: { change: (e) => { set(e.target.value); renderDoc(); $(id)?.focus(); } } },
      el("option", { value: "" }, "선택"), ...opts.map((o) => el("option", { value: o, selected: obj[key] === o }, names ? names[o] : o)));
  } else if (type === "ref") {
    const pool = (curAgent() ? curAgent().edges : S.doc.links).filter((x) => x.id !== obj.id);
    input = el("select", { id, on: { change: (e) => set(e.target.value) } }, el("option", { value: "" }, "없음"),
      ...pool.map((x) => el("option", { value: x.id, selected: obj[key] === x.id }, `${x.id} ${x.name || ""}`)));
  } else if (type === "color") {
    input = el("input", { id, type: "color", value: obj[key] || "#4C78A8", on: { input: (e) => set(e.target.value) } });
  } else if (["table", "process", "toolrefs", "tools", "glossary"].includes(type)) {
    const editor = { table: () => tableEl(kind, obj, key, extra), process: () => processEl(kind, obj), toolrefs: () => toolRefsEl(kind, obj),
      tools: () => toolsEl(obj), glossary: () => glossaryEl(obj) }[type]();
    return el("div", { class: "field", id: `field-${key}` }, el("div", { class: "label" }, label, required ? el("span", { class: "req" }, " *") : null,
      type === "process" ? el("span", { class: "hint" }, " 이 단계 안의 흐름을 순서대로") : null,
      type === "tools" ? el("span", { class: "hint" }, " 단계와 과정이 여기서 골라 씁니다") : null,
      type === "glossary" ? el("span", { class: "hint" }, " 데이터마다 구조를 적으면 구현할 때 그대로 씁니다") : null), editor);
  }
  return el("div", { class: "field", id: `field-${key}` }, lab, input);
}

// 과정: ordered rows joined by arrows; each row is a unit of the implementation (file, class, function, call, ...).
function processEl(kind, obj) {
  const rows = obj.process = obj.process || [];
  const wrap = el("div", { class: "process" });
  const touch = (key) => { snapshot(key); };
  const draw = () => {
    const items = rows.map((r, i) => {
      const unit = el("select", { class: "p-unit", "aria-label": `${i + 1}번 단위`, on: { change: (e) => { touch(); r.unit = e.target.value; changed(kind, obj, "process"); } } },
        ...S.schema.process_units.map((u) => el("option", { value: u, selected: r.unit === u }, u)));
      const name = el("input", { class: "p-name", value: r.name || "", placeholder: "이름 (예: minutes_loader.py, extract_decisions)", "aria-label": `${i + 1}번 이름`,
        on: { input: (e) => { touch(`process:${obj.id}:${i}:name`); r.name = e.target.value; changed(kind, obj, "process"); } } });
      const does = el("input", { class: "p-does", value: r.does || "", placeholder: "하는 일 (쉬운 말, 고르는 기준이 있으면 함께)", "aria-label": `${i + 1}번 하는 일`,
        on: { input: (e) => { touch(`process:${obj.id}:${i}:does`); r.does = e.target.value; changed(kind, obj, "process"); } } });
      const io = (k, ph) => el("input", { value: r[k] || "", placeholder: ph, list: "names", "aria-label": `${i + 1}번 ${k}`,
        on: { input: (e) => { touch(`process:${obj.id}:${i}:${k}`); r[k] = e.target.value; changed(kind, obj, "process"); } } });
      const ioRow = el("div", { class: "p-io" }, io("input", "input"), el("span", { "aria-hidden": "true" }, "→"), io("output", "output"));
      const tool = el("select", { class: "p-tool", "aria-label": `${i + 1}번 도구`, on: { change: (e) => { touch(); r.tool = e.target.value; changed(kind, obj, "process"); } } },
        el("option", { value: "" }, "도구 없음"), ...(S.doc.tools || []).map((t) => el("option", { value: t.id, selected: r.tool === t.id }, `${TOOL_ICON[t.kind] || ""} ${toolLabel(t)}`)));
      const move = (d) => { const j = i + d; if (j < 0 || j >= rows.length) return; touch(); [rows[i], rows[j]] = [rows[j], rows[i]]; changed(kind, obj, "process"); draw(); };
      const ctrls = el("div", { class: "row-ctrls" },
        el("button", { type: "button", class: "icon-s", "aria-label": `${i + 1}번 위로`, disabled: i === 0, on: { click: () => move(-1) } }, "↑"),
        el("button", { type: "button", class: "icon-s", "aria-label": `${i + 1}번 아래로`, disabled: i === rows.length - 1, on: { click: () => move(1) } }, "↓"),
        el("button", { type: "button", class: "icon-s", "aria-label": `${i + 1}번 삭제`, on: { click: () => { touch(); rows.splice(i, 1); changed(kind, obj, "process"); draw(); } } }, "×"));
      return [i ? el("div", { class: "process-arrow", "aria-hidden": "true" }, "↓") : null,
        el("div", { class: "process-item" }, el("span", { class: "num" }, String(i + 1)), unit, name, ctrls, does, ioRow, tool)];
    });
    wrap.replaceChildren(...items.flat().filter(Boolean),
      el("button", { type: "button", class: "add", on: { click: () => { touch(); rows.push({ unit: "함수", name: "", does: "", input: "", output: "", tool: "" }); changed(kind, obj, "process"); draw(); wrap.querySelector(".process-item:last-of-type input")?.focus(); } } }, "+ 과정 추가"));
  };
  draw();
  return wrap;
}

// Tools a step uses: chips picked from the project catalog, plus a quick way to add a new catalog entry.
function toolRefsEl(kind, obj) {
  const refs = obj.tools = obj.tools || [];
  const wrap = el("div", { class: "toolrefs" });
  const draw = () => {
    const pick = el("select", { "aria-label": "도구 추가", on: { change: (e) => {
      const v = e.target.value;
      if (v === "__new") return newTool((t) => { snapshot(); refs.push(t.id); changed(kind, obj, "tools"); draw(); });
      if (v) { snapshot(); refs.push(v); changed(kind, obj, "tools"); draw(); }
    } } }, el("option", { value: "" }, "+ 도구 추가"),
      ...(S.doc.tools || []).filter((t) => !refs.includes(t.id)).map((t) => el("option", { value: t.id }, `${TOOL_ICON[t.kind] || ""} ${toolLabel(t)}`)),
      el("option", { value: "__new" }, "새 도구 만들기…"));
    wrap.replaceChildren(...refs.map((id, i) => { const t = toolOf(id);
      return el("span", { class: `tool-pill${t ? "" : " missing"}` }, t ? `${TOOL_ICON[t.kind] || ""} ${toolLabel(t)}` : `${id} (목록에 없음)`,
        el("button", { type: "button", "aria-label": `${t ? toolLabel(t) : id} 빼기`, on: { click: () => { snapshot(); refs.splice(i, 1); changed(kind, obj, "tools"); draw(); } } }, "×")); }), pick);
  };
  draw();
  return wrap;
}
// 데이터 사전: one card per data item with its structure (field, type, required, description, example).
function glossaryEl(obj) {
  const rows = obj.glossary = obj.glossary || [];
  const wrap = el("div", { class: "tool-list" });
  const draw = () => {
    const missing = usedData().filter((n) => !rows.some((g) => g.name === n));
    const touched = () => changed("glossary", obj, "glossary");
    wrap.replaceChildren();
    add(wrap,
      missing.length ? el("div", { class: "notice" }, el("span", {}, `데이터 사전에 없는 데이터 ${missing.length}개: ${missing.join(", ")}`),
        el("button", { type: "button", on: { click: () => { snapshot(); missing.forEach((n) => rows.push({ name: n, meaning: "", contents: "", fields: [] })); touched(); draw(); } } }, "모두 추가")) : null,
      ...rows.map((g, i) => {
        const fields = g.fields = g.fields || [];
        const set = (target, k, v, key) => { snapshot(key); target[k] = v; touched(); };
        const text = (target, k, ph, key, cls) => el("input", { class: cls, value: target[k] ?? "", placeholder: ph, "aria-label": `${g.name || i + 1} ${ph}`,
          list: k === "type" ? "data-types" : null, on: { input: (e) => set(target, k, e.target.value, key) } });
        const fieldRow = (f, j) => el("div", { class: "data-field" },
          text(f, "name", "필드 이름", `gl:${i}:${j}:name`, "f-name"), text(f, "type", "형식", `gl:${i}:${j}:type`, "f-type"),
          el("label", { class: "req-box f-req", title: "필수" }, el("input", { type: "checkbox", checked: f.required !== false ? true : null, "aria-label": "필수",
            on: { change: (e) => set(f, "required", e.target.checked) } }), "필수"),
          text(f, "desc", "설명", `gl:${i}:${j}:desc`, "f-desc"), text(f, "example", "예", `gl:${i}:${j}:ex`, "f-ex"),
          el("button", { type: "button", class: "icon-s f-x", "aria-label": `${f.name || j + 1} 필드 삭제`, on: { click: () => { snapshot(); fields.splice(j, 1); touched(); draw(); } } }, "×"));
        return el("div", { class: "tool-card" },
          el("div", { class: "tool-head" }, el("span", { class: "tid" }, "데이터"), text(g, "name", "데이터 이름", `gl:${i}:name`),
            el("button", { type: "button", class: "icon-s", "aria-label": `${g.name || i + 1} 삭제`, on: { click: () => { snapshot(); rows.splice(i, 1); touched(); draw(); } } }, "×")),
          text(g, "meaning", "뜻 (한 줄)", `gl:${i}:meaning`),
          el("div", { class: "data-fields" }, ...fields.map(fieldRow),
            el("button", { type: "button", class: "add", on: { click: () => { snapshot(); fields.push({ name: "", type: "", required: true, desc: "", example: "" }); touched(); draw(); } } }, "+ 필드 추가")),
          text(g, "contents", "필드로 담지 못한 규칙 (선택)", `gl:${i}:contents`),
          el("div", { class: "tool-used" }, usedData().includes(g.name) ? "" : "아직 쓰는 곳이 없습니다"));
      }),
      el("button", { type: "button", class: "add", on: { click: () => { snapshot(); rows.push({ name: "", meaning: "", contents: "", fields: [] }); touched(); draw(); } } }, "+ 데이터 추가"));
  };
  draw();
  return wrap;
}
function newTool(done) {
  const kindSel = el("select", { "aria-label": "종류" }, ...S.schema.tool_kinds.map((k) => el("option", { value: k }, `${TOOL_ICON[k]} ${k}`)));
  const name = el("input", { placeholder: "이름 (예: 지도 MCP, 날씨 API, plan.py)", "aria-label": "이름" });
  const purpose = el("input", { placeholder: "용도", "aria-label": "용도" });
  const location = el("input", { placeholder: "위치·접속 (서버 이름, 파일 경로, 주소, 인증 방식)", "aria-label": "위치·접속" });
  const create = () => {
    if (!name.value.trim()) { name.focus(); return; }
    const t = { id: nextId(S.doc.tools || [], "T"), kind: kindSel.value, name: name.value.trim(), purpose: purpose.value.trim(), location: location.value.trim(), alternative: "" };
    snapshot();
    (S.doc.tools = S.doc.tools || []).push(t);
    closeModal();
    done(t);
  };
  modal("새 도구", [el("div", { class: "form-grid" }, kindSel, name, purpose, location)], [["만들기", create, "primary"], ["취소", closeModal]]);
}
// Project tool catalog: kind, name (or the agent it points at), purpose, location, alternative, and who uses it.
function toolsEl(obj) {
  const rows = obj.tools = obj.tools || [];
  const wrap = el("div", { class: "tool-list" });
  const users = () => {
    const map = {};
    for (const a of S.doc.agents) for (const st of a.steps) {
      for (const id of new Set([...(st.tools || []), ...(st.process || []).map((p) => p.tool).filter(Boolean)])) (map[id] = map[id] || []).push(`${a.id}-${st.id}`);
    }
    return map;
  };
  const draw = () => {
    const used = users();
    wrap.replaceChildren(...rows.map((t, i) => {
      const set = (k, v, key) => { snapshot(key); t[k] = v; changed("project", obj, "tools"); };
      const kind = el("select", { "aria-label": `${t.id} 종류`, on: { change: (e) => { set("kind", e.target.value); draw(); } } },
        ...S.schema.tool_kinds.map((k) => el("option", { value: k, selected: t.kind === k }, `${TOOL_ICON[k]} ${k}`)));
      const name = t.kind === "내부 에이전트"
        ? el("select", { "aria-label": `${t.id} 에이전트`, on: { change: (e) => { set("ref", e.target.value); set("name", toolLabel(t)); } } },
          el("option", { value: "" }, "에이전트 선택"), ...S.doc.agents.map((a) => el("option", { value: a.id, selected: t.ref === a.id }, `${a.id} ${a.name || ""}`)))
        : el("input", { value: t.name || "", placeholder: "이름", "aria-label": `${t.id} 이름`, on: { input: (e) => set("name", e.target.value, `tool:${t.id}:name`) } });
      const field = (k, ph) => el("input", { value: t[k] || "", placeholder: ph, "aria-label": `${t.id} ${ph}`, on: { input: (e) => set(k, e.target.value, `tool:${t.id}:${k}`) } });
      return el("div", { class: "tool-card" },
        el("div", { class: "tool-head" }, el("span", { class: "tid" }, t.id), kind,
          el("button", { type: "button", class: "icon-s", "aria-label": `${t.id} 삭제`, on: { click: () => { snapshot(); rows.splice(i, 1); changed("project", obj, "tools"); draw(); } } }, "×")),
        name, field("purpose", "용도"), field("location", "위치·접속 (서버, 파일 경로, 주소, 인증 방식)"), field("alternative", "대안"),
        el("div", { class: "tool-used" }, used[t.id] ? `쓰는 곳: ${used[t.id].join(", ")}` : "아직 쓰는 단계가 없습니다"));
    }), el("button", { type: "button", class: "add", on: { click: () => { snapshot(); rows.push({ id: nextId(rows, "T"), kind: "기타", name: "", purpose: "", location: "", alternative: "" }); changed("project", obj, "tools"); draw(); } } }, "+ 도구 추가"));
  };
  draw();
  return wrap;
}

function tableEl(kind, obj, key, cols) {
  const rows = obj[key] = obj[key] || [];
  const wrap = el("div", { class: "grid-table", style: `--cols: ${cols.length}` });
  const draw = () => {
    wrap.replaceChildren(
      el("div", { class: "tr head" }, ...cols.map(([, l]) => el("span", { text: l })), el("span", { class: "x" })),
      ...rows.map((row, i) => el("div", { class: "tr" },
        ...cols.map(([c, l]) => el("textarea", { rows: 1, "aria-label": l, on: { input: (e) => {
          snapshot(`${kind}:${obj.id}:${key}:${i}:${c}`);
          row[c] = e.target.value;
          autosize(e.target);
          changed(kind, obj, key);
        } } }, row[c] ?? "")),
        el("button", { type: "button", class: "x", "aria-label": "행 삭제", on: { click: () => {
          snapshot();
          rows.splice(i, 1);
          changed(kind, obj, key);
          draw();
        } } }, "×"))),
      el("button", { type: "button", on: { click: () => { snapshot(); rows.push(Object.fromEntries(cols.map(([c]) => [c, ""]))); changed(kind, obj, key); draw(); } } }, "+ 행 추가"));
    fitAreas();
  };
  draw();
  return wrap;
}

// ---------- tabs ----------
function setTab(tab) {
  S.tab = tab;
  $("tab-doc").setAttribute("aria-selected", tab === "doc");
  $("tab-chat").setAttribute("aria-selected", tab === "chat");
  $("panel-doc").hidden = tab !== "doc";
  $("panel-chat").hidden = tab !== "chat";
  if (tab === "chat") { S.unread = false; $("unread").hidden = true; scrollChat(); }
  if (tab === "doc") fitAreas();
}
$("tab-doc").addEventListener("click", () => setTab("doc"));
$("tab-chat").addEventListener("click", () => setTab("chat"));

// ---------- chat ----------
async function loadMessages() {
  if (!S.pid) return;
  const { ok, data } = await api("GET", `/api/projects/${S.pid}/messages`);
  if (!ok) return;
  const fresh = data.filter((m) => m.id > S.lastMsg);
  S.msgs = data;
  S.lastMsg = data.length ? data[data.length - 1].id : 0;
  if (S.msgsLoaded && fresh.some((m) => m.role !== "user") && S.tab !== "chat") { S.unread = true; $("unread").hidden = false; }
  S.msgsLoaded = true;
  renderChat();
}
function renderChat() {
  const box = $("messages");
  if (cy) { cy.elements().removeClass("hl"); cardEls.forEach((c) => c.classList.remove("hl")); }  // a removed card never gets its mouseleave
  box.replaceChildren(...S.msgs.map(messageEl));
  renderAiState();
  scrollChat();
}
function scrollChat() { const box = $("messages"); box.scrollTop = box.scrollHeight; }
function messageEl(m) {
  if (m.kind === "card") return cardEl(m);
  if (m.kind === "notice") return el("div", { class: "msg system" }, m.body.text);
  if (m.kind === "polish") return el("div", { class: "msg user" }, "한국어 다듬기를 요청했습니다.");
  return el("div", { class: `msg ${m.role}` }, m.body.text);
}
function cardEl(m) {
  const c = m.body, done = m.status !== "pending";
  const status = { applied: "적용함", dismissed: "닫음", pending: "" }[m.status] || "";
  const box = el("div", { class: `card${done ? " done" : ""}` },
    el("h3", { text: c.title || (c.kind === "polish" ? "한국어 다듬기" : "제안") }),
    c.criterion || (c.targets || []).length ? el("div", { class: "meta" }, [c.criterion, (c.targets || []).join(", ")].filter(Boolean).join(" · ")) : null,
    c.reason ? el("div", {}, el("strong", {}, "근거 "), c.reason) : null,
    (c.changes || []).length ? el("ul", {}, ...c.changes.map((x) => el("li", {}, x))) : null,
    c.effect ? el("div", {}, el("strong", {}, "효과 "), c.effect) : null,
    done ? el("div", { class: "meta" }, status)
      : el("div", { class: "row" },
        el("button", { type: "button", class: "primary", on: { click: (e) => { e.currentTarget.disabled = true; applyCard(m); } } }, "적용"),
        el("button", { type: "button", on: { click: () => dismissCard(m) } }, "닫기")));
  box.addEventListener("mouseenter", () => highlight(c.targets || [], true));
  box.addEventListener("mouseleave", () => highlight(c.targets || [], false));
  return box;
}
function highlight(targets, on) {
  if (!cy) return;
  const a = curAgent();
  for (const t of targets) {
    let id = null;
    if (!a && /^A\d+$/.test(t)) id = t;
    else if (!a && /^L\d+$/.test(t)) id = `link:${t}`;
    else if (a && t.startsWith(`${a.id}-N`)) id = t.slice(a.id.length + 1);
    else if (a && t.startsWith(`${a.id}-L`)) id = `edge:${t.slice(a.id.length + 1)}`;
    if (!id) continue;
    cardEls.get(id)?.classList.toggle("hl", on);
    cy.$id(id)[on ? "addClass" : "removeClass"]("hl");
  }
}
async function applyCard(m) {
  await flushSave();
  const res = await api("POST", `/api/cards/${m.id}/apply`);
  if (!res.ok) modal("적용할 수 없음", [el("p", {}, res.data.error || "")], [["닫기", closeModal]]);
  await reloadDoc();
  loadMessages();
}
async function dismissCard(m) { await api("POST", `/api/cards/${m.id}/dismiss`); loadMessages(); }

function renderAiState() {
  const box = $("ai-state");
  const on = S.aiSeen !== null && S.aiSeen < 150;
  box.className = on ? "" : "off";
  box.textContent = on ? "AI가 대기 중입니다." : "AI가 대기하고 있지 않습니다. 보낸 메시지는 쌓였다가, 터미널에서 /clonamic-create-agent를 다시 실행하면 이어서 처리됩니다.";
}
setInterval(async () => {
  if (!S.pid) return;
  const { ok, data } = await api("GET", `/api/projects/${S.pid}`);
  if (ok) { S.aiSeen = data.ai_seen; renderAiState(); }
}, 20000);

$("chat-form").addEventListener("submit", (e) => { e.preventDefault(); sendChat(); });
$("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); }
});
async function sendChat() {
  const text = $("chat-input").value.trim();
  if (!text || !S.pid) return;
  $("chat-input").value = "";
  await flushSave();
  const res = await api("POST", `/api/projects/${S.pid}/messages`, { role: "user", text });
  if (!res.ok) { $("chat-input").value = text; modal("보내지 못함", [el("p", {}, res.data.error || "메시지를 보내지 못했습니다.")], [["닫기", closeModal]]); return; }
  loadMessages();
}

// ---------- export ----------
async function openExport() {
  await flushSave();
  const input = el("input", { value: S.exportPath || S.defaultPath, "aria-label": "저장 경로" });
  const result = el("div");
  const check = async () => {
    result.replaceChildren(el("p", { class: "muted" }, "검사 중…"));
    const { ok, data } = await api("GET", `/api/projects/${S.pid}/check`);
    if (!ok) { result.replaceChildren(el("p", { class: "issues" }, data.error)); return false; }
    if (data.issues.length) {
      result.replaceChildren(el("p", {}, `검사에 걸린 항목 ${data.issues.length}개를 먼저 고치세요.`), issueList(data.issues));
      return false;
    }
    const plan = await api("POST", `/api/projects/${S.pid}/export`, { path: input.value, dry: true });
    if (!plan.ok) { result.replaceChildren(el("p", { class: "issues" }, plan.data.error)); return false; }
    const notes = [el("p", { class: "ok" }, "검사를 통과했습니다.")];
    if (plan.data.foreign.length) notes.push(el("p", { class: "muted" }, `이 도구가 만들지 않은 파일 ${plan.data.foreign.length}개는 그대로 둡니다.`));
    if (plan.data.clash.length) notes.push(el("p", { class: "issues" }, "같은 이름의 다른 파일이 있어 내보낼 수 없습니다: " + plan.data.clash.join(", ")));
    if (!S.polished) notes.push(el("p", { class: "muted" }, "한국어 다듬기를 아직 하지 않았습니다. 다듬기를 요청하면 AI가 제안 카드로 보여 주고, 적용한 뒤 다시 내보내면 됩니다."));
    result.replaceChildren(...notes);
    return !plan.data.clash.length;
  };
  const doExport = async () => {
    if (!(await check())) return;
    const res = await api("POST", `/api/projects/${S.pid}/export`, { path: input.value });
    if (!res.ok) { result.replaceChildren(el("p", { class: "issues" }, res.data.error)); return; }
    S.exportPath = input.value;
    const d = res.data;
    result.replaceChildren(...[el("p", { class: "ok" }, `${d.path}에 ${d.written}개 파일을 내보냈습니다.`),
      d.removed.length ? el("p", { class: "muted" }, `이전 내보내기의 파일 ${d.removed.length}개를 정리했습니다.`) : null,
      d.untouched.length ? el("p", { class: "muted" }, `다른 파일 ${d.untouched.length}개는 그대로 두었습니다.`) : null,
      d.polished ? null : el("p", { class: "muted" }, "README에 '다듬기 미적용'이 표시됩니다.")].filter(Boolean));
  };
  const polish = async () => {
    await api("POST", `/api/projects/${S.pid}/polish`);
    closeModal();
    setTab("chat");
    loadMessages();
  };
  modal("내보내기", [el("label", { for: "export-path" }, "저장 경로"), input, result], [
    ["검사", check], ["내보내기", doExport, "primary"], S.polished ? null : ["다듬기 요청", polish], ["닫기", closeModal],
  ].filter(Boolean));
  input.id = "export-path";
  check();
}
function goTo(target) {
  if (target === "project") return select("project", "");
  if (target === "glossary") return select("glossary", "");
  if (target === "tools") return select("project", "", "tools");
  const m = /^(A\d+)(?:-(N\d+|L\d+))?$/.exec(target);
  if (/^L\d+$/.test(target)) { back(); return select("link", target); }
  if (!m) return;
  if (!m[2]) { back(); return select("agent", m[1]); }
  enter(m[1]);
  select(m[2].startsWith("N") ? "step" : "edge", m[2]);
}

// ---------- boot ----------
function renderAll() { renderTop(); renderGraph(); renderDoc(); renderChat(); }
// ---------- right panel width ----------
function setRightWidth(px) {
  const w = Math.max(320, Math.min(760, Math.round(px)));
  document.documentElement.style.setProperty("--right-w", `${w}px`);
  if (cy) { cy.resize(); syncView(); }
  return w;
}
try { const saved = parseInt(localStorage.getItem("cagent-right-w"), 10); if (saved) setRightWidth(saved); } catch (_) { /* storage off */ }
$("resizer").addEventListener("pointerdown", (e) => {
  e.preventDefault();
  const move = (ev) => setRightWidth(window.innerWidth - ev.clientX);
  const up = (ev) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    try { localStorage.setItem("cagent-right-w", String(setRightWidth(window.innerWidth - ev.clientX))); } catch (_) { /* storage off */ }
    fitAreas();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
});

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (cy) cy.style(STYLE()); });
async function boot() {
  S.schema = (await api("GET", "/api/schema")).data;
  await loadProjects();
  listen();
  const pid = parseInt(location.hash.slice(1), 10);
  if (pid && S.projects.some((p) => p.id === pid)) openProject(pid);
  else renderAll();
}
window.addEventListener("hashchange", () => {
  const pid = parseInt(location.hash.slice(1), 10);
  if (pid && pid !== S.pid) openProject(pid);
});
boot();
