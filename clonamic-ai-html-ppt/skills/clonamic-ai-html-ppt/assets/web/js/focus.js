// Focus pins (format.md §9.4): numbered markers in an editor layer, never in the render tree,
// present mode, or PDF. Click an element or drag a region with the pin tool, then write a note.

import * as S from "./select.js";
import { el, popover, closePopover, toast, store as ls } from "./ui.js";

const STATUS_LABEL = { open: "열림", sent: "보냄", resolved: "해결됨" };
export { STATUS_LABEL };

export function initFocus(C, { layer }) {
  let pins = [];
  let showResolved = ls("ppt-pins-resolved") !== "0";
  let draft = null;        // {page, rect} while dragging
  let active = null;       // pin id with its region outlined
  const fns = new Set();

  const num = (id) => pins.findIndex((p) => p.id === id) + 1;
  const visible = () => pins.filter((p) => (showResolved || p.status !== "resolved") && C.store.get(p.page));
  function set(list) { pins = Array.isArray(list) ? [...list].sort((a, b) => a.id - b.id) : []; paint(); fns.forEach((f) => { try { f(pins); } catch (e) { console.error(e); } }); }
  async function load() { const r = await C.api.pins(C.deckId); if (r.ok) set(r.data); }

  // Canvas box of a pin: its layers' union if they still exist, else its stored rect.
  function boxOf(pin) {
    const live = (pin.ids || []).filter((id) => C.store.get(id));
    if (live.length) return S.unionBox(live);
    const pg = S.boxOfPage(pin.page), r = pin.rect || { x: 0, y: 0, w: 0, h: 0 };
    return { x: pg.x + r.x, y: pg.y + r.y, w: r.w, h: r.h };
  }

  // ---- markers (HTML so they take clicks; the SVG overlay is click-through) ----
  const marks = new Map();
  function paint() {
    const V = C.viewport, want = new Set();
    for (const pin of visible()) {
      want.add(pin.id);
      let m = marks.get(pin.id);
      if (!m) {
        m = el("button", { type: "button", class: "pin-marker", on: {
          click: (e) => { e.stopPropagation(); open(pin.id); },
          pointerenter: () => { active = pin.id; S.requestDraw(); },
          pointerleave: () => { if (!popOpen) { active = null; S.requestDraw(); } },
        } });
        marks.set(pin.id, m); layer.append(m);
      }
      const b = boxOf(pin), p = V.pageToScreen(b.x + b.w, b.y);
      m.style.transform = `translate(${Math.round(p.x - 4)}px, ${Math.round(p.y - 20)}px)`;
      m.textContent = String(num(pin.id));
      m.dataset.status = pin.status;
      m.title = `${num(pin.id)}. ${pin.note || "메모 없음"} (${STATUS_LABEL[pin.status] || pin.status})`;
      m.setAttribute("aria-label", `포커스 핀 ${m.title}`);
    }
    for (const [id, m] of marks) if (!want.has(id)) { m.remove(); marks.delete(id); }
    S.requestDraw();
  }
  S.addDrawer((svg, { toS, s }) => {
    const box = draft ? { x: S.boxOfPage(draft.page).x + draft.rect.x, y: S.boxOfPage(draft.page).y + draft.rect.y, w: draft.rect.w, h: draft.rect.h }
      : active && pins.find((p) => p.id === active) ? boxOf(pins.find((p) => p.id === active)) : null;
    if (!box) return;
    const a = toS({ x: box.x, y: box.y }), b = toS({ x: box.x + box.w, y: box.y + box.h });
    svg.append(s("rect", { x: a.x, y: a.y, width: Math.max(1, b.x - a.x), height: Math.max(1, b.y - a.y), class: "ov-pin" }));
  });
  C.viewport.onChange(paint);
  let q = 0;
  C.store.subscribe(() => { if (!q) q = requestAnimationFrame(() => { q = 0; paint(); }); });

  // ---- pin tool ----
  function handlePointerDown(e) {
    if (e.button !== 0) return false;
    e.preventDefault();
    const p0 = C.viewport.clientToPage(e.clientX, e.clientY);
    const page = S.pageAt(p0);
    if (!page) { toast("페이지 안에 핀을 꽂으세요."); return true; }
    const pg = S.boxOfPage(page);
    const origin = { x: e.clientX, y: e.clientY };
    let moved = false;
    S.startCustomDrag({
      move(ev) {
        if (!moved && Math.hypot(ev.clientX - origin.x, ev.clientY - origin.y) < 4) return;
        moved = true;
        const p1 = C.viewport.clientToPage(ev.clientX, ev.clientY);
        const x0 = Math.max(pg.x, Math.min(p0.x, p1.x)), y0 = Math.max(pg.y, Math.min(p0.y, p1.y));
        const x1 = Math.min(pg.x + pg.w, Math.max(p0.x, p1.x)), y1 = Math.min(pg.y + pg.h, Math.max(p0.y, p1.y));
        draft = { page, rect: { x: Math.round(x0 - pg.x), y: Math.round(y0 - pg.y), w: Math.max(0, Math.round(x1 - x0)), h: Math.max(0, Math.round(y1 - y0)) } };
      },
      up(ev) {
        let pin;
        if (moved && draft) {
          // layers inside the region, so the pin follows them
          const r = draft.rect, abs = { x: pg.x + r.x, y: pg.y + r.y, w: r.w, h: r.h };
          const ids = C.store.childIds(page).filter((id) => { const b = S.boxOf(id); return b && b.x >= abs.x && b.y >= abs.y && b.x + b.w <= abs.x + abs.w && b.y + b.h <= abs.y + abs.h; });
          pin = { page, ids: ids.slice(0, 1000), rect: r };
        } else {
          const id = S.pickAt(ev.clientX, ev.clientY, ev.metaKey || ev.ctrlKey);
          const b = id ? S.boxOf(id) : { x: p0.x, y: p0.y, w: 0, h: 0 };
          pin = { page, ids: id ? [id] : [], rect: { x: Math.round(b.x - pg.x), y: Math.round(b.y - pg.y), w: Math.round(b.w), h: Math.round(b.h) } };
        }
        draft = { page, rect: pin.rect };
        C.tools.setTool("move");
        editor(null, pin, { x: ev.clientX, y: ev.clientY });
      },
      cancel() { draft = null; S.requestDraw(); },
    });
    return true;
  }

  // ---- note popover ----
  let popOpen = false;
  function editor(pin, fresh, at) {
    const note = el("textarea", { rows: "3", maxlength: "2000", placeholder: "AI에게 남길 메모 (무엇을 어떻게 바꿀지)", "aria-label": "핀 메모" }, pin ? pin.note : "");
    const n = pin ? num(pin.id) : pins.length + 1;
    const save = async (sendNow) => {
      const text = note.value.trim();
      if (pin) {
        if (text !== pin.note) { const r = await C.api.updatePin(C.deckId, pin.id, { note: text }); if (!r.ok) return toast("핀을 고치지 못했습니다.", { kind: "error" }); }
        if (sendNow) send([pin.id]);
      } else {
        const r = await C.api.addPin(C.deckId, { ...fresh, note: text });
        if (!r.ok) return toast(r.data?.error || "핀을 만들지 못했습니다.", { kind: "error" });
        await load();
        if (sendNow) send([r.data.id]);
      }
      closePopover();
    };
    const statusRow = pin ? el("div", { class: "segmented", role: "group", "aria-label": "상태" }, ...["open", "sent", "resolved"].map((st) =>
      el("button", { type: "button", "aria-pressed": String(pin.status === st), on: { click: async () => { await C.api.updatePin(C.deckId, pin.id, { status: st }); closePopover(); } } }, STATUS_LABEL[st]))) : null;
    const box = el("div", { class: "pin-pop" },
      el("div", { class: "panel-title" }, `핀 ${n}${pin ? ` · ${STATUS_LABEL[pin.status] || ""}` : ""}`),
      note, statusRow,
      el("div", { class: "row end" },
        pin ? el("button", { type: "button", class: "ghost danger-text", on: { click: () => { remove(pin.id); closePopover(); } } }, "삭제") : null,
        el("button", { type: "button", class: "ghost", on: { click: () => save(false) } }, "저장"),
        el("button", { type: "button", class: "primary", on: { click: () => save(true) } }, "AI에게 보내기")));
    note.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !e.isComposing) save(true); });
    const keepDraft = draft, keepActive = active;
    closePopover();   // its onClose resets state; restore ours after
    draft = keepDraft; active = keepActive; popOpen = true;
    popover(at, box, { onClose: () => { popOpen = false; draft = null; active = null; S.requestDraw(); } });
    setTimeout(() => note.focus(), 0);
  }
  function open(id) {
    const pin = pins.find((p) => p.id === id);
    if (!pin) return;
    if (!C.store.get(pin.page)) return toast("핀의 페이지가 없습니다.");
    active = id;
    const b = boxOf(pin);
    const vis = C.viewport.visibleRect();
    if (b.x > vis.x + vis.w || b.x + b.w < vis.x || b.y > vis.y + vis.h || b.y + b.h < vis.y) C.viewport.zoomToPage(pin.page, false);
    C.setCurrentPage(pin.page);
    paint();
    const m = marks.get(id);
    const r = m?.getBoundingClientRect();
    editor(pin, null, r ? { x: r.left, y: r.bottom + 4 } : { x: innerWidth / 2, y: innerHeight / 3 });
  }
  async function remove(id) {
    const r = await C.api.deletePin(C.deckId, id);
    if (!r.ok) toast("핀을 지우지 못했습니다.", { kind: "error" });
  }
  async function setStatus(id, status) { await C.api.updatePin(C.deckId, id, { status }); }
  function send(ids) {
    const list = pins.filter((p) => ids.includes(p.id));
    const text = list.length === 1 && list[0].note ? list[0].note : list.map((p) => `${num(p.id)}. ${p.note || "(메모 없음)"}`).join("\n") || "핀 위치를 확인해 주세요.";
    C.ai?.send(text, { focus: ids, page: list[0]?.page });
  }
  function setShowResolved(v) { showResolved = v; ls("ppt-pins-resolved", v ? "1" : "0"); paint(); fns.forEach((f) => f(pins)); }
  // select the pin's layers (from the AI tab)
  function selectPin(id) {
    const pin = pins.find((p) => p.id === id);
    if (!pin) return;
    const live = (pin.ids || []).filter((x) => C.store.get(x));
    if (live.length) { C.selection.set(live); C.viewport.fitSelection(); } else C.viewport.zoomToPage(pin.page);
    active = id; S.requestDraw();
  }

  load();
  return {
    handlePointerDown, open, remove, setStatus, send, selectPin, load, set,
    get pins() { return pins; },
    get showResolved() { return showResolved; },
    setShowResolved, number: num,
    onChange(fn) { fns.add(fn); return () => fns.delete(fn); },
    setVisible(v) { layer.hidden = !v; },
  };
}
