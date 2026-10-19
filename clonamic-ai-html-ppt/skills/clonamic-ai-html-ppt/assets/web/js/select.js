// Selection, hit testing, transforms (move/resize/rotate/duplicate/reparent), vector edit mode, overlay.
// Also the geometry helpers the other editor modules share (matrices, boxes, group box recompute).

import { propsOf, newId, zBetween, zSeq, isContainer } from "./schema.js";
import { resizeOps } from "./layout.js";
import { beginTextEdit, editingId } from "./text.js";
import { normalize } from "./render.js";
import * as G from "./geometry.js";
import { el, toast } from "./ui.js";

let C = null;                      // editor ctx (main.js)
export const previews = new Map(); // id -> merged preview props (mirror of renderer previews)
const ACCENT = "#0D99FF";
const R2D = 180 / Math.PI;
const r3 = (v) => Math.round(v * 1000) / 1000;

// ---------------- matrices ----------------
export const I = [1, 0, 0, 1, 0, 0];
export const mul = (m, n) => [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
  m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
export function inv(m) {
  const d = m[0] * m[3] - m[1] * m[2];
  if (!d) return I;
  return [m[3] / d, -m[1] / d, -m[2] / d, m[0] / d, (m[2] * m[5] - m[3] * m[4]) / d, (m[1] * m[4] - m[0] * m[5]) / d];
}
export const ap = (m, x, y) => ({ x: m[0] * x + m[2] * y + m[4], y: m[1] * x + m[3] * y + m[5] });
export const apv = (m, x, y) => ({ x: m[0] * x + m[2] * y, y: m[1] * x + m[3] * y });
// local box -> parent: translate to x,y; rotate (clockwise degrees) and flip around the box center.
export function localM(g) {
  const r = (g.rotation || 0) / R2D, c = Math.cos(r), s = Math.sin(r);
  const fx = g.flipX ? -1 : 1, fy = g.flipY ? -1 : 1;
  const a = c * fx, b = s * fx, cc = -s * fy, d = c * fy, hw = g.w / 2, hh = g.h / 2;
  return [a, b, cc, d, g.x + hw - (a * hw + cc * hh), g.y + hh - (b * hw + d * hh)];
}
export const normDeg = (a) => { a = ((a + 180) % 360 + 360) % 360 - 180; return a === -180 ? 180 : a; };

// ---------------- node geometry ----------------
export const get = (id) => C.store.get(id);
// Resolved props (+ live preview), nested objects filled from defaults (W2 normalize).
const normCache = new WeakMap();
export function P(id) {
  const n = C.store.get(id);
  if (!n) return null;
  const p = propsOf(n), pv = previews.get(id);
  if (pv) return normalize(n.type, { ...p, ...pv });
  let q = normCache.get(p);
  if (!q) { q = normalize(n.type, p); normCache.set(p, q); }
  return q;
}
const mcache = new Map();
export function clearMeasureCache() { mcache.clear(); }
function measure(id) {
  if (mcache.has(id)) return mcache.get(id);
  let m = null;
  try { m = C.renderer.measure?.(id) || null; } catch (_) { m = null; }
  if (m && !(Number.isFinite(m.w) && Number.isFinite(m.h))) m = null;
  mcache.set(id, m);
  return m;
}
function inFlow(n, getP) {
  if (!n.parent) return false;
  const pn = getNode(n.parent);
  if (!pn || !["frame", "page"].includes(pn.type)) return false;
  const pp = getP(pn);
  return !!pp.layout && pp.layout.dir !== "NONE" && !getP(n).layoutChild?.absolute;
}
let getNode = (id) => C.store.get(id);
function autoW(n, p, flow) {
  if (n.type === "text") return p.autoResize === "WIDTH_AND_HEIGHT";
  if (p.layout && p.layout.dir !== "NONE" && p.layout.sizingH === "HUG") return true;
  return flow && p.layoutChild && p.layoutChild.sizingH !== "FIXED";
}
function autoH(n, p, flow) {
  if (n.type === "text") return p.autoResize === "WIDTH_AND_HEIGHT" || p.autoResize === "HEIGHT";
  if (p.layout && p.layout.dir !== "NONE" && p.layout.sizingV === "HUG") return true;
  return flow && p.layoutChild && p.layoutChild.sizingV !== "FIXED";
}
// {x,y,w,h,rotation,flipX,flipY} of a node in its parent's coordinates (pages: canvas, at cx,cy).
export function geomOf(n, p) {
  if (n.type === "page") return { x: p.cx || 0, y: p.cy || 0, w: p.w, h: p.h, rotation: 0, flipX: false, flipY: false };
  let { x, y, w, h } = p;
  const getP = (nn) => (nn.id === n.id ? p : resolvedOf(nn));
  const flow = inFlow(n, getP);
  if (autoW(n, p, flow) || autoH(n, p, flow) || flow) {
    const m = measure(n.id);
    if (m) {
      if (autoW(n, p, flow)) w = m.w;
      if (autoH(n, p, flow)) h = m.h;
      if (flow) {
        const pm = measure(n.parent);
        x = m.x - (pm ? pm.x : 0); y = m.y - (pm ? pm.y : 0);
      }
    }
  }
  return { x: x || 0, y: y || 0, w: Math.max(0, w || 0), h: Math.max(0, h || 0), rotation: p.rotation || 0, flipX: !!p.flipX, flipY: !!p.flipY };
}
let resolvedOf = (n) => P(n.id) || propsOf(n);
export const geom = (id) => { const n = get(id); return n ? geomOf(n, P(id)) : null; };
export function worldM(id) {
  const n = get(id);
  if (!n) return I;
  const g = geom(id);
  if (n.type === "page") return [1, 0, 0, 1, g.x, g.y];
  return mul(worldM(n.parent), localM(g));
}
export const parentM = (id) => { const n = get(id); return n && n.parent ? worldM(n.parent) : I; };
export function worldRot(id) {
  let r = 0;
  for (let n = get(id); n && n.type !== "page"; n = get(n.parent)) r += P(n.id).rotation || 0;
  return r;
}
export function cornersOf(id) {
  const g = geom(id), M = worldM(id);
  if (!g) return [];
  if (get(id).type === "page") return [{ x: g.x, y: g.y }, { x: g.x + g.w, y: g.y }, { x: g.x + g.w, y: g.y + g.h }, { x: g.x, y: g.y + g.h }];
  return [ap(M, 0, 0), ap(M, g.w, 0), ap(M, g.w, g.h), ap(M, 0, g.h)];
}
export function aabbOf(pts) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of pts) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); }
  return x0 === Infinity ? null : { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}
export const boxOf = (id) => aabbOf(cornersOf(id));
export const unionBox = (ids) => aabbOf(ids.flatMap((id) => cornersOf(id)));
export function boxOfPage(id) { const p = P(id); return { x: p.cx || 0, y: p.cy || 0, w: p.w, h: p.h }; }
export const toLocal = (parentId, pt) => (parentId ? ap(inv(worldM(parentId)), pt.x, pt.y) : pt);
// New box (in the node's own unrotated local frame) -> {x,y,w,h} in parent coordinates, same rotation/flip.
export function reframe(g, bx, by, bw, bh) {
  const c = ap(localM(g), bx + bw / 2, by + bh / 2);
  return { x: c.x - bw / 2, y: c.y - bh / 2, w: bw, h: bh };
}
export function ancestors(id) {
  const out = [];
  for (let n = get(get(id)?.parent); n; n = get(n.parent)) out.push(n.id);
  return out;
}
export const isLocked = (id) => { for (let n = get(id); n; n = get(n.parent)) if (P(n.id).locked) return true; return false; };
export const isHidden = (id) => { for (let n = get(id); n; n = get(n.parent)) if (P(n.id).visible === false) return true; return false; };
// Drop nodes whose ancestor is also in the list; keep layer order (bottom -> top).
export function topLevel(ids) {
  const set = new Set(ids);
  return ids.filter((id) => get(id) && !ancestors(id).some((a) => set.has(a)));
}
export function sortByOrder(ids) {
  const key = (id) => [...ancestors(id).reverse(), id].map((a) => get(a)?.z || "");
  const pageIdx = new Map(C.store.childIds(null).map((p, i) => [p, i]));
  return [...ids].sort((a, b) => {
    const pa = pageIdx.get(C.store.pageIdOf(a)) ?? 0, pb = pageIdx.get(C.store.pageIdOf(b)) ?? 0;
    if (pa !== pb) return pa - pb;
    const ka = key(a), kb = key(b);
    for (let i = 0; i < Math.min(ka.length, kb.length); i++) if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
    return ka.length - kb.length;
  });
}
export function selectionBounds(ids = C?.selection.ids) {
  if (!ids || !ids.length) return null;
  return unionBox(ids.filter((id) => get(id)));
}
// Placement props {x, y, rotation} that keep a node visually in place under a new parent.
export function placeIn(id, newParent, { center, rotDelta = 0 } = {}) {
  const g = geom(id);
  const c = center || ap(worldM(id), g.w / 2, g.h / 2);
  const lc = toLocal(newParent, c);
  const rot = normDeg(worldRot(id) + rotDelta - worldRot(newParent));
  return { x: r3(lc.x - g.w / 2), y: r3(lc.y - g.h / 2), rotation: r3(rot) };
}

