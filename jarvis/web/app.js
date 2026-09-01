/* Jarvis HUD front-end */
const $ = (s) => document.querySelector(s);
const log = $("#log"), input = $("#input"), reactor = $("#reactor"), dot = $("#live-dot");

let speakBack = true;      // browser speech synthesis for replies
let recognizer = null;     // Web Speech API recogniser
let listening = false;

/* ------------------------------------------------------------------ chat */
function bubble(role, text, actions = [], isErr = false) {
  const el = document.createElement("div");
  el.className = `msg ${role}${isErr ? " err" : ""}`;
  const who = role === "user" ? "you" : "jarvis";
  el.innerHTML = `<span class="who">${who}</span>`;
  const body = document.createElement("div");
  body.textContent = text;
  el.appendChild(body);
  for (const a of actions) {
    const act = document.createElement("div");
    act.className = "act";
    const args = Object.keys(a.arguments || {}).length ? ` ${JSON.stringify(a.arguments)}` : "";
    act.textContent = `⚙ ${a.skill}${args}`;
    el.appendChild(act);
  }
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function thinking() {
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = `<span class="who">jarvis</span><span class="typing"><i></i><i></i><i></i></span>`;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

async function send(text) {
  text = (text || "").trim();
  if (!text) return;
  bubble("user", text);
  input.value = "";
  const ghost = thinking();
  reactor.classList.add("thinking");
  dot.className = "dot busy";
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await r.json();
    ghost.remove();
    bubble("bot", data.reply || "(no reply)", data.actions || [], !!data.error);
    say(data.reply);
    if (data.error) console.warn("jarvis:", data.error);
  } catch (e) {
    ghost.remove();
    bubble("bot", `I couldn't reach my own backend: ${e}`, [], true);
  } finally {
    reactor.classList.remove("thinking");
    dot.className = "dot on";
  }
}

/* ------------------------------------------------------- speech synthesis */
function say(text) {
  if (!speakBack || !text || !window.speechSynthesis) return;
  const clean = String(text).replace(/[*_`#]/g, "").slice(0, 600);
  const u = new SpeechSynthesisUtterance(clean);
  const voices = speechSynthesis.getVoices();
  const pick =
    voices.find((v) => /david|guy|daniel|male/i.test(v.name) && /en/i.test(v.lang)) ||
    voices.find((v) => /en-GB/i.test(v.lang)) ||
    voices.find((v) => /en/i.test(v.lang));
  if (pick) u.voice = pick;
  u.rate = 1.03; u.pitch = 0.92;
  u.onstart = () => reactor.classList.add("speaking");
  u.onend = () => reactor.classList.remove("speaking");
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

/* --------------------------------------------------------- speech to text */
function initMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = $("#btn-mic");
  if (!SR) {
    btn.title = "Voice input needs Chrome or Edge — the desktop CLI has offline voice too";
    btn.addEventListener("click", () =>
      bubble("bot", "This browser has no speech recognition. Use Chrome/Edge, or run `python main.py --voice` for offline mic support.")
    );
    return;
  }
  recognizer = new SR();
  recognizer.lang = "en-US";
  recognizer.interimResults = false;
  recognizer.continuous = false;

  recognizer.onresult = (e) => {
    const text = e.results[0][0].transcript;
    input.value = text;
    send(text);
  };
  recognizer.onend = () => { listening = false; btn.classList.remove("rec"); };
  recognizer.onerror = () => { listening = false; btn.classList.remove("rec"); };

  btn.addEventListener("click", () => {
    if (listening) { recognizer.stop(); return; }
    speechSynthesis.cancel();
    try {
      recognizer.start();
      listening = true;
      btn.classList.add("rec");
    } catch (_) {}
  });
}

/* -------------------------------------------------------------- telemetry */
function setGauge(key, value, label) {
  const g = document.querySelector(`.gauge[data-key="${key}"]`);
  if (!g) return;
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  g.querySelector("i").style.width = pct + "%";
  g.querySelector("span").textContent = label ?? (value == null ? "n/a" : pct.toFixed(0) + "%");
  g.classList.toggle("high", pct > 85);
}

async function pollSystem() {
  try {
    const d = await (await fetch("/api/system")).json();
    setGauge("cpu", d.cpu);
    setGauge("memory", d.memory);
    setGauge("disk", d.disk);
    if (d.battery) setGauge("battery", d.battery.percent, `${d.battery.percent.toFixed(0)}%${d.battery.plugged ? " ⚡" : ""}`);
    else setGauge("battery", null, "n/a");
  } catch (_) {}
}

async function loadStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    dot.className = "dot on";
    $("#tagline").textContent = `${s.provider} · ${s.skills} skills · ${s.platform}`;
    $("#status-list").innerHTML = `
      <li>brain <b>${s.provider}</b></li>
      <li>model <b>${s.model}</b></li>
      <li>host <b>${s.platform}</b></li>
      <li>wake word <b>${s.wake_word}</b></li>
      ${(s.notes || []).map((n) => `<li style="color:var(--warn)">${n}</li>`).join("")}`;
    $("#provider").value = ["openai", "ollama", "offline"].includes(s.provider) ? s.provider : "auto";
    return s;
  } catch (_) { return null; }
}

/* ----------------------------------------------------------- skills panel */
const QUICK = [
  ["System status", "what's my system status"],
  ["Screenshot", "take a screenshot"],
  ["What's open?", "list open windows"],
  ["Weather", "what's the weather"],
  ["News", "what's the news"],
  ["Time", "what time is it"],
  ["Volume 30%", "set volume to 30"],
  ["Play/pause", "play music"],
  ["Top processes", "list processes by memory"],
  ["Joke", "tell me a joke"],
];

async function loadSkills() {
  const q = $("#quick-actions");
  QUICK.forEach(([label, cmd]) => {
    const b = document.createElement("button");
    b.className = "chip"; b.textContent = label;
    b.onclick = () => send(cmd);
    q.appendChild(b);
  });

  try {
    const { skills } = await (await fetch("/api/skills")).json();
    $("#skill-count").textContent = `(${skills.length})`;
    const ul = $("#skill-list");
    const render = (filter = "") => {
      ul.innerHTML = "";
      skills
        .filter((s) => (s.name + s.description).toLowerCase().includes(filter.toLowerCase()))
        .forEach((s) => {
          const li = document.createElement("li");
          if (s.dangerous) li.className = "danger";
          li.innerHTML = `<b>${s.name}</b><span>${s.description}</span>`;
          li.title = s.triggers.length ? `try: “${s.triggers[0]}”` : s.name;
          li.onclick = () => {
            input.value = s.triggers[0] ? s.triggers[0].replace(/\{(\w+)\}/g, "…") : s.name;
            input.focus();
          };
          ul.appendChild(li);
        });
    };
    render();
    $("#skill-filter").addEventListener("input", (e) => render(e.target.value));
  } catch (_) {}
}

/* ------------------------------------------------------------------- boot */
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });
$("#btn-reset").addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  log.innerHTML = "";
  bubble("bot", "Context cleared. Fresh start.");
});
$("#provider").addEventListener("change", async (e) => {
  const v = e.target.value;
  const s = await (await fetch(`/api/provider/${v}`, { method: "POST" })).json();
  bubble("bot", `Brain switched to ${s.provider} (${s.model}).` + (s.notes?.length ? "\n" + s.notes.join("\n") : ""));
  loadStatus();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== input) { e.preventDefault(); input.focus(); }
});

(async function boot() {
  initMic();
  await loadSkills();
  const s = await loadStatus();
  pollSystem();
  setInterval(pollSystem, 4000);
  const title = s?.user_title || "Sir";
  const greeting =
    s?.provider === "offline"
      ? `Good day, ${title}. I'm running in offline mode — direct commands only, no API key required. Ask "what can you do" for the list, or see the README to plug in a real model.`
      : `Good day, ${title}. All systems online. How can I help?`;
  bubble("bot", greeting);
  // Browsers block autoplay audio until the user interacts, so don't speak the greeting.
  window.speechSynthesis?.getVoices();
})();
