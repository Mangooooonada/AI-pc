# J.A.R.V.I.S. — AI Command Center for your PC

A Jarvis-style assistant that runs as a **native desktop app** and actually **controls your
Windows machine**: opens apps, sets volume and brightness, takes screenshots, reports system
health, plays music, manages tasks and long-term memory, searches the web — by voice or text.

It is not a website. It opens in its own OS window, with its own taskbar entry and icon.

```
┌────────────┬──────────────────────────────────────────────────────┐
│  JARVIS    │  SYSTEM STATUS ● OPTIMAL      11:18:21      🔍 ⌘ 🔔 👤 │
│  COMMAND   ├──────────────┬───────────────────────┬───────────────┤
│  CENTER    │ AI CORE      │                       │ LIVE          │
│            │ OVERVIEW     │      ◉  JARVIS        │ INTELLIGENCE  │
│ ▸ Command  │  ● Core      │       AI CORE         │ FEED          │
│ ▸ AI Core  │  ● Memory    │      (rotating        │  ⚠ 2 overdue  │
│ ▸ Agents   │  ● Voice     │       neural globe)   │  ⓘ Standup    │
│ ▸ Tasks  3 │  ● Agents    │                       │  ✦ CPU 15%    │
│ ▸ Calendar ├──────────────┴─────────┬─────────────┴───────────────┤
│ ▸ Memory   │  ACTIVE AGENTS         │ TIMELINE    │ QUICK COMMANDS│
│ ▸ Convos   ├────────────┬───────────┴─────────────┴───────────────┤
│ ▸ Tools 51 │ SYS MONITOR│ MEMORY INSIGHTS │  LLM STATUS           │
│  ◉ VOICE   │  ◔ ◔ ◔     │  ⋰⋱ 3,380       │  ● Ollama  ○ OpenAI   │
└────────────┴────────────┴─────────────────┴───────────────────────┘
  📍 Location   ☀ Weather   📶 Network    〰 TALK TO JARVIS 〰    ▶ Briefing
```

---

## Quick start (Windows)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/) — during install,
   tick **"Add Python to PATH"**.
2. Download this repo (green **Code** button → **Download ZIP** → extract).
3. Double-click **`setup.bat`** — builds a local environment and installs everything.
4. Double-click **`JARVIS.bat`** — the app window opens.

Works immediately with **no API key**. See *Giving Jarvis a real brain* below to make it
conversational.

### Make it a proper installed app

Double-click **`build-exe.bat`**. It produces `dist\JARVIS\JARVIS.exe` — a standalone app that
runs **without Python installed**. Copy that folder anywhere, then right-click `JARVIS.exe` →
*Send to* → *Desktop (create shortcut)*, or *Pin to Taskbar*.

Want it to start with Windows? Press `Win+R`, type `shell:startup`, and drop a shortcut in.

### Every way to run it

| Command | What it does |
|---|---|
| `python main.py` | **Desktop app window** (default) |
| `python main.py web` | Serve the command center in a browser instead |
| `python main.py cli` | Terminal chat |
| `python main.py cli --speak` | Terminal chat that talks back |
| `python main.py voice` | Hands-free: say **"Jarvis, …"** |
| `python main.py say "lock the computer"` | One-shot command |
| `python main.py --fullscreen` | Borderless full-screen app |
| `python main.py --minimized` | App starts tucked into the system tray (used by Start-with-Windows) |
| `python main.py --dev` | App window with the web inspector |

---

## The command center

**Left rail** — navigation, live voice waveform with a tap-to-speak orb, and a Focus Mode button
that pauses media, mutes audio and dims the display in one click.

**Command Center view**
- **AI Core Overview** — every subsystem's real state: brain, memory count, voice availability,
  running agents, connected LLMs, loaded skills.
- **Neural globe** — a live-rendered rotating node sphere with travelling data arcs.
- **Live Intelligence Feed** — generated from actual conditions: overdue tasks, upcoming
  schedule, CPU/memory spikes, low battery, full disk, setup tips. Each item is clickable.
- **Active Agents** — six subsystems with real status (active / standby / offline) and animated
  activity traces.
- **Mission Timeline** — your real tasks that have due times, colour-coded overdue / now /
  upcoming / done.
