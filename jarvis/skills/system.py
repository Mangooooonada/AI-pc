"""System control: volume, brightness, power, screenshots, stats, locking."""
from __future__ import annotations

import datetime as _dt
import os
import platform
import shutil
from pathlib import Path

from . import skill
from ._platform import IS_WINDOWS, powershell, run, send_keys, unsupported
from ..config import config


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------
def _win_volume_set(percent: int) -> str:
    try:
        from ctypes import cast, POINTER  # type: ignore
        from comtypes import CLSCTX_ALL  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(max(0, min(100, percent)) / 100.0, None)
        return f"Volume set to {percent}%."
    except Exception:
        # Fallback: nudge with media keys (coarse, 2% per press).
        presses = max(0, min(100, percent)) // 2
        send_keys("{VOLUME_DOWN 50}")
        if presses:
            send_keys("{VOLUME_UP %d}" % presses)
        return f"Volume set to roughly {percent}%."


@skill(
    "set_volume",
    "Set the system master volume to a percentage between 0 and 100.",
    {
        "type": "object",
        "properties": {
            "percent": {"type": "integer", "description": "Target volume, 0-100"}
        },
        "required": ["percent"],
    },
    triggers=["set volume to {percent}", "volume to {percent}", "change volume to {percent}"],
)
def set_volume(percent: int | str = 50) -> str:
    try:
        pct = int(str(percent).strip().rstrip("%").split()[0])
    except Exception:
        return "Give me a number between 0 and 100."
    pct = max(0, min(100, pct))
    if IS_WINDOWS:
        return _win_volume_set(pct)
    if shutil.which("pactl"):
        run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"])
        return f"Volume set to {pct}%."
    if shutil.which("osascript"):
        run(["osascript", "-e", f"set volume output volume {pct}"])
        return f"Volume set to {pct}%."
    return unsupported("Volume control")


@skill(
    "mute_audio",
    "Mute or unmute the system audio. Pass mute=true to mute, false to unmute.",
    {
        "type": "object",
        "properties": {"mute": {"type": "boolean", "description": "True to mute"}},
    },
    triggers=["mute", "unmute", "silence the audio"],
)
def mute_audio(mute: bool | str = True) -> str:
    want_mute = str(mute).lower() not in {"false", "0", "no", "unmute"}
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER  # type: ignore
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(1 if want_mute else 0, None)
            return "Audio muted." if want_mute else "Audio unmuted."
        except Exception:
            send_keys("{VOLUME_MUTE}")
            return "Toggled mute."
    if shutil.which("pactl"):
        run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if want_mute else "0"])
        return "Audio muted." if want_mute else "Audio unmuted."
    return unsupported("Mute control")


# --------------------------------------------------------------------------
# Brightness
# --------------------------------------------------------------------------
@skill(
    "set_brightness",
    "Set the main display brightness to a percentage between 0 and 100.",
    {
        "type": "object",
        "properties": {"percent": {"type": "integer", "description": "Brightness 0-100"}},
        "required": ["percent"],
    },
    triggers=["set brightness to {percent}", "brightness to {percent}"],
)
def set_brightness(percent: int | str = 70) -> str:
    try:
        pct = max(0, min(100, int(str(percent).strip().rstrip("%").split()[0])))
    except Exception:
        return "Give me a brightness between 0 and 100."
    if IS_WINDOWS:
        out = powershell(
            "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{pct})"
        )
        if "Exception" in out or "not" in out.lower() and "supported" in out.lower():
            return "This display doesn't expose software brightness control."
        return f"Brightness set to {pct}%."
    return unsupported("Brightness control")


# --------------------------------------------------------------------------
# Power / session
# --------------------------------------------------------------------------
@skill(
    "power_action",
    "Shut down, restart, sleep, lock the computer, or cancel a pending shutdown. "
    "Always confirm with the user before calling this with shutdown or restart.",
    {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["shutdown", "restart", "sleep", "lock", "signout", "cancel"],
            },
            "delay_seconds": {
                "type": "integer",
                "description": "Optional delay before shutdown/restart (default 20)",
            },
        },
        "required": ["action"],
    },
    triggers=["lock the computer", "lock my pc", "lock screen", "go to sleep mode"],
    dangerous=True,
)
def power_action(action: str = "lock", delay_seconds: int = 20) -> str:
    action = (action or "lock").lower().strip()
    if action in {"shutdown", "restart", "signout"} and not config.allow_power:
        return "Power actions are disabled in your config (JARVIS_ALLOW_POWER=false)."
    if not IS_WINDOWS:
        return unsupported("Power control")
    delay = max(0, int(delay_seconds or 0))
    if action == "lock":
        run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "Workstation locked."
    if action == "sleep":
        run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "Going to sleep."
    if action == "shutdown":
        run(["shutdown", "/s", "/t", str(delay)])
        return f"Shutting down in {delay} seconds. Say 'cancel shutdown' to abort."
    if action == "restart":
        run(["shutdown", "/r", "/t", str(delay)])
        return f"Restarting in {delay} seconds. Say 'cancel shutdown' to abort."
    if action == "signout":
        run(["shutdown", "/l"])
        return "Signing out."
    if action == "cancel":
        run(["shutdown", "/a"])
        return "Pending shutdown cancelled."
    return f"Unknown power action '{action}'."