// ---------------- simulated view over pending ops (for group box recompute) ----------------
function makeView(ops) {
  const over = new Map();
  const vget = (id) => { if (over.has(id)) { const o = over.get(id); return o.deleted ? null : o; } return C.store.get(id); };
  const view = {
    get: vget,
    apply(op) {
      if (op.op === "add") over.set(op.node.id, { id: op.node.id, type: op.node.type, parent: op.node.parent ?? null, z: op.node.z, props: { ...(op.node.props || {}) } });
      else if (op.op === "set") {
        const n = vget(op.id); if (!n) return;
        const props = { ...n.props };
        for (const [k, v] of Object.entries(op.props || {})) { if (v === null) delete props[k]; else props[k] = v; }
        over.set(op.id, { ...n, props });
      } else if (op.op === "move") { const n = vget(op.id); if (n) over.set(op.id, { ...n, parent: op.parent ?? null }); }
      else if (op.op === "del") { const n = vget(op.id); if (n) over.set(op.id, { ...n, deleted: true }); }
    },
    children(pid) {
      const out = C.store.childIds(pid).filter((id) => { const n = vget(id); return n && n.parent === pid; });
      for (const [id, o] of over) if (!o.deleted && o.parent === pid && !out.includes(id)) out.push(id);
      return out;
    },
    oldParent: (id) => C.store.get(id)?.parent ?? null,
  };
  ops.forEach((o) => view.apply(o));
  return view;
}
function viewGeom(view, id) {
  const n = view.get(id);
  const prevNode = getNode, prevRes = resolvedOf;
  getNode = (x) => view.get(x);
  resolvedOf = (nn) => propsOf(nn);
  try { return geomOf(n, propsOf(n)); } finally { getNode = prevNode; resolvedOf = prevRes; }
}
// Groups and booleans keep x/y/w/h equal to their children's union (format.md §1). Returns ops + fixes.
export function fixGroups(ops) {
  if (!ops?.length || !C) return ops;
  const view = makeView(ops);
  const groups = new Set();
  const climb = (pid) => { for (let n = view.get(pid); n; n = view.get(n.parent)) if (n.type === "group" || n.type === "boolean") groups.add(n.id); };
  for (const op of ops) {
    const id = op.id || op.node?.id;
    if (!id) continue;
    climb(view.get(id)?.parent);
    climb(view.oldParent(id));
  }
  if (!groups.size) return ops;
  const depth = (id) => { let d = 0; for (let n = view.get(id); n; n = view.get(n.parent)) d++; return d; };
  const extra = [];
  for (const gid of [...groups].sort((a, b) => depth(b) - depth(a))) {
    const gn = view.get(gid);
    if (!gn) continue;
    const kids = view.children(gid);
    if (!kids.length) { const o = { op: "del", id: gid }; extra.push(o); view.apply(o); continue; }
    const u = aabbOf(kids.flatMap((k) => { const g = viewGeom(view, k); const M = localM(g); return [ap(M, 0, 0), ap(M, g.w, 0), ap(M, g.w, g.h), ap(M, 0, g.h)]; }));
    const g = viewGeom(view, gid);
    if (!u || (Math.abs(u.x) < 1e-3 && Math.abs(u.y) < 1e-3 && Math.abs(u.w - g.w) < 1e-3 && Math.abs(u.h - g.h) < 1e-3)) continue;
    const box = reframe(g, u.x, u.y, u.w, u.h);
    const so = { op: "set", id: gid, props: { x: r3(box.x), y: r3(box.y), w: r3(box.w), h: r3(box.h) } };
    extra.push(so); view.apply(so);
    for (const k of kids) {
      const kp = propsOf(view.get(k));
      const ko = { op: "set", id: k, props: { x: r3((kp.x || 0) - u.x), y: r3((kp.y || 0) - u.y) } };
      extra.push(ko); view.apply(ko);
    }
  }
  return extra.length ? ops.concat(extra) : ops;
}

// ---------------- cloning (duplicate, ⌥-drag, paste) ----------------
// Clones each root subtree with new ids. Roots land right above their originals unless opts.parent is given.
export function cloneOps(roots, { parent, offset = { x: 0, y: 0 }, propsFor } = {}) {
  const ops = [], map = new Map(), newRoots = [];
  const byParent = new Map();
  for (const id of roots) { const p = parent ?? get(id).parent; if (!byParent.has(p)) byParent.set(p, []); byParent.get(p).push(id); }
  for (const [pid, ids] of byParent) {
    const sibs = C.store.childIds(pid);
    const zs = new Map();
    if (parent !== undefined) {
      const top = sibs.length ? get(sibs[sibs.length - 1]).z : null;
      zSeq(top, null, ids.length).forEach((z, i) => zs.set(ids[i], z));
    } else {
      // Above each original, below the original's next sibling (several clones of one gap stay ordered).
      for (const id of ids) {
        const i = sibs.indexOf(id);
        const next = sibs[i + 1] ? get(sibs[i + 1]).z : null;
        zs.set(id, zBetween(get(id).z, next));
      }
    }
    for (const id of ids) {
      const walk = (oid, np, z, root) => {
        const n = get(oid);
        const nid = newId(n.type);
        map.set(oid, nid);
        const props = structuredClone(n.props);
        if (root) {
          if (n.type === "page") { props.cx = (props.cx || 0) + offset.x; props.cy = (props.cy || 0) + offset.y; }
          else { props.x = r3((props.x || 0) + offset.x); props.y = r3((props.y || 0) + offset.y); }
          Object.assign(props, propsFor?.(oid) || {});
        }
        ops.push({ op: "add", node: { id: nid, type: n.type, parent: np, z, props } });
        for (const c of C.store.childIds(oid)) walk(c, nid, get(c).z, false);
        return nid;
      };
      newRoots.push(walk(id, get(id).type === "page" ? null : pid, zs.get(id), true));
    }
  }
  return { ops, map, roots: newRoots };
}

// ---------------- resize helpers ----------------
function scalePaths(paths, sx, sy) {
  return (paths || []).map((pa) => ({ ...pa, pts: (pa.pts || []).map((q) => ({ x: q.x * sx, y: q.y * sy, ix: (q.ix ?? q.x) * sx, iy: (q.iy ?? q.y) * sy, ox: (q.ox ?? q.x) * sx, oy: (q.oy ?? q.y) * sy })) }));
}
function scaleStyle(type, p, s) {
  const out = {};
  if (p.stroke && p.strokes?.length) out.stroke = { ...p.stroke, weight: r3(p.stroke.weight * s) };
  if (typeof p.radius === "number") out.radius = r3(p.radius * s);
  else if (Array.isArray(p.radius)) out.radius = p.radius.map((v) => r3(v * s));
  if (p.effects?.length) out.effects = p.effects.map((e) => ({ ...e, ...(e.blur != null ? { blur: r3(e.blur * s) } : {}), ...(e.x != null ? { x: r3(e.x * s), y: r3(e.y * s) } : {}),
    ...(e.spread != null ? { spread: r3(e.spread * s) } : {}), ...(e.radius != null ? { radius: r3(e.radius * s) } : {}) }));
  if (type === "text") {
    out.style = { ...p.style, size: Math.max(1, r3(p.style.size * s)) };
    if (p.runs?.some((r) => r.s?.size)) out.runs = p.runs.map((r) => (r.s?.size ? { ...r, s: { ...r.s, size: Math.max(1, r3(r.s.size * s)) } } : r));
  }
  if (p.layout) out.layout = { ...p.layout, gap: r3(p.layout.gap * s), gapCross: r3((p.layout.gapCross || 0) * s), pad: (p.layout.pad || [0, 0, 0, 0]).map((v) => r3(v * s)) };
  if (type === "table") { out.cols = p.cols.map((v) => r3(v * s)); out.rows = p.rows.map((v) => r3(v * s)); }
  return out;
}
// Scale every descendant's box by (sx, sy) about its parent's origin (groups, booleans, scale tool).
function scaleChildren(id, sx, sy, s, ops) {
  for (const c of C.store.childIds(id)) {
    const n = get(c), p = P(c), g = geom(c);
    const props = { x: r3(p.x * sx), y: r3(p.y * sy), w: r3(g.w * sx), h: r3(n.type === "line" ? 0 : g.h * sy) };
    if (n.type === "vector") props.paths = scalePaths(p.paths, sx, sy);
    if (n.type === "text" && !s && p.autoResize !== "NONE") props.autoResize = "NONE";
    if (s) Object.assign(props, scaleStyle(n.type, p, s));
    ops.push({ op: "set", id: c, props });
    scaleChildren(c, sx, sy, s, ops);
  }
}
// Ops resizing one node to g1 (parent coordinates). opts: {ignoreConstraints, scale (K tool)}.
export function resizeNodeOps(id, g1, opts = {}) {
  const n = get(id), p = P(id), g0 = geom(id);
  const sx = g0.w ? g1.w / g0.w : 1, sy = g0.h ? g1.h / g0.h : 1;
  const props = n.type === "page" ? { cx: r3(g1.x), cy: r3(g1.y), w: r3(g1.w), h: r3(g1.h) } : { x: r3(g1.x), y: r3(g1.y), w: r3(g1.w), h: r3(n.type === "line" ? 0 : g1.h) };
  if (g1.flipX !== undefined && g1.flipX !== g0.flipX) props.flipX = g1.flipX;
  if (g1.flipY !== undefined && g1.flipY !== g0.flipY) props.flipY = g1.flipY;
  if (n.type === "page" && (Math.abs(g1.w - g0.w) > 0.01 || Math.abs(g1.h - g0.h) > 0.01)) { props.preset = "CUSTOM"; props.orientation = g1.w >= g1.h ? "landscape" : "portrait"; }
  if (n.type === "text" && !opts.scale) {
    const dw = Math.abs(g1.w - g0.w) > 0.01, dh = Math.abs(g1.h - g0.h) > 0.01;
    if (p.autoResize === "WIDTH_AND_HEIGHT" && (dw || dh)) props.autoResize = dh ? "NONE" : "HEIGHT";
    else if (p.autoResize === "HEIGHT" && dh) props.autoResize = "NONE";
  }
  if (p.layout && p.layout.dir !== "NONE") {
    if (Math.abs(g1.w - g0.w) > 0.01 && p.layout.sizingH === "HUG") props.layout = { ...p.layout, sizingH: "FIXED" };
    if (Math.abs(g1.h - g0.h) > 0.01 && p.layout.sizingV === "HUG") props.layout = { ...(props.layout || p.layout), sizingV: "FIXED" };
  }
  if (n.type === "vector") props.paths = scalePaths(p.paths, sx, sy);
  const s = opts.scale ? Math.sqrt(Math.abs(sx * sy)) : 0;
  if (s) Object.assign(props, scaleStyle(n.type, p, s), props.layout ? { layout: { ...scaleStyle(n.type, p, s).layout, sizingH: props.layout.sizingH, sizingV: props.layout.sizingV } } : {});
  const ops = [{ op: "set", id, props }];
  if (n.type === "group" || n.type === "boolean" || (opts.scale && isContainer(n.type))) scaleChildren(id, sx, sy, s, ops);
  else if (isContainer(n.type) && n.type !== "group") {
    try {
      const more = resizeOps(C.store, id, { x: g1.x, y: g1.y, w: g1.w, h: g1.h }, { ignoreConstraints: !!opts.ignoreConstraints }) || [];
      for (const o of more) if (!(o.op === "set" && o.id === id)) ops.push(o);
    } catch (e) { console.warn("resizeOps", e); }
  }
  return ops;
}

