/* ══════════════════════════════════════════════════════════════
   JARVIS Command Center — front end
   ══════════════════════════════════════════════════════════════ */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

/* Phone/LAN pairing: the QR link carries ?key=… — keep it and send it on
   every API call so network mode's lock accepts us. */
(() => {
  const fromUrl = new URLSearchParams(location.search).get("key");
  if (fromUrl) {
    localStorage.setItem("jarvis.key", fromUrl);
    history.replaceState({}, "", location.pathname);  // don't leave it in history
  }
  const rawFetch = window.fetch.bind(window);
  window.fetch = (url, opts = {}) => {
    const key = localStorage.getItem("jarvis.key");
    if (key && typeof url === "string" && url.startsWith("/api")) {
      opts = { ...opts, headers: { ...(opts.headers || {}), "X-Jarvis-Key": key } };
    }
    return rawFetch(url, opts);
  };
})();

const api = async (path, opts) => (await fetch(path, opts)).json();
const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });

const IS_DESKTOP = !!window.pywebview;
let STATUS = {}, LISTENING = false, RECOGNIZER = null, SPEAK_BACK = true, FOCUS_ON = false;

/* ─────────────────────────── icon set ─────────────────────────── */
const ICON = {
  grid:'<path d="M3 3h8v8H3V3Zm10 0h8v8h-8V3ZM3 13h8v8H3v-8Zm10 0h8v8h-8v-8Z"/>',
  core:'<path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 4a6 6 0 1 1-6 6 6 6 0 0 1 6-6Zm0 3.5A2.5 2.5 0 1 0 14.5 12 2.5 2.5 0 0 0 12 9.5Z"/>',
  agents:'<path d="M12 2 3 7v10l9 5 9-5V7Zm0 2.3 6.5 3.6L12 11.5 5.5 7.9Zm-7 5.3 6 3.3v6.2l-6-3.3Zm8 9.5v-6.2l6-3.3v6.2Z"/>',
  task:'<path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4Z"/>',
  calendar:'<path d="M7 2v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2Zm12 8v10H5V10Z"/>',
  memory:'<path d="M12 2a5 5 0 0 0-5 5v1a4 4 0 0 0 0 8v1a5 5 0 0 0 10 0v-1a4 4 0 0 0 0-8V7a5 5 0 0 0-5-5Zm0 2a3 3 0 0 1 3 3v10a3 3 0 0 1-6 0V7a3 3 0 0 1 3-3Z"/>',
  chat:'<path d="M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2Z"/>',
  book:'<path d="M6 2h13v20H6a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3Zm0 2a1 1 0 0 0-1 1v11.2A3 3 0 0 1 6 16h11V4Z"/>',
  tools:'<path d="m21 4-3 3-2-2 3-3a5 5 0 0 0-6 6L4 15a2.8 2.8 0 0 0 4 4l7-9a5 5 0 0 0 6-6Z"/>',
  flow:'<path d="M4 4h6v4H4Zm10 0h6v4h-6ZM4 16h6v4H4Zm10 0h6v4h-6ZM7 8v8m10-8v8M7 12h10"/>',
  system:'<path d="M4 4h16v12H4Zm2 2v8h12V6ZM2 18h20v2H2Z"/>',
  voice:'<path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V22h2v-3.08A7 7 0 0 0 19 12Z"/>',
  research:'<path d="M10 18a8 8 0 1 1 5.3-2L21 21.7 19.7 23l-5.7-5.7A8 8 0 0 1 10 18Zm0-2a6 6 0 1 0 0-12 6 6 0 0 0 0 12Z"/>',
  llm:'<path d="M12 3 3 8v8l9 5 9-5V8Zm0 4.2 4.5 2.5L12 12.2 7.5 9.7Z"/>',
  alert:'<path d="M12 2 1 21h22Zm0 6 7 12H5Zm-1 4v4h2v-4Zm0 5v2h2v-2Z"/>',
  cpu:'<path d="M9 2v2H7a3 3 0 0 0-3 3v2H2v2h2v2H2v2h2v2a3 3 0 0 0 3 3h2v2h2v-2h2v2h2v-2h2a3 3 0 0 0 3-3v-2h2v-2h-2v-2h2V9h-2V7a3 3 0 0 0-3-3h-2V2h-2v2h-2V2Zm-1 6h8v8H8Z"/>',
  tip:'<path d="M12 2a7 7 0 0 0-4 12.7V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.3A7 7 0 0 0 12 2ZM9.5 21h5v1h-5Z"/>',
  disk:'<path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 6a4 4 0 1 1-4 4 4 4 0 0 1 4-4Zm0 2.5A1.5 1.5 0 1 0 13.5 12 1.5 1.5 0 0 0 12 10.5Z"/>',
  play:'<path d="M8 5v14l11-7Z"/>',
  plus:'<path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6Z"/>',
  clock:'<path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 5h-2v6l5 3 1-1.7-4-2.3Z"/>',
  camera:'<path d="M9 3 7.2 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3.2L15 3Zm3 5a6 6 0 1 1-6 6 6 6 0 0 1 6-6Z"/>',
  power:'<path d="M11 2v10h2V2Zm-3.6 3A9 9 0 1 0 21 12a9 9 0 0 0-3.4-7l-1.4 1.5A7 7 0 1 1 8.8 6.5Z"/>',
  check:'<path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4Z"/>',
  palette:'<path d="M12 2a10 10 0 0 0 0 20c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.2a2 2 0 0 1 2-2h2.5A4.5 4.5 0 0 0 22 11c-.5-5-4.7-9-10-9Zm-5.5 9A1.5 1.5 0 1 1 8 9.5 1.5 1.5 0 0 1 6.5 11Zm3-4A1.5 1.5 0 1 1 11 5.5 1.5 1.5 0 0 1 9.5 7Zm5 0A1.5 1.5 0 1 1 16 5.5 1.5 1.5 0 0 1 14.5 7Zm3 4a1.5 1.5 0 1 1 1.5-1.5 1.5 1.5 0 0 1-1.5 1.5Z"/>',
};
const svg = (k) => `<svg viewBox="0 0 24 24">${ICON[k] || ICON.core}</svg>`;

/* ───────────────────── interface studio (theming) ───────────────────── */
const THEME_FIELDS = [
  ["Accents", [
    { k: "accent",     label: "Accent (primary)", type: "color" },
    { k: "accentDeep", label: "Accent (deep)",    type: "color" },
    { k: "accentDim",  label: "Accent (dim)",     type: "color" },
  ]],
  ["Background", [
    { k: "bg0",        label: "Base background", type: "color" },
    { k: "glowTop",    label: "Glow — top",      type: "color" },
    { k: "glowBottom", label: "Glow — bottom",   type: "color" },
    { k: "panelTint",  label: "Panel tint",      type: "color" },
  ]],
  ["Text", [
    { k: "text",  label: "Text",       type: "color" },
    { k: "muted", label: "Muted text", type: "color" },
    { k: "dim",   label: "Faint text", type: "color" },
  ]],
  ["Status colours", [
    { k: "ok",     label: "Success",            type: "color" },
    { k: "warn",   label: "Warning",            type: "color" },
    { k: "hot",    label: "Danger / recording", type: "color" },
    { k: "violet", label: "Violet accent",      type: "color" },
    { k: "amber",  label: "Amber accent",       type: "color" },
  ]],
  ["Finish", [
    { k: "panelOpacity", label: "Panel opacity",    type: "range", min: 0.2, max: 1,  step: 0.01, fmt: (v) => Math.round(v * 100) + "%" },
    { k: "glow",         label: "Glow intensity",   type: "range", min: 0,   max: 2,  step: 0.05, fmt: (v) => "×" + (+v).toFixed(2) },
    { k: "radius",       label: "Corner roundness", type: "range", min: 0,   max: 20, step: 1,    fmt: (v) => v + "px" },
    { k: "fontSize",     label: "Text size",        type: "range", min: 12,  max: 17, step: 0.5,  fmt: (v) => v + "px" },
  ]],
  ["Layout", [
    { k: "sidebar",   label: "Sidebar width",     type: "range", min: 200, max: 330, step: 2, fmt: (v) => v + "px" },
    { k: "topbar",    label: "Top bar height",    type: "range", min: 50,  max: 86,  step: 1, fmt: (v) => v + "px" },
    { k: "statusbar", label: "Bottom bar height", type: "range", min: 46,  max: 80,  step: 1, fmt: (v) => v + "px" },
  ]],
  ["Effects", [
    { k: "scanlines",   label: "Scanline overlay",  type: "toggle" },
    { k: "scanOpacity", label: "Scanline strength", type: "range", min: 0, max: 0.9, step: 0.05, fmt: (v) => Math.round(v * 100) + "%" },
    { k: "vignette",    label: "Vignette",          type: "toggle" },
    { k: "motion",      label: "Animations",        type: "toggle" },
  ]],
];

const THEME_DEFAULTS = {
  accent: "#3ce0ff", accentDeep: "#12a8cf", accentDim: "#1c6b85",
  bg0: "#020610", glowTop: "#072a44", glowBottom: "#06202f", panelTint: "#070a18",
  text: "#d3ecf8", muted: "#5f8ba6", dim: "#3d6479",
  ok: "#38f5a8", warn: "#ffb545", hot: "#ff5f7e", violet: "#a06bff", amber: "#ffcf5c",
  panelOpacity: 0.72, glow: 1, radius: 12, fontSize: 14,
  sidebar: 262, topbar: 64, statusbar: 60,
  scanlines: true, scanOpacity: 0.5, vignette: true, motion: true,
};

