"""Export your conversation log into a fine-tuning dataset.

Turns the saved conversation history into ChatML-style JSONL — one
{"messages": [system, user, assistant]} sample per good turn — ready for
QLoRA fine-tuning (Unsloth/Axolotl) of a local model you then import into
Ollama. "A model raised on you."

Quality gates (bad data in = bad model out):
  - drops turns answered by the offline engine (canned text teaches canned text)
  - drops turns that ended in an error
  - drops empty/tiny turns and assistant monologues (no user side)
  - caps oversized entries so a single briefing can't dominate the epoch
  - collapses exact duplicate pairs
Safety gates:
  - both sides pass through the privacy redactor (API keys, tokens,
    passwords) BEFORE anything touches disk — this file is the thing you
    might upload to a rented GPU
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import state
from .config import config
from .privacy import redact

_PERSONA = (
    "You are {name}, {title}'s personal AI — precise, dry-witted when welcome, "
    "and allergic to filler. You answer directly, you use your tools, and you "
    "never pretend to have done something you have not."
)

_MAX_USER = 1500
_MAX_ASSISTANT = 1200


def build_samples(limit: int = 500) -> Dict[str, Any]:
    """Return {\"samples\": [...], \"dropped\": {reason: n}, \"redactions\": n}."""
    entries = state.recent_entries(limit * 3)  # over-fetch: filters will bite
    samples: List[Dict[str, Any]] = []
    dropped: Dict[str, int] = {}
    seen = set()
    redactions = 0
    system = _PERSONA.format(name=config.name, title=config.user_title)
    _FAIL_PHRASES = ("my connection to the model dropped", "that skill failed:")

    def _drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for turn in entries:
        # canned offline answers teach the fine-tune to be canned — skip;
        # error text teaches it to fail — skip those too.
        if (turn.get("provider") or "").strip() == "offline":
            _drop("offline-engine answer"); continue
        user, reply = turn["user"].strip(), turn["reply"].strip()
        if any(reply.lower().startswith(p) for p in _FAIL_PHRASES):
            _drop("error turn"); continue
        if len(user) < 3:
            _drop("tiny"); continue
        if len(user) > _MAX_USER:
            user = user[:_MAX_USER]
        if len(reply) > _MAX_ASSISTANT:
            reply = reply[:_MAX_ASSISTANT]
        user, n1 = redact(user)
        reply, n2 = redact(reply)
        redactions += n1 + n2
        key = (user.lower()[:200], reply[:200])
        if key in seen:
            _drop("duplicate"); continue
        seen.add(key)
        if len(samples) >= limit:
            break
        samples.append({"messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": reply},
        ]})
    # recent_entries is chronological already: samples run oldest -> newest.
    return {"samples": samples, "dropped": dropped, "redactions": redactions}


def export(out_path: Path | None = None, limit: int = 500) -> Dict[str, Any]:
    """Write the JSONL and return a summary dict."""
    out = out_path or (config.workspace / "training" / "jarvis-chatml.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    built = build_samples(limit)
    with out.open("w", encoding="utf-8") as fh:
        for s in built["samples"]:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    return {
        "path": str(out),
        "samples": len(built["samples"]),
        "dropped": built["dropped"],
        "redactions": built["redactions"],
    }


def main(argv: List[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Export Jarvis conversations as a fine-tuning JSONL dataset.")
    ap.add_argument("--out", default=None, help="Output JSONL path (default: <workspace>/training/jarvis-chatml.jsonl)")
    ap.add_argument("--limit", type=int, default=500, help="Max samples (default 500)")
    args = ap.parse_args(argv)
    summary = export(Path(args.out) if args.out else None, args.limit)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
