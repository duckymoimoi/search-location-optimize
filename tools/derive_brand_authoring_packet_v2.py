"""Apply reviewed intent-level merge/exclude decisions to packet v1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from stage1_brand_query_v1_common import read_jsonl, sha256_file


PACKET_VERSION = "brand_authoring_packet_v2"


def pool_hash(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest()


def derive(source: Path, overrides: Path, output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output: {output_dir}")
    rows = read_jsonl(source)
    by_intent = {str(row["intent_id"]): dict(row) for row in rows}
    source_index = {str(row["intent_id"]): i for i, row in enumerate(rows, start=1)}
    decisions: list[dict[str, str]] = []
    with overrides.open("r", encoding="utf-8-sig", newline="") as handle:
        for value in csv.DictReader(handle):
            decisions.append({key: str(item or "").strip() for key, item in value.items()})

    removed: set[str] = set()
    for decision in decisions:
        source_id = decision["source_intent_id"]
        action = decision["decision"]
        if source_id not in by_intent:
            raise ValueError(f"Unknown source intent: {source_id}")
        if action == "exclude":
            removed.add(source_id)
            continue
        if action != "merge":
            raise ValueError(f"Unknown decision: {action}")
        target_id = decision["target_intent_id"]
        if target_id not in by_intent or target_id == source_id:
            raise ValueError(f"Invalid merge target: {target_id}")
        source_row = by_intent[source_id]
        target_row = by_intent[target_id]
        if source_row["brand_namespace"] != target_row["brand_namespace"]:
            raise ValueError("Cannot merge different namespaces")
        merged = sorted(
            set(source_row["positive_poi_ids"]) | set(target_row["positive_poi_ids"])
        )
        target_row["positive_poi_ids"] = merged
        target_row["n_positive"] = len(merged)
        target_row["positive_pool_sha256"] = pool_hash(merged)
        target_row["merged_source_intents"] = sorted(
            set(target_row.get("merged_source_intents", [])) | {source_id}
        )
        target_row["membership_evidence_counts"] = {
            key: int(source_row["membership_evidence_counts"].get(key, 0))
            + int(target_row["membership_evidence_counts"].get(key, 0))
            for key in sorted(
                set(source_row["membership_evidence_counts"])
                | set(target_row["membership_evidence_counts"])
            )
        }
        removed.add(source_id)

    output_rows = []
    for intent_id, row in by_intent.items():
        if intent_id in removed:
            continue
        row["packet_version"] = PACKET_VERSION
        row["intent_index"] = source_index[intent_id]
        row.setdefault("merged_source_intents", [])
        output_rows.append(row)
    output_rows.sort(key=lambda row: int(row["intent_index"]))

    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "brand_authoring_packet_v2.jsonl"
    with packet_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {
        "dataset": "train_stage1_brand_queries_v2_authoring_packet",
        "packet_version": PACKET_VERSION,
        "status": "READY_FOR_AUTHORING",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_packet": {"path": str(source), "sha256": sha256_file(source)},
        "overrides": {"path": str(overrides), "sha256": sha256_file(overrides)},
        "output": {
            "path": str(packet_path),
            "sha256": sha256_file(packet_path),
            "bytes": packet_path.stat().st_size,
        },
        "stats": {
            "packet_rows": len(output_rows),
            "excluded_intents": sum(d["decision"] == "exclude" for d in decisions),
            "merged_intents": sum(d["decision"] == "merge" for d in decisions),
            "positive_members": sum(int(row["n_positive"]) for row in output_rows),
        },
        "decisions": decisions,
    }
    manifest_path = output_dir / "authoring_packet_manifest_v2.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(derive(args.source, args.overrides, args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
