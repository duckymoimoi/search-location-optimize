#!/usr/bin/env python3
"""Force same-brand other-branch negatives into the hardneg pilot pairs.

Does not author query text. Reads compiled views + existing training_pairs,
writes back only into data/vietnam/train_stage1_v6_hardneg_pilot/.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_pilot"
SIBLING_QUOTA = 2
MAX_NEGATIVES = 8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    view = pd.read_parquet(PILOT / "query_train_view.parquet")
    relations = pd.read_parquet(PILOT / "query_relation_view.parquet")
    pairs = pd.read_parquet(PILOT / "training_pairs.parquet")
    mining_path = PILOT / "mining_manifest.json"
    mining = json.loads(mining_path.read_text(encoding="utf-8")) if mining_path.exists() else {}

    train_ids = set(view.loc[view["split"] == "train", "query_id"].astype(str))
    siblings: dict[str, list[str]] = defaultdict(list)
    for row in relations.itertuples(index=False):
        if str(row.query_id) not in train_ids or row.label != "hard_neg_candidate":
            continue
        siblings[str(row.query_id)].append(str(row.poi_id))
    for query_id in siblings:
        siblings[query_id] = sorted(set(siblings[query_id]))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in pairs.to_dict("records"):
        grouped[str(record["query_id"])].append(record)

    out_rows: list[dict] = []
    stats = {
        "queries_with_sibling_pool": 0,
        "queries_injected": 0,
        "siblings_added": 0,
        "random_dropped": 0,
        "already_had_sibling": 0,
    }
    for query_id, rows in grouped.items():
        weight = float(rows[0]["sample_weight"])
        positives = {str(row["poi_id"]) for row in rows if row["label"] == "positive"}
        ignores = {str(row["poi_id"]) for row in rows if row["label"] == "ignore"}
        negatives = [row for row in rows if row["label"] == "negative"]
        existing_neg_ids = {str(row["poi_id"]) for row in negatives}
        keep_non_neg = [row for row in rows if row["label"] != "negative"]

        pool = [poi_id for poi_id in siblings.get(query_id, []) if poi_id not in positives and poi_id not in ignores]
        if pool:
            stats["queries_with_sibling_pool"] += 1
        already = [poi_id for poi_id in pool if poi_id in existing_neg_ids]
        missing = [poi_id for poi_id in pool if poi_id not in existing_neg_ids]
        take = missing[: max(0, SIBLING_QUOTA - min(len(already), SIBLING_QUOTA))]
        if already:
            stats["already_had_sibling"] += 1
        if take:
            stats["queries_injected"] += 1
            stats["siblings_added"] += len(take)
            for poi_id in take:
                negatives.append(
                    {
                        "query_id": query_id,
                        "poi_id": poi_id,
                        "label": "negative",
                        "negative_source": "same_brand_other_branch",
                        "source_rank": None,
                        "label_reason": "forced_same_brand_other_branch",
                        "sample_weight": weight,
                    }
                )

        if len(negatives) > MAX_NEGATIVES:
            randoms = [row for row in negatives if row.get("negative_source") == "random"]
            others = [row for row in negatives if row.get("negative_source") != "random"]
            drop = len(negatives) - MAX_NEGATIVES
            drop = min(drop, len(randoms))
            randoms = randoms[drop:]
            stats["random_dropped"] += drop
            negatives = others + randoms
            if len(negatives) > MAX_NEGATIVES:
                negatives = negatives[:MAX_NEGATIVES]

        out_rows.extend(keep_non_neg)
        out_rows.extend(negatives)

    table = pd.DataFrame(out_rows)
    out_path = PILOT / "training_pairs.parquet"
    pq.write_table(pa.Table.from_pandas(table, preserve_index=False), out_path, compression="zstd")

    mining["brand_sibling_augment"] = {
        "sibling_quota": SIBLING_QUOTA,
        "max_negatives": MAX_NEGATIVES,
        **stats,
        "pair_rows_after": int(len(table)),
        "pairs_by_label": table["label"].value_counts().to_dict(),
        "negatives_by_source": table.loc[table["label"] == "negative", "negative_source"]
        .value_counts()
        .to_dict(),
        "training_pairs_sha256": sha256(out_path),
    }
    mining_path.write_text(json.dumps(mining, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(mining["brand_sibling_augment"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
