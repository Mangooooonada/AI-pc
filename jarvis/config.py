"""Central configuration for Jarvis.

Every setting can be overridden with an environment variable or a .env file
sitting next to this repository (see .env.example).
"""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

if getattr(sys, "frozen", False):
    # Packaged with PyInstaller: settings live next to JARVIS.exe.
    ROOT = Path(sys.executable).resolve().parent
else:
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


def env_file_path() -> Path:
    return ROOT / ".env"


def update_env_file(updates: Dict[str, str]) -> bool:
    """Write KEY=value pairs into .env, replacing existing keys. Comment lines
    are preserved. Returns True if the file was written."""
    path = env_file_path()
    try:
        lines = (
            path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        )
    except OSError:
        lines = []
    done: set = set()
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                done.add(key)
                continue
        out.append(line)
    if len(lines) and lines[-1].strip() and updates.keys() - done:
        out.append("")  # visual gap before new keys
    for key, value in updates.items():
        if key not in done:
            out.append(f"{key}={value}")
    try:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    """Crash-proof int env: a dirty .env (e.g. '30.0' from a slider save)
    must never brick the whole app at import time."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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
    # Ollama ships models with a tiny 2k-4k context by default — far too small
    # for the system prompt + tool schemas + conversation, so the prompt would
    # be silently truncated. 12288 comfortably holds ~40 turns + packed tools
    # on any desktop 7-8B model; raise it if you have RAM to spare.
    ollama_num_ctx: int = _int("OLLAMA_NUM_CTX", 12288)
    # Keep the model loaded in RAM/VRAM between chats (snappier replies).
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    # Optional on/off for thinking-type models (e.g. qwen3): leave unset to
    # let the model decide, set OLLAMA_THINK=false to force plain answers.
    ollama_think: str = os.getenv("OLLAMA_THINK", "").strip().lower()
    # Heavy + vision sidekicks for the local brain. Blank = feature off.
    ollama_model_big: str = os.getenv("OLLAMA_MODEL_BIG", "")
    ollama_vision_model: str = os.getenv("OLLAMA_VISION_MODEL", "")
    # How many tool schemas a turn is allowed to see. Smaller packs = fewer
    # malformed tool calls out of small models + more context for chat.
    tool_pack: int = _int("JARVIS_TOOL_PACK", 20)  # skills offered per turn (LLM brains)
    temperature: float = _float("JARVIS_TEMPERATURE", 0.4)
    max_history: int = _int("JARVIS_MAX_HISTORY", 40)  # longer short-term thread

    # --- server -------------------------------------------------------------
    host: str = os.getenv("JARVIS_HOST", "0.0.0.0")
    port: int = _int("JARVIS_PORT", 8600)

    # --- voice --------------------------------------------------------------
    voice_enabled: bool = _bool("JARVIS_VOICE", True)
    tts_rate: int = _int("JARVIS_TTS_RATE", 185)
    tts_voice_hint: str = os.getenv("JARVIS_TTS_VOICE", "david")

    # --- safety -------------------------------------------------------------
    # Destructive skills (shutdown, kill process, delete) require confirmation.
    # Privacy guard: strict (local only) / guarded (redact secrets) / relaxed
    privacy_mode: str = os.getenv("JARVIS_PRIVACY", "guarded").strip().lower()
    allow_power: bool = _bool("JARVIS_ALLOW_POWER", True)
    allow_shell: bool = _bool("JARVIS_ALLOW_SHELL", False)
    # In-app updater (Settings → Updates).  Off = Jarvis never fetches or
    # installs a newer release.  The auth token for private repos is read
    # straight from JARVIS_UPDATE_TOKEN by jarvis/updater.py.
    allow_update: bool = _bool("JARVIS_ALLOW_UPDATE", True)
    # Resident-assistant behaviours.
    briefing: bool = _bool("JARVIS_BRIEFING", True)   # morning briefing on first launch of the day
    auto_mem: bool = _bool("JARVIS_AUTO_MEM", True)     # quietly save important personal facts   # morning briefing on first launch of the day
    tray: bool = _bool("JARVIS_TRAY", True)           # close → system tray instead of quitting
    observe: bool = _bool("JARVIS_OBSERVE", False)    # watch active-app history to learn habits
    observe_text: bool = _bool("JARVIS_OBSERVE_TEXT", False)  # ALSO record typed text (local-only)
    observe_shots: bool = _bool("JARVIS_OBSERVE_SHOTS", False)  # ALSO screenshot each minute
    shot_interval: int = _int("JARVIS_OBSERVE_SHOT_INTERVAL", 60)
    shot_auto_wipe: bool = _bool("JARVIS_SHOT_AUTO_WIPE", True)  # wipe frames daily + on exit
    observe_poll: int = _int("JARVIS_OBSERVE_POLL", 4)  # seconds between samples
    autolock: bool = _bool("JARVIS_AUTOLOCK", False)          # lock Windows when you walk away
    autolock_minutes: int = _int("JARVIS_AUTOLOCK_MINUTES", 10)  # idle threshold
    autolock_warn_secs: int = _int("JARVIS_AUTOLOCK_WARN", 30)   # bell warning before locking
    clipboard_watch: bool = _bool("JARVIS_CLIPBOARD_WATCH", False)  # remember what you copy
    computer_use: bool = _bool("JARVIS_COMPUTER_USE", False)  # Jarvis may drive the GUI (plan-first)
    hotkey: bool = _bool("JARVIS_HOTKEY", True)       # Ctrl+J summons the window (Windows)
    # Share the UI on the local network (phone control). Enabling binds the
    # server to 0.0.0.0 on next launch and requires net_key from other devices.
    network: bool = _bool("JARVIS_NETWORK", False)
    net_key: str = os.getenv("JARVIS_NET_KEY", "")
    # Remote-brain mode: use another running Jarvis server (a second PC, an
    # Arena sandbox session, a home server) as this Jarvis's brain over HTTP.
    remote_url: str = os.getenv("JARVIS_REMOTE_URL", "")
    remote_key: str = os.getenv("JARVIS_REMOTE_KEY", "")
    # Google scaffolding: OAuth Desktop client JSON (calendar/gmail skills).
    google_creds: str = os.getenv("JARVIS_GOOGLE_CREDENTIALS", "")
    workspace: Path = field(
        default_factory=lambda: Path(
            os.getenv("JARVIS_WORKSPACE", str(Path.home() / "JarvisFiles"))
        )
    )
    # Ask-my-documents: folder scanned by the ask_documents skill.
    docs_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("JARVIS_DOCS_DIR", str(Path(os.getenv("JARVIS_WORKSPACE", str(Path.home() / "JarvisFiles"))) / "docs"))
        )
    )

    @property
    def is_windows(self) -> bool:
        return platform.system() == "Windows"

    def credentials_path(self):
        """Locate the Google OAuth Desktop credentials.json, or None."""
        candidates = []
        if self.google_creds:
            candidates.append(Path(self.google_creds))
        repo_root = Path(__file__).resolve().parent.parent
        candidates += [repo_root / "credentials.json",
                       self.workspace / "credentials.json"]
        for c in candidates:
            try:
                if c.is_file():
                    return c
            except Exception:
                continue
        return None

    @property
    def platform_name(self) -> str:
        return platform.system() or "Unknown"

    def resolved_provider(self) -> str:
        """Decide which brain to use right now."""
        if self.provider in {"openai", "ollama", "remote", "offline"}:
            return self.provider
        if self.openai_api_key:
            return "openai"
        if self.ollama_available():
            return "ollama"
        return "offline"

    def ollama_available(self) -> bool:
        """Is the Ollama server reachable? (Does not check the model.)"""
        try:
            import requests

            r = requests.get(f"{self.ollama_host}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def ollama_models(self) -> list:
        """Names of the models installed in Ollama ([] if unreachable)."""
        try:
            import requests

            r = requests.get(f"{self.ollama_host}/api/tags", timeout=3)
            if r.status_code != 200:
                return []
            return [
                m["name"]
                for m in r.json().get("models", [])
                if isinstance(m, dict) and m.get("name")
            ]
        except Exception:
            return []


config = Config()
config.workspace.mkdir(parents=True, exist_ok=True)
config.docs_dir.mkdir(parents=True, exist_ok=True)
