// Shape geometry: SVG path builders, path parsing/flattening, booleans (polygon-clipping),
// flatten and outline-stroke conversions. All paths are in the node's own box coordinates.
import { propsOf } from './schema.js';

const TOL = 0.25; // flattening tolerance, px
const R2 = (v) => Math.round(v * 100) / 100;
const pc = () => globalThis.polygonClipping;

// ---------- builders ----------

// Regular polygon / star points, scaled so the outer points' bounds fill the w×h box.
function fitPoints(raw, outerCount, w, h) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < raw.length; i++) {
    if (i % (raw.length / outerCount) !== 0) continue;
    const [x, y] = raw[i];
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
  }
  const sx = w / (x1 - x0 || 1), sy = h / (y1 - y0 || 1);
  return raw.map(([x, y]) => [(x - x0) * sx, (y - y0) * sy]);
}

// Closed polygon with every corner rounded by radius r (circular arcs, tangent length clamped).
export function roundedPolyD(pts, r) {
  const n = pts.length;
  if (!r || r <= 0) return 'M' + pts.map((p) => R2(p[0]) + ' ' + R2(p[1])).join('L') + 'Z';
  let d = '';
  for (let i = 0; i < n; i++) {
    const P = pts[i], A = pts[(i - 1 + n) % n], B = pts[(i + 1) % n];
    const ax = A[0] - P[0], ay = A[1] - P[1], bx = B[0] - P[0], by = B[1] - P[1];
    const la = Math.hypot(ax, ay) || 1, lb = Math.hypot(bx, by) || 1;
    const cos = Math.max(-1, Math.min(1, (ax * bx + ay * by) / (la * lb)));
    const th = Math.acos(cos);
    const tanHalf = Math.tan(th / 2) || 1e-9;
    let t = r / tanHalf;
    const tMax = Math.min(la, lb) / 2;
    let rr = r;
    if (t > tMax) { t = tMax; rr = t * tanHalf; }
    const T1 = [P[0] + (ax / la) * t, P[1] + (ay / la) * t];
    const T2 = [P[0] + (bx / lb) * t, P[1] + (by / lb) * t];
    const cross = (P[0] - A[0]) * (B[1] - P[1]) - (P[1] - A[1]) * (B[0] - P[0]);
    d += (i ? 'L' : 'M') + R2(T1[0]) + ' ' + R2(T1[1]);
    d += `A${R2(rr)} ${R2(rr)} 0 0 ${cross > 0 ? 1 : 0} ${R2(T2[0])} ${R2(T2[1])}`;
  }
  return d + 'Z';
}

export function polygonPoints(n, w, h) {
  const raw = [];
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    raw.push([Math.cos(a), Math.sin(a)]);
  }
  return fitPoints(raw, n, w, h);
}

export function polygonD(n, w, h, r = 0) {
  return roundedPolyD(polygonPoints(Math.max(3, n | 0), w, h), r);
}

export function starPoints(n, inner, w, h) {
  const raw = [];
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const b = a + Math.PI / n;
    raw.push([Math.cos(a), Math.sin(a)], [Math.cos(b) * inner, Math.sin(b) * inner]);
  }
  return fitPoints(raw, n, w, h);
}

export function starD(n, inner, w, h, r = 0) {
  return roundedPolyD(starPoints(Math.max(3, n | 0), Math.max(0.001, inner), w, h), r);
}

// Ellipse with arc (start/end radians, 0 = +x, clockwise) and inner ratio → ellipse, pie or donut.
export function arcD(arc, w, h) {
  const rx = w / 2, ry = h / 2, cx = rx, cy = ry;
  const start = arc?.start ?? 0, end = arc?.end ?? Math.PI * 2, inner = arc?.inner ?? 0;
  let sweep = end - start;
  const full = Math.abs(sweep) >= Math.PI * 2 - 1e-6;
  const pt = (t, k) => R2(cx + rx * k * Math.cos(t)) + ' ' + R2(cy + ry * k * Math.sin(t));
  const ellipse = (k, cw) => {
    const a = R2(rx * k), b = R2(ry * k), f = cw ? 1 : 0;
    return `M${pt(start, k)}A${a} ${b} 0 1 ${f} ${pt(start + Math.PI, k)}A${a} ${b} 0 1 ${f} ${pt(start, k)}Z`;
  };
  if (full) return inner > 0 ? ellipse(1, true) + ellipse(inner, false) : ellipse(1, true);
  if (sweep < 0) sweep += Math.PI * 2 * Math.ceil(-sweep / (Math.PI * 2));
  const e = start + sweep, large = sweep > Math.PI ? 1 : 0;
  let d = `M${pt(start, 1)}A${R2(rx)} ${R2(ry)} 0 ${large} 1 ${pt(e, 1)}`;
  if (inner > 0) d += `L${pt(e, inner)}A${R2(rx * inner)} ${R2(ry * inner)} 0 ${large} 0 ${pt(start, inner)}Z`;
  else d += `L${R2(cx)} ${R2(cy)}Z`;
  return d;
}

