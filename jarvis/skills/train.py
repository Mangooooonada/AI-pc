"""Self-improvement tooling: export your conversations as training data."""
from __future__ import annotations

from . import skill


@skill(
    "export_training_data",
    "Export the conversation history as a privacy-scrubbed fine-tuning dataset (ChatML JSONL) for training your own local model.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["export my training data", "export training data", "make my training dataset",
              "export my chat data for training", "build my training data"],
)
def export_training_data() -> str:
    from ..training_export import export
    try:
        s = export()
    except Exception as exc:
        return f"Export failed: {exc}"
    n = s["samples"]
    if n == 0:
        return ("Nothing worth training on yet — the dataset would be empty. "
                "Chat with me for a few days first (the offline canned answers "
                "are skipped on purpose: they'd teach the model to be dumb).")
    dropped = ", ".join(f"{v} {k}" for k, v in sorted(s["dropped"].items())) or "nothing"
    redactions = s["redactions"]
    return (
        f"Training dataset written: {n} clean conversations →\n{s['path']}\n"
        f"Skipped: {dropped}. Secrets redacted: {redactions}.\n"
        "Next step: run training/qlora_finetune.py on this file (see "
        "training/README.md — local GPU or a ~$5 rented one, your pick)."
    )
