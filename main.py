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
    --minimized     with the desktop app, start tucked away (used by Start-with-Windows)
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

        return cli_main(_say_cli_args(args))

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

        return run(
            fullscreen="--fullscreen" in args, dev="--dev" in args,
            start_minimized=("--minimized" in args or "--tray" in args),
        )

    print(__doc__)
    return 1


def _say_cli_args(args: list) -> list:
    """cli_main argv for one-shot `say`.

    The words after the `say` mode word are the sentence, but app flags may
    sit on either side of it — `--speak` and `--provider NAME` must steer the
    reply, never be spoken as part of the sentence. (Previously a flag before
    `say` was silently dropped and one after it became literal text.)
    """
    out: list = ["--say"]
    text: list = []
    seen_mode = False
    i = 0
    while i < len(args):
        a = args[i]
        if not seen_mode and not a.startswith("-"):
            seen_mode = True  # the `say` mode word itself
            i += 1
            continue
        if a == "--provider" and i + 1 < len(args):
            out += ["--provider", args[i + 1]]
            i += 2
            continue
        if a == "--speak":
            out.append(a)
            i += 1
            continue
        if a.startswith("-"):
            if not seen_mode:
                i += 1  # other app flag before `say` — cli_main doesn't need it
                continue
            text.append(a)  # text after `say` may legitimately start with '-'
            i += 1
            continue
        text.append(a)
        i += 1
    return out + text


def _crash_report(exc: BaseException) -> None:
    """Last-resort crash handler: always leave evidence behind.

    The app launches via pythonw.exe (no console), so without this an early
    crash was completely invisible, which read as 'Jarvis sometimes crashes
    and nothing happens'.
    """
    import traceback
    from pathlib import Path

    log = Path(__file__).resolve().parent / "jarvis-launcher.log"
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"\n=== CRASH {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} ===\n{detail}")
    except OSError:
        pass
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"Jarvis crashed while starting:\n\n{type(exc).__name__}: {exc}\n\n"
                "Full details were written to jarvis-launcher.log.",
                "JARVIS",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
    else:
        print(detail, file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last resort crash reporting
        _crash_report(exc)
        raise SystemExit(2)