export function radiiOf(radius, w, h) {
  const r = Array.isArray(radius) ? radius : [radius || 0, radius || 0, radius || 0, radius || 0];
  const max = Math.min(w, h) / 2;
  return r.map((v) => Math.max(0, Math.min(+v || 0, max)));
}

// Rounded rect with per-corner radii; smoothing > 0 gives the continuous-curvature "squircle"
// corner (arc shortened, joined to the edges by two cubic segments, per the published math).
export function smoothRectD(w, h, radius, smoothing = 0) {
  const [tl, tr, br, bl] = radiiOf(radius, w, h);
  const budget = Math.min(w, h) / 2;
  const K = [[w, 0, 1, 0, 0, 1, tr], [w, h, 0, 1, -1, 0, br], [0, h, -1, 0, 0, -1, bl], [0, 0, 0, -1, 1, 0, tl]];
  const startP = corner(tl, smoothing, budget).p;
  let d = `M${R2(startP)} 0`;
  for (const [kx, ky, ux, uy, vx, vy, R] of K) {
    const c = corner(R, smoothing, budget);
    const sx = kx - ux * c.p, sy = ky - uy * c.p;
    d += `L${R2(sx)} ${R2(sy)}`;
    if (!R) continue;
    const P = (du, dv) => R2(sx + ux * du + vx * dv) + ' ' + R2(sy + uy * du + vy * dv);
    if (c.s <= 0) { d += `A${R2(R)} ${R2(R)} 0 0 1 ${P(R, R)}`; continue; }
    const { a, b, cc, dd, arc } = c;
    d += `C${P(a, 0)} ${P(a + b, 0)} ${P(a + b + cc, dd)}`;
    const u2 = a + b + cc + arc, v2 = dd + arc;
    d += `A${R2(R)} ${R2(R)} 0 0 1 ${P(u2, v2)}`;
    d += `C${P(u2 + dd, v2 + cc)} ${P(u2 + dd, v2 + b + cc)} ${P(u2 + dd, v2 + a + b + cc)}`;
  }
  return d + 'Z';
}

function corner(R, s, budget) {
  if (!R) return { p: 0, s: 0 };
  s = Math.max(0, Math.min(1, s || 0));
  let p = (1 + s) * R;
  if (p > budget) { s = Math.max(0, Math.min(s, budget / R - 1)); p = Math.min(p, budget); }
  if (s <= 0) return { p: R, s: 0 };
  const rad = Math.PI / 180;
  const arcMeasure = 90 * (1 - s);
  const arc = Math.sin((arcMeasure / 2) * rad) * R * Math.SQRT2;
  const alpha = (90 - arcMeasure) / 2;
  const p34 = R * Math.tan((alpha / 2) * rad);
  const beta = 45 * s;
  const cc = p34 * Math.cos(beta * rad);
  const dd = cc * Math.tan(beta * rad);
  const b = (p - arc - cc - dd) / 3;
  return { p, s, a: 2 * b, b, cc, dd, arc };
}

// Vector paths [{closed, pts:[{x,y,ix,iy,ox,oy}]}] → d. Equal handles = straight segment.
export function vectorD(paths) {
  let d = '';
  for (const path of paths || []) {
    const pts = path.pts || [];
    if (!pts.length) continue;
    d += `M${R2(pts[0].x)} ${R2(pts[0].y)}`;
    const seg = (a, b) => {
      const ox = a.ox ?? a.x, oy = a.oy ?? a.y, ix = b.ix ?? b.x, iy = b.iy ?? b.y;
      if (ox === a.x && oy === a.y && ix === b.x && iy === b.y) return `L${R2(b.x)} ${R2(b.y)}`;
      return `C${R2(ox)} ${R2(oy)} ${R2(ix)} ${R2(iy)} ${R2(b.x)} ${R2(b.y)}`;
    };
    for (let i = 0; i + 1 < pts.length; i++) d += seg(pts[i], pts[i + 1]);
    if (path.closed) d += (pts.length > 1 ? seg(pts[pts.length - 1], pts[0]) : '') + 'Z';
  }
  return d;
}

// ---------- parsing / transforms ----------

