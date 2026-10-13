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
async function api(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method, headers: { "Content-Type": "application/json", "X-Clonamic": "1" },
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
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
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
  if (ref.startsWith("exit:")) return ref.slice(5);
  const item = (a ? a.steps : S.doc.agents).find((x) => x.id === ref);
  return item ? item.name : ref;
}
function colorOf(a) {
  return a.color || S.schema.colors[S.doc.agents.indexOf(a) % S.schema.colors.length];
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
  S.redo = [];
  renderHistoryButtons();
}
function restore(from, to) {
  if (!from.length) return;
  to.push(JSON.stringify(S.doc));
  S.doc = JSON.parse(from.pop());
  S.lastKey = null;
  if (S.level !== "agents" && !agentOf(S.level)) S.level = "agents";
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
const FONT = getComputedStyle(document.body).fontFamily;

// ---------- modal ----------
function modal(title, body, actions) {
  const box = $("modal").firstElementChild;
  box.replaceChildren(el("h2", { text: title }), ...[body].flat(),
    el("div", { class: "row" }, ...actions.map(([label, fn, cls]) => el("button", { type: "button", class: cls, on: { click: fn } }, label))));
  $("modal").hidden = false;
  const first = box.querySelector("input, textarea, button.primary, button");
  if (first) first.focus();
}
const closeModal = () => { $("modal").hidden = true; };
$("modal").addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// ---------- projects ----------
async function loadProjects() {
  const { ok, data } = await api("GET", "/api/projects");
  if (!ok) return;
  S.projects = data;
  const list = $("projects");
  list.replaceChildren(...data.map((p) => el("li", { class: p.id === S.pid ? "active" : null },
    el("button", { class: "open", type: "button", title: p.name, "aria-current": p.id === S.pid ? "true" : null, on: { click: () => openProject(p.id) } },
      el("span", { class: "name" }, p.name || "(이름 없음)"), el("span", { class: "when" }, ago(p.updated))),
    el("button", { class: "more", type: "button", "aria-label": `${p.name} 메뉴`, on: { click: () => askDelete(p) } }, "⋯"))));
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
  modal("프로젝트 삭제", [el("p", {}, `편집기에서「${p.name}」을(를) 지웁니다. 이미 내보낸 문서 폴더는 그대로 남습니다. 확인하려면 프로젝트 이름을 입력하세요.`), input], [
    ["삭제", async () => {
      if (input.value.trim() !== p.name) { input.focus(); return; }
      await api("DELETE", `/api/projects/${p.id}`);
      closeModal();
      if (S.pid === p.id) { S.pid = null; S.doc = null; location.hash = ""; renderAll(); }
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
  S.level = "agents"; S.sel = null; S.msgs = []; S.lastMsg = 0; S.preview = false;
  S.undo = []; S.redo = []; S.lastKey = null; S.fitNext = true;
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
async function save() {
  if (!S.dirty || S.saving || !S.pid) return;
  S.saving = true; S.dirty = false;
  const res = await api("PUT", `/api/projects/${S.pid}`, { doc: S.doc, version: S.version });
  S.saving = false;
  if (res.ok) {
    S.version = res.data.version; S.polished = false; S.savedAt = Date.now();
    setSave("저장됨 · 방금");
    refreshIssues();
  } else if (res.status === 409) {
    await reloadDoc();
    setSave("다른 곳에서 바뀌어 최신 내용을 다시 불러왔습니다");
  } else {
    S.dirty = true;
    setSave("저장 실패 · 다시 시도합니다");
    S.saveTimer = setTimeout(save, 2000);
  }
  if (S.dirty) markDirty();
}
async function flushSave() { clearTimeout(S.saveTimer); await save(); }
async function reloadDoc() {
  const { ok, data } = await api("GET", `/api/projects/${S.pid}`);
  if (!ok) return;
  if (JSON.stringify(data.doc) !== JSON.stringify(S.doc)) snapshot();  // AI edits and applied cards can be undone too
  S.doc = data.doc; S.version = data.version; S.polished = data.polished; S.aiSeen = data.ai_seen;
  S.exportPath = data.export_path;
  if (S.level !== "agents" && !agentOf(S.level)) S.level = "agents";
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
    el("button", { type: "button", on: { click: () => { closeModal(); goTo(i.target); } } }, i.message))));
}
setInterval(() => {
  if (S.savedAt && !S.dirty && !S.saving) {
    const min = Math.floor((Date.now() - S.savedAt) / 60000);
    setSave(min < 1 ? "저장됨 · 방금" : `저장됨 · ${min}분 전`);
  }
}, 30000);
window.addEventListener("beforeunload", () => { if (S.dirty) save(); });

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
// The visible cards are HTML laid over those boxes. A card reads left to right: 입력 → 과정 → 출력;
// every 출력 row has a port the link leaves from, so no text ever sits on a line.
const CARD_W = 236, PILL_W = 132, LINE_H = 18;
const FONT_STACK = getComputedStyle(document.documentElement).getPropertyValue("--font");
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
    if (!a) return t === nodeId || t.startsWith(`${nodeId}-`) || (nodeId === "start" && false);
    if (t === `${a.id}-${nodeId}`) return true;
    const e = a.edges.find((x) => `${a.id}-${x.id}` === t);
    return !!e && e.from === nodeId;
  }).length;
}

