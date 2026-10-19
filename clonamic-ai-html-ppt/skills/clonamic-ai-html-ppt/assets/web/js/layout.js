// Resize with constraints (format.md §6). Auto-layout flow children are laid out by CSS, so only
// absolute children of auto-layout frames and children of plain frames/pages/sections respond.
import { propsOf } from './schema.js';
import { activeRenderer } from './render.js';

const r3 = (v) => Math.round(v * 1000) / 1000;
const CONTAINERS = new Set(['page', 'frame', 'section', 'group', 'boolean']);
const isAuto = (p) => !!(p.layout && p.layout.dir && p.layout.dir !== 'NONE');

function axis(c, pos, size, oldLen, newLen) {
  const d = newLen - oldLen;
  switch (c) {
    case 'RIGHT': case 'BOTTOM': return [pos + d, size];
    case 'LEFT_RIGHT': case 'TOP_BOTTOM': return [pos, Math.max(0, size + d)];
    case 'CENTER': return [pos + d / 2, size];
    case 'SCALE': { const s = oldLen ? newLen / oldLen : 1; return [pos * s, size * s]; }
    default: return [pos, size];
  }
}

// Ops that resize node `id` to newBox {x, y, w, h} (parent coordinates; for a page x/y = cx/cy)
// and move/resize its children per their constraints. opts.ignoreConstraints (⌘-resize): children
// keep their canvas position. Groups/booleans scale their children.
export function resizeOps(store, id, newBox, opts = {}) {
  const node = store.nodes.get(id);
  if (!node) return [];
  const p = propsOf(node);
  const ops = [];
  const own = node.type === 'page'
    ? { w: r3(newBox.w), h: r3(newBox.h), ...(newBox.x != null ? { cx: r3(newBox.x) } : {}), ...(newBox.y != null ? { cy: r3(newBox.y) } : {}) }
    : { x: r3(newBox.x ?? p.x), y: r3(newBox.y ?? p.y), w: r3(newBox.w), h: r3(newBox.h) };
  ops.push({ op: 'set', id, props: own });
  if (CONTAINERS.has(node.type)) childOps(store, node, p, newBox, opts, ops);
  return ops;
}

function childOps(store, node, p, nb, opts, ops) {
  const ow = p.w, oh = p.h, nw = nb.w, nh = nb.h;
  const dx = node.type === 'page' ? 0 : (nb.x ?? p.x) - p.x, dy = node.type === 'page' ? 0 : (nb.y ?? p.y) - p.y;
  const scaleAll = node.type === 'group' || node.type === 'boolean';
  const auto = isAuto(p);
  for (const c of store.children(node.id)) {
    const cp = propsOf(c);
    if (auto && !(cp.layoutChild || {}).absolute) continue;
    let box;
    if (opts.ignoreConstraints && !scaleAll) {
      if (!dx && !dy) continue;
      box = { x: cp.x - dx, y: cp.y - dy, w: cp.w, h: cp.h };
    } else if (scaleAll) {
      const sx = ow ? nw / ow : 1, sy = oh ? nh / oh : 1;
      box = { x: cp.x * sx, y: cp.y * sy, w: cp.w * sx, h: c.type === 'line' ? cp.h : cp.h * sy };
    } else {
      const k = cp.constraints || {};
      const [x, w] = axis(k.h || 'LEFT', cp.x, cp.w, ow, nw);
      const [y, h] = axis(k.v || 'TOP', cp.y, cp.h, oh, nh);
      box = { x, y, w, h: c.type === 'line' ? cp.h : h };
    }
    if (Math.abs(box.x - cp.x) < 1e-6 && Math.abs(box.y - cp.y) < 1e-6 && Math.abs(box.w - cp.w) < 1e-6 && Math.abs(box.h - cp.h) < 1e-6) continue;
    const sizeChanged = Math.abs(box.w - cp.w) > 1e-6 || Math.abs(box.h - cp.h) > 1e-6;
    if (!sizeChanged) { ops.push({ op: 'set', id: c.id, props: { x: r3(box.x), y: r3(box.y) } }); continue; }
    const sub = resizeOps(store, c.id, box, { ignoreConstraints: false });
    extraFor(c, cp, box, sub[0].props);
    ops.push(...sub);
  }
}

// Type-specific geometry that lives in box coordinates.
function extraFor(node, p, box, props) {
  const sx = p.w ? box.w / p.w : 1, sy = p.h ? box.h / p.h : 1;
  if (node.type === 'vector' && (p.paths || []).length) {
    props.paths = p.paths.map((path) => ({
      ...path,
      pts: path.pts.map((q) => {
        const o = { x: r3(q.x * sx), y: r3(q.y * sy) };
        for (const [a, b] of [['ix', 'iy'], ['ox', 'oy']]) { if (q[a] != null) o[a] = r3(q[a] * sx); if (q[b] != null) o[b] = r3(q[b] * sy); }
        return o;
      }),
    }));
  }
  if (node.type === 'table') {
    props.cols = (p.cols || []).map((v) => r3(v * sx));
    props.rows = (p.rows || []).map((v) => r3(v * sy));
  }
  if (node.type === 'text') {
    const ar = p.autoResize || 'WIDTH_AND_HEIGHT';
    if (ar === 'WIDTH_AND_HEIGHT' && Math.abs(sx - 1) > 1e-6) props.autoResize = Math.abs(sy - 1) > 1e-6 ? 'NONE' : 'HEIGHT';
    else if (ar === 'HEIGHT' && Math.abs(sy - 1) > 1e-6) props.autoResize = 'NONE';
  }
}

// The box a HUG frame (or auto-sized text) actually takes: stored x/y, measured w/h.
// Parent coordinates (page: cx/cy), like the stored box.
export function hugBox(id, renderer = activeRenderer()) {
  const node = renderer?.store?.nodes.get(id);
  const m = node && renderer.measure(id);
  if (!m) return null;
  const p = propsOf(node);
  return node.type === 'page' ? { x: p.cx || 0, y: p.cy || 0, w: m.w, h: m.h } : { x: p.x || 0, y: p.y || 0, w: m.w, h: m.h };
}
