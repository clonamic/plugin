// HTTP + SSE wrappers (format.md §3, §4). Every call resolves to {ok, status, data}; status 0 = unreachable.

let TOKEN = document.querySelector('meta[name="ppt-token"]')?.content || "";
// After a server restart the token may change: read the current one from the served index.html.
let tokenRead = null;
async function refreshToken() {
  if (!tokenRead) tokenRead = (async () => {
    try {
      const html = await (await fetch("/", { cache: "no-store" })).text();
      const m = html.match(/<meta name="ppt-token" content="([^"]*)"/);
      if (m && m[1] && m[1] !== TOKEN) { TOKEN = m[1]; document.querySelector('meta[name="ppt-token"]')?.setAttribute("content", TOKEN); return true; }
    } catch (_) { /* still down */ }
    return false;
  })().finally(() => { setTimeout(() => { tokenRead = null; }, 0); });
  return tokenRead;
}
export const CLIENT = "c_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);

export async function request(method, path, body, { raw = false, headers = {}, retried = false } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: {
        ...(method !== "GET" ? { "X-PPT-Token": TOKEN } : {}),
        ...(body !== undefined && !raw ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    });
  } catch (_) {
    return { ok: false, status: 0, data: { error: "서버에 연결할 수 없습니다." } };
  }
  // 403 on a write: the server may have restarted with a new token. Re-read it once and retry.
  if (res.status === 403 && method !== "GET" && !retried && await refreshToken()) return request(method, path, body, { raw, headers, retried: true });
  let data = null;
  const type = res.headers.get("Content-Type") || "";
  try { data = type.includes("json") ? await res.json() : await res.text(); } catch (_) { data = null; }
  if (!res.ok && (data === null || typeof data !== "object")) data = { error: typeof data === "string" && data ? data : `HTTP ${res.status}` };
  return { ok: res.ok, status: res.status, data };
}

const enc = encodeURIComponent;
export const api = {
  client: CLIENT,
  health: () => request("GET", "/api/health"),
  listDecks: () => request("GET", "/api/decks"),
  createDeck: (name, preset) => request("POST", "/api/decks", preset ? { name, preset } : { name }),
  deleteDeck: (d) => request("DELETE", `/api/decks/${enc(d)}`),
  getDeck: (d) => request("GET", `/api/decks/${enc(d)}`),
  postOps: (d, body) => request("POST", `/api/decks/${enc(d)}/ops`, { client: CLIENT, actor: "user", ...body }),
  undo: (d) => request("POST", `/api/decks/${enc(d)}/undo`, { client: `${CLIENT}-u` }),   // own id would look like an optimistic echo
  redo: (d) => request("POST", `/api/decks/${enc(d)}/redo`, { client: CLIENT }),
  messages: (d) => request("GET", `/api/decks/${enc(d)}/messages`),
  postMessage: (d, msg) => request("POST", `/api/decks/${enc(d)}/messages`, msg),
  pdf: (d, body) => request("POST", `/api/decks/${enc(d)}/pdf`, body),
  // AI integration (format.md §9)
  aiStatus: (d) => request("GET", `/api/decks/${enc(d)}/ai`),
  runs: (d, limit = 10) => request("GET", `/api/decks/${enc(d)}/runs?limit=${limit}`),
  run: (d, r) => request("GET", `/api/decks/${enc(d)}/runs/${enc(r)}`),
  undoRun: (d, r) => request("POST", `/api/decks/${enc(d)}/runs/${enc(r)}/undo`, { client: `${CLIENT}-u` }),   // own id would look like an optimistic echo
  confirmRun: (d, r, ok) => request("POST", `/api/decks/${enc(d)}/runs/${enc(r)}/confirm`, { ok }),
  pins: (d) => request("GET", `/api/decks/${enc(d)}/focus`),
  addPin: (d, pin) => request("POST", `/api/decks/${enc(d)}/focus`, pin),
  updatePin: (d, id, patch) => request("PATCH", `/api/decks/${enc(d)}/focus/${enc(id)}`, patch),
  deletePin: (d, id) => request("DELETE", `/api/decks/${enc(d)}/focus/${enc(id)}`),
  async uploadAsset(file) {
    const r = await request("POST", "/api/assets", file, { raw: true, headers: { "Content-Type": file.type || "application/octet-stream" } });
    if (!r.ok) throw new Error(r.data?.error || "업로드 실패");
    return r.data;   // {hash, mime, w?, h?}
  },
};
export const uploadAsset = (file) => api.uploadAsset(file);
export const assetUrl = (hash) => `/assets/${hash}`;

// SSE. Native EventSource reconnects by itself and sends Last-Event-ID. When it gives up (CLOSED)
// we reopen with ?last=<current seq>.
export function connectEvents(deck, h, last = 0) {
  let es = null, closed = false, retry = 1000, timer = 0;
  const safe = (fn) => (e) => { try { fn(e.data ? JSON.parse(e.data) : {}, e); } catch (err) { console.warn("SSE handler", err); } };
  function open() {
    // `last` replays edits made between the deck fetch and the stream opening (format.md §8).
    es = new EventSource(`/api/events?deck=${enc(deck)}&client=${enc(CLIENT)}&last=${enc(typeof last === "function" ? last() : last)}`);
    es.onopen = () => { retry = 1000; h.onState?.("open"); };
    es.addEventListener("ops", safe((d, e) => h.onOps?.(d, e.lastEventId)));
    es.addEventListener("msg", safe((d) => h.onMsg?.(d)));
    es.addEventListener("ai", safe((d) => h.onAI?.(d)));
    es.addEventListener("focus", safe((d) => h.onFocus?.(d)));
    es.addEventListener("reset", safe(() => h.onReset?.()));
    es.addEventListener("closing", safe(() => { closed = true; es.close(); h.onClosing?.(); }));
    es.onerror = () => {
      if (closed) return;
      h.onState?.("error");
      if (es.readyState === EventSource.CLOSED) {
        clearTimeout(timer);
        timer = setTimeout(open, retry);   // `last` (current seq) makes the server replay what we missed
        retry = Math.min(retry * 2, 15000);
      }
    };
  }
  open();
  return { close() { closed = true; clearTimeout(timer); es?.close(); }, get connected() { return es?.readyState === EventSource.OPEN; } };
}