function outgoing(id) {
  const a = curAgent();
  return a ? a.edges.filter((e) => e.from === id) : S.doc.links.filter((l) => l.from === id);
}
const rowText = (r) => r.label + (r.data && r.data.length ? ` → ${r.data.join(", ")}` : "");

// One card = a stack of fixed-height parts, so heights, ports, and click areas all come from the same numbers.
function buildSpecs() {
  const a = curAgent(), list = [];
  const destName = (e) => nodeName(a, e.to);
  const edgeRows = (id, always) => {
    const outs = outgoing(id);
    if (!outs.length) return always ? [{ edge: null, label: "연결 없음", empty: true }] : [];
    return outs.map((e) => ({ edge: e, label: e.name || destName(e), data: e.passes || [] }));
  };
  if (!a) {
    list.push({ id: "start", kind: "start", title: "시작", rows: outgoing("start").length > 1 ? edgeRows("start") : [], headOut: true });
    for (const x of S.doc.agents) {
      const incoming = S.doc.links.filter((l) => l.to === x.id);
      const n = issueCount(x.id);
      list.push({ id: x.id, kind: "agent", title: x.name, badge: x.id, color: colorOf(x), sub: x.role,
        chips: [x.steps.length ? `단계 ${x.steps.length}` : "단계 없음", n ? `⚠ ${n}` : null].filter(Boolean),
        input: [...new Set(incoming.flatMap((l) => l.passes || []))],
        rows: x.exits.map((ex) => { const l = S.doc.links.find((y) => y.from === x.id && y.exit === ex.name);
          return { exit: ex.name, edge: l || null, label: ex.name, data: l ? l.passes || [] : [], empty: !l }; }),
        headOut: true, headIn: true });
    }
    list.push({ id: "end", kind: "end", title: "끝", rows: [], headIn: true });
  } else {
    list.push({ id: "start", kind: "start", title: "시작", rows: outgoing("start").length > 1 ? edgeRows("start") : [], headOut: true });
    for (const st of a.steps) {
      const n = issueCount(st.id);
      list.push({ id: st.id, kind: "step", title: st.name, badge: st.id, color: colorOf(a), sub: st.summary,
        chips: [`${TYPE_ICON[st.type] || "□"} ${st.type || "유형 없음"}`, n ? `⚠ ${n}` : null].filter(Boolean),
        input: st.inputs || [], process: (st.process || []).filter((p) => (p.name || "").trim()),
        tools: [...new Set([...(st.tools || []), ...(st.process || []).map((p) => p.tool).filter(Boolean)])].map(toolOf).filter(Boolean),
        rows: edgeRows(st.id, true), headOut: true, headIn: true, tip: st });
    }
    for (const ex of a.exits) {
      const l = S.doc.links.find((y) => y.from === a.id && y.exit === ex.name);
      list.push({ id: `exit:${ex.name}`, kind: "exit", title: ex.name, color: colorOf(a), rows: [], headIn: true,
        sub: l ? `→ ${nodeName(null, l.to)}` : "에이전트 연결 없음" });
    }
  }
  for (const sp of list) measure(sp);
  specs = new Map(list.map((sp) => [sp.id, sp]));
  return list;
}

