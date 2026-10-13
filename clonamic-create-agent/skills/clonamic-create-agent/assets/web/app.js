"use strict";

// ---------- state ----------
const S = {
  schema: null, projects: [], pid: null, doc: null, version: 0, polished: false, exportPath: "", defaultPath: "",
  level: "agents", sel: null, dirty: false, saving: false, saveTimer: null, savedAt: 0,
  msgs: [], lastMsg: 0, tab: "doc", unread: false, aiSeen: null, draw: false, preview: false,
  undo: [], redo: [], lastKey: null, lastAt: 0, issues: [], fitNext: true,
};
const $ = (id) => document.getElementById(id);
let cy = null, eh = null;

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
    el("button", { class: "open", type: "button", title: p.name, on: { click: () => openProject(p.id) } }, p.name || "(이름 없음)"),
    el("button", { class: "more", type: "button", "aria-label": `${p.name} 메뉴`, on: { click: () => askDelete(p) } }, "⋯"))));
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

// ---------- graph ----------
const STYLE = () => {
  const css = getComputedStyle(document.documentElement);
  const v = (n) => css.getPropertyValue(n).trim();
  return [
    { selector: "node", style: {
      shape: "rectangle", label: "data(label)", "text-wrap": "wrap", "text-max-width": 1000, "text-valign": "center",
      "text-halign": "center", width: "data(w)", height: "data(h)", "font-size": 13, color: v("--text"),
      "background-color": v("--surface"), "border-width": 2, "border-color": "data(color)" } },
    { selector: "node.agent", style: { "background-color": "data(color)", color: "#ffffff", "border-width": 0, "font-weight": 600 } },
    { selector: "node.step", style: { "border-width": 3 } },
    { selector: "node.terminal", style: { shape: "round-rectangle", "background-color": v("--bg"), "border-color": v("--muted"), "font-size": 12 } },
    { selector: "node.exit", style: { shape: "ellipse", "border-style": "double", "border-width": 4 } },
    { selector: "edge", style: {
      width: 2, "curve-style": "bezier", "control-point-step-size": 150, "target-arrow-shape": "triangle", "line-color": v("--muted"),
      "target-arrow-color": v("--muted"), label: "data(label)", "font-size": 11, color: v("--text"), "text-wrap": "wrap",
      "text-max-width": 1000, "text-background-color": v("--canvas"), "text-background-opacity": 1,
      "text-background-padding": 3, "text-background-shape": "roundrectangle", "z-index": 2 } },
    { selector: "edge.cond", style: { "line-style": "dashed" } },
    { selector: ":selected", style: { "border-color": v("--accent"), "line-color": v("--accent"), "target-arrow-color": v("--accent"), "border-width": 4 } },
    { selector: ".hl", style: { "border-color": v("--hl"), "line-color": v("--hl"), "target-arrow-color": v("--hl"), "border-width": 5, width: 4 } },
    { selector: ".eh-handle", style: { "background-color": v("--accent"), width: 12, height: 12, shape: "ellipse", "border-width": 0 } },
    { selector: ".eh-ghost-edge, edge.eh-preview", style: { "line-color": v("--accent"), "target-arrow-color": v("--accent") } },
  ];
};

