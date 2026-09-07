"""Developer helpers: git status/log/diff and Docker ps/logs/restart.

Everything degrades gracefully — if git or Docker isn't installed, or the
workspace isn't a repo, you get a plain-English explanation, never a traceback.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from . import skill
from ..config import config


def _git(args: List[str], cwd: Path, timeout: int = 10) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if _win() else 0,
        )
    except subprocess.TimeoutExpired:
        return False, "(git took too long — is the repo huge or on a slow drive?)"
    except Exception as exc:
        return False, f"(couldn't run git: {exc})"
    out = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, out


def _docker(args: List[str], timeout: int = 12) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if _win() else 0,
        )
    except subprocess.TimeoutExpired:
        return False, "(Docker took too long — is the daemon up?)"
    except Exception as exc:
        return False, f"(couldn't run docker: {exc})"
    out = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, out


def _win() -> bool:
    import sys
    return sys.platform.startswith("win")


def _clip(text: str, max_lines: int = 40, max_chars: int = 2600) -> str:
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… ({len(text.splitlines()) - max_lines} more lines — ask for specifics)"]
    text = "\n".join(lines)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _find_repo() -> Optional[Path]:
    """Workspace if it's a repo, else our own install dir if that is."""
    if not shutil.which("git"):
        return None
    for candidate in (config.workspace, Path(__file__).resolve().parent.parent.parent):
        ok, top = _git(["rev-parse", "--show-toplevel"], candidate)
        if ok and top and not top.startswith("("):
            return Path(top.strip())
    return None


def _no_git() -> str:
    return ("Git isn't installed on this PC (or isn't on PATH), so I can't "
            "look at repositories. Install Git for Windows and I'll pick it up.")


def _no_repo() -> str:
    return (f"Neither your workspace ({config.workspace}) nor my install folder is a "
            "git repository. Point the JARVIS_WORKSPACE setting at a repo and I'll "
            "watch it for you.")


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------
@skill(
    "git_status",
    "Show a short git status (branch, ahead/behind, changed files) for the workspace repository.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["git status", "what's changed in git", "what is changed in git",
              "whats changed in git", "git summary", "any uncommitted changes"],
)
def git_status() -> str:
    if not shutil.which("git"):
        return _no_git()
    repo = _find_repo()
    if not repo:
        return _no_repo()
    ok, branch = _git(["status", "--short", "--branch", "--untracked-files=normal"], repo)
    if not ok:
        return f"Git didn't like that: {_clip(branch, 6)}"
    # ahead/behind comes from the ## line; count files for a one-liner
    lines = branch.splitlines()
    head = lines[0] if lines else ""
    changed = [ln for ln in lines[1:] if ln.strip()]
    if not changed:
        return f"{head}\nWorking tree clean — nothing uncommitted."
    return f"{head}\n{len(changed)} path(s) touched:\n{_clip(chr(10).join(changed), 30)}"


@skill(
    "git_log",
    "Show recent commits (oneline, decorated) for the workspace repository.",
    {
        "type": "object",
        "properties": {"count": {"type": "integer", "description": "How many commits, default 8"}},
        "required": [],
    },
    triggers=["git log", "git history", "recent commits", "show recent commits",
              "last {count} commits", "show the last {count} commits"],
)
def git_log(count: int | str = 8) -> str:
    if not shutil.which("git"):
        return _no_git()
    repo = _find_repo()
    if not repo:
        return _no_repo()
    try:
        n = max(1, min(30, int(str(count).strip() or 8)))
    except Exception:
        n = 8
    ok, out = _git(["log", f"-{n}", "--oneline", "--decorate", "--date-order"], repo)
    if not ok or not out:
        return (f"Git didn't like that: {_clip(out, 6)}" if out
                else "No commits yet in this repo.")
    return f"Repo {repo.name} — last {n} commit(s):\n{_clip(out, 30)}"


