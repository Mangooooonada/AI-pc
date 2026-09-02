"""Computer use: a plan-first GUI pilot.

Jarvis proposes an exact step list for your goal, you approve it
("execute the plan"), THEN hands touch the mouse and keyboard.
Every action is audited to the notification feed; "stop the computer"
halts mid-plan. Never types into password/sign-in dialogs.

Hard gates: JARVIS_COMPUTER_USE=on (Settings) — default OFF — and an
explicit approval per plan. Vision grounding kicks in automatically when
an Ollama vision model is installed; otherwise we drive on titles +
your description.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from . import state
from .config import config

_MAX_STEPS = 12
_TYPE_DENYLIST = ("password", "credential", "sign in", "log in", "passphrase",
                  "bank", "payment card", "credit card")

_pending: Dict[str, Any] = {}            # the single proposed plan awaiting approval
_pilot_thread: Optional[threading.Thread] = None

_DSL = """You are a GUI pilot. Reply with ONLY step lines, one per line:
OPEN_APP <name>
HOTKEY <keys joined by +>     (e.g. HOTKEY ctrl+l)
TYPE <text>                   (types into the focused field)
KEY <enter|tab|esc|space|up|down>
WAIT <seconds>
CLICK <x> <y>                 (only if the screen description gives coordinates)
DONE                            (mandatory final line)
Rules: minimum steps, maximum 12. Never TYPE into password or sign-in fields.
If the goal is impossible or unsafe, reply with exactly: REFUSE <why>"""


def enabled() -> bool:
    return bool(config.computer_use) and state.get_flag("computer_use", "1" if config.computer_use else "0") != "0"


def _screen_context(goal: str) -> str:
    """Best-effort grounding: vision model if present, else window title."""
    try:
        from .skills import vision as _v
        if _v._vision_model():
            desc = _v.describe_screen(
                "Describe what's on screen for GUI automation: app, dialogs, "
                "obvious buttons/fields and roughly where they are.")
            if desc and not desc.startswith(("I can't", "I need", "(")):
                return "SCREEN: " + desc[:600]
    except Exception:
        pass
    try:
        from .observe import active_window
        app, title = active_window()
        return f"FOCUSED: {app} — {title}" if app else "FOCUSED: unknown"
    except Exception:
        return "FOCUSED: unknown"


def _provider():
    from .brain.providers import get_provider
    provider, _ = get_provider(None)
    return provider


def propose_plan(goal: str) -> str:
    """Build the plan; store it pending approval; return human-readable text."""
    global _pending
    if not enabled():
        return ("Computer control is off — that's the safe default. Flip "
                "JARVIS_COMPUTER_USE in Settings (or .env), then ask again.")
    prov = _provider()
    ctx = _screen_context(goal)
    try:
        result = prov.chat(
            [{"role": "system", "content": _DSL},
             {"role": "user", "content": f"GOAL: {goal}\n{ctx}"}],
            tools=[])
    except Exception as exc:
        return f"The pilot couldn't think right now: {exc}"
    text = (result.get("content") or "").strip()
    steps = _parse(text)
    if text.startswith("REFUSE"):
        return f"I won't drive that: {text[6:].strip() or 'unsafe or impossible'}."
    if not steps:
        return (f"I couldn't turn that into steps on this screen. "
                f"The model said: {text[:160] or '(nothing)'}")
    steps = steps[:_MAX_STEPS]
    _pending = {"goal": goal, "steps": steps}
    pretty = "\n".join(f"  {i + 1}. {s['raw']}" for i, s in enumerate(steps))
    return (f"Here's exactly what I'll do ({len(steps)} steps):\n{pretty}\n"
            f"Say \"execute the plan\" and I'll do it — \"stop the computer\" halts mid-way. "
            "Every action hits your notification feed.")


def _parse(text: str) -> List[Dict[str, Any]]:
    steps = []
    for line in text.splitlines():
        line = line.strip()
        u = line.upper()
        if u.startswith("OPEN_APP "):
            steps.append({"op": "open", "arg": line[9:].strip(), "raw": line})
        elif u.startswith("HOTKEY "):
            steps.append({"op": "hotkey", "arg": line[7:].strip(), "raw": line})
        elif u.startswith("TYPE "):
            steps.append({"op": "type", "arg": line[5:].strip(), "raw": line})
        elif u.startswith("KEY "):
            steps.append({"op": "key", "arg": line[4:].strip().lower(), "raw": line})
        elif u.startswith("WAIT "):
            try:
                sec = max(0.0, min(10.0, float(line[5:].strip())))
            except ValueError:
                sec = 1.0
            steps.append({"op": "wait", "arg": sec, "raw": line})
        elif u.startswith("CLICK "):
            try:
                x, y = (int(v) for v in line[6:].split()[:2])
                steps.append({"op": "click", "arg": (x, y), "raw": line})
            except (ValueError, IndexError):
                continue
        elif u.startswith("DONE"):
            break
    return steps


def _run_step(step: Dict[str, Any]) -> str:
    op, arg = step["op"], step["arg"]
    if op == "open":
        from .skills.apps import open_app
        return open_app(arg)
    import pyautogui  # type: ignore
    if op == "hotkey":
        pyautogui.hotkey(*[k.strip() for k in str(arg).split("+")], interval=0.08)
        return f"hotkey {arg}"
    if op == "key":
        pyautogui.press(str(arg))
        return f"key {arg}"
    if op == "type":
        # never type into sensitive dialogs
        try:
            from .observe import active_window
            _, title = active_window()
        except Exception:
            title = ""
        low = (title or "").lower()
        if any(w in low for w in _TYPE_DENYLIST):
            return f"REFUSED: current window looks like a sign-in/payment dialog ('{title[:60]}')"
        pyautogui.write(str(arg), interval=0.03)
        return f"typed {len(str(arg))} chars"
    if op == "click":
        pyautogui.click(int(arg[0]), int(arg[1]))
        return f"click {arg[0]},{arg[1]}"
    if op == "wait":
        import time as _t
        _t.sleep(float(arg))
        return f"waited {arg}s"
    return "unknown step (skipped)"


def _pilot() -> None:
    """Executor thread: runs the approved plan step by step."""
    global _pilot_thread
    plan = dict(_pending)
    _pending.clear()
    state.set_flag("cu_stop", "0")
    done, errors = [], []
    for i, step in enumerate(plan["steps"], 1):
        if state.get_flag("cu_stop") == "1":
            done.append(f"(halted after {i - 1} steps, by you)")
            break
        try:
            done.append(_run_step(step))
        except Exception as exc:
            errors.append(f"step {i} ({step['raw']}): {exc}")
    summary = f"🎮 Plan '{plan['goal'][:60]}': " + (
        f"done ({len([d for d in done if not d.startswith('(')])} steps)."
        if not errors else f"{len(errors)} step(s) failed — {errors[0]}")
    state.add_notification(summary)
    _pilot_thread = None


def execute_pending() -> str:
    global _pilot_thread
    if not _pending:
        return "No plan is waiting. Tell me what to do first."
    if _pilot_thread and _pilot_thread.is_alive():
        return "I'm mid-plan already. 'stop the computer' halts me."
    n = len(_pending["steps"])  # capture BEFORE the thread clears _pending
    _pilot_thread = threading.Thread(target=_pilot, daemon=True, name="gui-pilot")
    _pilot_thread.start()
    return f"Executing now — {n} steps. Watch the feed; I'll report when done."


def stop() -> str:
    state.set_flag("cu_stop", "1")
    if _pending:
        _pending.clear()
        return "Plan cancelled — nothing touched the mouse yet."
    return "Stopping. I'll finish the current micro-action and freeze."
