// Tools and creation (figma-parity.md §2): toolbar, shape drawing with ⇧/⌥, pen, pencil, text, table,
// image/video placement (picker, paste, drop), eyedropper, frame presets.

import { SCHEMA, newId, defaultsFor, zSeq } from "./schema.js";
import { containerAt, pageAt, toLocal, lineProps, beginText, startCustomDrag, addDrawer, requestDraw, get, P, geom, ap, inv, worldM, dragging } from "./select.js";
import { el, menu, toast, ICON, PRESET_LABEL, keyLabel } from "./ui.js";
import { addPage, presetSize, orientSeg } from "./panels/pages.js";

// id, label, key (shortcut spec), icon, group
export const TOOLS = [
  { id: "move", label: "이동", key: "V", icon: "move", group: "move" },
  { id: "scale", label: "스케일", key: "K", icon: "scale", group: "move" },
  { id: "frame", label: "프레임", key: "F", alt: "A", icon: "frame", group: "frame" },
  { id: "section", label: "섹션", key: "Shift+S", icon: "section", group: "frame" },
  { id: "rect", label: "사각형", key: "R", icon: "rect", group: "shape" },
  { id: "line", label: "선", key: "L", icon: "line", group: "shape" },
  { id: "arrow", label: "화살표", key: "Shift+L", icon: "arrow", group: "shape" },
  { id: "ellipse", label: "타원", key: "O", icon: "ellipse", group: "shape" },
  { id: "polygon", label: "다각형", icon: "polygon", group: "shape" },
  { id: "star", label: "별", icon: "star", group: "shape" },
  { id: "place", label: "이미지/비디오 배치…", key: "Mod+Shift+K", icon: "image", group: "shape", action: true },
  { id: "pen", label: "펜", key: "P", icon: "pen", group: "pen" },
  { id: "pencil", label: "연필", key: "Shift+P", icon: "pencil", group: "pen" },
  { id: "text", label: "텍스트", key: "T", icon: "text", group: "text" },
  { id: "table", label: "표", icon: "table", group: "table" },
  { id: "pin", label: "포커스 핀", key: "Mod+Shift+J", icon: "pin", group: "pin" },
  { id: "hand", label: "손", key: "H", icon: "hand", group: "hand" },
];
const GROUPS = ["move", "frame", "shape", "pen", "text", "table", "pin", "hand"];
const SHAPE_TYPE = { rect: "rect", ellipse: "ellipse", polygon: "polygon", star: "star", frame: "frame", section: "section", table: "table" };

let C = null;
let bar = null, fileInput = null;
const lastInGroup = { move: "move", frame: "frame", shape: "rect", pen: "pen", text: "text", table: "table", pin: "pin", hand: "hand" };

