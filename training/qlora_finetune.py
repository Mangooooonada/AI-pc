#!/usr/bin/env python3
"""QLoRA fine-tune on your Jarvis dataset export — runs identically on your
own 16-24GB GPU or a rented one (~$3-6 total). See training/README.md.

    python qlora_finetune.py --data jarvis-chatml.jsonl --out jarvis-me
    python qlora_finetune.py --data jarvis-chatml.jsonl --out jarvis-me --merge

--merge also writes a full merged model (jarvis-me-merged/) ready for the
GGUF conversion step that imports into Ollama.

Deps (install INSIDE a venv):  pip install unsloth datasets trl
"""
from __future__ import annotations

import argparse
import json
import sys

BASE_MODELS = {
    # friendly name -> HF repo. Keep these 4-bit-loadable in 16-24GB VRAM.
    "qwen3-8b": "unsloth/Qwen3-8B",
    "llama-3.1-8b": "unsloth/Meta-Llama-3.1-8B-Instruct",
    "mistral-7b": "unsloth/mistral-7b-instruct-v0.3-bnb-4bit",
}


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="QLoRA fine-tune on a Jarvis ChatML export.")
    ap.add_argument("--data", required=True, help="Path to jarvis-chatml.jsonl")
    ap.add_argument("--base", default="qwen3-8b",
                    help="Base model key or HF repo. Known: "
                         + ", ".join(BASE_MODELS) + " (default qwen3-8b)")
    ap.add_argument("--out", default="jarvis-me", help="Adapter output dir")
    ap.add_argument("--epochs", type=float, default=1.0, help="Training epochs (default 1)")
    ap.add_argument("--max-steps", type=int, default=-1, help="Hard cap on steps (-1 = full epochs)")
    ap.add_argument("--seq", type=int, default=4096, help="Max sequence length")
    ap.add_argument("--merge", action="store_true", help="Also write merged full model for GGUF conversion")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Imports stay INSIDE main so --help works on machines without GPU deps.
    try:
        from unsloth import FastLanguageModel, is_bfloat16_supported  # noqa: F401
        from datasets import load_dataset
        from trl import SFTConfig, SFTTrainer
        import torch
    except ImportError as exc:
        print(f"Missing dependency: {exc}\n"
              "Install with:  pip install unsloth datasets trl\n"
              "(On a rented GPU the template usually has torch already.)")
        return 2

    base = BASE_MODELS.get(args.base, args.base)
    with open(args.data, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    if len(rows) < 50:
        print(f"Only {len(rows)} samples — fine-tuning under ~50 turns teaches "
              "very little. Chat with Jarvis more, re-export, then return.")
        return 1
    print(f"Loaded {len(rows)} samples from {args.data}\nBase model: {base}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base, max_seq_length=args.seq, load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=16, lora_dropout=0,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
    )

    def to_text(sample):
        return {"text": tokenizer.apply_chat_template(
            sample["messages"], tokenize=False, add_generation_prompt=False)}

    ds = load_dataset("json", data_files=args.data, split="train").map(to_text)

    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer, train_dataset=ds,
        args=SFTConfig(
            output_dir=args.out + "-ckpt",
            num_train_epochs=args.epochs, max_steps=args.max_steps,
            per_device_train_batch_size=2, gradient_accumulation_steps=4,
            learning_rate=2e-4, warmup_steps=5, logging_steps=5,
            bf16=is_bfloat16_supported(), fp16=not is_bfloat16_supported(),
            optim="adamw_8bit", seed=42, report_to="none",
            dataset_text_field="text", max_seq_length=args.seq,
        ),
    )
    trainer.train()
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print(f"LoRA adapter saved -> {args.out}/")

    if args.merge:
        merged = args.out + "-merged"
        model.save_pretrained_merged(merged, tokenizer, save_method="merged_16bit")
        print(f"Merged full model saved -> {merged}/")
        print("Next: convert to GGUF (see training/README.md, step 4).")
    else:
        print("Next: rerun with --merge, then see training/README.md step 4.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
