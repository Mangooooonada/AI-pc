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
import inspect
import logging
import os
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


def _backend_alive(port: int, timeout: float = 0.8) -> bool:
    """Is a Jarvis backend already answering on this port?"""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/status", timeout=timeout
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def _kill_stale_backend(port: int) -> None:
    """Politely terminate a leftover Jarvis backend from a previous launch.

    The desktop window's close handler os._exit()s, so a healthy past instance
    never survives — but if the process froze or the event never fired (some
    pywebview builds), the zombie keeps the port and can chew CPU, which is
    exactly how 'works the first time, fails every relaunch' happens.
    """
    import urllib.request

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/shutdown", data=b"", method="POST"
        )
        urllib.request.urlopen(req, timeout=2)
        logger.info("sent shutdown to the previous Jarvis instance on %s", port)
    except Exception as exc:
        logger.info("previous instance on %s didn't accept shutdown (%s)", port, exc)
    # Give it a moment to die and release the port.
    deadline = time.time() + 6
    while time.time() < deadline and _backend_alive(port, timeout=0.4):
        time.sleep(0.3)


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


def _supported_start_kwargs(webview_module, kwargs: dict) -> dict:
    """Drop arguments the installed pywebview's start() doesn't accept.

    The exact keyword set of webview.start() varies between releases (e.g.
    no release accepts ``fullscreen`` there — fullscreen belongs to
    create_window() — while ``icon`` only exists on newer ones). Passing an
    unsupported argument raises TypeError and the app would fall back to
    the browser for no good reason.
    """
    try:
        params = inspect.signature(webview_module.start).parameters
    except (TypeError, ValueError):
        # Signature unavailable (wrapped/builtin) — keep only the args that
        # have existed since pywebview 3.x.
        return {k: v for k, v in kwargs.items() if k in {"gui", "debug"}}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs  # start() accepts **kwargs
    dropped = sorted(set(kwargs) - set(params))
    if dropped:
        logger.info("pywebview.start() here doesn't accept %s; dropping them.", dropped)
    return {k: v for k, v in kwargs.items() if k in params}


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


def _browser_fallback(port: int, reason: str, window=None) -> int:
    """Last resort: serve the UI and open it in the default browser."""
    if window is not None:
        try:
            window.destroy()  # never leave a dead app window beside the tab
        except Exception:
            pass
    url = f"http://127.0.0.1:{port}"
    _explain_fallback(reason, url)
    if _wait_for_server(port):  # backend thread may still be warming up
        webbrowser.open(url)
    else:
        logger.error("fallback: backend never answered on %s", port)
    try:
        while True:  # keep the backend thread alive for the browser tab
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


def _splash_html() -> str:
    """Boot screen shown instantly while the backend warms up."""
    return """<!doctype html><html><body style="margin:0;height:100vh;display:grid;
place-items:center;background:#020610;color:#3ce0ff;font-family:'Segoe UI',sans-serif">
<div style="text-align:center">
<svg width="86" height="86" viewBox="0 0 48 48" style="margin:0 auto;display:block">
<circle cx="24" cy="24" r="20" fill="none" stroke="#3ce0ff" stroke-width="2"
 stroke-dasharray="60 20" opacity=".7">
 <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="3s" repeatCount="indefinite"/>
</circle>
<circle cx="24" cy="24" r="12" fill="none" stroke="#12a8cf" stroke-width="2"
 stroke-dasharray="26 14" opacity=".8">
 <animateTransform attributeName="transform" type="rotate" from="360 24 24" to="0 24 24" dur="2s" repeatCount="indefinite"/>
</circle>
<circle cx="24" cy="24" r="5" fill="#3ce0ff"/></svg>
<div style="font-size:20px;letter-spacing:.35em;margin-top:18px;color:#eafaff">JARVIS</div>
<div id="st" style="font-size:10px;letter-spacing:.3em;color:#1c6b85;margin-top:8px">BOOTING SYSTEMS…</div>
<div style="font-size:10px;color:#3d6479;margin-top:26px;max-width:380px;line-height:1.7">
If this screen stays up for more than a minute, the backend failed to start —
check jarvis-launcher.log next to the app.<br><br>
Tip: Python apps launch much faster if the Jarvis folder is on Windows
Defender's exclusion list (Defender scans every file on boot otherwise).</div>
</div></body></html>"""


