"""FastAPI backend for the Jarvis Command Center."""
from __future__ import annotations

import json
import platform
import queue
import socket
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agents as agents_mod
from . import state
from .brain import Agent
from .config import config, update_env_file
from .skills import REGISTRY, run_skill

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Jarvis Command Center", docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# The agent is constructed lazily on first use: Agent() probes LLM providers
# (HTTP calls to Ollama etc.) and that cost must not sit on the app's boot
# path — the desktop window should paint first.
_agent: Optional[Agent] = None
_agent_lock = threading.Lock()


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = Agent()
    return _agent


state.bump_boot()


# ------------------------------------------------------------------ models --
class ChatIn(BaseModel):
    message: str
    provider: Optional[str] = None


class SkillIn(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


class SettingsIn(BaseModel):
    updates: Dict[str, Any]


class SpeakIn(BaseModel):
    text: str


class TaskIn(BaseModel):
    title: str
    due: Optional[str] = None
    tag: str = "general"


class MemoryIn(BaseModel):
    text: str
    kind: str = "fact"


# ------------------------------------------------------------------- core --
@app.get("/api/status")
def status() -> Dict[str, Any]:
    ag = get_agent()
    st = ag.status()
    st.update(
        {
            "voice_enabled": config.voice_enabled,
            "wake_word": config.wake_word,
            "user_title": config.user_title,
            "version": __import__("jarvis").__version__,
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "overview": agents_mod.core_overview(ag.provider_name, st["model"]),
            "stats": state.stats(),
        }
    )
    return st


@app.post("/api/chat")
def chat(body: ChatIn) -> Dict[str, Any]:
    ag = get_agent()
    if body.provider and body.provider != ag.provider_name:
        ag.reload_provider(body.provider)
    turn = ag.ask(body.message)
    state.log_turn(body.message, turn.reply, turn.actions, turn.provider)
    return {
        "reply": turn.reply,
        "actions": turn.actions,
        "provider": turn.provider,
        "error": turn.error,
    }


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn) -> StreamingResponse:
    """Server-sent events: tokens as they're generated, then a final summary.

    Event shapes (lines of `data: {...}`):
      {"type":"action","skill":..., "arguments":..., "result":...}
      {"type":"token","text":...}
      {"type":"done","reply":..., "actions":[...], "provider":..., "error":...}
      {"type":"error","error":...}
    """
    events: "queue.Queue" = queue.Queue()

    def run() -> None:
        try:
            ag = get_agent()
            if body.provider and body.provider != ag.provider_name:
                ag.reload_provider(body.provider)
            turn = ag.ask(
                body.message,
                on_action=lambda skill, res: events.put(
                    ("action", {"skill": skill, "arguments": {}, "result": res})
                ),
                on_token=lambda tok: events.put(("token", {"text": tok})),
            )
            state.log_turn(body.message, turn.reply, turn.actions, turn.provider)
            events.put(
                (
                    "done",
                    {
                        "reply": turn.reply,
                        "actions": turn.actions,
                        "provider": turn.provider,
                        "error": turn.error,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 - report anything to the client
            events.put(("error", {"error": f"{type(exc).__name__}: {exc}"}))

    threading.Thread(target=run, daemon=True).start()

    def stream():
        while True:
            kind, data = events.get()
            yield f"data: {json.dumps({'type': kind, **data})}\n\n".encode()
            if kind in {"done", "error"}:
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/skill")
def run_one(body: SkillIn) -> Dict[str, Any]:
    return {"result": run_skill(body.name, body.arguments)}


# --------------------------------------------------------------- settings --
# Field metadata driving the Settings page. Kinds: text, number, range, bool.
SETTINGS_FIELDS: List[Dict[str, Any]] = [
    {"section": "Assistant", "blurb": "Who Jarvis is, and what it calls you.", "fields": [
        {"key": "JARVIS_NAME", "attr": "name", "label": "Assistant name", "kind": "text"},
        {"key": "JARVIS_USER_TITLE", "attr": "user_title", "label": "How Jarvis addresses you", "kind": "text"},
        {"key": "JARVIS_WAKE_WORD", "attr": "wake_word", "label": "Wake word", "kind": "text"},
    ]},
    {"section": "Voice", "blurb": "Spoken replies. The read-out-loud toggle lives here too.", "fields": [
        {"key": "JARVIS_VOICE", "attr": "voice_enabled", "label": "Voice replies enabled", "kind": "bool"},
        {"key": "JARVIS_TTS_RATE", "attr": "tts_rate", "label": "Speech rate", "kind": "range", "min": 120, "max": 260, "step": 1, "unit": " wpm"},
        {"key": "JARVIS_TTS_VOICE", "attr": "tts_voice_hint", "label": "Voice match (e.g. david, zira)", "kind": "text"},
    ]},
    {"section": "Brain", "blurb": "Tuning for the local model. Applies immediately.", "fields": [
        {"key": "JARVIS_TEMPERATURE", "attr": "temperature", "label": "Creativity (temperature)", "kind": "range", "min": 0, "max": 1.5, "step": 0.05},
        {"key": "JARVIS_MAX_HISTORY", "attr": "max_history", "label": "Conversation memory depth", "kind": "range", "min": 4, "max": 60, "step": 2},
        {"key": "OLLAMA_MODEL", "attr": "ollama_model", "label": "Ollama model", "kind": "text", "placeholder": "blank = auto-pick"},
        {"key": "OLLAMA_MODEL_BIG", "attr": "ollama_model_big", "label": "Heavy brain for hard questions", "kind": "text", "placeholder": "e.g. qwen3:32b (blank = off)"},
        {"key": "OLLAMA_VISION_MODEL", "attr": "ollama_vision_model", "label": "Vision model (screen eyes)", "kind": "text", "placeholder": "blank = auto-detect llava/qwen3-vl"},
        {"key": "OLLAMA_NUM_CTX", "attr": "ollama_num_ctx", "label": "Ollama context size", "kind": "number", "min": 2048, "max": 131072, "step": 1024},
        {"key": "OLLAMA_KEEP_ALIVE", "attr": "ollama_keep_alive", "label": "Keep model loaded", "kind": "text", "placeholder": "30m  (-1 = forever)"},
        {"key": "JARVIS_TOOL_PACK", "attr": "tool_pack", "label": "Skills offered per message", "kind": "number", "min": 6, "max": 60, "step": 1},
    ]},
    {"section": "Safety", "blurb": "What Jarvis is allowed to do without asking twice.", "fields": [
        {"key": "JARVIS_ALLOW_POWER", "attr": "allow_power", "label": "Allow power commands (shutdown / restart / sleep)", "kind": "bool", "danger": True},
        {"key": "JARVIS_ALLOW_SHELL", "attr": "allow_shell", "label": "Allow raw shell commands — dangerous", "kind": "bool", "danger": True},
    ]},
]

_FIELD_BY_KEY = {f["key"]: f for s in SETTINGS_FIELDS for f in s["fields"]}


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    sections = []
    for s in SETTINGS_FIELDS:
        fields = []
        for f in s["fields"]:
            fields.append({**f, "value": getattr(config, f["attr"])})
        sections.append({"section": s["section"], "blurb": s["blurb"], "fields": fields})
    return {"sections": sections}


@app.post("/api/settings")
def update_settings(body: SettingsIn) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    for key, raw in body.updates.items():
        f = _FIELD_BY_KEY.get(key)
        if not f:
            continue
        try:
            if f["kind"] == "bool":
                value = bool(raw)
            elif f["kind"] == "number":
                value = int(raw)
                value = max(f.get("min", value), min(f.get("max", value), value))
            elif f["kind"] == "range":
                value = float(raw)
                value = max(f.get("min", value), min(f.get("max", value), value))
            else:
                value = str(raw).strip()
        except (TypeError, ValueError):
            return {"ok": False, "error": f"bad value for {key}"}
        setattr(config, f["attr"], value)
        applied[key] = str(value).lower() if isinstance(value, bool) else str(value)

    env_ok = update_env_file(applied)

    notes: List[str] = []
    if any(k == "OLLAMA_MODEL" for k in applied):
        try:
            ag = get_agent()
            if ag.provider_name == "ollama":
                st = ag.reload_provider("ollama")
                notes.append(f"brain reloaded on {st['model']}")
        except Exception:
            pass
    return {"ok": True, "applied": list(applied), "persisted": env_ok, "notes": notes}


@app.post("/api/speak")
def speak(body: SpeakIn) -> Dict[str, Any]:
    try:
        from .voice.tts import available, speak as say

        if not available():
            return {"ok": False, "error": "pyttsx3 not installed"}
        say(body.text, block=False)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/shutdown")
def shutdown() -> Dict[str, Any]:
    """Terminate this backend process (used by the desktop launcher to clear
    a stale previous instance before booting a fresh one)."""

    def _kill() -> None:
        import os

        os._exit(0)

    threading.Timer(0.4, _kill).start()
    return {"ok": True, "shutting_down": True}


@app.post("/api/reset")
def reset() -> Dict[str, Any]:
    get_agent().reset()
    return {"ok": True}


@app.post("/api/provider/{name}")
def set_provider(name: str) -> Dict[str, Any]:
    return get_agent().reload_provider(name)


# ------------------------------------------------------------- telemetry ---
@app.get("/api/system")
def system_metrics() -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "cpu": None, "memory": None, "disk": None, "battery": None,
        "net": None, "uptime": None, "cores": None,
    }
    try:
        import os

        import psutil  # type: ignore

        data["cpu"] = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        data["memory"] = vm.percent
        data["memory_detail"] = f"{vm.used / 1e9:.1f} / {vm.total / 1e9:.1f} GB"
        du = psutil.disk_usage(os.path.abspath(os.sep))
        data["disk"] = du.percent
        data["disk_detail"] = f"{du.free / 1e9:.0f} GB free"
        data["cores"] = psutil.cpu_count(logical=True)
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat:
            data["battery"] = {"percent": bat.percent, "plugged": bat.power_plugged}
        boot = datetime.fromtimestamp(psutil.boot_time())
        secs = int((datetime.now() - boot).total_seconds())
        data["uptime"] = f"{secs // 3600}h {(secs % 3600) // 60}m"
        io = psutil.net_io_counters()
        data["net"] = {"sent": io.bytes_sent, "recv": io.bytes_recv}
    except Exception:
        pass
    return data


@app.get("/api/agents")
def get_agents() -> Dict[str, Any]:
    return {"agents": agents_mod.agents(get_agent().provider_name)}


@app.get("/api/llms")
def get_llms() -> Dict[str, Any]:
    return {"providers": agents_mod.llm_providers()}


@app.get("/api/feed")
def get_feed() -> Dict[str, Any]:
    return {"items": agents_mod.intelligence_feed(get_agent().provider_name)}


@app.get("/api/environment")
def environment() -> Dict[str, Any]:
    """Location, weather and connectivity for the status bar."""
    out: Dict[str, Any] = {"location": "Unknown", "weather": None, "network": "Offline"}
    try:
        import requests

        loc = requests.get("https://ipinfo.io/json", timeout=3).json()
        city = loc.get("city") or ""
        country = loc.get("country") or ""
        out["location"] = ", ".join(x for x in (city, country) if x) or "Unknown"
        out["network"] = "Excellent"
        lat, lon = (loc.get("loc") or "0,0").split(",")
        wx = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,weather_code&temperature_unit=fahrenheit&timezone=auto",
            timeout=4,
        ).json()
        codes = {
            0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Fog", 48: "Fog", 51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
            61: "Light Rain", 63: "Rain", 65: "Heavy Rain", 71: "Snow", 73: "Snow",
            75: "Heavy Snow", 80: "Showers", 81: "Showers", 82: "Showers",
            95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms",
        }
        cur = wx["current"]
        out["weather"] = {
            "temp": round(cur["temperature_2m"]),
            "text": codes.get(cur.get("weather_code"), "Unsettled"),
        }
    except Exception:
        out["network"] = "Limited"
    return out


# ----------------------------------------------------------------- skills --
@app.get("/api/skills")
def skills() -> Dict[str, Any]:
    groups = {
        "system": "System", "apps": "Applications", "media": "Media",
        "files": "Files", "web": "Research", "knowledge": "Utilities",
        "agenda": "Productivity",
    }
    out = []
    for s in sorted(REGISTRY.values(), key=lambda s: s.name):
        module = s.func.__module__.rsplit(".", 1)[-1]
        out.append(
            {
                "name": s.name,
                "description": s.description,
                "dangerous": s.dangerous,
                "triggers": s.triggers[:3],
                "group": groups.get(module, "Other"),
                "parameters": list((s.parameters.get("properties") or {}).keys()),
            }
        )
    return {"skills": out}


# ------------------------------------------------------------------ tasks --
@app.get("/api/tasks")
def get_tasks() -> Dict[str, Any]:
    return {
        "tasks": state.list_tasks(),
        "timeline": state.timeline(),
        "overdue": len(state.overdue_tasks()),
    }


@app.post("/api/tasks")
def post_task(body: TaskIn) -> Dict[str, Any]:
    from .skills.agenda import parse_when

    iso = parse_when(body.due) if body.due else None
    return {"task": state.add_task(body.title, iso, body.tag)}


@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str) -> Dict[str, Any]:
    current = next((t for t in state.list_tasks() if t["id"] == task_id), None)
    if not current:
        return {"ok": False}
    state.complete_task(task_id, not current["done"])
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: str) -> Dict[str, Any]:
    return {"ok": state.delete_task(task_id)}