// ---------------- hit testing ----------------
function chainOf(id) { return [...ancestors(id).reverse(), id]; }
// Topmost unlocked node under a client point (deepest element), or null.
export function leafAt(cx, cy) {
  const root = C.docRoot;
  for (const elx of document.elementsFromPoint(cx, cy)) {
    if (!root.contains(elx)) continue;
    const hit = elx.closest("[data-id]");
    if (!hit || !root.contains(hit)) continue;
    const id = hit.dataset.id;
    if (!get(id) || isLocked(id) || isHidden(id)) continue;
    if (C.textEdit && C.textEdit.id === id) return id;
    return id;
  }
  return null;
}
export function nodesUnder(cx, cy) {
  const out = [], root = C.docRoot;
  for (const elx of document.elementsFromPoint(cx, cy)) {
    if (!root.contains(elx)) continue;
    const hit = elx.closest("[data-id]");
    const id = hit?.dataset.id;
    if (id && get(id) && !out.includes(id)) out.push(id);
  }
  return out;
}
// Figma rule: a click picks the top-level child of the page (sections are transparent), or the
// child at the depth the user already entered; ⌘ picks the deepest layer.
export function pickAt(cx, cy, deep = false) {
  const leaf = leafAt(cx, cy);
  if (!leaf) return null;
  const chain = chainOf(leaf);
  if (deep) return get(leaf).type === "page" ? null : leaf;
  let idx = 1;
  while (idx < chain.length - 1 && get(chain[idx]).type === "section") idx++;
  for (const s of C.selection.ids) {
    const n = get(s);
    if (!n) continue;
    const i = chain.indexOf(n.parent);
    if (i >= 0 && i + 1 < chain.length && get(n.parent).type !== "page") idx = Math.max(idx, i + 1);
    const j = chain.indexOf(s);
    if (j >= 0) idx = Math.max(idx, j);
  }
  return chain[idx] && get(chain[idx]).type !== "page" ? chain[idx] : null;
}
export function pageAt(pt) {
  const pages = C.store.childIds(null);
  for (let i = pages.length - 1; i >= 0; i--) {
    const b = boxOfPage(pages[i]);
    if (pt.x >= b.x && pt.y >= b.y && pt.x <= b.x + b.w && pt.y <= b.y + b.h && !P(pages[i]).locked) return pages[i];
  }
  return null;
}
// Deepest frame/section/page under a canvas point, ignoring the given ids' subtrees.
export function containerAt(pt, exclude = new Set(), client) {
  const ex = (id) => exclude.has(id) || ancestors(id).some((a) => exclude.has(a));
  let best = null;
  if (client) {
    const root = C.docRoot;
    for (const elx of document.elementsFromPoint(client.x, client.y)) {
      if (!root.contains(elx)) continue;
      const hit = elx.closest("[data-id]");
      if (!hit) continue;
      for (const id of chainOf(hit.dataset.id).reverse()) {
        const n = get(id);
        if (!n || ex(id) || !["frame", "section", "page"].includes(n.type) || isLocked(id)) continue;
        if (!insideNode(id, pt)) continue;
        best = id; break;
      }
      if (best) break;
    }
  }
  return best || pageAt(pt);
}
function insideNode(id, pt) {
  const g = geom(id), q = ap(inv(worldM(id)), pt.x, pt.y);
  return q.x >= 0 && q.y >= 0 && q.x <= g.w && q.y <= g.h;
}

// ---------------- text editing ----------------
export function beginText(id, opts = {}) {
  endText();
  const n = get(id);
  if (!n || (n.type !== "text" && n.type !== "table")) return;
  C.selection.set([id]);
  try {
    const o = {};
    if (opts.cell) o.cell = opts.cell;
    if (opts.point) o.point = opts.point;
    if (opts.select) o.select = opts.select;
    const handle = beginTextEdit(id, C, o);
    C.textEdit = { id, handle, created: !!opts.created };
    C.docRoot.classList.add("editing-text");
  } catch (e) { console.error(e); toast("텍스트를 편집할 수 없습니다."); }
  requestDraw();
}
// text.js may end the session itself (Esc, blur); keep our flag in step.
export function syncText() {
  if (C?.textEdit && editingId() !== C.textEdit.id) {
    const te = C.textEdit;
    C.textEdit = null;
    C.docRoot.classList.remove("editing-text");
    afterText(te);
    requestDraw();
  }
}
function afterText(te) {
  // A text layer left empty is removed (Figma). text.js usually does it already.
  setTimeout(() => {
    const n = get(te.id);
    if (n && n.type === "text") {
      const txt = (P(te.id).runs || []).map((r) => r.t).join("");
      if (!txt.trim()) { C.selection.set(C.selection.ids.filter((i) => i !== te.id)); C.commit([{ op: "del", id: te.id }], "빈 텍스트 삭제"); }
    }
  }, 0);
}
export function endText() {
  const te = C?.textEdit;
  if (!te) return;
  C.textEdit = null;
  C.docRoot.classList.remove("editing-text");
  try { te.handle?.end?.(); } catch (e) { console.error(e); }
  afterText(te);
  requestDraw();
}

// ---------------- selection navigation ----------------
export function selectDeeper() {
  const ids = C.selection.ids;
  if (ids.length !== 1) return;
  const id = ids[0], n = get(id);
  if (n.type === "text") return beginText(id);
  if (["vector", "polygon", "star"].includes(n.type)) return enterVectorEdit(id);
  const kids = C.store.childIds(id).filter((k) => !isLocked(k));
  if (kids.length) C.selection.set(kids);
}
export function selectParent() {
  const ids = C.selection.ids;
  if (!ids.length) return;
  const par = [...new Set(ids.map((id) => get(id)?.parent).filter(Boolean))];
  if (par.length) C.selection.set(par);
}
export function selectSibling(dir) {
  const ids = C.selection.ids;
  if (!ids.length) { const pg = C.currentPage(); const k = pg ? C.store.childIds(pg) : []; if (k.length) C.selection.set([k[k.length - 1]]); return; }
  const id = ids[ids.length - 1], n = get(id);
  // Layer panel order is top (highest z) first; Tab walks down that list.
  const sibs = C.store.childIds(n.parent).slice().reverse();
  const i = sibs.indexOf(id);
  C.selection.set([sibs[(i + dir + sibs.length) % sibs.length]]);
}