function elements() {
  const items = [];
  // Fixed sizes from measured, pre-wrapped labels (Cytoscape's width "label" marked some nodes hidden).
  const node = (id, label, cls, color) => {
    const bold = cls === "agent" ? "600 " : "";
    const t = wrapText(label, 170, `${bold}13px ${FONT}`);
    items.push({ group: "nodes", data: { id, label: t.text, color: color || "#8a93a3",
      w: Math.max(64, Math.ceil(t.width) + 30), h: t.count * 17 + 24 }, classes: cls });
  };
  const edge = (id, src, dst, label, cls) => items.push({ group: "edges",
    data: { id, source: src, target: dst, label: wrapText(label, 130, `11px ${FONT}`).text }, classes: cls });
  const a = curAgent();
  if (!a) {
    node("start", "시작", "terminal");
    S.doc.agents.forEach((x) => node(x.id, `${x.id}\n${x.name || ""}`, "agent", colorOf(x)));
    node("end", "끝", "terminal");
    S.doc.links.forEach((x) => edge(`link:${x.id}`, x.from, x.to, x.id + (x.kind === "cond" || x.exit ? `: ${x.name || x.exit || ""}` : ""), x.kind));
  } else {
    node("start", "시작", "terminal");
    a.steps.forEach((s) => node(s.id, `${s.id}\n${s.name || ""}`, "step", colorOf(a)));
    a.exits.forEach((x) => node(`exit:${x.name}`, x.name, "terminal exit", colorOf(a)));
    a.edges.forEach((e) => edge(`edge:${e.id}`, e.from, e.to, e.id + (e.kind === "cond" ? `: ${e.name || ""}` : ""), e.kind));
  }
  const ids = new Set(items.filter((i) => i.group === "nodes").map((i) => i.data.id));
  return items.filter((i) => i.group === "nodes" || (ids.has(i.data.source) && ids.has(i.data.target)));
}

function renderGraph() {
  if (!S.doc) { if (cy) cy.elements().remove(); return; }
  if (!cy) {
    cy = cytoscape({ container: $("cy"), style: STYLE(), wheelSensitivity: 0.3, boxSelectionEnabled: false, minZoom: 0.2, maxZoom: 2.5 });
    cy.on("tap", (e) => {
      if (e.target === cy) { S.sel = null; renderDoc(); setTab("chat"); return; }
      const id = e.target.id();
      if (e.target.isEdge()) select(curAgent() ? "edge" : "link", id.split(":")[1]);
      else if (id === "start" || id === "end") return;
      else if (id.startsWith("exit:")) select("exit", id.slice(5));
      else select(curAgent() ? "step" : "agent", id);
    });
    cy.on("dbltap", "node.agent", (e) => enter(e.target.id()));
    cy.on("dragfree", "node", () => { snapshot(); savePositions(); markDirty(); });
    eh = cy.edgehandles({ canConnect: canConnect, edgeParams: () => ({}), hoverDelay: 150, snap: true, noEdgeEventsInDraw: true });
    cy.on("ehcomplete", (e, src, dst, added) => { added.remove(); connect(src.id(), dst.id()); });
  }
  const pos = layout(S.level);
  cy.elements().remove();
  cy.add(elements());
  let missing = false;
  cy.nodes().forEach((n) => { if (pos[n.id()]) n.position(pos[n.id()]); else missing = true; });
  if (missing) arrange(false);
  else if (S.fitNext) cy.fit(undefined, 40);
  S.fitNext = false;
  if (S.sel) cy.$id(cyId(S.sel.kind, S.sel.id)).select();
}

function arrange(save = true) {
  if (save) snapshot();
  const run = cy.layout({ name: "dagre", rankDir: "TB", nodeSep: 70, rankSep: 90, edgeSep: 30, fit: true, padding: 40 });
  run.one("layoutstop", () => { savePositions(); markDirty(); });
  run.run();
}
function savePositions() {
  const pos = layout(S.level);
  for (const k of Object.keys(pos)) delete pos[k];
  cy.nodes().forEach((n) => { const p = n.position(); pos[n.id()] = { x: Math.round(p.x), y: Math.round(p.y) }; });
}
function cyId(kind, id) {
  if (kind === "edge") return `edge:${id}`;
  if (kind === "link") return `link:${id}`;
  if (kind === "exit") return `exit:${id}`;
  return id;
}

function canConnect(src, dst) {
  const s = src.id(), d = dst.id();
  if (s === d || d === "start" || s === "end" || s.startsWith("exit:")) return false;
  return true;
}

