"""Launching, focusing and closing applications."""
from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path

from . import skill
from ._platform import IS_WINDOWS, powershell, run, unsupported

# Friendly name -> launch command on Windows.
APP_ALIASES: dict[str, str] = {
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "explorer": "explorer",
    "file explorer": "explorer",
    "files": "explorer",
    "task manager": "taskmgr",
    "control panel": "control",
    "settings": "ms-settings:",
    "cmd": "cmd",
    "command prompt": "cmd",
    "terminal": "wt",
    "windows terminal": "wt",
    "powershell": "powershell",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "spotify": "spotify",
    "discord": "discord",
    "steam": "steam",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "snipping tool": "snippingtool",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
    "store": "ms-windows-store:",
}

LINUX_ALIASES = {
    "files": "xdg-open ~",
    "terminal": "x-terminal-emulator",
    "calculator": "gnome-calculator",
    "text editor": "gedit",
}


@skill(
    "open_app",
    "Open an application or a Windows settings page by name, e.g. 'spotify', "
    "'notepad', 'task manager', 'chrome'.",
    {
        "type": "object",
        "properties": {"app": {"type": "string", "description": "Application name"}},
        "required": ["app"],
    },
    triggers=["open {app}", "launch {app}", "start {app}", "fire up {app}"],
)
def open_app(app: str) -> str:
    name = (app or "").strip().strip("'\"").lower()
    if not name:
        return "Which app should I open?"
    for filler in ("the ", "my ", "app ", "application "):
        if name.startswith(filler):
            name = name[len(filler):]
    name = name.removesuffix(" app").strip()

    if IS_WINDOWS:
        target = APP_ALIASES.get(name, name)
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return f"Opening {app}."
        except Exception:
            pass
        out = powershell(f"Start-Process '{target}'")
        if "not recognized" in out.lower() or "cannot find" in out.lower() or "error" in out.lower():
            # Last resort: search the Start Menu for a matching shortcut.
            found = powershell(
                "Get-ChildItem -Path "
                "\"$env:ProgramData\\Microsoft\\Windows\\Start Menu\","
                "\"$env:AppData\\Microsoft\\Windows\\Start Menu\" "
                f"-Recurse -Filter '*{name}*.lnk' -ErrorAction SilentlyContinue | "
                "Select-Object -First 1 -ExpandProperty FullName"
            )
            if found and found.endswith(".lnk"):
                powershell(f"Start-Process '{found}'")
                return f"Opening {Path(found).stem}."
            return f"I couldn't find an app called '{app}'."
        return f"Opening {app}."

    # Non-Windows fallback so the assistant still works while you develop.
    cmd = LINUX_ALIASES.get(name, name)
    if shutil.which(cmd.split()[0]) or shutil.which("xdg-open"):
        try:
            subprocess.Popen(cmd, shell=True)
            return f"Opening {app}."
        except Exception as exc:
            return f"Couldn't open {app}: {exc}"
    return unsupported(f"Launching '{app}'")


@skill(
    "close_app",
    "Close or force-quit a running application by name, e.g. 'notepad', 'chrome'.",
    {
        "type": "object",
        "properties": {"app": {"type": "string", "description": "Application name"}},
        "required": ["app"],
    },
    triggers=["close {app}", "quit {app}", "kill {app}", "shut down the app {app}"],
    dangerous=True,
)
def close_app(app: str) -> str:
    name = (app or "").strip().lower().removesuffix(".exe")
    if not name:
        return "Which app should I close?"
    exe = APP_ALIASES.get(name, name)
    if IS_WINDOWS:
        out = run(["taskkill", "/IM", f"{exe}.exe", "/F"])
        if "SUCCESS" in out.upper():
            return f"Closed {app}."
        return f"I couldn't close {app} — it may not be running."
    out = run(["pkill", "-f", exe])
    return f"Sent a close signal to {app}."


@skill(
    "focus_window",
    "Bring an already-open window to the foreground by (partial) title.",
    {
        "type": "object",
        "properties": {"title": {"type": "string", "description": "Window title fragment"}},
        "required": ["title"],
    },
    triggers=["switch to {title}", "focus {title}", "bring up {title}"],
)
def focus_window(title: str) -> str:
    if not IS_WINDOWS:
        return unsupported("Window focusing")
    out = powershell(
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"$p = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}} | Select-Object -First 1; "
        "if ($p) { [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id); 'ok' } else { 'none' }"
    )
    if out.strip().endswith("ok"):
        return f"Switched to {title}."
    return f"No open window matching '{title}'."


@skill(
    "list_windows",
    "List the titles of all currently open windows.",
    {"type": "object", "properties": {}},
    triggers=["what windows are open", "list windows", "list open windows"],
)
def list_windows() -> str:
    if not IS_WINDOWS:
        return unsupported("Window listing")
    out = powershell(
        "Get-Process | Where-Object {$_.MainWindowTitle} | "
        "Select-Object -ExpandProperty MainWindowTitle"
    )
    titles = [t for t in out.splitlines() if t.strip()]
    if not titles:
        return "No windows with visible titles."
    return "Open windows:\n" + "\n".join(f"  • {t}" for t in titles[:20])


@skill(
    "open_url",
    "Open a website in the default browser.",
    {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Full or partial URL"}},
        "required": ["url"],
    },
    triggers=["go to {url}", "open the website {url}"],
)
def open_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return "Which site?"
    if not u.startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    webbrowser.open(u)
    return f"Opening {u}"
