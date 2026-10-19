// Text: DOM building from runs (used by render.js) and the in-place editing session.
// Text is never HTML: every string goes through textContent / createTextNode.
//
// Line breaks: Enter starts a new paragraph ("\n", contract §1.1). Shift+Enter inserts a soft line
// break inside the same paragraph, stored as U+2028 (LINE SEPARATOR) so paragraphs stay "\n"-only.

import { defaultsFor } from './schema.js';

export const LS = '\u2028';
const FALLBACK = '"Apple SD Gothic Neo", "Noto Sans KR", "Noto Sans CJK KR", "Pretendard", "Malgun Gothic", system-ui, sans-serif';  // Mac first; Linux ships Noto Sans CJK KR
const BULLETS = ['•', '◦', '▪'];

export function fontStack(name) {
  const f = String(name || 'Inter').replace(/["\\;{}<>]/g, '');
  return `"${f}", ${FALLBACK}`;
}

export function rgba(hex, op = 1) {
  const m = /^#?([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(hex || '');
  if (!m) return 'rgba(0,0,0,0)';
  const n = parseInt(m[1], 16), a = (m[2] ? parseInt(m[2], 16) / 255 : 1) * op;
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${Math.round(a * 1000) / 1000})`;
}

// TextStyle (partial ok) → CSS declarations object.
export function styleCSS(s) {
  const c = {};
  if (!s) return c;
  if (s.font !== undefined) c.fontFamily = fontStack(s.font);
  if (s.weight !== undefined) c.fontWeight = String(s.weight);
  if (s.italic !== undefined) c.fontStyle = s.italic ? 'italic' : 'normal';
  if (s.size !== undefined) c.fontSize = s.size + 'px';
  if (s.lineHeight) {
    const { unit, value } = s.lineHeight;
    c.lineHeight = unit === 'PX' ? value + 'px' : unit === 'PERCENT' ? String(value / 100) : 'normal';
  }
  if (s.letterSpacing) {
    const { unit, value } = s.letterSpacing;
    c.letterSpacing = unit === 'PX' ? value + 'px' : value / 100 + 'em';
  }
  if (s.decoration !== undefined) c.textDecorationLine = s.decoration === 'UNDERLINE' ? 'underline' : s.decoration === 'STRIKETHROUGH' ? 'line-through' : 'none';
  if (s.case !== undefined) {
    c.textTransform = { UPPER: 'uppercase', LOWER: 'lowercase', TITLE: 'capitalize' }[s.case] || 'none';
    c.fontVariantCaps = s.case === 'SMALL_CAPS' ? 'small-caps' : 'normal';
  }
  return c;
}

// Approximate px line height of a style (for line clamping math).
export function lineHeightPx(s) {
  const lh = s?.lineHeight, size = s?.size || 24;
  if (lh?.unit === 'PX') return lh.value;
  if (lh?.unit === 'PERCENT') return (size * lh.value) / 100;
  return size * 1.21;
}

// runs → paragraphs of segments [{t, r}] (r = run index).
export function paragraphsOf(runs) {
  const paras = [[]];
  (runs || []).forEach((run, r) => {
    const parts = String(run.t ?? '').split('\n');
    parts.forEach((t, i) => {
      if (i) paras.push([]);
      if (t) paras[paras.length - 1].push({ t, r });
    });
  });
  return paras;
}

export const textOf = (runs) => (runs || []).map((r) => r.t ?? '').join('');

function markerText(list, level, n) {
  if (list === 'BULLET') return BULLETS[level % 3];
  const k = level % 3;
  if (k === 1) { let s = '', v = n; while (v > 0) { v--; s = String.fromCharCode(97 + (v % 26)) + s; v = Math.floor(v / 26); } return s + '.'; }
  if (k === 2) return roman(n) + '.';
  return n + '.';
}
function roman(n) {
  const t = [[1000, 'm'], [900, 'cm'], [500, 'd'], [400, 'cd'], [100, 'c'], [90, 'xc'], [50, 'l'], [40, 'xl'], [10, 'x'], [9, 'ix'], [5, 'v'], [4, 'iv'], [1, 'i']];
  let s = '';
  for (const [v, r] of t) while (n >= v) { s += r; n -= v; }
  return s;
}

const SAFE_LINK = /^(https?:|mailto:)/i;

// Fill `tx` with paragraph divs. p = {runs, paras, paragraphSpacing, indent}; opts.links = real <a>.
export function renderText(tx, p, opts = {}) {
  tx.textContent = '';
  const runs = p.runs || [];
  const paras = paragraphsOf(runs);
  const counters = [];
  paras.forEach((segs, i) => {
    const info = (p.paras || [])[i] || {};
    const list = info.list || 'NONE', level = Math.max(0, Math.min(8, info.level | 0));
    const div = document.createElement('div');
    div.className = 'ppt-p';
    div.dataset.list = list;
    div.dataset.level = String(level);
    if (i < paras.length - 1 && p.paragraphSpacing) div.style.marginBottom = p.paragraphSpacing + 'px';
    if (list !== 'NONE') {
      counters.length = level + 1;
      if (list === 'ORDERED') counters[level] = (counters[level] || 0) + 1;
      else counters[level] = 0;
      div.style.paddingLeft = (level + 1) * 1.5 + 'em';
      const mk = document.createElement('span');
      mk.className = 'ppt-mk';
      mk.contentEditable = 'false';
      mk.textContent = markerText(list, level, counters[level] || 1);
      div.appendChild(mk);
    } else {
      counters.length = 0;
      if (level) div.style.paddingLeft = level * 1.5 + 'em';
      if (p.indent) div.style.textIndent = p.indent + 'px';
    }
    let endsWithBreak = !segs.length;
    for (const seg of segs) {
      const run = runs[seg.r] || {};
      const href = opts.links && run.link && SAFE_LINK.test(run.link) ? run.link : null;
      const span = document.createElement(href ? 'a' : 'span');
      span.dataset.r = String(seg.r);
      if (href) { span.href = href; span.target = '_blank'; span.rel = 'noopener noreferrer'; }
      Object.assign(span.style, styleCSS(run.s));
      if (run.fill) { span.style.color = rgba(run.fill); span.style.webkitTextFillColor = rgba(run.fill); }
      if (run.link) { span.style.textDecorationLine = 'underline'; span.dataset.link = run.link; }
      const lines = seg.t.split(LS);
      lines.forEach((ln, k) => {
        if (k) span.appendChild(document.createElement('br'));
        if (ln) span.appendChild(document.createTextNode(ln));
      });
      endsWithBreak = seg.t.endsWith(LS);
      div.appendChild(span);
    }
    if (endsWithBreak) { const br = document.createElement('br'); br.dataset.ph = '1'; div.appendChild(br); }
    tx.appendChild(div);
  });
}

// ---------------- editing ----------------

let session = null;
export const activeTextEdit = () => session;
export const editingId = () => session?.id ?? null;

const clone = (v) => JSON.parse(JSON.stringify(v ?? null));
const sameStyle = (a, b) => JSON.stringify(a.s || null) === JSON.stringify(b.s || null) && (a.fill || null) === (b.fill || null) && (a.link || null) === (b.link || null);

function normalizeRuns(runs) {
  const out = [];
  for (const r of runs) {
    if (!r.t) continue;
    const last = out[out.length - 1];
    if (last && sameStyle(last, r)) last.t += r.t;
    else out.push({ ...r });
  }
  if (!out.length) out.push({ t: '', ...(runs[0] ? styleOnly(runs[0]) : {}) });
  return out;
}
function styleOnly(r) { const o = {}; if (r.s) o.s = r.s; if (r.fill) o.fill = r.fill; if (r.link) o.link = r.link; return o; }

// Split runs so that offsets a and b fall on run boundaries; returns new array.
function splitAt(runs, offs) {
  let out = runs.map((r) => ({ ...r }));
  for (const o of offs) {
    const next = [];
    let pos = 0;
    for (const r of out) {
      const len = r.t.length;
      if (o > pos && o < pos + len) {
        next.push({ ...r, t: r.t.slice(0, o - pos) }, { ...r, t: r.t.slice(o - pos) });
      } else next.push(r);
      pos += len;
    }
    out = next;
  }
  return out;
}

function styleAtOffset(runs, o) {
  let pos = 0, prev = runs[0];
  for (const r of runs) {
    if (o > pos && o <= pos + r.t.length) return r;
    if (o === pos && r.t.length && pos === 0) return r;
    pos += r.t.length;
    if (r.t.length) prev = r;
  }
  return prev || {};
}

function replaceRange(runs, a, b, text) {
  const style = styleOnly(styleAtOffset(runs, a) || {});
  const parts = splitAt(runs, [a, b]);
  const out = [];
  let pos = 0, inserted = false;
  for (const r of parts) {
    const len = r.t.length;
    if (pos >= a && pos + len <= b && len) { pos += len; if (!inserted) { out.push({ ...style, t: text }); inserted = true; } continue; }
    if (!inserted && pos >= a) { out.push({ ...style, t: text }); inserted = true; }
    out.push(r);
    pos += len;
  }
  if (!inserted) out.push({ ...style, t: text });
  return normalizeRuns(out);
}

const paraIndexAt = (text, o) => (text.slice(0, o).match(/\n/g) || []).length;

// opts: {cell: "r,c", point: {x, y} (client coords for the caret), select: 'all' | 'end'}
export function beginTextEdit(id, ctx, opts = {}) {
  if (session) session.end();
  const { store, renderer } = ctx;
  const node = store.nodes.get(id);
  const el = renderer.elementOf(id);
  if (!node || !el) return { end() {} };
  const cellKey = opts.cell || null;
  const tx = cellKey ? el.querySelector(`[data-cell="${CSS.escape(cellKey)}"] .ppt-tx`) : el.querySelector(':scope > .ppt-tx');
  if (!tx) return { end() {} };
  const props = node.props || {};
  const cell = cellKey ? (props.cells || {})[cellKey] || {} : null;
  const orig = { runs: clone(cellKey ? cell.runs || [{ t: '' }] : props.runs || [{ t: '' }]), paras: clone(cellKey ? [] : props.paras || []) };
  const model = { runs: clone(orig.runs), paras: clone(orig.paras) };
  const nodeChanges = {};
  const baseP = () => ({ runs: model.runs, paras: model.paras, paragraphSpacing: props.paragraphSpacing, indent: props.indent });

  let composing = false, pendingBreak = null, savedSel = [0, 0], ended = false;
  const undo = [], redo = [];
  let lastPush = 0;

  // DOM → model
  function sync() {
    const runs = [], paras = [];
    const blocks = [...tx.childNodes];
    const kids = blocks.length ? blocks : [];
    let pi = 0;
    for (const b of kids) {
      const isBlock = b.nodeType === 1 && b.classList.contains('ppt-p');
      if (pi > 0) runs.push({ ...(runs.length ? styleOnly(runs[runs.length - 1]) : {}), t: '\n' });
      if (isBlock) paras.push({ list: b.dataset.list || 'NONE', level: +b.dataset.level || 0 });
      else paras.push({ list: 'NONE', level: 0 });
      collect(b, runs);
      pi++;
    }
    if (!kids.length) runs.push({ t: '' });
    model.runs = normalizeRuns(runs);
    model.paras = paras.some((p) => p.list !== 'NONE' || p.level) ? paras : [];
  }
  // Style of a DOM text node: its run span, else the run before it (typing into an empty paragraph).
  function runOf(n, runs) {
    const sp = n.parentElement?.closest('[data-r]');
    const r = sp && tx.contains(sp) ? lastRender[+sp.dataset.r] : null;
    if (r) return styleOnly(r);
    const prev = runs[runs.length - 1];
    return prev ? styleOnly(prev) : lastRender[0] ? styleOnly(lastRender[0]) : {};
  }
  function collect(root, runs) {
    const nodes = [];
    const walk = (n) => {
      if (n.nodeType === 3) nodes.push(n);
      else if (n.nodeType === 1) {
        if (n.classList?.contains('ppt-mk')) return;
        if (n.tagName === 'BR') { nodes.push(n); return; }
        for (const c of n.childNodes) walk(c);
      }
    };
    walk(root);
    nodes.forEach((n, i) => {
      if (n.nodeType === 3) runs.push({ ...runOf(n, runs), t: n.data.replace(/\n/g, LS) });
      else if (i < nodes.length - 1) runs.push({ ...runOf(n, runs), t: LS });
    });
  }
  // DOM point ↔ text offset, mirroring collect()
  function pieces() {
    const out = [];
    let pos = 0;
    [...tx.childNodes].forEach((b, bi) => {
      if (bi) pos += 1;
      const nodes = [];
      const walk = (n) => {
        if (n.nodeType === 3) nodes.push(n);
        else if (n.nodeType === 1) { if (n.classList?.contains('ppt-mk')) return; if (n.tagName === 'BR') { nodes.push(n); return; } for (const c of n.childNodes) walk(c); }
      };
      walk(b);
      out.push({ block: b, start: pos });
      nodes.forEach((n, i) => {
        const len = n.nodeType === 3 ? n.data.length : i < nodes.length - 1 ? 1 : 0;
        out.push({ node: n, start: pos, len });
        pos += len;
      });
    });
    return { list: out, total: pos };
  }
  function toOffset(container, offset) {
    const { list } = pieces();
    const r = document.createRange();
    try { r.setStart(container, offset); } catch { return savedSel[0]; }
    let best = 0;
    for (const p of list) {
      if (!p.node) {
        if (r.comparePoint(p.block, 0) === 1) return best;
        best = p.start;
        continue;
      }
      if (p.node === container && container.nodeType === 3) return p.start + Math.min(offset, p.len);
      const end = p.node.nodeType === 3 ? [p.node, p.node.length] : [p.node.parentNode, [...p.node.parentNode.childNodes].indexOf(p.node) + 1];
      if (r.comparePoint(end[0], end[1]) <= 0) best = p.start + p.len;
      else return best;
    }
    return best;
  }
  function getSel() {
    const s = getSelection();
    if (!s.rangeCount || !tx.contains(s.anchorNode)) return savedSel;
    const r = s.getRangeAt(0);
    const a = toOffset(r.startContainer, r.startOffset), b = toOffset(r.endContainer, r.endOffset);
    return [Math.min(a, b), Math.max(a, b)];
  }
  function domPoint(o) {
    const { list } = pieces();
    let cand = null;
    for (const p of list) {
      if (!p.node) {
        if (p.start === o && !cand) cand = [p.block, p.block.firstChild?.classList?.contains('ppt-mk') ? 1 : 0];
        continue;
      }
      if (p.node.nodeType === 3) { if (o >= p.start && o <= p.start + p.len) return [p.node, o - p.start]; continue; }
      const par = p.node.parentNode, i = [...par.childNodes].indexOf(p.node);
      if (o === p.start) return [par, i];
      if (o === p.start + p.len) cand = [par, i + 1];
    }
    if (cand) return cand;
    const b = tx.lastChild || tx;
    return [b, b.childNodes.length];
  }
  function setSel(a, b = a) {
    savedSel = [a, b];
    if (document.activeElement !== tx && !tx.contains(document.activeElement)) { paintHighlight(); return; }
    const s = getSelection(), r = document.createRange();
    try { r.setStart(...domPoint(a)); r.setEnd(...domPoint(b)); s.removeAllRanges(); s.addRange(r); } catch { /* stale DOM */ }
  }
  let lastRender = model.runs;
  function rerender(sel) {
    lastRender = model.runs;
    renderText(tx, baseP());
    if (sel) setSel(sel[0], sel[1]);
  }
  function snapshot() { return { runs: clone(model.runs), paras: clone(model.paras), sel: getSel() }; }
  function pushUndo(force) {
    const now = Date.now();
    if (!force && now - lastPush < 600) return;
    lastPush = now;
    undo.push(snapshot());
    if (undo.length > 100) undo.shift();
    redo.length = 0;
  }
  function restore(snap) { model.runs = snap.runs; model.paras = snap.paras; rerender(snap.sel); }

  function insertText(text, newParaInfo) {
    sync();
    pushUndo(true);
    const [a, b] = getSel();
    const full = textOf(model.runs);
    const pa = paraIndexAt(full, a), pb = paraIndexAt(full, b);
    model.runs = replaceRange(model.runs, a, b, text);
    const nl = (text.match(/\n/g) || []).length;
    if (model.paras.length || newParaInfo) {
      const cur = model.paras[pa] || {};
      const kept = model.paras.slice(0, pa + 1).concat(Array(nl).fill(0).map(() => ({ ...cur })), model.paras.slice(pb + 1));
      model.paras = kept;
    }
    rerender([a + text.length, a + text.length]);
  }

  function applyStyle(partial) {
    if (ended) return;
    if (composing) return;
    sync();
    pushUndo(true);
    let [a, b] = savedSel;
    const total = textOf(model.runs).length;
    if (a === b) { a = 0; b = total; }
    const node2 = {};
    for (const k of ['alignH', 'alignV', 'paragraphSpacing', 'indent', 'autoResize', 'maxLines']) if (k in partial) node2[k] = partial[k];
    Object.assign(nodeChanges, node2);
    const runPart = { ...partial };
    for (const k of Object.keys(node2)) delete runPart[k];
    if (Object.keys(runPart).length) {
      const parts = splitAt(model.runs, [a, b]);
      let pos = 0;
      for (const r of parts) {
        const len = r.t.length;
        if (pos >= a && pos + len <= b && (len || total === 0)) {
          if ('fill' in runPart) { if (runPart.fill) r.fill = runPart.fill; else delete r.fill; }
          if ('link' in runPart) { if (runPart.link) r.link = runPart.link; else delete r.link; }
          const s = { ...(r.s || {}) };
          for (const [k, v] of Object.entries(runPart)) if (k !== 'fill' && k !== 'link') { if (v === null) delete s[k]; else s[k] = v; }
          if (Object.keys(s).length) r.s = s; else delete r.s;
        }
        pos += len;
      }
      model.runs = normalizeRuns(parts);
    }
    if (Object.keys(node2).length) ctx.preview?.(id, node2);
    rerender([savedSel[0], savedSel[1]]);
  }

  // Current style at the caret/selection start (merged over the base style), for the panel.
  function currentStyle() {
    const r = styleAtOffset(model.runs, savedSel[0]) || {};
    return { ...defaultsFor('text').style, ...(props.style || {}), ...(r.s || {}), fill: r.fill || null };
  }

  function toggleList(kind) {
    sync();
    pushUndo(true);
    const full = textOf(model.runs);
    const [a, b] = savedSel;
    const pa = paraIndexAt(full, a), pb = paraIndexAt(full, b);
    const count = full.split('\n').length;
    const paras = Array.from({ length: count }, (_, i) => ({ list: 'NONE', level: 0, ...(model.paras[i] || {}) }));
    const all = paras.slice(pa, pb + 1).every((p) => p.list === kind);
    for (let i = pa; i <= pb; i++) paras[i].list = all ? 'NONE' : kind;
    model.paras = paras.some((p) => p.list !== 'NONE' || p.level) ? paras : [];
    rerender([a, b]);
  }
  function shiftLevel(delta) {
    sync();
    const full = textOf(model.runs);
    const [a, b] = getSel();
    const pa = paraIndexAt(full, a), pb = paraIndexAt(full, b);
    const count = full.split('\n').length;
    const paras = Array.from({ length: count }, (_, i) => ({ list: 'NONE', level: 0, ...(model.paras[i] || {}) }));
    if (!paras.slice(pa, pb + 1).some((p) => p.list !== 'NONE')) return false;
    pushUndo(true);
    for (let i = pa; i <= pb; i++) paras[i].level = Math.max(0, Math.min(8, paras[i].level + delta));
    model.paras = paras;
    rerender([a, b]);
    return true;
  }

  // Step a numeric style key for the current range.
  function stepStyle(key, delta) {
    sync();
    savedSel = getSel();
    const cur = currentStyle();
    if (key === 'size') applyStyle({ size: Math.max(1, (cur.size || 24) + delta) });
    else if (key === 'weight') applyStyle({ weight: Math.max(100, Math.min(900, (cur.weight || 400) + delta * 100)) });
    else if (key === 'lineHeight') {
      const lh = cur.lineHeight || { unit: 'AUTO', value: 0 };
      const v = lh.unit === 'AUTO' ? { unit: 'PERCENT', value: 120 + delta } : { unit: lh.unit, value: Math.max(0, lh.value + delta) };
      applyStyle({ lineHeight: v });
    } else if (key === 'letterSpacing') {
      const ls = cur.letterSpacing || { unit: 'PERCENT', value: 0 };
      applyStyle({ letterSpacing: { unit: ls.unit, value: Math.round((ls.value + delta * (ls.unit === 'PX' ? 0.1 : 1)) * 100) / 100 } });
    }
  }
  function toggle(key, on, off) {
    sync();
    savedSel = getSel();
    const cur = currentStyle();
    applyStyle({ [key]: cur[key] === on ? off : on });
  }

  function onKey(e) {
    e.stopPropagation();
    if (e.isComposing || composing) return;
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === 'Escape') { e.preventDefault(); api.end(); return; }
    if (e.key === 'Enter' && !mod) { e.preventDefault(); insertText(e.shiftKey ? LS : '\n', !e.shiftKey); return; }
    if (mod && !e.shiftKey && e.code === 'KeyZ') { e.preventDefault(); sync(); if (undo.length) { redo.push(snapshot()); restore(undo.pop()); } return; }
    if (mod && ((e.shiftKey && e.code === 'KeyZ') || e.code === 'KeyY')) { e.preventDefault(); if (redo.length) { undo.push(snapshot()); restore(redo.pop()); } return; }
    if (mod && !e.shiftKey && !e.altKey && e.code === 'KeyB') { e.preventDefault(); toggle('weight', 700, 400); return; }
    if (mod && !e.shiftKey && !e.altKey && e.code === 'KeyI') { e.preventDefault(); toggle('italic', true, false); return; }
    if (mod && !e.shiftKey && !e.altKey && e.code === 'KeyU') { e.preventDefault(); toggle('decoration', 'UNDERLINE', 'NONE'); return; }
    if (mod && e.shiftKey && e.code === 'KeyX') { e.preventDefault(); toggle('decoration', 'STRIKETHROUGH', 'NONE'); return; }
    if (mod && e.shiftKey && (e.code === 'Digit7' || e.code === 'Digit8')) { e.preventDefault(); savedSel = getSel(); toggleList(e.code === 'Digit7' ? 'ORDERED' : 'BULLET'); return; }
    if (mod && e.altKey && ['KeyL', 'KeyT', 'KeyR', 'KeyJ'].includes(e.code)) {
      e.preventDefault();
      applyStyle({ alignH: { KeyL: 'LEFT', KeyT: 'CENTER', KeyR: 'RIGHT', KeyJ: 'JUSTIFIED' }[e.code] });
      return;
    }
    const dir = e.code === 'Period' ? 1 : e.code === 'Comma' ? -1 : 0;
    if (dir) {
      if (mod && e.shiftKey && !e.altKey) { e.preventDefault(); stepStyle('size', dir); return; }
      if (mod && e.altKey && !e.shiftKey) { e.preventDefault(); stepStyle('weight', dir); return; }
      if (e.altKey && e.shiftKey && !mod) { e.preventDefault(); stepStyle('lineHeight', dir); return; }
      if (e.altKey && !e.shiftKey && !mod) { e.preventDefault(); stepStyle('letterSpacing', dir); return; }
    }
    if (e.key === 'Tab' && !mod) { if (shiftLevel(e.shiftKey ? -1 : 1)) e.preventDefault(); else { e.preventDefault(); insertText('\t'); } return; }
    if (mod && e.code === 'KeyA') { e.preventDefault(); sync(); setSel(0, textOf(model.runs).length); }
  }
  function onBeforeInput(e) {
    const t = e.inputType;
    if (t === 'insertParagraph' || t === 'insertLineBreak') {
      e.preventDefault();
      const txt = t === 'insertParagraph' ? '\n' : LS;
      if (composing || e.isComposing) pendingBreak = txt;
      else insertText(txt, t === 'insertParagraph');
      return;
    }
    if (t === 'insertFromPaste' || t === 'insertFromDrop') return; // handled by paste/drop
    if (t === 'historyUndo' || t === 'historyRedo' || t.startsWith('format')) { e.preventDefault(); return; }
    pushUndo(false);
  }
  function onPaste(e) {
    e.preventDefault();
    const text = (e.clipboardData?.getData('text/plain') || '').replace(/\r\n?/g, '\n');
    if (text) insertText(text, text.includes('\n'));
  }
  function onDrop(e) {
    e.preventDefault();
    const text = (e.dataTransfer?.getData('text/plain') || '').replace(/\r\n?/g, '\n');
    if (text) insertText(text, text.includes('\n'));
  }
  const onCompStart = () => { composing = true; };
  const onCompEnd = () => {
    composing = false;
    if (pendingBreak) { const b = pendingBreak; pendingBreak = null; setTimeout(() => { if (!ended) insertText(b, b === '\n'); }); }
  };
  const onSelChange = () => {
    const s = getSelection();
    if (s.rangeCount && tx.contains(s.anchorNode) && !composing) savedSel = getSel();
  };
  const onBlur = () => paintHighlight();
  const onFocus = () => { try { CSS.highlights?.delete('ppt-text-sel'); } catch { /* unsupported */ } };
  function paintHighlight() {
    try {
      if (!CSS.highlights || savedSel[0] === savedSel[1]) return;
      const r = document.createRange();
      r.setStart(...domPoint(savedSel[0])); r.setEnd(...domPoint(savedSel[1]));
      CSS.highlights.set('ppt-text-sel', new Highlight(r));
    } catch { /* stale */ }
  }
  const root = renderer.root || el.closest('.ppt-root') || document;
  const onDown = (e) => {
    if (tx.contains(e.target)) return;
    if (root.contains(e.target) || e.target === root) api.end();
  };

  tx.contentEditable = 'plaintext-only';
  if (tx.contentEditable !== 'plaintext-only') tx.contentEditable = 'true';
  tx.spellcheck = false;
  tx.classList.add('ppt-editing');
  el.classList.add('ppt-editing-node');
  tx.addEventListener('keydown', onKey);
  tx.addEventListener('beforeinput', onBeforeInput);
  tx.addEventListener('paste', onPaste);
  tx.addEventListener('drop', onDrop);
  tx.addEventListener('compositionstart', onCompStart);
  tx.addEventListener('compositionend', onCompEnd);
  tx.addEventListener('blur', onBlur);
  tx.addEventListener('focus', onFocus);
  document.addEventListener('selectionchange', onSelChange);
  document.addEventListener('pointerdown', onDown, true);
  // stop canvas tools from reacting to clicks/drags inside the editor
  const stop = (e) => e.stopPropagation();
  tx.addEventListener('pointerdown', stop);
  tx.addEventListener('dblclick', stop);

  rerender(null);
  tx.focus({ preventScroll: true });
  let placed = false;
  if (opts.point && document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(opts.point.x, opts.point.y);
    if (r && tx.contains(r.startContainer)) { const s = getSelection(); s.removeAllRanges(); s.addRange(r); savedSel = getSel(); placed = true; }
  }
  if (!placed) {
    const n = textOf(model.runs).length;
    if (opts.select === 'end') setSel(n, n); else setSel(0, n);
  }

  const api = {
    id, cell: cellKey,
    applyStyle, toggleList, currentStyle,
    get composing() { return composing; },
    end() {
      if (ended) return;
      sync();
      ended = true;
      session = null;
      tx.removeEventListener('keydown', onKey);
      tx.removeEventListener('beforeinput', onBeforeInput);
      tx.removeEventListener('paste', onPaste);
      tx.removeEventListener('drop', onDrop);
      tx.removeEventListener('compositionstart', onCompStart);
      tx.removeEventListener('compositionend', onCompEnd);
      tx.removeEventListener('blur', onBlur);
      tx.removeEventListener('focus', onFocus);
      tx.removeEventListener('pointerdown', stop);
      tx.removeEventListener('dblclick', stop);
      document.removeEventListener('selectionchange', onSelChange);
      document.removeEventListener('pointerdown', onDown, true);
      try { CSS.highlights?.delete('ppt-text-sel'); } catch { /* unsupported */ }
      tx.removeAttribute('contenteditable');
      tx.classList.remove('ppt-editing');
      el.classList.remove('ppt-editing-node');
      if (tx.contains(document.activeElement)) document.activeElement.blur();
      getSelection().removeAllRanges();
      // lets the editor shell clear its own edit state when Esc / click-outside ended the session
      window.dispatchEvent(new CustomEvent('ppt:text-edit-end', { detail: { id, cell: cellKey } }));

      const runs = model.runs;
      const changed = JSON.stringify(runs) !== JSON.stringify(orig.runs) || JSON.stringify(model.paras) !== JSON.stringify(orig.paras) || Object.keys(nodeChanges).length;
      // measure before the store re-renders (auto-sized geometry is written back once)
      const p0 = { ...props, ...nodeChanges };
      const ar = p0.autoResize || 'WIDTH_AND_HEIGHT';
      const mw = Math.round(el.offsetWidth * 100) / 100, mh = Math.round(el.offsetHeight * 100) / 100;
      if (Object.keys(nodeChanges).length) ctx.clearPreview?.(id);
      if (!changed) { renderer.update([id], []); return; }
      if (cellKey) {
        const cells = { ...(props.cells || {}), [cellKey]: { ...cell, runs } };
        ctx.commit([{ op: 'set', id, props: { cells } }], '표 셀 편집');
        return;
      }
      if (!textOf(runs).trim() && !opts.keepEmpty) {
        ctx.commit([{ op: 'del', id }], '텍스트 삭제');
        return;
      }
      const set = { runs, ...nodeChanges };
      if (JSON.stringify(model.paras) !== JSON.stringify(orig.paras)) set.paras = model.paras;
      if (ar === 'WIDTH_AND_HEIGHT') {
        const ow = props.w ?? mw;
        set.w = mw; set.h = mh;
        const al = p0.alignH || 'LEFT';
        if (al === 'CENTER') set.x = Math.round(((props.x || 0) - (mw - ow) / 2) * 100) / 100;
        else if (al === 'RIGHT') set.x = Math.round(((props.x || 0) - (mw - ow)) * 100) / 100;
      } else if (ar === 'HEIGHT') set.h = mh;
      ctx.commit([{ op: 'set', id, props: set }], '텍스트 편집');
    },
  };
  session = api;
  return api;
}
