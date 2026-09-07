"""Hell soak: restart-cycling adversarial fuzz.

    python tests/hell_soak.py

Five "restart" cycles (module purge + state reload) of ~80 worst-mannered
chaos turns each (100KB payloads, emoji floods, refusal bait, SQL jokes,
unicode soup), plus list-bloat hunting on every state queue and a disk-parse
proof after the storm. Exit 0 = Jarvis survived.
"""
from __future__ import annotations

import json
import random
import string
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
random.seed(42)

CRASHES: List[Tuple[str, str]] = []


def tag(phase: str, exc: BaseException) -> None:
    CRASHES.append((phase, f"{type(exc).__name__}: {exc}"))
    print(f"  crash [{phase}]: {exc}")


class ChaosBrain:
    """Worst-behaved legal provider: refuses, throws, answers junk."""

    name = "ollama"
    last_turn_label = None

    def __init__(self) -> None:
        self.n = 0

    def chat(self, messages, tools=None, **kw):
        self.n += 1
        r = random.random()
        if r < 0.12:
            raise Exception("mystery network kraken")
        if r < 0.30:
            return {"content": "I'm afraid I can't do that, Sir.", "tool_calls": []}
        if r < 0.40:
            return {"content": None, "tool_calls": []}
        words = " ".join(random.choices(string.ascii_lowercase, k=random.randint(3, 60)))
        return {"content": words + ", Sir.", "tool_calls": []}


INPUTS = [
    "", " ", "\n", "💀" * 900, "x" * 100_000, "'; DROP TABLE users;--",
    "remember that", "I'm sorry", "tell me everything about it", "what is on the news",
    "\x00\x01 nulls", '{"json": "bomb"}', "add reminder poop daily",
    "set a timer for -5 mins", "what am I?" * 50, "привет مرحبا こんにちは",
    "I live in " + "z" * 500, "http://127.0.0.1:1/hack", "\t\t  ", "TELL ME MY NAME",
]


def main() -> int:
    ag = None
    for cycle in range(5):
        for k in list(sys.modules):
            if k.startswith("jarvis"):
                sys.modules.pop(k, None)
        from jarvis import state  # noqa: F401  (fresh after the wipe)
        from jarvis.brain.agent import Agent

        try:
            ag = Agent("offline")
            ag.provider = ChaosBrain()
            for i, text in enumerate(INPUTS * 2):
                t = ag.ask(text)
                assert isinstance(t.reply, str)
            assert len(ag.history) <= 60, f"history ballooned: {len(ag.history)}"
        except Exception as exc:  # noqa: BLE001
            tag(f"cycle{cycle}", exc)
        size = Path(state.STATE_FILE).stat().st_size if Path(state.STATE_FILE).exists() else 0
        print(f"cycle {cycle}: state.json={size}B history={len(ag.history)}")

    # bloat hunting
    for _ in range(300):
        state.add_notification("spam")
    for _ in range(300):
        state.add_activity("app.exe", "title title")
    for _ in range(100):
        state.log_turn("q" * 500, "a" * 500, [], "ollama")
    size = Path(state.STATE_FILE).stat().st_size
    print(f"state.json after abuse: {size:,} bytes")
    assert len(state._STATE["notifications"]) <= 50
    assert len(state._STATE["activity"]) <= 4000
    with open(state.STATE_FILE, encoding="utf-8") as fh:
        json.load(fh)
    print("state.json parses after the storm  PASS")

    if CRASHES:
        print(f"FAILED — {len(CRASHES)} crash(es):")
        for phase, err in CRASHES[:12]:
            print("  ", phase, "→", err)
        return 1
    print("==== 0 CRASHES ACROSS THE HELL RUN ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
