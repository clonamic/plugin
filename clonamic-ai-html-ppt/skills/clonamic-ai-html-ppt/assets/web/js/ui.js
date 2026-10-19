// Small UI primitives: element builder, toasts, modals, popovers, context menus, icons.

export function el(tag, attrs = {}, ...kids) {
  const node = tag.startsWith("svg:") ? document.createElementNS("http://www.w3.org/2000/svg", tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "on") for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
    else if (k === "text") node.textContent = v;
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k === "html") node.innerHTML = v;   // trusted static markup only (icons)
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return node;
}
export const $ = (sel, root = document) => root.querySelector(sel);

export const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

export function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  } catch (_) { /* storage blocked */ }
  return null;
}

// ---- toasts ----
let toastBox = null;
// actions: [{label, run}] (or the single action/onAction pair); onClick: clicking the message itself.
export function toast(text, { action, onAction, actions = [], onClick, timeout = 4000, kind = "" } = {}) {
  if (!toastBox) { toastBox = el("div", { id: "toasts", role: "status", "aria-live": "polite" }); document.body.append(toastBox); }
  const msg = onClick ? el("button", { type: "button", class: "toast-msg", on: { click: () => onClick() } }, text) : el("span", {}, text);
  const t = el("div", { class: `toast ${kind}` }, msg);
  const close = () => { t.classList.add("out"); setTimeout(() => t.remove(), 180); };
  if (action) actions = [{ label: action, run: onAction }, ...actions];
  for (const a of actions) t.append(el("button", { type: "button", on: { click: () => { close(); a.run?.(); } } }, a.label));
  toastBox.append(t);
  while (toastBox.children.length > 4) toastBox.firstChild.remove();
  if (timeout) setTimeout(close, timeout);
  return close;
}

// ---- modal ----
export function modal({ title, body, actions = [], onClose, wide = false }) {
  const prev = document.activeElement;
  const back = el("div", { class: "modal-back" });
  const box = el("div", { class: `modal${wide ? " wide" : ""}`, role: "dialog", "aria-modal": "true", "aria-label": title });
  const close = (v) => { back.remove(); document.removeEventListener("keydown", onKey, true); prev?.focus?.(); onClose?.(v); };
  const onKey = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); close(null); }
    if (e.key === "Tab") {   // keep focus inside
      const f = [...box.querySelectorAll("button, input, textarea, select, [tabindex]")].filter((x) => !x.disabled && x.offsetParent);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  };
  box.append(el("div", { class: "modal-head" }, el("h2", {}, title),
    el("button", { type: "button", class: "icon-btn", "aria-label": "닫기", title: "닫기", html: ICON.close, on: { click: () => close(null) } })));
  box.append(el("div", { class: "modal-body" }, body));
  if (actions.length) {
    box.append(el("div", { class: "modal-foot" }, ...actions.map((a) => {
      const b = el("button", { type: a.submit ? "submit" : "button", class: a.kind || "", disabled: a.disabled || null }, a.label);
      b.addEventListener("click", async () => { const v = await a.run?.(b); if (v !== false) close(v); });
      a.ref?.(b);
      return b;
    })));
  }
  back.append(box);
  back.addEventListener("pointerdown", (e) => { if (e.target === back) close(null); });
  document.addEventListener("keydown", onKey, true);
  document.body.append(back);
  queueMicrotask(() => (box.querySelector("[autofocus]") || box.querySelector("input, textarea, button.primary") || box).focus?.());
  return { close, box };
}

export function confirmDialog(title, text, okLabel = "확인", danger = false) {
  return new Promise((res) => {
    modal({ title, body: el("p", {}, text), onClose: (v) => res(v === true),
      actions: [{ label: "취소" },{ label: okLabel, kind: danger ? "danger" : "primary", run: () => true }] });
  });
}

// ---- popover / menu ----
let openPop = null;
export function closePopover() { if (openPop) { const p = openPop; openPop = null; p.cleanup(); } }
// anchor: element or {x, y} (client coordinates).
export function popover(anchor, content, { align = "start", side = "bottom", className = "", onClose } = {}) {
  closePopover();
  const pop = el("div", { class: `popover ${className}`, role: "dialog" }, content);
  document.body.append(pop);
  const r = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: anchor.x, right: anchor.x, top: anchor.y, bottom: anchor.y, width: 0, height: 0 };
  const pw = pop.offsetWidth, ph = pop.offsetHeight, vw = innerWidth, vh = innerHeight;
  let x = align === "end" ? r.right - pw : align === "center" ? r.left + r.width / 2 - pw / 2 : r.left;
  let y = side === "top" ? r.top - ph - 6 : r.bottom + (anchor.getBoundingClientRect ? 6 : 0);
  if (y + ph > vh - 8) y = Math.max(8, (anchor.getBoundingClientRect ? r.top - ph - 6 : vh - ph - 8));
  if (y < 8) y = 8;
  x = Math.max(8, Math.min(x, vw - pw - 8));
  pop.style.left = `${x}px`; pop.style.top = `${y}px`;
  const onDown = (e) => { if (!pop.contains(e.target) && !(anchor.contains && anchor.contains(e.target))) closePopover(); };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); closePopover(); anchor.focus?.(); } };
  setTimeout(() => document.addEventListener("pointerdown", onDown, true));
  document.addEventListener("keydown", onKey, true);
  openPop = { el: pop, cleanup() { pop.remove(); document.removeEventListener("pointerdown", onDown, true); document.removeEventListener("keydown", onKey, true); onClose?.(); } };
  return pop;
}

