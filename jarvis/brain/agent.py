"""The agent loop: user text in, tool calls executed, spoken reply out."""
from __future__ import annotations

import json
import re
import threading
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
        # Serializes conversations: desktop + phone + a scheduled routine all
        # hitting at once must queue, not interleave the history.
        self._busy = threading.Lock()
        self._restore_history()

    def _restore_history(self) -> None:
        """Reload recent conversation turns so a restart doesn't blank memory.

        The UI already re-renders the saved conversation log on launch — but
        previously the BRAIN started empty, so "what did I just ask you?" after
        a restart got a dumbfounded answer. Now the model sees the same last N
        turns the user sees on screen."""
        try:
            from .. import state as _st
            limit = max(10, int(config.max_history))
            pairs = _st.recent_turns(limit)
        except Exception:
            return
        msgs: List[Dict[str, Any]] = []
        for p in pairs:
            user, reply = p["user"].strip(), p["reply"].strip()
            if not user or not reply:
                continue
            msgs.append({"role": "user", "content": user[:2000]})
            # Briefing/tool-dump replies get a shorter cap — the gist is what
            # matters for continuity, and giant entries would crowd the
            # 7-8B context window.
            msgs.append({"role": "assistant", "content": reply[:900]})
        if msgs:
            self.history = msgs[-max(4, int(config.max_history)):]
            self._trim()

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
        with self._busy:
            turn = self._ask_unlocked(text, on_action, on_token)
        try:  # usage stats: which brain actually answered
            from .. import state as _st
            label = (turn.provider or "").lower()
            key = ("route_offline" if "offline" in label else
                   "route_local" if ("local" in label or "ollama" in label) else
                   "route_cloud")
            _st.bump_stat(key)
        except Exception:
            pass
        return turn

    def _ask_unlocked(
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
        nudge_at: Optional[int] = None  # refusal-retry: history index of the nudge block
        nudged_once = False  # one nudge per turn, then its answer stands

        _REFUSAL_RX = re.compile(
            r"(i'm afraid i (?:can't|cannot|won't be able)|i can't (?:fetch|access|write|compose|"
            r"create|check|search)|i cannot (?:access|fetch|write|search|browse)|i'm unable to "
            r"(?:access|fetch|connect|browse|search)|i don't have (?:internet|access to "
            r"(?:the )?internet|the ability)|please open .+manually)", re.I)

        def _drop_nudge() -> None:
            nonlocal nudge_at
            if nudge_at is not None:
                del self.history[nudge_at:]
                nudge_at = None

        for _ in range(MAX_TOOL_ROUNDS):
            prompt = system_prompt()
            # NOTE: no "hidden tools" hint — telling the model skills are hidden
            # made it parrot "I cannot perform that action" on requests the pack
            # covered. The offline engine is the literal last line, not the LLM.
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
                _drop_nudge()
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
                if actions:
                    # The primary brain already ran its tools before dying on
                    # the recap. The stand-in re-matching the same intent would
                    # DOUBLE-fire tools (two timers, two restarts…) — surface
                    # the real results and stop.
                    reply = "\n".join(
                        a["result"] for a in actions if a.get("result")
                    ).strip() or (result.get("content") or "Done.")
                    reply = reply[:2000]
                    self.history.append({"role": "assistant", "content": reply})
                    self._trim()
                    return Turn(reply=reply, actions=actions,
                                provider="offline", error=error)
            except Exception as exc:  # network blips etc.
                _drop_nudge()
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
                _drop_nudge()
                # Refusal interceptor: the small brain said "I can't" while
                # tools/ability clearly exist and nothing even tried. Nudge once.
                if (not degraded and not error and not actions and not nudged_once
                        and _REFUSAL_RX.search(reply)):
                    nudged_once = True
                    nudge_at = len(self.history)
                    self.history.append({"role": "assistant", "content": reply[:400]})
                    self.history.append({"role": "user", "content":
                        "[the reply above was wrong: you HAVE the ability — tools cover it, "
                        "or it's plain writing. Answer the user's actual request now: call "
                        "the tool in this same message if one applies; if it's a writing/"
                        "content request, write it in full. No apologies, no 'I can't'.]"})
                    continue
                # Fallback answered because the main brain stumbled this turn —
                # say so in one clause, or the user thinks the persona broke.
                if error and degraded and not actions:
                    note = (f"\n\n(That answer came from my offline engine — "
                            f"the main brain stumbled: {str(error)[:90]}. "
                            "Qwen/Ollama may be reloading; ask again if it reads flat.)")
                    reply = (reply + note) if len(reply) + len(note) < 1900 else reply
                # Brain died on the post-tool recap (error set, actions exist):
                # the stand-in/offline text is context-free junk — show the
                # actual tool results instead of pretending nothing happened.
                if error and actions and degraded:
                    tool_text = "\n".join(
                        a["result"] for a in actions if a.get("result")
                    ).strip()
                    if tool_text:
                        reply = tool_text[:2000]
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
                try:  # usage stats: tool success rate
                    from .. import state as _st
                    failed = output.startswith(("That skill failed:", "I don't have a skill"))
                    _st.bump_stat("tools_fail" if failed else "tools_ok")
                except Exception:
                    pass
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