// Parse any SVG path d into absolute subpaths of cubic segments: [{x, y, segs:[[c1x,c1y,c2x,c2y,x,y,isLine]], closed}].
export function parsePath(d) {
  const toks = String(d || '').match(/[a-zA-Z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/g) || [];
  const out = [];
  let i = 0, cmd = '', x = 0, y = 0, sx = 0, sy = 0, cur = null, lc = null, lq = null;
  const num = () => +toks[i++];
  const line = (nx, ny) => { cur.segs.push([x, y, nx, ny, nx, ny, 1]); x = nx; y = ny; };
  while (i < toks.length) {
    if (/[a-zA-Z]/.test(toks[i])) cmd = toks[i++];
    const rel = cmd === cmd.toLowerCase(), C = cmd.toUpperCase();
    const ox = rel ? x : 0, oy = rel ? y : 0;
    if (C === 'Z') { if (cur) { if (x !== sx || y !== sy) line(sx, sy); cur.closed = true; } x = sx; y = sy; cur = null; lc = lq = null; continue; }
    if (C === 'M') {
      x = num() + ox; y = num() + oy; sx = x; sy = y;
      cur = { x, y, segs: [], closed: false }; out.push(cur);
      cmd = rel ? 'l' : 'L'; lc = lq = null; continue;
    }
    if (!cur) { cur = { x, y, segs: [], closed: false }; out.push(cur); sx = x; sy = y; }
    if (C === 'L') { line(num() + ox, num() + oy); lc = lq = null; }
    else if (C === 'H') { line(num() + ox, y); lc = lq = null; }
    else if (C === 'V') { line(x, num() + oy); lc = lq = null; }
    else if (C === 'C' || C === 'S') {
      let c1x, c1y;
      if (C === 'S') { c1x = lc ? 2 * x - lc[0] : x; c1y = lc ? 2 * y - lc[1] : y; }
      else { c1x = num() + ox; c1y = num() + oy; }
      const c2x = num() + ox, c2y = num() + oy, nx = num() + ox, ny = num() + oy;
      cur.segs.push([c1x, c1y, c2x, c2y, nx, ny, 0]); lc = [c2x, c2y]; lq = null; x = nx; y = ny;
    } else if (C === 'Q' || C === 'T') {
      let qx, qy;
      if (C === 'T') { qx = lq ? 2 * x - lq[0] : x; qy = lq ? 2 * y - lq[1] : y; }
      else { qx = num() + ox; qy = num() + oy; }
      const nx = num() + ox, ny = num() + oy;
      cur.segs.push([x + (2 / 3) * (qx - x), y + (2 / 3) * (qy - y), nx + (2 / 3) * (qx - nx), ny + (2 / 3) * (qy - ny), nx, ny, 0]);
      lq = [qx, qy]; lc = null; x = nx; y = ny;
    } else if (C === 'A') {
      const rx = num(), ry = num(), rot = num(), large = num(), sw = num(), nx = num() + ox, ny = num() + oy;
      for (const s of arcToCubics(x, y, rx, ry, rot, large, sw, nx, ny)) cur.segs.push(s);
      x = nx; y = ny; lc = lq = null;
    } else { i++; }
  }
  return out;
}

// SVG arc (endpoint form) → cubic segments (≤ 90° each).
function arcToCubics(x1, y1, rx, ry, rotDeg, large, sweep, x2, y2) {
  if (!rx || !ry || (x1 === x2 && y1 === y2)) return [[x1, y1, x2, y2, x2, y2, 1]];
  rx = Math.abs(rx); ry = Math.abs(ry);
  const phi = (rotDeg * Math.PI) / 180, cp = Math.cos(phi), sp = Math.sin(phi);
  const dx = (x1 - x2) / 2, dy = (y1 - y2) / 2;
  const x1p = cp * dx + sp * dy, y1p = -sp * dx + cp * dy;
  const lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry);
  if (lam > 1) { const s = Math.sqrt(lam); rx *= s; ry *= s; }
  const num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p;
  const den = rx * rx * y1p * y1p + ry * ry * x1p * x1p;
  let co = Math.sqrt(Math.max(0, num / den));
  if (+large === +sweep) co = -co;
  const cxp = (co * rx * y1p) / ry, cyp = (-co * ry * x1p) / rx;
  const cx = cp * cxp - sp * cyp + (x1 + x2) / 2, cy = sp * cxp + cp * cyp + (y1 + y2) / 2;
  const ang = (ux, uy, vx, vy) => {
    const a = Math.atan2(ux * vy - uy * vx, ux * vx + uy * vy);
    return a;
  };
  const t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry);
  let dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry);
  if (!+sweep && dt > 0) dt -= 2 * Math.PI;
  else if (+sweep && dt < 0) dt += 2 * Math.PI;
  const n = Math.ceil(Math.abs(dt) / (Math.PI / 2) - 1e-9);
  const step = dt / n, k = (4 / 3) * Math.tan(step / 4);
  const P = (t) => [cx + rx * Math.cos(t) * cp - ry * Math.sin(t) * sp, cy + rx * Math.cos(t) * sp + ry * Math.sin(t) * cp];
  const D = (t) => [-rx * Math.sin(t) * cp - ry * Math.cos(t) * sp, -rx * Math.sin(t) * sp + ry * Math.cos(t) * cp];
  const segs = [];
  for (let j = 0; j < n; j++) {
    const a = t1 + j * step, b = a + step;
    const pa = P(a), pb = j === n - 1 ? [x2, y2] : P(b), da = D(a), db = D(b);
    segs.push([pa[0] + k * da[0], pa[1] + k * da[1], pb[0] - k * db[0], pb[1] - k * db[1], pb[0], pb[1], 0]);
  }
  return segs;
}

