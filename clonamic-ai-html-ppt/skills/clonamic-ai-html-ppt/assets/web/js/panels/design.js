// 디자인 패널 (우측) — Figma 스타일 속성 편집기. 바닐라 ES 모듈, 외부 의존 없음.
// 계약: format.md §6. 모든 편집은 ctx.preview(미리보기) → ctx.commit(1회) 흐름을 따른다.
import { SCHEMA, propsOf } from '../schema.js';
import { normalize } from '../render.js';

/* ───────────────────────── 모듈 상태 (패널은 한 번에 하나만 마운트) ───────────────────────── */
let ctx = null, store = null, root = null, hostEl = null;
let textMod = null;            // ../text.js (있을 때만)
let layoutMod = null;          // ../layout.js (있을 때만, resizeOps)
let busy = 0;                  // 드래그/스크럽 진행 중 개수 (재렌더 보류)
let dirtyWhileBusy = false;
let refreshers = [];           // 포커스 중 값만 갱신하는 콜백
let lastSig = '';
let pop = null;                // 열려 있는 팝오버 {el, close, refresh}
const lockIds = new Set();     // 비율 잠금
const indepRadius = new Set(); // 모서리 독립 편집
const MIXED = '\u0000mixed';
let localFonts = [];           // queryLocalFonts() 결과(사용자 제스처로 불러온 것)

/* ───────────────────────── 작은 유틸 ───────────────────────── */
// resolved props with partial nested objects (style/stroke/layout…) filled from defaults (format.md §8)
const normCache = new WeakMap();
const P = (n) => { const r = propsOf(n); let q = normCache.get(r); if (!q) { q = normalize(n.type, r); normCache.set(r, q); } return q; };
const clone = (v) => (v && typeof v === 'object' ? JSON.parse(JSON.stringify(v)) : v);
const eq = (a, b) => a === b || JSON.stringify(a) === JSON.stringify(b);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const round = (v, d = 2) => { const m = 10 ** d; return Math.round(v * m) / m || 0; };
const fmtNum = (v, d = 2) => String(round(v, d));
const allSame = (vs) => vs.every((v) => eq(v, vs[0]));
const rad2deg = (r) => (r * 180) / Math.PI;
const deg2rad = (d) => (d * Math.PI) / 180;
const raf = (fn) => requestAnimationFrame(fn);
const nodeById = (id) => store.nodes.get(id);
const parentOf = (n) => (n.parent ? nodeById(n.parent) : null);
const parentLayout = (n) => { const p = parentOf(n); return p ? P(p).layout || null : null; };
const lbl = (arr, v) => (arr.find((x) => x[0] === v) || [])[1] ?? v;

function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'style') { if (typeof v === 'string') e.style.cssText = v; else Object.assign(e.style, v); }
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (k === 'tabindex') e.setAttribute('tabindex', v);
      else if (k in e) e[k] = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}