function connect(src, dst) {
  snapshot();
  const a = curAgent();
  if (!a) {
    let exit = "";
    if (src !== "start") {
      const from = agentOf(src);
      const used = new Set(S.doc.links.filter((l) => l.from === src).map((l) => l.exit));
      const free = from.exits.find((x) => !used.has(x.name));
      if (free) exit = free.name;
      else {
        exit = from.exits.length ? `출구${from.exits.length + 1}` : "완료";
        from.exits.push({ name: exit, when: "" });
      }
    }
    const link = { id: nextId(S.doc.links, "L"), from: src, to: dst, kind: "always", exit, name: "", passes: [] };
    S.doc.links.push(link);
    after("link", link.id);
  } else {
    const e = { id: nextId(a.edges, "L"), from: src, to: dst, kind: "always", name: "", passes: [] };
    a.edges.push(e);
    after("edge", e.id);
  }
}
function after(kind, id) {
  markDirty();
  renderGraph();
  select(kind, id);
  const n = cy.$id(cyId(kind, id));
  if (n.length && n.isNode()) {
    const p = n.position(), e = cy.extent();
    if (p.x < e.x1 || p.x > e.x2 || p.y < e.y1 || p.y > e.y2) cy.fit(undefined, 40);  // keep the rest in view too
  }
}

function enter(aid) { S.level = aid; S.sel = null; S.fitNext = true; renderAll(); }
function back() { S.level = "agents"; S.sel = null; S.fitNext = true; renderAll(); }

// ---------- toolbar / crumb ----------
function renderTop() {
  const has = !!S.doc;
  $("empty").hidden = has;
  $("project-name").disabled = !has;
  $("project-name").value = has ? S.doc.name || "" : "";
  const crumb = $("crumb");
  crumb.replaceChildren();
  const tools = $("tools");
  tools.replaceChildren();
  $("actions").replaceChildren();
  if (!has) return;
  const a = curAgent();
  crumb.append(a ? el("button", { type: "button", on: { click: back } }, S.doc.name || "프로젝트")
    : el("span", { text: `${S.doc.name || "프로젝트"} · 에이전트 지도` }));
  if (a) crumb.append(el("span", { text: "›" }), el("span", { text: `${a.id} ${a.name || ""}` }));
  const btn = (label, fn, extra = {}) => tools.append(el("button", { type: "button", on: { click: fn }, ...extra }, label));
  const mod = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";
  tools.append(el("button", { type: "button", id: "btn-undo", class: "icon", title: `되돌리기 (${mod}Z)`, "aria-label": "되돌리기", on: { click: undo } }, icon("M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3")),
    el("button", { type: "button", id: "btn-redo", class: "icon", title: `다시 실행 (${mod}Shift+Z)`, "aria-label": "다시 실행", on: { click: redo } }, icon("m15 14 5-5-5-5M20 9H10a6 6 0 0 0 0 12h3")));
  if (!a) btn("+ 에이전트", addAgent, { class: "gap" });
  else { btn("+ 단계", addStep, { class: "gap" }); btn("+ 출구", addExit); }
  btn("연결 그리기", toggleDraw, { "aria-pressed": S.draw ? "true" : "false", title: "켜고 노드에서 노드로 끌어 연결합니다. Esc로 끕니다" });
  btn("자동 정렬", () => arrange(true), { class: "gap", title: "배치를 새로 계산합니다" });
  btn("화면 맞춤", () => cy.fit(undefined, 40), { title: "배치는 그대로 두고 전체가 보이게 합니다" });
  btn("프로젝트 문서", () => select("project", ""), { class: "gap" });
  btn("용어 사전", () => select("glossary", ""));
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
function toggleDraw() {
  S.draw = !S.draw;
  if (S.draw) eh.enableDrawMode(); else eh.disableDrawMode();
  renderTop();
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
  let n = a.exits.length + 1, name = `출구${n}`;
  while (a.exits.some((x) => x.name === name)) name = `출구${++n}`;
  a.exits.push({ name, when: "" });
  placeNew(`exit:${name}`);
  after("exit", name);
}
function placeNew(id) {
  // Below everything already on the canvas, so a new node never lands on top of another one.
  const box = cy.nodes().length ? cy.nodes().boundingBox() : null;
  const ext = cy.extent();
  layout(S.level)[id] = box ? { x: Math.round((box.x1 + box.x2) / 2), y: Math.round(box.y2 + 80) }
    : { x: Math.round((ext.x1 + ext.x2) / 2), y: Math.round((ext.y1 + ext.y2) / 2) };
}

// ---------- selection & delete ----------
function select(kind, id) {
  S.sel = { kind, id };
  S.preview = false;
  if (cy) { cy.elements().unselect(); if (["agent", "step", "edge", "link", "exit"].includes(kind)) cy.$id(cyId(kind, id)).select(); }
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
  const label = { agent: "에이전트와 그 연결", step: "단계와 그 연결", edge: "연결", link: "에이전트 연결", exit: "출구와 그곳으로 가는 연결" }[S.sel.kind];
  modal("삭제", [el("p", {}, `${label}을(를) 지웁니다.`)], [["삭제", () => { closeModal(); removeSelected(); }, "danger"], ["취소", closeModal]]);
}
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (!typing && $("modal").hidden && S.doc && (e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z" || e.key === "y")) {
    e.preventDefault();
    if (e.shiftKey || e.key === "y") redo(); else undo();
    return;
  }
  if (!typing && $("modal").hidden && e.key === "Escape" && S.draw) { toggleDraw(); return; }
  if (!typing && $("modal").hidden && (e.key === "Delete" || e.key === "Backspace") && S.sel && !["project", "glossary"].includes(S.sel.kind)) {
    e.preventDefault();
    askRemove();
  }
});

