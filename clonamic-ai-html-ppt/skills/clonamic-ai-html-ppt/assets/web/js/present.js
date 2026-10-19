// Presentation: fullscreen, one page scaled to fit (letterboxed), keyboard/click navigation, slide
// counter; presenter view in a second window (current + next, notes, timer) synced by BroadcastChannel.

import { createRenderer } from "./render.js";
import { el, toast } from "./ui.js";

const chanName = (deck) => `ppt-present-${deck}`;
const visiblePages = (store) => store.childIds(null).filter((id) => store.get(id)?.props.visible !== false);

// A page renderer that keeps the page letterboxed inside `host`.
function slideView(host, store, assetUrl, links = true) {
  const stage = el("div", { class: "slide-stage" });
  const root = el("div", { class: "slide-root" });
  root.style.setProperty("--ppt-backdrop", "#000");   // W2's LINEAR_BURN backdrop matches the letterbox
  stage.append(root);
  host.append(stage);
  let r = null, page = null;
  function fit() {
    const p = page && store.get(page)?.props;
    if (!p) return;
    const W = host.clientWidth, H = host.clientHeight, s = Math.min(W / p.w, H / p.h) || 1;
    root.style.width = `${p.w}px`; root.style.height = `${p.h}px`;
    root.style.transform = `translate(${(W - p.w * s) / 2}px, ${(H - p.h * s) / 2}px) scale(${s})`;
  }
  const ro = new ResizeObserver(fit);
  ro.observe(host);
  return {
    show(id) {
      page = id;
      if (!id) { r?.destroy(); r = null; return; }
      if (!r) { r = createRenderer({ root, mode: "present", assetUrl, page: id, links }); r.mount(store); }
      else if (r.page !== id) r.setPage(id);
      fit();
    },
    fit,
    destroy() { ro.disconnect(); r?.destroy(); stage.remove(); },
  };
}

export function startPresent(C, fromId) {
  const pages = () => visiblePages(C.store);
  let list = pages();
  if (!list.length) { toast("발표할 페이지가 없습니다."); return; }
  let i = Math.max(0, fromId ? list.indexOf(fromId) : 0);
  const overlay = el("div", { class: "present", tabindex: "-1", role: "dialog", "aria-label": "발표" });
  const counter = el("div", { class: "present-counter", "aria-live": "polite" });
  const bar = el("div", { class: "present-bar" },
    el("button", { type: "button", "aria-label": "이전", title: "이전 (←)", text: "‹", on: { click: (e) => { e.stopPropagation(); go(i - 1); } } }),
    counter,
    el("button", { type: "button", "aria-label": "다음", title: "다음 (→)", text: "›", on: { click: (e) => { e.stopPropagation(); go(i + 1); } } }),
    el("button", { type: "button", class: "text", on: { click: (e) => { e.stopPropagation(); presenterFromShow(); } } }, "발표자 보기"),
    el("button", { type: "button", class: "text", on: { click: (e) => { e.stopPropagation(); close(); } } }, "종료 (Esc)"));
  document.body.append(overlay);
  const view = slideView(overlay, C.store, C.assetUrl);
  overlay.append(bar);
  const chan = "BroadcastChannel" in window ? new BroadcastChannel(chanName(C.deckId)) : null;
  let idle = 0;
  const wake = () => { overlay.classList.add("ui"); clearTimeout(idle); idle = setTimeout(() => overlay.classList.remove("ui"), 2000); };

  function go(n, from) {
    list = pages();
    if (!list.length) return close();
    if (n >= list.length) n = list.length - 1;
    if (n < 0) n = 0;
    i = n;
    view.show(list[i]);
    counter.textContent = `${i + 1} / ${list.length}`;
    if (from !== "remote") chan?.postMessage({ type: "goto", page: list[i], index: i });
  }
  function onKey(e) {
    if (e.isComposing) return;
    const k = e.key;
    if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter", "n"].includes(k)) { e.preventDefault(); e.stopPropagation(); go(i + 1); }
    else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace", "p"].includes(k)) { e.preventDefault(); e.stopPropagation(); go(i - 1); }
    else if (k === "Home") { e.preventDefault(); e.stopPropagation(); go(0); }
    else if (k === "End") { e.preventDefault(); e.stopPropagation(); go(list.length - 1); }
    else if (k === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
    else e.stopPropagation();
  }
  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    window.removeEventListener("keydown", onKey, true);
    document.removeEventListener("fullscreenchange", onFs);
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    chan?.postMessage({ type: "end" });
    chan?.close();
    view.destroy();
    overlay.remove();
    C.setCurrentPage(list[i]);
    C.container.focus();
  }
  // Opening the presenter window drops fullscreen (window.open): keep the show running in the window.
  let keepOnFsExit = false, keepT = 0;
  function presenterFromShow() {
    keepOnFsExit = !!document.fullscreenElement;
    clearTimeout(keepT);
    keepT = setTimeout(() => { keepOnFsExit = false; }, 2000);
    openPresenter(C);
    chan?.postMessage({ type: "goto", page: list[i], index: i });
    setTimeout(() => overlay.focus(), 0);
  }
  function onFs() {
    if (document.fullscreenElement) return;
    if (keepOnFsExit) { keepOnFsExit = false; overlay.classList.add("windowed"); return; }
    close();
  }
  window.addEventListener("keydown", onKey, true);
  overlay.addEventListener("click", (e) => { if (!e.target.closest("button")) go(i + 1); });
  overlay.addEventListener("pointermove", wake);
  if (chan) chan.onmessage = (e) => {
    const d = e.data || {};
    if (d.type === "goto") { const k = pages().indexOf(d.page); go(k >= 0 ? k : d.index, "remote"); }
    if (d.type === "hello") chan.postMessage({ type: "goto", page: list[i], index: i });
    if (d.type === "end") close();
  };
  overlay.requestFullscreen?.().then(() => document.addEventListener("fullscreenchange", onFs)).catch(() => { /* windowed fallback */ });
  overlay.focus();
  go(i);
  wake();
}

