"""
Pluto-LM Fine-tuning Script (Apple Silicon / MLX-LM)
Base model : Qwen2.5 1.5B Instruct (fits in 32GB, fast on M2 Max)
Method     : LoRA via mlx-lm
Dataset    : data/pluto_lm_dataset.jsonl

Usage:
  python3 scripts/finetune_pluto_lm.py --prep      # prepare data only
  python3 scripts/finetune_pluto_lm.py --train     # prepare + train
  python3 scripts/finetune_pluto_lm.py --test      # test fused model
  python3 scripts/finetune_pluto_lm.py --all       # prep + train + test

Output:
  models/pluto-lm-adapters/   → LoRA adapter weights
  models/pluto-lm-fused/      → fused model ready for Ollama
"""

import json
import os
import sys
import subprocess
import argparse
import random
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BASE_MODEL    = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
DATASET_FILE  = "data/pluto_lm_dataset.jsonl"
TRAIN_FILE    = "data/train.jsonl"
VALID_FILE    = "data/valid.jsonl"
ADAPTER_PATH  = "models/plutoedge-v3-adapters"
FUSED_PATH    = "models/PlutoEdge-1.5B-v3"

LORA_CONFIG = {
    "num_layers": 16,          # number of layers to apply LoRA
    "batch_size": 4,
    "iters": 1200,             # training iterations
    "val_batches": 25,
    "learning_rate": 1e-4,
    "steps_per_report": 50,
    "steps_per_eval": 100,
    "save_every": 200,
    "lora_parameters": {
        "rank": 16,
        "alpha": 16,
        "dropout": 0.05,
        "scale": 10.0,
    },
}

SYSTEM_PROMPT = (
    "You are Pluto, an AI controller for the PlutoClaw Edge AI platform. "
    "PlutoClaw runs on Raspberry Pi and controls physical IoT devices via GPIO. "
    "When the user requests an action, respond concisely and end with "
    "PLUTO_ACTION: {json} for device commands."
)

# ── Data preparation ───────────────────────────────────────────────────────────

def apply_chat_template(conversations: list[dict]) -> str:
    """Convert conversations to Qwen2.5 ChatML format."""
    result = ""
    for msg in conversations:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            result += f"<|im_start|>system\n{content}<|im_end|>\n"
        elif role == "user":
            result += f"<|im_start|>user\n{content}<|im_end|>\n"
        elif role == "assistant":
            result += f"<|im_start|>assistant\n{content}<|im_end|>\n"
    return result


def prepare_data():
    print("\n[Prep] Loading dataset...")
    if not Path(DATASET_FILE).exists():
        print(f"  ERROR: {DATASET_FILE} not found. Run build_dataset.py first.")
        sys.exit(1)

    with open(DATASET_FILE) as f:
        entries = [json.loads(l) for l in f if l.strip()]

    print(f"  Loaded {len(entries)} entries")

    # Convert to MLX text format
    mlx_entries = []
    for entry in entries:
        convs = entry.get("conversations", [])
        # Ensure system prompt is always present and up to date
        if convs and convs[0]["role"] == "system":
            convs[0]["content"] = SYSTEM_PROMPT
        elif convs:
            convs.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        text = apply_chat_template(convs)
        if len(text) > 50:  # skip empty entries
            mlx_entries.append({"text": text})

    # Shuffle and split 90/10 train/valid
    random.shuffle(mlx_entries)
    split = int(len(mlx_entries) * 0.9)
    train_entries = mlx_entries[:split]
    valid_entries = mlx_entries[split:]

    os.makedirs("data", exist_ok=True)
    with open(TRAIN_FILE, "w") as f:
        for e in train_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    with open(VALID_FILE, "w") as f:
        for e in valid_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"  Train: {len(train_entries)} entries → {TRAIN_FILE}")
    print(f"  Valid: {len(valid_entries)} entries → {VALID_FILE}")

    # Write LoRA config
    os.makedirs(ADAPTER_PATH, exist_ok=True)
    with open(f"{ADAPTER_PATH}/adapter_config.json", "w") as f:
        json.dump(LORA_CONFIG["lora_parameters"], f, indent=2)

    print("  Data preparation complete.")
    return len(train_entries), len(valid_entries)


# ── Training ──────────────────────────────────────────────────────────────────

