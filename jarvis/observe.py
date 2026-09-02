"""Observer: watch which apps you use and learn your recurring habits.

Privacy contract (non-negotiable):
  * records APP-LEVEL events only — process name + window title at the moment
    of a switch. Never keystrokes. Never text. Never screenshots.
  * stored locally in jarvis-state.json, capped at 4000 events.
  * OFF by default; toggled live with "start watching what I do".

Learning contract (honest scope): this mines your app-switch timeline for
REPEATED habits — sequences ("Outlook then Teams then Spotify") seen on
several different days at a similar hour. Those become proposed workflows
you approve or ignore. It is pattern mining over YOUR behavior, not magic.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import state
from .config import config

_GAP_MIN = 30          # inactivity gap this long splits "sessions"
_MIN_DAYS = 3          # a habit must repeat on this many distinct days
_NGRAM = (2, 3, 4)     # sequence lengths we try to learn

_mine_lock = threading.Lock()


# ------------------------------------------------------------- sampling ----
def active_window() -> Tuple[str, str]:
    """(process_name, window_title) of the focused window. ('','') if N/A."""
    try:
        import sys as _sys
        if _sys.platform.startswith("win"):
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "", ""
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                import psutil  # type: ignore
                proc = psutil.Process(pid.value).name()
            except Exception:
                proc = ""
            return proc, title
        # Other platforms: no window access — observer stays politely blind.
        return "", ""
    except Exception:
        return "", ""


def observer_enabled() -> bool:
    flag = state.get_flag("observe", "")
    if flag:
        return flag == "1"
    return bool(config.observe)


def set_observer(on: bool) -> None:
    state.set_flag("observe", "1" if on else "0")
    if on:
        state.add_notification("👁 Observer on — I'll quietly note which apps you use. "
                               "Say 'stop watching' any time.")


def watch_loop() -> None:
    """Daemon: sample the focused window; mine patterns every ~10 min."""
    import time as _t
    last_app, last_title, last_mine = "", "", 0.0
    while True:
        try:
            if observer_enabled():
                app, title = active_window()
                if app and (app, title) != (last_app, last_title):
                    state.add_activity(app, title)
                    last_app, last_title = app, title
                if _t.time() - last_mine > 600:
                    last_mine = _t.time()
                    mine_patterns()
            else:
                last_app, last_title = "", ""  # don't record the toggle moment
        except Exception:
            pass  # the watcher must never crash the app
        _t.sleep(max(2, int(config.observe_poll)))


# ------------------------------------------------------------- learning ----
def _sessions(events: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    out, cur, prev = [], [], None
    for e in events:
        try:
            t = datetime.fromisoformat(e["at"])
        except Exception:
            continue
        if prev is not None and (t - prev).total_seconds() > _GAP_MIN * 60:
            out.append(cur); cur = []
        cur.append({"app": e["app"], "title": e.get("title", ""), "t": t})
        prev = t
    if cur:
        out.append(cur)
    return out


def _app_runs(session: List[Dict[str, Any]]) -> List[Tuple[str, datetime]]:
    """Collapse repeats: outlook,outlook,teams -> [(outlook,t),(teams,t)]."""
    runs: List[Tuple[str, datetime]] = []
    for e in session:
        if not runs or runs[-1][0] != e["app"]:
            runs.append((e["app"], e["t"]))
    return runs


def _is_contiguous_sub(shorter: tuple, longer: tuple) -> bool:
    n = len(shorter)
    return any(longer[i:i + n] == shorter for i in range(len(longer) - n + 1))


def mine_patterns(events: Optional[List[Dict[str, Any]]] = None,
                  min_days: int = _MIN_DAYS) -> List[Dict[str, Any]]:
    """Find repeated app sequences + their usual hour. Returns all patterns."""
    events = events if events is not None else state.get_activity()
    days: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for sess in _sessions(events):
        runs = _app_runs(sess)
        if len(runs) < 2:
            continue
        for n in _NGRAM:
            for i in range(len(runs) - n + 1):
                gram = tuple(a for a, _ in runs[i:i + n])
                if len(set(gram)) != n:   # degenerate (a,a,b) repeats
                    continue
                when = runs[i][1]
                dkey = when.date().isoformat()
                slot = days.setdefault(gram, {"days": set(), "hours": []})
                slot["days"].add(dkey)
                slot["hours"].append(when.hour + when.minute / 60.0)

    found: List[Dict[str, Any]] = []
    for gram, slot in days.items():
        if len(slot["days"]) < min_days:
            continue
        # subsumed by a longer qualifying sequence that contains it?
        if any(other != gram
               and len(days[other]["days"]) >= len(slot["days"])
               and _is_contiguous_sub(gram, other)
               for other in days):
            continue
        hour = round(sum(slot["hours"]) / len(slot["hours"]), 2)
        apps = [a.lower()[:-4] if a.lower().endswith(".exe") else a.lower() for a in gram]
        key = "seq:" + ">".join(apps)
        hh, mm = int(hour), int((hour % 1) * 60)
        label = (f"{' then '.join(apps)} around "
                 f"{hh % 12 or 12}:{mm:02d} {'AM' if hh < 12 else 'PM'}")
        existing = {p["key"]: p for p in state.list_patterns()}
        patch = {"kind": "sequence", "apps": apps, "hour": hour,
                 "days_seen": len(slot["days"]), "label": label}
        if key in existing:
            state.upsert_pattern(key, patch)
        else:
            state.upsert_pattern(key, patch)
            state.add_notification(
                f"🧠 I spotted a habit: {label} — seen on {len(slot['days'])} days. "
                "Say 'review my habits' to teach it to me.")
        found.append({"key": key, **patch})
    return found


def today_summary() -> str:
    events = state.get_activity()
    if not events:
        return ("I haven't watched anything yet. Say 'start watching what I do' "
                "and I'll begin noting app usage (never keystrokes).")
    today = datetime.now().date().isoformat()
    seen = [e for e in events if e["at"].startswith(today)]
    if not seen:
        return "I've observed no activity yet today."
    apps: Dict[str, int] = {}
    for e in seen:
        name = e["app"].lower()
        apps[name] = apps.get(name, 0) + 1
    top = sorted(apps.items(), key=lambda kv: -kv[1])[:6]
    names = ", ".join(f"{a} ({n}×)" for a, n in top)
    try:
        first = datetime.fromisoformat(seen[0]["at"]).strftime("%H:%M")
        last = datetime.fromisoformat(seen[-1]["at"]).strftime("%H:%M")
    except Exception:
        first = last = "?"
    return (f"Today ({first} → {last}), your most-visited apps: {names}. "
            f"{len(seen)} switches observed.")
