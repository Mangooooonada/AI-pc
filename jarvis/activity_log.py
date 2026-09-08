"""Activity log — human-readable ledger of what Jarvis did.

This is the user-facing log (chat turns, skills run, system events),
distinct from the watcher activity (app-focus episodes). It is persisted
via jarvis.state (jarvis-state.json) and exposed via /api/activity/log.

    from jarvis.activity_log import log_event, get_events
    log_event("chat", "User asked about weather", {"provider": "ollama"})
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import state


def log_event(kind: str, message: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record one activity event. Thin wrapper over state.add_activity_log."""
    return state.add_activity_log(kind=kind, message=message, meta=meta)


def get_events(limit: int = 100, kind: str = "") -> List[Dict[str, Any]]:
    return state.get_activity_log(limit=limit, kind=kind)


def clear() -> None:
    state.clear_activity_log()