export function serializePath(subs) {
  let d = '';
  for (const s of subs) {
    d += `M${R2(s.x)} ${R2(s.y)}`;
    for (const g of s.segs) d += g[6] ? `L${R2(g[4])} ${R2(g[5])}` : `C${R2(g[0])} ${R2(g[1])} ${R2(g[2])} ${R2(g[3])} ${R2(g[4])} ${R2(g[5])}`;
    if (s.closed) d += 'Z';
  }
  return d;
}

// Affine matrices [a, b, c, d, e, f]: x' = a x + c y + e, y' = b x + d y + f.
export const mul = (m, n) => [
  m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1],
  m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
  m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5],
];
export const apply = (m, x, y) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];

// Node local box → parent coords. CSS order: translate(x,y) · rotate(θ) · scale(flip), around the center.
export function nodeMatrix(p) {
  const t = ((p.rotation || 0) * Math.PI) / 180, c = Math.cos(t), s = Math.sin(t);
  const fx = p.flipX ? -1 : 1, fy = p.flipY ? -1 : 1, hw = p.w / 2, hh = p.h / 2;
  let m = [1, 0, 0, 1, (p.x || 0) + hw, (p.y || 0) + hh];
  m = mul(m, [c, s, -s, c, 0, 0]);
  m = mul(m, [fx, 0, 0, fy, 0, 0]);
  return mul(m, [1, 0, 0, 1, -hw, -hh]);
}

export function transformD(d, m) {
  const subs = parsePath(d);
  for (const s of subs) {
    [s.x, s.y] = apply(m, s.x, s.y);
    for (const g of s.segs) {
      [g[0], g[1]] = apply(m, g[0], g[1]); [g[2], g[3]] = apply(m, g[2], g[3]); [g[4], g[5]] = apply(m, g[4], g[5]);
    }
  }
  return serializePath(subs);
}

// ---------- flattening ----------

function flatCubic(out, x0, y0, x1, y1, x2, y2, x3, y3, depth) {
  const dx = x3 - x0, dy = y3 - y0, L = Math.hypot(dx, dy) || 1e-9;
  const d1 = Math.abs((x1 - x3) * dy - (y1 - y3) * dx) / L;
  const d2 = Math.abs((x2 - x3) * dy - (y2 - y3) * dx) / L;
  if (depth > 16 || Math.max(d1, d2) <= TOL) { out.push([x3, y3]); return; }
  const ax = (x0 + x1) / 2, ay = (y0 + y1) / 2, bx = (x1 + x2) / 2, by = (y1 + y2) / 2, cx = (x2 + x3) / 2, cy = (y2 + y3) / 2;
  const abx = (ax + bx) / 2, aby = (ay + by) / 2, bcx = (bx + cx) / 2, bcy = (by + cy) / 2;
  const mx = (abx + bcx) / 2, my = (aby + bcy) / 2;
  flatCubic(out, x0, y0, ax, ay, abx, aby, mx, my, depth + 1);
  flatCubic(out, mx, my, bcx, bcy, cx, cy, x3, y3, depth + 1);
}

// d → [{pts:[[x,y]...], closed, corners:Set(index of original vertices)}]
export function flattenD(d) {
  return parsePath(d).map((s) => {
    const pts = [[s.x, s.y]], corners = new Set([0]);
    let x = s.x, y = s.y;
    for (const g of s.segs) {
      if (g[6]) pts.push([g[4], g[5]]);
      else flatCubic(pts, x, y, g[0], g[1], g[2], g[3], g[4], g[5], 0);
      corners.add(pts.length - 1);
      x = g[4]; y = g[5];
    }
    if (s.closed && pts.length > 1) {
      const a = pts[0], b = pts[pts.length - 1];
      if (Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6) pts.pop();
    }
    return { pts, closed: s.closed, corners };
  });
}

