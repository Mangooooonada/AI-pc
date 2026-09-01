"""Cross-platform helpers, optimised for Windows."""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import List, Optional

from ..config import config

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def run(cmd: List[str] | str, shell: bool = False, timeout: int = 25) -> str:
    """Run a command and return trimmed output (or an error string)."""
    try:
        proc = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
        )
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return out
    except subprocess.TimeoutExpired:
        return "(command timed out)"
    except FileNotFoundError:
        return "(command not available on this system)"
    except Exception as exc:
        return f"(command failed: {exc})"


def powershell(script: str, timeout: int = 25) -> str:
    """Run a PowerShell snippet. Windows only."""
    if not IS_WINDOWS:
        return "(PowerShell is only available on Windows)"
    exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    return run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
    )


def send_keys(keys: str) -> str:
    """Send virtual keystrokes (media keys, shortcuts...)."""
    try:
        import pyautogui  # type: ignore

        pyautogui.press(keys)
        return "ok"
    except Exception:
        pass
    if IS_WINDOWS:
        return powershell(
            "$w = New-Object -ComObject WScript.Shell; "
            f"$w.SendKeys('{keys}')"
        )
    return "(keystroke sending unavailable)"


def unsupported(feature: str) -> str:
    return (
        f"{feature} is built for Windows and this machine is running "
        f"{config.platform_name}. The command was skipped."
    )


def find_optional(module: str) -> Optional[object]:
    try:
        return __import__(module)
    except Exception:
        return None
