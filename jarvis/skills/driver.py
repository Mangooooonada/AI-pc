"""Observer + computer-use skills: watch me, learn my habits, drive the PC."""
from __future__ import annotations

from . import skill


@skill(
    "observer_toggle",
    "Turn the activity observer on/off. When on, Jarvis notes which apps you use (never keystrokes) to learn your habits.",
    {
        "type": "object",
        "properties": {"on": {"type": "boolean", "description": "True to start watching, false to stop"}},
        "required": ["on"],
    },
    triggers=["start watching what i do", "start watching me", "watch what i do",
              "watch me", "observe my activity"],
)
def observer_toggle(on: bool | str = True) -> str:
    from .. import observe
    want = str(on).strip().lower() not in ("false", "0", "off", "no")
    if want and observe.observer_enabled():
        return "Already watching — I only note app switches, never keystrokes."
    if not want and not observe.observer_enabled():
        return "Already not watching."
    observe.set_observer(want)
    if want:
        return ("Observer on. I'll note which apps you use as you use them, and "
                "start suggesting habits once the same pattern shows up on a few "
                "days. Say 'stop watching what I do' to shut it off — and "
                "'what was I doing today' anytime to see the log.")
    return "Observer off — the log stays on this machine until you clear it. (What I already learned stays learned unless you say otherwise.)"


@skill(
    "todays_activity",
    "Summarize today's observed app usage timeline (observer must be on).",
    {"type": "object", "properties": {}, "required": []},
    triggers=["what was i doing", "what have i been doing", "what was i doing today",
              "today's activity", "my activity today"],
)
def todays_activity() -> str:
    from .. import observe
    return observe.today_summary()


@skill(
    "review_learnings",
    "List habits the observer has spotted; accept ('learn it') turns one into a runnable workflow, 'ignore it' dismisses it.",
    {
        "type": "object",
        "properties": {"action": {"type": "string", "description": "review | learn | ignore (default review)"}},
        "required": [],
    },
    triggers=["review my habits", "what have you learned", "what have you learned about me"],
)
def review_learnings(action: str = "review") -> str:
    from .. import state
    action = (action or "review").strip().lower()
    pending = state.list_patterns("pending")
    learned = state.list_patterns("learned")

    if not pending and not learned:
        return ("Nothing learned yet. I need to watch you (say 'start watching "
                "what I do') and see the same routine on a few different days.")
    lines = []
    if pending:
        lines.append("Waiting on your word:")
        for p in pending[-5:]:
            lines.append(f"  • {p['label']} — seen {p['days_seen']} days")
        lines.append("Say 'learn it' to make the newest one a workflow, or 'ignore it'.")
    if learned:
        lines.append("Already learned: " + ", ".join(p["label"] for p in learned[-4:]))
    return "\n".join(lines)


@skill(
    "take_control",
    "Plan a GUI automation for a goal (computer use). Returns the exact step list for approval before anything moves the mouse or keyboard.",
    {
        "type": "object",
        "properties": {"goal": {"type": "string", "description": "What to accomplish, e.g. 'open spotify and start my playlist'"}},
        "required": ["goal"],
    },
    triggers=["take control {goal}", "take control and {goal}", "drive my computer to {goal}",
              "automate {goal} on my computer"],
)
def take_control(goal: str = "") -> str:
    goal = (goal or "").strip()
    if not goal:
        return "What should I do? Tell me the goal and I'll plan every click first."
    from .. import computer_use
    return computer_use.propose_plan(goal)


@skill(
    "execute_plan",
    "Execute the approved computer-use plan.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["execute the plan", "execute it", "proceed with the plan", "run the plan"],
)
def execute_plan() -> str:
    from .. import computer_use
    return computer_use.execute_pending()


@skill(
    "stop_control",
    "Immediately halt an executing computer-use plan (or cancel a pending one).",
    {"type": "object", "properties": {}, "required": []},
    triggers=["stop the computer", "stop control", "abort the plan", "halt computer use"],
)
def stop_control() -> str:
    from .. import computer_use
    return computer_use.stop()


@skill(
    "observer_off",
    "Turn the activity observer OFF, immediately.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["stop watching", "stop watching me", "stop watching what i do",
              "stop observing", "turn off the observer", "don't watch me"],
)
def observer_off() -> str:
    return observer_toggle(False)


def _decide_newest(accept: bool) -> str:
    from .. import state
    pending = state.list_patterns("pending")
    if not pending:
        return "Nothing pending — no spotted habits waiting on your word."
    target = pending[-1]
    if not accept:
        state.set_pattern_status(target["key"], "ignored")
        return f"Okay, ignoring '{target['label']}'. It won't come up again."
    wf = state.add_workflow(
        name="Learned: " + " & ".join(a.title() for a in target["apps"])[:60],
        description=f"Learned from your routine: {target['label']} (seen {target['days_seen']} days).",
        steps=[{"skill": "open_app", "arguments": {"app": a}} for a in target["apps"]],
    )
    state.set_pattern_status(target["key"], "learned")
    return (f"Learned. '{wf['name']}' is now a workflow — say "
            f"'run workflow {wf['name']}' and I'll set up your desk like you do. "
            f"(Currently: opens {', '.join(target['apps'])} in order.)")


@skill(
    "learn_habit",
    "Accept the newest spotted habit and turn it into a runnable workflow.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["learn it", "learn that", "yes learn it", "make it a workflow",
              "teach it to you", "learn that habit"],
)
def learn_habit() -> str:
    return _decide_newest(True)


@skill(
    "ignore_habit",
    "Dismiss the newest spotted habit pattern.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["ignore it", "ignore that habit", "ignore that", "dismiss it"],
)
def ignore_habit() -> str:
    return _decide_newest(False)