export function bboxOfD(d) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const s of flattenD(d)) for (const [x, y] of s.pts) {
    if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y;
  }
  if (x0 === Infinity) return { x: 0, y: 0, w: 0, h: 0 };
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

// ---------- booleans ----------

const area = (r) => { let a = 0; for (let i = 0, n = r.length; i < n; i++) { const p = r[i], q = r[(i + 1) % n]; a += p[0] * q[1] - q[0] * p[1]; } return a / 2; };
const closeRing = (pts) => { const r = pts.map((p) => [p[0], p[1]]); if (r.length) r.push([r[0][0], r[0][1]]); return r; };

// One path (with its fill rule) → polygon-clipping MultiPolygon.
export function geomOfD(d, rule = 'NONZERO') {
  const rings = flattenD(d).filter((s) => s.pts.length >= 3).map((s) => s.pts);
  if (!rings.length) return [];
  const polys = rings.map((r) => [closeRing(r)]);
  const P = pc();
  if (polys.length === 1) return P.union(polys[0]);
  if (rule === 'EVENODD') return P.xor(...polys);
  // Nonzero approximation: rings wound like the largest ring add, opposite-wound rings cut.
  let big = 0;
  rings.forEach((r, i) => { if (Math.abs(area(r)) > Math.abs(area(rings[big]))) big = i; });
  const sign = Math.sign(area(rings[big]));
  const add = polys.filter((_, i) => Math.sign(area(rings[i])) === sign);
  const cut = polys.filter((_, i) => Math.sign(area(rings[i])) !== sign);
  const pos = P.union(...add);
  return cut.length ? P.difference(pos, ...cut) : pos;
}

export function geomToD(mp) {
  let d = '';
  for (const poly of mp || []) for (const ring of poly) {
    const r = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? ring.slice(0, -1) : ring;
    if (r.length < 3) continue;
    d += 'M' + r.map((p) => R2(p[0]) + ' ' + R2(p[1])).join('L') + 'Z';
  }
  return d;
}

// items: d strings or {d, rule}, bottom→top, all in one coordinate space.
// SUBTRACT = bottom minus everything above (Figma semantics).
export function booleanD(op, items) {
  const P = pc();
  if (!P) throw new Error('polygonClipping not loaded');
  const all = items.map((it) => (typeof it === 'string' ? geomOfD(it) : geomOfD(it.d, it.rule)));
  const geoms = all.filter((g) => g.length);
  if (!geoms.length) return '';
  let r;
  if (op === 'SUBTRACT') {
    if (!all[0].length) return '';
    const rest = all.slice(1).filter((g) => g.length);
    r = rest.length ? P.difference(all[0], ...rest) : all[0];
  } else if (op === 'INTERSECT') {
    if (geoms.length < all.length) return '';
    r = geoms.length > 1 ? P.intersection(geoms[0], ...geoms.slice(1)) : geoms[0];
  } else if (op === 'EXCLUDE') r = geoms.length > 1 ? P.xor(geoms[0], ...geoms.slice(1)) : geoms[0];
  else r = geoms.length > 1 ? P.union(geoms[0], ...geoms.slice(1)) : geoms[0];
  return geomToD(r);
}

// ---------- node geometry ----------

const BOXY = new Set(['rect', 'frame', 'page', 'section', 'text', 'video', 'table']);

// Own outline of a node in its box coords. src = {props(id), type(id), children(id) → ids}.
// Returns {d, rule}; groups/booleans combine their children.
export function nodeGeometry(id, src) {
  const type = src.type(id), p = src.props(id);
  if (BOXY.has(type)) return { d: smoothRectD(p.w, p.h, p.radius ?? 0, p.smoothing || 0), rule: 'NONZERO' };
  if (type === 'ellipse') return { d: arcD(p.arc, p.w, p.h), rule: 'NONZERO' };
  if (type === 'polygon') return { d: polygonD(p.points, p.w, p.h, p.radius), rule: 'NONZERO' };
  if (type === 'star') return { d: starD(p.points, p.inner, p.w, p.h, p.radius), rule: 'NONZERO' };
  if (type === 'vector') return { d: vectorD(p.paths), rule: p.winding || 'NONZERO', open: (p.paths || []).some((x) => !x.closed) };
  if (type === 'line') return { d: `M0 ${R2(p.h / 2)}L${R2(p.w)} ${R2(p.h / 2)}`, rule: 'NONZERO', open: true };
  if (type === 'group' || type === 'boolean') {
    const items = [];
    for (const cid of src.children(id)) {
      const cp = src.props(cid);
      if (cp.visible === false || src.type(cid) === 'line') continue;
      const g = nodeGeometry(cid, src);
      if (!g.d) continue;
      items.push({ d: transformD(g.d, nodeMatrix(cp)), rule: g.rule });
    }
    if (!items.length) return { d: '', rule: 'NONZERO' };
    return { d: booleanD(type === 'boolean' ? p.op || 'UNION' : 'UNION', items), rule: 'NONZERO' };
  }
  return { d: '', rule: 'NONZERO' };
}