// ---------------- vector edit mode ----------------
let vedit = null;   // {id, sel:Set("pi:i")}
export const vectorEditing = () => vedit?.id || null;
export function enterVectorEdit(id) {
  const n = get(id);
  if (!n) return;
  if (n.type === "polygon" || n.type === "star") {
    let props;
    try { props = G.flattenToVector(id, C.store); } catch (e) { console.error(e); toast("벡터로 바꿀 수 없습니다."); return; }
    const sibs = C.store.childIds(n.parent), i = sibs.indexOf(id);
    const nid = newId("vector");
    const p = P(id);
    C.commit([{ op: "add", node: { id: nid, type: "vector", parent: n.parent, z: zBetween(n.z, sibs[i + 1] ? get(sibs[i + 1]).z : null), props: { ...props, name: p.name } } }, { op: "del", id }], "벡터로 편집");
    id = nid;
  }
  if (get(id)?.type !== "vector") return;
  C.selection.set([id]);
  vedit = { id, sel: new Set() };
  C.container.classList.add("vector-editing");
  requestDraw();
}
export function exitVectorEdit() {
  if (!vedit) return;
  vedit = null;
  C.container.classList.remove("vector-editing");
  requestDraw();
}
function vScreen(id) {
  const M = worldM(id), V = C.viewport;
  return (x, y) => { const q = ap(M, x, y); return V.pageToScreen(q.x, q.y); };
}
function vPathsNorm(paths) { return (paths || []).map((pa) => ({ closed: !!pa.closed, pts: (pa.pts || []).map((q) => ({ x: q.x, y: q.y, ix: q.ix ?? q.x, iy: q.iy ?? q.y, ox: q.ox ?? q.x, oy: q.oy ?? q.y })) })); }
function bez(p0, c1, c2, p1, t) {
  const u = 1 - t;
  return { x: u * u * u * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * p1.x, y: u * u * u * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * p1.y };
}
function segs(pa) {
  const out = [], n = pa.pts.length;
  for (let i = 0; i < n - 1 + (pa.closed ? 1 : 0); i++) out.push([i, (i + 1) % n]);
  return out;
}
export function pathsBox(paths) {
  try { const d = G.vectorD(paths); const b = G.bboxOfD(d); if (b && Number.isFinite(b.w)) return b; } catch (_) { /* fall back */ }
  const pts = paths.flatMap((pa) => pa.pts.flatMap((q) => [{ x: q.x, y: q.y }, { x: q.ix, y: q.iy }, { x: q.ox, y: q.oy }]));
  return aabbOf(pts) || { x: 0, y: 0, w: 0, h: 0 };
}
// Commit-ready props for edited paths: points re-based so the box starts at 0,0.
export function vectorProps(id, paths) {
  const g = geom(id), b = pathsBox(paths);
  const box = reframe(g, b.x, b.y, b.w, b.h);
  const moved = paths.map((pa) => ({ closed: pa.closed, pts: pa.pts.map((q) => ({ x: r3(q.x - b.x), y: r3(q.y - b.y), ix: r3(q.ix - b.x), iy: r3(q.iy - b.y), ox: r3(q.ox - b.x), oy: r3(q.oy - b.y) })) }));
  return { paths: moved, x: r3(box.x), y: r3(box.y), w: r3(Math.max(b.w, 0.01)), h: r3(Math.max(b.h, 0.01)) };
}
function vectorDown(e, sp) {
  const id = vedit.id, toS = vScreen(id), paths = vPathsNorm(P(id).paths);
  const M = worldM(id), Mi = inv(M);
  const toLocalPt = (s) => { const c = C.viewport.screenToPage(s.x, s.y); return ap(Mi, c.x, c.y); };
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  // handles of selected points first
  for (const key of vedit.sel) {
    const [pi, i] = key.split(":").map(Number), q = paths[pi]?.pts[i];
    if (!q) continue;
    for (const side of ["i", "o"]) {
      const hp = toS(q[side + "x"], q[side + "y"]);
      if ((q[side + "x"] !== q.x || q[side + "y"] !== q.y) && dist(hp, sp) < 7) return startVDrag(e, { kind: "handle", pi, i, side, paths, toLocalPt, alt: e.altKey });
    }
  }
  for (let pi = 0; pi < paths.length; pi++) for (let i = 0; i < paths[pi].pts.length; i++) {
    const q = paths[pi].pts[i];
    if (dist(toS(q.x, q.y), sp) < 8) {
      const key = `${pi}:${i}`;
      if (e.shiftKey) vedit.sel.has(key) ? vedit.sel.delete(key) : vedit.sel.add(key);
      else if (!vedit.sel.has(key)) vedit.sel = new Set([key]);
      requestDraw();
      // Alt-drag on a point pulls new smooth handles out of a corner.
      return startVDrag(e, { kind: e.altKey ? "pull" : "point", pi, i, paths, toLocalPt });
    }
  }
  // segment: insert a point
  for (let pi = 0; pi < paths.length; pi++) for (const [a, b] of segs(paths[pi])) {
    const A = paths[pi].pts[a], B = paths[pi].pts[b];
    for (let k = 1; k < 24; k++) {
      const t = k / 24, q = bez({ x: A.x, y: A.y }, { x: A.ox, y: A.oy }, { x: B.ix, y: B.iy }, { x: B.x, y: B.y }, t);
      if (dist(toS(q.x, q.y), sp) < 6) {
        // de Casteljau split at t
        const p0 = { x: A.x, y: A.y }, p1 = { x: A.ox, y: A.oy }, p2 = { x: B.ix, y: B.iy }, p3 = { x: B.x, y: B.y };
        const L = (u, v) => ({ x: u.x + (v.x - u.x) * t, y: u.y + (v.y - u.y) * t });
        const q01 = L(p0, p1), q12 = L(p1, p2), q23 = L(p2, p3), q012 = L(q01, q12), q123 = L(q12, q23), m = L(q012, q123);
        A.ox = q01.x; A.oy = q01.y; B.ix = q23.x; B.iy = q23.y;
        const np = { x: m.x, y: m.y, ix: q012.x, iy: q012.y, ox: q123.x, oy: q123.y };
        const at = b === 0 ? paths[pi].pts.length : b;
        paths[pi].pts.splice(at, 0, np);
        vedit.sel = new Set([`${pi}:${at}`]);
        C.commit([{ op: "set", id, props: vectorProps(id, paths) }], "점 추가");
        return true;
      }
    }
  }
  const c = C.viewport.screenToPage(sp.x, sp.y);
  if (insideNode(id, c)) { vedit.sel.clear(); requestDraw(); return true; }
  exitVectorEdit();
  return false;
}
function startVDrag(e, d) {
  const start = d.toLocalPt(C.viewport.clientToScreen(e.clientX, e.clientY));
  const orig = structuredClone(d.paths);
  let moved = false;
  dragState = {
    move(ev) {
      const cur = d.toLocalPt(C.viewport.clientToScreen(ev.clientX, ev.clientY));
      const dx = cur.x - start.x, dy = cur.y - start.y;
      if (!moved && Math.hypot(dx, dy) * C.viewport.zoom < 2) return;
      moved = true;
      const paths = structuredClone(orig);
      if (d.kind === "point") {
        for (const key of vedit.sel) {
          const [pi, i] = key.split(":").map(Number), q = paths[pi]?.pts[i];
          if (!q) continue;
          q.x += dx; q.y += dy; q.ix += dx; q.iy += dy; q.ox += dx; q.oy += dy;
        }
      } else if (d.kind === "pull") {
        const q = paths[d.pi].pts[d.i];
        q.ox = q.x + dx; q.oy = q.y + dy; q.ix = q.x - dx; q.iy = q.y - dy;
      } else {
        const q = paths[d.pi].pts[d.i], o = d.side === "i" ? "o" : "i";
        q[d.side + "x"] = cur.x; q[d.side + "y"] = cur.y;
        const sym = !d.alt && !ev.altKey && (q[o + "x"] !== q.x || q[o + "y"] !== q.y);
        if (sym) { q[o + "x"] = 2 * q.x - cur.x; q[o + "y"] = 2 * q.y - cur.y; }
      }
      d.cur = paths;
      C.preview(vedit.id, { paths });
    },
    up() {
      if (moved && d.cur) {
        const id = vedit.id;
        C.commit([{ op: "set", id, props: vectorProps(id, d.cur) }], "벡터 편집");
        C.clearPreview(id);
      }
    },
  };
  return true;
}
// Arrow-key nudge of the selected points (canvas delta), one commit per key press.
export function nudgeVectorPoints(dx, dy) {
  if (!vedit || !vedit.sel.size) return false;
  const id = vedit.id, l = apv(inv(worldM(id)), dx, dy);
  const paths = vPathsNorm(P(id).paths);
  for (const key of vedit.sel) {
    const [pi, i] = key.split(":").map(Number), q = paths[pi]?.pts[i];
    if (!q) continue;
    q.x += l.x; q.y += l.y; q.ix += l.x; q.iy += l.y; q.ox += l.x; q.oy += l.y;
  }
  C.commit([{ op: "set", id, props: vectorProps(id, paths) }], "점 이동");
  return true;
}
export function deleteVectorPoints() {
  if (!vedit || !vedit.sel.size) return false;
  const id = vedit.id;
  let paths = vPathsNorm(P(id).paths);
  const rm = new Map();
  for (const key of vedit.sel) { const [pi, i] = key.split(":").map(Number); if (!rm.has(pi)) rm.set(pi, new Set()); rm.get(pi).add(i); }
  paths = paths.map((pa, pi) => ({ ...pa, pts: pa.pts.filter((_, i) => !rm.get(pi)?.has(i)) })).filter((pa) => pa.pts.length >= 2)
    .map((pa) => (pa.pts.length < 3 ? { ...pa, closed: false } : pa));
  vedit.sel.clear();
  if (!paths.length) { exitVectorEdit(); C.selection.clear(); C.commit([{ op: "del", id }], "벡터 삭제"); return true; }
  C.commit([{ op: "set", id, props: vectorProps(id, paths) }], "점 삭제");
  return true;
}

// ---------------- pointer interaction ----------------
let dragState = null;
let hoverId = null, hoverPt = null, altDown = false;
export let marquee = null;   // screen rect
let dropTarget = null, insertLine = null, angleLabel = null;

const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const HPOS = { nw: [0, 0], n: [0.5, 0], ne: [1, 0], e: [1, 0.5], se: [1, 1], s: [0.5, 1], sw: [0, 1], w: [0, 0.5] };

// Selection frame: single node = its rotated box; several = axis-aligned union.
function selFrame() {
  const ids = C.selection.ids.filter((id) => get(id));
  if (!ids.length || C.textEdit || vedit) return null;
  if (ids.length === 1) {
    const id = ids[0], n = get(id), g = geom(id);
    if (n.type === "line") return { id, line: true, g, M: worldM(id) };
    if (n.type === "page") return { id, g, M: [1, 0, 0, 1, g.x, g.y] };
    return { id, g, M: worldM(id) };
  }
  const b = unionBox(ids);
  return { multi: true, g: { x: 0, y: 0, w: b.w, h: b.h, rotation: 0 }, M: [1, 0, 0, 1, b.x, b.y], box: b };
}
function frameScreenPts(f) {
  const V = C.viewport;
  const pt = (u, v) => { const q = ap(f.M, u * f.g.w, v * f.g.h); return V.pageToScreen(q.x, q.y); };
  return { pt, corners: [pt(0, 0), pt(1, 0), pt(1, 1), pt(0, 1)] };
}
function pointInPoly(p, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
function segDist(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy;
  const t = L ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L)) : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}
function handleAt(sp) {
  const f = selFrame();
  if (!f) return null;
  if (f.id && isLocked(f.id)) return null;
  const { pt, corners } = frameScreenPts(f);
  if (f.line) {
    const a = pt(0, 0), b = pt(1, 0);
    if (Math.hypot(sp.x - a.x, sp.y - a.y) < 7) return { h: "p0", f };
    if (Math.hypot(sp.x - b.x, sp.y - b.y) < 7) return { h: "p1", f };
    return null;
  }
  for (const h of ["nw", "ne", "se", "sw"]) {
    const q = pt(...HPOS[h]);
    if (Math.hypot(sp.x - q.x, sp.y - q.y) < 6) return { h, f };
  }
  const small = Math.hypot(corners[1].x - corners[0].x, corners[1].y - corners[0].y) < 24 || Math.hypot(corners[3].x - corners[0].x, corners[3].y - corners[0].y) < 24;
  const edges = [["n", 0, 1], ["e", 1, 2], ["s", 2, 3], ["w", 3, 0]];
  if (!small) for (const [h, a, b] of edges) if (segDist(sp, corners[a], corners[b]) < 4) return { h, f };
  if (!pointInPoly(sp, corners) && get(f.id)?.type !== "page") {
    for (const h of ["nw", "ne", "se", "sw"]) {
      const q = pt(...HPOS[h]);
      if (Math.hypot(sp.x - q.x, sp.y - q.y) < 20) return { h: "rot-" + h, f };
    }
  }
  return null;
}
function cursorFor(hit) {
  if (!hit) return "";
  if (hit.h === "p0" || hit.h === "p1") return "crosshair";
  const { pt } = frameScreenPts(hit.f);
  const c = pt(0.5, 0.5), base = hit.h.replace("rot-", ""), q = pt(...HPOS[base]);
  const ang = Math.atan2(q.y - c.y, q.x - c.x) * R2D;
  if (hit.h.startsWith("rot-")) return rotCursor(ang + 135);
  const a = ((ang % 180) + 180) % 180;
  return a < 22.5 || a >= 157.5 ? "ew-resize" : a < 67.5 ? "nwse-resize" : a < 112.5 ? "ns-resize" : "nesw-resize";
}
const rotCache = new Map();
function rotCursor(deg) {
  const k = Math.round(deg / 15) * 15;
  if (!rotCache.has(k)) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g transform="rotate(${k} 12 12)" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M7 15a7 7 0 0 1 8-8" stroke="#fff" stroke-width="4"/><path d="M7 15a7 7 0 0 1 8-8" stroke="#000" stroke-width="1.5"/><path d="M12 5l3 2-2 3M5 12l2 3 3-2" stroke="#fff" stroke-width="4"/><path d="M12 5l3 2-2 3M5 12l2 3 3-2" stroke="#000" stroke-width="1.5"/></g></svg>`;
    rotCache.set(k, `url("data:image/svg+xml,${encodeURIComponent(svg)}") 12 12, crosshair`);
  }
  return rotCache.get(k);
}

