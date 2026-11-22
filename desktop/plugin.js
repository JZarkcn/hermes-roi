// ROI — Return on Intelligence · native page (T03 + T04b-wire + design pass v3).
//
// Self-contained ESM: no JSX, no build step. Imports only `react` and
// `@hermes/plugin-sdk`, both provided by the Hermes Desktop runtime
// (verified against the installed hermes-activity bundle's import
// specifiers and the desktop-plugin-sdk docs: the only importable
// specifiers are `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`).
// The shipped artifact IS this file.
//
// Product rules baked in (owner decisions, 2026-11-02):
//  1. ROI is machine-GLOBAL: scope=all by default. The page never follows
//     the active profile tab — switching tabs must not change the numbers.
//  2. "Local" is user-declared: a tick-list of model names (current and
//     historical) is passed as local_models=; the loopback URL check stays
//     only a candidate hint. Models deployed over a LAN IP / proxy / docker
//     are local if the user ticks them, even when Hermes sees a remote URL.
//
// Backend: dashboard/plugin_api.py, mounted at /api/plugins/hermes-roi/.
// The plugin id MUST equal dashboard/manifest.json's "name" — that is what
// scopes ctx.rest() to this backend (verified against the installed
// home-dashboard pair: id "home-dashboard" == manifest name).
//
// Layout v3 (2026-11-05, owner: "iterate on our original design mockup"):
//  - Verdict banner: tier icon + "[ LV4 · PAYBACK IS A DISTANT DREAM ]"
//    English-first (catalog rule, maintainer review 2026-11-22); Chinese copy
//    stays as a secondary subtitle. Roast + countdown below.
//  - Two panels: HARDWARE RECOVERY (3dp) | PROJECTED BREAK-EVEN + live countdown.
//  - Stat strip: Hardware Cost / Cloud-Equivalent / Pace (30d) / Net ROI.
//  - Row: CUMULATIVE SAVINGS SVG chart (solid actuals + dashed projection +
//    dashed cost line) | SETTINGS list (label → control rows).
//  - Tier ladder LV1–LV4 (zh + en), active highlighted.
//  - Machine-wide usage (T03) below the fold, de-emphasized.
// All money is an explicit cloud-equivalent ESTIMATE against the user's
// own hardware cost — hypothetical, never money earned (D-018~D-022).

import { createElement as h, useState, useEffect } from "react";
import {
  useQuery,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  Skeleton,
} from "@hermes/plugin-sdk";

// Theme: the app's real --ui-* tokens (names verified against the desktop
// build's stylesheet), with graceful fallbacks if a token is unavailable.
const TEXT = "var(--ui-text-primary, inherit)";
const SOFT = "var(--ui-text-secondary, inherit)";
const MUTED = "var(--ui-text-tertiary, inherit)";
const ACCENT = "var(--ui-accent, inherit)";
const BORDER = "var(--ui-stroke-secondary, inherit)";
const HAIRLINE = "var(--ui-stroke-tertiary, inherit)";
const PANEL = "var(--ui-bg-chrome, transparent)";
const CARD_BG = "var(--ui-widget-surface-background, transparent)";
const GREEN = "var(--ui-green, #4ade80)";
const CYAN = "var(--ui-cyan, #22d3ee)";
const YELLOW = "var(--ui-yellow, #facc15)";
const PURPLE = "var(--ui-purple, #a78bfa)";
const RED = "var(--ui-red, #f87171)";
// Tier theme colours (owner 2026-11-05 "propose a theme colour per level"):
// a warm→cool emotional sweep — you won (gold) → near (green) → grinding
// (amber fire) → it's a dream (purple). LV1/LV3 have no native --ui token,
// so they pin a hex.
const GOLD = "#fcd34d";  // LV1 — paid off, absolute legend (gold trophy)
const AMBER = "#fb923c"; // LV3 — still a long way, keep grinding (the grind's fire)
const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

const TIER_COLOR = { LV1: GOLD, LV2: GREEN, LV3: AMBER, LV4: PURPLE, unknown: MUTED };
// RGB components per tier, for the bold gradient wash + glow (daring colour,
// owner 2026-11-05). Match the TIER_COLOR hexes above.
const TIER_RGB = { LV1: "252,211,77", LV2: "74,222,128", LV3: "251,146,60", LV4: "167,139,250", unknown: "148,163,184" };
const tierRGB = (t) => TIER_RGB[t] || TIER_RGB.unknown;

// Captured at register time; used by the page's data queries.
let rest = null;
let storage = null;

