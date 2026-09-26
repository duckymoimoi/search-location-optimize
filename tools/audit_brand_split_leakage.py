"""Audit family-disjoint split, query leakage, and Gold POI overlap."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from stage1_brand_query_v1_common import normalize_query, read_jsonl
from stage1_brand_v3_common import (
    GOLD_POI,
    MEMBERSHIP_V3,
    SPLITS_V1,
    TRAIN_BRAND_V3,
    TRAIN_V6,
    exposure_for_family,
    fold_text,
    load_v3_core,
    parse_id_list,
    remap_lookup,
    sha256_file,
    source_record,
    write_json,
)


def load_split(split_path: Path) -> dict[str, str]:
    doc = json.loads(split_path.read_text(encoding="utf-8"))
    return {row["brand_family_id"]: row["split"] for row in doc["families"]}


def audit(
    split_path: Path,
    queries_path: Path,
    packet_path: Path,
    membership_dir: Path,
    train_csv: Path,
    gold_dir: Path,
    output_dir: Path,
) -> dict:
    assignment = load_split(split_path)
    queries = pd.read_parquet(queries_path)
    packet = read_jsonl(packet_path)
    members = pd.read_parquet(membership_dir / "brand_group_members_v3.parquet")
    accepted = members[members["membership_status"] == "accepted"]
    gold_targets = pd.read_parquet(gold_dir / "target_pois_v2_1.parquet")
    gold_sessions = pd.read_parquet(gold_dir / "query_sessions_v2_1.parquet")
    train = pd.read_csv(train_csv, usecols=["query_text", "intended_poi_id", "acceptable_poi_ids"])
    composed = pd.read_parquet(membership_dir / "composed_poi_id_migration_v1_v3.parquet")
    v3_ids = set(load_v3_core()["poi_id"].astype(str))
    remap = remap_lookup(composed, v3_ids)

    errors: list[str] = []
    warnings: list[str] = []
    families_by_split: dict[str, set[str]] = defaultdict(set)
    for family_id, split_name in assignment.items():
        families_by_split[split_name].add(family_id)
    overlap = (families_by_split["test"] & families_by_split["train"]) | (
        families_by_split["dev"] & families_by_split["train"]
    ) | (families_by_split["test"] & families_by_split["dev"])
    if overlap:
        errors.append(f"family split overlap: {sorted(overlap)[:10]}")

    query_split = {}
    for row in queries.itertuples(index=False):
        family_id = str(row.brand_family_id)
        if family_id not in assignment:
            errors.append(f"query family missing from split: {family_id}")
            continue
        query_split[str(row.query_id)] = assignment[family_id]

    text_index: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    fold_index: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in queries.itertuples(index=False):
        family_id = str(row.brand_family_id)
        split_name = assignment.get(family_id, "")
        text_index[normalize_query(row.query_text)].append((str(row.query_id), family_id, split_name))
        fold_index[fold_text(row.query_text)].append((str(row.query_id), family_id, split_name))

    cross_split = []
    for key, items in text_index.items():
        splits = {item[2] for item in items}
        families = {item[1] for item in items}
        if len(splits) > 1 or (len(families) > 1 and len(splits) > 1):
            cross_split.append({"key": key, "kind": "normalized", "items": items})
        elif len(families) > 1:
            warnings.append(f"same normalized brand query in multiple families: {key}")
    for key, items in fold_index.items():
        splits = {item[2] for item in items}
        if len(splits) > 1:
            cross_split.append({"key": key, "kind": "accent_fold", "items": items})
    if cross_split:
        errors.append(f"{len(cross_split)} brand query collisions across splits")

    gold_norm = {normalize_query(text): str(qid) for qid, text in zip(gold_sessions["query_id"], gold_sessions["query_text"])}
    gold_fold = {fold_text(text): str(qid) for qid, text in zip(gold_sessions["query_id"], gold_sessions["query_text"])}
    gold_text_hits = []
    for row in queries.itertuples(index=False):
        norm = normalize_query(row.query_text)
        folded = fold_text(row.query_text)
        if norm in gold_norm or folded in gold_fold:
            gold_text_hits.append(
                {
                    "query_id": str(row.query_id),
                    "query_text": str(row.query_text),
                    "gold_query_id": gold_norm.get(norm) or gold_fold.get(folded),
                    "split": assignment.get(str(row.brand_family_id)),
                }
            )
    if gold_text_hits:
        errors.append(f"{len(gold_text_hits)} brand queries collide with Gold POI text")

    train_poi_ids: set[str] = set()
    for raw in train.to_dict("records"):
        for poi_id in [str(raw["intended_poi_id"]), *parse_id_list(raw.get("acceptable_poi_ids"))]:
            dest, _, _ = remap.get(poi_id, (poi_id if poi_id in v3_ids else None, "", ""))
            if dest:
                train_poi_ids.add(dest)
    gold_ids = set(gold_targets["poi_id"].astype(str))
    gold_ents = set(gold_targets["entity_group_id"].astype(str))
    core = load_v3_core()
    gold_eq = set(core[core["entity_group_id"].astype(str).isin(gold_ents)]["poi_id"].astype(str)) | gold_ids

    members_by_family: dict[str, set[str]] = defaultdict(set)
    for row in accepted.itertuples(index=False):
        members_by_family[str(row.brand_family_id)].add(str(row.poi_id))

    exposure = {}
    train_positive_blocked = []
    for family_id, split_name in assignment.items():
        members_ids = members_by_family.get(family_id, set())
        label = exposure_for_family(members_ids, train_poi_ids, allow_cold=False)
        exposure[family_id] = {
            "split": split_name,
            "exposure_class": label,
            "n_members": len(members_ids),
            "n_members_in_poi_train": len(members_ids & train_poi_ids),
            "n_gold_members": len(members_ids & gold_eq),
        }
        if split_name == "train" and members_ids & gold_eq:
            train_positive_blocked.extend(sorted(members_ids & gold_eq))

    positives_by_family: dict[str, set[str]] = defaultdict(set)
    for row in packet:
        positives_by_family[str(row["brand_family_id"])].update(str(pid) for pid in row.get("positive_poi_ids") or [])
    empty_train = [
        family_id
        for family_id, split_name in assignment.items()
        if split_name == "train" and not (positives_by_family.get(family_id, set()) - gold_eq)
    ]

    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "sources": {
            "family_split": source_record(split_path),
            "queries": source_record(queries_path),
            "packet": source_record(packet_path),
            "membership": source_record(membership_dir / "manifest.json"),
            "train_v6": source_record(train_csv),
            "gold_poi": source_record(gold_dir / "manifest.json"),
        },
        "stats": {
            "families": {key: len(value) for key, value in families_by_split.items()},
            "cross_split_collisions": len(cross_split),
            "gold_text_collisions": len(gold_text_hits),
            "train_brand_gold_member_ids": len(set(train_positive_blocked)),
            "train_families_without_non_gold_positive": empty_train,
            "exposure": {
                label: sum(1 for row in exposure.values() if row["exposure_class"] == label)
                for label in (
                    "brand_query_heldout_branch_seen",
                    "brand_query_heldout_branch_unseen",
                    "cold_brand",
                )
            },
        },
        "gold_text_hits": gold_text_hits,
        "cross_split": cross_split[:50],
        "exposure_by_family": exposure,
        "train_brand_mask_gold_ids": sorted(set(train_positive_blocked)),
    }
    write_json(output_dir / "leakage_audit.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, default=SPLITS_V1 / "family_split.json")
    parser.add_argument("--queries", type=Path, default=TRAIN_BRAND_V3 / "brand_intent_queries_v3.parquet")
    parser.add_argument("--packet", type=Path, default=TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl")
    parser.add_argument("--membership-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--train-csv", type=Path, default=TRAIN_V6 / "query_variants.csv")
    parser.add_argument("--gold-dir", type=Path, default=GOLD_POI)
    parser.add_argument("--output-dir", type=Path, default=SPLITS_V1)
    args = parser.parse_args()
    report = audit(
        args.split,
        args.queries,
        args.packet,
        args.membership_dir,
        args.train_csv,
        args.gold_dir,
        args.output_dir,
    )
    print(json.dumps({key: report[key] for key in ("verdict", "errors", "warnings", "stats")}, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