export function handlePointerDown(e) {
  if (e.button !== 0) return false;
  const sp = C.viewport.clientToScreen(e.clientX, e.clientY);
  const cp = C.viewport.screenToPage(sp.x, sp.y);
  if (C.textEdit) {
    const elx = C.renderer.elementOf?.(C.textEdit.id);
    if (elx && elx.contains(e.target)) return true;   // caret placement inside the editor
    endText();
  }
  if (vedit) { if (vectorDown(e, sp)) { capture(e); return true; } }
  const hit = handleAt(sp);
  if (hit) {
    if (hit.h.startsWith("rot-")) startRotate(e, hit, cp);
    else if (hit.h === "p0" || hit.h === "p1") startLineEnd(e, hit);
    else startResize(e, hit, cp);
    capture(e);
    return true;
  }
  const deep = e.metaKey || e.ctrlKey;
  const pick = pickAt(e.clientX, e.clientY, deep);
  const sel = C.selection.ids;
  if (pick) {
    let clickSelectOnly = null;
    if (e.shiftKey) C.selection.toggle(pick);
    else if (sel.includes(pick)) clickSelectOnly = pick;
    else C.selection.set([pick]);
    if (C.selection.ids.length) startMove(e, cp, clickSelectOnly);
    capture(e);
    return true;
  }
  // Dragging inside the current selection's frame moves it (Figma).
  const f = selFrame();
  if (f && !e.shiftKey && pointInPoly(sp, frameScreenPts(f).corners) && !(f.id && get(f.id).type === "page")) {
    startMove(e, cp, null);
    capture(e);
    return true;
  }
  if (!e.shiftKey) C.selection.clear();
  startMarquee(e, cp, deep);
  capture(e);
  return true;
}
function capture(e) { try { C.container.setPointerCapture(e.pointerId); } catch (_) { /* synthetic */ } }

function onMove(e) {
  if (C.viewport.panning) return;
  altDown = e.altKey;
  if (dragState) { dragState.move(e); requestDraw(); return; }
  if (e.buttons) return;
  hoverPt = { x: e.clientX, y: e.clientY };
  scheduleHover();
}
let hoverRaf = 0;
function scheduleHover() {
  if (hoverRaf) return;
  hoverRaf = requestAnimationFrame(() => {
    hoverRaf = 0;
    if (!hoverPt || dragState) return;
    const tool = C.tool;
    const sp = C.viewport.clientToScreen(hoverPt.x, hoverPt.y);
    let cursor = "";
    if (tool === "move" || tool === "scale") {
      const h = vedit ? null : handleAt(sp);
      cursor = cursorFor(h);
      const nh = h ? null : pickAt(hoverPt.x, hoverPt.y, false);
      if (nh !== hoverId) { hoverId = nh; requestDraw(); }
      else if (altDown) requestDraw();
    } else if (hoverId) { hoverId = null; requestDraw(); }
    C.container.style.cursor = cursor;
  });
}
export function setHover(id) { if (hoverId !== id) { hoverId = id; requestDraw(); } }
export const hovered = () => hoverId;

function onUp(e) {
  if (!dragState) return;
  const d = dragState;
  dragState = null;
  try { d.up(e); } catch (err) { console.error(err); }
  try { C.container.releasePointerCapture(e.pointerId); } catch (_) { /* released */ }
  marquee = null; dropTarget = null; insertLine = null; angleLabel = null;
  C.snapper.clear();
  requestDraw();
}
function onCancel(e) {
  if (!dragState) return;
  const d = dragState;
  dragState = null;
  try { d.cancel ? d.cancel() : d.up(e); } catch (err) { console.error(err); }
  marquee = null; dropTarget = null; insertLine = null; angleLabel = null;
  C.snapper.clear();
  requestDraw();
}
export const dragging = () => !!dragState;
// Esc during a drag cancels it.
export function cancelDrag() {
  if (!dragState) return false;
  const d = dragState;
  dragState = null;
  try { d.cancel?.(); } catch (err) { console.error(err); }
  marquee = null; dropTarget = null; insertLine = null; angleLabel = null;
  C.snapper.clear();
  requestDraw();
  return true;
}
export function startCustomDrag(state) { dragState = state; }

// ---- marquee ----
function startMarquee(e, cp, deep) {
  const startPage = pageAt(cp);
  const base = e.shiftKey ? C.selection.ids.slice() : [];
  const cands = [];
  const addBox = (id) => { if (!isLocked(id) && !isHidden(id)) cands.push({ id, b: boxOf(id) }); };
  if (startPage) {
    const walk = (pid) => {
      for (const c of C.store.childIds(pid)) {
        const t = get(c).type;
        if (deep && isContainer(t) && C.store.childIds(c).length) walk(c);
        else if (t === "section" && C.store.childIds(c).length) { addBox(c); walk(c); }
        else addBox(c);
      }
    };
    walk(startPage);
  } else {
    for (const pg of C.store.childIds(null)) {
      cands.push({ id: pg, b: boxOfPage(pg), page: true });
      for (const c of C.store.childIds(pg)) addBox(c);
    }
  }
  let raf = 0;
  dragState = {
    move(ev) {
      const s1 = C.viewport.clientToScreen(ev.clientX, ev.clientY);
      const p1 = C.viewport.screenToPage(s1.x, s1.y);
      const r = { x: Math.min(cp.x, p1.x), y: Math.min(cp.y, p1.y), w: Math.abs(p1.x - cp.x), h: Math.abs(p1.y - cp.y) };
      const a = C.viewport.pageToScreen(cp.x, cp.y);
      marquee = { x: Math.min(a.x, s1.x), y: Math.min(a.y, s1.y), w: Math.abs(s1.x - a.x), h: Math.abs(s1.y - a.y) };
      if (raf) return;   // hit testing once per frame
      raf = requestAnimationFrame(() => {
        raf = 0;
        const inside = (b) => b.x >= r.x && b.y >= r.y && b.x + b.w <= r.x + r.w && b.y + b.h <= r.y + r.h;
        const touch = (b) => b.x <= r.x + r.w && b.x + b.w >= r.x && b.y <= r.y + r.h && b.y + b.h >= r.y;
        const hits = [];
        const fullPages = new Set(cands.filter((c) => c.page && inside(c.b)).map((c) => c.id));
        const sectionsIn = new Set();
        for (const c of cands) {
          if (c.page) { if (fullPages.has(c.id)) hits.push(c.id); continue; }
          if (!startPage && fullPages.has(get(c.id).parent)) continue;
          const t = get(c.id).type;
          if (t === "section") { if (inside(c.b)) { hits.push(c.id); sectionsIn.add(c.id); } continue; }
          if (touch(c.b) && !sectionsIn.has(get(c.id).parent)) hits.push(c.id);
        }
        const next = [...new Set([...base, ...hits])].filter((id) => !(sectionsIn.has(get(id)?.parent)));
        const cur = C.selection.ids;
        if (next.length !== cur.length || next.some((x, i) => x !== cur[i])) C.selection.set(next);
      });
    },
    up() { cancelAnimationFrame(raf); },
    cancel() { cancelAnimationFrame(raf); },
  };
}

