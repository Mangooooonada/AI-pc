"""File and folder skills, scoped to safe locations."""
from __future__ import annotations

import datetime as _dt
import os
import shutil
import subprocess
from pathlib import Path

from . import skill
from ._platform import IS_WINDOWS, powershell, run
from ..config import config

SAFE_ROOTS = [Path.home(), config.workspace]


def _resolve(path_str: str) -> Path:
    raw = (path_str or "").strip().strip("'\"")
    shortcuts = {
        "desktop": Path.home() / "Desktop",
        "documents": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "pictures": Path.home() / "Pictures",
        "music": Path.home() / "Music",
        "videos": Path.home() / "Videos",
        "home": Path.home(),
        "workspace": config.workspace,
        "": config.workspace,
    }
    low = raw.lower().strip("/\\")
    if low in shortcuts:
        return shortcuts[low]
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not p.is_absolute():
        p = config.workspace / p
    return p


def _is_safe(p: Path) -> bool:
    try:
        rp = p.resolve()
    except Exception:
        return False
    return any(str(rp).startswith(str(root.resolve())) for root in SAFE_ROOTS)


@skill(
    "list_folder",
    "List the contents of a folder. Accepts shortcuts like desktop, downloads, documents.",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Folder path or shortcut"}},
    },
    triggers=["what's in my {path} folder", "list my {path} folder", "show me my {path} folder"],
)
def list_folder(path: str = "workspace") -> str:
    p = _resolve(path)
    if not p.exists():
        return f"{p} doesn't exist."
    if not p.is_dir():
        return f"{p} is a file, not a folder."
    entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))[:40]
    if not entries:
        return f"{p} is empty."
    rows = [f"Contents of {p}:"]
    for e in entries:
        if e.is_dir():
            rows.append(f"  [dir]  {e.name}")
        else:
            try:
                size = e.stat().st_size
            except OSError:
                size = 0
            rows.append(f"  [file] {e.name} ({size / 1024:.0f} KB)")
    return "\n".join(rows)


@skill(
    "open_folder",
    "Open a folder in File Explorer.",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Folder path or shortcut"}},
    },
    triggers=["open my {path} folder", "open the folder {path}"],
)
def open_folder(path: str = "workspace") -> str:
    p = _resolve(path)
    if not p.exists():
        return f"{p} doesn't exist."
    try:
        if IS_WINDOWS:
            os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except (OSError, FileNotFoundError) as exc:
        return f"Couldn't open {p}: folder opener missing on this machine ({exc})."
    return f"Opened {p}."


@skill(
    "find_files",
    "Search for files by name pattern under a folder (defaults to your home folder).",
    {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Name fragment, e.g. 'invoice' or '*.pdf'"},
            "path": {"type": "string", "description": "Folder to search in"},
        },
        "required": ["pattern"],
    },
    triggers=["find files named {pattern}", "search for the file {pattern}"],
)
def find_files(pattern: str, path: str = "home") -> str:
    root = _resolve(path)
    pat = (pattern or "").strip()
    if not pat:
        return "What should I search for?"
    if "*" not in pat and "?" not in pat:
        pat = f"*{pat}*"
    hits: list[Path] = []
    for i, f in enumerate(root.rglob(pat)):
        if i > 20000:
            break
        if f.is_file():
            hits.append(f)
        if len(hits) >= 20:
            break
    if not hits:
        return f"No files matching '{pattern}' under {root}."
    return f"Found {len(hits)} match(es):\n" + "\n".join(f"  {h}" for h in hits)


@skill(
    "read_text_file",
    "Read the beginning of a text file and return its contents.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "max_chars": {"type": "integer", "description": "Character limit (default 3000)"},
        },
        "required": ["path"],
    },
)
def read_text_file(path: str, max_chars: int = 3000) -> str:
    p = _resolve(path)
    if not p.exists() or not p.is_file():
        return f"No file at {p}."
    if not _is_safe(p):
        return "That path is outside the folders I'm allowed to read."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Couldn't read it: {exc}"
    limit = max(200, min(20000, int(max_chars or 3000)))
    clipped = text[:limit]
    suffix = "\n… (truncated)" if len(text) > limit else ""
    return f"{p.name}:\n{clipped}{suffix}"


@skill(
    "write_note",
    "Save a note or any text into a file in the Jarvis workspace folder.",
    {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Text to save"},
            "filename": {"type": "string", "description": "Optional file name"},
        },
        "required": ["content"],
    },
    triggers=["take a note {content}", "make a note {content}", "note that {content}"],
)
def write_note(content: str, filename: str = "") -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = (filename or f"note-{stamp}.txt").strip()
    if not Path(name).suffix:
        name += ".txt"
    target = config.workspace / Path(name).name
    header = f"# Saved by Jarvis on {_dt.datetime.now():%Y-%m-%d %H:%M}\n\n"
    target.write_text(header + (content or ""), encoding="utf-8")
    return f"Note saved to {target}"


@skill(
    "clean_downloads",
    "Report how much space old files in the Downloads folder are taking, and "
    "optionally move files older than N days into an 'Old' subfolder.",
    {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Age threshold in days (default 30)"},
            "apply": {"type": "boolean", "description": "Actually move the files"},
        },
    },
    triggers=["clean my downloads", "tidy my downloads folder"],
)
def clean_downloads(days: int = 30, apply: bool = False) -> str:
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return "I can't find your Downloads folder."
    cutoff = _dt.datetime.now().timestamp() - int(days or 30) * 86400
    old = [f for f in downloads.glob("*") if f.is_file() and f.stat().st_mtime < cutoff]
    size = sum(f.stat().st_size for f in old) / 1e6
    if not old:
        return f"Nothing in Downloads older than {days} days. Tidy already."
    if not str(apply).lower() in {"true", "1", "yes"}:
        return (
            f"{len(old)} files older than {days} days, using {size:.0f} MB. "
            "Tell me to apply it and I'll move them into Downloads/Old."
        )
    dest = downloads / "Old"
    dest.mkdir(exist_ok=True)
    moved = 0
    for f in old:
        try:
            shutil.move(str(f), str(dest / f.name))
            moved += 1
        except Exception:
            continue
    return f"Moved {moved} files ({size:.0f} MB) into {dest}."