def train():
    print(f"\n[Train] Fine-tuning {BASE_MODEL} with LoRA...")
    print(f"  Adapter output: {ADAPTER_PATH}")
    print(f"  Iters: {LORA_CONFIG['iters']} | Batch: {LORA_CONFIG['batch_size']}")
    print(f"  LoRA rank: {LORA_CONFIG['lora_parameters']['rank']}\n")

    os.makedirs(ADAPTER_PATH, exist_ok=True)

    cmd = [
        "mlx_lm.lora",
        "--model",            BASE_MODEL,
        "--train",
        "--data",             "data/",
        "--batch-size",       str(LORA_CONFIG["batch_size"]),
        "--num-layers",       str(LORA_CONFIG["num_layers"]),
        "--iters",            str(LORA_CONFIG["iters"]),
        "--val-batches",      str(LORA_CONFIG["val_batches"]),
        "--learning-rate",    str(LORA_CONFIG["learning_rate"]),
        "--steps-per-report", str(LORA_CONFIG["steps_per_report"]),
        "--steps-per-eval",   str(LORA_CONFIG["steps_per_eval"]),
        "--save-every",       str(LORA_CONFIG["save_every"]),
        "--adapter-path",     ADAPTER_PATH,
    ]

    print("  Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=os.getcwd())
    if result.returncode != 0:
        print("\n  ERROR: Training failed.")
        sys.exit(1)
    print(f"\n  Training complete. Adapters saved to {ADAPTER_PATH}/")


# ── Fuse model ────────────────────────────────────────────────────────────────

def fuse():
    print(f"\n[Fuse] Merging LoRA adapters into base model...")
    os.makedirs(FUSED_PATH, exist_ok=True)

    cmd = [
        "mlx_lm.fuse",
        "--model",        BASE_MODEL,
        "--adapter-path", ADAPTER_PATH,
        "--save-path",    FUSED_PATH,
        "--dequantize",
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("  ERROR: Fuse failed.")
        sys.exit(1)
    print(f"  Fused model saved to {FUSED_PATH}/")


# ── Test ──────────────────────────────────────────────────────────────────────

def test_model(use_adapter=True):
    print("\n[Test] Running inference on Pluto-LM...")

    test_prompts = [
        "Turn on the ventilation fan.",
        "Temperature is 42°C, too hot. What should I do?",
        "Soil moisture is critically low. Activate irrigation.",
        "Motor temperature is 87°C. Trigger emergency shutdown and sound alarm.",
        "What devices are currently available?",
        "Run a 10-second watering pulse.",
        "End of shift: shut down all industrial equipment safely.",
    ]

    for prompt in test_prompts:
        print(f"\n  User: {prompt}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]

        text = apply_chat_template(messages)
        text += "<|im_start|>assistant\n"

        if use_adapter and Path(ADAPTER_PATH).exists():
            cmd = [
                "python3", "-m", "mlx_lm.generate",
                "--model",        BASE_MODEL,
                "--adapter-path", ADAPTER_PATH,
                "--prompt",       text,
                "--max-tokens",   "200",
                "--temp",         "0.1",
            ]
        else:
            cmd = [
                "python3", "-m", "mlx_lm.generate",
                "--model",    FUSED_PATH if Path(FUSED_PATH).exists() else BASE_MODEL,
                "--prompt",   text,
                "--max-tokens", "200",
                "--temp",     "0.1",
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip()

        # Extract just the assistant response
        if "<|im_start|>assistant" in output:
            output = output.split("<|im_start|>assistant")[-1]
        if "<|im_end|>" in output:
            output = output.split("<|im_end|>")[0]
        output = output.strip()

        print(f"  Pluto: {output[:300]}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prep",  action="store_true", help="Prepare training data")
    parser.add_argument("--train", action="store_true", help="Prepare + train")
    parser.add_argument("--fuse",  action="store_true", help="Fuse adapters into model")
    parser.add_argument("--test",  action="store_true", help="Test the model")
    parser.add_argument("--all",   action="store_true", help="Run full pipeline")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    # Check mlx-lm
    try:
        import mlx_lm
    except ImportError:
        print("\n[!] mlx-lm not installed. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "mlx-lm", "-q"])

    if args.prep or args.train or args.all:
        prepare_data()

    if args.train or args.all:
        train()

    if args.fuse or args.all:
        fuse()

    if args.test or args.all:
        test_model()

    print("\n✅ Done!")
    if args.train or args.all:
        print(f"   Adapters : {ADAPTER_PATH}/")
        print(f"   Next     : python3 scripts/finetune_pluto_lm.py --fuse --test")


if __name__ == "__main__":
    main()