- **Quick Commands** — one-click briefing, screenshot, system report, lock, voice chat.
- **System Monitor** — three animated dials driven by live `psutil` telemetry.
- **Memory Insights** — a constellation graph plus memories stored, session turns, tool calls.
- **LLM Status** — which providers are genuinely reachable right now.

**Other views** — AI Core (full chat + provider control), Agents, Tasks (add/complete/delete),
Calendar, Memory, Conversations, Knowledge Base, Tools & Skills (all 51, grouped and filterable),
Workflows.

**Status bar** — your location, live weather, connectivity, a centre **TALK TO JARVIS** button
with dual waveforms, and Executive Briefing.

**Shortcuts** — `Space` starts voice input anywhere · `/` focuses search · `Esc` stops listening.

---

## Giving Jarvis a real brain

Fastest path: **Settings ⚙ → Brain presets** — one click for *Groq (free,
fastest cloud)*, *OpenAI (paid, top tier)* or *Ollama (local, private)*. For
the cloud brains you only need to paste a free/paid API key afterwards;
everything else — URL, model, provider — is filled in and hot-reloaded.



Three interchangeable brains, switchable live from the dropdown in **AI Core**.

### Option A — Ollama (free, private, no key, runs on your PC) ⭐ recommended

1. Install **[ollama.com/download](https://ollama.com/download)**.
2. Pull a model:
   ```
   ollama pull llama3.2
   ```
   *`llama3.2` (2 GB) runs on almost anything. With 16 GB+ RAM or a decent GPU, try
   `ollama pull qwen2.5:7b` — noticeably better at using tools.*
3. Restart Jarvis. It auto-detects it.

### Living on your PC (resident mode)

- **System tray** — the close button tucks Jarvis into the tray (needs `pystray`, installed by setup); the **Quit** item on the tray icon is the real off switch.
- **Start with Windows** — Settings → App. Jarvis boots minimized with your PC.
- **Ctrl+J anywhere** — global hotkey that summons Jarvis and starts listening (Windows).
- **Morning briefing** — first launch of the day greets you with time, weather, open/overdue tasks and machine health, spoken aloud.
- **Always-listening wake word** — Settings → App. The mic idles until it hears "Jarvis".
- **Proactive nudges** — timers and due reminders interrupt you with a toast + a spoken line, even mid-chat.

### Phone control (same Wi-Fi)

Settings → App → **Control from my phone**: Jarvis shows a LAN URL + QR code.
Open it on your phone and you get the full command center. Sharing binds the
server to the network on next launch and **locks every API call behind a
pairing key** carried by that link — your neighbours' bored teenager can't
drive your PC. Turning it off binds Jarvis back to localhost-only.

### Interface Studio — make it yours

Open **Interface Studio** in the sidebar to restyle the command center live:

- **Colours** — accent (primary / deep / dim), background glows, panel tint, all text
  tones, and every status colour (success / warning / danger / violet / amber)
- **Finish** — panel opacity, glow intensity (everything glow scales together),
  corner roundness, interface text size
- **Layout** — sidebar width, top bar height, bottom bar height
- **Effects** — scanlines on/off + strength, vignette, animations on/off
- **Presets** — Jarvis Classic, Iron Legion, Matrix Ops, Ultraviolet, Solar Dusk
- **Copy theme / Paste theme** — export your setup as JSON and move it between PCs

Changes apply instantly and are saved in the app (`localStorage`), so they survive
restarts.

### Making Ollama smarter

- **Bigger/better model = better brain.** In 2026 the sweet spots for tool-calling
  assistants are `qwen3:8b` (~5 GB, golden mean), `qwen3:14b` (step up, ~9 GB),
  and `llama3.1:8b` (fastest time-to-first-token). Big GPU (24 GB+)? Try
  `qwen3:32b` or `qwen3-coder-next`. Then set `OLLAMA_MODEL=` to match.
- **Context size matters.** Ollama defaults models to a 2k–4k-token context, which
  silently chops Jarvis's prompt and tool list. Jarvis now sends `num_ctx` itself —
  tune it with `OLLAMA_NUM_CTX` (default `12288`; raise to `16384`+ if you have the RAM).
- **Keep it loaded.** `OLLAMA_KEEP_ALIVE=30m` (default) keeps the model in memory
  between requests instead of reloading every chat.
- **Deterministic tools.** Lower `JARVIS_TEMPERATURE` towards `0.2` for stricter,
  more literal tool usage; raise it (≤0.8) for chattier, more creative replies.
- **Thinking models** (qwen3 family): set `OLLAMA_THINK=false` if you want fast
  plain answers without visible reasoning time.

### Privacy guard + audit trail (their "Privacy Guard Core")

`JARVIS_PRIVACY` in Settings (or .env) sets one of three modes:
- **strict** — cloud LLM calls are refused outright; Jarvis runs on Ollama/offline only.
- **guarded** *(default)* — cloud is allowed, but API keys, `ghp_`/`sk-`/Slack/AWS/Google
  tokens, `password: …`/`token=…` values and private-key blocks are redacted from every
  outbound message before it leaves the PC (your own on-disk history stays intact).
- **relaxed** — cloud allowed, no redaction.

Every external call is written to a replayable **audit ledger** (`GET /api/audit`,
capped at 500 entries) recording provider, model, redaction count and strict-blocks.

### Brain auto-routing + a memory that sticks

- **Auto / router mode** (the default when both exist): quick and private turns
  go to the fast local Ollama model; long or code/analysis-flavoured turns go
  to the heavy cloud brain (OpenAI/Groq preset). Both brains read the SAME
  conversation history, so context follows you across brains. STRICT privacy
  mode pins every turn local, no matter how heavy it looks.
- **Longer short-term memory**: default history depth is now 40 turns (was 20;
  raise it further in Settings → Brain).
- **Memory survives restarts**: on launch, Jarvis reloads the last
  `JARVIS_MAX_HISTORY` turns from the saved conversation log into the brain —
  the model sees the same conversation you see on screen. Long briefing/tool
  replies are recalled trimmed so they don't crowd an 8B context window.
- **Auto-memory** (JARVIS_AUTO_MEM): Jarvis quietly saves the facts worth
  keeping — your name, favourites, where you live/work, email, birthday —
  into long-term memory. They feed every brain's system prompt AND the
  offline engine, and exact/near duplicates collapse. Toggle it in
  Settings → Resident Assistant.

### Routines — Jarvis acts on a schedule

Say **"every morning brief me on my tasks"** or **"every day at 5pm review my
downloads folder"** and Jarvis files it as a routine. Every slot, a watcher
runs that prompt through the *full* agent loop — tools, brains, everything —
and reports back as a toast + voice note ("🕐 Routine 'Morning brief': …").
Schedules are plain English: `every day at 5pm`, `every 2 hours`,
`every friday at 9am`, `in 30 minutes`. It fires **once per missed slot**
after the PC sleeps (never a burst), and it politely waits its turn while
you're mid-chat. Manage them in **Workflows → Routines** (run now, delete,
see the last summary) or by voice: "list my routines".

