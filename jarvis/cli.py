"""Terminal interface: text chat and hands-free voice mode."""
from __future__ import annotations

import sys

from .brain import Agent
from .config import config
from .skills import REGISTRY

BANNER = r"""
     ___  ________  ________  ___      ___ ___  ________
    |\  \|\   __  \|\   __  \|\  \    /  /|\  \|\   ____\
    \ \  \ \  \|\  \ \  \|\  \ \  \  /  / | \  \ \  \___|_
  __ \ \  \ \   __  \ \   _  _\ \  \/  / / \ \  \ \_____  \
 |\  \\_\  \ \  \ \  \ \  \\  \\ \    / /   \ \  \|____|\  \
 \ \________\ \__\ \__\ \__\\ _\\ \__/ /     \ \__\____\_\  \
  \|________|\|__|\|__|\|__|\|__|\|__|/       \|__|\_________\
"""

C = {
    "cyan": "\033[96m", "dim": "\033[2m", "bold": "\033[1m",
    "green": "\033[92m", "yellow": "\033[93m", "red": "\033[91m", "off": "\033[0m",
}


def _p(color: str, text: str) -> str:
    return f"{C.get(color, '')}{text}{C['off']}"


def _header(agent: Agent) -> None:
    st = agent.status()
    print(_p("cyan", BANNER))
    print(_p("dim", f"  {config.name} online — {st['skills']} skills — {st['platform']}"))
    print(_p("dim", f"  brain: {st['provider']} ({st['model']})"))
    for note in st["notes"]:
        print(_p("yellow", f"  note: {note}"))
    if st["provider"] == "offline":
        print(_p("yellow", "  Offline mode: direct commands only. See README to add a real model."))
    print(_p("dim", "  commands: /help  /skills  /status  /provider  /voice  /reset  /quit\n"))


def _speak(text: str) -> None:
    if not config.voice_enabled:
        return
    try:
        from .voice.tts import speak

        speak(text, block=True)
    except Exception:
        pass


def chat_loop(agent: Agent, speak_replies: bool = False) -> None:
    while True:
        try:
            text = input(_p("bold", "you › ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        low = text.lower()
        if low in {"/quit", "/exit", "quit", "exit"}:
            print(_p("dim", f"{config.name} offline."))
            return
        if low == "/reset":
            agent.reset()
            print(_p("dim", "Context cleared."))
            continue
        if low == "/status":
            for k, v in agent.status().items():
                print(_p("dim", f"  {k}: {v}"))
            continue
        if low == "/skills":
            for sk in sorted(REGISTRY.values(), key=lambda s: s.name):
                print(f"  {_p('cyan', sk.name):<28} {sk.description.split('.')[0]}")
            continue
        if low == "/help":
            for cmd, what in (
                ("/help", "this list"),
                ("/skills", "all registered skills"),
                ("/status", "current brain, model and notes"),
                ("/reset", "clear the conversation memory"),
                ("/voice", "switch to hands-free wake-word mode"),
                ("/provider ollama|openai|remote|offline|auto", "swap the brain live"),
                ("/quit", "exit"),
            ):
                print(f"  {_p('cyan', cmd):<38} {what}")
            continue
        if low.startswith("/provider"):
            bits = text.split(None, 1)
            if len(bits) == 2 and bits[1].lower() in {
                    "auto", "ollama", "openai", "remote", "offline"}:
                st = agent.reload_provider(bits[1].lower())
                print(_p("dim", f"  brain → {st['provider']} ({st['model']})"))
                for note in st.get("notes", []):
                    if note:
                        print(_p("yellow", f"  note: {note}"))
                continue
            print(_p("yellow", "  usage: /provider auto | ollama | openai | remote | offline"))
            continue
        if low == "/voice":
            voice_loop(agent)
            continue

        turn = agent.ask(text)
        for a in turn.actions:
            print(_p("dim", f"  ⚙ {a['skill']}({a['arguments']})"))
        print(f"{_p('cyan', config.name.lower() + ' › ')}{turn.reply}\n")
        if speak_replies:
            _speak(turn.reply)


def voice_loop(agent: Agent) -> None:
    """Hands-free mode: say the wake word, then your command."""
    from .voice.stt import Ears, strip_wake_word

    ears = Ears()
    if not ears.ok:
        print(_p("red", f"  {ears.error}"))
        return
    print(_p("green", f"  Listening. Say '{config.wake_word}' followed by a command. Ctrl+C to stop."))
    _speak(f"{config.name} online.")
    armed = False
    try:
        while True:
            heard = ears.listen(timeout=8 if armed else 20)
            if not heard:
                armed = False
                continue
            print(_p("dim", f"  heard: {heard}"))
            has_wake, command = strip_wake_word(heard)
            if not (has_wake or armed):
                continue
            if not command:
                _speak(f"Yes, {config.user_title}?")
                armed = True
                continue
            if command.lower() in {"stop listening", "goodbye", "that's all", "go to sleep"}:
                _speak("Standing by.")
                return
            turn = agent.ask(command)
            print(f"{_p('cyan', config.name.lower() + ' › ')}{turn.reply}\n")
            _speak(turn.reply)
            armed = True
    except KeyboardInterrupt:
        print()
        print(_p("dim", "  Voice mode off."))


def main(argv: list[str] | None = None) -> int:
    try:
        from .crashlog import enable as _crashlog
        _crashlog()
    except Exception:
        pass
    argv = argv if argv is not None else sys.argv[1:]
    speak_replies = "--speak" in argv
    provider = None
    for i, a in enumerate(argv):
        if a == "--provider" and i + 1 < len(argv):
            provider = argv[i + 1]

    agent = Agent(provider)
    _header(agent)

    if "--voice" in argv:
        voice_loop(agent)
        return 0
    if "--say" in argv:
        idx = argv.index("--say")
        # The sentence is every non-flag token after --say; --speak and
        # --provider NAME steer the reply instead of being spoken as text.
        words: list[str] = []
        i = idx + 1
        while i < len(argv):
            a = argv[i]
            if a == "--provider" and i + 1 < len(argv):
                i += 2
                continue
            if a == "--speak":
                i += 1
                continue
            words.append(a)
            i += 1
        text = " ".join(words).strip()
        if not text:
            print("Nothing to say — pass a sentence:  python main.py say \"…\"")
            return 1
        turn = agent.ask(text)
        print(turn.reply)
        if speak_replies:
            _speak(turn.reply)
        return 0
    chat_loop(agent, speak_replies=speak_replies)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
