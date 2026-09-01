# J.A.R.V.I.S. — an AI assistant for your PC

A Jarvis-style assistant that actually **controls your Windows computer**: opens apps, sets
volume and brightness, takes screenshots, reports system health, plays music, searches the web,
sets timers, locks or shuts down the machine — by voice or by text.

It ships with a holographic HUD dashboard, a terminal chat, and a hands-free wake-word mode.

```
┌──────────────┬──────────────────────────────┬──────────────┐
│  TELEMETRY   │        ARC REACTOR           │   SKILLS     │
│  CPU  ▓▓▓░░  │        ( ◉ )                 │  open_app    │
│  RAM  ▓▓▓▓░  │                              │  set_volume  │
│  DISK ▓▓░░░  │   you › open spotify         │  screenshot  │
│  BATT ▓▓▓▓▓  │   jarvis › Opening Spotify.  │  …34 total   │
└──────────────┴──────────────────────────────┴──────────────┘
```

---

## Quick start (Windows)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/) — during install,
   tick **"Add Python to PATH"**.
2. Download this repo (green **Code** button → **Download ZIP** → extract).
3. Double-click **`setup.bat`** — installs everything into a local virtual environment.
4. Double-click **`start-jarvis.bat`** — the HUD opens in your browser.

That's it. Jarvis works immediately with **no API key** (offline command mode). Read on to make
it genuinely conversational.

### Other ways to run it

| Command | What it does |
|---|---|
| `python main.py` | HUD dashboard at `http://localhost:8600` |
| `python main.py cli` | Terminal chat |
| `python main.py cli --speak` | Terminal chat that talks back |
| `python main.py voice` | Hands-free: say **"Jarvis, …"** |
| `python main.py say "set volume to 20"` | One-shot command |

---

## Giving Jarvis a real brain

Jarvis has three interchangeable brains. Pick one — you can switch live from the dropdown in the
top-right of the HUD.

### Option A — Ollama (free, private, no key, runs on your PC) ⭐ recommended

Since you don't have an API key, start here. Everything stays on your machine.

