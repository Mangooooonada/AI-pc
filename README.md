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
  tune it with `OLLAMA_NUM_CTX` (default `8192`; raise to `16384`+ if you have the RAM).
- **Keep it loaded.** `OLLAMA_KEEP_ALIVE=30m` (default) keeps the model in memory
  between requests instead of reloading every chat.
- **Deterministic tools.** Lower `JARVIS_TEMPERATURE` towards `0.2` for stricter,
  more literal tool usage; raise it (≤0.8) for chattier, more creative replies.
- **Thinking models** (qwen3 family): set `OLLAMA_THINK=false` if you want fast
  plain answers without visible reasoning time.

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

### Option B — OpenAI (smartest, costs a few cents)

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

### Option C — Offline (default, zero setup)

A keyword engine maps plain phrases straight onto skills. No chat, but every command below works.

---

## What it can do — 51 skills

| Area | Say something like |
|---|---|
| **Apps** | "open spotify", "launch task manager", "close chrome", "switch to word", "what windows are open" |
| **Volume & display** | "set volume to 30", "mute", "set brightness to 80" |
| **Media** | "play music", "next track", "play Daft Punk on YouTube", "play lo-fi on Spotify" |
| **System** | "system status", "list processes by memory", "empty the recycle bin" |
| **Power** | "lock the computer", "sleep", "shut down in 60 seconds", "cancel shutdown" |
| **Screen** | "take a screenshot" |
| **Files** | "what's in my downloads folder", "find files named invoice", "clean my downloads", "take a note: buy cables" |
| **Tasks** | "add a task finish the report at 5pm", "what are my tasks", "mark report as done" |
| **Memory** | "remember that I prefer dark mode", "what do you know about me" |
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

Everything lives in `.env` (copy from `.env.example`):

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
| Window won't open at all | Jarvis falls back to your browser (with an explanation pop-up); `pip install pywebview pythonnet` to fix |
| Brain says `offline` unexpectedly | No key and no Ollama running. Start Ollama or check `.env` (a one-off Ollama error no longer sticks — the next message retries it automatically). Look at the **AI Core notes** for the exact reason |
| Ollama is running but Jarvis stays `offline` | The configured model likely isn't pulled. Jarvis now tells you in AI Core notes exactly what to run, e.g. `ollama pull llama3.2`, or that your `.env` `OLLAMA_MODEL` doesn't match an installed model |
| `Model 'x' isn't installed` | `ollama pull llama3.2` |
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