// items: [{label, hint, run, disabled, checked, sep, header, danger}]
export function menu(anchor, items, opts = {}) {
  const list = el("div", { class: "menu", role: "menu" });
  for (const it of items) {
    if (it.sep) { if (list.lastChild && !list.lastChild.classList.contains("sep")) list.append(el("div", { class: "sep", role: "separator" })); continue; }
    if (it.header) { list.append(el("div", { class: "menu-header" }, it.header)); continue; }
    const b = el("button", { type: "button", role: it.checked !== undefined ? "menuitemcheckbox" : "menuitem", class: `menu-item${it.danger ? " danger" : ""}`,
      disabled: it.disabled || null, "aria-checked": it.checked !== undefined ? String(!!it.checked) : null },
    el("span", { class: "check", "aria-hidden": "true" }, it.checked ? "✓" : ""),
    el("span", { class: "label" }, it.label),
    el("span", { class: "hint" }, it.hint || ""));
    b.addEventListener("click", () => { closePopover(); it.run?.(); });
    b.addEventListener("pointerenter", () => it.onHover?.(true));
    b.addEventListener("pointerleave", () => it.onHover?.(false));
    list.append(b);
  }
  while (list.lastChild?.classList.contains("sep")) list.lastChild.remove();
  list.addEventListener("keydown", (e) => {
    const btns = [...list.querySelectorAll("button:not([disabled])")];
    const i = btns.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); btns[(i + 1) % btns.length]?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); btns[(i - 1 + btns.length) % btns.length]?.focus(); }
  });
  const pop = popover(anchor, list, { className: "menu-pop", ...opts });
  if (opts.focus !== false) list.querySelector("button:not([disabled])")?.focus({ preventScroll: true });
  return pop;
}

// ---- icons (own simple 16px line drawings) ----
const s = (d, extra = "") => `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"${extra}>${d}</svg>`;
export const ICON = {
  move: s('<path d="M3 2.5l9 4.2-3.9 1.2L6.8 12z"/>'),
  scale: s('<path d="M3 13V3h10"/><path d="M7 9l6-6M9 3h4v4"/>'),
  hand: s('<path d="M5 8V4.5a1 1 0 012 0V8M7 7.5V3.5a1 1 0 012 0v4M9 7.5V4.5a1 1 0 012 0V9c0 2.8-1.8 4.5-4 4.5-1.6 0-2.6-.8-3.4-2.1L2.4 9.3a1 1 0 011.6-1.1L5 9.5"/>'),
  frame: s('<path d="M5 2v12M11 2v12M2 5h12M2 11h12"/>'),
  section: s('<rect x="2" y="4" width="12" height="10" rx="1"/><path d="M2 4V2.5h6V4"/>'),
  rect: s('<rect x="2.5" y="2.5" width="11" height="11" rx="0.5"/>'),
  ellipse: s('<circle cx="8" cy="8" r="5.5"/>'),
  line: s('<path d="M3 13L13 3"/>'),
  arrow: s('<path d="M3 13L13 3M7 3h6v6"/>'),
  polygon: s('<path d="M8 2.5l5.5 10h-11z"/>'),
  star: s('<path d="M8 2l1.8 3.8 4.2.5-3.1 2.9.8 4.1L8 11.3l-3.7 2 .8-4.1L2 6.3l4.2-.5z"/>'),
  image: s('<rect x="2" y="3" width="12" height="10" rx="1"/><circle cx="6" cy="6.5" r="1.2"/><path d="M2.5 12l3.5-3.5 2.5 2.5 2-2 3 3"/>'),
  video: s('<rect x="2" y="3.5" width="9" height="9" rx="1"/><path d="M11 7l3-2v6l-3-2"/>'),
  pen: s('<path d="M8 2l3.5 6L8 14 4.5 8z"/><circle cx="8" cy="8.5" r="1"/>'),
  pencil: s('<path d="M3 13l1-3.5L11 2.5 13.5 5 6.5 12z"/><path d="M9.5 4l2.5 2.5"/>'),
  text: s('<path d="M3 3.5h10M8 3.5V13M6 13h4"/>'),
  table: s('<rect x="2" y="2.5" width="12" height="11" rx="1"/><path d="M2 6.5h12M2 10h12M6.5 2.5v11"/>'),
  pin: s('<path d="M8 14.5s-4.5-4.2-4.5-7.5a4.5 4.5 0 019 0c0 3.3-4.5 7.5-4.5 7.5z"/><circle cx="8" cy="7" r="1.6"/>'),
  sparkle: s('<path d="M8 2l1.3 3.7L13 7l-3.7 1.3L8 12l-1.3-3.7L3 7l3.7-1.3zM12.5 11l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/>'),
  dropper: s('<path d="M9.5 3.5l3 3M11 2l3 3-1.5 1.5-3-3zM9.5 5L3.5 11 3 13l2-.5 6-6"/>'),
  chevron: s('<path d="M4.5 6.5L8 10l3.5-3.5"/>'),
  close: s('<path d="M4 4l8 8M12 4l-8 8"/>'),
  plus: s('<path d="M8 3v10M3 8h10"/>'),
  eye: s('<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>'),
  eyeOff: s('<path d="M2 2l12 12M6.5 4C7 3.7 7.5 3.5 8 3.5c4 0 6.5 4.5 6.5 4.5a12 12 0 01-1.7 2.2M10.4 11.8c-.7.4-1.5.7-2.4.7-4 0-6.5-4.5-6.5-4.5a12 12 0 012.4-2.9"/>'),
  lock: s('<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/>'),
  unlock: s('<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 014.8-1"/>'),
  play: s('<path d="M5 3.5l7 4.5-7 4.5z"/>'),
  download: s('<path d="M8 2.5v8M4.5 7L8 10.5 11.5 7M3 13.5h10"/>'),
  menu: s('<path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11"/>'),
  group: s('<rect x="2" y="2" width="12" height="12" rx="1" stroke-dasharray="2 1.5"/><rect x="5" y="5" width="6" height="6"/>'),
  boolean: s('<rect x="2.5" y="2.5" width="7" height="7"/><circle cx="10" cy="10" r="3.5"/>'),
  vector: s('<path d="M3 12c2-7 8-1 10-8"/><rect x="1.8" y="10.8" width="2.4" height="2.4"/><rect x="11.8" y="2.8" width="2.4" height="2.4"/>'),
  page: s('<rect x="3" y="2" width="10" height="12" rx="1"/>'),
  autolayout: s('<rect x="2.5" y="3" width="11" height="10" rx="1"/><path d="M5.5 6v4M8 6v4M10.5 6v4"/>'),
  more: s('<circle cx="4" cy="8" r=".8"/><circle cx="8" cy="8" r=".8"/><circle cx="12" cy="8" r=".8"/>'),
  chat: s('<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>'),
  copy: s('<rect x="5" y="5" width="8.5" height="8.5" rx="1"/><path d="M3 10.5V3a.5.5 0 01.5-.5H11"/>'),
  trash: s('<path d="M3 4.5h10M6 4.5V3h4v1.5M4.5 4.5l.7 9h5.6l.7-9"/>'),
  caret: s('<path d="M6 4l4 4-4 4"/>', ' class="caret"'),
};