1. Download and install **[ollama.com/download](https://ollama.com/download)**.
2. Open Command Prompt and pull a model:
   ```
   ollama pull llama3.2
   ```
   *`llama3.2` (2 GB) runs on almost anything. With 16 GB+ RAM or a decent GPU, try
   `ollama pull qwen2.5:7b` — noticeably smarter at using tools.*
3. Ollama runs in the background automatically. Restart Jarvis — it auto-detects it.

To pin the model, put this in your `.env`:
```
JARVIS_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
```

### Option B — OpenAI (smartest, costs a few cents)

**How to get an API key:**

1. Go to **[platform.openai.com/signup](https://platform.openai.com/signup)** and create an account
   (this is *separate* from a ChatGPT Plus subscription — Plus does **not** include API access).
2. Add credit: **[platform.openai.com/settings/organization/billing](https://platform.openai.com/settings/organization/billing)**
   → *Add payment details*. The $5 minimum lasts a very long time — `gpt-4o-mini` costs roughly
   **$0.01 for ~50 Jarvis commands**.
3. Go to **[platform.openai.com/api-keys](https://platform.openai.com/api-keys)** → *Create new
   secret key* → copy it (it starts with `sk-` and is shown **only once**).
4. In the Jarvis folder, copy `.env.example` to `.env`, open it in Notepad and set:
   ```
   OPENAI_API_KEY=sk-your-key-here
   OPENAI_MODEL=gpt-4o-mini
   ```
5. Restart Jarvis.

> Never commit `.env` or share your key — `.gitignore` already excludes it.

**Free alternatives that use the same setting:** [Groq](https://console.groq.com/keys) has a
generous free tier and is very fast. Get a key there and set:
```
OPENAI_API_KEY=gsk_your_groq_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```
The same trick works for OpenRouter, Together, DeepSeek, or a local LM Studio server.

### Option C — Offline (default, zero setup)

No model at all. A keyword engine maps plain phrases straight onto skills. It won't chat, but
every command below works. Say **"what can you do"** for the full list.

---

## What it can do — 34 skills

| Area | Say something like |
|---|---|
| **Apps** | "open spotify", "launch task manager", "close chrome", "switch to word", "what windows are open" |
| **Volume & display** | "set volume to 30", "mute", "set brightness to 80" |
| **Media** | "play music", "next track", "play Daft Punk on YouTube", "play lo-fi on Spotify" |
| **System** | "system status", "list processes by memory", "empty the recycle bin" |
| **Power** | "lock the computer", "sleep", "shut down in 60 seconds", "cancel shutdown" |
| **Screen** | "take a screenshot" |
| **Files** | "what's in my downloads folder", "open my documents folder", "find files named invoice", "clean my downloads", "take a note: buy cables" |
| **Web** | "what's the weather", "what's the news", "who is Ada Lovelace", "google mechanical keyboards" |
| **Productivity** | "what time is it", "set a timer for 10 minutes", "remind me to call mom at 17:30", "what is 15% of 240" |
| **Fun** | "tell me a joke" |

---

## Voice

**In the HUD** — click the 🎤 button (Chrome or Edge). Speech recognition and the reply voice both
run in the browser, so nothing extra to install.

**Hands-free desktop mode** — `python main.py voice`, then just talk:

> **"Jarvis, what's my system status?"**

Say the wake word once and Jarvis stays armed for follow-ups. "Stop listening" ends the session.
This mode needs a microphone package:

```
pip install SpeechRecognition
pip install pipwin && pipwin install pyaudio     # if plain 'pip install pyaudio' fails
```

For fully offline transcription (no Google round-trip), also `pip install openai-whisper` — Jarvis
uses it automatically when present. Speech output uses `pyttsx3`, which drives the voices already
built into Windows. Change voice with `JARVIS_TTS_VOICE=zira` in `.env`.

---

## Configuration

Everything lives in `.env` (copy from `.env.example`):

| Setting | Default | Meaning |
|---|---|---|
| `JARVIS_PROVIDER` | `auto` | `auto` / `openai` / `ollama` / `offline` |
| `JARVIS_NAME` | `Jarvis` | What it calls itself |
| `JARVIS_USER_TITLE` | `Sir` | What it calls you |
| `JARVIS_WAKE_WORD` | `jarvis` | Wake word for voice mode |
| `JARVIS_PORT` | `8600` | HUD port |
| `JARVIS_ALLOW_POWER` | `true` | Permit shutdown / restart / sign-out |
| `JARVIS_ALLOW_SHELL` | `false` | Permit arbitrary shell commands ⚠ |
| `JARVIS_WORKSPACE` | `~/JarvisFiles` | Where notes and screenshots are saved |

---

## Safety

- Destructive skills (shutdown, close app, empty Recycle Bin) are flagged, and the system prompt
  requires the model to confirm with you first.
- Free-form shell execution is **off by default**. Turn it on only if you trust your model.
- File reads are restricted to your home folder and the Jarvis workspace.
- The HUD binds to your machine; don't expose port 8600 to the open internet.

---

## Adding your own skill

Drop a function in any file under `jarvis/skills/` — the decorator does the rest. It instantly
becomes both an LLM tool and an offline voice command.

```python
from . import skill

@skill(
    "coffee_break",
    "Start a coffee break: pause media, dim the screen and set a 10 minute timer.",
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

---

## Project layout

```
main.py                 entry point (ui / cli / voice / say)
setup.bat               one-click Windows install
start-jarvis.bat        launch the HUD
start-voice.bat         launch hands-free voice mode
jarvis/
  config.py             settings from .env
  server.py             FastAPI backend + REST API
  cli.py                terminal + wake-word interfaces
  brain/
    agent.py            conversation loop, tool execution
    providers.py        OpenAI / Ollama / offline keyword engine
    prompts.py          personality
  skills/
    __init__.py         @skill registry + offline intent matcher
    system.py           volume, brightness, power, screenshots, stats
    apps.py             launch / close / focus windows
    media.py            playback control, YouTube, Spotify
    files.py            browse, search, read, notes, cleanup
    web.py              search, weather, news, Wikipedia
    knowledge.py        time, timers, reminders, math, jokes
  voice/
    tts.py              offline speech output
    stt.py              microphone input + wake word
  web/                  the HUD (HTML/CSS/JS, no build step)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognised | Reinstall Python with **Add to PATH** ticked |
| Brain says `offline` unexpectedly | No key and no Ollama running. Run `ollama serve`, or check `.env` |
| `Model 'x' isn't installed` | `ollama pull llama3.2` |
| Volume control imprecise | `pip install pycaw comtypes` for exact control |
| Mic button does nothing | Use Chrome/Edge and allow microphone access |
| `pyaudio` won't install | `pip install pipwin && pipwin install pyaudio` |
| Brightness does nothing | Many desktop monitors don't expose software brightness |
| Port 8600 in use | Set `JARVIS_PORT=8700` in `.env` |

## REST API

The backend is plain HTTP if you want to wire in a Stream Deck, phone shortcut, or hotkey:

```
GET  /api/status              brain, model, skill count
GET  /api/system              live CPU / memory / disk / battery
GET  /api/skills              full skill catalogue
POST /api/chat                {"message": "open notepad"}
POST /api/skill               {"name": "set_volume", "arguments": {"percent": 20}}
POST /api/speak               {"text": "Ready when you are"}
POST /api/provider/{name}     switch brain at runtime
```

Interactive docs at `http://localhost:8600/api/docs`.