const THEME_PRESETS = [
  ["Jarvis Classic", {}],
  ["Iron Legion", { accent: "#ff5340", accentDeep: "#c22a1c", accentDim: "#7c2a1e", bg0: "#0a0304", glowTop: "#3d0f0a", glowBottom: "#260a06", panelTint: "#180a08", text: "#ffe9e0", muted: "#a6756b", dim: "#6e463c", hot: "#ff8a3d" }],
  ["Matrix Ops", { accent: "#41ff8f", accentDeep: "#14b85c", accentDim: "#1d7a4a", bg0: "#010a05", glowTop: "#06341c", glowBottom: "#042313", panelTint: "#05170d", text: "#d9ffe9", muted: "#5f8f74", dim: "#3a6649", hot: "#ff5f7e" }],
  ["Ultraviolet", { accent: "#b07aff", accentDeep: "#7c4fd0", accentDim: "#5a3a8f", bg0: "#08031a", glowTop: "#241040", glowBottom: "#150a2b", panelTint: "#0e0722", text: "#eee6ff", muted: "#8b7bb3", dim: "#584a7a" }],
  ["Solar Dusk", { accent: "#ffb545", accentDeep: "#cf7a12", accentDim: "#8f5d1c", bg0: "#0d0703", glowTop: "#3a2408", glowBottom: "#241605", panelTint: "#171008", text: "#ffefd9", muted: "#a68a63", dim: "#6e5a3c" }],
];

const THEME_KEY = "jarvis.theme.v1";
const THEME = { values: { ...THEME_DEFAULTS }, rgb: {} };

function hexRgb(h) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(h || "").trim());
  if (!m) return [255, 255, 255];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const lighten = (rgb, t) => rgb.map((c) => Math.round(c + (255 - c) * t));
const mixRgbStr = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t)).join(",");
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const trgba = (rgb, a) => `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${clamp01(a)})`;

function applyTheme(save = true) {
  const v = THEME.values, s = document.documentElement.style;
  const acc = hexRgb(v.accent), deep = hexRgb(v.accentDeep), dimc = hexRgb(v.accentDim);
  const pan = hexRgb(v.panelTint);
  THEME.rgb = {
    acc, deep, dim: dimc,
    ok: hexRgb(v.ok), warn: hexRgb(v.warn), hot: hexRgb(v.hot),
    violet: hexRgb(v.violet), amber: hexRgb(v.amber),
    lite: lighten(acc, 0.55), liteHot: lighten(hexRgb(v.hot), 0.35),
  };
  s.setProperty("--cy", v.accent);            s.setProperty("--cy-rgb", acc.join(","));
  s.setProperty("--cy-2", v.accentDeep);      s.setProperty("--cy-dim", v.accentDim);
  s.setProperty("--bg-0", v.bg0);             s.setProperty("--glow-1", v.glowTop);
  s.setProperty("--glow-2", v.glowBottom);
  s.setProperty("--panel", trgba(pan, v.panelOpacity));
  s.setProperty("--panel-2", `rgba(${mixRgbStr(pan, acc, 0.28)},${clamp01(v.panelOpacity * 0.78)})`);
  s.setProperty("--txt", v.text);             s.setProperty("--muted", v.muted);
  s.setProperty("--dim", v.dim);
  s.setProperty("--ok", v.ok);                s.setProperty("--warn", v.warn);
  s.setProperty("--hot", v.hot);              s.setProperty("--violet", v.violet);
  s.setProperty("--amber", v.amber);
  s.setProperty("--line", trgba(acc, 0.16));  s.setProperty("--line-2", trgba(acc, 0.3));
  s.setProperty("--glow", +v.glow);
  s.setProperty("--rc", v.radius + "px");     s.setProperty("--rm", Math.max(0, +v.radius - 3) + "px");
  s.setProperty("--sb", v.sidebar + "px");    s.setProperty("--top", v.topbar + "px");
  s.setProperty("--bot", v.statusbar + "px"); s.setProperty("--fs", v.fontSize + "px");
  document.body.classList.toggle("no-scan", !v.scanlines);
  document.body.classList.toggle("no-vig", !v.vignette);
  document.body.classList.toggle("calm", !v.motion);
  const scan = document.querySelector(".scanlines");
  if (scan) scan.style.opacity = v.scanlines ? v.scanOpacity : 0;
  if (save) localStorage.setItem(THEME_KEY, JSON.stringify(v));
}

function initTheme() {
  try {
    const saved = JSON.parse(localStorage.getItem(THEME_KEY) || "{}");
    Object.assign(THEME.values, THEME_DEFAULTS, saved);
  } catch { /* corrupt theme blob → defaults */ }
  applyTheme(false);
}

function buildStudio() {
  const root = $("#studio");
  if (!root) return;
  const v = THEME.values;
  const flat = THEME_FIELDS.flatMap(([, fs]) => fs);
  const ctl = (f) => {
    if (f.type === "color")
      return `<label class="st-ctl"><span>${f.label}</span><code data-lab="${f.k}">${v[f.k]}</code><input type="color" data-tk="${f.k}" value="${v[f.k]}"></label>`;
    if (f.type === "range")
      return `<label class="st-ctl"><span>${f.label}</span><b data-lab="${f.k}">${f.fmt(+v[f.k])}</b><input type="range" data-tk="${f.k}" min="${f.min}" max="${f.max}" step="${f.step}" value="${v[f.k]}"></label>`;
    return `<label class="st-ctl"><span>${f.label}</span><button type="button" class="st-toggle ${v[f.k] ? "on" : ""}" data-tk="${f.k}" title="${f.label}"></button></label>`;
  };
  root.innerHTML =
    `<div class="st-presets">${THEME_PRESETS.map(([n], i) => {
      const pv = { ...THEME_DEFAULTS, ...THEME_PRESETS[i][1] };
      return `<button type="button" class="st-preset" data-preset="${i}"><i style="background:linear-gradient(135deg,${pv.accent} 0 55%,${pv.bg0} 55% 100%)"></i>${n}</button>`;
    }).join("")}</div>` +
    THEME_FIELDS.map(([g, fields]) =>
      `<div class="st-group"><h3>${g}</h3><div class="st-rows">${fields.map(ctl).join("")}</div></div>`).join("") +
    `<p class="st-note">Every change applies instantly and is stored on this machine (<code>localStorage</code>),
     so your theme survives restarts. <b>Copy theme</b> exports it as JSON — paste it on another PC to move it.</p>`;

  root.querySelectorAll("[data-preset]").forEach((b) => (b.onclick = () => {
    const i = +b.dataset.preset;
    THEME.values = { ...THEME_DEFAULTS, ...THEME_PRESETS[i][1] };
    applyTheme(); buildStudio();
    toast(`Theme applied: ${THEME_PRESETS[i][0]}`);
  }));
  root.querySelectorAll('input[type="color"][data-tk]').forEach((el) => (el.oninput = () => {
    THEME.values[el.dataset.tk] = el.value;
    const lab = root.querySelector(`[data-lab="${el.dataset.tk}"]`);
    if (lab) lab.textContent = el.value;
    applyTheme();
  }));
  root.querySelectorAll('input[type="range"][data-tk]').forEach((el) => (el.oninput = () => {
    const f = flat.find((x) => x.k === el.dataset.tk);
    THEME.values[el.dataset.tk] = parseFloat(el.value);
    const lab = root.querySelector(`[data-lab="${el.dataset.tk}"]`);
    if (lab && f) lab.textContent = f.fmt(parseFloat(el.value));
    applyTheme();
  }));
  root.querySelectorAll(".st-toggle[data-tk]").forEach((el) => (el.onclick = () => {
    THEME.values[el.dataset.tk] = !THEME.values[el.dataset.tk];
    el.classList.toggle("on", !!THEME.values[el.dataset.tk]);
    applyTheme();
  }));
}

