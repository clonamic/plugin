// One action registry drives keyboard shortcuts, the context menu, the ⌘K palette, and the ⌃⇧? panel.

import { SCHEMA, newId, zBetween, zSeq, propKeys } from "./schema.js";
import * as S from "./select.js";
import * as G from "./geometry.js";
import { TOOLS, setTool } from "./tools.js";
import { el, modal, menu, toast, keyLabel, IS_MAC } from "./ui.js";

const MIME = "application/x-ai-html-ppt+json";
let C = null;
const actions = new Map();
const order = [];
const { get, P } = S;

function def(id, label, group, keys, run, enabled = () => true) {
  const a = { id, label, group, keys: [].concat(keys || []).filter(Boolean), run, enabled };
  actions.set(id, a);
  order.push(a);
}
export const action = (id) => actions.get(id);
export function runAction(id, e) {
  const a = actions.get(id);
  if (!a) return false;
  let ok = false;
  try { ok = a.enabled(); } catch (_) { ok = false; }
  if (!ok) return false;
  try { a.run(e); } catch (err) { console.error(err); toast("작업을 실행하지 못했습니다."); }
  return true;
}

// ---------------- helpers ----------------
const ids = () => C.selection.ids.filter((id) => get(id));
const tops = () => S.sortByOrder(S.topLevel(ids()).filter((id) => !S.isLocked(id) || C.selection.ids.length === 1));
const nonPages = () => tops().filter((id) => get(id).type !== "page");
const has = (n = 1) => () => ids().length >= n;
const hasNonPage = (n = 1) => () => nonPages().length >= n;
const r3 = (v) => Math.round(v * 1000) / 1000;
const textSel = () => ids().filter((id) => get(id).type === "text");
const onlyText = () => !!C.textEdit || (ids().length > 0 && textSel().length === ids().length);

function deltaOps(id, dx, dy) {
  // canvas delta -> parent-local delta
  const n = get(id), p = P(id);
  if (n.type === "page") return { op: "set", id, props: { cx: r3(p.cx + dx), cy: r3(p.cy + dy) } };
  const l = S.apv(S.inv(S.parentM(id)), dx, dy), g = S.geom(id);
  return { op: "set", id, props: { x: r3(g.x + l.x), y: r3(g.y + l.y) } };
}
function zAfter(parent, id) {
  const sibs = C.store.childIds(parent), i = sibs.indexOf(id);
  return zBetween(get(id).z, sibs[i + 1] ? get(sibs[i + 1]).z : null);
}

// Boolean result style (figma-parity §3): UNION/INTERSECT take the top layer's, SUBTRACT/EXCLUDE the bottom's.
function boolStyle(op, kidsBottomToTop) {
  const src = ["UNION", "INTERSECT"].includes(op) ? kidsBottomToTop[kidsBottomToTop.length - 1] : kidsBottomToTop[0];
  const p = src && P(src);
  if (!p) return {};
  const out = {};
  for (const k of ["fills", "strokes", "stroke", "effects"]) if (p[k] !== undefined) out[k] = structuredClone(p[k]);
  return out;
}
// Wrap selected siblings in a new container (group / boolean / frame).
function wrap(type, extra, label) {
  const list = nonPages();
  if (!list.length) return null;
  if (type === "boolean" && list.some((id) => ["section", "frame"].includes(get(id).type))) { toast("불리언은 도형에만 쓸 수 있습니다."); return null; }
  if (type === "boolean") extra = { ...extra, ...boolStyle(extra.op, list) };
  const anchor = list[list.length - 1], parent = get(anchor).parent;
  const PM = S.worldM(parent), PMi = S.inv(PM);
  const b = S.aabbOf(list.flatMap((id) => S.cornersOf(id).map((c) => S.ap(PMi, c.x, c.y))));
  const gid = newId(type);
  const ops = [{ op: "add", node: { id: gid, type, parent, z: zAfter(parent, anchor), props: { x: r3(b.x), y: r3(b.y), w: r3(b.w), h: r3(b.h), ...extra } } }];
  const GM = S.mul(PM, [1, 0, 0, 1, b.x, b.y]), GMi = S.inv(GM);
  const zs = zSeq(null, null, list.length);
  list.forEach((id, i) => {
    const g = S.geom(id), c = S.ap(S.worldM(id), g.w / 2, g.h / 2), lc = S.ap(GMi, c.x, c.y);
    ops.push({ op: "move", id, parent: gid, z: zs[i] });
    ops.push({ op: "set", id, props: { x: r3(lc.x - g.w / 2), y: r3(lc.y - g.h / 2), rotation: r3(S.normDeg(S.worldRot(id) - S.worldRot(parent))) } });
  });
  C.commit(ops, label);
  C.selection.set([gid]);
  return gid;
}
function ungroup() {
  const list = tops().filter((id) => ["group", "boolean", "frame", "section"].includes(get(id).type));
  if (!list.length) return;
  const ops = [], out = [];
  for (const gid of list) {
    const n = get(gid), kids = C.store.childIds(gid);
    const zs = zSeq(n.z, (() => { const s = C.store.childIds(n.parent), i = s.indexOf(gid); return s[i + 1] ? get(s[i + 1]).z : null; })(), kids.length);
    kids.forEach((k, i) => {
      if (get(k).type === "section" && get(n.parent).type !== "page") return;
      const place = S.placeIn(k, n.parent);
      ops.push({ op: "move", id: k, parent: n.parent, z: zs[i] }, { op: "set", id: k, props: place });
      out.push(k);
    });
    ops.push({ op: "del", id: gid });
  }
  C.selection.set([]);
  C.commit(ops, "그룹 해제");
  C.selection.set(out.filter((id) => get(id)));
}
function replaceWith(id, props, label) {
  const n = get(id);
  const nid = newId("vector");
  return [{ op: "add", node: { id: nid, type: "vector", parent: n.parent, z: zAfter(n.parent, id), props: { ...props, name: P(id).name || props.name } } }, { op: "del", id }, nid];
}
function vectorize(fn, label) {
  const ops = [], next = [];
  for (const id of nonPages()) {
    let props;
    try { props = fn(id, C.store); } catch (e) { console.warn(e); continue; }
    if (!props) continue;
    const [a, d, nid] = replaceWith(id, props, label);
    ops.push(a, d); next.push(nid);
  }
  if (!ops.length) { toast("변환할 수 있는 레이어가 없습니다."); return; }
  C.commit(ops, label);
  C.selection.set(next);
}

// z-order within each parent. mode: forward | backward | front | back
function reorder(mode) {
  const byParent = new Map();
  for (const id of nonPages()) { const p = get(id).parent; if (!byParent.has(p)) byParent.set(p, new Set()); byParent.get(p).add(id); }
  const ops = [];
  for (const [pid, set] of byParent) {
    let m = mode;
    const lay = P(pid)?.layout;
    if (lay && lay.dir !== "NONE") m = { forward: "backward", backward: "forward", front: "back", back: "front" }[mode];   // auto layout: reversed (figma-parity §2.3)
    const arr = C.store.childIds(pid).slice();
    if (m === "front") { const keep = arr.filter((x) => !set.has(x)); arr.splice(0, arr.length, ...keep, ...arr.filter((x) => set.has(x))); }
    else if (m === "back") { const keep = arr.filter((x) => !set.has(x)); arr.splice(0, arr.length, ...arr.filter((x) => set.has(x)), ...keep); }
    else if (m === "forward") { for (let i = arr.length - 2; i >= 0; i--) if (set.has(arr[i]) && !set.has(arr[i + 1])) [arr[i], arr[i + 1]] = [arr[i + 1], arr[i]]; }
    else for (let i = 1; i < arr.length; i++) if (set.has(arr[i]) && !set.has(arr[i - 1])) [arr[i], arr[i - 1]] = [arr[i - 1], arr[i]];
    let prev = null;
    for (let i = 0; i < arr.length; i++) {
      const id = arr[i];
      if (!set.has(id)) { prev = get(id).z; continue; }
      let next = null;
      for (let j = i + 1; j < arr.length; j++) if (!set.has(arr[j])) { next = get(arr[j]).z; break; }
      const z = zBetween(prev, next);
      if (z !== get(id).z) ops.push({ op: "move", id, parent: pid, z });
      prev = z;
    }
  }
  C.commit(ops, "순서 변경");
}

