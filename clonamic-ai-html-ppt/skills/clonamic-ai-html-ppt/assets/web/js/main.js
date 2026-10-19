// Boot: schema → deck (from location.hash) → store → renderer → selection/ctx → panels → SSE.

import { loadSchema } from "./schema.js";
import { api, connectEvents, assetUrl } from "./api.js";
import { createStore } from "./state.js";
import { createRenderer } from "./render.js";
import { createViewport } from "./viewport.js";
import { initSelect, fixGroups, previews, selectionBounds, boxOfPage, pageAt, requestDraw, clearMeasureCache } from "./select.js";
import { createSnapper } from "./snap.js";
import { initTools, renderFramePresets, trackPointer } from "./tools.js";
import { initShortcuts } from "./shortcuts.js";
import { startPresent, bootPresenter, openPresenter } from "./present.js";
import { mountDesignPanel } from "./panels/design.js";
import { mountLayers } from "./panels/layers.js";
import { mountPages, presetSize } from "./panels/pages.js";
import { mountAI } from "./panels/ai.js";
import { initFocus } from "./focus.js";
import { openExport } from "./panels/export.js";
import { el, $, toast, modal, menu, store as ls, ICON, PRESET_LABEL, keyLabel } from "./ui.js";

const FLAGS_KEY = "ppt-flags";

function makeSelection(store) {
  let ids = [];
  const fns = new Set();
  const emit = () => { for (const f of [...fns]) { try { f(ids); } catch (e) { console.error(e); } } };
  const sel = {
    get ids() { return ids; },
    set(list) {
      const next = [...new Set(list || [])].filter((id) => store.nodes.has(id));
      if (next.length === ids.length && next.every((x, i) => x === ids[i])) return;
      ids = next; emit();
    },
    add(id) { if (!ids.includes(id)) sel.set([...ids, id]); },
    toggle(id) { sel.set(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]); },
    clear() { sel.set([]); },
    on(fn) { fns.add(fn); return () => fns.delete(fn); },
  };
  store.subscribe((_c, d) => { if (d.length && ids.some((i) => d.includes(i))) sel.set(ids.filter((i) => !d.includes(i))); });
  return sel;
}

async function boot() {
  await loadSchema();
  const params = new URLSearchParams(location.search);
  const raw = decodeURIComponent(location.hash.slice(1));
  const deckId = /^\d+$/.test(raw) ? Number(raw) : null;
  window.addEventListener("hashchange", () => location.reload());
  if (deckId == null) return showPicker();
  const r = await api.getDeck(deckId);
  if (!r.ok) { if (r.status === 404) toast("덱을 찾을 수 없습니다."); else toast(r.data?.error || "서버에 연결할 수 없습니다.", { kind: "error" }); return showPicker(); }
  const store = createStore(api, r.data, deckId);
  if (params.has("presenter")) {
    const conn = connectEvents(deckId, { onOps: (ev) => store.receive(ev), onReset: () => store.resync() }, () => store.deck.seq);
    store.attachEvents(conn);
    bootPresenter(store, { deckId, assetUrl });
    return;
  }
  editor(store, deckId);
}