/* ─────────────────────────── settings ─────────────────────────── */
async function loadSettings() {
  const d = await api("/api/settings");
  const root = $("#settings-groups");
  if (!root || !d.sections) return;
  const flat = {};
  const chunks = [];

  // App-side setting that only lives in the browser: read replies aloud.
  const speakOn = localStorage.getItem("jarvis.speak") !== "off";
  const listenOn = localStorage.getItem("jarvis.listen") === "on";
  let bootState = null, netState = null;
  try { bootState = await api("/api/autostart"); } catch {}
  try { netState = await api("/api/network"); } catch {}
  const netQr = netState?.enabled && netState.url
    ? `<div class="st-net">${netState.qr ? `<img src="${netState.qr}" alt="QR" class="st-qr">` : ""}
       <div class="st-net-meta"><code>${esc(netState.url)}</code>
         <button type="button" class="st-copy" id="net-copy">copy link</button>
         <span>Same Wi-Fi only. Locked with a pairing key${netState.qr ? "" : " (install the qrcode package for the QR)"}. Takes full effect next launch.</span></div></div>`
    : "";
  chunks.push(`<div class="st-group"><h3>App</h3><div class="st-rows">
    <label class="st-ctl"><span>Read Jarvis's replies aloud (browser voice)</span>
      <button type="button" class="st-toggle ${speakOn ? "on" : ""}" id="set-speak"></button></label>
    <label class="st-ctl"><span>Always listen for the wake word</span>
      <button type="button" class="st-toggle ${listenOn ? "on" : ""}" id="set-listen"></button></label>${bootState && bootState.supported ? `
    <label class="st-ctl"><span>Start with Windows (tucks into the tray)</span>
      <button type="button" class="st-toggle ${bootState.enabled ? "on" : ""}" id="set-boot"></button></label>` : ""}
    <label class="st-ctl"><span>Control from my phone (local network)</span>
      <button type="button" class="st-toggle ${netState?.enabled ? "on" : ""}" id="set-net"></button></label>
    ${netQr}
  </div><p class="st-note" style="margin-top:8px">Closing the window hides Jarvis to the <b>system tray</b> (quit from its icon). <b>Ctrl+J</b> summons Jarvis from anywhere. Theme, colours, glow and layout live in the <b>Interface Studio</b> (top right button).</p></div>`);

  // One-click brain presets: fill the Brain section's cloud fields for them.
  const presets = [
    ["⚡ Groq as the CASCADE-brain (free)", "Ollama stays king; Groq answers when it sulks",
     { JARVIS_PROVIDER: "auto", OPENAI_BASE_URL: "https://api.groq.com/openai/v1", OPENAI_MODEL: "llama-3.3-70b-versatile" }],
    ["⚡ Groq as the PRIMARY brain", "70B cloud mind answers everything (shielded)",
     { JARVIS_PROVIDER: "openai", OPENAI_BASE_URL: "https://api.groq.com/openai/v1", OPENAI_MODEL: "llama-3.3-70b-versatile" }],
    ["🧠 OpenAI — paid, top tier", "key at platform.openai.com",
     { JARVIS_PROVIDER: "openai", OPENAI_BASE_URL: "https://api.openai.com/v1", OPENAI_MODEL: "gpt-4o-mini" }],
    ["🏠 Ollama — local & 100% private", "uses your installed models",
     { JARVIS_PROVIDER: "ollama" }],
    ["🛰 Remote Jarvis — a Jarvis running elsewhere", "its URL + pairing key below",
     { JARVIS_PROVIDER: "remote" }],
  ];
  chunks.push(`<div class="st-group"><h3>BRAIN PRESETS</h3><div class="st-rows">
    ${presets.map((p, i) => `<button type="button" class="st-copy st-preset" data-preset="${i}">${p[0]}<span class="st-preset-sub">${p[1]}</span></button>`).join("")}
    <div class="st-arm">
      <strong>🧠 Arm the second mind in 60 seconds:</strong>
      <a class="st-arm-link" id="groq-get">1 · get a free Groq key ↗</a>
      <input class="st-input" id="groq-key" placeholder="2 · paste gsk_..." autocomplete="off" spellcheck="false">
      <button type="button" id="groq-arm">3 · Test & arm</button>
      <div class="st-note" id="groq-arm-note">Guarded shield stays on — your name, city, age and Panda never leave this PC.</div>
    </div>
  </div><p class="st-note" style="margin-top:8px">One click rewires the Brain section below. For cloud brains, paste your key into <b>Cloud brain API key</b> after. The current brain shows in <b>AI Core</b>. Privacy guard is watching cloud traffic (Settings → Safety).</p></div>`);

  for (const sec of d.sections) {
    const rows = sec.fields.map((f) => {
      flat[f.key] = f;
      if (f.kind === "bool")
        return `<label class="st-ctl ${f.danger ? "danger" : ""}"><span>${esc(f.label)}</span>
          <button type="button" class="st-toggle ${f.value ? "on" : ""}" data-set="${f.key}"></button></label>`;
      if (f.kind === "range")
        return `<label class="st-ctl"><span>${esc(f.label)}</span><b data-lab="${f.key}">${f.value}${f.unit || ""}</b>
          <input type="range" data-set="${f.key}" min="${f.min}" max="${f.max}" step="${f.step}" value="${f.value}"></label>`;
      const kind = f.kind === "number" ? "number" : "text";
      const bounds = f.kind === "number" ? ` min="${f.min}" max="${f.max}" step="${f.step}"` : "";
      return `<label class="st-ctl"><span>${esc(f.label)}</span>
        <input class="st-input" type="${kind}" data-set="${f.key}" value="${esc(String(f.value))}"${bounds} placeholder="${esc(f.placeholder || "")}"></label>`;
    }).join("");
    chunks.push(`<div class="st-group"><h3>${esc(sec.section.toUpperCase())}</h3>
      <div class="st-rows">${rows}</div>
      <p class="st-note" style="margin-top:8px">${esc(sec.blurb)}</p></div>`);
  }
  // Rejected-credential banner: dead keys stopped posing as brains.
  const deadBanner = (d.dead_keys || []).length
    ? `<div class="dead-keys"><b>🔑 Rejected credential${(d.dead_keys || []).length > 1 ? "s" : ""}:</b> ` +
      (d.dead_keys || []).map((k) =>
        `<span class="dk-pill">${esc(k)}</span><button class="dk-clear" data-deadclear="${esc(k)}">delete it</button>`
      ).join(" ") +
      ` <span class="st-note">— these brains 401'd and are blacklisted until the key changes. Deleting stops the error storms.</span></div>`
    : "";
  root.innerHTML = deadBanner + chunks.join("");
  root.querySelectorAll("[data-deadclear]").forEach((b) => (b.onclick = async () => {
    const prov = b.dataset.deadclear;
    const field = { openai: "OPENAI_API_KEY", remote: "JARVIS_REMOTE_KEY" }[prov];
    if (!field) return toast(`Clear ${prov}'s key in the Brain section below.`, "warn");
    const r = await post("/api/settings", { updates: { [field]: "" } });
    if (r.ok) { toast(`${prov} key purged — it will never 401 again.`); loadSettings(); loadStatus(); }
    else toast(r.error || "Couldn't clear the key", "err");
  }));

  $("#set-speak").onclick = (e) => {
    SPEAK_BACK = !SPEAK_BACK;
    localStorage.setItem("jarvis.speak", SPEAK_BACK ? "on" : "off");
    e.currentTarget.classList.toggle("on", SPEAK_BACK);
    if (!SPEAK_BACK) window.speechSynthesis?.cancel();
    toast(SPEAK_BACK ? "Spoken replies on." : "Spoken replies muted.");
  };

  $("#set-listen").onclick = (e) => {
    const on = localStorage.getItem("jarvis.listen") !== "on";
    localStorage.setItem("jarvis.listen", on ? "on" : "off");
    e.currentTarget.classList.toggle("on", on);
    if (on) startWakeLoop(); else { stopWakeLoop(); toast("Always-listen off."); }
  };

  const bootBtn = $("#set-boot");
  if (bootBtn) bootBtn.onclick = async (e) => {
    const on = !e.currentTarget.classList.contains("on");
    const r = await post("/api/autostart", { enabled: on });
    if (r.ok) { e.currentTarget.classList.toggle("on", on); toast(on ? "Jarvis will start with Windows, tucked into the tray." : "Autostart off."); }
    else toast(r.error || "Couldn't change autostart", "err");
  };

  $("#set-net").onclick = async (e) => {
    const on = !e.currentTarget.classList.contains("on");
    const r = await post("/api/network", { enabled: on });
    if (r.ok) {
      e.currentTarget.classList.toggle("on", on);
      toast(on ? "Phone control on — locked with a pairing key. Live after one relaunch." : "Phone control off (next launch).");
      loadSettings();  // re-render so the QR row appears/disappears
    } else toast(r.error || "Couldn't change network sharing", "err");
  };
  const copyBtn = $("#net-copy");
  if (copyBtn) copyBtn.onclick = async () => {
    try { await navigator.clipboard.writeText(netState.url); toast("Link copied — open it on your phone."); }
    catch { toast(netState.url); }
  };

  const groqGet = $("#groq-get");
  if (groqGet) groqGet.onclick = () => window.open("https://console.groq.com/keys", "_blank");
  const groqArm = $("#groq-arm");
  if (groqArm) groqArm.onclick = async () => {
    const key = $("#groq-key").value.trim();
    const note = $("#groq-arm-note");
    if (!key) { note.textContent = "Paste the key first."; return; }
    groqArm.disabled = true; note.textContent = "Testing the key against Groq…";
    const r = await post("/api/providers/test_key", { api_key: key });
    groqArm.disabled = false;
    if (r.ok) {
      note.textContent = `✔ Armed in ${r.latency_ms}ms — cascade brain live. Shield remains ${"guarded"}.`;
      toast(`Groq armed — Ollama stays king, cloud covers the sulks.`);
      $("#groq-key").value = "";
      loadStatus(); loadSettings();
    } else {
      note.textContent = `✘ ${r.error || "key refused"} (nothing saved)`;
    }
  };

  root.querySelectorAll(".st-preset").forEach((b) => (b.onclick = async () => {
    const [name, , updates] = presets[+b.dataset.preset];
    const r = await post("/api/settings", { updates });
    if (r.ok) {
      toast(`${name.replace(/^[^ ]+ /, "")} wired up.` + (r.notes?.length ? " " + r.notes.join(" ") : ""));
      loadStatus(); loadSettings();
    } else toast(r.error || "Preset failed", "err");
  }));

  const save = async (key, value) => {
    const f = flat[key];
    const r = await post("/api/settings", { updates: { [key]: value } });
    if (r.ok) {
      toast(`${f?.label || key} saved.` + (r.notes?.length ? " " + r.notes.join(" ") : ""));
      if (key.startsWith("OLLAMA")) loadStatus();
    } else {
      toast(`Couldn't save ${f?.label || key}: ${r.error || "unknown error"}`, "err");
    }
  };

  root.querySelectorAll(".st-toggle[data-set]").forEach((el) => (el.onclick = () => {
    el.classList.toggle("on");
    save(el.dataset.set, el.classList.contains("on"));
  }));
  root.querySelectorAll("input[data-set]").forEach((el) => {
    const key = el.dataset.set, f = flat[key];
    const liveLabel = () => {
      const lab = root.querySelector(`[data-lab="${key}"]`);
      if (lab && f) lab.textContent = el.value + (f.unit || "");
    };
    if (el.type === "range") { el.oninput = liveLabel; el.onchange = () => save(key, el.value); }
    else el.onchange = () => save(key, el.value);
  });
}

/* ─────────────────────────── navigation ─────────────────────────── */
const NAV = [
  ["command", "Command Center", "grid"],
  ["aicore", "AI Core", "core"],
  ["agents", "Agents", "agents"],
  ["tasks", "Tasks", "task"],
  ["calendar", "Calendar", "calendar"],
  ["memory", "Memory", "memory"],
  ["conversations", "Conversations", "chat"],
  ["knowledge", "Knowledge Base", "book"],
  ["watcher", "The Watcher", "eye"],
  ["tools", "Tools & Skills", "tools"],
  ["workflows", "Workflows", "flow"],
  ["studio", "Interface Studio", "palette"],
  ["settings", "Settings", "system"],
];

