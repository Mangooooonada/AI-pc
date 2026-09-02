"""Crash forensics: faulthandler -> <workspace>/jarvis-crash.log.

Python try/except can't see native crashes (SAPI audio, mic drivers,
WebView2). faulthandler can: a segfault dumps every thread's stack to this
file, so 'the app just vanished' becomes a readable log. Enable at every
entry point; zero cost until something actually crashes.
"""
from __future__ import annotations

import faulthandler
import os


def enable() -> str:
    try:
        from .config import config
        log_dir = config.workspace
    except Exception:
        log_dir = os.getcwd()  # type: ignore[assignment]
    path = os.path.join(str(log_dir), "jarvis-crash.log")
    try:
        fh = open(path, "a", encoding="utf-8", buffering=1)
        fh.write(f"\n--- session started ---\n")
        faulthandler.enable(file=fh)
    except Exception:
        faulthandler.enable()  # stderr fallback
    return path


def last_crash(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except Exception:
        return ""
    # the interesting part is after the final session marker
    tail = text.rsplit("--- session started ---", 1)
    return (tail[-1] if len(tail) > 1 else "").strip()[-4000:]