function align(how) {
  const list = tops();
  if (!list.length) return;
  const boxes = new Map(list.map((id) => [id, get(id).type === "page" ? S.boxOfPage(id) : S.boxOf(id)]));
  let ref;
  if (list.length === 1) {
    const p = get(list[0]).parent;
    if (!p) return;
    ref = get(p).type === "page" ? S.boxOfPage(p) : S.boxOf(p);
  } else ref = S.aabbOf([...boxes.values()].flatMap((b) => [{ x: b.x, y: b.y }, { x: b.x + b.w, y: b.y + b.h }]));
  const ops = [];
  for (const [id, b] of boxes) {
    let dx = 0, dy = 0;
    if (how === "left") dx = ref.x - b.x;
    if (how === "right") dx = ref.x + ref.w - (b.x + b.w);
    if (how === "hcenter") dx = ref.x + ref.w / 2 - (b.x + b.w / 2);
    if (how === "top") dy = ref.y - b.y;
    if (how === "bottom") dy = ref.y + ref.h - (b.y + b.h);
    if (how === "vcenter") dy = ref.y + ref.h / 2 - (b.y + b.h / 2);
    if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) ops.push(deltaOps(id, dx, dy));
  }
  C.commit(ops, "정렬");
}
function distribute(axis) {
  const list = tops();
  if (list.length < 3) return;
  const lo = axis === "h" ? "x" : "y", sz = axis === "h" ? "w" : "h";
  const items = list.map((id) => ({ id, b: get(id).type === "page" ? S.boxOfPage(id) : S.boxOf(id) })).sort((a, b) => a.b[lo] + a.b[sz] / 2 - (b.b[lo] + b.b[sz] / 2));
  const first = items[0].b, last = items[items.length - 1].b;
  const span = last[lo] + last[sz] - first[lo], sum = items.reduce((a, it) => a + it.b[sz], 0);
  const gap = (span - sum) / (items.length - 1);
  let pos = first[lo];
  const ops = [];
  for (const it of items) {
    const d = pos - it.b[lo];
    if (Math.abs(d) > 1e-6) ops.push(deltaOps(it.id, axis === "h" ? d : 0, axis === "h" ? 0 : d));
    pos += it.b[sz] + gap;
  }
  C.commit(ops, "간격 분배");
}
function tidy() {
  const list = tops();
  if (list.length < 2) return;
  const items = list.map((id) => ({ id, b: get(id).type === "page" ? S.boxOfPage(id) : S.boxOf(id) }));
  items.sort((a, b) => a.b.y - b.b.y);
  const rows = [];
  for (const it of items) {
    const row = rows.find((r) => Math.abs(r.cy - (it.b.y + it.b.h / 2)) < Math.max(r.h, it.b.h) / 2);
    if (row) { row.items.push(it); row.h = Math.max(row.h, it.b.h); } else rows.push({ cy: it.b.y + it.b.h / 2, h: it.b.h, items: [it] });
  }
  rows.forEach((r) => r.items.sort((a, b) => a.b.x - b.b.x));
  const gapsH = rows.flatMap((r) => r.items.slice(1).map((it, i) => it.b.x - (r.items[i].b.x + r.items[i].b.w))).filter((g) => g >= 0);
  const gapsV = rows.slice(1).map((r, i) => Math.min(...r.items.map((it) => it.b.y)) - Math.max(...rows[i].items.map((it) => it.b.y + it.b.h))).filter((g) => g >= 0);
  const avg = (a, d) => (a.length ? Math.round(a.reduce((x, y) => x + y, 0) / a.length) : d);
  const gx = avg(gapsH, 20), gy = avg(gapsV, gx);
  const cols = Math.max(...rows.map((r) => r.items.length));
  const colW = Array.from({ length: cols }, (_, c) => Math.max(...rows.map((r) => r.items[c]?.b.w || 0)));
  const x0 = Math.min(...items.map((it) => it.b.x));
  let y = Math.min(...items.map((it) => it.b.y));
  const ops = [];
  for (const r of rows) {
    let x = x0;
    r.items.forEach((it, c) => {
      const dx = x - it.b.x, dy = y - it.b.y;
      if (Math.abs(dx) > 1e-6 || Math.abs(dy) > 1e-6) ops.push(deltaOps(it.id, dx, dy));
      x += colW[c] + gx;
    });
    y += r.h + gy;
  }
  C.commit(ops, "정돈");
}
function flip(axis) {
  const list = nonPages();
  if (!list.length) return;
  const B = S.unionBox(list), ops = [];
  for (const id of list) {
    const p = P(id), props = axis === "h" ? { flipX: !p.flipX } : { flipY: !p.flipY };
    // Mirroring flips the visual rotation direction too.
    if (p.rotation) props.rotation = r3(S.normDeg(-p.rotation));
    if (list.length > 1) {
      const b = S.boxOf(id), c = { x: b.x + b.w / 2, y: b.y + b.h / 2 };
      const nc = axis === "h" ? { x: 2 * (B.x + B.w / 2) - c.x, y: c.y } : { x: c.x, y: 2 * (B.y + B.h / 2) - c.y };
      Object.assign(props, deltaOps(id, nc.x - c.x, nc.y - c.y).props);
    }
    ops.push({ op: "set", id, props });
  }
  C.commit(ops, "뒤집기");
}
function toggleProp(key, label) {
  const list = tops();
  if (!list.length) return;
  const on = key === "visible" ? list.some((id) => P(id).visible !== false) : !list.every((id) => P(id).locked);
  const v = key === "visible" ? !on : on;
  C.commit(list.map((id) => ({ op: "set", id, props: { [key]: key === "visible" ? (v ? null : false) : (v ? true : null) } })), label);
}