const S = {
  root: { display: "flex", flexDirection: "column", gap: 12, padding: 16 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" },
  title: { fontFamily: MONO, fontSize: 14, letterSpacing: "0.06em", color: TEXT },
  titleMark: { fontFamily: MONO, fontSize: 14, color: MUTED, marginRight: 6 },
  tagline: { fontFamily: MONO, fontSize: 11, color: SOFT },
  scope: { fontFamily: MONO, fontSize: 10, color: MUTED, letterSpacing: "0.08em", display: "flex", alignItems: "baseline", gap: 12, justifyContent: "space-between", flexWrap: "wrap" },
  refreshBtn: { fontFamily: MONO, fontSize: 10, letterSpacing: "0.08em", color: SOFT, background: "transparent", border: `1px solid ${BORDER}`, borderRadius: 6, padding: "4px 10px", cursor: "pointer" },
  overline: { fontFamily: MONO, fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color: MUTED },

  // ── verdict hero (big, bold, daring colour — owner 2026-11-05) ─────────
  banner: { display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", border: `1px solid ${BORDER}`, borderRadius: 10, background: PANEL, padding: "20px 24px" },
  bannerIcon: { display: "flex", alignItems: "center", gap: 6, flexShrink: 0 },
  zz: { fontFamily: MONO, fontSize: 11, color: MUTED, letterSpacing: "0.1em" },
  bannerChip: { alignSelf: "flex-start", fontFamily: MONO, fontSize: 13, letterSpacing: "0.06em", padding: "3px 12px", border: "1px solid currentColor", borderRadius: 999, whiteSpace: "nowrap" },
  bannerEn: { fontSize: 30, fontWeight: 800, lineHeight: 1.12, letterSpacing: "0.005em", color: TEXT },
  bannerZh: { fontSize: 14, fontWeight: 600, color: MUTED }, // Chinese subtitle under the EN headline
  bannerRoast: { fontFamily: MONO, fontSize: 16, fontWeight: 700, fontStyle: "italic", lineHeight: 1.35 },
  bannerClock: { fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: "0.02em", lineHeight: 1.2 },
  bannerMain: { flex: "1 1 320px", minWidth: 240, display: "flex", flexDirection: "column", gap: 7 },

  // ── two panels + stat strip ─────────────────────────────────────────
  panels: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10 },
  panel: { border: `1px solid ${BORDER}`, borderRadius: 8, background: CARD_BG, padding: "12px 16px", display: "flex", flexDirection: "column", gap: 6 },
  bigNum: { fontFamily: MONO, fontSize: 42, lineHeight: 1.05, letterSpacing: "-0.02em" },
  panelSub: { fontFamily: MONO, fontSize: 12, color: SOFT },
  beDate: { fontFamily: MONO, fontSize: 22, fontWeight: 600 },
  countdown: { fontFamily: MONO, fontSize: 12, color: SOFT, letterSpacing: "0.04em" },
  statStrip: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 },
  stat: { border: `1px solid ${BORDER}`, borderRadius: 6, background: CARD_BG, padding: "10px 12px" },
  statLabel: { fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: MUTED, marginBottom: 4 },
  statValue: { fontFamily: MONO, fontSize: 16 },

  // ── chart + settings row (shrunk — subordinate to the hero) ──────────
  chartSettings: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 10, alignItems: "stretch" },
  card: { border: `1px solid ${BORDER}`, borderRadius: 6, background: CARD_BG, padding: 10, display: "flex", flexDirection: "column", gap: 8 },
  setRow: { display: "grid", gridTemplateColumns: "120px 1fr", gap: 10, alignItems: "center", padding: "4px 0", borderBottom: `1px solid ${HAIRLINE}` },
  setLabel: { fontFamily: MONO, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: MUTED },
  input: { fontFamily: MONO, fontSize: 11, padding: "4px 7px", border: `1px solid ${BORDER}`, borderRadius: 4, background: "transparent", color: TEXT, width: "100%", boxSizing: "border-box" },
  // value + unit as one compact box (electricity row: $ rate and kWh/mo)
  affix: { display: "flex", alignItems: "center", border: `1px solid ${BORDER}`, borderRadius: 4, background: "transparent", overflow: "hidden" },
  affixInput: { fontFamily: MONO, fontSize: 11, padding: "4px 4px 4px 7px", border: "none", background: "transparent", color: TEXT, width: 62, textAlign: "right" },
  affixUnit: { fontFamily: MONO, fontSize: 9, color: MUTED, letterSpacing: "0.05em", whiteSpace: "nowrap", paddingRight: 6 },
  hint: { fontFamily: MONO, fontSize: 10, color: MUTED, lineHeight: 1.4 },
  warn: { fontFamily: MONO, fontSize: 10, color: YELLOW, lineHeight: 1.4 },

  // ── tier ladder ─────────────────────────────────────────────────────
  ladder: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 },
  tier: { display: "flex", gap: 8, alignItems: "center", border: `1px solid ${HAIRLINE}`, borderRadius: 6, padding: "8px 10px", background: CARD_BG },
  // English-first ladder rows (maintainer review 2026-11-22): tierZh = headline
  // slot (now carrying the EN line), tierSub = secondary Chinese subtitle.
  tierZh: { fontSize: 12, fontWeight: 600, lineHeight: 1.3 },
  tierSub: { fontSize: 9, color: MUTED, lineHeight: 1.4 },

  // ── T03 usage section (unchanged contract) ─────────────────────────
  label: { fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: MUTED, marginBottom: 4 },
  value: { fontFamily: MONO, fontSize: 15 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 },
  dayRow: { display: "grid", gridTemplateColumns: "84px 60px 1fr", gap: 8, fontFamily: MONO, fontSize: 12, padding: "2px 0" },
  note: { fontFamily: MONO, fontSize: 11, color: MUTED },
  footer: { fontFamily: MONO, fontSize: 10, letterSpacing: "0.08em", color: MUTED, lineHeight: 1.6 },
};

function fmt(n) {
  return (n ?? 0).toLocaleString("en-US");
}