export function storeSource(store, overlay) {
  return {
    props: (id) => { const n = store.nodes.get(id); const p = propsOf(n); return overlay?.has(id) ? { ...p, ...overlay.get(id) } : p; },
    type: (id) => store.nodes.get(id).type,
    children: (id) => store.children(id).map((n) => n.id),
  };
}

// ---------- caps ----------

// Arrow/cap shapes at end point P with outward unit direction (ux, uy) for stroke weight w.
// Returns {fill: [ring...], lines: [polyline...], inset} (inset = how far to pull the line end back).
export function capShapes(type, P, ux, uy, w) {
  const L = Math.max(4 * w, w + 6), nx = -uy, ny = ux;
  const at = (a, b) => [P[0] + ux * a + nx * b, P[1] + uy * a + ny * b];
  switch (type) {
    case 'ROUND': return { fill: [circle(P, w / 2)], lines: [], inset: 0 };
    case 'SQUARE': return { fill: [[at(0, w / 2), at(w / 2, w / 2), at(w / 2, -w / 2), at(0, -w / 2)]], lines: [], inset: 0 };
    case 'ARROW_LINES': return { fill: [], lines: [[at(-L * 0.85, L * 0.55), at(0, 0), at(-L * 0.85, -L * 0.55)]], inset: 0 };
    case 'ARROW_EQUILATERAL': return { fill: [[at(0, 0), at(-L, L / Math.sqrt(3)), at(-L, -L / Math.sqrt(3))]], lines: [], inset: L * 0.5 };
    case 'TRIANGLE_FILLED': return { fill: [[at(0, L * 0.5), at(0, -L * 0.5), at(-L * 0.85, 0)]], lines: [], inset: 0 };
    case 'DIAMOND_FILLED': return { fill: [[at(L * 0.5, 0), at(0, L * 0.4), at(-L * 0.5, 0), at(0, -L * 0.4)]], lines: [], inset: 0 };
    case 'CIRCLE_FILLED': return { fill: [circle(P, L * 0.38)], lines: [], inset: 0 };
    default: return { fill: [], lines: [], inset: 0 };
  }
}

function circle(c, r, n = 0) {
  n = n || Math.max(12, Math.min(64, Math.ceil(r * 2)));
  const out = [];
  for (let i = 0; i < n; i++) { const a = (i / n) * Math.PI * 2; out.push([c[0] + Math.cos(a) * r, c[1] + Math.sin(a) * r]); }
  return out;
}

// End points + outward directions of an open polyline set (first subpath start, last subpath end).
export function openEnds(d) {
  const subs = parsePath(d).filter((s) => !s.closed && s.segs.length);
  if (!subs.length) return null;
  const a = subs[0], g0 = a.segs[0];
  let sx = a.x - (g0[6] ? g0[4] : g0[0]), sy = a.y - (g0[6] ? g0[5] : g0[1]);
  if (!sx && !sy) { sx = a.x - g0[4]; sy = a.y - g0[5]; }
  const b = subs[subs.length - 1], gl = b.segs[b.segs.length - 1];
  const prevX = b.segs.length > 1 ? b.segs[b.segs.length - 2][4] : b.x, prevY = b.segs.length > 1 ? b.segs[b.segs.length - 2][5] : b.y;
  let ex = gl[4] - (gl[6] ? prevX : gl[2]), ey = gl[5] - (gl[6] ? prevY : gl[3]);
  if (!ex && !ey) { ex = gl[4] - prevX; ey = gl[5] - prevY; }
  const n1 = Math.hypot(sx, sy) || 1, n2 = Math.hypot(ex, ey) || 1;
  return { start: [a.x, a.y], su: [sx / n1, sy / n1], end: [gl[4], gl[5]], eu: [ex / n2, ey / n2] };
}

// ---------- stroke outlining ----------

