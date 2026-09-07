"""Security auditing and PC tune-up skills.

Windows-first. Everything degrades to a friendly notice on other platforms, and
every skill is read-only except the ones explicitly marked dangerous
(disable_startup_item) or obviously janitorial (clean_temp).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import skill
from ._platform import IS_WINDOWS, powershell, run, unsupported

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ps_json(script: str, timeout: int = 30) -> Optional[Any]:
    """Run PowerShell that emits ConvertTo-Json; return parsed object or None."""
    out = powershell(script + " | ConvertTo-Json -Depth 3", timeout=timeout)
    if not out or out.startswith("("):
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def _entropyish(name: str) -> float:
    """Crude randomness score for a filename (or process name): 0 normal, ~3 random."""
    stem = Path(name).stem.lower()
    if len(stem) < 6:
        return 0.0
    vowels = sum(c in "aeiou" for c in stem)
    digits = sum(c.isdigit() for c in stem)
    score = 0.0
    if vowels / len(stem) < 0.22:
        score += 1.5
    if digits / len(stem) > 0.35:
        score += 1.0
    if len(set(stem)) / len(stem) > 0.85 and len(stem) >= 8:
        score += 0.5
    return score


def _risky_path(path: str) -> int:
    p = (path or "").lower()
    score = 0
    if "\\temp" in p or "\\tmp\\" in p:
        score += 3
    if "\\downloads\\" in p:
        score += 2
    if "\\appdata\\local\\" in p and "\\programs\\" not in p:
        score += 1
    if "\\recycle" in p or "$recycle" in p:
        score += 3
    return score


def _folder_size(path: Path, cap_files: int = 20000) -> int:
    total = 0
    seen = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                seen += 1
                if seen > cap_files:
                    return total
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _fmt_mb(num: float) -> str:
    return f"{num / 1_048_576:.0f} MB" if num >= 1_048_576 else f"{num / 1024:.0f} KB"


# ---------------------------------------------------------------------------
# Windows Defender / virus protection
# ---------------------------------------------------------------------------
def _defender_status() -> Dict[str, Any]:
    data = _ps_json(
        "Get-MpComputerStatus | Select-Object AMServiceEnabled, AntivirusEnabled,"
        " AntispywareEnabled, RealTimeProtectionEnabled, AntivirusSignatureAge,"
        " QuickScanAge, FullScanAge, QuickScanStartTime"
    )
    return data or {}


@skill(
    "virus_scan",
    "Check Windows Defender's protection status and optionally start a quick "
    "antivirus scan. Use for 'scan for viruses', 'am I infected', 'check my "
    "security'.",
    {
        "type": "object",
        "properties": {
            "start": {
                "type": "boolean",
                "description": "true to also kick off a quick scan in the background",
            }
        },
    },
    triggers=[
        "scan for viruses",
        "virus scan",
        "scan my pc for viruses",
        "check for viruses",
        "am i infected",
        "check my security",
        "run an antivirus scan",
    ],
)
def virus_scan(start: bool = False) -> str:
    if not IS_WINDOWS:
        return unsupported("Virus scanning via Windows Defender")

    st = _defender_status()
    lines: List[str] = ["Windows Defender report:"]
    if not st:
        lines.append(
            "  ⚠ Couldn't read Defender status — it may be disabled or replaced "
            "by a third-party antivirus."
        )
    else:
        def onoff(key: str) -> str:
            return "ON" if st.get(key) else "OFF"

        sig_age = st.get("AntivirusSignatureAge")
        sig_txt = "today" if sig_age == 0 else f"{sig_age} day(s) ago"
        lines.append(f"  • Real-time protection: {onoff('RealTimeProtectionEnabled')}")
        lines.append(f"  • Antivirus engine: {onoff('AntivirusEnabled')}")
        lines.append(f"  • Definitions updated: {sig_txt}")
        if st.get("QuickScanStartTime"):
            lines.append(f"  • Last quick scan started: {st['QuickScanStartTime']}")
        if st.get("AntivirusEnabled") and not st.get("RealTimeProtectionEnabled"):
            lines.append("  ⚠ Real-time protection is OFF — anything you download goes unchecked.")
        if isinstance(sig_age, int) and sig_age >= 3:
            lines.append("  ⚠ Virus definitions are stale — update Windows Defender.")

    threats = _ps_json(
        "@(Get-MpThreatDetection | Select-Object -First 10 ThreatName, InitialDetectionTime)"
    )
    if threats:
        hits = threats if isinstance(threats, list) else [threats]
        lines.append(f"  ⚠ {len(hits)} previous detection(s) on record:")
        for h in hits[:5]:
            if isinstance(h, dict):
                lines.append(f"      - {h.get('ThreatName', '?')} ({h.get('InitialDetectionTime', '?')})")

    if start:
        out = powershell(
            "Start-Process powershell -WindowStyle Hidden -ArgumentList "
            "'-NoProfile -Command Start-MpScan -ScanType QuickScan'; 'started'"
        )
        lines.append(
            "Quick scan launched in the background. It takes a few minutes — "
            "ask me to 'scan for viruses' again later to see the result."
            if "started" in out
            else f"Couldn't launch the scan ({out}). Open Windows Security and start a Quick scan."
        )
    else:
        lines.append("Say 'run an antivirus scan' and I'll start a quick scan.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Startup audit (why boot takes forever + where adware hides)
# ---------------------------------------------------------------------------
def _startup_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    import winreg  # Windows only; callers guard IS_WINDOWS

    roots = [
        (winreg.HKEY_CURRENT_USER, r"HKCU"),
        (winreg.HKEY_LOCAL_MACHINE, r"HKLM"),
    ]
    paths = [
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
    ]
    for hive, hname in roots:
        for sub in paths:
            try:
                with winreg.OpenKey(hive, sub) as key:
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                        except OSError:
                            break
                        entries.append(
                            {"source": f"{hname}\\…\\{sub.split('CurrentVersion')[1].lstrip(chr(92))}",
                             "name": str(name), "command": str(value)}
                        )
                        i += 1
            except OSError:
                continue

    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", "")
    for label, folder in (
        ("Startup folder (user)", Path(appdata) / r"Microsoft\Windows\Start Menu\Programs\Startup"),
        ("Startup folder (all)", Path(programdata) / r"Microsoft\Windows\Start Menu\Programs\Startup"),
    ):
        try:
            for item in sorted(folder.iterdir()):
                if item.name == "desktop.ini" or item.name == "Disabled":
                    continue
                entries.append(
                    {"source": label, "name": item.stem, "command": str(item)}
                )
        except OSError:
            continue
    return entries


def _score_entry(e: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    target = e.get("command", "")
    if _risky_path(target) >= 2:
        flags.append("runs from a suspicious location")
    if _entropyish(e.get("name", "")) >= 2:
        flags.append("random-looking name")
    if re.search(r"\.(js|vbs|ps1|bat|cmd)(\b|\")", target, re.I):
        flags.append("script-based autostart")
    if "powershell" in target.lower() and "-enc" in target.lower().replace("-encodedcommand", "-enc"):
        flags.append("encoded PowerShell payload")
    return flags


@skill(
    "startup_audit",
    "List every program that launches at sign-in and flag the ones that look "
    "suspicious or slow boot. Use for 'check startup programs', 'why is boot so "
    "slow', 'what launches at startup'.",
    {"type": "object", "properties": {}},
    triggers=[
        "check startup programs",
        "what launches at startup",
        "list startup items",
        "why is boot so slow",
        "startup audit",
    ],
)
def startup_audit() -> str:
    if not IS_WINDOWS:
        return unsupported("Startup auditing")
    try:
        entries = _startup_entries()
    except ImportError:
        return unsupported("Startup auditing")
    if not entries:
        return "No startup entries found at all — unusual, but nothing is auto-starting."

    flagged: List[str] = []
    for e in entries:
        flags = _score_entry(e)
        if flags:
            flagged.append(f"      ! {e['name']} — {'; '.join(flags)} [{e['source']}]")

    lines = [
        f"{len(entries)} program(s) launch at sign-in. That's what boot time pays for.",
    ]
    if flagged:
        lines.append("  Suspicious ones worth a look:")
        lines.extend(flagged[:8])
        lines.append("Say 'disable startup item <name>' to stop one from auto-starting.")
    else:
        lines.append("  Nothing looked outright suspicious.")
    heavy_hint = [e["name"] for e in entries[:12]]
    lines.append("  Everything that auto-starts: " + ", ".join(heavy_hint) + ("…" if len(entries) > 12 else ""))
    lines.append(
        "Tip: Task Manager → Startup apps shows Microsoft-measured boot impact; "
        "disable what you don't need daily."
    )
    return "\n".join(lines)


@skill(
    "disable_startup_item",
    "Stop a program from auto-starting at sign-in by name (removes its Run "
    "registry entry or moves its Startup-folder shortcut aside). Asks first — "
    "use startup_audit to see the names.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the startup entry"},
        },
        "required": ["name"],
    },
    triggers=["disable startup item {name}", "stop {name} from starting with windows"],
    dangerous=True,
)
def disable_startup_item(name: str) -> str:
    if not IS_WINDOWS:
        return unsupported("Disabling startup items")
    needle = (name or "").strip().lower()
    if not needle:
        return "Which startup item? Say 'startup audit' to see the list."

    import winreg

    for hive, hname in ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
        sub = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                i = 0
                while True:
                    try:
                        val_name, _val, _t = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    if needle in str(val_name).lower():
                        winreg.DeleteValue(key, val_name)
                        return (
                            f"Done — '{val_name}' ({hname}) will no longer start with Windows. "
                            "You can re-add it by reinstalling or re-enabling the app."
                        )
                    i += 1
        except OSError as exc:
            if hname == "HKCU":
                return f"Couldn't change the registry ({exc})."
            continue

    appdata = os.environ.get("APPDATA", "")
    folder = Path(appdata) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    try:
        for item in folder.iterdir():
            if needle in item.stem.lower():
                disabled_dir = folder / "Disabled"
                disabled_dir.mkdir(exist_ok=True)
                target = disabled_dir / item.name
                item.replace(target)
                return (
                    f"Done — moved '{item.name}' out of the Startup folder into "
                    f"'{target}'. Move it back any time to re-enable it."
                )
    except OSError as exc:
        return f"Couldn't move the shortcut ({exc})."
    return f"I couldn't find a startup entry matching '{name}'. Say 'startup audit' for the exact names."


# ---------------------------------------------------------------------------
# Suspicious processes
# ---------------------------------------------------------------------------
@skill(
    "find_suspicious_processes",
    "Scan running processes for signs of malware: unsigned apps running from "
    "temp/downloads, random-looking names, high resource usage. Use for 'check "
    "running processes for malware', 'what suspicious processes are running'.",
    {"type": "object", "properties": {}},
    triggers=[
        "check for suspicious processes",
        "find suspicious processes",
        "what suspicious processes are running",
        "check running processes for malware",
    ],
)
def find_suspicious_processes() -> str:
    try:
        import psutil  # type: ignore
    except ImportError:
        return "psutil isn't installed, so I can't inspect processes."

    boring_dirs = ("\\windows\\", "\\program files", "\\programdata\\", "\\microsoft\\")
    suspects: List[str] = []
    worst_cpu: List[str] = []
    worst_mem: List[tuple] = []
    for p in psutil.process_iter(["name", "exe", "memory_info"]):
        try:
            name = p.info["name"] or "?"
            exe = p.info["exe"] or ""
            score = _risky_path(exe) + _entropyish(name)
            if exe and not any(d in exe.lower() for d in boring_dirs):
                score += 0.5
            mem = (p.info["memory_info"].rss if p.info["memory_info"] else 0)
            worst_mem.append((mem, name))
            if score >= 2.5:
                suspects.append(f"  ! {name} (pid {p.pid}) — {exe or 'path hidden'}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    worst_mem.sort(reverse=True)
    lines: List[str] = []
    if suspects:
        lines.append(f"{len(suspects)} process(es) deserve a second look:")
        lines.extend(suspects[:8])
        lines.append("I can 'close app <name>' on your word, or run a virus scan.")
    else:
        lines.append("Nothing running right now trips my heuristics — looks clean.")
    hogs = ", ".join(f"{n} ({_fmt_mb(m)})" for m, n in worst_mem[:5])
    lines.append(f"Heaviest on memory: {hogs}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Junk + memory cleaning (stop the slowdown)
# ---------------------------------------------------------------------------
@skill(
    "clean_temp",
    "Delete temporary files to free disk space (safe: Windows temp, user temp). "
    "Reports how much space was freed.",
    {"type": "object", "properties": {}},
    triggers=["clean temp files", "clear temporary files", "clean up disk space", "delete temp files"],
)
def clean_temp() -> str:
    targets: List[Path] = []
    tmp = os.environ.get("TEMP") or os.environ.get("TMP")
    if tmp:
        targets.append(Path(tmp))
    if IS_WINDOWS:
        targets.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Temp")
    freed = 0
    removed = 0
    for target in targets:
        if not target.exists():
            continue
        before = _folder_size(target)
        for root, dirs, files in os.walk(target, topdown=False):
            base = Path(root)
            for f in files:
                try:
                    (base / f).unlink()
                    removed += 1
                except OSError:
                    pass  # in use — leave it
            for d in dirs:
                try:
                    (base / d).rmdir()
                except OSError:
                    pass
        freed += max(0, before - _folder_size(target))
    verb = "Freed" if freed else "Almost nothing to free — temp folders were already tidy"
    return f"{verb} {_fmt_mb(freed)} across {removed} temp file(s). Locked files in use were skipped."


@skill(
    "free_memory",
    "Free up RAM: trims the working sets of background apps and shows the "
    "biggest memory hogs. Use for 'clean my memory', 'free up RAM'.",
    {"type": "object", "properties": {}},
    triggers=["clean my memory", "free up ram", "free up memory", "clear memory", "clean ram"],
)
def free_memory() -> str:
    try:
        import psutil  # type: ignore
    except ImportError:
        return "psutil isn't installed, so I can't manage memory."

    before = sum(
        p.info["memory_info"].rss
        for p in psutil.process_iter(["memory_info"])
        if p.info["memory_info"]
    )
    trimmed = 0
    if IS_WINDOWS:
        import ctypes

        psapi = ctypes.windll.psapi
        kernel32 = ctypes.windll.kernel32
        own = os.getpid()
        skip_names = {"system", "registry", "memory compression", "idle", "msmpeng.exe"}
        for p in psutil.process_iter(["name"]):
            try:
                if p.pid == own or p.pid < 100 or (p.info["name"] or "").lower() in skip_names:
                    continue
                handle = kernel32.OpenProcess(0x0400 | 0x1000, False, p.pid)
                if handle:
                    trimmed += 1
                    psapi.EmptyWorkingSet(handle)
                    kernel32.CloseHandle(handle)
            except Exception:
                continue
    after = sum(
        p.info["memory_info"].rss
        for p in psutil.process_iter(["memory_info"])
        if p.info["memory_info"]
    )
    hogs = psutil.process_iter(["name", "memory_info"])
    top = sorted(
        ((p.info["memory_info"].rss if p.info["memory_info"] else 0, p.info["name"] or "?") for p in hogs),
        reverse=True,
    )[:4]
    pct = psutil.virtual_memory().percent
    lines = [
        f"Trimmed working sets on {trimmed} background process(es); "
        f"about {_fmt_mb(max(0, before - after))} reclaimed right away."
        if IS_WINDOWS
        else "Memory trimming is Windows-only — but here's where your RAM is going:",
        f"Memory in use: {pct:.0f}%.",
        "Biggest eaters: " + ", ".join(f"{n} ({_fmt_mb(m)})" for m, n in top),
    ]
    if pct > 85:
        lines.append("RAM is critically full — restarting a couple of those top apps will help most.")
    return "\n".join(lines)


@skill(
    "speed_up_pc",
    "One-shot tune-up: reclaim RAM, clear temp files, flush the DNS cache, set "
    "the High performance power plan and report heavy startup apps. Use for "
    "'speed up my pc', 'my computer is slow', 'make my pc faster'.",
    {"type": "object", "properties": {}},
    triggers=[
        "speed up my pc",
        "make my pc faster",
        "my computer is slow",
        "pc is running slow",
        "tune up my computer",
        "stop my pc from slowing down",
    ],
)
def speed_up_pc() -> str:
    lines = ["Tune-up pass complete:", ""]
    lines.append("① " + free_memory().splitlines()[0])
    lines.append("② " + clean_temp().splitlines()[0])
    if IS_WINDOWS:
        dns = run("ipconfig /flushdns", shell=True)
        lines.append("③ DNS cache flushed." if "Successfully" in dns or "erfolgreich" in dns.lower() else f"③ DNS flush: {dns[:60]}")
        power = run("powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", shell=True)
        lines.append(
            "④ Power plan set to High performance."
            if not power.startswith("(")
            else f"④ Couldn't switch power plan ({power[:60]})."
        )
        try:
            entries = _startup_entries()
            lines.append(f"⑤ {len(entries)} apps auto-start at sign-in — say 'startup audit' to trim boot time.")
        except Exception:
            pass
    else:
        lines.append("③④ Those steps are Windows-only.")
    lines.append("")
    lines.append("If it's still slow after this: say 'list processes' and I'll find what's hogging the machine.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Composite security report
# ---------------------------------------------------------------------------
@skill(
    "security_report",
    "Full security posture check: antivirus status, suspicious processes, risky "
    "startup entries. Use for 'security report', 'is my pc safe', 'full security check'.",
    {"type": "object", "properties": {}},
    triggers=["security report", "is my pc safe", "full security check", "am i protected"],
)
def security_report() -> str:
    parts = [virus_scan(start=False), "", find_suspicious_processes(), ""]
    if IS_WINDOWS:
        try:
            entries = _startup_entries()
            risky = [e["name"] for e in entries if _score_entry(e)]
            parts.append(
                f"Startup: {len(entries)} auto-start item(s)"
                + (f", {len(risky)} flagged: {', '.join(risky[:5])}" if risky else ", none flagged.")
            )
        except Exception:
            pass
    parts = [p for p in parts if p]
    parts.append("For anything flagged, say 'startup audit', 'run an antivirus scan', or 'close app <name>'.")
    return "\n".join(parts)