export function openPresenter(C) {
  const w = window.open(`/?presenter=1#${encodeURIComponent(C.deckId)}`, `ppt-presenter-${C.deckId}`, "width=1200,height=760");
  if (!w) toast("팝업이 막혔습니다. 팝업을 허용하세요.");
}

// Presenter window (index.html?presenter=1#deck): current + next slide, notes, timer.
export function bootPresenter(store, { deckId, assetUrl }) {
  document.title = `발표자 보기 — ${store.deck.name || ""}`;
  document.body.className = "presenter-body";
  const cur = el("div", { class: "pv-cur" }), next = el("div", { class: "pv-next" });
  const notes = el("div", { class: "pv-notes", "aria-label": "발표자 노트" });
  const timer = el("div", { class: "pv-timer", "aria-live": "off" }, "00:00");
  const count = el("div", { class: "pv-count" });
  const chan = "BroadcastChannel" in window ? new BroadcastChannel(chanName(deckId)) : null;
  let i = 0, t0 = Date.now(), paused = 0, pausedAt = 0;
  const btn = (label, fn) => el("button", { type: "button", on: { click: fn } }, label);
  document.body.replaceChildren(el("div", { class: "pv" },
    el("div", { class: "pv-main" }, el("div", { class: "pv-label" }, "현재"), cur),
    el("div", { class: "pv-side" }, el("div", { class: "pv-label" }, "다음"), next,
      el("div", { class: "pv-ctrl" }, btn("‹ 이전", () => go(i - 1, true)), count, btn("다음 ›", () => go(i + 1, true))),
      el("div", { class: "pv-time" }, timer,
        btn("일시정지", (e) => { if (pausedAt) { paused += Date.now() - pausedAt; pausedAt = 0; e.target.textContent = "일시정지"; } else { pausedAt = Date.now(); e.target.textContent = "계속"; } }),
        btn("초기화", () => { t0 = Date.now(); paused = 0; pausedAt = pausedAt ? Date.now() : 0; })),
      el("div", { class: "pv-label" }, "노트"), notes)));
  const vc = slideView(cur, store, assetUrl, false), vn = slideView(next, store, assetUrl, false);
  function go(n, local) {
    const list = visiblePages(store);
    if (!list.length) return;
    i = Math.max(0, Math.min(list.length - 1, n));
    vc.show(list[i]);
    vn.show(list[i + 1] || null);
    if (!list[i + 1]) next.dataset.empty = "마지막 페이지"; else delete next.dataset.empty;
    notes.textContent = store.get(list[i])?.props.notes || "노트 없음";
    count.textContent = `${i + 1} / ${list.length}`;
    if (local) chan?.postMessage({ type: "goto", page: list[i], index: i });
  }
  if (chan) chan.onmessage = (e) => {
    const d = e.data || {};
    if (d.type === "goto") { const k = visiblePages(store).indexOf(d.page); go(k >= 0 ? k : d.index, false); }
  };
  store.subscribe(() => { notes.textContent = store.get(visiblePages(store)[i])?.props.notes || "노트 없음"; });
  setInterval(() => {
    const ms = (pausedAt || Date.now()) - t0 - paused, s = Math.max(0, Math.floor(ms / 1000));
    timer.textContent = `${String(Math.floor(s / 3600) ? Math.floor(s / 3600) + ":" : "")}${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 500);
  window.addEventListener("keydown", (e) => {
    if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(e.key)) { e.preventDefault(); go(i + 1, true); }
    if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) { e.preventDefault(); go(i - 1, true); }
  });
  go(0, false);
  chan?.postMessage({ type: "hello" });
}
