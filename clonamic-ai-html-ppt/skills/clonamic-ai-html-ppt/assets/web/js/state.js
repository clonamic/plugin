// Deck store (format.md §6): local node map + optimistic op batches synced with the server.
//
// Local state = server base + "layers" (unconfirmed batches bottom→top, then temporary previews).
// Every layer keeps its inverse, so a remote batch is applied by reverting layers, applying it,
// and re-applying them (a rebase). A rejected batch is reverted the same way. Confirmed batches
// (POST response or our own SSE echo) leave the layer stack and become base.

import { SCHEMA, zBetween } from "./schema.js";

const MAX_OPS = 5000;
const clone = (v) => (v === undefined ? undefined : structuredClone(v));
// An `add` never carries null/undefined props (null means "back to default" only in `set`).
function cleanOps(ops) {
  return ops.map((o) => {
    if (o.op !== "add" || !o.node?.props) return o;
    const props = {};
    for (const [k, v] of Object.entries(o.node.props)) if (v !== null && v !== undefined) props[k] = v;
    return { ...o, node: { ...o.node, props } };
  });
}

export function createStore(api, data, deckId = data?.deck?.id) {
  const nodes = new Map();
  const kids = new Map();      // parent id ("" for null) -> Set<id>
  const sorted = new Map();    // parent key -> sorted id array (cache)
  const subs = new Set();
  const listeners = { status: new Set(), deck: new Set(), remote: new Set(), error: new Set() };
  const deck = { id: deckId, name: "", seq: 0 };
  const layers = [];           // {kind:"batch"|"temp", ops, inv, label?, resolve?, sent?}
  let inflight = null;         // {layers:[...], seq:null|number, retried:bool}
  let retryTimer = 0, retryDelay = 500, scheduled = false, needResync = false, status = "saved";
  let failed = false;          // a batch was rolled back; stays visible until the next successful save
  let idleWaiters = [];

  const key = (p) => (p == null ? "" : p);
  function index(id, parent) {
    const k = key(parent);
    let s = kids.get(k);
    if (!s) kids.set(k, (s = new Set()));
    s.add(id);
    sorted.delete(k);
  }
  function unindex(id, parent) {
    const k = key(parent);
    kids.get(k)?.delete(id);
    sorted.delete(k);
  }
  function load(d) {
    nodes.clear(); kids.clear(); sorted.clear();
    for (const n of d.nodes || []) {
      const node = { id: n.id, type: n.type, parent: n.parent ?? null, z: n.z || "a0", rev: n.rev || 0, props: n.props || {} };
      nodes.set(node.id, node);
      index(node.id, node.parent);
    }
    if (d.deck) Object.assign(deck, d.deck);
  }
  if (data) load(data);

  function childIds(id = null) {
    const k = key(id);
    let list = sorted.get(k);
    if (!list) {
      list = [...(kids.get(k) || [])];
      list.sort((a, b) => { const za = nodes.get(a).z, zb = nodes.get(b).z; return za < zb ? -1 : za > zb ? 1 : a < b ? -1 : 1; });
      sorted.set(k, list);
    }
    return list;
  }
  function pageNode(id) {
    let n = nodes.get(id);
    while (n && n.type !== "page") n = nodes.get(n.parent);
    return n || null;
  }
  function topZ(parent) { const c = childIds(parent); return c.length ? nodes.get(c[c.length - 1]).z : null; }

  // ---- raw op engine (no network, no notify) ----
  function applyOne(op, touched) {
    switch (op.op) {
      case "add": {
        const n = op.node;
        if (!n || nodes.has(n.id)) throw new Error(`add: ${n?.id} exists`);
        const parent = n.parent ?? null;
        if (parent !== null && !nodes.has(parent)) throw new Error(`add: parent ${parent} missing`);
        if (n.type === "page" ? parent !== null : parent === null) throw new Error("add: bad parent");
        if (!n.z) n.z = zBetween(topZ(parent), null);
        const node = { id: n.id, type: n.type, parent, z: n.z, rev: n.rev || 0, props: clone(n.props) || {} };
        nodes.set(node.id, node);
        index(node.id, parent);
        touched.add(node.id);
        return [{ op: "del", id: node.id }];
      }
      case "set": {
        const n = nodes.get(op.id);
        if (!n) throw new Error(`set: ${op.id} missing`);
        const old = {}, next = { ...n.props };
        for (const [k, v] of Object.entries(op.props || {})) {
          old[k] = k in n.props ? n.props[k] : null;
          if (v === null) delete next[k]; else next[k] = clone(v);
        }
        n.props = next;
        if (op.rev) n.rev = op.rev;
        touched.add(n.id);
        return [{ op: "set", id: n.id, props: old }];
      }
      case "del": {
        const root = nodes.get(op.id);
        if (!root) throw new Error(`del: ${op.id} missing`);
        const list = [];
        const walk = (id) => { list.push(nodes.get(id)); for (const c of childIds(id)) walk(c); };
        walk(root.id);
        const inv = list.map((n) => ({ op: "add", node: { id: n.id, type: n.type, parent: n.parent, z: n.z, rev: n.rev, props: n.props } }));
        for (const n of list.slice().reverse()) { unindex(n.id, n.parent); nodes.delete(n.id); touched.add(n.id); }
        return inv;
      }
      case "move": {
        const n = nodes.get(op.id);
        if (!n) throw new Error(`move: ${op.id} missing`);
        const parent = op.parent ?? null;
        if (parent !== null) {
          if (!nodes.has(parent) || !SCHEMA.containers.includes(nodes.get(parent).type)) throw new Error("move: bad parent");
          for (let p = parent; p; p = nodes.get(p)?.parent) if (p === n.id) throw new Error("move: cycle");
        }
        const old = { parent: n.parent, z: n.z };
        unindex(n.id, n.parent);
        n.parent = parent;
        if (!op.z) op.z = zBetween(topZ(parent), null);
        n.z = op.z;
        if (op.rev) n.rev = op.rev;
        index(n.id, parent);
        touched.add(n.id);
        return [{ op: "move", id: n.id, parent: old.parent, z: old.z }];
      }
      case "deck": {
        const old = { name: deck.name };
        Object.assign(deck, op.props || {});
        touched.add("\0deck");
        return [{ op: "deck", props: old }];
      }
      default: throw new Error(`unknown op ${op.op}`);
    }
  }
  // Applies all or nothing; returns the inverse batch.
  function applyRaw(ops, touched) {
    const inv = [];
    try { for (const op of ops) inv.push(applyOne(op, touched)); }
    catch (e) { for (let i = inv.length - 1; i >= 0; i--) for (const o of inv[i]) applyOne(o, touched); throw e; }
    return inv.reverse().flat();
  }
  function revertLayers(from, touched) { for (let i = layers.length - 1; i >= from; i--) applyRaw(layers[i].inv, touched); }
  function reapplyLayers(from, touched) {
    let dropped = 0;
    for (let i = from; i < layers.length; i++) {
      const L = layers[i];
      try { L.inv = applyRaw(L.ops, touched); }
      catch (_) {
        if (L.sent) { needResync = true; L.inv = []; continue; }   // already on its way to the server
        layers.splice(i--, 1); dropped++;
        L.resolve?.({ ok: false, error: "conflict" });
        L.onDrop?.();
      }
    }
    if (dropped) emit("error", "다른 편집과 겹쳐 일부 변경을 되돌렸습니다.");
  }

  function notify(touched) {
    if (!touched.size) return;
    const changed = [], deleted = [];
    for (const id of touched) {
      if (id === "\0deck") { emit("deck", deck); continue; }
      (nodes.has(id) ? changed : deleted).push(id);
    }
    if (!changed.length && !deleted.length) return;
    for (const fn of [...subs]) { try { fn(changed, deleted); } catch (e) { console.error(e); } }
  }
  function emit(type, payload) { for (const fn of [...listeners[type]]) { try { fn(payload); } catch (e) { console.error(e); } } }
  const unconfirmed = () => layers.some((l) => l.kind === "batch" && l.seq == null);
  function setStatus(s) { if (s !== status) { status = s; emit("status", s); } }
  function refreshStatus() {
    if (retryTimer) setStatus("offline");
    else if (inflight || unconfirmed()) setStatus("saving");
    else { setStatus(failed ? "error" : "saved"); const w = idleWaiters; idleWaiters = []; w.forEach((f) => f(true)); }
  }

  // ---- public: local apply ----
  // apply({ops} | ops, {remote}) applies a server batch (remote) or a local-only batch.
  function apply(batch, { remote = false } = {}) {
    const ops = Array.isArray(batch) ? batch : batch.ops;
    const touched = new Set();
    if (remote) {
      revertLayers(0, touched);
      try { applyRaw(ops, touched); }
      catch (e) { console.warn("remote batch diverged", e); needResync = true; }
      reapplyLayers(0, touched);
      notify(touched);
      if (needResync) resync();
      return null;
    }
    const inv = applyRaw(clone(ops), touched);
    notify(touched);
    return inv;
  }

  // Temporary local layer (live drawing, ghost duplicates). revert() removes it wherever it sits.
  function applyTemp(ops) {
    const touched = new Set();
    const L = { kind: "temp", ops: clone(cleanOps(ops)), inv: null };
    L.inv = applyRaw(L.ops, touched);
    layers.push(L);
    notify(touched);
    return {
      get ops() { return L.ops; },
      revert() {
        const i = layers.indexOf(L);
        if (i < 0) return;
        const t = new Set();
        revertLayers(i, t);
        layers.splice(i, 1);
        reapplyLayers(i, t);
        notify(t);
      },
    };
  }

  // ---- public: commit ----
  function commit(ops, label = "") {
    if (!ops || !ops.length) return Promise.resolve({ ok: true, seq: null });
    if (!api) return Promise.resolve({ ok: false, error: "read-only" });
    const L = { kind: "batch", ops: clone(cleanOps(ops)), inv: null, label };
    const touched = new Set();
    try {
      // Fill omitted z (add/move) locally so the server keeps the same order.
      L.inv = applyRaw(L.ops, touched);
    } catch (e) {
      console.warn("commit rejected locally", e, ops);
      emit("error", "이 편집은 적용할 수 없습니다.");
      return Promise.resolve({ ok: false, error: String(e.message || e) });
    }
    // Keep temporary layers on top: insert the batch below them.
    let at = layers.length;
    while (at > 0 && layers[at - 1].kind === "temp") at--;
    if (at < layers.length) {
      // Rebase temps over the new batch (rare: a commit during a live drag).
      const t = new Set();
      applyRaw(L.inv, t);
      revertLayers(at, t);
      L.inv = applyRaw(L.ops, t);
      layers.splice(at, 0, L);
      reapplyLayers(at + 1, t);
      for (const id of t) touched.add(id);
    } else layers.push(L);
    notify(touched);
    const p = new Promise((resolve) => { L.resolve = resolve; });
    schedule();
    refreshStatus();
    return p;
  }

  function schedule() {
    if (scheduled || inflight || retryTimer) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; send(); });
  }

  async function send() {
    if (inflight || retryTimer) return;
    const pending = layers.filter((l) => l.kind === "batch" && !l.sent);
    if (!pending.length) { refreshStatus(); if (needResync) resync(); return; }
    // Coalesce queued batches into one request (<= MAX_OPS ops; a single oversized batch goes alone).
    const pick = [];
    let count = 0;
    for (const l of pending) {
      if (pick.length && count + l.ops.length > MAX_OPS) break;
      pick.push(l); count += l.ops.length;
    }
    pick.forEach((l) => { l.sent = true; });
    inflight = { layers: pick, seq: null, echoed: false, retried: false };
    await post(inflight);
  }

  async function post(fl) {
    refreshStatus();
    const label = [...new Set(fl.layers.map((l) => l.label).filter(Boolean))].join(", ").slice(0, 200);
    const r = await api.postOps(deck.id, { label, ops: fl.layers.flatMap((l) => l.ops) });
    if (inflight !== fl) return;
    if (r.ok) {
      retryDelay = 500;
      failed = false;
      const seq = r.data?.seq ?? null;
      for (const [id, rev] of Object.entries(r.data?.revs || {})) { const n = nodes.get(id); if (n) n.rev = rev; }
      // Layers stay until our SSE echo arrives, so remote batches with a lower seq still rebase under them.
      if (!fl.echoed) fl.layers.forEach((l) => { l.seq = seq; });
      if (seq == null) dropLayers(fl.layers);
      inflight = null;
      fl.layers.forEach((l) => l.resolve?.({ ok: true, seq }));
    } else if (r.status === 0 || r.status >= 500) {
      // Server briefly unreachable: keep the batch and retry with backoff. Nothing is dropped.
      fl.retried = true;
      retryTimer = setTimeout(() => { retryTimer = 0; post(fl); }, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 10000);
      refreshStatus();
      return;
    } else {
      // 400/403/409: roll back this request's batches.
      inflight = null;
      failed = true;
      const t = new Set();
      const idx = fl.layers.map((l) => layers.indexOf(l)).filter((i) => i >= 0);
      if (idx.length) {
        const from = Math.min(...idx);
        revertLayers(from, t);
        dropLayers(fl.layers);
        reapplyLayers(from, t);
      }
      notify(t);
      const msg = r.status === 409 ? "다른 곳에서 먼저 바뀌어 변경을 되돌렸습니다." : `저장하지 못해 되돌렸습니다: ${r.data?.error || r.status}`;
      emit("error", msg);
      fl.layers.forEach((l) => l.resolve?.({ ok: false, status: r.status, error: r.data }));
      // After a retried send the server may already hold it; a 409 means our view is stale.
      if (fl.retried || r.status === 409) needResync = true;
    }
    refreshStatus();
    if (needResync && !layers.some((l) => l.kind === "batch" && l.seq == null)) resync();
    else schedule();
  }

  function dropLayers(list) { for (const l of list) { const i = layers.indexOf(l); if (i >= 0) layers.splice(i, 1); } }

  // ---- SSE ----
  function receive(ev) {
    if (!ev || !Array.isArray(ev.ops)) return;
    const seq = Number(ev.seq) || 0;
    const own = !!api && ev.client === api.client && ev.label !== "undo" && ev.label !== "redo";
    if (own) {
      const mine = layers.filter((l) => l.seq === seq);
      if (mine.length) { reconcile(ev.ops, mine); dropLayers(mine); deck.seq = Math.max(deck.seq, seq); refreshStatus(); return; }
      if (inflight && inflight.seq == null) {
        inflight.seq = seq; inflight.echoed = true;
        reconcile(ev.ops, inflight.layers);
        dropLayers(inflight.layers);
        deck.seq = Math.max(deck.seq, seq);
        return;
      }
    }
    // replayed batch we already hold; an amend (extra ops folded into an existing seq) still applies
    if (seq && seq <= deck.seq && !ev.amend) return;
    deck.seq = Math.max(deck.seq, seq);
    const touched = new Set();
    // Layers confirmed with a lower seq are already under this batch on the server.
    let from = 0;
    while (from < layers.length && layers[from].seq != null && layers[from].seq < seq + (ev.amend ? 1 : 0)) from++;
    revertLayers(from, touched);
    try { applyRaw(ops2(ev.ops), touched); }
    catch (e) { console.warn("remote batch diverged", e); needResync = true; }
    reapplyLayers(from, touched);
    notify(touched);
    emit("remote", ev);
    if (needResync) resync();
  }
  const ops2 = (ops) => clone(ops);
  function reconcile(ops, mine) {
    const later = new Set(layers.filter((l) => !mine.includes(l)).flatMap((l) => l.ops.map((o) => o.id || o.node?.id)));
    const t = new Set();
    for (const o of ops) {
      const id = o.id || o.node?.id;
      const n = nodes.get(id);
      if (!n) continue;
      const rev = o.rev ?? o.node?.rev;
      if (rev) n.rev = rev;
      const z = o.z ?? o.node?.z;
      if (z && z !== n.z && !later.has(id)) { unindex(n.id, n.parent); n.z = z; index(n.id, n.parent); t.add(n.id); }
    }
    notify(t);
  }

  let resyncing = null;
  function resync() {
    if (!api) return Promise.resolve();
    if (inflight) { needResync = true; return Promise.resolve(); }
    if (resyncing) return resyncing;
    needResync = false;
    resyncing = (async () => {
      const r = await api.getDeck(deck.id);
      if (!r.ok) { needResync = true; resyncing = null; return; }
      const before = new Set(nodes.keys());
      const t = new Set();
      load(r.data);
      dropLayers(layers.filter((l) => l.seq != null && l.seq <= deck.seq));
      layers.forEach((l) => { l.sent = false; l.seq = null; });
      reapplyLayers(0, t);
      for (const id of before) t.add(id);
      for (const id of nodes.keys()) t.add(id);
      t.add("\0deck");
      notify(t);
      resyncing = null;
      schedule();
    })();
    return resyncing;
  }

  // ---- undo / redo (server-side, deck-wide) ----
  function whenIdle(timeout = 4000) {
    if (!inflight && !unconfirmed()) return Promise.resolve(true);
    if (retryTimer) return Promise.resolve(false);
    return new Promise((res) => { idleWaiters.push(res); setTimeout(() => res(false), timeout); });
  }
  let chain = Promise.resolve();
  function history(kind) {
    chain = chain.then(async () => {
      if (!(await whenIdle())) { emit("error", "저장이 끝난 뒤 다시 시도하세요."); return { ok: false }; }
      const r = await api[kind](deck.id);
      if (!r.ok) { emit("error", kind === "undo" ? "실행 취소하지 못했습니다." : "다시 실행하지 못했습니다."); return r; }
      if (r.data?.seq == null) emit("error", kind === "undo" ? "실행 취소할 작업이 없습니다." : "다시 실행할 작업이 없습니다.");
      else if (!sse?.connected) await resync();
      return r;
    }).catch(() => ({ ok: false }));
    return chain;
  }

  let sse = null;
  const store = {
    deck, nodes, childIds,
    // W2's renderer/panels take node objects; editor modules use the id variants.
    children: (id = null) => childIds(id).map((c) => nodes.get(c)),
    pageOf: pageNode,
    pageIdOf: (id) => pageNode(id)?.id ?? null,
    get status() { return status; },
    get pending() { return unconfirmed() || !!inflight; },
    apply, applyTemp, commit, receive, resync,
    undo: () => history("undo"),
    redo: () => history("redo"),
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    get subscriberCount() { return subs.size; },
    on(type, fn) { listeners[type].add(fn); return () => listeners[type].delete(fn); },
    attachEvents(conn) { sse = conn; },
    get(id) { return nodes.get(id) || null; },
  };
  return store;
}