// Money display: the backend carries 6dp strings (precision is the contract);
// the UI shows 2dp like the mockup. Display formatting only — no recompute.
function usd(s) {
  const v = parseFloat(s);
  if (!Number.isFinite(v)) return String(s);
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function Field({ label, value }) {
  return h("div", null, h("div", { style: S.label }, label), h("div", { style: S.value }, value));
}

function tickedModels() {
  // P2 writes the tick-list here (settings page); read defensively.
  try {
    const raw = storage ? storage.get("local_models", "[]") : "[]";
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

// --- user hardware settings (persisted, explicit — D-018~D-022) ──────────
const ECON_KEYS = {
  hw: "roi_hw_cost",
  start: "roi_start_at",
  bench: "roi_benchmark",
  ep: "roi_energy_price",
  ek: "roi_energy_kwh",
};

function st(key, dflt) {
  try { return storage ? storage.get(key, dflt) : dflt; } catch { return dflt; }
}

function setSt(key, v) {
  try { if (storage) storage.set(key, v); } catch { /* non-fatal */ }
}

function econQuery(cfg) {
  const hw = (cfg.hw || "").trim();
  const start = (cfg.start || "").trim();
  if (!hw || !start) return null;
  const p = new URLSearchParams({
    scope: "all",
    hardware_cost: hw,
    start_at: start,
    local_models: tickedModels().join(","),
  });
  const bench = (cfg.bench || "").trim();
  if (bench) p.set("benchmark", bench);
  const ep = (cfg.ep || "").trim();
  const ek = (cfg.ek || "").trim();
  if (ep && ek) {
    p.set("energy_price", ep);
    p.set("energy_kwh", ek);
  }
  return p.toString();
}

// Returns `value` after it has been unchanged for `delay` ms. Used so the
// economics query (and its recompute) only fires once the user stops typing,
// not on every keystroke (owner 2026-11-05: "等输完/删完再刷新").
function useDebouncedValue(value, delay) {
  const [d, setD] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setD(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return d;
}

// ── tier icons (inline SVG, stroke = currentColor) ────────────────────────
function Icon({ kind, size = 22, color }) {
  const paths = {
    LV1: "M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4zM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4",
    LV2: "M12 2c3 2 4 6 4 9l-4 4-4-4c0-3 1-7 4-9zM12 15v4M8.5 12l-3 3 3 1M15.5 12l3 3-3 1",
    LV3: "M2 10h2v4H2zM20 10h2v4h-2zM6 11h2v2H6zM16 11h2v2h-2zM8 12h8",
    LV4: "M12 3a7 7 0 0 0-7 7c0 3 2 5 4 6v3h6v-3c2-1 4-3 4-6a7 7 0 0 0-7-7zM9 10.5a1.4 1.4 0 1 0 2.8 0 1.4 1.4 0 1 0-2.8 0zM12.2 10.5a1.4 1.4 0 1 0 2.8 0 1.4 1.4 0 1 0-2.8 0zM10.5 19v-1.5M12 19v-1.5M13.5 19v-1.5",
    unknown: "M6 3h12M6 21h12M7 3c0 6 5 6 5 9s-5 3-5 9M17 3c0 6-5 6-5 9s5 3 5 9",
  };
  return h("svg", {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: color || "currentColor", strokeWidth: 1.5,
    strokeLinecap: "round", strokeLinejoin: "round",
  }, h("path", { d: paths[kind] || paths.unknown }));
}

// ── pixel-art tier flourishes (owner 2026-11-22: "换成像素风的" + "用1") ──
// Painted on a 16×16 grid at module load, rendered as crisp SVG rects —
// no bitmaps, no external assets, same renderer for the big (banner) and
// small (ladder) sizes. Glyphs: LV1 stacked gold ingots, LV2 slightly-open
// chest leaking gold, LV3 donkey at the mill (拉磨的驴), LV4 tombstone.
// 2026-11-22: wheel→donkey and web→tombstone were owner symbol-swaps —
// radial/circular motifs collapse at 16px; solid silhouettes don't.
const FX_PAL = {
  LV1: { 1: "#22190a", 2: "#fcd34d", 3: "#fef08a", 4: "#fffbe6", 5: "#8a5a10" },
  LV2: { 1: "#0d2b16", 2: "#4ade80", 3: "#bef264", 4: "#f2fefe", 5: "#1d6b35" },
  LV3: { 1: "#241304", 2: "#fb923c", 3: "#ffd8a8", 4: "#fff5e8", 5: "#7c3c10" },
  LV4: { 1: "#241340", 2: "#a78bfa", 3: "#d8c7fd", 4: "#f6efff", 5: "#7a5ec7" },
};
// Fixed colours used across tiers: wood / wood-dark / gold / flame.
const FX_FIX = { 6: "#8a5a10", 7: "#4a2a08", 8: "#fcd34d", 9: "#fb923c" };
const FX_GLYPH = { LV1: "bars", LV2: "chest", LV3: "donkey", LV4: "tomb" };
const W16 = 16;
const fxMk = () => new Uint8Array(256);
const fxPx = (g, x, y, v) => { if (x >= 0 && x < W16 && y >= 0 && y < W16) g[y * W16 + x] = v; };
const fxGv = (g, x, y) => (x < 0 || x >= W16 || y < 0 || y >= W16 ? 0 : g[y * W16 + x]);
const fxCirc = (g, cx, cy, r, v) => { for (let y = 0; y < W16; y++) for (let x = 0; x < W16; x++) { const dx = x - cx, dy = y - cy; if (dx * dx + dy * dy <= r * r) fxPx(g, x, y, v); } };
const fxLine = (g, x1, y1, x2, y2, v) => { const n = Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1)) || 1; for (let i = 0; i <= n; i++) fxPx(g, Math.round(x1 + (x2 - x1) * i / n), Math.round(y1 + (y2 - y1) * i / n), v); };
const fxBox = (g, x, y, w, h_, v) => { for (let j = 0; j < h_; j++) for (let i = 0; i < w; i++) fxPx(g, x + i, y + j, v); };
function fxOutline(g, v) { const b = []; for (let y = 0; y < W16; y++) for (let x = 0; x < W16; x++) if (fxGv(g, x, y) === v) { for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const n = fxGv(g, x + dx, y + dy); if (n === 0) { b.push([x, y]); break; } } } b.forEach(([x, y]) => fxPx(g, x, y, 1)); }
function fxHi(g, v) { const a = []; for (let y = 0; y < W16; y++) for (let x = 0; x < W16; x++) if (fxGv(g, x, y) === v) { const t = fxGv(g, x, y - 1), l = fxGv(g, x - 1, y); const tb = t === 0 || t === 1, lb = l === 0 || l === 1; if (tb && lb) a.push([x, y, 4]); else if (tb || lb) a.push([x, y, 3]); } a.forEach(([x, y, c]) => fxPx(g, x, y, c)); }
const FX_PAINTERS = {
  bars() {
    // Owner 2026-11-22: "如果金币不好渲染,可以试试堆叠在一起的金条" + "金条
    // 肯定要用梯形的吧" + "梯形再明显一点,周围光点换成辐射光线" — wider
    // 5×3 ingots (bright 3-wide top face, shoulders stepping out to a 5-wide
    // base = unmistakable trapezoid); the sparkle dots became radiating rays.
    // 2026-11-22 QA round 2: the white centred glints read as wrong grey
    // squares and a flat 1-row top read as a plain rectangle — now each ingot
    // is 5×4 with a TRAPEZOID top face (far edge 1px over a 3px near edge),
    // slanted side bevels and a wide dark base row; rays use bright gold (3).
    const g = fxMk();
    const bar = (x, y) => {                                                                   // 5×4
      fxPx(g, x + 2, y, 4);                                                                   // top face far edge (white glint)
      fxPx(g, x + 1, y + 1, 3); fxPx(g, x + 2, y + 1, 3); fxPx(g, x + 3, y + 1, 3);           // top face near edge
      fxPx(g, x, y + 2, 5); fxPx(g, x + 4, y + 2, 5);                                         // slanted side bevels
      fxPx(g, x + 1, y + 2, 2); fxPx(g, x + 2, y + 2, 2); fxPx(g, x + 3, y + 2, 2);           // gold front
      fxPx(g, x, y + 3, 5); fxPx(g, x + 1, y + 3, 5); fxPx(g, x + 2, y + 3, 5); fxPx(g, x + 3, y + 3, 5); fxPx(g, x + 4, y + 3, 5); // wide dark base
    };
    [[0, 11], [5, 11], [10, 11]].forEach(([x, y]) => bar(x, y));            // bottom row of three
    [[2, 7], [7, 7]].forEach(([x, y]) => bar(x, y));                        // middle row over the seams
    bar(4, 3);                                                               // crown bar
    const rays = [[[2, 2], [0, 0]], [[12, 2], [14, 0]], [[5, 0], [5, 2]], [[10, 0], [10, 2]], [[0, 8], [1, 8]], [[14, 8], [15, 8]]]; // radiating light
    rays.forEach(([a, b]) => fxLine(g, a[0], a[1], b[0], b[1], 4));
    return g;
  },
  chest() {
    const g = fxMk();
    fxBox(g, 3, 1, 10, 3, 6); fxOutline(g, 6);           // lid
    fxBox(g, 2, 4, 12, 1, 8); fxPx(g, 2, 4, 1); fxPx(g, 13, 4, 1); // gold rim at the crack
    fxBox(g, 2, 5, 12, 2, 8);                             // light leaking through the gap
    [[4, 5, 3], [6, 5, 4], [9, 5, 3], [11, 5, 4], [3, 6, 3], [8, 6, 4], [12, 6, 3]].forEach(([x, y, v]) => fxPx(g, x, y, v)); // glow sparkles
    // Owner 2026-11-22: "箱子打开的一条缝两边画辐射光线" — rays bursting out
    // left and right of the crack.
    fxLine(g, 1, 4, 0, 2, 4); fxLine(g, 1, 6, 0, 8, 4);
    fxLine(g, 14, 4, 15, 2, 4); fxLine(g, 14, 6, 15, 8, 4);
    fxLine(g, 0, 5, 0, 6, 4); fxLine(g, 15, 5, 15, 6, 4);
    fxBox(g, 2, 7, 12, 7, 6); fxOutline(g, 6);            // body
    fxBox(g, 7, 7, 2, 7, 2); fxOutline(g, 2);             // tier-colour ribbon
    fxBox(g, 6, 12, 4, 3, 8); fxOutline(g, 8);            // gold lock
    fxPx(g, 8, 13, 7); fxPx(g, 8, 14, 7);                 // keyhole
    return g;
  },
  // Banner donkey-at-the-mill — 2026-11-22 rework #6: owner swapped the
  // hamster wheel for 拉磨的驴 ("这么小的像素也画不出来，有什么其他替代方案"
  // → 拉磨的驴): "keep at it" is literal donkey work. Side view: long-eared
  // donkey with muzzle to the central axle beam, the beam plugged into a
  // flat two-tier millstone, flour spilling off its right edge. No circles
  // anywhere, so nothing collapses into wheel-soup.
  donkey() {
    const g = fxMk();
    fxLine(g, 0, 13, 15, 13, 5);                                   // ground
    fxBox(g, 7, 10, 7, 1, 5); fxBox(g, 8, 11, 5, 1, 7); fxBox(g, 8, 12, 7, 1, 5); // lower stone
    fxBox(g, 7, 7, 5, 3, 2); fxPx(g, 7, 7, 3); fxPx(g, 8, 7, 3); fxPx(g, 9, 7, 3); // upper stone, lit rim
    fxLine(g, 9, 3, 9, 7, 6); fxPx(g, 9, 3, 4);                     // axle beam + cap
    fxBox(g, 6, 4, 3, 2, 2); fxPx(g, 7, 4, 4); fxPx(g, 8, 5, 4);   // head + eye + muzzle at the beam
    fxLine(g, 6, 2, 6, 3, 2); fxLine(g, 7, 2, 7, 3, 2);            // long ears
    fxLine(g, 6, 6, 5, 7, 2); fxPx(g, 5, 6, 2);                    // neck
    fxBox(g, 1, 7, 5, 3, 2);                                        // body
    fxLine(g, 1, 10, 1, 12, 5); fxLine(g, 2, 10, 2, 12, 5);         // hind legs
    fxLine(g, 4, 10, 4, 12, 5); fxLine(g, 5, 10, 5, 12, 5);         // front legs
    fxLine(g, 0, 6, 0, 8, 3);                                       // tail flick
    fxPx(g, 14, 12, 4); fxPx(g, 15, 12, 4); fxPx(g, 15, 11, 4);     // flour spill
    return g;
  },
  // Banner tombstone — 2026-11-22 rework #5: owner dropped the orb web for a
  // new symbol ("蜘蛛网画不好的话，推荐一下其他象征" → chose 墓碑). It IS the
  // LV4 roast gag — "at this rate your next GPU will retire first": dome
  // headstone with a glowing engraved cross, one ground line, nothing else.
  tomb() {
    const g = fxMk();
    const tops = [6, 5, 4, 3, 3, 3, 3, 4, 5, 6];                  // dome silhouette, x = 3..12
    for (let i = 0; i < 10; i++) {
      const x = 3 + i;
      for (let y = tops[i]; y <= 12; y++) fxPx(g, x, y, 2);       // stone body
      fxPx(g, x, tops[i], 3);                                      // dome lip highlight
      if (i === 0) for (let y = 6; y <= 12; y++) fxPx(g, x, y, 3); // left edge lit
      if (i === 9) for (let y = 6; y <= 12; y++) fxPx(g, x, y, 5); // right edge shaded
    }
    fxLine(g, 8, 5, 8, 10, 4); fxLine(g, 5, 7, 10, 7, 4);         // glowing cross
    fxLine(g, 0, 13, 15, 13, 5);                                   // ground line
    return g;
  },
};
const FX_CACHE = {};
function fxGrid(tier, small) {
  const base = FX_GLYPH[tier];
  if (!base) return null;
  // webMini was deleted together with the ladder icons (owner 2026-11-22:
  // at 16px nothing ever read — the orb web even as a "lilac eye").
  const ck = `${tier}:${base}`;
  if (!FX_CACHE[ck]) FX_CACHE[ck] = FX_PAINTERS[base]();
  return FX_CACHE[ck];
}
function PixelFlourish({ tier, size = 16, style }) {
  const g = fxGrid(tier, size < 40);
  if (!g) return null;
  const pal = FX_PAL[tier];
  const rects = [];
  for (let y = 0; y < W16; y++) for (let x = 0; x < W16; x++) {
    const v = g[y * W16 + x];
    if (!v) continue;
    const c = pal[v] || FX_FIX[v];
    if (c) rects.push(h("rect", { key: `${x}-${y}`, x, y, width: 1, height: 1, fill: c }));
  }
  return h("svg", {
    width: size, height: size, viewBox: "0 0 16 16", shapeRendering: "crispEdges",
    style: { display: "block", ...style },
  }, ...rects);
}

// ── verdict hero (icon + [ LVn · zh ] + EN + roast + big countdown) ─────
function VerdictBanner({ d }) {
  const v = d.verdict;
  const be = d.break_even;
  const color = TIER_COLOR[v.tier] || MUTED;
  const rgb = tierRGB(v.tier);
  let clock = null;
  if (be && be.state === "ok") {
    clock = h(Countdown, { isoDate: be.date, big: true, color });
  } else if (be && be.state === "already_paid_off") {
    clock = h("span", { style: { ...S.bannerClock, color: GREEN } }, "REACHED — 回本了 · the dream came true 🎉");
  }
  return h("div", {
    style: {
      ...S.banner,
      borderLeft: `5px solid ${color}`,
      background: `linear-gradient(120deg, rgba(${rgb},0.22), rgba(${rgb},0.06) 55%, transparent)`,
      boxShadow: `0 0 52px -12px rgba(${rgb},0.6)`,
      position: "relative", overflow: "hidden",
    },
  },
    h("div", { style: { ...S.bannerIcon, color } },
      h(Icon, { kind: v.tier, size: 44 }),
      v.tier === "LV4" && h("span", { style: S.zz }, "z z z")),
    h("div", { style: { ...S.bannerMain, position: "relative", zIndex: 1 } },
      h("div", { style: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" } },
        h("span", { style: { ...S.bannerChip, color, fontWeight: 700 } },
          `[ ${v.tier === "unknown" ? "ONBOARDING" : v.tier} · ${v.label || "…"} ]`),
        // Option B (owner 2026-11-06): <30 days of history → provisional pace,
        // flagged in amber so the number isn't mistaken for the standard
        // 30-day basis (it flips to the real window on day 30).
        v.provisional && h("span", {
          style: {
            fontSize: 11, fontWeight: 700, letterSpacing: 0.3, color: AMBER,
            background: `rgba(${TIER_RGB.LV3},0.16)`,
            border: `1px solid rgba(${TIER_RGB.LV3},0.5)`,
            borderRadius: 20, padding: "2px 10px", whiteSpace: "normal",
          },
        }, `Provisional estimate · based on ${be && be.pace_days ? be.pace_days : "—"} days (switches to the 30-day basis on day 30)`)),
      h("div", { style: S.bannerEn }, v.label),
      v.label_zh && h("div", { style: S.bannerZh }, v.label_zh),
      v.roast && h("div", { style: { ...S.bannerRoast, color } }, v.roast),
      clock),
    // Pixel flourish (owner 2026-11-22): big bottom-right decoration in the
    // verdict box, under the text layer, clipped by the rounded corners.
    v.tier !== "unknown" && h("div", {
      key: "flourish",
      style: { position: "absolute", right: 14, bottom: -6, zIndex: 0, pointerEvents: "none", opacity: 0.55 },
    }, h(PixelFlourish, { tier: v.tier, size: 104 })),
  );
}

// ── live countdown to the break-even date (mockup: 17 Y 09 M 01 D …) ─────
function Countdown({ isoDate, big, color }) {
  const target = Date.parse(`${isoDate}T00:00:00Z`);
  const [left, setLeft] = useState(() => (Number.isFinite(target) ? target - Date.now() : 0));
  useEffect(() => {
    if (!Number.isFinite(target)) return undefined;
    setLeft(target - Date.now());
    const id = setInterval(() => setLeft(target - Date.now()), 1000);
    return () => clearInterval(id);
  }, [target]);
  const base = big ? S.bannerClock : S.countdown;
  if (!Number.isFinite(target) || left <= 0) {
    return h("span", { style: { ...base, color: GREEN } }, "REACHED — the dream came true");
  }
  const total = Math.floor(left / 1000);
  const ss = total % 60, mm = Math.floor(total / 60) % 60, hh = Math.floor(total / 3600) % 24;
  const days = Math.floor(total / 86400);
  const Y = Math.floor(days / 365), M = Math.floor((days % 365) / 30), D = days % 30;
  const p2 = (x) => String(x).padStart(2, "0");
  return h("span", { style: big ? { ...base, color: color || TEXT } : S.countdown },
    `${p2(Y)} Y ${p2(M)} MO ${p2(D)} D ${p2(hh)} H ${p2(mm)} M ${p2(ss)} S`);
}

// ── two panels: recovery + break-even (mockup) ───────────────────────────
function Panels({ d }) {
  const v = d.verdict;
  const b = d.break_even;
  const color = TIER_COLOR[v.tier] || MUTED;
  let beContent;
  if (b.state === "ok") {
    // The ticking countdown now lives in the verdict hero (big + bold);
    // this panel keeps the static date + distance.
    beContent = h("div", { style: { display: "flex", flexDirection: "column", gap: 4 } },
      h("div", { style: S.beDate }, b.date),
      h("div", { style: S.panelSub }, `${b.days_remaining} days out`));
  } else if (b.state === "already_paid_off") {
    beContent = h("div", { style: { ...S.beDate, color: GREEN } }, "REACHED");
  } else if (b.state === "no_positive_pace") {
    beContent = h("div", { style: S.note }, "no positive pace in the trailing 30 days — the clock is off");
  } else {
    beContent = h("div", { style: S.note }, "no usage recorded yet — feed it tokens, the clock wakes with data");
  }
  return h("div", { style: S.panels },
    h("div", { style: { ...S.panel, borderLeft: `3px solid ${color}` } },
      h("div", { style: S.overline }, "Hardware Recovery"),
      h("div", { style: { ...S.bigNum, color: v.tier === "unknown" ? SOFT : color } }, `${v.recovery_pct}%`),
      h("div", { style: S.panelSub }, `${usd(d.net_usd)} / ${usd(d.hardware_cost_usd)}`)),
    h("div", { style: S.panel },
      h("div", { style: S.overline }, "Projected Break-Even"),
      beContent),
  );
}

// ── stat strip (mockup: cost / cloud-equiv / pace / net ROI) ─────────────
function StatStrip({ d }) {
  const roi = d.verdict.net_roi_pct;
  const roiColor = roi.startsWith("-") ? RED : GREEN;
  const pace = d.break_even.pace_per_day_usd;
  return h("div", { style: S.statStrip },
    h("div", { style: S.stat },
      h("div", { style: S.statLabel }, "Hardware Cost"),
      h("div", { style: S.statValue }, usd(d.hardware_cost_usd))),
    h("div", { style: S.stat },
      h("div", { style: S.statLabel }, "Cloud-Equivalent"),
      h("div", { style: S.statValue }, usd(d.gross_usd))),
    h("div", { style: S.stat },
      h("div", { style: S.statLabel },
        d.verdict.provisional ? `Pace (${d.break_even.pace_days}d · provisional)` : "Pace (30d)"),
      h("div", { style: S.statValue }, pace ? `$${parseFloat(pace).toFixed(3)}/day` : "—")),
    h("div", { style: S.stat },
      h("div", { style: S.statLabel }, "Net ROI"),
      h("div", { style: { ...S.statValue, color: roiColor } }, `${roi}%`)),
  );
}

// ── cumulative savings chart (SVG, no library) ───────────────────────────
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthLabel(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function Chart({ curve }) {
  const W = 660, H = 150, PL = 60, PR = 16, PT = 14, PB = 26;
  const pts = curve.points || [];
  if (pts.length < 2) {
    return h("div", { style: { ...S.note, padding: "24px 0", textAlign: "center" } },
      "no data since the start date — the chart is waiting for tokens");
  }
  const t0 = Date.parse(`${pts[0].d}T00:00:00Z`);
  const t1 = Date.parse(`${pts[pts.length - 1].d}T00:00:00Z`);
  const cost = parseFloat(curve.cost) || 0;
  let vMax = cost, vMin = 0;
  for (const p of pts) {
    const v = parseFloat(p.v);
    if (v > vMax) vMax = v;
    if (v < vMin) vMin = v;
  }
  vMax = vMax * 1.08 || 1;
  vMin = Math.min(0, vMin * 1.15);
  const X = (t) => PL + (W - PL - PR) * ((t - t0) / (t1 - t0 || 1));
  const Y = (v) => PT + (H - PT - PB) * (1 - (v - vMin) / (vMax - vMin || 1));
  const nAct = curve.projected ? pts.length - 1 : pts.length;
  const act = pts.slice(0, nAct).map((p) => [X(Date.parse(`${p.d}T00:00:00Z`)), Y(parseFloat(p.v))]);
  const line = act.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const base = Y(0) > H - PB ? H - PB : Y(0);
  const area = `${line} L${act[act.length - 1][0].toFixed(1)} ${base.toFixed(1)} L${act[0][0].toFixed(1)} ${base.toFixed(1)} Z`;
  const lastAct = act[act.length - 1];
  const projSeg = curve.projected
    ? h("line", { x1: lastAct[0], y1: lastAct[1], x2: X(t1), y2: Y(cost), stroke: ACCENT, strokeWidth: 1.2, strokeDasharray: "3 5", opacity: 0.4 })
    : null;
  const endP = [X(t1), Y(parseFloat(pts[pts.length - 1].v))];
  const yTicks = [0, cost / 2, cost];
  const xTicks = [
    { t: t0, label: monthLabel(pts[0].d), anchor: "start" },
    { t: lastAct[0] > X(t0) + 40 ? lastAct[0] : null, label: "now", anchor: "middle" },
    { t: t1, label: curve.projected ? monthLabel(pts[pts.length - 1].d) : null, anchor: "end" },
  ].filter((x) => x.t !== null);
  return h("svg", { viewBox: `0 0 ${W} ${H}`, style: { width: "100%", height: "auto", display: "block" } },
    yTicks.map((v, i) => h("g", { key: `y${i}` },
      h("line", { x1: PL, x2: W - PR, y1: Y(v), y2: Y(v), stroke: HAIRLINE, strokeWidth: 0.5 }),
      h("text", { x: PL - 6, y: Y(v) + 3, textAnchor: "end", fill: MUTED, fontSize: 9, fontFamily: MONO },
        `$${v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : v.toFixed(v < 10 && v > 0 ? 1 : 0)}`))),
    xTicks.map((x, i) => h("text", { key: `x${i}`, x: x.t, y: H - 8, textAnchor: x.anchor, fill: MUTED, fontSize: 10, fontFamily: MONO }, x.label)),
    h("line", { x1: PL, x2: W - PR, y1: Y(0), y2: Y(0), stroke: MUTED, strokeWidth: 0.75 }),
    h("line", { x1: X(t0), x2: X(t0), y1: Y(cost), y2: H - PB, stroke: MUTED, strokeWidth: 0.5, strokeDasharray: "2 3", opacity: 0.6 }),
    // dashed hardware-cost line (mockup: purple dashed)
    h("line", { x1: PL, x2: W - PR, y1: Y(cost), y2: Y(cost), stroke: PURPLE, strokeWidth: 1.8, strokeDasharray: "6 4" }),
    h("text", { x: W - PR, y: Y(cost) - 6, textAnchor: "end", fill: PURPLE, fontSize: 10, fontFamily: MONO }, `cost $${cost.toLocaleString("en-US")}`),
    h("path", { d: area, fill: ACCENT, opacity: 0.14 }),
    h("path", { d: line, fill: "none", stroke: ACCENT, strokeWidth: 2, strokeLinejoin: "round" }),
    projSeg,
    h("circle", { cx: endP[0], cy: endP[1], r: 3.2, fill: ACCENT }),
  );
}

// ── settings list (mockup: label → control rows) ─────────────────────────
function Settings({ cfg, save, models, defaultModel, applied, primary }) {
  const ep = (cfg.ep || "").trim();
  const ek = (cfg.ek || "").trim();
  const energyHalf = (ep && !ek) || (ek && !ep);
  return h("div", { style: S.card },
    h("div", { style: S.overline },
      primary
        ? "Your hardware — set cost + start date to run the math"
        : "Your hardware — inputs (persisted locally)"),
    h("div", null,
      h("div", { style: S.setRow },
        h("div", { style: S.setLabel }, "Hardware cost"),
        h("input", { style: S.input, value: cfg.hw, onChange: save("hw"), inputMode: "decimal", placeholder: "USD, e.g. 3000" })),
      h("div", { style: S.setRow },
        h("div", { style: S.setLabel }, "Start date"),
        h("input", { style: S.input, type: "date", value: cfg.start, onChange: save("start") })),
      h("div", { style: S.setRow },
        h("div", { style: S.setLabel }, "Benchmark model"),
        h("select", { style: S.input, value: cfg.bench, onChange: save("bench") },
          h("option", { value: "" }, `default — ${defaultModel || "deepseek-flash"}`),
          (models || []).map((m) => h("option", { key: m, value: m }, m)))),
      h("div", { style: { ...S.setRow, borderBottom: "none" } },
        h("div", { style: S.setLabel }, "Electricity (opt.)"),
        h("div", { style: { display: "flex", gap: 8 } },
          h("div", { style: S.affix },
            h("input", { style: S.affixInput, value: cfg.ep, onChange: save("ep"), inputMode: "decimal", placeholder: "0.266" }),
            h("span", { style: S.affixUnit }, "$/kWh")),
          h("div", { style: S.affix },
            h("input", { style: S.affixInput, value: cfg.ek, onChange: save("ek"), inputMode: "decimal", placeholder: "10" }),
            h("span", { style: S.affixUnit }, "kWh/mo"))))
    ),
    energyHalf && h("div", { style: S.warn },
      "electricity needs BOTH a $/kWh rate and a monthly kWh estimate — or leave both empty (gross = net)."),
    !energyHalf && applied && h("div", { style: S.hint },
      applied.kwh_per_month != null
        ? `applied electricity: −${usd(applied.total_applied_usd)} so far · ${usd(applied.monthly_usd)}/mo (${applied.price} ${applied.ccy}/kWh × ${applied.kwh_per_month} kWh/mo) · ~$${parseFloat(applied.per_day_usd)}/day ongoing, netted from pace`
        : `applied electricity: −${usd(applied.usd)} (flat offset — restart the gateway to see the monthly breakdown)`),
  );
}

// ── tier ladder (mockup: LV1 green → LV4 purple) ──────────────────────────
const LADDER = [
  ["LV1", "回本了·太强了！", "PAID OFF. ABSOLUTE LEGEND."],
  ["LV2", "马上回本！", "ALMOST THERE."],
  ["LV3", "还差得远·再接再厉！", "STILL A LONG WAY. KEEP GRINDING."],
  ["LV4", "回本遥遥无期！", "PAYBACK IS A DISTANT DREAM."],
];

function TierLadder({ tier }) {
  return h("div", { style: S.ladder },
    LADDER.map(([id, zh, en]) => {
      const active = tier === id;
      const color = TIER_COLOR[id];
      return h("div", {
        key: id,
        style: { ...S.tier, opacity: active ? 1 : 0.4, border: active ? `1px solid ${color}` : S.tier.border, boxShadow: active ? `0 0 22px -10px ${color}` : "none" },
      },
        // Owner 2026-11-22: "下面那一排小图标根本看不清，都删除" — the 16px
        // pixel flourishes were illegible; ladder rows are labels only now.
        // The line-icon robot-head stays for the unknown/onboarding row.
        id === "unknown" ? h("span", { style: { color } }, h(Icon, { kind: id, size: 18 })) : null,
        h("div", { style: { display: "flex", flexDirection: "column", gap: 1, minWidth: 0 } },
          h("div", { style: { ...S.tierZh, color: active ? color : TEXT } }, en),
          h("div", { style: S.tierSub }, zh)));
    }));
}

// ── T03 usage section (rendering preserved) ────────────────────────────────
function UsageSection({ s }) {
  const t = s.totals || {};
  const empty = (t.sessions || 0) === 0;
  return h("div", { style: { display: "flex", flexDirection: "column", gap: 12 } },
    h("div", { style: S.card },
      empty
        ? h("div", { style: S.note }, "No usage in range. The GPU remains a decorative object.")
        : h("div", { style: S.grid },
            h(Field, { label: "Sessions", value: `${fmt(t.sessions)} (+${fmt(t.subagent_sessions)} sub)` }),
            h(Field, { label: "Input", value: fmt(t.input_tokens) }),
            h(Field, { label: "Output", value: fmt(t.output_tokens) }),
            h(Field, { label: "Cache read", value: fmt(t.cache_read_tokens) }),
            h(Field, { label: "Cache write", value: fmt(t.cache_write_tokens) }),
            h(Field, { label: "Reasoning", value: fmt(t.reasoning_tokens) }),
            h(Field, { label: "Local sessions", value: fmt(s.local_candidate_sessions) }),
            h(Field, { label: "Unknown-route sessions", value: fmt(s.unknown_route_sessions) }),
          ),
    ),
    (s.days || []).length > 0 && h("div", { style: S.card },
      h("div", { style: S.label }, "Daily (last 7 shown)"),
      s.days.slice(-7).reverse().map((d) =>
        h("div", { key: d.day, style: S.dayRow },
          h("span", null, d.day),
          h("span", { style: { color: SOFT } }, `${d.sessions}+${d.subagent_sessions}`),
          h("span", { style: { color: MUTED } },
            `${fmt(d.input_tokens + d.output_tokens + d.cache_read_tokens + d.cache_write_tokens + d.reasoning_tokens)} tok · local ${fmt(d.local_tokens)}`),
        )),
    ),
    (s.audit_notes || []).length > 0 && h("div", { style: S.note }, s.audit_notes.map((n, i) => h("div", { key: i }, `· ${n}`))),
  );
}

// ── page ───────────────────────────────────────────────────────────────────
function RoiPage() {
  // Machine-global on purpose: no profile tab, no per-profile re-keying.
  const [cfg, setCfg] = useState({
    hw: st(ECON_KEYS.hw, ""),
    start: st(ECON_KEYS.start, ""),
    bench: st(ECON_KEYS.bench, ""),
    ep: st(ECON_KEYS.ep, ""),
    ek: st(ECON_KEYS.ek, ""),
  });
  const save = (key) => (e) => {
    const v = e.target.value;
    setCfg((c) => ({ ...c, [key]: v }));
    setSt(ECON_KEYS[key], v);
  };
  const q = useQuery({
    queryKey: ["roi", "summary", "all", tickedModels().join("|")],
    queryFn: () =>
      rest(`/summary?scope=all&local_models=${encodeURIComponent(tickedModels().join(","))}`),
    staleTime: 60_000,
    retry: 1,
  });
  const cfgD = useDebouncedValue(cfg, 500); // debounced copy → drives the query
  const ep = econQuery(cfgD); // economics recompute waits out the typing pause
  const qe = useQuery({
    queryKey: ["roi", "economics", ep || "off", tickedModels().join("|")],
    queryFn: () => (ep ? rest(`/economics?${ep}`) : Promise.resolve(null)),
    staleTime: 60_000,
    retry: 1,
  });
  // Card's model list for the benchmark dropdown (never free-typed).
  const qh = useQuery({
    queryKey: ["roi", "health"],
    queryFn: () => rest("/health"),
    staleTime: 10 * 60_000,
    retry: 1,
  });
  const benchModels = qh.data && qh.data.benchmark_models;
  const benchDefault = qh.data && qh.data.benchmark_default;
  // Manual refresh: re-runs both queries against the backend (which recomputes
  // on the spot — no cron, no self-update; rule-3 clean). Same on any machine:
  // ctx.rest() is the public plugin API.
  const roiFetching = q.isFetching || qe.isFetching;
  const roiRefresh = () => {
    q.refetch();
    if (ep) qe.refetch();
  };

  if (!rest) {
    return h("div", { style: { ...S.root, ...S.note } }, "backend not mounted yet (enable the plugin, restart the gateway)");
  }
  if (q.isLoading) {
    return h("div", { style: S.root }, h(Skeleton, { className: "h-24 w-full" }));
  }
  if (q.error) {
    const d = q.error && (q.error.detail || q.error.message) ? q.error.detail || q.error.message : "the store is not answering";
    return h("div", { style: S.root },
      h("div", { style: S.header }, h("div", { style: S.title }, "ROI / Return on Intelligence")),
      h("div", { style: S.card }, h("div", { style: S.note }, `No data: ${String(d)}`)),
    );
  }
  const s = q.data;
  const appliedEnergy = qe.data && qe.data.energy && qe.data.energy.applied ? qe.data.energy : null;

  let econArea = null;
  if (ep) {
    if (qe.isLoading) {
      econArea = h("div", { style: S.card }, h(Skeleton, { className: "h-20 w-full" }));
    } else if (qe.error) {
      econArea = h("div", { style: S.card },
        h("div", { style: S.overline }, "Recovery — could not compute"),
        h("div", { style: S.note }, `economics: ${String((qe.error && (qe.error.detail || qe.error.message)) || "failed")}`),
        h("div", { style: S.hint }, "check the inputs below — half-set energy fields and non-numeric costs are rejected."));
    } else {
      const d = qe.data;
      econArea = h("div", { style: { display: "flex", flexDirection: "column", gap: 12 } },
        h(VerdictBanner, { d }),
        // Tier ladder sits right under the verdict punchline so it is in the
        // first screen (no scroll) — the "where I am on the spectrum" answer
        // to the LVx headline. (owner 2026-11-05: "让这一条出现在头一屏")
        h(TierLadder, { tier: d.verdict.tier }),
        h(Panels, { d }),
        h(StatStrip, { d }),
        h("div", { style: S.chartSettings },
          h("div", { style: S.card },
            h("div", { style: S.overline }, "Cumulative Savings — net since start, projected to break-even"),
            h(Chart, { curve: d.curve || { points: [] } })),
          h(Settings, { cfg, save, models: benchModels, defaultModel: benchDefault, applied: appliedEnergy, primary: false })));
    }
  }

  return h("div", { style: S.root },
    h("div", { style: S.header },
      h("div", { style: { display: "flex", alignItems: "baseline", gap: 4, minWidth: 0, flexWrap: "wrap" } },
        h("span", { style: S.titleMark }, ">"),
        h("div", { style: S.title }, "ROI / Return on Intelligence"),
        h("div", { style: { ...S.tagline, marginLeft: 10 } }, "A brutally honest ROI for your local AI rig.")),
      h("div", { style: S.scope },
        h("span", null,
          `SCOPE: ALL PROFILES (${(s.profiles || []).length})` +
          (s.profiles && s.profiles.length ? ` — ${s.profiles.join(", ")}` : "")),
        h("button", {
          style: { ...S.refreshBtn, opacity: roiFetching ? 0.55 : 1, cursor: roiFetching ? "default" : "pointer" },
          onClick: roiRefresh,
          disabled: roiFetching,
          title: "Re-read the store and recompute everything (backend runs on the spot)",
        }, roiFetching ? "REFRESHING…" : "⟳ REFRESH"))),
    ep ? econArea : h("div", { style: { display: "flex", flexDirection: "column", gap: 8 } },
      h(Settings, { cfg, save, models: benchModels, defaultModel: benchDefault, applied: appliedEnergy, primary: true }),
      h("div", { style: S.hint }, "set the hardware cost + start date — the recovery math, countdown and chart run on save.")),
    h("div", { style: S.overline }, "Machine-wide usage — all profiles"),
    h(UsageSection, { s }),
    h("div", { style: S.footer },
      h("div", null, "> ROI Plugin for Hermes Desktop"),
      h("div", null, "Track token savings. Roast your purchase. Count down to (maybe) payback."),
      ep
        ? "Cloud-equivalent estimate — hypothetical, never money earned · read-only"
        : "No hardware configured — usage above is not money yet · read-only"),
  );
}

export default {
  id: "hermes-roi",
  name: "ROI",
  defaultEnabled: true,
  register(ctx) {
    rest = (path) => ctx.rest(path);
    storage = ctx.storage;
    ctx.register({
      id: "roi-page",
      area: ROUTES_AREA,
      title: "ROI",
      data: { path: "/roi" },
      render: () => h(RoiPage, {}),
    });
    ctx.register({
      id: "roi-nav",
      area: SIDEBAR_NAV_AREA,
      data: { path: "/roi", label: "ROI", codicon: "pulse" },
    });
  },
};
