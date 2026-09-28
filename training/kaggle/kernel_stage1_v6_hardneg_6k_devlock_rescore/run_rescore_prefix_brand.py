#!/usr/bin/env python3
"""Score the locked 6k checkpoint on Gold prefix ranks and brand rankings.

Kaggle runs this file alone. It encodes the corpus twice: zero-shot, then the
dev-lock checkpoint. It does not train and does not write an embedding npy.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

MODEL_ID = "intfloat/multilingual-e5-small"
PREFIX_DEPTH = 50
BRAND_DEPTH = 50


def parse_ids(raw) -> list[str]:
    if raw is None:
        return []
    try:
        if raw != raw:
            return []
    except Exception:
        pass
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    if hasattr(raw, "tolist") and not isinstance(raw, str):
        return [str(item) for item in raw.tolist()]
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def find_dir(filename: str) -> Path:
    root = Path("/kaggle/input")
    matches = sorted(root.rglob(filename))
    if not matches:
        raise SystemExit(f"Missing {filename} under /kaggle/input")
    return matches[0].parent


def ensure_kaggle_gpu_compatibility() -> None:
    if not Path("/kaggle").exists():
        return
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


def exact_topk(queries: np.ndarray, corpus: np.ndarray, ids: list[str], top_k: int, chunk: int) -> list[list[str]]:
    out: list[list[str]] = []
    for start in range(0, len(queries), chunk):
        scores = queries[start : start + chunk] @ corpus.T
        for row_scores in scores:
            k = min(top_k, len(row_scores))
            cand = np.argpartition(-row_scores, k - 1)[:k]
            order = np.lexsort((cand, -row_scores[cand]))
            out.append([ids[i] for i in cand[order]])
    return out


def grapheme_clusters(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", str(text or ""))
    out: list[str] = []
    for ch in text:
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def expand_char_prefixes(sessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in sessions.itertuples(index=False):
        role = str(getattr(row, "query_role", "") or "")
        if role and role != "q01":
            continue
        chars = grapheme_clusters(row.query_text)
        acceptable = parse_ids(getattr(row, "acceptable_poi_ids", None))
        if not acceptable:
            acceptable = [str(row.intended_poi_id)]
        for n in range(1, len(chars) + 1):
            prefix = "".join(chars[:n])
            if not prefix.strip():
                continue
            rows.append(
                {
                    "variant_id": str(row.variant_id),
                    "case_id": str(row.case_id),
                    "acceptable_poi_ids": "|".join(acceptable),
                    "prefix_text": prefix,
                    "prefix_index": n,
                }
            )
    return pd.DataFrame(rows)


def rank_of(top: list[str], acceptable: set[str]) -> int | None:
    return next((index for index, poi_id in enumerate(top, start=1) if poi_id in acceptable), None)


def write_prefix(path: Path, prefix_df: pd.DataFrame, ranked: list[list[str]]) -> None:
    lines = []
    for record, top in zip(prefix_df.itertuples(index=False), ranked):
        acceptable = set(parse_ids(record.acceptable_poi_ids))
        lines.append(
            json.dumps(
                {
                    "variant_id": str(record.variant_id),
                    "case_id": str(record.case_id),
                    "prefix_index": int(record.prefix_index),
                    "prefix_text": str(record.prefix_text),
                    "rank": rank_of(top, acceptable),
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_brand(path: Path, queries: pd.DataFrame, ranked: list[list[str]]) -> None:
    lines = []
    for record, top in zip(queries.itertuples(index=False), ranked):
        lines.append(
            json.dumps(
                {
                    "query_id": str(record.query_id),
                    "brand_family_id": str(record.brand_family_id),
                    "brand_group_id": str(record.brand_group_id),
                    "query_role": str(record.query_role),
                    "exposure_class": str(getattr(record, "exposure_class", "") or ""),
                    "acceptable_poi_ids": parse_ids(record.acceptable_poi_ids),
                    "top_ids": top,
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_encoder(source: str, device: Any):
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(source)
    model = AutoModel.from_pretrained(source).to(device).eval()
    return model, tokenizer


def main() -> None:
    ensure_kaggle_gpu_compatibility()
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("This kernel requires a CUDA GPU")
    device = torch.device("cuda")
    corpus_dir = find_dir("search_documents.parquet")
    gold_csv = corpus_dir / "gold_query_variants.csv"
    if not gold_csv.exists():
        gold_csv = find_dir("gold_query_variants.csv") / "gold_query_variants.csv"
    checkpoint = find_dir("model.safetensors")
    brand_dir = find_dir("brand_queries_v1.parquet")
    out = Path("/kaggle/working/rescore")
    out.mkdir(parents=True, exist_ok=True)

    docs = pd.read_parquet(corpus_dir / "search_documents.parquet", columns=["poi_id", "passage_context"])
    corpus_ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].astype(str).tolist()
    gold = pd.read_csv(gold_csv)
    prefixes = expand_char_prefixes(gold)
    brand = pd.read_parquet(brand_dir / "brand_queries_v1.parquet")
    print(
        f"docs={len(docs)} gold={len(gold)} prefixes={len(prefixes)} brand={len(brand)} device={device}",
        flush=True,
    )

    started = time.time()
    for tag, source in (("zero_shot", MODEL_ID), ("finetuned", str(checkpoint))):
        print(f"load {tag} from {source}", flush=True)
        model, tokenizer = load_encoder(source, device)
        print(f"encode corpus {tag}", flush=True)
        corpus_vectors = encode_texts(model, tokenizer, passages, "passage: ", 128, 48, device)
        print(f"encode prefixes {tag}", flush=True)
        prefix_vectors = encode_texts(model, tokenizer, prefixes["prefix_text"].astype(str).tolist(), "query: ", 64, 48, device)
        write_prefix(out / f"run_{tag}_prefix.jsonl", prefixes, exact_topk(prefix_vectors, corpus_vectors, corpus_ids, PREFIX_DEPTH, 32))
        print(f"encode brand {tag}", flush=True)
        brand_vectors = encode_texts(model, tokenizer, brand["query_text"].astype(str).tolist(), "query: ", 64, 48, device)
        write_brand(out / f"run_{tag}_brand.jsonl", brand, exact_topk(brand_vectors, corpus_vectors, corpus_ids, BRAND_DEPTH, 32))
        del model, corpus_vectors, prefix_vectors, brand_vectors
        torch.cuda.empty_cache()
    print(f"done {time.time() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
