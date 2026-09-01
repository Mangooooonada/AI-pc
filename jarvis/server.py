"""FastAPI backend serving the Jarvis HUD and the chat API."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .brain import Agent
from .config import config
from .skills import REGISTRY, run_skill

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Jarvis", docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = Agent()


class ChatIn(BaseModel):
    message: str
    provider: Optional[str] = None


class SkillIn(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


class SpeakIn(BaseModel):
    text: str


@app.get("/api/status")
def status() -> Dict[str, Any]:
    st = agent.status()
    st["voice_enabled"] = config.voice_enabled
    st["wake_word"] = config.wake_word
    st["user_title"] = config.user_title
    return st


@app.get("/api/skills")
def skills() -> Dict[str, Any]:
    return {
        "skills": [
            {
                "name": s.name,
                "description": s.description,
                "dangerous": s.dangerous,
                "triggers": s.triggers[:3],
                "parameters": list((s.parameters.get("properties") or {}).keys()),
            }
            for s in sorted(REGISTRY.values(), key=lambda s: s.name)
        ]
    }


@app.post("/api/chat")
def chat(body: ChatIn) -> Dict[str, Any]:
    if body.provider and body.provider != agent.provider_name:
        agent.reload_provider(body.provider)
    turn = agent.ask(body.message)
    return {
        "reply": turn.reply,
        "actions": turn.actions,
        "provider": turn.provider,
        "error": turn.error,
    }


@app.post("/api/skill")
def run_one(body: SkillIn) -> Dict[str, Any]:
    return {"result": run_skill(body.name, body.arguments)}


@app.post("/api/speak")
def speak(body: SpeakIn) -> Dict[str, Any]:
    """Speak through the PC's own speakers (server-side TTS)."""
    try:
        from .voice.tts import available, speak as say

        if not available():
            return {"ok": False, "error": "pyttsx3 not installed on the host"}
        say(body.text, block=False)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/reset")
def reset() -> Dict[str, Any]:
    agent.reset()
    return {"ok": True}


@app.post("/api/provider/{name}")
def set_provider(name: str) -> Dict[str, Any]:
    return agent.reload_provider(name)


@app.get("/api/system")
def system_metrics() -> Dict[str, Any]:
    """Live gauges for the HUD."""
    data: Dict[str, Any] = {"cpu": None, "memory": None, "disk": None, "battery": None}
    try:
        import psutil  # type: ignore

        data["cpu"] = psutil.cpu_percent(interval=None)
        data["memory"] = psutil.virtual_memory().percent
        import os

        data["disk"] = psutil.disk_usage(os.path.abspath(os.sep)).percent
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat:
            data["battery"] = {"percent": bat.percent, "plugged": bat.power_plugged}
    except Exception:
        pass
    return data


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

    uvicorn.run(
        app,
        host=host or config.host,
        port=port or config.port,
        log_level="warning",
    )