// Korean preset names (schema.presets keys).
export const PRESET_LABEL = {
  SLIDE_16_9: "슬라이드 16:9", SLIDE_4_3: "슬라이드 4:3", A3: "A3", A4: "A4", A5: "A5", A6: "A6",
  LETTER: "레터", LEGAL: "리갈", TABLOID: "타블로이드", CUSTOM: "사용자 지정",
};
export const TYPE_LABEL = {
  page: "페이지", frame: "프레임", section: "섹션", group: "그룹", boolean: "불리언", rect: "사각형", ellipse: "타원", line: "선",
  polygon: "다각형", star: "별", vector: "벡터", text: "텍스트", video: "비디오", table: "표",
};
export const TYPE_ICON = { page: "page", frame: "frame", section: "section", group: "group", boolean: "boolean", rect: "rect", ellipse: "ellipse",
  line: "line", polygon: "polygon", star: "star", vector: "vector", text: "text", video: "video", table: "table" };

// Key label formatting for the shortcuts UI: "Mod+Shift+G" -> "⌘⇧G" (mac) / "Ctrl+Shift+G".
export function keyLabel(spec) {
  if (!spec) return "";
  const parts = spec.split("+");
  const k = parts.pop();
  const map = IS_MAC ? { Mod: "⌘", Ctrl: "⌃", Alt: "⌥", Shift: "⇧", Meta: "⌘" } : { Mod: "Ctrl+", Ctrl: "Ctrl+", Alt: "Alt+", Shift: "Shift+", Meta: "Win+" };
  const order = IS_MAC ? ["Ctrl", "Alt", "Shift", "Mod", "Meta"] : ["Mod", "Ctrl", "Alt", "Shift", "Meta"];
  const mods = order.filter((m) => parts.includes(m)).map((m) => map[m]).join("");
  const keyMap = { ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→", Enter: IS_MAC ? "⏎" : "Enter", Escape: "Esc", Backspace: IS_MAC ? "⌫" : "Backspace",
    Delete: IS_MAC ? "⌦" : "Del", Space: "Space", Tab: "Tab", Equal: "=", Minus: "-", BracketLeft: "[", BracketRight: "]", Backslash: "\\", Quote: "'",
    Slash: "/", Comma: "<", Period: ">", PageUp: "PgUp", PageDown: "PgDn" };
  return mods + (keyMap[k] || k.replace(/^Key|^Digit/, ""));
}