### Install Jarvis on your phone (PWA) + interrupt him mid-sentence

The phone UI is now a real installable web app — open it on the phone and
choose **Add to Home Screen** for a full-screen Jarvis with its own icon.
And barge-in works both ways: while Jarvis is speaking, say the wake word
and he stops talking and starts listening. No more waiting out a monologue.

### It watches, learns your habits, and (with permission) drives

Two opt-in superpowers, both **off by default**:

1. **Observer** — say *"start watching what I do"* and Jarvis quietly logs
   which apps you use and when (app-switch events only — **never keystrokes,
   never text, never screenshots in the log**; capped, local, wipeable).
   When the same ritual shows up on several different days around the same
   hour — Outlook then Teams then Spotify at 8:55 — you get a 🧠 nudge:
   *"I spotted a habit…"* Say **"review my habits"** then **"learn it"** and it
   becomes a real workflow you can trigger or schedule as a routine.
   *"what was I doing today"* gives you the honest timeline.

2. **Computer use** — flip JARVIS_COMPUTER_USE in Settings and say
   *"take control and open spotify, then start my playlist."* Jarvis plans
   the exact clicks/keystrokes FIRST and shows them to you; only after you say
   **"execute the plan"** does anything touch the mouse or keyboard. It never
   types into sign-in/payment dialogs, caps plans at 12 steps, audits every
   action to your feed, and **"stop the computer"** halts it mid-flight.
   With a vision model installed (llava/qwen3-vl) it plans *what it actually
   sees*; without one it plans from window titles. This is a pilot, not a
   chauffeur — keep it supervised.

