// Schema access shared by every browser module (format.md §6). schema.json is the single source of truth.

export let SCHEMA = null;

export async function loadSchema(url = "/schema.json") {
  if (SCHEMA) return SCHEMA;
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`schema.json ${res.status}`);
  SCHEMA = await res.json();
  defaultsCache.clear();
  return SCHEMA;
}

const defaultsCache = new Map();
function baseDefaults(type) {
  let d = defaultsCache.get(type);
  if (!d) {
    d = {};
    for (const [k, spec] of Object.entries(SCHEMA.common)) d[k] = spec.default;
    for (const [k, spec] of Object.entries(SCHEMA.props[type] || {})) d[k] = spec.default;
    Object.assign(d, SCHEMA.typeDefaults[type] || {});
    defaultsCache.set(type, d);
  }
  return d;
}

// A fresh deep copy: callers may mutate it.
export const defaultsFor = (type) => structuredClone(baseDefaults(type));

// Resolved props (defaults filled in). Read-only: nested defaults are shared. Cached per props object.
const resolved = new WeakMap();
export function propsOf(node) {
  if (!node) return null;
  const p = node.props || {};
  let r = resolved.get(p);
  if (!r) { r = { ...baseDefaults(node.type), ...p }; resolved.set(p, r); }
  return r;
}

export const isContainer = (type) => SCHEMA.containers.includes(type);

// Keys allowed for a type (common + type props), for filtering pasted properties.
export function propKeys(type) {
  return new Set([...Object.keys(SCHEMA.common), ...Object.keys(SCHEMA.props[type] || {})]);
}

const PREFIX = { page: "p", frame: "f", section: "s", group: "g", boolean: "b", rect: "r", ellipse: "e", line: "l",
  polygon: "pg", star: "st", vector: "v", text: "t", video: "vd", table: "tb" };
const ID_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
export function newId(type) {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let s = "";
  for (const b of bytes) s += ID_CHARS[b % 62];
  return `${PREFIX[type] || "n"}_${s}`;
}

// Fractional index keys compared as plain ASCII strings. DIGITS is in ASCII order.
const DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
function midpoint(a, b) {
  // a: "" means 0; b: null means 1. Requires a < b.
  if (b !== null) {
    let n = 0;
    while (n < b.length && (a[n] || "0") === b[n]) n++;
    if (n > 0) return b.slice(0, n) + midpoint(a.slice(n), b.slice(n) || null);
  }
  const da = a ? DIGITS.indexOf(a[0]) : 0;
  const db = b !== null ? DIGITS.indexOf(b[0]) : DIGITS.length;
  if (db - da > 1) return DIGITS[Math.round((da + db) / 2)];
  if (b !== null && b.length > 1) return b.slice(0, 1);
  return DIGITS[da] + midpoint(a.slice(1), null);
}

// A key strictly between a and b (either may be null/empty = open end).
export function zBetween(a, b) {
  a = a || "";
  b = b || null;
  if (b !== null && a >= b) [a, b] = [b, a];
  if (b !== null && a === b) return a + "V";
  let k = midpoint(a, b);
  // Keys that differ only by trailing zeros compare unequal but have no room between: extend past a.
  if (!(k > a) || (b !== null && !(k < b))) k = a + "V";
  return k;
}

// n increasing keys between a and b.
export function zSeq(a, b, n) {
  const out = [];
  let lo = a || "";
  for (let i = 0; i < n; i++) { lo = zBetween(lo, b); out.push(lo); }
  return out;
}

if (typeof location !== "undefined" && new URLSearchParams(location.search).has("selftest")) {
  const k = [];
  let a = "", b = null;
  for (let i = 0; i < 50; i++) { const m = zBetween(a, b); console.assert(m > a && (b === null || m < b), "zBetween", a, b, m); k.push(m); a = m; }
  console.assert(zBetween("a0", "a1") > "a0" && zBetween("a0", "a1") < "a1", "zBetween a0 a1");
  console.assert(zBetween("a", null) > "a", "zBetween open");
}
