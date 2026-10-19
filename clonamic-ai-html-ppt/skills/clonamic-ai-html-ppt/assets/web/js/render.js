// The one renderer for canvas (edit), presentation (present) and PDF (print). Contract: format.md §6.
//
// DOM per node: div.ppt-n[data-id] positioned at x,y (page: cx,cy in edit) with rotation/flip as a
// CSS transform around the center. Inside, in paint order:
//   pre decorations (.ppt-d: behind-shadows, fill layers, fill SVG, inner shadow)
//   content (.ppt-c children container for containers | .ppt-tx text | table grid | media)
//   post decorations (strokes, guides, labels)
// Approximations (documented): effect blend modes are ignored (shadows composite normally);
// LINEAR_BURN falls back to color-burn where `plus-darker` is unsupported; image filters are an
// SVG color-matrix + tone-curve approximation; rotated children in auto layout are laid out by
// their unrotated box; text INSIDE strokes render as CENTER; per-side stroke weights with dashes
// or corner smoothing use the uniform weight; drop-shadow spread on non-box shapes uses a square
// morphology kernel.
import { propsOf, defaultsFor } from './schema.js';
import { smoothRectD, radiiOf, nodeGeometry, parsePath, serializePath, openEnds, capShapes, transformD } from './geometry.js';
import { renderText, styleCSS, rgba, lineHeightPx, editingId } from './text.js';

const CONTAINERS = new Set(['page', 'frame', 'section', 'group', 'boolean']);
const BOXES = new Set(['rect', 'frame', 'page', 'section', 'video', 'table']);
const SHAPES = new Set(['ellipse', 'polygon', 'star', 'line', 'vector', 'boolean']);
const HEX64 = /^[0-9a-f]{64}$/;
const n2 = (v) => Math.round((+v || 0) * 100) / 100;
const vis = (arr) => (arr || []).filter((x) => x && x.visible !== false);

let PLUS_DARKER = 'color-burn';
const BLEND = {
  PASS_THROUGH: 'normal', NORMAL: 'normal', DARKEN: 'darken', MULTIPLY: 'multiply', LINEAR_BURN: 'plus-darker', COLOR_BURN: 'color-burn',
  LIGHTEN: 'lighten', SCREEN: 'screen', LINEAR_DODGE: 'plus-lighter', COLOR_DODGE: 'color-dodge', OVERLAY: 'overlay', SOFT_LIGHT: 'soft-light',
  HARD_LIGHT: 'hard-light', DIFFERENCE: 'difference', EXCLUSION: 'exclusion', HUE: 'hue', SATURATION: 'saturation', COLOR: 'color', LUMINOSITY: 'luminosity',
};
const blendCSS = (b) => (b === 'LINEAR_BURN' ? PLUS_DARKER : BLEND[b] || 'normal');

const BASE_CSS = `
.ppt-n{position:absolute;box-sizing:border-box;transform-origin:50% 50%;pointer-events:auto}
.ppt-edit .ppt-n{user-select:none;-webkit-user-select:none}
.ppt-d{position:absolute;pointer-events:none;box-sizing:border-box}
.ppt-c{position:absolute;left:0;top:0;width:100%;height:100%;box-sizing:border-box}
.ppt-c.ppt-al{position:relative;display:flex}
.ppt-t-group,.ppt-t-group>.ppt-c,.ppt-shape,.ppt-t-boolean>.ppt-c{pointer-events:none}
.ppt-t-group>.ppt-c>.ppt-n,.ppt-t-boolean>.ppt-c>.ppt-n{pointer-events:auto}
.ppt-t-boolean>.ppt-c{visibility:hidden}
.ppt-sv{position:absolute;overflow:visible;pointer-events:none}
.ppt-sv .ppt-hit{pointer-events:all}
.ppt-sv .ppt-hit.ppt-open{pointer-events:stroke}
.ppt-tx{position:relative;outline:none;overflow-wrap:break-word;flex:none}
.ppt-p{margin:0}
.ppt-tx a{color:inherit;-webkit-text-fill-color:inherit}
.ppt-mk{display:inline-block;width:1.5em;margin-left:-1.5em;text-indent:0;text-decoration:none;user-select:none;-webkit-user-select:none}
.ppt-editing{cursor:text;user-select:text;-webkit-user-select:text;caret-color:auto}
.ppt-tb{position:relative;display:grid;box-sizing:border-box}
.ppt-cell{display:flex;flex-direction:column;overflow:hidden;box-sizing:border-box;padding:4px 8px;min-width:0}
.ppt-media{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;pointer-events:none;display:block}
.ppt-pl{position:absolute;white-space:nowrap;max-width:none;font:500 calc(12px / var(--zoom, 1))/1.25 Inter,"Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;color:#8c8c8c;transform:translateY(-100%);padding-bottom:calc(4px / var(--zoom, 1));user-select:none;-webkit-user-select:none;cursor:default}
.ppt-sl{left:0;top:0;transform:translateY(calc(-100% - 4px / var(--zoom, 1)));white-space:nowrap;font:500 calc(12px / var(--zoom, 1))/1 Inter,"Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif;color:#1e1e1e;background:rgba(255,255,255,.9);border-radius:calc(4px / var(--zoom, 1));padding:calc(4px / var(--zoom, 1)) calc(6px / var(--zoom, 1))}
.ppt-twin{pointer-events:none!important}
.ppt-slice,.ppt-slice *{pointer-events:none!important}
.ppt-twin *{pointer-events:none!important}
::highlight(ppt-text-sel){background-color:rgba(13,153,255,.3)}
`;

function injectCSS() {
  if (typeof document === 'undefined' || document.getElementById('ppt-render-css')) return;
  const s = document.createElement('style');
  s.id = 'ppt-render-css';
  s.textContent = BASE_CSS;
  document.head.appendChild(s);
  try { if (CSS.supports('mix-blend-mode', 'plus-darker')) PLUS_DARKER = 'plus-darker'; } catch { /* old engine */ }
}

// Nested props may be partial (format.md §8: `style: {size: 72}`); fill them from the defaults.
const DEFS = new Map();
const LAYOUT_DEF = { dir: 'HORIZONTAL', wrap: false, gap: 0, gapCross: 0, pad: [0, 0, 0, 0], alignMain: 'MIN', alignCross: 'MIN', sizingH: 'FIXED', sizingV: 'FIXED', strokesIncluded: false, reverseZ: false };
const STROKE_DEF = { weight: 1, align: 'INSIDE', sides: null, dash: [], dashCap: 'NONE', join: 'MITER', miterLimit: 4, capStart: 'NONE', capEnd: 'NONE' };
export function normalize(type, p) {
  let d = DEFS.get(type);
  if (!d) { d = defaultsFor(type); DEFS.set(type, d); }
  let q = p;
  for (const k of ['style', 'stroke', 'arc', 'layoutChild', 'constraints']) {
    const base = k === 'stroke' ? { ...STROKE_DEF, ...d.stroke } : d[k];
    if (p[k] && base && p[k] !== d[k]) { if (q === p) q = { ...p }; q[k] = { ...base, ...p[k] }; }
  }
  if (p.layout) { if (q === p) q = { ...p }; q.layout = { ...LAYOUT_DEF, ...p.layout }; }
  return q;
}

let ridSeq = 0;
let active = null;
export const activeRenderer = () => active;

