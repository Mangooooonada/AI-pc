"""Routines: plain-English schedules for jobs Jarvis runs on its own.

A routine = a prompt (what to do) + a schedule (when). The scheduler lives in
the server's nudge-watcher; execution goes through the same agent loop as
chat (same brains, same 55 skills), and results arrive as notifications.

Schedule grammars understood:
  every morning / every afternoon / every evening / every day
  every day at 5pm · daily at 17:30 · every monday at 9am
  every 30 minutes · every 2 hours · every hour
  at 5pm · tomorrow at 9am · in 30 minutes          (one-shot)

Design rules matching the brief: local-timezone times, survives PC sleep
(missed runs fire once when the machine wakes, never a burst), defers when
you're mid-conversation, persists to the plain JSON state store.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}
_DAYPARTS = {"morning": (8, 0), "afternoon": (15, 0), "evening": (18, 0), "night": (21, 0)}


def _clock(text: str) -> Optional[tuple[int, int]]:
    m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b", text)
    if not m:
        m = re.search(r"\b([01]?\d|2[0-3])[:.](\d{2})\b", text)  # 24h "17:30"
        if m:
            return int(m.group(1)), int(m.group(2))
        return None
    hh = int(m.group(1)) % 12
    if m.group(3) == "pm":
        hh += 12
    return hh, int(m.group(2) or 0)


def parse_schedule(text: str) -> Optional[Dict[str, Any]]:
    """Plain-English schedule -> machine dict, or None if unrecognizable."""
    t = " ".join((text or "").lower().split()).strip()
    if not t:
        return None

    m = re.search(r"\bevery\s+(\d+)\s*(minute|min|hour|hr)s?\b", t)
    if m:
        mins = int(m.group(1)) * (60 if m.group(2).startswith(("hour", "hr")) else 1)
        return {"kind": "interval", "minutes": max(1, mins), "label": t}
    if re.search(r"\bevery hour\b|\bhourly\b", t):
        return {"kind": "interval", "minutes": 60, "label": t}

    for name, day in _WEEKDAYS.items():
        if re.search(rf"\b(?:every\s+)?{name}s?\b", t):
            hh, mm = _clock(t) or (9, 0)
            return {"kind": "weekly", "weekday": day, "hour": hh, "minute": mm, "label": t}

    if re.search(r"\bevery (?:day|morning|afternoon|evening|night)\b|\bdaily\b", t):
        clock = _clock(t)
        if not clock:
            for part, hm in _DAYPARTS.items():
                if part in t:
                    clock = hm
                    break
        hh, mm = clock or (9, 0)
        return {"kind": "daily", "hour": hh, "minute": mm, "label": t}

    # one-shot: "at 5pm", "tomorrow at 9am", "in 30 minutes"
    try:
        from .skills.agenda import parse_when

        iso = parse_when(t)
        if iso:
            return {"kind": "once", "at": iso, "label": t}
    except Exception:
        pass
    return None


def human(schedule: Dict[str, Any]) -> str:
    kind = schedule.get("kind")
    if kind == "interval":
        mins = int(schedule.get("minutes", 60))
        return f"every {mins} minutes" if mins < 60 else f"every {mins // 60} hour{'s' if mins > 60 else ''}"
    if kind == "weekly":
        day = [k for k, v in _WEEKDAYS.items() if v == schedule.get("weekday")][0]
        return f"{day}s at {int(schedule.get('hour', 9)):02d}:{int(schedule.get('minute', 0)):02d}"
    if kind == "once":
        try:
            return "once — " + datetime.fromisoformat(schedule["at"]).strftime("%b %d at %H:%M")
        except Exception:
            return "once"
    return f"daily at {int(schedule.get('hour', 9)):02d}:{int(schedule.get('minute', 0)):02d}"


def due(routine: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Should this routine fire right now? Exactly-once-per-slot semantics:
    a missed slot fires once when the machine wakes, never a burst."""
    if not routine.get("enabled", True):
        return False
    now = now or datetime.now()
    sched = routine.get("schedule") or {}
    last_raw = routine.get("last_run")
    try:
        last = datetime.fromisoformat(last_raw) if last_raw else None
    except (TypeError, ValueError):
        last = None
    kind = sched.get("kind")

    if kind == "once":
        try:
            at = datetime.fromisoformat(sched["at"])
        except Exception:
            return False
        return last is None and at <= now

    if kind == "interval":
        mins = max(1, int(sched.get("minutes", 60)))
        if last is None:
            try:
                created = datetime.fromisoformat(routine.get("created", ""))
            except Exception:
                created = now
            return created + timedelta(minutes=mins) <= now
        return last + timedelta(minutes=mins) <= now

    target = now.replace(
        hour=int(sched.get("hour", 9)), minute=int(sched.get("minute", 0)),
        second=0, microsecond=0,
    )
    if kind == "weekly" and now.weekday() != int(sched.get("weekday", 0)):
        return False
    return target <= now and (last is None or last < target)
