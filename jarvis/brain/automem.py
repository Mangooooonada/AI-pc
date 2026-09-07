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
    # ---- v2: the facts people ACTUALLY state out loud ----
    (re.compile(r"\b(?:i am|i'm|i just turned)\s+(\d{1,3})(?!\s*(?:%|percent|minutes?|"
                r"mins?|seconds?|kg|lbs?|dollars?|usd|miles?|km))(?:\s*years?\s*old)?\b", re.I),
     "The user is {0} years old."),
    (re.compile(r"\bcall me\s+([A-Za-z][\w'’-]{1,20})", re.I),
     "The user likes to be called {0}."),
    (re.compile(r"\bi have a\s+(dog|cat|puppy|kitten|bird|parrot|hamster|rabbit|snake|fish)"
                r"(?:\s+(?:named|called)\s+([A-Za-z][\w'’-]{1,20}))?", re.I),
     "The user has a {0}{PETNAME}."),
    (re.compile(r"\bmy (?:dog|cat|puppy|kitten|bird|parrot|hamster|rabbit|snake|fish|pet)"
                r"(?:'s name is| is named| is called| is)\s+([A-Za-z][\w'’-]{1,20})\b", re.I),
     "The user's pet is named {0}."),
    (re.compile(r"\bmy (wife|husband|partner|son|daughter|mother|father|mom|dad|brother|"
                r"sister|girlfriend|boyfriend|boss|best friend)(?:'s name)? is\s+"
                r"([A-Za-z][\w'’ .-]{0,28})\b", re.I),
     "The user's {0} is {1}."),
    (re.compile(r"\bi work as\s+([\w][\w -]{1,38})\b", re.I),
     "The user works as {0}."),
    (re.compile(r"\bmy (?:car|truck|bike|ride) is (?:a )?([^.!;\n]{2,45})\b", re.I),
     "The user's vehicle is {0}."),
    (re.compile(r"\bmy phone number is\s+([+()\d\s.-]{7,20})", re.I),
     "The user's phone number is {0}."),
]

# trailing command form: "<statement>, remember that ok?" → bank the statement
_REMEMBER_THAT = re.compile(
    r"^(?P<stmt>.{4,180}?)[.!?,]*\s*(?:please\s+)?remember\s+(?:that|this|it)"
    r"\s*(?:ok(?:ay)?)?\s*[.!?]*$", re.I | re.S)



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
            groups = [g.strip().strip(" .") for g in m.groups() if g]
            if "{PETNAME}" in tpl:
                tpl_ = tpl.replace("{PETNAME}", f" named {groups[-1]}" if len(groups) > 1 else "")
                groups = groups[:1]
            else:
                tpl_ = tpl
            fact = tpl_.format(*groups)
            key = fact.lower().rstrip(".")
            # collapse near-duplicates as well as exact ones
            if key in known or any(k in key or key in k for k in known):
                continue
            state.add_memory(fact, kind="fact", source="auto")
            known.add(key)
            saved.append(fact)
        if not saved:
            m = _REMEMBER_THAT.match(body)
            if m:
                stmt = m.group("stmt").strip(" .!?,")
                fact = f"Note from the user: {stmt.rstrip('.')}."
                key = fact.lower().rstrip(".")
                if key not in known and not any(k in key or key in k for k in known):
                    state.add_memory(fact, kind="fact", source="auto")
                    saved.append(fact)
        return saved
    except Exception:
        return []
