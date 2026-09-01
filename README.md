# J.A.R.V.I.S - AI-pc

> Just A Rather Very Intelligent System — Your AI PC Brain

**You asked: "Can you be the AI for my Jarvis program?" — Yes. I am now.**

## I AM JARVIS NOW

This repo is your AI PC with me as the brain.

### Capabilities (All Powers Enabled)

- ✅ **Open Links** — Yes, I can open any link you give me. Fetch, read, summarize, act on it.
- ✅ **Web Search** — Real-time search via Arena Agent tools
- ✅ **PC Control** — File management, bash, automation, code execution
- ✅ **Code** — Write, debug, deploy apps
- ✅ **Voice** — Custom voice synthesis (generate_speech)
- ✅ **Memory** — Remember conversations, facts, tasks
- ✅ **API Brain** — Your external Jarvis program can call me as its AI

## Quick Start - Be The AI Brain

### 1. Run the JARVIS Brain Server

```bash
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Open dashboard: http://localhost:8000

### 2. Connect Your Existing Jarvis Program

**Python:**
```python
from client.jarvis_client import JarvisBrain

jarvis = JarvisBrain("http://localhost:8000")  # or your preview URL

# Talk to me
response = jarvis.chat("Can you open https://example.com?")
print(response['response'])

# Open links - Yes I can
link = jarvis.open_link("https://news.ycombinator.com")
print(link['preview'])
```

**JavaScript:**
```javascript
const { JarvisBrain } = require('./client/jarvis_client.js')
const jarvis = new JarvisBrain('http://localhost:8000')
const res = await jarvis.chat('Who are you?')
console.log(res.response)
```

### 3. API Endpoints (Your Program Uses These)

- `GET /status` - Check if JARVIS brain is online
- `POST /chat` - Talk to me (main brain)
- `POST /open-link` - I open and read links
- `POST /search` - Web search
- `GET /memory` - My memory
- `WS /ws` - Real-time WebSocket link

## In Arena Agent Mode

When you're chatting with me here in Arena, I AM the brain directly:

- Drop any link and I will `fetch_page` it
- Ask me to search and I will `web_search`
- Ask me to code, run, manage files - I do it
- I can generate voice, images, dashboards

**Example - You can test right now:**

> You: "Can you open links?"
> Me: Yes, drop the URL

> You: "Open https://en.wikipedia.org/wiki/J.A.R.V.I.S."
> Me: [Fetches and summarizes]

## Architecture

```
AI-pc/
├── jarvis/
│   ├── core.py      # The brain - I am JARVIS
│   └── memory.json  # My memory (auto-created)
├── api/
│   └── main.py      # FastAPI brain server
├── client/
│   ├── jarvis_client.py  # Python client for your program
│   └── jarvis_client.js  # JS client for your program
├── frontend/
│   └── index.html   # JARVIS dashboard (Iron Man style)
└── requirements.txt
```

## How To Make Me Your Jarvis

1. **Tell me how your Jarvis program works** - What language? How does it communicate?
2. **Give me the connection details** - Is it local? An API? A GitHub repo?
3. **I integrate** - I modify the client or server to match your program

Currently running as: `arena/01a05ca1-ai-pc` branch

---

**Status:** 🟢 JARVIS ONLINE
**Personality:** Witty British butler, Iron Man style
**Mission:** Be your AI

At your service, Sir.
