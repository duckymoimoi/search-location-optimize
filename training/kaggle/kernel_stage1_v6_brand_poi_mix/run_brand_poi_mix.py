#!/usr/bin/env python3
"""Continue the 6k checkpoint with POI pairs and brand queries in the same batch.

Does not write brand rows into the 6k pair table. POI rows keep their own
positives and hard negatives. Brand rows keep a multi-positive mask, and other
members of that family are not negatives.
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

CONFIG = {
    "experiment": "stage1_v6_brand_poi_mix",
    "checkpoint_selection": "brand_dev_and_poi_dev",
    "epochs": 2,
    "learning_rate": 2e-6,
    "weight_decay": 0.01,
    "warmup_ratio": 0.06,
    "max_grad_norm": 1.0,
    "temperature_scale": 20.0,
    "seed": 42,
    "poi_per_batch": 12,
    "brand_per_batch": 4,
    "positives_per_query": 4,
    "negatives_per_query": 4,
    "poi_dev_drop_limit": 0.01,
    "query_prefix": "query: ",
    "passage_prefix": "passage: ",
    "max_query_tokens": 64,
    "max_passage_tokens": 128,
    "encode_batch_size": 48,
}


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
            [sys.executable, "-m", "pip", "install", "--quiet", "--force-reinstall", "torch==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu126"],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "torchvision", "torchaudio"], check=False)


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


def poi_rows(frame: pd.DataFrame, pairs: pd.DataFrame) -> list[dict]:
    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"positives": [], "negatives": [], "ignore": []})
    for record in pairs.itertuples(index=False):
        bucket = grouped[str(record.query_id)]
        poi_id = str(record.poi_id)
        label = str(record.label)
        if label == "positive":
            bucket["positives"].append(poi_id)
        elif label == "negative":
            bucket["negatives"].append(poi_id)
        elif label == "ignore":
            bucket["ignore"].append(poi_id)
    rows = []
    for record in frame.to_dict("records"):
        query_id = str(record["query_id"])
        pack = grouped.get(query_id, {"positives": [], "negatives": [], "ignore": []})
        positives = list(dict.fromkeys(pack["positives"]))
        if not positives:
            continue
        rows.append(
            {
                "scope": "POI",
                "query_text": str(record["query_text"]),
                "intended_poi_id": str(record.get("intended_poi_id") or positives[0]),
                "sample_weight": float(record.get("sample_weight") or 1.0),
                "pool": positives,
                "positives": positives,
                "negatives": list(dict.fromkeys(pack["negatives"])),
                "ignore": set(pack["ignore"]),
            }
        )
    return rows


def brand_rows(frame: pd.DataFrame, corpus_ids: list[str], gold_ids: set[str], config: dict[str, Any]) -> list[dict]:
    rng = random.Random(config["seed"])
    corpus_set = set(corpus_ids)
    rows = []
    for record in frame.itertuples(index=False):
        pool = [poi_id for poi_id in dict.fromkeys(parse_ids(record.acceptable_poi_ids)) if poi_id in corpus_set and poi_id not in gold_ids]
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
                "scope": "BRAND",
                "query_text": str(record.query_text),
                "brand_family_id": str(record.brand_family_id),
                "intended_poi_id": "",
                "sample_weight": 1.0,
                "pool": pool,
                "positives": chosen,
                "negatives": negatives,
                "ignore": set(),
            }
        )
    return rows


def mix_batches(poi: list[dict], brand: list[dict], config: dict[str, Any], epoch: int) -> list[list[dict]]:
    rng = random.Random(config["seed"] + epoch)
    poi_order = list(poi)
    brand_order = list(brand)
    rng.shuffle(poi_order)
    rng.shuffle(brand_order)
    cursor = 0
    batches: list[list[dict]] = []
    for start in range(0, len(brand_order), config["brand_per_batch"]):
        chunk = brand_order[start : start + config["brand_per_batch"]]
        blocked = set()
        families = {row["brand_family_id"] for row in chunk}
        for row in chunk:
            blocked.update(row["pool"])
        picked: list[dict] = []
        seen_targets: set[str] = set()
        scanned = 0
        while len(picked) < config["poi_per_batch"] and scanned < len(poi_order) * 2:
            row = poi_order[cursor % len(poi_order)]
            cursor += 1
            scanned += 1
            target = row["intended_poi_id"]
            if target in seen_targets or target in blocked:
                continue
            if set(row["positives"]) & blocked or set(row["negatives"]) & blocked:
                continue
            picked.append(row)
            seen_targets.add(target)
        if len(picked) < config["poi_per_batch"]:
            raise RuntimeError(f"Could not fill POI side of a mixed batch ({len(picked)})")
        del families
        batches.append(chunk + picked)
    return batches


def train_epoch(model: Any, tokenizer: Any, batches: list[list[dict]], passage_by_id: dict[str, str], config: dict[str, Any], device: Any, optimizer: Any, scheduler: Any, scaler: Any) -> dict[str, Any]:
    import torch

    losses: list[float] = []
    model.train()
    started = time.time()
    for batch in batches:
        passage_ids: list[str] = []
        seen: set[str] = set()
        for row in batch:
            for poi_id in list(row["positives"]) + list(row["negatives"]):
                if poi_id not in seen and poi_id in passage_by_id and poi_id not in row["ignore"]:
                    seen.add(poi_id)
                    passage_ids.append(poi_id)
        if not passage_ids:
            continue
        query_inputs = tokenize(tokenizer, [row["query_text"] for row in batch], config["query_prefix"], config["max_query_tokens"], device)
        passage_inputs = tokenize(tokenizer, [passage_by_id[poi_id] for poi_id in passage_ids], config["passage_prefix"], config["max_passage_tokens"], device)
        index = {poi_id: i for i, poi_id in enumerate(passage_ids)}
        pos_mask = torch.zeros((len(batch), len(passage_ids)), dtype=torch.bool, device=device)
        allowed_mask = torch.zeros((len(batch), len(passage_ids)), dtype=torch.bool, device=device)
        usable: list[int] = []
        for row_i, row in enumerate(batch):
            pool = set(row["pool"])
            ignore = set(row["ignore"])
            pos_cols = [index[poi_id] for poi_id in row["positives"] if poi_id in index and poi_id not in ignore]
            if not pos_cols:
                continue
            pos_mask[row_i, pos_cols] = True
            for poi_id in list(row["positives"]) + list(row["negatives"]):
                if poi_id in index and poi_id not in ignore and not (row["scope"] == "BRAND" and poi_id in pool and poi_id not in row["positives"]):
                    allowed_mask[row_i, index[poi_id]] = True
            for poi_id, col in index.items():
                if row["scope"] == "BRAND" and poi_id in pool and poi_id not in row["positives"]:
                    allowed_mask[row_i, col] = False
                if poi_id in ignore:
                    allowed_mask[row_i, col] = False
            allowed_mask[row_i].logical_or_(pos_mask[row_i])
            if int(allowed_mask[row_i].sum().item()) <= len(pos_cols):
                pos_mask[row_i, :] = False
                continue
            usable.append(row_i)
        if not usable:
            continue
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
            logits = (embed(model, query_inputs) @ embed(model, passage_inputs).T) * config["temperature_scale"]
            usable_idx = torch.tensor(usable, device=device, dtype=torch.long)
            per = multi_positive_loss(logits[usable_idx], pos_mask[usable_idx], allowed_mask[usable_idx])
            weights = torch.tensor([float(batch[i]["sample_weight"]) for i in usable], device=device)
            loss = (per * weights).sum() / torch.clamp(weights.sum(), min=1e-6)
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
    return -(torch.logsumexp(logits.masked_fill(~pos_mask, neg_inf), dim=1) - torch.logsumexp(logits.masked_fill(~allowed_mask, neg_inf), dim=1))


def encode_corpus(model: Any, tokenizer: Any, passages: list[str], device: Any) -> np.ndarray:
    return encode_texts(model, tokenizer, passages, CONFIG["passage_prefix"], CONFIG["max_passage_tokens"], CONFIG["encode_batch_size"], device)


def score_brand(model: Any, tokenizer: Any, corpus: np.ndarray, corpus_ids: list[str], frame: pd.DataFrame, device: Any) -> dict[str, float]:
    vectors = encode_texts(model, tokenizer, frame["query_text"].astype(str).tolist(), CONFIG["query_prefix"], CONFIG["max_query_tokens"], CONFIG["encode_batch_size"], device)
    return brand_metrics(frame, exact_topk(vectors, corpus, corpus_ids, 50))


def score_poi(model: Any, tokenizer: Any, corpus: np.ndarray, corpus_ids: list[str], frame: pd.DataFrame, device: Any) -> float:
    vectors = encode_texts(model, tokenizer, frame["query_text"].astype(str).tolist(), CONFIG["query_prefix"], CONFIG["max_query_tokens"], CONFIG["encode_batch_size"], device)
    return poi_hit1(frame, exact_topk(vectors, corpus, corpus_ids, 50))


def main() -> None:
    ensure_kaggle_gpu_compatibility()
    import torch
    from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

    if not torch.cuda.is_available():
        raise SystemExit("This kernel requires a CUDA GPU")
    device = torch.device("cuda")
    families = json.loads(find_file("split_families.json").read_text(encoding="utf-8"))
    if set(families["train"]) & set(families["dev"]) or set(families["train"]) & set(families["gold"]) or set(families["dev"]) & set(families["gold"]):
        raise SystemExit("Brand family splits overlap")
    docs = pd.read_parquet(find_file("search_documents.parquet"), columns=["poi_id", "passage_context"])
    corpus_ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].fillna("").astype(str).tolist()
    passage_by_id = dict(zip(corpus_ids, passages))
    view = pd.read_parquet(find_file("query_train_view.parquet"))
    pairs = pd.read_parquet(find_file("training_pairs.parquet"))
    poi_train = poi_rows(view[view["split"] == "train"], pairs)
    poi_dev = view[view["split"] == "dev"].reset_index(drop=True)
    brand_train = pd.read_parquet(find_file("brand_train_queries.parquet"))
    brand_dev = pd.read_parquet(find_file("brand_dev_queries.parquet"))
    gold_poi = pd.read_csv(find_file("gold_query_variants.csv"))
    gold_ids: set[str] = set()
    for raw in gold_poi["acceptable_poi_ids"]:
        gold_ids.update(parse_ids(raw))
    gold_ids.update(gold_poi["intended_poi_id"].astype(str))
    if set(pairs["poi_id"].astype(str)) & gold_ids:
        raise SystemExit("POI pairs still contain Gold ids")
    checkpoint = find_file("model.safetensors").parent
    brand = brand_rows(brand_train, corpus_ids, gold_ids, CONFIG)
    print(f"poi_train={len(poi_train)} brand_train={len(brand)} poi_dev={len(poi_dev)}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModel.from_pretrained(checkpoint).to(device)
    out = Path("/kaggle/working/brand_poi_mix")
    out.mkdir(parents=True, exist_ok=True)

    def snapshot() -> dict[str, Any]:
        return {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}

    def restore(state: dict[str, Any]) -> None:
        model.load_state_dict({key: value.to(device) for key, value in state.items()})

    base_state = snapshot()
    corpus = encode_corpus(model, tokenizer, passages, device)
    base_brand = score_brand(model, tokenizer, corpus, corpus_ids, brand_dev, device)
    base_poi = score_poi(model, tokenizer, corpus, corpus_ids, poi_dev, device)
    print(f"baseline brand Hit@1={base_brand['Hit@1']:.4f} poi dev Hit@1={base_poi:.4f}", flush=True)
    best_state = base_state
    best = {"epoch": 0, "brand_dev": base_brand, "poi_dev_hit1": base_poi, "keep": True}
    epoch_eval = []
    steps = max(1, (len(brand) + CONFIG["brand_per_batch"] - 1) // CONFIG["brand_per_batch"]) * CONFIG["epochs"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG["learning_rate"], weight_decay=CONFIG["weight_decay"])
    scheduler = get_linear_schedule_with_warmup(optimizer, int(steps * CONFIG["warmup_ratio"]), steps)
    scaler = torch.amp.GradScaler("cuda")
    for epoch in range(1, CONFIG["epochs"] + 1):
        batches = mix_batches(poi_train, brand, CONFIG, epoch)
        stats = train_epoch(model, tokenizer, batches, passage_by_id, CONFIG, device, optimizer, scheduler, scaler)
        print(f"epoch {epoch} loss={stats['mean_loss']} steps={stats['steps']}", flush=True)
        corpus = encode_corpus(model, tokenizer, passages, device)
        brand_score = score_brand(model, tokenizer, corpus, corpus_ids, brand_dev, device)
        poi_score = score_poi(model, tokenizer, corpus, corpus_ids, poi_dev, device)
        kept = brand_score["Hit@1"] + 1e-12 >= base_brand["Hit@1"] and poi_score + 1e-12 >= base_poi - CONFIG["poi_dev_drop_limit"]
        row = {"epoch": epoch, "train": stats, "brand_dev": brand_score, "poi_dev_hit1": poi_score, "keep": kept, "poi_per_batch": CONFIG["poi_per_batch"], "brand_per_batch": CONFIG["brand_per_batch"]}
        epoch_eval.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if kept and (best["epoch"] == 0 or brand_score["Hit@1"] >= best["brand_dev"]["Hit@1"]):
            best_state = snapshot()
            best = {"epoch": epoch, "brand_dev": brand_score, "poi_dev_hit1": poi_score, "keep": True}
    restore(best_state)
    corpus = encode_corpus(model, tokenizer, passages, device)
    gold_brand = score_brand(model, tokenizer, corpus, corpus_ids, pd.read_parquet(find_file("brand_gold_queries.parquet")), device)
    gold_poi_hit = score_poi(model, tokenizer, corpus, corpus_ids, gold_poi, device)
    summary = {
        "experiment": CONFIG["experiment"],
        "checkpoint_selection": CONFIG["checkpoint_selection"],
        "gold_opened_after_lock": True,
        "mix": {"poi_per_batch": CONFIG["poi_per_batch"], "brand_per_batch": CONFIG["brand_per_batch"]},
        "writes_brand_into_poi_pairs": False,
        "baseline_brand_dev": base_brand,
        "baseline_poi_dev_hit1": base_poi,
        "kept_checkpoint": best,
        "epoch_eval": epoch_eval,
        "gold_brand": gold_brand,
        "gold_poi_hit1": gold_poi_hit,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ckpt_dir = out / "checkpoint"
    model.save_pretrained(ckpt_dir)
    tokenizer.save_pretrained(ckpt_dir)
    np.save(out / "corpus_embeddings.npy", corpus)
    pd.DataFrame({"poi_id": corpus_ids}).to_parquet(out / "poi_ids.parquet", index=False)
    (out / "embedding_manifest.json").write_text(
        json.dumps(
            {
                "model_id": "intfloat/multilingual-e5-small",
                "checkpoint": "stage1_v6_brand_poi_mix epoch 2",
                "corpus_version": "vn-poi-core-v3-semantic-address-dedup50",
                "row_count": int(corpus.shape[0]),
                "embedding_dimension": int(corpus.shape[1]),
                "max_length": 128,
                "index_name": "vn-poi-core-v3-me5-brand-poi-mix",
                "do_not_overwrite": ["artifacts/embeddings/me5_small_v3", "vn-poi-core-v3-me5-small"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