// ---------- document form ----------
function fieldsFor(kind) {
  if (kind === "glossary") return S.schema.project.filter((f) => f[0] === "glossary");
  if (kind === "project") return S.schema.project.filter((f) => f[0] !== "glossary");
  if (kind === "exit") return [["name", "출구 이름", "line", true, null], ["when", "언제", "text", true, null]];
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
  return `출구 · ${obj.name}`;
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
      el("li", {}, "노드나 연결을 누르면 그 문서가 열립니다."),
      el("li", {}, "에이전트를 두 번 누르면 안의 단계로 들어갑니다."),
      el("li", {}, "「연결 그리기」를 켜고 노드에서 노드로 끌면 연결이 생깁니다. Esc로 끕니다."),
      el("li", {}, "「프로젝트 문서」와「용어 사전」은 위 버튼으로 엽니다."),
      el("li", {}, "되돌리기는 ⌘Z(Windows는 Ctrl+Z), 다시 실행은 ⇧⌘Z입니다.")) : "");
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
  const datalist = el("datalist", { id: "names" }, ...allNames().map((n) => el("option", { value: n })));
  kids.push(datalist);
  for (const field of fieldsFor(kind)) {
    if (kind === "link" && field[0] === "exit" && obj.from === "start") continue;
    kids.push(fieldEl(kind, obj, field));
  }
  panel.replaceChildren(...kids);
  fitAreas();
}
function fitAreas() { requestAnimationFrame(() => $("panel-doc").querySelectorAll("textarea").forEach(autosize)); }
function autosize(t) { t.style.height = "auto"; t.style.height = `${t.scrollHeight + 2}px`; }
function togglePreview() { S.preview = !S.preview; renderDoc(); }

function changed(kind, obj, key) {
  markDirty();
  if (["name", "color", "kind", "exit"].includes(key)) {
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
  } else if (type === "table") {
    return el("div", { class: "field" }, el("div", { class: "label" }, label, required ? el("span", { class: "req" }, " *") : null),
      tableEl(kind, obj, key, extra));
  }
  return el("div", { class: "field" }, lab, input);
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
    if (id) cy.$id(id)[on ? "addClass" : "removeClass"]("hl");
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
  if (cy) cy.resize();
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
