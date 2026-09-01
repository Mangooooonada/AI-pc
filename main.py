#!/usr/bin/env python3
"""Jarvis entry point.

    python main.py              # desktop app window (default)
    python main.py web          # serve the command center in a browser instead
    python main.py cli          # terminal chat
    python main.py voice        # hands-free wake-word mode
    python main.py say "..."    # one-shot command

Flags:
    --no-browser    with `web`, don't auto-open a browser tab
    --fullscreen    with the desktop app, start borderless full screen
    --dev           with the desktop app, enable the web inspector
    --speak         with `cli`, speak the replies aloud
"""
from __future__ import annotations

import sys
import threading
import webbrowser


def main() -> int:
    args = sys.argv[1:]
    positional = [a for a in args if not a.startswith("-")]
    mode = (positional[0].lower() if positional else "app")

    if mode in {"cli", "chat", "text"}:
        from jarvis.cli import main as cli_main

        return cli_main([a for a in args if a != mode])

    if mode == "voice":
        from jarvis.cli import main as cli_main

        return cli_main(["--voice"] + [a for a in args if a != mode])

    if mode == "say":
        from jarvis.cli import main as cli_main

        idx = args.index(positional[0])
        return cli_main(["--say"] + args[idx + 1:])

    if mode in {"web", "server", "browser"}:
        from jarvis.config import config
        from jarvis.server import serve

        url = f"http://localhost:{config.port}"
        print(f"\n  {config.name} Command Center → {url}\n  Ctrl+C to shut down.\n")
        if "--no-browser" not in args:
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        try:
            serve()
        except KeyboardInterrupt:
            print("\n  Jarvis offline.")
        return 0

    if mode in {"app", "ui", "gui", "desktop", "hud"}:
        from jarvis.desktop import run

        return run(fullscreen="--fullscreen" in args, dev="--dev" in args)

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
