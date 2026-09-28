#!/usr/bin/env python3
"""Pack brand train/dev/gold queries for a continuation trial.

Does not rewrite the locked Gold brand release or the POI pair table.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TRAIN = ROOT / "data/vietnam/train_stage1_brand_queries_v3/train_eval_view/brand_queries_v1.parquet"
DEV = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_brand_dev_v1/brand_queries_v1.parquet"
GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/brand_queries_v1.parquet"
DATA_DIR = HERE / "dataset_stage1_v6_brand_dev_trial"
KERNEL_DIR = HERE / "kernel_stage1_v6_brand_dev_trial"


def families(path: Path) -> set[str]:
    frame = pd.read_parquet(path, columns=["brand_family_id"])
    return set(frame["brand_family_id"].astype(str))


def main() -> None:
    cred = json.loads((Path.home() / ".kaggle" / "kaggle.json").read_text(encoding="utf-8"))
    username = cred["username"]
    for path in (TRAIN, DEV, GOLD, KERNEL_DIR / "run_brand_continuation.py"):
        if not path.exists():
            raise SystemExit(f"Missing {path}")
    train_f, dev_f, gold_f = families(TRAIN), families(DEV), families(GOLD)
    if train_f & dev_f or train_f & gold_f or dev_f & gold_f:
        raise SystemExit("Brand family splits overlap")
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    shutil.copy2(TRAIN, DATA_DIR / "brand_train_queries.parquet")
    shutil.copy2(DEV, DATA_DIR / "brand_dev_queries.parquet")
    shutil.copy2(GOLD, DATA_DIR / "brand_gold_queries.parquet")
    (DATA_DIR / "split_families.json").write_text(
        json.dumps(
            {
                "train": sorted(train_f),
                "dev": sorted(dev_f),
                "gold": sorted(gold_f),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    config = {
        "experiment": "stage1_v6_brand_continuation",
        "init_checkpoint": "stage1_v6_hardneg_6k_devlock epoch 2",
        "checkpoint_selection": "brand_dev_and_poi_dev",
        "epochs": 2,
        "learning_rate": 5e-6,
        "weight_decay": 0.01,
        "warmup_ratio": 0.06,
        "max_grad_norm": 1.0,
        "temperature_scale": 20.0,
        "seed": 42,
        "train_batch_size": 16,
        "positives_per_query": 4,
        "negatives_per_query": 4,
        "poi_dev_drop_limit": 0.01,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "max_query_tokens": 64,
        "max_passage_tokens": 128,
        "encode_batch_size": 48,
        "note": "Brand multi-positive continuation. Gold brand and Gold POI are scored once after the lock.",
    }
    (DATA_DIR / "train_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    data_ref = f"{username}/vn-poi-stage1-v6-brand-dev-trial"
    kernel_ref = f"{username}/vn-poi-stage1-v6-brand-dev-trial-train"
    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "VN POI Stage1 v6 brand dev trial",
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "Brand train, dev, and gold queries. No embeddings.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (KERNEL_DIR / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": "vn-poi-stage1-v6-brand-dev-trial-train",
                "code_file": "run_brand_continuation.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": "true",
                "enable_gpu": "true",
                "enable_internet": "true",
                "dataset_sources": [
                    data_ref,
                    f"{username}/vn-poi-stage1-v6-hardneg-6k-devlock",
                    f"{username}/vn-poi-stage1-v6-hardneg-6k-devlock-rescore",
                ],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"data_ref": data_ref, "kernel_ref": kernel_ref, "train_families": len(train_f), "dev_families": len(dev_f)}, indent=2))


if __name__ == "__main__":
    main()