function dashPolyline(pts, closed, dash) {
  const sum = dash.reduce((a, b) => a + Math.max(0, b), 0);
  if (!dash.length || sum <= 0) return [{ pts, closed }];
  const seq = dash.length % 2 ? dash.concat(dash) : dash;
  const P = closed ? pts.concat([pts[0]]) : pts;
  const out = [];
  let k = 0, left = seq[0], on = true, cur = [P[0]];
  for (let i = 0; i + 1 < P.length; i++) {
    let [x, y] = P[i];
    const [x2, y2] = P[i + 1];
    let segLen = Math.hypot(x2 - x, y2 - y);
    while (segLen > 1e-9) {
      const step = Math.min(left, segLen), t = step / segLen;
      x += (x2 - x) * t; y += (y2 - y) * t; segLen -= step; left -= step;
      if (on) cur.push([x, y]);
      if (left <= 1e-9) {
        if (on && cur.length > 1) out.push({ pts: cur, closed: false });
        on = !on; k = (k + 1) % seq.length; left = seq[k]; cur = [[x, y]];
      }
    }
  }
  if (on && cur.length > 1) out.push({ pts: cur, closed: false });
  return out;
}

function strokePolys(line, hw, join, miter, capS, capE, capType) {
  const { pts, closed } = line, polys = [], n = pts.length;
  if (n < 2) return polys;
  const segN = closed ? n : n - 1;
  const quad = (a, b, ea, eb) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L, nx = -uy * hw, ny = ux * hw;
    const A = [a[0] - ux * ea, a[1] - uy * ea], B = [b[0] + ux * eb, b[1] + uy * eb];
    return [[A[0] + nx, A[1] + ny], [B[0] + nx, B[1] + ny], [B[0] - nx, B[1] - ny], [A[0] - nx, A[1] - ny]];
  };
  for (let i = 0; i < segN; i++) {
    const a = pts[i], b = pts[(i + 1) % n];
    const ea = !closed && i === 0 && capS === 'SQUARE' ? hw : 0, eb = !closed && i === segN - 1 && capE === 'SQUARE' ? hw : 0;
    polys.push(quad(a, b, ea, eb));
  }
  const vStart = closed ? 0 : 1, vEnd = closed ? n : n - 1;
  for (let i = vStart; i < vEnd; i++) {
    const P = pts[i], A = pts[(i - 1 + n) % n], B = pts[(i + 1) % n];
    const d1 = [P[0] - A[0], P[1] - A[1]], d2 = [B[0] - P[0], B[1] - P[1]];
    const l1 = Math.hypot(...d1) || 1, l2 = Math.hypot(...d2) || 1;
    const n1 = [-d1[1] / l1 * hw, d1[0] / l1 * hw], n2 = [-d2[1] / l2 * hw, d2[0] / l2 * hw];
    const turn = Math.abs(Math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1]));
    const isCorner = line.corners ? line.corners.has(i) && turn > 0.17 : turn > 0.17;
    const j = isCorner ? join : 'BEVEL';
    if (j === 'ROUND') { polys.push(circle(P, hw)); continue; }
    for (const s of [1, -1]) polys.push([P, [P[0] + n1[0] * s, P[1] + n1[1] * s], [P[0] + n2[0] * s, P[1] + n2[1] * s]]);
    if (j === 'MITER' && turn > 1e-3 && 1 / Math.sin((Math.PI - turn) / 2) <= miter) {
      const bis = [n1[0] + n2[0], n1[1] + n2[1]], bl = Math.hypot(...bis) || 1, len = hw / Math.cos(turn / 2);
      const s = d1[0] * d2[1] - d1[1] * d2[0] > 0 ? -1 : 1;
      const M = [P[0] + (bis[0] / bl) * len * s, P[1] + (bis[1] / bl) * len * s];
      polys.push([P, [P[0] + n1[0] * s, P[1] + n1[1] * s], M, [P[0] + n2[0] * s, P[1] + n2[1] * s]]);
    }
  }
  if (!closed) {
    if (capS === 'ROUND') polys.push(circle(pts[0], hw));
    if (capE === 'ROUND') polys.push(circle(pts[n - 1], hw));
  }
  return polys;
}

// Stroke outline of path d → MultiPolygon. stroke = schema stroke object.
export function strokeGeom(d, stroke, { closedShape = true, fillRule = 'NONZERO', weight } = {}) {
  const P = pc(), w = weight ?? stroke.weight ?? 1;
  const lines = flattenD(d);
  const open = lines.some((l) => !l.closed);
  const align = open || !closedShape ? 'CENTER' : stroke.align || 'CENTER';
  const hw = align === 'CENTER' ? w / 2 : w;
  const polys = [];
  for (const l of lines) for (const piece of dashPolyline(l.pts, l.closed, stroke.dash || [])) {
    if (piece !== l) piece.corners = null;
    else piece.corners = l.corners;
    const dashed = (stroke.dash || []).length > 0;
    const capS = dashed ? stroke.dashCap : l.closed ? 'NONE' : stroke.capStart;
    const capE = dashed ? stroke.dashCap : l.closed ? 'NONE' : stroke.capEnd;
    polys.push(...strokePolys(piece, hw, stroke.join || 'MITER', stroke.miterLimit || 4, capS, capE));
  }
  if (open) {
    const e = openEnds(d);
    if (e) for (const [type, pt, u] of [[stroke.capStart, e.start, e.su], [stroke.capEnd, e.end, e.eu]]) {
      if (!type || type === 'NONE' || type === 'ROUND' || type === 'SQUARE') continue;
      const c = capShapes(type, pt, u[0], u[1], w);
      polys.push(...c.fill);
      for (const ln of c.lines) polys.push(...strokePolys({ pts: ln, closed: false }, w / 2, 'ROUND', 4, 'ROUND', 'ROUND'));
    }
  }
  if (!polys.length) return [];
  let g = P.union(...polys.map((r) => [closeRing(r)]));
  if (align === 'INSIDE') g = P.intersection(g, geomOfD(d, fillRule));
  else if (align === 'OUTSIDE') g = P.difference(g, geomOfD(d, fillRule));
  return g;
}