function editor(store, deckId) {
  document.body.classList.add("has-deck");
  const container = $("#canvas"), world = $("#world"), docRoot = $("#doc");
  const flags = { rulers: false, pixelGrid: true, snapPixel: true, guides: true, outline: false, hideUI: false, hideSidebars: false };
  try { Object.assign(flags, JSON.parse(ls(FLAGS_KEY) || "{}")); } catch (_) { /* defaults */ }
  flags.hideUI = false;

  const renderer = createRenderer({ root: docRoot, mode: "edit", assetUrl });
  const before = store.subscriberCount;
  renderer.mount(store);
  if (store.subscriberCount === before) store.subscribe((c, d) => renderer.update(c, d));   // renderer did not self-subscribe
  const selection = makeSelection(store);

  let curPage = store.childIds(null)[0] || null;
  const pageFns = new Set();
  const ctx = {
    store, selection, renderer, api, deckId, assetUrl, container, docRoot, flags,
    overlay: $("#overlay"), labels: $("#labels"), aiLayer: $("#ai-layer"),
    tool: "move", textEdit: null,
    commit: (ops, label) => store.commit(fixGroups(ops), label),
    preview(id, props) {
      previews.set(id, { ...(previews.get(id) || {}), ...props });
      try { renderer.setPreview(id, props); } catch (e) { console.error(e); }
      clearMeasureCache();
      requestDraw();
    },
    clearPreview(id) {
      previews.delete(id);
      try { renderer.clearPreview(id); } catch (e) { console.error(e); }
      clearMeasureCache();
      requestDraw();
    },
    uploadAsset: (file) => api.uploadAsset(file),
    currentPage: () => (curPage && store.get(curPage) ? curPage : (curPage = store.childIds(null)[0] || null)),
    setCurrentPage(id) { if (id && id !== curPage && store.get(id)) { curPage = id; pageFns.forEach((f) => { try { f(id); } catch (e) { console.error(e); } }); viewport?.refresh(); } },
    onPageChange(fn) { pageFns.add(fn); return () => pageFns.delete(fn); },
    boxOfPage, selectionBounds,
    applyFlags() {
      renderer.setShowGuides?.(flags.guides);
      renderer.setOutlineMode?.(flags.outline);
      document.body.classList.toggle("ui-hidden", flags.hideUI);
      document.body.classList.toggle("sidebars-hidden", flags.hideSidebars);
      viewport.refresh();
      requestDraw();
      const { hideUI, ...keep } = flags;
      void hideUI;
      ls(FLAGS_KEY, JSON.stringify(keep));
      paintZoom();
    },
    present: (from) => startPresent(ctx, from),
    openExport: () => openExport(ctx),
    showLeftTab, showRightTab,
  };
  let viewport = null;
  viewport = createViewport(ctx, { container, world, rulerTop: $("#ruler-top"), rulerLeft: $("#ruler-left"), rulerCorner: $("#ruler-corner"), grid: $("#pixel-grid") });
  ctx.viewport = viewport;
  ctx.snapper = createSnapper(ctx);
  const sel = initSelect(ctx);
  ctx.select = sel;
  ctx.tools = initTools(ctx, { toolbar: $("#toolbar") });
  ctx.shortcuts = initShortcuts(ctx);

  // pointer routing: pan → creation tools → selection/transform
  container.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".no-canvas")) return;
    if (document.activeElement && document.activeElement !== container && !e.target.closest("[contenteditable]")) {
      if (!(ctx.textEdit && renderer.elementOf(ctx.textEdit.id)?.contains(e.target))) container.focus({ preventScroll: true });
    }
    if (viewport.handlePointerDown(e)) return;
    if (ctx.tools.handlePointerDown(e)) return;
    sel.handlePointerDown(e);
  });
  container.addEventListener("pointermove", trackPointer, { passive: true });

  // current page follows the selection, or the page under the viewport center
  selection.on((ids) => { const pg = ids.length ? store.pageIdOf(ids[0]) : null; if (pg) ctx.setCurrentPage(pg); });
  let settle = 0;
  viewport.onChange(() => {
    paintZoom();
    clearTimeout(settle);
    settle = setTimeout(() => { if (!selection.ids.length) { const pg = pageAt(viewport.center()); if (pg) ctx.setCurrentPage(pg); } }, 300);
  });

  // ---- panels ----
  ctx.pages = mountPages($("#panel-pages"), ctx);
  const layers = mountLayers($("#panel-layers"), ctx);
  ctx.layers = { rename: (id) => { showLeftTab("layers"); return layers.rename(id); }, reveal: layers.reveal };
  try { mountDesignPanel($("#panel-design"), ctx); } catch (e) { console.error(e); $("#panel-design").textContent = "디자인 패널을 불러오지 못했습니다."; }
  ctx.focus = initFocus(ctx, { layer: $("#pins-layer") });
  const ai = mountAI($("#panel-ai"), ctx, { focus: ctx.focus, onUnread: () => { if ($("#tab-ai").getAttribute("aria-selected") !== "true") $("#ai-dot").hidden = false; } });
  ctx.ai = ai;
  ctx.showFramePresets = (on) => {
    const fp = $("#frame-presets");
    fp.hidden = !on;
    if (on) { renderFramePresets(fp); showRightTab("design"); }
  };

  // ---- top bar ----
  const nameInput = $("#deck-name");
  const paintName = () => { if (document.activeElement !== nameInput) nameInput.value = store.deck.name || ""; document.title = `${store.deck.name || "프레젠테이션"} — AI HTML PPT`; };
  paintName();
  store.on("deck", paintName);
  nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) nameInput.blur(); if (e.key === "Escape") { nameInput.value = store.deck.name || ""; nameInput.blur(); } });
  nameInput.addEventListener("change", () => {
    const v = nameInput.value.trim().slice(0, 200);
    if (v && v !== store.deck.name) store.commit([{ op: "deck", props: { name: v } }], "덱 이름 변경");
    else nameInput.value = store.deck.name || "";
  });
  const status = $("#save-status");
  let sseState = "open";
  const paintStatus = () => {
    const s = store.status;
    const off = s === "offline" || sseState === "closed";
    status.dataset.state = off ? "offline" : s;
    status.textContent = off ? "오프라인 — 다시 연결 중" : s === "saving" ? "저장 중…" : s === "error" ? "저장 실패 — 되돌림" : "저장됨";
  };
  store.on("status", paintStatus);
  store.on("error", (msg) => toast(msg, { kind: "error" }));
  paintStatus();
  window.addEventListener("beforeunload", (e) => { if (store.pending) { e.preventDefault(); e.returnValue = ""; } });

  const zoomBtn = $("#zoom-btn");
  function paintZoom() { const z = viewport.zoom * 100, t = `${z >= 10 ? Math.round(z) : z.toFixed(1)}%`; if (zoomBtn.textContent !== t) zoomBtn.textContent = t; }
  zoomBtn.addEventListener("click", () => {
    const run = (id) => () => ctx.shortcuts.runAction(id);
    const k = (id) => { const a = ctx.shortcuts.actions.find((x) => x.id === id); return a?.keys[0] ? keyLabel(a.keys[0]) : ""; };
    menu(zoomBtn, [
      { label: "확대", hint: k("zoomIn"), run: run("zoomIn") }, { label: "축소", hint: k("zoomOut"), run: run("zoomOut") },
      { label: "100%로 보기", hint: k("zoom100"), run: run("zoom100") }, { label: "전체 보기", hint: k("zoomFit"), run: run("zoomFit") },
      { label: "선택 영역 보기", hint: k("zoomSel"), run: run("zoomSel") }, { sep: true },
      { label: "눈금자", hint: k("rulers"), checked: flags.rulers, run: run("rulers") },
      { label: "픽셀 그리드", hint: k("pixelGrid"), checked: flags.pixelGrid, run: run("pixelGrid") },
      { label: "픽셀 그리드에 맞추기", hint: k("snapPixel"), checked: flags.snapPixel, run: run("snapPixel") },
      { label: "레이아웃 가이드", hint: k("guides"), checked: flags.guides, run: run("guides") },
      { label: "윤곽 보기", hint: k("outline"), checked: flags.outline, run: run("outline") },
      { sep: true }, { label: "키보드 단축키", hint: k("help"), run: run("help") },
    ], { align: "end" });
  });
  $("#present-btn").addEventListener("click", () => ctx.present(ctx.currentPage()));
  $("#present-more").addEventListener("click", (e) => menu(e.currentTarget, [
    { label: "현재 페이지부터", hint: keyLabel("Mod+Enter"), run: () => ctx.present(ctx.currentPage()) },
    { label: "처음부터", run: () => ctx.present(null) },
    { label: "발표자 보기 열기", run: () => openPresenter(ctx) },
  ], { align: "end" }));
  $("#export-btn").addEventListener("click", () => openExport(ctx));
  window.addEventListener("ppt:export-pdf", (e) => openExport(ctx, { pages: e.detail?.pages }));
  $("#deck-menu").addEventListener("click", (e) => deckMenu(e.currentTarget, store));
  mountDeckRail(store);

  // ---- tabs ----
  function showLeftTab(which) {
    for (const t of ["pages", "layers"]) { $(`#tab-${t}`).setAttribute("aria-selected", String(t === which)); $(`#panel-${t}`).hidden = t !== which; }
    ls("ppt-left-tab", which);
    if (which === "layers") layers.reveal(selection.ids.length ? selection.ids : []);
  }
  function showRightTab(which) {
    for (const t of ["ai", "design"]) { $(`#tab-${t}`).setAttribute("aria-selected", String(t === which)); $(`#panel-${t}-wrap`).hidden = t !== which; }
    ls("ppt-right-tab", which);
    if (which === "ai") $("#ai-dot").hidden = true;
  }
  $("#tab-pages").addEventListener("click", () => showLeftTab("pages"));
  $("#tab-layers").addEventListener("click", () => showLeftTab("layers"));
  $("#tab-design").addEventListener("click", () => showRightTab("design"));
  $("#tab-ai").addEventListener("click", () => { showRightTab("ai"); ai.focus(); });
  showRightTab(ls("ppt-right-tab") === "design" ? "design" : "ai");
  showLeftTab(ls("ppt-left-tab") === "layers" ? "layers" : "pages");

  // ---- events ----
  const conn = connectEvents(deckId, {
    onOps: (ev) => store.receive(ev),
    onMsg: (m) => ai.receive(m),
    onAI: (s) => ai.onAI(s),
    onFocus: (d) => ctx.focus.set(d?.pins),
    onReset: () => store.resync(),
    onClosing: () => { sseState = "closed"; paintStatus(); modal({ title: "서버가 종료되었습니다", body: el("p", {}, "편집기 서버가 멈췄습니다. 서버를 다시 시작한 뒤 이 페이지를 새로 고치세요.") }); },
    onState: (s) => { sseState = s === "open" ? "open" : "error"; if (s === "open") paintStatus(); else setTimeout(() => { if (sseState === "error") { sseState = "closed"; paintStatus(); } }, 3000); },
  }, () => store.deck.seq);
  store.attachEvents(conn);

  ctx.applyFlags();
  if (!viewport.restore()) requestAnimationFrame(() => viewport.fitAll(false));
  paintZoom();
  container.focus({ preventScroll: true });
  if (session("ppt-rename") === String(deckId)) { session("ppt-rename", null); nameInput.focus(); nameInput.select(); }   // "이름 바꾸기" from the deck rail
  window.__ppt = ctx;   // debugging handle
}