### Raise your own model on you (fine-tuning kit)

When you've logged a few hundred good turns, say **"export my training
data"** — Jarvis writes a privacy-scrubbed ChatML dataset
(`<workspace>/training/jarvis-chatml.jsonl`: canned offline answers and error
turns skipped, API keys/passwords redacted). Then `training/README.md` walks
the two upgrade paths — **your GPU** (16 GB+) or a **~$5 rented one** — and
imports the result into Ollama as `jarvis-me`, a second brain you can switch
to from the dropdown while the stock model stays untouched.

### Ask your documents (no cloud, no embeddings)

Drop text-files-by-other-names (md, txt, json, code, logs, csv…) into
`<workspace>/docs/` (or point `JARVIS_DOCS_DIR` anywhere) and ask
**"what do my documents say about the wifi password"**. Jarvis keyword-scores
paragraphs across every file — stale-cache-free, fully local — and quotes the
relevant passage with its file name. "list my documents" shows what he can see.

### Git + Docker + Google

- **"git status" / "recent commits" / "show my changes"** read the workspace
  repo (falls back to the install folder).
- **"docker ps" / "docker logs for web" / "restart container api"** talk to the
  Docker CLI with fuzzy container-name matching — all of it degrades to plain
  English when git or Docker isn't installed.
- **Google Calendar + Gmail are pre-wired**: create an OAuth **Desktop app**
  client in Google Cloud Console, drop `credentials.json` next to JARVIS.bat,
  and say "google status" → the first request opens a browser sign-in, then
  stays connected. Read-only scopes only; both secrets files are gitignored.

### Dual brains + smart skill packing

- **Dual-brain routing** — set `OLLAMA_MODEL_BIG` (Settings → Brain, e.g. `qwen3:32b`) and long/code/analysis questions are routed to the heavy model automatically; quick chatter stays on the fast daily driver. Missing model? Jarvis warns once and stays put.
- **Skill packing** — each message only offers the ~16 most relevant skills (`JARVIS_TOOL_PACK`) instead of all 55. Less context eaten, fewer malformed tool calls out of small models. Memory, identity and web search are always packed.
- **Vision** — `OLLAMA_VISION_MODEL` (Settings → Brain) or auto-detected `llava`/`qwen3-vl`/`moondream` power *"what's on my screen?"*.

### Making Jarvis feel faster

Replies **stream in word-by-word** now (via `/api/chat/stream`), so answers start
appearing immediately instead of after the whole response is done. With 32 GB of
RAM you can also go further:

- **Never unload the model:** set `OLLAMA_KEEP_ALIVE=-1` — with 32 GB there's no
  reason to ever drop it from memory.
- **More room for context:** set `OLLAMA_NUM_CTX=16384` (KV cache eats RAM; you
  have plenty).
- **Use a bigger model:** `ollama pull qwen3:14b` (~9 GB) runs comfortably in
  32 GB and is a solid speed-vs-smarts balance.
- **GPU off-load is the real speed king:** if your PC has an NVIDIA/AMD GPU,
  Ollama uses it automatically. Verify with `ollama ps` — look for `100% GPU`.
  CPU-only inference is the usual cause of slow replies.
- **Ollama server flags** (set as system environment variables, not in `.env`):
  `OLLAMA_FLASH_ATTENTION=true` speeds up long contexts on supported models.

### Option B — OpenAI-compatible clouds (OpenAI, Groq, OpenRouter…)

**How to get an API key:**

