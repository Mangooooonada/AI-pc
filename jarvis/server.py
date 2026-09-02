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

from fastapi import FastAPI, Request
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
@app.middleware("http")
async def _network_guard(request: Request, call_next):
    """When network sharing is on, non-local devices need the pairing key.

    Pages stay public; every /api/* call from a non-loopback client must
    carry the key (?key=… from the QR link, then the UI sends X-Jarvis-Key).
    """
    if config.network and config.net_key and request.url.path.startswith("/api"):
        client = request.client.host if request.client else ""
        if client not in {"127.0.0.1", "::1", "localhost"}:
            key = request.query_params.get("key") or request.headers.get("x-jarvis-key")
            if key != config.net_key:
                return JSONResponse(
                    {"ok": False, "error": "locked — open the QR-code link from Settings on that device"},
                    status_code=403,
                )
    return await call_next(request)


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
            # Proactive nudges (timers firing, reminders coming due) drain
            # through here — the UI shows and speaks them.
            "alerts": state.drain_notifications(),
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
        {"key": "JARVIS_TTS_RATE", "attr": "tts_rate", "label": "Speech rate", "kind": "range", "min": 120, "max": 260, "step": 1, "unit": " wpm", "as_int": True},
        {"key": "JARVIS_TTS_VOICE", "attr": "tts_voice_hint", "label": "Voice match (e.g. david, zira)", "kind": "text"},
    ]},
    {"section": "Brain", "blurb": "Tuning for the local model. Applies immediately.", "fields": [
        {"key": "JARVIS_TEMPERATURE", "attr": "temperature", "label": "Creativity (temperature)", "kind": "range", "min": 0, "max": 1.5, "step": 0.05},
        {"key": "JARVIS_MAX_HISTORY", "attr": "max_history", "label": "Conversation memory depth", "kind": "range", "min": 4, "max": 60, "step": 2, "as_int": True},
        {"key": "OLLAMA_MODEL", "attr": "ollama_model", "label": "Ollama model", "kind": "text", "placeholder": "blank = auto-pick"},
        {"key": "OLLAMA_MODEL_BIG", "attr": "ollama_model_big", "label": "Heavy brain for hard questions", "kind": "text", "placeholder": "e.g. qwen3:32b (blank = off)"},
        {"key": "OLLAMA_VISION_MODEL", "attr": "ollama_vision_model", "label": "Vision model (screen eyes)", "kind": "text", "placeholder": "blank = auto-detect llava/qwen3-vl"},
        {"key": "OLLAMA_NUM_CTX", "attr": "ollama_num_ctx", "label": "Ollama context size", "kind": "number", "min": 2048, "max": 131072, "step": 1024},
        {"key": "OLLAMA_KEEP_ALIVE", "attr": "ollama_keep_alive", "label": "Keep model loaded", "kind": "text", "placeholder": "30m  (-1 = forever)"},
        {"key": "JARVIS_TOOL_PACK", "attr": "tool_pack", "label": "Skills offered per message", "kind": "number", "min": 6, "max": 60, "step": 1},
        {"key": "JARVIS_PROVIDER", "attr": "provider", "label": "Brain provider (auto / ollama / openai / offline)", "kind": "text", "placeholder": "auto"},
        {"key": "OPENAI_BASE_URL", "attr": "openai_base_url", "label": "Cloud brain URL (OpenAI-compatible)", "kind": "text", "placeholder": "https://api.groq.com/openai/v1"},
        {"key": "OPENAI_MODEL", "attr": "openai_model", "label": "Cloud brain model", "kind": "text", "placeholder": "llama-3.3-70b-versatile"},
        {"key": "OPENAI_API_KEY", "attr": "openai_api_key", "label": "Cloud brain API key", "kind": "text", "placeholder": "gsk_… or sk-…"},
        {"key": "JARVIS_REMOTE_URL", "attr": "remote_url", "label": "Remote Jarvis brain URL", "kind": "text", "placeholder": "https://… (another Jarvis server)"},
        {"key": "JARVIS_REMOTE_KEY", "attr": "remote_key", "label": "Remote brain pairing key", "kind": "text", "placeholder": "from that machine's network sharing settings"},
    ]},
    {"section": "Resident Assistant", "blurb": "Always-on behaviours. Autostart, always-listen and spoken-reply toggles are in the App card above.", "fields": [
        {"key": "JARVIS_TRAY", "attr": "tray", "label": "Close button tucks Jarvis into the system tray", "kind": "bool"},
        {"key": "JARVIS_OBSERVE", "attr": "observe", "label": "Observer: quietly learn my app-usage habits (never keystrokes)", "kind": "bool"},
        {"key": "JARVIS_COMPUTER_USE", "attr": "computer_use", "label": "Computer use: Jarvis may drive mouse/keyboard (plan-approved, stoppable)", "kind": "bool"},
        {"key": "JARVIS_AUTO_MEM", "attr": "auto_mem", "label": "Auto-remember important facts you mention", "kind": "bool"},
        {"key": "JARVIS_BRIEFING", "attr": "briefing", "label": "Morning briefing on first launch of the day", "kind": "bool"},
        {"key": "JARVIS_HOTKEY", "attr": "hotkey", "label": "Ctrl+J summons Jarvis from anywhere (Windows)", "kind": "bool"},
    ]},
    {"section": "Safety", "blurb": "What Jarvis is allowed to do — and what may leave this PC. Privacy: strict = local models only · guarded = secrets redacted before any cloud call · relaxed = no redaction. Every external call is written to the audit ledger (Settings → note, GET /api/audit).", "fields": [
        {"key": "JARVIS_PRIVACY", "attr": "privacy_mode", "label": "Privacy mode", "kind": "text", "placeholder": "strict | guarded | relaxed", "danger": True},
        {"key": "JARVIS_ALLOW_POWER", "attr": "allow_power", "label": "Allow power commands (shutdown / restart / sleep)", "kind": "bool", "danger": True},
        {"key": "JARVIS_ALLOW_SHELL", "attr": "allow_shell", "label": "Allow raw shell commands — dangerous", "kind": "bool", "danger": True},
    ]},
]

