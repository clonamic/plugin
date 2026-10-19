// Infinite canvas. One transform on the world element: screen = canvas * zoom + (tx, ty).
// "Screen" coordinates are relative to the canvas container's top-left. "Page" (canvas) coordinates
// are the deck canvas where pages sit at cx, cy (Figma calls this space the page).

import { store as ls } from "./ui.js";

export const MIN_ZOOM = 0.02, MAX_ZOOM = 256;
const clampZ = (z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

export function createViewport(ctx, { container, world, rulerTop, rulerLeft, rulerCorner, grid }) {
  let tx = 0, ty = 0, z = 1, raf = 0, anim = 0;
  let rect = container.getBoundingClientRect();
  const listeners = new Set();
  const viewKey = `ppt-view-${ctx.deckId}`;

  new ResizeObserver(() => { rect = container.getBoundingClientRect(); sizeRulers(); schedule(); }).observe(container);

  // --zoom is inherited by every node element (W2 reads it for hit-stroke widths and labels), so
  // writing it restyles and repaints the whole document (~15 ms on 1,000 nodes). Write it only when
  // the viewport has been at rest for 150 ms (any pan or zoom re-arms the timer), and only for a real
  // change (a zoom in/out pair drifts by ~1e-16). During gestures only the world transform changes.
  let zApplied = null, zTimer = 0;
  const zoomChanged = () => zApplied === null || Math.abs(z - zApplied) > zApplied * 1e-6;
  function applyZoomVar() { zTimer = 0; if (zoomChanged()) { zApplied = z; container.style.setProperty("--zoom", z); } }
  function flush() {
    raf = 0;
    world.style.transform = `translate(${tx}px, ${ty}px) scale(${z})`;
    if (zApplied === null) applyZoomVar();
    else if (zTimer || zoomChanged()) { clearTimeout(zTimer); zTimer = setTimeout(applyZoomVar, 150); }
    drawGrid();
    drawRulers();
    for (const fn of listeners) { try { fn(); } catch (e) { console.error(e); } }
    saveView();
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(flush); }
  let saveT = 0;
  function saveView() { clearTimeout(saveT); saveT = setTimeout(() => ls(viewKey, JSON.stringify({ tx, ty, z })), 400); }

  const toScreen = (x, y) => ({ x: x * z + tx, y: y * z + ty });
  const toPage = (sx, sy) => ({ x: (sx - tx) / z, y: (sy - ty) / z });

  function set(ntx, nty, nz) { tx = ntx; ty = nty; z = clampZ(nz); schedule(); }
  function zoomAt(nz, sx = rect.width / 2, sy = rect.height / 2) {
    nz = clampZ(nz);
    const p = toPage(sx, sy);
    set(sx - p.x * nz, sy - p.y * nz, nz);
  }
  function animateTo(ntx, nty, nz, ms = 180) {
    cancelAnimationFrame(anim);
    nz = clampZ(nz);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || ms <= 0) { set(ntx, nty, nz); return; }
    const s0 = { tx, ty, z }, t0 = performance.now();
    // Interpolate in screen space of the target so the motion feels like one zoom.
    const step = (now) => {
      const k = Math.min(1, (now - t0) / ms), e = 1 - (1 - k) ** 3;
      const lz = Math.exp(Math.log(s0.z) + (Math.log(nz) - Math.log(s0.z)) * e);
      // Keep the canvas point that ends up at the viewport center moving smoothly.
      const cx = rect.width / 2, cy = rect.height / 2;
      const a = { x: (cx - s0.tx) / s0.z, y: (cy - s0.ty) / s0.z }, b = { x: (cx - ntx) / nz, y: (cy - nty) / nz };
      const px = a.x + (b.x - a.x) * e, py = a.y + (b.y - a.y) * e;
      set(cx - px * lz, cy - py * lz, lz);
      if (k < 1) anim = requestAnimationFrame(step);
    };
    anim = requestAnimationFrame(step);
  }
  function fitRect(b, { pad = 64, max = 1, animate = true } = {}) {
    if (!b || !(b.w >= 0) || !(b.h >= 0)) return;
    const W = Math.max(50, rect.width - pad * 2), H = Math.max(50, rect.height - pad * 2);
    const nz = clampZ(Math.min(max, W / Math.max(b.w, 1), H / Math.max(b.h, 1)));
    const ntx = rect.width / 2 - (b.x + b.w / 2) * nz, nty = rect.height / 2 - (b.y + b.h / 2) * nz;
    animate ? animateTo(ntx, nty, nz) : set(ntx, nty, nz);
  }

  function pagesBounds() {
    const ids = ctx.store.childIds(null);
    if (!ids.length) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const id of ids) {
      const b = ctx.boxOfPage(id);
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h);
    }
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }
  const fitAll = (animate = true) => fitRect(pagesBounds(), { max: 1, animate });
  function fitSelection() {
    const b = ctx.selectionBounds?.();
    if (b) fitRect(b, { max: MAX_ZOOM }); else fitAll();
  }
  function zoomToPage(id, animate = true) {
    if (!ctx.store.get(id)) return;
    ctx.setCurrentPage?.(id);
    fitRect(ctx.boxOfPage(id), { pad: 48, max: MAX_ZOOM, animate });
  }
  function stepPage(dir) {
    const pages = ctx.store.childIds(null);
    if (!pages.length) return;
    const cur = pages.indexOf(ctx.currentPage?.());
    const next = pages[(cur < 0 ? 0 : cur + dir + pages.length) % pages.length];
    zoomToPage(next);
  }
  function zoomStep(dir, anchor) {
    // Figma-like steps: double / halve, snapping to powers of two.
    const lv = Math.log2(z);
    const next = dir > 0 ? Math.floor(lv + 1e-6) + 1 : Math.ceil(lv - 1e-6) - 1;
    zoomAt(2 ** next, anchor?.x, anchor?.y);
  }

  // ---- wheel: pan, ⌘/Ctrl or pinch zoom ----
  container.addEventListener("wheel", (e) => {
    if (e.target.closest?.(".no-canvas-wheel")) return;
    e.preventDefault();
    cancelAnimationFrame(anim);
    const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    let dx = e.deltaX, dy = e.deltaY;
    if (e.deltaMode === 1) { dx *= 32; dy *= 32; } else if (e.deltaMode === 2) { dx *= rect.width; dy *= rect.height; }
    if (e.ctrlKey || e.metaKey) {
      const d = Math.max(-120, Math.min(120, dy));
      zoomAt(z * Math.exp(-d * (e.ctrlKey && !e.metaKey && Math.abs(dy) < 50 ? 0.012 : 0.0045)), sx, sy);
    } else {
      if (e.shiftKey && !dx) { dx = dy; dy = 0; }
      set(tx - dx, ty - dy, z);
    }
  }, { passive: false });

  // ---- drag pan: Space, H tool, middle button ----
  let spaceDown = false, panning = null;
  function wantsPan(e) { return e.button === 1 || (e.button === 0 && (spaceDown || ctx.tool === "hand")); }
  function handlePointerDown(e) {
    if (!wantsPan(e)) return false;
    e.preventDefault();
    cancelAnimationFrame(anim);
    panning = { x: e.clientX, y: e.clientY, tx, ty, id: e.pointerId };
    container.setPointerCapture?.(e.pointerId);
    container.classList.add("panning");
    return true;
  }
  container.addEventListener("pointermove", (e) => {
    if (!panning || e.pointerId !== panning.id) return;
    set(panning.tx + e.clientX - panning.x, panning.ty + e.clientY - panning.y, z);
  });
  const endPan = (e) => {
    if (!panning || e.pointerId !== panning.id) return;
    panning = null;
    container.classList.remove("panning");
    try { container.releasePointerCapture(e.pointerId); } catch (_) { /* already released */ }
  };
  container.addEventListener("pointerup", endPan);
  container.addEventListener("pointercancel", endPan);
  container.addEventListener("auxclick", (e) => { if (e.button === 1) e.preventDefault(); });
  function setSpace(v) { spaceDown = v; container.classList.toggle("space-pan", v); }

  // ---- pixel grid (⌘', visible at >= 400%) ----
  function drawGrid() {
    const on = ctx.flags.pixelGrid && z >= 4;
    grid.hidden = !on;
    if (!on) return;
    grid.style.backgroundSize = `${z}px ${z}px`;
    grid.style.backgroundPosition = `${tx % z}px ${ty % z}px`;
  }

  // ---- rulers (⇧R) ----
  const dpr = () => window.devicePixelRatio || 1;
  function sizeRulers() {
    const r = dpr();
    rulerTop.width = Math.max(1, rect.width * r); rulerTop.height = 20 * r;
    rulerLeft.width = 20 * r; rulerLeft.height = Math.max(1, rect.height * r);
  }
  sizeRulers();
  function drawRulers() {
    const on = ctx.flags.rulers;
    rulerTop.hidden = rulerLeft.hidden = rulerCorner.hidden = !on;
    if (!on) return;
    const css = getComputedStyle(container);
    const fg = css.getPropertyValue("--text-dim").trim() || "#888", bg = css.getPropertyValue("--panel").trim() || "#fff";
    const line = css.getPropertyValue("--border").trim() || "#ddd", acc = "#0D99FF";
    const pageId = ctx.currentPage?.();
    const origin = pageId && ctx.store.get(pageId) ? ctx.boxOfPage(pageId) : { x: 0, y: 0 };
    const steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000];
    const step = steps.find((s) => s * z >= 60) || 100000;
    const sel = ctx.selectionBounds?.();
    const draw = (cv, horiz) => {
      const g = cv.getContext("2d"), r = dpr();
      g.setTransform(r, 0, 0, r, 0, 0);
      const len = horiz ? rect.width : rect.height;
      g.fillStyle = bg; g.fillRect(0, 0, horiz ? len : 20, horiz ? 20 : len);
      if (sel) {
        const a = (horiz ? sel.x : sel.y) * z + (horiz ? tx : ty), b = (horiz ? sel.x + sel.w : sel.y + sel.h) * z + (horiz ? tx : ty);
        g.fillStyle = "rgba(13,153,255,0.18)";
        horiz ? g.fillRect(a, 0, b - a, 20) : g.fillRect(0, a, 20, b - a);
      }
      g.strokeStyle = line; g.beginPath();
      horiz ? (g.moveTo(0, 19.5), g.lineTo(len, 19.5)) : (g.moveTo(19.5, 0), g.lineTo(19.5, len));
      g.stroke();
      g.fillStyle = fg; g.strokeStyle = fg; g.font = "9px " + (css.getPropertyValue("--font") || "sans-serif");
      const o = horiz ? origin.x : origin.y, t = horiz ? tx : ty;
      const startU = Math.floor(((0 - t) / z - o) / step) * step;
      g.beginPath();
      for (let u = startU; ; u += step) {
        const px = Math.round((u + o) * z + t) + 0.5;
        if (px > len) break;
        for (let k = 1; k < 10; k++) {
          const mp = Math.round((u + o + (step * k) / 10) * z + t) + 0.5;
          const h = k === 5 ? 6 : 3;
          horiz ? (g.moveTo(mp, 20 - h), g.lineTo(mp, 20)) : (g.moveTo(20 - h, mp), g.lineTo(20, mp));
        }
        horiz ? (g.moveTo(px, 4), g.lineTo(px, 20)) : (g.moveTo(4, px), g.lineTo(20, px));
        const label = String(Math.round(u));
        if (horiz) g.fillText(label, px + 3, 10);
        else { g.save(); g.translate(10, px - 3); g.rotate(-Math.PI / 2); g.fillText(label, 0, 0); g.restore(); }
      }
      g.stroke();
      if (sel) {
        g.fillStyle = acc;
        const vals = horiz ? [sel.x, sel.x + sel.w] : [sel.y, sel.y + sel.h];
        for (const v of vals) {
          const px = v * z + t, label = String(Math.round(v - o));
          if (horiz) { g.fillText(label, px + 2, 18); }
          else { g.save(); g.translate(18, px - 2); g.rotate(-Math.PI / 2); g.fillText(label, 0, 0); g.restore(); }
        }
      }
    };
    draw(rulerTop, true);
    draw(rulerLeft, false);
  }

  function restore() {
    try {
      const v = JSON.parse(ls(viewKey) || "null");
      if (v && Number.isFinite(v.tx) && Number.isFinite(v.ty) && Number.isFinite(v.z)) { set(v.tx, v.ty, v.z); return true; }
    } catch (_) { /* ignore */ }
    return false;
  }

  return {
    get zoom() { return z; },
    get tx() { return tx; },
    get ty() { return ty; },
    get rect() { return rect; },
    get panning() { return !!panning; },
    get spaceDown() { return spaceDown; },
    pageToScreen: toScreen,
    screenToPage: toPage,
    clientToPage: (cx, cy) => toPage(cx - rect.left, cy - rect.top),
    clientToScreen: (cx, cy) => ({ x: cx - rect.left, y: cy - rect.top }),
    visibleRect() { const a = toPage(0, 0), b = toPage(rect.width, rect.height); return { x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y }; },
    center() { return toPage(rect.width / 2, rect.height / 2); },
    zoomTo: (nz, anchor) => zoomAt(nz, anchor?.x, anchor?.y),
    zoomStep, fitRect, fitAll, fitSelection, zoomToPage, stepPage, panBy: (dx, dy) => set(tx - dx, ty - dy, z),
    handlePointerDown, setSpace, restore, refresh: schedule, onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
}
