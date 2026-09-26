"""Rematerialize staging brand queries/qrels against membership v3 and packet v3."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from stage1_brand_query_v1_common import (
    GENERATOR_VERSION,
    QRELS_VERSION,
    QUERY_COLUMNS,
    read_jsonl,
)
from stage1_brand_v3_common import (
    LEFT_OVER_FAMILIES,
    MEMBERSHIP_V3,
    PACKET_V2,
    STAGING_V1,
    TRAIN_BRAND_V3,
    sha256_file,
    source_record,
    write_json,
)


def reconcile(
    batches_dir: Path,
    packet_path: Path,
    membership_dir: Path,
    output_dir: Path,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_rows = read_jsonl(packet_path)
    packet_by_intent = {str(row["intent_id"]): row for row in packet_rows}
    query_rows: list[dict] = []
    for path in sorted(batches_dir.glob("batch_*.jsonl")):
        query_rows.extend(read_jsonl(path))
    kept = [row for row in query_rows if str(row.get("intent_id") or "") in packet_by_intent]
    dropped_leftover = [
        str(row.get("intent_id") or "")
        for row in query_rows
        if str(row.get("brand_family_id") or "") in LEFT_OVER_FAMILIES
        and str(row.get("intent_id") or "") not in packet_by_intent
    ]
    leftover_kept = [
        row for row in kept if str(row.get("brand_family_id") or "") in LEFT_OVER_FAMILIES
    ]
    if leftover_kept:
        raise ValueError(f"leftover families leaked into compiled queries: {len(leftover_kept)}")
    for row in kept:
        row["namespace_scope"] = [str(value) for value in row["namespace_scope"]]
        row["generator_version"] = GENERATOR_VERSION
    kept.sort(key=lambda row: str(row["query_id"]))

    qrel_rows: list[dict[str, str]] = []
    empty_queries: list[str] = []
    for row in kept:
        packet = packet_by_intent[str(row["intent_id"])]
        positives = [str(pid) for pid in packet["positive_poi_ids"]]
        if not positives:
            empty_queries.append(str(row["query_id"]))
            continue
        for poi_id in positives:
            qrel_rows.append(
                {
                    "query_id": str(row["query_id"]),
                    "poi_id": poi_id,
                    "relation": "positive_pool",
                    "label_reason": "accepted_brand_namespace_membership_v3",
                    "brand_group_id": str(packet["brand_group_id"]),
                    "qrels_version": QRELS_VERSION,
                }
            )
    if empty_queries:
        raise ValueError(f"queries without v3 positives: {empty_queries[:10]}")

    csv_path = output_dir / "brand_intent_queries_v3.csv"
    query_path = output_dir / "brand_intent_queries_v3.parquet"
    qrels_path = output_dir / "brand_query_qrels_v3.parquet"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUERY_COLUMNS)
        writer.writeheader()
        for row in kept:
            value = dict(row)
            value["namespace_scope"] = json.dumps(
                value["namespace_scope"], ensure_ascii=False, separators=(",", ":")
            )
            writer.writerow({key: value.get(key) for key in QUERY_COLUMNS})
    pq.write_table(pa.Table.from_pylist(kept), query_path, compression="zstd")
    pq.write_table(pa.Table.from_pylist(qrel_rows), qrels_path, compression="zstd")

    staging_intents = {str(row["intent_id"]) for row in kept}
    packet_intents = set(packet_by_intent)
    manifest = {
        "dataset": "train_stage1_brand_queries_v3_reconciled",
        "status": "RECONCILED",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "sources": {
            "packet_v3": source_record(packet_path),
            "packet_v2": source_record(PACKET_V2),
            "membership_v3": source_record(membership_dir / "manifest.json"),
        },
        "stats": {
            "authored_intents": len(staging_intents),
            "packet_intents": len(packet_intents),
            "intent_id_mismatch": sorted(packet_intents ^ staging_intents),
            "query_rows": len(kept),
            "qrel_rows": len(qrel_rows),
            "leftover_families_excluded": LEFT_OVER_FAMILIES,
            "dropped_historical_leftover_query_intents": sorted(set(dropped_leftover)),
        },
        "artifacts": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in (csv_path, query_path, qrels_path)
        },
    }
    write_json(output_dir / "reconcile_manifest_v3.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches-dir", type=Path, default=STAGING_V1 / "batches")
    parser.add_argument("--packet", type=Path, default=TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl")
    parser.add_argument("--membership-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--output-dir", type=Path, default=TRAIN_BRAND_V3)
    args = parser.parse_args()
    print(
        json.dumps(
            reconcile(args.batches_dir, args.packet, args.membership_dir, args.output_dir),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