// ---- auto layout ----
function layoutFor(kids, frameBox, horizontal) {
  const boxes = kids.map((k) => S.boxOf(k)).sort((a, b) => (horizontal ? a.x - b.x : a.y - b.y));
  const gaps = boxes.slice(1).map((b, i) => (horizontal ? b.x - (boxes[i].x + boxes[i].w) : b.y - (boxes[i].y + boxes[i].h)));
  const gap = gaps.length ? Math.max(0, Math.round(gaps.reduce((a, b) => a + b, 0) / gaps.length)) : 10;
  let pad = [0, 0, 0, 0];
  if (frameBox && boxes.length) {
    const u = S.aabbOf(boxes.flatMap((b) => [{ x: b.x, y: b.y }, { x: b.x + b.w, y: b.y + b.h }]));
    pad = [u.y - frameBox.y, frameBox.x + frameBox.w - (u.x + u.w), frameBox.y + frameBox.h - (u.y + u.h), u.x - frameBox.x].map((v) => Math.max(0, Math.round(v)));
  }
  return { gap, pad };
}
function addAutoLayout() {
  const list = nonPages();
  const single = list.length === 1 && ["frame"].includes(get(list[0]).type) ? list[0] : (ids().length === 1 && get(ids()[0]).type === "page" ? ids()[0] : null);
  const base = { wrap: false, gapCross: 0, alignMain: "MIN", alignCross: "MIN", strokesIncluded: false, reverseZ: false };
  if (single && !(P(single).layout && P(single).layout.dir !== "NONE")) {
    const kids = C.store.childIds(single).filter((k) => !P(k).layoutChild?.absolute);
    const bs = kids.map((k) => S.boxOf(k));
    const spreadX = bs.length ? Math.max(...bs.map((b) => b.x + b.w / 2)) - Math.min(...bs.map((b) => b.x + b.w / 2)) : 0;
    const spreadY = bs.length ? Math.max(...bs.map((b) => b.y + b.h / 2)) - Math.min(...bs.map((b) => b.y + b.h / 2)) : 0;
    const horizontal = spreadX >= spreadY;
    const fb = get(single).type === "page" ? S.boxOfPage(single) : S.boxOf(single);
    const { gap, pad } = layoutFor(kids, fb, horizontal);
    const ops = [{ op: "set", id: single, props: { layout: { ...base, dir: horizontal ? "HORIZONTAL" : "VERTICAL", gap, pad, sizingH: "FIXED", sizingV: "FIXED" } } }];
    // child order follows position
    const sorted = kids.slice().sort((a, b) => { const A = S.boxOf(a), B = S.boxOf(b); return horizontal ? A.x - B.x : A.y - B.y; });
    zSeq(null, null, sorted.length).forEach((z, i) => ops.push({ op: "move", id: sorted[i], parent: single, z }));
    C.commit(ops, "오토 레이아웃 추가");
    return;
  }
  if (!list.length) return;
  const bs = list.map((k) => S.boxOf(k));
  const spreadX = Math.max(...bs.map((b) => b.x + b.w / 2)) - Math.min(...bs.map((b) => b.x + b.w / 2));
  const spreadY = Math.max(...bs.map((b) => b.y + b.h / 2)) - Math.min(...bs.map((b) => b.y + b.h / 2));
  const horizontal = spreadX >= spreadY;
  const { gap } = layoutFor(list, null, horizontal);
  const sorted = list.slice().sort((a, b) => { const A = S.boxOf(a), B = S.boxOf(b); return horizontal ? A.x - B.x : A.y - B.y; });
  C.selection.set(sorted);
  const fid = wrap("frame", { fills: [], name: "Frame", layout: { ...base, dir: horizontal ? "HORIZONTAL" : "VERTICAL", gap, pad: [0, 0, 0, 0], sizingH: "HUG", sizingV: "HUG" } }, "오토 레이아웃 추가");
  void fid;
}
function removeAutoLayout() {
  const list = ids().filter((id) => P(id).layout && P(id).layout.dir !== "NONE");
  if (!list.length) return;
  const ops = [];
  for (const id of list) {
    const g = S.geom(id);
    // Bake the laid-out positions so nothing moves.
    for (const k of C.store.childIds(id)) {
      if (P(k).layoutChild?.absolute) continue;
      const kg = S.geom(k);
      ops.push({ op: "set", id: k, props: { x: r3(kg.x), y: r3(kg.y), w: r3(kg.w), h: r3(kg.h), layoutChild: null } });
    }
    ops.push({ op: "set", id, props: { layout: null, ...(get(id).type === "page" ? {} : { w: r3(g.w), h: r3(g.h) }) } });
  }
  C.commit(ops, "오토 레이아웃 제거");
}
function fitFrame() {
  const list = nonPages().filter((id) => get(id).type === "frame" && C.store.childIds(id).length);
  const ops = [];
  for (const id of list) {
    const kids = C.store.childIds(id), g = S.geom(id);
    const u = S.aabbOf(kids.flatMap((k) => { const kg = S.geom(k), M = S.localM(kg); return [S.ap(M, 0, 0), S.ap(M, kg.w, 0), S.ap(M, kg.w, kg.h), S.ap(M, 0, kg.h)]; }));
    const box = S.reframe(g, u.x, u.y, u.w, u.h);
    ops.push({ op: "set", id, props: { x: r3(box.x), y: r3(box.y), w: r3(u.w), h: r3(u.h) } });
    for (const k of kids) { const kp = P(k); ops.push({ op: "set", id: k, props: { x: r3(kp.x - u.x), y: r3(kp.y - u.y) } }); }
  }
  C.commit(ops, "프레임 맞춤");
}