const cssUrl = (u) => `url('${String(u).replace(/['"\\()\s]/g, (c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))}')`;
const attr = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const hex6 = (c) => (/^#[0-9a-f]{6}/i.test(c || '') ? c.slice(0, 7) : '#000000');
const alphaOf = (c) => (/^#[0-9a-f]{8}$/i.test(c || '') ? parseInt(c.slice(7, 9), 16) / 255 : 1);
const sortStops = (stops) => [...(stops || [])].sort((a, b) => a.p - b.p);

// ---------- CSS paint layers ----------

function stopsCSS(stops, op, scale = 1) {
  const s = sortStops(stops);
  if (!s.length) return 'transparent, transparent';
  if (s.length === 1) s.push(s[0]);
  return s.map((st) => `${rgba(st.color, op)} ${n2(st.p * 100 * scale)}%`).join(', ');
}

// Gradient line of CSS linear-gradient at `deg` over w×h; returns position t (0..1) of a box point.
function cssLineT(deg, w, h) {
  const t = (deg * Math.PI) / 180, ux = Math.sin(t), uy = -Math.cos(t);
  const L = Math.abs(w * ux) + Math.abs(h * uy) || 1;
  return (x, y) => ((x - w / 2) * ux + (y - h / 2) * uy) / L + 0.5;
}

// One paint → CSS background layers (top first) [{img, size, pos, repeat}], opacity baked in except IMAGE.
function cssLayers(paint, w, h, ctx) {
  const op = paint.opacity ?? 1;
  switch (paint.type) {
    case 'SOLID': { const c = rgba(paint.color, op); return [{ img: `linear-gradient(${c}, ${c})` }]; }
    case 'LINEAR': return [{ img: `linear-gradient(${n2((paint.angle || 0) + 90)}deg, ${stopsCSS(paint.stops, op)})` }];
    case 'RADIAL': return [{ img: `radial-gradient(${n2((paint.rx ?? 0.5) * 100)}% ${n2((paint.ry ?? 0.5) * 100)}% at ${n2((paint.cx ?? 0.5) * 100)}% ${n2((paint.cy ?? 0.5) * 100)}%, ${stopsCSS(paint.stops, op)})` }];
    case 'ANGULAR': return [{ img: `conic-gradient(from ${n2((paint.angle || 0) + 90)}deg at ${n2((paint.cx ?? 0.5) * 100)}% ${n2((paint.cy ?? 0.5) * 100)}%, ${stopsCSS(paint.stops, op)})` }];
    case 'DIAMOND': {
      // four quadrant linear gradients (iso-lines parallel to the diamond edges) over the last stop color
      const cx = (paint.cx ?? 0.5) * w, cy = (paint.cy ?? 0.5) * h, rx = Math.max(0.5, (paint.rx ?? 0.5) * w), ry = Math.max(0.5, (paint.ry ?? 0.5) * h);
      const st = sortStops(paint.stops), last = rgba(st.length ? st[st.length - 1].color : '#00000000', op);
      const g = (dir) => `linear-gradient(to ${dir}, ${stopsCSS(st, op, 0.5)}, ${last} 50%)`;
      const L = (dir, x, y) => ({ img: g(dir), size: `${n2(rx)}px ${n2(ry)}px`, pos: `${n2(x)}px ${n2(y)}px`, repeat: 'no-repeat' });
      return [L('top left', cx - rx, cy - ry), L('top right', cx, cy - ry), L('bottom right', cx, cy), L('bottom left', cx - rx, cy), { img: `linear-gradient(${last}, ${last})` }];
    }
    case 'IMAGE': {
      const url = ctx.src(paint.asset, ctx.id);
      if (!url) return [];
      const mode = paint.mode || 'FILL';
      if (mode === 'FIT') return [{ img: cssUrl(url), size: 'contain', pos: 'center', repeat: 'no-repeat' }];
      if (mode === 'TILE') {
        const nat = ctx.natural(paint.asset, ctx.id), s = paint.scale || 1;
        return [{ img: cssUrl(url), size: nat ? `${n2(nat.w * s)}px ${n2(nat.h * s)}px` : 'auto', pos: '0 0', repeat: 'repeat' }];
      }
      if (mode === 'CROP' && paint.crop) {
        const c = paint.crop, cw = Math.max(0.001, c.w ?? 1), ch = Math.max(0.001, c.h ?? 1);
        const px = cw < 1 ? ((c.x || 0) / (1 - cw)) * 100 : 0, py = ch < 1 ? ((c.y || 0) / (1 - ch)) * 100 : 0;
        return [{ img: cssUrl(url), size: `${n2(100 / cw)}% ${n2(100 / ch)}%`, pos: `${n2(px)}% ${n2(py)}%`, repeat: 'no-repeat' }];
      }
      return [{ img: cssUrl(url), size: 'cover', pos: 'center', repeat: 'no-repeat' }];
    }
    default: return [];
  }
}

const hasFilters = (p) => p.filters && Object.values(p.filters).some((v) => +v);
const simplePaint = (p) => ['NORMAL', 'PASS_THROUGH', undefined].includes(p.blend) && (p.type !== 'IMAGE' || ((p.opacity ?? 1) >= 1 && !hasFilters(p) && !((p.rotation || 0) % 360)));

// Paint stack (bottom→top) → background CSS declarations.
function bgCSS(paints, w, h, ctx) {
  const layers = [];
  for (let i = paints.length - 1; i >= 0; i--) layers.push(...cssLayers(paints[i], w, h, ctx));
  if (!layers.length) return '';
  return `background-image:${layers.map((l) => l.img).join(',')};background-size:${layers.map((l) => l.size || 'auto').join(',')};` +
    `background-position:${layers.map((l) => l.pos || '0 0').join(',')};background-repeat:${layers.map((l) => l.repeat || 'no-repeat').join(',')};`;
}

// SVG filter approximating Figma image adjustments (each −1..1).
function imageFilterSVG(fid, f) {
  const e = +f.exposure || 0, c = +f.contrast || 0, s = 1 + (+f.saturation || 0), t = +f.temperature || 0, ti = +f.tint || 0;
  const hi = +f.highlights || 0, sh = +f.shadows || 0;
  const ex = Math.pow(2, e);
  const k = 1 + c, off = 0.5 * (1 - k);
  const lr = 0.2126, lg = 0.7152, lb = 0.0722;
  const sat = [lr + (1 - lr) * s, lg - lg * s, lb - lb * s, lr - lr * s, lg + (1 - lg) * s, lb - lb * s, lr - lr * s, lg - lg * s, lb + (1 - lb) * s];
  const gain = [ex * k * (1 + 0.2 * t), ex * k * (1 - 0.2 * ti), ex * k * (1 - 0.2 * t)];
  const m = [];
  for (let r = 0; r < 3; r++) m.push(sat[r * 3] * gain[r], sat[r * 3 + 1] * gain[r], sat[r * 3 + 2] * gain[r], 0, off);
  m.push(0, 0, 0, 1, 0);
  const curve = [0 + sh * 0.05, 0.25 + sh * 0.15, 0.5 + (sh + hi) * 0.04, 0.75 + hi * 0.15, 1 + hi * 0.05].map((v) => n2(Math.max(0, Math.min(1, v)) * 1000) / 1000).join(' ');
  return `<filter id="${fid}" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="${m.map((v) => n2(v * 1000) / 1000).join(' ')}"/>` +
    `<feComponentTransfer><feFuncR type="table" tableValues="${curve}"/><feFuncG type="table" tableValues="${curve}"/><feFuncB type="table" tableValues="${curve}"/></feComponentTransfer></filter>`;
}

// Paint-level LINEAR_BURN without plus-darker (same identity as the layer case, see lbMode): an
// inversion layer, the paint drawn inverted with plus-lighter, a second inversion layer. ctx.plb is
// 'bf' (backdrop-filter, canvas/present) or 'diff' (opaque white difference inside a raster group, print).
const lbBurn = (paint, ctx) => (paint.blend === 'LINEAR_BURN' && ctx && ctx.plb ? ctx.plb : null);
const lbInner = (lb, ctx) => lb && !ctx.lbSlice; // in slice mode the slice element carries invert + plus-lighter
function lbInvHTML(m, S) {
  return m === 'bf'
    ? '<div class="ppt-d" style="position:fixed;left:-100000px;top:-100000px;width:300000px;height:300000px;backdrop-filter:invert(1);-webkit-backdrop-filter:invert(1)"></div>'
    : `<div class="ppt-d" style="left:${-S}px;top:${-S}px;width:${3 * S}px;height:${3 * S}px;background:#fff;mix-blend-mode:difference"></div>`;
}
// Markers let a rotated node split its paint stack into sibling slices (see paint: slice mode).
const lbWrap = (m, html, S) => (m ? `<!--lb1-->${lbInvHTML(m, S)}<!--lbp-->${html}<!--lb3-->${lbInvHTML(m, S)}<!--lbe-->` : html);

// One paint as an absolutely positioned layer div (for blend/opacity/filter/rotation the CSS stack can't do).
function layerHTML(paint, w, h, ctx, extra, defs, key) {
  const lb = lbBurn(paint, ctx), li = lbInner(lb, ctx);
  const blend = lb ? (li ? 'mix-blend-mode:plus-lighter;' : '') : paint.blend && paint.blend !== 'NORMAL' && paint.blend !== 'PASS_THROUGH' ? `mix-blend-mode:${blendCSS(paint.blend)};` : '';
  const isImg = paint.type === 'IMAGE';
  const op = isImg && (paint.opacity ?? 1) < 1 ? `opacity:${n2(paint.opacity)};` : '';
  const fl = [];
  if (isImg && hasFilters(paint)) { const fid = `${ctx.uid}-if${key}`; defs.push(imageFilterSVG(fid, paint.filters)); fl.push(`url(#${fid})`); }
  const rot = isImg ? ((paint.rotation || 0) % 360 + 360) % 360 : 0;
  if (rot) {
    const sw = rot % 180 ? h : w, sh = rot % 180 ? w : h;
    const inner = bgCSS([{ ...paint, rotation: 0, opacity: 1 }], sw, sh, ctx);
    return lbWrap(lb, `<div class="ppt-d ppt-fl" style="left:0;top:0;width:100%;height:100%;overflow:hidden;${extra}${blend}${op}${li ? 'filter:invert(1);' : ''}"><div class="ppt-d" style="left:${n2((w - sw) / 2)}px;top:${n2((h - sh) / 2)}px;width:${n2(sw)}px;height:${n2(sh)}px;transform:rotate(${rot}deg);${inner}${fl.length ? `filter:${fl.join(' ')};` : ''}"></div></div>`, ctx.lbS);
  }
  if (li) fl.push('invert(1)');
  const filt = fl.length ? `filter:${fl.join(' ')};` : '';
  return lbWrap(lb, `<div class="ppt-d ppt-fl" style="left:0;top:0;width:100%;height:100%;${extra}${blend}${op}${filt}${bgCSS([{ ...paint, opacity: isImg ? 1 : paint.opacity }], w, h, ctx)}"></div>`, ctx.lbS);
}

// ---------- SVG painting ----------

const JOIN = { MITER: 'miter', BEVEL: 'bevel', ROUND: 'round' };
const CAP = { NONE: 'butt', ROUND: 'round', SQUARE: 'square' };
const SIMPLE_CAPS = new Set(['NONE', 'ROUND', 'SQUARE', undefined]);

function svgStops(stops) {
  const s = sortStops(stops);
  return s.map((st) => `<stop offset="${n2(st.p)}" stop-color="${hex6(st.color)}" stop-opacity="${n2(alphaOf(st.color))}"/>`).join('');
}

// Native SVG paint server for SOLID/LINEAR/RADIAL; null when the paint needs a CSS foreignObject.
function svgServer(paint, w, h, gid, defs) {
  if (paint.type === 'SOLID') return { ref: hex6(paint.color), op: alphaOf(paint.color) * (paint.opacity ?? 1) };
  if (paint.type === 'LINEAR') {
    const deg = (paint.angle || 0) + 90, t = (deg * Math.PI) / 180, ux = Math.sin(t), uy = -Math.cos(t);
    const L = Math.abs(w * ux) + Math.abs(h * uy);
    defs.push(`<linearGradient id="${gid}" gradientUnits="userSpaceOnUse" x1="${n2(w / 2 - (ux * L) / 2)}" y1="${n2(h / 2 - (uy * L) / 2)}" x2="${n2(w / 2 + (ux * L) / 2)}" y2="${n2(h / 2 + (uy * L) / 2)}">${svgStops(paint.stops)}</linearGradient>`);
    return { ref: `url(#${gid})`, op: paint.opacity ?? 1 };
  }
  if (paint.type === 'RADIAL') {
    const sx = Math.max(0.001, (paint.rx ?? 0.5) * w), sy = Math.max(0.001, (paint.ry ?? 0.5) * h);
    defs.push(`<radialGradient id="${gid}" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="1" gradientTransform="translate(${n2((paint.cx ?? 0.5) * w)} ${n2((paint.cy ?? 0.5) * h)}) scale(${n2(sx)} ${n2(sy)})">${svgStops(paint.stops)}</radialGradient>`);
    return { ref: `url(#${gid})`, op: paint.opacity ?? 1 };
  }
  return null;
}

// Drop/inner shadows as one SVG filter (userSpaceOnUse in the element's box coordinates).
function fxFilter(fid, effects, w, h, bbox = false, only = null) {
  const drops = effects.filter((e) => e.type === 'DROP_SHADOW'), inners = effects.filter((e) => e.type === 'INNER_SHADOW');
  if (!drops.length && !inners.length) return '';
  let ext = 4;
  for (const e of [...drops, ...inners]) ext = Math.max(ext, Math.abs(e.x || 0) + Math.abs(e.y || 0) + (e.blur || 0) * 1.5 + Math.abs(e.spread || 0) + 4);
  // bbox: HTML elements whose real size is only known after layout (auto text, groups) get a generous relative region
  let f = bbox ? `<filter id="${fid}" x="-3" y="-3" width="7" height="7" color-interpolation-filters="sRGB">`
    : `<filter id="${fid}" filterUnits="userSpaceOnUse" x="${n2(-ext)}" y="${n2(-ext)}" width="${n2(w + 2 * ext)}" height="${n2(h + 2 * ext)}" color-interpolation-filters="sRGB">`;
  const merge = [];
  if (drops.some((e) => !e.showBehind)) f += `<feComponentTransfer in="SourceAlpha" result="hard"><feFuncA type="linear" slope="1000"/></feComponentTransfer>`;
  drops.forEach((e, i) => {
    let src = 'SourceAlpha';
    const sp = +e.spread || 0;
    if (sp) { f += `<feMorphology in="SourceAlpha" operator="${sp > 0 ? 'dilate' : 'erode'}" radius="${n2(Math.abs(sp))}" result="m${i}"/>`; src = `m${i}`; }
    f += `<feGaussianBlur in="${src}" stdDeviation="${n2((e.blur || 0) / 2)}"/><feOffset dx="${n2(e.x)}" dy="${n2(e.y)}" result="o${i}"/>`;
    f += `<feFlood flood-color="${hex6(e.color)}" flood-opacity="${n2(alphaOf(e.color))}"/><feComposite in2="o${i}" operator="in" result="s${i}"/>`;
    if (!e.showBehind) f += `<feComposite in="s${i}" in2="hard" operator="out" result="s${i}"/>`;
    merge.push(`s${i}`);
  });
  if (only === 'inner') merge.length = 0;
  if (!only) merge.push('SourceGraphic');
  inners.forEach((e, i) => {
    f += `<feComponentTransfer in="SourceAlpha" result="v${i}"><feFuncA type="table" tableValues="1 0"/></feComponentTransfer>`;
    let src = `v${i}`;
    const sp = +e.spread || 0;
    if (sp > 0) { f += `<feMorphology in="v${i}" operator="dilate" radius="${n2(sp)}" result="vm${i}"/>`; src = `vm${i}`; }
    f += `<feGaussianBlur in="${src}" stdDeviation="${n2((e.blur || 0) / 2)}"/><feOffset dx="${n2(e.x)}" dy="${n2(e.y)}" result="io${i}"/>`;
    f += `<feFlood flood-color="${hex6(e.color)}" flood-opacity="${n2(alphaOf(e.color))}"/><feComposite in2="io${i}" operator="in"/><feComposite in2="SourceAlpha" operator="in" result="i${i}"/>`;
    if (only !== 'drop') merge.push(`i${i}`);
  });
  return f + `<feMerge>${merge.map((m) => `<feMergeNode in="${m}"/>`).join('')}</feMerge></filter>`;
}

function trimEnds(d, a, b) {
  if (!a && !b) return d;
  const subs = parsePath(d);
  const s0 = subs.find((s) => !s.closed && s.segs.length), s1 = [...subs].reverse().find((s) => !s.closed && s.segs.length);
  if (a && s0 && s0.segs[0][6]) {
    const g = s0.segs[0], L = Math.hypot(g[4] - s0.x, g[5] - s0.y);
    if (L > a) { s0.x += ((g[4] - s0.x) * a) / L; s0.y += ((g[5] - s0.y) * a) / L; g[0] = s0.x; g[1] = s0.y; }
  }
  if (b && s1) {
    const g = s1.segs[s1.segs.length - 1];
    if (g[6]) {
      const px = s1.segs.length > 1 ? s1.segs[s1.segs.length - 2][4] : s1.x, py = s1.segs.length > 1 ? s1.segs[s1.segs.length - 2][5] : s1.y;
      const L = Math.hypot(g[4] - px, g[5] - py);
      if (L > b) { g[4] -= ((g[4] - px) * b) / L; g[5] -= ((g[5] - py) * b) / L; g[2] = g[4]; g[3] = g[5]; }
    }
  }
  return serializePath(subs);
}

// Inline SVG painting one outline d in a w×h box. parts = {fills, strokes, stroke, effects}.
function svgPaint(o, ctx) {
  const { d, rule, w, h, open, ol, hit } = o;
  const fills = o.fills || [], strokes = o.strokes || [], st = o.stroke || {}, effects = o.effects || [];
  const segs = o.segs || null; // per-side stroke segments [{d, weight}] (centered, own weight each)
  const uid = ctx.uid + (o.key || '');
  const fr = rule === 'EVENODD' ? 'evenodd' : 'nonzero';
  const wt = ol ? 1 : Math.max(0, st.weight ?? 1);
  const closed = !open;
  const align = closed ? st.align || 'CENTER' : 'CENTER';
  const sw = align === 'CENTER' ? wt : wt * 2;
  const dashed = (st.dash || []).some((v) => v > 0);
  const capS = st.capStart || 'NONE', capE = st.capEnd || 'NONE';
  const nativeCap = dashed ? CAP[st.dashCap] || 'butt' : open && capS === capE && SIMPLE_CAPS.has(capS) ? CAP[capS] || 'butt' : 'butt';
  const capExt = open ? Math.max(4 * wt, wt + 6) : 0;
  const P = Math.ceil(Math.max(sw, ...(segs || []).map((g) => g.weight)) + capExt + 2);
  const defs = [];
  let body = '';
  let needClip = false, needOut = false;

  // caps (open paths with per-end or arrow caps) + line shortening
  let dd = d;
  const caps = [];
  // dashed: the dash cap shapes every dash end, so only non-simple (arrow/shape) end caps are added
  const endCap = (c) => (dashed && SIMPLE_CAPS.has(c) ? 'NONE' : c);
  const needCaps = dashed ? !SIMPLE_CAPS.has(capS) || !SIMPLE_CAPS.has(capE) : !(capS === capE && SIMPLE_CAPS.has(capS));
  if (open && needCaps && strokes.length && !ol) {
    const e = openEnds(d);
    if (e) {
      const cs = capShapes(endCap(capS), e.start, e.su[0], e.su[1], wt), ce = capShapes(endCap(capE), e.end, e.eu[0], e.eu[1], wt);
      caps.push(cs, ce);
      dd = trimEnds(d, cs.inset, ce.inset);
    }
  }
  const capMarkup = (paintAttr) => caps.map((c) =>
    c.fill.map((r) => `<path d="M${r.map((p) => n2(p[0]) + ' ' + n2(p[1])).join('L')}Z" ${paintAttr.fill}/>`).join('') +
    c.lines.map((l) => `<path d="M${l.map((p) => n2(p[0]) + ' ' + n2(p[1])).join('L')}" fill="none" ${paintAttr.stroke} stroke-width="${n2(wt)}" stroke-linejoin="${JOIN[st.join] || 'miter'}" stroke-linecap="round"/>`).join('')).join('');

  const strokeAttrs = `stroke-width="${n2(sw)}" stroke-linejoin="${JOIN[st.join] || 'miter'}" stroke-miterlimit="${n2(st.miterLimit || 4)}" stroke-linecap="${nativeCap}"${dashed ? ` stroke-dasharray="${st.dash.map(n2).join(' ')}"` : ''}`;
  const alignAttr = () => {
    if (align === 'INSIDE') { needClip = true; return ` clip-path="url(#${uid}-c)"`; }
    if (align === 'OUTSIDE') { needOut = true; return ` mask="url(#${uid}-o)"`; }
    return '';
  };
  const blendStyle = (p) => (p.blend && p.blend !== 'NORMAL' && p.blend !== 'PASS_THROUGH' ? ` style="mix-blend-mode:${blendCSS(p.blend)}"` : '');
  const fo = (x, y, fw, fh, inner, extra) => `<foreignObject x="${n2(x)}" y="${n2(y)}" width="${n2(fw)}" height="${n2(fh)}"${extra}><div xmlns="http://www.w3.org/1999/xhtml" style="position:absolute;left:0;top:0;width:${n2(fw)}px;height:${n2(fh)}px">${inner}</div></foreignObject>`;

  if (ol) {
    body += `<path d="${d}" fill="none" stroke="#000" style="stroke-width:calc(1px / var(--zoom, 1))"/>`;
  } else {
    fills.forEach((p, i) => {
      const s = svgServer(p, w, h, `${uid}-g${i}`, defs);
      if (s) body += `<path d="${d}" fill="${s.ref}" fill-opacity="${n2(s.op)}" fill-rule="${fr}"${blendStyle(p)}/>`;
      else {
        needClip = true;
        body += fo(0, 0, w, h, layerHTML(p, w, h, ctx, '', defs, `${o.key || ''}f${i}`), ` clip-path="url(#${uid}-c)"${blendStyle(p)}`);
      }
    });
    if (wt > 0) strokes.forEach((p, i) => {
      const s = svgServer(p, w, h, `${uid}-s${i}`, defs);
      if (segs) {
        const lines = (ref) => segs.map((g) => `<path d="${g.d}" fill="none" stroke="${ref}" stroke-width="${n2(g.weight)}" stroke-linecap="${nativeCap}"${dashed ? ` stroke-dasharray="${st.dash.map(n2).join(' ')}"` : ''}/>`).join('');
        if (s) body += `<g stroke-opacity="${n2(s.op)}"${blendStyle(p)}>${lines(s.ref)}</g>`;
        else {
          const mid = `${uid}-sm${i}`;
          defs.push(`<mask id="${mid}" maskUnits="userSpaceOnUse" x="${-P}" y="${-P}" width="${n2(w + 2 * P)}" height="${n2(h + 2 * P)}">${lines('#fff')}</mask>`);
          body += fo(-P, -P, w + 2 * P, h + 2 * P, layerHTML(p, w + 2 * P, h + 2 * P, ctx, '', defs, `${o.key || ''}s${i}`), ` mask="url(#${mid})"${blendStyle(p)}`);
        }
      } else if (s) {
        body += `<path d="${dd}" fill="none" stroke="${s.ref}" stroke-opacity="${n2(s.op)}" ${strokeAttrs}${alignAttr()}${blendStyle(p)}/>`;
        if (caps.length) body += `<g opacity="${n2(s.op)}">${capMarkup({ fill: `fill="${s.ref}"`, stroke: `stroke="${s.ref}"` })}</g>`;
      } else {
        const mid = `${uid}-sm${i}`;
        defs.push(`<mask id="${mid}" maskUnits="userSpaceOnUse" x="${-P}" y="${-P}" width="${n2(w + 2 * P)}" height="${n2(h + 2 * P)}"><path d="${dd}" fill="none" stroke="#fff" ${strokeAttrs}${alignAttr()}/>${capMarkup({ fill: 'fill="#fff"', stroke: 'stroke="#fff"' })}</mask>`);
        body += fo(-P, -P, w + 2 * P, h + 2 * P, layerHTML(p, w + 2 * P, h + 2 * P, ctx, '', defs, `${o.key || ''}s${i}`), ` mask="url(#${mid})"${blendStyle(p)}`);
      }
    });
  }
  if (needClip) defs.push(`<clipPath id="${uid}-c"><path d="${d}" clip-rule="${fr}"/></clipPath>`);
  if (needOut) defs.push(`<mask id="${uid}-o" maskUnits="userSpaceOnUse" x="${-P - 1}" y="${-P - 1}" width="${n2(w + 2 * P + 2)}" height="${n2(h + 2 * P + 2)}"><rect x="${-P - 1}" y="${-P - 1}" width="${n2(w + 2 * P + 2)}" height="${n2(h + 2 * P + 2)}" fill="#fff"/><path d="${d}" fill="#000" fill-rule="${fr}"/></mask>`);
  const ff = ol ? '' : fxFilter(`${uid}-fx`, effects, w, h, false, o.fxOnly || null);
  if (ff) defs.push(ff);
  // an effect-only layer (separately blended shadow) may blend with the content behind it
  const svgBlend = (o.blend ? `mix-blend-mode:${blendCSS(o.blend)};` : '') + (o.css || '');
  const hitMarkup = hit ? `<path class="ppt-hit${open ? ' ppt-open' : ''}" d="${d}" fill="none" stroke="transparent" style="stroke-width:max(${n2(sw)}px, calc(8px / var(--zoom, 1)))"/>` : '';
  return `<svg class="ppt-d ppt-sv" xmlns="http://www.w3.org/2000/svg" style="left:${-P}px;top:${-P}px;width:${n2(w + 2 * P)}px;height:${n2(h + 2 * P)}px;${svgBlend}" viewBox="${-P} ${-P} ${n2(w + 2 * P)} ${n2(h + 2 * P)}">` +
    (defs.length ? `<defs>${defs.join('')}</defs>` : '') + (ff ? `<g filter="url(#${uid}-fx)">${body}</g>` : body) + hitMarkup + '</svg>';
}

// Split one SVG paint list at each paint-level burn: [paints below] L1 [burn paint, inverted, plus-lighter] L3 [rest].
// (backdrop-filter / plus-lighter can't apply between paths inside one SVG.) kind = 'fills' | 'strokes'.
function svgChunks(base, list, kind, ctx) {
  const out = [];
  let run = [], k = 0;
  const other = kind === 'fills' ? 'strokes' : 'fills';
  const emit = (paints, css) => out.push(svgPaint({ ...base, [kind]: paints, [other]: [], effects: k === 0 ? base.effects || [] : [], hit: !!base.hit && k === 0, key: `${base.key || ''}k${k++}`, css }, ctx));
  for (const f of list) {
    const lb = lbBurn(f, ctx);
    if (!lb) { run.push(f); continue; }
    if (run.length) emit(run);
    run = [];
    out.push('<!--lb1-->' + lbInvHTML(lb, ctx.lbS) + '<!--lbp-->');
    emit([{ ...f, blend: 'NORMAL' }], lbInner(lb, ctx) ? 'filter:invert(1);mix-blend-mode:plus-lighter;' : '');
    out.push('<!--lb3-->' + lbInvHTML(lb, ctx.lbS) + '<!--lbe-->');
  }
  if (run.length || !k) emit(run);
  return out;
}

// ---------- per-side strokes ----------

const ALIGN_K = { INSIDE: 0, CENTER: 0.5, OUTSIDE: 1 }; // fraction of each side's weight outside the box
const shiftD = (d, dx, dy) => (dx || dy ? transformD(d, [1, 0, 0, 1, dx, dy]) : d);

// Filled ring between the outer and inner stroke edges (even-odd), honoring per-side weights and smoothing.
function sideRingD(w, h, radii, smoothing, sd, align) {
  const k = ALIGN_K[align] ?? 0, { t = 0, r = 0, b = 0, l = 0 } = sd;
  const adj = [[t, l], [t, r], [b, r], [b, l]];
  const oR = radii.map((v, j) => (v ? v + k * Math.max(...adj[j]) : 0));
  const iR = radii.map((v, j) => Math.max(0, v - (1 - k) * Math.max(...adj[j])));
  const ox = -l * k, oy = -t * k, ow = w + (l + r) * k, oh = h + (t + b) * k;
  const ix = l * (1 - k), iy = t * (1 - k), iw = w - (l + r) * (1 - k), ih = h - (t + b) * (1 - k);
  let d = shiftD(smoothRectD(ow, oh, oR, smoothing), ox, oy);
  if (iw > 0 && ih > 0) d += shiftD(smoothRectD(iw, ih, iR, smoothing), ix, iy);
  return d;
}

// Dashed per-side strokes: one centered segment per side (own weight) plus circular corner arcs.
function sideSegs(w, h, radii, sd, align) {
  const k = ALIGN_K[align] ?? 0, { t = 0, r = 0, b = 0, l = 0 } = sd;
  const oc = (s) => s * (0.5 - k); // centre-line offset into the box
  const [rtl, rtr, rbr, rbl] = radii;
  const out = [];
  const ext = (s, rad) => (rad ? 0 : s * k); // square corners: extend to cover the corner
  if (t) out.push({ d: `M${n2(rtl - ext(l, rtl))} ${n2(oc(t))}L${n2(w - rtr + ext(r, rtr))} ${n2(oc(t))}`, weight: t });
  if (r) out.push({ d: `M${n2(w - oc(r))} ${n2(rtr - ext(t, rtr))}L${n2(w - oc(r))} ${n2(h - rbr + ext(b, rbr))}`, weight: r });
  if (b) out.push({ d: `M${n2(w - rbr + ext(r, rbr))} ${n2(h - oc(b))}L${n2(rbl - ext(l, rbl))} ${n2(h - oc(b))}`, weight: b });
  if (l) out.push({ d: `M${n2(oc(l))} ${n2(h - rbl + ext(b, rbl))}L${n2(oc(l))} ${n2(rtl - ext(t, rtl))}`, weight: l });
  const arc = (rad, a, bw, cx, cy, a0) => {
    if (!rad || !a || !bw) return;
    const wt = (a + bw) / 2, rr = Math.max(0.01, rad - oc(wt));
    const p = (ang) => `${n2(cx + rr * Math.cos(ang))} ${n2(cy + rr * Math.sin(ang))}`;
    out.push({ d: `M${p(a0)}A${n2(rr)} ${n2(rr)} 0 0 1 ${p(a0 + Math.PI / 2)}`, weight: wt });
  };
  arc(rtr, t, r, w - rtr, rtr, -Math.PI / 2);
  arc(rbr, r, b, w - rbr, h - rbr, 0);
  arc(rbl, b, l, rbl, h - rbl, Math.PI / 2);
  arc(rtl, l, t, rtl, rtl, Math.PI);
  return out;
}

// ---------- renderer ----------

// links: real <a> for runs[].link (present/print); false for previews such as thumbnails.
export function createRenderer({ root, mode = 'edit', assetUrl = (h) => '/assets/' + h, page = null, links = mode !== 'edit' } = {}) {
  injectCSS();
  const rid = 'r' + ++ridSeq;
  const EDIT = mode === 'edit';
  const els = new Map(), labels = new Map(), preview = new Map(), pending = new Set();
  const natural = new Map(), imgUsers = new Map(), loads = new Map(), twins = new Set();
  const lbIds = new Set(), plbIds = new Set(), rasterIds = new Set(), unisoIds = new Set(), lbPages = new Set();
  let store = null, unsub = null, raf = 0, showGuides = false, outline = false, pageId = page;
  root.classList.add('ppt-root', 'ppt-' + mode);

  const nodeOf = (id) => store?.nodes.get(id);
  const normCache = new WeakMap();
  const props = (id) => {
    const n = nodeOf(id);
    if (!n) return null;
    const p = propsOf(n);
    if (preview.has(id)) return normalize(n.type, { ...p, ...preview.get(id) });
    let q = normCache.get(p);
    if (!q) { q = normalize(n.type, p); normCache.set(p, q); }
    return q;
  };
  const geoSrc = { props, type: (id) => nodeOf(id).type, children: (id) => store.children(id).map((n) => n.id) };
  const pages = () => [...store.nodes.values()].filter((n) => n.type === 'page').sort((a, b) => (a.z < b.z ? -1 : a.z > b.z ? 1 : 0));
  const inScope = (id) => EDIT || store.pageOf(id)?.id === pageId;

  function loadImage(hash, user) {
    if (!imgUsers.has(hash)) imgUsers.set(hash, new Set());
    if (user) imgUsers.get(hash).add(user);
    if (loads.has(hash)) return;
    const img = new Image();
    loads.set(hash, new Promise((res) => {
      img.onload = () => {
        natural.set(hash, { w: img.naturalWidth, h: img.naturalHeight });
        res();
        const ids = [...(imgUsers.get(hash) || [])].filter((id) => els.has(id));
        if (ids.length) update(ids, []);
      };
      img.onerror = () => res();
    }));
    img.src = assetUrl(hash);
  }
  const paintCtx = (id, uid) => ({
    id, uid,
    src: (hash) => { if (!HEX64.test(hash || '')) return null; loadImage(hash, id); return assetUrl(hash); },
    natural: (hash) => natural.get(hash),
  });

  // ----- element management -----

  function containerFor(node) {
    if (node.type === 'page') return root;
    const pel = ensureEl(node.parent);
    return pel ? pel._c : null;
  }
  function ensureEl(id) {
    let el = els.get(id);
    if (el) return el;
    const node = nodeOf(id);
    if (!node || !inScope(id)) return null;
    el = document.createElement('div');
    el.className = 'ppt-n ppt-t-' + node.type;
    el.dataset.id = id;
    if (CONTAINERS.has(node.type)) { el._c = document.createElement('div'); el._c.className = 'ppt-c'; el.appendChild(el._c); }
    els.set(id, el);
    const parent = containerFor(node);
    if (parent) parent.appendChild(el);
    if (node.type === 'page' && EDIT) {
      const lab = document.createElement('div');
      lab.className = 'ppt-pl';
      lab.dataset.pageLabel = id;
      root.appendChild(lab);
      labels.set(id, lab);
    }
    return el;
  }
  function removeNode(id) {
    const el = els.get(id);
    if (!el) return;
    for (const d of el.querySelectorAll('[data-id]')) { const k = d.dataset.id; els.get(k)?._twin?.remove(); els.get(k)?._fx?.remove(); if (els.get(k)) { dropLB(els.get(k)); dropSlices(els.get(k)); } lbIds.delete(k); plbIds.delete(k); els.delete(k); twins.delete(k); labels.get(k)?.remove(); labels.delete(k); }
    el._twin?.remove();
    el._fx?.remove();
    dropLB(el); dropSlices(el); lbIds.delete(id); plbIds.delete(id);
    el.remove();
    els.delete(id); twins.delete(id);
    labels.get(id)?.remove(); labels.delete(id);
    preview.delete(id);
  }
  function reorder(pid) {
    const pel = els.get(pid);
    if (!pel?._c) return;
    let ref = pel._c.firstChild;
    for (const n of store.children(pid)) {
      const e0 = els.get(n.id);
      for (const el of [e0?._lb1, e0?._fx, ...(e0?._slices || []), e0, e0?._twin, e0?._lb3]) {
        if (!el) continue;
        if (el === ref) ref = ref.nextSibling;
        else pel._c.insertBefore(el, ref);
      }
    }
  }
  function buildSubtree(id) {
    if (!ensureEl(id)) return;
    for (const c of store.children(id)) buildSubtree(c.id);
    paint(id);
  }

  // ----- box (position / size / flex item) -----

  function sizing(node, p, axis, flow) {
    const k = axis === 'h' ? 'sizingH' : 'sizingV';
    if (flow && (p.layoutChild || {})[k] === 'FILL') return 'FILL';
    if (node.type === 'text') {
      const ar = p.autoResize || 'WIDTH_AND_HEIGHT';
      return (axis === 'h' ? ar === 'WIDTH_AND_HEIGHT' : ar === 'WIDTH_AND_HEIGHT' || ar === 'HEIGHT') ? 'HUG' : 'FIXED';
    }
    if (p.layout && p.layout.dir && p.layout.dir !== 'NONE' && p.layout[k] === 'HUG') return 'HUG';
    if (node.type === 'table' && axis === 'v') return 'HUG';
    return 'FIXED';
  }
  const autoLayout = (p) => (p && p.layout && p.layout.dir && p.layout.dir !== 'NONE' ? p.layout : null);

  function boxCSS(node, p) {
    if (node.type === 'page') {
      const x = EDIT ? p.cx || 0 : 0, y = EDIT ? p.cy || 0 : 0;
      const hug = sizing(node, p, 'h', false) === 'HUG', hugV = sizing(node, p, 'v', false) === 'HUG';
      let s = `left:${n2(x)}px;top:${n2(y)}px;${hug ? 'width:max-content;' : `width:${n2(p.w)}px;`}${hugV ? '' : `height:${n2(p.h)}px;`}`;
      if (EDIT && p.clip !== false && !lbPages.has(node.id)) s += `content-visibility:auto;contain-intrinsic-size:auto ${n2(p.w)}px auto ${n2(p.h)}px;`;
      return s;
    }
    const parent = nodeOf(node.parent);
    const pp = parent ? props(parent.id) : null;
    const L = parent && (parent.type === 'frame' || parent.type === 'page') ? autoLayout(pp) : null;
    const flow = !!L && !(p.layoutChild || {}).absolute;
    const sh = sizing(node, p, 'h', flow), sv = sizing(node, p, 'v', flow);
    let s = '';
    if (flow) {
      const horiz = L.dir === 'HORIZONTAL';
      s += 'position:relative;flex:none;';
      const main = horiz ? sh : sv, cross = horiz ? sv : sh;
      if (main === 'FILL') s += `flex:1 1 0;${horiz ? 'min-width' : 'min-height'}:0;`;
      if (cross === 'FILL') s += 'align-self:stretch;';
      if (L.reverseZ) {
        const kids = store.children(parent.id);
        s += `z-index:${kids.length - kids.findIndex((k) => k.id === node.id)};`;
      }
      const lc = p.layoutChild || {};
      for (const [k, css] of [['minW', 'min-width'], ['maxW', 'max-width'], ['minH', 'min-height'], ['maxH', 'max-height']]) if (lc[k] != null) s += `${css}:${n2(lc[k])}px;`;
    } else s += `left:${n2(p.x)}px;top:${n2(p.y)}px;`;
    if (sh === 'FIXED') s += `width:${n2(p.w)}px;`;
    else if (sh === 'HUG') s += node.type === 'text' ? 'width:max-content;' : flow ? '' : 'width:max-content;';
    if (sv === 'FIXED') s += `height:${n2(p.h)}px;`;
    const tf = [];
    if (p.rotation) tf.push(`rotate(${n2(p.rotation)}deg)`);
    if (p.flipX || p.flipY) tf.push(`scale(${p.flipX ? -1 : 1},${p.flipY ? -1 : 1})`);
    if (tf.length) s += `transform:${tf.join(' ')};`;
    return s;
  }
  // Auto-sized boxes (HUG/FILL frames, tables): decorations that need pixel sizes are repainted
  // with the laid-out size in one batched pass (all reads, then writes).
  const autoSeen = new Set();
  function isAutoSized(node, p) {
    if (node.type === 'table') return true;
    if (node.type === 'page') return sizing(node, p, 'h', false) !== 'FIXED' || sizing(node, p, 'v', false) !== 'FIXED';
    const parent = nodeOf(node.parent);
    const flow = !!(parent && (parent.type === 'frame' || parent.type === 'page') && autoLayout(props(parent.id))) && !(p.layoutChild || {}).absolute;
    return sizing(node, p, 'h', flow) !== 'FIXED' || sizing(node, p, 'v', flow) !== 'FIXED';
  }
  function fixAuto(ids) {
    const fix = [];
    for (const id of ids) {
      const el = els.get(id);
      if (!el || el._hidden || !el.isConnected) continue;
      const cs = getComputedStyle(el), w = parseFloat(cs.width), h = parseFloat(cs.height);
      if (!Number.isFinite(w) || !Number.isFinite(h)) continue;
      const p = props(id), cur = el._size || { w: p.w, h: p.h };
      if (Math.abs(cur.w - w) > 0.5 || Math.abs(cur.h - h) > 0.5) fix.push([id, el, { w, h }]);
    }
    for (const [id, el, size] of fix) { el._size = size; paint(id); }
  }

  function applyBox(id) {
    const el = els.get(id), node = nodeOf(id);
    if (!el || !node || el._hidden) return;
    el.style.cssText = boxCSS(node, props(id)) + (el._paintCSS || '');
    if (el._fx) { const p = props(id); el._fx.style.cssText = boxCSS(node, p) + 'pointer-events:none;' + ((p.opacity ?? 1) < 1 ? `opacity:${n2(p.opacity)};` : ''); }
    if (el._lb1) { el._lb1.style.zIndex = el._lb3.style.zIndex = el.style.zIndex; }
    if (el._slices) paint(id); // slices copy the node's box; cheapest correct refresh is a repaint
  }

  // ----- paint -----

  function smooth0(type, p, radii) { return (type === 'rect' || type === 'frame') && (p.smoothing || 0) > 0 && radii.some((r) => r); }

  function clearDecor(el) {
    for (const ch of [...el.children]) if (ch !== el._c && ch !== el._content) ch.remove();
  }

  function paint(id) {
    const node = nodeOf(id), el = els.get(id);
    if (!node || !el) return;
    let p = props(id);
    const type = node.type;
    if (type === 'page' && EDIT) {
      const lab = labels.get(id);
      if (lab) { lab.textContent = p.name || ''; lab.style.left = n2(p.cx) + 'px'; lab.style.top = n2(p.cy) + 'px'; lab.style.display = p.visible === false ? 'none' : ''; }
    }
    if (p.visible === false) { el._fx?.remove(); el._fx = null; dropLB(el); dropSlices(el); lbIds.delete(id); plbIds.delete(id); clearDecor(el); el._hidden = true; el._paintCSS = ''; el.style.cssText = 'display:none'; return; }
    el._hidden = false;
    const OL = outline && EDIT;
    if (OL) p = { ...p, fills: [], strokes: [], effects: [], opacity: 1, blend: 'PASS_THROUGH' };
    const sz = el._size;
    const w = sz ? sz.w : p.w, h = sz ? sz.h : p.h;
    if (type !== 'text' && isAutoSized(node, p)) autoSeen.add(id);
    const fills = vis(p.fills), strokes = vis(p.strokes), effects = vis(p.effects);
    const st = p.stroke || {};
    const ctx = paintCtx(id, `${rid}-${id}`);
    ctx.plb = OL ? null : paintLBMode(node, p);
    if (ctx.plb) { const pg = store.pageOf(id), pp = pg ? props(pg.id) : p; ctx.lbS = Math.ceil(2 * Math.max(pp.w || 0, pp.h || 0) + 1000); }
    // A rotated/flipped node is its own stacking context (CSS transform), so its paints could only blend
    // against its own content. Slice mode renders the paint stack as transformed sibling slices instead.
    ctx.lbSlice = !!ctx.plb && transformOnlyStack(node, p) && !isFlowChild(node, p);
    const pre = [], post = [], defs = [];
    let css = '';
    const filters = [];
    const radii = BOXES.has(type) && p.radius != null ? radiiOf(p.radius, w, h) : [0, 0, 0, 0];
    const rCSS = radii.some((r) => r) ? `border-radius:${radii.map((r) => n2(r) + 'px').join(' ')};` : '';
    const smooth = smooth0(type, p, radii);
    // shadows with their own blend mode are painted as separate layers so mix-blend-mode can apply
    const blended = (e) => e.blend && e.blend !== 'NORMAL' && e.blend !== 'PASS_THROUGH';
    const allDrops = effects.filter((e) => e.type === 'DROP_SHADOW'), allInners = effects.filter((e) => e.type === 'INNER_SHADOW');
    const canSplit = BOXES.has(type) || smooth0(type, p, radii) || SHAPES.has(type);
    const bDrops = canSplit ? allDrops.filter(blended) : [], bInners = canSplit ? allInners.filter(blended) : [];
    let drops = allDrops.filter((e) => !bDrops.includes(e)), inners = allInners.filter((e) => !bInners.includes(e));
    let printInners = [];
    const fxLayers = []; // blended drop-shadow layers (box coords), placed behind the node
    const plainFx = effects.filter((e) => !bDrops.includes(e) && !bInners.includes(e));
    const blur = effects.find((e) => e.type === 'LAYER_BLUR'), bgBlur = effects.find((e) => e.type === 'BACKGROUND_BLUR');
    let svgFx = false; // shadows via an SVG filter on the element itself

    if (BOXES.has(type) && !smooth) {
      if (mode === 'print' && fills.length && (allDrops.length || allInners.length)) {
        // Chrome writes CSS box-shadow into PDFs as soft-masked images that macOS Preview draws as hard
        // dark rectangles; an SVG filter shadow prints cleanly, so print uses black-silhouette shadow layers.
        const bd = smoothRectD(w, h, radii, 0);
        const silB = (e, only, k) => svgPaint({ d: bd, w, h, fills: [{ type: 'SOLID', color: '#000000FF' }], effects: [e], fxOnly: only, blend: blended(e) ? e.blend : null, key: k }, ctx);
        allDrops.forEach((e, i) => fxLayers.push(silB(e, 'drop', 'pd' + i)));
        printInners = allInners.map((e, i) => silB(e, 'inner', 'pi' + i));
        drops = []; inners = []; bDrops.length = 0; bInners.length = 0;
      }
      const behind = drops.filter((e) => e.showBehind);
      const layered = behind.length || !fills.every(simplePaint);
      for (const e of bDrops) {
        const sp = +e.spread || 0, mb = `mix-blend-mode:${blendCSS(e.blend)};`;
        if (e.showBehind) fxLayers.push(`<div class="ppt-d" style="left:${n2(e.x - sp)}px;top:${n2(e.y - sp)}px;right:${n2(-e.x - sp)}px;bottom:${n2(-e.y - sp)}px;${radii.some((r) => r) ? `border-radius:${radii.map((r) => n2(r ? r + sp : 0) + 'px').join(' ')};` : ''}background:${rgba(e.color)};filter:blur(${n2((e.blur || 0) / 2)}px);${mb}"></div>`);
        else fxLayers.push(`<div class="ppt-d" style="left:0;top:0;width:100%;height:100%;${rCSS}box-shadow:${n2(e.x)}px ${n2(e.y)}px ${n2(e.blur)}px ${n2(e.spread)}px ${rgba(e.color)};${mb}"></div>`);
      }
      if (!fills.length && (drops.length || inners.length)) svgFx = true;
      else {
        const front = drops.filter((e) => !e.showBehind).reverse().map((e) => `${n2(e.x)}px ${n2(e.y)}px ${n2(e.blur)}px ${n2(e.spread)}px ${rgba(e.color)}`);
        if (front.length) css += `box-shadow:${front.join(',')};`;
        for (const e of behind) {
          const sp = +e.spread || 0;
          pre.push(`<div class="ppt-d" style="left:${n2(e.x - sp)}px;top:${n2(e.y - sp)}px;right:${n2(-e.x - sp)}px;bottom:${n2(-e.y - sp)}px;${radii.some((r) => r) ? `border-radius:${radii.map((r) => n2(r ? r + sp : 0) + 'px').join(' ')};` : ''}background:${rgba(e.color)};filter:blur(${n2((e.blur || 0) / 2)}px)"></div>`);
        }
        if (layered) fills.forEach((f, i) => pre.push(layerHTML(f, w, h, ctx, rCSS, defs, 'f' + i)));
        else css += bgCSS(fills, w, h, ctx);
        if (inners.length) pre.push(`<div class="ppt-d" style="left:0;top:0;width:100%;height:100%;${rCSS}box-shadow:${inners.reverse().map((e) => `inset ${n2(e.x)}px ${n2(e.y)}px ${n2(e.blur)}px ${n2(e.spread)}px ${rgba(e.color)}`).join(',')}"></div>`);
      }
      pre.push(...printInners);
      for (const e of bInners) pre.push(`<div class="ppt-d" style="left:0;top:0;width:100%;height:100%;${rCSS}box-shadow:inset ${n2(e.x)}px ${n2(e.y)}px ${n2(e.blur)}px ${n2(e.spread)}px ${rgba(e.color)};mix-blend-mode:${blendCSS(e.blend)}"></div>`);
      css += rCSS;
      if (OL) post.push(`<div class="ppt-d" style="left:0;top:0;width:100%;height:100%;${rCSS}border:calc(1px / var(--zoom, 1)) solid #000"></div>`);
      else if (strokes.length && (st.weight > 0 || st.sides)) {
        const dashed = (st.dash || []).some((v) => v > 0);
        const sides = ['rect', 'frame', 'page'].includes(type) && st.sides ? st.sides : null;
        if (dashed && sides) post.push(...svgChunks({ d: smoothRectD(w, h, radii, 0), w, h, stroke: st, segs: sideSegs(w, h, radii, sides, st.align), key: 'b' }, strokes, 'strokes', ctx));
        else if (dashed) post.push(...svgChunks({ d: smoothRectD(w, h, radii, 0), w, h, stroke: st, key: 'b' }, strokes, 'strokes', ctx));
        else strokes.forEach((s, i) => post.push(ringHTML(s, st, radii, w, h, ctx, defs, i, !!sides)));
      }
      if (bgBlur) css += `backdrop-filter:blur(${n2(bgBlur.radius / 2)}px);-webkit-backdrop-filter:blur(${n2(bgBlur.radius / 2)}px);`;
    } else if (smooth || SHAPES.has(type)) {
      if (SHAPES.has(type)) el.classList.add('ppt-shape');
      const g = smooth ? { d: smoothRectD(w, h, radii, p.smoothing) } : nodeGeometry(id, geoSrc);
      if (g.d) {
        const open = !!g.open || type === 'line';
        // silhouette (fills + strokes in black) carrying one separately blended shadow
        const sil = (e, only, k) => svgPaint({ d: g.d, rule: g.rule, w, h, open, fills: open ? [] : [{ type: 'SOLID', color: '#000000FF' }], strokes: strokes.length ? [{ type: 'SOLID', color: '#000000FF' }] : [], stroke: st, effects: [e], fxOnly: only, blend: e.blend, key: k }, ctx);
        // paint-level burn splits the SVG; shadows then move to silhouette layers (they need the whole shape)
        const split = !!ctx.plb && [...fills, ...strokes].some((f) => f.blend === 'LINEAR_BURN');
        if (split && ctx.lbSlice && SHAPES.has(type)) ctx.hitHTML = svgPaint({ d: g.d, rule: g.rule, w, h, open, stroke: st, hit: true, key: 'h' }, ctx);
        const shDrops = split ? allDrops : bDrops, shInners = split ? allInners : bInners;
        const fx0 = split ? plainFx.filter((e) => e.type !== 'DROP_SHADOW' && e.type !== 'INNER_SHADOW') : plainFx;
        shDrops.forEach((e, i) => fxLayers.push(sil(e, 'drop', 'd' + i)));
        if (smooth) {
          pre.push(...svgChunks({ d: g.d, w, h, effects: fx0, key: 'a', ol: OL }, fills, 'fills', ctx));
          shInners.forEach((e, i) => pre.push(sil(e, 'inner', 'i' + i)));
          const sides = st.sides && !OL ? st.sides : null;
          const dashed = (st.dash || []).some((v) => v > 0);
          if (strokes.length && sides && dashed) post.push(...svgChunks({ d: g.d, w, h, stroke: st, segs: sideSegs(w, h, radii, sides, st.align), key: 'b' }, strokes, 'strokes', ctx));
          else if (strokes.length && sides) post.push(...svgChunks({ d: sideRingD(w, h, radii, p.smoothing, sides, st.align), rule: 'EVENODD', w, h, key: 'b' }, strokes, 'fills', ctx));
          else if (strokes.length) post.push(...svgChunks({ d: g.d, w, h, stroke: st, key: 'b' }, strokes, 'strokes', ctx));
        } else if (split) {
          const base = { d: g.d, rule: g.rule, w, h, open, stroke: st, effects: fx0, key: 'a', ol: OL, hit: true };
          pre.push(...svgChunks(base, type === 'line' ? [] : fills, 'fills', ctx));
          shInners.forEach((e, i) => pre.push(sil(e, 'inner', 'i' + i)));
          pre.push(...svgChunks({ ...base, hit: false, key: 'b' }, strokes, 'strokes', ctx));
        } else {
          pre.push(svgPaint({ d: g.d, rule: g.rule, w, h, open, fills: type === 'line' ? [] : fills, strokes, stroke: st, effects: plainFx, key: 'a', ol: OL, hit: true }, ctx));
          bInners.forEach((e, i) => pre.push(sil(e, 'inner', 'i' + i)));
        }
        if (bgBlur) pre.unshift(`<div class="ppt-d" style="left:0;top:0;width:100%;height:100%;clip-path:path('${g.d}');backdrop-filter:blur(${n2(bgBlur.radius / 2)}px);-webkit-backdrop-filter:blur(${n2(bgBlur.radius / 2)}px)"></div>`);
      }
    } else if (type === 'text' || type === 'group') {
      if (drops.length || inners.length) svgFx = true;
    }
    if (svgFx) {
      const ff = fxFilter(`${ctx.uid}-hx`, [...drops, ...inners], w, h, true);
      if (ff) { defs.push(ff); filters.push(`url(#${ctx.uid}-hx)`); }
    }
    if (blur && !blur.progressive) filters.push(`blur(${n2(blur.radius / 2)}px)`);
    const lbm = OL ? null : lbMode(node, p);
    if (lbm) filters.push('invert(1)');
    if (mode === 'print' && rasterIds.has(id)) filters.push('opacity(1)'); // forces a raster group in the PDF
    if (filters.length) css += `filter:${filters.join(' ')};`;
    if (p.opacity != null && p.opacity < 1) css += `opacity:${n2(p.opacity)};`;
    const mb = lbm ? 'plus-lighter' : blendCSS(p.blend);
    if (mb !== 'normal') css += `mix-blend-mode:${mb};`;
    else if (p.blend === 'NORMAL' && CONTAINERS.has(type) && !unisoIds.has(id)) css += 'isolation:isolate;';

    // content
    if (type === 'text') css += paintText(el, node, p, OL, defs, ctx.uid);
    else if (type === 'table') css += paintTable(el, p, OL);
    else if (type === 'video') paintVideo(el, p);
    else if (el._content && !CONTAINERS.has(type)) { el._content.remove(); el._content = null; }
    if (el._c) styleContainer(el, node, p, radii, smooth);

    // post decorations: guides, section label
    if (EDIT && showGuides && (type === 'page' || type === 'frame') && !p.rotation) {
      const gh = guidesHTML(p.guides, w, h);
      if (gh) post.push(gh);
    }

    clearDecor(el);
    el._paintCSS = css;
    el.style.cssText = boxCSS(node, p) + css;
    const stacking = p.rotation || p.flipX || p.flipY || filters.length || (p.opacity ?? 1) < 1 || mb !== 'normal' || bgBlur || /isolation/.test(css);
    const flowChild = !!(nodeOf(node.parent) && autoLayout(props(node.parent)) && !(p.layoutChild || {}).absolute && type !== 'page');
    if (el._fx && (!fxLayers.length || !stacking || flowChild)) { el._fx.remove(); el._fx = null; }
    if (fxLayers.length && stacking && !flowChild) {
      if (!el._fx) { el._fx = document.createElement('div'); el._fx.className = 'ppt-n ppt-fxs'; el.before(el._fx); }
      el._fx.style.cssText = boxCSS(node, p) + `width:${n2(w)}px;height:${n2(h)}px;pointer-events:none;` + ((p.opacity ?? 1) < 1 ? `opacity:${n2(p.opacity)};` : '') + (blur && !blur.progressive ? `filter:blur(${n2(blur.radius / 2)}px);` : '');
      el._fx.innerHTML = fxLayers.join('');
    } else if (fxLayers.length) pre.unshift(...fxLayers);
    if (defs.length) pre.unshift(`<svg class="ppt-d" width="0" height="0" style="left:0;top:0;overflow:hidden" aria-hidden="true"><defs>${defs.join('')}</defs></svg>`);
    let preHTML = pre.join('');
    dropSlices(el);
    if (ctx.lbSlice && preHTML.includes('<!--lb1-->')) preHTML = buildSlices(el, node, p, preHTML) + (ctx.hitHTML || ''); // hit path stays on the node
    if (preHTML) el.insertAdjacentHTML('afterbegin', preHTML);
    if (post.length) el.insertAdjacentHTML('beforeend', post.join(''));
    if (type === 'section' && EDIT && p.name) {
      const sl = document.createElement('div');
      sl.className = 'ppt-d ppt-sl';
      sl.textContent = p.name;
      el.appendChild(sl);
    }
    if (blur?.progressive && type !== 'page') twins.add(id);
    else if (twins.has(id) || el._twin) { twins.delete(id); el._twin?.remove(); el._twin = null; }
    if (ctx.plb) {
      plbIds.add(id);
      const pg = store.pageOf(id);
      if (EDIT && pg && !lbPages.has(pg.id)) { lbPages.add(pg.id); applyBox(pg.id); }
    } else plbIds.delete(id);
    if (lbm) {
      if (!el._lb1 || el._lb1.dataset.m !== lbm) { dropLB(el); el._lb1 = lbLayer(lbm); el._lb3 = lbLayer(lbm); }
      if (!el._lb1.isConnected) el.before(el._lb1);
      if (!el._lb3.isConnected) (el._twin || el).after(el._lb3);
      // L1/L3 edges must never land on visible pixels: a partly covered edge pixel does not cancel under
      // the double inversion. Canvas/present: position:fixed escapes page/frame overflow clips (they are
      // not in its containing-block chain) and spans far beyond the content. Print: an absolute layer
      // spanning the page, clipped at the PDF page edge.
      const pg = store.pageOf(id), pp = pg ? props(pg.id) : p;
      const S = lbm === 'bf' ? 100000 : Math.ceil(2 * Math.max(pp.w || 0, pp.h || 0) + 1000);
      const fill = lbm === 'bf' ? 'backdrop-filter:invert(1);-webkit-backdrop-filter:invert(1);' : 'background:#fff;mix-blend-mode:difference;';
      el._lb1.style.cssText = el._lb3.style.cssText = `position:${lbm === 'bf' ? 'fixed' : 'absolute'};pointer-events:none;left:${-S}px;top:${-S}px;width:${3 * S}px;height:${3 * S}px;${el.style.zIndex ? `z-index:${el.style.zIndex};` : ''}${fill}`;
      if (EDIT && pg && !lbPages.has(pg.id)) { lbPages.add(pg.id); applyBox(pg.id); } // paint containment would clip L1/L3
      lbIds.add(id);
    } else if (el._lb1) { dropLB(el); lbIds.delete(id); }
  }

  // ----- LINEAR_BURN without plus-darker: max(0, b + s − 1) = 1 − min(1, (1 − b) + (1 − s)) -----
  // L1 inverts the backdrop under the layer, the layer itself is drawn inverted with plus-lighter, L3
  // inverts the result back. Canvas/present invert with backdrop-filter (transparent backdrop stays
  // transparent). Chrome's PDF output drops backdrop-filter and plus-lighter, so print inverts with an
  // opaque white `difference` layer inside a rasterized group whose fill is opaque (see lbMode).
  // Residual: where the source is partly transparent (layer opacity < 1, antialiased edges) and the burn
  // clips to black, the result is max(0, b − α(1 − s)) instead of (1 − α)·b. NORMAL-blend isolation of
  // ancestors is not honored for this mode (it burns against everything behind, like pass-through).
  function lbLayer(m) {
    const d = document.createElement('div');
    d.className = 'ppt-lb';
    d.dataset.m = m;
    return d;
  }
  function dropLB(el) { el._lb1?.remove(); el._lb3?.remove(); el._lb1 = el._lb3 = null; }
  function dropSlices(el) { for (const x of el._slices || []) x.remove(); el._slices = null; }
  const isFlowChild = (node, p) => !!(nodeOf(node.parent) && autoLayout(props(node.parent)) && !(p.layoutChild || {}).absolute && node.type !== 'page');
  const transformOnlyStack = (node, p) => !!(p.rotation || p.flipX || p.flipY) && !isStack(node, { ...p, rotation: 0, flipX: false, flipY: false });
  // Split a node's pre-decoration HTML at burn markers into sibling elements placed before it:
  // [transformed slice: paints below] [L1] [transformed slice: burn paint, inverted, plus-lighter] [L3] …
  // The trailing part (paints above) stays inside the node element. Returns that trailing HTML.
  function buildSlices(el, node, p, html) {
    const parts = html.split(/<!--(lb1|lbp|lb3|lbe)-->/);
    const slices = [];
    const box = () => boxCSS(node, p) + `width:${n2(el._size?.w ?? p.w)}px;height:${n2(el._size?.h ?? p.h)}px;pointer-events:none;`;
    const mk = (inner, kind) => {
      const t = document.createElement('template');
      t.innerHTML = inner;
      if (kind === 'inv') { slices.push(...t.content.children); return; }
      const d = document.createElement('div');
      d.className = 'ppt-n ppt-slice';
      d.dataset.k = kind;
      d.style.cssText = box() + (kind === 'p' ? 'filter:invert(1);mix-blend-mode:plus-lighter;' : '');
      d.append(t.content);
      slices.push(d);
    };
    let tail = '', state = 'text';
    for (let i = 0; i < parts.length; i++) {
      const tok = parts[i];
      if (i % 2 === 1) { state = { lb1: 'inv', lbp: 'p', lb3: 'inv', lbe: 'text' }[tok]; continue; }
      if (!tok) continue;
      if (state === 'text') tail += tok;
      else {
        if (tail.trim()) { mk(tail, 't'); tail = ''; }
        mk(tok, state);
      }
    }
    for (const x of slices) el.before(x);
    el._slices = slices;
    return tail;
  }
  // A transformed canvas/present root is its own composited surface; backdrop-filter only sees that
  // surface, where the area around pages is transparent, and semi-transparent page-edge pixels do not
  // survive the double inversion. While a burn layer exists, an opaque canvas-colored backdrop sits first
  // in the root (color: --ppt-backdrop, else the app's --canvas).
  let lbBackdrop = null;
  function syncLBBackdrop() {
    if (mode === 'print') return;
    const any = lbIds.size || plbIds.size;
    if (any && !lbBackdrop) {
      lbBackdrop = document.createElement('div');
      lbBackdrop.className = 'ppt-lb-backdrop';
      lbBackdrop.style.cssText = `position:absolute;left:-100000px;top:-100000px;width:300000px;height:300000px;pointer-events:none;background:var(--ppt-backdrop, var(--canvas, ${EDIT ? '#F5F5F5' : '#000'}))`;
    }
    if (any && root.firstChild !== lbBackdrop) root.prepend(lbBackdrop);
    if (!any && lbBackdrop) { lbBackdrop.remove(); lbBackdrop = null; }
  }
  // The enclosing stacking context of a node's element (what its blend composites against).
  // Is this node's element its own stacking context (its blends composite only against its content)?
  // NORMAL-blend isolation alone does not count: those nodes render pass-through for burns (unisoIds)
  // so print composites against the same backdrop the canvas variant sees.
  function isStack(a, q) {
    const fx = vis(q.effects), shadows = fx.some((e) => e.type === 'DROP_SHADOW' || e.type === 'INNER_SHADOW');
    return !!(q.rotation || q.flipX || q.flipY || (q.opacity ?? 1) < 1 || (q.blend && q.blend !== 'PASS_THROUGH' && q.blend !== 'NORMAL') ||
      fx.some((e) => e.type === 'LAYER_BLUR' || e.type === 'BACKGROUND_BLUR') || (shadows && (a.type === 'group' || a.type === 'text' || !vis(q.fills).length)));
  }
  function stackOf(node) {
    for (let a = nodeOf(node.parent); a; a = nodeOf(a.parent)) {
      if (a.type === 'page') return a;
      if (isStack(a, props(a.id))) return a;
    }
    return null;
  }
  const opaquePaint = (f) => (f.opacity ?? 1) >= 1 && (!f.blend || f.blend === 'NORMAL' || f.blend === 'PASS_THROUGH') &&
    (f.type === 'SOLID' ? alphaOf(f.color) >= 1 : f.type === 'LINEAR' || f.type === 'RADIAL' || f.type === 'ANGULAR' || f.type === 'DIAMOND' ? (f.stops || []).every((s) => alphaOf(s.color) >= 1) : false);
  function lbMode(node, p) {
    if (p.blend !== 'LINEAR_BURN' || PLUS_DARKER === 'plus-darker') return null;
    if (mode !== 'print') return 'bf';
    const g = stackOf(node);
    if (!g) return null;
    const q = props(g.id);
    const ok = vis(q.fills).some(opaquePaint) && (g.type === 'page' || q.clip !== false);
    return ok ? 'diff' : null; // no opaque backdrop to invert against: falls back to color-burn
  }
  // Paint-level burn mode for a node (fills/strokes with blend LINEAR_BURN). Text paints are merged into
  // one clipped background and keep the CSS fallback. Print needs an opaque backdrop outside the node.
  function paintLBMode(node, p) {
    if (PLUS_DARKER === 'plus-darker' || node.type === 'text' || node.type === 'group') return null;
    if (![...vis(p.fills), ...vis(p.strokes)].some((f) => f.blend === 'LINEAR_BURN')) return null;
    if (mode !== 'print') return 'bf';
    if (isStack(node, p) && !(transformOnlyStack(node, p) && !isFlowChild(node, p))) return null;
    const g = stackOf(node);
    if (!g) return null;
    const q = props(g.id);
    return vis(q.fills).some(opaquePaint) && (g.type === 'page' || q.clip !== false) ? 'diff' : null;
  }
  // Which ancestors render pass-through (NORMAL isolation would make them separate surfaces whose
  // semi-transparent edges break the inversion) and, in print, which group is rasterized.
  // Returns ids whose isolation/raster state changed (they need a repaint).
  function scanLB() {
    const was = new Set([...unisoIds, ...[...rasterIds].map((x) => 'r' + x)]);
    rasterIds.clear(); unisoIds.clear();
    const burns = (arr) => Array.isArray(arr) && arr.some((f) => f && f.blend === 'LINEAR_BURN');
    for (const n of store.nodes.values()) {
      const r = n.props || {};
      if (r.blend !== 'LINEAR_BURN' && !burns(r.fills) && !burns(r.strokes) && !preview.has(n.id)) continue; // cheap pre-filter
      if (!inScope(n.id)) continue;
      const q = props(n.id);
      const m = lbMode(n, q), pm = paintLBMode(n, q);
      if (!m && !pm) continue;
      const g = stackOf(n);
      if (m === 'diff' || pm === 'diff') rasterIds.add(g.id);
      if (pm && q.blend === 'NORMAL' && CONTAINERS.has(n.type)) unisoIds.add(n.id);
      for (let a = nodeOf(n.parent); a && a !== g; a = nodeOf(a.parent)) if (props(a.id).blend === 'NORMAL') unisoIds.add(a.id);
    }
    const now = new Set([...unisoIds, ...[...rasterIds].map((x) => 'r' + x)]);
    const diff = [];
    for (const k of new Set([...was, ...now])) if (was.has(k) !== now.has(k)) diff.push(k[0] === 'r' && !nodeOf(k) ? k.slice(1) : k);
    return diff;
  }

  function ringHTML(paint, st, radii, w, h, ctx, defs, i, sidesOK) {
    const wt = Math.max(0, st.weight ?? 1);
    const sd = sidesOK && st.sides ? st.sides : { t: wt, r: wt, b: wt, l: wt };
    const k = st.align === 'OUTSIDE' ? 1 : st.align === 'CENTER' ? 0.5 : 0;
    const [t, r, b, l] = [sd.t || 0, sd.r || 0, sd.b || 0, sd.l || 0];
    const adj = [[t, l], [t, r], [b, r], [b, l]];
    const rad = radii.map((v, j) => (v ? v + k * Math.max(...adj[j]) : 0));
    const isImg = paint.type === 'IMAGE';
    const lb = lbBurn(paint, ctx);
    const blend = lb ? (lbInner(lb, ctx) ? 'mix-blend-mode:plus-lighter;filter:invert(1);' : '') : paint.blend && paint.blend !== 'NORMAL' && paint.blend !== 'PASS_THROUGH' ? `mix-blend-mode:${blendCSS(paint.blend)};` : '';
    const op = isImg && (paint.opacity ?? 1) < 1 ? `opacity:${n2(paint.opacity)};` : '';
    const ow = w + (l + r) * k, oh = h + (t + b) * k;
    return lbWrap(lb, `<div class="ppt-d" style="left:${n2(-l * k)}px;top:${n2(-t * k)}px;right:${n2(-r * k)}px;bottom:${n2(-b * k)}px;padding:${n2(t)}px ${n2(r)}px ${n2(b)}px ${n2(l)}px;` +
      `border-radius:${rad.map((v) => n2(v) + 'px').join(' ')};${bgCSS([{ ...paint, opacity: isImg ? 1 : paint.opacity }], ow, oh, ctx)}${blend}${op}` +
      `-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box exclude,linear-gradient(#000 0 0)"></div>`, ctx.lbS);
  }

  function styleContainer(el, node, p, radii, smooth) {
    const c = el._c, type = node.type;
    if (type === 'group' || type === 'boolean') { c.className = 'ppt-c'; c.style.cssText = ''; return; }
    const L = type === 'frame' || type === 'page' ? autoLayout(p) : null;
    let s = '';
    if (L) {
      const horiz = L.dir === 'HORIZONTAL';
      c.className = 'ppt-c ppt-al';
      const pad = (L.pad || [0, 0, 0, 0]).slice();
      if (L.strokesIncluded && vis(p.strokes).length && !outline) {
        const k = { INSIDE: 1, CENTER: 0.5, OUTSIDE: 0 }[p.stroke?.align || 'INSIDE'] ?? 1;
        const wt = (p.stroke?.weight || 0) * k;
        for (let i = 0; i < 4; i++) pad[i] += wt;
      }
      const between = L.alignMain === 'SPACE_BETWEEN';
      const mainGap = between ? 0 : L.gap || 0, crossGap = L.wrap ? L.gapCross ?? L.gap ?? 0 : 0;
      const jc = { MIN: 'flex-start', CENTER: 'center', MAX: 'flex-end', SPACE_BETWEEN: 'space-between' }[L.alignMain] || 'flex-start';
      const ai = { MIN: 'flex-start', CENTER: 'center', MAX: 'flex-end', BASELINE: horiz ? 'baseline' : 'flex-start' }[L.alignCross] || 'flex-start';
      s += `flex-direction:${horiz ? 'row' : 'column'};flex-wrap:${L.wrap ? 'wrap' : 'nowrap'};` +
        `${horiz ? 'column-gap' : 'row-gap'}:${n2(mainGap)}px;${horiz ? 'row-gap' : 'column-gap'}:${n2(crossGap)}px;` +
        `padding:${pad.map((v) => n2(v) + 'px').join(' ')};justify-content:${jc};align-items:${ai};align-content:${ai === 'baseline' ? 'flex-start' : ai};`;
      const parent = nodeOf(node.parent), pL = parent ? autoLayout(props(parent.id)) : null;
      const flow = !!pL && !(p.layoutChild || {}).absolute;
      s += sizing(node, p, 'h', flow) === 'HUG' ? 'width:max-content;' : 'width:100%;';
      s += sizing(node, p, 'v', flow) === 'HUG' ? 'height:auto;' : 'height:100%;';
    } else c.className = 'ppt-c';
    const clip = type === 'section' ? false : p.clip !== false;
    if (clip && !outline) {
      s += 'overflow:hidden;';
      if (smooth) s += `clip-path:path('${smoothRectD(el._size?.w ?? p.w, el._size?.h ?? p.h, radii, p.smoothing)}');`;
      else if (radii.some((r) => r)) s += `border-radius:${radii.map((r) => n2(r) + 'px').join(' ')};`;
    }
    c.style.cssText = s;
  }

  function textFillCSS(p, OL) {
    if (OL) return 'color:#000;';
    const f = vis(p.fills);
    if (!f.length) return 'color:transparent;';
    if (f.length === 1 && f[0].type === 'SOLID') return `color:${rgba(f[0].color, f[0].opacity ?? 1)};`;
    return `color:transparent;-webkit-text-fill-color:transparent;${bgCSS(f, p.w, p.h, { src: (h) => (HEX64.test(h || '') ? assetUrl(h) : null), natural: (h) => natural.get(h) })}-webkit-background-clip:text;background-clip:text;`;
  }

  function paintText(el, node, p, OL, defs, uid) {
    let tx = el._content;
    if (!tx || !tx.classList.contains('ppt-tx')) {
      el._content?.remove();
      tx = document.createElement('div');
      tx.className = 'ppt-tx';
      el._content = tx;
      el.appendChild(tx);
    }
    const ar = p.autoResize || 'WIDTH_AND_HEIGHT';
    const style = p.style || {};
    if (editingId() !== node.id) renderText(tx, p, { links });
    const sc = styleCSS(style);
    let s = Object.entries(sc).map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}:${v};`).join('');
    s += `text-align:${{ CENTER: 'center', RIGHT: 'right', JUSTIFIED: 'justify' }[p.alignH] || 'left'};`;
    // Korean wraps by word (like PowerPoint); over-long words still break
    s += `white-space:${ar === 'WIDTH_AND_HEIGHT' ? 'pre' : 'pre-wrap'};word-break:keep-all;overflow-wrap:anywhere;`;
    s += textFillCSS(p, OL);
    const sk = vis(p.strokes).find((x) => x.type === 'SOLID');
    if (sk && !OL && (p.stroke?.weight || 0) > 0) {
      const wt = p.stroke.weight, col = rgba(sk.color, sk.opacity ?? 1), al = p.stroke.align || 'INSIDE';
      if (al === 'CENTER') s += `-webkit-text-stroke:${n2(wt)}px ${col};`;
      else if (al === 'OUTSIDE') s += `-webkit-text-stroke:${n2(wt * 2)}px ${col};paint-order:stroke fill;`;
      else {
        // INSIDE: the band between the glyph alpha and the glyph alpha eroded by the weight
        const fid = `${uid}-ts`;
        defs.push(`<filter id="${fid}" x="-0.2" y="-0.2" width="1.4" height="1.4" color-interpolation-filters="sRGB"><feMorphology in="SourceAlpha" operator="erode" radius="${n2(wt)}" result="er"/><feComposite in="SourceAlpha" in2="er" operator="out" result="band"/><feFlood flood-color="${hex6(sk.color)}" flood-opacity="${n2(alphaOf(sk.color) * (sk.opacity ?? 1))}"/><feComposite in2="band" operator="in" result="st"/><feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="st"/></feMerge></filter>`);
        s += `filter:url(#${fid});`;
      }
    }
    if (ar === 'TRUNCATE') {
      const lines = p.maxLines > 0 ? p.maxLines : Math.max(1, Math.floor((p.h + 0.5) / lineHeightPx(style)));
      s += `display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:${lines};line-clamp:${lines};overflow:hidden;max-height:100%;`;
    }
    if (ar === 'NONE' || ar === 'TRUNCATE') s += 'width:100%;';
    tx.style.cssText = s;
    let box = '';
    if (ar === 'NONE' || ar === 'TRUNCATE') {
      box += `display:flex;flex-direction:column;justify-content:${{ CENTER: 'center', BOTTOM: 'flex-end' }[p.alignV] || 'flex-start'};`;
      if (ar === 'TRUNCATE') box += 'overflow:hidden;';
    }
    return box;
  }

  function paintTable(el, p, OL) {
    let tb = el._content;
    if (!tb || !tb.classList.contains('ppt-tb')) { el._content?.remove(); tb = document.createElement('div'); tb.className = 'ppt-tb'; el._content = tb; el.appendChild(tb); }
    tb.textContent = '';
    const cols = p.cols || [], rows = p.rows || [];
    const bd = p.border || { color: '#D9D9D9FF', weight: 1 };
    const bw = OL ? 1 : Math.max(0, bd.weight || 0), bc = OL ? '#000' : rgba(bd.color);
    tb.style.cssText = `grid-template-columns:${cols.map((c) => n2(c) + 'px').join(' ')};grid-template-rows:${rows.map((r) => `minmax(${n2(r)}px, auto)`).join(' ')};border-top:${bw}px solid ${bc};border-left:${bw}px solid ${bc};`;
    const tint = OL ? 'transparent' : rgba(bd.color, 0.35);
    for (let r = 0; r < rows.length; r++) for (let c = 0; c < cols.length; c++) {
      const key = r + ',' + c, cell = (p.cells || {})[key] || {};
      const div = document.createElement('div');
      div.className = 'ppt-cell';
      div.dataset.cell = key;
      const head = p.header && r === 0;
      const bg = cell.fill && !OL ? rgba(cell.fill) : head ? tint : 'transparent';
      div.style.cssText = `border-right:${bw}px solid ${bc};border-bottom:${bw}px solid ${bc};background:${bg};justify-content:${{ TOP: 'flex-start', BOTTOM: 'flex-end' }[cell.alignV] || 'center'};`;
      const tx = document.createElement('div');
      tx.className = 'ppt-tx';
      const cs = { font: 'Inter', size: 14, weight: head ? 700 : 400, lineHeight: { unit: 'AUTO', value: 0 }, ...(cell.style || {}) };
      if (head && !(cell.style && cell.style.weight)) cs.weight = 700;
      Object.assign(tx.style, styleCSS(cs));
      tx.style.textAlign = { CENTER: 'center', RIGHT: 'right', JUSTIFIED: 'justify' }[cell.alignH] || 'left';
      tx.style.whiteSpace = 'pre-wrap';
      tx.style.wordBreak = 'keep-all';
      tx.style.overflowWrap = 'anywhere';
      tx.style.color = OL ? '#000' : '#000000';
      if (!(editingId() === el.dataset.id)) renderText(tx, { runs: cell.runs || [{ t: '' }] }, { links });
      div.appendChild(tx);
      tb.appendChild(div);
    }
    return `width:${n2(cols.reduce((a, b) => a + b, 0) + bw)}px;height:auto;`;
  }

  function paintVideo(el, p) {
    const src = HEX64.test(p.asset || '') ? assetUrl(p.asset) : '';
    const poster = HEX64.test(p.poster || '') ? assetUrl(p.poster) : '';
    const usePoster = mode === 'print' && poster;
    const key = [mode, src, poster, p.autoplay, p.loop, p.muted].join('|');
    if (el._content?.dataset.key === key) { el.appendChild(el._content); return; }
    el._content?.remove();
    let m;
    if (usePoster) { m = document.createElement('img'); m.src = poster; m.alt = ''; m.decoding = 'sync'; }
    else {
      m = document.createElement('video');
      m.muted = true; m.playsInline = true;
      if (poster) m.poster = poster;
      if (mode === 'present') { m.muted = !!p.muted; m.loop = !!p.loop; m.autoplay = !!p.autoplay; m.controls = !p.autoplay; m.preload = 'auto'; }
      else m.preload = mode === 'print' ? 'auto' : 'metadata';
      if (src) m.src = mode === 'present' || poster ? src : src + '#t=0.001';
    }
    m.className = 'ppt-media';
    m.dataset.key = key;
    el._content = m;
    el.appendChild(m);
  }

  function guidesHTML(guides, w, h) {
    let out = '';
    for (const g of vis(guides)) {
      const color = rgba(g.color || '#FF00001A');
      if (g.type === 'GRID') {
        const s = Math.max(1, g.size || 10);
        out += `<div class="ppt-d" style="left:0;top:0;width:100%;height:100%;background-image:linear-gradient(to right, ${color} 1px, transparent 1px),linear-gradient(to bottom, ${color} 1px, transparent 1px);background-size:${n2(s)}px ${n2(s)}px"></div>`;
        continue;
      }
      const cols = g.type === 'COLUMNS', len = cols ? w : h;
      const gut = g.gutter || 0, mar = g.margin || 0, off = g.offset || 0, align = g.align || 'STRETCH';
      let n = g.count | 0, size = g.size || 0, start;
      if (align === 'STRETCH') {
        if (!n) n = Math.max(1, Math.floor((len - 2 * mar + gut) / ((size || 60) + gut)));
        size = (len - 2 * mar - (n - 1) * gut) / n; start = mar;
      } else {
        size = size || 60;
        if (!n) n = Math.max(1, Math.floor((len - off + gut) / (size + gut)));
        const total = n * size + (n - 1) * gut;
        start = align === 'MIN' ? off : align === 'MAX' ? len - off - total : (len - total) / 2 + off;
      }
      for (let i = 0; i < n && i < 500; i++) {
        const a = start + i * (size + gut);
        out += cols ? `<div class="ppt-d" style="left:${n2(a)}px;top:0;width:${n2(size)}px;height:100%;background:${color}"></div>`
          : `<div class="ppt-d" style="left:0;top:${n2(a)}px;width:100%;height:${n2(size)}px;background:${color}"></div>`;
      }
    }
    return out;
  }

  // Progressive layer blur: the element keeps the start radius and fades out along start→end,
  // a clone carries the end radius and fades in.
  function refreshTwin(id) {
    const el = els.get(id);
    if (!el) return;
    el._twin?.remove();
    el._twin = null;
    const p = props(id), fx = vis(p.effects).find((e) => e.type === 'LAYER_BLUR' && e.progressive);
    if (!fx || p.visible === false) return;
    const pr = fx.progressive, w = p.w, h = p.h;
    const s = pr.start || [0.5, 0], e = pr.end || [0.5, 1];
    const dx = (e[0] - s[0]) * w, dy = (e[1] - s[1]) * h;
    const deg = (Math.atan2(dx, -dy) * 180) / Math.PI;
    const T = cssLineT(deg, w, h), t0 = T(s[0] * w, s[1] * h) * 100, t1 = T(e[0] * w, e[1] * h) * 100;
    const grad = (a, b) => `linear-gradient(${n2(deg)}deg, ${a} ${n2(t0)}%, ${b} ${n2(t1)}%)`;
    const base = el.style.filter && el.style.filter !== 'none' ? el.style.filter + ' ' : '';
    const twin = el.cloneNode(true);
    for (const d of [twin, ...twin.querySelectorAll('[data-id]')]) d.removeAttribute('data-id');
    twin.classList.add('ppt-twin');
    el.style.filter = base + `blur(${n2((pr.startRadius || 0) / 2)}px)`;
    el.style.maskImage = el.style.webkitMaskImage = grad('#000', 'transparent');
    twin.style.filter = base + `blur(${n2((fx.radius || 0) / 2)}px)`;
    twin.style.maskImage = twin.style.webkitMaskImage = grad('transparent', '#000');
    el.after(twin);
    el._twin = twin;
  }

  // ----- public -----

  function update(changed = [], deleted = []) {
    if (!store) return;
    for (const id of deleted) removeNode(id);
    const repaint = new Set(), parents = new Set(), relayout = new Set(), twinDirty = new Set();
    for (const id of changed) {
      const node = nodeOf(id);
      if (!node) { removeNode(id); continue; }
      if (!inScope(id)) { removeNode(id); continue; }
      let el = els.get(id);
      if (!el) {
        el = ensureEl(id);
        if (!el) continue;
        for (const c of store.children(id)) if (!els.has(c.id)) buildSubtree(c.id);
      } else {
        const want = containerFor(node);
        if (want && el.parentNode !== want) { want.appendChild(el); if (el._fx) el.before(el._fx); for (const x of el._slices || []) el.before(x); if (el._lb1) { el.before(el._lb1); el.after(el._lb3); } }
      }
      repaint.add(id);
      if (node.parent) parents.add(node.parent);
      if (CONTAINERS.has(node.type)) for (const c of store.children(id)) relayout.add(c.id);
      for (let a = node.parent; a; a = nodeOf(a)?.parent) {
        const an = nodeOf(a);
        if (!an) break;
        if (an.type === 'boolean') repaint.add(a);
        if (twins.has(a)) twinDirty.add(a);
      }
    }
    for (const pid of parents) reorder(pid);
    autoSeen.clear();
    for (const id of scanLB()) if (els.has(id)) repaint.add(id);
    for (const id of repaint) paint(id);
    for (const id of relayout) if (!repaint.has(id)) applyBox(id);
    const check = new Set(autoSeen);
    for (const id of changed) for (let a = nodeOf(id)?.parent; a; a = nodeOf(a)?.parent) { const an = nodeOf(a); if (an && isAutoSized(an, props(a))) check.add(a); }
    fixAuto(check);
    for (const id of twins) if (repaint.has(id) || twinDirty.has(id)) refreshTwin(id);
    syncLBBackdrop();
  }

  // Previews flush on the next frame; the timer covers throttled rAF (hidden tabs, headless).
  let timer = 0;
  function flush() {
    if (raf) cancelAnimationFrame(raf);
    clearTimeout(timer);
    raf = 0; timer = 0;
    const ids = [...pending];
    pending.clear();
    if (ids.length) update(ids, []);
  }
  const schedule = (id) => { pending.add(id); if (!raf) { raf = requestAnimationFrame(flush); timer = setTimeout(flush, 50); } };

  function mountAll() {
    if (!EDIT && !pageId) pageId = pages()[0]?.id || null;
    autoSeen.clear();
    scanLB();
    for (const pg of pages()) if (inScope(pg.id)) buildSubtree(pg.id);
    fixAuto(new Set(autoSeen));
    for (const id of twins) refreshTwin(id);
    syncLBBackdrop();
  }
  function unmountAll() {
    for (const el of [...els.values()]) { el._twin?.remove(); el._fx?.remove(); el._fx = null; dropLB(el); dropSlices(el); }
    lbIds.clear(); plbIds.clear(); syncLBBackdrop();
    for (const [, el] of els) if (nodeOf(el.dataset.id)?.type === 'page') el.remove();
    for (const lab of labels.values()) lab.remove();
    els.clear(); labels.clear(); twins.clear();
  }

  const api = {
    root,
    get store() { return store; },
    mount(s) {
      store = s;
      if (unsub) unsub();
      unmountAll();
      mountAll();
      const u = store.subscribe?.((c, d) => update(c || [], d || []));
      unsub = typeof u === 'function' ? u : null;
      if (EDIT) active = api;
    },
    update,
    measure(id) {
      const node = nodeOf(id);
      if (!node) return null;
      const p = props(id);
      const el = els.get(id);
      const live = el && !el._hidden && el.isConnected;
      const size = () => {
        if (!live) return [p.w, p.h];
        const cs = getComputedStyle(el);
        const w = parseFloat(cs.width), h = parseFloat(cs.height);
        return [Number.isFinite(w) ? w : p.w, Number.isFinite(h) ? h : p.h];
      };
      if (node.type === 'page') { const [w, h] = size(); return { x: 0, y: 0, w, h }; }
      const parent = nodeOf(node.parent);
      const base = parent && parent.type !== 'page' ? api.measure(parent.id) : { x: 0, y: 0 };
      const pL = parent && (parent.type === 'frame' || parent.type === 'page') ? autoLayout(props(parent.id)) : null;
      let x = p.x || 0, y = p.y || 0;
      if (pL && !(p.layoutChild || {}).absolute && live) { x = el.offsetLeft; y = el.offsetTop; }
      const [w, h] = size();
      return { x: n2(base.x + x), y: n2(base.y + y), w: n2(w), h: n2(h) };
    },
    elementOf: (id) => els.get(id) || null,
    pageElementOf: (id) => { const pg = store?.pageOf(id); return pg ? els.get(pg.id) || null : null; },
    setPreview(id, partial) { preview.set(id, { ...(preview.get(id) || {}), ...partial }); schedule(id); },
    clearPreview(id) { if (preview.delete(id)) schedule(id); },
    setShowGuides(v) { showGuides = !!v; if (store) update([...els.keys()], []); },
    setOutlineMode(v) { outline = !!v; root.classList.toggle('ppt-outline', outline); if (store) update([...els.keys()], []); },
    setPage(id) { pageId = id; if (store) { unmountAll(); mountAll(); } },
    get page() { return pageId; },
    // Resolves when every image referenced so far has loaded (print waits on it).
    ready: () => Promise.all([...loads.values(), document.fonts?.ready]).then(() => undefined),
    destroy() {
      if (raf) cancelAnimationFrame(raf);
      clearTimeout(timer);
      if (unsub) unsub();
      unmountAll();
      root.classList.remove('ppt-root', 'ppt-' + mode, 'ppt-outline');
      if (active === api) active = null;
      store = null;
    },
  };
  return api;
}
