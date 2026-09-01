"""Native desktop application window.

Runs the Jarvis backend on a private local port and renders the command center
in an OS window (Edge WebView2 on Windows, WebKit elsewhere) — no browser
chrome, no address bar, its own taskbar entry and icon.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path
import threading
import time
from typing import Optional

from .config import config

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON = ASSETS / "icon.png"
ICON_WIN = ASSETS / "icon.ico"

WINDOW_TITLE = f"{config.name} Command Center"


def _free_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", candidate))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


def _wait_for_server(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


class Bridge:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self) -> None:
        self.window = None

    def minimize(self) -> None:
        if self.window:
            self.window.minimize()

    def toggle_fullscreen(self) -> None:
        if self.window:
            self.window.toggle_fullscreen()

    def close(self) -> None:
        if self.window:
            self.window.destroy()

    def is_desktop(self) -> bool:
        return True


def _set_app_identity() -> None:
    """Give the app its own taskbar identity and icon on Windows."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"Jarvis.CommandCenter.{config.name}"
        )
    except Exception:
        pass


def run(port: Optional[int] = None, fullscreen: bool = False, dev: bool = False) -> int:
    try:
        import webview  # type: ignore
    except ImportError:
        print(
            "\n  The desktop window needs pywebview:\n"
            "      pip install pywebview\n\n"
            "  Falling back to the browser interface...\n"
        )
        from .server import serve

        serve()
        return 0

    port = port or _free_port(config.port)

    def _serve() -> None:
        import uvicorn

        from .server import app

        uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

    threading.Thread(target=_serve, daemon=True).start()

    if not _wait_for_server(port):
        print("  Backend failed to start.")
        return 1

    _set_app_identity()

    bridge = Bridge()
    window = webview.create_window(
        WINDOW_TITLE,
        f"http://127.0.0.1:{port}",
        width=1440,
        height=900,
        min_size=(1080, 680),
        background_color="#03080f",
        js_api=bridge,
        text_select=True,
        confirm_close=False,
        frameless=False,
    )
    bridge.window = window

    def _on_closed() -> None:
        # Make sure the uvicorn thread doesn't keep the process alive.
        import os

        os._exit(0)

    window.events.closed += _on_closed

    gui = None
    if sys.platform.startswith("win"):
        gui = "edgechromium"

    start_kwargs = {"debug": dev, "gui": gui, "fullscreen": fullscreen}
    if ICON.exists():
        start_kwargs["icon"] = str(ICON)

    try:
        try:
            webview.start(**start_kwargs)
        except TypeError:
            # Older pywebview builds don't accept an icon argument.
            start_kwargs.pop("icon", None)
            webview.start(**start_kwargs)
    except Exception as exc:
        print(f"  Native window unavailable ({exc}); opening in your browser instead.")
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
