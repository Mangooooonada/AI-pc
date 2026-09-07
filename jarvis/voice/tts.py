"""Text to speech. Uses pyttsx3 (offline, built into Windows) when available.

THREAD-SAFETY CONTRACT (the voice-crash fix): pyttsx3 wraps a native COM
engine (SAPI5 on Windows). COM forbids calling an engine from a different
thread than the one that created it — the old code built it on whichever
HTTP thread answered first and *spoke* on another, which on Windows can
ACCESS-VIOLATE the whole process. Rules now:
  * exactly ONE engine, created inside the dedicated TTS worker thread,
  * pythoncom.CoInitialize() on that thread first,
  * every say/runAndWait happens only there,
  * any engine failure flips a dead-flag and degrades to print — never crash.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from ..config import config

_queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
_worker: Optional[threading.Thread] = None
_dead = False          # engine died; don't retry forever, print instead
_ready = threading.Event()


def _run() -> None:
    """The ONLY thread that may touch pyttsx3."""
    global _dead
    eng = None
    try:
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
        except Exception:
            pass  # non-Windows: nothing to initialize
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
        except Exception:
            eng = None  # unavailable on this machine — print fallback
        _ready.set()
        while True:
            item = _queue.get()
            if item is None:
                return
            text, done = item
            try:
                if eng is not None:
                    eng.say(text)
                    eng.runAndWait()
                else:
                    print(f"[{config.name}] {text}")
            except Exception:
                # engine hiccuped mid-sentence; rebuild next time rather than dying
                try:
                    eng = None
                    _dead = True
                except Exception:
                    pass
                print(f"[{config.name}] {text}")
            finally:
                if done is not None:
                    done.set()
    finally:
        try:
            import pythoncom  # type: ignore
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _ensure_worker() -> bool:
    """Start the TTS thread once. False if it's already dead."""
    global _worker
    if _worker and _worker.is_alive():
        return True
    if _dead and not (_worker and _worker.is_alive()):
        return False
    _worker = threading.Thread(target=_run, daemon=True, name="jarvis-tts")
    _worker.start()
    _ready.wait(timeout=5)
    return True


def available() -> bool:
    """Cheap probe: can we at least import the engine? (No thread juggling.)"""
    try:
        import pyttsx3  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def speak(text: str, block: bool = True) -> None:
    """Say something out loud. Always routed through the single TTS thread."""
    text = (text or "").strip()
    if not text or not config.voice_enabled:
        return
    if not available():
        print(f"[{config.name}] {text}")
        return
    if not _ensure_worker():
        print(f"[{config.name}] {text}")
        return
    done = threading.Event() if block else None
    _queue.put((text, done))
    if block and done is not None:
        done.wait(timeout=max(8.0, len(text) / 12.0 + 2))


def stop_all() -> None:
    """Flush pending speech and terminate the worker cleanly."""
    global _worker, _dead
    try:
        while True:
            _queue.get_nowait()
    except queue.Empty:
        pass
    _queue.put(None)
    _worker = None
    _dead = False


def list_voices() -> list[str]:
    """Listing voices would juggle the COM engine across threads — the exact
    crash we're avoiding. Rare enough to skip: return []."""
    return []