_FIELD_BY_KEY = {f["key"]: f for s in SETTINGS_FIELDS for f in s["fields"]}


# ---------------------------------------------------- morning briefing ---
def _build_briefing() -> Dict[str, str]:
    """Compose the morning briefing from the executive_briefing skill plus a
    one-breath spoken line. Every section is individually fault-tolerant."""
    from . import state as _st

    now = datetime.now()
    daypart = "morning" if now.hour < 12 else ("afternoon" if now.hour < 18 else "evening")
    spoken = f"Good {daypart}, {config.user_title}."
    try:
        text = run_skill("executive_briefing", {})
    except Exception as exc:  # briefing must never block boot
        text = f"(briefing degraded: {exc})"
    try:
        open_tasks = [t for t in _st.list_tasks() if not t["done"]]
        overdue = _st.overdue_tasks()
        if overdue:
            spoken += f" {len(overdue)} reminder{'s are' if len(overdue) > 1 else ' is'} overdue."
        elif open_tasks:
            spoken += f" You have {len(open_tasks)} open task{'s' if len(open_tasks) > 1 else ''}."
        else:
            spoken += " Your plate is clean."
    except Exception:
        pass
    return {"text": f"Good {daypart}, {config.user_title}.\n\n{text}", "spoken": spoken}


