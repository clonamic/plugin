// Page list: live thumbnails (present-mode renderers, only while visible), add with presets,
// duplicate, delete, rename, drag reorder (z order + left→right layout with 100 px gaps).

import { SCHEMA, newId, zSeq } from "../schema.js";
import { createRenderer } from "../render.js";
import { cloneOps } from "../select.js";
import { el, menu, popover, closePopover, toast, ICON, PRESET_LABEL } from "../ui.js";

const GAP = 100, THUMB_W = 176;

// No orientation = the preset's natural one (slides landscape, paper portrait).
export function presetSize(preset, orientation) {
  let [w, h] = SCHEMA.presets[preset] || SCHEMA.presets.SLIDE_16_9;
  if (orientation && (orientation === "landscape") !== (w >= h)) [w, h] = [h, w];
  return [w, h];
}

// Positions for pages in the given order: one row, left→right, tops aligned to the first page.
function layoutOps(C, order, sizes = new Map()) {
  const ops = [];
  const first = C.store.get(order[0]);
  let x = first ? (sizes.get(order[0])?.cx ?? first.props.cx ?? 0) : 0;
  const y = first ? (sizes.get(order[0])?.cy ?? first.props.cy ?? 0) : 0;
  for (const id of order) {
    const n = C.store.get(id), s = sizes.get(id);
    const w = s?.w ?? n?.props.w ?? 1920;
    const cx = n?.props.cx ?? 0, cy = n?.props.cy ?? 0;
    if (s) { s.cx = x; s.cy = y; }
    else if (Math.abs(cx - x) > 1e-6 || Math.abs(cy - y) > 1e-6) ops.push({ op: "set", id, props: { cx: x, cy: y } });
    x += w + GAP;
  }
  return ops;
}

export function addPage(C, { preset = "SLIDE_16_9", orientation = null, w, h } = {}) {
  const pages = C.store.childIds(null);
  const [pw, ph] = w && h ? [w, h] : presetSize(preset, orientation);
  let cx = 0, cy = 0;
  if (pages.length) {
    cx = Math.max(...pages.map((id) => (C.store.get(id).props.cx || 0) + (C.store.get(id).props.w || 1920))) + GAP;
    cy = C.store.get(pages[0]).props.cy || 0;
  }
  const id = newId("page");
  const z = zSeq(pages.length ? C.store.get(pages[pages.length - 1]).z : null, null, 1)[0];
  C.commit([{ op: "add", node: { id, type: "page", parent: null, z, props: {
    name: `페이지 ${pages.length + 1}`, cx, cy, w: pw, h: ph, preset: w && h ? "CUSTOM" : preset, orientation: pw >= ph ? "landscape" : "portrait" } } }], "페이지 추가");
  C.selection.set([id]);
  C.setCurrentPage(id);
  C.viewport.zoomToPage(id);
  return id;
}

export function duplicatePages(C, ids) {
  const order = C.store.childIds(null);
  ids = order.filter((id) => ids.includes(id));
  if (!ids.length) return;
  const c = cloneOps(ids);
  // final order with the copies right after their originals
  const sizes = new Map();
  for (const o of c.ops) if (o.node.parent === null) sizes.set(o.node.id, { w: o.node.props.w ?? 1920, z: o.node.z });
  const all = [...order.map((id) => ({ id, z: C.store.get(id).z })), ...[...sizes].map(([id, s]) => ({ id, z: s.z }))].sort((a, b) => (a.z < b.z ? -1 : a.z > b.z ? 1 : 0)).map((x) => x.id);
  const ops = layoutOps(C, all, sizes);
  for (const o of c.ops) if (sizes.has(o.node.id)) { const s = sizes.get(o.node.id); o.node.props.cx = s.cx; o.node.props.cy = s.cy; o.node.props.name = `${o.node.props.name || "페이지"} 사본`.slice(0, 200); }
  C.commit([...c.ops, ...ops], "페이지 복제");
  C.selection.set(c.roots);
  C.setCurrentPage(c.roots[0]);
}

export function deletePages(C, ids) {
  const pages = C.store.childIds(null);
  ids = ids.filter((id) => pages.includes(id));
  if (!ids.length) return;
  if (ids.length >= pages.length) { toast("마지막 페이지는 지울 수 없습니다."); return; }
  C.selection.set(C.selection.ids.filter((id) => !ids.includes(id) && !ids.includes(C.store.pageIdOf(id))));
  C.commit(ids.map((id) => ({ op: "del", id })), "페이지 삭제");
}