function measure(sp) {
  const pill = ["start", "end", "exit"].includes(sp.kind), detail = S.detail;
  sp.w = pill ? PILL_W : CARD_W;
  sp.bt = sp.kind === "agent" ? 3 : 1;
  const parts = [];
  sp.lines = lines(sp.title, pill ? sp.w - 28 : sp.w - 24 - 36 - 8, TITLE_FONT);
  const headH = pill ? 16 + sp.lines * LINE_H + (sp.sub ? 16 : 0) : 10 + sp.lines * LINE_H + (sp.chips?.length ? 22 : 0) + 6;
  parts.push({ type: "head", h: headH });
  if (!pill && detail && sp.sub) parts.push({ type: "sub", h: 20 });
  if (!pill && detail && sp.input?.length) parts.push({ type: "input", h: 26 });
  if (!pill && detail && sp.process?.length) parts.push({ type: "process", h: 26 });
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

// Where a link attaches: the right edge of its 출력 row (or the header), and the left edge of the target header.
function endpoints(edge, sourceId, targetId) {
  const s = specs.get(sourceId), t = specs.get(targetId);
  if (!s || !t) return null;
  const i = s.rows.findIndex((r) => r.edge === edge);
  const part = i >= 0 ? partOf(s, "row", i) : partOf(s, "head");
  return { src: `${s.w / 2}px ${part.y + part.h / 2 - s.h / 2}px`, dst: `${-t.w / 2}px ${t.bt + t.headH / 2 - t.h / 2}px` };
}

// Node.append() turns null into the text "null"; skip empty parts instead.
const add = (parent, ...kids) => parent.append(...kids.filter((k) => k !== null && k !== undefined && k !== false));
function nodeCardEl(sp) {
  const pill = ["start", "end", "exit"].includes(sp.kind);
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
    else if (part.type === "input") add(box, el("span", { class: "tag" }, "입력"), el("span", { class: "line" }, sp.input.join(" · ")));
    else if (part.type === "process") add(box, el("span", { class: "tag" }, `과정 ${sp.process.length}`),
      el("span", { class: "line" }, ...sp.process.flatMap((p, i) => [i ? el("span", { class: "arrow" }, " → ") : null, p.name])));
    else if (part.type === "outlabel") add(box, el("span", { class: "tag" }, "출력"));
    else if (part.type === "row") {
      const r = sp.rows[part.i];
      box.classList.toggle("empty", !!r.empty);
      add(box, el("span", { class: "row-text", style: `-webkit-line-clamp:${r.lines}` },
        el("span", { class: "rname" }, r.label), r.data?.length ? el("span", { class: "rdata" }, ` → ${r.data.join(", ")}`) : null),
        r.empty && r.exit ? el("span", { class: "rnone" }, "연결 없음") : null);
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
    "curve-style": "round-taxi", "taxi-direction": "rightward", "taxi-turn": 28, "taxi-turn-min-distance": 8, "taxi-radius": 10, label: "" } },
  { selector: "edge.back", style: { "curve-style": "unbundled-bezier", "control-point-distances": [-60], "control-point-weights": [0.5], "line-style": "dashed", "line-dash-pattern": [6, 4] } },
  { selector: "edge.sel", style: { "line-color": css("--accent"), "target-arrow-color": css("--accent"), width: 2.6, "z-index": 9 } },
  { selector: "edge.hl", style: { "line-color": css("--hl"), "target-arrow-color": css("--hl"), width: 3, "z-index": 9 } },
];

function elements() {
  const a = curAgent(), items = [];
  for (const sp of buildSpecs()) items.push({ group: "nodes", data: { id: sp.id, w: sp.w, h: sp.h } });
  const edges = a ? a.edges.map((e) => [`edge:${e.id}`, e]) : S.doc.links.map((l) => [`link:${l.id}`, l]);
  for (const [id, e] of edges) {
    const ends = endpoints(e, e.from, e.to);
    if (ends) items.push({ group: "edges", data: { id, source: e.from, target: e.to, se: ends.src, te: ends.dst } });
  }
  return items;
}

