#!/usr/bin/env python3
"""Kaggle GPU: fine-tune mE5-small on Stage-1 v6 (corpus v3, gold v2).

Pilot in-batch unique-target contrastive. The kernel encodes the full
corpus itself; the dataset pack does not include embeddings.
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
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

RECALL_KS = (100, 500, 1000)
DIAG_KS = (1, 5, 10, 20, 50)


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
    if (preferred / "search_documents.parquet").exists() and (preferred / "query_variants_train.csv").exists():
        return preferred
    kaggle_input = Path("/kaggle/input")
    if kaggle_input.exists():
        matches = sorted(kaggle_input.rglob("query_variants_train.csv"))
        for match in matches:
            if (match.parent / "search_documents.parquet").exists():
                return match.parent
    raise FileNotFoundError(f"Stage-1 v6 pack not under {preferred}")


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


def split_cases(train: pd.DataFrame, fraction: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    cases = sorted(train["case_id"].astype(str).unique())
    rng = random.Random(seed)
    rng.shuffle(cases)
    n_dev = max(1, int(round(len(cases) * fraction)))
    dev_cases = set(cases[:n_dev])
    dev = train[train["case_id"].astype(str).isin(dev_cases)].copy()
    fit = train[~train["case_id"].astype(str).isin(dev_cases)].copy()
    return fit.reset_index(drop=True), dev.reset_index(drop=True)


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
            target = row["intended_poi_id"]
            entity = row["entity_group_id"]
            compatible = set(row["acceptable"])
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


def train_epochs(
    model: Any,
    tokenizer: Any,
    rows: list[dict],
    passage_by_id: dict[str, str],
    config: dict[str, Any],
    device: Any,
    seed: int,
) -> dict[str, Any]:
    import torch
    import torch.nn.functional as functional
    from transformers import get_linear_schedule_with_warmup

    epochs = int(config.get("epochs") or 3)
    epoch_batches = [
        make_unique_batches(rows, config["train_batch_size"], seed + epoch)
        for epoch in range(epochs)
    ]
    total_steps = sum(len(batches) for batches in epoch_batches)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config["learning_rate"],
        weight_decay=config["weight_decay"],
    )
    warmup_steps = int(math.ceil(total_steps * config["warmup_ratio"]))
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    history: list[dict[str, Any]] = []
    started = time.time()
    global_step = 0
    for epoch, batches in enumerate(epoch_batches, start=1):
        losses: list[float] = []
        model.train()
        epoch_started = time.time()
        for step, batch in enumerate(batches, start=1):
            query_inputs = tokenizer(
                [config["query_prefix"] + row["query_text"] for row in batch],
                padding=True,
                truncation=True,
                max_length=config["max_query_tokens"],
                return_tensors="pt",
            )
            passage_inputs = tokenizer(
                [config["passage_prefix"] + passage_by_id[row["intended_poi_id"]] for row in batch],
                padding=True,
                truncation=True,
                max_length=config["max_passage_tokens"],
                return_tensors="pt",
            )
            query_inputs.pop("token_type_ids", None)
            passage_inputs.pop("token_type_ids", None)
            query_inputs = {key: value.to(device) for key, value in query_inputs.items()}
            passage_inputs = {key: value.to(device) for key, value in passage_inputs.items()}
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                query_vec = model_embeddings(model, query_inputs)
                passage_vec = model_embeddings(model, passage_inputs)
                logits = (query_vec @ passage_vec.T) * config["temperature_scale"]
                loss = functional.cross_entropy(logits, torch.arange(len(batch), device=device))
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), config["max_grad_norm"])
            scale_before = scaler.get_scale()
            scaler.step(optimizer)
            scaler.update()
            if scaler.get_scale() >= scale_before:
                scheduler.step()
            losses.append(float(loss.detach().cpu()))
            global_step += 1
            if step == 1 or step == len(batches) or step % 50 == 0:
                print(
                    f"  epoch {epoch}/{epochs} step {step}/{len(batches)} "
                    f"loss={losses[-1]:.4f}",
                    flush=True,
                )
        record = {
            "epoch": epoch,
            "steps": len(batches),
            "batch_size_min": min(map(len, batches)),
            "batch_size_max": max(map(len, batches)),
            "mean_train_loss": float(np.mean(losses)),
            "elapsed_seconds": round(time.time() - epoch_started, 1),
        }
        history.append(record)
        print(
            f"epoch {epoch}/{epochs} mean_loss={record['mean_train_loss']:.4f} "
            f"steps={record['steps']}",
            flush=True,
        )
    return {
        "epochs": epochs,
        "steps": total_steps,
        "mean_train_loss": float(np.mean([row["mean_train_loss"] for row in history])),
        "elapsed_seconds": round(time.time() - started, 1),
        "history": history,
    }


def rows_from_train(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for record in frame.to_dict("records"):
        row = dict(record)
        row["intended_poi_id"] = str(row["intended_poi_id"])
        row["entity_group_id"] = str(row["entity_group_id"])
        row["query_text"] = str(row["query_text"])
        row["acceptable"] = parse_ids(row["acceptable_poi_ids"])
        rows.append(row)
    return rows


def verify_pack(data_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    docs = pd.read_parquet(data_dir / "search_documents.parquet", columns=["poi_id", "passage_context"])
    train = pd.read_csv(data_dir / "query_variants_train.csv")
    gold = pd.read_csv(data_dir / "gold_query_variants.csv")
    corpus_ids = set(docs["poi_id"].astype(str))
    empty = int((docs["passage_context"].fillna("").str.strip() == "").sum())
    train_ids = set(train["intended_poi_id"].astype(str))
    for raw in train["acceptable_poi_ids"]:
        train_ids.update(parse_ids(raw))
    gold_ids = set(gold["intended_poi_id"].astype(str))
    for raw in gold["acceptable_poi_ids"]:
        gold_ids.update(parse_ids(raw))
    checks = {
        "corpus_rows": int(len(docs)),
        "empty_passages": empty,
        "train_rows": int(len(train)),
        "train_cases": int(train["case_id"].nunique()),
        "gold_rows": int(len(gold)),
        "gold_cases": int(gold["case_id"].nunique()),
        "train_ids_missing": sorted(train_ids - corpus_ids)[:10],
        "gold_ids_missing": sorted(gold_ids - corpus_ids)[:10],
        "train_gold_overlap": sorted(train_ids & gold_ids)[:10],
        "config_corpus": config.get("corpus_version"),
        "config_gold": config.get("gold_dataset"),
    }
    checks["passed"] = (
        empty == 0
        and not checks["train_ids_missing"]
        and not checks["gold_ids_missing"]
        and not checks["train_gold_overlap"]
        and checks["train_rows"] > 0
        and checks["gold_rows"] == 1080
    )
    if not checks["passed"]:
        raise ValueError(f"Pack verification failed: {checks}")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("/kaggle/input/vn-poi-stage1-v6-corpus-v3"))
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working/stage1_v6_e5"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    data_dir = resolve_input(args.data)
    config = json.loads((data_dir / "train_config.json").read_text(encoding="utf-8"))
    if int(config.get("epochs") or 0) < 3:
        config["epochs"] = 3
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
    from transformers import AutoModel, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("This kernel requires a CUDA GPU")

    seed_everything(config["seed"])
    device = torch.device("cuda")
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"device={device} torch={torch.__version__} data={data_dir}", flush=True)

    docs = pd.read_parquet(data_dir / "search_documents.parquet", columns=["poi_id", "passage_context"])
    train = pd.read_csv(data_dir / "query_variants_train.csv")
    gold = pd.read_csv(data_dir / "gold_query_variants.csv")
    fit_frame, dev_frame = split_cases(train, config["dev_case_fraction"], config["seed"])
    corpus_ids = docs["poi_id"].astype(str).tolist()
    passages = docs["passage_context"].fillna("").astype(str).tolist()
    passage_by_id = dict(zip(corpus_ids, passages))
    print(
        f"corpus={len(corpus_ids)} train={len(fit_frame)}/{fit_frame['case_id'].nunique()} "
        f"dev={len(dev_frame)}/{dev_frame['case_id'].nunique()} gold={len(gold)}",
        flush=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(config["model_id"])
    model = AutoModel.from_pretrained(config["model_id"]).to(device)
    summary: dict[str, Any] = {
        "experiment": config["experiment"],
        "corpus_version": config["corpus_version"],
        "gold_dataset": config["gold_dataset"],
        "uploads_embeddings": False,
        "split": {
            "train_rows": int(len(fit_frame)),
            "train_cases": int(fit_frame["case_id"].nunique()),
            "dev_rows": int(len(dev_frame)),
            "dev_cases": int(dev_frame["case_id"].nunique()),
            "gold_rows": int(len(gold)),
        },
        "runtime": {
            "device": str(device),
            "gpu": torch.cuda.get_device_name(0),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "python": platform.python_version(),
        },
        "profiles": {},
    }
    write_json(args.output / "split_manifest.json", summary["split"])

    print("encoding zero-shot corpus …", flush=True)
    zero_corpus, zero_corpus_s = encode_texts(
        model,
        tokenizer,
        passages,
        config["passage_prefix"],
        config["max_passage_tokens"],
        config["encode_batch_size"],
        device,
    )
    print(f"zero-shot corpus encode {zero_corpus_s:.1f}s", flush=True)
    print("eval zero-shot gold v2 …", flush=True)
    zero_gold, _ = evaluate_frame(
        model,
        tokenizer,
        zero_corpus,
        corpus_ids,
        gold,
        config,
        device,
        args.output / "run_zero_shot_gold.jsonl",
        "zero_shot_gold",
    )
    print("eval zero-shot internal dev …", flush=True)
    zero_dev, _ = evaluate_frame(
        model,
        tokenizer,
        zero_corpus,
        corpus_ids,
        dev_frame,
        config,
        device,
        args.output / "run_zero_shot_dev.jsonl",
        "zero_shot_dev",
    )
    summary["profiles"]["zero_shot_gold"] = zero_gold
    summary["profiles"]["zero_shot_dev"] = zero_dev
    write_json(args.output / "summary_partial.json", summary)
    print(
        "zero-shot gold "
        f"R@100={zero_gold['overall']['recall']['Recall@100']:.3f} "
        f"Hit@1={zero_gold['overall']['diagnostic']['Hit@1']:.3f} "
        f"MRR@10={zero_gold['overall']['diagnostic']['MRR@10']:.3f}",
        flush=True,
    )
    del zero_corpus
    torch.cuda.empty_cache()

    print(f"training {int(config.get('epochs') or 3)} epochs …", flush=True)
    train_stats = train_epochs(
        model,
        tokenizer,
        rows_from_train(fit_frame),
        passage_by_id,
        config,
        device,
        config["seed"],
    )
    summary["train"] = train_stats
    write_json(args.output / "summary_partial.json", summary)
    print(f"train done loss={train_stats['mean_train_loss']:.4f} steps={train_stats['steps']}", flush=True)

    ckpt = args.output / "checkpoint_e5_v6"
    model.save_pretrained(ckpt)
    tokenizer.save_pretrained(ckpt)

    print("encoding fine-tuned corpus …", flush=True)
    tuned_corpus, tuned_corpus_s = encode_texts(
        model,
        tokenizer,
        passages,
        config["passage_prefix"],
        config["max_passage_tokens"],
        config["encode_batch_size"],
        device,
    )
    print(f"fine-tuned corpus encode {tuned_corpus_s:.1f}s", flush=True)
    print("eval fine-tuned gold v2 …", flush=True)
    tuned_gold, _ = evaluate_frame(
        model,
        tokenizer,
        tuned_corpus,
        corpus_ids,
        gold,
        config,
        device,
        args.output / "run_finetuned_gold.jsonl",
        "finetuned_gold",
    )
    print("eval fine-tuned internal dev …", flush=True)
    tuned_dev, _ = evaluate_frame(
        model,
        tokenizer,
        tuned_corpus,
        corpus_ids,
        dev_frame,
        config,
        device,
        args.output / "run_finetuned_dev.jsonl",
        "finetuned_dev",
    )
    summary["profiles"]["finetuned_gold"] = tuned_gold
    summary["profiles"]["finetuned_dev"] = tuned_dev
    summary["encode_corpus_s"] = {
        "zero_shot": round(zero_corpus_s, 1),
        "finetuned": round(tuned_corpus_s, 1),
    }
    write_json(args.output / "summary.json", summary)
    write_json(
        args.output / "gate_table.json",
        [
            {
                "profile": name,
                "Recall@100": report["overall"]["recall"]["Recall@100"],
                "Recall@1000": report["overall"]["recall"]["Recall@1000"],
                "Hit@1": report["overall"]["diagnostic"]["Hit@1"],
                "Hit@5": report["overall"]["diagnostic"]["Hit@5"],
                "MRR@10": report["overall"]["diagnostic"]["MRR@10"],
                "K@95": report["overall"]["k_at_r"]["K@95"],
            }
            for name, report in summary["profiles"].items()
        ],
    )
    print(
        "finetuned gold "
        f"R@100={tuned_gold['overall']['recall']['Recall@100']:.3f} "
        f"Hit@1={tuned_gold['overall']['diagnostic']['Hit@1']:.3f} "
        f"MRR@10={tuned_gold['overall']['diagnostic']['MRR@10']:.3f}",
        flush=True,
    )
    print("DONE", args.output, flush=True)


if __name__ == "__main__":
    main()
