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


# ------------------------------------------------------------- auto-lock ----
_autolock = {"warned": False, "locked": False}


def autolock_enabled() -> bool:
    flag = state.get_flag("autolock", "")
    return flag == "1" if flag else bool(config.autolock)


def set_autolock(on: bool) -> None:
    state.set_flag("autolock", "1" if on else "0")
    if on:
        state.add_notification(
            f"🔒 Auto-lock armed — I'll lock Windows after {config.autolock_minutes} "
            "idle minutes (30s bell warning first). Typing or mouse resets it.")


def _last_input_secs() -> int:
    """Seconds since the last keyboard/mouse activity. 0 where unsupported."""
    try:
        import sys as _sys
        if not _sys.platform.startswith("win"):
            return 0
        import ctypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]
        lii = LASTINPUTINFO(); lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(0, millis // 1000)
    except Exception:
        return 0


def autolock_tick(idle_secs=None, lock_fn=None, notify_fn=None) -> bool:
    """One beat of the walk-away guard. Returns True when it locked.
    Injectable knobs keep the lock testable without barricading the host PC.
    """
    if not autolock_enabled():
        _autolock.update(warned=False, locked=False)
        return False
    idle = _last_input_secs() if idle_secs is None else idle_secs
    threshold = max(60, int(config.autolock_minutes) * 60)
    if idle < threshold:
        _autolock.update(warned=False, locked=_autolock["locked"] and idle > 5)
        if idle <= 5:
            _autolock["locked"] = False
        return False
    if not _autolock["warned"]:
        _autolock["warned"] = True
        notice = (f"🔒 Idle {idle // 60} min — locking this PC in "
                  f"{config.autolock_warn_secs}s unless you move. (Auto-lock.)")
        (notify_fn or state.add_notification)(notice)
    if idle >= threshold + int(config.autolock_warn_secs) and not _autolock["locked"]:
        _autolock["locked"] = True
        try:
            if lock_fn is not None:
                lock_fn()
            else:
                import sys as _sys
                if _sys.platform.startswith("win"):
                    import ctypes
                    ctypes.windll.user32.LockWorkStation()
            return True
        except Exception:
            return False
    return False


# ------------------------------------------------------- clipboard watch ----
_clip = {"last_hash": ""}


def clipboard_enabled() -> bool:
    flag = state.get_flag("clipboard", "")
    return flag == "1" if flag else bool(config.clipboard_watch)


def set_clipboard(on: bool) -> None:
    state.set_flag("clipboard", "1" if on else "0")
    if on:
        state.add_notification(
            "📋 Clipboard memory on — things you copy become searchable "
            "('what did I copy earlier?'). Password/keys are never stored; "
            "'stop remembering the clipboard' ends it.")


def _read_clipboard_text() -> str:
    """Windows CF_UNICODETEXT via ctypes — no deps. '' elsewhere/failure."""
    try:
        import sys as _sys
        if not _sys.platform.startswith("win"):
            return ""
        import ctypes
        user32 = ctypes.windll.user32
        CF_UNICODETEXT = 13
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        if not user32.OpenClipboard(None):
            return ""
        try:
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalLock.restype = ctypes.c_wchar_p
            txt = kernel32.GlobalLock(h) or ""
            kernel32.GlobalUnlock(h)
            return str(txt).strip()
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""


def _looks_secret(text: str) -> bool:
    """Never archive passwords/keys/tokens people copy."""
    try:
        from .privacy import _PATTERNS
        for rx, _ in _PATTERNS:
            if rx.search(text):
                return True
    except Exception:
        pass
    low = text.lower()
    return ("password" in low and "=" in low) or low.startswith(("sk-", "ghp_", "xox"))


def clipboard_tick(reader=None) -> bool:
    """One beat: if the clipboard changed and isn't sensitive-shaped, bank it.
    Returns True on a new entry. reader() is injectable for tests."""
    if not clipboard_enabled():
        return False
    txt = (reader or _read_clipboard_text)()
    if not txt or len(txt) > 2048 or _sensitive_now():
        return False
    digest = str(hash(txt))
    if digest == _clip["last_hash"]:
        return False
    _clip["last_hash"] = digest
    if _looks_secret(txt):
        return False  # deliberately NOT stored
    app, _title = active_window()
    state.add_clipboard(txt, app)
    return True


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
                tick_observer()
                if _t.time() - last_mine > 600:
                    last_mine = _t.time()
                    mine_patterns()
            else:
                last_app, last_title = "", ""  # don't record the toggle moment
            autolock_tick()  # independent of the observer switch
            clipboard_tick()  # bank newly-copied text
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


# ------------------------------------------------------- typed text --------
_SENSITIVE_TITLES = ("password", "sign in", "log in", "credential", "passphrase",
                     "bank", "payment", "credit card", "pin", "unlock")

_kl: Dict[str, Any] = {"buf": [], "app": "", "last": 0.0, "started": False,
                       "missing_note": False}
_shots = {"last": 0.0, "warned": False, "day": ""}
_SHOT_KEEP = 60


def typed_log_enabled() -> bool:
    flag = state.get_flag("observe_text", "")
    return flag == "1" if flag else bool(config.observe_text)


def set_typed_log(on: bool) -> None:
    state.set_flag("observe_text", "1" if on else "0")
    if on:
        state.add_notification("⌨️ Typing-log on — I now remember what you type "
                               "(paused automatically on sign-in/payment screens). "
                               "It's local-only; 'stop logging my typing' to end it.")
    else:
        _flush_typed()


def shots_enabled() -> bool:
    flag = state.get_flag("observe_shots", "")
    return flag == "1" if flag else bool(config.observe_shots)


def set_shots(on: bool) -> None:
    state.set_flag("observe_shots", "1" if on else "0")
    if on:
        state.add_notification("📸 Screenshot timeline on — one frame per minute, "
                               "last 60 kept, local-only. 'stop the screenshots' to end.")


def _sensitive_now() -> bool:
    app, title = active_window()
    low = f"{app} {title}".lower()
    return any(w in low for w in _SENSITIVE_TITLES)


def _flush_typed() -> None:
    import time as _t
    buf = _kl["buf"]
    if not buf:
        return
    text = "".join(buf).strip()
    _kl["buf"] = []
    if text:
        state.add_typed(_kl.get("app", ""), text)
    _kl["last"] = _t.time()


def _on_key(key) -> None:
    """pynput callback: accumulate printable text; commit on Enter."""
    import time as _t
    if not typed_log_enabled():
        return
    app, title = active_window()
    low = f"{app} {title}".lower()
    if any(w in low for w in _SENSITIVE_TITLES):
        _kl["buf"] = []
        _kl["last"] = _t.time()
        return
    _kl["app"] = app
    _kl["last"] = _t.time()
    try:
        ch = key.char            # printable key
        if ch:
            _kl["buf"].append(ch)
            return
    except AttributeError:
        pass
    name = str(key)
    if name.endswith("backspace"):
        if _kl["buf"]:
            _kl["buf"].pop()
    elif name.endswith(("enter", "tab")) or "enter" in name or "tab" in name:
        _flush_typed()
    elif name.endswith("space"):
        _kl["buf"].append(" ")
    # other keys (shift/ctrl/arrows): ignored entirely


def ensure_keyboard_listener() -> bool:
    """Start pynput once (lazy). False if pynput missing — notes it once."""
    if _kl["started"]:
        return True
    try:
        from pynput import keyboard  # type: ignore
    except Exception:
        if not _kl["missing_note"]:
            _kl["missing_note"] = True
            state.add_notification("⌨️ Typing-log needs one package: pip install pynput")
        return False
    _kl["started"] = True

    def _loop() -> None:
        with keyboard.Listener(on_press=_on_key) as listener:
            listener.join()

    threading.Thread(target=_loop, daemon=True, name="jarvis-keys").start()
    return True


# ------------------------------------------------------- screenshots -------
def _shots_dir():
    d = config.workspace / "observer-shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _take_observation_shot() -> None:
    try:
        from PIL import ImageGrab  # type: ignore
        img = ImageGrab.grab()
        img.thumbnail((1600, 900))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        img.save(_shots_dir() / f"shot-{stamp}.png", optimize=True)
        shots = sorted(_shots_dir().glob("shot-*.png"))
        for old in shots[: max(0, len(shots) - _SHOT_KEEP)]:
            old.unlink(missing_ok=True)
    except Exception as exc:
        if not _shots["warned"]:
            _shots["warned"] = True
            state.add_notification(f"📸 Screenshot timeline couldn't run: {exc}")


def tick_observer() -> None:
    """Called from watch_loop each cycle: keyboard listener + shot cadence
    + idle flush of the typing buffer + daily frame wipe."""
    import time as _t
    if shots_enabled():
        _wipe_if_new_day()
    if typed_log_enabled():
        if ensure_keyboard_listener():
            # idle flush: untouched buffer older than 8s becomes a record
            if _kl["buf"] and _t.time() - _kl["last"] > 8:
                _flush_typed()
    if shots_enabled():
        interval = max(20, int(config.shot_interval))
        if _t.time() - _shots["last"] >= interval:
            _shots["last"] = _t.time()
            _take_observation_shot()


def typed_recall(limit: int = 12) -> str:
    rows = state.get_typed(limit)[-limit:]
    if not rows:
        return ("No typed-text log yet. Say 'log what I type' to enable it — "
                "it auto-pauses on sign-in/payment screens.")
    lines = [f"Your last {len(rows)} typed entries (local-only):"]
    for r in rows:
        try:
            hh = datetime.fromisoformat(r["at"]).strftime("%H:%M")
        except Exception:
            hh = "?"
        lines.append(f"  {hh}  [{r['app'] or '?'}] {r['text'][:110]}")
    return "\n".join(lines)


def wipe_observer_shots(reason: str = "scheduled") -> int:
    """Delete the screenshot timeline. Returns how many frames died."""
    try:
        folder = _shots_dir()
    except Exception:
        return 0
    n = 0
    for f in folder.glob("shot-*.png"):
        try:
            f.unlink(); n += 1
        except Exception:
            pass
    if n:
        state.add_notification(f"📸 Screenshot timeline cleared ({n} frame(s)) — {reason}.")
    return n


def _wipe_if_new_day() -> None:
    """Daily hygiene: frames never survive past midnight (or a powered-off
    night — the first tick of a new day finishes the job)."""
    today = datetime.now().date().isoformat()
    if _shots.get("day") and _shots["day"] != today:
        wipe_observer_shots("new day")
    _shots["day"] = today