function renderGraph() {
  hideTip();
  if (!S.doc) { if (cy) cy.elements().remove(); $("cards-inner").replaceChildren(); return; }
  if (!cy) {
    cy = cytoscape({ container: $("cy"), style: STYLE(), wheelSensitivity: 0.3, boxSelectionEnabled: false, autounselectify: true, minZoom: 0.2, maxZoom: 2.5 });
    cy.on("tap", "node", (e) => tapNode(e.target, e.position));
    cy.on("tap", "edge", (e) => select(curAgent() ? "edge" : "link", e.target.id().split(":")[1]));
    // A tap on empty canvas keeps the last opened document; the 검토 tab is one click away.
    cy.on("dbltap", "node", (e) => { if (!curAgent() && agentOf(e.target.id())) enter(e.target.id()); });
    cy.on("dragfree", "node", () => { snapshot(); resolveOverlaps(); savePositions(); markDirty(); markBack(); });
    cy.on("position", "node", (e) => placeCard(e.target));
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
  let missing = stale;
  cy.nodes().forEach((n) => { if (!stale && pos[n.id()]) n.position(pos[n.id()]); else missing = true; placeCard(n); });
  if (missing) { if (stale) snapshot(); arrange(false); }
  else {
    if (resolveOverlaps()) { savePositions(); markDirty(); }
    if (S.fitNext) openView();
  }
  S.fitNext = false;
  markBack();
  markSelection();
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
// Links that run right-to-left are drawn as a dashed curve; a rightward elbow would fold back over the cards.
function markBack() {
  cy.edges().forEach((e) => e.toggleClass("back", e.target().position().x <= e.source().position().x + 40));
}
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
function markSelection() {
  cardEls.forEach((c) => c.classList.remove("sel"));
  cy.edges().removeClass("sel");
  if (!S.sel) return;
  const id = cyId(S.sel.kind, S.sel.id);
  cardEls.get(id)?.classList.add("sel");
  cy.$id(id).addClass("sel");
}

function arrange(save = true) {
  if (save) snapshot();
  const run = cy.layout({ name: "dagre", rankDir: "LR", nodeSep: 32, rankSep: 90, edgeSep: 14, fit: false });
  run.one("layoutstop", () => { resolveOverlaps(); savePositions(); markDirty(); markBack(); openView(); });
  run.run();
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
  if (kind === "exit") return `exit:${id}`;
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
    if (r.exit) return select("agent", id, "exits");
  }
  if (id === "start" || id === "end") return;
  if (id.startsWith("exit:")) return select("exit", id.slice(5));
  const focus = { input: "inputs", process: "process", tools: "tools", outlabel: "outputs", sub: a ? "summary" : "role" }[part?.type];
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
  tip.replaceChildren(el("div", {}, el("strong", {}, "입력 "), (st.inputs || []).join(", ") || "없음"),
    el("div", {}, el("strong", {}, "출력 "), (st.outputs || []).join(", ") || "없음"));
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
  S.portDrag = { nodeId, rowIndex, target: null };
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
  };
  const end = (ev) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("keydown", esc);
    svg.hidden = true;
    path.setAttribute("d", "");
    cardEls.forEach((c) => c.classList.remove("drop", "nodrop"));
    const drag = S.portDrag;
    S.portDrag = null;
    if (ev && drag?.target) dropLink(drag.nodeId, drag.rowIndex, drag.target);
  };
  const esc = (ev) => { if (ev.key === "Escape") end(null); };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
  window.addEventListener("keydown", esc);
  move(e);
}
function canDrop(src, dst) {
  if (src === dst || dst === "start") return false;
  return !src.startsWith("exit:") && src !== "end";
}
function dropLink(src, rowIndex, dst) {
  const a = curAgent(), sp = specs.get(src), row = rowIndex >= 0 ? sp.rows[rowIndex] : null;
  snapshot();
  if (row?.edge) {
    row.edge.to = dst;
    return after(a ? "edge" : "link", row.edge.id);
  }
  if (!a) {
    let exit = "";
    if (src !== "start") {
      const from = agentOf(src);
      if (row?.exit) exit = row.exit;
      else {
        let n = from.exits.length + 1;
        exit = from.exits.length ? `출력${n}` : "완료";
        while (from.exits.some((x) => x.name === exit)) exit = `출력${++n}`;
        from.exits.push({ name: exit, when: "" });
      }
    }
    const link = { id: nextId(S.doc.links, "L"), from: src, to: dst, kind: "always", exit, name: "", passes: [] };
    S.doc.links.push(link);
    return after("link", link.id);
  }
  const e = { id: nextId(a.edges, "L"), from: src, to: dst, kind: "always", name: "", passes: [] };
  a.edges.push(e);
  after("edge", e.id);
}
function after(kind, id) {
  markDirty();
  renderGraph();
  select(kind, id);
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
    el("p", {}, a ? "이 에이전트가 맡은 역할을 이루는 단계를 추가하세요." : "직접 에이전트를 추가하거나, 검토 탭에서 AI와 인터뷰로 시작하세요."),
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
  else { btn("+ 단계", addStep); btn("+ 출력", addExit, { title: "에이전트가 끝나는 경우를 추가합니다" }); }
  btn("자동 정렬", () => arrange(true), { title: "배치를 새로 계산합니다" });
  sep();
  btn("프로젝트 문서", () => select("project", ""));
  btn("도구 목록", () => select("project", "", "tools"));
  btn("용어 사전", () => select("glossary", ""));
  $("zoom").append(ibtn(I.plus, "확대 (+)", () => zoomBy(1.2)), ibtn(I.minus, "축소 (-)", () => zoomBy(1 / 1.2)), ibtn(I.fit, "화면 맞춤 (0)", fitView),
    ibtn(S.detail ? I.compact : I.detail, S.detail ? "간단히 보기" : "자세히 보기", toggleDetail, { id: "btn-detail" }));
  const mod = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";
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

function addAgent() {
  snapshot();
  const id = nextId(S.doc.agents, "A");
  const color = S.schema.colors[S.doc.agents.length % S.schema.colors.length];
  S.doc.agents.push({ id, name: "새 에이전트", color, role: "", intent: "", not_doing: "", exits: [{ name: "완료", when: "" }],
    tools: [], fixed: "", discretion: "", paths: "", notes: "", steps: [], edges: [] });
  placeNew(id);
  after("agent", id);
}
function addStep() {
  snapshot();
  const a = curAgent();
  const id = nextId(a.steps, "N");
  a.steps.push({ id, name: "새 단계", type: "처리", summary: "", intent: "", does: [], inputs: [], outputs: [], tools: [],
    done: [], fixed: "", discretion: "", example: "", cautions: "", on_fail: "" });
  placeNew(id);
  after("step", id);
}
function addExit() {
  snapshot();
  const a = curAgent();
  let n = a.exits.length + 1, name = `출력${n}`;
  while (a.exits.some((x) => x.name === name)) name = `출력${++n}`;
  a.exits.push({ name, when: "" });
  placeNew(`exit:${name}`);
  after("exit", name);
}
function placeNew(id) {
  // Below everything already on the canvas, so a new node never lands on top of another one.
  const box = cy.nodes().length ? cy.nodes().boundingBox() : null;
  const ext = cy.extent();
  layout(S.level)[id] = box ? { x: Math.round((box.x1 + box.x2) / 2), y: Math.round(box.y2 + 110) }
    : { x: Math.round((ext.x1 + ext.x2) / 2), y: Math.round((ext.y1 + ext.y2) / 2) };
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
  if (kind === "exit") return a.exits.find((x) => x.name === id);
  return null;
}
function removeSelected() {
  snapshot();
  const { kind, id } = S.sel, a = curAgent();
  if (kind === "agent") {
    S.doc.agents = S.doc.agents.filter((x) => x.id !== id);
    S.doc.links = S.doc.links.filter((l) => l.from !== id && l.to !== id);
    if (S.doc.layout) delete S.doc.layout[id];
  } else if (kind === "link") S.doc.links = S.doc.links.filter((x) => x.id !== id);
  else if (kind === "step") {
    a.steps = a.steps.filter((x) => x.id !== id);
    a.edges = a.edges.filter((e) => e.from !== id && e.to !== id);
  } else if (kind === "edge") a.edges = a.edges.filter((x) => x.id !== id);
  else if (kind === "exit") {
    a.exits = a.exits.filter((x) => x.name !== id);
    dropExit(a, id);
  } else return;
  delete layout(S.level)[cyId(kind, id)];
  S.sel = null;
  markDirty();
  renderAll();
}
function askRemove() {
  const label = { agent: "에이전트와 그 연결", step: "단계와 그 연결", edge: "연결", link: "에이전트 연결", exit: "출력과 그곳으로 가는 연결" }[S.sel.kind];
  modal("삭제", [el("p", {}, `${label}을(를) 지웁니다.`)], [["삭제", () => { closeModal(); removeSelected(); }, "danger"], ["취소", closeModal]]);
}
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (!typing && $("modal").hidden && S.doc && (e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z" || e.key === "y")) {
    e.preventDefault();
    if (e.shiftKey || e.key === "y") redo(); else undo();
    return;
  }
  if (!typing && $("modal").hidden && cy && S.doc && !e.metaKey && !e.ctrlKey) {
    if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomBy(1.2); return; }
    if (e.key === "-") { e.preventDefault(); zoomBy(1 / 1.2); return; }
    if (e.key === "0") { e.preventDefault(); fitView(); return; }
  }
  if (!typing && $("modal").hidden && (e.key === "Delete" || e.key === "Backspace") && S.sel && !["project", "glossary"].includes(S.sel.kind)) {
    e.preventDefault();
    askRemove();
  }
});

