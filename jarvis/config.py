"""Central configuration for Jarvis.

Every setting can be overridden with an environment variable or a .env file
sitting next to this repository (see .env.example).
"""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Load .env without hard-depending on python-dotenv."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ROOT / ".env")
        return
    except Exception:
        pass
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    # --- assistant identity -------------------------------------------------
    name: str = os.getenv("JARVIS_NAME", "Jarvis")
    user_title: str = os.getenv("JARVIS_USER_TITLE", "Sir")
    wake_word: str = os.getenv("JARVIS_WAKE_WORD", "jarvis").lower()

    # --- brain --------------------------------------------------------------
    # auto | openai | ollama | offline
    provider: str = os.getenv("JARVIS_PROVIDER", "auto").lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    temperature: float = float(os.getenv("JARVIS_TEMPERATURE", "0.4"))
    max_history: int = int(os.getenv("JARVIS_MAX_HISTORY", "20"))

    # --- server -------------------------------------------------------------
    host: str = os.getenv("JARVIS_HOST", "0.0.0.0")
    port: int = int(os.getenv("JARVIS_PORT", "8600"))

    # --- voice --------------------------------------------------------------
    voice_enabled: bool = _bool("JARVIS_VOICE", True)
    tts_rate: int = int(os.getenv("JARVIS_TTS_RATE", "185"))
    tts_voice_hint: str = os.getenv("JARVIS_TTS_VOICE", "david")

    # --- safety -------------------------------------------------------------
    # Destructive skills (shutdown, kill process, delete) require confirmation.
    allow_power: bool = _bool("JARVIS_ALLOW_POWER", True)
    allow_shell: bool = _bool("JARVIS_ALLOW_SHELL", False)
    workspace: Path = field(
        default_factory=lambda: Path(
            os.getenv("JARVIS_WORKSPACE", str(Path.home() / "JarvisFiles"))
        )
    )

    @property
    def is_windows(self) -> bool:
        return platform.system() == "Windows"

    @property
    def platform_name(self) -> str:
        return platform.system() or "Unknown"

    def resolved_provider(self) -> str:
        """Decide which brain to use right now."""
        if self.provider in {"openai", "ollama", "offline"}:
            return self.provider
        if self.openai_api_key:
            return "openai"
        if self.ollama_available():
            return "ollama"
        return "offline"

    def ollama_available(self) -> bool:
        try:
            import requests

            r = requests.get(f"{self.ollama_host}/api/tags", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False


config = Config()
config.workspace.mkdir(parents=True, exist_ok=True)