@skill(
    "git_diff_summary",
    "Summarize uncommitted changes (diff --stat, staged + unstaged) for the workspace repository.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["git diff", "show the git diff", "what did i change in git",
              "what did i change", "show my changes", "diff summary"],
)
def git_diff_summary() -> str:
    if not shutil.which("git"):
        return _no_git()
    repo = _find_repo()
    if not repo:
        return _no_repo()
    ok_u, unstaged = _git(["diff", "--stat"], repo)
    ok_s, staged = _git(["diff", "--stat", "--cached"], repo)
    if not (ok_u and ok_s):
        return f"Git didn't like that: {_clip(unstaged or staged, 6)}"
    parts = []
    if staged:
        parts.append("Staged:\n" + _clip(staged, 20))
    if unstaged:
        parts.append("Unstaged:\n" + _clip(unstaged, 20))
    if not parts:
        return "Working tree clean — no staged or unstaged diffs."
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Docker
# --------------------------------------------------------------------------
def _no_docker() -> str:
    return ("Docker isn't installed on this PC (or the CLI isn't on PATH). "
            "Install Docker Desktop and I can peek at your containers.")


def _list_containers(all_: bool = False) -> Tuple[bool, List[Tuple[str, str, str]]]:
    """(ok, [(name, image, status), ...])"""
    ok, out = _docker(["ps", *(["--all"] if all_ else []),
                       "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
    if not ok:
        return False, []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append((parts[0], parts[1], parts[2]))
    return True, rows


def _resolve_container(name: str, running_only: bool) -> Tuple[Optional[str], str]:
    """Fuzzy-find a container by (partial) name. Returns (name, error_message)."""
    if not shutil.which("docker"):
        return None, _no_docker()
    ok, rows = _list_containers(all_=not running_only)
    if not ok:
        return None, ("Docker isn't answering — is the daemon / Docker Desktop running?")
    if not rows:
        scope = "running" if running_only else "any"
        return None, f"I don't see {scope} containers on this machine."
    want = (name or "").strip().lower()
    exact = [r for r in rows if r[0].lower() == want]
    part = exact or [r for r in rows if want and want in r[0].lower()]
    if len(part) == 1:
        return part[0][0], ""
    if len(part) > 1:
        opts = ", ".join(r[0] for r in part)
        return None, f"'{name}' matches a few containers ({opts}). Which one did you mean?"
    opts = ", ".join(r[0] for r in rows)
    return None, f"There's no container called '{name}'. I can see: {opts}."


@skill(
    "docker_ps",
    "List running Docker containers (name, image, status).",
    {"type": "object", "properties": {}, "required": []},
    triggers=["docker ps", "list docker containers", "what containers are running",
              "what's running in docker", "show docker containers"],
)
def docker_ps() -> str:
    if not shutil.which("docker"):
        return _no_docker()
    ok, rows = _list_containers()
    if not ok:
        return "Docker isn't answering — is the daemon / Docker Desktop running?"
    if not rows:
        ok_all, rows_all = _list_containers(all_=True)
        if ok_all and rows_all:
            names = ", ".join(r[0] for r in rows_all)
            return f"Nothing running right now. Stopped containers exist though: {names}."
        return "No containers on this machine at all."
    lines = [f"{len(rows)} running container(s):"]
    lines += [f"  • {name}  ({image}) — {status}" for name, image, status in rows[:20]]
    return "\n".join(lines)


@skill(
    "docker_logs",
    "Show the tail of a Docker container's logs (by exact or partial name).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Container name or a unique fragment"},
            "lines": {"type": "integer", "description": "How many log lines, default 40"},
        },
        "required": ["name"],
    },
    triggers=["docker logs {name}", "docker logs for {name}", "show me docker logs for {name}",
              "logs for the {name} container", "logs for {name}"],
)
def docker_logs(name: str = "", lines: int | str = 40) -> str:
    container, err = _resolve_container(name, running_only=False)
    if not container:
        return err
    try:
        n = max(1, min(300, int(str(lines).strip() or 40)))
    except Exception:
        n = 40
    ok, out = _docker(["logs", "--tail", str(n), container], timeout=15)
    if not ok:
        return f"Couldn't pull logs for {container}: {_clip(out, 6)}"
    if not out:
        return f"{container} hasn't logged anything yet."
    return f"Last {n} line(s) from {container}:\n{_clip(out, 60)}"


@skill(
    "docker_restart",
    "Restart a Docker container by exact or partial name. Reports the result.",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Container name or a unique fragment"}},
        "required": ["name"],
    },
    triggers=["restart docker container {name}", "docker restart {name}",
              "restart container {name}", "restart the {name} container"],
)
def docker_restart(name: str = "") -> str:
    container, err = _resolve_container(name, running_only=True)
    if not container:
        return err
    ok, out = _docker(["restart", container], timeout=60)
    if ok:
        return f"{container} restarted. Give it a few seconds to come back up."
    return f"Restart of {container} failed: {_clip(out, 6)}"