// ---------- document form ----------
function fieldsFor(kind) {
  if (kind === "glossary") return S.schema.project.filter((f) => f[0] === "glossary");
  if (kind === "project") return S.schema.project.filter((f) => f[0] !== "glossary");
  if (kind === "exit") return [["name", "출력 이름", "line", true, null], ["when", "언제", "text", true, null]];
  return S.schema[kind];
}
function titleFor(kind, obj) {
  const a = curAgent();
  if (kind === "project") return "프로젝트 문서";
  if (kind === "glossary") return "용어 사전";
  if (kind === "agent") return `${obj.id} · ${obj.name || ""}`;
  if (kind === "step") return `${a.id}-${obj.id} · ${obj.name || ""}`;
  if (kind === "edge") return `${a.id}-${obj.id} · ${nodeName(a, obj.from)} → ${nodeName(a, obj.to)}`;
  if (kind === "link") return `${obj.id} · ${nodeName(null, obj.from)} → ${nodeName(null, obj.to)}`;
  return `출력 · ${obj.name}`;
}
function previewTarget() {
  const { kind, id } = S.sel, a = curAgent();
  if (kind === "project") return "project";
  if (kind === "glossary") return "glossary";
  if (kind === "agent" || kind === "link") return id;
  if (kind === "exit") return a.id;
  return `${a.id}-${id}`;
}
function allNames() {
  const names = new Set(S.doc.glossary.map((g) => g.name));
  S.doc.inputs.forEach((r) => names.add(r.item));
  S.doc.agents.forEach((a) => a.steps.forEach((s) => [...s.inputs, ...s.outputs].forEach((n) => names.add(n))));
  return [...names].filter(Boolean).sort();
}