/* ───────────────────────── 아이콘 (직접 그린 16×16 선 아이콘) ───────────────────────── */
const ICONS = {
  plus: '<path d="M8 3v10M3 8h10"/>', minus: '<path d="M3 8h10"/>', close: '<path d="M4 4l8 8M12 4l-8 8"/>',
  chev: '<path d="M4.5 6.5L8 10l3.5-3.5"/>', check: '<path d="M3.5 8.5l3 3 6-7"/>',
  eye: '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>',
  eyeOff: '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/><path d="M3 13L13 3"/>',
  drag: '<g fill="currentColor" stroke="none"><circle cx="6" cy="4" r="1"/><circle cx="10" cy="4" r="1"/><circle cx="6" cy="8" r="1"/><circle cx="10" cy="8" r="1"/><circle cx="6" cy="12" r="1"/><circle cx="10" cy="12" r="1"/></g>',
  lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1.2"/><path d="M5.5 7V5.2a2.5 2.5 0 015 0V7"/>',
  unlock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1.2"/><path d="M5.5 7V5.2a2.5 2.5 0 014.8-1"/>',
  portrait: '<rect x="4" y="2" width="8" height="12" rx="1"/>', landscape: '<rect x="2" y="4" width="12" height="8" rx="1"/>',
  rotate: '<path d="M13 8a5 5 0 11-1.6-3.7M13 2.5v3h-3"/>', rot90: '<path d="M12.5 8A4.5 4.5 0 118 3.5M8 1.5l2 2-2 2"/>',
  swap: '<path d="M3 5h9M9.5 2.5L12 5 9.5 7.5M13 11H4M6.5 8.5L4 11l2.5 2.5"/>', flip: '<path d="M8 2v12"/><path d="M5.5 4L2 8l3.5 4zM10.5 4L14 8l-3.5 4z"/>',
  gear: '<path d="M2.5 5h11M2.5 11h11"/><circle cx="6" cy="5" r="1.6" fill="var(--panel,#fff)"/><circle cx="10.5" cy="11" r="1.6" fill="var(--panel,#fff)"/>',
  dropper: '<path d="M10 3l3 3-1.6 1.6-3-3zM9 5L3.5 10.5V13H6l5.5-5.5"/>',
  alL: '<path d="M2 3h12M2 6h8M2 9h12M2 12h8"/>', alC: '<path d="M2 3h12M4 6h8M2 9h12M4 12h8"/>', alR: '<path d="M2 3h12M6 6h8M2 9h12M6 12h8"/>', alJ: '<path d="M2 3h12M2 6h12M2 9h12M2 12h12"/>',
  avT: '<path d="M2 2.5h12M6 5v8.5M10 5v5.5"/>', avM: '<path d="M2 8h12M6 3v10M10 5v6"/>', avB: '<path d="M2 13.5h12M6 2.5v8.5M10 5.5v5.5"/>',
  dNone: '<path d="M4 4h8M8 4v7"/>', dUnder: '<path d="M4 3h8M8 3v7M4 13h8"/>', dStrike: '<path d="M4 3h8M8 3v10M3 8.5h10"/>',
  lNone: '<path d="M4 4h9M4 8h9M4 12h9"/>', lBullet: '<g fill="currentColor" stroke="none"><circle cx="3" cy="4" r="1"/><circle cx="3" cy="8" r="1"/><circle cx="3" cy="12" r="1"/></g><path d="M6 4h8M6 8h8M6 12h8"/>',
  lOrder: '<text x="1" y="6" font-size="5.5" fill="currentColor" stroke="none">1</text><text x="1" y="10.5" font-size="5.5" fill="currentColor" stroke="none">2</text><text x="1" y="15" font-size="5.5" fill="currentColor" stroke="none">3</text><path d="M7 4h7M7 8.5h7M7 13h7"/>',
  arW: '<path d="M2 8h12M4.5 5.5L2 8l2.5 2.5M11.5 5.5L14 8l-2.5 2.5"/>', arH: '<path d="M8 2v12M5.5 4.5L8 2l2.5 2.5M5.5 11.5L8 14l2.5-2.5"/>', arFix: '<rect x="3" y="3" width="10" height="10" rx="1"/>', arTrunc: '<path d="M2 8h7"/><g fill="currentColor" stroke="none"><circle cx="11.2" cy="8" r=".9"/><circle cx="14" cy="8" r=".9"/></g>',
  dirV: '<path d="M8 2.5v11M4.5 10L8 13.5 11.5 10"/>', dirH: '<path d="M2.5 8h11M10 4.5L13.5 8 10 11.5"/>', wrap: '<path d="M3 4h9.5a1.8 1.8 0 010 3.6H4M6 5.6L3.8 7.6 6 9.6M3 12h6"/>',
  baseline: '<path d="M2.5 13h11"/><path d="M5 10V4M9 10V6.5M12 10V5"/>',
  bUnion: '<path d="M2.5 2.5h7v4h4v7h-7v-4h-4z" fill="currentColor" fill-opacity=".25"/>', bSub: '<path d="M2.5 2.5h7v4h-3v3h-4z" fill="currentColor" fill-opacity=".25"/><path d="M9.5 6.5h4v7h-7v-4"/>',
  bInt: '<path d="M2.5 2.5h7v7h-7zM6.5 6.5h7v7h-7z"/><path d="M6.5 6.5h3v3h-3z" fill="currentColor" fill-opacity=".4"/>', bExc: '<path d="M2.5 2.5h7v7h-7zM6.5 6.5h7v7h-7z"/><path d="M2.5 2.5h7v4h-3v3h-4zM9.5 9.5h4v4h-7v-4z" fill="currentColor" fill-opacity=".35" stroke="none"/>',
  corner: '<path d="M3 13V8.5A5.5 5.5 0 018.5 3H13"/>', corners: '<path d="M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3"/>',
  baselineI: '<path d="M3 13h10M8 3v7M5 3h6"/>',
  none: '<path d="M3 13L13 3"/><rect x="3" y="3" width="10" height="10" rx="1.5" stroke-dasharray="1.5 2"/>',
};
function ic(name) {
  const s = h('span', { class: 'dp-ic' });
  s.innerHTML = `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
  return s;
}

/* ───────────────────────── 색 유틸 ───────────────────────── */
const hex2 = (n) => Math.round(clamp(n, 0, 255)).toString(16).padStart(2, '0').toUpperCase();
function parseHex(c) {
  let s = String(c || '').replace('#', '').trim();
  if (s.length === 3 || s.length === 4) s = [...s].map((x) => x + x).join('');
  if (!/^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(s)) return null;
  return { r: parseInt(s.slice(0, 2), 16), g: parseInt(s.slice(2, 4), 16), b: parseInt(s.slice(4, 6), 16), a: s.length === 8 ? parseInt(s.slice(6, 8), 16) / 255 : 1 };
}
const toHex = ({ r, g, b, a }) => '#' + hex2(r) + hex2(g) + hex2(b) + hex2(a * 255);
function rgb2hsv(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let hh = 0;
  if (d) { if (mx === r) hh = ((g - b) / d) % 6; else if (mx === g) hh = (b - r) / d + 2; else hh = (r - g) / d + 4; hh *= 60; if (hh < 0) hh += 360; }
  return [hh, mx ? d / mx : 0, mx];
}
function hsv2rgb(hh, s, v) {
  const c = v * s, x = c * (1 - Math.abs(((hh / 60) % 2) - 1)), m = v - c;
  let r = 0, g = 0, b = 0;
  if (hh < 60) [r, g, b] = [c, x, 0]; else if (hh < 120) [r, g, b] = [x, c, 0]; else if (hh < 180) [r, g, b] = [0, c, x];
  else if (hh < 240) [r, g, b] = [0, x, c]; else if (hh < 300) [r, g, b] = [x, 0, c]; else [r, g, b] = [c, 0, x];
  return { r: (r + m) * 255, g: (g + m) * 255, b: (b + m) * 255 };
}
const withAlpha = (hex, a) => { const c = parseHex(hex) || { r: 0, g: 0, b: 0 }; return toHex({ ...c, a }); };
const lerpColor = (c1, c2, t) => { const a = parseHex(c1), b = parseHex(c2); if (!a || !b) return c1; return toHex({ r: a.r + (b.r - a.r) * t, g: a.g + (b.g - a.g) * t, b: a.b + (b.b - a.b) * t, a: a.a + (b.a - a.a) * t }); };

/* ───────────────────────── 수식 파서 (+ - * / ^ ( ), eval 미사용) ───────────────────────── */
function calcExpr(src, base) {
  let s = String(src).replace(/\s+/g, '').replace(/(px|pt|°|deg|%)$/i, '').replace(/,/g, '.');
  if (!s) return NaN;
  if (/^[*/+]/.test(s) && Number.isFinite(base)) s = `(${base.toFixed(6)})${s}`;
  const toks = s.match(/\d+\.?\d*|\.\d+|[-+*/^()]/g);
  if (!toks || toks.join('') !== s) return NaN;
  let i = 0;
  const peek = () => toks[i];
  function expr() { let v = term(); while (peek() === '+' || peek() === '-') { const o = toks[i++]; const r = term(); v = o === '+' ? v + r : v - r; } return v; }
  function term() { let v = unary(); while (peek() === '*' || peek() === '/') { const o = toks[i++]; const r = unary(); v = o === '*' ? v * r : v / r; } return v; }
  function unary() { if (peek() === '-') { i++; return -unary(); } if (peek() === '+') { i++; return unary(); } return pow(); }
  function pow() { const b = atom(); if (peek() === '^') { i++; return b ** unary(); } return b; }
  function atom() {
    const t = toks[i++];
    if (t === '(') { const v = expr(); if (toks[i++] !== ')') return NaN; return v; }
    const n = parseFloat(t);
    return Number.isNaN(n) ? NaN : n;
  }
  const v = expr();
  return i === toks.length && Number.isFinite(v) ? v : NaN;
}

/* ───────────────────────── 편집 세션: 미리보기(rAF 스로틀) → commit 1회 ───────────────────────── */
function session(nodes) {
  const pend = new Map(), seen = new Set();
  let q = 0;
  const flush = () => { q = 0; for (const [id, p] of pend) ctx.preview(id, p); pend.clear(); };
  const clear = () => { if (q) { cancelAnimationFrame(q); q = 0; } pend.clear(); for (const id of seen) { try { ctx.clearPreview(id); } catch (e) { console.error(e); } } seen.clear(); };
  return {
    preview(build) {
      for (const n of nodes) { const p = build(n); if (p) { pend.set(n.id, p); seen.add(n.id); } }
      if (!q) q = raf(flush);
    },
    async commit(build, label) {
      if (q) { cancelAnimationFrame(q); q = 0; }
      pend.clear();
      const ops = [];
      for (const n of nodes) { const p = build(n); if (p) ops.push({ op: 'set', id: n.id, props: p }); }
      try { if (ops.length) await ctx.commit(ops, label); } catch (e) { console.warn('commit 실패', e); }
      clear();
    },
    cancel: clear,
  };
}
// 미리보기 없이 즉시 한 번 commit
async function commitNodes(nodes, build, label) { await session(nodes).commit(build, label); }
// commit에 임의 op 배열을 넘기고 싶을 때
async function commitOps(ops, label) { try { if (ops.length) await ctx.commit(ops, label); } catch (e) { console.warn('commit 실패', e); } }

function beginBusy() { busy++; }
function endBusy() { busy = Math.max(0, busy - 1); if (!busy && dirtyWhileBusy) { dirtyWhileBusy = false; softRefresh(); } }
const typing = (scope) => { const a = document.activeElement; return !!a && scope.contains(a) && (a.tagName === 'TEXTAREA' || (a.tagName === 'INPUT' && !['checkbox', 'range', 'button'].includes(a.type))); };

/* 텍스트 편집 세션 (text.js 가 있을 때만) */
function activeEdit(nodes) {
  try {
    const e = textMod && textMod.activeTextEdit && textMod.activeTextEdit();
    if (e && nodes.length === 1 && nodes[0].id === e.id) return e;
  } catch (err) { /* 무시 */ }
  return null;
}

/* ───────────────────────── 스타일 (한 번만 주입, .dp-* 네임스페이스) ───────────────────────── */
const CSS = `
.dp,.dp-pop{--dp-bg:var(--bg,#fff);--dp-panel:var(--panel,#fff);--dp-border:var(--border,#e6e6e6);--dp-text:var(--text,#1e1e1e);--dp-dim:var(--text-dim,#8c8c8c);--dp-accent:var(--accent,#0D99FF);--dp-danger:var(--danger,#f24822);--dp-r:var(--radius,5px);--dp-field:var(--field,var(--panel-2,#f5f5f5));--dp-hover:var(--hover,#ececec);
 font:11px/16px var(--font,Inter,"Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif);color:var(--dp-text);box-sizing:border-box;letter-spacing:0}
.dp *,.dp-pop *{box-sizing:border-box}
.dp{background:var(--dp-panel);width:100%;user-select:none;-webkit-user-select:none;padding-bottom:24px}
.dp-sec{border-bottom:1px solid var(--dp-border);padding:2px 0 8px}
.dp-sh{display:flex;align-items:center;height:32px;padding:0 6px 0 12px;font-weight:600;gap:2px}
.dp-sh>.dp-grow{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dp-sh .dp-sub{font-weight:400;color:var(--dp-dim);margin-left:6px}
.dp-body{padding:0 8px 0 12px;display:flex;flex-direction:column;gap:4px}
.dp-row{display:flex;align-items:center;gap:4px;min-height:24px}
.dp-row>*{min-width:0}
.dp-g2{display:grid;grid-template-columns:1fr 1fr;gap:4px}
.dp-g3{display:grid;grid-template-columns:1fr 1fr 24px;gap:4px;align-items:center}
.dp-g4{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}
.dp-cap{color:var(--dp-dim);font-size:11px;padding:4px 0 0}
.dp-dim{color:var(--dp-dim)}
.dp-lab{color:var(--dp-dim);flex:0 0 64px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dp-grow{flex:1}
.dp-empty{padding:24px 12px;color:var(--dp-dim);text-align:center}
.dp-ic{display:inline-flex;width:16px;height:16px;align-items:center;justify-content:center;flex:none;pointer-events:none}
.dp-ic svg{display:block}
/* 아이콘 버튼 */
.dp-ib{width:24px;height:24px;flex:none;border:0;border-radius:var(--dp-r);background:transparent;color:var(--dp-text);display:inline-flex;align-items:center;justify-content:center;padding:0;cursor:default;font:inherit}
.dp-ib:hover{background:var(--dp-hover)}
.dp-ib:focus-visible{outline:2px solid var(--dp-accent);outline-offset:-2px}
.dp-ib.dp-on{background:var(--dp-hover);color:var(--dp-accent)}
.dp-ib[disabled]{opacity:.35;pointer-events:none}
.dp-ib.dp-dng:hover{color:var(--dp-danger)}
.dp-seg{display:flex;background:var(--dp-field);border-radius:var(--dp-r);padding:1px;gap:1px;flex:1;min-width:0}
.dp-seg .dp-ib{flex:1;width:auto;min-width:22px;height:22px}
.dp-seg .dp-ib.dp-on{background:var(--dp-panel);color:var(--dp-text);box-shadow:0 0 0 1px var(--dp-border),0 1px 2px rgba(0,0,0,.08)}
.dp-seg.dp-dis{opacity:.45}
/* 입력 */
.dp-nf{display:flex;align-items:center;height:24px;min-width:0;border:1px solid transparent;border-radius:var(--dp-r);background:var(--dp-field);position:relative}
.dp-nf:hover{border-color:var(--dp-border)}
.dp-nf:focus-within{border-color:var(--dp-accent)}
.dp-nl{flex:none;width:22px;height:22px;text-align:center;color:var(--dp-dim);font-size:11px;line-height:22px;cursor:ew-resize;overflow:hidden;display:inline-flex;align-items:center;justify-content:center}
.dp-nl.dp-nlw{width:auto;padding:0 2px 0 7px;white-space:nowrap}
.dp-nl.dp-nowide{width:auto;padding:0 0 0 6px;cursor:default}
.dp-nf.dp-nolab .dp-in{padding-left:6px}
.dp-tb{font-size:11px}
.dp-ib.dp-tb.dp-on{font-weight:600}
.dp-in{flex:1;min-width:0;width:100%;height:22px;border:0;background:transparent;color:inherit;font:inherit;padding:0 6px 0 2px;outline:0;user-select:text;-webkit-user-select:text;text-overflow:ellipsis}
.dp-in::placeholder{color:var(--dp-dim)}
.dp-in:disabled{opacity:.5}
.dp-sfx{padding-right:6px;color:var(--dp-dim)}
.dp-sel{appearance:none;-webkit-appearance:none;width:100%;height:24px;min-width:0;border:1px solid transparent;border-radius:var(--dp-r);background:var(--dp-field) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath d='M4.5 6.5L8 10l3.5-3.5' fill='none' stroke='%238c8c8c' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat right 2px center;color:inherit;font:inherit;padding:0 18px 0 6px;outline:0;text-overflow:ellipsis}
.dp-sel:hover{border-color:var(--dp-border)}
.dp-sel:focus{border-color:var(--dp-accent)}
.dp-sel:disabled{opacity:.5}
.dp-sf{display:flex;align-items:center;min-width:0;position:relative}
.dp-sf>.dp-sfl{position:absolute;left:6px;color:var(--dp-dim);pointer-events:none;display:inline-flex}
.dp-sf>.dp-sel{padding-left:24px}
.dp-chk{display:flex;align-items:center;gap:6px;min-height:24px;cursor:default}
.dp-chk input{margin:0;width:14px;height:14px;accent-color:var(--dp-accent)}
.dp-ta{width:100%;min-height:72px;resize:vertical;border:1px solid transparent;border-radius:var(--dp-r);background:var(--dp-field);font:inherit;color:inherit;padding:6px;outline:0;user-select:text;-webkit-user-select:text}
.dp-ta:hover{border-color:var(--dp-border)}.dp-ta:focus{border-color:var(--dp-accent)}
.dp-btn{height:24px;border:1px solid var(--dp-border);border-radius:var(--dp-r);background:var(--dp-panel);color:var(--dp-text);font:inherit;padding:0 10px;cursor:default;display:inline-flex;align-items:center;justify-content:center;gap:4px}
.dp-btn:hover{background:var(--dp-hover)}
.dp-btn.dp-pri{background:var(--dp-accent);border-color:var(--dp-accent);color:#fff}
.dp-btn.dp-wide{width:100%}
input[type=range].dp-range{-webkit-appearance:none;appearance:none;flex:1;min-width:0;height:16px;background:transparent;margin:0}
input[type=range].dp-range::-webkit-slider-runnable-track{height:2px;background:var(--dp-border);border-radius:1px}
input[type=range].dp-range::-webkit-slider-thumb{-webkit-appearance:none;width:12px;height:12px;margin-top:-5px;border-radius:50%;background:var(--dp-panel);border:1px solid var(--dp-dim);box-shadow:0 1px 2px rgba(0,0,0,.2)}
input[type=range].dp-range:focus{outline:0}input[type=range].dp-range:focus::-webkit-slider-thumb{border-color:var(--dp-accent)}
/* 스와치/칠 행 */
.dp-prow{display:flex;align-items:center;gap:4px;height:28px;position:relative;border-radius:var(--dp-r)}
.dp-prow.dp-drag{opacity:.55;background:var(--dp-hover)}
.dp-prow.dp-hid .dp-sw,.dp-prow.dp-hid .dp-nf{opacity:.45}
.dp-grip{width:12px;height:24px;flex:none;color:var(--dp-dim);cursor:grab;display:inline-flex;align-items:center;justify-content:center;opacity:0}
.dp-prow:hover .dp-grip{opacity:1}
.dp-sw{width:22px;height:22px;flex:none;border-radius:var(--dp-r);border:1px solid var(--dp-border);position:relative;overflow:hidden;padding:0;cursor:default;background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E%3Crect width='4' height='4' fill='%23ddd'/%3E%3Crect x='4' y='4' width='4' height='4' fill='%23ddd'/%3E%3C/svg%3E")}
.dp-sw>i{position:absolute;inset:0;display:block;background-size:cover;background-position:center}
.dp-sw.dp-mixed{background:repeating-linear-gradient(135deg,#fff 0 3px,#cfcfcf 3px 6px)}
.dp-sw:focus-visible{outline:2px solid var(--dp-accent)}
.dp-ptype{flex:1;min-width:0;height:24px;line-height:24px;padding:0 6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:default}
.dp-prow .dp-nf.dp-op{width:58px;flex:none}
.dp-prow .dp-nf.dp-hexf{flex:1}
.dp-mixrow{height:28px;display:flex;align-items:center;padding:0 6px;border-radius:var(--dp-r);background:var(--dp-field);color:var(--dp-dim);cursor:default}
.dp-mixrow:hover{background:var(--dp-hover)}
.dp-dropline{position:absolute;left:0;right:0;height:2px;background:var(--dp-accent);pointer-events:none}
.dp-list{position:relative;display:flex;flex-direction:column;gap:2px}
/* 팝오버 */
.dp-pop{position:fixed;z-index:2147483000;width:240px;max-height:calc(100vh - 16px);overflow-y:auto;overflow-x:hidden;background:var(--dp-panel);border:1px solid var(--dp-border);border-radius:8px;box-shadow:0 5px 17px rgba(0,0,0,.2),0 2px 7px rgba(0,0,0,.15);user-select:none;-webkit-user-select:none}
.dp-ph{display:flex;align-items:center;height:36px;padding:0 6px 0 12px;font-weight:600;border-bottom:1px solid var(--dp-border);position:sticky;top:0;background:var(--dp-panel);z-index:2}
.dp-ph>.dp-grow{flex:1}
.dp-pb{padding:8px 12px 12px;display:flex;flex-direction:column;gap:6px}
.dp-tabs{display:flex;gap:2px}
.dp-tab{flex:1;height:24px;border:1px solid transparent;border-radius:var(--dp-r);background:var(--dp-field);color:var(--dp-text);font:inherit;font-size:10px;padding:0;cursor:default;position:relative;overflow:hidden}
.dp-tab:hover{border-color:var(--dp-border)}
.dp-tab.dp-on{border-color:var(--dp-accent);box-shadow:0 0 0 1px var(--dp-accent) inset}
.dp-tab>i{position:absolute;inset:4px 6px;border-radius:2px;display:block;border:1px solid rgba(0,0,0,.15)}
/* 색 선택기 */
.dp-cp{display:flex;flex-direction:column;gap:8px}
.dp-sv{position:relative;height:132px;border-radius:var(--dp-r);cursor:crosshair;touch-action:none}
.dp-sv::before,.dp-sv::after{content:"";position:absolute;inset:0;border-radius:inherit}
.dp-sv::before{background:linear-gradient(90deg,#fff,rgba(255,255,255,0))}
.dp-sv::after{background:linear-gradient(0deg,#000,rgba(0,0,0,0))}
.dp-knob{position:absolute;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.35),0 1px 3px rgba(0,0,0,.4);z-index:3;pointer-events:none}
.dp-bar{position:relative;height:12px;border-radius:6px;touch-action:none;cursor:default}
.dp-bar.dp-hue{background:linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)}
.dp-bar.dp-alpha{background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E%3Crect width='4' height='4' fill='%23ddd'/%3E%3Crect x='4' y='4' width='4' height='4' fill='%23ddd'/%3E%3C/svg%3E")}
.dp-bar.dp-alpha>i{position:absolute;inset:0;border-radius:6px}
.dp-bar .dp-knob{top:6px;margin-left:-6px}
.dp-stopbar{background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E%3Crect width='4' height='4' fill='%23ddd'/%3E%3Crect x='4' y='4' width='4' height='4' fill='%23ddd'/%3E%3C/svg%3E");position:relative;height:16px;margin:6px 6px 14px;border-radius:3px;border:1px solid rgba(0,0,0,.12);cursor:copy;touch-action:none;outline:0}
.dp-stopbar:focus-visible{box-shadow:0 0 0 2px var(--dp-accent)}
.dp-stopbar>.dp-gbg{position:absolute;inset:0;border-radius:2px}
.dp-stop{position:absolute;top:12px;width:12px;height:16px;margin-left:-6px;border-radius:2px 2px 6px 6px;background:#fff;border:1px solid var(--dp-dim);box-shadow:0 1px 2px rgba(0,0,0,.25);cursor:grab;padding:0}
.dp-stop>i{position:absolute;inset:2px;border-radius:1px;display:block}
.dp-stop.dp-on{border-color:var(--dp-accent);box-shadow:0 0 0 1px var(--dp-accent)}
.dp-drop{border:1px dashed var(--dp-border);border-radius:var(--dp-r);min-height:84px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;color:var(--dp-dim);position:relative;overflow:hidden;background:var(--dp-field)}
.dp-drop.dp-over{border-color:var(--dp-accent);color:var(--dp-accent)}
.dp-drop img{max-width:100%;max-height:110px;display:block}
.dp-thumb{height:96px;border-radius:var(--dp-r);border:1px solid var(--dp-border);background:var(--dp-field) center/contain no-repeat}
/* 레이아웃 위젯 */
.dp-cw{position:relative;width:64px;height:64px;flex:none;border:1px solid var(--dp-border);border-radius:var(--dp-r);background:var(--dp-field)}
.dp-cw .dp-cin{position:absolute;left:19px;top:19px;width:24px;height:24px;border:1px solid var(--dp-dim);border-radius:2px;background:var(--dp-panel)}
.dp-cw button{position:absolute;border:0;background:transparent;padding:0;cursor:default}
.dp-cw button::after{content:"";position:absolute;background:var(--dp-border);border-radius:1px}
.dp-cw button:hover::after{background:var(--dp-dim)}
.dp-cw button.dp-on::after{background:var(--dp-danger)}
.dp-cw .dp-cl{left:0;top:25px;width:20px;height:12px}.dp-cw .dp-cl::after{left:0;right:0;top:5px;height:2px}
.dp-cw .dp-cr{right:0;top:25px;width:20px;height:12px}.dp-cw .dp-cr::after{left:0;right:0;top:5px;height:2px}
.dp-cw .dp-ct{top:0;left:25px;height:20px;width:12px}.dp-cw .dp-ct::after{top:0;bottom:0;left:5px;width:2px}
.dp-cw .dp-cb{bottom:0;left:25px;height:20px;width:12px}.dp-cw .dp-cb::after{top:0;bottom:0;left:5px;width:2px}
.dp-cw .dp-cch{left:25px;top:21px;height:20px;width:12px}.dp-cw .dp-cch::after{top:0;bottom:0;left:5px;width:2px}
.dp-cw .dp-ccv{top:25px;left:21px;width:20px;height:12px}.dp-cw .dp-ccv::after{left:0;right:0;top:5px;height:2px}
.dp-agrid{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(3,1fr);width:64px;height:64px;flex:none;background:var(--dp-field);border-radius:var(--dp-r);padding:3px;position:relative}
.dp-agrid button{border:0;background:transparent;padding:0;display:flex;align-items:center;justify-content:center;cursor:default;position:relative}
.dp-agrid button::before{content:"";width:4px;height:4px;border-radius:50%;background:var(--dp-dim);opacity:.6}
.dp-agrid button:hover::before{opacity:1;background:var(--dp-text)}
.dp-agrid button.dp-on::before{width:10px;height:10px;background:var(--dp-accent);opacity:1;border-radius:3px}
.dp-agrid button.dp-on2::before{width:6px;height:6px;background:var(--dp-accent);opacity:.9}
.dp-fontlist{max-height:260px;overflow-y:auto;margin:0 -12px;padding:0}
.dp-fi{display:flex;align-items:center;height:28px;padding:0 12px;cursor:default;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}
.dp-fi:hover,.dp-fi.dp-hl{background:var(--dp-accent);color:#fff}
.dp-fi.dp-cur::before{content:"✓";width:14px;margin-left:-4px;flex:none}
.dp-fh{padding:6px 12px 2px;color:var(--dp-dim);font-size:10px}
.dp-fontbtn{justify-content:flex-start;text-align:left;width:100%;height:24px;border:1px solid transparent;border-radius:var(--dp-r);background:var(--dp-field);font:inherit;color:inherit;padding:0 18px 0 6px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;display:block;cursor:default;position:relative}
.dp-fontbtn:hover{border-color:var(--dp-border)}
.dp-fontbtn::after{content:"";position:absolute;right:3px;top:4px;width:16px;height:16px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath d='M4.5 6.5L8 10l3.5-3.5' fill='none' stroke='%238c8c8c' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")}
.dp-err{color:var(--dp-danger);padding:4px 12px}
/* The app's global form rules (input:not([type=radio]):not([type=checkbox]) {height;padding;border;background})
   outrank single-class selectors; these win on specificity so panel controls follow the theme tokens. */
.dp .dp-nf input.dp-in,.dp-pop .dp-nf input.dp-in{height:22px;padding:0 6px 0 2px;border:0;border-radius:0;background:transparent;color:inherit;box-shadow:none;min-width:0}
.dp .dp-nf input.dp-in:focus,.dp-pop .dp-nf input.dp-in:focus{border:0;box-shadow:none}
.dp.dp select.dp-sel,.dp-pop.dp-pop select.dp-sel{height:24px;border:1px solid transparent;background-color:var(--dp-field);color:var(--dp-text);box-shadow:none}
.dp.dp select.dp-sel:focus,.dp-pop.dp-pop select.dp-sel:focus{border-color:var(--dp-accent);box-shadow:none}
.dp select.dp-sel option,.dp-pop select.dp-sel option{background:var(--dp-panel);color:var(--dp-text)}
.dp.dp textarea.dp-ta{height:auto;border:1px solid transparent;background:var(--dp-field);color:var(--dp-text);box-shadow:none}
.dp.dp textarea.dp-ta:focus{border-color:var(--dp-accent)}
.dp-pop.dp-pop input[type=search].dp-in{color:var(--dp-text)}
.dp-pop.dp-pop input[type=search].dp-in:focus{border-color:var(--dp-accent)!important;box-shadow:none}
.dp .dp-ib,.dp-pop .dp-ib{color:var(--dp-text)}
.dp.dp input[type=range].dp-range,.dp-pop.dp-pop input[type=range].dp-range{height:16px;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
`;
function injectStyle() {
  if (document.getElementById('dp-style')) return;
  const s = document.createElement('style');
  s.id = 'dp-style';
  s.textContent = CSS;
  document.head.append(s);
}

/* ───────────────────────── 공용 위젯 ───────────────────────── */
function iconBtn(icon, title, onclick, o = {}) {
  const b = h('button', { class: 'dp-ib' + (o.on ? ' dp-on' : '') + (o.cls ? ' ' + o.cls : ''), type: 'button', title, 'aria-label': title, disabled: o.disabled, onclick: (e) => { e.stopPropagation(); onclick && onclick(e, b); } }, ic(icon));
  if (o.popkey) b.dataset.popkey = o.popkey;
  return b;
}
function section(title, o, ...body) {
  o = o || {};
  const sh = h('div', { class: 'dp-sh' }, h('span', { class: 'dp-grow' }, title, o.sub ? h('span', { class: 'dp-sub' }, o.sub) : null), ...(o.actions || []));
  const kids = body.flat(Infinity).filter(Boolean);
  return h('section', { class: 'dp-sec ' + (o.cls || '') }, sh, kids.length ? h('div', { class: 'dp-body' }, kids) : null);
}
const row = (...k) => h('div', { class: 'dp-row' }, ...k);

/* 숫자 입력: 수식, ↑↓, 라벨 스크럽, 혼합 표시, Enter/blur 커밋, Esc 복원
   o: {nodes|local, cur(n), put(n, stored)→partial|null, label(커밋 라벨), text|icon(라벨), scale, dec, min, max, step,
       raw(fmt/parse/nudge 사용), optional, scrub:false, intercept(stored, final)→true}  */
function numField(o) {
  const targets = o.local ? [0] : o.nodes;
  const scale = o.scale || 1, dec = o.dec ?? 2, min = o.min ?? -Infinity, max = o.max ?? Infinity;
  const live = () => (o.optional || o.local ? targets : targets.filter((n) => o.cur(n) !== undefined));
  const curDisp = (n) => { const v = o.cur(n); return o.raw || v == null || v === MIXED ? v : v * scale; };
  const input = h('input', { class: 'dp-in', type: 'text', spellcheck: false, autocomplete: 'off', title: o.title || '' });
  const lab = o.text != null || o.icon ? h('span', { class: 'dp-nl' + (o.scrub === false ? ' dp-nowide' : '') + (typeof o.text === 'string' && o.text.length > 1 ? ' dp-nlw' : ''), title: o.title || '' }, o.icon ? ic(o.icon) : o.text) : null;
  const wrap = h('label', { class: 'dp-nf' + (lab ? '' : ' dp-nolab') + (o.cls ? ' ' + o.cls : '') }, lab, input, o.suffix ? h('span', { class: 'dp-sfx' }, o.suffix) : null);
  let dirty = false, justFocus = false;

  function show() {
    const ns = live();
    input.disabled = !ns.length || !!o.disabled;
    if (!ns.length) { input.value = ''; input.placeholder = o.ph || ''; return; }
    const vs = ns.map(curDisp);
    if (vs.some((v) => v === MIXED) || !allSame(vs)) { input.value = ''; input.placeholder = '혼합'; }
    else { input.value = vs[0] == null ? '' : o.fmt ? o.fmt(vs[0]) : fmtNum(vs[0], dec); input.placeholder = o.ph || ''; }
  }
  const valueFn = (spec, bases) => (n) => {
    let d;
    if ('abs' in spec) d = spec.abs;
    else { const b = bases ? bases.get(n) : curDisp(n); if (b == null || b === MIXED) return undefined; d = o.raw ? (o.nudge ? o.nudge(b, spec.delta) : b) : b + spec.delta; }
    if (!o.raw && d != null) d = round(clamp(d, min, max), dec);
    return d == null ? null : o.raw ? d : d / scale;
  };
  async function apply(spec, final, bases, sess) {
    const ns = live(); if (!ns.length) return;
    const vf = valueFn(spec, bases);
    if (o.intercept && o.intercept(vf(ns[0]), final)) return;
    if (o.local) { const v = vf(0); if (v !== undefined) (final ? o.local.commit : o.local.preview)(v); return; }
    if (final && o.finalOps) { const ops = o.finalOps(ns, vf); if (ops && ops.length) { await commitOps(ops, o.label); sess && sess.cancel(); return; } }
    const build = (n) => { const v = vf(n); return v === undefined ? null : o.put(n, v); };
    if (final) await (sess || session(ns)).commit(build, o.label);
    else sess.preview(build);
  }
  const invalid = (v) => v === undefined || (typeof v === 'number' && Number.isNaN(v));
  function parseText() {
    const t = input.value.trim(), first = live()[0], base = first === undefined ? 0 : curDisp(first);
    if (o.parse) return o.parse(t, base);
    return calcExpr(t, typeof base === 'number' ? base : 0);
  }
  async function commitText() {
    const t = input.value.trim(); dirty = false;
    if (t === '') { if (o.optional && live().some((n) => o.cur(n) != null)) await apply({ abs: null }, true); show(); return; }
    const v = parseText();
    if (invalid(v)) { show(); return; }
    await apply({ abs: v }, true); show();
  }
  input.addEventListener('input', () => { dirty = true; });
  input.addEventListener('focus', () => { justFocus = true; input.select(); });
  input.addEventListener('mouseup', (e) => { if (justFocus) { e.preventDefault(); justFocus = false; } });
  input.addEventListener('blur', () => { justFocus = false; if (dirty) commitText(); });
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); commitText().then(() => input.select()); }
    else if (e.key === 'Escape') { dirty = false; show(); input.blur(); }
    else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const d = (e.key === 'ArrowUp' ? 1 : -1) * (o.step || 1) * (e.shiftKey ? 10 : e.altKey ? 0.1 : 1);
      if (dirty) { const v = parseText(); dirty = false; if (!invalid(v) && typeof v === 'number') apply({ abs: v + d }, true).then(show); else show(); }
      else apply({ delta: d }, true).then(show);
    }
  });

  // 라벨 드래그 스크럽: 미리보기 → 포인터 업에서 1회 커밋 (⇧ ×10, ⌥ ×0.1)
  if (lab && o.scrub !== false) {
    lab.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || input.disabled || o.raw) return;
      e.preventDefault();
      const ns = live(), sess = o.local ? null : session(ns);
      const bases = new Map(ns.map((n) => [n, curDisp(n)]));
      let total = 0, moved = 0, lastX = e.clientX, done = false;
      beginBusy();
      try { lab.setPointerCapture(e.pointerId); } catch (err) { /* 무시 */ }
      try { const r = lab.requestPointerLock && lab.requestPointerLock(); if (r && r.catch) r.catch(() => {}); } catch (err) { /* 무시 */ }
      const move = (ev) => {
        const locked = document.pointerLockElement === lab;
        const dx = locked ? ev.movementX : ev.clientX - lastX; lastX = ev.clientX;
        moved += Math.abs(dx);
        total += dx * (o.step || 1) * (ev.shiftKey ? 10 : ev.altKey ? 0.1 : 1);
        if (moved < 2) return;
        apply({ delta: total }, false, bases, sess);
        const f = ns[0]; const b = bases.get(f);
        if (typeof b === 'number' && allSame([...bases.values()])) input.value = fmtNum(clamp(b + total, min, max), dec);
      };
      const end = (ev, cancel) => {
        if (done) return; done = true;
        lab.removeEventListener('pointermove', move); lab.removeEventListener('pointerup', up); lab.removeEventListener('pointercancel', cx);
        window.removeEventListener('keydown', esc, true);
        try { if (document.pointerLockElement === lab) document.exitPointerLock(); } catch (err) { /* 무시 */ }
        const fin = async () => {
          if (moved >= 2 && !cancel) await apply({ delta: total }, true, bases, sess);
          else { sess && sess.cancel(); if (o.local && cancel) o.local.cancel && o.local.cancel(); }
          show(); endBusy();
          if (moved < 2 && !cancel) input.focus();
        };
        fin();
      };
      const up = (ev) => end(ev, false), cx = (ev) => end(ev, true);
      const esc = (ev) => { if (ev.key === 'Escape') { ev.stopPropagation(); end(ev, true); } };
      lab.addEventListener('pointermove', move); lab.addEventListener('pointerup', up); lab.addEventListener('pointercancel', cx);
      window.addEventListener('keydown', esc, true);
    });
  }
  refreshers.push(() => { if (!dirty && document.activeElement !== input) show(); });
  show();
  wrap.input = input; wrap.show = show;
  return wrap;
}

/* 드롭다운. options: [value,label] | 'sep' */
function fillOptions(sel, options) {
  sel.append(h('option', { value: MIXED, disabled: true, hidden: true }, '혼합'));
  for (const op of options) {
    if (op === 'sep') sel.append(document.createElement('hr'));
    else sel.append(h('option', { value: op[0], disabled: op[2] === 'disabled' }, op[1]));
  }
}
function selField(o) {
  const sel = h('select', { class: 'dp-sel', title: o.title || '' });
  fillOptions(sel, o.options);
  const live = () => o.nodes.filter((n) => o.cur(n) !== undefined);
  function show() {
    const ns = live(); sel.disabled = !ns.length || !!o.disabled;
    const vs = ns.map(o.cur);
    if (!vs.length) { sel.selectedIndex = -1; return; }
    if (vs.includes(MIXED) || !allSame(vs)) sel.value = MIXED;
    else { sel.value = vs[0]; if (sel.value !== String(vs[0])) sel.selectedIndex = -1; }
  }
  sel.addEventListener('keydown', (e) => e.stopPropagation());
  sel.addEventListener('change', async () => {
    const v = sel.value, ns = live();
    if (v === MIXED) return;
    if (o.intercept && o.intercept(v)) { show(); return; }
    await commitNodes(ns, (n) => o.put(n, v), o.label);
    show();
  });
  refreshers.push(show); show();
  if (o.text || o.icon) { if (o.text) sel.style.paddingLeft = 12 + String(o.text).length * 11 + 'px'; return h('div', { class: 'dp-sf' + (o.cls ? ' ' + o.cls : '') }, h('span', { class: 'dp-sfl' }, o.icon ? ic(o.icon) : o.text), sel); }
  return sel;
}

function chk(o) {
  const live = () => o.nodes.filter((n) => o.cur(n) !== undefined);
  const inp = h('input', { type: 'checkbox' });
  function show() {
    const vs = live().map(o.cur); inp.disabled = !vs.length;
    inp.indeterminate = vs.length > 0 && !allSame(vs); inp.checked = !inp.indeterminate && !!vs[0];
  }
  inp.addEventListener('change', async () => {
    const v = inp.checked, ns = live();
    if (o.intercept && o.intercept(v)) return;
    await commitNodes(ns, (n) => o.put(n, v), o.label); show();
  });
  refreshers.push(show); show();
  return h('label', { class: 'dp-chk', title: o.title || '' }, inp, o.text);
}

/* 아이콘 세그먼트. items: [{v, icon, title}] */
function seg(o) {
  const live = () => o.nodes.filter((n) => o.cur(n) !== undefined);
  const btns = o.items.map((it) => iconBtn(it.icon, it.title, async () => {
    if (o.intercept && o.intercept(it.v)) { show(); return; }
    await commitNodes(live(), (n) => o.put(n, it.v), o.label); show();
  }));
  const el = h('div', { class: 'dp-seg' + (o.cls ? ' ' + o.cls : ''), role: 'group' }, btns);
  function show() {
    const vs = live().map(o.cur), same = vs.length && allSame(vs) && vs[0] !== MIXED;
    o.items.forEach((it, i) => { btns[i].classList.toggle('dp-on', !!same && eq(vs[0], it.v)); btns[i].setAttribute('aria-pressed', !!same && eq(vs[0], it.v)); btns[i].disabled = !vs.length; });
  }
  refreshers.push(show); show();
  return el;
}

/* 슬라이더 (input → 미리보기, change → 커밋 1회) */
function slider(o) {
  const scale = o.scale || 1;
  const live = () => o.nodes.filter((n) => o.cur(n) !== undefined);
  const r = h('input', { class: 'dp-range', type: 'range', min: o.min, max: o.max, step: o.step || 1, title: o.title || '' });
  let sess = null, held = false;
  const stored = () => parseFloat(r.value) / scale;
  function show() { const vs = live().map(o.cur); r.disabled = !vs.length; if (vs.length && allSame(vs) && typeof vs[0] === 'number') r.value = vs[0] * scale; else if (vs.length) r.value = o.mixedAt ?? o.min; }
  const release = () => { if (held) { held = false; endBusy(); } };
  r.addEventListener('pointerdown', () => { if (held) return; held = true; beginBusy(); window.addEventListener('pointerup', release, { once: true }); });
  r.addEventListener('pointercancel', release);
  r.addEventListener('input', () => {
    const v = stored();
    if (o.intercept && o.intercept(v, false)) return;
    sess = sess || session(live()); sess.preview((n) => o.put(n, v));
    if (o.onInput) o.onInput(v);
  });
  r.addEventListener('change', async () => {
    const v = stored();
    if (o.intercept && o.intercept(v, true)) return;
    const s = sess || session(live()); sess = null;
    await s.commit((n) => o.put(n, v), o.label); show();
  });
  r.addEventListener('keydown', (e) => e.stopPropagation());
  refreshers.push(() => { if (!held) show(); });
  show();
  return r;
}

/* ───────────────────────── 팝오버 ───────────────────────── */
function closePop() { if (pop) { const p = pop; pop = null; p.close(); } }
function openPop(anchor, title, build, o = {}) {
  closePop();
  const key = o.key || '';
  const el = h('div', { class: 'dp-pop', role: 'dialog', 'aria-label': title });
  const titleEl = h('span', { class: 'dp-grow' }, title);
  const body = h('div', { class: 'dp-pb' });
  el.append(h('div', { class: 'dp-ph' }, titleEl, iconBtn('close', '닫기', () => closePop())), body);
  document.body.append(el);
  const ar = anchor.getBoundingClientRect(), pr = (root || anchor).getBoundingClientRect();
  const y0 = ar.top;
  const api = {
    el, body, key, refs: [],
    // 팝오버 내부 필드의 refresher를 패널과 분리해 모은다
    run(fn) { const saved = refreshers; refreshers = api.refs = []; try { fn(); } finally { refreshers = saved; } },
    refresh() { api.refs.forEach((r) => r()); },
    setTitle(t) { titleEl.textContent = t; },
    reposition() {
      let left = pr.left - el.offsetWidth - 8;
      if (left < 8) left = Math.min(pr.right + 8, innerWidth - el.offsetWidth - 8);
      el.style.left = Math.max(8, left) + 'px';
      el.style.top = clamp(y0 - 40, 8, Math.max(8, innerHeight - el.offsetHeight - 8)) + 'px';
    },
    close() {
      document.removeEventListener('pointerdown', onDown, true); document.removeEventListener('keydown', onKey, true);
      el.remove(); o.onClose && o.onClose();
    },
  };
  const onDown = (e) => {
    if (el.contains(e.target) || e.target.closest('.dp-pop')) return;
    if (key && e.target.closest && e.target.closest(`[data-popkey="${key}"]`)) return;
    closePop();
  };
  const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); closePop(); } };
  document.addEventListener('pointerdown', onDown, true); document.addEventListener('keydown', onKey, true);
  pop = api;
  api.run(() => build(api));
  api.reposition();
  return api;
}
const popIsOpen = (key) => !!(pop && pop.key === key);

/* ───────────────────────── 색 선택기 (SV 사각형 / 색조 / 알파 / HEX / 스포이트) ───────────────────────── */
function dragArea(el, fn, onEnd) {
  el.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try { el.setPointerCapture(e.pointerId); } catch (err) { /* 무시 */ }
    beginBusy();
    const at = (ev) => { const r = el.getBoundingClientRect(); fn(clamp((ev.clientX - r.left) / (r.width || 1), 0, 1), clamp((ev.clientY - r.top) / (r.height || 1), 0, 1), false); };
    at(e);
    const mv = (ev) => at(ev);
    const up = () => { el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); fn(null, null, true); endBusy(); onEnd && onEnd(); };
    el.addEventListener('pointermove', mv); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
  });
}
function colorPicker(init, onChange) {
  let c = parseHex(init) || { r: 0, g: 0, b: 0, a: 1 };
  let [hh, ss, vv] = rgb2hsv(c.r, c.g, c.b);
  const svKnob = h('i', { class: 'dp-knob' }), hueKnob = h('i', { class: 'dp-knob' }), alKnob = h('i', { class: 'dp-knob' });
  const sv = h('div', { class: 'dp-sv', title: '채도/명도' }, svKnob);
  const hue = h('div', { class: 'dp-bar dp-hue', title: '색조' }, hueKnob);
  const alG = h('i');
  const al = h('div', { class: 'dp-bar dp-alpha', title: '투명도' }, alG, alKnob);
  const hexIn = h('input', { class: 'dp-in', type: 'text', spellcheck: false, 'aria-label': 'HEX', maxLength: 9 });
  const alIn = h('input', { class: 'dp-in', type: 'text', spellcheck: false, 'aria-label': '불투명도 %' });
  const rgb = () => hsv2rgb(hh, ss, vv);
  const cur = () => toHex({ ...rgb(), a: c.a });
  function paint() {
    const { r, g, b } = rgb();
    sv.style.backgroundColor = `hsl(${hh} 100% 50%)`;
    svKnob.style.left = ss * 100 + '%'; svKnob.style.top = (1 - vv) * 100 + '%';
    hueKnob.style.left = (hh / 360) * 100 + '%'; hueKnob.style.background = `hsl(${hh} 100% 50%)`;
    alG.style.background = `linear-gradient(90deg, rgba(${r | 0},${g | 0},${b | 0},0), rgb(${r | 0},${g | 0},${b | 0}))`;
    alKnob.style.left = c.a * 100 + '%';
    if (document.activeElement !== hexIn) hexIn.value = (hex2(r) + hex2(g) + hex2(b));
    if (document.activeElement !== alIn) alIn.value = fmtNum(c.a * 100, 0) + '%';
  }
  const emit = (final) => onChange(cur(), final);
  dragArea(sv, (x, y, fin) => { if (fin) return emit(true); ss = x; vv = 1 - y; paint(); emit(false); });
  dragArea(hue, (x, y, fin) => { if (fin) return emit(true); hh = Math.min(359.99, x * 360); paint(); emit(false); });
  dragArea(al, (x, y, fin) => { if (fin) return emit(true); c = { ...c, a: round(x, 3) }; paint(); emit(false); });
  const setRgb = (p, keepA) => { c = { ...p, a: keepA ? c.a : p.a }; [hh, ss, vv] = rgb2hsv(p.r, p.g, p.b); };
  hexIn.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') { e.preventDefault(); hexIn.blur(); } else if (e.key === 'Escape') { hexIn.value = ''; paint(); hexIn.blur(); } });
  hexIn.addEventListener('focus', () => hexIn.select());
  hexIn.addEventListener('blur', () => {
    const raw = hexIn.value.replace('#', '').trim();
    const p = raw ? parseHex(raw) : null;
    if (p) { const had8 = raw.length === 8 || raw.length === 4; setRgb(p, !had8); paint(); emit(true); } else paint();
  });
  alIn.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') { e.preventDefault(); alIn.blur(); } else if (e.key === 'Escape') { alIn.value = ''; paint(); alIn.blur(); } });
  alIn.addEventListener('focus', () => alIn.select());
  alIn.addEventListener('blur', () => {
    const v = calcExpr(alIn.value, c.a * 100);
    if (Number.isFinite(v)) { c = { ...c, a: clamp(v, 0, 100) / 100 }; paint(); emit(true); } else paint();
  });
  const dropBtn = window.EyeDropper
    ? iconBtn('dropper', '스포이트', async () => {
      try { const r = await new window.EyeDropper().open(); const p = parseHex(r.sRGBHex); if (p) { setRgb(p, true); paint(); emit(true); } } catch (e) { /* 취소 */ }
    })
    : null;
  const el = h('div', { class: 'dp-cp' }, sv, row(dropBtn, h('div', { style: { flex: 1, display: 'flex', flexDirection: 'column', gap: '6px', minWidth: 0 } }, hue, al)),
    h('div', { class: 'dp-g2' }, h('label', { class: 'dp-nf' }, h('span', { class: 'dp-nl dp-nowide' }, '#'), hexIn), h('label', { class: 'dp-nf' }, h('span', { class: 'dp-nl dp-nowide', title: '불투명도' }, 'α'), alIn)));
  paint();
  return {
    el,
    set(color) {
      const p = parseHex(color); if (!p) return;
      const now = rgb();
      if (Math.round(now.r) === p.r && Math.round(now.g) === p.g && Math.round(now.b) === p.b) c = { ...c, a: p.a };
      else { c = p; [hh, ss, vv] = rgb2hsv(p.r, p.g, p.b); }
      paint();
    },
  };
}

/* ───────────────────────── 칠(Paint) 공용 ───────────────────────── */
const PAINT_NAMES = { SOLID: '단색', LINEAR: '선형', RADIAL: '원형', ANGULAR: '각도형', DIAMOND: '다이아몬드', IMAGE: '이미지' };
const PAINT_FULL = { SOLID: '단색', LINEAR: '선형 그라디언트', RADIAL: '원형 그라디언트', ANGULAR: '각도형 그라디언트', DIAMOND: '다이아몬드 그라디언트', IMAGE: '이미지' };
const IMG_MODES = [['FILL', '채우기'], ['FIT', '맞춤'], ['CROP', '자르기'], ['TILE', '바둑판식']];
const FILTERS = [['exposure', '노출'], ['contrast', '대비'], ['saturation', '채도'], ['temperature', '색온도'], ['tint', '색조'], ['highlights', '밝은 영역'], ['shadows', '어두운 영역']];
const GRAD = ['LINEAR', 'RADIAL', 'ANGULAR', 'DIAMOND'];
const LBLS = {
  fills: { add: '채우기 추가', del: '채우기 삭제', color: '채우기 색 변경', type: '칠 종류 변경', img: '이미지 칠 변경', vis: '채우기 표시 전환', order: '채우기 순서 변경', op: '채우기 불투명도 변경', blend: '채우기 혼합 모드 변경', unify: '채우기 통일', grad: '그라디언트 변경' },
  strokes: { add: '획 추가', del: '획 삭제', color: '획 색 변경', type: '획 종류 변경', img: '획 이미지 변경', vis: '획 표시 전환', order: '획 순서 변경', op: '획 불투명도 변경', blend: '획 혼합 모드 변경', unify: '획 통일', grad: '획 그라디언트 변경' },
};
const BLEND_LABELS = {
  PASS_THROUGH: '통과 (Pass through)', NORMAL: '표준 (Normal)', DARKEN: '어둡게 (Darken)', MULTIPLY: '곱하기 (Multiply)', LINEAR_BURN: '선형 번 (Plus darker)', COLOR_BURN: '색상 번 (Color burn)',
  LIGHTEN: '밝게 (Lighten)', SCREEN: '스크린 (Screen)', LINEAR_DODGE: '선형 닷지 (Plus lighter)', COLOR_DODGE: '색상 닷지 (Color dodge)', OVERLAY: '오버레이 (Overlay)', SOFT_LIGHT: '소프트 라이트 (Soft light)',
  HARD_LIGHT: '하드 라이트 (Hard light)', DIFFERENCE: '차이 (Difference)', EXCLUSION: '제외 (Exclusion)', HUE: '색조 (Hue)', SATURATION: '채도 (Saturation)', COLOR: '색상 (Color)', LUMINOSITY: '광도 (Luminosity)',
};
// 패리티 문서 §4.3 그룹 구분선: PASS_THROUGH/NORMAL | 어둡게 그룹 | 밝게 그룹 | 오버레이 그룹 | 차이 그룹 | 색조 그룹
const BLEND_BREAK = new Set(['DARKEN', 'LIGHTEN', 'OVERLAY', 'DIFFERENCE', 'HUE']);
function blendOptions(withPass) {
  const out = [];
  for (const b of SCHEMA.enums.blend) {
    if (b === 'PASS_THROUGH' && !withPass) continue;
    if (BLEND_BREAK.has(b)) out.push('sep');
    out.push([b, BLEND_LABELS[b] || b]);
  }
  return out;
}
const hashOk = (s) => /^[0-9a-f]{64}$/i.test(s || '');
const assetSrc = (hash) => (!hashOk(hash) ? '' : ctx.assetUrl ? ctx.assetUrl(hash) : '/assets/' + hash);
const sortedStops = (st) => [...st].sort((a, b) => a.p - b.p);
const stopCss = (st) => sortedStops(st).map((s) => `${s.color} ${round(s.p * 100, 2)}%`).join(',');
function paintCss(p) {
  if (!p) return '';
  switch (p.type) {
    case 'SOLID': return p.color;
    case 'LINEAR': return `linear-gradient(${round((p.angle || 0) + 90, 2)}deg,${stopCss(p.stops)})`;
    case 'RADIAL': case 'DIAMOND': return `radial-gradient(ellipse ${round((p.rx ?? 0.5) * 100, 2)}% ${round((p.ry ?? 0.5) * 100, 2)}% at ${round((p.cx ?? 0.5) * 100, 2)}% ${round((p.cy ?? 0.5) * 100, 2)}%,${stopCss(p.stops)})`;
    case 'ANGULAR': return `conic-gradient(from ${round((p.angle || 0) + 90, 2)}deg at ${round((p.cx ?? 0.5) * 100, 2)}% ${round((p.cy ?? 0.5) * 100, 2)}%,${stopCss(p.stops)})`;
    case 'IMAGE': { const u = assetSrc(p.asset); return u ? `url("${u}") center/cover` : 'linear-gradient(135deg,#ddd,#bbb)'; }
    default: return '';
  }
}
function swatch(p, mixed) {
  const i = h('i');
  if (p) i.style.background = paintCss(p);
  return h('button', { class: 'dp-sw' + (mixed ? ' dp-mixed' : ''), type: 'button' }, mixed ? null : i);
}
function newPaint(color) { return { type: 'SOLID', color, opacity: 1, visible: true, blend: 'NORMAL' }; }
function convertPaint(p, type) {
  if (p.type === type) return p;
  const base = { type, visible: p.visible !== false, opacity: p.opacity ?? 1, blend: p.blend || 'NORMAL' };
  const isG = (t) => GRAD.includes(t);
  if (type === 'SOLID') return { ...base, color: isG(p.type) ? p.stops[0].color : p.color || '#D9D9D9FF' };
  if (isG(type)) {
    const c = p.color || '#D9D9D9FF';
    const g = { ...base, stops: isG(p.type) ? clone(p.stops) : [{ p: 0, color: c }, { p: 1, color: c.slice(0, 7) + '00' }] };
    if (type === 'LINEAR') g.angle = p.angle ?? 0;
    if (type === 'ANGULAR') { g.angle = p.angle ?? 0; g.cx = p.cx ?? 0.5; g.cy = p.cy ?? 0.5; }
    if (type === 'RADIAL' || type === 'DIAMOND') { g.cx = p.cx ?? 0.5; g.cy = p.cy ?? 0.5; g.rx = p.rx ?? 0.5; g.ry = p.ry ?? 0.5; }
    return g;
  }
  return { ...base, asset: '', mode: 'FILL', scale: 1, rotation: 0, crop: { x: 0, y: 0, w: 1, h: 1 }, filters: { exposure: 0, contrast: 0, saturation: 0, temperature: 0, tint: 0, highlights: 0, shadows: 0 } };
}
const paintsOf = (n, key) => P(n)[key] || [];
const setAt = (list, i, patch) => list.map((x, k) => (k === i ? { ...x, ...patch } : x));
// 노드 하나의 set props. 텍스트의 채우기는 run 개별 fill 을 지워 노드 전체가 바뀌게 한다.
function paintPut(n, key, list) {
  const out = { [key]: list };
  if (n.type === 'text' && key === 'fills') {
    const runs = P(n).runs;
    if (Array.isArray(runs) && runs.some((r) => r.fill)) out.runs = runs.map((r) => { if (!r.fill) return r; const { fill, ...rest } = r; return rest; });
  }
  return out;
}

/* ───────────────────────── 칠 팝오버 (색/그라디언트/이미지) ───────────────────────── */
function openPaintPop(anchor, nodes, key, idx, pk) {
  const L = LBLS[key];
  const live = () => nodes.filter((n) => paintsOf(n, key)[idx]);
  const fromStore = () => clone(paintsOf(nodes[0], key)[idx]);
  let cur = fromStore(), selStop = 0, ps = null, drag = 0, errMsg = '', picker = null;
  const buildFor = (p) => (n) => paintPut(n, key, paintsOf(n, key).map((x, k) => (k === idx ? p : x))); // 통째로 교체(병합 금지: 종류가 바뀌면 키가 달라짐)
  function change(p, final, label) {
    cur = p;
    if (p.type === 'IMAGE' && !hashOk(p.asset)) return;
    const edit = key === 'fills' && p.type === 'SOLID' ? activeEdit(nodes) : null;
    if (edit) { edit.applyStyle({ fill: p.color }); return; }
    if (final) { const s = ps || session(live()); ps = null; return s.commit(buildFor(p), label); }
    ps = ps || session(live()); ps.preview(buildFor(p));
  }
  openPop(anchor, key === 'fills' ? '채우기' : '획', (api) => {
    const body = api.body;
    const targetColor = () => (cur.type === 'SOLID' ? cur.color : cur.stops ? cur.stops[Math.min(selStop, cur.stops.length - 1)].color : '#000000FF');
    const setTarget = (c) => { cur = cur.type === 'SOLID' ? { ...cur, color: c } : { ...cur, stops: cur.stops.map((s, i) => (i === selStop ? { ...s, color: c } : s)) }; };
    const locf = (k, text, o = {}) => numField({
      local: { preview: (v) => change({ ...cur, [k]: v }, false), commit: (v) => change({ ...cur, [k]: v }, true, o.label || L.grad) },
      cur: () => cur[k], text, scale: o.scale || 1, dec: o.dec ?? 1, min: o.min ?? (o.scale === 100 ? 0 : undefined), max: o.max ?? (o.scale === 100 ? 100 : undefined), suffix: o.suffix, title: o.title,
    });

    function renderTabs() {
      return h('div', { class: 'dp-tabs', role: 'tablist' }, Object.keys(PAINT_NAMES).map((t) => {
        const b = h('button', { class: 'dp-tab' + (cur.type === t ? ' dp-on' : ''), type: 'button', title: PAINT_FULL[t], 'aria-label': PAINT_FULL[t], role: 'tab', onclick: () => setType(t) });
        const i = h('i'); i.style.background = t === 'IMAGE' ? 'linear-gradient(135deg,#9bd,#58a)' : paintCss(convertPaint({ ...cur, type: cur.type, stops: cur.stops, color: targetColor().slice(0, 7) + 'FF' }, t)) || '#888';
        if (t === 'SOLID') i.style.background = targetColor().slice(0, 7);
        b.append(i); return b;
      }));
    }
    function setType(t) {
      if (cur.type === t) return;
      const p = convertPaint(cur, t); selStop = 0;
      if (t === 'IMAGE' && !hashOk(p.asset)) { cur = p; render(); return; }
      change(p, true, L.type); render();
    }

    function gradEditor() {
      const bar = h('div', { class: 'dp-stopbar', tabindex: 0, title: '클릭하여 정지점 추가 · Delete 로 삭제', role: 'group', 'aria-label': '그라디언트 정지점' });
      const gbg = h('div', { class: 'dp-gbg' });
      bar.append(gbg);
      function draw() {
        gbg.style.background = `linear-gradient(90deg,${stopCss(cur.stops)})`;
        bar.querySelectorAll('.dp-stop').forEach((x) => x.remove());
        cur.stops.forEach((s, i) => {
          const b = h('button', { class: 'dp-stop' + (i === selStop ? ' dp-on' : ''), type: 'button', title: `정지점 ${round(s.p * 100, 1)}%`, 'aria-label': `정지점 ${i + 1}` }, h('i'));
          b.style.left = s.p * 100 + '%'; b.firstChild.style.background = s.color;
          b.addEventListener('pointerdown', (e) => {
            e.stopPropagation(); e.preventDefault(); selStop = i; bar.focus();
            try { b.setPointerCapture(e.pointerId); } catch (err) { /* 무시 */ }
            bar.querySelectorAll('.dp-stop').forEach((x, k) => x.classList.toggle('dp-on', k === i));
            picker && picker.set(cur.stops[i].color); drag++; beginBusy();
            const rect = bar.getBoundingClientRect(); let moved = false;
            const mv = (ev) => { moved = true; const p = round(clamp((ev.clientX - rect.left) / rect.width, 0, 1), 3); b.style.left = p * 100 + '%'; change({ ...cur, stops: cur.stops.map((x, k) => (k === i ? { ...x, p } : x)) }, false); gbg.style.background = `linear-gradient(90deg,${stopCss(cur.stops)})`; };
            const up = () => {
              b.removeEventListener('pointermove', mv); b.removeEventListener('pointerup', up); b.removeEventListener('pointercancel', up);
              drag--; endBusy();
              if (moved) { const s0 = cur.stops[i]; const st = sortedStops(cur.stops); selStop = st.indexOf(s0); change({ ...cur, stops: st }, true, L.grad); } else ps && ps.cancel();
              render();
            };
            b.addEventListener('pointermove', mv); b.addEventListener('pointerup', up); b.addEventListener('pointercancel', up);
          });
          bar.append(b);
        });
      }
      bar.addEventListener('pointerdown', (e) => {
        if (e.target !== bar && e.target !== gbg) return;
        const rect = bar.getBoundingClientRect(), p = round(clamp((e.clientX - rect.left) / rect.width, 0, 1), 3);
        const st = sortedStops(cur.stops); let color = st[0].color;
        for (let k = 0; k < st.length; k++) { if (p >= st[k].p) color = st[k].color; if (k < st.length - 1 && p >= st[k].p && p <= st[k + 1].p) { color = lerpColor(st[k].color, st[k + 1].color, (p - st[k].p) / ((st[k + 1].p - st[k].p) || 1)); break; } }
        const add = { p, color }; const next = sortedStops([...cur.stops, add]); selStop = next.indexOf(add);
        change({ ...cur, stops: next }, true, '그라디언트 정지점 추가'); render();
      });
      const removeStop = () => {
        if (cur.stops.length <= 2) return;
        const next = cur.stops.filter((s, i) => i !== selStop); selStop = Math.max(0, selStop - 1);
        change({ ...cur, stops: next }, true, '그라디언트 정지점 삭제'); render();
      };
      bar.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); removeStop(); } });
      draw();
      const stopRow = row(
        numField({
          local: { preview: (v) => change({ ...cur, stops: cur.stops.map((s, i) => (i === selStop ? { ...s, p: v } : s)) }, false), commit: (v) => { const s0 = { ...cur.stops[selStop], p: v }; const st = sortedStops(cur.stops.map((s, i) => (i === selStop ? s0 : s))); selStop = st.findIndex((s) => s.p === v && s.color === s0.color); change({ ...cur, stops: st }, true, L.grad); render(); } },
          cur: () => cur.stops[selStop].p, text: '위치', scale: 100, dec: 1, min: 0, max: 100, suffix: '%',
        }),
        iconBtn('flip', '정지점 뒤집기', () => { change({ ...cur, stops: sortedStops(cur.stops.map((s) => ({ ...s, p: round(1 - s.p, 3) }))) }, true, '그라디언트 뒤집기'); selStop = cur.stops.length - 1 - selStop; render(); }),
        iconBtn('rot90', '90° 회전', () => {
          if (cur.type === 'RADIAL' || cur.type === 'DIAMOND') change({ ...cur, rx: cur.ry ?? 0.5, ry: cur.rx ?? 0.5 }, true, '그라디언트 회전');
          else change({ ...cur, angle: ((cur.angle || 0) + 90) % 360 }, true, '그라디언트 회전');
          render();
        }),
        iconBtn('minus', '선택한 정지점 삭제', removeStop, { disabled: cur.stops.length <= 2 }),
      );
      return [bar, stopRow];
    }

    function colorPart() {
      picker = colorPicker(targetColor(), (c, final) => {
        setTarget(c);
        if (cur.stops) { const gb = body.querySelector('.dp-gbg'); if (gb) gb.style.background = `linear-gradient(90deg,${stopCss(cur.stops)})`; const sb = body.querySelectorAll('.dp-stop')[selStop]; if (sb) sb.firstChild.style.background = c; }
        change(cur, final, L.color);
      });
      return picker.el;
    }

    function gradParams() {
      const t = cur.type;
      if (t === 'LINEAR') return [row(locf('angle', '∠', { title: '각도', suffix: '°', dec: 1 }))];
      if (t === 'ANGULAR') return [h('div', { class: 'dp-g3' }, locf('angle', '∠', { title: '각도', suffix: '°' }), locf('cx', 'X', { scale: 100, suffix: '%', title: '중심 X' }), locf('cy', 'Y', { scale: 100, suffix: '%', title: '중심 Y' }))];
      return [h('div', { class: 'dp-g2' }, locf('cx', 'X', { scale: 100, suffix: '%', title: '중심 X' }), locf('cy', 'Y', { scale: 100, suffix: '%', title: '중심 Y' })),
        h('div', { class: 'dp-g2' }, locf('rx', 'W', { scale: 100, suffix: '%', title: '가로 반경', min: 0 }), locf('ry', 'H', { scale: 100, suffix: '%', title: '세로 반경', min: 0 }))];
    }

    async function upload(file) {
      if (!file) return;
      if (!/^image\//.test(file.type)) { errMsg = '이미지 파일만 올릴 수 있습니다'; render(); return; }
      errMsg = ''; const dz = body.querySelector('.dp-drop'); if (dz) dz.textContent = '업로드 중…';
      try {
        const r = await ctx.uploadAsset(file); const hash = r && (r.hash || r);
        if (!hashOk(hash)) throw new Error('해시 없음');
        change({ ...cur, asset: hash }, true, L.img);
      } catch (e) { console.warn('업로드 실패', e); errMsg = '업로드에 실패했습니다'; }
      render();
    }
    function imagePart() {
      const file = h('input', { type: 'file', accept: 'image/*', style: { display: 'none' }, onchange: () => upload(file.files[0]) });
      const dz = h('div', { class: 'dp-drop', tabindex: 0, role: 'button', 'aria-label': '이미지 업로드', ondragover: (e) => { e.preventDefault(); dz.classList.add('dp-over'); }, ondragleave: () => dz.classList.remove('dp-over'), ondrop: (e) => { e.preventDefault(); dz.classList.remove('dp-over'); upload(e.dataTransfer.files[0]); }, onclick: () => file.click(), onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); } } });
      if (hashOk(cur.asset)) { const im = h('img', { alt: '', draggable: false }); im.src = assetSrc(cur.asset); dz.append(im, h('span', {}, '클릭하거나 끌어다 놓아 교체')); }
      else dz.append(ic('plus'), h('span', {}, '이미지를 끌어다 놓거나 클릭하여 업로드'));
      const out = [dz, file]; if (errMsg) out.push(h('div', { class: 'dp-err' }, errMsg));
      if (!hashOk(cur.asset)) return out;
      const sel = h('select', { class: 'dp-sel' }); sel.append(...IMG_MODES.map(([v, l]) => h('option', { value: v }, l))); sel.value = cur.mode;
      sel.addEventListener('change', () => { change({ ...cur, mode: sel.value }, true, L.img); render(); });
      out.push(row(h('div', { style: { flex: 1, minWidth: 0 } }, sel), iconBtn('rot90', `90° 회전 (현재 ${cur.rotation || 0}°)`, () => { change({ ...cur, rotation: ((cur.rotation || 0) + 90) % 360 }, true, L.img); render(); })));
      if (cur.mode === 'TILE') out.push(row(numField({ local: { preview: (v) => change({ ...cur, scale: v }, false), commit: (v) => change({ ...cur, scale: v }, true, L.img) }, cur: () => cur.scale ?? 1, text: '배율', scale: 100, dec: 1, min: 1, max: 1000, suffix: '%' })));
      if (cur.mode === 'CROP') {
        const cf = (k, t) => numField({ local: { preview: (v) => change({ ...cur, crop: { ...cur.crop, [k]: v } }, false), commit: (v) => change({ ...cur, crop: { ...cur.crop, [k]: v } }, true, L.img) }, cur: () => (cur.crop || {})[k] ?? (k === 'w' || k === 'h' ? 1 : 0), text: t, scale: 100, dec: 1, min: 0, max: 100, suffix: '%' });
        out.push(h('div', { class: 'dp-g2' }, cf('x', 'X'), cf('y', 'Y')), h('div', { class: 'dp-g2' }, cf('w', 'W'), cf('h', 'H')));
      }
      out.push(h('div', { class: 'dp-cap' }, '이미지 조정'));
      for (const [k, name] of FILTERS) {
        const val = h('span', { class: 'dp-dim', style: { width: '28px', textAlign: 'right' } }, String(Math.round(((cur.filters || {})[k] || 0) * 100)));
        const r = h('input', { class: 'dp-range', type: 'range', min: -100, max: 100, step: 1, title: name, 'aria-label': name });
        r.value = Math.round(((cur.filters || {})[k] || 0) * 100);
        const mk = () => ({ ...cur, filters: { exposure: 0, contrast: 0, saturation: 0, temperature: 0, tint: 0, highlights: 0, shadows: 0, ...(cur.filters || {}), [k]: parseFloat(r.value) / 100 } });
        let held = false;
        const rel = () => { if (held) { held = false; drag--; endBusy(); } };
        r.addEventListener('pointerdown', () => { if (held) return; held = true; drag++; beginBusy(); window.addEventListener('pointerup', rel, { once: true }); });
        r.addEventListener('input', () => { val.textContent = r.value; change(mk(), false); });
        r.addEventListener('change', () => change(mk(), true, L.img));
        r.addEventListener('keydown', (e) => e.stopPropagation());
        out.push(row(h('span', { class: 'dp-lab' }, name), r, val));
      }
      return out;
    }

    function blendPart() {
      const sel = h('select', { class: 'dp-sel', title: '혼합 모드' }); sel.append(h('option', { value: MIXED, hidden: true, disabled: true }, '혼합'));
      for (const op of blendOptions(false)) sel.append(op === 'sep' ? document.createElement('hr') : h('option', { value: op[0] }, op[1]));
      sel.value = cur.blend || 'NORMAL';
      sel.addEventListener('change', () => { change({ ...cur, blend: sel.value }, true, L.blend); });
      return row(h('span', { class: 'dp-lab' }, '혼합'), sel);
    }

    function render() {
      api.run(() => {
        body.textContent = '';
        body.append(renderTabs());
        if (GRAD.includes(cur.type)) body.append(...gradEditor());
        if (cur.type === 'SOLID' || GRAD.includes(cur.type)) body.append(colorPart());
        if (GRAD.includes(cur.type)) body.append(...gradParams());
        if (cur.type === 'IMAGE') body.append(...imagePart());
        body.append(blendPart());
        api.setTitle((key === 'fills' ? '채우기 · ' : '획 · ') + PAINT_NAMES[cur.type]);
        api.reposition();
      });
    }
    api.refresh = () => {
      if (!live().length) { closePop(); return; }
      if (drag || busy || typing(api.el) || (cur.type === 'IMAGE' && !hashOk(cur.asset))) return;
      const s = fromStore(); if (eq(s, cur)) return;
      cur = s; selStop = Math.min(selStop, (cur.stops || [1]).length - 1); render();
    };
    render();
  }, { key: pk, onClose: () => { ps && ps.cancel(); } });
}
function togglePaintPop(anchor, nodes, key, idx) {
  const pk = key + idx;
  if (popIsOpen(pk)) { closePop(); return; }
  openPaintPop(anchor, nodes, key, idx, pk);
}

/* ───────────────────────── 칠 목록 섹션 (채우기 / 획) ───────────────────────── */
function paintSection(nodes, key, title, extra = []) {
  const L = LBLS[key];
  const lists = nodes.map((n) => paintsOf(n, key));
  const same = allSame(lists);
  const addBtn = iconBtn('plus', key === 'fills' ? '채우기 추가' : '획 추가', async () => {
    const mk = (n) => newPaint(key === 'fills' && n.type !== 'text' ? '#D9D9D9FF' : '#000000FF');
    await commitNodes(nodes, (n) => paintPut(n, key, same ? [...paintsOf(n, key), mk(n)] : [mk(n)]), L.add);
  });
  const body = [];
  if (!same) {
    body.push(h('div', { class: 'dp-mixrow', role: 'button', tabindex: 0, title: '클릭하여 첫 번째 선택 항목의 내용으로 통일', onclick: () => commitNodes(nodes, (n) => paintPut(n, key, clone(lists[0])), L.unify) }, '혼합 — 클릭하여 통일'));
  } else {
    const list = lists[0];
    const box = h('div', { class: 'dp-list' });
    for (let i = list.length - 1; i >= 0; i--) box.append(paintRow(nodes, key, i, list, box));
    body.push(box);
  }
  return section(title, { actions: [addBtn], cls: 'dp-' + key }, body, extra);
}
function paintRow(nodes, key, i, list, box) {
  const L = LBLS[key], p = list[i];
  const sw = swatch(p, false);
  sw.dataset.popkey = key + i; sw.title = '색상 편집'; sw.setAttribute('aria-label', (key === 'fills' ? '채우기' : '획') + ' 색상 편집');
  sw.addEventListener('click', () => togglePaintPop(sw, nodes, key, i));
  const at = (n) => paintsOf(n, key)[i];
  let mid;
  if (p.type === 'SOLID') {
    mid = numField({
      nodes, raw: true, scrub: false, cls: 'dp-hexf', title: 'HEX 색상',
      cur: (n) => at(n) && at(n).color, fmt: (c) => String(c).slice(1, 7), label: L.color,
      parse: (t, base) => { const q = parseHex(t.replace('#', '')); if (!q) return undefined; const cb = parseHex(base) || { a: 1 }; const hasA = /^#?([0-9a-f]{8}|[0-9a-f]{4})$/i.test(t); return toHex({ ...q, a: hasA ? q.a : cb.a }); },
      put: (n, v) => paintPut(n, key, setAt(paintsOf(n, key), i, { color: v })),
      intercept: (v, fin) => { const e = key === 'fills' && activeEdit(nodes); if (e) { e.applyStyle({ fill: v }); return true; } return false; },
    });
  } else {
    mid = h('div', { class: 'dp-ptype', title: PAINT_FULL[p.type], onclick: () => togglePaintPop(sw, nodes, key, i) }, PAINT_NAMES[p.type]);
  }
  const op = numField({ nodes, cur: (n) => at(n) && (at(n).opacity ?? 1), scale: 100, dec: 0, min: 0, max: 100, suffix: '%', cls: 'dp-op', title: '불투명도', label: L.op, put: (n, v) => paintPut(n, key, setAt(paintsOf(n, key), i, { opacity: v })) });
  const grip = h('span', { class: 'dp-grip', title: '끌어서 순서 변경' }, ic('drag'));
  const r = h('div', { class: 'dp-prow' + (p.visible === false ? ' dp-hid' : '') }, grip, sw, mid, op,
    iconBtn(p.visible === false ? 'eyeOff' : 'eye', p.visible === false ? '표시' : '숨기기', () => commitNodes(nodes, (n) => paintPut(n, key, setAt(paintsOf(n, key), i, { visible: p.visible === false })), L.vis)),
    iconBtn('minus', key === 'fills' ? '채우기 삭제' : '획 삭제', () => { if (popIsOpen(key + i)) closePop(); commitNodes(nodes, (n) => paintPut(n, key, paintsOf(n, key).filter((_, k) => k !== i)), L.del); }, { cls: 'dp-dng' }));
  dragReorder(grip, r, box, list.length - 1 - i, (toDisp) => {
    const to = list.length - 1 - toDisp;
    if (to === i) return;
    commitNodes(nodes, (n) => { const a = clone(paintsOf(n, key)); const [m] = a.splice(i, 1); a.splice(to, 0, m); return paintPut(n, key, a); }, L.order);
  });
  return r;
}
// 행 드래그 정렬: 표시 순서 인덱스(위→아래)로 콜백
function dragReorder(grip, rowEl, box, fromDisp, onDrop) {
  grip.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try { grip.setPointerCapture(e.pointerId); } catch (err) { /* 무시 */ }
    beginBusy(); rowEl.classList.add('dp-drag');
    const rows = [...box.children].filter((c) => c.classList.contains('dp-prow'));
    const line = h('div', { class: 'dp-dropline' }); box.append(line);
    let target = fromDisp;
    const mv = (ev) => {
      const br = box.getBoundingClientRect(); let t = 0;
      rows.forEach((rw) => { const rc = rw.getBoundingClientRect(); if (ev.clientY > rc.top + rc.height / 2) t = rows.indexOf(rw) + 1; });
      target = clamp(t > fromDisp ? t - 1 : t, 0, rows.length - 1);
      const rc = rows[Math.min(t, rows.length - 1)].getBoundingClientRect();
      line.style.top = (t >= rows.length ? rc.bottom : rc.top) - br.top - 1 + 'px';
    };
    const up = () => {
      grip.removeEventListener('pointermove', mv); grip.removeEventListener('pointerup', up); grip.removeEventListener('pointercancel', up);
      line.remove(); rowEl.classList.remove('dp-drag'); endBusy();
      if (target !== fromDisp) onDrop(target);
    };
    grip.addEventListener('pointermove', mv); grip.addEventListener('pointerup', up); grip.addEventListener('pointercancel', up);
  });
}

/* ───────────────────────── 효과 ───────────────────────── */
const EFX = [['DROP_SHADOW', '드롭 섀도'], ['INNER_SHADOW', '이너 섀도'], ['LAYER_BLUR', '레이어 블러'], ['BACKGROUND_BLUR', '배경 블러']];
const EFX_MAX = { DROP_SHADOW: 8, INNER_SHADOW: 8, LAYER_BLUR: 1, BACKGROUND_BLUR: 1 };
const isShadow = (t) => t === 'DROP_SHADOW' || t === 'INNER_SHADOW';
const effOf = (n) => P(n).effects || [];
function newEffect(type) {
  if (type === 'DROP_SHADOW') return { type, visible: true, color: '#00000040', x: 0, y: 4, blur: 4, spread: 0, blend: 'NORMAL', showBehind: false };
  if (type === 'INNER_SHADOW') return { type, visible: true, color: '#00000040', x: 0, y: 4, blur: 4, spread: 0, blend: 'NORMAL' };
  return { type, visible: true, radius: 4 };
}
function convertEffect(e, type) {
  if (e.type === type) return e;
  const out = newEffect(type);
  if (isShadow(type)) {
    if (isShadow(e.type)) Object.assign(out, e, { type });
    else out.blur = e.radius ?? 4;
    if (type === 'INNER_SHADOW') delete out.showBehind;
    else out.showBehind = !!out.showBehind;
  } else out.radius = isShadow(e.type) ? e.blur ?? 4 : e.radius ?? 4;
  out.visible = e.visible !== false;
  return out;
}
// 효과 하나를 패치 (null 값 키는 삭제)
function patchEffect(list, i, patch) {
  return list.map((e, k) => {
    if (k !== i) return e;
    const o = { ...e, ...patch };
    for (const [kk, v] of Object.entries(patch)) if (v === null) delete o[kk];
    return o;
  });
}

function effectsSection(nodes) {
  const lists = nodes.map(effOf), same = allSame(lists), list = lists[0];
  const count = (t) => (same ? list.filter((e) => e.type === t).length : 0);
  const nextType = EFX.map((x) => x[0]).find((t) => count(t) < EFX_MAX[t]);
  const addBtn = iconBtn('plus', '효과 추가', () => commitNodes(nodes, (n) => ({ effects: same ? [...effOf(n), newEffect(nextType)] : [newEffect(nextType)] }), '효과 추가'), { disabled: !nextType });
  const body = [];
  if (!same) body.push(h('div', { class: 'dp-mixrow', role: 'button', tabindex: 0, title: '클릭하여 첫 번째 선택 항목의 내용으로 통일', onclick: () => commitNodes(nodes, (n) => ({ effects: clone(lists[0]) }), '효과 통일') }, '혼합 — 클릭하여 통일'));
  else {
    const box = h('div', { class: 'dp-list' });
    list.forEach((e, i) => {
      const pk = 'eff' + i;
      const gear = iconBtn('gear', '효과 설정', () => (popIsOpen(pk) ? closePop() : openEffectPop(gear, nodes, i, pk)), { popkey: pk, on: popIsOpen(pk) });
      const opts = EFX.map(([t, l]) => [t, l, count(t) >= EFX_MAX[t] && t !== e.type ? 'disabled' : '']);
      const type = selField({ nodes, options: opts, cur: (n) => effOf(n)[i] && effOf(n)[i].type, put: (n, v) => ({ effects: effOf(n).map((x, k) => (k === i ? convertEffect(x, v) : x)) }), label: '효과 종류 변경', title: '효과 종류' });
      const grip = h('span', { class: 'dp-grip', title: '끌어서 순서 변경' }, ic('drag'));
      const r = h('div', { class: 'dp-prow' + (e.visible === false ? ' dp-hid' : '') }, grip,
        iconBtn(e.visible === false ? 'eyeOff' : 'eye', e.visible === false ? '표시' : '숨기기', () => commitNodes(nodes, (n) => ({ effects: patchEffect(effOf(n), i, { visible: e.visible === false }) }), '효과 표시 전환')),
        h('div', { style: { flex: 1, minWidth: 0 } }, type), gear,
        iconBtn('minus', '효과 삭제', () => { closePop(); commitNodes(nodes, (n) => ({ effects: effOf(n).filter((_, k) => k !== i) }), '효과 삭제'); }, { cls: 'dp-dng' }));
      dragReorder(grip, r, box, i, (to) => {
        closePop();
        commitNodes(nodes, (n) => { const a = clone(effOf(n)); const [m] = a.splice(i, 1); a.splice(to, 0, m); return { effects: a }; }, '효과 순서 변경');
      });
      box.append(r);
    });
    body.push(box);
  }
  return section('효과', { actions: [addBtn], cls: 'dp-effects' }, body);
}

function openEffectPop(anchor, nodes, i, pk) {
  const at = (n) => effOf(n)[i];
  const put = (n, patch) => ({ effects: patchEffect(effOf(n), i, patch) });
  const first = at(nodes[0]); if (!first) return;
  let es = null; // 색상 드래그 미리보기 세션
  openPop(anchor, '효과', (api) => {
    const body = api.body;
    let type = first.type, colorOpen = false, picker = null, shownColor = '';
    const ef = (k, text, o = {}) => numField({ nodes, cur: (n) => (at(n) ? at(n)[k] : undefined), put: (n, v) => put(n, { [k]: v }), text, label: '효과 변경', title: o.title, min: o.min, max: o.max, dec: o.dec ?? 1, suffix: o.suffix });
    const pr = (n) => (at(n) && at(n).progressive) || null;
    function colorRow() {
      const cur = () => at(nodes[0]).color; shownColor = cur();
      const sw = swatch({ type: 'SOLID', color: cur() }, false); sw.title = '색상';
      sw.addEventListener('click', () => { colorOpen = !colorOpen; render(); });
      const hex = numField({ nodes, raw: true, scrub: false, cur: (n) => at(n) && at(n).color, fmt: (c) => String(c).slice(1, 7), label: '효과 변경', title: 'HEX',
        parse: (t, base) => { const q = parseHex(t.replace('#', '')); if (!q) return undefined; const cb = parseHex(base) || { a: 1 }; return toHex({ ...q, a: /^#?([0-9a-f]{8}|[0-9a-f]{4})$/i.test(t) ? q.a : cb.a }); },
        put: (n, v) => put(n, { color: v }) });
      const out = [row(sw, hex, h('span', { class: 'dp-dim', style: { width: '40px', textAlign: 'right' } }, Math.round((parseHex(cur()).a) * 100) + '%'))];
      if (colorOpen) {
        picker = colorPicker(cur(), (c, fin) => {
          const build = (n) => put(n, { color: c });
          if (fin) { const s = es || session(nodes); es = null; s.commit(build, '효과 변경'); } else { es = es || session(nodes); es.preview(build); }
        });
        out.push(picker.el);
      }
      return out;
    }
    function render() {
      api.run(() => {
        body.textContent = ''; type = at(nodes[0]).type;
        api.setTitle(lbl(EFX, type));
        if (isShadow(type)) {
          body.append(h('div', { class: 'dp-g2' }, ef('x', 'X'), ef('y', 'Y')), h('div', { class: 'dp-g2' }, ef('blur', '블러', { min: 0, title: '블러' }), ef('spread', '퍼짐', { title: '퍼짐' })));
          body.append(...colorRow());
          body.append(row(h('span', { class: 'dp-lab' }, '혼합'), selField({ nodes, options: blendOptions(false), cur: (n) => (at(n) ? at(n).blend || 'NORMAL' : undefined), put: (n, v) => put(n, { blend: v }), label: '효과 변경', title: '혼합 모드' })));
          if (type === 'DROP_SHADOW') body.append(chk({ nodes, cur: (n) => (at(n) ? !!at(n).showBehind : undefined), put: (n, v) => put(n, { showBehind: v }), text: '투명 영역 뒤에도 표시', label: '효과 변경' }));
        } else {
          body.append(row(ef('radius', '반경', { min: 0, title: '반경' })));
          if (type === 'LAYER_BLUR') {
            body.append(chk({ nodes, cur: (n) => (at(n) ? !!pr(n) : undefined), put: (n, v) => put(n, { progressive: v ? { startRadius: 0, start: [0.5, 0], end: [0.5, 1] } : null }), text: '점진적 블러', label: '효과 변경' }));
            if (nodes.every((n) => at(n) && pr(n))) {
              const pf = (text, get, set, o = {}) => numField({ nodes, cur: (n) => (pr(n) ? get(pr(n)) : undefined), put: (n, v) => put(n, { progressive: set(pr(n), v) }), text, label: '효과 변경', scale: o.scale || 1, dec: 1, min: o.min, max: o.max, suffix: o.suffix, title: o.title });
              body.append(row(pf('시작 반경', (q) => q.startRadius, (q, v) => ({ ...q, startRadius: v }), { min: 0, title: '시작 반경' })),
                h('div', { class: 'dp-g2' }, pf('X', (q) => q.start[0], (q, v) => ({ ...q, start: [v, q.start[1]] }), { scale: 100, min: 0, max: 100, suffix: '%', title: '시작 X' }), pf('Y', (q) => q.start[1], (q, v) => ({ ...q, start: [q.start[0], v] }), { scale: 100, min: 0, max: 100, suffix: '%', title: '시작 Y' })),
                h('div', { class: 'dp-g2' }, pf('X', (q) => q.end[0], (q, v) => ({ ...q, end: [v, q.end[1]] }), { scale: 100, min: 0, max: 100, suffix: '%', title: '끝 X' }), pf('Y', (q) => q.end[1], (q, v) => ({ ...q, end: [q.end[0], v] }), { scale: 100, min: 0, max: 100, suffix: '%', title: '끝 Y' })));
            }
          }
        }
        api.reposition();
      });
    }
    api.refresh = () => {
      if (!nodes.every(at)) { closePop(); return; }
      if (busy || typing(api.el)) return;
      if (at(nodes[0]).type !== type || (isShadow(type) && at(nodes[0]).color !== shownColor)) render(); else api.refs.forEach((r) => r());
    };
    render();
  }, { key: pk, onClose: () => { es && es.cancel(); } });
}

/* ───────────────────────── 획 상세 (두께/위치/변별/스타일/끝/조인) ───────────────────────── */
const SIDES = [['t', '위'], ['r', '오'], ['b', '아'], ['l', '왼']];
const CAPS = [['NONE', '없음'], ['ROUND', '둥글게'], ['SQUARE', '사각형'], ['ARROW_LINES', '선 화살표'], ['ARROW_EQUILATERAL', '삼각형 화살표'], ['DIAMOND_FILLED', '다이아몬드'], ['TRIANGLE_FILLED', '삼각형'], ['CIRCLE_FILLED', '원']];
const strokeOf = (n) => P(n).stroke;
const putStroke = (n, patch) => ({ stroke: { ...strokeOf(n), ...patch } });
function dashKind(s) {
  const d = s.dash || [];
  if (!d.length) return 'SOLID';
  if (d.length === 2 && s.dashCap === 'ROUND' && d[0] <= 0.5) return 'DOT';
  if (d.length === 2) return 'DASH';
  return 'CUSTOM';
}
function sideMode(s) {
  if (!s.sides) return 'ALL';
  const nz = SIDES.filter(([k]) => s.sides[k] > 0);
  return nz.length === 1 ? nz[0][0] : 'CUSTOM';
}
function strokeExtras(nodes) {
  const L = '획 변경';
  const all = (f) => nodes.every(f);
  const isLine = all((n) => n.type === 'line');
  const rectLike = all((n) => n.type === 'rect' || n.type === 'frame' || n.type === 'page');
  const out = [];
  if (!isLine) out.push(row(h('span', { class: 'dp-lab' }, '위치'), selField({ nodes, options: [['INSIDE', '안쪽'], ['CENTER', '가운데'], ['OUTSIDE', '바깥쪽']], cur: (n) => strokeOf(n).align, put: (n, v) => putStroke(n, { align: v }), label: '획 위치 변경', title: '획 위치' })));
  // 두께 (+변별)
  const wCur = (n) => { const s = strokeOf(n), m = sideMode(s); return m === 'ALL' ? s.weight : m === 'CUSTOM' ? Math.max(0, ...SIDES.map(([k]) => s.sides[k] || 0)) : s.sides[m]; };
  const wPut = (n, v) => { const s = strokeOf(n), m = sideMode(s); if (m === 'ALL') return putStroke(n, { weight: v }); if (m === 'CUSTOM') return putStroke(n, { weight: v, sides: Object.fromEntries(SIDES.map(([k]) => [k, v])) }); return putStroke(n, { sides: { t: 0, r: 0, b: 0, l: 0, [m]: v }, weight: v }); };
  const weight = numField({ nodes, icon: 'baselineI', cur: wCur, put: wPut, label: '획 두께 변경', min: 0, dec: 2, title: '획 두께' });
  if (rectLike) {
    const modeSel = selField({
      nodes, options: [['ALL', '전체'], ['t', '위'], ['b', '아래'], ['l', '왼쪽'], ['r', '오른쪽'], ['CUSTOM', '사용자 지정']], title: '변별 두께',
      cur: (n) => sideMode(strokeOf(n)), label: '획 변별 두께 변경',
      put: (n, v) => {
        const s = strokeOf(n), w = wCur(n) || s.weight || 1;
        if (v === 'ALL') return putStroke(n, { sides: null, weight: w });
        if (v === 'CUSTOM') return putStroke(n, { sides: s.sides || Object.fromEntries(SIDES.map(([k]) => [k, w])) });
        return putStroke(n, { sides: { t: 0, r: 0, b: 0, l: 0, [v]: w }, weight: w });
      },
    });
    out.push(h('div', { class: 'dp-g2' }, weight, modeSel));
    if (nodes.every((n) => sideMode(strokeOf(n)) === 'CUSTOM')) {
      out.push(h('div', { class: 'dp-g4' }, SIDES.map(([k, t]) => numField({ nodes, text: t, title: { t: '위', r: '오른쪽', b: '아래', l: '왼쪽' }[k] + ' 두께', cur: (n) => (strokeOf(n).sides || {})[k], put: (n, v) => putStroke(n, { sides: { ...strokeOf(n).sides, [k]: v } }), label: '획 변별 두께 변경', min: 0, dec: 1 }))));
    }
  } else out.push(row(weight));
  // 스타일
  out.push(row(h('span', { class: 'dp-lab' }, '스타일'), selField({
    nodes, options: [['SOLID', '실선'], ['DASH', '대시'], ['DOT', '점선'], ['CUSTOM', '사용자 지정']], title: '획 스타일', label: '획 스타일 변경',
    cur: (n) => dashKind(strokeOf(n)),
    put: (n, v) => {
      const s = strokeOf(n), w = Math.max(1, s.weight || 1), d = s.dash || [];
      if (v === 'SOLID') return putStroke(n, { dash: [], dashCap: s.dashCap === 'ROUND' && dashKind(s) === 'DOT' ? 'NONE' : s.dashCap });
      if (v === 'DOT') return putStroke(n, { dash: [0.01, w * 2], dashCap: 'ROUND' });
      if (v === 'DASH') return putStroke(n, { dash: d.length >= 2 && d[0] > 0.5 ? [d[0], d[1]] : [w * 10, w * 10], dashCap: dashKind(s) === 'DOT' ? 'NONE' : s.dashCap });
      return putStroke(n, { dash: d.length ? d : [4, 2] });
    },
  })));
  const kinds = nodes.map((n) => dashKind(strokeOf(n)));
  if (allSame(kinds)) {
    const k = kinds[0];
    const df = (idx, text, title) => numField({ nodes, text, title, cur: (n) => (strokeOf(n).dash || [])[idx], put: (n, v) => { const d = [...(strokeOf(n).dash || [])]; d[idx] = v; return putStroke(n, { dash: d }); }, label: '획 스타일 변경', min: 0, dec: 2 });
    if (k === 'DASH') out.push(h('div', { class: 'dp-g2' }, df(0, '대시', '대시 길이'), df(1, '간격', '간격')));
    if (k === 'DOT') out.push(row(df(1, '간격', '간격')));
    if (k === 'CUSTOM') {
      out.push(row(numField({
        nodes, raw: true, scrub: false, text: '', title: '대시 패턴 (쉼표로 구분: 4,2,1,2)', ph: '4,2,1,2', label: '획 스타일 변경',
        cur: (n) => strokeOf(n).dash, fmt: (d) => d.join(','),
        parse: (t) => { const a = t.split(/[,\s]+/).filter(Boolean).map(Number); return a.length && a.length <= 16 && a.every((x) => Number.isFinite(x) && x >= 0) && a.reduce((s, x) => s + x, 0) > 0 ? a : undefined; },
        put: (n, v) => putStroke(n, { dash: v }),
      })));
    }
    if (k === 'DASH' || k === 'CUSTOM') out.push(row(h('span', { class: 'dp-lab' }, '대시 끝'), selField({ nodes, options: [['NONE', '없음'], ['ROUND', '둥글게'], ['SQUARE', '사각형']], cur: (n) => strokeOf(n).dashCap, put: (n, v) => putStroke(n, { dashCap: v }), label: '획 스타일 변경', title: '대시 끝 모양' })));
  }
  // 연결(조인)
  out.push(row(h('span', { class: 'dp-lab' }, '연결'), selField({ nodes, options: [['MITER', '마이터'], ['BEVEL', '베벨'], ['ROUND', '둥글게']], cur: (n) => strokeOf(n).join, put: (n, v) => putStroke(n, { join: v }), label: '획 연결 변경', title: '획 연결' })));
  if (nodes.every((n) => strokeOf(n).join === 'MITER')) out.push(row(numField({ nodes, text: '∠', title: '마이터 한계', cur: (n) => strokeOf(n).miterLimit, put: (n, v) => putStroke(n, { miterLimit: v }), label: '획 연결 변경', min: 1, dec: 2 })));
  // 끝 모양 (선/벡터)
  if (all((n) => n.type === 'line' || n.type === 'vector')) {
    const capSel = (k, title) => selField({ nodes, options: CAPS, cur: (n) => strokeOf(n)[k], put: (n, v) => putStroke(n, { [k]: v }), label: '획 끝 모양 변경', title });
    out.push(h('div', { class: 'dp-cap' }, '끝 모양'), h('div', { style: { display: 'grid', gridTemplateColumns: '1fr 24px 1fr', gap: '4px', alignItems: 'center' } }, capSel('capStart', '시작 끝 모양'),
      iconBtn('swap', '시작/끝 교환', () => commitNodes(nodes, (n) => putStroke(n, { capStart: strokeOf(n).capEnd, capEnd: strokeOf(n).capStart }), '획 끝 모양 교환')), capSel('capEnd', '끝 끝 모양')));
  }
  return out;
}

/* ───────────────────────── 레이아웃 가이드 ───────────────────────── */
const GUIDE_TYPES = [['GRID', '그리드'], ['COLUMNS', '열'], ['ROWS', '행']];
const GUIDE_ALIGN = [['MIN', '시작'], ['MAX', '끝'], ['STRETCH', '늘이기'], ['CENTER', '가운데']];
const guidesOf = (n) => P(n).guides || [];
function newGuide(type) {
  return type === 'GRID'
    ? { type, count: 0, size: 10, gutter: 0, margin: 0, offset: 0, align: 'STRETCH', color: '#FF000019', visible: true }
    : { type, count: 5, size: 100, gutter: 20, margin: 0, offset: 0, align: 'STRETCH', color: '#FF000019', visible: true };
}
function guidesSection(nodes) {
  const lists = nodes.map(guidesOf), same = allSame(lists), list = lists[0];
  const add = iconBtn('plus', '레이아웃 가이드 추가', () => commitNodes(nodes, (n) => ({ guides: same ? [...guidesOf(n), newGuide('GRID')] : [newGuide('GRID')] }), '가이드 추가'));
  const body = [];
  if (!same) body.push(h('div', { class: 'dp-mixrow', role: 'button', tabindex: 0, onclick: () => commitNodes(nodes, () => ({ guides: clone(lists[0]) }), '가이드 통일') }, '혼합 — 클릭하여 통일'));
  else {
    const box = h('div', { class: 'dp-list' });
    list.forEach((g, i) => {
      const pk = 'guide' + i;
      const gear = iconBtn('gear', '가이드 설정', () => (popIsOpen(pk) ? closePop() : openGuidePop(gear, nodes, i, pk)), { popkey: pk, on: popIsOpen(pk) });
      const type = selField({ nodes, options: GUIDE_TYPES, cur: (n) => guidesOf(n)[i] && guidesOf(n)[i].type, put: (n, v) => ({ guides: setAt(guidesOf(n), i, { ...newGuide(v), color: guidesOf(n)[i].color, visible: guidesOf(n)[i].visible }) }), label: '가이드 종류 변경', title: '가이드 종류' });
      box.append(h('div', { class: 'dp-prow' + (g.visible === false ? ' dp-hid' : '') },
        iconBtn(g.visible === false ? 'eyeOff' : 'eye', g.visible === false ? '표시' : '숨기기', () => commitNodes(nodes, (n) => ({ guides: setAt(guidesOf(n), i, { visible: g.visible === false }) }), '가이드 표시 전환')),
        h('div', { style: { flex: 1, minWidth: 0 } }, type), gear,
        iconBtn('minus', '가이드 삭제', () => { closePop(); commitNodes(nodes, (n) => ({ guides: guidesOf(n).filter((_, k) => k !== i) }), '가이드 삭제'); }, { cls: 'dp-dng' })));
    });
    body.push(box);
  }
  return section('레이아웃 가이드', { actions: [add], cls: 'dp-guides' }, body);
}
function openGuidePop(anchor, nodes, i, pk) {
  const at = (n) => guidesOf(n)[i];
  if (!nodes.every(at)) return;
  const put = (n, patch) => ({ guides: setAt(guidesOf(n), i, patch) });
  openPop(anchor, '레이아웃 가이드', (api) => {
    const body = api.body; let type = at(nodes[0]).type, colorOpen = false, gs = null;
    const gf = (k, text, o = {}) => numField({ nodes, cur: (n) => (at(n) ? at(n)[k] : undefined), put: (n, v) => put(n, { [k]: o.int ? Math.round(v) : v }), text, title: o.title, label: '가이드 변경', min: o.min, dec: o.int ? 0 : 2, ph: o.ph });
    function render() {
      api.run(() => {
        body.textContent = ''; type = at(nodes[0]).type; api.setTitle(lbl(GUIDE_TYPES, type));
        body.append(selField({ nodes, options: GUIDE_TYPES, cur: (n) => (at(n) ? at(n).type : undefined), put: (n, v) => put(n, { ...newGuide(v), color: at(n).color, visible: at(n).visible }), label: '가이드 종류 변경', title: '종류' }));
        if (type === 'GRID') body.append(row(gf('size', '크기', { min: 1, title: '셀 크기' })));
        else {
          body.append(h('div', { class: 'dp-g2' }, gf('count', '개수', { min: 0, int: true, title: '개수 (0 = 자동)', ph: '자동' }), gf('size', '너비', { min: 0, title: type === 'ROWS' ? '높이' : '너비' })),
            h('div', { class: 'dp-g2' }, gf('gutter', '간격', { min: 0, title: '간격' }), gf('margin', '여백', { title: '여백' })),
            h('div', { class: 'dp-g2' }, gf('offset', '오프셋', { title: '오프셋' }), selField({ nodes, options: GUIDE_ALIGN, cur: (n) => (at(n) ? at(n).align : undefined), put: (n, v) => put(n, { align: v }), label: '가이드 변경', title: '정렬' })),
            h('div', { class: 'dp-cap' }, '개수 0 = 자동'));
        }
        const cur = at(nodes[0]).color, sw = swatch({ type: 'SOLID', color: cur }, false);
        sw.addEventListener('click', () => { colorOpen = !colorOpen; render(); });
        body.append(row(sw, h('span', { class: 'dp-dim' }, '가이드 색상')));
        if (colorOpen) {
          body.append(colorPicker(cur, (c, fin) => {
            const build = (n) => put(n, { color: c });
            if (fin) { const s = gs || session(nodes); gs = null; s.commit(build, '가이드 변경'); } else { gs = gs || session(nodes); gs.preview(build); }
          }).el);
        }
        api.reposition();
      });
    }
    api.refresh = () => { if (!nodes.every(at)) { closePop(); return; } if (busy || typing(api.el)) return; if (at(nodes[0]).type !== type) render(); else api.refs.forEach((r) => r()); };
    render();
  }, { key: pk });
}

/* ───────────────────────── 섹션: 페이지 ───────────────────────── */
const PRESET_NAMES = { SLIDE_16_9: '프레젠테이션 16:9', SLIDE_4_3: '프레젠테이션 4:3', A3: 'A3', A4: 'A4', A5: 'A5', A6: 'A6', LETTER: '레터', LEGAL: '리걸', TABLOID: '타블로이드' };
function presetOptions() {
  const out = Object.entries(SCHEMA.presets).map(([k, [w, hh]]) => [k, `${PRESET_NAMES[k] || k} (${w}×${hh})`]);
  out.push(['CUSTOM', '사용자 지정']);
  return out;
}
function presetOf(p) {
  const d = SCHEMA.presets[p.preset];
  if (d && ((d[0] === p.w && d[1] === p.h) || (d[0] === p.h && d[1] === p.w))) return p.preset;
  return 'CUSTOM';
}
const orientOf = (w, hh) => (w >= hh ? 'landscape' : 'portrait');
// 페이지 크기 변경: layout.js resizeOps 로 자식 제약까지 반영 (+ preset/orientation)
function pageResize(pages, size, extra, label) {
  const ops = [];
  for (const n of pages) {
    const p = P(n), want = size(n, p), more = extra(n, p, want);
    let r = null;
    if (want && layoutMod && layoutMod.resizeOps && (want.w !== p.w || want.h !== p.h)) {
      try { r = layoutMod.resizeOps(store, n.id, { w: want.w, h: want.h }); } catch (e) { console.warn('resizeOps 실패', e); }
    }
    if (r && r.length) { r[0] = { ...r[0], props: { ...r[0].props, ...more } }; ops.push(...r); }
    else { const props = { ...(want ? { w: want.w, h: want.h } : {}), ...more }; if (Object.keys(props).length) ops.push({ op: 'set', id: n.id, props }); }
  }
  return commitOps(ops, label);
}
function secPage(pages) {
  const body = [];
  const dims = (axis) => numField({
    nodes: pages, text: axis.toUpperCase(), title: axis === 'w' ? '페이지 너비' : '페이지 높이', cur: (n) => P(n)[axis], min: 1, label: '페이지 크기 변경',
    put: (n, v) => { const p = P(n); const w = axis === 'w' ? v : p.w, hh = axis === 'h' ? v : p.h; return { [axis]: v, preset: 'CUSTOM', orientation: orientOf(w, hh) }; },
    finalOps: (list, vf) => {
      const ops = [];
      for (const n of list) {
        const v = vf(n); if (v == null) continue;
        const p = P(n), w = axis === 'w' ? v : p.w, hh = axis === 'h' ? v : p.h;
        let r = null;
        try { r = layoutMod && layoutMod.resizeOps ? layoutMod.resizeOps(store, n.id, { w, h: hh }) : null; } catch (e) { r = null; }
        const extra = { preset: 'CUSTOM', orientation: orientOf(w, hh) };
        if (r && r.length) { r[0] = { ...r[0], props: { ...r[0].props, ...extra } }; ops.push(...r); }
        else ops.push({ op: 'set', id: n.id, props: { w, h: hh, ...extra } });
      }
      return ops;
    },
  });
  body.push(selField({
    nodes: pages, options: presetOptions(), title: '페이지 크기 프리셋', label: '페이지 크기 변경', cur: (n) => presetOf(P(n)),
    put: (n, v) => ({ preset: v }),
    intercept: (v) => {
      if (v === 'CUSTOM') return false;
      const [a, b] = SCHEMA.presets[v];
      pageResize(pages, (n, p) => { const land = (p.orientation || 'landscape') === 'landscape'; return { w: land ? Math.max(a, b) : Math.min(a, b), h: land ? Math.min(a, b) : Math.max(a, b) }; }, () => ({ preset: v }), '페이지 크기 변경');
      return true;
    },
  }));
  body.push(row(seg({
    nodes: pages, label: '페이지 방향 변경', cls: 'dp-grow',
    items: [{ v: 'portrait', icon: 'portrait', title: '세로' }, { v: 'landscape', icon: 'landscape', title: '가로' }],
    cur: (n) => P(n).orientation || 'landscape',
    put: (n, v) => ({ orientation: v }),
    intercept: (v) => {
      pageResize(pages, (n, p) => (orientOf(p.w, p.h) !== v && p.w !== p.h ? { w: p.h, h: p.w } : null), () => ({ orientation: v }), '페이지 방향 변경');
      return true;
    },
  }), h('span', { class: 'dp-grow' })));
  body.push(h('div', { class: 'dp-g2' }, dims('w'), dims('h')));
  body.push(chk({ nodes: pages, cur: (n) => !!P(n).clip, put: (n, v) => ({ clip: v }), text: '내용 자르기', label: '내용 자르기 변경' }));
  // 발표자 노트
  const notes = pages.map((n) => P(n).notes || '');
  const ta = h('textarea', { class: 'dp-ta', placeholder: allSame(notes) ? '이 페이지의 발표자 노트' : '혼합', 'aria-label': '발표자 노트', rows: 4 });
  ta.value = allSame(notes) ? notes[0] : '';
  let touched = false;
  ta.addEventListener('input', () => { touched = true; });
  ta.addEventListener('keydown', (e) => e.stopPropagation());
  ta.addEventListener('blur', () => { if (touched) { touched = false; commitNodes(pages, () => ({ notes: ta.value }), '노트 변경'); } });
  refreshers.push(() => { if (document.activeElement !== ta && !touched) ta.value = allSame(pages.map((n) => P(n).notes || '')) ? P(pages[0]).notes || '' : ''; });
  body.push(h('div', { class: 'dp-cap' }, '발표자 노트'), ta);
  return section('페이지', { cls: 'dp-page' }, body);
}

/* ───────────────────────── 섹션: 레이아웃 (X/Y/W/H/회전/제약/자식 크기) ───────────────────────── */
const meas = (n) => { try { return ctx.renderer && ctx.renderer.measure ? ctx.renderer.measure(n.id) : null; } catch (e) { return null; } };
const isManaged = (n) => { const l = parentLayout(n); return !!l && !P(n).layoutChild.absolute; };
// 해당 축 크기가 레이아웃/텍스트에 의해 자동 결정되는가
function autoAxis(n, axis) {
  const p = P(n), k = axis === 'w' ? 'sizingH' : 'sizingV';
  if (n.type === 'text') { if (axis === 'w' ? p.autoResize === 'WIDTH_AND_HEIGHT' : p.autoResize === 'WIDTH_AND_HEIGHT' || p.autoResize === 'HEIGHT') return true; }
  if (p.layout && p.layout[k] && p.layout[k] !== 'FIXED') return true;
  if (isManaged(n) && p.layoutChild[k] && p.layoutChild[k] !== 'FIXED') return true;
  return false;
}
function dimOf(n, axis) {
  const p = P(n);
  if (autoAxis(n, axis)) { const m = meas(n); if (m && Number.isFinite(m[axis])) return m[axis]; }
  return p[axis];
}
// W/H 편집 → 고정 크기로 전환되는 부수 속성까지 포함한 set props
function sizeEdit(n, vals) {
  const p = P(n), out = {};
  let layout = p.layout, lc = parentLayout(n) ? p.layoutChild : null, ar = p.autoResize;
  for (const [axis, v] of Object.entries(vals)) {
    const k = axis === 'w' ? 'sizingH' : 'sizingV';
    out[axis] = round(v, 2);
    if (n.type === 'text') { if (axis === 'w' && ar === 'WIDTH_AND_HEIGHT') ar = 'HEIGHT'; if (axis === 'h' && (ar === 'WIDTH_AND_HEIGHT' || ar === 'HEIGHT')) ar = 'NONE'; }
    if (layout && layout[k] && layout[k] !== 'FIXED') layout = { ...layout, [k]: 'FIXED' };
    if (lc && !lc.absolute && lc[k] && lc[k] !== 'FIXED') lc = { ...lc, [k]: 'FIXED' };
  }
  if (n.type === 'text' && ar !== p.autoResize) {
    out.autoResize = ar;
    if (p.autoResize === 'WIDTH_AND_HEIGHT' && vals.w == null) out.w = round(dimOf(n, 'w'), 2);
  }
  if (layout !== p.layout) out.layout = layout;
  if (lc && lc !== p.layoutChild) out.layoutChild = lc;
  return out;
}
function sizeVals(n, axis, v) {
  const vals = { [axis]: v };
  if (lockIds.has(n.id) && n.type !== 'line') {
    const o = axis === 'w' ? 'h' : 'w', a = dimOf(n, axis), b = dimOf(n, o);
    if (a > 0) vals[o] = (b * v) / a;
  }
  return vals;
}
// 컨테이너(그룹/프레임…)의 W/H 는 제약에 따라 자식도 바뀌므로 layout.js 의 resizeOps 를 쓴다
function resizeFinalOps(ns, vf, axis) {
  const ops = [];
  for (const n of ns) {
    const v = vf(n); if (v == null) continue;
    const vals = sizeVals(n, axis, v), p = P(n);
    const set = sizeEdit(n, vals);
    const isBox = SCHEMA.containers.includes(n.type) && n.type !== 'page' && store.children(n.id).length;
    let used = false;
    if (isBox && layoutMod && layoutMod.resizeOps) {
      try {
        const r = layoutMod.resizeOps(store, n.id, { x: p.x, y: p.y, w: vals.w ?? p.w, h: vals.h ?? p.h });
        if (Array.isArray(r) && r.length) {
          ops.push(...r);
          const extra = {}; for (const k of ['layout', 'layoutChild', 'autoResize']) if (k in set) extra[k] = set[k];
          if (Object.keys(extra).length) ops.push({ op: 'set', id: n.id, props: extra });
          used = true;
        }
      } catch (e) { console.warn('resizeOps 실패 — 단순 set 으로 대체', e); }
    }
    if (!used) ops.push({ op: 'set', id: n.id, props: set });
  }
  return ops;
}
function constraintsUI(nodes) {
  const C = (n) => P(n).constraints || { h: 'LEFT', v: 'TOP' };
  const put = (k, v) => commitNodes(nodes, (n) => ({ constraints: { ...C(n), [k]: v } }), '제약 변경');
  const bits = (v, a, b, ab) => ({ a: v === a || v === ab, b: v === b || v === ab });
  function toggle(k, side, a, b, ab) {
    const vals = nodes.map((n) => C(n)[k]), cur = allSame(vals) ? vals[0] : a;
    let { a: A, b: B } = bits(cur, a, b, ab);
    if (cur === 'CENTER' || cur === 'SCALE') { A = false; B = false; }
    if (side === 'a') A = !A; else B = !B;
    put(k, A && B ? ab : A ? a : B ? b : side === 'a' ? a : b);
  }
  const wrap = h('div', { class: 'dp-cw', role: 'group', 'aria-label': '제약' });
  const mk = (cls, title, fn) => { const b = h('button', { class: cls, type: 'button', title, 'aria-label': title, onclick: fn }); wrap.append(b); return b; };
  wrap.append(h('div', { class: 'dp-cin' }));
  const bl = mk('dp-cl', '왼쪽 고정', () => toggle('h', 'a', 'LEFT', 'RIGHT', 'LEFT_RIGHT')), br = mk('dp-cr', '오른쪽 고정', () => toggle('h', 'b', 'LEFT', 'RIGHT', 'LEFT_RIGHT'));
  const bt = mk('dp-ct', '위 고정', () => toggle('v', 'a', 'TOP', 'BOTTOM', 'TOP_BOTTOM')), bb = mk('dp-cb', '아래 고정', () => toggle('v', 'b', 'TOP', 'BOTTOM', 'TOP_BOTTOM'));
  const bch = mk('dp-cch', '가로 가운데', () => put('h', 'CENTER')), bcv = mk('dp-ccv', '세로 가운데', () => put('v', 'CENTER'));
  const hOpts = [['LEFT', '왼쪽'], ['RIGHT', '오른쪽'], ['LEFT_RIGHT', '왼쪽 및 오른쪽'], ['CENTER', '가운데'], ['SCALE', '크기 조정']];
  const vOpts = [['TOP', '위'], ['BOTTOM', '아래'], ['TOP_BOTTOM', '위 및 아래'], ['CENTER', '가운데'], ['SCALE', '크기 조정']];
  const hs = selField({ nodes, options: hOpts, cur: (n) => C(n).h, put: (n, v) => ({ constraints: { ...C(n), h: v } }), label: '제약 변경', title: '가로 제약', text: '가로' });
  const vs = selField({ nodes, options: vOpts, cur: (n) => C(n).v, put: (n, v) => ({ constraints: { ...C(n), v: v } }), label: '제약 변경', title: '세로 제약', text: '세로' });
  function show() {
    const hv = nodes.map((n) => C(n).h), vv = nodes.map((n) => C(n).v), H = allSame(hv) ? hv[0] : null, V = allSame(vv) ? vv[0] : null;
    bl.classList.toggle('dp-on', H === 'LEFT' || H === 'LEFT_RIGHT' || H === 'SCALE'); br.classList.toggle('dp-on', H === 'RIGHT' || H === 'LEFT_RIGHT' || H === 'SCALE'); bch.classList.toggle('dp-on', H === 'CENTER' || H === 'SCALE');
    bt.classList.toggle('dp-on', V === 'TOP' || V === 'TOP_BOTTOM' || V === 'SCALE'); bb.classList.toggle('dp-on', V === 'BOTTOM' || V === 'TOP_BOTTOM' || V === 'SCALE'); bcv.classList.toggle('dp-on', V === 'CENTER' || V === 'SCALE');
  }
  refreshers.push(show); show();
  return h('div', { style: { display: 'flex', gap: '8px', alignItems: 'center' } }, wrap, h('div', { style: { flex: 1, display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 } }, hs, vs));
}

/* 자식의 크기 조절(고정/내용에 맞춤/채우기): 레이아웃 부모 안에서의 크기 모드 */
function sizingOf(n, axis) {
  const k = axis === 'w' ? 'sizingH' : 'sizingV', p = P(n);
  if (isManaged(n) && p.layoutChild[k] === 'FILL') return 'FILL';
  if (p.layout) return p.layout[k] === 'FILL' ? 'FILL' : p.layout[k] || 'FIXED';
  if (n.type === 'text') {
    const lc = p.layoutChild[k];
    if (lc && lc !== 'FIXED') return lc;
    return (axis === 'w' ? p.autoResize === 'WIDTH_AND_HEIGHT' : p.autoResize === 'WIDTH_AND_HEIGHT' || p.autoResize === 'HEIGHT') ? 'HUG' : 'FIXED';
  }
  return p.layoutChild[k] || 'FIXED';
}
function sizingPut(n, axis, v) {
  const out = sizingPut0(n, axis, v), p = P(n);
  // HUG/FILL/auto text → FIXED keeps the laid-out size instead of jumping back to the stale stored w/h
  if (v === 'FIXED' && autoAxis(n, axis)) out[axis] = round(dimOf(n, axis), 2);
  if (n.type === 'text' && p.autoResize === 'WIDTH_AND_HEIGHT' && out.autoResize && out.autoResize !== 'WIDTH_AND_HEIGHT' && out.w == null) out.w = round(dimOf(n, 'w'), 2);
  return out;
}
function sizingPut0(n, axis, v) {
  const k = axis === 'w' ? 'sizingH' : 'sizingV', p = P(n), out = {};
  const managed = !!parentLayout(n);
  if (p.layout) {
    out.layout = { ...p.layout, [k]: v === 'FILL' ? 'FIXED' : v };
    if (managed) out.layoutChild = { ...p.layoutChild, [k]: v === 'FILL' ? 'FILL' : 'FIXED' };
    return out;
  }
  const lc = { ...p.layoutChild, [k]: v };
  if (n.type === 'text') {
    let ar = p.autoResize;
    if (axis === 'w') { if (v === 'HUG') { ar = 'WIDTH_AND_HEIGHT'; lc.sizingV = 'HUG'; } else if (ar === 'WIDTH_AND_HEIGHT') ar = 'HEIGHT'; }
    else if (v === 'HUG') { if (ar === 'NONE' || ar === 'TRUNCATE') ar = 'HEIGHT'; } else if (ar === 'WIDTH_AND_HEIGHT' || ar === 'HEIGHT') ar = 'NONE';
    if (ar !== p.autoResize) out.autoResize = ar;
  }
  out.layoutChild = lc;
  return out;
}
function sizingSelect(nodes, axis, withOwnLayout) {
  const hugOk = nodes.every((n) => n.type === 'text' || (n.type === 'frame' && P(n).layout));
  const fillOk = nodes.every((n) => !!parentLayout(n));
  const options = [['FIXED', '고정']]; if (hugOk) options.push(['HUG', '내용에 맞춤']); if (fillOk) options.push(['FILL', '채우기']);
  return selField({ nodes, options, cur: (n) => sizingOf(n, axis), put: (n, v) => sizingPut(n, axis, v), label: axis === 'w' ? '가로 크기 조절 변경' : '세로 크기 조절 변경', title: axis === 'w' ? '가로 크기 조절' : '세로 크기 조절', icon: axis === 'w' ? 'arW' : 'arH' });
}

function secLayout(ns) {
  const xs = ns.filter((n) => n.type !== 'page');
  const lines = xs.every((n) => n.type === 'line');
  const pos = (key, text) => numField({ nodes: xs, text, title: key === 'x' ? 'X 위치' : 'Y 위치', cur: (n) => P(n)[key], put: (n, v) => ({ [key]: v }), label: '위치 변경', disabled: xs.every(isManaged) });
  const dim = (axis) => numField({
    nodes: xs, text: axis.toUpperCase(), title: axis === 'w' ? '너비' : '높이', min: 0, label: '크기 변경', disabled: axis === 'h' && lines,
    cur: (n) => (axis === 'h' && n.type === 'line' ? undefined : round(dimOf(n, axis), 2)),
    put: (n, v) => sizeEdit(n, sizeVals(n, axis, v)),
    finalOps: (list, vf) => resizeFinalOps(list, vf, axis),
  });
  const locked = xs.every((n) => lockIds.has(n.id));
  const lockBtn = iconBtn(locked ? 'lock' : 'unlock', locked ? '비율 잠금 해제' : '비율 잠금', (e, b) => { xs.forEach((n) => (locked ? lockIds.delete(n.id) : lockIds.add(n.id))); b.replaceChildren(ic(locked ? 'unlock' : 'lock')); b.classList.toggle('dp-on', !locked); b.title = locked ? '비율 잠금' : '비율 잠금 해제'; softRender(); }, { on: locked });
  const rot = numField({
    nodes: xs, icon: 'rotate', title: '회전 (도)', cur: (n) => (P(n).rotation ? -P(n).rotation : 0), label: '회전 변경', suffix: '°', dec: 2,
    // UI: counter-clockwise positive (Figma). Store: clockwise degrees in [-180, 180).
    put: (n, v) => ({ rotation: round(((((-v + 180) % 360) + 360) % 360) - 180, 2) }),
  });
  const body = [h('div', { class: 'dp-g3' }, pos('x', 'X'), pos('y', 'Y'), h('span')), h('div', { class: 'dp-g3' }, dim('w'), dim('h'), lines ? h('span') : lockBtn), h('div', { class: 'dp-g3' }, rot, h('span'), h('span'))];
  // 제약 (자동 레이아웃에 관리되지 않는 프레임/페이지/그룹의 자식)
  const cx = xs.filter((n) => { const par = parentOf(n); return par && ['page', 'frame', 'group'].includes(par.type) && (!P(par).layout || P(n).layoutChild.absolute); });
  if (cx.length) body.push(h('div', { class: 'dp-cap' }, '제약'), constraintsUI(cx));
  // 오토 레이아웃 자식
  const ch = xs.filter((n) => !!parentLayout(n));
  if (ch.length) {
    body.push(h('div', { class: 'dp-cap' }, '오토 레이아웃 자식'));
    const plain = ch.filter((n) => !(n.type === 'frame' && P(n).layout));
    if (plain.length) body.push(h('div', { class: 'dp-g2' }, sizingSelect(plain, 'w'), sizingSelect(plain, 'h')));
    body.push(chk({ nodes: ch, cur: (n) => !!P(n).layoutChild.absolute, put: (n, v) => ({ layoutChild: { ...P(n).layoutChild, absolute: v } }), text: '오토 레이아웃 무시', label: '오토 레이아웃 무시 전환' }));
    const mm = (k, text, title) => numField({ nodes: ch, text, title, optional: true, ph: '없음', cur: (n) => P(n).layoutChild[k] ?? null, put: (n, v) => { const o = { ...P(n).layoutChild }; if (v == null) delete o[k]; else o[k] = v; return { layoutChild: o }; }, label: '최소/최대 크기 변경', min: 0 });
    body.push(h('div', { class: 'dp-g2' }, mm('minW', '최소W', '최소 너비'), mm('maxW', '최대W', '최대 너비')), h('div', { class: 'dp-g2' }, mm('minH', '최소H', '최소 높이'), mm('maxH', '최대H', '최대 높이')));
  }
  return section('레이아웃', { cls: 'dp-layout' }, body);
}

/* ───────────────────────── 섹션: 오토 레이아웃 ───────────────────────── */
const defaultLayout = () => ({ dir: 'HORIZONTAL', wrap: false, gap: 10, gapCross: 10, pad: [10, 10, 10, 10], alignMain: 'MIN', alignCross: 'MIN', sizingH: 'HUG', sizingV: 'HUG', strokesIncluded: false, reverseZ: false });
const LY = (n) => P(n).layout;
const putL = (n, patch) => ({ layout: { ...LY(n), ...patch } });
const AL = ['MIN', 'CENTER', 'MAX'];
const AL_NAME = { MIN: '시작', CENTER: '가운데', MAX: '끝' };
function txtBtn(text, title, onclick, o = {}) {
  return h('button', { class: 'dp-ib dp-tb' + (o.on ? ' dp-on' : ''), type: 'button', title, 'aria-label': title, 'aria-pressed': o.on ? 'true' : 'false', disabled: o.disabled, style: Object.assign({ width: 'auto', padding: '0 6px', ...(o.style || {}) }), onclick: (e) => { e.stopPropagation(); onclick(e); } }, text);
}
function alignGrid(nodes) {
  const g = h('div', { class: 'dp-agrid', role: 'group', 'aria-label': '정렬' });
  const cells = [];
  const horiz = (n) => LY(n).dir === 'HORIZONTAL';
  const pick = (r, c) => commitNodes(nodes, (n) => {
    const l = LY(n), main = horiz(n) ? c : r, cross = horiz(n) ? r : c;
    return putL(n, { alignMain: l.alignMain === 'SPACE_BETWEEN' ? 'SPACE_BETWEEN' : AL[main], alignCross: AL[cross] });
  }, '오토 레이아웃 정렬 변경');
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
    const b = h('button', { type: 'button', title: '정렬', 'aria-label': `정렬 ${r + 1}행 ${c + 1}열`, onclick: () => pick(r, c) });
    cells.push([r, c, b]); g.append(b);
  }
  function show() {
    const ps = nodes.map((n) => { const l = LY(n); return { hz: horiz(n), m: l.alignMain === 'SPACE_BETWEEN' ? -1 : AL.indexOf(l.alignMain), c: AL.indexOf(l.alignCross === 'BASELINE' ? 'MIN' : l.alignCross) }; });
    const ok = allSame(ps), p = ps[0];
    for (const [r, c, b] of cells) {
      const main = ok && p.hz ? c : r, cross = ok && p.hz ? r : c;
      const on = ok && cross === p.c && (p.m === -1 ? false : main === p.m);
      b.classList.toggle('dp-on', on);
      b.classList.toggle('dp-on2', ok && p.m === -1 && cross === p.c && !on);
    }
  }
  refreshers.push(show); show();
  return g;
}
function secAuto(ns) {
  const cand = ns.filter((n) => n.type === 'frame' || n.type === 'page');
  if (!cand.length) return null;
  const on = cand.filter((n) => LY(n));
  const add = iconBtn('plus', '오토 레이아웃 추가', () => commitNodes(cand.filter((n) => !LY(n)), () => ({ layout: defaultLayout() }), '오토 레이아웃 추가'), { disabled: on.length === cand.length });
  const rem = iconBtn('minus', '오토 레이아웃 제거', () => commitNodes(on, () => ({ layout: null }), '오토 레이아웃 제거'), { disabled: !on.length });
  if (!on.length) return section('오토 레이아웃', { actions: [add], cls: 'dp-auto' });
  const body = [];
  const swapAlign = (l, dir) => {
    if (l.dir === dir) return {};
    const a = l.alignMain, c = l.alignCross;
    return { dir, alignMain: AL.includes(c) ? c : 'MIN', alignCross: AL.includes(a) ? a : 'MIN' };
  };
  const allWrap = on.every((n) => LY(n).wrap);
  const allBase = on.every((n) => LY(n).alignCross === 'BASELINE');
  body.push(row(
    seg({ nodes: on, label: '오토 레이아웃 방향 변경', cur: (n) => LY(n).dir, items: [{ v: 'VERTICAL', icon: 'dirV', title: '세로 방향' }, { v: 'HORIZONTAL', icon: 'dirH', title: '가로 방향' }], put: (n, v) => putL(n, swapAlign(LY(n), v)) }),
    iconBtn('wrap', '줄바꿈', () => commitNodes(on, (n) => putL(n, { wrap: !allWrap }), '오토 레이아웃 줄바꿈 변경'), { on: allWrap }),
    iconBtn('baseline', '텍스트 기준선 정렬', () => commitNodes(on, (n) => putL(n, { alignCross: allBase ? 'MIN' : 'BASELINE' }), '오토 레이아웃 정렬 변경'), { on: allBase, disabled: !on.every((n) => LY(n).dir === 'HORIZONTAL') }),
  ));
  // 정렬 격자 + 간격
  const autoGap = on.every((n) => LY(n).alignMain === 'SPACE_BETWEEN');
  const gap = numField({ nodes: on, text: '간격', title: '항목 사이 간격', cur: (n) => (autoGap ? undefined : LY(n).gap), put: (n, v) => putL(n, { gap: v }), label: '오토 레이아웃 간격 변경', min: 0, ph: '자동', disabled: autoGap });
  const autoBtn = txtBtn('자동', '간격 자동 (양끝 정렬)', () => commitNodes(on, (n) => putL(n, { alignMain: autoGap ? 'MIN' : 'SPACE_BETWEEN' }), '오토 레이아웃 간격 변경'), { on: autoGap });
  const rightCol = [row(gap, autoBtn)];
  if (on.some((n) => LY(n).wrap)) rightCol.push(numField({ nodes: on.filter((n) => LY(n).wrap), text: '줄 간격', title: '줄 사이 간격', cur: (n) => LY(n).gapCross, put: (n, v) => putL(n, { gapCross: v }), label: '오토 레이아웃 간격 변경', min: 0 }));
  body.push(h('div', { style: { display: 'flex', gap: '8px', alignItems: 'flex-start' } }, alignGrid(on), h('div', { style: { flex: 1, display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 } }, rightCol)));
  // 패딩
  const padCur = (idx) => (n) => { const pd = LY(n).pad; return idx.every((i) => pd[i] === pd[idx[0]]) ? pd[idx[0]] : MIXED; };
  const padPut = (idx) => (n, v) => { const pd = [...LY(n).pad]; idx.forEach((i) => { pd[i] = v; }); return putL(n, { pad: pd }); };
  const pf = (idx, text, title) => numField({ nodes: on, text, title, cur: padCur(idx), put: padPut(idx), label: '오토 레이아웃 패딩 변경', min: 0 });
  const expanded = on.some((n) => padExpand.has(n.id)) || on.some((n) => { const pd = LY(n).pad; return pd[0] !== pd[2] || pd[1] !== pd[3]; });
  const exBtn = iconBtn('corners', expanded ? '패딩 한 번에 편집' : '패딩 개별 편집', () => { on.forEach((n) => (expanded ? padExpand.delete(n.id) : padExpand.add(n.id))); softRender(); }, { on: expanded });
  body.push(h('div', { class: 'dp-cap' }, '패딩'));
  if (!expanded) body.push(h('div', { class: 'dp-g3' }, pf([3, 1], '좌우', '좌우 패딩'), pf([0, 2], '상하', '상하 패딩'), exBtn));
  else body.push(h('div', { class: 'dp-g3' }, pf([3], '왼쪽', '왼쪽 패딩'), pf([0], '위', '위 패딩'), exBtn), h('div', { class: 'dp-g3' }, pf([1], '오른쪽', '오른쪽 패딩'), pf([2], '아래', '아래 패딩'), h('span')));
  // 크기
  body.push(h('div', { class: 'dp-g2' }, sizingSelect(on, 'w'), sizingSelect(on, 'h')));
  body.push(chk({ nodes: on, cur: (n) => !!LY(n).strokesIncluded, put: (n, v) => putL(n, { strokesIncluded: v }), text: '획 포함', label: '오토 레이아웃 획 포함 변경' }));
  body.push(chk({ nodes: on, cur: (n) => !!LY(n).reverseZ, put: (n, v) => putL(n, { reverseZ: v }), text: '마지막 항목을 위로', label: '오토 레이아웃 쌓임 순서 변경' }));
  return section('오토 레이아웃', { actions: [add, rem], cls: 'dp-auto' }, body);
}
const padExpand = new Set();

/* ───────────────────────── 섹션: 모양 (반경/스무딩/꼭짓점/호/불리언/자르기) ───────────────────────── */
const SHAPE_TITLE = { rect: '사각형', frame: '프레임', polygon: '다각형', star: '별', ellipse: '타원', boolean: '불리언 연산' };
function secShape(ns) {
  const body = [];
  const rc = ns.filter((n) => n.type === 'rect' || n.type === 'frame');
  const radArr = (n) => { const r = P(n).radius; return Array.isArray(r) ? r : [r, r, r, r]; };
  if (rc.length) {
    const differ = (n) => new Set(radArr(n)).size > 1;
    const indep = rc.some((n) => indepRadius.has(n.id) || differ(n));
    const toggle = iconBtn('corners', indep ? '모서리 한 번에 편집' : '모서리 독립 편집', () => {
      if (indep) { rc.forEach((n) => indepRadius.delete(n.id)); commitNodes(rc, (n) => ({ radius: radArr(n)[0] }), '모서리 반경 변경').then(softRender); } else { rc.forEach((n) => indepRadius.add(n.id)); softRender(); }
    }, { on: indep });
    if (!indep) {
      body.push(h('div', { class: 'dp-g3' }, numField({ nodes: rc, icon: 'corner', title: '모서리 반경', cur: (n) => (differ(n) ? MIXED : radArr(n)[0]), put: (n, v) => ({ radius: v }), label: '모서리 반경 변경', min: 0 }), h('span'), toggle));
    } else {
      const cf = (i, text, title) => numField({ nodes: rc, text, title, cur: (n) => radArr(n)[i], put: (n, v) => { const a = [...radArr(n)]; a[i] = v; return { radius: a }; }, label: '모서리 반경 변경', min: 0 });
      body.push(h('div', { class: 'dp-g3' }, cf(0, '좌상', '왼쪽 위 반경'), cf(1, '우상', '오른쪽 위 반경'), toggle), h('div', { class: 'dp-g3' }, cf(3, '좌하', '왼쪽 아래 반경'), cf(2, '우하', '오른쪽 아래 반경'), h('span')));
    }
    const sm = (n) => P(n).smoothing || 0;
    body.push(row(h('div', { style: { flex: 1, minWidth: 0 } }, numField({ nodes: rc, text: '스무딩', title: '모서리 스무딩', cur: sm, scale: 100, dec: 0, min: 0, max: 100, suffix: '%', put: (n, v) => ({ smoothing: v }), label: '모서리 스무딩 변경' })), txtBtn('iOS', 'iOS 스타일 (60%)', () => commitNodes(rc, () => ({ smoothing: 0.6 }), '모서리 스무딩 변경'), { style: { border: '1px solid var(--dp-border)', height: '24px' } })));
    body.push(row(slider({ nodes: rc, cur: sm, put: (n, v) => ({ smoothing: v }), min: 0, max: 100, step: 1, scale: 100, title: '모서리 스무딩', label: '모서리 스무딩 변경' })));
  }
  const fr = ns.filter((n) => n.type === 'frame');
  if (fr.length) body.push(chk({ nodes: fr, cur: (n) => !!P(n).clip, put: (n, v) => ({ clip: v }), text: '내용 자르기', label: '내용 자르기 변경' }));
  const poly = ns.filter((n) => n.type === 'polygon'), star = ns.filter((n) => n.type === 'star');
  const ptsField = (list) => numField({ nodes: list, text: '꼭짓점', title: '꼭짓점 수 (3–60)', cur: (n) => P(n).points, put: (n, v) => ({ points: clamp(Math.round(v), 3, 60) }), label: '꼭짓점 수 변경', min: 3, max: 60, dec: 0 });
  const radField = (list) => numField({ nodes: list, text: '반경', title: '모서리 반경', cur: (n) => P(n).radius, put: (n, v) => ({ radius: v }), label: '모서리 반경 변경', min: 0 });
  if (poly.length) body.push(h('div', { class: 'dp-g2' }, ptsField(poly), radField(poly)));
  if (star.length) {
    body.push(h('div', { class: 'dp-g2' }, ptsField(star), numField({ nodes: star, text: '비율', title: '안쪽 비율', cur: (n) => P(n).inner, scale: 100, dec: 0, min: 0, max: 100, suffix: '%', put: (n, v) => ({ inner: v }), label: '별 비율 변경' })), row(radField(star)));
  }
  const el = ns.filter((n) => n.type === 'ellipse');
  if (el.length) {
    const A = (n) => P(n).arc;
    body.push(h('div', { class: 'dp-g2' },
      numField({ nodes: el, text: '시작', title: '호 시작 각도', cur: (n) => rad2deg(A(n).start), suffix: '°', dec: 2, label: '호 변경', put: (n, v) => { const a = A(n), sw = a.end - a.start; return { arc: { ...a, start: deg2rad(v), end: deg2rad(v) + sw } }; } }),
      numField({ nodes: el, text: '스윕', title: '호 스윕 각도 (0–360)', cur: (n) => rad2deg(A(n).end - A(n).start), min: 0, max: 360, suffix: '°', dec: 2, label: '호 변경', put: (n, v) => ({ arc: { ...A(n), end: A(n).start + deg2rad(v) } }) })),
    row(numField({ nodes: el, text: '비율', title: '안쪽 비율', cur: (n) => A(n).inner, scale: 100, dec: 0, min: 0, max: 100, suffix: '%', label: '호 변경', put: (n, v) => ({ arc: { ...A(n), inner: v } }) })));
  }
  const bo = ns.filter((n) => n.type === 'boolean');
  if (bo.length) body.push(seg({ nodes: bo, label: '불리언 연산 변경', cur: (n) => P(n).op, put: (n, v) => ({ op: v }), items: [{ v: 'UNION', icon: 'bUnion', title: '합치기' }, { v: 'SUBTRACT', icon: 'bSub', title: '빼기' }, { v: 'INTERSECT', icon: 'bInt', title: '교차' }, { v: 'EXCLUDE', icon: 'bExc', title: '제외' }] }));
  if (!body.length) return null;
  const types = [...new Set(ns.filter((n) => SHAPE_TITLE[n.type]).map((n) => n.type))];
  return section(types.length === 1 ? SHAPE_TITLE[types[0]] : '모양', { cls: 'dp-shape' }, body);
}

/* ───────────────────────── 섹션: 표 ───────────────────────── */
function secTable(ns) {
  const tb = ns.filter((n) => n.type === 'table');
  if (!tb.length) return null;
  const sum = (a) => a.reduce((s, x) => s + x, 0);
  const prune = (cells, rows, cols) => Object.fromEntries(Object.entries(cells || {}).filter(([k]) => { const [r, c] = k.split(',').map(Number); return r < rows && c < cols; }));
  const mod = (kind, delta) => commitNodes(tb, (n) => {
    const p = P(n);
    let rows = [...p.rows], cols = [...p.cols];
    const arr = kind === 'row' ? rows : cols;
    if (delta > 0) arr.push(arr.length ? arr[arr.length - 1] : 40); else if (arr.length > 1) arr.pop(); else return null;
    return { rows, cols, cells: prune(p.cells, rows.length, cols.length), w: sum(cols), h: sum(rows) };
  }, kind === 'row' ? (delta > 0 ? '표 행 추가' : '표 행 삭제') : (delta > 0 ? '표 열 추가' : '표 열 삭제'));
  const counter = (kind, name) => {
    const vs = tb.map((n) => P(n)[kind === 'row' ? 'rows' : 'cols'].length);
    return h('div', { class: 'dp-row', style: { gap: '4px' } }, h('span', { class: 'dp-lab', style: { flex: '1 1 auto' } }, `${name} ${allSame(vs) ? vs[0] : '혼합'}`),
      iconBtn('minus', `${name} 삭제 (마지막)`, () => mod(kind, -1), { disabled: vs.some((v) => v <= 1) }), iconBtn('plus', `${name} 추가 (마지막)`, () => mod(kind, 1)));
  };
  const colorSw = swatch({ type: 'SOLID', color: P(tb[0]).border.color }, !allSame(tb.map((n) => P(n).border.color)));
  colorSw.dataset.popkey = 'tblborder'; colorSw.title = '테두리 색상';
  colorSw.addEventListener('click', () => {
    if (popIsOpen('tblborder')) { closePop(); return; }
    let s = null;
    openPop(colorSw, '표 테두리', (api) => {
      api.body.append(colorPicker(P(tb[0]).border.color, (c, fin) => {
        const build = (n) => ({ border: { ...P(n).border, color: c } });
        if (fin) { const q = s || session(tb); s = null; q.commit(build, '표 테두리 변경'); } else { s = s || session(tb); s.preview(build); }
      }).el);
    }, { key: 'tblborder' });
  });
  const hex = numField({ nodes: tb, raw: true, scrub: false, cur: (n) => P(n).border.color, fmt: (c) => String(c).slice(1, 7), label: '표 테두리 변경', title: '테두리 HEX',
    parse: (t, base) => { const q = parseHex(t.replace('#', '')); if (!q) return undefined; const cb = parseHex(base) || { a: 1 }; return toHex({ ...q, a: /^#?([0-9a-f]{8}|[0-9a-f]{4})$/i.test(t) ? q.a : cb.a }); },
    put: (n, v) => ({ border: { ...P(n).border, color: v } }) });
  return section('표', { cls: 'dp-table' },
    counter('row', '행'), counter('col', '열'),
    h('div', { class: 'dp-cap' }, '테두리'),
    row(colorSw, h('div', { style: { flex: 1, minWidth: 0 } }, hex), h('div', { style: { width: '70px', flex: 'none' } }, numField({ nodes: tb, text: '두께', title: '테두리 두께', cur: (n) => P(n).border.weight, put: (n, v) => ({ border: { ...P(n).border, weight: v } }), label: '표 테두리 변경', min: 0, dec: 1 }))),
    chk({ nodes: tb, cur: (n) => !!P(n).header, put: (n, v) => ({ header: v }), text: '머리글 행', label: '머리글 행 전환' }));
}

/* ───────────────────────── 섹션: 레이어(불투명도/혼합), 내보내기 ───────────────────────── */
function secLayer(ns) {
  return section('레이어', { cls: 'dp-layer' },
    h('div', { class: 'dp-g2', style: { gridTemplateColumns: '84px 1fr' } },
      numField({ nodes: ns, icon: 'eye', title: '불투명도', cur: (n) => P(n).opacity, scale: 100, dec: 1, min: 0, max: 100, suffix: '%', label: '불투명도 변경', put: (n, v) => ({ opacity: v }) }),
      selField({ nodes: ns, options: blendOptions(true), title: '혼합 모드', cur: (n) => P(n).blend, put: (n, v) => ({ blend: v }), label: '블렌드 모드 변경' })));
}
function secExport(ns) {
  const pg = ns[0] && (ns[0].type === 'page' ? ns[0] : store.pageOf(ns[0].id));
  return section('내보내기', { cls: 'dp-export' },
    h('button', { class: 'dp-btn dp-wide', type: 'button', disabled: !pg, onclick: () => { if (pg) window.dispatchEvent(new CustomEvent('ppt:export-pdf', { detail: { pages: [pg.id] } })); } }, '이 페이지 PDF로 내보내기'));
}

/* ───────────────────────── 섹션: 텍스트 ───────────────────────── */
const FONTS = ['Inter', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Nanum Gothic', 'Nanum Myeongjo', 'Malgun Gothic', '맑은 고딕', 'Pretendard', 'Spoqa Han Sans Neo', 'Helvetica Neue', 'Helvetica', 'Arial', 'Arial Black', 'Avenir Next', 'Avenir', 'Futura', 'Gill Sans', 'Georgia', 'Times New Roman', 'Palatino', 'Baskerville', 'Didot', 'Menlo', 'Monaco', 'SF Mono', 'Courier New', 'Verdana', 'Tahoma', 'Trebuchet MS', 'Segoe UI', 'Calibri', 'Cambria', 'Consolas', 'Roboto', 'Open Sans', 'Lato', 'Montserrat', 'Source Sans Pro', 'Hiragino Sans', 'PingFang SC'];
const WEIGHTS = [['100', '100 Thin'], ['200', '200 Extra Light'], ['300', '300 Light'], ['400', '400 Regular'], ['500', '500 Medium'], ['600', '600 Semi Bold'], ['700', '700 Bold'], ['800', '800 Extra Bold'], ['900', '900 Black']];
const cssFont = (name) => `"${String(name).replace(/["\\]/g, '')}", sans-serif`;

// 런(run)별 유효 스타일 값
function styleVals(n, key) {
  const st = P(n).style || {}, runs = P(n).runs || [], vals = [];
  for (const r of runs) if (r.t) vals.push(r.s && key in r.s ? r.s[key] : st[key]);
  if (!vals.length) vals.push(st[key]);
  return vals;
}
const styleCur = (key) => (n) => {
  const e = activeEdit([n]); // 편집 중이면 캐럿/선택 시작 위치의 스타일을 보여준다
  if (e && e.currentStyle) { try { const c = e.currentStyle()[key]; if (c !== undefined && c !== null) return c; } catch (err) { /* 무시 */ } }
  const v = styleVals(n, key); return allSame(v) ? v[0] : MIXED;
};
// 노드 전체 스타일 변경: style 갱신 + 각 런의 개별 오버라이드 제거
function stylePut(n, key, val) {
  const p = P(n), out = { style: { ...p.style, [key]: val } };
  const runs = p.runs || [];
  if (runs.some((r) => r.s && key in r.s)) {
    out.runs = runs.map((r) => {
      if (!(r.s && key in r.s)) return r;
      const { [key]: _drop, ...rest } = r.s, o = { ...r };
      if (Object.keys(rest).length) o.s = rest; else delete o.s;
      return o;
    });
  }
  return out;
}
const paraCount = (n) => (P(n).runs || []).map((r) => r.t || '').join('').split('\n').length;
const listCur = (n) => { const c = paraCount(n), ps = P(n).paras || [], ks = Array.from({ length: c }, (_, i) => (ps[i] && ps[i].list) || 'NONE'); return allSame(ks) ? ks[0] : MIXED; };
function listPut(n, kind) {
  const old = P(n).paras || [];
  const arr = Array.from({ length: paraCount(n) }, (_, i) => ({ list: kind, level: (old[i] && old[i].level) || 0 }));
  return { paras: kind === 'NONE' && arr.every((x) => x.level === 0) ? [] : arr };
}

function openFontPop(anchor, nodes, pick) {
  const used = () => { const s = new Set(); for (const n of store.nodes.values()) if (n.type === 'text') { const p = P(n); if (p.style && p.style.font) s.add(p.style.font); for (const r of p.runs || []) if (r.s && r.s.font) s.add(r.s.font); } return [...s]; };
  openPop(anchor, '글꼴', (api) => {
    const search = h('input', { class: 'dp-in', type: 'search', placeholder: '글꼴 검색', 'aria-label': '글꼴 검색', style: { background: 'var(--dp-field)', borderRadius: 'var(--dp-r)', height: '24px', padding: '0 8px', border: '1px solid transparent', userSelect: 'text' } });
    const list = h('div', { class: 'dp-fontlist', role: 'listbox' });
    const msg = h('div', { class: 'dp-dim', style: { fontSize: '10px', padding: '2px 0' } });
    api.body.append(search, list, msg);
    let items = [], hl = 0;
    const cur = (() => { const vs = nodes.map(styleCur('font')); return allSame(vs) ? vs[0] : null; })();
    function draw() {
      const q = search.value.trim().toLowerCase(), seen = new Set();
      const groups = [['문서에서 사용 중', used()], ['글꼴', FONTS], ['이 컴퓨터의 글꼴', localFonts]];
      list.textContent = ''; items = [];
      for (const [title, arr] of groups) {
        const f = arr.filter((x) => !seen.has(x) && (!q || x.toLowerCase().includes(q))).slice(0, 300);
        f.forEach((x) => seen.add(x));
        if (!f.length) continue;
        list.append(h('div', { class: 'dp-fh' }, title));
        for (const name of f) {
          const el = h('div', { class: 'dp-fi' + (name === cur ? ' dp-cur' : ''), role: 'option', onclick: () => { closePop(); pick(name); }, onmouseenter: () => { hl = items.findIndex((i) => i.name === name); mark(); } }, name);
          el.style.fontFamily = cssFont(name);
          list.append(el); items.push({ name, el });
        }
      }
      if (!items.length && q) list.append(h('div', { class: 'dp-fi', style: { color: 'var(--dp-dim)' }, onclick: () => { closePop(); pick(search.value.trim()); } }, `"${search.value.trim()}" 사용`));
      if (window.queryLocalFonts && !localFonts.length) {
        list.append(h('div', { class: 'dp-fi', style: { color: 'var(--dp-accent)' }, role: 'button', onclick: loadLocal }, '로컬 글꼴 불러오기…'));
      }
      hl = Math.max(0, items.findIndex((i) => i.name === cur)); mark();
    }
    function mark() { items.forEach((i, k) => i.el.classList.toggle('dp-hl', k === hl)); const e = items[hl]; if (e && e.el.scrollIntoView) e.el.scrollIntoView({ block: 'nearest' }); }
    async function loadLocal() {
      try { // 사용자 제스처(클릭) 안에서만 호출
        const fonts = await window.queryLocalFonts();
        localFonts = [...new Set(fonts.map((f) => f.family))].sort((a, b) => a.localeCompare(b));
        msg.textContent = `${localFonts.length}개 글꼴을 불러왔습니다`;
      } catch (e) { msg.textContent = '로컬 글꼴 접근 권한이 없습니다'; }
      draw();
    }
    search.addEventListener('input', draw);
    search.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'ArrowDown') { e.preventDefault(); hl = Math.min(items.length - 1, hl + 1); mark(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); hl = Math.max(0, hl - 1); mark(); }
      else if (e.key === 'Enter') { e.preventDefault(); const it = items[hl]; closePop(); if (it) pick(it.name); else if (search.value.trim()) pick(search.value.trim()); }
    });
    draw();
    setTimeout(() => search.focus(), 0);
  }, { key: 'font' });
}

function secText(ns) {
  const tx = ns.filter((n) => n.type === 'text');
  if (!tx.length) return null;
  const E = () => activeEdit(tx);
  // 글자 단위 스타일 필드 공통 옵션: 편집 세션이 있으면 applyStyle 로 라우팅, 아니면 노드 전체 style 커밋
  const nodeKey = (key) => (v) => { const e = E(); if (!e) return false; e.applyStyle({ [key]: v }); return true; };
  const sty = (key, conv) => ({ nodes: tx, cur: styleCur(key), put: (n, v) => stylePut(n, key, conv ? conv(v) : v), intercept: (v) => { const e = E(); if (!e) return false; e.applyStyle({ [key]: conv ? conv(v) : v }); return true; } });
  const body = [];
  if (E()) body.push(h('div', { class: 'dp-cap', style: { color: 'var(--dp-accent)' } }, '글자 편집 중 — 선택한 범위에 적용됩니다'));

  // 글꼴 패밀리 콤보박스
  const fbtn = h('button', { class: 'dp-fontbtn', type: 'button', title: '글꼴', 'aria-haspopup': 'listbox' });
  fbtn.dataset.popkey = 'font';
  const showFont = () => { const vs = tx.map(styleCur('font')); if (!allSame(vs) || vs[0] === MIXED) { fbtn.textContent = '혼합'; fbtn.style.fontFamily = ''; } else { fbtn.textContent = vs[0]; fbtn.style.fontFamily = cssFont(vs[0]); } };
  showFont(); refreshers.push(showFont);
  const pickFont = (name) => { const e = E(); if (e) e.applyStyle({ font: name }); else commitNodes(tx, (n) => stylePut(n, 'font', name), '글꼴 변경'); };
  fbtn.addEventListener('click', () => (popIsOpen('font') ? closePop() : openFontPop(fbtn, tx, pickFont)));
  body.push(fbtn);

  // 굵기 / 기울임 / 크기
  const italicOn = tx.every((n) => styleCur('italic')(n) === true);
  const weight = selField({ ...sty('weight', Number), cur: (n) => { const v = styleCur('weight')(n); return v === MIXED ? v : String(v); }, options: WEIGHTS, label: '글꼴 굵기 변경', title: '굵기' });
  const italic = txtBtn('I', '기울임', () => { const e = E(); if (e) e.applyStyle({ italic: !italicOn }); else commitNodes(tx, (n) => stylePut(n, 'italic', !italicOn), '기울임 변경'); }, { on: italicOn, style: { fontStyle: 'italic', width: '24px', padding: '0', fontFamily: 'serif', fontSize: '13px' } });
  const size = numField({ ...sty('size'), icon: null, text: 'T', title: '글자 크기', label: '글자 크기 변경', min: 1, dec: 2 });
  body.push(h('div', { style: { display: 'grid', gridTemplateColumns: '1fr 24px 62px', gap: '4px', alignItems: 'center' } }, weight, italic, size));

  // 행간 / 자간
  const lhFmt = (v) => (v.unit === 'AUTO' ? '자동' : v.unit === 'PERCENT' ? `${fmtNum(v.value, 2)}%` : fmtNum(v.value, 2));
  const unitParse = (kind) => (t, base) => {
    const s = t.trim().toLowerCase();
    if (kind === 'lh' && (s === '' || s === 'auto' || s === '자동')) return { unit: 'AUTO', value: 0 };
    const bv = base && typeof base.value === 'number' ? base.value : 0;
    const v = calcExpr(s, bv);
    if (!Number.isFinite(v) || (kind === 'lh' && v < 0)) return undefined;
    const unit = /%$/.test(s) ? 'PERCENT' : /px$/.test(s) ? 'PX' : base && base.unit && base.unit !== 'AUTO' ? base.unit : kind === 'lh' ? 'PERCENT' : 'PERCENT';
    return { unit, value: round(v, 2) };
  };
  body.push(h('div', { class: 'dp-g2' },
    numField({ ...sty('lineHeight'), raw: true, scrub: false, text: '행간', title: '행간 (자동 / 120% / 24px)', label: '행간 변경', fmt: lhFmt, parse: unitParse('lh'), nudge: (b, d) => (b.unit === 'AUTO' ? { unit: 'PERCENT', value: round(120 + d, 2) } : { ...b, value: Math.max(0, round(b.value + d, 2)) }) }),
    numField({ ...sty('letterSpacing'), raw: true, scrub: false, text: '자간', title: '자간 (0% / 1px)', label: '자간 변경', fmt: (v) => `${fmtNum(v.value, 2)}${v.unit === 'PX' ? 'px' : '%'}`, parse: unitParse('ls'), nudge: (b, d) => ({ ...b, value: round(b.value + d, 2) }) })));

  // 문단 간격 / 들여쓰기
  body.push(h('div', { class: 'dp-g2' },
    numField({ nodes: tx, text: '문단', title: '문단 간격', cur: (n) => P(n).paragraphSpacing, put: (n, v) => ({ paragraphSpacing: v }), intercept: nodeKey('paragraphSpacing'), label: '문단 간격 변경', min: 0 }),
    numField({ nodes: tx, text: '들여쓰기', title: '첫 줄 들여쓰기', cur: (n) => P(n).indent, put: (n, v) => ({ indent: v }), intercept: nodeKey('indent'), label: '들여쓰기 변경', min: 0 })));

  // 정렬
  const fixedSize = tx.every((n) => { const a = P(n).autoResize; return a === 'NONE' || a === 'TRUNCATE'; });
  body.push(row(
    seg({ nodes: tx, label: '텍스트 정렬 변경', cur: (n) => P(n).alignH, put: (n, v) => ({ alignH: v }), intercept: nodeKey('alignH'), items: [{ v: 'LEFT', icon: 'alL', title: '왼쪽 정렬' }, { v: 'CENTER', icon: 'alC', title: '가운데 정렬' }, { v: 'RIGHT', icon: 'alR', title: '오른쪽 정렬' }, { v: 'JUSTIFIED', icon: 'alJ', title: '양쪽 정렬' }] }),
    seg({ nodes: tx, label: '텍스트 세로 정렬 변경', cls: fixedSize ? '' : 'dp-dis', cur: (n) => P(n).alignV, put: (n, v) => ({ alignV: v }), intercept: nodeKey('alignV'), items: [{ v: 'TOP', icon: 'avT', title: '위 정렬 (고정 크기에서만)' }, { v: 'CENTER', icon: 'avM', title: '세로 가운데 (고정 크기에서만)' }, { v: 'BOTTOM', icon: 'avB', title: '아래 정렬 (고정 크기에서만)' }] })));

  // 장식 / 대소문자
  body.push(h('div', { class: 'dp-g2' },
    seg({ ...sty('decoration'), label: '텍스트 장식 변경', items: [{ v: 'NONE', icon: 'dNone', title: '장식 없음' }, { v: 'UNDERLINE', icon: 'dUnder', title: '밑줄' }, { v: 'STRIKETHROUGH', icon: 'dStrike', title: '취소선' }] }),
    selField({ ...sty('case'), label: '대소문자 변경', title: '대소문자', options: [['ORIGINAL', '원래대로'], ['UPPER', '대문자'], ['LOWER', '소문자'], ['TITLE', '단어 첫 글자'], ['SMALL_CAPS', '작은 대문자']] })));

  // 목록
  body.push(seg({
    nodes: tx, label: '목록 변경', cur: listCur, put: (n, v) => listPut(n, v),
    intercept: (v) => { const e = E(); if (!e) return false; const kind = v === 'NONE' ? tx.map(listCur)[0] : v; if (kind && kind !== 'NONE' && kind !== MIXED) e.toggleList(kind); return true; },
    items: [{ v: 'NONE', icon: 'lNone', title: '목록 없음' }, { v: 'BULLET', icon: 'lBullet', title: '글머리 기호' }, { v: 'ORDERED', icon: 'lOrder', title: '번호' }],
  }));

  // 링크: 발표·PDF에서 눌리는 주소. 편집 중이면 선택 범위, 아니면 텍스트 전체
  const linkVals = tx.flatMap((n) => (P(n).runs || []).filter((r) => r.t).map((r) => r.link || ''));
  const linkIn = h('input', { class: 'dp-in', type: 'text', spellcheck: false, autocomplete: 'off', title: '링크 (https://… 또는 메일 주소)', placeholder: allSame(linkVals) ? 'https://… 또는 메일 주소' : '혼합', value: allSame(linkVals) ? linkVals[0] || '' : '' });
  const putLink = () => {
    let v = linkIn.value.trim();
    if (v && !/^(https?:|mailto:)/i.test(v)) v = /^[^\s@/]+@[^\s@/]+\.[^\s@/]+$/.test(v) ? 'mailto:' + v : 'https://' + v;
    if (v.length > 2000 || /\s/.test(v)) { linkIn.value = allSame(linkVals) ? linkVals[0] || '' : ''; return; }
    const e = E();
    if (e) { e.applyStyle({ link: v || null }); return; }
    commitNodes(tx, (n) => ({ runs: (P(n).runs || []).map((r) => { const { link: _drop, ...o } = r; return v ? { ...o, link: v } : o; }) }), v ? '링크 추가' : '링크 제거');
  };
  linkIn.addEventListener('change', putLink);
  linkIn.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); linkIn.blur(); } ev.stopPropagation(); });
  body.push(h('label', { class: 'dp-nf' }, h('span', { class: 'dp-nl dp-nowide dp-nlw', title: '링크' }, '링크'), linkIn));

  // 크기 조절
  const measuredPut = (n, v) => {
    const p = P(n), m = meas(n), out = { autoResize: v };
    if (m) {
      if (p.autoResize === 'WIDTH_AND_HEIGHT' && v !== 'WIDTH_AND_HEIGHT') { out.w = round(m.w, 2); if (v !== 'HEIGHT') out.h = round(m.h, 2); }
      else if (p.autoResize === 'HEIGHT' && (v === 'NONE' || v === 'TRUNCATE')) out.h = round(m.h, 2);
    }
    return out;
  };
  body.push(seg({ nodes: tx, label: '텍스트 크기 조절 변경', cur: (n) => P(n).autoResize, put: measuredPut, intercept: nodeKey('autoResize'), items: [{ v: 'WIDTH_AND_HEIGHT', icon: 'arW', title: '자동 너비' }, { v: 'HEIGHT', icon: 'arH', title: '자동 높이' }, { v: 'NONE', icon: 'arFix', title: '고정 크기' }, { v: 'TRUNCATE', icon: 'arTrunc', title: '말줄임' }] }));
  if (tx.every((n) => P(n).autoResize === 'TRUNCATE')) body.push(row(numField({ nodes: tx, text: '최대 줄 수', title: '최대 줄 수 (0 = 제한 없음)', cur: (n) => P(n).maxLines, put: (n, v) => ({ maxLines: Math.max(0, Math.round(v)) }), intercept: nodeKey('maxLines'), label: '최대 줄 수 변경', min: 0, dec: 0 })));
  return section('텍스트', { cls: 'dp-text' }, body);
}

/* ───────────────────────── 조립: 대상 결정, 렌더, 스토어 동기화, 마운트 ───────────────────────── */
const CAP = {
  fills: (t) => !['group', 'line', 'video'].includes(t),
  strokes: (t) => t !== 'group',
  effects: (t) => !['page', 'section'].includes(t),
};
const zcmp = (a, b) => (a.z < b.z ? -1 : a.z > b.z ? 1 : 0);
function currentPage() {
  let c = null;
  try { c = ctx.currentPage && ctx.currentPage(); } catch (e) { /* 무시 */ }
  if (c) { const n = typeof c === 'string' ? nodeById(c) : c; if (n && n.type === 'page') return n; }
  return [...store.nodes.values()].filter((n) => n.type === 'page').sort(zcmp)[0] || null;
}
function targets() {
  const ids = (ctx.selection && ctx.selection.ids) || [];
  const ns = ids.map(nodeById).filter(Boolean);
  if (ns.length) return ns;
  const pg = currentPage();
  return pg ? [pg] : [];
}
// 구조가 바뀌면 전체 재렌더, 같으면 포커스 중 입력만 값 갱신
function signature(ns) {
  const part = (n) => {
    const p = P(n), par = parentOf(n);
    return [n.id, n.type,
      (p.fills || []).map((f) => f.type + (f.visible === false ? 0 : 1)).join(), (p.strokes || []).map((f) => f.type + (f.visible === false ? 0 : 1)).join(), (p.effects || []).map((e) => e.type + (e.visible === false ? 0 : 1)).join(),
      p.layout ? [p.layout.dir, p.layout.wrap, p.layout.alignMain === 'SPACE_BETWEEN', p.layout.alignCross === 'BASELINE', p.layout.sizingH, p.layout.sizingV].join() : '-',
      Array.isArray(p.radius) ? 'a' : 'n', p.stroke ? dashKind(p.stroke) + p.stroke.join + (p.stroke.sides ? sideMode(p.stroke) : '') + p.stroke.align : '',
      p.autoResize, (p.guides || []).length, (p.cols || []).length, (p.rows || []).length, par ? (P(par).layout ? 1 : 0) : '', p.layoutChild && p.layoutChild.absolute, p.preset, p.orientation, p.arc ? 1 : 0,
      n.type === 'text' ? (p.paras || []).map((q) => q.list).join('') : ''].join('|');
  };
  const mixes = ['fills', 'strokes', 'effects', 'guides'].map((k) => allSame(ns.map((n) => P(n)[k] || [])));
  return ns.map(part).join('#') + '#' + mixes.join();
}

function buildSections(ns) {
  const pages = ns.filter((n) => n.type === 'page'), others = ns.filter((n) => n.type !== 'page');
  const pageMode = pages.length > 0 && !others.length;
  const base = pageMode ? pages : others;
  const out = [];
  if (pageMode) out.push(secPage(pages), guidesSection(pages));
  else out.push(secLayout(others));
  out.push(secAuto(base));
  if (!pageMode) {
    out.push(secShape(others));
    const fr = others.filter((n) => n.type === 'frame');
    if (fr.length) out.push(guidesSection(fr));
    out.push(secText(others), secTable(others));
  }
  const f = base.filter((n) => CAP.fills(n.type));
  if (f.length) out.push(paintSection(f, 'fills', pageMode ? '배경' : '채우기'));
  const s = base.filter((n) => CAP.strokes(n.type));
  if (s.length) { const withS = s.filter((n) => paintsOf(n, 'strokes').length); out.push(paintSection(s, 'strokes', '획', withS.length ? strokeExtras(withS) : [])); }
  const e = base.filter((n) => CAP.effects(n.type));
  if (e.length) out.push(effectsSection(e));
  const l = base.filter((n) => CAP.effects(n.type));
  if (l.length) out.push(secLayer(l));
  out.push(secExport(ns));
  return out.filter(Boolean);
}

function render() {
  if (!root) return;
  const sc = root.scrollTop;
  refreshers = [];
  root.textContent = '';
  const ns = targets();
  lastSig = signature(ns);
  if (!ns.length) root.append(h('div', { class: 'dp-empty' }, '선택한 항목이 없습니다'));
  else {
    try { root.append(...buildSections(ns)); } catch (e) { console.error('디자인 패널 렌더 실패', e); root.append(h('div', { class: 'dp-err' }, '패널을 그리지 못했습니다')); }
  }
  root.scrollTop = sc;
}
const softRender = () => render();

let queued = 0;
function schedule() { if (!queued) queued = raf(() => { queued = 0; softRefresh(); }); }
function softRefresh() {
  if (!root) return;
  if (busy) { dirtyWhileBusy = true; return; }
  const sig = signature(targets());
  if (typing(root) && sig === lastSig) refreshers.forEach((r) => r());
  else render();
  if (pop) pop.refresh();
}

export function mountDesignPanel(el, c) {
  if (root) { closePop(); root.remove(); }
  ctx = c; store = c.store; hostEl = el; busy = 0; dirtyWhileBusy = false; pop = null;
  injectStyle();
  import('../text.js').then((m) => { textMod = m; }).catch(() => {});
  import('../layout.js').then((m) => { layoutMod = m; }).catch(() => {});
  root = h('div', { class: 'dp', role: 'region', 'aria-label': '디자인 패널' });
  root.style.overflowY = 'auto'; root.style.height = '100%';
  el.replaceChildren(root);
  const relevant = new Set();
  const offStore = store.subscribe((changed, deleted) => {
    relevant.clear();
    for (const n of targets()) { relevant.add(n.id); if (n.parent) relevant.add(n.parent); }
    const cp = currentPage(); if (cp) relevant.add(cp.id);
    for (const id of [...(changed || []), ...(deleted || [])]) if (relevant.has(id) || (pop && pop.el)) { schedule(); return; }
  });
  const offSel = c.selection && c.selection.on ? c.selection.on(() => { closePop(); render(); }) : null;
  // 텍스트 편집 세션이 시작/종료되면(포커스 이동) 텍스트 섹션 표시를 갱신
  let wasEditing = !!activeEdit(targets());
  const onFocus = () => { const now = !!activeEdit(targets()); if (now !== wasEditing) { wasEditing = now; if (!busy) render(); } };
  document.addEventListener('focusin', onFocus); document.addEventListener('focusout', onFocus);
  // 글자 편집 중 캐럿/선택이 바뀌면 글자 스타일 필드 값을 갱신 (포커스 중인 입력은 건드리지 않음)
  let selQ = 0;
  const onSelChange = () => { if (selQ || !wasEditing || busy) return; selQ = raf(() => { selQ = 0; if (root && !typing(root)) refreshers.forEach((r) => r()); }); };
  document.addEventListener('selectionchange', onSelChange);
  render();
  return {
    destroy() {
      closePop();
      try { offStore && offStore(); } catch (e) { /* 무시 */ }
      try { typeof offSel === 'function' && offSel(); } catch (e) { /* 무시 */ }
      document.removeEventListener('focusin', onFocus); document.removeEventListener('focusout', onFocus); document.removeEventListener('selectionchange', onSelChange);
      if (queued) cancelAnimationFrame(queued);
      queued = 0; root && root.remove(); root = null; ctx = null; store = null; refreshers = [];
    },
  };
}
