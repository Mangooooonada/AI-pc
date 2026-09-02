"""LLM providers.

Each provider exposes chat(messages, tools) -> dict with keys:
    content    : str | None
    tool_calls : list of {"id", "name", "arguments"(dict)}
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..config import config

log = logging.getLogger(__name__)

# Smells like a heavy turn? (long or code/analysis-flavoured) — shared by the
# Ollama dual-brain router and the cross-brain RouterProvider.
HEAVY_PAT = re.compile(
    r"(```|\bcode\b|\bdebug\b|\brefactor\b|\bessay\b|\banaly[sz]e\b|"
    r"\bcompare\b|\bexplain\b|\bwrite (?:a|an|me|some)\b|\bdesign\b|"
    r"\boptimi[sz]e\b|\bstory\b|\breport\b|\bplan\b|\bwalk me through\b)",
    re.I,
)


def is_heavy_turn(text: str) -> bool:
    t = (text or "").strip()
    return len(t) > 240 or bool(HEAVY_PAT.search(t))


class ProviderError(RuntimeError):
    pass


_POISONED: set = set()  # provider names that AUTH-FAILED this session


def poison(name: str, reason: str) -> None:
    """401/403 rejections are permanent for the session: stop proposing that brain."""
    if name in _POISONED:
        return
    _POISONED.add(name)
    try:
        from .. import state as _st
        _st.add_notification(
            f"🔑 Brain refused: {name} rejected its credentials — skipping it "
            f"for this session ({reason[:60]}). Fix the key in Settings.")
    except Exception:
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
        if "openai" in _POISONED:
            raise ProviderError("OpenAI rejected its key earlier this session — skipped.")
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
            poison("openai", "invalid API key (401)")
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
        # Set to True when Ollama says the model "does not support tools" —
        # we then quietly run without skills for the rest of the session.
        self._no_tools = False
        # Dual-brain routing cache: is OLLAMA_MODEL_BIG installed?
        self._big_ok: Optional[bool] = None
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

    def _model_installed(self, installed: List[str], want: str = "") -> bool:
        want = want or self.model
        return any(
            m == want or m == f"{want}:latest" or m.split(":")[0] == want
            for m in installed
        )

    # Ollama parses model output for tool calls with a brace-matching
    # heuristic; a truncated or malformed call makes the whole REQUEST fail
    # with HTTP 400 "Value looks like object, but can't find closing '}'
    # symbol". Small models do this often; deep conversations with big tool
    # schemas make truncation more likely.
    _TOOL_PARSE_SIGNS = ("closing '}'", "looks like object")
    _NO_TOOLS_NUDGE = (
        "Tool use is unavailable right now. Answer the user's last message "
        "directly in plain prose — no JSON, no code blocks, no curly braces."
    )

    def _route_model(self, messages: List[Dict]) -> str:
        """Dual-brain: quick model for chatter, OLLAMA_MODEL_BIG for heavy turns."""
        big = (getattr(config, "ollama_model_big", "") or "").strip()
        if not big:
            return self.model
        if getattr(self, "_big_ok", None) is None:
            self._big_ok = self._model_installed(config.ollama_models(), want=big)
            if not self._big_ok:
                log.warning(
                    "ollama: heavy brain '%s' isn't pulled; staying on '%s'", big, self.model
                )
        if not self._big_ok:
            return self.model
        last = next(
            ((m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if is_heavy_turn(last) and big != self.model:
            log.info("ollama: heavy turn routed to '%s'", big)
            return big
        return self.model

    def _build_payload(self, messages: List[Dict], tools: Optional[List[Dict]],
                       stream: bool) -> Dict[str, Any]:
        # Ollama's API doesn't accept OpenAI's "tool_call_id" field.
        clean: List[Dict[str, Any]] = []
        for m in messages:
            c = {k: v for k, v in m.items() if k in {"role", "content", "tool_calls", "images"}}
            if c.get("content") is None:
                c["content"] = ""
            clean.append(c)
        payload: Dict[str, Any] = {
            "model": self._route_model(messages),
            "messages": clean,
            "stream": stream,
            "keep_alive": config.ollama_keep_alive,
            "options": {
                "temperature": config.temperature,
                "num_ctx": config.ollama_num_ctx,
            },
        }
        think_cfg = str(config.ollama_think or "").strip().lower()
        if think_cfg in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            payload["think"] = think_cfg in {"true", "1", "yes", "on"}
        if tools and not self._no_tools:
            payload["tools"] = tools
            # Thinking + tools is a buggy combo upstream: qwen3's brace-heavy
            # reasoning gets mistaken for tool calls → the HTTP 400 above.
            # Unless the user asked for thinking explicitly, keep it off here.
            if "think" not in payload and "qwen3" in self.model.lower():
                payload["think"] = False
        return payload

    def _families(self, name: str) -> str:
        """'qwen3:8b' -> 'qwen3' (same family = same template = same bugs)."""
        return name.split(":")[0]

    def _repick_model(self, avoid: str) -> str:
        """Pick the best installed model that ISN'T the one choking — ideally
        from a different family, since parser bugs run in families."""
        try:
            installed = [m for m in config.ollama_models()
                         if self._families(m) != self._families(avoid)]
        except Exception:
            installed = []
        if not installed:
            try:
                installed = [m for m in config.ollama_models() if m != avoid]
            except Exception:
                return ""
        return self._best_installed(installed) if installed else ""

    def _post_chat(self, payload: Dict[str, Any]):
        import requests

        stream = bool(payload.get("stream"))
        url = f"{self.host}/api/chat"
        r = requests.post(url, json=payload, timeout=180, stream=stream)
        if r.status_code == 400 and "tools" in payload:
            low = r.text.lower()
            if "does not support tools" in low:
                # This model has no tool template at all — remember it and
                # quietly run without skills for the rest of the session.
                self._no_tools = True
                log.warning(
                    "ollama: '%s' does not support tools; skills disabled for this session",
                    self.model,
                )
                payload = {k: v for k, v in payload.items() if k != "tools"}
                r = requests.post(url, json=payload, timeout=180, stream=stream)
            elif any(s in low for s in self._TOOL_PARSE_SIGNS):
                # Heal ladder for a botched tool call — each rung is safer:
                #  1) same model, no tools, plain-text nudge
                #  2) clean room: drop the whole history (it can trip the
                #     parser), keep only system + the last user message
                #  3) a completely different installed model
                log.warning(
                    "ollama: malformed tool call from '%s'; retrying without tools",
                    self.model,
                )
                payload = {k: v for k, v in payload.items() if k != "tools"}
                payload["messages"] = payload["messages"] + [
                    {"role": "system", "content": self._NO_TOOLS_NUDGE}
                ]
                r = requests.post(url, json=payload, timeout=180, stream=stream)
                if r.status_code == 400 and any(
                    s in r.text.lower() for s in self._TOOL_PARSE_SIGNS
                ):
                    log.warning("ollama: still choking — clean-room retry (no history)")
                    keep = [m for m in payload["messages"] if m.get("role") == "system"][:1]
                    keep += [m for m in payload["messages"] if m.get("role") == "user"][-1:]
                    keep.append({"role": "system", "content": self._NO_TOOLS_NUDGE})
                    clean = {k: v for k, v in payload.items() if k not in {"tools", "messages"}}
                    clean["messages"] = keep
                    r = requests.post(url, json=clean, timeout=180, stream=stream)
                if r.status_code == 400 and any(
                    s in r.text.lower() for s in self._TOOL_PARSE_SIGNS
                ):
                    alt = self._repick_model(self.model)
                    if alt:
                        log.error(
                            "ollama: '%s' cannot be coaxed into behaving — "
                            "switching this session to '%s'", self.model, alt,
                        )
                        old = self.model
                        self.model, self._big_ok = alt, None
                        self.note = (
                            f"'{old}' kept mangling tool calls; using '{alt}' "
                            f"for the rest of this session. Pin it with OLLAMA_MODEL={alt} in .env."
                        )
                        heal = {k: v for k, v in payload.items() if k != "tools"}
                        heal["model"] = alt
                        r = requests.post(url, json=heal, timeout=180, stream=stream)
                        if r.status_code >= 400:
                            self.model = old  # didn't help either — restore
        if r.status_code == 404:
            raise ProviderError(
                f"Model '{self.model}' isn't installed. Run: ollama pull {self.model}"
            )
        if r.status_code >= 400:
            if any(s in r.text.lower() for s in self._TOOL_PARSE_SIGNS):
                raise ProviderError(
                    f"'{self.model}' is choking on its own tool calls (Ollama HTTP 400) "
                    "even with skills and history fully stripped. Try again, switch "
                    "models in Settings (llama3.1:8b is the most reliable skill model), "
                    "or update Ollama — newer releases ship fixed tool templates."
                )
            raise ProviderError(f"Ollama error {r.status_code}: {r.text[:200]}")
        return r

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        payload = self._build_payload(messages, tools, stream=False)
        r = self._post_chat(payload)
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
        payload = self._build_payload(messages, tools, stream=True)
        r = self._post_chat(payload)

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


class RouterProvider:
    """Cross-brain routing: heavy turns → cloud brain, quick/private → local.

    Both brains receive the SAME conversation history (the agent owns it, not
    the provider), so Groq sees what Ollama heard and vice-versa. STRICT
    privacy mode forces every turn to the local brain.
    """

    name = "router"

    def __init__(self, fast, heavy) -> None:
        self.fast = fast    # local, private (usually OllamaProvider)
        self.heavy = heavy  # big cloud brain (usually OpenAIProvider/Groq)
        self.model = f"{fast.model} ⇄ {heavy.model}"
        self.note = f"router: quick/private → {fast.model} · heavy → {heavy.model}"
        self.last_route = "starting"

    def resolve(self, messages: List[Dict]):
        """Which backend answers THIS turn."""
        if (getattr(config, "privacy_mode", "") or "guarded").lower() == "strict":
            self.last_route = "local (strict privacy)"
            return self.fast
        last = next(
            ((m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if is_heavy_turn(last):
            self.last_route = f"heavy → {self.heavy.model}"
            return self.heavy
        self.last_route = f"local → {self.fast.model}"
        return self.fast

    @property
    def last_turn_label(self) -> str:
        return f"router·{self.last_route}"

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        return self.resolve(messages).chat(messages, tools)

    def chat_stream(self, messages, tools, on_token):
        sub = self.resolve(messages)
        stream_fn = getattr(sub, "chat_stream", None)
        if callable(stream_fn):
            return stream_fn(messages, tools, on_token)
        out = sub.chat(messages, tools)
        if out.get("content"):
            on_token(out["content"])
        return out


class RemoteJarvisProvider:
    """Use another running Jarvis server as this Jarvis's brain, over HTTP.

    Speaks our own protocol: GET /api/status for the handshake, then
    POST /api/chat {"message": ...} per turn. Honours the pairing-key lock
    (X-Jarvis-Key) from the network-sharing feature.

    IMPORTANT: tool calls execute on *that* machine, on *its* files — this
    is conversation-plus-remote-skills, not local PC control. For a remote
    brain with LOCAL tool execution, use an OpenAI-compatible endpoint
    instead (the 'openai' provider).
    """

    name = "remote"

    def __init__(self) -> None:
        url = (getattr(config, "remote_url", "") or "").strip()
        if not url:
            raise ProviderError(
                "JARVIS_REMOTE_URL isn't set — point it at a running Jarvis server."
            )
        if "remote" in _POISONED:
            raise ProviderError("Remote brain rejected its key earlier this session — skipped.")
        self.base = url.rstrip("/")
        self.model = "remote jarvis"
        self.note: Optional[str] = None
        try:
            import requests

            r = requests.get(f"{self.base}/api/status", headers=self._headers(), timeout=5)
        except Exception as exc:
            raise ProviderError(
                f"Remote brain unreachable at {self.base} ({type(exc).__name__}). Is that "
                "server still running? Arena sandbox URLs die when their sandbox sleeps."
            )
        if r.status_code in {401, 403}:
            raise ProviderError(
                "The remote brain is locked — set JARVIS_REMOTE_KEY to its pairing key."
            )
        if r.status_code >= 400:
            raise ProviderError(f"Remote brain answered {r.status_code} at {self.base}.")
        try:
            st = r.json()
            self.model = f"{st.get('provider', '?')} @ {st.get('hostname', 'remote')}"
            self.note = (
                f"remote brain: {self.base} → {st.get('provider', '?')} "
                f"({st.get('model', '?')})"
            )
        except Exception:
            pass

    def _headers(self) -> Dict[str, str]:
        key = (getattr(config, "remote_key", "") or "").strip()
        return {"X-Jarvis-Key": key} if key else {}

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        import requests

        # The remote keeps its own conversation history — we forward the
        # freshest user message each turn and let it carry the thread.
        last = next(
            ((m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        r = requests.post(
            f"{self.base}/api/chat",
            json={"message": last},
            headers=self._headers(),
            timeout=180,
        )
        if r.status_code in {401, 403}:
            poison("remote", "pairing key rejected")
            raise ProviderError("Remote brain rejected the pairing key (401/403).")
        if r.status_code >= 400:
            raise ProviderError(f"Remote brain error {r.status_code}: {r.text[:200]}")
        data = r.json()
        return {"content": data.get("reply") or "", "tool_calls": []}

    def chat_stream(self, messages, tools, on_token):
        # Simplest contract: the remote answers whole; emit it as one chunk.
        out = self.chat(messages, tools)
        if out.get("content"):
            on_token(out["content"])
        return out


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
                f"My usual brain isn't answering right now, {config.user_title}, so I'm on the "
                "offline engine — direct commands only: \"open spotify\", \"set volume to 30\", "
                "\"what's the weather\", \"take a screenshot\". Say \"what can you do\" for the "
                "full list. If Ollama is running this clears itself on the next message."
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
    order = [choice] + [p for p in ("remote", "openai", "ollama", "offline") if p != choice]
    for candidate in order:
        try:
            if candidate == "auto":
                # Pair fast-local with heavy-cloud and route per turn. If only
                # one backend exists, use it alone; if neither, keep falling.
                fast = heavy = None
                try:
                    fast = OllamaProvider()
                except ProviderError as exc:
                    errors.append(f"ollama: {exc}")
                try:
                    heavy = OpenAIProvider()
                except ProviderError as exc:
                    errors.append(f"cloud: {exc}")
                if fast and heavy:
                    router = RouterProvider(fast, heavy)
                    errors.append(router.note)
                    for sub in (fast, heavy):
                        if getattr(sub, "note", None):
                            errors.append(sub.note)
                    return router, errors
                if fast or heavy:
                    only = fast or heavy
                    if getattr(only, "note", None):
                        errors.append(only.note)
                    return only, errors
                continue
                provider = RemoteJarvisProvider()
                if getattr(provider, "note", None):
                    errors.append(provider.note)
                return provider, errors
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