// ---- clipboard ----
let memClip = null, memProps = null, lastDup = null;
function payload() {
  const roots = S.sortByOrder(S.topLevel(ids()));
  if (!roots.length) return null;
  const nodes = [];
  const walk = (id) => { const n = get(id); nodes.push({ id: n.id, type: n.type, parent: n.parent, z: n.z, props: structuredClone(n.props) }); for (const c of C.store.childIds(id)) walk(c); };
  roots.forEach(walk);
  const info = roots.map((id) => {
    const g = S.geom(id), c = get(id).type === "page" ? { x: g.x + g.w / 2, y: g.y + g.h / 2 } : S.ap(S.worldM(id), g.w / 2, g.h / 2);
    return { id, cx: c.x, cy: c.y, w: g.w, h: g.h, rot: get(id).type === "page" ? 0 : S.worldRot(id) };
  });
  return { app: "ai-html-ppt", v: 1, deck: C.deckId, roots: info, nodes };
}
function plainText(p) {
  return p.nodes.filter((n) => n.type === "text").map((n) => (n.props.runs || []).map((r) => r.t).join("")).join("\n") || p.nodes.filter((n) => p.roots.some((r) => r.id === n.id)).map((n) => n.props.name || n.type).join("\n");
}
function onCopy(e, cut = false) {
  if (editable(e.target) || !ids().length) return;
  const p = payload();
  if (!p) return;
  e.preventDefault();
  memClip = p;
  try { e.clipboardData.setData(MIME, JSON.stringify(p)); e.clipboardData.setData("text/plain", plainText(p)); } catch (_) { /* memory clip only */ }
  if (cut) deleteSelection("잘라내기");
}
async function onPaste(e) {
  if (editable(e.target)) return;
  const dt = e.clipboardData;
  if (!dt) return;
  e.preventDefault();
  const raw = dt.getData(MIME);
  if (raw) { try { return pasteNodes(JSON.parse(raw), pasteMode); } catch (err) { console.warn(err); } }
  const files = [...dt.files].filter((f) => /^(image|video)\//.test(f.type));
  if (files.length) return C.tools.placeFiles(files, pasteMode === "here" ? pasteAt : null);
  const text = dt.getData("text/plain");
  if (text) { try { const j = JSON.parse(text); if (j?.app === "ai-html-ppt") return pasteNodes(j, pasteMode); } catch (_) { /* plain text */ } return pasteText(text); }
  if (memClip) pasteNodes(memClip, pasteMode);
}
let pasteMode = "default", pasteAt = null;
async function pasteFromMenu(mode, at) {
  // Menu paste has no paste event: use the in-app clipboard, else read images/text from the system.
  if (memClip) return pasteNodes(memClip, mode, at);
  try {
    const items = await navigator.clipboard.read();
    for (const it of items) {
      const img = it.types.find((t) => t.startsWith("image/"));
      if (img) { const b = await it.getType(img); return C.tools.placeFiles([new File([b], "image", { type: img })], mode === "here" ? at : null); }
      if (it.types.includes("text/plain")) { const t = await (await it.getType("text/plain")).text(); try { const j = JSON.parse(t); if (j?.app === "ai-html-ppt") return pasteNodes(j, mode, at); } catch (_) { /* text */ } return pasteText(t); }
    }
  } catch (_) { toast("⌘V로 붙여넣으세요."); }
}
function pasteTarget() {
  const sel = ids();
  if (sel.length === 1 && ["frame", "page", "section"].includes(get(sel[0]).type)) return { parent: sel[0], after: null };
  if (sel.length) { const last = S.sortByOrder(S.topLevel(sel)).pop(); return { parent: get(last).parent, after: last }; }
  const pg = S.pageAt(C.viewport.center()) || C.currentPage() || C.store.childIds(null)[0];
  return { parent: pg, after: null };
}
export function pasteNodes(p, mode = "default", at = null) {
  if (!p || !Array.isArray(p.nodes) || !Array.isArray(p.roots) || !p.roots.length) return;
  const byId = new Map(p.nodes.map((n) => [n.id, n]));
  const known = new Set(SCHEMA.types);
  if (p.nodes.some((n) => !known.has(n.type))) { toast("붙여넣을 수 없는 내용입니다."); return; }
  const map = new Map(p.nodes.map((n) => [n.id, newId(n.type)]));
  const ops = [], newRoots = [];
  const pageRoots = p.roots.filter((r) => byId.get(r.id)?.type === "page");
  const nodeRoots = p.roots.filter((r) => byId.get(r.id)?.type !== "page");
  const addSub = (oid, parent, z, rootProps) => {
    const n = byId.get(oid);
    ops.push({ op: "add", node: { id: map.get(oid), type: n.type, parent, z, props: { ...structuredClone(n.props), ...(rootProps || {}) } } });
    const kids = p.nodes.filter((k) => k.parent === oid).sort((a, b) => (a.z < b.z ? -1 : 1));
    for (const k of kids) addSub(k.id, map.get(oid), k.z);
  };
  if (pageRoots.length) {
    const pages = C.store.childIds(null);
    let x = pages.length ? Math.max(...pages.map((id) => S.boxOfPage(id)).map((b) => b.x + b.w)) + 100 : 0;
    const y = pages.length ? S.boxOfPage(pages[0]).y : 0;
    const zs = zSeq(pages.length ? get(pages[pages.length - 1]).z : null, null, pageRoots.length);
    pageRoots.forEach((r, i) => { addSub(r.id, null, zs[i], { cx: x, cy: y }); x += r.w + 100; newRoots.push(map.get(r.id)); });
  }
  if (nodeRoots.length) {
    let { parent, after } = pasteTarget();
    if (!parent) { toast("붙여넣을 페이지가 없습니다."); return; }
    if (map.has(parent)) parent = get(parent)?.parent;   // never into itself
    // Bounding box of the copied layers on the canvas.
    const bx0 = Math.min(...nodeRoots.map((r) => r.cx - r.w / 2)), by0 = Math.min(...nodeRoots.map((r) => r.cy - r.h / 2));
    const bx1 = Math.max(...nodeRoots.map((r) => r.cx + r.w / 2)), by1 = Math.max(...nodeRoots.map((r) => r.cy + r.h / 2));
    let dx = 0, dy = 0;
    const vis = C.viewport.visibleRect();
    const visible = bx0 < vis.x + vis.w && bx1 > vis.x && by0 < vis.y + vis.h && by1 > vis.y;
    if (mode === "here" && at) { dx = at.x - (bx0 + bx1) / 2; dy = at.y - (by0 + by1) / 2; }
    else if (mode !== "inPlace" && !visible) { const c = C.viewport.center(); dx = c.x - (bx0 + bx1) / 2; dy = c.y - (by0 + by1) / 2; }
    const sibs = C.store.childIds(parent);
    const zs = after ? zSeq(get(after).z, (() => { const i = sibs.indexOf(after); return sibs[i + 1] ? get(sibs[i + 1]).z : null; })(), nodeRoots.length)
      : zSeq(sibs.length ? get(sibs[sibs.length - 1]).z : null, null, nodeRoots.length);
    const PMi = S.inv(S.worldM(parent)), prot = S.worldRot(parent);
    nodeRoots.forEach((r, i) => {
      const n = byId.get(r.id);
      let par = parent;
      if (n.type === "section" && get(par).type !== "page") par = C.store.pageIdOf(par);
      const lc = S.ap(par === parent ? PMi : S.inv(S.worldM(par)), r.cx + dx, r.cy + dy);
      addSub(r.id, par, zs[i], { x: r3(lc.x - r.w / 2), y: r3(lc.y - r.h / 2), rotation: r3(S.normDeg(r.rot - (par === parent ? prot : S.worldRot(par)))) || null });
      newRoots.push(map.get(r.id));
    });
  }
  // Drop the rotation key when zero (back to default).
  for (const o of ops) if (o.node.props.rotation === null || o.node.props.rotation === 0) delete o.node.props.rotation;
  C.commit(ops, "붙여넣기");
  C.selection.set(newRoots);
}
function pasteText(text) {
  const { parent } = pasteTarget();
  if (!parent) return;
  const c = C.viewport.center(), lc = S.toLocal(parent, c);
  const id = newId("text");
  const sibs = C.store.childIds(parent);
  C.commit([{ op: "add", node: { id, type: "text", parent, z: zSeq(sibs.length ? get(sibs[sibs.length - 1]).z : null, null, 1)[0], props: { x: Math.round(lc.x), y: Math.round(lc.y), runs: [{ t: text.slice(0, 100000) }] } } }], "텍스트 붙여넣기");
  C.selection.set([id]);
}
function copyProps() {
  const id = ids()[0];
  if (!id) return;
  const p = P(id), keys = ["fills", "strokes", "stroke", "effects", "opacity", "blend", "radius", "smoothing", "style", "alignH", "alignV", "paragraphSpacing", "indent"];
  memProps = Object.fromEntries(keys.filter((k) => k in p).map((k) => [k, structuredClone(p[k])]));
  toast("속성을 복사했습니다.");
}
function pasteProps() {
  if (!memProps) return;
  const ops = ids().map((id) => {
    const allowed = propKeys(get(id).type), props = {};
    for (const [k, v] of Object.entries(memProps)) if (allowed.has(k)) props[k] = structuredClone(v);
    return { op: "set", id, props };
  }).filter((o) => Object.keys(o.props).length);
  C.commit(ops, "속성 붙여넣기");
}
function deleteSelection(label = "삭제") {
  if (S.vectorEditing()) { S.deleteVectorPoints(); return; }
  const list = S.topLevel(ids()).filter((id) => !S.isLocked(id));
  if (!list.length) return;
  const pages = C.store.childIds(null);
  if (list.filter((id) => get(id).type === "page").length >= pages.length) { toast("마지막 페이지는 지울 수 없습니다."); return; }
  C.selection.clear();
  C.commit(list.map((id) => ({ op: "del", id })), label);
}
function duplicate() {
  const list = S.sortByOrder(S.topLevel(ids()));
  if (!list.length) return;
  if (list.every((id) => get(id).type === "page")) { C.pages?.duplicate(list); return; }
  let offset = { x: 0, y: 0 };
  // Repeat the offset the previous duplicate was moved by (Figma smart duplicate).
  if (lastDup && lastDup.out.length === list.length && lastDup.out.every((id, i) => id === list[i])) {
    const a = P(lastDup.src[0]), b = P(lastDup.out[0]);
    if (a && b) offset = { x: (b.x || 0) - (a.x || 0), y: (b.y || 0) - (a.y || 0) };
  }
  const c = S.cloneOps(list.filter((id) => get(id).type !== "page"), { offset });
  C.commit(c.ops, "복제");
  lastDup = { src: list, out: c.roots };
  C.selection.set(c.roots);
}

// ---- select same ----
function selectSame(fn, label) {
  const ref = ids()[0];
  if (!ref) return;
  const v = JSON.stringify(fn(ref));
  const out = [];
  for (const [id, n] of C.store.nodes) if (n.type !== "page" && !S.isLocked(id) && JSON.stringify(fn(id)) === v) out.push(id);
  C.selection.set(out);
  toast(`${label}: ${out.length}개`);
}

// ⌥⌘A: same type and either the same custom name, or the same look (fills, strokes, effects, radius) and size.
function selectMatching() {
  const ref = ids()[0];
  if (!ref) return;
  const n0 = get(ref), p0 = P(ref);
  const defName = SCHEMA.typeDefaults[n0.type]?.name || "";
  const look = (p) => JSON.stringify([p.fills, p.strokes, p.strokes?.length ? p.stroke : null, p.effects, p.radius ?? null, Math.round(p.w), Math.round(p.h)]);
  const name = p0.name && p0.name !== defName ? p0.name : null, l0 = look(p0);
  const out = [];
  for (const [id, n] of C.store.nodes) {
    if (n.type !== n0.type || S.isLocked(id)) continue;
    const p = P(id);
    if ((name && p.name === name) || look(p) === l0) out.push(id);
  }
  C.selection.set(out);
  toast(`일치 레이어: ${out.length}개`);
}

// ---- text styles ----
function textStyle(fnStyle, nodeProps) {
  if (C.textEdit) {
    const p = P(C.textEdit.id);
    if (fnStyle) { try { C.textEdit.handle?.applyStyle?.(fnStyle(p.style, p)); } catch (e) { console.error(e); } }
    if (nodeProps) C.commit([{ op: "set", id: C.textEdit.id, props: nodeProps(p) }], "텍스트 스타일");
    return;
  }
  const list = textSel();
  if (!list.length) return;
  C.commit(list.map((id) => {
    const p = P(id), props = {};
    if (fnStyle) {
      const part = fnStyle(p.style, p);
      props.style = { ...p.style, ...part };
      // whole-layer change: drop run overrides of the same keys
      if (p.runs?.some((r) => r.s && Object.keys(part).some((k) => k in r.s))) props.runs = p.runs.map((r) => { if (!r.s) return r; const s2 = { ...r.s }; for (const k of Object.keys(part)) delete s2[k]; return Object.keys(s2).length ? { ...r, s: s2 } : { t: r.t, ...(r.fill ? { fill: r.fill } : {}), ...(r.link ? { link: r.link } : {}) }; });
    }
    if (nodeProps) Object.assign(props, nodeProps(p));
    return { op: "set", id, props };
  }), "텍스트 스타일");
}
const lh = (st, d) => { const cur = st.lineHeight?.unit === "PX" ? st.lineHeight.value : Math.round(st.size * 1.2); return { lineHeight: { unit: "PX", value: Math.max(0, cur + d) } }; };
const ls = (st, d) => { const u = st.letterSpacing?.unit || "PERCENT"; return { letterSpacing: { unit: u, value: r3((st.letterSpacing?.value || 0) + (u === "PX" ? d / 10 : d)) } }; };

// ---- batch rename (⌘R) ----
function renameDialog() {
  const list = S.sortByOrder(ids());
  if (!list.length) return;
  if (list.length === 1 && C.layers?.rename(list[0])) return;
  const to = el("input", { value: list.length === 1 ? P(list[0]).name : "$&", "aria-label": "새 이름", autofocus: true });
  const find = el("input", { "aria-label": "찾을 문자열", placeholder: "찾기" });
  const repl = el("input", { "aria-label": "바꿀 문자열", placeholder: "바꾸기" });
  const start = el("input", { type: "number", value: "1", min: "0", "aria-label": "시작 번호" });
  const prev = el("ol", { class: "rename-preview" });
  const names = () => list.map((id, i) => {
    let n = P(id).name || "";
    if (find.value) n = n.split(find.value).join(repl.value);
    const k = Number(start.value) || 0;
    return to.value.replace(/\$&/g, n).replace(/\$n/g, String(k + i)).replace(/\$N/g, String(k + list.length - 1 - i)).slice(0, 200);
  });
  const paint = () => prev.replaceChildren(...names().slice(0, 50).map((n) => el("li", {}, n)));
  [to, find, repl, start].forEach((i) => i.addEventListener("input", paint));
  paint();
  modal({ title: `이름 바꾸기 (${list.length}개)`,
    body: el("div", { class: "form" },
      el("label", {}, "이름", to), el("p", { class: "hint" }, "$& 현재 이름 · $n 오름차순 번호 · $N 내림차순 번호"),
      el("div", { class: "row2" }, el("label", {}, "찾기", find), el("label", {}, "바꾸기", repl)),
      el("label", {}, "시작 번호", start), prev),
    actions: [{ label: "취소" }, { label: "바꾸기", kind: "primary", run: () => {
      const n = names();
      C.commit(list.map((id, i) => ({ op: "set", id, props: { name: n[i] } })).filter((o, i) => o.props.name !== P(list[i]).name), "이름 바꾸기");
    } }] });
}

// ---- view toggles ----
function toggleFlag(k, label) {
  C.flags[k] = !C.flags[k];
  C.applyFlags();
  toast(`${label} ${C.flags[k] ? "켬" : "끔"}`, { timeout: 1500 });
}

// ---------------- registry ----------------
function register() {
  // tools
  for (const t of TOOLS) {
    if (t.action) continue;
    def(`tool.${t.id}`, `${t.label} 도구`, "도구", [t.key, t.alt], () => setTool(t.id));
  }
  def("place", "이미지/비디오 배치…", "도구", "Mod+Shift+K", () => C.tools.pickFiles());
  def("eyedropper", "스포이트", "도구", IS_MAC ? ["I", "Ctrl+C"] : ["I"], () => C.tools.eyedropper());

  // edit
  def("undo", "실행 취소", "편집", "Mod+Z", () => C.store.undo());
  def("redo", "다시 실행", "편집", IS_MAC ? "Mod+Shift+Z" : ["Mod+Shift+Z", "Ctrl+Y"], () => C.store.redo());
  def("copy", "복사", "편집", "Mod+C", () => document.execCommand("copy"), has());
  def("cut", "잘라내기", "편집", "Mod+X", () => document.execCommand("cut"), has());
  def("paste", "붙여넣기", "편집", "Mod+V", () => pasteFromMenu("default"));
  def("pasteInPlace", "제자리에 붙여넣기", "편집", "Mod+Shift+V", () => pasteFromMenu("inPlace"));
  def("pasteHere", "여기에 붙여넣기", "편집", null, () => pasteFromMenu("here", C.lastContextPoint || C.viewport.center()));
  def("duplicate", "복제", "편집", "Mod+D", duplicate, has());
  def("delete", "삭제", "편집", ["Delete", "Backspace"], () => deleteSelection(), () => has()() || !!S.vectorEditing());
  def("selectAll", "모두 선택", "편집", "Mod+A", () => {
    const sel = ids();
    let parent = sel.length ? get(sel[0]).parent : C.currentPage();
    if (sel.length && get(sel[0]).type === "page") parent = null;
    const list = C.store.childIds(parent).filter((id) => !S.isLocked(id) && P(id).visible !== false);
    C.selection.set(list);
  });
  def("selectInverse", "선택 반전", "편집", null, () => {
    const sel = new Set(ids());
    if (!sel.size) return;
    const parent = get([...sel][0]).parent;
    C.selection.set(C.store.childIds(parent).filter((id) => !sel.has(id) && !S.isLocked(id)));
  }, has());
  def("selectNone", "선택 해제", "편집", null, () => C.selection.clear(), has());
  def("copyProps", "속성 복사", "편집", "Mod+Alt+C", copyProps, has());
  def("pasteProps", "속성 붙여넣기", "편집", "Mod+Alt+V", pasteProps, () => has()() && !!memProps);
  def("selectMatching", "일치 레이어 선택", "편집", "Mod+Alt+A", selectMatching, has());
  def("selectSameFill", "같은 칠 모두 선택", "편집", null, () => selectSame((id) => P(id).fills, "같은 칠"), has());
  def("selectSameStroke", "같은 획 모두 선택", "편집", null, () => selectSame((id) => [P(id).strokes, P(id).strokes?.length ? P(id).stroke : null], "같은 획"), has());
  def("selectSameEffect", "같은 효과 모두 선택", "편집", null, () => selectSame((id) => P(id).effects, "같은 효과"), has());
  def("selectSameFont", "같은 글꼴 모두 선택", "편집", null, () => selectSame((id) => (get(id).type === "text" ? [P(id).style.font, P(id).style.weight] : null), "같은 글꼴"), () => textSel().length > 0);

  // text (before arrange/align so shared Windows chords prefer text when text is selected)
  def("textBold", "굵게", "텍스트", "Mod+B", () => textStyle((st) => ({ weight: st.weight >= 600 ? 400 : 700 })), onlyText);
  def("textItalic", "기울임", "텍스트", "Mod+I", () => textStyle((st) => ({ italic: !st.italic })), onlyText);
  def("textUnderline", "밑줄", "텍스트", "Mod+U", () => textStyle((st) => ({ decoration: st.decoration === "UNDERLINE" ? "NONE" : "UNDERLINE" })), onlyText);
  def("textStrike", "취소선", "텍스트", "Mod+Shift+X", () => textStyle((st) => ({ decoration: st.decoration === "STRIKETHROUGH" ? "NONE" : "STRIKETHROUGH" })), onlyText);
  def("textAlignLeft", "텍스트 왼쪽 정렬", "텍스트", "Mod+Alt+L", () => textStyle(null, () => ({ alignH: "LEFT" })), onlyText);
  def("textAlignCenter", "텍스트 가운데 정렬", "텍스트", "Mod+Alt+T", () => textStyle(null, () => ({ alignH: "CENTER" })), onlyText);
  def("textAlignRight", "텍스트 오른쪽 정렬", "텍스트", "Mod+Alt+R", () => textStyle(null, () => ({ alignH: "RIGHT" })), onlyText);
  def("textJustify", "텍스트 양쪽 정렬", "텍스트", "Mod+Alt+J", () => textStyle(null, () => ({ alignH: "JUSTIFIED" })), onlyText);
  def("textBigger", "글자 크기 키우기", "텍스트", "Mod+Shift+Period", () => textStyle((st) => ({ size: st.size + 1 })), onlyText);
  def("textSmaller", "글자 크기 줄이기", "텍스트", "Mod+Shift+Comma", () => textStyle((st) => ({ size: Math.max(1, st.size - 1) })), onlyText);
  def("textHeavier", "굵기 올리기", "텍스트", "Mod+Alt+Period", () => textStyle((st) => ({ weight: Math.min(900, st.weight + 100) })), onlyText);
  def("textLighter", "굵기 내리기", "텍스트", "Mod+Alt+Comma", () => textStyle((st) => ({ weight: Math.max(100, st.weight - 100) })), onlyText);
  def("textLineUp", "행간 늘리기", "텍스트", "Alt+Shift+Period", () => textStyle((st) => lh(st, 1)), onlyText);
  def("textLineDown", "행간 줄이기", "텍스트", "Alt+Shift+Comma", () => textStyle((st) => lh(st, -1)), onlyText);
  def("textTrackUp", "자간 늘리기", "텍스트", "Alt+Period", () => textStyle((st) => ls(st, 1)), onlyText);
  def("textTrackDown", "자간 줄이기", "텍스트", "Alt+Comma", () => textStyle((st) => ls(st, -1)), onlyText);

  // object
  def("group", "그룹", "개체", "Mod+G", () => wrap("group", {}, "그룹"), hasNonPage());
  def("ungroup", "그룹 해제", "개체", ["Mod+Shift+G", "Mod+Backspace"], ungroup, () => tops().some((id) => ["group", "boolean", "frame", "section"].includes(get(id).type)));
  def("frameSelection", "프레임으로 감싸기", "개체", "Mod+Alt+G", () => wrap("frame", { fills: [] }, "프레임으로 감싸기"), hasNonPage());
  def("autoLayout", "오토 레이아웃 추가", "개체", ["Shift+A", "Ctrl+Shift+A"], addAutoLayout, () => hasNonPage()() || (ids().length === 1 && get(ids()[0]).type === "page"));
  def("removeAutoLayout", "오토 레이아웃 제거", "개체", "Alt+Shift+A", removeAutoLayout, () => ids().some((id) => P(id).layout && P(id).layout.dir !== "NONE"));
  def("fitFrame", "프레임을 내용에 맞추기", "개체", "Mod+Alt+Shift+R", fitFrame, () => nonPages().some((id) => get(id).type === "frame"));
  for (const [k, label, key] of [["UNION", "합치기", "Alt+Shift+U"], ["SUBTRACT", "빼기", "Alt+Shift+S"], ["INTERSECT", "교차", "Alt+Shift+I"], ["EXCLUDE", "제외", "Alt+Shift+E"]]) {
    def(`bool.${k}`, `불리언 ${label}`, "개체", key, () => {
      const sel = nonPages();
      if (sel.length === 1 && get(sel[0]).type === "boolean") { C.commit([{ op: "set", id: sel[0], props: { op: k, ...boolStyle(k, C.store.childIds(sel[0])) } }], `불리언 ${label}`); return; }
      wrap("boolean", { op: k, name: label }, `불리언 ${label}`);
    }, () => nonPages().length >= 2 || (nonPages().length === 1 && get(nonPages()[0]).type === "boolean"));
  }
  def("flatten", "평탄화", "개체", ["Mod+E", "Alt+Shift+F"], () => vectorize(G.flattenToVector, "평탄화"), hasNonPage());
  def("outlineStroke", "윤곽선 획", "개체", "Mod+Alt+O", () => vectorize(G.outlineStrokeToVector, "윤곽선 획"), () => nonPages().some((id) => P(id).strokes?.length));
  def("flipH", "가로로 뒤집기", "개체", "Shift+H", () => flip("h"), hasNonPage());
  def("flipV", "세로로 뒤집기", "개체", "Shift+V", () => flip("v"), hasNonPage());
  def("hide", "숨기기/표시", "개체", "Mod+Shift+H", () => toggleProp("visible", "숨기기"), has());
  def("lock", "잠금/잠금 해제", "개체", "Mod+Shift+L", () => toggleProp("locked", "잠금"), has());
  def("rename", "이름 바꾸기", "개체", "Mod+R", renameDialog, has());
  def("enter", "하위 레이어 선택", "선택", "Enter", () => { if (C.tools.penActive()) C.tools.finishPen(); else S.selectDeeper(); }, () => has()() || C.tools.penActive());
  def("parent", "상위 레이어 선택", "선택", ["Shift+Enter", "Backslash"], S.selectParent, has());
  def("nextSibling", "다음 레이어 선택", "선택", "Tab", () => S.selectSibling(1));
  def("prevSibling", "이전 레이어 선택", "선택", "Shift+Tab", () => S.selectSibling(-1));

  // arrange
  def("forward", "앞으로 가져오기", "정렬", "Mod+BracketRight", () => reorder("forward"), hasNonPage());
  def("backward", "뒤로 보내기", "정렬", "Mod+BracketLeft", () => reorder("backward"), hasNonPage());
  def("front", "맨 앞으로 가져오기", "정렬", IS_MAC ? "Mod+Alt+BracketRight" : ["Ctrl+Shift+BracketRight", "Mod+Alt+BracketRight"], () => reorder("front"), hasNonPage());
  def("back", "맨 뒤로 보내기", "정렬", IS_MAC ? "Mod+Alt+BracketLeft" : ["Ctrl+Shift+BracketLeft", "Mod+Alt+BracketLeft"], () => reorder("back"), hasNonPage());
  def("alignLeft", "왼쪽 정렬", "정렬", "Alt+A", () => align("left"), has());
  def("alignRight", "오른쪽 정렬", "정렬", "Alt+D", () => align("right"), has());
  def("alignTop", "위쪽 정렬", "정렬", "Alt+W", () => align("top"), has());
  def("alignBottom", "아래쪽 정렬", "정렬", "Alt+S", () => align("bottom"), has());
  def("alignHCenter", "가로 가운데 정렬", "정렬", "Alt+H", () => align("hcenter"), has());
  def("alignVCenter", "세로 가운데 정렬", "정렬", "Alt+V", () => align("vcenter"), has());
  def("distH", "가로 간격 분배", "정렬", "Ctrl+Alt+H", () => distribute("h"), has(3));
  def("distV", "세로 간격 분배", "정렬", "Ctrl+Alt+V", () => distribute("v"), has(3));
  def("tidy", "정돈", "정렬", "Ctrl+Alt+T", tidy, has(2));

  // nudge (handled specially for Shift = 10)
  for (const [k, dx, dy, l] of [["ArrowLeft", -1, 0, "왼쪽"], ["ArrowRight", 1, 0, "오른쪽"], ["ArrowUp", 0, -1, "위"], ["ArrowDown", 0, 1, "아래"]]) {
    def(`nudge.${k}`, `${l}으로 1 이동 (⇧ 10)`, "선택", [k, `Shift+${k}`], (e) => nudge(dx, dy, e?.shiftKey ? 10 : 1));
  }

  // view
  def("zoomIn", "확대", "보기", ["Shift+Equal", "Mod+Equal", "Equal"], () => C.viewport.zoomStep(1));
  def("zoomOut", "축소", "보기", ["Minus", "Mod+Minus", "Shift+Minus"], () => C.viewport.zoomStep(-1));
  def("zoom100", "100%로 보기", "보기", "Shift+0", () => C.viewport.zoomTo(1));
  def("zoomFit", "전체 보기", "보기", "Shift+1", () => C.viewport.fitAll());
  def("zoomSel", "선택 영역 보기", "보기", "Shift+2", () => C.viewport.fitSelection());
  def("nextPage", "다음 페이지", "보기", "N", () => C.viewport.stepPage(1));
  def("prevPage", "이전 페이지", "보기", "Shift+N", () => C.viewport.stepPage(-1));
  def("pixelGrid", "픽셀 그리드", "보기", "Mod+Quote", () => toggleFlag("pixelGrid", "픽셀 그리드"));
  def("snapPixel", "픽셀 그리드에 맞추기", "보기", "Mod+Shift+Quote", () => toggleFlag("snapPixel", "픽셀 맞춤"));
  def("guides", "레이아웃 가이드", "보기", "Ctrl+G", () => toggleFlag("guides", "레이아웃 가이드"));
  def("rulers", "눈금자", "보기", "Shift+R", () => toggleFlag("rulers", "눈금자"));
  def("outline", "윤곽 보기", "보기", "Mod+Shift+O", () => toggleFlag("outline", "윤곽 보기"));
  def("hideUI", "UI 숨기기", "보기", "Mod+Backslash", () => toggleFlag("hideUI", "UI 숨기기"));
  def("hideSidebars", "사이드바 숨기기", "보기", "Mod+Shift+Backslash", () => toggleFlag("hideSidebars", "사이드바 숨기기"));
  def("layersPanel", "레이어 패널", "보기", "Alt+1", () => C.showLeftTab("layers"));
  def("pagesPanel", "페이지 패널", "보기", "Alt+2", () => C.showLeftTab("pages"));

  // app
  def("palette", "빠른 작업…", "앱", ["Mod+K", "Mod+Slash"], palette);
  def("help", "키보드 단축키", "앱", "Ctrl+Shift+Slash", helpPanel);
  def("present", "현재 페이지부터 발표", "앱", "Mod+Enter", () => C.present(C.currentPage()));
  def("presentStart", "처음부터 발표", "앱", null, () => C.present(null));
  def("export", "PDF로 내보내기…", "앱", "Mod+Shift+E", () => C.openExport());
  def("aiInline", "AI로 수정…", "AI", "Mod+J", () => C.ai?.openInline(), has());
  def("aiPanel", "AI 패널 열기", "AI", null, () => C.showRightTab("ai"));
}

function nudge(dx, dy, k) {
  if (S.vectorEditing()) { S.nudgeVectorPoints(dx * k, dy * k); return; }
  const list = tops().filter((id) => !S.isLocked(id));
  if (!list.length) { C.viewport.panBy(dx * (k === 10 ? 200 : 40), dy * (k === 10 ? 200 : 40)); return; }
  C.commit(list.map((id) => {
    const n = get(id), p = P(id);
    if (n.type === "page") return { op: "set", id, props: { cx: r3(p.cx + dx * k), cy: r3(p.cy + dy * k) } };
    if (S.geom && P(n.parent)?.layout && P(n.parent).layout.dir !== "NONE" && !p.layoutChild?.absolute) return null;
    return { op: "set", id, props: { x: r3(p.x + dx * k), y: r3(p.y + dy * k) } };
  }).filter(Boolean), "이동");
}

// ---------------- keyboard ----------------
const MODS = ["Mod", "Ctrl", "Alt", "Shift"];
function parse(spec) {
  const parts = spec.split("+");
  const key = parts.pop();
  const m = new Set(parts);
  let code = key;
  if (/^[A-Z]$/.test(key)) code = "Key" + key;
  else if (/^[0-9]$/.test(key)) code = "Digit" + key;
  // On mac Mod = ⌘ (meta) and Ctrl = ⌃; elsewhere both mean Ctrl.
  return { code, meta: IS_MAC ? m.has("Mod") : false, ctrl: IS_MAC ? m.has("Ctrl") : m.has("Mod") || m.has("Ctrl"), alt: m.has("Alt"), shift: m.has("Shift"), single: !parts.some((x) => x !== "Shift") };
}
const parsed = new Map();
function matches(a, e) {
  let list = parsed.get(a);
  if (!list) parsed.set(a, (list = a.keys.map(parse)));
  return list.some((k) => {
    let code = e.code;
    if (code === "NumpadAdd") code = "Equal";
    if (code === "NumpadSubtract") code = "Minus";
    if (code === "NumpadEnter") code = "Enter";
    if (/^Numpad[0-9]$/.test(code)) code = "Digit" + code.slice(6);
    if (code !== k.code) return false;
    return k.meta === e.metaKey && k.ctrl === e.ctrlKey && k.alt === e.altKey && k.shift === e.shiftKey;
  }) ? list : null;
}
export function editable(t) {
  if (!t || t === document.body) return false;
  const tag = t.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable;
}
function onKeyDown(e) {
  if (e.isComposing || e.keyCode === 229) return;
  if (document.querySelector(".modal-back")) return;   // modals own the keyboard
  const target = e.target;
  // text editing: Esc ends the edit; text style chords apply to the range
  if (C.textEdit && target.isContentEditable) {
    if (e.key === "Escape") { e.preventDefault(); const id = C.textEdit.id; S.endText(); C.selection.set(get(id) ? [id] : []); return; }
    for (const a of order) if (a.group === "텍스트" && matches(a, e)) { e.preventDefault(); runAction(a.id, e); return; }
    return;
  }
  if (editable(target)) return;
  if (e.code === "Space" && !e.repeat && !e.metaKey && !e.ctrlKey) { e.preventDefault(); C.viewport.setSpace(true); return; }
  if (e.code === "Space") { e.preventDefault(); return; }
  if (e.key === "Escape") { e.preventDefault(); escape(); return; }
  if (S.dragging()) return;
  // Copy/cut/paste go through the native clipboard events.
  if ((e.metaKey || e.ctrlKey) !== false && (IS_MAC ? e.metaKey : e.ctrlKey) && !e.altKey && ["KeyC", "KeyX", "KeyV"].includes(e.code)) {
    if (e.code === "KeyV") { pasteMode = e.shiftKey ? "inPlace" : "default"; }
    if (!e.shiftKey || e.code === "KeyV") return;
  }
  for (const a of order) {
    if (!matches(a, e)) continue;
    if (runAction(a.id, e)) { e.preventDefault(); return; }
  }
  // Tab must never move focus out of the canvas.
  if (e.code === "Tab") e.preventDefault();
}
function escape() {
  if (S.cancelDrag()) return;
  if (C.tools.penActive()) { C.tools.finishPen(); return; }
  if (S.vectorEditing()) { S.exitVectorEdit(); return; }
  if (C.tool !== "move") { setTool("move"); return; }
  if (C.selection.ids.length) {
    // Esc in a nested selection goes up to the parent first (Figma); else clears.
    C.selection.clear();
  }
}

// ---------------- context menu ----------------
function menuItem(id, extra = {}) {
  const a = actions.get(id);
  if (!a) return null;
  let ok = false;
  try { ok = a.enabled(); } catch (_) { ok = false; }
  return { label: extra.label || a.label, hint: a.keys[0] ? keyLabel(a.keys[0]) : "", disabled: !ok, run: () => runAction(id) };
}
function onContextMenu(e) {
  if (editable(e.target)) return;
  e.preventDefault();
  if (C.textEdit) S.endText();
  const cp = C.viewport.clientToPage(e.clientX, e.clientY);
  C.lastContextPoint = cp;
  const pick = S.pickAt(e.clientX, e.clientY, e.metaKey || e.ctrlKey);
  if (pick && !C.selection.ids.includes(pick)) C.selection.set([pick]);
  if (!pick && !S.leafAt(e.clientX, e.clientY)) C.selection.clear();
  const sel = ids();
  const items = [];
  const add = (...xs) => xs.forEach((x) => items.push(typeof x === "string" ? menuItem(x) : x));
  if (sel.length) {
    add("aiInline", { sep: true }, "copy", "cut", "paste", "pasteHere", "duplicate", "delete", { sep: true },
      "front", "forward", "backward", "back", { sep: true },
      "group", "ungroup", "frameSelection", "autoLayout", "removeAutoLayout", { sep: true },
      "bool.UNION", "bool.SUBTRACT", "bool.INTERSECT", "bool.EXCLUDE", "flatten", "outlineStroke", { sep: true },
      "flipH", "flipV", "hide", "lock", "rename", { sep: true },
      "copyProps", "pasteProps", "selectMatching");
    if (sel.length === 1 && get(sel[0]).type === "page") add({ sep: true }, "present");
  } else {
    add("paste", "pasteHere", "selectAll", { sep: true }, "zoomFit", "zoomSel", { sep: true }, "rulers", "guides", "outline", "pixelGrid", { sep: true }, "presentStart", "help");
  }
  const under = S.nodesUnder(e.clientX, e.clientY).filter((id) => get(id).type !== "page").slice(0, 8);
  if (under.length > 1) {
    items.push({ sep: true }, { header: "레이어 선택" });
    for (const id of under) items.push({ label: P(id).name || get(id).type, checked: sel.includes(id), run: () => C.selection.set([id]), onHover: (on) => S.setHover(on ? id : null) });
  }
  // Inapplicable entries are left out (keeps the menu short, like Figma).
  menu({ x: e.clientX, y: e.clientY }, items.filter((it) => it && !it.disabled), { focus: false });
}

// ---------------- ⌘K palette ----------------
function palette() {
  const input = el("input", { type: "search", placeholder: "작업 검색…", "aria-label": "작업 검색", autofocus: true });
  const list = el("ul", { class: "palette-list", role: "listbox" });
  let items = [], idx = 0;
  const paint = () => {
    const q = input.value.trim().toLowerCase();
    items = order.filter((a) => !a.id.startsWith("nudge.") && (!q || a.label.toLowerCase().includes(q) || a.id.toLowerCase().includes(q) || a.group.includes(q)));
    idx = Math.min(idx, Math.max(0, items.length - 1));
    list.replaceChildren(...items.slice(0, 60).map((a, i) => {
      let ok = false;
      try { ok = a.enabled(); } catch (_) { ok = false; }
      return el("li", { role: "option", class: `${i === idx ? "on" : ""}${ok ? "" : " off"}`, "aria-selected": String(i === idx), on: { click: () => go(a), pointerenter: () => { idx = i; mark(); } } },
        el("span", { class: "grp" }, a.group), el("span", { class: "label" }, a.label), el("kbd", {}, a.keys[0] ? keyLabel(a.keys[0]) : ""));
    }));
  };
  const mark = () => [...list.children].forEach((li, i) => { li.classList.toggle("on", i === idx); li.setAttribute("aria-selected", String(i === idx)); if (i === idx) li.scrollIntoView({ block: "nearest" }); });
  let m = null;
  const go = (a) => { m.close(); setTimeout(() => { if (!runAction(a.id)) toast("지금은 실행할 수 없습니다."); }, 0); };
  input.addEventListener("input", () => { idx = 0; paint(); });
  input.addEventListener("keydown", (e) => {
    if (e.isComposing) return;
    if (e.key === "ArrowDown") { e.preventDefault(); idx = Math.min(items.length - 1, idx + 1); mark(); }
    if (e.key === "ArrowUp") { e.preventDefault(); idx = Math.max(0, idx - 1); mark(); }
    if (e.key === "Enter" && items[idx]) { e.preventDefault(); go(items[idx]); }
  });
  paint();
  m = modal({ title: "빠른 작업", body: el("div", { class: "palette" }, input, list) });
}

// ---------------- shortcuts panel ----------------
function helpPanel() {
  const groups = new Map();
  for (const a of order) { if (!a.keys.length) continue; if (!groups.has(a.group)) groups.set(a.group, []); groups.get(a.group).push(a); }
  modal({ title: "키보드 단축키", wide: true,
    body: el("div", { class: "help-grid" }, ...[...groups].map(([g, list]) => el("section", {}, el("h3", {}, g),
      el("dl", {}, ...list.flatMap((a) => [el("dt", {}, a.label), el("dd", {}, ...a.keys.map((k) => el("kbd", {}, keyLabel(k))))]))))) });
}

export function initShortcuts(ctx) {
  C = ctx;
  register();
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", (e) => { if (e.code === "Space") C.viewport.setSpace(false); });
  window.addEventListener("blur", () => C.viewport.setSpace(false));
  document.addEventListener("copy", (e) => onCopy(e, false));
  document.addEventListener("cut", (e) => onCopy(e, true));
  document.addEventListener("paste", (e) => { onPaste(e); pasteMode = "default"; });
  ctx.container.addEventListener("contextmenu", onContextMenu);
  return { runAction, actions: order, contextMenu: onContextMenu, pasteNodes };
}
