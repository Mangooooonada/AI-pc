"""Native desktop application window.

Runs the Jarvis backend on a private local port and renders the command center
in an OS window (Edge WebView2 on Windows, WebKit elsewhere) — no browser
chrome, no address bar, its own taskbar entry and icon.

If the native window can't be created (pywebview missing, WebView2 runtime
absent, backend failure) the app used to silently fall back to opening the UI
in the default browser — "the app goes to the website". It still falls back as
a last resort, but now it:

  * checks the WebView2 runtime BEFORE starting, so the likely failure is
    caught up front and explained;
  * picks the best available window backend instead of always forcing
    EdgeChromium;
  * logs every failure to jarvis-launcher.log (vital when launched via
    pythonw.exe, which has no console);
  * shows a Windows message box explaining WHY it fell back.
"""
from __future__ import annotations

import ctypes
import logging
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import List, Optional

from .config import config

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON = ASSETS / "icon.png"
ICON_WIN = ASSETS / "icon.ico"
LOG_FILE = ASSETS.parent / "jarvis-launcher.log"

WINDOW_TITLE = f"{config.name} Command Center"

logger = logging.getLogger("jarvis.launcher")


def _init_logging() -> None:
    """Log to a file so failures are visible even under pythonw.exe."""
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        handler: logging.Handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    logger.addHandler(stream)


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


def _webview2_runtime_installed() -> bool:
    """Detect the Edge WebView2 runtime via the registry (Windows only)."""
    if not sys.platform.startswith("win"):
        return True
    import winreg

    client_id = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\{client_id}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\{client_id}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\{client_id}"),
    )
    for root, subkey in locations:
        try:
            with winreg.OpenKey(root, subkey) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and str(version) not in {"0", "0.0.0.0"}:
                    return True
        except OSError:
            continue
    return False


def _gui_candidates() -> List[Optional[str]]:
    """Best-first list of pywebview backends to try for this platform."""
    if not sys.platform.startswith("win"):
        return [None]  # let pywebview pick (GTK/Cocoa/Qt)

    candidates: List[Optional[str]] = []
    if _webview2_runtime_installed():
        candidates.append("edgechromium")  # modern, matches the HUD design
    else:
        logger.warning(
            "Edge WebView2 runtime not found; the native window may not start. "
            "Re-run setup.bat or install Microsoft Edge WebView2 Runtime."
        )
    try:
        import clr  # noqa: F401  (pythonnet — needed by the .NET backends)
    except ImportError:
        logger.warning("pythonnet not available; .NET-based window backends will fail.")
    candidates.append("cef")  # works without WebView2 when pywin32+cefpython exist
    candidates.append(None)   # last resort: pywebview's own auto-detection
    return candidates


def _set_app_identity() -> None:
    """Give the app its own taskbar identity and icon on Windows."""
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"Jarvis.CommandCenter.{config.name}"
        )
    except Exception:
        pass


def _explain_fallback(reason: str, url: str) -> None:
    """Tell the user why we had to open a browser instead of the app window."""
    message = (
        f"{config.name} couldn't open its desktop window ({reason}).\n\n"
        f"The command center will open in your browser instead:\n{url}\n\n"
        "To get the native app window back:\n"
        "  1. Run setup.bat again (it repairs WebView2 and pywebview).\n"
        "  2. Or install 'Microsoft Edge WebView2 Runtime'.\n\n"
        f"Details are in jarvis-launcher.log."
    )
    logger.error("Falling back to browser UI: %s", reason)
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.user32.MessageBoxW(0, message, WINDOW_TITLE, 0x30)  # MB_ICONWARNING
            return
        except Exception:
            pass
    print("\n" + message + "\n")


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


def _browser_fallback(port: int, reason: str) -> int:
    """Last resort: serve the UI and open it in the default browser."""
    url = f"http://127.0.0.1:{port}"
    _explain_fallback(reason, url)
    webbrowser.open(url)
    try:
        while True:  # keep the backend thread alive for the browser tab
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


def run(port: Optional[int] = None, fullscreen: bool = False, dev: bool = False) -> int:
    _init_logging()

    try:
        import webview  # type: ignore
    except ImportError:
        logger.exception("pywebview is not installed")
        # The window library itself is missing — run the backend in the
        # foreground and send the user to the browser UI explicitly.
        port = port or _free_port(config.port)
        url = f"http://127.0.0.1:{port}"
        _explain_fallback("pywebview is not installed", url)

        def _open() -> None:
            if _wait_for_server(port):
                webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()
        from .server import serve

        try:
            serve(port=port)
        except KeyboardInterrupt:
            pass
        return 0

    port = port or _free_port(config.port)

    def _serve() -> None:
        import uvicorn

        from .server import app

        uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

    threading.Thread(target=_serve, daemon=True).start()

    if not _wait_for_server(port):
        logger.error("Backend failed to start on port %s", port)
        _explain_fallback("the backend server failed to start", f"http://127.0.0.1:{port}")
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

    start_kwargs = {"debug": dev, "fullscreen": fullscreen}
    if ICON.exists() and not sys.platform.startswith("win"):
        # The `icon` argument is only honoured by the Linux/GTK backend.
        start_kwargs["icon"] = str(ICON)

    # pywebview.start() may only be called once per process, so pick the
    # single best backend up front instead of trying them one by one.
    gui = _gui_candidates()[0]
    if gui:
        start_kwargs["gui"] = gui

    try:
        webview.start(**start_kwargs)
        return 0
    except TypeError:
        # Older pywebview builds reject some of the keyword arguments.
        start_kwargs.pop("icon", None)
        try:
            webview.start(**start_kwargs)
            return 0
        except Exception as exc:
            logger.exception("webview.start failed after argument fallback")
            return _browser_fallback(port, f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        logger.exception("webview.start failed (gui=%s)", gui)
        return _browser_fallback(port, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(run())
