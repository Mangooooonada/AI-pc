"""LLM providers.

Each provider exposes chat(messages, tools) -> dict with keys:
    content    : str | None
    tool_calls : list of {"id", "name", "arguments"(dict)}
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..config import config


class ProviderError(RuntimeError):
    pass


def _parse_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except Exception:
            return {}
    return {}


class OpenAIProvider:
    """Any OpenAI-compatible chat completions endpoint."""

    name = "openai"

    def __init__(self) -> None:
        if not config.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not set.")
        self.model = config.openai_model
        self.base = config.openai_base_url.rstrip("/")

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        import requests

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": config.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        r = requests.post(
            f"{self.base}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        if r.status_code == 401:
            raise ProviderError("OpenAI rejected the API key (401).")
        if r.status_code == 429:
            raise ProviderError("OpenAI rate limit or quota exceeded (429).")
        if r.status_code >= 400:
            raise ProviderError(f"OpenAI error {r.status_code}: {r.text[:200]}")
        msg = r.json()["choices"][0]["message"]
        calls = [
            {
                "id": c.get("id", f"call_{i}"),
                "name": c["function"]["name"],
                "arguments": _parse_args(c["function"].get("arguments")),
            }
            for i, c in enumerate(msg.get("tool_calls") or [])
        ]
        return {"content": msg.get("content"), "tool_calls": calls}


class OllamaProvider:
    """Local models through Ollama — free, private, no API key."""

    name = "ollama"

    def __init__(self) -> None:
        self.host = config.ollama_host.rstrip("/")
        self.model = config.ollama_model
        if not config.ollama_available():
            raise ProviderError(
                f"Ollama isn't reachable at {self.host}. Start it with 'ollama serve'."
            )
        # The server being up isn't enough — if the configured model was
        # never pulled, every chat call 404s and Jarvis "falls back to
        # offline". Check it now so the user gets the exact fix.
        installed = config.ollama_models()
        if installed and not self._model_installed(installed):
            names = ", ".join(installed)
            raise ProviderError(
                f"Model '{self.model}' isn't installed. Run: ollama pull {self.model}  "
                f"(installed: {names} — or set OLLAMA_MODEL={installed[0]} in .env)"
            )

    def _model_installed(self, installed: List[str]) -> bool:
        want = self.model
        return any(
            m == want or m == f"{want}:latest" or m.split(":")[0] == want
            for m in installed
        )

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        import requests

        # Ollama's API doesn't accept OpenAI's "tool_call_id" field.
        clean: List[Dict[str, Any]] = []
        for m in messages:
            c = {k: v for k, v in m.items() if k in {"role", "content", "tool_calls", "images"}}
            if c.get("content") is None:
                c["content"] = ""
            clean.append(c)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": clean,
            "stream": False,
            "options": {"temperature": config.temperature},
        }
        if tools:
            payload["tools"] = tools
        r = requests.post(f"{self.host}/api/chat", json=payload, timeout=180)
        if r.status_code == 404:
            raise ProviderError(
                f"Model '{self.model}' isn't installed. Run: ollama pull {self.model}"
            )
        if r.status_code >= 400:
            raise ProviderError(f"Ollama error {r.status_code}: {r.text[:200]}")
        msg = r.json().get("message", {})
        calls = [
            {
                "id": f"call_{i}",
                "name": c["function"]["name"],
                "arguments": _parse_args(c["function"].get("arguments")),
            }
            for i, c in enumerate(msg.get("tool_calls") or [])
        ]
        return {"content": msg.get("content"), "tool_calls": calls}


class OfflineProvider:
    """No model at all: keyword intent matching plus canned conversation.

    This keeps Jarvis genuinely useful before you install anything.
    """

    name = "offline"

    GREETINGS = {
        "hello": "Hello, {title}. Systems nominal.",
        "hi": "Hello, {title}. What do you need?",
        "hey": "At your service, {title}.",
        "good morning": "Good morning, {title}. Ready when you are.",
        "good night": "Good night, {title}. I'll keep the lights on.",
        "thanks": "Any time, {title}.",
        "thank you": "My pleasure, {title}.",
        "how are you": "All processes green, {title}. Yourself?",
        "who are you": (
            "I'm {name}, your desktop assistant. Right now I'm running in offline mode — "
            "keyword skills only. Install Ollama or add an OpenAI key and I get much smarter."
        ),
        "bye": "Goodbye, {title}.",
        "goodbye": "Goodbye, {title}.",
    }

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        from ..skills import match_offline

        user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user = (m.get("content") or "").strip()
                break

        low = " ".join(user.lower().split()).strip("?!.,")
        for key, reply in self.GREETINGS.items():
            if low == key or low.startswith(key + " ") or low.endswith(" " + key):
                return {
                    "content": reply.format(title=config.user_title, name=config.name),
                    "tool_calls": [],
                }

        hit = match_offline(user)
        if hit:
            name, args = hit
            return {
                "content": None,
                "tool_calls": [{"id": "call_0", "name": name, "arguments": args}],
            }
        return {
            "content": (
                f"I'm in offline mode, {config.user_title}, so I only understand direct commands "
                "right now — things like \"open spotify\", \"set volume to 30\", \"what's the weather\", "
                "or \"take a screenshot\". Say \"what can you do\" for the full list. "
                "To have a real conversation, install Ollama (free) or add an OpenAI key."
            ),
            "tool_calls": [],
        }


def get_provider(force: Optional[str] = None):
    """Build the best available provider, degrading gracefully."""
    choice = (force or config.resolved_provider()).lower()
    errors: List[str] = []
    order = [choice] + [p for p in ("openai", "ollama", "offline") if p != choice]
    for candidate in order:
        try:
            if candidate == "openai":
                return OpenAIProvider(), errors
            if candidate == "ollama":
                return OllamaProvider(), errors
            if candidate == "offline":
                return OfflineProvider(), errors
        except ProviderError as exc:
            errors.append(f"{candidate}: {exc}")
    return OfflineProvider(), errors
