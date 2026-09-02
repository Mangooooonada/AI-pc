"""Persistent state: tasks, memories, conversation log, workflows.

Everything is stored as JSON in the Jarvis workspace so the command center has
real data behind every panel instead of decoration.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import config

_LOCK = threading.RLock()
STATE_FILE = config.workspace / "jarvis-state.json"

DEFAULT: Dict[str, Any] = {
    "tasks": [],
    "memories": [],
    "conversations": [],
    "activity": [],
    "patterns": [],
    "workflows": [],
    "stats": {"tool_calls": 0, "session_turns": 0, "boot_count": 0,
              "route_local": 0, "route_cloud": 0, "route_offline": 0,
              "tools_ok": 0, "tools_fail": 0, "usage_since": None},
    "created": None,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT.items():
                data.setdefault(k, v if not isinstance(v, (list, dict)) else type(v)())
            data.setdefault("stats", dict(DEFAULT["stats"]))
            for _k, _v in DEFAULT["stats"].items():
                data["stats"].setdefault(_k, _v)
            return data
        except Exception:
            pass
    seed = json.loads(json.dumps(DEFAULT))
    seed["created"] = _now()
    seed["workflows"] = _seed_workflows()
    return seed


def _seed_workflows() -> List[Dict[str, Any]]:
    return [
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Focus Mode",
            "description": "Pause media, mute audio and dim the display for deep work.",
            "steps": [
                {"skill": "media_control", "arguments": {"action": "playpause"}},
                {"skill": "mute_audio", "arguments": {"mute": True}},
                {"skill": "set_brightness", "arguments": {"percent": 35}},
            ],
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Morning Briefing",
            "description": "Time, weather, headlines and machine health in one shot.",
            "steps": [
                {"skill": "get_time", "arguments": {}},
                {"skill": "get_weather", "arguments": {}},
                {"skill": "get_news", "arguments": {}},
                {"skill": "system_status", "arguments": {}},
            ],
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "End of Day",
            "description": "Screenshot the desktop, tidy Downloads and lock the machine.",
            "steps": [
                {"skill": "take_screenshot", "arguments": {}},
                {"skill": "clean_downloads", "arguments": {"days": 30}},
                {"skill": "power_action", "arguments": {"action": "lock"}},
            ],
        },
        {
            "id": str(uuid.uuid4())[:8],
            "name": "Wind Down",
            "description": "Drop the brightness and volume for evening use.",
            "steps": [
                {"skill": "set_brightness", "arguments": {"percent": 25}},
                {"skill": "set_volume", "arguments": {"percent": 20}},
            ],
        },
    ]


_STATE: Dict[str, Any] = _load()


def save() -> None:
    with _LOCK:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(_STATE, indent=2), encoding="utf-8")
        except Exception:
            pass


def snapshot() -> Dict[str, Any]:
    with _LOCK:
        return json.loads(json.dumps(_STATE))


# ---------------------------------------------------------------- tasks ----
def add_task(title: str, due: Optional[str] = None, tag: str = "general") -> Dict[str, Any]:
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title.strip(),
        "due": due,
        "tag": tag,
        "done": False,
        "created": _now(),
    }
    with _LOCK:
        _STATE["tasks"].append(task)
    save()
    return task


def list_tasks(include_done: bool = True) -> List[Dict[str, Any]]:
    with _LOCK:
        tasks = list(_STATE["tasks"])
    return tasks if include_done else [t for t in tasks if not t["done"]]


def complete_task(task_id: str, done: bool = True) -> bool:
    with _LOCK:
        for t in _STATE["tasks"]:
            if t["id"] == task_id:
                t["done"] = done
                t["completed"] = _now() if done else None
                save()
                return True
    return False


def delete_task(task_id: str) -> bool:
    with _LOCK:
        before = len(_STATE["tasks"])
        _STATE["tasks"] = [t for t in _STATE["tasks"] if t["id"] != task_id]
        changed = len(_STATE["tasks"]) != before
    if changed:
        save()
    return changed


def overdue_tasks() -> List[Dict[str, Any]]:
    out = []
    now = datetime.now()
    for t in list_tasks(include_done=False):
        if not t.get("due"):
            continue
        try:
            if datetime.fromisoformat(t["due"]) < now:
                out.append(t)
        except Exception:
            continue
    return out


# -------------------------------------------------------------- memories ---
def add_memory(text: str, kind: str = "fact", source: str = "user") -> Dict[str, Any]:
    mem = {
        "id": str(uuid.uuid4())[:8],
        "text": text.strip(),
        "kind": kind,
        "source": source,
        "created": _now(),
    }
    with _LOCK:
        for old in _STATE["memories"]:
            if old.get("text", "").strip().lower() == mem["text"].lower():
                # Same fact told twice: refresh it in place instead of
                # piling up duplicates.
                old["created"] = mem["created"]
                old["source"] = mem["source"]
                old["kind"] = mem["kind"]
                mem = old
                break
        else:
            _STATE["memories"].append(mem)
            # Keep the store bounded.
            if len(_STATE["memories"]) > 2000:
                _STATE["memories"] = _STATE["memories"][-2000:]
    save()
    return mem


def list_memories(limit: int = 200, query: str = "") -> List[Dict[str, Any]]:
    with _LOCK:
        mems = list(_STATE["memories"])
    if query:
        q = query.lower()
        mems = [m for m in mems if q in m["text"].lower()]
    return list(reversed(mems))[:limit]


def delete_memory(mem_id: str) -> bool:
    with _LOCK:
        before = len(_STATE["memories"])
        _STATE["memories"] = [m for m in _STATE["memories"] if m["id"] != mem_id]
        changed = len(_STATE["memories"]) != before
    if changed:
        save()
    return changed


# ---------------------------------------------------------- conversations --
def log_turn(user: str, reply: str, actions: List[Dict[str, Any]], provider: str) -> None:
    entry = {
        "id": str(uuid.uuid4())[:8],
        "at": _now(),
        "user": user,
        "reply": reply,
        "actions": actions,
        "provider": provider,
    }
    with _LOCK:
        _STATE["conversations"].append(entry)
        if len(_STATE["conversations"]) > 500:
            _STATE["conversations"] = _STATE["conversations"][-500:]
        _STATE["stats"]["session_turns"] = _STATE["stats"].get("session_turns", 0) + 1
        _STATE["stats"]["tool_calls"] = _STATE["stats"].get("tool_calls", 0) + len(actions)
    save()


def list_conversations(limit: int = 100) -> List[Dict[str, Any]]:
    with _LOCK:
        convos = list(_STATE["conversations"])
    return list(reversed(convos))[:limit]


def recent_turns(limit: int = 80) -> List[Dict[str, str]]:
    """Chronological {user, reply} pairs — feeds brain-memory restoration."""
    with _LOCK:
        convos = list(_STATE["conversations"])
    pairs = [
        {"user": str(c.get("user") or ""), "reply": str(c.get("reply") or "")}
        for c in convos
        if (c.get("user") or "").strip() and (c.get("reply") or "").strip()
    ]
    return pairs[-limit:]


def recent_entries(limit: int = 500) -> List[Dict[str, Any]]:
    """Chronological FULL entries (with provider) — training-data export."""
    with _LOCK:
        convos = list(_STATE["conversations"])
    return [c for c in convos
            if (c.get("user") or "").strip() and (c.get("reply") or "").strip()][-limit:]


def clear_conversations() -> None:
    with _LOCK:
        _STATE["conversations"] = []
    save()


def stats() -> Dict[str, Any]:
    with _LOCK:
        return dict(_STATE["stats"])


def bump_stat(*keys: str) -> None:
    """Increment usage counters (routes taken, tool success). Silent."""
    with _LOCK:
        st = _STATE["stats"]
        if not st.get("usage_since"):
            st["usage_since"] = _now()[:10]
        for k in keys:
            st[k] = int(st.get(k) or 0) + 1
    save()


def bump_boot() -> None:
    with _LOCK:
        _STATE["stats"]["boot_count"] = _STATE["stats"].get("boot_count", 0) + 1
        _STATE["stats"]["session_turns"] = 0
    save()


# ------------------------------------------------------------- flags -------
def get_flag(key: str, default: str = "") -> str:
    with _LOCK:
        return _STATE.setdefault("flags", {}).get(key, default)


def set_flag(key: str, value: str) -> None:
    with _LOCK:
        _STATE.setdefault("flags", {})[key] = value
    save()


# ------------------------------------------------------- notifications -----
def add_notification(text: str, kind: str = "nudge") -> Dict[str, Any]:
    """Queue something Jarvis wants to interrupt the user with (timers, due
    reminders…). The UI drains these via /api/status and shows + speaks them."""
    note = {"id": str(uuid.uuid4())[:8], "at": _now(), "text": text, "kind": kind}
    with _LOCK:
        notes = _STATE.setdefault("notifications", [])
        notes.append(note)
        del notes[:-50]
    save()
    return note


def drain_notifications() -> List[Dict[str, Any]]:
    """Return everything pending and clear it — single-consumer semantics."""
    with _LOCK:
        notes = list(_STATE.setdefault("notifications", []))
        _STATE["notifications"] = []
    if notes:
        save()
    return notes


def audit(kind: str, **fields) -> None:
    """Append to the audit ledger of external/off-device calls (bounded)."""
    entry = {"id": str(uuid.uuid4())[:8], "at": _now(), "kind": kind, **fields}
    with _LOCK:
        log = _STATE.setdefault("audit", [])
        log.append(entry)
        del log[:-500]
    save()


def list_audit(limit: int = 100, kind: str = "") -> List[Dict[str, Any]]:
    with _LOCK:
        rows = list(_STATE.setdefault("audit", []))
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return list(reversed(rows))[:limit]


def mark_task_notified(task_id: str) -> bool:
    with _LOCK:
        for t in _STATE["tasks"]:
            if t["id"] == task_id:
                t["notified"] = True
                save()
                return True
    return False


# -------------------------------------------------------------- routines ---
def add_routine(name: str, prompt: str, schedule: Dict[str, Any]) -> Dict[str, Any]:
    routine = {
        "id": str(uuid.uuid4())[:8],
        "name": (name or "").strip() or "Routine",
        "prompt": (prompt or "").strip(),
        "schedule": schedule,          # {"kind": "daily"|"interval"|"weekly"|"once", ...}
        "enabled": True,
        "last_run": None,              # ISO string of last completed run
        "runs": [],                    # soft history: [{"at":..., "ok":bool, "summary":...}]
        "created": _now(),
    }
    with _LOCK:
        _STATE.setdefault("routines", []).append(routine)
        if len(_STATE["routines"]) > 50:
            _STATE["routines"] = _STATE["routines"][-50:]
    save()
    return routine


def list_routines() -> List[Dict[str, Any]]:
    with _LOCK:
        return [dict(r) for r in _STATE.setdefault("routines", [])]


def get_routine(routine_id: str) -> Optional[Dict[str, Any]]:
    for r in list_routines():
        if r["id"] == routine_id or r["name"].lower() == routine_id.lower():
            return r
    return None


def record_routine_run(routine_id: str, ok: bool, summary: str) -> None:
    with _LOCK:
        for r in _STATE.setdefault("routines", []):
            if r["id"] == routine_id:
                r["last_run"] = _now()
                r.setdefault("runs", []).append(
                    {"at": _now(), "ok": bool(ok), "summary": summary[:400]}
                )
                r["runs"] = r["runs"][-10:]
                if r["schedule"].get("kind") == "once":
                    r["enabled"] = False
                break
    save()


def delete_routine(routine_id: str) -> bool:
    with _LOCK:
        routines = _STATE.setdefault("routines", [])
        before = len(routines)
        _STATE["routines"] = [
            r for r in routines if r["id"] != routine_id and r["name"].lower() != routine_id.lower()
        ]
        changed = len(_STATE["routines"]) != before
    if changed:
        save()
    return changed


# -------------------------------------------------------------- workflows --
def list_workflows() -> List[Dict[str, Any]]:
    with _LOCK:
        return list(_STATE["workflows"])


def get_workflow(wf_id: str) -> Optional[Dict[str, Any]]:
    for wf in list_workflows():
        if wf["id"] == wf_id or wf["name"].lower() == wf_id.lower():
            return wf
    return None


def add_workflow(name: str, description: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    wf = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "description": description,
        "steps": steps,
    }
    with _LOCK:
        _STATE["workflows"].append(wf)
    save()
    return wf


def delete_workflow(wf_id: str) -> bool:
    with _LOCK:
        before = len(_STATE["workflows"])
        _STATE["workflows"] = [w for w in _STATE["workflows"] if w["id"] != wf_id]
        changed = len(_STATE["workflows"]) != before
    if changed:
        save()
    return changed


# ------------------------------------------------------------ timeline -----
def timeline(days: int = 1) -> List[Dict[str, Any]]:
    """Build a mission timeline from tasks that have due times."""
    items = []
    now = datetime.now()
    horizon = now + timedelta(days=days)
    for t in list_tasks():
        if not t.get("due"):
            continue
        try:
            due = datetime.fromisoformat(t["due"])
        except Exception:
            continue
        if due > horizon + timedelta(days=6):
            continue
        delta = due - now
        if t["done"]:
            state = "done"
        elif delta.total_seconds() < 0:
            state = "overdue"
        elif delta.total_seconds() < 3600:
            state = "now"
        else:
            state = "upcoming"
        items.append(
            {
                "id": t["id"],
                "title": t["title"],
                "at": due.strftime("%I:%M %p").lstrip("0").lower(),
                "iso": t["due"],
                "state": state,
                "relative": _relative(delta) if not t["done"] else "Done",
                "tag": t.get("tag", "general"),
            }
        )
    items.sort(key=lambda i: i["iso"])
    return items


def _relative(delta: timedelta) -> str:
    secs = int(delta.total_seconds())
    if secs < 0:
        secs = -secs
        prefix, suffix = "", " ago"
    else:
        prefix, suffix = "In ", ""
    if secs < 60:
        return f"{prefix}moments{suffix}" if suffix else "Now"
    mins, hours = (secs // 60) % 60, secs // 3600
    if hours >= 24:
        return f"{prefix}{hours // 24}d {hours % 24}h{suffix}"
    if hours:
        return f"{prefix}{hours}h {mins}m{suffix}"
    return f"{prefix}{mins}m{suffix}"


# ------------------------------------------------------------ observer ----
def add_activity(app: str, title: str, at: str = "") -> None:
    """Record an app-switch event. Titles are stored locally only."""
    app = (app or "").strip().lower()
    if app.endswith(".exe"):
        app = app[:-4]
    with _LOCK:
        _STATE["activity"].append(
            {"at": at or _now(), "app": app[:80], "title": (title or "")[:140]}
        )
        if len(_STATE["activity"]) > 4000:
            _STATE["activity"] = _STATE["activity"][-4000:]
    save()


def get_activity(limit: int = 4000) -> List[Dict[str, Any]]:
    """Chronological activity events (oldest first)."""
    with _LOCK:
        return list(_STATE["activity"][-limit:])


def clear_activity() -> None:
    with _LOCK:
        _STATE["activity"] = []
    save()


def list_patterns(status: str = "") -> List[Dict[str, Any]]:
    with _LOCK:
        pats = list(_STATE["patterns"])
    return [p for p in pats if not status or p.get("status") == status]


def upsert_pattern(key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Create-or-update a detected habit by its dedupe key."""
    with _LOCK:
        pats = _STATE["patterns"]
        if len(pats) >= 60 and not any(p["key"] == key for p in pats):
            pats[:] = pats[-59:]
        for p in pats:
            if p["key"] == key:
                p.update(patch)
                save()
                return dict(p)
        new = {"key": key, "id": str(uuid.uuid4())[:8],
               "status": "pending", "created": _now()}
        new.update(patch)
        pats.append(new)
    save()
    return new


def set_pattern_status(key: str, status: str) -> bool:
    with _LOCK:
        for p in _STATE["patterns"]:
            if p["key"] == key:
                p["status"] = status
                save()
                return True
    return False
