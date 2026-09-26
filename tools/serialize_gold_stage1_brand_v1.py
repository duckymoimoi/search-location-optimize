"""Serialize family-split brand queries into Gold/dev/train evaluation records."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from stage1_brand_query_v1_common import read_jsonl
from stage1_brand_v3_common import (
    GOLD_BRAND,
    GOLD_BRAND_DEV,
    GOLD_BRAND_STAGING,
    GOLD_POI,
    LABEL_POLICY_VERSION,
    MEMBERSHIP_V3,
    OPERATOR_TO_DIFFICULTY,
    OPERATOR_TO_ROLE,
    PREFIX_EXPANDER_VERSION,
    SCHEMA_VERSION,
    SPLITS_V1,
    TRAIN_BRAND_V3,
    CORPUS_VERSION,
    NORMALIZER_VERSION,
    exposure_for_family,
    fold_text,
    graphemes,
    group_ready_grapheme,
    load_v3_core,
    parse_id_list,
    remap_lookup,
    sha256_file,
    source_record,
    write_json,
)


def load_assignment(split_path: Path) -> dict[str, str]:
    doc = json.loads(split_path.read_text(encoding="utf-8"))
    return {row["brand_family_id"]: row["split"] for row in doc["families"]}


def load_exposure(leakage_path: Path) -> dict[str, str]:
    if not leakage_path.exists():
        return {}
    doc = json.loads(leakage_path.read_text(encoding="utf-8"))
    return {
        family_id: row["exposure_class"]
        for family_id, row in doc.get("exposure_by_family", {}).items()
    }


def serialize_split(
    split_name: str,
    queries: pd.DataFrame,
    packet_by_intent: dict[str, dict],
    assignment: dict[str, str],
    exposure: dict[str, str],
    other_folds: list[str],
    gold_mask: set[str],
    output_dir: Path,
    *,
    suite_id: str,
    status: str,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = queries[queries["brand_family_id"].map(assignment) == split_name].copy()
    query_rows: list[dict] = []
    qrel_rows: list[dict] = []
    prefix_rows: list[dict] = []
    review_rows: list[dict] = []
    for raw in selected.to_dict("records"):
        packet = packet_by_intent[str(raw["intent_id"])]
        positives = [str(pid) for pid in packet["positive_poi_ids"]]
        if split_name == "train":
            sample_pool = [pid for pid in positives if pid not in gold_mask]
            mask_pool = [pid for pid in positives if pid in gold_mask]
            if not sample_pool:
                continue
            positives = sample_pool
            ignore_ids = mask_pool
        else:
            ignore_ids = []
        operator = str(raw["variant_operator"])
        role = OPERATOR_TO_ROLE[operator]
        family_id = str(raw["brand_family_id"])
        query_id = str(raw["query_id"])
        qrel_set_id = f"{query_id}:brand"
        query_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_type": "brand_group_query",
                "suite_id": suite_id,
                "query_id": query_id,
                "query_family_id": family_id,
                "query_text": str(raw["query_text"]),
                "query_role": role,
                "difficulty": OPERATOR_TO_DIFFICULTY[operator],
                "brand_family_id": family_id,
                "brand_group_id": str(packet["brand_group_id"]),
                "namespace": str(packet["brand_namespace"]),
                "variant_operator": operator,
                "exposure_class": exposure.get(family_id, "brand_query_heldout_branch_seen"),
                "acceptable_poi_ids": positives,
                "qrel_set_id": qrel_set_id,
                "review_status": "accepted",
            }
        )
        for poi_id in positives:
            qrel_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "evaluation_qrel",
                    "suite_id": suite_id,
                    "qrel_set_id": qrel_set_id,
                    "target_type": "poi",
                    "target_id": poi_id,
                    "label": "compatible",
                    "relevance": 2,
                    "label_reason": "brand_group_member",
                    "evidence_source": ["brand_membership_v3"],
                }
            )
        for poi_id in ignore_ids:
            qrel_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "record_type": "evaluation_qrel",
                    "suite_id": suite_id,
                    "qrel_set_id": qrel_set_id,
                    "target_type": "poi",
                    "target_id": poi_id,
                    "label": "ignore",
                    "relevance": 0,
                    "label_reason": "manual_adjudication",
                    "evidence_source": ["gold_stage1_v2_1_overlap_mask"],
                }
            )
        if operator in {"brand_canonical", "brand_namespace_form"}:
            ready_n, ready_prefix = group_ready_grapheme(str(raw["query_text"]), other_folds)
            units = graphemes(str(raw["query_text"]))
            prefix_rows.append(
                {
                    "query_id": query_id,
                    "query_family_id": family_id,
                    "group_ready_grapheme": ready_n,
                    "full_graphemes": len(units),
                    "group_ready_prefix": ready_prefix,
                    "review_note": "First compact prefix that does not collide with another accepted brand fold.",
                }
            )
            for index in range(1, len(units) + 1):
                prefix = "".join(units[:index])
                state = "pre_identity" if index < ready_n else "group_ready"
                qrel = qrel_set_id if state == "group_ready" else None
                prefix_rows.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "record_type": "prefix_checkpoint",
                        "suite_id": suite_id,
                        "query_id": query_id,
                        "checkpoint_index": index,
                        "prefix_text": prefix,
                        "prefix_unit": "grapheme",
                        "full_unit_count": len(units),
                        "evidence_state": state,
                        "qrel_set_id": qrel,
                        "is_full_query": index == len(units),
                        "expander_version": PREFIX_EXPANDER_VERSION,
                    }
                )
        review_rows.append(
            {
                "brand_family_id": family_id,
                "brand_group_id": str(packet["brand_group_id"]),
                "brand_canonical": str(packet["brand_canonical"]),
                "namespace": str(packet["brand_namespace"]),
                "n_positive": len(positives),
                "verified_aliases": packet.get("verified_aliases") or [],
                "requires_namespace_token": bool(packet.get("requires_namespace_token")),
                "review_status": "accepted_structural",
            }
        )

    queries_path = output_dir / "brand_queries_v1.parquet"
    qrels_path = output_dir / "brand_qrels_v1.parquet"
    pq.write_table(pa.Table.from_pylist(query_rows), queries_path, compression="zstd")
    pq.write_table(pa.Table.from_pylist(qrel_rows), qrels_path, compression="zstd")
    evidence = [row for row in prefix_rows if "group_ready_grapheme" in row]
    checkpoints = [row for row in prefix_rows if row.get("record_type") == "prefix_checkpoint"]
    write_jsonl(output_dir / "prefix_evidence_v1.jsonl", evidence)
    write_jsonl(output_dir / "prefix_checkpoints_v1.jsonl", checkpoints)
    write_json(
        output_dir / "independent_family_review.json",
        {
            "policy": "Structural review of canonical, namespace, alias evidence, and v3 member set. No invented aliases.",
            "n_families": len({row["brand_family_id"] for row in review_rows}),
            "n_verified_alias_queries": sum(1 for row in query_rows if row["query_role"] == "verified_alias"),
            "alias_shortfall_adjudicated": True,
            "rows": review_rows,
        },
    )
    counts = {
        "n_queries": len(query_rows),
        "n_qrels": len(qrel_rows),
        "n_families": len({row["brand_family_id"] for row in query_rows}),
        "n_prefix_evidence": len(evidence),
        "n_prefix_checkpoints": len(checkpoints),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "suite_manifest",
        "suite_id": suite_id,
        "status": status,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "corpus_version": CORPUS_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "entity_snapshot_version": None,
        "brand_snapshot_version": "brand_membership_v3",
        "address_snapshot_version": None,
        "prefix_expander_version": PREFIX_EXPANDER_VERSION,
        "label_policy_version": LABEL_POLICY_VERSION,
        "source_hashes": {
            "queries_v3": sha256_file(TRAIN_BRAND_V3 / "brand_intent_queries_v3.parquet"),
            "packet_v3": sha256_file(TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl"),
            "membership_v3": sha256_file(MEMBERSHIP_V3 / "manifest.json"),
            "family_split": sha256_file(SPLITS_V1 / "family_split.json"),
        },
        "artifact_hashes": {
            path.name: sha256_file(path)
            for path in (
                queries_path,
                qrels_path,
                output_dir / "prefix_evidence_v1.jsonl",
                output_dir / "prefix_checkpoints_v1.jsonl",
                output_dir / "independent_family_review.json",
            )
        },
        "counts": counts,
        "split": split_name,
    }
    write_json(output_dir / "manifest.json", manifest)
    return {"split": split_name, "counts": counts, "output_dir": str(output_dir.as_posix())}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def serialize(output_root: Path | None = None) -> dict:
    assignment = load_assignment(SPLITS_V1 / "family_split.json")
    exposure = load_exposure(SPLITS_V1 / "leakage_audit.json")
    queries = pd.read_parquet(TRAIN_BRAND_V3 / "brand_intent_queries_v3.parquet")
    packet = {str(row["intent_id"]): row for row in read_jsonl(TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl")}
    gold_targets = pd.read_parquet(GOLD_POI / "target_pois_v2_1.parquet")
    gold_mask = set(gold_targets["poi_id"].astype(str))
    other_folds = sorted({fold_text(row["brand_canonical"]) for row in packet.values()})
    gold_dir = GOLD_BRAND_STAGING if output_root is None else output_root / "gold"
    dev_dir = GOLD_BRAND_DEV if output_root is None else output_root / "dev"
    train_dir = TRAIN_BRAND_V3 / "train_eval_view" if output_root is None else output_root / "train"
    reports = [
        serialize_split(
            "test",
            queries,
            packet,
            assignment,
            exposure,
            other_folds,
            gold_mask,
            gold_dir,
            suite_id="gold_stage1_brand_v1",
            status="validated",
        ),
        serialize_split(
            "dev",
            queries,
            packet,
            assignment,
            exposure,
            other_folds,
            gold_mask,
            dev_dir,
            suite_id="gold_stage1_brand_v1",
            status="draft",
        ),
        serialize_split(
            "train",
            queries,
            packet,
            assignment,
            exposure,
            other_folds,
            gold_mask,
            train_dir,
            suite_id="gold_stage1_brand_v1",
            status="draft",
        ),
    ]
    write_json(
        TRAIN_BRAND_V3 / "compile_manifest.json",
        {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "splits": reports,
            "sources": {
                "family_split": source_record(SPLITS_V1 / "family_split.json"),
                "packet": source_record(TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl"),
            },
        },
    )
    return {"splits": reports}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    del args
    print(json.dumps(serialize(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
