#!/usr/bin/env python3
"""Pack compiled 6k views for a Kaggle GPU miner. Does not upload embeddings."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VIEWS = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_6k_clean"
GOLD = ROOT / "data" / "vietnam" / "stage1_eval_suite_v2" / "gold_stage1_v2_1"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v3"
DATA_DIR = HERE / "dataset_stage1_v6_hardneg_6k_mine"
KERNEL_DIR = HERE / "kernel_stage1_v6_hardneg_6k_mine"
MINER = ROOT / "tools" / "mine_stage1_hardneg_pilot.py"


def gold_ids() -> list[str]:
    sessions = pd.read_parquet(
        GOLD / "query_sessions_v2_1.parquet",
        columns=["intended_poi_id", "acceptable_poi_ids"],
    )
    ids = set(sessions["intended_poi_id"].astype(str))
    for raw in sessions["acceptable_poi_ids"]:
        if hasattr(raw, "tolist"):
            ids.update(str(item) for item in raw.tolist())
        else:
            ids.add(str(raw))
    targets = pd.read_parquet(GOLD / "target_pois_v2_1.parquet", columns=["poi_id"])
    ids.update(targets["poi_id"].astype(str))
    ids.discard("")
    return sorted(ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--views", type=Path, default=VIEWS)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--kernel-dir", type=Path, default=KERNEL_DIR)
    parser.add_argument("--dataset-slug", default="vn-poi-stage1-v6-hardneg-6k-mine")
    parser.add_argument("--kernel-slug", default="vn-poi-stage1-v6-hardneg-6k-mine-run")
    args = parser.parse_args()
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        raise SystemExit(f"Missing {cred_path}")
    username = json.loads(cred_path.read_text(encoding="utf-8"))["username"]
    views = args.views
    data_dir = args.data_dir
    kernel_dir = args.kernel_dir
    required = [
        views / "query_train_view.parquet",
        views / "query_relation_view.parquet",
        CORPUS / "search_documents.parquet",
        CORPUS / "pois_core.parquet",
        MINER,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))

    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    kernel_dir.mkdir(parents=True, exist_ok=True)
    for name in ("query_train_view.parquet", "query_relation_view.parquet"):
        shutil.copy2(views / name, data_dir / name)
    docs = pd.read_parquet(CORPUS / "search_documents.parquet", columns=["poi_id", "passage_context"])
    core = pd.read_parquet(CORPUS / "pois_core.parquet", columns=["poi_id", "entity_group_id"])
    pq.write_table(pa.Table.from_pandas(docs, preserve_index=False), data_dir / "search_documents.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pandas(core, preserve_index=False), data_dir / "pois_entity.parquet", compression="zstd")
    ids = gold_ids()
    (data_dir / "gold_holdout_ids.json").write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    npy = list(data_dir.glob("*.npy"))
    if npy:
        raise SystemExit(f"Refusing to pack embeddings: {npy}")

    data_ref = f"{username}/{args.dataset_slug}"
    kernel_ref = f"{username}/{args.kernel_slug}"
    (data_dir / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": args.dataset_slug,
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "Compiled views + corpus passages. No embeddings.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.copy2(MINER, kernel_dir / "mine_stage1_hardneg_pilot.py")
    (kernel_dir / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": args.kernel_slug,
                "code_file": "mine_stage1_hardneg_pilot.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": "true",
                "enable_gpu": "true",
                "enable_internet": "true",
                "dataset_sources": [data_ref],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (kernel_dir / "README.md").write_text(
        f"# {args.kernel_slug}\n\n"
        "Single-file GPU miner. Encodes the corpus on Kaggle.\n"
        "Does not upload or read `*.npy` embeddings.\n"
        "Quota: lexical 1, dense 3, random 2, sibling 0. Gold POI ids are blocked.\n",
        encoding="utf-8",
    )
    print(json.dumps({"data_ref": data_ref, "kernel_ref": kernel_ref, "holdout_ids": len(ids), "docs": int(len(docs))}, indent=2))


if __name__ == "__main__":
    main()
