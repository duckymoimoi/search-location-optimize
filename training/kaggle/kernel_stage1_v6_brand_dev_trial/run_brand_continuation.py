#!/usr/bin/env python3
"""Continue the 6k dev-lock checkpoint on brand multi-positive queries.

Kaggle runs this file alone. Checkpoint choice uses brand dev and POI dev.
Gold brand and Gold POI are scored once after that lock.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")


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


def find_file(name: str) -> Path:
    matches = sorted(Path("/kaggle/input").rglob(name))
    if not matches:
        raise SystemExit(f"Missing {name} under /kaggle/input")
    return matches[0]


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


def mean_pool(hidden: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(hidden.size()).float()
    return torch.sum(hidden * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)


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
    return np.concatenate(parts)


def exact_topk(queries: np.ndarray, corpus: np.ndarray, ids: list[str], top_k: int, chunk: int = 32) -> list[list[str]]:
    out: list[list[str]] = []
    for start in range(0, len(queries), chunk):
        scores = queries[start : start + chunk] @ corpus.T
        for row_scores in scores:
            k = min(top_k, len(row_scores))
            cand = np.argpartition(-row_scores, k - 1)[:k]
            order = np.lexsort((cand, -row_scores[cand]))
            out.append([ids[i] for i in cand[order]])
    return out


def brand_metrics(frame: pd.DataFrame, ranked: list[list[str]]) -> dict[str, float]:
    hits: dict[int, dict[str, list[float]]] = {k: defaultdict(list) for k in (1, 20)}
    for record, top in zip(frame.itertuples(index=False), ranked):
        accepted = set(parse_ids(record.acceptable_poi_ids))
        family_id = str(record.brand_family_id)
        rank = next((index for index, poi_id in enumerate(top, start=1) if poi_id in accepted), None)
        for k in (1, 20):
            hits[k][family_id].append(1.0 if rank is not None and rank <= k else 0.0)

    def family_mean(groups: dict[str, list[float]]) -> float:
        means = [sum(values) / len(values) for values in groups.values() if values]
        return sum(means) / len(means)

    return {"Hit@1": family_mean(hits[1]), "Hit@20": family_mean(hits[20]), "n_families": float(len(hits[1]))}


def poi_hit1(frame: pd.DataFrame, ranked: list[list[str]]) -> float:
    hits = 0
    for record, top in zip(frame.itertuples(index=False), ranked):
        accepted = set(parse_ids(record.acceptable_poi_ids))
        if not accepted:
            accepted = {str(record.intended_poi_id)}
        if top and top[0] in accepted:
            hits += 1
    return hits / len(frame)


def make_batches(rows: list[dict], batch_size: int, seed: int) -> list[list[dict]]:
    pending = list(rows)
    random.Random(seed).shuffle(pending)
    batches: list[list[dict]] = []
    while pending:
        batch: list[dict] = []
        deferred: list[dict] = []
        families: set[str] = set()
        for row in pending:
            family_id = str(row["brand_family_id"])
            if len(batch) < batch_size and family_id not in families:
                batch.append(row)
                families.add(family_id)
            else:
                deferred.append(row)
        if not batch:
            raise RuntimeError("Brand batch sampler made no progress")
        batches.append(batch)
        pending = deferred
    return batches


def build_train_rows(frame: pd.DataFrame, corpus_ids: list[str], gold_ids: set[str], config: dict[str, Any]) -> list[dict]:
    rng = random.Random(config["seed"])
    corpus_set = set(corpus_ids)
    rows = []
    for record in frame.itertuples(index=False):
        pool = [
            poi_id
            for poi_id in dict.fromkeys(parse_ids(record.acceptable_poi_ids))
            if poi_id in corpus_set and poi_id not in gold_ids
        ]
        if not pool:
            continue
        ban = set(pool) | gold_ids
        negatives = []
        guard = 0
        while len(negatives) < config["negatives_per_query"] and guard < 10000:
            guard += 1
            poi_id = corpus_ids[rng.randrange(len(corpus_ids))]
            if poi_id in ban or poi_id in negatives:
                continue
            negatives.append(poi_id)
        chosen = pool if len(pool) <= config["positives_per_query"] else rng.sample(pool, config["positives_per_query"])
        rows.append(
            {
                "query_text": str(record.query_text),
                "brand_family_id": str(record.brand_family_id),
                "pool": pool,
                "positives": chosen,
                "negatives": negatives,
            }
        )
    return rows


def train_epoch(model: Any, tokenizer: Any, rows: list[dict], passage_by_id: dict[str, str], config: dict[str, Any], device: Any, optimizer: Any, scheduler: Any, scaler: Any, epoch: int) -> dict[str, Any]:
    import torch

    batches = make_batches(rows, config["train_batch_size"], config["seed"] + epoch)
    losses: list[float] = []
    model.train()
    started = time.time()
    for batch in batches:
        passage_ids: list[str] = []
        seen: set[str] = set()
        for row in batch:
            for poi_id in row["positives"] + row["negatives"]:
                if poi_id not in seen and poi_id in passage_by_id:
                    seen.add(poi_id)
                    passage_ids.append(poi_id)
        if not passage_ids:
            continue
        query_inputs = tokenize(tokenizer, [row["query_text"] for row in batch], config["query_prefix"], config["max_query_tokens"], device)
        passage_inputs = tokenize(tokenizer, [passage_by_id[poi_id] for poi_id in passage_ids], config["passage_prefix"], config["max_passage_tokens"], device)
        index = {poi_id: i for i, poi_id in enumerate(passage_ids)}
        pos_mask = torch.zeros((len(batch), len(passage_ids)), dtype=torch.bool, device=device)
        allowed_mask = torch.ones((len(batch), len(passage_ids)), dtype=torch.bool, device=device)
        usable: list[int] = []
        for row_i, row in enumerate(batch):
            pool = set(row["pool"])
            pos_cols = [index[poi_id] for poi_id in row["positives"] if poi_id in index]
            if not pos_cols:
                continue
            pos_mask[row_i, pos_cols] = True
            for poi_id, col in index.items():
                if poi_id in pool and not pos_mask[row_i, col]:
                    allowed_mask[row_i, col] = False
            if int(allowed_mask[row_i].sum().item()) <= len(pos_cols):
                pos_mask[row_i, :] = False
                continue
            usable.append(row_i)
        if not usable:
            continue
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
            query_vec = embed(model, query_inputs)
            passage_vec = embed(model, passage_inputs)
            logits = (query_vec @ passage_vec.T) * config["temperature_scale"]
            usable_idx = torch.tensor(usable, device=device, dtype=torch.long)
            per = multi_positive_loss(logits[usable_idx], pos_mask[usable_idx], allowed_mask[usable_idx])
            loss = per.mean()
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), config["max_grad_norm"])
        scale_before = scaler.get_scale()
        scaler.step(optimizer)
        scaler.update()
        if scaler.get_scale() >= scale_before:
            scheduler.step()
        losses.append(float(loss.detach().cpu()))
    return {"steps": len(batches), "mean_loss": (sum(losses) / len(losses)) if losses else None, "elapsed_seconds": round(time.time() - started, 1)}


def tokenize(tokenizer: Any, texts: list[str], prefix: str, max_length: int, device: Any) -> dict[str, Any]:
    tokens = tokenizer([prefix + text for text in texts], padding=True, truncation=True, max_length=max_length, return_tensors="pt")
    tokens.pop("token_type_ids", None)
    return {key: value.to(device) for key, value in tokens.items()}


def embed(model: Any, tokens: dict[str, Any]) -> Any:
    import torch.nn.functional as functional

    return functional.normalize(mean_pool(model(**tokens).last_hidden_state, tokens["attention_mask"]), p=2, dim=1)


def multi_positive_loss(logits, pos_mask, allowed_mask):
    import torch

    neg_inf = torch.finfo(logits.dtype).min
    pos_logits = logits.masked_fill(~pos_mask, neg_inf)
    allowed_logits = logits.masked_fill(~allowed_mask, neg_inf)
    return -(torch.logsumexp(pos_logits, dim=1) - torch.logsumexp(allowed_logits, dim=1))


def encode_corpus(model: Any, tokenizer: Any, passages: list[str], config: dict[str, Any], device: Any) -> np.ndarray:
    return encode_texts(model, tokenizer, passages, config["passage_prefix"], config["max_passage_tokens"], config["encode_batch_size"], device)


def score_brand(model: Any, tokenizer: Any, corpus: np.ndarray, corpus_ids: list[str], frame: pd.DataFrame, config: dict[str, Any], device: Any) -> dict[str, float]:
    vectors = encode_texts(model, tokenizer, frame["query_text"].astype(str).tolist(), config["query_prefix"], config["max_query_tokens"], config["encode_batch_size"], device)
    return brand_metrics(frame, exact_topk(vectors, corpus, corpus_ids, 50))


def score_poi(model: Any, tokenizer: Any, corpus: np.ndarray, corpus_ids: list[str], frame: pd.DataFrame, config: dict[str, Any], device: Any) -> float:
    vectors = encode_texts(model, tokenizer, frame["query_text"].astype(str).tolist(), config["query_prefix"], config["max_query_tokens"], config["encode_batch_size"], device)
    return poi_hit1(frame, exact_topk(vectors, corpus, corpus_ids, 50))


def keep_epoch(brand: dict[str, float], poi: float, base_brand: dict[str, float], base_poi: float, drop_limit: float) -> bool:
    return brand["Hit@1"] + 1e-12 >= base_brand["Hit@1"] and poi + 1e-12 >= base_poi - drop_limit


def main() -> None:
    ensure_kaggle_gpu_compatibility()
    import torch
    from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

    if not torch.cuda.is_available():
        raise SystemExit("This kernel requires a CUDA GPU")
    device = torch.device("cuda")
    config = json.loads(find_file("train_config.json").read_text(encoding="utf-8"))
    families = json.loads(find_file("split_families.json").read_text(encoding="utf-8"))
    train_f, dev_f, gold_f = set(families["train"]), set(families["dev"]), set(families["gold"])
    if train_f & dev_f or train_f & gold_f or dev_f & gold_f:
        raise SystemExit("Brand family splits overlap")
    docs = pd.read_parquet(find_file("search_documents.parquet"), columns=["poi_id", "passage_context"])
    corpus_ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].fillna("").astype(str).tolist()
    passage_by_id = dict(zip(corpus_ids, passages))
    poi_view = pd.read_parquet(find_file("query_train_view.parquet"))
    poi_dev = poi_view[poi_view["split"] == "dev"].reset_index(drop=True)
    brand_train = pd.read_parquet(find_file("brand_train_queries.parquet"))
    brand_dev = pd.read_parquet(find_file("brand_dev_queries.parquet"))
    gold_poi_ids = set(pd.read_csv(find_file("gold_query_variants.csv"))["intended_poi_id"].astype(str))
    checkpoint = find_file("model.safetensors").parent
    print(
        f"brand_train={len(brand_train)} brand_dev={len(brand_dev)} poi_dev={len(poi_dev)} docs={len(docs)}",
        flush=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModel.from_pretrained(checkpoint).to(device)
    rows = build_train_rows(brand_train, corpus_ids, gold_poi_ids, config)
    print(f"trainable_brand_queries={len(rows)}", flush=True)
    out = Path("/kaggle/working/brand_trial")
    out.mkdir(parents=True, exist_ok=True)

    def snapshot() -> dict[str, Any]:
        return {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}

    def restore(state: dict[str, Any]) -> None:
        model.load_state_dict({key: value.to(device) for key, value in state.items()})

    base_state = snapshot()
    print("encode baseline corpus", flush=True)
    corpus = encode_corpus(model, tokenizer, passages, config, device)
    base_brand = score_brand(model, tokenizer, corpus, corpus_ids, brand_dev, config, device)
    base_poi = score_poi(model, tokenizer, corpus, corpus_ids, poi_dev, config, device)
    print(f"baseline brand Hit@1={base_brand['Hit@1']:.4f} poi dev Hit@1={base_poi:.4f}", flush=True)
    best_state = base_state
    best = {"epoch": 0, "brand_dev": base_brand, "poi_dev_hit1": base_poi, "keep": True}
    epoch_eval = []
    steps_per_epoch = max(1, (len(rows) + config["train_batch_size"] - 1) // config["train_batch_size"])
    total_steps = steps_per_epoch * config["epochs"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * config["warmup_ratio"]), total_steps)
    scaler = torch.amp.GradScaler("cuda")
    for epoch in range(1, config["epochs"] + 1):
        stats = train_epoch(model, tokenizer, rows, passage_by_id, config, device, optimizer, scheduler, scaler, epoch)
        print(f"epoch {epoch} loss={stats['mean_loss']}", flush=True)
        corpus = encode_corpus(model, tokenizer, passages, config, device)
        brand = score_brand(model, tokenizer, corpus, corpus_ids, brand_dev, config, device)
        poi = score_poi(model, tokenizer, corpus, corpus_ids, poi_dev, config, device)
        kept = keep_epoch(brand, poi, base_brand, base_poi, float(config["poi_dev_drop_limit"]))
        row = {"epoch": epoch, "train": stats, "brand_dev": brand, "poi_dev_hit1": poi, "keep": kept, "selection": config["checkpoint_selection"]}
        epoch_eval.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if kept and (best["epoch"] == 0 or brand["Hit@1"] >= best["brand_dev"]["Hit@1"]):
            best_state = snapshot()
            best = {"epoch": epoch, "brand_dev": brand, "poi_dev_hit1": poi, "keep": True}
    restore(best_state)
    print("score gold after lock", flush=True)
    corpus = encode_corpus(model, tokenizer, passages, config, device)
    brand_gold = pd.read_parquet(find_file("brand_gold_queries.parquet"))
    poi_gold = pd.read_csv(find_file("gold_query_variants.csv"))
    gold_brand = score_brand(model, tokenizer, corpus, corpus_ids, brand_gold, config, device)
    gold_poi = score_poi(model, tokenizer, corpus, corpus_ids, poi_gold, config, device)
    summary = {
        "experiment": config["experiment"],
        "checkpoint_selection": config["checkpoint_selection"],
        "gold_opened_after_lock": True,
        "baseline_brand_dev": base_brand,
        "baseline_poi_dev_hit1": base_poi,
        "kept_checkpoint": best,
        "epoch_eval": epoch_eval,
        "gold_brand": gold_brand,
        "gold_poi_hit1": gold_poi,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
