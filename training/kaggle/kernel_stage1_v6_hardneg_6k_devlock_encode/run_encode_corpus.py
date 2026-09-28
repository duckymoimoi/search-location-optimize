#!/usr/bin/env python3
"""Encode corpus v3 with the 6k dev-lock checkpoint.

Writes a new embedding directory under /kaggle/working. Does not read or write
artifacts/embeddings/me5_small_v3 and does not build the demo index.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

OUT_NAME = "me5_small_v3_6k_devlock"
FORBIDDEN = {"me5_small_v3", "vn-poi-core-v3-me5-small"}


def find_dir(filename: str) -> Path:
    matches = sorted(Path("/kaggle/input").rglob(filename))
    if not matches:
        raise SystemExit(f"Missing {filename} under /kaggle/input")
    return matches[0].parent


def ensure_kaggle_gpu_compatibility() -> None:
    probe = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.stdout.strip().startswith("6.0"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--force-reinstall",
                "torch==2.7.1",
                "--index-url",
                "https://download.pytorch.org/whl/cu126",
            ],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "torchvision", "torchaudio"],
            check=False,
        )


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return torch.sum(last_hidden_state * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)


def encode_texts(model: Any, tokenizer: Any, texts: list[str], prefix: str, max_length: int, batch_size: int, device: Any) -> np.ndarray:
    import torch
    import torch.nn.functional as functional

    parts: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = [prefix + text for text in texts[start : start + batch_size]]
            tokens = tokenizer(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
            tokens.pop("token_type_ids", None)
            tokens = {key: value.to(device) for key, value in tokens.items()}
            vec = functional.normalize(mean_pool(model(**tokens).last_hidden_state, tokens["attention_mask"]), p=2, dim=1)
            parts.append(vec.cpu().numpy().astype(np.float32, copy=False))
            done = min(start + batch_size, len(texts))
            if start == 0 or done == len(texts) or done % (batch_size * 20) == 0:
                print(f"  encoded {done}/{len(texts)}", flush=True)
    return np.concatenate(parts)


def main() -> None:
    if OUT_NAME in FORBIDDEN:
        raise SystemExit("Refusing to write the demo embedding directory")
    ensure_kaggle_gpu_compatibility()
    import torch
    from transformers import AutoModel, AutoTokenizer

    if not torch.cuda.is_available():
        raise SystemExit("This kernel requires a CUDA GPU")
    device = torch.device("cuda")
    corpus_dir = find_dir("search_documents.parquet")
    checkpoint = find_dir("model.safetensors")
    docs = pd.read_parquet(corpus_dir / "search_documents.parquet", columns=["poi_id", "passage_context"])
    if len(docs) != 179209:
        raise SystemExit(f"Expected 179209 passages, got {len(docs)}")
    out = Path("/kaggle/working") / OUT_NAME
    out.mkdir(parents=True, exist_ok=True)
    print(f"encode {len(docs)} passages from {checkpoint} on {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModel.from_pretrained(checkpoint).to(device).eval()
    started = time.time()
    vectors = encode_texts(
        model,
        tokenizer,
        docs["passage_context"].fillna("").astype(str).tolist(),
        "passage: ",
        128,
        48,
        device,
    )
    np.save(out / "corpus_embeddings.npy", vectors)
    pd.DataFrame({"poi_id": docs["poi_id"].astype(str)}).to_parquet(out / "poi_ids.parquet", index=False)
    manifest = {
        "model_id": "intfloat/multilingual-e5-small",
        "checkpoint": "stage1_v6_hardneg_6k_devlock epoch 2",
        "corpus_version": "vn-poi-core-v3-semantic-address-dedup50",
        "row_count": int(vectors.shape[0]),
        "embedding_dimension": int(vectors.shape[1]),
        "dtype": "float32",
        "normalized": True,
        "passage_prefix": "passage: ",
        "max_length": 128,
        "index_name": "vn-poi-core-v3-me5-6k-devlock",
        "do_not_overwrite": ["artifacts/embeddings/me5_small_v3", "vn-poi-core-v3-me5-small"],
        "encode_seconds": round(time.time() - started, 1),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