function buildNav() {
  $("#nav").innerHTML = NAV.map(([id, label, icon]) =>
    `<button class="nav-item${id === "command" ? " on" : ""}" data-view="${id}">
       ${svg(icon)}<span>${label}</span><span class="n" data-count="${id}" hidden>0</span>
     </button>`).join("");
  $$(".nav-item").forEach((b) => (b.onclick = () => go(b.dataset.view)));
}

/* ── notification center (the bell actually does something now) ── */
let NOTIFS = [];
try { NOTIFS = JSON.parse(localStorage.getItem("jarvis.notifs") || "[]"); } catch {}
let NOTIF_UNREAD = NOTIFS.filter(n => !n.read).length;

function fmtWhen(at) {
  const d = at ? new Date(at) : new Date();
  return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function pushNotif(text, at = "") {
  NOTIFS.unshift({ text, at: at || new Date().toISOString(), read: false });
  NOTIFS = NOTIFS.slice(0, 50);
  localStorage.setItem("jarvis.notifs", JSON.stringify(NOTIFS));
  NOTIF_UNREAD++;
  paintNotifBadge();
}
function paintNotifBadge() {
  const b = $("#feed-badge");
  b.textContent = NOTIF_UNREAD;
  b.hidden = NOTIF_UNREAD === 0;
}
function renderNotifPanel() {
  const el = $("#notif-panel");
  if (!el) return;
  el.innerHTML =
    '<div class="np-head"><strong>Notifications</strong>' +
    '<button class="np-clear" id="np-clear">Mark all read</button></div>' +
    (NOTIFS.length
      ? NOTIFS.map((n) =>
          `<div class="np-item${n.read ? "" : " unread"}"><span class="np-when">${fmtWhen(n.at)}</span>${esc(n.text)}</div>`
        ).join("")
      : '<div class="np-item">Nothing yet — routines, reminders and brain events land here.</div>');
  const clear = $("#np-clear");
  if (clear) clear.onclick = () => {
    NOTIFS.forEach((n) => (n.read = true));
    NOTIF_UNREAD = 0;
    localStorage.setItem("jarvis.notifs", JSON.stringify(NOTIFS));
    paintNotifBadge(); renderNotifPanel();
  };
}
function toggleNotifPanel(force) {
  let el = $("#notif-panel");
  if (!el) {
    el = document.createElement("div");
    el.id = "notif-panel";
    document.body.appendChild(el);
    document.addEventListener("click", (e) => {
      if (!el.contains(e.target) && e.target.closest("#btn-bell") === null)
        el.classList.remove("open");
    });
  }
  const show = force !== undefined ? force : !el.classList.contains("open");
  el.classList.toggle("open", show);
  if (show) renderNotifPanel();
}

function go(view) {
  $$(".nav-item").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
  const loader = { tasks: loadTasks, calendar: loadTasks, memory: loadMemory,
    conversations: loadConversations, tools: loadSkills, workflows: loadWorkflows,
    agents: loadAgents, aicore: loadLLMs, knowledge: renderKB, studio: buildStudio,
    watcher: loadWatch, settings: loadSettings }[view];
  if (loader) loader();
  if (view === "aicore") setTimeout(() => $("#input").focus(), 60);
}

function setCount(view, n) {
  const el = document.querySelector(`.n[data-count="${view}"]`);
  if (!el) return;
  el.textContent = n;
  el.hidden = !n;
}

/* ─────────────────────────── the globe ─────────────────────────── */
function initGlobe() {
  const cv = $("#globe"), ctx = cv.getContext("2d");
  let W = 0, H = 0, t = 0, dpr = Math.min(devicePixelRatio || 1, 2);

  const pts = [];
  const N = 620;
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = Math.PI * (3 - Math.sqrt(5)) * i;
    pts.push([Math.cos(th) * r, y, Math.sin(th) * r]);
  }
  const arcs = [];
  for (let i = 0; i < 16; i++) {
    arcs.push({ a: pts[(Math.random() * N) | 0], b: pts[(Math.random() * N) | 0], p: Math.random() });
  }

  function size() {
    W = cv.clientWidth; H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  new ResizeObserver(size).observe(cv);
  size();

  function draw() {
    const T = THEME.rgb.acc || [60, 224, 255];
    const GL = (v => (Number.isFinite(v) ? v : 1))(+THEME.values.glow);
    const LITE = THEME.rgb.lite || [160, 240, 255];
    const faint = GL || 0.35;               // keep structure readable at 0 glow
    t += THEME.values.motion ? 0.0032 : 0;
    ctx.clearRect(0, 0, W, H);
    const cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.36;
    if (R <= 0) return requestAnimationFrame(draw);

    // halo
    const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.7);
    g.addColorStop(0, trgba(T, 0.13 * faint));
    g.addColorStop(0.55, trgba(THEME.rgb.deep || [30, 140, 190], 0.05 * faint));
    g.addColorStop(1, "transparent");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    // equator + orbit rings
    ctx.strokeStyle = trgba(T, 0.22 * faint); ctx.lineWidth = 1;
    for (const [rx, ry, rot] of [[1.35, .42, t * .5], [1.18, .3, -t * .35], [1.5, .2, t * .22]]) {
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot);
      ctx.beginPath(); ctx.ellipse(0, 0, R * rx, R * ry, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
    }

    const rot = (p) => {
      const [x, y, z] = p;
      const x1 = x * Math.cos(t) - z * Math.sin(t);
      const z1 = x * Math.sin(t) + z * Math.cos(t);
      const tilt = 0.42;
      const y1 = y * Math.cos(tilt) - z1 * Math.sin(tilt);
      const z2 = y * Math.sin(tilt) + z1 * Math.cos(tilt);
      return [cx + x1 * R, cy + y1 * R, z2];
    };

    const proj = pts.map(rot);

    // mesh links
    ctx.lineWidth = 0.55;
    for (let i = 0; i < proj.length; i += 3) {
      const a = proj[i];
      if (a[2] < -0.15) continue;
      for (let j = i + 1; j < i + 14 && j < proj.length; j++) {
        const b = proj[j];
        if (b[2] < -0.15) continue;
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (d < R * 0.24) {
          ctx.strokeStyle = trgba(T, 0.1 * (1 - d / (R * 0.24)) * (a[2] + 1));
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        }
      }
    }
    // nodes
    for (const [x, y, z] of proj) {
      const depth = (z + 1) / 2;
      ctx.fillStyle = trgba(LITE, 0.18 + depth * 0.62);
      ctx.beginPath(); ctx.arc(x, y, 0.7 + depth * 1.3, 0, 6.283); ctx.fill();
    }
    // travelling arcs
    for (const arc of arcs) {
      arc.p += 0.006;
      if (arc.p > 1) { arc.p = 0; arc.a = pts[(Math.random() * N) | 0]; arc.b = pts[(Math.random() * N) | 0]; }
      const A = rot(arc.a), B = rot(arc.b);
      if (A[2] < 0 && B[2] < 0) continue;
      const x = A[0] + (B[0] - A[0]) * arc.p;
      const y = A[1] + (B[1] - A[1]) * arc.p - Math.sin(arc.p * Math.PI) * R * 0.22;
      ctx.fillStyle = trgba(LITE, 0.95);
      ctx.beginPath(); ctx.arc(x, y, 1.9, 0, 6.283); ctx.fill();
      ctx.shadowBlur = 10 * (GL || 0.35); ctx.shadowColor = THEME.values.accent;
      ctx.fill(); ctx.shadowBlur = 0;
    }
    requestAnimationFrame(draw);
  }
  draw();
}

