// Layer tree: pages at the top level, children top-first (highest z first, like Figma).
// Always virtualized (fixed 28 px rows), so 500+ rows cost the same as 50.

import { zSeq } from "../schema.js";
import * as S from "../select.js";
import { reorderPages } from "./pages.js";
import { el, ICON, TYPE_ICON } from "../ui.js";

const ROW = 28, OVERSCAN = 8;

export function mountLayers(box, C) {
  const expanded = new Set();
  let rows = [];            // {id, depth, hasKids}
  let anchor = null;
  const scroller = el("div", { class: "layer-scroll", role: "tree", "aria-label": "레이어", "aria-multiselectable": "true", tabindex: "0" });
  const spacer = el("div", { class: "layer-spacer" });
  const indicator = el("div", { class: "drop-line", hidden: true });
  scroller.append(spacer, indicator);
  box.replaceChildren(scroller);
  const pool = new Map();   // id -> row element (only visible rows)

  const P = (id) => S.P(id);
  const get = (id) => C.store.get(id);

  function build() {
    rows = [];
    const walk = (id, depth) => {
      const kids = C.store.childIds(id);
      rows.push({ id, depth, hasKids: kids.length > 0 });
      if (expanded.has(id)) for (let i = kids.length - 1; i >= 0; i--) walk(kids[i], depth + 1);
    };
    for (const pg of C.store.childIds(null)) walk(pg, 0);
    spacer.style.height = `${rows.length * ROW}px`;
  }
  function iconFor(n) {
    const p = P(n.id);
    if (n.type === "frame" && p.layout && p.layout.dir !== "NONE") return ICON.autolayout;
    if (n.type === "rect" && (p.fills || []).some((f) => f.type === "IMAGE")) return ICON.image;
    return ICON[TYPE_ICON[n.type]] || ICON.rect;
  }
  function paint() {
    const top = scroller.scrollTop, h = scroller.clientHeight || 400;
    const a = Math.max(0, Math.floor(top / ROW) - OVERSCAN), b = Math.min(rows.length, Math.ceil((top + h) / ROW) + OVERSCAN);
    const want = new Set();
    const sel = new Set(C.selection.ids);
    const hov = S.hovered();
    for (let i = a; i < b; i++) {
      const r = rows[i], n = get(r.id);
      if (!n) continue;
      want.add(r.id);
      let row = pool.get(r.id);
      if (!row) { row = makeRow(r.id); pool.set(r.id, row); scroller.append(row); }
      const p = P(r.id);
      row.style.transform = `translateY(${i * ROW}px)`;
      row.style.paddingLeft = `${6 + r.depth * 14}px`;
      row.classList.toggle("on", sel.has(r.id));
      row.classList.toggle("in-sel", !sel.has(r.id) && S.ancestors(r.id).some((x) => sel.has(x)));
      row.classList.toggle("hover", hov === r.id);
      row.classList.toggle("hidden-layer", p.visible === false);
      row.classList.toggle("locked", !!p.locked);
      row.classList.toggle("page-row", n.type === "page");
      row.setAttribute("aria-selected", String(sel.has(r.id)));
      row.setAttribute("aria-level", String(r.depth + 1));
      if (r.hasKids) row.setAttribute("aria-expanded", String(expanded.has(r.id))); else row.removeAttribute("aria-expanded");
      const caret = row.children[0];
      caret.style.visibility = r.hasKids ? "visible" : "hidden";
      caret.classList.toggle("open", expanded.has(r.id));
      const icon = row.children[1], key = n.type + (p.layout ? "al" : "") + ((p.fills || []).some((f) => f.type === "IMAGE") ? "im" : "");
      if (icon.dataset.k !== key) { icon.innerHTML = iconFor(n); icon.dataset.k = key; }
      const name = row.children[2];
      if (!name.querySelector("input")) name.textContent = p.name || n.type;
      row.querySelector(".eye").innerHTML = p.visible === false ? ICON.eyeOff : ICON.eye;
      row.querySelector(".eye").setAttribute("aria-label", p.visible === false ? "표시" : "숨기기");
      row.querySelector(".lock").innerHTML = p.locked ? ICON.lock : ICON.unlock;
      row.querySelector(".lock").setAttribute("aria-label", p.locked ? "잠금 해제" : "잠금");
    }
    for (const [id, row] of pool) if (!want.has(id) && !row.querySelector("input")) { row.remove(); pool.delete(id); }
  }
  function makeRow(id) {
    const caret = el("button", { type: "button", class: "caret-btn", tabindex: "-1", "aria-label": "펼치기/접기", html: ICON.caret });
    const eye = el("button", { type: "button", class: "row-act eye", tabindex: "-1", title: "숨기기/표시" });
    const lock = el("button", { type: "button", class: "row-act lock", tabindex: "-1", title: "잠금" });
    const row = el("div", { class: "layer-row", role: "treeitem", "data-id": id },
      caret, el("span", { class: "layer-icon", "aria-hidden": "true" }), el("span", { class: "layer-name" }), el("span", { class: "row-acts" }, lock, eye));
    caret.addEventListener("click", (e) => { e.stopPropagation(); toggle(id, e.altKey); });
    eye.addEventListener("click", (e) => { e.stopPropagation(); C.commit([{ op: "set", id, props: { visible: P(id).visible === false ? null : false } }], "숨기기"); });
    lock.addEventListener("click", (e) => { e.stopPropagation(); C.commit([{ op: "set", id, props: { locked: P(id).locked ? null : true } }], "잠금"); });
    row.addEventListener("pointerdown", (e) => down(e, id));
    row.addEventListener("dblclick", (e) => { if (e.target.closest(".layer-name")) rename(id); });
    row.addEventListener("pointerenter", () => S.setHover(id));
    row.addEventListener("pointerleave", () => S.setHover(null));
    row.addEventListener("contextmenu", (e) => { if (!C.selection.ids.includes(id)) C.selection.set([id]); C.shortcuts.contextMenu(e); });
    return row;
  }
  function toggle(id, deep) {
    const open = !expanded.has(id);
    const apply = (x) => { open ? expanded.add(x) : expanded.delete(x); if (deep) for (const c of C.store.childIds(x)) apply(c); };
    apply(id);
    refresh();
  }
  function select(e, id) {
    if (e.shiftKey && anchor && rows.some((r) => r.id === anchor)) {
      const a = rows.findIndex((r) => r.id === anchor), b = rows.findIndex((r) => r.id === id);
      C.selection.set(rows.slice(Math.min(a, b), Math.max(a, b) + 1).map((r) => r.id));
    } else if (e.metaKey || e.ctrlKey) { C.selection.toggle(id); anchor = id; }
    else { C.selection.set([id]); anchor = id; }
    const pg = C.store.pageIdOf(id);
    if (pg) C.setCurrentPage(pg);
    fromPanel = true;
  }

  // ---- drag to reorder / reparent ----
  function down(e, id) {
    if (e.button !== 0 || e.target.closest("button, input")) return;
    const startY = e.clientY;
    let drag = null;
    const sel0 = C.selection.ids.includes(id);
    if (!sel0 || e.shiftKey || e.metaKey || e.ctrlKey) select(e, id);
    const move = (ev) => {
      if (!drag && Math.abs(ev.clientY - startY) < 4) return;
      if (!drag) {
        const ids = S.topLevel(C.selection.ids).filter((x) => get(x));
        const pages = ids.filter((x) => get(x).type === "page");
        drag = { ids: pages.length ? pages : ids.filter((x) => get(x).type !== "page"), pages: pages.length > 0 };
        scroller.classList.add("dragging");
      }
      drag.target = dropAt(ev, drag);
      showIndicator(drag.target);
    };
    const up = (ev) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      scroller.classList.remove("dragging");
      indicator.hidden = true;
      pool.forEach((r) => r.classList.remove("drop-in"));
      if (!drag) { if (sel0 && !ev.shiftKey && !ev.metaKey && !ev.ctrlKey) select(ev, id); return; }
      if (drag.target) drop(drag, drag.target);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
  // -> {parent, beforeId (layer list order: insert above this sibling = higher z than it), inside, row}
  function dropAt(ev, drag) {
    const r = scroller.getBoundingClientRect();
    const y = ev.clientY - r.top + scroller.scrollTop;
    const i = Math.max(0, Math.min(rows.length - 1, Math.floor(y / ROW)));
    const row = rows[i];
    if (!row) return null;
    const n = get(row.id), f = (y - i * ROW) / ROW;
    const blocked = (pid) => drag.ids.some((d) => d === pid || S.ancestors(pid).includes(d));
    if (drag.pages) {
      if (n.type !== "page") return null;
      return { pages: true, before: f < 0.5 ? row.id : nextPageAfter(row.id), row: i, edge: f < 0.5 ? "top" : "bottom", depth: 0 };
    }
    const container = ["page", "frame", "section", "group", "boolean"].includes(n.type);
    if (container && (n.type === "page" || (f > 0.25 && f < 0.75) || (f >= 0.75 && expanded.has(row.id) && row.hasKids))) {
      if (blocked(row.id)) return null;
      if (drag.ids.some((d) => get(d).type === "section") && n.type !== "page") return null;
      // inside: on top of the children
      return { parent: row.id, aboveZ: null, row: i, inside: true, depth: row.depth + 1 };
    }
    const parent = n.parent;
    if (!parent || blocked(parent)) return null;
    if (drag.ids.some((d) => get(d).type === "section") && get(parent).type !== "page") return null;
    // list order is top-first: "top" edge = above row = higher z than row
    return { parent, ref: row.id, above: f < 0.5, row: i, edge: f < 0.5 ? "top" : "bottom", depth: row.depth };
  }
  function nextPageAfter(id) { const pg = C.store.childIds(null); return pg[pg.indexOf(id) + 1] || null; }
  function showIndicator(t) {
    pool.forEach((r) => r.classList.remove("drop-in"));
    if (!t) { indicator.hidden = true; return; }
    if (t.inside) { indicator.hidden = true; const row = pool.get(rows[t.row].id); row?.classList.add("drop-in"); return; }
    indicator.hidden = false;
    indicator.style.top = `${(t.row + (t.edge === "bottom" ? 1 : 0)) * ROW - 1}px`;
    indicator.style.left = `${6 + t.depth * 14 + 16}px`;
  }
  function drop(drag, t) {
    if (t.pages) { reorderPages(C, drag.ids, t.before); return; }
    const ids = S.sortByOrder(drag.ids);   // bottom -> top
    const sibs = C.store.childIds(t.parent).filter((x) => !ids.includes(x));
    let lo = null, hi = null;
    if (t.inside) lo = sibs.length ? get(sibs[sibs.length - 1]).z : null;
    else {
      const k = sibs.indexOf(t.ref);
      if (t.above) { lo = get(t.ref).z; hi = sibs[k + 1] ? get(sibs[k + 1]).z : null; }
      else { lo = sibs[k - 1] ? get(sibs[k - 1]).z : null; hi = get(t.ref).z; }
    }
    const zs = zSeq(lo, hi, ids.length);
    const tp = S.P(t.parent), flow = tp.layout && tp.layout.dir !== "NONE";
    const ops = [];
    ids.forEach((id, i) => {
      const same = get(id).parent === t.parent;
      const place = same || flow ? null : S.placeIn(id, t.parent);
      ops.push({ op: "move", id, parent: t.parent, z: zs[i] });
      if (place) ops.push({ op: "set", id, props: place });
    });
    C.commit(ops, "레이어 이동");
    if (t.inside) expanded.add(t.parent);
    refresh();
  }

  // ---- rename ----
  function rename(id) {
    revealIds([id]);
    const row = pool.get(id);
    if (!row) return false;
    const name = row.querySelector(".layer-name");
    const input = el("input", { class: "label-input", value: P(id).name || "", "aria-label": "레이어 이름" });
    name.replaceChildren(input);
    input.focus(); input.select();
    let done = false;
    const finish = (ok) => {
      if (done) return; done = true;
      const v = input.value.trim().slice(0, 200);
      name.textContent = P(id)?.name || "";
      if (ok && v !== (P(id)?.name || "")) C.commit([{ op: "set", id, props: { name: v || null } }], "이름 변경");
      paint();
    };
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.isComposing) return;
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
      if (e.key === "Tab") { e.preventDefault(); finish(true); const i = rows.findIndex((r) => r.id === id), nx = rows[i + (e.shiftKey ? -1 : 1)]; if (nx) { C.selection.set([nx.id]); setTimeout(() => rename(nx.id)); } }
    });
    input.addEventListener("blur", () => finish(true));
    return true;
  }

  // ---- keep in sync ----
  function revealIds(ids) {
    let changed = false;
    for (const id of ids) for (const a of S.ancestors(id)) if (!expanded.has(a)) { expanded.add(a); changed = true; }
    if (changed) build();
    const i = rows.findIndex((r) => r.id === ids[0]);
    if (i >= 0) {
      const top = i * ROW, h = scroller.clientHeight;
      if (top < scroller.scrollTop || top + ROW > scroller.scrollTop + h) scroller.scrollTop = Math.max(0, top - h / 2);
    }
    paint();
  }
  let q = 0;
  function refresh() { if (!q) q = requestAnimationFrame(() => { q = 0; build(); paint(); }); }
  let fromPanel = false;
  scroller.addEventListener("scroll", () => { if (!q) q = requestAnimationFrame(() => { q = 0; paint(); }); }, { passive: true });
  new ResizeObserver(() => paint()).observe(scroller);
  C.store.subscribe((changed, deleted) => {
    for (const id of deleted) { expanded.delete(id); const r = pool.get(id); if (r) { r.remove(); pool.delete(id); } }
    refresh();
  });
  C.selection.on((ids) => {
    if (!fromPanel && ids.length && box.offsetParent) revealIds(ids); else paint();
    fromPanel = false;
  });
  C.onPageChange(() => { const pg = C.currentPage(); if (pg && !expanded.has(pg)) { expanded.add(pg); refresh(); } });
  C.onHover?.(() => paint());
  // keyboard inside the tree: ↑/↓ moves selection, ←/→ collapse/expand
  scroller.addEventListener("keydown", (e) => {
    if (e.target !== scroller) return;
    const cur = C.selection.ids[C.selection.ids.length - 1], i = rows.findIndex((r) => r.id === cur);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); e.stopPropagation();
      const nx = rows[Math.max(0, Math.min(rows.length - 1, (i < 0 ? 0 : i) + (e.key === "ArrowDown" ? 1 : -1)))];
      if (nx) { C.selection.set([nx.id]); anchor = nx.id; revealIds([nx.id]); }
    } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && cur) {
      e.preventDefault(); e.stopPropagation();
      if (e.key === "ArrowRight") expanded.add(cur); else expanded.delete(cur);
      refresh();
    }
  });
  const pg = C.currentPage();
  if (pg) expanded.add(pg);
  build(); paint();
  return { rename, reveal: revealIds };
}
