"""Text to speech. Uses pyttsx3 (offline, built into Windows) when available."""
from __future__ import annotations

import queue
import threading
from typing import Optional

from ..config import config

_engine = None
_lock = threading.Lock()
_queue: "queue.Queue[Optional[str]]" = queue.Queue()
_worker: Optional[threading.Thread] = None


def _build_engine():
    global _engine
    if _engine is not None:
        return _engine
    try:
        import pyttsx3  # type: ignore

        eng = pyttsx3.init()
        eng.setProperty("rate", config.tts_rate)
        hint = (config.tts_voice_hint or "").lower()
        if hint:
            for v in eng.getProperty("voices"):
                if hint in (v.name or "").lower() or hint in (v.id or "").lower():
                    eng.setProperty("voice", v.id)
                    break
        _engine = eng
    except Exception:
        _engine = False  # mark as unavailable
    return _engine


def available() -> bool:
    return bool(_build_engine())


def speak(text: str, block: bool = True) -> None:
    """Say something out loud. Falls back to printing."""
    text = (text or "").strip()
    if not text or not config.voice_enabled:
        return
    eng = _build_engine()
    if not eng:
        print(f"[{config.name}] {text}")
        return
    if block:
        with _lock:
            try:
                eng.say(text)
                eng.runAndWait()
            except Exception:
                print(f"[{config.name}] {text}")
    else:
        _ensure_worker()
        _queue.put(text)


def _ensure_worker() -> None:
    global _worker
    if _worker and _worker.is_alive():
        return

    def loop() -> None:
        while True:
            item = _queue.get()
            if item is None:
                return
            speak(item, block=True)

    _worker = threading.Thread(target=loop, daemon=True)
    _worker.start()


def list_voices() -> list[str]:
    eng = _build_engine()
    if not eng:
        return []
    try:
        return [v.name for v in eng.getProperty("voices")]
    except Exception:
        return []
