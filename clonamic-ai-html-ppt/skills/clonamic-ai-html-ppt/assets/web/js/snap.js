// Smart guides: snap edges/centers to siblings and parent, equal spacing, ⌥ measurement.
// Colors per figma-parity.md §9: guides/measure #F24822, spacing pink.

import { topLevel, boxOf, boxOfPage, get, isHidden } from "./select.js";

const GUIDE = "#F24822", SPACE = "#FF24BD", THRESH = 5;   // screen px

export function createSnapper(ctx) {
  let cands = [];            // {b, page}
  let guides = [];           // {axis:"x"|"y", v, a, b}
  let spacing = [];          // {axis, a, b, at, gap}

  function prepare(ids) {
    cands = [];
    const sel = new Set(ids);
    const tops = topLevel(ids);
    const view = ctx.viewport.visibleRect();
    const pad = Math.max(view.w, view.h);
    const near = (b) => b.x < view.x + view.w + pad && b.x + b.w > view.x - pad && b.y < view.y + view.h + pad && b.y + b.h > view.y - pad;
    const parents = new Set(tops.map((id) => get(id)?.parent ?? null));
    for (const pid of parents) {
      if (pid === null) {
        for (const pg of ctx.store.childIds(null)) if (!sel.has(pg)) cands.push({ b: boxOfPage(pg) });
        continue;
      }
      const pn = get(pid);
      if (pn) cands.push({ b: pn.type === "page" ? boxOfPage(pid) : boxOf(pid), parent: true });
      const kids = ctx.store.childIds(pid);
      for (const k of kids) {
        if (sel.has(k) || isHidden(k)) continue;
        const b = boxOf(k);
        if (b && near(b)) cands.push({ b });
        if (cands.length > 1500) break;   // ponytail: cap on huge parents; spatial index if decks get bigger
      }
    }
    clear();
  }
  function clear() { guides = []; spacing = []; }

  const T = () => THRESH / ctx.viewport.zoom;
  const xs = (b) => [b.x, b.x + b.w / 2, b.x + b.w];
  const ys = (b) => [b.y, b.y + b.h / 2, b.y + b.h];

  function bestEdge(vals, axis) {
    let best = null;
    const t = T();
    for (const c of cands) {
      const cv = axis === "x" ? xs(c.b) : ys(c.b);
      for (const v of vals) for (const w of cv) {
        const d = w - v;
        if (Math.abs(d) <= t && (!best || Math.abs(d) < Math.abs(best))) best = d;
      }
    }
    return best;
  }
  // Equal spacing along an axis: candidates in the same row/column as the box.
  function bestSpacing(box, axis) {
    const t = T();
    const lo = axis === "x" ? "x" : "y", sz = axis === "x" ? "w" : "h", olo = axis === "x" ? "y" : "x", osz = axis === "x" ? "h" : "w";
    const row = cands.filter((c) => !c.parent && c.b[olo] < box[olo] + box[osz] && c.b[olo] + c.b[osz] > box[olo]).map((c) => c.b);
    if (!row.length) return null;
    row.sort((a, b) => a[lo] - b[lo]);
    const gaps = [];
    for (let i = 0; i < row.length - 1; i++) {
      const g = row[i + 1][lo] - (row[i][lo] + row[i][sz]);
      if (g > 0) gaps.push({ g, a: row[i], b: row[i + 1] });
    }
    const before = row.filter((b) => b[lo] + b[sz] <= box[lo] + t).pop();
    const after = row.find((b) => b[lo] >= box[lo] + box[sz] - t);
    let best = null;
    const consider = (pos, info) => { const d = pos - box[lo]; if (Math.abs(d) <= t && (!best || Math.abs(d) < Math.abs(best.d))) best = { d, ...info }; };
    if (before && after) {
      const g = (after[lo] - (before[lo] + before[sz]) - box[sz]) / 2;
      if (g > 0) consider(before[lo] + before[sz] + g, { g, mode: "between", before, after });
    }
    for (const gp of gaps) {
      if (before) consider(before[lo] + before[sz] + gp.g, { g: gp.g, mode: "after", before, ref: gp });
      if (after) consider(after[lo] - gp.g - box[sz], { g: gp.g, mode: "before", after, ref: gp });
    }
    return best;
  }

  function guidesFor(box, axis) {
    const out = [], e = 0.5 / ctx.viewport.zoom;
    const vals = axis === "x" ? xs(box) : ys(box);
    for (const v of vals) {
      let a = axis === "x" ? box.y : box.x, b = axis === "x" ? box.y + box.h : box.x + box.w, hit = false;
      for (const c of cands) {
        const cv = axis === "x" ? xs(c.b) : ys(c.b);
        if (cv.some((w) => Math.abs(w - v) < e)) {
          hit = true;
          a = Math.min(a, axis === "x" ? c.b.y : c.b.x); b = Math.max(b, axis === "x" ? c.b.y + c.b.h : c.b.x + c.b.w);
        }
      }
      if (hit) out.push({ axis, v, a, b });
    }
    return out;
  }

  function move(box, { lockX, lockY } = {}) {
    clear();
    let dx = 0, dy = 0;
    for (const axis of ["x", "y"]) {
      if ((axis === "x" && lockX) || (axis === "y" && lockY)) continue;
      const edge = bestEdge(axis === "x" ? xs(box) : ys(box), axis);
      const sp = bestSpacing(box, axis);
      let d = 0, spUse = null;
      if (sp && (edge === null || Math.abs(sp.d) < Math.abs(edge) - 1e-6)) { d = sp.d; spUse = sp; }
      else if (edge !== null) d = edge;
      if (axis === "x") dx = d; else dy = d;
      if (spUse) markSpacing(spUse, axis, { ...box, x: box.x + (axis === "x" ? d : 0), y: box.y + (axis === "y" ? d : 0) });
    }
    const fin = { x: box.x + dx, y: box.y + dy, w: box.w, h: box.h };
    guides = [...guidesFor(fin, "x"), ...guidesFor(fin, "y")];
    if (ctx.flags.snapPixel) {
      // Keep the snapped result on whole pixels.
      dx = Math.round(fin.x) - box.x; dy = Math.round(fin.y) - box.y;
      if (Math.abs(fin.x - Math.round(fin.x)) > 1e-6 && guides.some((g) => g.axis === "x")) dx = fin.x - box.x;
      if (Math.abs(fin.y - Math.round(fin.y)) > 1e-6 && guides.some((g) => g.axis === "y")) dy = fin.y - box.y;
    }
    return { dx, dy };
  }
  function markSpacing(sp, axis, box) {
    const lo = axis === "x" ? "x" : "y", sz = axis === "x" ? "w" : "h";
    const seg = (a, b) => {
      const s = a[lo] + a[sz], e = b[lo];
      const ol = axis === "x" ? Math.max(a.y, b.y) : Math.max(a.x, b.x), oh = axis === "x" ? Math.min(a.y + a.h, b.y + b.h) : Math.min(a.x + a.w, b.x + b.w);
      spacing.push({ axis, s, e, at: ol < oh ? (ol + oh) / 2 : axis === "x" ? b.y + b.h / 2 : b.x + b.w / 2, gap: e - s });
    };
    if (sp.mode === "between") { seg(sp.before, box); seg(box, sp.after); }
    else if (sp.mode === "after") { seg(sp.before, box); seg(sp.ref.a, sp.ref.b); }
    else { seg(box, sp.after); seg(sp.ref.a, sp.ref.b); }
  }

  // Snap one moving point (resize handle, line end). axes: which coordinates may snap.
  function point(pt, axes = { x: true, y: true }) {
    clear();
    const t = T();
    let dx = 0, dy = 0, bx = null, by = null;
    for (const c of cands) {
      if (axes.x) for (const w of xs(c.b)) { const d = w - pt.x; if (Math.abs(d) <= t && (bx === null || Math.abs(d) < Math.abs(bx))) bx = d; }
      if (axes.y) for (const w of ys(c.b)) { const d = w - pt.y; if (Math.abs(d) <= t && (by === null || Math.abs(d) < Math.abs(by))) by = d; }
    }
    if (bx !== null) dx = bx;
    if (by !== null) dy = by;
    const p = { x: pt.x + dx, y: pt.y + dy, w: 0, h: 0 };
    guides = [...(bx !== null ? guidesFor(p, "x") : []), ...(by !== null ? guidesFor(p, "y") : [])].filter((g, i, a) => a.findIndex((h) => h.axis === g.axis && h.v === g.v) === i);
    return { dx, dy };
  }

  function draw(svg, toS) {
    for (const g of guides) {
      const a = g.axis === "x" ? toS({ x: g.v, y: g.a }) : toS({ x: g.a, y: g.v });
      const b = g.axis === "x" ? toS({ x: g.v, y: g.b }) : toS({ x: g.b, y: g.v });
      svg.append(line(a, b, GUIDE));
      for (const q of [a, b]) svg.append(cross(q, GUIDE));
    }
    for (const sp of spacing) {
      const a = sp.axis === "x" ? toS({ x: sp.s, y: sp.at }) : toS({ x: sp.at, y: sp.s });
      const b = sp.axis === "x" ? toS({ x: sp.e, y: sp.at }) : toS({ x: sp.at, y: sp.e });
      svg.append(line(a, b, SPACE));
      label(svg, (a.x + b.x) / 2, (a.y + b.y) / 2 + 6, fmt(sp.gap), SPACE);
    }
  }

  // ⌥ hover: red distance lines from the selection box a to box b (the hovered layer or the parent).
  function drawMeasure(svg, toS, a, b, inside) {
    if (!a || !b) return;
    const segs = [];
    const contains = b.x <= a.x && b.y <= a.y && b.x + b.w >= a.x + a.w && b.y + b.h >= a.y + a.h;
    const midY = a.y + a.h / 2, midX = a.x + a.w / 2;
    if (inside || contains) {
      segs.push(["x", b.x, a.x, midY], ["x", a.x + a.w, b.x + b.w, midY], ["y", b.y, a.y, midX], ["y", a.y + a.h, b.y + b.h, midX]);
    } else {
      const oy0 = Math.max(a.y, b.y), oy1 = Math.min(a.y + a.h, b.y + b.h), ox0 = Math.max(a.x, b.x), ox1 = Math.min(a.x + a.w, b.x + b.w);
      const ry = oy0 < oy1 ? (oy0 + oy1) / 2 : midY, rx = ox0 < ox1 ? (ox0 + ox1) / 2 : midX;
      if (b.x >= a.x + a.w) segs.push(["x", a.x + a.w, b.x, ry]);
      else if (b.x + b.w <= a.x) segs.push(["x", b.x + b.w, a.x, ry]);
      if (b.y >= a.y + a.h) segs.push(["y", a.y + a.h, b.y, rx]);
      else if (b.y + b.h <= a.y) segs.push(["y", b.y + b.h, a.y, rx]);
      if (!segs.length) segs.push(["x", Math.min(a.x, b.x), Math.max(a.x, b.x), midY], ["y", Math.min(a.y, b.y), Math.max(a.y, b.y), midX]);
    }
    // outline the target
    const q = [toS({ x: b.x, y: b.y }), toS({ x: b.x + b.w, y: b.y }), toS({ x: b.x + b.w, y: b.y + b.h }), toS({ x: b.x, y: b.y + b.h })];
    svg.append(svgEl("polygon", { points: q.map((p) => `${p.x},${p.y}`).join(" "), fill: "none", stroke: GUIDE, "stroke-width": 1 }));
    for (const [axis, s, e, at] of segs) {
      if (Math.abs(e - s) < 1e-6) continue;
      const p0 = axis === "x" ? toS({ x: s, y: at }) : toS({ x: at, y: s });
      const p1 = axis === "x" ? toS({ x: e, y: at }) : toS({ x: at, y: e });
      svg.append(line(p0, p1, GUIDE));
      label(svg, (p0.x + p1.x) / 2, (p0.y + p1.y) / 2 + (axis === "x" ? 6 : -8), fmt(Math.abs(e - s)), GUIDE);
    }
  }

  return { prepare, move, point, clear, draw, drawMeasure };
}

const fmt = (v) => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1));
function svgEl(tag, attrs) { const n = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; }
const line = (a, b, color) => svgEl("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: color, "stroke-width": 1, "shape-rendering": "crispEdges" });
const cross = (p, color) => svgEl("path", { d: `M${p.x - 2.5},${p.y - 2.5}L${p.x + 2.5},${p.y + 2.5}M${p.x + 2.5},${p.y - 2.5}L${p.x - 2.5},${p.y + 2.5}`, stroke: color, "stroke-width": 1 });
function label(svg, x, y, text, color) {
  const w = Math.max(20, text.length * 6.4 + 8);
  const g = svgEl("g", { class: "ov-badge" });
  g.append(svgEl("rect", { x: x - w / 2, y: y - 1, width: w, height: 15, rx: 3, fill: color }));
  const t = svgEl("text", { x, y: y + 10, "text-anchor": "middle" });
  t.textContent = text;
  g.append(t);
  svg.append(g);
}
