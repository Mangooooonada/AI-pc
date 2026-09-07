"""Self-improvement tooling: export your conversations as training data."""
from __future__ import annotations

import shutil

from . import skill
from ._platform import run
from ..config import config


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


_MIN_VRAM = 16        # GB — comfortable QLoRA floor for an 8B model
_TIGHT_VRAM = 12      # possible but cramped (seq 2048, batch 1)
_MIN_DISK = 25        # GB free on the workspace drive
_GOOD_SAMPLES = 200   # below 50 the trainer itself refuses
_TRAINABLE = 50


@skill(
    "training_readiness",
    "Check whether this PC is ready to fine-tune its own model: NVIDIA GPU VRAM, free disk, RAM, and whether the conversation log has enough training data yet.",
    {"type": "object", "properties": {}, "required": []},
    triggers=["can i train", "can i train yet", "check training readiness",
              "is my pc ready for training", "training readiness", "ready to train"],
)
def training_readiness() -> str:
    lines, bad = [], []

    # --- GPU (the Path A gate) ---
    gpu_name, vram_gb = "", 0
    if shutil.which("nvidia-smi"):
        out = run(["nvidia-smi", "--query-gpu=name,memory.total",
                   "--format=csv,noheader,nounits"], timeout=15)
        first = (out.splitlines() or [""])[0]
        if first and not first.startswith("("):
            bits = [b.strip() for b in first.split(",")]
            gpu_name = bits[0]
            try:
                vram_gb = round(float(bits[1]) / 1024, 1)
            except (IndexError, ValueError):
                vram_gb = 0
    if not gpu_name:
        lines.append("❌ GPU: no NVIDIA GPU detected (nvidia-smi missing or no card). "
                     "Path A needs one — Path B (rent ~$5) is your door.")
        bad.append("gpu")
    elif vram_gb >= _MIN_VRAM:
        lines.append(f"✅ GPU: {gpu_name}, {vram_gb} GB — Path A is GREEN.")
    elif vram_gb >= _TIGHT_VRAM:
        lines.append(f"⚠️ GPU: {gpu_name}, {vram_gb} GB — trainable but cramped "
                     "(shorter context: --seq 2048). Path B would be smoother.")
    else:
        lines.append(f"⚠️ GPU: {gpu_name}, {vram_gb} GB — too small for 8B QLoRA. "
                     "Use Path B (~$5 one evening).")
        bad.append("gpu")

    # --- Disk on the workspace drive (model 5GB + checkpoints + GGUF) ---
    try:
        free_gb = shutil.disk_usage(str(config.workspace)).free / 1e9
    except Exception:
        free_gb = 0
    if free_gb >= _MIN_DISK:
        lines.append(f"✅ Disk: {free_gb:.0f} GB free on the workspace drive.")
    else:
        lines.append(f"⚠️ Disk: {free_gb:.0f} GB free — need ~{_MIN_DISK}.")
        bad.append("disk")

    # --- Training data so far ---
    try:
        from ..training_export import build_samples
        samples = len(build_samples(limit=10_000)["samples"])
    except Exception:
        samples = 0
    if samples >= _GOOD_SAMPLES:
        lines.append(f"✅ Data: {samples} trainable conversations right now. Chef's kiss.")
    elif samples >= _TRAINABLE:
        lines.append(f"⚠️ Data: {samples} conversations — trainable, but 200+ "
                     "makes a noticeably better model. Keep chatting this week.")
    else:
        lines.append(f"❌ Data: only {samples} usable conversations — under {_TRAINABLE} "
                     "the trainer refuses. Just chat normally for a few days.")
        bad.append("data")

    if not bad:
        lines.append("\nVERDICT: Path A is a go — training/README.md, steps 2A → 5.")
    elif "gpu" in bad:
        lines.append("\nVERDICT: Path B tonight (~$5, 24 GB card), or upgrade chat cards later.")
    else:
        lines.append("\nVERDICT: almost — fix the flagged item(s), then Path A.")
    return "\n".join(lines)
