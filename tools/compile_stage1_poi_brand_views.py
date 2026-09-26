"""Compile unified POI + brand train views. Does not merge tracks into the trainer."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from stage1_brand_v3_common import (
    GOLD_BRAND_DEV,
    GOLD_POI,
    MEMBERSHIP_V3,
    SPLITS_V1,
    TRAIN_BRAND_V3,
    TRAIN_V6,
    UNIFIED_VIEWS,
    load_v3_core,
    parse_id_list,
    refuse_nonempty,
    remap_lookup,
    sha256_file,
    source_record,
    write_json,
)


POI_WEIGHT = 0.85
BRAND_WEIGHT = 0.15


def _ids(value) -> list[str]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [str(item) for item in value]


def compile_views(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    core = load_v3_core()
    v3_ids = set(core["poi_id"].astype(str))
    entity_by = dict(zip(core["poi_id"].astype(str), core["entity_group_id"].astype(str)))
    composed = pd.read_parquet(MEMBERSHIP_V3 / "composed_poi_id_migration_v1_v3.parquet")
    remap = remap_lookup(composed, v3_ids)
    members = pd.read_parquet(MEMBERSHIP_V3 / "brand_group_members_v3.parquet")
    accepted = members[members["membership_status"] == "accepted"]
    group_of = {
        str(row.poi_id): str(row.brand_group_id)
        for row in accepted.itertuples(index=False)
    }
    gold_ids = set(pd.read_parquet(GOLD_POI / "target_pois_v2_1.parquet")["poi_id"].astype(str))
    assignment = {
        row["brand_family_id"]: row["split"]
        for row in json.loads((SPLITS_V1 / "family_split.json").read_text(encoding="utf-8"))["families"]
    }

    train = pd.read_csv(TRAIN_V6 / "query_variants.csv")
    brand_train = pd.read_parquet(TRAIN_BRAND_V3 / "train_eval_view" / "brand_queries_v1.parquet")
    brand_dev = pd.read_parquet(GOLD_BRAND_DEV / "brand_queries_v1.parquet")
    brand_qrels = pd.concat(
        [
            pd.read_parquet(TRAIN_BRAND_V3 / "train_eval_view" / "brand_qrels_v1.parquet"),
            pd.read_parquet(GOLD_BRAND_DEV / "brand_qrels_v1.parquet"),
        ],
        ignore_index=True,
    )
    ignore_by_query = defaultdict(list)
    pos_by_query = defaultdict(list)
    for row in brand_qrels.itertuples(index=False):
        if str(row.label) == "compatible":
            pos_by_query[str(row.qrel_set_id)].append(str(row.target_id))
        elif str(row.label) == "ignore":
            ignore_by_query[str(row.qrel_set_id)].append(str(row.target_id))

    query_rows: list[dict] = []
    relation_rows: list[dict] = []

    for raw in train.to_dict("records"):
        intended_src = str(raw["intended_poi_id"])
        intended, _, _ = remap.get(intended_src, (intended_src if intended_src in v3_ids else None, "", ""))
        if intended is None:
            continue
        positives = []
        for poi_id in parse_id_list(raw.get("acceptable_poi_ids")):
            dest, _, _ = remap.get(poi_id, (poi_id if poi_id in v3_ids else None, "", ""))
            if dest and dest not in positives:
                positives.append(dest)
        if intended not in positives:
            positives.insert(0, intended)
        query_id = str(raw["variant_id"])
        query_rows.append(
            {
                "query_id": query_id,
                "query_text": str(raw["query_text"]),
                "source_dataset": "poi_queries",
                "intent_scope": "POI",
                "intent_id": intended,
                "intended_poi_id": intended,
                "entity_group_id": entity_by.get(intended, ""),
                "brand_family_id": "",
                "brand_group_id": group_of.get(intended, ""),
                "case_id": str(raw["case_id"]),
                "variant_id": query_id,
                "query_variant_family": str(raw.get("query_variant_family") or ""),
                "variant_operator": str(raw.get("variant_operator") or ""),
                "split": "train",
                "sample_weight": POI_WEIGHT,
                "generator_version": str(raw.get("generator_version") or ""),
            }
        )
        seen: set[str] = set()
        for poi_id in positives:
            relation_rows.append(
                {
                    "query_id": query_id,
                    "poi_id": poi_id,
                    "relation": "positive_pool",
                    "label": "positive",
                    "label_reason": "authored_acceptable",
                    "split": "train",
                }
            )
            seen.add(poi_id)

    for frame, split_name in ((brand_train, "train"), (brand_dev, "dev")):
        for raw in frame.to_dict("records"):
            query_id = str(raw["query_id"])
            qrel_set = str(raw["qrel_set_id"])
            family_id = str(raw["brand_family_id"])
            if assignment.get(family_id) not in {split_name, "dev" if split_name == "dev" else "train"}:
                continue
            positives = pos_by_query.get(qrel_set) or _ids(raw["acceptable_poi_ids"])
            ignore = [pid for pid in ignore_by_query.get(qrel_set, []) if pid not in positives]
            query_rows.append(
                {
                    "query_id": query_id,
                    "query_text": str(raw["query_text"]),
                    "source_dataset": "brand_queries",
                    "intent_scope": "BRAND",
                    "intent_id": str(raw["brand_group_id"]),
                    "intended_poi_id": positives[0] if positives else "",
                    "entity_group_id": family_id,
                    "brand_family_id": family_id,
                    "brand_group_id": str(raw["brand_group_id"]),
                    "case_id": family_id,
                    "variant_id": query_id,
                    "query_variant_family": str(raw.get("variant_operator") or ""),
                    "variant_operator": str(raw.get("variant_operator") or ""),
                    "split": split_name,
                    "sample_weight": BRAND_WEIGHT,
                    "generator_version": "manual_brand_authored_v1",
                }
            )
            seen = set()
            for poi_id in positives:
                relation_rows.append(
                    {
                        "query_id": query_id,
                        "poi_id": poi_id,
                        "relation": "positive_pool",
                        "label": "positive",
                        "label_reason": "brand_group_member",
                        "split": split_name,
                    }
                )
                seen.add(poi_id)
            for poi_id in ignore:
                relation_rows.append(
                    {
                        "query_id": query_id,
                        "poi_id": poi_id,
                        "relation": "ignore",
                        "label": "ignore",
                        "label_reason": "gold_overlap_mask",
                        "split": split_name,
                    }
                )
                seen.add(poi_id)

    query_path = output_dir / "query_train_view.parquet"
    relation_path = output_dir / "query_relation_view.parquet"
    pq.write_table(pa.Table.from_pylist(query_rows), query_path, compression="zstd")
    pq.write_table(pa.Table.from_pylist(relation_rows), relation_path, compression="zstd")
    queries = pd.DataFrame(query_rows)
    relations = pd.DataFrame(relation_rows)
    manifest = {
        "dataset": "train_stage1_poi_brand_views_v1",
        "status": "EXPERIMENTAL",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "note": "Unified views only. Do not merge brand into training until the sampler/mask tests pass.",
        "mix": {"poi_weight": POI_WEIGHT, "brand_weight": BRAND_WEIGHT},
        "gold_ids_masked_from_brand_train": len(gold_ids),
        "counts": {
            "query_rows": int(len(queries)),
            "poi_rows": int((queries["intent_scope"] == "POI").sum()),
            "brand_rows": int((queries["intent_scope"] == "BRAND").sum()),
            "train_rows": int((queries["split"] == "train").sum()),
            "dev_rows": int((queries["split"] == "dev").sum()),
            "relation_rows": int(len(relations)),
            "relations_by_label": relations["label"].value_counts().to_dict(),
        },
        "sources": {
            "train_v6": source_record(TRAIN_V6 / "query_variants.csv"),
            "brand_train": source_record(TRAIN_BRAND_V3 / "train_eval_view" / "manifest.json"),
            "brand_dev": source_record(GOLD_BRAND_DEV / "manifest.json"),
            "membership": source_record(MEMBERSHIP_V3 / "manifest.json"),
            "split": source_record(SPLITS_V1 / "family_split.json"),
        },
        "outputs": {
            "query_train_view.parquet": sha256_file(query_path),
            "query_relation_view.parquet": sha256_file(relation_path),
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=UNIFIED_VIEWS)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args()
    if not args.allow_existing:
        refuse_nonempty(args.output_dir)
    print(json.dumps(compile_views(args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
