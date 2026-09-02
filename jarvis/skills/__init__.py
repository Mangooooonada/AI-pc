"""Skill registry.

A *skill* is a plain Python function decorated with @skill. The decorator records
an OpenAI-style JSON schema so the LLM can call it as a tool, and also registers
plain-language trigger phrases so the offline brain can still fire it without
any model at all.
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Skill:
    name: str
    description: str
    func: Callable[..., Any]
    parameters: Dict[str, Any]
    triggers: List[str] = field(default_factory=list)
    dangerous: bool = False

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __call__(self, **kwargs: Any) -> str:
        sig = inspect.signature(self.func)
        clean = {k: v for k, v in kwargs.items() if k in sig.parameters}
        result = self.func(**clean)
        return str(result) if result is not None else "Done."


REGISTRY: Dict[str, Skill] = {}


def skill(
    name: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    triggers: Optional[List[str]] = None,
    dangerous: bool = False,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        REGISTRY[name] = Skill(
            name=name,
            description=description,
            func=func,
            parameters=parameters or {"type": "object", "properties": {}},
            triggers=triggers or [],
            dangerous=dangerous,
        )
        return func

    return decorator


def all_skills() -> List[Skill]:
    return list(REGISTRY.values())


def tool_schemas() -> List[Dict[str, Any]]:
    return [s.schema() for s in REGISTRY.values()]


# Always offered, whatever the user says — memory, identity and the two
# escape hatches are cheap and frequently useful mid-conversation.
_PACK_ALWAYS = {"remember", "recall", "who_am_i", "web_search", "list_capabilities"}


def pack_tools(user_text: str, limit: int = 0) -> tuple[List[Dict[str, Any]], int]:
    """Pick the most relevant tool schemas for this message.

    50+ schemas swamp a 7B local model: they eat context AND make malformed
    tool-call output (the Ollama "closing '}'" 400) measurably more likely.
    Packing the ~16 most relevant ones per message keeps small models sharp.
    """
    from ..config import config  # local import: avoid module cycles

    tools = tool_schemas()
    limit = max(6, limit or getattr(config, "tool_pack", 16))
    if len(tools) <= limit:
        return tools, 0

    text = normalize(user_text or "")
    words = {w for w in re.split(r"\W+", text) if len(w) > 2}
    scored: List[tuple[float, str]] = []
    for sk in REGISTRY.values():
        best = 55.0 if sk.name in _PACK_ALWAYS else 0.0
        name_words = set(sk.name.split("_"))
        for trigger in sk.triggers:
            trig = normalize(trigger)
            parts = re.split(r"\{(\w+)\}", trig)
            pattern, literal = "", 0
            for i, part in enumerate(parts):
                if i % 2:
                    pattern += r".+?"
                else:
                    pattern += re.escape(part)
                    literal += len(part.strip())
            if re.search(pattern + r"\s*$", text) or re.fullmatch(pattern, text):
                best = max(best, 10_000.0 + literal)
                continue
            trig_words = {w for w in re.split(r"\W+", trig) if len(w) > 2}
            overlap = len((trig_words | name_words) & words)
            best = max(best, overlap * 100.0 + literal)
        scored.append((-best, sk.name))

    scored.sort()
    keep = {name for _, name in scored[:limit]}
    packed = [t for t in tools if t["function"]["name"] in keep]
    return packed, len(tools) - len(packed)


def run_skill(name: str, arguments: Dict[str, Any]) -> str:
    sk = REGISTRY.get(name)
    if sk is None:
        return f"I don't have a skill called '{name}'."
    try:
        return sk(**(arguments or {}))
    except Exception as exc:  # skills must never crash the assistant
        return f"That skill failed: {exc}"


CONTRACTIONS = {
    "what's": "what is", "whats": "what is", "how's": "how is", "hows": "how is",
    "that's": "that is", "it's": "it is", "i'm": "i am", "let's": "let us",
    "don't": "do not", "can't": "can not", "won't": "will not",
    "who's": "who is", "there's": "there is", "please": "",
}


def normalize(text: str) -> str:
    low = " ".join((text or "").lower().split()).strip(" ?!.,")
    for a, b in CONTRACTIONS.items():
        low = re.sub(rf"\b{re.escape(a)}\b", b, low)
    return " ".join(low.split())


def looks_like_math(text: str) -> bool:
    t = normalize(text)
    if not re.search(r"\d", t):
        return False
    return bool(re.search(r"[\d\s]+[-+*/^x%]|\bpercent\b|% of |\bplus\b|\bminus\b|\btimes\b|\bdivided by\b", t))


def match_offline(text: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """Very small intent matcher used when no LLM is available.

    Triggers may contain a `{arg}` placeholder which captures the rest of the
    phrase, e.g. "open {target}" against "open notepad" -> {"target": "notepad"}.
    """
    low = normalize(text)
    if not low:
        return None
    best: Optional[tuple[tuple[int, int], str, Dict[str, Any]]] = None
    for sk in REGISTRY.values():
        for trigger in sk.triggers:
            trig = normalize(trigger).replace("{ ", "{").replace(" }", "}")
            parts = re.split(r"\{(\w+)\}", trig)
            pattern = ""
            literal = 0
            for i, part in enumerate(parts):
                if i % 2:
                    pattern += f"(?P<{part}>.+?)"
                else:
                    pattern += re.escape(part)
                    literal += len(part.strip())
            m = re.search(pattern + r"\s*$", low) or re.fullmatch(pattern, low)
            if not m:
                continue
            args = {k: v.strip(" ?.!,") for k, v in (m.groupdict() or {}).items() if v}
            # Rank by how much literal trigger text was matched, then by how
            # early in the sentence the trigger starts.
            score = (literal, -m.start())
            if best is None or score > best[0]:
                best = (score, sk.name, args)
    if best:
        # "what is 15% of 240" is arithmetic, not an encyclopedia lookup.
        if best[1] in {"wikipedia_summary", "web_search"} and looks_like_math(text):
            return "calculate", {"expression": best[2].get("topic") or best[2].get("query") or text}
        return best[1], best[2]
    if looks_like_math(text):
        return "calculate", {"expression": text}
    return None


# Importing the modules below populates REGISTRY.
from . import system, apps, media, files, web, knowledge, agenda, security, vision, dev, docs, google, train  # noqa: E402,F401