// ---- move ----
function startMove(e, cp, clickSelectOnly) {
  let ids = topLevel(C.selection.ids).filter((id) => !isLocked(id));
  if (!ids.length) return;
  const pages = ids.filter((id) => get(id).type === "page");
  if (pages.length) ids = pages;   // pages move alone
  const origin = { x: e.clientX, y: e.clientY };
  let started = false, ghost = null, moveIds = ids;
  const st = new Map();
  const box0 = () => unionBox(moveIds);
  let b0 = null, lastD = { x: 0, y: 0 };
  const init = (list) => {
    st.clear();
    for (const id of list) {
      const n = get(id), g = geom(id), p = P(id);
      const flow = n.type !== "page" && inFlow(n, (nn) => P(nn.id));
      st.set(id, { g, x: n.type === "page" ? p.cx : g.x, y: n.type === "page" ? p.cy : g.y, Mi: inv(parentM(id)), flow, lc: p.layoutChild });
    }
    b0 = box0();
    C.snapper.prepare(list);
  };
  dragState = {
    move(ev) {
      if (!started) {
        if (Math.hypot(ev.clientX - origin.x, ev.clientY - origin.y) < 3) return;
        started = true;
        if (ev.altKey) {
          // ⌥-drag duplicates: ghost copies (local only) follow the pointer; originals stay.
          const c = cloneOps(ids);
          ghost = C.store.applyTemp(c.ops);
          moveIds = c.roots;
          C.selection.set(moveIds);
        }
        init(moveIds);
      }
      const p = C.viewport.clientToPage(ev.clientX, ev.clientY);
      let dx = p.x - cp.x, dy = p.y - cp.y;
      if (ev.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
      const snapOff = ev.ctrlKey && !ev.metaKey;
      if (!snapOff) {
        const s = C.snapper.move({ x: b0.x + dx, y: b0.y + dy, w: b0.w, h: b0.h }, { lockX: ev.shiftKey && dx === 0, lockY: ev.shiftKey && dy === 0 });
        dx += s.dx; dy += s.dy;
      } else C.snapper.clear();
      lastD = { x: dx, y: dy };
      const pix = C.flags.snapPixel && !snapOff;
      for (const [id, s] of st) {
        const n = get(id);
        if (n.type === "page") { C.preview(id, { cx: pix ? Math.round(s.x + dx) : s.x + dx, cy: pix ? Math.round(s.y + dy) : s.y + dy }); continue; }
        const l = apv(s.Mi, dx, dy);
        const nx = s.x + l.x, ny = s.y + l.y;
        const props = { x: pix ? Math.round(nx) : r3(nx), y: pix ? Math.round(ny) : r3(ny) };
        if (s.flow) props.layoutChild = { ...(s.lc || {}), absolute: true };
        C.preview(id, props);
      }
      // reparent target
      if (!pages.length) {
        const ex = new Set(moveIds);
        dropTarget = containerAt(p, ex, { x: ev.clientX, y: ev.clientY });
        insertLine = null;
        if (dropTarget && P(dropTarget).layout && P(dropTarget).layout.dir !== "NONE") insertLine = flowInsert(dropTarget, p, ex);
      }
    },
    up(ev) {
      if (!started) {
        if (clickSelectOnly && !ev.shiftKey) C.selection.set([clickSelectOnly]);
        return;
      }
      const ops = [];
      const p = C.viewport.clientToPage(ev.clientX, ev.clientY);
      if (ghost) {
        // Re-create the ghosts for real at their final positions.
        const finals = new Map([...st.keys()].map((id) => [id, { ...previews.get(id) }]));
        const gops = ghost.ops.map((o) => {
          const f = finals.get(o.node.id);
          if (!f) return o;
          const props = { ...o.node.props, ...f };
          if (props.layoutChild?.absolute && !st.get(o.node.id).lc?.absolute) props.layoutChild = st.get(o.node.id).lc || null;
          if (props.layoutChild === null) delete props.layoutChild;
          return { ...o, node: { ...o.node, props } };
        });
        for (const id of st.keys()) clearPreviewLocal(id);
        ghost.revert();
        ops.push(...gops);
        const dropOps = reparentOps(moveIds, p, ev, gops);
        C.commit(ops.concat(dropOps), "복제");
        C.selection.set(moveIds.filter((id) => get(id)));
        return;
      }
      for (const [id, s] of st) {
        const pv = previews.get(id) || {};
        if (get(id).type === "page") ops.push({ op: "set", id, props: { cx: pv.cx, cy: pv.cy } });
        else if (!s.flow) ops.push({ op: "set", id, props: { x: pv.x, y: pv.y } });
      }
      ops.push(...reparentOps(moveIds, p, ev, null, st));
      C.commit(ops, "이동");
      for (const id of st.keys()) C.clearPreview(id);
      void lastD;
    },
    cancel() {
      for (const id of st.keys()) C.clearPreview(id);
      ghost?.revert();
      if (ghost) C.selection.set(ids);
    },
  };
}
function clearPreviewLocal(id) { previews.delete(id); try { C.renderer.clearPreview(id); } catch (_) { /* gone */ } }
// Insert position inside an auto-layout container: {parent, index, line (screen segment)}.
function flowInsert(pid, p, exclude) {
  const lay = P(pid).layout, horiz = lay.dir === "HORIZONTAL";
  const kids = C.store.childIds(pid).filter((k) => !exclude.has(k) && !P(k).layoutChild?.absolute);
  let index = kids.length;
  const boxes = kids.map((k) => boxOf(k));
  for (let i = 0; i < kids.length; i++) {
    const b = boxes[i], mid = horiz ? b.x + b.w / 2 : b.y + b.h / 2;
    if ((horiz ? p.x : p.y) < mid) { index = i; break; }
  }
  const pb = boxOf(pid);
  let a, b;
  if (!kids.length) { a = horiz ? { x: pb.x + pb.w / 2, y: pb.y } : { x: pb.x, y: pb.y + pb.h / 2 }; b = horiz ? { x: a.x, y: pb.y + pb.h } : { x: pb.x + pb.w, y: a.y }; }
  else {
    const ref = boxes[Math.min(index, kids.length - 1)], after = index >= kids.length;
    const v = horiz ? (after ? ref.x + ref.w + 2 : ref.x - 2) : (after ? ref.y + ref.h + 2 : ref.y - 2);
    a = horiz ? { x: v, y: ref.y } : { x: ref.x, y: v };
    b = horiz ? { x: v, y: ref.y + ref.h } : { x: ref.x + ref.w, y: v };
  }
  return { parent: pid, index, kids, a, b };
}
// Moves into/out of containers at drop. fresh = add ops of ghost copies (already positioned).
function reparentOps(ids, p, ev, fresh, st) {
  const ops = [];
  const ex = new Set(ids);
  const target = containerAt(p, ex, { x: ev.clientX, y: ev.clientY });
  if (!target) return ops;
  const tp = P(target), flow = tp.layout && tp.layout.dir !== "NONE";
  const plan = [];
  for (const id of sortByOrder(ids)) {
    const n = get(id) || null;
    const addOp = fresh?.find((o) => o.node.id === id);
    const type = n ? n.type : addOp?.node.type;
    const parent = n ? n.parent : addOp?.node.parent;
    if (!type || type === "page") continue;
    if (type === "section" && get(target).type !== "page") continue;
    let keep = parent === target;
    // Children of a group stay in it while dropped inside the group's own container.
    if (!keep && parent && ["group", "boolean"].includes(get(parent)?.type)) {
      let a = get(parent);
      while (a && ["group", "boolean"].includes(a.type)) a = get(a.parent);
      if (a && a.id === target) keep = true;
    }
    const wasFlow = st?.get(id)?.flow;
    if (keep && !wasFlow) continue;   // same parent: position already set (absolute children stay absolute)
    plan.push({ id, keep, addOp });
  }
  if (!plan.length) return ops;
  if (flow) {
    const ins = flowInsert(target, p, ex);
    const before = ins.kids[ins.index - 1], after = ins.kids[ins.index];
    const zs = zSeq(before ? get(before).z : null, after ? get(after).z : null, plan.length);
    plan.forEach((it, i) => {
      if (it.addOp) { it.addOp.node.parent = target; it.addOp.node.z = zs[i]; const lc = it.addOp.node.props.layoutChild; if (lc?.absolute) it.addOp.node.props.layoutChild = { ...lc, absolute: false }; return; }
      ops.push({ op: "move", id: it.id, parent: target, z: zs[i] });
      const lc = st?.get(it.id)?.lc;
      ops.push({ op: "set", id: it.id, props: { layoutChild: lc && !lc.absolute ? lc : lc ? { ...lc, absolute: false } : null } });
    });
    return ops;
  }
  const top = C.store.childIds(target).filter((k) => !ex.has(k));
  const zs = zSeq(top.length ? get(top[top.length - 1]).z : null, null, plan.length);
  plan.forEach((it, i) => {
    if (it.keep) {
      // Leaving flow inside the same parent is not possible here (keep && flow handled above).
      return;
    }
    if (it.addOp) {
      // Ghost copy: compute its placement from the current (temp-free) state via the original's geometry.
      const node = it.addOp.node, g = { x: node.props.x || 0, y: node.props.y || 0, w: node.props.w ?? 100, h: node.props.h ?? 100, rotation: node.props.rotation || 0 };
      const M = mul(worldM(node.parent), localM(g)), c = ap(M, g.w / 2, g.h / 2), lc = toLocal(target, c);
      node.props.rotation = r3(normDeg(g.rotation + worldRot(node.parent) - worldRot(target)));
      node.props.x = r3(lc.x - g.w / 2); node.props.y = r3(lc.y - g.h / 2);
      node.parent = target; node.z = zs[i];
      return;
    }
    const place = placeIn(it.id, target);
    ops.push({ op: "move", id: it.id, parent: target, z: zs[i] });
    const lc = P(it.id).layoutChild;
    ops.push({ op: "set", id: it.id, props: { ...place, ...(lc?.absolute && st?.get(it.id)?.flow ? { layoutChild: { ...lc, absolute: false } } : {}) } });
  });
  return ops;
}

// ---- resize ----
function startResize(e, hit, cp) {
  const f = hit.f, h = hit.h;
  const ids = f.multi ? topLevel(C.selection.ids).filter((id) => !isLocked(id)) : [f.id];
  const g0 = { ...f.g }, Mi = inv(f.M);
  const per = new Map(ids.map((id) => [id, { g: geom(id), M: worldM(id), PMi: inv(parentM(id)) }]));
  const scaleTool = C.tool === "scale";
  C.snapper.prepare(ids);
  let last = null;
  const [hx, hy] = HPOS[h];
  dragState = {
    move(ev) {
      const p = C.viewport.clientToPage(ev.clientX, ev.clientY);
      let q = ap(Mi, p.x, p.y);   // in frame-local (unrotated) coordinates
      // snapping (axis-aligned frames only)
      if (!(ev.ctrlKey && !ev.metaKey) && !(f.g.rotation % 360) && !(f.id && worldRot(f.id) % 360)) {
        const wpt = ap(f.M, q.x, q.y);
        const s = C.snapper.point(wpt, { x: hx !== 0.5, y: hy !== 0.5 });
        q = ap(Mi, wpt.x + s.dx, wpt.y + s.dy);
      }
      let x0 = 0, y0 = 0, x1 = g0.w, y1 = g0.h;
      if (hx === 0) x0 = q.x; else if (hx === 1) x1 = q.x;
      if (hy === 0) y0 = q.y; else if (hy === 1) y1 = q.y;
      const center = ev.altKey;
      if (center) {
        if (hx === 0) x1 = g0.w - x0; else if (hx === 1) x0 = g0.w - x1;
        if (hy === 0) y1 = g0.h - y0; else if (hy === 1) y0 = g0.h - y1;
      }
      const prop = ev.shiftKey || scaleTool;
      if (prop && g0.w && g0.h) {
        let sx = (x1 - x0) / g0.w, sy = (y1 - y0) / g0.h;
        if (hx === 0.5) sx = sy; else if (hy === 0.5) sy = sx;
        else { const s = Math.max(Math.abs(sx), Math.abs(sy)); sx = Math.sign(sx || 1) * s; sy = Math.sign(sy || 1) * s; }
        const w = g0.w * sx, hh = g0.h * sy;
        const ax = center ? g0.w / 2 : hx === 0 ? g0.w : hx === 1 ? 0 : g0.w / 2;
        const ay = center ? g0.h / 2 : hy === 0 ? g0.h : hy === 1 ? 0 : g0.h / 2;
        const fx = center ? 0.5 : hx === 0 ? 1 : hx === 1 ? 0 : 0.5;
        const fy = center ? 0.5 : hy === 0 ? 1 : hy === 1 ? 0 : 0.5;
        x0 = ax - w * fx; x1 = x0 + w; y0 = ay - hh * fy; y1 = y0 + hh;
      }
      const flipX = x1 < x0, flipY = y1 < y0;
      const bx = Math.min(x0, x1), by = Math.min(y0, y1), bw = Math.abs(x1 - x0), bh = Math.abs(y1 - y0);
      const ops = [];
      if (!f.multi) {
        const id = f.id, pg = per.get(id).g;
        const box = reframe(pg, bx, by, bw, bh);
        if (C.flags.snapPixel && !(pg.rotation % 360) && !(ev.ctrlKey && !ev.metaKey)) {
          const xa = Math.round(box.x), ya = Math.round(box.y);
          box.w = Math.max(1, Math.round(box.x + box.w) - xa); box.h = get(id).type === "line" ? 0 : Math.max(1, Math.round(box.y + box.h) - ya);
          box.x = xa; box.y = ya;
        }
        ops.push(...resizeNodeOps(id, { ...box, flipX: flipX ? !pg.flipX : pg.flipX, flipY: flipY ? !pg.flipY : pg.flipY }, { ignoreConstraints: ev.metaKey, scale: scaleTool }));
        angleLabel = { text: `${fmt(box.w)} × ${fmt(box.h)}` };
      } else {
        const sx = g0.w ? bw / g0.w : 1, sy = g0.h ? bh / g0.h : 1;
        const B = f.box;
        const nb = { x: B.x + bx, y: B.y + by };
        for (const id of ids) {
          const { g, M, PMi } = per.get(id);
          const c = ap(M, g.w / 2, g.h / 2);
          const nc = { x: nb.x + (flipX ? (B.x + B.w - c.x) : (c.x - B.x)) * sx, y: nb.y + (flipY ? (B.y + B.h - c.y) : (c.y - B.y)) * sy };
          const lc = ap(PMi, nc.x, nc.y);
          const rot = ((g.rotation % 180) + 180) % 180;
          const swap = rot > 45 && rot < 135;
          const w = g.w * (swap ? sy : sx), hh = g.h * (swap ? sx : sy);
          const n = get(id);
          const box = n.type === "page" ? { x: nc.x - w / 2, y: nc.y - hh / 2, w, h: hh } : { x: lc.x - w / 2, y: lc.y - hh / 2, w, h: hh };
          ops.push(...resizeNodeOps(id, { ...box, flipX: flipX ? !g.flipX : g.flipX, flipY: flipY ? !g.flipY : g.flipY }, { ignoreConstraints: ev.metaKey, scale: scaleTool }));
        }
        angleLabel = { text: `${Math.round(bw)} × ${Math.round(bh)}` };
      }
      last = ops;
      previewOps(ops);
    },
    up() {
      if (!last) return;
      C.commit(last, scaleTool ? "크기 조절" : "크기 변경");
      clearOps(last);
    },
    cancel() { if (last) clearOps(last); },
  };
}
const previewOps = (ops) => { for (const o of ops) if (o.op === "set") C.preview(o.id, o.props); };
const clearOps = (ops) => { for (const id of new Set(ops.map((o) => o.id))) C.clearPreview(id); };

// ---- rotate ----
function startRotate(e, hit, cp) {
  const f = hit.f;
  const ids = f.multi ? topLevel(C.selection.ids).filter((id) => !isLocked(id) && get(id).type !== "page") : [f.id];
  const c = ap(f.M, f.g.w / 2, f.g.h / 2);
  const a0 = Math.atan2(cp.y - c.y, cp.x - c.x) * R2D;
  const per = new Map(ids.map((id) => { const g = geom(id); return [id, { g, c: ap(worldM(id), g.w / 2, g.h / 2), PMi: inv(parentM(id)), r: P(id).rotation || 0 }]; }));
  let last = null;
  dragState = {
    move(ev) {
      const p = C.viewport.clientToPage(ev.clientX, ev.clientY);
      let da = Math.atan2(p.y - c.y, p.x - c.x) * R2D - a0;
      const ops = [];
      if (!f.multi) {
        const s = per.get(f.id);
        let r = s.r + da;
        if (ev.shiftKey) r = Math.round(r / 15) * 15;
        r = normDeg(r);
        ops.push({ op: "set", id: f.id, props: { rotation: r3(r) } });
        angleLabel = { text: `${Math.round(r)}°` };
      } else {
        if (ev.shiftKey) da = Math.round(da / 15) * 15;
        const rad = da / R2D, cs = Math.cos(rad), sn = Math.sin(rad);
        for (const [id, s] of per) {
          const vx = s.c.x - c.x, vy = s.c.y - c.y;
          const nc = { x: c.x + vx * cs - vy * sn, y: c.y + vx * sn + vy * cs };
          const lc = ap(s.PMi, nc.x, nc.y);
          ops.push({ op: "set", id, props: { x: r3(lc.x - s.g.w / 2), y: r3(lc.y - s.g.h / 2), rotation: r3(normDeg(s.r + da)) } });
        }
        angleLabel = { text: `${Math.round(normDeg(da))}°` };
      }
      last = ops;
      previewOps(ops);
    },
    up() { if (last) { C.commit(last, "회전"); clearOps(last); } },
    cancel() { if (last) clearOps(last); },
  };
}

// ---- line endpoints ----
function startLineEnd(e, hit) {
  const id = hit.f.id, g = hit.f.g, M = worldM(id), PMi = inv(parentM(id));
  const fixed = hit.h === "p0" ? ap(M, g.w, 0) : ap(M, 0, 0);
  let last = null;
  C.snapper.prepare([id]);
  dragState = {
    move(ev) {
      let p = C.viewport.clientToPage(ev.clientX, ev.clientY);
      if (ev.shiftKey) {
        const a = Math.round(Math.atan2(p.y - fixed.y, p.x - fixed.x) / (Math.PI / 4)) * (Math.PI / 4), L = Math.hypot(p.x - fixed.x, p.y - fixed.y);
        p = { x: fixed.x + Math.cos(a) * L, y: fixed.y + Math.sin(a) * L };
      } else if (!(ev.ctrlKey && !ev.metaKey)) { const s = C.snapper.point(p, { x: true, y: true }); p = { x: p.x + s.dx, y: p.y + s.dy }; }
      const [wa, wb] = hit.h === "p0" ? [p, fixed] : [fixed, p];
      const a = ap(PMi, wa.x, wa.y), b = ap(PMi, wb.x, wb.y);
      last = [{ op: "set", id, props: { ...lineProps(a, b), flipX: null, flipY: null } }];   // the endpoints now define the direction
      angleLabel = { text: `${Math.round(last[0].props.w)}` };
      previewOps(last);
    },
    up() { if (last) { C.commit(last, "선 편집"); clearOps(last); } },
    cancel() { if (last) clearOps(last); },
  };
}
export function lineProps(a, b) {
  const w = Math.hypot(b.x - a.x, b.y - a.y), c = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  return { x: r3(c.x - w / 2), y: r3(c.y), w: r3(w), h: 0, rotation: r3(normDeg(Math.atan2(b.y - a.y, b.x - a.x) * R2D)) };
}

// ---- double click ----
function onDblClick(e) {
  if (C.tool !== "move" && C.tool !== "scale") return;
  if (C.textEdit) return;
  const ids = C.selection.ids;
  const leaf = leafAt(e.clientX, e.clientY);
  if (vedit) return;
  if (ids.length === 1) {
    const id = ids[0], n = get(id);
    if (leaf && (leaf === id || ancestors(leaf).includes(id))) {
      if (n.type === "text") return beginText(id, { point: { x: e.clientX, y: e.clientY } });
      if (n.type === "table") return beginText(id, { cell: tableCellAt(id, C.viewport.clientToPage(e.clientX, e.clientY)), point: { x: e.clientX, y: e.clientY } });
      if (["vector", "polygon", "star"].includes(n.type)) return enterVectorEdit(id);
      if (isContainer(n.type) && leaf !== id) {
        const chain = chainOf(leaf), i = chain.indexOf(id);
        const next = chain[i + 1];
        if (next) {
          C.selection.set([next]);
          const nn = get(next);
          if (nn.type === "text" && next === leaf) beginText(next, { point: { x: e.clientX, y: e.clientY } });
        }
        return;
      }
    }
  }
}
export function tableCellAt(id, cp) {
  const p = P(id), q = ap(inv(worldM(id)), cp.x, cp.y);
  let r = 0, c = 0, acc = 0;
  for (let i = 0; i < p.rows.length; i++) { acc += p.rows[i]; if (q.y < acc) { r = i; break; } r = i; }
  acc = 0;
  for (let i = 0; i < p.cols.length; i++) { acc += p.cols[i]; if (q.x < acc) { c = i; break; } c = i; }
  return `${r},${c}`;
}

// ---------------- overlay drawing ----------------
let drawRaf = 0;
export function requestDraw() { if (!drawRaf && C) drawRaf = requestAnimationFrame(draw); }
const NS = "http://www.w3.org/2000/svg";
function s(tag, attrs) { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; }
const poly = (pts) => pts.map((p) => `${p.x},${p.y}`).join(" ");
const drawers = new Set();
export function addDrawer(fn) { drawers.add(fn); return () => drawers.delete(fn); }

function draw() {
  drawRaf = 0;
  mcache.clear();
  const svg = C.overlay;
  svg.replaceChildren();
  const V = C.viewport;
  const toS = (p) => V.pageToScreen(p.x, p.y);
  const quad = (id) => cornersOf(id).map(toS);
  const sel = C.selection.ids.filter((id) => get(id));
  // hover
  if (hoverId && !sel.includes(hoverId) && !dragState && get(hoverId)) svg.append(s("polygon", { points: poly(quad(hoverId)), class: "ov-hover" }));
  // drop target
  if (dropTarget && get(dropTarget) && !sel.includes(dropTarget)) svg.append(s("polygon", { points: poly(quad(dropTarget)), class: "ov-drop" }));
  if (insertLine) { const a = toS(insertLine.a), b = toS(insertLine.b); svg.append(s("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "ov-insert" })); }
  // selection outlines
  if (sel.length && !vedit) {
    for (const id of sel) {
      const n = get(id);
      if (n.type === "line") { const g = geom(id), M = worldM(id), a = toS(ap(M, 0, 0)), b = toS(ap(M, g.w, 0)); svg.append(s("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "ov-sel" })); }
      else svg.append(s("polygon", { points: poly(quad(id)), class: sel.length > 1 ? "ov-sel thin" : "ov-sel" }));
    }
    const f = selFrame();
    if (f) {
      const { pt, corners } = frameScreenPts(f);
      if (f.multi) svg.append(s("polygon", { points: poly(corners), class: "ov-sel" }));
      const locked = f.id && isLocked(f.id);
      if (!locked && !dragState?.noHandles) {
        if (f.line) for (const q of [pt(0, 0), pt(1, 0)]) svg.append(s("circle", { cx: q.x, cy: q.y, r: 4, class: "ov-handle" }));
        else {
          const small = Math.hypot(corners[1].x - corners[0].x, corners[1].y - corners[0].y) < 24 || Math.hypot(corners[3].x - corners[0].x, corners[3].y - corners[0].y) < 24;
          const ang = Math.atan2(corners[1].y - corners[0].y, corners[1].x - corners[0].x) * R2D;
          for (const h of HANDLES) {
            if (small && h.length === 1) continue;
            const q = pt(...HPOS[h]);
            svg.append(s("rect", { x: q.x - 3.5, y: q.y - 3.5, width: 7, height: 7, class: "ov-handle", transform: `rotate(${ang} ${q.x} ${q.y})` }));
          }
        }
      }
      // size badge
      const bb = aabbOf(corners);
      const g = f.g;
      const label = angleLabel?.text || (f.line ? `${Math.round(g.w)}` : `${fmt(g.w)} × ${fmt(g.h)}`);
      badge(svg, bb.x + bb.w / 2, bb.y + bb.h + 8, label, ACCENT);
    }
  }
  // text edit outline
  if (C.textEdit && get(C.textEdit.id)) svg.append(s("polygon", { points: poly(quad(C.textEdit.id)), class: "ov-sel thin" }));
  // vector edit
  if (vedit && get(vedit.id)) drawVector(svg);
  // marquee
  if (marquee) svg.append(s("rect", { x: marquee.x, y: marquee.y, width: marquee.w, height: marquee.h, class: "ov-marquee" }));
  // snapping guides / measurement
  C.snapper.draw(svg, toS);
  if (altDown && !dragState && sel.length && !C.textEdit) {
    const target = hoverId && !sel.includes(hoverId) ? hoverId : get(topLevel(sel)[0])?.parent;
    if (target && get(target)) C.snapper.drawMeasure(svg, toS, selectionBounds(sel), get(target).type === "page" ? boxOfPage(target) : boxOf(target), !hoverId || target === get(sel[0]).parent);
  }
  for (const fn of drawers) { try { fn(svg, { toS, s, badge }); } catch (e) { console.error(e); } }
  // An empty overlay would still be a full-canvas composited layer (it overlaps the world): hide it.
  const empty = !svg.firstChild;   // (SVG elements have no .hidden property: use the attribute)
  if (svg.hasAttribute("hidden") !== empty) svg.toggleAttribute("hidden", empty);
  C.onOverlayDrawn?.();
}
const fmt = (v) => (Math.abs(v - Math.round(v)) < 0.05 ? String(Math.round(v)) : v.toFixed(1));
export function badge(svg, x, y, text, color) {
  const w = Math.max(24, text.length * 6.4 + 10);
  const g = s("g", { class: "ov-badge" });
  g.append(s("rect", { x: x - w / 2, y, width: w, height: 16, rx: 3, fill: color }));
  const t = s("text", { x, y: y + 11.5, "text-anchor": "middle" });
  t.textContent = text;
  g.append(t);
  svg.append(g);
}
function drawVector(svg) {
  const id = vedit.id, toS = vScreen(id), paths = vPathsNorm(P(id).paths);
  let d = "";
  for (const pa of paths) {
    if (!pa.pts.length) continue;
    const p0 = toS(pa.pts[0].x, pa.pts[0].y);
    d += `M${p0.x},${p0.y}`;
    for (const [a, b] of segs(pa)) {
      const A = pa.pts[a], B = pa.pts[b], c1 = toS(A.ox, A.oy), c2 = toS(B.ix, B.iy), e = toS(B.x, B.y);
      d += `C${c1.x},${c1.y} ${c2.x},${c2.y} ${e.x},${e.y}`;
    }
    if (pa.closed) d += "Z";
  }
  svg.append(s("path", { d, class: "ov-path" }));
  paths.forEach((pa, pi) => pa.pts.forEach((q, i) => {
    const key = `${pi}:${i}`, on = vedit.sel.has(key), c = toS(q.x, q.y);
    if (on) for (const side of ["i", "o"]) {
      if (q[side + "x"] === q.x && q[side + "y"] === q.y) continue;
      const h = toS(q[side + "x"], q[side + "y"]);
      svg.append(s("line", { x1: c.x, y1: c.y, x2: h.x, y2: h.y, class: "ov-bez" }));
      svg.append(s("circle", { cx: h.x, cy: h.y, r: 3, class: "ov-bez-h" }));
    }
    svg.append(s("circle", { cx: c.x, cy: c.y, r: 4, class: on ? "ov-pt on" : "ov-pt" }));
  }));
}

// ---------------- page labels (names above pages; click selects, drag moves) ----------------
function drawLabels() {
  const box = C.labels, V = C.viewport, pages = C.store.childIds(null);
  const have = new Map([...box.children].map((c) => [c.dataset.page, c]));
  for (const id of pages) {
    let lab = have.get(id);
    have.delete(id);
    if (!lab) {
      lab = el("div", { class: "page-label", "data-page": id });
      lab.addEventListener("pointerdown", (e) => labelDown(e, id));
      lab.addEventListener("dblclick", () => renamePage(id, lab));
      lab.addEventListener("pointerenter", () => setHover(id));
      lab.addEventListener("pointerleave", () => setHover(null));
      box.append(lab);
    }
    const p = P(id), a = V.pageToScreen(p.cx || 0, p.cy || 0), w = p.w * V.zoom;
    // Runs every viewport frame: write only what changed.
    const name = p.name || "페이지";
    if (!lab.querySelector("input") && lab.textContent !== name) lab.textContent = name;
    const tf = `translate(${a.x}px, ${a.y - 18}px)`, mw = `${Math.max(0, w)}px`;
    if (lab.style.transform !== tf) lab.style.transform = tf;
    if (lab.style.maxWidth !== mw) lab.style.maxWidth = mw;
    const hid = w < 24 || P(id).visible === false;
    if (lab.hidden !== hid) lab.hidden = hid;
    lab.classList.toggle("on", C.selection.ids.includes(id));
    lab.classList.toggle("current", C.currentPage() === id);
  }
  for (const lab of have.values()) lab.remove();
}
function labelDown(e, id) {
  if (e.button !== 0 || C.tool === "hand" || C.viewport.spaceDown) return;
  e.stopPropagation();
  e.preventDefault();
  if (C.textEdit) endText();
  if (e.shiftKey) C.selection.toggle(id); else if (!C.selection.ids.includes(id)) C.selection.set([id]);
  C.setCurrentPage(id);
  const cp = C.viewport.clientToPage(e.clientX, e.clientY);
  startMove(e, cp, null);
  capture(e);
}
export function renamePage(id, lab = C.labels.querySelector(`[data-page="${CSS.escape(id)}"]`)) {
  if (!lab) return;
  const input = el("input", { class: "label-input", value: P(id).name || "", "aria-label": "페이지 이름" });
  lab.replaceChildren(input);
  input.focus(); input.select();
  let done = false;
  const finish = (ok) => {
    if (done) return; done = true;
    const v = input.value.trim().slice(0, 200);
    lab.textContent = P(id)?.name || "";
    if (ok && v && v !== P(id).name) C.commit([{ op: "set", id, props: { name: v } }], "이름 변경");
    drawLabels();
  };
  input.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter" && !e.isComposing) finish(true); if (e.key === "Escape") finish(false); });
  input.addEventListener("blur", () => finish(true));
}

// ---------------- init ----------------
export function initSelect(ctx) {
  C = ctx;
  const c = ctx.container;
  c.addEventListener("pointermove", onMove);
  c.addEventListener("pointerup", onUp);
  c.addEventListener("pointercancel", onCancel);
  c.addEventListener("dblclick", onDblClick);
  c.addEventListener("pointerleave", () => { if (!dragState && hoverId) { hoverId = null; requestDraw(); } hoverPt = null; });
  window.addEventListener("keydown", (e) => { if (e.key === "Alt" && !altDown) { altDown = true; requestDraw(); } });
  window.addEventListener("keyup", (e) => { if (e.key === "Alt") { altDown = false; requestDraw(); } });
  window.addEventListener("blur", () => { altDown = false; });
  document.addEventListener("focusout", () => setTimeout(syncText, 0));
  window.addEventListener("ppt:text-edit-end", () => setTimeout(syncText, 0));
  document.addEventListener("keyup", () => syncText());
  ctx.viewport.onChange(() => { requestDraw(); drawLabels(); });
  ctx.selection.on(() => {
    if (vedit && !ctx.selection.ids.includes(vedit.id)) exitVectorEdit();
    if (ctx.textEdit && !ctx.selection.ids.includes(ctx.textEdit.id)) endText();
    requestDraw(); drawLabels();
  });
  ctx.store.subscribe((changed, deleted) => {
    mcache.clear();
    for (const id of deleted) previews.delete(id);
    if (vedit && deleted.includes(vedit.id)) exitVectorEdit();
    requestDraw();
    if (changed.some((id) => get(id)?.type === "page") || deleted.length) drawLabels();
  });
  drawLabels();
  return {
    handlePointerDown, requestDraw, drawLabels, setHover, cancelDrag,
  };
}
