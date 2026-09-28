#!/usr/bin/env python3
"""Kaggle GPU: fine-tune mE5-small on the isolated v6 hard-negative pilot.

Uses compiled views + mined pairs. Does not overwrite the in-batch kernel.
The pack does not include embeddings; this script encodes the corpus itself.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

RECALL_KS = (100, 500, 1000)
DIAG_KS = (1, 5, 10, 20, 50)
PREFIX_KS = (1, 5, 10)
SHC_W = 3
PREFIX_DEPTH = 50


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_ids(raw) -> list[str]:
    if raw is None:
        return []
    try:
        if raw != raw:  # NaN
            return []
    except Exception:
        pass
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def resolve_input(preferred: Path) -> Path:
    if (preferred / "search_documents.parquet").exists() and (preferred / "training_pairs.parquet").exists():
        return preferred
    kaggle_input = Path("/kaggle/input")
    if kaggle_input.exists():
        matches = sorted(kaggle_input.rglob("training_pairs.parquet"))
        for match in matches:
            if (match.parent / "search_documents.parquet").exists():
                return match.parent
    raise FileNotFoundError(f"Hardneg pilot pack not under {preferred}")


def disable_torch_compile() -> None:
    os.environ["TORCHDYNAMO_DISABLE"] = "1"
    os.environ["TORCH_COMPILE_DISABLE"] = "1"
    try:
        import torch._dynamo

        torch._dynamo.config.disable = True
    except Exception:
        pass


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


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return torch.sum(last_hidden_state * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)


def model_embeddings(model: Any, encoded: dict[str, Any]) -> Any:
    import torch.nn.functional as functional

    hidden = model(**encoded).last_hidden_state
    return functional.normalize(mean_pool(hidden, encoded["attention_mask"]), p=2, dim=1)


def make_unique_batches(rows: list[dict], batch_size: int, seed: int) -> list[list[dict]]:
    pending = list(rows)
    random.Random(seed).shuffle(pending)
    batches: list[list[dict]] = []
    while pending:
        batch: list[dict] = []
        deferred: list[dict] = []
        target_ids: set[str] = set()
        entity_ids: set[str] = set()
        compatible_ids: set[str] = set()
        queries: set[str] = set()
        for row in pending:
            target = str(row.get("intended_poi_id") or (row.get("positives") or [""])[0])
            entity = str(row.get("entity_group_id") or row.get("brand_family_id") or target)
            compatible = set(row["positives"])
            query_key = " ".join(str(row["query_text"]).casefold().split())
            conflict = (
                target in target_ids
                or entity in entity_ids
                or query_key in queries
                or bool(compatible & compatible_ids)
            )
            if len(batch) < batch_size and not conflict:
                batch.append(row)
                target_ids.add(target)
                entity_ids.add(entity)
                compatible_ids.update(compatible)
                queries.add(query_key)
            else:
                deferred.append(row)
        if not batch:
            raise RuntimeError("Unique batch sampler made no progress")
        batches.append(batch)
        pending = deferred
    return batches


def encode_texts(
    model: Any,
    tokenizer: Any,
    texts: list[str],
    prefix: str,
    max_length: int,
    batch_size: int,
    device: Any,
) -> tuple[np.ndarray, float]:
    import torch
    import torch.nn.functional as functional

    parts: list[np.ndarray] = []
    model.eval()
    started = time.time()
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = [prefix + text for text in texts[start : start + batch_size]]
            tokens = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            tokens.pop("token_type_ids", None)
            tokens = {key: value.to(device) for key, value in tokens.items()}
            vec = functional.normalize(mean_pool(model(**tokens).last_hidden_state, tokens["attention_mask"]), p=2, dim=1)
            parts.append(vec.cpu().numpy().astype(np.float32, copy=False))
            done = min(start + batch_size, len(texts))
            if start == 0 or done == len(texts) or done % (batch_size * 20) == 0:
                print(f"  encoded {done}/{len(texts)}", flush=True)
    return np.concatenate(parts), time.time() - started


def exact_topk(
    queries: np.ndarray, corpus: np.ndarray, ids: list[str], top_k: int, chunk: int
) -> list[list[str]]:
    out: list[list[str]] = []
    for start in range(0, len(queries), chunk):
        scores = queries[start : start + chunk] @ corpus.T
        for row_scores in scores:
            k = min(top_k, len(row_scores))
            cand = np.argpartition(-row_scores, k - 1)[:k]
            order = np.lexsort((cand, -row_scores[cand]))
            out.append([ids[i] for i in cand[order]])
    return out


def best_rank(top_ids: list[str], acceptable: set[str], depth: int) -> int:
    for index, poi_id in enumerate(top_ids, start=1):
        if poi_id in acceptable:
            return index if index <= depth else depth + 1
    return depth + 1


def k_at_recall(ranks: list[int], rate: float, depth: int) -> int | None:
    if not ranks:
        return None
    need = int(np.ceil(rate * len(ranks)))
    ordered = sorted(ranks)
    if need > len(ordered):
        return None
    value = ordered[need - 1]
    return int(value) if value <= depth else None


def summarize_rows(rows: list[dict], label: str, depth: int) -> dict[str, Any]:
    ranks = [row["best_rank"] for row in rows]
    count = len(ranks)
    out: dict[str, Any] = {"n": count, "label": label, "recall": {}, "diagnostic": {}, "k_at_r": {}}
    for k in RECALL_KS:
        out["recall"][f"Recall@{k}"] = sum(rank <= k for rank in ranks) / count if count else 0.0
    for k in DIAG_KS:
        out["diagnostic"][f"Hit@{k}"] = sum(rank <= k for rank in ranks) / count if count else 0.0
    out["diagnostic"]["MRR@10"] = (
        sum((1.0 / rank) for rank in ranks if rank <= 10) / count if count else 0.0
    )
    out["k_at_r"]["K@95"] = k_at_recall(ranks, 0.95, depth)
    out["k_at_r"]["K@98"] = k_at_recall(ranks, 0.98, depth)
    return out


def profile_report(rows: list[dict], depth: int) -> dict[str, Any]:
    by_family: dict[str, list[dict]] = defaultdict(list)
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_family[str(row["query_variant_family"])].append(row)
        by_stratum[str(row["primary_sampling_stratum"])].append(row)
    return {
        "overall": summarize_rows(rows, "overall", depth),
        "by_family": {key: summarize_rows(value, key, depth) for key, value in by_family.items()},
        "by_stratum": {key: summarize_rows(value, key, depth) for key, value in by_stratum.items()},
    }


def evaluate_frame(
    model: Any,
    tokenizer: Any,
    corpus_vectors: np.ndarray,
    corpus_ids: list[str],
    frame: pd.DataFrame,
    config: dict[str, Any],
    device: Any,
    out_path: Path | None,
    profile: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    query_vectors, encode_s = encode_texts(
        model,
        tokenizer,
        frame["query_text"].astype(str).tolist(),
        config["query_prefix"],
        config["max_query_tokens"],
        config["encode_batch_size"],
        device,
    )
    ranked = exact_topk(
        query_vectors, corpus_vectors, corpus_ids, config["eval_depth"], chunk=16
    )
    rows: list[dict[str, Any]] = []
    handle = out_path.open("w", encoding="utf-8") if out_path else None
    try:
        for record, top in zip(frame.itertuples(index=False), ranked):
            acceptable = set(parse_ids(getattr(record, "acceptable_poi_ids")))
            if not acceptable:
                acceptable = {str(record.intended_poi_id)}
            intended = str(record.intended_poi_id)
            try:
                intended_rank = top.index(intended) + 1
            except ValueError:
                intended_rank = None
            row = {
                "variant_id": record.variant_id,
                "case_id": record.case_id,
                "query_text": record.query_text,
                "query_variant_family": getattr(record, "query_variant_family", ""),
                "primary_sampling_stratum": getattr(record, "primary_sampling_stratum", ""),
                "intended_poi_id": intended,
                "acceptable_poi_ids": sorted(acceptable),
                "rank": intended_rank,
                "best_rank": best_rank(top, acceptable, config["eval_depth"]),
                "top_ids": top[:50],
                "profile": profile,
            }
            rows.append(row)
            if handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if handle:
            handle.close()
    report = profile_report(rows, config["eval_depth"])
    report["meta"] = {"encode_queries_s": round(encode_s, 1), "n": len(rows)}
    return report, rows


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
        if not chars:
            continue
        acceptable = parse_ids(getattr(row, "acceptable_poi_ids", None))
        if not acceptable:
            acceptable = [str(row.intended_poi_id)]
        for n in range(1, len(chars) + 1):
            prefix = "".join(chars[:n])
            if not prefix.strip():
                continue
            rows.append(
                {
                    "variant_id": row.variant_id,
                    "case_id": row.case_id,
                    "query_variant_family": getattr(row, "query_variant_family", ""),
                    "primary_sampling_stratum": getattr(row, "primary_sampling_stratum", ""),
                    "intended_poi_id": str(row.intended_poi_id),
                    "acceptable_poi_ids": "|".join(acceptable),
                    "prefix_text": prefix,
                    "prefix_index": n,
                    "full_unit_count": len(chars),
                    "is_full_query": n == len(chars),
                }
            )
    return pd.DataFrame(rows)


def session_prefix_metrics(ranks: list[int | None]) -> dict[str, Any]:
    t_q = len(ranks)
    out: dict[str, Any] = {"T_q": t_q, "fhc": {}, "shc": {}, "prefix_auc": {}}
    for k in PREFIX_KS:
        hits = [rank is not None and rank <= k for rank in ranks]
        fhc = next((index + 1 for index, hit in enumerate(hits) if hit), None)
        shc = None
        if t_q >= SHC_W:
            for start in range(0, t_q - SHC_W + 1):
                if all(hits[index] for index in range(start, start + SHC_W)):
                    shc = start + 1
                    break
        out["fhc"][k] = {"found": fhc is not None, "value": fhc}
        out["shc"][k] = {"found": shc is not None, "value": shc, "w": SHC_W}
        out["prefix_auc"][k] = sum(hits) / t_q if t_q else 0.0
    return out


def summarize_prefix(prefix_df: pd.DataFrame, ranks: list[int | None]) -> dict[str, Any]:
    by_vid: dict[str, list] = defaultdict(list)
    for row, rank in zip(prefix_df.itertuples(index=False), ranks):
        by_vid[str(row.variant_id)].append(
            {
                "prefix_index": int(row.prefix_index),
                "rank": rank,
                "query_variant_family": str(row.query_variant_family),
                "case_id": str(row.case_id),
            }
        )
    variants: dict[str, dict[str, Any]] = {}
    for vid, items in by_vid.items():
        items = sorted(items, key=lambda item: item["prefix_index"])
        metrics = session_prefix_metrics([item["rank"] for item in items])
        metrics["query_variant_family"] = items[0]["query_variant_family"]
        variants[vid] = metrics
    count = len(variants)

    def agg(metric: str, k: int) -> dict[str, Any]:
        values, miss = [], 0
        for info in variants.values():
            cell = info[metric][k]
            if not cell["found"]:
                miss += 1
            else:
                values.append(cell["value"])
        arr = np.asarray(values, dtype=np.float64) if values else np.asarray([], dtype=np.float64)
        return {
            "hit_rate": (count - miss) / count if count else 0.0,
            "n_found": count - miss,
            "n_miss": miss,
            "mean_conditional": float(arr.mean()) if len(arr) else None,
            "p50_conditional": float(np.quantile(arr, 0.5)) if len(arr) else None,
        }

    summary: dict[str, Any] = {
        "n_variants": count,
        "n_prefixes": int(len(prefix_df)),
        "prefix_unit": "char_grapheme",
        "shc_window": SHC_W,
        "shc_requires_full_window": True,
        "k_list": list(PREFIX_KS),
        "fhc": {},
        "shc": {},
        "prefix_auc": {},
        "by_family": {},
    }
    for k in PREFIX_KS:
        summary["fhc"][f"@{k}"] = agg("fhc", k)
        summary["shc"][f"@{k}"] = agg("shc", k)
        aucs = [info["prefix_auc"][k] for info in variants.values()]
        arr = np.asarray(aucs, dtype=np.float64)
        summary["prefix_auc"][f"@{k}"] = {
            "mean": float(arr.mean()) if len(arr) else 0.0,
            "p50": float(np.quantile(arr, 0.5)) if len(arr) else 0.0,
        }
    by_family: dict[str, list] = defaultdict(list)
    for info in variants.values():
        by_family[str(info["query_variant_family"])].append(info)
    for family, items in by_family.items():
        n_family = len(items)
        summary["by_family"][family] = {
            "n": n_family,
            **{f"FHC-char-HitRate@{k}": sum(1 for item in items if item["fhc"][k]["found"]) / n_family for k in PREFIX_KS},
            **{f"SHC-char-HitRate@{k}": sum(1 for item in items if item["shc"][k]["found"]) / n_family for k in PREFIX_KS},
            **{f"PrefixAUC-char@{k}_mean": float(np.mean([item["prefix_auc"][k] for item in items])) for k in PREFIX_KS},
        }
    return summary


def evaluate_prefix(
    model: Any,
    tokenizer: Any,
    corpus_vectors: np.ndarray,
    corpus_ids: list[str],
    prefix_df: pd.DataFrame,
    config: dict[str, Any],
    device: Any,
    out_path: Path | None = None,
) -> dict[str, Any]:
    query_vectors, encode_s = encode_texts(
        model,
        tokenizer,
        prefix_df["prefix_text"].astype(str).tolist(),
        config["query_prefix"],
        config["max_query_tokens"],
        config["encode_batch_size"],
        device,
    )
    ranked = exact_topk(query_vectors, corpus_vectors, corpus_ids, PREFIX_DEPTH, chunk=32)
    ranks: list[int | None] = []
    dumped: list[dict[str, Any]] = []
    for record, top in zip(prefix_df.itertuples(index=False), ranked):
        acceptable = set(parse_ids(record.acceptable_poi_ids))
        rank = next((index for index, poi_id in enumerate(top, start=1) if poi_id in acceptable), None)
        ranks.append(rank)
        dumped.append(
            {
                "variant_id": str(record.variant_id),
                "case_id": str(record.case_id),
                "prefix_index": int(record.prefix_index),
                "prefix_text": str(record.prefix_text),
                "rank": rank,
            }
        )
    if out_path is not None:
        out_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in dumped),
            encoding="utf-8",
        )
    summary = summarize_prefix(prefix_df, ranks)
    summary["meta"] = {"encode_prefixes_s": round(encode_s, 1), "n_prefixes": int(len(prefix_df))}
    print(
        "  prefix "
        f"FHC@5={summary['fhc']['@5']['hit_rate']:.3f} "
        f"SHC@5={summary['shc']['@5']['hit_rate']:.3f} "
        f"PrefixAUC@5={summary['prefix_auc']['@5']['mean']:.3f}",
        flush=True,
    )
    return summary


def gate_table(profiles: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, report in profiles.items():
        row: dict[str, Any] = {
            "profile": name,
            "Recall@100": report.get("overall", {}).get("recall", {}).get("Recall@100"),
            "Recall@1000": report.get("overall", {}).get("recall", {}).get("Recall@1000"),
            "Hit@1": report.get("overall", {}).get("diagnostic", {}).get("Hit@1"),
            "Hit@5": report.get("overall", {}).get("diagnostic", {}).get("Hit@5"),
            "MRR@10": report.get("overall", {}).get("diagnostic", {}).get("MRR@10"),
            "K@95": report.get("overall", {}).get("k_at_r", {}).get("K@95"),
        }
        prefix = report.get("prefix")
        if prefix:
            row["FHC-char-HitRate@1"] = prefix["fhc"]["@1"]["hit_rate"]
            row["FHC-char-HitRate@5"] = prefix["fhc"]["@5"]["hit_rate"]
            row["FHC-char-HitRate@10"] = prefix["fhc"]["@10"]["hit_rate"]
            row["SHC-char-HitRate@1"] = prefix["shc"]["@1"]["hit_rate"]
            row["SHC-char-HitRate@5"] = prefix["shc"]["@5"]["hit_rate"]
            row["SHC-char-HitRate@10"] = prefix["shc"]["@10"]["hit_rate"]
            row["PrefixAUC-char@5"] = prefix["prefix_auc"]["@5"]["mean"]
            row["PrefixAUC-char@10"] = prefix["prefix_auc"]["@10"]["mean"]
        rows.append(row)
    return rows


def hit1(report: dict[str, Any]) -> float:
    return float(report["overall"]["diagnostic"]["Hit@1"])


def keep_checkpoint(dev: dict[str, Any], zero_dev: dict[str, Any]) -> bool:
    """Dev-only lock. Gold must not enter this decision."""
    return hit1(dev) + 1e-12 >= hit1(zero_dev)


def tokenize_texts(tokenizer: Any, texts: list[str], prefix: str, max_length: int, device: Any) -> dict[str, Any]:
    tokens = tokenizer(
        [prefix + text for text in texts],
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    tokens.pop("token_type_ids", None)
    return {key: value.to(device) for key, value in tokens.items()}


def masked_multi_positive_loss(logits, pos_mask, allowed_mask):
    import torch

    neg_inf = torch.finfo(logits.dtype).min
    pos_logits = logits.masked_fill(~pos_mask, neg_inf)
    allowed_logits = logits.masked_fill(~allowed_mask, neg_inf)
    return -(torch.logsumexp(pos_logits, dim=1) - torch.logsumexp(allowed_logits, dim=1))


def sample_pool_positives(pool: list[str], rng: random.Random, k_min: int = 2, k_max: int = 4) -> list[str]:
    unique = list(dict.fromkeys(str(item) for item in pool if item))
    if not unique:
        return []
    k = 1 if len(unique) == 1 else min(len(unique), rng.randint(k_min, min(k_max, len(unique))))
    return rng.sample(unique, k)


def apply_brand_epoch_sampling(rows: list[dict], seed: int) -> list[dict]:
    rng = random.Random(seed)
    sampled: list[dict] = []
    for row in rows:
        if str(row.get("intent_scope") or "POI") != "BRAND":
            sampled.append(row)
            continue
        pool = list(row.get("positive_pool") or row.get("positives") or [])
        chosen = sample_pool_positives(pool, rng)
        remainder = [poi_id for poi_id in pool if poi_id not in chosen]
        updated = dict(row)
        updated["positives"] = chosen
        updated["ignore"] = list(dict.fromkeys([*list(row.get("ignore") or []), *remainder]))
        sampled.append(updated)
    return sampled


def sample_epoch_rows(rows: list[dict], seed: int) -> list[dict]:
    rng = random.Random(seed)
    kept: list[dict] = []
    for row in rows:
        probability = float(row.get("sampling_probability", row.get("sample_weight", 1.0)))
        if probability >= 1.0 or rng.random() < max(probability, 0.0):
            kept.append(row)
    return apply_brand_epoch_sampling(kept, seed + 17)


def configure_training_weights(rows: list[dict], mode: str) -> list[dict]:
    """Keep the historical objective explicit; independent controls for new trials."""
    if mode not in {"legacy_both", "sampling_only", "loss_only"}:
        raise ValueError(f"Unknown weight mode: {mode}")
    configured = []
    for row in rows:
        weight = float(row.get("sample_weight", 1.0))
        if not np.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("slot weight must be finite and in [0, 1]")
        configured.append(dict(row, sampling_probability=weight if mode != "loss_only" or weight == 0 else 1.0,
                               loss_weight=weight if mode != "sampling_only" else (1.0 if weight > 0 else 0.0)))
    return configured


def train_one_epoch(
    model: Any,
    tokenizer: Any,
    rows: list[dict],
    passage_by_id: dict[str, str],
    config: dict[str, Any],
    device: Any,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
    epoch: int,
    epochs: int,
) -> dict[str, Any]:
    import torch

    batches = make_unique_batches(rows, config["train_batch_size"], config["seed"] + epoch)
    losses: list[float] = []
    skipped = 0
    model.train()
    started = time.time()
    for step, batch in enumerate(batches, start=1):
        passage_ids: list[str] = []
        seen: set[str] = set()
        for row in batch:
            for poi_id in row["positives"] + row["negatives"] + list(row.get("ignore") or []):
                if poi_id not in seen and poi_id in passage_by_id:
                    seen.add(poi_id)
                    passage_ids.append(poi_id)
        if not passage_ids:
            skipped += 1
            continue
        query_inputs = tokenize_texts(
            tokenizer,
            [row["query_text"] for row in batch],
            config["query_prefix"],
            config["max_query_tokens"],
            device,
        )
        passage_inputs = tokenize_texts(
            tokenizer,
            [passage_by_id[poi_id] for poi_id in passage_ids],
            config["passage_prefix"],
            config["max_passage_tokens"],
            device,
        )
        index = {poi_id: i for i, poi_id in enumerate(passage_ids)}
        pos_mask = torch.zeros((len(batch), len(passage_ids)), dtype=torch.bool, device=device)
        allowed_mask = torch.zeros((len(batch), len(passage_ids)), dtype=torch.bool, device=device)
        usable: list[int] = []
        for row_i, row in enumerate(batch):
            ignore = set(row["ignore"])
            pos_cols = [index[poi_id] for poi_id in row["positives"] if poi_id in index and poi_id not in ignore]
            if not pos_cols:
                skipped += 1
                continue
            pos_mask[row_i, pos_cols] = True
            allowed_mask[row_i, :] = True
            for poi_id in ignore:
                if poi_id in index:
                    allowed_mask[row_i, index[poi_id]] = False
            allowed_mask[row_i].logical_or_(pos_mask[row_i])
            if int(allowed_mask[row_i].sum().item()) <= len(pos_cols):
                skipped += 1
                pos_mask[row_i, :] = False
                allowed_mask[row_i, :] = False
                continue
            usable.append(row_i)
        if not usable:
            continue
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
            query_vec = model_embeddings(model, query_inputs)
            passage_vec = model_embeddings(model, passage_inputs)
            logits = (query_vec @ passage_vec.T) * config["temperature_scale"]
            usable_idx = torch.tensor(usable, device=device, dtype=torch.long)
            per = masked_multi_positive_loss(logits[usable_idx], pos_mask[usable_idx], allowed_mask[usable_idx])
            weights = torch.tensor([float(batch[i].get("loss_weight", batch[i]["sample_weight"])) for i in usable], device=device)
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
        if step == 1 or step == len(batches) or step % 50 == 0:
            print(
                f"  epoch {epoch}/{epochs} step {step}/{len(batches)} "
                f"loss={losses[-1]:.4f}",
                flush=True,
            )
    return {
        "epoch": epoch,
        "steps": len(batches),
        "skipped_queries": skipped,
        "mean_train_loss": float(np.mean(losses)) if losses else None,
        "elapsed_seconds": round(time.time() - started, 1),
    }


def rows_from_view(frame: pd.DataFrame, pairs: pd.DataFrame) -> list[dict]:
    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"positives": [], "negatives": [], "ignore": []})
    for record in pairs.itertuples(index=False):
        query_id = str(record.query_id)
        poi_id = str(record.poi_id)
        label = str(record.label)
        if label == "positive":
            grouped[query_id]["positives"].append(poi_id)
        elif label == "negative":
            grouped[query_id]["negatives"].append(poi_id)
        elif label == "ignore":
            grouped[query_id]["ignore"].append(poi_id)
    rows = []
    for record in frame.to_dict("records"):
        query_id = str(record["query_id"] if "query_id" in record else record["variant_id"])
        pack = grouped.get(query_id, {"positives": [], "negatives": [], "ignore": []})
        positives = pack["positives"] or parse_ids(record.get("acceptable_poi_ids"))
        if not positives and record.get("intended_poi_id"):
            positives = [str(record["intended_poi_id"])]
        rows.append(
            {
                "query_id": query_id,
                "case_id": str(record.get("case_id") or record.get("brand_family_id") or query_id),
                "variant_id": str(record.get("variant_id") or query_id),
                "query_text": str(record["query_text"]),
                "intended_poi_id": str(record.get("intended_poi_id") or (positives[0] if positives else "")),
                "entity_group_id": str(record.get("entity_group_id") or record.get("brand_family_id") or ""),
                "brand_family_id": str(record.get("brand_family_id") or ""),
                "intent_scope": str(record.get("intent_scope") or "POI"),
                "sample_weight": float(record.get("sample_weight", 1.0)),
                "query_variant_family": str(record.get("query_variant_family") or ""),
                "primary_sampling_stratum": str(record.get("primary_sampling_stratum") or ""),
                "acceptable_poi_ids": record.get("acceptable_poi_ids"),
                "positive_pool": list(positives),
                "positives": positives,
                "negatives": pack["negatives"],
                "ignore": pack["ignore"],
            }
        )
    return rows


def verify_pack(data_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    docs = pd.read_parquet(data_dir / "search_documents.parquet", columns=["poi_id", "passage_context"])
    view = pd.read_parquet(data_dir / "query_train_view.parquet")
    pairs = pd.read_parquet(data_dir / "training_pairs.parquet")
    gold = pd.read_csv(data_dir / "gold_query_variants.csv")
    corpus_ids = set(docs["poi_id"].astype(str))
    empty = int((docs["passage_context"].fillna("").str.strip() == "").sum())
    train = view[view["split"] == "train"]
    pair_ids = set(pairs["poi_id"].astype(str))
    gold_ids = set(gold["intended_poi_id"].astype(str))
    for raw in gold["acceptable_poi_ids"]:
        gold_ids.update(parse_ids(raw))
    checks = {
        "corpus_rows": int(len(docs)),
        "empty_passages": empty,
        "train_rows": int(len(train)),
        "train_cases": int(train["case_id"].nunique()),
        "dev_rows": int((view["split"] == "dev").sum()),
        "dev_cases": int(view.loc[view["split"] == "dev", "case_id"].nunique()),
        "pair_rows": int(len(pairs)),
        "gold_rows": int(len(gold)),
        "pair_ids_missing": sorted(pair_ids - corpus_ids)[:10],
        "gold_ids_missing": sorted(gold_ids - corpus_ids)[:10],
        "pair_gold_overlap": sorted(pair_ids & gold_ids)[:10],
        "train_intended_gold_overlap": sorted(set(train["intended_poi_id"].astype(str)) & gold_ids)[:10],
        "acceptable_gold_overlap": sorted(
            {
                poi_id
                for raw in view["acceptable_poi_ids"]
                for poi_id in parse_ids(raw)
                if poi_id in gold_ids
            }
        )[:10],
        "non_train_pairs": int((~pairs["query_id"].isin(train["query_id"])).sum()),
        "config_corpus": config.get("corpus_version"),
        "config_gold": config.get("gold_dataset"),
        "config_epochs": config.get("epochs"),
    }
    checks["passed"] = (
        empty == 0
        and not checks["pair_ids_missing"]
        and not checks["gold_ids_missing"]
        and not checks["pair_gold_overlap"]
        and not checks["train_intended_gold_overlap"]
        and not checks["acceptable_gold_overlap"]
        and checks["non_train_pairs"] == 0
        and checks["train_rows"] > 0
        and checks["gold_rows"] == int(config.get("expected_gold_rows") or 800)
        and int(config.get("epochs") or 0) <= 2
    )
    if not checks["passed"]:
        raise ValueError(f"Pack verification failed: {checks}")
    return checks


def encode_and_eval(
    model: Any,
    tokenizer: Any,
    passages: list[str],
    corpus_ids: list[str],
    gold: pd.DataFrame,
    dev_frame: pd.DataFrame,
    config: dict[str, Any],
    device: Any,
    out_dir: Path,
    tag: str,
    prefix_df: pd.DataFrame | None = None,
    which: str = "both",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, float]:
    if which not in {"dev", "gold", "both"}:
        raise ValueError(f"unknown eval scope: {which}")
    print(f"encoding corpus for {tag} ({which}) …", flush=True)
    corpus_vectors, encode_s = encode_texts(
        model,
        tokenizer,
        passages,
        config["passage_prefix"],
        config["max_passage_tokens"],
        config["encode_batch_size"],
        device,
    )
    print(f"{tag} corpus encode {encode_s:.1f}s", flush=True)
    gold_report = None
    dev_report = None
    if which in {"gold", "both"}:
        gold_report, _ = evaluate_frame(
            model,
            tokenizer,
            corpus_vectors,
            corpus_ids,
            gold,
            config,
            device,
            out_dir / f"run_{tag}_gold.jsonl",
            f"{tag}_gold",
        )
        print(f"{tag} gold Hit@1={hit1(gold_report):.3f}", flush=True)
        if prefix_df is not None and len(prefix_df):
            print(f"eval {tag} gold prefixes ({len(prefix_df)}) …", flush=True)
            gold_report["prefix"] = evaluate_prefix(
                model,
                tokenizer,
                corpus_vectors,
                corpus_ids,
                prefix_df,
                config,
                device,
                out_dir / f"run_{tag}_prefix.jsonl",
            )
    if which in {"dev", "both"}:
        dev_report, _ = evaluate_frame(
            model,
            tokenizer,
            corpus_vectors,
            corpus_ids,
            dev_frame,
            config,
            device,
            out_dir / f"run_{tag}_dev.jsonl",
            f"{tag}_dev",
        )
        print(f"{tag} dev Hit@1={hit1(dev_report):.3f}", flush=True)
    del corpus_vectors
    import torch

    torch.cuda.empty_cache()
    return gold_report, dev_report, encode_s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("/kaggle/input/vn-poi-stage1-v6-hardneg-6k-devlock"))
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working/stage1_v6_hardneg"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--dev-only", action="store_true", default=os.environ.get("POI_DEV_ONLY") == "1")
    parser.add_argument("--weight-mode", choices=("legacy_both", "sampling_only", "loss_only"), default=os.environ.get("POI_WEIGHT_MODE", "legacy_both"))
    args = parser.parse_args()
    if not args.validate_only and not Path("/kaggle").exists():
        raise RuntimeError("Heavy training runs on Kaggle only; use --validate-only for local pack checks")

    data_dir = resolve_input(args.data)
    config = json.loads((data_dir / "train_config.json").read_text(encoding="utf-8"))
    config["weight_mode"] = args.weight_mode
    config["epochs"] = min(int(config.get("epochs") or 2), 2)
    checks = verify_pack(data_dir, config)
    print(json.dumps(checks, ensure_ascii=False), flush=True)
    if args.validate_only:
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / "input_manifest_verified.json", checks)
        return

    ensure_kaggle_gpu_compatibility()
    disable_torch_compile()
    import torch
    import transformers
    from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

    if not torch.cuda.is_available():
        raise RuntimeError("This kernel requires a CUDA GPU")

    seed_everything(config["seed"])
    device = torch.device("cuda")
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"device={device} torch={torch.__version__} data={data_dir}", flush=True)

    docs = pd.read_parquet(data_dir / "search_documents.parquet", columns=["poi_id", "passage_context"])
    view = pd.read_parquet(data_dir / "query_train_view.parquet")
    pairs = pd.read_parquet(data_dir / "training_pairs.parquet")
    gold = pd.read_csv(data_dir / "gold_query_variants.csv")
    fit_frame = view[view["split"] == "train"].reset_index(drop=True)
    dev_frame = view[view["split"] == "dev"].reset_index(drop=True)
    corpus_ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].fillna("").astype(str).tolist()
    passage_by_id = dict(zip(corpus_ids, passages))
    train_rows = configure_training_weights(rows_from_view(fit_frame, pairs), args.weight_mode)
    gold_prefixes = expand_char_prefixes(gold)
    print(
        f"corpus={len(corpus_ids)} train={len(fit_frame)}/{fit_frame['case_id'].nunique()} "
        f"dev={len(dev_frame)}/{dev_frame['case_id'].nunique()} gold={len(gold)} "
        f"gold_prefixes={len(gold_prefixes)} pairs={len(pairs)}",
        flush=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(config["model_id"])
    model = AutoModel.from_pretrained(config["model_id"]).to(device)
    initial_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    summary: dict[str, Any] = {
        "experiment": config["experiment"],
        "corpus_version": config["corpus_version"],
        "gold_dataset": config["gold_dataset"],
        "checkpoint_selection": "dev_only",
        "weight_mode": args.weight_mode,
        "uploads_embeddings": False,
        "split": {
            "train_rows": int(len(fit_frame)),
            "train_cases": int(fit_frame["case_id"].nunique()),
            "dev_rows": int(len(dev_frame)),
            "dev_cases": int(dev_frame["case_id"].nunique()),
            "gold_rows": int(len(gold)),
            "pair_rows": int(len(pairs)),
        },
        "runtime": {
            "device": str(device),
            "gpu": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "python": platform.python_version(),
        },
        "profiles": {},
        "epoch_eval": [],
        "kept_checkpoint": None,
    }
    write_json(args.output / "split_manifest.json", summary["split"])

    zero_gold, zero_dev, zero_s = encode_and_eval(
        model,
        tokenizer,
        passages,
        corpus_ids,
        gold,
        dev_frame,
        config,
        device,
        args.output,
        "zero_shot",
        which="dev",
    )
    summary["profiles"]["zero_shot_dev"] = zero_dev
    summary["encode_corpus_s"] = {"zero_shot_dev": round(zero_s, 1)}
    write_json(args.output / "summary_partial.json", summary)
    write_json(args.output / "gate_table.json", gate_table(summary["profiles"]))

    epochs = int(config["epochs"])
    sampled_epochs = [sample_epoch_rows(train_rows, config["seed"] + epoch) for epoch in range(epochs)]
    total_steps = sum(
        len(make_unique_batches(rows, config["train_batch_size"], config["seed"] + epoch))
        for epoch, rows in enumerate(sampled_epochs, start=1)
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["learning_rate"], weight_decay=config["weight_decay"])
    warmup_steps = int(math.ceil(total_steps * config["warmup_ratio"]))
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=max(total_steps, 1)
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    history: list[dict[str, Any]] = []
    kept: dict[str, Any] | None = None
    best_state = None
    best_dev = -1.0
    train_started = time.time()

    for epoch, sampled in enumerate(sampled_epochs, start=1):
        print(f"training epoch {epoch}/{epochs} sampled_rows={len(sampled)} …", flush=True)
        record = train_one_epoch(
            model,
            tokenizer,
            sampled,
            passage_by_id,
            config,
            device,
            optimizer,
            scheduler,
            scaler,
            epoch,
            epochs,
        )
        history.append(record)
        print(
            f"epoch {epoch}/{epochs} mean_loss={record['mean_train_loss']} steps={record['steps']}",
            flush=True,
        )
        _gold_report, dev_report, encode_s = encode_and_eval(
            model,
            tokenizer,
            passages,
            corpus_ids,
            gold,
            dev_frame,
            config,
            device,
            args.output,
            f"epoch{epoch}",
            which="dev",
        )
        summary["profiles"][f"epoch{epoch}_dev"] = dev_report
        summary["encode_corpus_s"][f"epoch{epoch}_dev"] = round(encode_s, 1)
        keep = keep_checkpoint(dev_report, zero_dev)
        dev_hit = hit1(dev_report)
        epoch_gate = {
            "epoch": epoch,
            "train": record,
            "dev_hit1": dev_hit,
            "zero_shot_dev_hit1": hit1(zero_dev),
            "keep": keep and dev_hit + 1e-12 >= best_dev,
            "selection": "dev_only",
        }
        summary["epoch_eval"].append(epoch_gate)
        write_json(args.output / "summary_partial.json", summary)
        write_json(args.output / "gate_table.json", gate_table(summary["profiles"]))
        if keep and dev_hit + 1e-12 >= best_dev:
            best_dev = dev_hit
            kept = epoch_gate
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            ckpt = args.output / "checkpoint_e5_hardneg"
            model.save_pretrained(ckpt)
            tokenizer.save_pretrained(ckpt)
            print(f"kept checkpoint after epoch {epoch} dev Hit@1={dev_hit:.3f}", flush=True)
        else:
            print(
                f"epoch {epoch} not kept: dev Hit@1 {dev_hit:.3f} "
                f"vs zero-shot {hit1(zero_dev):.3f} best {best_dev:.3f}",
                flush=True,
            )

    if best_state is not None and kept is not None:
        model.load_state_dict(best_state)
        summary["kept_checkpoint"] = kept
        summary["profiles"]["finetuned_dev"] = summary["profiles"][f"epoch{int(kept['epoch'])}_dev"]
        final_state = best_state
    else:
        summary["kept_checkpoint"] = {
            "epoch": 0,
            "keep": False,
            "reason": "no epoch beat the zero-shot dev lock",
            "selection": "dev_only",
        }
        summary["profiles"]["finetuned_dev"] = zero_dev
        final_state = initial_state
        model.load_state_dict(initial_state)

    if args.dev_only:
        model.load_state_dict(final_state)
        checkpoint = args.output / "checkpoint_e5_hardneg"
        model.save_pretrained(checkpoint)
        tokenizer.save_pretrained(checkpoint)
        summary["weight_mode"] = args.weight_mode
        summary["gold_opened_after_lock"] = False
        summary["evaluation_role"] = "dev_only_experiment"
        summary["train"] = {"epochs": epochs, "steps": total_steps, "history": history,
                            "elapsed_seconds": round(time.time() - train_started, 1)}
        write_json(args.output / "summary.json", summary)
        print("DONE dev-only; no Gold scoring", args.output, flush=True)
        return

    model.load_state_dict(initial_state)
    zs_gold, _ignored_dev, zs_gold_s = encode_and_eval(
        model,
        tokenizer,
        passages,
        corpus_ids,
        gold,
        dev_frame,
        config,
        device,
        args.output,
        "zero_shot",
        gold_prefixes,
        which="gold",
    )
    summary["profiles"]["zero_shot_gold"] = zs_gold
    summary["encode_corpus_s"]["zero_shot_gold"] = round(zs_gold_s, 1)
    if best_state is None:
        summary["profiles"]["finetuned_gold"] = zs_gold
        summary["encode_corpus_s"]["finetuned_gold"] = round(zs_gold_s, 1)
    else:
        model.load_state_dict(final_state)
        ft_gold, _ignored_dev, ft_gold_s = encode_and_eval(
            model,
            tokenizer,
            passages,
            corpus_ids,
            gold,
            dev_frame,
            config,
            device,
            args.output,
            "finetuned",
            gold_prefixes,
            which="gold",
        )
        summary["profiles"]["finetuned_gold"] = ft_gold
        summary["encode_corpus_s"]["finetuned_gold"] = round(ft_gold_s, 1)
    summary["gold_opened_after_lock"] = True

    summary["train"] = {
        "epochs": epochs,
        "steps": total_steps,
        "mean_train_loss": float(np.mean([row["mean_train_loss"] for row in history if row["mean_train_loss"] is not None])),
        "elapsed_seconds": round(time.time() - train_started, 1),
        "history": history,
    }
    write_json(args.output / "summary.json", summary)
    write_json(args.output / "gate_table.json", gate_table(summary["profiles"]))
    print("DONE", args.output, flush=True)


if __name__ == "__main__":
    main()
