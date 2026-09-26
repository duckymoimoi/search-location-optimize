"""Combine manually authored brand-query batches and materialize qrels."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from stage1_brand_query_v1_common import (
    GENERATOR_VERSION,
    QRELS_VERSION,
    QUERY_COLUMNS,
    read_jsonl,
    sha256_file,
)


def serialize(batches_dir: Path, packet_path: Path, output_dir: Path) -> dict[str, Any]:
    batch_paths = sorted(batches_dir.glob("batch_*.jsonl"))
    if not batch_paths:
        raise FileNotFoundError(f"No batch_*.jsonl under {batches_dir}")
    query_rows: list[dict[str, Any]] = []
    for path in batch_paths:
        query_rows.extend(read_jsonl(path))
    packet_rows = read_jsonl(packet_path)
    packet_by_intent = {str(row["intent_id"]): row for row in packet_rows}

    # Reviewed packet revisions may merge/exclude an intent while preserving
    # immutable historical batch files. Only intents present in the selected
    # packet are compiled into the current staging view.
    query_rows = [
        row for row in query_rows if str(row.get("intent_id") or "") in packet_by_intent
    ]

    for row in query_rows:
        if set(row) != set(QUERY_COLUMNS):
            raise ValueError(
                f"{row.get('query_id')}: query schema mismatch "
                f"missing={sorted(set(QUERY_COLUMNS)-set(row))} "
                f"extra={sorted(set(row)-set(QUERY_COLUMNS))}"
            )
        row["namespace_scope"] = [str(value) for value in row["namespace_scope"]]
    query_rows.sort(key=lambda row: str(row["query_id"]))

    qrel_rows: list[dict[str, str]] = []
    for row in query_rows:
        intent_id = str(row["intent_id"])
        packet = packet_by_intent.get(intent_id)
        if packet is None:
            raise ValueError(f"{row['query_id']}: intent missing from packet")
        for poi_id in packet["positive_poi_ids"]:
            qrel_rows.append(
                {
                    "query_id": str(row["query_id"]),
                    "poi_id": str(poi_id),
                    "relation": "positive_pool",
                    "label_reason": "accepted_brand_namespace_membership",
                    "brand_group_id": intent_id,
                    "qrels_version": QRELS_VERSION,
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "brand_intent_queries_v1.csv"
    query_path = output_dir / "brand_intent_queries_v1.parquet"
    qrels_path = output_dir / "brand_query_qrels_v1.parquet"
    manifest_path = output_dir / "authored_manifest_v1.json"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUERY_COLUMNS)
        writer.writeheader()
        for row in query_rows:
            value = dict(row)
            value["namespace_scope"] = json.dumps(
                value["namespace_scope"], ensure_ascii=False, separators=(",", ":")
            )
            writer.writerow(value)
    pq.write_table(
        pa.Table.from_pylist(query_rows), query_path, compression="zstd"
    )
    pq.write_table(pa.Table.from_pylist(qrel_rows), qrels_path, compression="zstd")

    manifest = {
        "dataset": "train_stage1_brand_queries_v1",
        "status": "STAGING",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "qrels_version": QRELS_VERSION,
        "packet": {"path": str(packet_path), "sha256": sha256_file(packet_path)},
        "batches": [
            {"path": str(path), "sha256": sha256_file(path)} for path in batch_paths
        ],
        "stats": {
            "authored_intents": len({row["intent_id"] for row in query_rows}),
            "query_rows": len(query_rows),
            "qrel_rows": len(qrel_rows),
        },
        "artifacts": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in (csv_path, query_path, qrels_path)
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches-dir", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            serialize(args.batches_dir, args.packet, args.output_dir),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
