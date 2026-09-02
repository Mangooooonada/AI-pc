#!/usr/bin/env python3
"""Cut a named release: bumps VERSION, tags, pushes, makes a GitHub Release.

    python scripts/release.py patch
    python scripts/release.py minor "Codename"
    python scripts/release.py major "Codename"

Old releases are NEVER replaced — every tag + release stays on GitHub
(Releases page), and each one ships a JARVIS-vX.Y.Z.zip source bundle you
can re-download years later.
"""
from __future__ import annotations

import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(*args: str) -> str:
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(args)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def main() -> int:
    bump = sys.argv[1] if len(sys.argv) > 1 else "patch"
    codename = " ".join(sys.argv[2:]).strip()
    if bump not in {"patch", "minor", "major"}:
        raise SystemExit(__doc__)
    vf = ROOT / "VERSION"
    major, minor, patch = (int(x) for x in vf.read_text().strip().split("."))
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    ver = f"{major}.{minor}.{patch}"
    vf.write_text(ver + "\n")

    sh("git", "add", "VERSION")
    sh("git", "commit", "-m", f"Release v{ver}" + (f' "{codename}"' if codename else ""))
    title = f"v{ver}" + (f' — {codename}' if codename else "")
    sh("git", "tag", "-a", f"v{ver}", "-m", title)
    sh("git", "push", "origin", "--follow-tags")

    bundle = ROOT / "dist" / f"JARVIS-v{ver}.zip"
    bundle.parent.mkdir(exist_ok=True)
    sh("git", "archive", "--output", str(bundle), "--prefix", f"JARVIS-v{ver}/", f"v{ver}")
    sh("gh", "release", "create", f"v{ver}", "--title", title,
       "--notes", f"Jarvis {ver}{f' \"{codename}\"' if codename else ''}. "
                  "Source snapshot attached; extract and double-click JARVIS.bat.",
       str(bundle))
    print(f"Released {title} — old versions untouched on the Releases page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
