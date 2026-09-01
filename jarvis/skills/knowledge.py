"""Time, timers, reminders, jokes and small utilities."""
from __future__ import annotations

import datetime as _dt
import random
import threading
import time
from typing import List

from . import skill
from ..config import config

_REMINDERS: List[dict] = []
_TIMERS: List[dict] = []


@skill(
    "get_time",
    "Get the current time and date.",
    {"type": "object", "properties": {}},
    triggers=["what time is it", "what's the time", "the time", "what's today's date", "what day is it"],
)
def get_time() -> str:
    now = _dt.datetime.now()
    return now.strftime("It's %I:%M %p on %A, %B %d, %Y.").replace(" 0", " ")


@skill(
    "set_timer",
    "Set a countdown timer. Jarvis will announce when it finishes.",
    {
        "type": "object",
        "properties": {
            "minutes": {"type": "number", "description": "Duration in minutes"},
            "label": {"type": "string", "description": "Optional label"},
        },
        "required": ["minutes"],
    },
    triggers=["set a timer for {minutes} minutes", "timer for {minutes} minutes"],
)
def set_timer(minutes: float | str = 5, label: str = "") -> str:
    try:
        mins = float(str(minutes).split()[0])
    except Exception:
        return "How many minutes?"
    fire_at = _dt.datetime.now() + _dt.timedelta(minutes=mins)
    entry = {"label": label or "timer", "at": fire_at, "done": False}
    _TIMERS.append(entry)

    def _fire() -> None:
        time.sleep(max(0.0, (fire_at - _dt.datetime.now()).total_seconds()))
        entry["done"] = True
        try:
            from ..voice.tts import speak

            speak(f"{config.user_title}, your {entry['label']} is up.")
        except Exception:
            print(f"\n[TIMER] {entry['label']} is up!")

    threading.Thread(target=_fire, daemon=True).start()
    pretty = f"{mins:g}"
    return f"Timer set for {pretty} minute{'s' if mins != 1 else ''}."


@skill(
    "add_reminder",
    "Remember something for the user, optionally at a specific time today "
    "(24h 'HH:MM' format).",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What to remember"},
            "at": {"type": "string", "description": "Optional HH:MM time today"},
        },
        "required": ["text"],
    },
    triggers=["remind me to {text}", "remember that {text}"],
)
def add_reminder(text: str, at: str = "") -> str:
    entry = {"text": text, "at": at, "created": _dt.datetime.now()}
    _REMINDERS.append(entry)
    if at:
        try:
            hh, mm = [int(x) for x in at.replace(".", ":").split(":")[:2]]
            target = _dt.datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target < _dt.datetime.now():
                target += _dt.timedelta(days=1)

            def _fire() -> None:
                time.sleep(max(0.0, (target - _dt.datetime.now()).total_seconds()))
                try:
                    from ..voice.tts import speak

                    speak(f"Reminder, {config.user_title}: {text}")
                except Exception:
                    print(f"\n[REMINDER] {text}")

            threading.Thread(target=_fire, daemon=True).start()
            return f"I'll remind you to {text} at {target:%I:%M %p}."
        except Exception:
            pass
    return f"Noted: {text}"


@skill(
    "list_reminders",
    "List everything the user has asked to be reminded about.",
    {"type": "object", "properties": {}},
    triggers=["what are my reminders", "list my reminders", "what do i need to do"],
)
def list_reminders() -> str:
    if not _REMINDERS:
        return "You have no reminders."
    rows = ["Your reminders:"]
    for r in _REMINDERS:
        when = f" at {r['at']}" if r.get("at") else ""
        rows.append(f"  • {r['text']}{when}")
    return "\n".join(rows)


@skill(
    "calculate",
    "Evaluate a mathematical expression, e.g. '15% of 240' or '2^10 / 4'.",
    {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "Math expression"}},
        "required": ["expression"],
    },
    triggers=["calculate {expression}", "compute {expression}", "what is {expression} equal to"],
)
def calculate(expression: str) -> str:
    import ast
    import math
    import operator
    import re

    expr = (expression or "").lower()
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"(\1/100)*", expr)
    expr = expr.replace("^", "**").replace("x", "*").replace("÷", "/").replace("plus", "+")
    expr = expr.replace("minus", "-").replace("times", "*").replace("divided by", "/")
    expr = re.sub(r"[^0-9+\-*/().%\s]", "", expr).strip()
    if not expr:
        return "That doesn't look like math I can do."

    ops = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv,
    }

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.operand))
        raise ValueError("unsupported expression")

    try:
        value = ev(ast.parse(expr, mode="eval"))
    except Exception:
        return "I couldn't work that one out."
    if isinstance(value, float) and abs(value - round(value)) < 1e-9:
        value = round(value)
    if isinstance(value, float):
        value = round(value, 6)
    return f"{expression.strip()} = {value}"


_JOKES = [
    "I would tell you a UDP joke, but you might not get it.",
    "There are 10 kinds of people: those who understand binary and those who don't.",
    "I'd tell you a joke about the boot sector, but it's a bit of a stretch to load.",
    "My favourite thing about your PC is the RAM. It never remembers our arguments.",
    "A SQL query walks into a bar, approaches two tables and asks: may I join you?",
]


@skill(
    "tell_joke",
    "Tell the user a light joke.",
    {"type": "object", "properties": {}},
    triggers=["tell me a joke", "make me laugh", "say something funny"],
)
def tell_joke() -> str:
    return random.choice(_JOKES)


@skill(
    "list_capabilities",
    "List what Jarvis can do. Use when the user asks for help or what's possible.",
    {"type": "object", "properties": {}},
    triggers=["what can you do", "help", "list your skills", "your capabilities"],
)
def list_capabilities() -> str:
    from . import REGISTRY

    rows = [f"I have {len(REGISTRY)} skills wired up:"]
    for sk in sorted(REGISTRY.values(), key=lambda s: s.name):
        rows.append(f"  • {sk.name} — {sk.description.split('.')[0]}")
    return "\n".join(rows)
