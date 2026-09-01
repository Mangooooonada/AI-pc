"""Auto-memory: quietly save the personal facts worth keeping.

Heuristic, offline-safe, zero latency: patterns spot the things people tell
an assistant on purpose (name, likes, location, work, email, birthday) and
drop them into the same long-term store the offline engine reads from.
Explicit "remember that …" skills stay untouched; this catches the casual
mentions. Duplicate-ish facts collapse (the store dedupes exact repeats;
near-dupes are containment-checked here).
"""
from __future__ import annotations

import re
from typing import List

from ..config import config

_PATTERNS = [
    (re.compile(r"\bmy name is\s+([A-Za-z][\w'’ .-]{1,38})", re.I),
     "The user's name is {0}."),
    (re.compile(r"\bmy favou?rite (\w[\w -]{1,28}?) (?:is|=)\s+([^.!;\n]{1,60})", re.I),
     "The user's favourite {0} is {1}."),
    (re.compile(r"\bi (?:really )?(?:like|love|enjoy)\s+([^.!;\n]{2,60})", re.I),
     "The user likes {0}."),
    (re.compile(r"\bi (?:live|am based)\s+in\s+([^.!;\n]{2,40})", re.I),
     "The user lives in {0}."),
    (re.compile(r"\bi work (?:at|for)\s+([^.!;\n]{2,40})", re.I),
     "The user works at {0}."),
    (re.compile(r"\bmy email is\s+([\w.+-]+@[\w-]+\.[\w.]+)", re.I),
     "The user's email is {0}."),
    (re.compile(r"\bmy (?:birthday|b-day) is\s+([^.!;\n]{2,30})", re.I),
     "The user's birthday is {0}."),
]


def maybe_autoremember(text: str) -> List[str]:
    """Extract and save noteworthy facts from one user utterance.

    Returns the facts stored (usually []). Never raises — auto-memory must
    never break a conversation.
    """
    if not getattr(config, "auto_mem", True):
        return []
    body = (text or "").strip()
    if not body:
        return []
    try:
        from .. import state

        known = {
            m["text"].strip().lower().rstrip(".")
            for m in state.list_memories(limit=500)
        }
        saved: List[str] = []
        for rx, tpl in _PATTERNS:
            m = rx.search(body)
            if not m:
                continue
            fact = tpl.format(*[g.strip().strip(" .") for g in m.groups()])
            key = fact.lower().rstrip(".")
            # collapse near-duplicates as well as exact ones
            if key in known or any(k in key or key in k for k in known):
                continue
            state.add_memory(fact, kind="fact", source="auto")
            known.add(key)
            saved.append(fact)
        return saved
    except Exception:
        return []