def _ensure_ollama_running() -> None:
    """Ollama installed but not serving? Start it — quietly, best effort.

    Without this, launching Jarvis on a fresh Windows boot lands on the
    offline keyword brain until someone remembers to open Ollama.
    """
    try:
        import shutil
        import subprocess

        if config.ollama_available():
            return
        exe = shutil.which("ollama")
        if not exe and os.name == "nt":
            candidate = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
            exe = candidate if os.path.exists(candidate) else None
        if not exe:
            return  # not installed — nothing to start
        logger.info("ollama is installed but not running; starting it")
        if os.name == "nt":
            subprocess.Popen(
                [exe, "app"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0),
            )
        else:
            subprocess.Popen(
                [exe, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception as exc:
        logger.warning("couldn't auto-start ollama: %s", exc)


def _tk_boot_splash():
    """A Featherweight tkinter splash shown during the import storm, BEFORE the
    WebView window exists. This is how the first-boot 'Not Responding' dies:
    the CPU-hungry uvicorn/server imports used to run on a thread WHILE the
    WebView2 GUI was initializing, starving its UI thread for seconds at a
    time → Windows flagged the window. Now the storm completes first; the
    window is only created once the backend is answering, so it pumps its
    message loop from birth."""
    try:
        import tkinter as tk
    except Exception:
        return None
    try:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        w, h = 340, 110
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        root.configure(bg="#020610")
        frame = tk.Frame(root, bg="#020610", highlightbackground="#12a8cf",
                         highlightthickness=1)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="J A R V I S", fg="#3ce0ff", bg="#020610",
                 font=("Consolas", 18, "bold")).pack(pady=(22, 2))
        tk.Label(frame, text="WAKING SYSTEMS…", fg="#1c6b85", bg="#020610",
                 font=("Consolas", 8)).pack()
        root.update()
        return root
    except Exception:
        return None


def _tray_image():
    """A tiny glowing Jarvis orb, drawn with PIL — no asset dependency."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=16, fill=(4, 12, 24, 255), outline=(60, 224, 255, 255), width=2)
    d.ellipse((20, 20, 44, 44), fill=(60, 224, 255, 255))
    d.ellipse((27, 27, 37, 37), fill=(4, 12, 24, 255))
    return img


def _start_tray(window, on_quit) -> bool:
    """System-tray icon so closing the window hides instead of quitting.
    Returns True when the tray actually came up (pystray is optional)."""
    try:
        import pystray  # type: ignore

        def _open(icon, item):
            try:
                window.show()
                window.restore()
            except Exception:
                pass

        def _quit(icon, item):
            try:
                icon.stop()
            except Exception:
                pass
            on_quit()

        icon = pystray.Icon(
            "jarvis",
            _tray_image(),
            "Jarvis",
            menu=pystray.Menu(
                pystray.MenuItem("Open Jarvis", _open, default=True),
                pystray.MenuItem("Quit", _quit),
            ),
        )
        threading.Thread(target=icon.run, daemon=True, name="tray").start()
        logger.info("system tray icon started")
        return True
    except Exception as exc:
        logger.warning("tray unavailable (%s) — closing the window will quit Jarvis", exc)
        return False


def _start_hotkey(window) -> None:
    """Ctrl+J summons the window from anywhere (Windows, native, no deps)."""
    if not config.hotkey or os.name != "nt":
        return

    def _loop() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            MOD_CONTROL, VK_J, WM_HOTKEY, HOTKEY_ID = 0x0002, 0x4A, 0x0312, 0x1A24
            if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL, VK_J):
                logger.warning("Ctrl+J hotkey already taken by another app")
                return
            logger.info("global hotkey live: Ctrl+J")
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        window.show()
                        window.restore()
                        window.evaluate_js("window.jarvisWake && window.jarvisWake()")
                    except Exception:
                        pass
            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception as exc:
            logger.warning("hotkey thread died: %s", exc)

    threading.Thread(target=_loop, daemon=True, name="hotkey").start()


def run(port: Optional[int] = None, fullscreen: bool = False, dev: bool = False,
        start_minimized: bool = False) -> int:
    _init_logging()
    _ensure_ollama_running()

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

    port = port or config.port

    # If a previous Jarvis instance never fully died, its backend still owns
    # the default port and can starve this launch. Retire it first.
    if _backend_alive(port):
        logger.info("found a leftover Jarvis backend on port %s; retiring it", port)
        _kill_stale_backend(port)

    port = _free_port(port)

    # ── early boot: run the import storm BEFORE the OS window exists ──
    # (see _tk_boot_splash docstring). Skipped when the user opts out or when
    # the environment already proved fine (JARVIS_NO_EARLY_BOOT=1).
    _early_done = False
    early_app = None
    if not os.environ.get("JARVIS_NO_EARLY_BOOT"):
        splash_tk = _tk_boot_splash()
        try:
            logger.info("early boot: importing server stack before window creation")
            t_imp = time.time()
            import uvicorn as _uv

            from .server import app as early_app
            import uvicorn  # noqa: F401  (local alias warm)
            logger.info("early boot: imports took %.1fs", time.time() - t_imp)

            def _early_serve() -> None:
                try:
                    _uv.run(early_app, host="127.0.0.1", port=port, log_level="error")
                except Exception:
                    logger.exception("early backend thread died")

            threading.Thread(target=_early_serve, daemon=True,
                             name="jarvis-backend").start()
            if _wait_for_server(port, timeout=95.0):
                _early_done = True
            else:
                logger.warning("early boot: backend didn't answer in time; using legacy splash boot")
        except Exception:
            logger.exception("early boot failed; using legacy splash boot")
        if splash_tk is not None:
            try:
                splash_tk.destroy()
            except Exception:
                pass

    def _serve() -> None:
        try:
            logger.info("backend: importing server package…")
            t_imp = time.time()
            import uvicorn

            from .server import app

            logger.info("backend: imports took %.1fs; binding port %s", time.time() - t_imp, port)
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
        except Exception:
            # Under pythonw.exe there is no console — without this the backend
            # dies invisibly and the log only shows "Backend failed to start".
            logger.exception("backend thread died before/during uvicorn startup")

    _set_app_identity()

    # Paint the OS window IMMEDIATELY with a boot splash, then swap in the
    # real UI as soon as the backend answers — no more staring at nothing
    # (or a blank white pane) while imports and provider probes run.
    # Escape hatch: JARVIS_NO_SPLASH=1 swaps the animated splash for a plain
    # page in case the splash itself ever misbehaves on some WebView2 build.
    if os.environ.get("JARVIS_NO_SPLASH"):
        splash = (
            "<!doctype html><body style='background:#020610;color:#3d6479;display:grid;"
            "place-items:center;height:100vh;font-family:sans-serif;margin:0'>"
            "<div id='st' style='letter-spacing:.3em;font-size:11px'>JARVIS BOOTING…</div></body>"
        )
    else:
        splash = _splash_html()

    bridge = Bridge()
    window = webview.create_window(
        WINDOW_TITLE,
        url=(f"http://127.0.0.1:{port}" if _early_done else None),
        html=(None if _early_done else splash),
        width=1440,
        height=900,
        min_size=(1080, 680),
        background_color="#03080f",
        js_api=bridge,
        text_select=True,
        confirm_close=False,
        frameless=False,
        fullscreen=fullscreen,  # belongs on the window, not on start()
        minimized=start_minimized,
    )
    bridge.window = window

    def _dead_backend_html() -> str:
        return """<!doctype html><html><body style="margin:0;height:100vh;display:grid;
place-items:center;background:#020610;color:#eafaff;font-family:'Segoe UI',sans-serif">
<div style="text-align:center;max-width:420px">
<div style="font-size:20px;letter-spacing:.3em;color:#ff5f7e">BOOT FAILURE</div>
<div style="font-size:11px;color:#5f8ba6;margin-top:18px;line-height:2">
The Jarvis backend never came up, so the command center can't load.<br>
Open <b style="color:#3ce0ff">jarvis-launcher.log</b> (next to the app) for the reason,<br>
or try <b style="color:#3ce0ff">main.py web</b> for the browser version.</div>
</div></body></html>"""

    def _splash_status(text: str) -> None:
        try:
            window.evaluate_js(
                "var el=document.getElementById('st');if(el){el.textContent=%r;el.style.color='#12a8cf';}"
                % (text,)
            )
        except Exception:
            pass

    def _handoff() -> None:
        # Small grace so WebView2's GUI initialisation gets first dibs on the
        # CPU (running the import storm DURING window init is what got the
        # window flagged "Not Responding"). Do NOT wait on window.events.loaded
        # here: for inline-HTML windows that event doesn't fire reliably on
        # some backends and we'd burn ~20s for nothing before even starting
        # the backend.
        time.sleep(1.2)
        _splash_status("BACKEND WARMING…")  # no-op if the GUI isn't up yet
        t1 = time.time()
        threading.Thread(target=_serve, daemon=True).start()

        # Wait (up to 90s — antivirus-scanned venvs make imports crawl) with
        # heartbeat log lines so a slow boot is visible in the log.
        deadline = time.time() + 90.0
        last_beat = 0.0
        server_up = False
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    server_up = True
                    break
            except OSError:
                elapsed = time.time() - t1
                if elapsed - last_beat >= 15:
                    last_beat = elapsed
                    logger.info("…backend still warming (%.0fs)", elapsed)
                    _splash_status(f"BACKEND WARMING… {int(elapsed)}s")
                time.sleep(0.15)

        if server_up:
            logger.info("Backend ready after %.1fs; handing off to the UI", time.time() - t1)
            _splash_status("LOADING INTERFACE…")
            # load_url() raises while the GUI loop isn't accepting calls yet
            # (and was the original stall); retry until it actually takes.
            gui_deadline = time.time() + 40.0
            attempt = 0
            while time.time() < gui_deadline:
                attempt += 1
                try:
                    window.load_url(f"http://127.0.0.1:{port}")
                    logger.info("UI loaded (load_url attempt %d)", attempt)
                    ui_state["loaded"] = True
                    return
                except Exception as exc:
                    logger.info("load_url attempt %d not accepted yet: %s", attempt, exc)
                    time.sleep(0.8)
            logger.error("load_url was never accepted by the GUI backend")
        else:
            logger.error("Backend failed to start on port %s within 90s", port)
        try:
            window.load_html(_dead_backend_html())
        except Exception:
            logger.exception("couldn't even show the boot-failure page")

    ui_state = {"loaded": False}  # set by _handoff the moment the page paints
    if not _early_done:
        threading.Thread(target=_handoff, daemon=True).start()
    else:
        ui_state["loaded"] = True  # born painted: window opens on the live UI

    def _hard_quit() -> None:
        # Make sure the uvicorn thread doesn't keep the process alive.
        os._exit(0)

    tray_live = _start_tray(window, _hard_quit) if config.tray else False
    _start_hotkey(window)

    def _on_closed() -> None:
        _hard_quit()

    def _on_closing() -> bool:
        if tray_live:
            # Close button → tuck Jarvis into the system tray instead of
            # quitting. "Quit" on the tray icon is the real off switch.
            try:
                window.hide()
            except Exception:
                pass
            return False  # cancel the close
        return True

    # Different pywebview versions expose `closed` and/or `closing`; hook
    # whatever exists so a real close ALWAYS kills the process (a survivor
    # process is what makes the *next* launch misbehave).
    for evt_name, handler in (("closed", _on_closed), ("closing", _on_closing)):
        evt = getattr(window.events, evt_name, None)
        if evt is None:
            continue
        try:
            evt += handler
        except Exception:
            logger.warning("couldn't hook window event %s", evt_name)


    start_kwargs = {"debug": dev}
    if ICON.exists() and not sys.platform.startswith("win"):
        # The `icon` argument is only honoured by the Linux/GTK backend.
        start_kwargs["icon"] = str(ICON)

    # pywebview.start() may only be called once per process, so pick the
    # single best backend up front instead of trying them one by one.
    gui = _gui_candidates()[0]
    if gui:
        start_kwargs["gui"] = gui

    start_kwargs = _supported_start_kwargs(webview, start_kwargs)
    logger.info("Starting pywebview backend=%s args=%s", gui or "auto", start_kwargs)

    try:
        webview.start(**start_kwargs)
        # Every clean exit path (window X, tray Quit) os._exit()s inside the
        # close handlers, so start() returning early means the WebView2 window
        # died during init without raising (locked profile / GPU hiccup) —
        # the 'splash logs then silence' failure. Never exit mute: hand the
        # user the browser UI instead.
        if not ui_state["loaded"]:
            logger.warning("webview window never loaded its UI (silent WebView2 death)")
            return _browser_fallback(port, "WebView2 window vanished during init", window=window)
        return 0
    except Exception as exc:
        logger.exception("webview.start failed (backend=%s)", gui or "auto")
        return _browser_fallback(port, f"{type(exc).__name__}: {exc}", window=window)


if __name__ == "__main__":
    raise SystemExit(run())
