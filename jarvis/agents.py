"""Subsystem ("agent") status and the live intelligence feed.

Every card in the command center maps onto something real: an actual capability
check, an actual counter, or an actual condition on the machine.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from typing import Any, Dict, List

from . import state
from .config import config
from .skills import REGISTRY


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


def llm_providers() -> List[Dict[str, Any]]:
    """Which brains are actually reachable right now."""
    out: List[Dict[str, Any]] = []

    key = config.openai_api_key
    base = config.openai_base_url
    branded = "OpenAI"
    if "groq" in base:
        branded = "Groq"
    elif "openrouter" in base:
        branded = "OpenRouter"
    elif "together" in base:
        branded = "Together"
    elif "deepseek" in base:
        branded = "DeepSeek"
    elif "localhost" in base or "127.0.0.1" in base:
        branded = "Local server"

    out.append(
        {
            "name": branded,
            "connected": bool(key),
            "detail": config.openai_model if key else "No API key",
            "hint": "Add OPENAI_API_KEY to .env",
        }
    )

    ollama_up = config.ollama_available()
    models = ""
    if ollama_up:
        try:
            import requests

            tags = requests.get(f"{config.ollama_host}/api/tags", timeout=1.5).json()
            names = [m["name"] for m in tags.get("models", [])]
            models = f"{len(names)} model(s)" if names else "No models"
            ollama_up = bool(names)
        except Exception:
            models = "reachable"
    out.append(
        {
            "name": "Ollama",
            "connected": ollama_up,
            "detail": models or "Not running",
            "hint": "Install ollama.com then: ollama pull llama3.2",
        }
    )

    out.append(
        {
            "name": "Offline engine",
            "connected": True,
            "detail": f"{len(REGISTRY)} keyword intents",
            "hint": "Always available, no key required",
        }
    )

    for extra, present, detail in (
        ("Whisper STT", _has("whisper"), "Local transcription"),
        ("Web Speech", True, "Browser voice I/O"),
    ):
        out.append(
            {
                "name": extra,
                "connected": bool(present),
                "detail": detail if present else "Not installed",
                "hint": "pip install openai-whisper",
            }
        )
    return out


def agents(provider_name: str = "offline") -> List[Dict[str, Any]]:
    """Subsystems, presented as agents."""
    tts_ok = _has("pyttsx3")
    stt_ok = _has("speech_recognition")
    psutil_ok = _has("psutil")
    net_ok = _has("requests")

    brain_active = provider_name in {"openai", "ollama"}
    mem_count = len(state.list_memories(limit=100000))
    task_count = len([t for t in state.list_tasks() if not t["done"]])

    def mk(key, name, icon, ok, detail, active=False):
        return {
            "id": key,
            "name": name,
            "icon": icon,
            "status": "active" if active and ok else ("standby" if ok else "offline"),
            "detail": detail,
        }

    return [
        mk("core", "Reasoning Agent", "core", True,
           f"{provider_name} brain", brain_active),
        mk("system", "System Agent", "system", psutil_ok,
           "Telemetry & control" if psutil_ok else "pip install psutil", psutil_ok),
        mk("voice", "Voice Agent", "voice", tts_ok or stt_ok,
           ("Speech ready" if tts_ok and stt_ok else "Output only" if tts_ok else
            "Input only" if stt_ok else "pip install pyttsx3"), tts_ok),
        mk("memory", "Memory Agent", "memory", True,
           f"{mem_count} stored", mem_count > 0),
        mk("task", "Task Agent", "task", True,
           f"{task_count} open", task_count > 0),
        mk("research", "Research Agent", "research", net_ok,
           "Web, weather, news" if net_ok else "No network stack", net_ok),
    ]


def core_overview(provider_name: str, model: str) -> List[Dict[str, Any]]:
    mem_count = len(state.list_memories(limit=100000))
    st = state.stats()
    llms = llm_providers()
    connected = sum(1 for p in llms if p["connected"])
    running = sum(1 for a in agents(provider_name) if a["status"] == "active")
    voice_ok = _has("pyttsx3") or _has("speech_recognition")
    return [
        {"key": "core", "label": "AI Core", "value": model, "state": "ok"},
        {"key": "memory", "label": "Memory", "value": f"{mem_count} stored", "state": "ok"},
        {"key": "voice", "label": "Voice",
         "value": "Online" if voice_ok else "Browser only",
         "state": "ok" if voice_ok else "warn"},
        {"key": "agents", "label": "Agents", "value": f"{running} running", "state": "ok"},
        {"key": "llms", "label": "LLMs", "value": f"{connected} connected",
         "state": "ok" if connected > 1 else "warn"},
        {"key": "system", "label": "System",
         "value": "Optimal" if _has("psutil") else "Limited",
         "state": "ok" if _has("psutil") else "warn"},
        {"key": "skills", "label": "Skills", "value": f"{len(REGISTRY)} loaded", "state": "ok"},
        {"key": "turns", "label": "Session", "value": f"{st.get('session_turns', 0)} turns",
         "state": "ok"},
    ]


def intelligence_feed(provider_name: str = "offline") -> List[Dict[str, Any]]:
    """Real, actionable notices generated from live machine + user state."""
    feed: List[Dict[str, Any]] = []
    now = datetime.now()

    overdue = state.overdue_tasks()
    if overdue:
        titles = ", ".join(f'"{t["title"]}"' for t in overdue[:2])
        feed.append({
            "kind": "warn", "tag": "Overdue", "icon": "alert",
            "title": f"{len(overdue)} task(s) overdue — {titles}",
            "action": {"label": "View Tasks", "view": "tasks"},
        })

    tl = state.timeline()
    soon = [i for i in tl if i["state"] in {"now", "upcoming"}][:1]
    for item in soon:
        feed.append({
            "kind": "info", "tag": "Schedule", "icon": "calendar",
            "title": f'{item["title"]} — {item["relative"].lower()}',
            "action": {"label": "Timeline", "view": "calendar"},
        })

    try:
        import psutil  # type: ignore

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        if cpu > 85:
            feed.append({"kind": "warn", "tag": "Load", "icon": "cpu",
                         "title": f"CPU at {cpu:.0f}% — something is working hard",
                         "action": {"label": "Inspect", "cmd": "list processes by cpu"}})
        elif mem > 85:
            feed.append({"kind": "warn", "tag": "Memory", "icon": "cpu",
                         "title": f"Memory at {mem:.0f}% — consider closing apps",
                         "action": {"label": "Inspect", "cmd": "list processes by memory"}})
        else:
            feed.append({"kind": "live", "tag": "System load nominal", "icon": "cpu",
                         "title": f"CPU {cpu:.0f}% · memory {mem:.0f}% · all clear"})

        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat and not bat.power_plugged and bat.percent < 25:
            feed.append({"kind": "warn", "tag": "Power", "icon": "alert",
                         "title": f"Battery at {bat.percent:.0f}% and unplugged"})

        try:
            import os

            disk = psutil.disk_usage(os.path.abspath(os.sep))
            if disk.percent > 90:
                feed.append({"kind": "warn", "tag": "Storage", "icon": "disk",
                             "title": f"System drive {disk.percent:.0f}% full",
                             "action": {"label": "Clean up", "cmd": "clean my downloads"}})
        except Exception:
            pass
    except Exception:
        feed.append({"kind": "tip", "tag": "Setup", "icon": "tip",
                     "title": "Install psutil for full telemetry: pip install psutil"})

    if provider_name == "offline":
        feed.append({
            "kind": "tip", "tag": "Brain", "icon": "tip",
            "title": "Running keyword-only. Install Ollama for real conversation.",
            "action": {"label": "How", "view": "aicore"},
        })

    if 14 <= now.hour < 16:
        feed.append({"kind": "tip", "tag": "Focus", "icon": "tip",
                     "title": "Your deep-work block is 2–4 PM. Focus Mode is one click away.",
                     "action": {"label": "Focus", "cmd": "run workflow Focus Mode"}})

    mems = state.list_memories(limit=1)
    if mems:
        feed.append({"kind": "info", "tag": "Memory", "icon": "memory",
                     "title": f"Latest memory: {mems[0]['text'][:70]}",
                     "action": {"label": "Memory", "view": "memory"}})

    convo = state.list_conversations(limit=1)
    if convo:
        feed.append({"kind": "info", "tag": "Conversation", "icon": "chat",
                     "title": f'Last exchange: "{convo[0]["user"][:60]}"',
                     "action": {"label": "History", "view": "conversations"}})

    if not shutil.which("ollama") and provider_name != "openai":
        feed.append({"kind": "tip", "tag": "Github", "icon": "tip",
                     "title": "Tip: ask “what can you do” to see all skills."})

    return feed[:8]