function renderDoc() {
  const panel = $("panel-doc");
  const obj = selected();
  if (!obj) {
    panel.replaceChildren(S.doc ? el("ul", { class: "hint-list muted" },
      el("li", {}, "카드나 연결선을 누르면 그 문서가 열립니다. 카드의 입력·과정·출력 줄을 누르면 그 칸으로 바로 갑니다. 빈 곳을 눌러도 마지막 문서는 그대로 남습니다."),
      el("li", {}, "에이전트 카드를 두 번 누르면 안의 단계로 들어갑니다."),
      el("li", {}, "카드 오른쪽의 점을 끌어 다른 카드에 놓으면 연결이 생깁니다. 출력 행의 점에서 끌면 그 출력의 연결이 되고, 이미 이어진 행이면 도착지가 바뀝니다. Esc로 취소합니다."),
      el("li", {}, "왼쪽 아래 버튼으로 카드를 간단히 또는 자세히 볼 수 있습니다."),
      el("li", {}, "확대·축소는 +와 -, 화면 맞춤은 0, 되돌리기는 ⌘Z(Windows는 Ctrl+Z)입니다.")) : "");
    return;
  }
  const kind = S.sel.kind;
  const head = el("div", { class: "doc-head" }, el("h2", { text: titleFor(kind, obj) }),
    el("div", { class: "row" },
      kind === "exit" ? null : el("button", { type: "button", "aria-pressed": S.preview ? "true" : "false", on: { click: togglePreview } }, "미리보기"),
      ["project", "glossary"].includes(kind) ? null : el("button", { type: "button", class: "danger", on: { click: askRemove } }, "삭제"),
      kind === "agent" ? el("button", { type: "button", on: { click: () => enter(obj.id) } }, "안으로") : null));
  if (S.preview) {
    const pre = el("pre", { class: "preview" }, "불러오는 중…");
    panel.replaceChildren(head, pre);
    flushSave().then(() => api("GET", `/api/projects/${S.pid}/preview?target=${encodeURIComponent(previewTarget())}`))
      .then(({ data }) => { pre.textContent = data.text || "(아직 생성할 내용이 없습니다)"; });
    return;
  }
  const kids = [head];
  if (kind === "edge" || kind === "link") {
    const a = curAgent();
    kids.push(el("div", { class: "route" }, `${nodeName(a, obj.from)} → ${nodeName(a, obj.to)}`));
  }
  kids.push(el("datalist", { id: "names" }, ...allNames().map((n) => el("option", { value: n }))));
  // Required fields first; optional ones fold away until they hold something (or the user opens them).
  const fields = fieldsFor(kind).filter((f) => !(kind === "link" && f[0] === "exit" && obj.from === "start"));
  const need = (f) => f[3] || ((kind === "edge" || kind === "link") && obj.kind === "cond" && ["name", "condition", "judge", "intent"].includes(f[0]));
  const main = fields.filter(need), rest = fields.filter((f) => !need(f));
  kids.push(el("div", { class: "group" }, ...main.map((f) => fieldEl(kind, obj, need(f) ? [...f.slice(0, 3), true, f[4]] : f))));
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
      requestAnimationFrame(() => { f.scrollIntoView({ block: "center" }); f.querySelector("input, textarea, select, button")?.focus({ preventScroll: true }); });
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

function changed(kind, obj, key) {
  markDirty();
  if (["name", "color", "kind", "exit", "process", "tools", "inputs", "outputs", "passes", "summary", "role", "type", "exits"].includes(key)) {
    if (kind === "exit") renameExit(obj);
    renderGraph();
    renderTop();
    const h = $("panel-doc").querySelector(".doc-head h2");
    if (h) h.textContent = titleFor(kind, obj);
  }
}
function renameExit(obj) {
  const a = curAgent();
  if (!a) return;
  moveExit(a, S.sel.id, obj.name);
  S.sel.id = obj.name;
}
// An exit's name is referenced by edges inside its agent and by the agent-level link leaving through it.
function moveExit(a, old, now) {
  if (old === now) return;
  a.edges.forEach((e) => { if (e.to === `exit:${old}`) e.to = `exit:${now}`; });
  S.doc.links.forEach((l) => { if (l.from === a.id && l.exit === old) l.exit = now; });
  const pos = S.doc.layout?.[a.id];
  if (pos?.[`exit:${old}`]) { pos[`exit:${now}`] = pos[`exit:${old}`]; delete pos[`exit:${old}`]; }
}
function dropExit(a, name) {
  a.edges = a.edges.filter((e) => e.to !== `exit:${name}`);
  S.doc.links = S.doc.links.filter((l) => !(l.from === a.id && l.exit === name));
  if (S.doc.layout?.[a.id]) delete S.doc.layout[a.id][`exit:${name}`];
}

function fieldEl(kind, obj, [key, label, type, required, extra]) {
  const id = `f-${key}`;
  const lab = el("label", { for: id }, label, required ? el("span", { class: "req" }, " *") : null);
  const set = (v) => { snapshot(`${kind}:${obj.id || obj.name || ""}:${key}`); obj[key] = v; changed(kind, obj, key); };
  let input;
  if (type === "line") input = el("input", { id, value: obj[key] ?? "", on: { input: (e) => set(e.target.value) } });
  else if (type === "text") input = el("textarea", { id, rows: 2, on: { input: (e) => { autosize(e.target); set(e.target.value); } } }, obj[key] ?? "");
  else if (type === "lines") {
    input = el("textarea", { id, rows: 2, on: { input: (e) => { autosize(e.target); set(e.target.value.split("\n").map((x) => x.trim()).filter(Boolean)); } } }, (obj[key] || []).join("\n"));
    lab.append(el("span", { class: "hint" }, " 한 줄에 하나"));
  } else if (type === "names") {
    input = el("input", { id, list: "names", value: (obj[key] || []).join(", "),
      on: { input: (e) => set(e.target.value.split(",").map((x) => x.trim()).filter(Boolean)) } });
    lab.append(el("span", { class: "hint" }, " 쉼표로 구분, 용어 사전 이름"));
  } else if (type === "select") {
    const names = kind === "edge" || kind === "link" ? (key === "kind" ? S.schema.edge_kinds : null) : null;
    const opts = Array.isArray(extra) ? extra : [];
    input = el("select", { id, on: { change: (e) => { set(e.target.value); renderDoc(); } } },
      el("option", { value: "" }, "선택"), ...opts.map((o) => el("option", { value: o, selected: obj[key] === o }, names ? names[o] : o)));
  } else if (type === "ref") {
    const pool = (curAgent() ? curAgent().edges : S.doc.links).filter((x) => x.id !== obj.id);
    input = el("select", { id, on: { change: (e) => set(e.target.value) } }, el("option", { value: "" }, "없음"),
      ...pool.map((x) => el("option", { value: x.id, selected: obj[key] === x.id }, `${x.id} ${x.name || ""}`)));
  } else if (type === "exit") {
    const from = agentOf(obj.from);
    input = el("select", { id, on: { change: (e) => set(e.target.value) } }, el("option", { value: "" }, "선택"),
      ...(from ? from.exits : []).map((x) => el("option", { value: x.name, selected: obj[key] === x.name }, x.name)));
  } else if (type === "color") {
    input = el("input", { id, type: "color", value: obj[key] || "#4C78A8", on: { input: (e) => set(e.target.value) } });
  } else if (type === "table" || type === "process" || type === "toolrefs" || type === "tools") {
    const editor = { table: () => tableEl(kind, obj, key, extra), process: () => processEl(kind, obj), toolrefs: () => toolRefsEl(kind, obj), tools: () => toolsEl(obj) }[type]();
    return el("div", { class: "field", id: `field-${key}` }, el("div", { class: "label" }, label, required ? el("span", { class: "req" }, " *") : null,
      type === "process" ? el("span", { class: "hint" }, " 이 단계 안의 흐름을 순서대로") : null,
      type === "tools" ? el("span", { class: "hint" }, " 단계와 과정이 여기서 골라 씁니다") : null), editor);
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
      const unit = el("select", { "aria-label": `${i + 1}번 단위`, on: { change: (e) => { touch(); r.unit = e.target.value; changed(kind, obj, "process"); } } },
        ...S.schema.process_units.map((u) => el("option", { value: u, selected: r.unit === u }, u)));
      const name = el("input", { value: r.name || "", placeholder: "이름 (예: minutes_loader.py, extract_decisions)", "aria-label": `${i + 1}번 이름`,
        on: { input: (e) => { touch(`process:${obj.id}:${i}:name`); r.name = e.target.value; changed(kind, obj, "process"); } } });
      const does = el("input", { value: r.does || "", placeholder: "하는 일 (쉬운 말)", "aria-label": `${i + 1}번 하는 일`,
        on: { input: (e) => { touch(`process:${obj.id}:${i}:does`); r.does = e.target.value; changed(kind, obj, "process"); } } });
      const tool = el("select", { "aria-label": `${i + 1}번 도구`, on: { change: (e) => { touch(); r.tool = e.target.value; changed(kind, obj, "process"); } } },
        el("option", { value: "" }, "도구 없음"), ...(S.doc.tools || []).map((t) => el("option", { value: t.id, selected: r.tool === t.id }, `${TOOL_ICON[t.kind] || ""} ${toolLabel(t)}`)));
      const move = (d) => { const j = i + d; if (j < 0 || j >= rows.length) return; touch(); [rows[i], rows[j]] = [rows[j], rows[i]]; changed(kind, obj, "process"); draw(); };
      const ctrls = el("div", { class: "row-ctrls" },
        el("button", { type: "button", class: "icon-s", "aria-label": `${i + 1}번 위로`, disabled: i === 0, on: { click: () => move(-1) } }, "↑"),
        el("button", { type: "button", class: "icon-s", "aria-label": `${i + 1}번 아래로`, disabled: i === rows.length - 1, on: { click: () => move(1) } }, "↓"),
        el("button", { type: "button", class: "icon-s", "aria-label": `${i + 1}번 삭제`, on: { click: () => { touch(); rows.splice(i, 1); changed(kind, obj, "process"); draw(); } } }, "×"));
      return [i ? el("div", { class: "process-arrow", "aria-hidden": "true" }, "↓") : null,
        el("div", { class: "process-item" }, el("span", { class: "num" }, String(i + 1)), unit, name, ctrls, does, tool)];
    });
    wrap.replaceChildren(...items.flat().filter(Boolean),
      el("button", { type: "button", class: "add", on: { click: () => { touch(); rows.push({ unit: "함수", name: "", does: "", tool: "" }); changed(kind, obj, "process"); draw(); wrap.querySelector(".process-item:last-of-type input")?.focus(); } } }, "+ 과정 추가"));
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
function newTool(done) {
  const kindSel = el("select", { "aria-label": "종류" }, ...S.schema.tool_kinds.map((k) => el("option", { value: k }, `${TOOL_ICON[k]} ${k}`)));
  const name = el("input", { placeholder: "이름 (예: 지도 MCP, 날씨 API, plan.py)", "aria-label": "이름" });
  const purpose = el("input", { placeholder: "용도", "aria-label": "용도" });
  const location = el("input", { placeholder: "위치·연결 (선택: 서버 이름, 파일 경로, 주소)", "aria-label": "위치·연결" });
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
        name, field("purpose", "용도"), field("location", "위치·연결 (서버, 파일 경로, 주소)"), field("alternative", "대안"),
        el("div", { class: "tool-used" }, used[t.id] ? `쓰는 곳: ${used[t.id].join(", ")}` : "아직 쓰는 단계가 없습니다"));
    }), el("button", { type: "button", class: "add", on: { click: () => { snapshot(); rows.push({ id: nextId(rows, "T"), kind: "기타", name: "", purpose: "", location: "", alternative: "" }); changed("project", obj, "tools"); draw(); } } }, "+ 도구 추가"));
  };
  draw();
  return wrap;
}