1. Create an account at **[platform.openai.com/signup](https://platform.openai.com/signup)**.
   This is *separate* from ChatGPT — a ChatGPT Plus subscription does **not** include API access.
2. Add credit at **[platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing)**.
   The $5 minimum lasts a long time — `gpt-4o-mini` is roughly **$0.01 per 50 commands**.
3. Create a key at **[platform.openai.com/api-keys](https://platform.openai.com/api-keys)** and
   copy it (shown **only once**).
4. Copy `.env.example` to `.env`, open it in Notepad, set:
   ```
   OPENAI_API_KEY=sk-your-key-here
   OPENAI_MODEL=gpt-4o-mini
   ```
5. Restart Jarvis.

> Never commit or share `.env` — `.gitignore` already excludes it.

**Free alternative:** [Groq](https://console.groq.com/keys) has a generous free tier and is fast:
```
OPENAI_API_KEY=gsk_your_groq_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```
The same three settings work for OpenRouter, Together, DeepSeek and LM Studio.

### Option D — Remote Jarvis (a brain at a URL)

Point this Jarvis at *another running Jarvis server* (a second PC, a home
server, a live Arena sandbox session): Settings ⚙ → **Remote Jarvis** preset,
then set **Remote Jarvis brain URL** + **pairing key** (from that machine's
network-sharing card). Conversation flows to it; its AI Core shows in the
status note. Fair warning: its skills run on *that* machine, and sandbox URLs
die with their sandbox — for a permanent cloud brain use the Groq preset.

### Option C — Offline (default, zero setup)

A keyword engine maps plain phrases straight onto skills. No chat, but every command below works.

---

## What it can do — 69 skills

| Area | Say something like |
|---|---|
| **Apps** | "open spotify", "launch task manager", "close chrome", "switch to word", "what windows are open" |
| **Volume & display** | "set volume to 30", "mute", "set brightness to 80" |
| **Media** | "play music", "next track", "play Daft Punk on YouTube", "play lo-fi on Spotify" |
| **Routines** | "every morning brief me on my tasks", "every day at 5pm review my downloads", "every 90 minutes stand up and stretch" |
| **Git** | "git status", "recent commits", "what did I change in git" |
| **Docker** | "docker ps", "docker logs for web", "restart container api" |
| **Documents** | "what do my documents say about the wifi password", "search my documents for ramen", "list my documents" |
| **Google** | "google status", "what's on my google calendar", "check my gmail" |
| **Self-training** | "is my PC ready for training", "export my training data" → `training/README.md` |
| **Observer** | "start watching what I do", "what was I doing today", "review my habits", "learn it" |
| **Computer use** | "take control and open notepad", "execute the plan", "stop the computer" |
| **System** | "system status", "list processes by memory", "empty the recycle bin" |
| **Power** | "lock the computer", "sleep", "shut down in 60 seconds", "cancel shutdown" |
| **Screen & eyes** | "take a screenshot", "what's on my screen?" *(needs a vision model: `ollama pull llava`)* |
| **Clipboard** | "what's on my clipboard", "summarize my clipboard", "copy that to my clipboard" |
| **Files** | "what's in my downloads folder", "find files named invoice", "clean my downloads", "take a note: buy cables" |
| **Tasks** | "add a task finish the report at 5pm", "what are my tasks", "mark report as done" |
| **Memory** | "remember that I prefer dark mode", "what do you know about me", "what's my name" |
| **Workflows** | "run workflow Focus Mode", "brief me" |
| **Web** | "what's the weather", "what's the news", "who is Ada Lovelace", "google mechanical keyboards", "read the page https://…" |
| **Security** | "security report", "scan for viruses", "check for suspicious processes", "startup audit", "disable startup item Spotify" |
| **Tune-up** | "speed up my pc", "clean my memory", "clean temp files", "why is boot so slow" |
| **Utilities** | "what time is it", "set a timer for 10 minutes", "what is 15% of 240", "tell me a joke" |

Tasks, memories, conversations and workflows persist in
`C:\Users\you\JarvisFiles\jarvis-state.json`.

---

## Voice

**In the app** — click the mic orb, the bottom **TALK TO JARVIS** bar, or press `Space`.
Recognition and speech both run in the embedded WebView, so there's nothing extra to install.

**Hands-free desktop mode** — `python main.py voice`, then talk:

> **"Jarvis, what's my system status?"**

Say the wake word once and Jarvis stays armed for follow-ups; "stop listening" ends it. Needs:

```
pip install SpeechRecognition
pip install pipwin && pipwin install pyaudio     # if plain 'pip install pyaudio' fails
```

For fully offline transcription add `pip install openai-whisper` — used automatically when
present. Speech output uses `pyttsx3` and the voices already built into Windows
(`JARVIS_TTS_VOICE=zira` to change).

---

## Configuration

The ⚙ **Settings** page (top-right gear, or the sidebar) edits identity, voice,
brain tuning, Ollama knobs and safety switches — changes are written to `.env`
and applied live (changing `OLLAMA_MODEL` even reloads the brain in place). The
read-out-loud toggle lives there too, next to everything theme-related in the
**Interface Studio**.

Everything else lives in `.env` (copy from `.env.example`):

| Setting | Default | Meaning |
|---|---|---|
| `JARVIS_PROVIDER` | `auto` | `auto` / `openai` / `ollama` / `offline` |
| `JARVIS_NAME` | `Jarvis` | What it calls itself |
| `JARVIS_USER_TITLE` | `Sir` | What it calls you (shown as your operator role) |
| `JARVIS_WAKE_WORD` | `jarvis` | Wake word for voice mode |
| `JARVIS_PORT` | `8600` | Internal port the app talks to |
| `JARVIS_ALLOW_POWER` | `true` | Permit shutdown / restart / sign-out |
| `JARVIS_ALLOW_SHELL` | `false` | Permit arbitrary shell commands ⚠ |
| `JARVIS_WORKSPACE` | `~/JarvisFiles` | Notes, screenshots and saved state |
| `JARVIS_DOCS_DIR` | `<workspace>/docs` | Folder the "ask my documents" skill searches |
| `JARVIS_GOOGLE_CREDENTIALS` | `credentials.json` (auto-found) | Google OAuth Desktop client JSON for Calendar/Gmail |
| `JARVIS_OBSERVE` | `false` | Observer: learn app-usage habits (app switches only, never keys) |
| `JARVIS_COMPUTER_USE` | `false` | Let Jarvis drive mouse/keyboard after plan approval |

---

## Safety

- Destructive skills (shutdown, close app, empty Recycle Bin) are flagged, and the system prompt
  requires confirmation first.
- Free-form shell execution is **off by default**.
- File reads are restricted to your home folder and the Jarvis workspace.
- The desktop app binds its backend to `127.0.0.1` only — nothing is exposed to your network.

---

## Adding your own skill

Drop a function in any file under `jarvis/skills/`. It instantly becomes both an LLM tool and an
offline voice command, and appears in the Tools & Skills panel.

```python
from . import skill

@skill(
    "coffee_break",
    "Start a coffee break: pause media, dim the screen and set a timer.",
    {"type": "object", "properties": {
        "minutes": {"type": "integer", "description": "Break length"}}},
    triggers=["coffee break", "take a break for {minutes} minutes"],
)
def coffee_break(minutes: int = 10) -> str:
    from .media import media_control
    from .system import set_brightness
    from .knowledge import set_timer
    media_control("playpause")
    set_brightness(20)
    set_timer(minutes, "coffee break")
    return f"Enjoy your {minutes} minutes, Sir."
```

Multi-step **workflows** are defined in `jarvis/state.py` and run from the Workflows panel.

---

## Project layout

```
main.py                 entry point (app / web / cli / voice / say)
setup.bat               one-click Windows install
JARVIS.bat              launch the desktop app
start-voice.bat         hands-free voice mode
start-console.bat       terminal chat
build-exe.bat           build a standalone JARVIS.exe
jarvis.spec             PyInstaller build recipe
assets/icon.ico|png     app icon
jarvis/
  config.py             settings from .env
  desktop.py            native app window (pywebview / WebView2)
  server.py             FastAPI backend + REST API
  state.py              persistent tasks, memory, conversations, workflows
  agents.py             subsystem status + live intelligence feed
  cli.py                terminal + wake-word interfaces
  brain/
    agent.py            conversation loop, tool execution
    providers.py        OpenAI / Ollama / offline keyword engine
    prompts.py          personality
  skills/
    __init__.py         @skill registry + offline intent matcher
    system.py           volume, brightness, power, screenshots, stats
    apps.py             launch / close / focus windows
    media.py            playback, YouTube, Spotify
    files.py            browse, search, read, notes, cleanup
    web.py              search, weather, news, Wikipedia
    knowledge.py        time, timers, reminders, math, jokes
    agenda.py           tasks, long-term memory, workflows, briefing
  voice/                offline TTS + microphone STT
  web/                  the command center UI (no build step)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognised | Reinstall Python with **Add to PATH** ticked |
| App window is blank/white | Install the **[WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)** (already present on Windows 11) |
| **App opens the website in your browser instead of a window** | The native window failed (usually a missing/broken WebView2 Runtime). Re-run `setup.bat` — it auto-repairs WebView2 — or install the runtime manually. Jarvis now shows a pop-up explaining the reason and logs details to `jarvis-launcher.log` |
| **Window says "Not Responding" right after launch** | The backend's imports were starving the window during boot. Fixed in the current build (backend now starts only after the window is on the clock). If boot feels glacial: run from a folder outside Downloads and add that folder to Windows Defender exclusions (`Add-MpPreference -ExclusionPath "C:\Jarvis"` in admin PowerShell) — Defender scanning every Python file at launch is the usual cause |
| **Stuck on the JARVIS boot splash** | The backend didn't answer in time. Check `jarvis-launcher.log` — the boot is instrumented (`GUI ready after…` / `Backend ready after…`). If the splash itself ever misbehaves, set env `JARVIS_NO_SPLASH=1` to bypass it |
| Window won't open at all | Jarvis falls back to your browser (with an explanation pop-up); `pip install pywebview pythonnet` to fix |
| Brain says `offline` unexpectedly | No key and no Ollama running. Start Ollama or check `.env` (a one-off Ollama error no longer sticks — the next message retries it automatically). Look at the **AI Core notes** for the exact reason |
| Ollama is running but Jarvis stays `offline` | Jarvis now self-heals: if the configured model isn't pulled, it automatically uses the best model you *do* have and tells you in the AI Core notes (e.g. "'llama3.2' isn't pulled; using 'qwen2.5:7b'"). Pin your choice with `OLLAMA_MODEL=` in `.env` |
| Chat dies with `Ollama error 400: ... can't find closing '}' symbol` | The model emitted a half-written tool call (Ollama rejects the whole request when that happens). Jarvis now automatically retries that turn without skills, so you get an answer instead of an error — the retry is logged in the console. If it keeps happening, switch models in **Settings ⚙** (`llama3.1:8b` / `qwen3:8b` are the most reliable at skills) and raise the Ollama context size there |
| Every reply is tagged `offline` and answers come from Wikipedia | Jarvis started before Ollama was up. Now the launcher **starts Ollama for you** at boot, and if you ever land offline anyway, Jarvis re-checks on every message and quietly takes the real brain the moment it appears — no restart. Also: personal questions ("what's my name", "who am I") are answered from long-term memory, never Wikipedia |
| "Does Jarvis remember things I tell it?" | Say `remember that …` (e.g. "remember my name is Manny"). Memories are injected into the brain's context every turn, so any provider can use them, and exact duplicates refresh in place instead of piling up |
| `Model 'x' isn't installed` | `ollama pull llama3.2` — or just let Jarvis auto-pick an installed one |
| Volume control imprecise | `pip install pycaw comtypes` |
| Mic does nothing | Allow microphone access when prompted; WebView2 must be up to date |
| `pyaudio` won't install | `pip install pipwin && pipwin install pyaudio` |
| Brightness does nothing | Most desktop monitors don't expose software brightness |
| Port 8600 in use | Set `JARVIS_PORT=8700` in `.env` |
| `build-exe.bat` fails | Run `setup.bat` first, then retry; check antivirus isn't quarantining PyInstaller |

## REST API

The backend is plain HTTP if you want to wire in a Stream Deck, phone shortcut or hotkey:

```
GET    /api/status              brain, model, subsystem overview
GET    /api/system              live CPU / memory / disk / battery / uptime
GET    /api/agents              subsystem roster
GET    /api/llms                provider connectivity
GET    /api/feed                live intelligence items
GET    /api/environment         location, weather, network
GET    /api/skills              full skill catalogue
POST   /api/chat                {"message": "open notepad"}
POST   /api/skill               {"name": "set_volume", "arguments": {"percent": 20}}
POST   /api/speak               {"text": "Ready when you are"}
GET    /api/tasks               tasks + timeline
POST   /api/tasks               {"title": "…", "due": "5pm"}
POST   /api/tasks/{id}/toggle   complete / reopen
GET    /api/memory              long-term memory
POST   /api/memory              {"text": "…"}
GET    /api/conversations       conversation log
GET    /api/workflows           saved workflows
POST   /api/workflows/{id}/run  execute one
POST   /api/provider/{name}     switch brain at runtime
```

Interactive docs at `/api/docs` when running in `web` mode.
