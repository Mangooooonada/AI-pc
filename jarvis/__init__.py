"""Jarvis — an AI assistant that actually runs your PC."""
from pathlib import Path as _Path

_VF = _Path(__file__).resolve().parent.parent / "VERSION"
try:
    __version__ = _VF.read_text(encoding="utf-8").strip() or "0.0.0-dev"
except OSError:                     # packaged / frozen builds bundle no root file
    __version__ = "1.2.0"
