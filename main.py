#!/usr/bin/env python3
"""Jarvis entry point.

    python main.py              # launch the HUD dashboard in your browser
    python main.py cli          # terminal chat
    python main.py voice        # hands-free wake-word mode
    python main.py say "..."    # one-shot command
"""
from __future__ import annotations

import sys
import threading
import webbrowser


def main() -> int:
    args = sys.argv[1:]
    positional = [a for a in args if not a.startswith("-")]
    mode = (positional[0].lower() if positional else "ui")

    if mode in {"cli", "chat", "text"}:
        from jarvis.cli import main as cli_main

        return cli_main(args[1:])

    if mode == "voice":
        from jarvis.cli import main as cli_main

        return cli_main(["--voice"] + args[1:])

    if mode == "say":
        from jarvis.cli import main as cli_main

        return cli_main(["--say"] + args[1:])

    if mode in {"ui", "web", "gui", "hud", "server"}:
        from jarvis.config import config
        from jarvis.server import serve

        url = f"http://localhost:{config.port}"
        print(f"\n  {config.name} HUD → {url}\n  Ctrl+C to shut down.\n")
        if "--no-browser" not in args:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        try:
            serve()
        except KeyboardInterrupt:
            print("\n  Jarvis offline.")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
