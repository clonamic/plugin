# Format and contract

The single source of truth for the data model, the edit operations, the HTTP API, and the browser module boundaries. `assets/web/schema.json` holds every type, prop, default, and enum; the Python validator (`scripts/ops.py`) and the browser (`js/schema.js`) both read it. Change the model there first.

## 1. Document model

A **deck** is one document. It holds a flat set of **nodes**. Each node:

```json
{"id": "r_8f2KxQ1a", "type": "rect", "parent": "p_1", "z": "a0", "rev": 42, "props": {"x": 10, "y": 20, "w": 300, "h": 120}}
```

- `id`: `[A-Za-z0-9_-]{1,32}`, unique in the deck, chosen by the client (browser or AI). Browser ids: type prefix + `_` + 8 random chars.
- `type`: one of `schema.types`.
- `parent`: `null` only for `page`. Otherwise the id of a container (`schema.containers`). `section` may only sit directly in a page. No cycles.
- `z`: fractional-index key `[0-9A-Za-z]+`, compared as plain strings (ASCII order). Siblings render bottom→top in ascending `z`. Omitted on add/move → server puts it above the top sibling.
- `rev`: set by the server to the op `seq` that last changed the node. Clients never send it except as an optimistic-concurrency guard.
- `props`: sparse. A missing key means the default: `schema.typeDefaults[type]` over `schema.props[type]` defaults over `schema.common` defaults. Pages ignore `x`, `y`, `rotation`, flips, `constraints`, `layoutChild`; they use `cx`, `cy` (canvas position of the page's top-left).

**Coordinates.** `x`, `y` are relative to the parent's top-left (page or frame or group or section or boolean). `w`, `h` are the unrotated box; `rotation` is degrees clockwise around the box center, then `flipX`/`flipY` mirror around the center. 1 unit = 1 CSS px on canvas at 100% = 1 pt in PDF.

**Groups and booleans** keep `x, y, w, h` equal to their children's union box. Whenever an edit changes a child, the editor recomputes the box and, in the same op batch, shifts the group by the delta and the children by the inverse so nothing moves on screen.

**Auto-sized geometry.** For text with `autoResize` `WIDTH_AND_HEIGHT` or `HEIGHT`, and for auto-layout frames with `HUG` sizing, the stored `w`/`h` is a hint. The renderer lays them out with CSS and `renderer.measure(id)` returns the real box. Editors use the measured box for selection, snapping, and alignment, and write the measured `w`/`h` back once when an edit of that node ends (inside the same batch).

### 1.1 Value shapes

- Color: `"#RRGGBBAA"` uppercase hex.
- Paint (`fills[]`, `strokes[]`, bottom→top):
  - common: `{type, visible: true, opacity: 0..1, blend: <blend, default NORMAL>}`
  - `SOLID`: `color`
  - `LINEAR`: `stops: [{p: 0..1, color}]` (≥2), `angle` degrees (0 = left→right, clockwise)
  - `RADIAL` / `DIAMOND`: `stops`, `cx`, `cy` (0..1 of box), `rx`, `ry` (0..1 of box, default 0.5)
  - `ANGULAR`: `stops`, `cx`, `cy`, `angle`
  - `IMAGE`: `asset` (sha256 hex), `mode` FILL|FIT|CROP|TILE, `scale` (TILE, 1 = 100%), `rotation` 0|90|180|270, `crop` `{x,y,w,h}` 0..1 (CROP), `filters` `{exposure, contrast, saturation, temperature, tint, highlights, shadows}` each −1..1 default 0.
- `stroke`: `{weight, align INSIDE|CENTER|OUTSIDE, sides: null | {t,r,b,l} (rect/frame/page only), dash: [dash, gap, ...] px ([] = solid), dashCap, join, miterLimit, capStart, capEnd (line/vector open ends; ARROW_* etc.)}`.
- Effect (`effects[]`): `{type, visible: true}` plus
  - `DROP_SHADOW` / `INNER_SHADOW`: `color, x, y, blur ≥0, spread, blend` (+ `showBehind` bool for drop). At most 8 of each.
  - `LAYER_BLUR`: `radius`, optional `progressive: {startRadius, start: [x,y], end: [x,y]}` (0..1). At most 1.
  - `BACKGROUND_BLUR`: `radius`. At most 1.
- `radius`: number (all corners) or `[tl, tr, br, bl]`.
- `layout` (auto layout on frame/page, `null` = off): `{dir HORIZONTAL|VERTICAL, wrap bool, gap, gapCross, pad: [t,r,b,l], alignMain, alignCross, sizingH FIXED|HUG|FILL, sizingV, strokesIncluded bool, reverseZ bool}`.
- `layoutChild` (child of an auto-layout parent): `{sizingH, sizingV, absolute bool, minW?, maxW?, minH?, maxH?}`.
- `constraints`: `{h: constraintH, v: constraintV}` (children of non-auto-layout frames/pages).
- Guide (`guides[]`): `{type GRID|COLUMNS|ROWS, count (0 = auto), size, gutter, margin, offset, align, color, visible}`.
- `ellipse.arc`: `{start, end}` radians (0 = +x axis, clockwise), `inner` 0..1 (donut ratio).
- `vector.paths`: `[{closed: bool, pts: [{x, y, ix, iy, ox, oy}]}]` in the node's box coordinates; `ix,iy` / `ox,oy` are absolute in-/out-handle positions (equal to the point = sharp corner). Pencil output is a vector too.
- Text:
  - `runs: [{t: string, s?: TextStyle-partial, fill?: color, link?: url}]`; `"\n"` inside `t` breaks paragraphs. Concatenated `t` is the text. The text is never HTML; the renderer builds DOM with `textContent` only. `link` becomes a real `<a>` in `present` and `print` (clickable in the PDF) only for `http:`, `https:`, `mailto:`; it keeps the run's color and is underlined in every mode.
  - `style`: the base TextStyle `{font, weight 100..900, italic, size ≥1, lineHeight {unit AUTO|PX|PERCENT, value}, letterSpacing {unit PX|PERCENT, value}, decoration, case}`. A run's `s` overrides it. Text color: run `fill`, else the node's first visible SOLID fill.
  - `paras: [{list NONE|BULLET|ORDERED, level 0..8}]`, index = paragraph index; missing = NONE.
- Table: `cols: [w...]`, `rows: [h...]`, `cells: {"r,c": {runs, style?, fill?: color, alignH?, alignV?}}`, `border: {color, weight}`, `header` (first row bold + tinted).
- Video: `asset`, `poster` (image asset; PDF shows the poster or the first frame).

## 2. Edit operations

All writes go through op batches. A batch is atomic: all ops apply or none.

| op | shape | meaning |
|---|---|---|
| `add` | `{op:"add", node:{id, type, parent, z?, props}}` | create; id must be new |
| `set` | `{op:"set", id, props:{k: v \| null}, rev?}` | shallow merge of top-level props; `null` deletes the key (back to default); arrays/objects replace wholesale |
| `del` | `{op:"del", id, rev?}` | delete node and its whole subtree |
| `move` | `{op:"move", id, parent, z?, rev?}` | reparent and/or reorder (coordinates are not converted; send a `set` in the same batch) |
| `deck` | `{op:"deck", props:{name}}` | deck-level fields |

- `rev` guard: if given and the node's current `rev` differs, the batch is rejected with 409 and nothing applies. The browser omits `rev` for its own interactive edits (last writer wins per node); the AI CLI always sends the `rev` it read.
- Validation (server, `ops.py`): known type, known prop keys for the type (unknown → 400), kinds and ranges from `schema.json`, enums, colors, id format, parent exists and is a container, page parent null, section parent is a page, no cycle, string limits, ≤ 5,000 ops per batch, asset hashes `[0-9a-f]{64}`. The 400 body names the op index and the key.
- Each applied batch gets `seq` (deck-wide, increasing) and is stored with its inverse batch for undo.

**Undo/redo** is deck-wide and server-side: `POST …/undo` applies the inverse of the most recent batch not yet undone (any actor: user or AI); `…/redo` re-applies. Depth 100. A new batch clears the redo stack. Undo/redo are themselves broadcast as normal `ops` events (with `label: "undo"`/`"redo"`).

## 3. HTTP API

Server binds `127.0.0.1` only. Requests whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>` get 403. Every non-GET request needs header `X-PPT-Token: <token>` (the token is in `server.json` for the CLI and in `<meta name="ppt-token">` in the served `index.html` / `print.html`). JSON bodies ≤ 20 MB; uploads ≤ 200 MB. Responses over 8 KB are gzip-compressed when the request accepts it.

| method path | body → response |
|---|---|
| `GET /api/health` | `{ok, app:"ai-html-ppt", version}` |
| `GET /api/decks` | `[{id, name, updated, pages}]` (most recent first) |
| `POST /api/decks` | `{name, preset?}` → 201 `{id}`; creates one page with the preset (default `SLIDE_16_9`) |
| `DELETE /api/decks/{d}` | 200 `{ok}` |
| `GET /api/decks/{d}` | `{deck:{id, name, seq}, nodes:[...]}` |
| `GET /api/decks/{d}/outline[?page=id]` | `text/plain` outline for the AI (§5) |
| `GET /api/decks/{d}/nodes?ids=a,b` or `?page=id` | `{seq, nodes:[...]}` (page = page + subtree) |
| `POST /api/decks/{d}/ops` | `{actor:"user"\|"ai", client, label, ops}` → `{seq, revs:{id:rev}}` / 400 `{error, index, key}` / 409 `{error, conflicts:[{id, rev, node}]}` |
| `POST /api/decks/{d}/undo`, `/redo` | `{client}` → `{seq}` or `{seq:null}` when nothing to do |
| `POST /api/assets` | raw bytes, `Content-Type` image/* or video/* → `{hash, mime, w?, h?}` (dedup by sha256). CLI `ppt.py asset FILE` uploads a local file the same way. |
| `GET /assets/{hash}` | bytes, `Cache-Control: public, max-age=31536000, immutable` |
| `GET /api/decks/{d}/messages` | `[{id, role, text, meta, status, created}]` (last 200) |
| `POST /api/decks/{d}/messages` | `{role:"user"\|"ai", text, meta?:{page, selection:[ids]}}` → 201 `{id}` |
| `GET /api/wait?deck=&token=&timeout=` | AI long-poll: `{status: message\|timeout\|closed\|replaced, message?}` (same semantics as create-agent) |
| `GET /api/events?deck=&client=` | SSE (§4) |
| `POST /api/decks/{d}/pdf` | `{pages:[ids] (empty = all, in order), mode:"single"\|"each", dir}` → `{files:[abs paths]}`; 503 `{error, fallback:"print"}` when Chrome is missing |
| `GET /print.html?deck=&pages=a,b` | print page with the deck JSON inlined |
| `POST /api/shutdown` | `{}` → `{ok}`; server closes SSE streams and exits |

Static files: `/` → `index.html`, `/schema.json`, `/js/**`, `/vendor/**`, `/app.css` with strong ETags.

## 4. Events (SSE)

`GET /api/events?deck=<d>&client=<tab id>`; event ids are op `seq`. On reconnect the browser sends `Last-Event-ID`; the server replays retained batches after it, or sends `reset` if they are gone (client refetches the deck).

- `event: ops` → `{seq, actor, client, label, ops}` (applied ops with server-assigned `z` and `rev` filled in: `add.node.rev`, and `set/del/move` carry the new `rev`). A tab that receives its own `client` batch only reconciles `rev`/`z`.
- `event: msg` → a chat message object.
- `event: reset` → `{}`.
- `event: closing` → `{}` (server shutting down).
- `: ping` comment every 15 s.

The server counts open SSE streams. It shuts down 10 s after the last stream closes, or on `/api/shutdown`. Until a stream ever opens, it stays while a `wait` is in flight and stops 180 s after start or after the last CLI call (`X-PPT-Client: cli`), so a headless AI keeps it while it works.

## 5. AI outline

Compact, line-based, two-space indent per depth, order = render order (bottom→top). Text is cut to 80 chars.

```
deck 3 "3분기 보고" seq=42
page p_1 "표지" 1920x1080 SLIDE_16_9 landscape rev=40
  rect r_bg "배경" 0,0 1920x1080 fill=#FFFFFFFF rev=12
  text t_title "제목" 120,200 800x120 size=72 "2026 3분기 실적" rev=40
  frame f_card "카드" 120,400 600x300 layout=VERTICAL gap=16 rev=33
    text t_c1 "본문" 24,24 552x40 "매출 12% 증가" rev=33
```

## 6. Browser modules (ES modules, no build step)

Files under `assets/web/`. Owner in brackets. Modules talk only through these exports.

- `js/schema.js` [W3]: `await loadSchema()`, `SCHEMA`, `defaultsFor(type)`, `propsOf(node)` (resolved with defaults), `newId(type)`, `zBetween(a, b)`.
- `js/state.js` [W3]: `createStore(api)` → `{deck, nodes: Map<id,node>, children(id), pageOf(id), apply(batch, {remote}), commit(ops, label) → Promise, undo(), redo(), subscribe(fn(changedIds, deletedIds))}`. Optimistic: applies locally first, rolls back on 400/409.
- `js/api.js` [W3]: fetch wrappers with the token, SSE with `Last-Event-ID`, `uploadAsset(file) → {hash}`.
- `js/render.js` [W2]: `createRenderer({root, mode: "edit"|"present"|"print", assetUrl: hash→url, links?})` (`links` defaults to `mode !== "edit"`; thumbnails and presenter previews pass `false`) → `{mount(store), update(changedIds, deletedIds), measure(id) → {x, y, w, h} (page coordinates, unrotated), elementOf(id), pageElementOf(id), setPreview(id, partialProps) (transient, no commit), clearPreview(id), destroy()}`. The same code renders canvas, present, and print. In `edit` mode pages sit at `cx, cy`; in `present`/`print` one page at 0,0. Every node element carries `data-id`.
- `js/geometry.js` [W2]: `polygonD(n, w, h, r)`, `starD(n, inner, w, h, r)`, `arcD(arc, w, h)`, `smoothRectD(w, h, radius, smoothing)`, `vectorD(paths)`, `booleanD(op, items)`, `flattenToVector(id, store) → props`, `outlineStrokeToVector(id, store) → props`, `bboxOfD(d)`. Uses `vendor/polygon-clipping-0.15.7.min.js` for booleans.
- `js/text.js` [W2]: text rendering helpers plus `beginTextEdit(id, ctx) → {end()}` (contenteditable on the rendered element; turns DOM edits into `runs`; exposes `applyStyle(partial)` for the current range; commits one `set` on end).
- `js/layout.js` [W2]: `resizeOps(store, id, newBox) → ops` (applies constraints to children; auto layout handled by CSS), `hugBox(id)`.
- `js/panels/design.js` [W2]: `mountDesignPanel(el, ctx)`, where `ctx = {store, selection, renderer, commit(ops, label), preview(id, props), clearPreview(id), uploadAsset(file)}`. Sections: page (preset, orientation, background, guides, notes), layout (x/y/w/h/rotation, constraints, auto layout), shape-specific (radius, smoothing, points, inner, arc), text, fills, strokes, effects, blend/opacity, export (PDF of selection's page). Numeric fields accept math expressions and scrub-drag.
- `js/main.js`, `js/viewport.js`, `js/tools.js`, `js/select.js`, `js/snap.js`, `js/shortcuts.js`, `js/present.js`, `js/panels/{layers,pages,chat,export}.js`, `index.html`, `print.html`, `app.css` [W3]. `selection = {ids: [], set(ids), add(id), toggle(id), clear(), on(fn)}`; `selection` and `ctx` are created in `main.js`.
- `print.html` [W3] loads `render.js` in `print` mode, renders the requested pages each into `<section style="page: P<i>">` with `@page P<i> {size: <w>pt <h>pt; margin: 0}` and the page content scaled ×4/3 (CSS `zoom`) so 1 unit = 1 pt; it sets `window.__PPT_READY__ = true` after `document.fonts.ready` and every image has decoded.

## 7. Quality bars

- Canvas, present, and print share `render.js`; nothing renders a node any other way.
- Dragging, resizing, rotating, scrubbing: preview only (`setPreview`), one `commit` on pointer-up.
- 1,000-node deck: first render < 1 s, pan/zoom average frame ≤ 16.7 ms (one `transform` on the world element; offscreen pages use `content-visibility: auto`).
- No console errors. No external network requests (fonts are local).
- UI text is Korean. Keyboard shortcuts match Figma; the editor lists them all under ⌃⇧?.

## 8. Clarifications (binding, from the backend implementation)

- Deck ids are integers.
- Nested objects are strict: unknown keys inside paints, stroke, effects, layout, layoutChild, constraints, style, runs, paras, cells, guides are rejected with 400. Never add helper keys (e.g. a paint `id`); keep UI-only state outside props. Partial objects are fine (`style: {size: 72}`). Colors must be uppercase `#RRGGBBAA`.
- `z` keys: base-62 fractional keys compared as ASCII strings, generated keys never end in `0`. The server's `z_between` (ops.py) follows rocicorp-style fractional indexing; `js/schema.js` `zBetween` must produce keys with the same properties (any key strictly between its neighbours is accepted).
- SSE: open `/api/events?deck=<d>&client=<c>&last=<deck.seq>` so edits between the deck fetch and the stream opening are replayed; `Last-Event-ID` is used on reconnects.
- `/api/wait` also needs `X-PPT-Token`. Requests with `Sec-Fetch-Site: cross-site` get 403.
- `print.html` inlined data: `{deck:{id, name, seq}, pages:[ids in requested order], nodes:[...], assets:[hashes]}`.
- New decks start with one page named "페이지 1" (rev 0, not undoable). Undo/redo bodies accept optional `actor`.
- PDF names: `single` → `<deck>.pdf`; `each` → `<deck>-<position in deck>-<page name>.pdf`; existing files get ` (2)`.
- Every headless Chrome launch uses `--use-mock-keychain --password-store=basic` and a fresh `--user-data-dir` (no macOS keychain dialog).

## 9. AI integration: session status, agent graph, inline edits, focus pins, snapshots

### 9.1 Session status
- `ppt.py open --host <claude-code|codex|cursor|grok|other>` registers the host for the returned `session`. Every `/api/wait` call refreshes `seen` for that session.
- `GET /api/decks/{d}/ai` → `{connected, host, seen_s, run}`; `connected` = a wait is in flight now or `seen_s < 10`. `run` = the latest run summary `{id, node, status, label, tries}` or null.
- SSE `event: ai` carries the same object whenever it changes (connect, disconnect after 10 s silence, node change).

### 9.2 Agent graph (LangGraph-style, stdlib, `scripts/agent.py`)
- Engine: `StateGraph` with nodes, plain edges, conditional edges (a function of state → next node name), `END`, `interrupt` (pause until a human resumes), and a SQLite checkpointer. Each node transition is one checkpoint (`runs` + `steps` tables), so a run resumes after a restart.
- Graph `edit`:
  - `intake` (code): builds context — `message`, `meta` (page, selection, mode, focus), page outline, a snapshot PNG of the current page, full props of selected nodes and their subtrees, focus pins with a snapshot PNG per pin.
  - `plan` (AI): host AI returns `{kind: "edit"|"answer"|"pdf"|"check", ops?, label?, pdf?: {pages, mode, dir}, pages?, note?}`.
  - route after `plan`: `answer` → `reply`; `pdf` → `export`; `check` (review with nothing to change yet) → `verify` on `pages` (`[]` = all); `edit` with ≥ 20 deletions or any page deletion → `confirm` (interrupt) → `apply` on approval / `reply` on rejection; otherwise → `apply`.
  - `apply` (code): validates and commits the ops as actor `ai` with the label; `mode: "inline"` restricts ops to the selection's subtrees (`add` only under them) — anything else fails the step with the offending op index.
  - `verify` (code): `agent.check` — measured text boxes (print.html `measure` mode), rendered sizes of auto-sized nodes written into the applied batch, `lint.py` — on the affected pages (a `check` plan: its pages, sizes written as a new batch "자동 크기 맞춤"), plus one snapshot of each page. Errors and `tries < 2` → back to `plan` with `issues`; otherwise → `reply` with remaining warnings.
  - `export` (code): runs pdf.py → `reply`.
  - `reply` (AI): host returns `{text, resolved_focus?: [ids], suggestions?: [strings]}`; posted as an AI chat message (suggestions become `추천:` lines); resolved pins → `resolved`.
- A web message (role user) creates a run (status `active`, node `intake`); `wait` returns `{status:"message", message, run}`.
- CLI: `ppt.py agent next --deck D --run R` advances code nodes until an AI node, an interrupt, or END and returns `{run, node: "plan"|"reply"|"waiting_user"|"end", instruction, state}`; `instruction` states the exact JSON to submit. `ppt.py agent submit --deck D --run R --node <plan|reply>` (stdin JSON) records the output and advances. When the user answers a `confirm` card in the web (`POST /api/decks/{d}/runs/{r}/confirm {ok}`), `wait` returns `{status:"resume", run}`.
- Endpoints: `GET /api/decks/{d}/runs?limit=`, `GET /api/decks/{d}/runs/{r}` (state + steps), `POST …/runs/{r}/next`, `POST …/runs/{r}/submit {node, output}`, `POST …/runs/{r}/confirm {ok}`.

### 9.3 Inline AI edits
- Browser sends `POST …/messages {role:"user", text, meta:{page, selection:[ids], mode:"inline"}}`. The UI marks the target elements as busy until the run's node is `end`, then shows "AI가 바꾼 내용 · 되돌리기".

### 9.4 Focus pins (not nodes; never rendered in canvas content or PDF)
- Table `focus(id, deck_id, page, ids JSON, rect JSON, note, status open|sent|resolved, created, updated)`.
- `GET /api/decks/{d}/focus`, `POST {page, ids?, rect?: {x,y,w,h} page coords, note}` → 201 `{id}`, `PATCH /api/decks/{d}/focus/{id} {note?, status?}`, `DELETE …/focus/{id}`. Changes broadcast as SSE `event: focus` `{pins}`.
- "AI에게 보내기" posts a message with `meta.focus: [pin ids]`; `intake` marks them `sent`.

### 9.5 Snapshots and measurement (print.html modes, run by headless Chrome)
- `print.html?deck=&pages=<one id>&mode=snapshot&rect=x,y,w,h&scale=s` renders that page region at CSS px × `scale` (no ×4/3 pt zoom), region's top-left at 0,0, body exactly `w·s × h·s`. Server screenshots with `--screenshot --window-size=<w·s>,<h·s> --hide-scrollbars`. Default rect = whole page, scale 1 (max 4, max 4096 px per side).
- `print.html?deck=&pages=a,b&mode=measure` renders normally and, after ready, appends `<script id="ppt-measure" type="application/json">{"<id>": {"x","y","w","h","sw","sh"}}</script>` for every text and table node (page coords; `sw`/`sh` = content scroll size, overflow when > `w`/`h`). Server reads it via `--dump-dom`.
- `GET /api/decks/{d}/snapshot?page=&rect=&ids=&scale=` → `{path, w, h}` (ids → union box of those nodes + 24 px margin). Files under `~/.clonamic/ai-html-ppt/snapshots/`, newest 50 kept. CLI `ppt.py snapshot --deck --page [--ids a,b | --rect x,y,w,h] [--scale 2]`.

### 9.6 Lint (`scripts/lint.py`, used by `verify`)
- error: node outside its page bounds (fully or > 10 % outside), text overflow in fixed boxes (from measure), missing asset, empty text.
- warning: text smaller than 18 px on slide presets / 8 pt on paper presets, text-on-background contrast < 4.5:1, or < 3:1 for large text (WCAG: 18 pt, or 14 pt bold; 1 px = 0.75 pt on slides), using the nearest underlying solid fill and the node color only when a run has no own `fill`; overlapping text boxes (measured boxes when given; text placed by auto layout without one is skipped); element off by < 2 px from a sibling edge (near-miss alignment; not among auto layout children).
- CLI `ppt.py check --deck D [--pages a,b]` (`POST /api/decks/{d}/check {pages}`) runs the same check outside a run: `{issues, warnings, verify_notes, autosized, counts}` (`counts` per lint code).
- Output `[{level, code, id, page, message (Korean)}]`.

## 10. Renderer additions (binding, from the renderer implementation)
- `createRenderer({..., page})`, plus `ready()` (resolves when referenced images, including CSS backgrounds, are loaded; print.html awaits it), `setPage(id)`, `store`, `root`; module exports `activeRenderer()` and `normalize(type, props)` (fills partial nested objects from defaults; read nested props through it).
- `mount(store)` subscribes to the store; callers never forward store changes to `update` themselves.
- Node transform: `translate · rotate(θ) · scale(flip)` around the box center (`geometry.nodeMatrix`).
- The canvas root carries CSS var `--zoom`. DOM classes: `.ppt-n[data-id]`, `.ppt-c` (children/flex box), `.ppt-tx`, `[data-cell]`, `[data-page-label]`.
- Events on `window`: `ppt:text-edit-end` `{id, cell}`, `ppt:export-pdf` `{pages}`.
- Text: `autoResize` is the source of truth for text sizing, also inside auto layout. Enter = `"\n"` (new paragraph), Shift+Enter = U+2028 (soft break).
- Tables: `w`/`h` equal the sums of `cols`/`rows`. Gradients: at most 64 stops.

## 11. Editor additions (binding, from the editor implementation)
- `createStore(api, data, deckId)`; `api = null` makes a read-only store (print.html). `store.children(id)` → child node objects sorted by z, `store.pageOf(id)` → page node; `store.childIds(id)`, `store.pageIdOf(id)`, `store.get(id)`; `store.on('status'|'deck'|'remote'|'error', fn)`, `applyTemp(ops)` (local preview layers), `receive(event)`, `resync()`, `pending`.
- `ctx` also carries `assetUrl`, `currentPage()`, `setCurrentPage()`, `onPageChange()`, `viewport`, `flags`, `tools`, `shortcuts`, `pages`, `layers`, `present`, `openExport`. `ctx.commit` recomputes group/boolean boxes before sending.

## 12. AI integration readings (binding, from the backend implementation)
- `ppt.py open --host` registers via `POST /api/sessions {session, host}`. `GET …/snapshot` needs `X-PPT-Token`; 503 without Chrome.
- A user message `POST …/messages` returns 201 `{id, run}`. Run statuses: `active`, `waiting_user`, `done`, `failed`; `meta.mode` is `inline` or `chat`. `next` returns `{run, node, status, instruction, state}`.
- Confirm: when a run pauses at `confirm`, the server posts an AI chat message with `meta: {kind: "confirm", run, deletions, pages, label}`; the web answers `POST …/runs/{r}/confirm {ok}`.
- The AI reply message carries `meta: {run, suggestions}`.
- `apply` failures (scope, invalid op, stale rev) go back to `plan` with `state.issues` under the same retry limit (2) as `verify`; batches already applied stay applied.
- The server calls print.html with `&mode=snapshot|measure&rect=x,y,w,h&scale=s&token=…`; rect is clamped to the page, scale ≤ min(4, 4096/w, 4096/h).