// Move `ids` so they sit before `beforeId` (null = end), then re-lay the row.
export function reorderPages(C, ids, beforeId) {
  const order = C.store.childIds(null);
  const moving = order.filter((id) => ids.includes(id));
  const rest = order.filter((id) => !ids.includes(id));
  let at = beforeId ? rest.indexOf(beforeId) : rest.length;
  if (at < 0) at = rest.length;
  const next = [...rest.slice(0, at), ...moving, ...rest.slice(at)];
  if (next.every((id, i) => id === order[i])) return;
  const prevZ = at > 0 ? C.store.get(rest[at - 1]).z : null, nextZ = at < rest.length ? C.store.get(rest[at]).z : null;
  const zs = zSeq(prevZ, nextZ, moving.length);
  const ops = moving.map((id, i) => ({ op: "move", id, parent: null, z: zs[i] }));
  // positions follow the new order
  const firstOld = C.store.get(order[0]).props;
  let x = firstOld.cx || 0;
  const y = firstOld.cy || 0;
  for (const id of next) {
    const p = C.store.get(id).props;
    if (Math.abs((p.cx || 0) - x) > 1e-6 || Math.abs((p.cy || 0) - y) > 1e-6) ops.push({ op: "set", id, props: { cx: x, cy: y } });
    x += (p.w || 1920) + GAP;
  }
  C.commit(ops, "페이지 순서 변경");
}

export function orientSeg(get, set) {
  const seg = el("div", { class: "segmented", role: "group", "aria-label": "방향" }, ...[[null, "기본"], ["landscape", "가로"], ["portrait", "세로"]].map(([v, l]) =>
    el("button", { type: "button", "aria-pressed": String(v === get()), title: v ? null : "용지는 세로, 슬라이드는 가로", on: { click: (e) => {
      set(v); seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
    } } }, l)));
  return seg;
}
export function presetPicker(C, anchor) {
  let orient = null;
  const wIn = el("input", { type: "number", min: "1", value: "1280", "aria-label": "너비" });
  const hIn = el("input", { type: "number", min: "1", value: "720", "aria-label": "높이" });
  const keys = Object.keys(SCHEMA.presets);
  const grid = el("div", { class: "preset-list" });
  const paint = () => grid.replaceChildren(...keys.map((k) => {
    const [w, h] = presetSize(k, orient);
    return el("button", { type: "button", class: "preset", on: { click: () => { closePopover(); addPage(C, { preset: k, orientation: orient }); } } },
      el("span", {}, PRESET_LABEL[k] || k), el("span", { class: "dim" }, `${w}×${h}`));
  }));
  const seg = orientSeg(() => orient, (v) => { orient = v; paint(); });
  paint();
  popover(anchor, el("div", { class: "page-picker" }, el("div", { class: "panel-title" }, "새 페이지"), seg, grid,
    el("div", { class: "preset-head" }, "사용자 지정"),
    el("div", { class: "row" }, wIn, el("span", { class: "dim" }, "×"), hIn,
      el("button", { type: "button", class: "primary", on: { click: () => {
        const w = Math.round(Number(wIn.value)), h = Math.round(Number(hIn.value));
        if (!(w >= 1 && h >= 1 && w <= 100000 && h <= 100000)) { toast("크기를 확인하세요."); return; }
        closePopover(); addPage(C, { w, h });
      } } }, "추가"))), { className: "wide" });
}

