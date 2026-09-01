"""Media playback control via virtual media keys."""
from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus

from . import skill
from ._platform import IS_WINDOWS, send_keys, unsupported

_MEDIA_KEYS = {
    "playpause": ("playpause", "{MEDIA_PLAY_PAUSE}"),
    "next": ("nexttrack", "{MEDIA_NEXT_TRACK}"),
    "previous": ("prevtrack", "{MEDIA_PREV_TRACK}"),
    "stop": ("stop", "{MEDIA_STOP}"),
    "volumeup": ("volumeup", "{VOLUME_UP}"),
    "volumedown": ("volumedown", "{VOLUME_DOWN}"),
}


def _press(action: str) -> str:
    pyautogui_key, sendkeys = _MEDIA_KEYS[action]
    try:
        import pyautogui  # type: ignore

        pyautogui.press(pyautogui_key)
        return "ok"
    except Exception:
        pass
    if IS_WINDOWS:
        from ._platform import powershell

        powershell(
            "$w = New-Object -ComObject WScript.Shell; "
            f"$w.SendKeys('{sendkeys}')"
        )
        return "ok"
    return ""


@skill(
    "media_control",
    "Control media playback: play/pause, skip to next track, previous track, or stop.",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["playpause", "next", "previous", "stop", "volumeup", "volumedown"],
            }
        },
        "required": ["action"],
    },
    triggers=[
        "play music",
        "pause the music",
        "pause music",
        "resume music",
        "next track",
        "skip this song",
        "next song",
        "previous track",
        "previous song",
        "stop the music",
    ],
)
def media_control(action: str = "playpause") -> str:
    key = (action or "playpause").lower().replace(" ", "").replace("_", "")
    aliases = {
        "play": "playpause",
        "pause": "playpause",
        "resume": "playpause",
        "skip": "next",
        "nexttrack": "next",
        "back": "previous",
        "prev": "previous",
        "previoustrack": "previous",
    }
    key = aliases.get(key, key)
    if key not in _MEDIA_KEYS:
        return f"I can't do '{action}' — try play, pause, next, previous or stop."
    if not _press(key):
        return unsupported("Media control")
    labels = {
        "playpause": "Toggled playback.",
        "next": "Skipping to the next track.",
        "previous": "Going back a track.",
        "stop": "Playback stopped.",
        "volumeup": "Volume up.",
        "volumedown": "Volume down.",
    }
    return labels[key]


@skill(
    "play_on_youtube",
    "Search YouTube for a song, video or artist and open the first result page.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to play"}},
        "required": ["query"],
    },
    triggers=["play {query} on youtube", "youtube {query}"],
)
def play_on_youtube(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "What should I play?"
    try:
        import pywhatkit  # type: ignore

        pywhatkit.playonyt(q)
        return f"Playing {q} on YouTube."
    except Exception:
        webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(q)}")
        return f"Here are YouTube results for {q}."


@skill(
    "play_on_spotify",
    "Search and open something in Spotify.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Artist, song or playlist"}},
        "required": ["query"],
    },
    triggers=["play {query} on spotify", "spotify {query}"],
)
def play_on_spotify(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "What should I put on?"
    webbrowser.open(f"spotify:search:{quote_plus(q)}")
    return f"Searching Spotify for {q}."