// ---------- conversions ----------

// d → vector paths in pts/handles form.
export function dToPaths(d) {
  const out = [];
  for (const s of parsePath(d)) {
    const pts = [{ x: s.x, y: s.y, ix: s.x, iy: s.y, ox: s.x, oy: s.y }];
    for (const g of s.segs) {
      const prev = pts[pts.length - 1];
      if (!g[6]) { prev.ox = g[0]; prev.oy = g[1]; }
      pts.push({ x: g[4], y: g[5], ix: g[6] ? g[4] : g[2], iy: g[6] ? g[5] : g[3], ox: g[4], oy: g[5] });
    }
    if (s.closed && pts.length > 1) {
      const a = pts[0], b = pts[pts.length - 1];
      if (Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.y - b.y) < 1e-6) { a.ix = b.ix; a.iy = b.iy; pts.pop(); }
    }
    for (const p of pts) for (const k of ['x', 'y', 'ix', 'iy', 'ox', 'oy']) p[k] = R2(p[k]);
    out.push({ closed: s.closed, pts });
  }
  return out;
}

// Re-box a d (box coords of node p) to its own bounds → {x, y, w, h, paths} in the parent's coordinates.
function reboxed(d, p) {
  const bb = bboxOfD(d);
  const shifted = transformD(d, [1, 0, 0, 1, -bb.x, -bb.y]);
  // keep the node's rotation/flip: new center = old matrix applied to the bbox center
  const m = nodeMatrix(p);
  const [cx, cy] = apply(m, bb.x + bb.w / 2, bb.y + bb.h / 2);
  return { x: R2(cx - bb.w / 2), y: R2(cy - bb.h / 2), w: R2(bb.w), h: R2(bb.h), paths: dToPaths(shifted) };
}

const KEEP = ['name', 'rotation', 'flipX', 'flipY', 'opacity', 'blend', 'visible', 'locked', 'effects', 'constraints', 'layoutChild'];

// Destructive flatten → props of a new `vector` node (caller swaps the node). Text is not supported (null).
export function flattenToVector(id, store) {
  const node = store.nodes.get(id);
  if (!node || node.type === 'text' || node.type === 'page') return null;
  const src = storeSource(store);
  const p = propsOf(node);
  const g = nodeGeometry(id, src);
  if (!g.d) return null;
  const out = {};
  for (const k of KEEP) if (p[k] !== undefined) out[k] = p[k];
  let style = p;
  if ((node.type === 'group' || node.type === 'frame' || node.type === 'section') && !(p.fills || []).some((f) => f.visible !== false)) {
    const kids = store.children(id);
    if (kids.length) style = propsOf(kids[kids.length - 1]);
  }
  Object.assign(out, { fills: style.fills || [], strokes: style.strokes || [], stroke: style.stroke, winding: g.rule }, reboxed(g.d, p));
  return out;
}

// Destructive outline stroke → props of a new `vector` node filled with the stroke paints.
export function outlineStrokeToVector(id, store) {
  const node = store.nodes.get(id);
  if (!node || node.type === 'text' || node.type === 'page') return null;
  const p = propsOf(node);
  if (!(p.strokes || []).length || !(p.stroke?.weight > 0)) return null;
  const g = nodeGeometry(id, storeSource(store));
  if (!g.d) return null;
  const mp = strokeGeom(g.d, p.stroke, { closedShape: !g.open, fillRule: g.rule });
  const d = geomToD(mp);
  if (!d) return null;
  const out = {};
  for (const k of KEEP) if (p[k] !== undefined) out[k] = p[k];
  Object.assign(out, { fills: p.strokes, strokes: [], winding: 'NONZERO' }, reboxed(d, p));
  out.name = p.name || 'Vector';
  return out;
}
