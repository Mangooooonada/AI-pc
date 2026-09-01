"""Tasks, long-term memory and workflow skills — backed by persistent state."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import skill
from .. import state
from ..config import config


def parse_when(text: str) -> Optional[str]:
    """Turn '5pm', '17:30', 'tomorrow 9am', 'in 20 minutes' into an ISO string."""
    if not text:
        return None
    t = " ".join(str(text).lower().split()).strip()
    now = datetime.now()

    m = re.search(r"in (\d+)\s*(minute|min|hour|hr|day)s?", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = (
            timedelta(minutes=n)
            if unit.startswith(("min",))
            else timedelta(hours=n)
            if unit.startswith(("hour", "hr"))
            else timedelta(days=n)
        )
        return (now + delta).isoformat(timespec="seconds")

    base = now
    if "tomorrow" in t:
        base = now + timedelta(days=1)
    elif "tonight" in t:
        base = now

    m = re.search(r"(\d{1,2})[:.](\d{2})\s*(am|pm)?", t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        ap = m.group(3)
        if ap == "pm" and hh < 12:
            hh += 12
        if ap == "am" and hh == 12:
            hh = 0
        target = base.replace(hour=min(hh, 23), minute=min(mm, 59), second=0, microsecond=0)
        if target < now and "tomorrow" not in t:
            target += timedelta(days=1)
        return target.isoformat(timespec="seconds")

    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", t)
    if m:
        hh = int(m.group(1))
        if m.group(2) == "pm" and hh < 12:
            hh += 12
        if m.group(2) == "am" and hh == 12:
            hh = 0
        target = base.replace(hour=min(hh, 23), minute=0, second=0, microsecond=0)
        if target < now and "tomorrow" not in t:
            target += timedelta(days=1)
        return target.isoformat(timespec="seconds")

    if "tomorrow" in t:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    return None


@skill(
    "add_task",
    "Add a task or to-do item, optionally with a due time like '5pm', "
    "'tomorrow 9am' or 'in 30 minutes'.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "What needs doing"},
            "due": {"type": "string", "description": "Optional due time in plain English"},
            "tag": {"type": "string", "description": "Optional category, e.g. work, home"},
        },
        "required": ["title"],
    },
    triggers=[
        "add a task {title}",
        "add task {title}",
        "new task {title}",
        "put {title} on my list",
    ],
)
def add_task(title: str, due: str = "", tag: str = "general") -> str:
    clean = (title or "").strip()
    if not clean:
        return "What's the task?"
    # Pull an inline time out of the title if no explicit due was given.
    if not due:
        m = re.search(r"\b(at|by|tomorrow|tonight|in)\b.*$", clean, re.I)
        if m and parse_when(m.group(0)):
            due = m.group(0)
            clean = clean[: m.start()].strip(" ,")
    iso = parse_when(due) if due else None
    task = state.add_task(clean, iso, tag or "general")
    if iso:
        when = datetime.fromisoformat(iso).strftime("%A at %I:%M %p").replace(" 0", " ")
        return f"Task added: {task['title']} — due {when}."
    return f"Task added: {task['title']}."


@skill(
    "list_tasks",
    "List the user's outstanding tasks and to-dos.",
    {
        "type": "object",
        "properties": {
            "include_done": {"type": "boolean", "description": "Include completed tasks"}
        },
    },
    triggers=["what are my tasks", "list my tasks", "what is on my list", "my to do list"],
)
def list_tasks(include_done: bool = False) -> str:
    tasks = state.list_tasks(include_done=bool(include_done))
    if not include_done:
        tasks = [t for t in tasks if not t["done"]]
    if not tasks:
        return "Your task list is clear."
    rows = [f"You have {len(tasks)} task(s):"]
    for t in tasks[:20]:
        mark = "✓" if t["done"] else "•"
        when = ""
        if t.get("due"):
            try:
                when = " — " + datetime.fromisoformat(t["due"]).strftime("%a %I:%M %p").replace(" 0", " ")
            except Exception:
                pass
        rows.append(f"  {mark} {t['title']}{when}")
    return "\n".join(rows)


@skill(
    "complete_task",
    "Mark a task as done. Match on part of the task title.",
    {
        "type": "object",
        "properties": {"title": {"type": "string", "description": "Task title fragment"}},
        "required": ["title"],
    },
    triggers=["mark {title} as done", "complete the task {title}", "finished {title}"],
)
def complete_task(title: str) -> str:
    q = (title or "").lower().strip()
    for t in state.list_tasks():
        if not t["done"] and q and q in t["title"].lower():
            state.complete_task(t["id"], True)
            return f"Marked '{t['title']}' as done."
    return f"I couldn't find an open task matching '{title}'."


@skill(
    "remember",
    "Store a fact about the user in long-term memory so it survives restarts. "
    "Use for preferences, names, project details and anything worth recalling later.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The fact to remember"},
            "kind": {"type": "string", "description": "fact, preference, person or project"},
        },
        "required": ["text"],
    },
    triggers=["remember that {text}", "make a memory {text}", "store this {text}"],
)
def remember(text: str, kind: str = "fact") -> str:
    if not (text or "").strip():
        return "What should I remember?"
    state.add_memory(text.strip(), kind or "fact", "user")
    return f"Stored. I'll remember that {text.strip().rstrip('.')}."


@skill(
    "recall",
    "Search long-term memory for stored facts about the user.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for"}},
    },
    triggers=[
        "what do you remember about {query}", "recall {query}",
        "what do you know about me", "what do you know about {query}",
        "what is my {query}", "who is my {query}", "do you remember my {query}",
    ],
)
def recall(query: str = "") -> str:
    mems = state.list_memories(limit=12, query=query or "")
    if not mems:
        return (
            f"Nothing stored about '{query}'." if query else "My long-term memory is empty."
        )
    rows = [f"{len(mems)} memory item(s):" if not query else f"About '{query}':"]
    for m in mems:
        rows.append(f"  • {m['text']}")
    return "\n".join(rows)


@skill(
    "who_am_i",
    "Answer 'who am I' / 'what is my name' from long-term memory.",
    {"type": "object", "properties": {}},
    triggers=[
        "who am i", "what is my name", "do you know my name",
        "you know my name", "say my name",
    ],
)
def who_am_i() -> str:
    for m in state.list_memories(limit=100):
        hit = re.search(
            r"(?:my name is|call me|name is|i am called)\s+([A-Za-z][\w'’ .-]{0,38})",
            m["text"], re.I,
        )
        if hit:
            who = hit.group(1).strip().rstrip(".")
            return f"You're {who}, {config.user_title}. It's right there in my memory."
    return (
        f"You haven't told me your name yet, {config.user_title}. "
        "Say \"remember my name is …\" and I'll never forget it."
    )


@skill(
    "run_workflow",
    "Run a saved multi-step workflow by name, e.g. 'Focus Mode', 'Morning Briefing', "
    "'End of Day' or 'Wind Down'.",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Workflow name"}},
        "required": ["name"],
    },
    triggers=["run the workflow {name}", "run workflow {name}", "activate {name}"],
)
def run_workflow(name: str) -> str:
    from . import run_skill

    wf = state.get_workflow((name or "").strip())
    if not wf:
        names = ", ".join(w["name"] for w in state.list_workflows())
        return f"No workflow called '{name}'. Available: {names}."
    results: List[str] = [f"Running {wf['name']}:"]
    for step in wf["steps"]:
        out = run_skill(step["skill"], step.get("arguments", {}))
        results.append(f"  • {step['skill']}: {out.splitlines()[0][:120]}")
    return "\n".join(results)


@skill(
    "list_workflows",
    "List the saved workflows that can be run.",
    {"type": "object", "properties": {}},
    triggers=["what workflows do i have", "list workflows"],
)
def list_workflows() -> str:
    wfs = state.list_workflows()
    if not wfs:
        return "No workflows saved."
    rows = ["Saved workflows:"]
    for w in wfs:
        rows.append(f"  • {w['name']} — {w['description']} ({len(w['steps'])} steps)")
    return "\n".join(rows)


@skill(
    "executive_briefing",
    "Give a full situational briefing: time, machine health, tasks due, and weather.",
    {"type": "object", "properties": {}},
    triggers=["executive briefing", "brief me", "give me a briefing", "status report"],
)
def executive_briefing() -> str:
    from .knowledge import get_time
    from .system import system_status
    from .web import get_weather

    parts: List[str] = [get_time()]
    open_tasks = [t for t in state.list_tasks() if not t["done"]]
    overdue = state.overdue_tasks()
    if open_tasks:
        parts.append(
            f"You have {len(open_tasks)} open task(s)"
            + (f", {len(overdue)} overdue." if overdue else ".")
        )
        for t in open_tasks[:3]:
            parts.append(f"  • {t['title']}")
    else:
        parts.append("Your task list is clear.")
    try:
        parts.append(get_weather())
    except Exception:
        pass
    parts.append(system_status().replace("\n", "; "))
    return "\n".join(parts)