/* ─────────────────────────── waveforms ─────────────────────────── */
function waveform(canvas, opts = {}) {
  const ctx = canvas.getContext("2d");
  const bars = opts.bars || 34;
  let t = 0, amp = 0.12, dpr = Math.min(devicePixelRatio || 1, 2);
  function size() {
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  new ResizeObserver(size).observe(canvas);
  size();
  function frame() {
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const colIdle = opts.color || THEME.values.accent || "#3ce0ff";
    const colLive = trgba(THEME.rgb.liteHot || [255, 143, 164], 0.95);
    ctx.clearRect(0, 0, W, H);
    if (THEME.values.motion) t += 0.09;
    const target = LISTENING ? 0.92 : opts.idle ?? 0.16;
    amp += (target - amp) * 0.09;
    const bw = W / bars;
    for (let i = 0; i < bars; i++) {
      const env = Math.sin((i / bars) * Math.PI);
      const h = Math.max(1.5,
        (Math.sin(t + i * 0.55) * 0.5 + Math.sin(t * 1.7 + i * 0.31) * 0.5 + 1) / 2 * H * amp * env);
      const x = i * bw + bw * 0.22, w = Math.max(1.2, bw * 0.5);
      ctx.fillStyle = LISTENING ? colLive : colIdle;
      ctx.globalAlpha = 0.35 + env * 0.6;
      ctx.fillRect(x, (H - h) / 2, w, h);
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  }
  frame();
}

/* ─────────────────────────── clock & status ─────────────────────────── */
function tickClock() {
  const d = new Date();
  $("#clock").textContent = d.toLocaleTimeString("en-GB", { hour12: false });
  $("#date").textContent = d.toLocaleDateString(undefined, {
    weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

/* ─────────────────────────── data loaders ─────────────────────────── */
/* ─────────────────────────── the watcher ─────────────────────────── */
async function loadWatch() {
  const d = await api("/api/watch");
  const sub = d.observer
    ? `watching — sampling every ${d.poll}s${d.shots_on ? `, a frame every ${d.shot_interval}s` : ""}`
    : "OFF — flip a switch and I'll start remembering what happens here.";
  $("#watch-sub").textContent = sub;

  const tgl = (label, on, key, hint) =>
    `<label class="st-ctl"><span>${label}<br><small class="st-note">${hint}</small></span>
     <button type="button" class="st-toggle ${on ? "on" : ""}" data-watch="${key}"></button></label>`;
  $("#watch-toggles").innerHTML =
    tgl("👁 Observer", d.observer, "observer", "remembers which apps you use, learns your hours") +
    tgl("📸 Screenshot timeline", d.shots_on, "shots", `one frame / ${d.shot_interval}s, pruned on rollover + exit`) +
    tgl("⌨️ Typing memory", d.typed_on, "typed", "remembers text you type (auto-pauses on sign-in screens)") +
    tgl("🔒 Auto-lock walk-away", d.autolock, "autolock", `locks Windows after ${d.autolock_minutes} idle minutes (30s warning first)`) +
    tgl("📋 Clipboard memory", d.clipboard_on, "clipboard", "copies become searchable — secrets never stored");
  $("#watch-focus").innerHTML = d.observer && d.focused?.app
    ? `<div class="watch-focus-app">${esc(d.focused.app)}</div>
       <div class="st-note">${esc(d.focused.title || "(no window title)")}</div>`
    : `<div class="st-note">Nothing — the observer is off${d.observer ? " (or the desktop can't be read here)" : ""}.</div>`;
  $("#watch-clipboard").innerHTML = (d.clipboard_recent || []).slice().reverse().map((c) =>
    `<div class="li"><span>${esc((c.text || "").replace(/\n/g, " ").slice(0, 52))}${(c.text || "").length > 52 ? "…" : ""}</span>
     <span class="st-note">${esc(c.app || "")} · ${fmtWhen(c.at)}</span></div>`
  ).join("") || `<span class="st-note">${d.clipboard_on ? "Nothing copied yet — it lands here." : "Off — flip the 📋 switch above."}</span>`;
  $("#watch-activity").innerHTML = (d.activity || []).slice().reverse().map((a) =>
    `<div class="li"><span>${esc(a.app || "?")}</span>
     <span class="st-note">${esc((a.title || "").slice(0, 60))} · ${fmtWhen(a.at)}</span></div>`
  ).join("") || '<div class="li"><span class="st-note">No sightings yet.</span></div>';
  $("#watch-shot-count").textContent = d.shots_on ? `(${d.shots_total} on disk, last 8 shown)` : "(off)";
  $("#watch-shots").innerHTML = (d.shots || []).slice().reverse().map((sh) =>
    `<figure class="shot"><img loading="lazy" src="/api/watch/shot?name=${encodeURIComponent(sh.name)}" alt="${esc(sh.name)}">
     <figcaption>${new Date(sh.at * 1000).toLocaleTimeString()}</figcaption></figure>`
  ).join("") || `<span class="st-note">${d.shots_on ? "No frames captured yet — give it a minute." : "Turn on the timeline to start capturing."}</span>`;

  document.querySelectorAll("[data-watch]").forEach((b) => (b.onclick = async () => {
    const next = !b.classList.contains("on");
    const r = await post("/api/watch", { [b.dataset.watch]: next });
    if (r.ok) { paintNotifBadge(); loadWatch(); toast(next ? "Eyes open." : "Eyes closed."); }
  }));
}
setInterval(() => {  // live focus line refreshes while you're on the view
  if ($$(".view.active")[0]?.dataset.view === "watcher") loadWatch();
}, 6000);

async function loadStatus() {
  try {
    STATUS = await api("/api/status");
  (STATUS.alerts || []).forEach((a) => {
    toast(`🔔 ${a.text}`, "good");
    if (SPEAK_BACK) say(a.text);
    pushNotif(a.text, a.at || "");
  });
  $("#core-version").textContent = "v" + STATUS.version;
  $("#op-role").textContent = STATUS.user_title || "Commander";
  const bad = STATUS.provider === "offline";
  const pill = $("#sys-pill");
  pill.classList.toggle("warn", bad);
  $("#sys-state").textContent = bad ? "LIMITED" : "OPTIMAL";

  $("#ov-list").innerHTML = (STATUS.overview || []).map((o) =>
    `<div class="ov-row ${o.state === "warn" ? "warn" : ""}">
       <div class="ov-ic">${svg(o.key === "core" ? "core" : o.key === "memory" ? "memory" :
        o.key === "voice" ? "voice" : o.key === "agents" ? "agents" : o.key === "llms" ? "llm" :
        o.key === "skills" ? "tools" : o.key === "turns" ? "chat" : "system")}</div>
       <div><b>${o.label}</b><span>${o.value}</span></div><i class="st"></i>
     </div>`).join("");

  $("#directives").innerHTML = `
    <li>Assistant <b>${STATUS.assistant}</b></li>
    <li>Brain <b>${STATUS.provider}</b></li>
    <li>Model <b>${STATUS.model}</b></li>
    <li>Host <b>${STATUS.hostname}</b></li>
    <li>Platform <b>${STATUS.os}</b></li>
    <li>Skills <b>${STATUS.skills}</b></li>
    <li>Wake word <b>${STATUS.wake_word}</b></li>
    ${(STATUS.notes || []).map((n) => `<li style="color:var(--warn)">${n}</li>`).join("")}`;

  const sel = $("#provider");
  if (sel) sel.value = ["openai", "ollama", "offline"].includes(STATUS.provider) ? STATUS.provider : "auto";
  setCount("tools", STATUS.skills);
  $("#tool-count").textContent = `${STATUS.skills} registered`;
  $("#mem-turns").textContent = STATUS.stats?.session_turns ?? 0;
  $("#mem-tools").textContent = STATUS.stats?.tool_calls ?? 0;
  } catch (e) {
    // backend (or your own hiccup): the dashboard must NEVER freeze in BOOTING
    const pill = document.querySelector("#sys-pill");
    if (pill) { pill.textContent = "LINK DOWN — retrying"; pill.style.color = "#f0b35c"; }
    try { post("/api/uierror", { text: "loadStatus: " + (e && e.message || e) }); } catch (_2) {}
  }
}
async function loadSystem() {
  const d = await api("/api/system");
  for (const key of ["cpu", "memory", "disk"]) {
    const dial = document.querySelector(`.dial[data-key="${key}"]`);
    if (!dial) continue;
    const v = d[key] ?? 0;
    dial.querySelector(".fill").style.strokeDashoffset = 251.2 * (1 - v / 100);
    dial.querySelector("b").textContent = d[key] == null ? "—" : Math.round(v) + "%";
    dial.classList.toggle("high", v > 85);
  }
  $("#uptime").textContent = d.uptime ? `up ${d.uptime}` : "—";
}

async function loadFeed() {
  const { items } = await api("/api/feed");
  const warn = items.filter((i) => i.kind === "warn").length;
  $("#feed-badge").textContent = warn;
  $("#feed-badge").hidden = !warn;
  $("#feed").innerHTML = items.map((i, n) =>
    `<div class="feed-item ${i.kind}">
       <div class="fi-ic">${svg(i.icon)}</div>
       <div class="fi-body"><p>${esc(i.title)}</p><span class="fi-tag">${esc(i.tag)}</span></div>
       ${i.action ? `<button class="fi-act" data-fi="${n}">${esc(i.action.label)}</button>` : ""}
     </div>`).join("") || `<div class="empty">All quiet. Nothing needs your attention.</div>`;
  $$("[data-fi]").forEach((b) => {
    const act = items[+b.dataset.fi].action;
    b.onclick = () => (act.view ? go(act.view) : sendMessage(act.cmd, true));
  });
}

const AGENT_COLOR = { core: "", system: "green", voice: "violet", memory: "violet", task: "amber", research: "" };

async function loadAgents() {
  const { agents } = await api("/api/agents");
  const html = agents.map((a) =>
    `<div class="agent ${a.status}" data-c="${AGENT_COLOR[a.id] || ""}">
       <div class="ag-ic">${svg(a.icon)}</div>
       <div class="ag-body"><b>${esc(a.name)}</b>
         <div class="ag-state"><i></i>${a.status}${a.detail ? " · " + esc(a.detail) : ""}</div></div>
       <canvas class="ag-wave"></canvas>
     </div>`).join("");
  $("#agent-grid").innerHTML = html;
  $("#agent-grid-full").innerHTML = html;
  $("#agent-count").textContent = `${agents.filter((a) => a.status === "active").length} active / ${agents.length}`;
  $$(".ag-wave").forEach((c) => waveform(c, { bars: 14, idle: 0.5 }));
}

async function loadLLMs() {
  const { providers } = await api("/api/llms");
  const on = providers.filter((p) => p.connected).length;
  $("#llm-count").textContent = `${on} connected`;
  const html = providers.map((p) =>
    `<div class="llm ${p.connected ? "on" : ""}" title="${esc(p.hint)}">
       <div class="llm-dot">${p.connected ? "●" : "○"}</div>
       <div style="min-width:0"><b>${esc(p.name)}</b><span>${esc(p.detail)}</span></div>
     </div>`).join("");
  $("#llm-grid").innerHTML = html;
  $("#llm-list").innerHTML = html;
}

async function loadTasks() {
  const { tasks, timeline, overdue } = await api("/api/tasks");
  const open = tasks.filter((t) => !t.done);
  setCount("tasks", open.length);
  $("#task-count").textContent = `${open.length} open${overdue ? ` · ${overdue} overdue` : ""}`;

  $("#task-list").innerHTML = tasks.length ? tasks.map((t) =>
    `<div class="li ${t.done ? "done" : ""}">
       <button class="li-check" data-toggle="${t.id}">${svg("check")}</button>
       <div class="li-body"><div class="li-title">${esc(t.title)}</div>
         <div class="li-meta"><span class="tag">${esc(t.tag)}</span>
         ${t.due ? `<span>${fmtDue(t.due)}</span>` : ""}</div></div>
       <button class="li-del" data-del-task="${t.id}">×</button>
     </div>`).join("") : `<div class="empty">No tasks. Say “add a task finish the report at 5pm”.</div>`;

  const tlHtml = timeline.length ? timeline.map((i) =>
    `<div class="tl-row ${i.state}"><div class="tl-time">${esc(i.at)}</div>
       <div class="tl-main"><span class="tl-rel">${esc(i.relative)}</span><b>${esc(i.title)}</b>
       <div class="tl-bar" style="width:${i.state === "done" ? 100 : i.state === "now" ? 65 : 30}%"></div></div>
     </div>`).join("") : `<div class="empty">Nothing scheduled.\nAdd a task with a time to populate the timeline.</div>`;
  $("#timeline").innerHTML = tlHtml;
  $("#timeline-full").innerHTML = tlHtml;

  $$("[data-toggle]").forEach((b) => (b.onclick = async () => {
    await post(`/api/tasks/${b.dataset.toggle}/toggle`); loadTasks(); loadFeed();
  }));
  $$("[data-del-task]").forEach((b) => (b.onclick = async () => {
    await fetch(`/api/tasks/${b.dataset.delTask}`, { method: "DELETE" }); loadTasks(); loadFeed();
  }));
}

async function loadMemory() {
  const { memories, total } = await api("/api/memory");
  $("#mem-total").textContent = total;
  $("#memory-count").textContent = `${total} stored`;
  setCount("memory", total);
  $("#memory-list").innerHTML = memories.length ? memories.map((m) =>
    `<div class="li"><div class="li-check" style="border-color:var(--violet);color:var(--violet)">${svg("memory")}</div>
       <div class="li-body"><div class="li-title">${esc(m.text)}</div>
         <div class="li-meta"><span class="tag">${esc(m.kind)}</span><span>${fmtDate(m.created)}</span></div></div>
       <button class="li-del" data-del-mem="${m.id}">×</button></div>`).join("")
    : `<div class="empty">Memory is empty. Tell Jarvis “remember that I prefer dark mode”.</div>`;
  $$("[data-del-mem]").forEach((b) => (b.onclick = async () => {
    await fetch(`/api/memory/${b.dataset.delMem}`, { method: "DELETE" }); loadMemory();
  }));
  drawMemGraph(total);
}

function drawMemGraph(n) {
  const cv = $("#mem-graph"); if (!cv) return;
  const ctx = cv.getContext("2d"), dpr = Math.min(devicePixelRatio || 1, 2);
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const count = Math.max(6, Math.min(26, n + 6));
  const nodes = [];
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 + i * 0.7;
    const r = (0.18 + ((i * 37) % 100) / 100 * 0.32) * Math.min(W, H);
    nodes.push([W / 2 + Math.cos(a) * r * 1.5, H / 2 + Math.sin(a) * r]);
  }
  ctx.strokeStyle = trgba(THEME.rgb.acc || [60, 224, 255], 0.22); ctx.lineWidth = 0.7;
  nodes.forEach((a, i) => nodes.slice(i + 1).forEach((b) => {
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < Math.min(W, H) * 0.34) {
      ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
    }
  }));
  nodes.forEach(([x, y], i) => {
    ctx.fillStyle = i % 4 === 0 ? THEME.values.violet || "#a06bff" : THEME.values.accent || "#3ce0ff";
    ctx.shadowBlur = 8; ctx.shadowColor = ctx.fillStyle;
    ctx.beginPath(); ctx.arc(x, y, i % 4 === 0 ? 3 : 2, 0, 6.283); ctx.fill();
  });
  ctx.shadowBlur = 0;
}

async function loadConversations() {
  const { conversations } = await api("/api/conversations");
  setCount("conversations", conversations.length);
  $("#convo-list").innerHTML = conversations.length ? conversations.map((c) =>
    `<div class="convo"><div class="cu">› ${esc(c.user)}</div>
       <div class="cr">${esc(c.reply)}</div>
       <div class="cm">${fmtDate(c.at)} · ${esc(c.provider)}${c.actions?.length ? ` · ${c.actions.length} tool call(s)` : ""}</div>
     </div>`).join("") : `<div class="empty">No conversations logged yet.</div>`;
}

let SKILLS = [];
async function loadSkills() {
  if (!SKILLS.length) SKILLS = (await api("/api/skills")).skills;
  renderSkills($("#skill-filter").value || "");
}
function renderSkills(filter) {
  const f = filter.toLowerCase();
  const list = SKILLS.filter((s) => (s.name + s.description + s.group).toLowerCase().includes(f));
  const groups = {};
  list.forEach((s) => (groups[s.group] = groups[s.group] || []).push(s));
  $("#skill-groups").innerHTML = Object.entries(groups).map(([g, items]) =>
    `<div class="sg-title">${esc(g)} — ${items.length}</div>
     <div class="sk-grid">${items.map((s) =>
      `<div class="sk ${s.dangerous ? "danger" : ""}" data-try="${esc(s.triggers[0] || s.name)}">
         <b>${esc(s.name)}</b><span>${esc(s.description)}</span>
         ${s.triggers[0] ? `<em>“${esc(s.triggers[0].replace(/\{(\w+)\}/g, "…"))}”</em>` : ""}
       </div>`).join("")}</div>`).join("") || `<div class="empty">No skills match “${esc(filter)}”.</div>`;
  $$("[data-try]").forEach((el) => (el.onclick = () => {
    go("aicore"); $("#input").value = el.dataset.try.replace(/\{(\w+)\}/g, ""); $("#input").focus();
  }));
}

async function loadRoutines() {
  const { routines } = await api("/api/routines");
  const grid = $("#rt-grid");
  grid.innerHTML = routines.length ? routines.map((r) =>
    `<div class="wf"><h3>🕐 ${esc(r.name)}</h3>
       <p>${esc(r.schedule_human)} · ${r.enabled ? "on" : "done"} · last: ${esc(r.last_run || "never")}</p>
       <p class="dim" style="font-size:11px">${esc(r.prompt.slice(0, 120))}</p>
       <div style="display:flex;gap:8px">
         <button class="wf-run" data-rt-run="${r.id}">▶ Run now</button>
         <button class="wf-run st-danger" data-rt-del="${r.id}">✕</button>
       </div>${r.runs?.length ? `<p class="dim" style="font-size:10.5px;margin-top:6px">last run: ${esc((r.runs[r.runs.length-1].summary || "").slice(0, 140))}</p>` : ""}</div>`
  ).join("") : `<p class="dim">No routines yet — try “every morning brief me on my tasks” in chat, or + new routine.</p>`;
  $$("[data-rt-run]").forEach((b) => (b.onclick = async () => {
    b.textContent = "Running…";
    const r = await post(`/api/routines/${b.dataset.rtRun}/run`);
    toast(r.note || r.error, r.ok ? "good" : "err");
    setTimeout(loadRoutines, 1200);
  }));
  $$("[data-rt-del]").forEach((b) => (b.onclick = async () => {
    b.textContent = "…";
    await fetch(`/api/routines/${b.dataset.rtDel}`, { method: "DELETE" });
    toast("Routine removed."); loadRoutines();
  }));
}

async function loadWorkflows() {
  const { workflows } = await api("/api/workflows");
  loadRoutines();
  setCount("workflows", workflows.length);
  $("#wf-grid").innerHTML = workflows.map((w) =>
    `<div class="wf"><h3>${esc(w.name)}</h3><p>${esc(w.description)}</p>
       <ol>${w.steps.map((s) => `<li>${esc(s.skill)}</li>`).join("")}</ol>
       <button class="wf-run" data-wf="${w.id}">▶ Execute</button></div>`).join("");
  $$("[data-wf]").forEach((b) => (b.onclick = async () => {
    b.textContent = "Running…";
    const r = await post(`/api/workflows/${b.dataset.wf}/run`);
    b.textContent = "▶ Execute";
    toast(`${r.name}\n` + (r.results || []).map((x) => `• ${x.result.split("\n")[0]}`).join("\n"));
    refreshDash();
  }));
}

async function loadQuick() {
  const items = [
    ["Start New Task", "plus", () => { go("tasks"); $("#task-title").focus(); }],
    ["Executive Briefing", "play", () => sendMessage("executive briefing", true)],
    ["Take Screenshot", "camera", () => sendMessage("take a screenshot", true)],
    ["Open Calendar", "calendar", () => go("calendar")],
    ["System Report", "cpu", () => sendMessage("system status", true)],
    ["Security Scan", "alert", () => sendMessage("security report", true)],
    ["Speed Up My PC", "power", () => sendMessage("speed up my pc", true)],
    ["Start Voice Chat", "voice", () => toggleMic()],
    ["Run Workflow", "flow", () => go("workflows")],
    ["Lock Computer", "power", () => sendMessage("lock the computer", true)],
  ];
  $("#quick").innerHTML = items.map(([label, ic], i) =>
    `<button class="qbtn" data-q="${i}"><i>${svg(ic)}</i>${label}</button>`).join("");
  $$("[data-q]").forEach((b) => (b.onclick = items[+b.dataset.q][2]));
}

async function loadEnvironment() {
  const e = await api("/api/environment");
  $("#sb-location").textContent = e.location;
  $("#sb-weather").textContent = e.weather ? `${e.weather.temp}°F ${e.weather.text}` : "Unavailable";
  $("#sb-network").textContent = e.network;
}

function renderKB() {
  const cards = [
    ["Talking to Jarvis", `<p>Type in <b>AI Core</b>, click the mic orb, or hit the <b>TALK TO JARVIS</b> bar. Press <code>Space</code> anywhere to start voice input, <code>/</code> to jump to search.</p>`],
    ["Give it a real brain", `<p>Offline mode understands direct commands only. For conversation:</p>
      <ul><li>Free & private: install <code>ollama</code>, run <code>ollama pull llama3.2</code></li>
      <li>Cloud: put <code>OPENAI_API_KEY</code> in <code>.env</code></li>
      <li>Free cloud tier: Groq — set <code>OPENAI_BASE_URL</code> to their endpoint</li></ul>`],
    ["Controlling the PC", `<ul><li>“open spotify”, “close chrome”, “switch to word”</li>
      <li>“set volume to 30”, “mute”, “set brightness to 80”</li>
      <li>“take a screenshot”, “lock the computer”, “sleep”</li>
      <li>“list processes by memory”, “empty the recycle bin”</li></ul>`],
    ["Tasks & memory", `<ul><li>“add a task finish the report at 5pm”</li>
      <li>“what are my tasks”, “mark report as done”</li>
      <li>“remember that I prefer dark mode”</li>
      <li>“what do you know about me”</li></ul>
      <p>Everything persists in <code>JarvisFiles/jarvis-state.json</code>.</p>`],
    ["Workflows", `<p>Chain skills into one command. Run them from the <b>Workflows</b> panel or say “run workflow Focus Mode”. Add your own in <code>jarvis/state.py</code>.</p>`],
    ["Files & research", `<ul><li>“what's in my downloads folder”</li><li>“find files named invoice”</li>
      <li>“clean my downloads”</li><li>“what's the weather”, “what's the news”</li>
      <li>“who is Ada Lovelace”, “read the page https://…”</li></ul>`],
    ["Security & tune-up", `<ul><li>“security report” — antivirus + processes + startup</li>
      <li>“scan for viruses”, “run an antivirus scan” (Windows Defender)</li>
      <li>“startup audit”, “disable startup item Spotify”</li>
      <li>“find suspicious processes”</li>
      <li>“speed up my pc”, “clean my memory”, “clean temp files”</li></ul>
      <p>Everything flagged is read-only until you approve the change.</p>`],
  ];
  $("#kb").innerHTML = cards.map(([t, b]) => `<div class="kb-card"><h3>${t}</h3>${b}</div>`).join("");
}

/* ─────────────────────────── chat ─────────────────────────── */
function esc(s) { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; }
function fmtDate(iso) { try { return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); } catch { return iso; } }
function fmtDue(iso) {
  try {
    const d = new Date(iso), now = new Date();
    const s = d.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
    return d < now ? `<span class="over">overdue · ${s}</span>` : `due ${s}`;
  } catch { return iso; }
}

function bubble(role, text, actions = [], isErr = false, meta = {}) {
  const el = document.createElement("div");
  const prov = (meta.provider || "").toLowerCase();
  const isOffline = prov.includes("offline");   // backup brain: styles + label loudly
  el.className = `msg ${role}${isErr ? " err" : ""}${isOffline ? " offline" : ""}`;
  // The WHO label says which brain answered — no more squinting for a tiny chip.
  const who = role === "user" ? "operator"
    : isOffline ? "jarvis · offline engine"
    : prov ? `jarvis · ${prov.toUpperCase()}` : "jarvis";
  const chip = (role === "user" || !meta.provider) ? "" :
    `<div class="prov-chip${isOffline ? " warn" : ""}">via ${esc(meta.provider)}</div>`;
  el.innerHTML = `<span class="who">${who}</span>` +
    `<div>${esc(text)}</div>` +
    actions.map((a) => `<div class="act">⚙ ${esc(a.skill)}${Object.keys(a.arguments || {}).length ? " " + esc(JSON.stringify(a.arguments)) : ""}</div>`).join("") + chip;
  $("#log").appendChild(el);
  $("#log").scrollTop = $("#log").scrollHeight;
  return el;
}

async function sendMessage(text, switchView = false) {
  text = (text || "").trim(); if (!text) return;
  if (switchView) go("aicore");
  bubble("user", text);
  $("#input").value = "";
  const ghost = document.createElement("div");
  ghost.className = "msg bot";
  ghost.innerHTML = `<span class="who">jarvis</span><span class="typing"><i></i><i></i><i></i></span>`;
  $("#log").appendChild(ghost);
  $("#log").scrollTop = $("#log").scrollHeight;
  $("#sys-state").textContent = "PROCESSING";
  try {
    // Fast path: stream the answer token-by-token.
    const res = await streamChat(text, ghost);
    ghost.remove();
    bubble("bot", res.reply || "(no reply)", res.actions || [], !!res.error, { provider: res.provider });
    say(res.reply);
    refreshDash();
  } catch (e) {
    // Nothing ever streamed (old backend) — safe to retry once on the
    // classic endpoint, since no work can have happened server-side yet.
    try {
      const d = await post("/api/chat", { message: text });
      ghost.remove();
      bubble("bot", d.reply || "(no reply)", d.actions || [], !!d.error, { provider: d.provider });
      say(d.reply);
      refreshDash();
    } catch (e2) {
      ghost.remove();
      bubble("bot", `Backend unreachable: ${e2}`, [], true);
    }
  } finally {
    $("#sys-state").textContent = STATUS.provider === "offline" ? "LIMITED" : "OPTIMAL";
  }
}

async function streamChat(text, ghost) {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });
  if (!resp.ok || !resp.body) throw new Error(`stream unavailable (${resp.status})`);

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "", reply = "", actions = [], final = null, sawEvent = false;

  const paint = () => {
    ghost.innerHTML = `<span class="who">jarvis</span><div>${esc(reply)}</div>`;
    $("#log").scrollTop = $("#log").scrollHeight;
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx); buf = buf.slice(idx + 2);
      const line = raw.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      let ev;
      try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
      sawEvent = true;
      if (ev.type === "token") { reply += ev.text; paint(); }
      else if (ev.type === "action") { actions.push(ev); }
      else if (ev.type === "done") { final = ev; }
      else if (ev.type === "error") {
        // A crash after partial work — do NOT retry elsewhere (would double-run).
        final = { reply: reply || `Something glitched mid-thought. (${ev.error})`, actions, error: ev.error };
      }
    }
  }
  if (final) {
    return {
      reply: final.reply || reply,
      actions: (final.actions && final.actions.length ? final.actions : actions),
      error: final.error || null,
    };
  }
  if (sawEvent || reply) {
    // Connection died mid-stream: keep what we have, never re-queue the work.
    return { reply: reply || "My connection to the backend dropped mid-reply.", actions, error: "stream ended early" };
  }
  throw new Error("no stream events"); // → caller falls back to /api/chat
}