# --------------------------------------------------------------------------
# Screenshot
# --------------------------------------------------------------------------
@skill(
    "take_screenshot",
    "Capture the whole screen and save it as a PNG in the Jarvis workspace folder.",
    {"type": "object", "properties": {}},
    triggers=["take a screenshot", "screenshot", "capture my screen"],
)
def take_screenshot() -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = config.workspace / f"screenshot-{stamp}.png"
    try:
        from PIL import ImageGrab  # type: ignore

        ImageGrab.grab().save(target)
        return f"Screenshot saved to {target}"
    except Exception:
        pass
    if IS_WINDOWS:
        out = powershell(
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
            "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height); "
            "$g=[System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
            f"$bmp.Save('{target}');"
        )
        if target.exists():
            return f"Screenshot saved to {target}"
        return f"Screenshot failed: {out}"
    return unsupported("Screenshots")


# --------------------------------------------------------------------------
# Machine status
# --------------------------------------------------------------------------
@skill(
    "system_status",
    "Report CPU load, memory usage, disk space, battery level and uptime.",
    {"type": "object", "properties": {}},
    triggers=["system status", "how is my pc", "pc status", "system report", "how's my computer"],
)
def system_status() -> str:
    lines = [f"{platform.system()} {platform.release()} on {platform.machine()}"]
    try:
        import psutil  # type: ignore

        cpu = psutil.cpu_percent(interval=0.4)
        mem = psutil.virtual_memory()
        lines.append(f"CPU load {cpu:.0f}% across {psutil.cpu_count(logical=True)} threads")
        lines.append(
            f"Memory {mem.percent:.0f}% used "
            f"({mem.used / 1e9:.1f} GB of {mem.total / 1e9:.1f} GB)"
        )
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        lines.append(
            f"System drive {disk.percent:.0f}% full, {disk.free / 1e9:.0f} GB free"
        )
        battery = getattr(psutil, "sensors_battery", lambda: None)()
        if battery:
            state = "charging" if battery.power_plugged else "on battery"
            lines.append(f"Battery {battery.percent:.0f}% ({state})")
        boot = _dt.datetime.fromtimestamp(psutil.boot_time())
        up = _dt.datetime.now() - boot
        hours, rem = divmod(int(up.total_seconds()), 3600)
        lines.append(f"Uptime {hours}h {rem // 60}m")
    except Exception:
        total, used, free = shutil.disk_usage(Path.home())
        lines.append(f"Disk {free / 1e9:.0f} GB free of {total / 1e9:.0f} GB")
        lines.append("(install psutil for CPU, memory and battery detail)")
    return "\n".join(lines)


@skill(
    "list_processes",
    "List the top processes by memory or CPU usage.",
    {
        "type": "object",
        "properties": {
            "sort_by": {"type": "string", "enum": ["memory", "cpu"]},
            "limit": {"type": "integer", "description": "How many to list (default 8)"},
        },
    },
    triggers=[
        "what is running",
        "list processes",
        "list processes by {sort_by}",
        "top processes",
        "top processes by {sort_by}",
    ],
)
def list_processes(sort_by: str = "memory", limit: int = 8) -> str:
    try:
        import psutil  # type: ignore
    except Exception:
        return "I need the psutil package for that (pip install psutil)."
    limit = max(1, min(25, int(limit or 8)))
    procs = []
    for p in psutil.process_iter(["name", "memory_info", "cpu_percent", "pid"]):
        try:
            info = p.info
            procs.append(
                (
                    info.get("name") or "?",
                    info["pid"],
                    (info.get("memory_info").rss if info.get("memory_info") else 0) / 1e6,
                    info.get("cpu_percent") or 0.0,
                )
            )
        except Exception:
            continue
    key = 3 if str(sort_by).lower() == "cpu" else 2
    procs.sort(key=lambda r: r[key], reverse=True)
    rows = [f"Top {limit} processes by {sort_by}:"]
    for name, pid, mem, cpu in procs[:limit]:
        rows.append(f"  {name} (pid {pid}) — {mem:.0f} MB, {cpu:.0f}% CPU")
    return "\n".join(rows)


@skill(
    "empty_recycle_bin",
    "Empty the Windows Recycle Bin.",
    {"type": "object", "properties": {}},
    triggers=["empty the recycle bin", "empty recycle bin", "clear the trash"],
    dangerous=True,
)
def empty_recycle_bin() -> str:
    if not IS_WINDOWS:
        return unsupported("Recycle Bin control")
    powershell("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
    return "Recycle Bin emptied."


@skill(
    "run_shell",
    "Run an arbitrary shell/PowerShell command. Disabled unless the user enabled "
    "JARVIS_ALLOW_SHELL. Use only when no other skill fits.",
    {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "Command to run"}},
        "required": ["command"],
    },
    dangerous=True,
)
def run_shell(command: str) -> str:
    if not config.allow_shell:
        return (
            "Free-form shell access is off. Set JARVIS_ALLOW_SHELL=true in .env "
            "if you want me to run raw commands."
        )
    out = powershell(command) if IS_WINDOWS else run(command, shell=True)
    return out[:4000] or "Command finished with no output."