function tableEl(kind, obj, key, cols) {
  const rows = obj[key] = obj[key] || [];
  const exits = kind === "agent" && key === "exits";  // exit names are referenced by edges and links
  const wrap = el("div", { class: "grid-table", style: `--cols: ${cols.length}` });
  const draw = () => {
    wrap.replaceChildren(
      el("div", { class: "tr head" }, ...cols.map(([, l]) => el("span", { text: l })), el("span", { class: "x" })),
      ...rows.map((row, i) => el("div", { class: "tr" },
        ...cols.map(([c, l]) => el("textarea", { rows: 1, "aria-label": l, on: { input: (e) => {
          snapshot(`${kind}:${obj.id}:${key}:${i}:${c}`);
          const old = row[c];
          row[c] = e.target.value;
          if (exits && c === "name") moveExit(obj, old, row[c]);
          autosize(e.target);
          changed(kind, obj, exits && c === "name" ? "name" : key);
        } } }, row[c] ?? "")),
        el("button", { type: "button", class: "x", "aria-label": "행 삭제", on: { click: () => {
          snapshot();
          const [gone] = rows.splice(i, 1);
          if (exits) dropExit(obj, gone.name);
          changed(kind, obj, exits ? "name" : key);
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
  if (fresh.some((m) => m.role !== "user") && S.tab !== "chat") { S.unread = true; $("unread").hidden = false; }
  renderChat();
}
function renderChat() {
  const box = $("messages");
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
        el("button", { type: "button", class: "primary", on: { click: () => applyCard(m) } }, "적용"),
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
  await api("POST", `/api/projects/${S.pid}/messages`, { role: "user", text });
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
    if (plan.data.foreign.length) notes.push(el("p", { class: "muted" }, `이 도구가 만들지 않은 파일 ${plan.data.foreign.length}개는 건드리지 않습니다.`));
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