export function mountPages(box, C) {
  const marked = new Set();
  let anchorId = null;
  const head = el("div", { class: "panel-head" }, el("span", { class: "panel-title" }, "페이지"),
    el("button", { type: "button", class: "icon-btn", "aria-label": "페이지 추가", title: "페이지 추가", html: ICON.plus, on: { click: (e) => presetPicker(C, e.currentTarget) } }));
  const list = el("div", { class: "page-list", role: "listbox", "aria-label": "페이지 목록", "aria-multiselectable": "true", tabindex: "0" });
  box.replaceChildren(head, list);
  const items = new Map();   // id -> {li, thumb, renderer, frame}

  // Thumbnails see changes 300 ms late, batched (one store subscription for all of them).
  const thumbSubs = new Set();
  let pc = new Set(), pd = new Set(), timer = 0;
  C.store.subscribe((c, d) => {
    c.forEach((x) => pc.add(x)); d.forEach((x) => pd.add(x));
    clearTimeout(timer);
    timer = setTimeout(() => { const cc = [...pc], dd = [...pd]; pc = new Set(); pd = new Set(); thumbSubs.forEach((fn) => { try { fn(cc, dd); } catch (e) { console.error(e); } }); }, 300);
  });
  const lazyStore = {
    get deck() { return C.store.deck; }, nodes: C.store.nodes, get: C.store.get,
    children: C.store.children, childIds: C.store.childIds, pageOf: C.store.pageOf, pageIdOf: C.store.pageIdOf,
    subscribe(fn) { thumbSubs.add(fn); return () => thumbSubs.delete(fn); },
  };

  const io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      const id = en.target.dataset.page, it = items.get(id);
      if (!it) continue;
      if (en.isIntersecting && !it.renderer) mountThumb(id, it);
      else if (!en.isIntersecting && it.renderer) { try { it.renderer.destroy(); } catch (_) { /* gone */ } it.renderer = null; it.root.replaceChildren(); }
    }
  }, { root: list, rootMargin: "200px 0px" });

  function sizeThumb(id, it) {
    const p = C.store.get(id)?.props;
    if (!p) return;
    const s = THUMB_W / (p.w || 1920);
    it.frame.style.height = `${Math.round((p.h || 1080) * s)}px`;
    it.root.style.width = `${p.w}px`; it.root.style.height = `${p.h}px`;
    it.root.style.transform = `scale(${s})`;
  }
  function mountThumb(id, it) {
    sizeThumb(id, it);
    try {
      it.renderer = createRenderer({ root: it.root, mode: "present", assetUrl: C.assetUrl, page: id, links: false });
      it.renderer.mount(lazyStore);
    } catch (e) { console.error(e); it.renderer = null; }
  }

  function render() {
    const pages = C.store.childIds(null);
    for (const [id, it] of items) if (!pages.includes(id)) { io.unobserve(it.li); try { it.renderer?.destroy(); } catch (_) { /* gone */ } it.li.remove(); items.delete(id); }
    for (const id of [...marked]) if (!pages.includes(id)) marked.delete(id);
    pages.forEach((id, i) => {
      let it = items.get(id);
      if (!it) {
        const root = el("div", { class: "thumb-root" });
        const frame = el("div", { class: "thumb" }, root);
        const name = el("div", { class: "thumb-name" });
        const num = el("div", { class: "thumb-num" });
        const li = el("div", { class: "page-item", role: "option", "data-page": id, draggable: "true", tabindex: "-1" }, num, el("div", { class: "thumb-col" }, frame, name));
        it = { li, root, frame, name, num, renderer: null };
        items.set(id, it);
        li.addEventListener("click", (e) => clickItem(e, id));
        li.addEventListener("dblclick", (e) => { if (e.target.closest(".thumb-name")) rename(id); else C.viewport.zoomToPage(id); });
        li.addEventListener("contextmenu", (e) => { e.preventDefault(); itemMenu(e, id); });
        li.addEventListener("dragstart", (e) => dragStart(e, id));
        io.observe(li);
      }
      const p = C.store.get(id).props;
      it.num.textContent = String(i + 1);
      if (!it.name.querySelector("input")) it.name.textContent = p.name || `페이지 ${i + 1}`;
      it.li.title = p.name || "";
      it.li.setAttribute("aria-label", `${i + 1}. ${p.name || "페이지"}`);
      sizeThumb(id, it);
      if (list.children[i] !== it.li) list.insertBefore(it.li, list.children[i] || null);
    });
    paintState();
  }
  function paintState() {
    const cur = C.currentPage();
    for (const [id, it] of items) {
      it.li.classList.toggle("current", id === cur);
      it.li.classList.toggle("marked", marked.has(id));
      it.li.setAttribute("aria-selected", String(marked.has(id)));
    }
  }
  function clickItem(e, id) {
    const pages = C.store.childIds(null);
    if (e.shiftKey && anchorId && pages.includes(anchorId)) {
      const a = pages.indexOf(anchorId), b = pages.indexOf(id);
      marked.clear();
      pages.slice(Math.min(a, b), Math.max(a, b) + 1).forEach((x) => marked.add(x));
    } else if (e.metaKey || e.ctrlKey) { marked.has(id) ? marked.delete(id) : marked.add(id); anchorId = id; }
    else { marked.clear(); marked.add(id); anchorId = id; }
    C.setCurrentPage(id);
    C.selection.set([...marked].filter((x) => pages.includes(x)));
    if (!e.shiftKey && !e.metaKey && !e.ctrlKey) C.viewport.zoomToPage(id);
    paintState();
  }
  function rename(id) {
    const it = items.get(id);
    if (!it) return;
    const input = el("input", { class: "label-input", value: C.store.get(id).props.name || "", "aria-label": "페이지 이름" });
    it.name.replaceChildren(input);
    input.focus(); input.select();
    let done = false;
    const finish = (ok) => {
      if (done) return; done = true;
      const v = input.value.trim().slice(0, 200);
      it.name.textContent = C.store.get(id)?.props.name || "";
      if (ok && v && v !== C.store.get(id)?.props.name) C.commit([{ op: "set", id, props: { name: v } }], "페이지 이름 변경");
    };
    input.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter" && !e.isComposing) finish(true); if (e.key === "Escape") finish(false); });
    input.addEventListener("blur", () => finish(true));
  }
  function targets(id) { return marked.has(id) ? [...marked] : [id]; }
  function itemMenu(e, id) {
    if (!marked.has(id)) { marked.clear(); marked.add(id); anchorId = id; paintState(); }
    menu({ x: e.clientX, y: e.clientY }, [
      { label: "페이지 추가", run: () => presetPicker(C, { x: e.clientX, y: e.clientY }) },
      { label: "복제", run: () => duplicatePages(C, targets(id)) },
      { label: "이름 바꾸기", run: () => rename(id) },
      { label: "여기서 발표", run: () => C.present(id) },
      { sep: true },
      { label: "삭제", danger: true, run: () => deletePages(C, targets(id)) },
    ]);
  }

  // drag reorder (HTML5 DnD within the list)
  let dragIds = null;
  const indicator = el("div", { class: "drop-line", hidden: true });
  list.append(indicator);
  function dragStart(e, id) {
    dragIds = targets(id);
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", ""); } catch (_) { /* some browsers */ }
  }
  function dropBefore(e) {
    const lis = [...list.querySelectorAll(".page-item")];
    for (const li of lis) { const r = li.getBoundingClientRect(); if (e.clientY < r.top + r.height / 2) return li; }
    return null;
  }
  list.addEventListener("dragover", (e) => {
    if (!dragIds) return;
    e.preventDefault();
    const li = dropBefore(e), lr = list.getBoundingClientRect();
    const last = list.querySelector(".page-item:last-of-type");
    const y = li ? li.getBoundingClientRect().top - lr.top + list.scrollTop - 3 : (last ? last.getBoundingClientRect().bottom - lr.top + list.scrollTop + 1 : 0);
    indicator.hidden = false; indicator.style.top = `${y}px`;
  });
  list.addEventListener("dragleave", (e) => { if (!list.contains(e.relatedTarget)) indicator.hidden = true; });
  list.addEventListener("drop", (e) => {
    if (!dragIds) return;
    e.preventDefault();
    indicator.hidden = true;
    const li = dropBefore(e);
    let before = li ? li.dataset.page : null;
    while (before && dragIds.includes(before)) { const nx = items.get(before).li.nextElementSibling; before = nx?.dataset?.page || null; }
    reorderPages(C, dragIds, before);
    dragIds = null;
  });
  list.addEventListener("dragend", () => { dragIds = null; indicator.hidden = true; });

  // keyboard: ↑/↓ move through pages
  list.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault(); e.stopPropagation();
    const pages = C.store.childIds(null), i = pages.indexOf(C.currentPage());
    const next = pages[Math.max(0, Math.min(pages.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) clickItem({}, next);
  });

  let renderQueued = 0;
  const queue = () => { if (!renderQueued) renderQueued = requestAnimationFrame(() => { renderQueued = 0; render(); }); };
  C.store.subscribe((changed, deleted) => {
    if (deleted.length || changed.some((id) => C.store.get(id)?.type === "page")) queue();
  });
  C.onPageChange(() => {
    paintState();
    const it = items.get(C.currentPage());
    it?.li.scrollIntoView({ block: "nearest" });
  });
  C.selection.on((ids) => {
    // canvas selection of pages mirrors into the list
    const pages = ids.filter((id) => C.store.get(id)?.type === "page");
    if (pages.length) { marked.clear(); pages.forEach((p) => marked.add(p)); paintState(); }
  });
  render();
  return {
    get marked() { return C.store.childIds(null).filter((id) => marked.has(id)); },
    duplicate: (ids) => duplicatePages(C, ids),
    rename,
  };
}