# ----------------------------------------------------------------- memory --
@app.get("/api/memory")
def get_memory(q: str = "") -> Dict[str, Any]:
    mems = state.list_memories(limit=300, query=q)
    kinds: Dict[str, int] = {}
    for m in mems:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    return {"memories": mems, "total": len(state.list_memories(limit=100000)), "kinds": kinds}


@app.post("/api/memory")
def post_memory(body: MemoryIn) -> Dict[str, Any]:
    return {"memory": state.add_memory(body.text, body.kind, "ui")}


@app.delete("/api/memory/{mem_id}")
def remove_memory(mem_id: str) -> Dict[str, Any]:
    return {"ok": state.delete_memory(mem_id)}


# ---------------------------------------------------------- conversations --
@app.get("/api/conversations")
def get_conversations() -> Dict[str, Any]:
    return {"conversations": state.list_conversations(limit=100)}


@app.delete("/api/conversations")
def clear_conversations() -> Dict[str, Any]:
    state.clear_conversations()
    get_agent().reset()
    return {"ok": True}


# -------------------------------------------------------------- workflows --
@app.get("/api/workflows")
def get_workflows() -> Dict[str, Any]:
    return {"workflows": state.list_workflows()}


@app.post("/api/workflows/{wf_id}/run")
def run_wf(wf_id: str) -> Dict[str, Any]:
    wf = state.get_workflow(wf_id)
    if not wf:
        return {"ok": False, "error": "not found"}
    results: List[Dict[str, str]] = []
    for step in wf["steps"]:
        results.append(
            {"skill": step["skill"], "result": run_skill(step["skill"], step.get("arguments", {}))}
        )
    return {"ok": True, "name": wf["name"], "results": results}


@app.delete("/api/workflows/{wf_id}")
def delete_wf(wf_id: str) -> Dict[str, Any]:
    return {"ok": state.delete_workflow(wf_id)}


# ------------------------------------------------------------------- app ----
@app.post("/api/shutdown")
def shutdown_app() -> Dict[str, Any]:
    """Let the desktop window close the backend cleanly."""
    import os
    import threading

    threading.Timer(0.3, lambda: os._exit(0)).start()
    return {"ok": True}


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

else:  # pragma: no cover

    @app.get("/")
    def index_missing() -> JSONResponse:
        return JSONResponse({"error": "web assets missing"}, status_code=500)


def serve(host: Optional[str] = None, port: Optional[int] = None) -> None:
    import uvicorn

    uvicorn.run(app, host=host or config.host, port=port or config.port, log_level="warning")