export function initTools(ctx, { toolbar }) {
  C = ctx;
  bar = toolbar;
  fileInput = el("input", { type: "file", accept: "image/*,video/*", multiple: true, hidden: true });
  fileInput.addEventListener("change", () => { const files = [...fileInput.files]; fileInput.value = ""; if (files.length) placeFiles(files, null); });
  document.body.append(fileInput);
  renderBar();
  // drag & drop files onto the canvas
  ctx.container.addEventListener("dragover", (e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
  ctx.container.addEventListener("drop", (e) => {
    const files = [...(e.dataTransfer?.files || [])].filter((f) => /^(image|video)\//.test(f.type));
    if (!files.length) return;
    e.preventDefault();
    placeFiles(files, ctx.viewport.clientToPage(e.clientX, e.clientY));
  });
  addDrawer(drawPen);
  return { setTool, handlePointerDown, placeFiles, pickFiles, eyedropper, finishPen, cancelPen, penActive: () => !!pen };
}

export function setTool(id) {
  if (id === "place") { pickFiles(); return; }
  if (!TOOLS.some((t) => t.id === id)) return;
  if (pen && id !== "pen") finishPen();
  C.tool = id;
  const t = TOOLS.find((x) => x.id === id);
  lastInGroup[t.group] = id;
  C.container.dataset.tool = id;
  C.container.style.cursor = "";
  renderBar();
  C.showFramePresets?.(id === "frame");
  requestDraw();
}

function renderBar() {
  bar.replaceChildren(...GROUPS.map((g) => {
    const tools = TOOLS.filter((t) => t.group === g);
    const cur = TOOLS.find((t) => t.id === lastInGroup[g]) || tools[0];
    const active = tools.some((t) => t.id === C.tool);
    const btn = el("button", { type: "button", class: `tool${active ? " on" : ""}`, "aria-pressed": String(active),
      "aria-label": `${cur.label}${cur.key ? ` (${keyLabel(cur.key)})` : ""}`, title: `${cur.label}${cur.key ? `  ${keyLabel(cur.key)}` : ""}`, html: ICON[cur.icon],
      on: { click: () => setTool(cur.id) } });
    if (tools.length < 2) return btn;
    const more = el("button", { type: "button", class: "tool-more", "aria-label": `${tools.map((t) => t.label).join(", ")} 도구 목록`, title: "도구 목록", html: ICON.chevron,
      on: { click: (e) => menu(e.currentTarget.parentElement, tools.map((t) => ({ label: t.label, hint: t.key ? keyLabel(t.key) : "", checked: C.tool === t.id, run: () => setTool(t.id) })), { side: "top" }) } });
    return el("div", { class: "tool-group" }, btn, more);
  }));
}

// ---------------- creation ----------------
let pen = null;   // {pts:[{x,y,ix,iy,ox,oy}] canvas, hover, closing}
const r3 = (v) => Math.round(v * 1000) / 1000;
const rnd = (v) => (C.flags.snapPixel ? Math.round(v) : r3(v));
const lastPageSize = () => { const pg = C.store.childIds(null); const p = pg.length ? P(pg[pg.length - 1]) : null; return p ? [p.w, p.h] : SCHEMA.presets.SLIDE_16_9; };

export function handlePointerDown(e) {
  const tool = C.tool;
  if (e.button !== 0 || tool === "move" || tool === "scale" || tool === "hand") return false;
  const cp = C.viewport.clientToPage(e.clientX, e.clientY);
  if (tool === "pin") return C.focus ? C.focus.handlePointerDown(e) : false;
  if (tool === "pen") return penDown(e, cp);
  if (tool === "pencil") return pencilDown(e, cp);
  // container under the pointer
  let parent;
  if (tool === "section") parent = pageAt(cp);
  else parent = containerAt(cp, new Set(), { x: e.clientX, y: e.clientY });
  const makesPage = tool === "frame" && !parent;
  if (!parent && !makesPage) { toast(tool === "section" ? "섹션은 페이지 안에 만들 수 있습니다." : "페이지 안에서 그리세요."); return true; }
  e.preventDefault();
  const type = tool === "line" || tool === "arrow" ? "line" : tool === "text" ? "text" : makesPage ? "page" : SHAPE_TYPE[tool];
  const id = newId(type);
  const toL = (pt) => (makesPage ? pt : toLocal(parent, pt));
  const l0 = toL(cp);
  let temp = null, started = false;
  const base = baseProps(tool, type);
  const sibs = makesPage ? C.store.childIds(null) : C.store.childIds(parent);
  const z = zSeq(sibs.length ? get(sibs[sibs.length - 1]).z : null, null, 1)[0];
  C.snapper.prepare([]);
  const boxFor = (ev) => {
    const cur = C.viewport.clientToPage(ev.clientX, ev.clientY);
    let l1 = toL(cur);
    if (type === "line") {
      if (ev.shiftKey) {
        const a = Math.round(Math.atan2(l1.y - l0.y, l1.x - l0.x) / (Math.PI / 4)) * (Math.PI / 4), L = Math.hypot(l1.x - l0.x, l1.y - l0.y);
        l1 = { x: l0.x + Math.cos(a) * L, y: l0.y + Math.sin(a) * L };
      }
      const a = ev.altKey ? { x: 2 * l0.x - l1.x, y: 2 * l0.y - l1.y } : l0;
      return lineProps(a, l1);
    }
    let dx = l1.x - l0.x, dy = l1.y - l0.y;
    if (ev.shiftKey) { const m = Math.max(Math.abs(dx), Math.abs(dy)); dx = Math.sign(dx || 1) * m; dy = Math.sign(dy || 1) * m; }
    let x = ev.altKey ? l0.x - Math.abs(dx) : Math.min(l0.x, l0.x + dx), y = ev.altKey ? l0.y - Math.abs(dy) : Math.min(l0.y, l0.y + dy);
    let w = Math.abs(dx) * (ev.altKey ? 2 : 1), h = Math.abs(dy) * (ev.altKey ? 2 : 1);
    if (C.flags.snapPixel) { const x1 = Math.round(x + w), y1 = Math.round(y + h); x = Math.round(x); y = Math.round(y); w = x1 - x; h = y1 - y; }
    return makesPage ? { cx: x, cy: y, w: Math.max(1, w), h: Math.max(1, h) } : { x, y, w: Math.max(1, w), h: Math.max(1, h) };
  };
  const origin = { x: e.clientX, y: e.clientY };
  let lastBox = null;
  startCustomDrag({
    move(ev) {
      if (!started && Math.hypot(ev.clientX - origin.x, ev.clientY - origin.y) < 3) return;
      lastBox = boxFor(ev);
      if (!started) {
        started = true;
        try { temp = C.store.applyTemp([{ op: "add", node: { id, type, parent: makesPage ? null : parent, z, props: { ...base, ...lastBox } } }]); }
        catch (err) { console.error(err); temp = null; }
      }
      if (temp) C.preview(id, lastBox);
    },
    up() {
      let props;
      if (started && lastBox) props = { ...base, ...lastBox };
      else props = { ...base, ...clickProps(tool, type, l0, makesPage) };
      if (temp) { C.clearPreview(id); temp.revert(); }
      if (type === "text" && started) props.autoResize = "NONE";
      if (type === "table" && started) {
        // table w/h must equal the sums of cols/rows
        props.cols = [0, 1, 2].map(() => Math.max(1, Math.round(props.w / 3)));
        props.rows = [0, 1, 2].map(() => Math.max(1, Math.round(props.h / 3)));
        props.w = props.cols.reduce((a, b) => a + b, 0); props.h = props.rows.reduce((a, b) => a + b, 0);
      }
      if (makesPage) { props.preset = "CUSTOM"; props.orientation = props.w >= props.h ? "landscape" : "portrait"; props.name = `페이지 ${C.store.childIds(null).length + 1}`; }
      C.commit([{ op: "add", node: { id, type, parent: makesPage ? null : parent, z, props } }], `${TOOLS.find((t) => t.id === tool)?.label || "도형"} 만들기`);
      C.selection.set([id]);
      if (makesPage) C.setCurrentPage(id);
      setTool("move");
      if (type === "text") beginText(id, { created: true });
    },
    cancel() { if (temp) { C.clearPreview(id); temp.revert(); } },
  });
  return true;
}
function baseProps(tool, type) {
  const p = {};
  if (tool === "arrow") p.stroke = { ...defaultsFor("line").stroke, capEnd: "ARROW_LINES" };
  if (tool === "arrow") p.name = "Arrow";
  if (type === "text") p.runs = [{ t: "" }];
  return p;
}
function clickProps(tool, type, l0, makesPage) {
  if (type === "line") return lineProps(l0, { x: l0.x + 100, y: l0.y });
  if (type === "text") return { x: rnd(l0.x), y: rnd(l0.y), autoResize: "WIDTH_AND_HEIGHT" };
  if (makesPage) { const [w, h] = lastPageSize(); return { cx: rnd(l0.x), cy: rnd(l0.y), w, h }; }
  if (type === "table") return { x: rnd(l0.x), y: rnd(l0.y), w: 360, h: 120, cols: [120, 120, 120], rows: [40, 40, 40] };
  if (type === "section") return { x: rnd(l0.x), y: rnd(l0.y), w: 600, h: 400 };
  return { x: rnd(l0.x), y: rnd(l0.y), w: 100, h: 100 };
}

// ---------------- pen ----------------
function penDown(e, cp) {
  e.preventDefault();
  const z = C.viewport.zoom;
  if (!pen) {
    const parent = containerAt(cp, new Set(), { x: e.clientX, y: e.clientY });
    if (!parent) { toast("페이지 안에서 그리세요."); return true; }
    pen = { pts: [], parent, cursor: cp };
  }
  const first = pen.pts[0];
  if (first && pen.pts.length >= 2 && Math.hypot(cp.x - first.x, cp.y - first.y) * z < 8) { finishPen(true); return true; }
  const pt = { x: cp.x, y: cp.y, ix: cp.x, iy: cp.y, ox: cp.x, oy: cp.y };
  pen.pts.push(pt);
  const origin = { x: e.clientX, y: e.clientY };
  startCustomDrag({
    move(ev) {
      const c = C.viewport.clientToPage(ev.clientX, ev.clientY);
      if (Math.hypot(ev.clientX - origin.x, ev.clientY - origin.y) < 2) return;
      pt.ox = c.x; pt.oy = c.y;
      if (!ev.altKey) { pt.ix = 2 * pt.x - c.x; pt.iy = 2 * pt.y - c.y; }
      requestDraw();
    },
    up() { requestDraw(); },
    cancel() { requestDraw(); },
  });
  requestDraw();
  return true;
}
export function finishPen(closed = false) {
  const p = pen;
  pen = null;
  requestDraw();
  if (!p || p.pts.length < 2) return;
  addVector([{ closed, pts: p.pts }], p.parent, "펜", {});
  setTool("move");
}
export function cancelPen() { pen = null; requestDraw(); }
function addVector(paths, parent, label, extra) {
  // canvas -> parent coordinates, then rebase to the bbox
  const M = inv(worldM(parent));
  const loc = paths.map((pa) => ({ closed: pa.closed, pts: pa.pts.map((q) => {
    const a = ap(M, q.x, q.y), i = ap(M, q.ix, q.iy), o = ap(M, q.ox, q.oy);
    return { x: a.x, y: a.y, ix: i.x, iy: i.y, ox: o.x, oy: o.y };
  }) }));
  const all = loc.flatMap((pa) => pa.pts.flatMap((q) => [[q.x, q.y], [q.ix, q.iy], [q.ox, q.oy]]));
  const x0 = Math.min(...all.map((a) => a[0])), y0 = Math.min(...all.map((a) => a[1]));
  const x1 = Math.max(...all.map((a) => a[0])), y1 = Math.max(...all.map((a) => a[1]));
  const rel = loc.map((pa) => ({ closed: pa.closed, pts: pa.pts.map((q) => ({ x: r3(q.x - x0), y: r3(q.y - y0), ix: r3(q.ix - x0), iy: r3(q.iy - y0), ox: r3(q.ox - x0), oy: r3(q.oy - y0) })) }));
  const id = newId("vector");
  const sibs = C.store.childIds(parent);
  const z = zSeq(sibs.length ? get(sibs[sibs.length - 1]).z : null, null, 1)[0];
  C.commit([{ op: "add", node: { id, type: "vector", parent, z, props: { x: r3(x0), y: r3(y0), w: r3(Math.max(0.01, x1 - x0)), h: r3(Math.max(0.01, y1 - y0)), paths: rel, ...extra } } }], label);
  C.selection.set([id]);
  return id;
}
function drawPen(svg, { toS, s }) {
  if (!pen || !pen.pts.length) return;
  const pts = pen.pts;
  let d = "";
  const P0 = toS(pts[0]);
  d = `M${P0.x},${P0.y}`;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], c1 = toS({ x: a.ox, y: a.oy }), c2 = toS({ x: b.ix, y: b.iy }), e = toS(b);
    d += `C${c1.x},${c1.y} ${c2.x},${c2.y} ${e.x},${e.y}`;
  }
  svg.append(s("path", { d, class: "ov-path" }));
  if (pen.cursor && !dragging()) {
    const last = pts[pts.length - 1], c1 = toS({ x: last.ox, y: last.oy }), e = toS(pen.cursor);
    svg.append(s("path", { d: `M${toS(last).x},${toS(last).y}Q${c1.x},${c1.y} ${e.x},${e.y}`, class: "ov-rubber" }));
  }
  const lastPt = pts[pts.length - 1];
  for (const side of ["i", "o"]) {
    const h = { x: lastPt[side + "x"], y: lastPt[side + "y"] };
    if (h.x === lastPt.x && h.y === lastPt.y) continue;
    const a = toS(lastPt), b = toS(h);
    svg.append(s("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "ov-bez" }));
    svg.append(s("circle", { cx: b.x, cy: b.y, r: 3, class: "ov-bez-h" }));
  }
  pts.forEach((q, i) => { const c = toS(q); svg.append(s("circle", { cx: c.x, cy: c.y, r: i === 0 && pts.length >= 2 ? 5 : 4, class: i === pts.length - 1 ? "ov-pt on" : "ov-pt" })); });
}
// rubber band follows the pointer
function trackPen(e) { if (pen) { pen.cursor = C.viewport.clientToPage(e.clientX, e.clientY); requestDraw(); } }

// ---------------- pencil ----------------
function pencilDown(e, cp) {
  e.preventDefault();
  const parent = containerAt(cp, new Set(), { x: e.clientX, y: e.clientY });
  if (!parent) { toast("페이지 안에서 그리세요."); return true; }
  const raw = [cp];
  const remove = addDrawer((svg, { toS, s }) => {
    svg.append(s("polyline", { points: raw.map((p) => { const q = toS(p); return `${q.x},${q.y}`; }).join(" "), class: "ov-path" }));
  });
  startCustomDrag({
    move(ev) {
      const c = C.viewport.clientToPage(ev.clientX, ev.clientY), l = raw[raw.length - 1];
      if (Math.hypot(c.x - l.x, c.y - l.y) * C.viewport.zoom >= 1.5) raw.push(c);
    },
    up() {
      remove();
      if (raw.length < 2) return;
      const pts = simplify(raw, 1.2 / C.viewport.zoom);
      const n = pts.length;
      const out = pts.map((p, i) => {
        const a = pts[Math.max(0, i - 1)], b = pts[Math.min(n - 1, i + 1)];
        const tx = (b.x - a.x) / 6, ty = (b.y - a.y) / 6;
        const end = i === 0 || i === n - 1;
        return { x: p.x, y: p.y, ix: end ? p.x : p.x - tx, iy: end ? p.y : p.y - ty, ox: end ? p.x : p.x + tx, oy: end ? p.y : p.y + ty };
      });
      const stroke = { ...defaultsFor("vector").stroke, weight: 2, capStart: "ROUND", capEnd: "ROUND", join: "ROUND" };
      addVector([{ closed: false, pts: out }], parent, "연필", { stroke, name: "Pencil" });
    },
    cancel() { remove(); },
  });
  return true;
}
// Ramer–Douglas–Peucker
function simplify(pts, eps) {
  if (pts.length < 3) return pts;
  const keep = new Uint8Array(pts.length); keep[0] = keep[pts.length - 1] = 1;
  const stack = [[0, pts.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    let md = 0, mi = -1;
    const A = pts[a], B = pts[b], dx = B.x - A.x, dy = B.y - A.y, L = Math.hypot(dx, dy) || 1;
    for (let i = a + 1; i < b; i++) { const d = Math.abs((pts[i].x - A.x) * dy - (pts[i].y - A.y) * dx) / L; if (d > md) { md = d; mi = i; } }
    if (md > eps && mi > 0) { keep[mi] = 1; stack.push([a, mi], [mi, b]); }
  }
  return pts.filter((_, i) => keep[i]);
}

// ---------------- images & video ----------------
export function pickFiles() { fileInput.click(); }
async function naturalSize(file, info) {
  if (info?.w && info?.h) return [info.w, info.h];
  const url = URL.createObjectURL(file);
  try {
    if (file.type.startsWith("video/")) {
      return await new Promise((res) => {
        const v = document.createElement("video");
        v.preload = "metadata"; v.muted = true;
        v.onloadedmetadata = () => res([v.videoWidth || 640, v.videoHeight || 360]);
        v.onerror = () => res([640, 360]);
        v.src = url;
      });
    }
    const img = new Image();
    img.src = url;
    await img.decode();
    return [img.naturalWidth || 100, img.naturalHeight || 100];
  } catch (_) { return [400, 300]; } finally { URL.revokeObjectURL(url); }
}
export async function placeFiles(files, at) {
  files = files.filter((f) => /^(image|video)\//.test(f.type));
  if (!files.length) return;
  const close = toast(`업로드 중… (${files.length}개)`, { timeout: 0 });
  const center = at || C.viewport.center();
  let parent = containerAt(center) || C.currentPage() || C.store.childIds(null)[0];
  if (!parent) { close(); toast("페이지가 없습니다."); return; }
  const results = [];
  for (const f of files) {
    try {
      const info = await C.uploadAsset(f);
      const [w, h] = await naturalSize(f, info);
      results.push({ f, info, w, h });
    } catch (e) { toast(`${f.name}: 업로드 실패`, { kind: "error" }); }
  }
  close();
  if (!results.length) return;
  // Fit inside 80% of the parent box and lay out side by side.
  const pg = geom(parent);
  const maxW = pg.w * 0.8, maxH = pg.h * 0.8;
  const lc = toLocal(parent, center);
  const sized = results.map((r) => { const k = Math.min(1, maxW / r.w, maxH / r.h); return { ...r, w: Math.max(1, Math.round(r.w * k)), h: Math.max(1, Math.round(r.h * k)) }; });
  const total = sized.reduce((a, r) => a + r.w, 0) + 20 * (sized.length - 1);
  let x = lc.x - total / 2;
  const sibs = C.store.childIds(parent);
  const zs = zSeq(sibs.length ? get(sibs[sibs.length - 1]).z : null, null, sized.length);
  const ops = [], ids = [];
  sized.forEach((r, i) => {
    const video = r.f.type.startsWith("video/");
    const id = newId(video ? "video" : "rect");
    const props = { x: Math.round(x), y: Math.round(lc.y - r.h / 2), w: r.w, h: r.h, name: r.f.name.replace(/\.[^.]+$/, "").slice(0, 200) || (video ? "Video" : "Image") };
    if (video) props.asset = r.info.hash;
    else props.fills = [{ type: "IMAGE", asset: r.info.hash, mode: "FILL", scale: 1, rotation: 0, visible: true, opacity: 1, blend: "NORMAL" }];
    ops.push({ op: "add", node: { id, type: video ? "video" : "rect", parent, z: zs[i], props } });
    ids.push(id);
    x += r.w + 20;
  });
  C.commit(ops, files.length > 1 ? "이미지 배치" : video0(files) ? "비디오 배치" : "이미지 배치");
  C.selection.set(ids);
  setTool("move");
}
const video0 = (files) => files[0]?.type.startsWith("video/");

// ---------------- eyedropper ----------------
export async function eyedropper() {
  if (!("EyeDropper" in window)) { toast("이 브라우저는 스포이트를 지원하지 않습니다."); return; }
  let hex;
  try { hex = (await new window.EyeDropper().open()).sRGBHex; } catch (_) { return; }   // cancelled
  const color = /^#[0-9a-f]{6}$/i.test(hex) ? hex.toUpperCase() + "FF" : null;
  if (!color) return;
  const ids = C.selection.ids.filter((id) => get(id) && !["group", "boolean"].includes(get(id).type));
  if (!ids.length) {
    try { await navigator.clipboard.writeText(color.slice(0, 7)); toast(`${color.slice(0, 7)} 복사됨`); } catch (_) { toast(color.slice(0, 7)); }
    return;
  }
  const ops = ids.map((id) => {
    const p = P(id);
    const fills = (p.fills || []).slice();
    let i = -1;
    for (let k = fills.length - 1; k >= 0; k--) if (fills[k].type === "SOLID") { i = k; break; }
    if (i >= 0) fills[i] = { ...fills[i], color };
    else fills.push({ type: "SOLID", color, opacity: 1, visible: true, blend: "NORMAL" });
    return { op: "set", id, props: { fills } };
  });
  C.commit(ops, "색 추출");
}

// ---------------- frame presets (right panel while the frame tool is active) ----------------
export function renderFramePresets(box) {
  let orient = null;   // natural: paper portrait, slides landscape
  const list = el("div", { class: "preset-list" });
  const groups = [["프레젠테이션", ["SLIDE_16_9", "SLIDE_4_3"]], ["용지", ["A3", "A4", "A5", "A6", "LETTER", "LEGAL", "TABLOID"]]];
  const known = new Set(groups.flatMap((g) => g[1]));
  const extra = Object.keys(SCHEMA.presets).filter((k) => !known.has(k));
  if (extra.length) groups.push(["기타", extra]);
  const paint = () => {
    list.replaceChildren(...groups.flatMap(([title, keys]) => [
      el("div", { class: "preset-head" }, title),
      ...keys.map((k) => {
        const [w, h] = presetSize(k, orient);
        return el("button", { type: "button", class: "preset", on: { click: () => { addPage(C, { preset: k, orientation: orient }); setTool("move"); } } },
          el("span", {}, PRESET_LABEL[k] || k), el("span", { class: "dim" }, `${w}×${h}`));
      }),
    ]));
  };
  const seg = orientSeg(() => orient, (v) => { orient = v; paint(); });
  paint();
  box.replaceChildren(el("div", { class: "panel-title" }, "프레임"), el("p", { class: "hint" }, "캔버스에서 끌어 그리거나 크기를 고르면 새 페이지가 생깁니다. 페이지 안에서 그리면 프레임이 됩니다."), seg, list);
}

export function trackPointer(e) { trackPen(e); }
