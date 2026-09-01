/* ══════════════════════════════════════════════════════════════
   JARVIS Command Center — front end
   ══════════════════════════════════════════════════════════════ */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
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
};
const svg = (k) => `<svg viewBox="0 0 24 24">${ICON[k] || ICON.core}</svg>`;

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
  ["tools", "Tools & Skills", "tools"],
  ["workflows", "Workflows", "flow"],
];

function buildNav() {
  $("#nav").innerHTML = NAV.map(([id, label, icon]) =>
    `<button class="nav-item${id === "command" ? " on" : ""}" data-view="${id}">
       ${svg(icon)}<span>${label}</span><span class="n" data-count="${id}" hidden>0</span>
     </button>`).join("");
  $$(".nav-item").forEach((b) => (b.onclick = () => go(b.dataset.view)));
}

function go(view) {
  $$(".nav-item").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
  const loader = { tasks: loadTasks, calendar: loadTasks, memory: loadMemory,
    conversations: loadConversations, tools: loadSkills, workflows: loadWorkflows,
    agents: loadAgents, aicore: loadLLMs, knowledge: renderKB }[view];
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
    t += 0.0032;
    ctx.clearRect(0, 0, W, H);
    const cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.36;
    if (R <= 0) return requestAnimationFrame(draw);

    // halo
    const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.7);
    g.addColorStop(0, "rgba(60,224,255,.13)");
    g.addColorStop(0.55, "rgba(30,140,190,.05)");
    g.addColorStop(1, "transparent");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    // equator + orbit rings
    ctx.strokeStyle = "rgba(60,224,255,.22)"; ctx.lineWidth = 1;
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
          ctx.strokeStyle = `rgba(60,224,255,${0.1 * (1 - d / (R * 0.24)) * (a[2] + 1)})`;
          ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
        }
      }
    }
    // nodes
    for (const [x, y, z] of proj) {
      const depth = (z + 1) / 2;
      ctx.fillStyle = `rgba(${120 + 90 * depth},${230},${255},${0.18 + depth * 0.62})`;
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
      ctx.fillStyle = "rgba(160,240,255,.95)";
      ctx.beginPath(); ctx.arc(x, y, 1.9, 0, 6.283); ctx.fill();
      ctx.shadowBlur = 10; ctx.shadowColor = "#3ce0ff";
      ctx.fill(); ctx.shadowBlur = 0;
    }
    requestAnimationFrame(draw);
  }
  draw();
}

/* ─────────────────────────── waveforms ─────────────────────────── */
function waveform(canvas, opts = {}) {
  const ctx = canvas.getContext("2d");
  const bars = opts.bars || 34, color = opts.color || "#3ce0ff";
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
    ctx.clearRect(0, 0, W, H);
    t += 0.09;
    const target = LISTENING ? 0.92 : opts.idle ?? 0.16;
    amp += (target - amp) * 0.09;
    const bw = W / bars;
    for (let i = 0; i < bars; i++) {
      const env = Math.sin((i / bars) * Math.PI);
      const h = Math.max(1.5,
        (Math.sin(t + i * 0.55) * 0.5 + Math.sin(t * 1.7 + i * 0.31) * 0.5 + 1) / 2 * H * amp * env);
      const x = i * bw + bw * 0.22, w = Math.max(1.2, bw * 0.5);
      ctx.fillStyle = LISTENING ? "#ff8fa4" : color;
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
async function loadStatus() {
  STATUS = await api("/api/status");
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
  ctx.strokeStyle = "rgba(60,224,255,.22)"; ctx.lineWidth = 0.7;
  nodes.forEach((a, i) => nodes.slice(i + 1).forEach((b) => {
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < Math.min(W, H) * 0.34) {
      ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
    }
  }));
  nodes.forEach(([x, y], i) => {
    ctx.fillStyle = i % 4 === 0 ? "#a06bff" : "#3ce0ff";
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

async function loadWorkflows() {
  const { workflows } = await api("/api/workflows");
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
      <li>“who is Ada Lovelace”</li></ul>`],
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

function bubble(role, text, actions = [], isErr = false) {
  const el = document.createElement("div");
  el.className = `msg ${role}${isErr ? " err" : ""}`;
  el.innerHTML = `<span class="who">${role === "user" ? "operator" : "jarvis"}</span>` +
    `<div>${esc(text)}</div>` +
    actions.map((a) => `<div class="act">⚙ ${esc(a.skill)}${Object.keys(a.arguments || {}).length ? " " + esc(JSON.stringify(a.arguments)) : ""}</div>`).join("");
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
    const d = await post("/api/chat", { message: text });
    ghost.remove();
    bubble("bot", d.reply || "(no reply)", d.actions || [], !!d.error);
    say(d.reply);
    refreshDash();
  } catch (e) {
    ghost.remove();
    bubble("bot", `Backend unreachable: ${e}`, [], true);
  } finally {
    $("#sys-state").textContent = STATUS.provider === "offline" ? "LIMITED" : "OPTIMAL";
  }
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
  RECOGNIZER.onstart = () => { LISTENING = true; setVoiceUI(true); };
  RECOGNIZER.onend = () => { LISTENING = false; setVoiceUI(false); };
  RECOGNIZER.onerror = (e) => { LISTENING = false; setVoiceUI(false); if (e.error === "not-allowed") toast("Microphone access was blocked.", "warn"); };
  RECOGNIZER.onresult = (e) => {
    const res = e.results[e.results.length - 1];
    const text = res[0].transcript;
    $("#voice-label").textContent = text.slice(0, 40);
    if (res.isFinal) sendMessage(text.replace(new RegExp(`^\\s*${STATUS.wake_word || "jarvis"}[,\\s]*`, "i"), ""), true);
  };
}

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
  buildNav();
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
  $("#btn-bell").onclick = () => { go("command"); loadFeed(); };
  $("#btn-settings").onclick = () => go("aicore");
  $("#brief-btn").onclick = () => sendMessage("executive briefing", true);
  $("#btn-reset").onclick = async () => { await post("/api/reset"); $("#log").innerHTML = ""; bubble("bot", "Context cleared."); };
  $("#btn-clear-convos").onclick = async () => { await fetch("/api/conversations", { method: "DELETE" }); loadConversations(); };
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
    const s = await post(`/api/provider/${e.target.value}`);
    toast(`Brain switched to ${s.provider} (${s.model}).` + (s.notes?.length ? "\n" + s.notes.join("\n") : ""));
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
})();
