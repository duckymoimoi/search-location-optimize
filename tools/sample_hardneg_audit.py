#!/usr/bin/env python3
"""Stratified hard-negative worksheet for the clean 6k pack.

Writes a CSV a person can label true_hard / false_negative / easy.
Does not modify pairs or Gold.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_6k_clean"
CORE = ROOT / "data" / "vietnam" / "poi_corpus_v3" / "pois_core.parquet"
OUT = ROOT / "docs" / "deliveries" / "w3_evidence" / "hardneg_audit_6k_sample.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    pairs = pd.read_parquet(args.pack / "training_pairs.parquet")
    view = pd.read_parquet(
        args.pack / "query_train_view.parquet",
        columns=["query_id", "query_text", "intended_poi_id", "primary_sampling_stratum", "split"],
    )
    negatives = pairs.loc[pairs["label"].astype(str) == "negative"].copy()
    counts = negatives["negative_source"].astype(str).value_counts().to_dict()
    total = sum(counts.values()) or 1
    allocations = {source: max(1, round(args.n * count / total)) for source, count in counts.items()}
    while sum(allocations.values()) > args.n:
        source = max(allocations, key=allocations.get)
        allocations[source] -= 1
    while sum(allocations.values()) < args.n:
        source = max(counts, key=counts.get)
        allocations[source] += 1

    parts = []
    for source, size in allocations.items():
        pool = negatives.loc[negatives["negative_source"].astype(str) == source]
        parts.append(pool.sample(n=min(size, len(pool)), random_state=args.seed))
    sample = pd.concat(parts, ignore_index=True)
    train = view.loc[view["split"] == "train", ["query_id", "query_text", "intended_poi_id", "primary_sampling_stratum"]]
    sample = sample.merge(train, on="query_id", how="left")
    core = pd.read_parquet(CORE, columns=["poi_id", "name", "brand", "address_text", "category", "entity_group_id"])
    core["poi_id"] = core["poi_id"].astype(str)
    intended = core.rename(
        columns={
            "poi_id": "intended_poi_id",
            "name": "intended_name",
            "brand": "intended_brand",
            "address_text": "intended_address",
            "category": "intended_category",
            "entity_group_id": "intended_entity_group_id",
        }
    )
    negative = core.rename(
        columns={
            "poi_id": "poi_id",
            "name": "negative_name",
            "brand": "negative_brand",
            "address_text": "negative_address",
            "category": "negative_category",
            "entity_group_id": "negative_entity_group_id",
        }
    )
    sample["poi_id"] = sample["poi_id"].astype(str)
    sample["intended_poi_id"] = sample["intended_poi_id"].astype(str)
    sample = sample.merge(intended, on="intended_poi_id", how="left")
    sample = sample.merge(negative, on="poi_id", how="left")
    sample["same_entity_group"] = (
        sample["intended_entity_group_id"].astype(str) == sample["negative_entity_group_id"].astype(str)
    ) & sample["intended_entity_group_id"].notna()
    sample["audit_label"] = ""
    sample["audit_note"] = ""
    columns = [
        "negative_source",
        "query_id",
        "query_text",
        "primary_sampling_stratum",
        "intended_poi_id",
        "intended_name",
        "intended_brand",
        "intended_address",
        "poi_id",
        "negative_name",
        "negative_brand",
        "negative_address",
        "negative_category",
        "same_entity_group",
        "source_rank",
        "audit_label",
        "audit_note",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sample.loc[:, columns].to_csv(args.out, index=False, encoding="utf-8-sig")
    print(json.dumps({"out": str(args.out), "rows": int(len(sample)), "by_source": allocations}, ensure_ascii=False))


if __name__ == "__main__":
    main()
