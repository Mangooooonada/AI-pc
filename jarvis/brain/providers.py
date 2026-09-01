"""LLM providers.

Each provider exposes chat(messages, tools) -> dict with keys:
    content    : str | None
    tool_calls : list of {"id", "name", "arguments"(dict)}
"""
from __future__ import annotations

import json
import re
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

    def chat_stream(self, messages: List[Dict], tools: Optional[List[Dict]], on_token) -> Dict[str, Any]:
        """SSE-streaming variant: on_token(text) fires as words arrive."""
        import json
        import requests

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": config.temperature,
            "stream": True,
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
            stream=True,
        )
        if r.status_code >= 400:
            raise ProviderError(f"OpenAI error {r.status_code}: {r.text[:200]}")

        content_parts: List[str] = []
        tool_acc: Dict[int, Dict[str, Any]] = {}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
                on_token(delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_acc.setdefault(idx, {"id": f"call_{idx}", "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]

        calls = [
            {"id": s["id"], "name": s["name"], "arguments": _parse_args(s["args"])}
            for _, s in sorted(tool_acc.items())
            if s["name"]
        ]
        return {"content": "".join(content_parts) or None, "tool_calls": calls}


class OllamaProvider:
    """Local models through Ollama — free, private, no API key."""

    name = "ollama"

    # Daily-driver preference when auto-picking: small modern models first
    # (fast on CPU), bigger brains deliberately last so nobody auto-lands on a
    # 19 GB model that streams two tokens a second.
    _PREFERRED = [
        "qwen3:8b", "qwen2.5:7b", "llama3.1:8b", "llama3.2:3b", "llama3.2",
        "qwen3:14b", "qwen2.5", "mistral-nemo", "gemma4", "gemma3",
        "qwen3:30b", "qwen3:32b", "qwen3", "llama3", "phi4", "mistral", "deepseek",
    ]

    def __init__(self) -> None:
        self.host = config.ollama_host.rstrip("/")
        configured = (config.ollama_model or "").strip()
        self.model = configured
        self.note: Optional[str] = None
        if not config.ollama_available():
            raise ProviderError(
                f"Ollama isn't reachable at {self.host}. Start it with 'ollama serve'."
            )
        installed = config.ollama_models()
        if not installed:
            return  # can't list models — assume the configured one will work
        if configured and self._model_installed(installed):
            return
        # The configured model isn't pulled. Rather than failing with an
        # error the user must act on, self-heal: use the best model that IS
        # installed and say so loudly.
        pick = self._best_installed(installed)
        big = [m for m in installed if m != pick and re.search(r":(\d{2,})b", m)
               and int(re.search(r":(\d+)b", m).group(1)) >= 14]
        hint = (
            f" Bigger brain available: {big[0]} — set OLLAMA_MODEL={big[0]} in .env "
            "for max smarts (slower per reply)."
        ) if big else ""
        if configured:
            self.note = (
                f"ollama: '{configured}' isn't pulled; using '{pick}' automatically."
                + hint
            )
        else:
            self.note = f"ollama: auto-picked '{pick}'." + hint
        self.model = pick

    def _best_installed(self, installed: List[str]) -> str:
        def score(m: str) -> int:
            for i, pref in enumerate(self._PREFERRED):
                if m == pref or m.startswith(pref):
                    return i
            return len(self._PREFERRED)

        return min(installed, key=score)

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
            "keep_alive": config.ollama_keep_alive,
            "options": {
                "temperature": config.temperature,
                "num_ctx": config.ollama_num_ctx,
            },
        }
        if config.ollama_think in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            payload["think"] = config.ollama_think in {"true", "1", "yes", "on"}
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

    def chat_stream(self, messages: List[Dict], tools: Optional[List[Dict]], on_token) -> Dict[str, Any]:
        """NDJSON-streaming variant: on_token(text) fires as words arrive."""
        import json
        import requests

        clean: List[Dict[str, Any]] = []
        for m in messages:
            c = {k: v for k, v in m.items() if k in {"role", "content", "tool_calls", "images"}}
            if c.get("content") is None:
                c["content"] = ""
            clean.append(c)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": clean,
            "stream": True,
            "keep_alive": config.ollama_keep_alive,
            "options": {
                "temperature": config.temperature,
                "num_ctx": config.ollama_num_ctx,
            },
        }
        if config.ollama_think in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            payload["think"] = config.ollama_think in {"true", "1", "yes", "on"}
        if tools:
            payload["tools"] = tools
        r = requests.post(f"{self.host}/api/chat", json=payload, timeout=180, stream=True)
        if r.status_code == 404:
            raise ProviderError(
                f"Model '{self.model}' isn't installed. Run: ollama pull {self.model}"
            )
        if r.status_code >= 400:
            raise ProviderError(f"Ollama error {r.status_code}: {r.text[:200]}")

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except ValueError:
                continue
            msg = chunk.get("message") or {}
            if msg.get("content"):
                content_parts.append(msg["content"])
                on_token(msg["content"])
            for i, c in enumerate(msg.get("tool_calls") or []):
                # Ollama delivers tool calls complete (usually one chunk).
                if c.get("function", {}).get("name"):
                    tool_calls.append(
                        {
                            "id": c.get("id") or f"call_{len(tool_calls)}_{i}",
                            "name": c["function"]["name"],
                            "arguments": _parse_args(c["function"].get("arguments")),
                        }
                    )
            if chunk.get("done"):
                break
        return {"content": "".join(content_parts) or None, "tool_calls": tool_calls}


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

    def chat_stream(self, messages: List[Dict], tools: Optional[List[Dict]], on_token) -> Dict[str, Any]:
        """Offline answers are instant anyway — emit them as one 'token'."""
        result = self.chat(messages, tools)
        if result.get("content"):
            on_token(result["content"])
        return result


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
                provider = OllamaProvider()
                if getattr(provider, "note", None):
                    errors.append(provider.note)
                return provider, errors
            if candidate == "offline":
                return OfflineProvider(), errors
        except ProviderError as exc:
            errors.append(f"{candidate}: {exc}")
    return OfflineProvider(), errors