@app.get("/api/briefing")
def get_briefing(fresh: int = 0) -> Dict[str, Any]:
    """First call of the day returns pending=true so the UI shows + speaks it.

    ?fresh=1 forces a rebuild without consuming the daily flag (chat command).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    due = datetime.now().hour >= 5  # don't brief at 3 a.m.
    if fresh:
        return {"pending": True, **_build_briefing()}
    if not config.briefing or not due or state.get_flag("briefing_day") == today:
        return {"pending": False}
    state.set_flag("briefing_day", today)
    return {"pending": True, **_build_briefing()}


# ---------------------------------------------------------- autostart ------
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "JarvisAI"


def _autostart_cmd() -> str:
    bat = Path(__file__).resolve().parent.parent / "JARVIS.bat"
    return f'"{bat}" --minimized'


def _autostart_enabled() -> Optional[bool]:
    if platform.system() != "Windows":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _AUTOSTART_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


@app.get("/api/autostart")
def get_autostart() -> Dict[str, Any]:
    enabled = _autostart_enabled()
    return {
        "supported": enabled is not None,
        "enabled": bool(enabled),
        "command": _autostart_cmd(),
        "note": "" if enabled is not None else "Windows-only for now.",
    }


class AutostartIn(BaseModel):
    enabled: bool


@app.post("/api/autostart")
def set_autostart(body: AutostartIn) -> Dict[str, Any]:
    if platform.system() != "Windows":
        return {"ok": False, "error": "Autostart is Windows-only right now."}
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            if body.enabled:
                winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_cmd())
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return {"ok": True, "enabled": body.enabled}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------- phone / LAN mode ----
def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 80))  # no traffic is actually sent
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return socket.gethostname()


def _network_info(request=None) -> Dict[str, Any]:
    port = config.port
    if request is not None:
        try:
            port = int(str(request.url.port or request.headers.get("host", "").split(":")[-1]))
        except (TypeError, ValueError):
            pass
    url = ""
    if config.network:
        url = f"http://{_lan_ip()}:{port}" + (f"?key={config.net_key}" if config.net_key else "")
    qr = None
    if url:
        try:
            import base64
            import io

            import qrcode  # type: ignore

            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            qr = None
    return {
        "enabled": config.network,
        "locked": bool(config.net_key),
        "url": url,
        "qr": qr,
    }


@app.get("/api/network")
def get_network(request: Request) -> Dict[str, Any]:
    return _network_info(request)


class NetworkIn(BaseModel):
    enabled: bool


@app.post("/api/network")
def set_network(body: NetworkIn, request: Request) -> Dict[str, Any]:
    if body.enabled and not config.net_key:
        import secrets

        config.net_key = secrets.token_urlsafe(9)
        update_env_file({"JARVIS_NET_KEY": config.net_key})
    config.network = bool(body.enabled)
    update_env_file({"JARVIS_NETWORK": "1" if config.network else "0"})
    info = _network_info(request)
    info["ok"] = True
    info["note"] = (
        "Network sharing is ON. Fully live on next launch — reopen Jarvis, then "
        "point your phone (same Wi-Fi) at the URL or QR below."
        if config.network
        else "Network sharing off. Jarvis binds back to this PC only on next launch."
    )
    return info


# ------------------------------------------------ proactive nudge loop ----
_watcher_started = False


def _routine_worker(r: Dict[str, Any]) -> None:
    """Run one routine through the real agent loop, then report back.

    Takes the agent busy-lock WITHOUT waiting — if the user is mid-chat the
    routine just defers to the next watcher tick ('it waits for you')."""
    ag = get_agent()
    if not ag._busy.acquire(blocking=False):
        return
    try:
        turn = ag._ask_unlocked(r["prompt"])
        summary = " ".join((turn.reply or "").split())[:240] or "(no response)"
        state.record_routine_run(r["id"], not turn.error, summary)
        label = "Routine" if not turn.error else "Routine (with warnings)"
        state.add_notification(f"🕐 {label} '{r['name']}': {summary}")
    except Exception as exc:
        state.record_routine_run(r["id"], False, f"{type(exc).__name__}: {exc}")
        state.add_notification(f"🕐 Routine '{r['name']}' failed: {exc}")
    finally:
        ag._busy.release()


def _nudge_watcher() -> None:
    """Scan for due reminders/timers AND fire due routines.

    Tasks already past their 'due' time that were never announced get one
    notification each; timers enqueue their own from the skill that fires
    them; routines run through the full agent loop and report back via
    notifications. Runs forever as a daemon — silent on any error.
    """
    import time as _time

    from .routines import due as _routine_due

    while True:
        _time.sleep(20)
        try:
            now = datetime.now()
            for t in state.list_tasks(include_done=False):
                due = t.get("due")
                if not due or t.get("notified"):
                    continue
                try:
                    due_dt = datetime.fromisoformat(due)
                except (TypeError, ValueError):
                    continue
                if due_dt <= now:
                    state.add_notification(f"Reminder: {t['title']}")
                    state.mark_task_notified(t["id"])
            for r in state.list_routines():
                if _routine_due(r, now):
                    threading.Thread(target=_routine_worker, args=(r,), daemon=True).start()
        except Exception:
            pass


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
    for key, raw in (body.updates or {}).items():
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
                if f.get("as_int"):
                    value = int(round(value))  # whole-number sliders stay whole in .env
            else:
                value = str(raw).strip()
        except (TypeError, ValueError):
            return {"ok": False, "error": f"bad value for {key}"}
        if f["key"] == "JARVIS_PRIVACY" and str(value).lower() not in {"strict", "guarded", "relaxed"}:
            return {"ok": False, "error": "privacy mode must be strict, guarded or relaxed"}
        if f["key"] == "JARVIS_PROVIDER" and str(value).lower() not in {"auto", "ollama", "openai", "remote", "offline"}:
            return {"ok": False, "error": "provider must be auto, ollama, openai, remote or offline"}
        setattr(config, f["attr"], value)
        applied[key] = str(value).lower() if isinstance(value, bool) else str(value)

    env_ok = update_env_file(applied)

    notes: List[str] = []
    if set(applied) & {"OLLAMA_MODEL", "JARVIS_PROVIDER",
                       "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"}:
        try:
            st = get_agent().reload_provider(None)
            notes.append(f"brain re-initialized: {st['provider']} ({st['model']})")
            notes.extend(n for n in st.get("notes", []) if n)
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


@app.get("/api/audit")
def get_audit(limit: int = 100, kind: str = "") -> Dict[str, Any]:
    return {"entries": state.list_audit(limit=limit, kind=kind)}


@app.delete("/api/conversations")
def clear_conversations() -> Dict[str, Any]:
    state.clear_conversations()
    get_agent().reset()
    return {"ok": True}


# ------------------------------------------------------------- routines ----
class RoutineIn(BaseModel):
    name: str = ""
    schedule_text: str = ""
    prompt: str


@app.get("/api/routines")
def get_routines() -> Dict[str, Any]:
    from .routines import human

    return {
        "routines": [
            {**r, "schedule_human": human(r.get("schedule", {}))}
            for r in state.list_routines()
        ]
    }


@app.post("/api/routines")
def make_routine(body: RoutineIn) -> Dict[str, Any]:
    from .routines import human, parse_schedule

    prompt = (body.prompt or "").strip()
    if not prompt:
        return {"ok": False, "error": "A routine needs steps — what should Jarvis do?"}
    sched = parse_schedule(body.schedule_text)
    if not sched:
        return {
            "ok": False,
            "error": "Couldn't read the schedule — try 'every morning', 'every day at 5pm', "
                     "'every 2 hours', 'every monday at 9am' or 'in 30 minutes'.",
        }
    routine = state.add_routine(body.name or "Routine", prompt, sched)
    return {
        "ok": True,
        "routine": routine,
        "note": f"Saved — fires {human(sched)}. It'll defer politely while you're chatting.",
    }


@app.delete("/api/routines/{routine_id}")
def drop_routine(routine_id: str) -> Dict[str, Any]:
    return {"ok": state.delete_routine(routine_id)}


@app.post("/api/routines/{routine_id}/run")
def run_routine_now(routine_id: str) -> Dict[str, Any]:
    r = state.get_routine(routine_id)
    if not r:
        return {"ok": False, "error": f"No routine '{routine_id}'."}
    threading.Thread(target=_routine_worker, args=(r,), daemon=True).start()
    return {"ok": True, "note": f"'{r['name']}' is running — it'll report back when done."}


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

    # PWA files must answer at the ROOT: a service worker under /static would
    # only control /static/* (scope = its directory), and manifests/icons are
    # fetched root-relative by install prompts.
    @app.get("/sw.js", include_in_schema=False)
    def _sw() -> FileResponse:
        return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/",
                                     "Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def _manifest() -> FileResponse:
        return FileResponse(WEB_DIR / "manifest.webmanifest",
                            media_type="application/manifest+json")

    @app.get("/icon-192.png", include_in_schema=False)
    def _icon192() -> FileResponse:
        return FileResponse(WEB_DIR / "icon-192.png", media_type="image/png")

    @app.get("/icon-512.png", include_in_schema=False)
    def _icon512() -> FileResponse:
        return FileResponse(WEB_DIR / "icon-512.png", media_type="image/png")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

else:  # pragma: no cover

    @app.get("/")
    def index_missing() -> JSONResponse:
        return JSONResponse({"error": "web assets missing"}, status_code=500)


def serve(host: Optional[str] = None, port: Optional[int] = None) -> None:
    import uvicorn

    global _watcher_started
    if not _watcher_started:
        _watcher_started = True
        threading.Thread(target=_nudge_watcher, daemon=True, name="nudge-watcher").start()
        from .observe import watch_loop
        threading.Thread(target=watch_loop, daemon=True, name="observer").start()

    # Default to loopback-only; LAN binding is an explicit Settings choice
    # (network sharing) or an explicit JARVIS_HOST in .env.
    import os

    explicit_host = bool((os.environ.get("JARVIS_HOST") or "").strip())
    bind = host or (
        config.host if explicit_host else ("0.0.0.0" if config.network else "127.0.0.1")
    )
    uvicorn.run(app, host=bind, port=port or config.port, log_level="warning")
