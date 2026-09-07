# Train your own Jarvis (raised on you)

Everything below turns **your actual Jarvis conversations** into a fine-tuned
local model, then plugs it back into Jarvis as a second brain you can switch
to any time (the brain dropdown) — the stock model stays untouched.

Paths: **A = your own GPU** (needs NVIDIA with ≥16 GB VRAM) or
**B = a rented GPU** (~$3–6 total on RunPod/Vast.ai). The training step is
THE SAME on both — only the setup differs, so you can start on one and finish
on the other.

## Step 1 — Export your data (both paths)

In Jarvis chat say **"export my training data"**, or run:

```bash
python -m jarvis.training_export
```

You get `<workspace>/training/jarvis-chatml.jsonl` — one sample per good turn,
secrets redacted (API keys/passwords/tokens get `[REDACTED]`), offline canned
answers and error turns skipped. **Wait until the summary says ~200+ samples**
— under ~50 the script refuses because there's nothing meaningful to learn.

## Step 2A — Setup: your own GPU

0. Ask Jarvis **"is my PC ready for training"** — he checks VRAM, disk, and
   data volume and gives a green/cramped/Path-B verdict on the spot.
1. `nvidia-smi` works, ideally ≥16 GB. **12 GB works too — this kit was tuned
   for exactly that** (the script auto-detects a 12 GB card and switches to
   seq 2048 / batch 1 / accum 8 / rank 8, which fits because Jarvis chat turns
   are short). Before starting: close Chrome/Edge, Discord, Steam and any
   wallpaper/GPU apps — they quietly hold 1–2 GB of VRAM. If it still OOMs,
   rerun with `--base qwen3-4b` (the built-in 12 GB comfort pick).
2. Easiest on Windows: do this inside **WSL2 (Ubuntu)** with the NVIDIA driver
   on the Windows side. Then:
   ```bash
   python3 -m venv ft && source ft/bin/activate
   pip install unsloth datasets trl
   ```

## Step 2B — Setup: rented GPU (~$5)

1. RunPod → GPU pod, template **PyTorch 2.x**, pick a 24 GB card
   (RTX 4090 / A5000 / A40 — $0.25–0.50/hr).
2. In the pod terminal:
   ```bash
   pip install unsloth datasets trl
   ```
3. Upload your `jarvis-chatml.jsonl` (RunPod: the file browser, or
   `scp jarvis-chatml.jsonl root@<pod>:/workspace/`).

## Step 3 — Train (identical both paths)

```bash
python qlora_finetune.py --data jarvis-chatml.jsonl --out jarvis-me --merge
```

- 200–500 samples ≈ **30–90 minutes** on a 24 GB card ($1.50–3.00 rented).
- `--base` defaults to `qwen3-8b` (the model you already run in Ollama).
  Alternatives: `--base llama-3.1-8b`, `--base mistral-7b`.
- This teaches **style and patterns**, not encyclopedic facts — keep using
  Jarvis memory + documents for facts. That's the intended division of labor.

## Step 4 — Import into Ollama

On the machine where Ollama runs (for Path B: download the
`jarvis-me-merged/` folder back from the pod first — then stop the pod!):

```bash
git clone --depth 1 https://github.com/ggml-org/llama.cpp
pip install -r llama.cpp/requirements.txt
python llama.cpp/convert_hf_to_gguf.py jarvis-me-merged --outfile jarvis-me-f16.gguf
# optional but recommended on modest GPUs (halves the size):
llama.cpp/build/bin/llama-quantize jarvis-me-f16.gguf jarvis-me-q4.gguf Q4_K_M

printf 'FROM ./jarvis-me-q4.gguf\n' > Modelfile   # (or jarvis-me-f16.gguf)
ollama create jarvis-me -f Modelfile
```

(Hugging Face/safetensors → GGUF needs a 64-bit Python with the llama.cpp
requirements; on Windows use the same WSL2 shell for this step.)

## Step 5 — Switch brains (both, any time)

Jarvis → brain dropdown → **Ollama (local)** is already pointing at your model
list: `ollama list` now shows `jarvis-me`. Set it as the default with
`JARVIS_OLLAMA_MODEL=jarvis-me` in `.env`, or just pick it in
**Settings → Brain**. Switch back to `qwen3:8b` whenever — they're
side-by-side models, both yours, both options under one roof.

Heads-up: re-export and re-train every few weeks; each run layers more *you*
in. Delete the rented pod IMMEDIATELY when done — it's billed by the minute
even idle.
