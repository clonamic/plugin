"use strict";
// Left-to-right layered layout that knows where each link leaves and enters a card.
//   nodes: [{id, w, h, inY, role}]  role: "start" (first column), "end" (last column), or anything else.
//          inY = y of the incoming port, measured from the card top.
//   edges: [{source, target, outY}]  outY = y of the outgoing port (its 출력 row) on the source card.
// Returns {id: {x, y}} card centers. Steps: break cycles (DFS in port order) → ranks (longest path,
// sources pulled next to their targets, end nodes in the last column) → lanes for links that skip columns →
// sweeps that line each card's in-port up with the ports it is linked to and keep port order (no crossings
// where avoidable) → cards with no links in a row underneath.
function layered(nodes, edges, opt = {}) {
  const RANK = opt.rankSep ?? 96, GAP = opt.nodeSep ?? 28, LANE = 12;
  const N = new Map(nodes.map((n, i) => [n.id, { ...n, ord: i }]));
  const isEnd = (id) => N.get(id).role === "end", isStart = (id) => N.get(id).role === "start";
  const out = new Map(), inn = new Map();
  for (const id of N.keys()) { out.set(id, []); inn.set(id, []); }
  const live = edges.filter((e) => N.has(e.source) && N.has(e.target) && e.source !== e.target);
  for (const e of live) { out.get(e.source).push(e); inn.get(e.target).push(e); }

  // 1. Cycles: an edge back into the DFS stack, into the start, or out of an end node is drawn as a back link.
  const state = new Map(), seen = [], post = [], back = new Set();
  const visit = (id) => {
    state.set(id, 1); seen.push(id);
    for (const e of [...out.get(id)].sort((p, q) => p.outY - q.outY)) {
      if (state.get(e.target) === 1 || isStart(e.target) || isEnd(e.source)) back.add(e);
      else if (!state.has(e.target)) visit(e.target);
    }
    state.set(id, 2); post.push(id);
  };
  const roots = [...N.keys()].sort((p, q) => (isStart(q) - isStart(p)) || (inn.get(p).length ? 1 : 0) - (inn.get(q).length ? 1 : 0) || N.get(p).ord - N.get(q).ord);
  for (const id of roots) if (!state.has(id)) visit(id);
  const fwd = live.filter((e) => !back.has(e));
  const fOut = (id) => fwd.filter((e) => e.source === id), fIn = (id) => fwd.filter((e) => e.target === id);

  // 2. Ranks. Nodes without any link (except start and end) go to a row underneath instead.
  const alone = (id) => !isStart(id) && !isEnd(id) && !out.get(id).length && !inn.get(id).length;
  const topo = post.slice().reverse().filter((id) => !alone(id));
  const rank = new Map(topo.map((id) => [id, 0]));
  for (const id of topo) for (const e of fOut(id)) rank.set(e.target, Math.max(rank.get(e.target), rank.get(id) + 1));
  for (const id of topo.slice().reverse()) {  // a source sits right before its nearest target, not in column 0
    if (isStart(id) || isEnd(id) || fIn(id).length) continue;
    const t = fOut(id).filter((e) => !isEnd(e.target)).map((e) => rank.get(e.target));
    if (t.length) rank.set(id, Math.max(0, Math.min(...t) - 1));
  }
  const last = Math.max(0, ...topo.filter((id) => !isEnd(id)).map((id) => rank.get(id))) + 1;
  for (const id of topo) if (isEnd(id)) rank.set(id, last);
  for (const id of topo) if (isStart(id)) rank.set(id, 0);

  // 3. Segments; a link that skips columns gets a thin lane node in every column it crosses.
  const L = new Map(), segIn = new Map(), segOut = new Map();
  const addNode = (id, n) => { L.set(id, n); segIn.set(id, []); segOut.set(id, []); };
  topo.forEach((id, i) => addNode(id, { ...N.get(id), rank: rank.get(id), seq: i }));
  let k = 0;
  for (const e of fwd) {
    const r0 = rank.get(e.source), r1 = rank.get(e.target);
    if (r1 <= r0) continue;
    let u = e.source, uy = e.outY;
    for (let r = r0 + 1; r < r1; r++) {
      const id = `\u0000${k++}`;
      addNode(id, { id, w: 0, h: LANE, inY: LANE / 2, rank: r, lane: true, seq: L.get(e.source).seq + 0.5 });
      const s = { u, v: id, uy, vy: LANE / 2 };
      segOut.get(u).push(s); segIn.get(id).push(s);
      u = id; uy = LANE / 2;
    }
    const s = { u, v: e.target, uy, vy: N.get(e.target).inY };
    segOut.get(u).push(s); segIn.get(e.target).push(s);
  }
  const cols = [];
  for (const [id, n] of L) (cols[n.rank] ||= []).push(id);
  for (let r = 0; r < cols.length; r++) cols[r] = (cols[r] || []).sort((p, q) => L.get(p).seq - L.get(q).seq);

  // 4. Vertical positions (card tops). Each sweep sorts a column by where its links want each card,
  //    then finds the closest non-overlapping tops (isotonic regression, pool adjacent violators).
  const top = new Map();
  for (const col of cols) { let y = 0; for (const id of col) { top.set(id, y); y += L.get(id).h + GAP; } }
  const median = (v) => { v.sort((p, q) => p - q); const m = v.length >> 1; return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2; };
  const want = (id, dir) => {
    const n = L.get(id);
    const ys = dir === "in" || n.lane
      ? segIn.get(id).map((s) => top.get(s.u) + s.uy - s.vy)
      : segOut.get(id).map((s) => top.get(s.v) + s.vy - s.uy);
    return ys.length ? median(ys) : null;
  };
  const gapOf = (p, q) => (L.get(p).lane && L.get(q).lane ? 6 : GAP);
  const place = (col, dir) => {
    const w = new Map(col.map((id) => [id, want(id, dir)]));
    const key = (id) => (w.get(id) ?? top.get(id)) + L.get(id).inY;  // compare in-port heights, so port order is kept
    col.sort((p, q) => key(p) - key(q) || top.get(p) - top.get(q));
    const blocks = [];
    let c = 0;
    col.forEach((id, i) => {
      const d = w.get(id), weight = d === null ? 0.05 : L.get(id).lane ? 4 : 1;
      blocks.push({ sum: ((d ?? top.get(id)) - c) * weight, w: weight, n: 1 });
      c += L.get(id).h + (i + 1 < col.length ? gapOf(id, col[i + 1]) : 0);
      while (blocks.length > 1 && blocks.at(-2).sum / blocks.at(-2).w > blocks.at(-1).sum / blocks.at(-1).w) {
        const b = blocks.pop(), a = blocks.at(-1);
        a.sum += b.sum; a.w += b.w; a.n += b.n;
      }
    });
    let i = 0;
    c = 0;
    for (const b of blocks) for (let j = 0; j < b.n; j++, i++) {
      top.set(col[i], b.sum / b.w + c);
      c += L.get(col[i]).h + (i + 1 < col.length ? gapOf(col[i], col[i + 1]) : 0);
    }
  };
  for (let it = 0; it < 12; it++) {
    for (let r = 1; r < cols.length; r++) place(cols[r], "in");
    for (let r = cols.length - 2; r >= 0; r--) place(cols[r], "out");
  }
  for (let r = 1; r < cols.length; r++) place(cols[r], "in");

  // 5. Columns left to right, each as wide as its widest card.
  const pos = {};
  let x = 0, minY = Infinity, maxY = -Infinity;
  for (const col of cols) {
    const w = Math.max(0, ...col.map((id) => L.get(id).w));
    for (const id of col) {
      const n = L.get(id);
      if (n.lane) continue;
      pos[id] = { x: x + w / 2, y: top.get(id) + n.h / 2 };
      minY = Math.min(minY, top.get(id)); maxY = Math.max(maxY, top.get(id) + n.h);
    }
    x += w + RANK;
  }
  if (!Number.isFinite(minY)) { minY = 0; maxY = 0; }
  for (const id in pos) pos[id].y -= minY;
  // 6. Cards without links: a row underneath, in document order.
  let ax = 0, ay = maxY - minY + 72, rowH = 0;
  const wrap = Math.max(x - RANK, 4 * ((nodes[0]?.w || 236) + 40));
  for (const n of nodes) {
    if (!alone(n.id)) continue;
    if (ax > 0 && ax + n.w > wrap) { ax = 0; ay += rowH + 40; rowH = 0; }
    pos[n.id] = { x: ax + n.w / 2, y: ay + n.h / 2 };
    ax += n.w + 40; rowH = Math.max(rowH, n.h);
  }
  return pos;
}
if (typeof module !== "undefined") module.exports = { layered };
