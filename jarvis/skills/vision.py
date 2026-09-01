"""Eyes and clipboard: see the screen, read/write the clipboard."""
from __future__ import annotations

import base64
import io
import subprocess

from . import skill
from ..config import config

_VISION_PREFS = (
    "qwen3-vl", "llava", "qwen2.5vl", "qwen2.5-vl", "moondream",
    "minicpm-v", "gemma3", "llama3.2-vision",
)


def _vision_model() -> str:
    """Configured vision model, else the best vision-capable one installed."""
    want = (config.ollama_vision_model or "").strip()
    installed = config.ollama_models()
    if want:
        if any(m == want or m.split(":")[0] == want or m == f"{want}:latest" for m in installed):
            return want
        return ""  # configured but not pulled — caller explains
    for pref in _VISION_PREFS:
        for m in installed:
            if m == pref or m.startswith(pref + ":") or m.startswith(pref + "-"):
                return m
    return ""


def _grab_screen_b64() -> str:
    from PIL import ImageGrab  # type: ignore

    buf = io.BytesIO()
    ImageGrab.grab().save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@skill(
    "describe_screen",
    "Look at the user's screen right now and describe or answer questions about it. "
    "Needs a vision model installed in Ollama (e.g. llava, qwen3-vl, moondream).",
    {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "What to look for / answer about the screen"}
        },
    },
    triggers=[
        "what is on my screen", "describe my screen", "look at my screen",
        "read my screen", "what am i looking at",
    ],
)
def describe_screen(question: str = "") -> str:
    if not config.ollama_available():
        return "Ollama isn't running, so I have no eyes right now. Start it and ask again."
    model = _vision_model()
    if not model:
        return (
            "I don't have a vision model installed. Run `ollama pull llava` (or qwen3-vl), "
            "or set OLLAMA_VISION_MODEL in Settings, and I'll be able to see."
        )
    try:
        image = _grab_screen_b64()
    except Exception as exc:
        return f"Couldn't capture the screen: {exc}"
    prompt = (question or "").strip() or (
        "Describe what's on this screen in two short sentences — apps, content, anything odd."
    )
    try:
        import requests

        r = requests.post(
            f"{config.ollama_host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt, "images": [image]}],
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=180,
        )
        if r.status_code >= 400:
            return f"Vision model rejected the frame ({r.status_code}): {r.text[:160]}"
        return (r.json().get("message", {}).get("content") or "(saw nothing)").strip()
    except Exception as exc:
        return f"Vision failed: {exc}"


def _clip_read() -> str:
    import sys

    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        if not u32.OpenClipboard(None):
            return ""
        try:
            handle = u32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            k32.GlobalLock.restype = ctypes.c_wchar_p
            ptr = k32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(ptr) if ptr else ""
            finally:
                k32.GlobalUnlock(handle)
        finally:
            u32.CloseClipboard()
    for cmd in (["pbpaste"], ["xclip", "-o", "-selection", "clipboard"], ["wl-paste"]):
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=2)
            if out.returncode == 0:
                return out.stdout.decode("utf-8", "replace")
        except FileNotFoundError:
            continue
        except Exception:
            continue
    try:
        import pyperclip  # type: ignore

        return pyperclip.paste() or ""
    except Exception:
        return ""


def _clip_write(text: str) -> bool:
    import sys

    if sys.platform.startswith("win"):
        import ctypes
        from ctypes import wintypes

        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
        if not u32.OpenClipboard(None):
            return False
        try:
            u32.EmptyClipboard()
            data = (text + "\0").encode("utf-16-le")
            handle = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            k32.GlobalLock.restype = ctypes.c_void_p
            ptr = k32.GlobalLock(handle)
            ctypes.memmove(ptr, data, len(data))
            k32.GlobalUnlock(handle)
            if not u32.SetClipboardData(CF_UNICODETEXT, handle):
                k32.GlobalFree(handle)
                return False
            return True
        finally:
            u32.CloseClipboard()
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True
    except Exception:
        pass
    for cmd in (["xclip", "-selection", "clipboard"], ["wl-copy"], ["pbcopy"]):
        try:
            p = subprocess.run(cmd, input=text.encode(), timeout=2)
            if p.returncode == 0:
                return True
        except Exception:
            continue
    return False


@skill(
    "read_clipboard",
    "Read the current clipboard text so you can summarize, explain, translate or rewrite it.",
    {"type": "object", "properties": {}},
    triggers=[
        "what is on my clipboard", "read my clipboard", "show my clipboard",
        "what did i copy", "summarize my clipboard", "explain my clipboard",
        "rewrite my clipboard", "translate my clipboard",
    ],
)
def read_clipboard() -> str:
    text = _clip_read()
    if not text.strip():
        return "The clipboard is empty (or holds an image/file, which I can't read as text)."
    if len(text) > 4000:
        text = text[:4000] + "\n… (truncated — clipboard is longer)"
    return "Clipboard contents:\n" + text


@skill(
    "copy_to_clipboard",
    "Put text onto the user's clipboard, ready to paste somewhere else.",
    {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to copy"}},
        "required": ["text"],
    },
    triggers=["copy {text} to my clipboard", "put {text} on my clipboard"],
)
def copy_to_clipboard(text: str) -> str:
    if not (text or "").strip():
        return "Copy what?"
    if _clip_write(text):
        return f"On your clipboard: {text[:80]}{'…' if len(text) > 80 else ''}"
    return "Couldn't reach the clipboard on this system."
