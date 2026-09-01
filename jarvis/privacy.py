"""Privacy guard: keep secrets on this machine.

Three modes (JARVIS_PRIVACY):
  strict   — no cloud LLM calls at all; local (Ollama/offline) only
  guarded  — cloud allowed, but secrets are redacted from outbound text
  relaxed  — cloud allowed, no redaction

Every cloud call (and every redaction count, and every strict block) is
written to the audit ledger, so external calls are replayable evidence.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .config import config

_CLOUD_HOST_HINTS = ("api.openai.com", "api.groq.com", "openrouter", "anthropic",
                     "generativelanguage", "deepseek", "together", "mistral")

def is_cloud(provider: Any) -> bool:
    """Is this provider about to leave the machine?"""
    if getattr(provider, "name", "") == "openai":
        base = getattr(provider, "base", "") or ""
        return not any(h in base for h in ("127.0.0.1", "localhost", "0.0.0.0"))
    return getattr(provider, "name", "") not in {"", "ollama", "offline"}


_PATTERNS = [
    # API keys / tokens
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED-API-KEY]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED-GH-TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED-GH-TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED-SLACK-TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED-AWS-KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "[REDACTED-GOOGLE-KEY]"),
    # password / secret = value  (and JSON form)
    # (?!\[REDACTED) keeps a generic rule from eating a marker a specific
    # rule already planted, so auditability of WHICH key type it was survives.
    (re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token|bearer)\"\s*:\s*\"(?!\[REDACTED)[^\"]{4,}\""),
     r"\1\":\"[REDACTED]\""),
    (re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\s*[=:]\s*(?!\[REDACTED)\S{4,}"),
     r"\1=[REDACTED]"),
    # PEM private key bodies
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED-PRIVATE-KEY]"),
]


def redact(text: str) -> Tuple[str, int]:
    n = 0
    for rx, repl in _PATTERNS:
        text, c = rx.subn(repl, text)
        n += c
    return text, n


def scrub_messages(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    total = 0
    out = []
    for m in messages:
        if isinstance(m.get("content"), str):
            c, n = redact(m["content"])
            total += n
            out.append({**m, "content": c})
        else:
            out.append(m)
    return out, total


def guard(provider: Any, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the privacy mode to an outbound LLM payload. Raises in STRICT."""
    from . import state

    if not is_cloud(provider):
        return messages
    mode = (config.privacy_mode or "guarded").lower()
    if mode == "strict":
        state.audit("strict_block", provider=getattr(provider, "name", "?"),
                    model=getattr(provider, "model", "?"), redactions=0,
                    detail="cloud call blocked by STRICT privacy mode")
        from .brain.providers import ProviderError
        raise ProviderError(
            "Privacy mode is STRICT — no cloud calls. Use Ollama (local) or "
            "set JARVIS_PRIVACY=guarded/relaxed in Settings."
        )
    if mode == "guarded":
        cleaned, n = scrub_messages(messages)
        state.audit("cloud_call", provider=getattr(provider, "name", "?"),
                    model=getattr(provider, "model", "?"), redactions=n, detail="guarded send")
        return cleaned
    state.audit("cloud_call", provider=getattr(provider, "name", "?"),
                model=getattr(provider, "model", "?"), redactions=0, detail="relaxed send")
    return messages
