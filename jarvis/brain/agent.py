"""The agent loop: user text in, tool calls executed, spoken reply out."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..config import config
from ..skills import REGISTRY, pack_tools, run_skill
from .prompts import system_prompt
from .providers import ProviderError, get_provider

MAX_TOOL_ROUNDS = 4


@dataclass
class Turn:
    """The result of one exchange."""

    reply: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    provider: str = "offline"
    error: Optional[str] = None


class Agent:
    def __init__(self, provider: Optional[str] = None) -> None:
        self.provider, self.provider_errors = get_provider(provider)
        self.history: List[Dict[str, Any]] = []

    # -- state -------------------------------------------------------------
    @property
    def provider_name(self) -> str:
        return getattr(self.provider, "name", "offline")

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": getattr(self.provider, "model", "keyword engine"),
            "skills": len(REGISTRY),
            "platform": config.platform_name,
            "notes": (
                [n for n in self.provider_errors if n]
                + (([pnote] if (pnote := getattr(self.provider, "note", None))
                    and pnote not in self.provider_errors else []))
            ),
            "assistant": config.name,
        }

    def reload_provider(self, provider: Optional[str] = None) -> Dict[str, Any]:
        self.provider, self.provider_errors = get_provider(provider)
        return self.status()

    def reset(self) -> None:
        self.history.clear()

    # -- main loop ---------------------------------------------------------
    def ask(
        self,
        text: str,
        on_action: Optional[Callable[[str, str], None]] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> Turn:
        text = (text or "").strip()
        if not text:
            return Turn(reply="", provider=self.provider_name)

        # Booted before the brain was ready? While offline we re-run the
        # provider pick each turn (one quick local ping), so the moment
        # Ollama/OpenAI becomes reachable Jarvis takes it — no restart,
        # no button to press.
        if self.provider_name == "offline":
            try:
                upgraded, up_errors = get_provider(None)
                if getattr(upgraded, "name", "offline") != "offline":
                    self.provider = upgraded
                    self.provider_errors = up_errors + [
                        f"brain came online via {self.provider_name} — real answers are back"
                    ]
            except Exception:
                pass  # stay offline this turn

        self.history.append({"role": "user", "content": text})
        self._trim()
        try:
            from .automem import maybe_autoremember
            maybe_autoremember(text)
        except Exception:
            pass  # auto-memory must never break a conversation

        actions: List[Dict[str, Any]] = []
        tools, hidden_tools = pack_tools(text)
        error: Optional[str] = None
        degraded = False  # real brain failed this turn → offline stand-in

        for _ in range(MAX_TOOL_ROUNDS):
            prompt = system_prompt()
            if hidden_tools:
                prompt += (
                    f"\nNote: {hidden_tools} less-relevant skills are hidden this turn to keep you "
                    "fast. If none of the listed tools fit, just say you cannot and suggest the user "
                    "phrase it as a short command — the right skill appears on the next turn."
                )
            messages = [{"role": "system", "content": prompt}] + self.history
            from ..privacy import guard as _privacy_guard
            _resolved = (self.provider.resolve(messages)
                         if hasattr(self.provider, "resolve") else self.provider)
            messages = _privacy_guard(_resolved, messages)
            try:
                stream_fn = getattr(self.provider, "chat_stream", None)
                if on_token and callable(stream_fn):
                    result = stream_fn(messages, tools, on_token)
                else:
                    result = self.provider.chat(messages, tools)
            except ProviderError as exc:
                error = str(exc)
                degraded = True
                # Stand in with the offline brain for THIS turn only, keeping
                # the configured provider so the next message retries it —
                # a single Ollama hiccup must not downgrade the whole
                # session (previously this swapped self.provider for good).
                from .providers import OfflineProvider

                self.provider_errors = [error]
                stand_in = OfflineProvider()
                if on_token:
                    result = stand_in.chat_stream(messages, tools, on_token)
                else:
                    result = stand_in.chat(messages, tools)
            except Exception as exc:  # network blips etc.
                error = f"{type(exc).__name__}: {exc}"
                return Turn(
                    reply=f"My connection to the model dropped, {config.user_title}. ({error})",
                    actions=actions,
                    provider=self.provider_name,
                    error=error,
                )

            calls = result.get("tool_calls") or []
            content = (result.get("content") or "").strip()

            if not calls:
                reply = content or "Done."
                self.history.append({"role": "assistant", "content": reply})
                self._trim()
                return Turn(reply=reply, actions=actions,
                            provider=getattr(self.provider, "last_turn_label", None)
                                or self.provider_name, error=error)

            # Record the assistant's tool-calling turn.
            self.history.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": json.dumps(c["arguments"]),
                            },
                        }
                        for c in calls
                    ],
                }
            )

            for call in calls:
                output = run_skill(call["name"], call["arguments"])
                actions.append(
                    {"skill": call["name"], "arguments": call["arguments"], "result": output}
                )
                if on_action:
                    try:
                        on_action(call["name"], output)
                    except Exception:
                        pass
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": output,
                    }
                )

            # The offline brain can't summarise tool output, so return it directly.
            # (Also applies when a real brain failed and offline stood in this
            # turn — otherwise the loop would keep re-firing the same intent.)
            if self.provider_name == "offline" or degraded:
                reply = "\n".join(a["result"] for a in actions[-len(calls):])
                self.history.append({"role": "assistant", "content": reply})
                self._trim()
                return Turn(reply=reply, actions=actions, provider="offline", error=error)

        # Ran out of tool rounds.
        summary = actions[-1]["result"] if actions else "I got stuck in a loop there."
        self.history.append({"role": "assistant", "content": summary})
        return Turn(reply=summary, actions=actions,
                    provider=getattr(self.provider, "last_turn_label", None)
                        or self.provider_name, error=error)

    def _trim(self) -> None:
        limit = max(4, config.max_history)
        if len(self.history) <= limit:
            return
        # Never start the trimmed history on an orphaned tool result.
        cut = len(self.history) - limit
        while cut < len(self.history) and self.history[cut].get("role") == "tool":
            cut += 1
        self.history = self.history[cut:]