// ---- decks ----
function session(key, value) {
  try {
    if (value === undefined) return sessionStorage.getItem(key);
    if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value);
  } catch (_) { /* storage blocked */ }
  return null;
}
function ago(sec) {
  const d = Date.now() / 1000 - sec;
  if (d < 60) return "방금 수정";
  if (d < 3600) return `${Math.floor(d / 60)}분 전 수정`;
  if (d < 86400) return `${Math.floor(d / 3600)}시간 전 수정`;
  const t = new Date(sec * 1000);
  return `${t.getMonth() + 1}월 ${t.getDate()}일 수정`;
}
// Left rail: one entry per deck (one PPT topic), most recently edited first.
function mountDeckRail(store) {
  const root = $("#deck-rail");
  const list = el("ul", { id: "deck-list-rail", class: "rail-list" });
  const toggle = el("button", { type: "button", class: "rail-toggle", "aria-controls": "deck-list-rail", html: ICON.chevron },
    el("span", { class: "panel-title" }, "프레젠테이션"));
  const setOpen = (open) => { toggle.setAttribute("aria-expanded", String(open)); list.hidden = !open; ls("ppt-deck-rail", open ? null : "closed"); };
  toggle.addEventListener("click", () => setOpen(list.hidden));
  root.append(el("div", { class: "panel-head" }, toggle,
    el("button", { type: "button", class: "icon-btn sm", "aria-label": "새 프레젠테이션", title: "새 프레젠테이션", html: ICON.plus, on: { click: newDeckDialog } })), list);
  setOpen(ls("ppt-deck-rail") !== "closed");
  async function paint() {
    const r = await api.listDecks();
    if (!r.ok || !Array.isArray(r.data)) return;
    list.replaceChildren(...r.data.map((d) => {
      const cur = d.id === store.deck.id;
      const name = cur ? store.deck.name : d.name;
      const more = (e) => menu(e.currentTarget, [
        { label: "이름 바꾸기", run: () => { if (cur) { $("#deck-name").focus(); $("#deck-name").select(); } else { session("ppt-rename", String(d.id)); location.hash = String(d.id); } } },
        { label: "삭제…", danger: true, run: () => deleteDeckDialog({ id: d.id, name }, store.deck.id, paint) },
      ], { align: "end" });
      return el("li", { class: cur ? "current" : null },
        el("button", { type: "button", class: "open", title: name, "aria-current": cur ? "true" : null, on: { click: () => { if (!cur) location.hash = String(d.id); } } },
          el("span", { class: "name" }, name || `덱 ${d.id}`), el("span", { class: "dim" }, `${d.pages ?? 0}쪽 · ${ago(d.updated)}`)),
        el("button", { type: "button", class: "icon-btn sm", "aria-label": `${name} 메뉴`, title: "메뉴", html: ICON.more, on: { click: more } }));
    }));
  }
  paint();
  store.on("deck", paint);
  window.addEventListener("focus", paint);   // decks made in another tab or by the AI
}
async function deckMenu(anchor, store) {
  const r = await api.listDecks();
  const decks = r.ok && Array.isArray(r.data) ? r.data : [];
  menu(anchor, [
    { header: "덱" },
    ...decks.slice(0, 30).map((d) => ({ label: d.name || `덱 ${d.id}`, hint: `${d.pages ?? ""}쪽`, checked: store && d.id === store.deck.id, run: () => { location.hash = String(d.id); } })),
    { sep: true },
    { label: "새 덱…", run: () => newDeckDialog() },
    ...(store ? [
      { label: "이름 바꾸기", run: () => { $("#deck-name").focus(); $("#deck-name").select(); } },
      { label: "덱 삭제…", danger: true, run: () => deleteDeckDialog(store.deck) },
    ] : []),
  ]);
}
function newDeckDialog() {
  const name = el("input", { value: "새 프레젠테이션", "aria-label": "덱 이름", autofocus: true });
  const preset = el("select", { "aria-label": "첫 페이지 크기" }, ...["SLIDE_16_9", "SLIDE_4_3", "A4", "A3", "LETTER"].map((k) => el("option", { value: k }, `${PRESET_LABEL[k]} (${presetSize(k, k.startsWith("SLIDE") ? "landscape" : "portrait").join("×")})`)));
  modal({ title: "새 덱", body: el("div", { class: "form" }, el("label", {}, "이름", name), el("label", {}, "첫 페이지", preset)),
    actions: [{ label: "취소" }, { label: "만들기", kind: "primary", run: async () => {
      const r = await api.createDeck(name.value.trim().slice(0, 200) || "새 프레젠테이션", preset.value);
      if (!r.ok) { toast(r.data?.error || "만들지 못했습니다.", { kind: "error" }); return false; }
      location.hash = String(r.data.id);
    } }] });
}
// current/onDone: deleting a deck other than the open one only refreshes the list.
function deleteDeckDialog(deck, current = deck.id, onDone = null) {
  const input = el("input", { "aria-label": "덱 이름 입력", autofocus: true, placeholder: deck.name });
  let btn = null;
  input.addEventListener("input", () => { btn.disabled = input.value !== deck.name; });
  modal({ title: "덱 삭제", body: el("div", { class: "form" }, el("p", {}, `“${deck.name}” 덱을 지웁니다. 되돌릴 수 없습니다. 지우려면 덱 이름을 그대로 입력하세요.`), input),
    actions: [{ label: "취소" }, { label: "삭제", kind: "danger", disabled: true, ref: (b) => { btn = b; }, run: async () => {
      if (input.value !== deck.name) return false;
      const r = await api.deleteDeck(deck.id);
      if (!r.ok) { toast(r.data?.error || "지우지 못했습니다.", { kind: "error" }); return false; }
      if (deck.id !== current) { onDone?.(); return; }
      const list = await api.listDecks();
      const next = list.ok && list.data.find((d) => d.id !== deck.id);
      location.hash = next ? String(next.id) : "";
      if (!next) location.reload();
    } }] });
}
async function showPicker() {
  document.body.classList.remove("has-deck");
  const r = await api.listDecks();
  if (!r.ok) {
    $("#picker").hidden = false;
    $("#picker").replaceChildren(el("div", { class: "picker-card" }, el("h1", {}, "서버에 연결할 수 없습니다"), el("p", {}, "편집기 서버를 시작한 뒤 새로 고치세요."),
      el("button", { type: "button", class: "primary", on: { click: () => location.reload() } }, "새로 고침")));
    return;
  }
  const decks = r.data || [];
  if (!decks.length) {
    const c = await api.createDeck("새 프레젠테이션", "SLIDE_16_9");
    if (c.ok) { location.hash = String(c.data.id); return; }
  }
  $("#picker").hidden = false;
  $("#picker").replaceChildren(el("div", { class: "picker-card" },
    el("h1", {}, "프레젠테이션"),
    el("ul", { class: "deck-list" }, ...decks.map((d) => el("li", {}, el("button", { type: "button", on: { click: () => { location.hash = String(d.id); } } },
      el("span", { class: "deck-name" }, d.name || `덱 ${d.id}`), el("span", { class: "dim" }, `${d.pages ?? 0}쪽 · ${fmtDate(d.updated)}`))))),
    el("button", { type: "button", class: "primary", html: `${ICON.plus}<span>새 프레젠테이션</span>`, on: { click: newDeckDialog } })));
}
function fmtDate(v) {
  if (v == null) return "";
  const d = new Date(typeof v === "number" && v < 1e12 ? v * 1000 : v);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

window.addEventListener("unhandledrejection", (e) => { console.warn("unhandled", e.reason); e.preventDefault(); });
boot().catch((e) => { console.error(e); toast("편집기를 시작하지 못했습니다.", { kind: "error", timeout: 0 }); });