/* ─────────────────────────── voice ─────────────────────────── */
function say(text) {
  if (!SPEAK_BACK || !text || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(String(text).replace(/[*_`#]/g, "").slice(0, 600));
  const vs = speechSynthesis.getVoices();
  const pick = vs.find((v) => /david|guy|daniel|male/i.test(v.name) && /en/i.test(v.lang))
    || vs.find((v) => /en-GB/i.test(v.lang)) || vs.find((v) => /en/i.test(v.lang));
  if (pick) u.voice = pick;
  u.rate = 1.03; u.pitch = 0.92;
  if (WAKE_WANT && !LISTENING && !WAKE_LOOP) startWakeLoop();  // barge-in: ears stay on while I speak
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}

function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    $("#voice-label").textContent = "Browser STT unavailable";
    $("#talk-sub").textContent = "Use the text console";
    return;
  }
  RECOGNIZER = new SR();
  RECOGNIZER.lang = "en-US"; RECOGNIZER.interimResults = true; RECOGNIZER.continuous = false;
  RECOGNIZER.onstart = () => { LISTENING = true; setVoiceUI(true); if (WAKE_LOOP) stopWakeLoopSoft(); };
  RECOGNIZER.onend = () => {
    LISTENING = false; setVoiceUI(false);
    // hand the mic back to the always-listen loop when a command finishes
    if (WAKE_WANT) setTimeout(() => { if (!LISTENING) { WAKE_LOOP = null; startWakeLoop(); } }, 700);
  };
  RECOGNIZER.onerror = (e) => { LISTENING = false; setVoiceUI(false); if (e.error === "not-allowed") toast("Microphone access was blocked.", "warn"); };
  RECOGNIZER.onresult = (e) => {
    const res = e.results[e.results.length - 1];
    const text = res[0].transcript;
    $("#voice-label").textContent = text.slice(0, 40);
    if (res.isFinal) sendMessage(text.replace(new RegExp(`^\\s*${STATUS.wake_word || "jarvis"}[,\\s]*`, "i"), ""), true);
  };
}

/* ───── always-listening wake loop + global summon hook ───── */
let WAKE_LOOP = null, WAKE_WANT = false;

let _wakeFailCount = 0;
function safeStartWakeLoop() {
  // WebView2 (the desktop window) has flaked out voice before; if the
  // recognizer won't stay alive after 3 honest tries, disarm rather than hang.
  if (_wakeFailCount >= 3) {
    localStorage.setItem("jarvis.listen", "off");
    toast("Always-listen keeps failing here, so I disarmed it — the mic button still works.", "warn");
    fetch("/api/uierror", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: "wake loop gave up after 3 failed starts"})}).catch(() => {});
    return;
  }
  try { startWakeLoop(); } catch (e) { _wakeFailCount++; reportUiError("startWakeLoop threw: " + e); }
}

function reportUiError(text) {
  try {
    fetch("/api/uierror", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: String(text).slice(0, 500)})}).catch(() => {});
  } catch {}
}
window.addEventListener("error", (e) => reportUiError("JS: " + (e.message || e.type)));
window.addEventListener("unhandledrejection", (e) => reportUiError("Promise: " + (e.reason?.message || e.reason || "unknown")));

function startWakeLoop() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return toast("Always-listen needs Edge or Chrome for speech recognition.", "warn");
  if (WAKE_LOOP || LISTENING) return;
  WAKE_WANT = true;
  WAKE_LOOP = new SR();
  WAKE_LOOP.lang = "en-US"; WAKE_LOOP.continuous = true; WAKE_LOOP.interimResults = true;
  const wake = (STATUS.wake_word || "jarvis").toLowerCase();
  WAKE_LOOP.onresult = (e) => {
    const tail = Array.from(e.results).slice(-2).map((r) => r[0].transcript).join(" ").toLowerCase();
    if (tail.includes(wake)) {
      WAKE_LOOP._hot = true;
      speechSynthesis?.cancel();   // barging in: silence the reply instantly
      try { WAKE_LOOP.stop(); } catch {}
    }
  };
  WAKE_LOOP.onend = () => {
    const hot = WAKE_LOOP && WAKE_LOOP._hot;
    WAKE_LOOP = null;
    if (hot) { toast(`Heard you — listening…`); toggleMic(); }
    else if (WAKE_WANT && !LISTENING) setTimeout(() => { if (WAKE_WANT && !LISTENING) startWakeLoop(); }, 2200);
  };
  WAKE_LOOP.onerror = (e) => {
    if (e.error === "not-allowed") {
      stopWakeLoop();
      localStorage.setItem("jarvis.listen", "off");
      toast("Microphone blocked — always-listen switched off.", "warn");
    }
  };
  try { WAKE_LOOP.start(); } catch {}
  toast(`Always-listen: say “${wake}” anytime.`, "good");
}

function stopWakeLoop() {
  WAKE_WANT = false;
  try { WAKE_LOOP?.abort(); } catch {}
  WAKE_LOOP = null;
}

// Pause the wake loop without disabling the preference (mic handoff).
function stopWakeLoopSoft() {
  try { WAKE_LOOP?.abort(); } catch {}
}

// Summoned from the Windows Ctrl+J global hotkey (desktop.py).
window.jarvisWake = () => {
  try { go("command"); } catch {}
  document.querySelector("#search")?.focus();
  if (!LISTENING && RECOGNIZER) setTimeout(() => toggleMic(), 150);
  toast("At your service.");
};

function setVoiceUI(on) {
  $("#mic-orb").classList.toggle("rec", on);
  $("#mic-sm")?.classList.toggle("rec", on);
  $("#talk-bar").classList.toggle("live", on);
  $("#voice-label").textContent = on ? "Listening…" : "Standby";
  $("#talk-sub").textContent = on ? "I am listening…" : "Click or press Space";
}

function toggleMic() {
  if (!RECOGNIZER) return toast("Speech recognition needs Edge or Chrome. Text console works everywhere.", "warn");
  if (LISTENING) return RECOGNIZER.stop();
  speechSynthesis?.cancel();
  try { RECOGNIZER.start(); } catch { /* already running */ }
}

/* ─────────────────────────── misc ─────────────────────────── */
function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`; el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(20px)"; el.style.transition = ".3s"; }, 5200);
  setTimeout(() => el.remove(), 5600);
}

function refreshDash() { loadStatus(); loadFeed(); loadTasks(); loadMemory(); loadAgents(); }

/* ─────────────────────────── boot ─────────────────────────── */
(async function boot() {
  initTheme();   // before any canvas work so drawings pick up themed colours
  SPEAK_BACK = localStorage.getItem("jarvis.speak") !== "off";
  buildNav();
  buildStudio();
  loadSettings();
  initGlobe();
  waveform($("#voice-wave"), { bars: 30, idle: 0.22 });
  waveform($("#talk-wave-l"), { bars: 16, idle: 0.3 });
  waveform($("#talk-wave-r"), { bars: 16, idle: 0.3 });
  tickClock(); setInterval(tickClock, 1000);
  initVoice();
  renderKB();

  // events
  $("#composer").onsubmit = (e) => { e.preventDefault(); sendMessage($("#input").value); };
  $("#mic-orb").onclick = toggleMic;
  $("#mic-sm").onclick = toggleMic;
  $("#talk-bar").onclick = toggleMic;
  $("#btn-grid").onclick = () => go("command");
  $("#btn-bell").onclick = (e) => { e.stopPropagation(); toggleNotifPanel(); };
  paintNotifBadge();
  $("#btn-settings").onclick = () => go("settings");
  $("#settings-studio").onclick = () => go("studio");
  $("#brief-btn").onclick = () => sendMessage("executive briefing", true);
  $("#btn-reset").onclick = async () => { await post("/api/reset"); $("#log").innerHTML = ""; bubble("bot", "Context cleared."); };
  $("#btn-clear-convos").onclick = async () => { await fetch("/api/conversations", { method: "DELETE" }); loadConversations(); };
  $("#rt-add").onclick = async () => {
    const schedule = prompt("When should it run? (e.g. 'every morning', 'every day at 5pm', 'every 2 hours', 'monday 9am')", "every morning");
    if (!schedule) return;
    const promptText = prompt("What should Jarvis do each run? (plain words)", "Brief me on my tasks and the weather");
    if (!promptText) return;
    const name = prompt("Name this routine:", "Morning briefing") || "Routine";
    const r = await post("/api/routines", { name, schedule_text: schedule, prompt: promptText });
    toast(r.note || r.error, r.ok ? "good" : "err");
    if (r.ok) loadRoutines();
  };
  $("#theme-reset").onclick = () => { THEME.values = { ...THEME_DEFAULTS }; applyTheme(); buildStudio(); toast("Theme reset to the Jarvis default."); };
  $("#theme-copy").onclick = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(THEME.values, null, 2)); toast("Theme copied to the clipboard."); }
    catch { toast("Clipboard was blocked by the system.", "warn"); }
  };
  $("#theme-paste").onclick = () => {
    const raw = window.prompt("Paste a theme JSON blob from 'Copy theme':");
    if (!raw) return;
    try {
      const obj = JSON.parse(raw);
      THEME.values = { ...THEME_DEFAULTS, ...obj };
      applyTheme(); buildStudio(); toast("Theme imported.");
    } catch { toast("That doesn't look like a theme blob.", "err"); }
  };
  $("#skill-filter").oninput = (e) => renderSkills(e.target.value);
  $$("[data-goto]").forEach((b) => (b.onclick = () => go(b.dataset.goto)));

  $("#focus-btn").onclick = async (e) => {
    FOCUS_ON = !FOCUS_ON;
    e.currentTarget.classList.toggle("on", FOCUS_ON);
    const wfs = (await api("/api/workflows")).workflows;
    const wf = wfs.find((w) => /focus/i.test(w.name));
    if (FOCUS_ON && wf) { await post(`/api/workflows/${wf.id}/run`); toast("Focus Mode engaged — media paused, audio muted, display dimmed."); }
    else { await post("/api/skill", { name: "mute_audio", arguments: { mute: false } });
           await post("/api/skill", { name: "set_brightness", arguments: { percent: 80 } });
           toast("Focus Mode disengaged."); }
  };

  $("#task-form").onsubmit = async (e) => {
    e.preventDefault();
    const title = $("#task-title").value.trim(); if (!title) return;
    await post("/api/tasks", { title, due: $("#task-due").value.trim() || null });
    $("#task-title").value = ""; $("#task-due").value = "";
    loadTasks(); loadFeed();
  };
  $("#mem-form").onsubmit = async (e) => {
    e.preventDefault();
    const text = $("#mem-text").value.trim(); if (!text) return;
    await post("/api/memory", { text });
    $("#mem-text").value = ""; loadMemory();
  };
  $("#provider").onchange = async (e) => {
    const wanted = e.target.value;
    const s = await post(`/api/provider/${wanted}`);
    const fellBack = wanted !== "auto" && s.provider !== wanted;
    toast(
      (fellBack
        ? `Couldn't use ${wanted} — fell back to ${s.provider} (${s.model}).`
        : `Brain switched to ${s.provider} (${s.model}).`) +
        (s.notes?.length ? "\n" + s.notes.join("\n") : ""),
      fellBack || s.notes?.length ? "warn" : "",
    );
    loadStatus(); loadLLMs(); loadAgents();
  };
  $("#search").oninput = (e) => {
    const q = e.target.value.trim();
    if (q.length < 2) return;
    go("tools"); $("#skill-filter").value = q; renderSkills(q);
  };
  $("#search").onkeydown = (e) => { if (e.key === "Enter" && e.target.value.trim()) { sendMessage(e.target.value.trim(), true); e.target.value = ""; } };

  document.addEventListener("keydown", (e) => {
    const typing = /input|textarea|select/i.test(document.activeElement?.tagName || "");
    if (e.key === "/" && !typing) { e.preventDefault(); $("#search").focus(); }
    if (e.code === "Space" && !typing) { e.preventDefault(); toggleMic(); }
    if (e.key === "Escape" && LISTENING) RECOGNIZER?.stop();
  });

  // initial data
  await loadStatus();
  loadQuick(); loadSystem(); loadFeed(); loadAgents(); loadLLMs();
  loadTasks(); loadMemory(); loadConversations(); loadSkills(); loadWorkflows();
  loadEnvironment();
  setInterval(loadSystem, 3000);
  setInterval(loadFeed, 20000);
  setInterval(loadStatus, 30000);
  setInterval(loadEnvironment, 600000);

  const t = STATUS.user_title || "Sir";
  bubble("bot", STATUS.provider === "offline"
    ? `Command center online, ${t}. I'm running the offline engine — direct commands only, no API key needed. Open the Knowledge Base for how to add a real model.`
    : `Command center online, ${t}. All systems nominal. What do you need?`);
  speechSynthesis?.getVoices();

  // Morning briefing: first launch of the day gets the situational rundown.
  try {
    const brief = await api("/api/briefing");
    if (brief?.pending) setTimeout(() => { bubble("bot", brief.text); if (SPEAK_BACK) say(brief.spoken); }, 900);
  } catch {}

  // Always-listening wake word, if the user armed it — but LATE: letting the
  // page settle first avoids the WebView2 voice-start freeze (mic/perms race
  // right after load was the post-boot "Not Responding").
  if (localStorage.getItem("jarvis.listen") === "on") setTimeout(safeStartWakeLoop, 4000);

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
})();
