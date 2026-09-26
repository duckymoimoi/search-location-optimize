"""Move active Stage-1 targets/qrels onto cleaned corpus v2.

Keep historical Gold v1 untouched. Write a corpus-v2-compatible Gold snapshot;
remove invalid and Gold-positive POIs from the active train target pool without
replenishing it. The locked 500-query checkpoint is left unchanged.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/vietnam"
GOLD_V1 = DATA / "gold_stage1_v1"
GOLD_V2 = DATA / "gold_stage1_v1_corpus_v2"
TRAIN = DATA / "train_stage1_20k"
WORKSPACE = DATA / "train_stage1_queries_v6"
CORPUS = DATA / "poi_corpus_v2"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict[str, str]], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    source_manifest = json.loads((TRAIN / "manifest.json").read_text(encoding="utf-8"))
    require(source_manifest["total_target_pois"] == 20000, "Expected original 20k pool; migration already run?")
    for filename in ("target_pois_20k.csv", "target_pois_20k.parquet"):
        require(digest(TRAIN / filename) == source_manifest["files"][filename]["sha256"],
                f"Source hash mismatch: {filename}")
    require(not GOLD_V2.exists(), f"Output already exists: {GOLD_V2}")

    migration = {r["old_poi_id"]: r for r in pq.read_table(CORPUS / "poi_id_migration.parquet").to_pylist()}
    live = {r["poi_id"]: r for r in pq.read_table(CORPUS / "pois_core.parquet").to_pylist()}
    gold_table = pq.read_table(GOLD_V1 / "target_pois_v1.parquet")
    gold_rows = gold_table.to_pylist()
    gold_csv, gold_headers = read_csv(GOLD_V1 / "target_pois_v1.csv")
    require(len(gold_rows) == len(gold_csv) == 180, "Unexpected Gold target count")
    replacements = []
    for row, csv_row in zip(gold_rows, gold_csv, strict=True):
        require(row["case_id"] == csv_row["case_id"] and row["poi_id"] == csv_row["poi_id"],
                "Gold CSV/Parquet target mismatch")
        old_id = row["poi_id"]
        move = migration[old_id]
        require(move["action"] != "drop_short_name", f"Gold target has no survivor: {old_id}")
        new_id = move["canonical_poi_id"]
        require(new_id in live, f"Missing Gold survivor: {new_id}")
        if new_id != old_id:
            poi = live[new_id]
            address = poi["address"] or {}
            for key, value in {
                "poi_id": new_id,
                "name": poi["name"],
                "brand": poi["brand"],
                "ref": poi["ref"],
                "category": poi["category"],
                "province": poi["province"],
                "subdistrict": poi["subdistrict"],
                "housenumber": address.get("housenumber"),
                "street": address.get("street"),
                "address_text": poi["address_text"],
                "address_status": poi["address_status"],
            }.items():
                row[key] = value
                csv_row[key] = "" if value is None else str(value)
            replacements.append({"case_id": row["case_id"], "old_poi_id": old_id,
                                 "new_poi_id": new_id, "name": poi["name"]})
    require(len(replacements) == 2, f"Expected 2 Gold replacements, got {len(replacements)}")

    query_table = pq.read_table(GOLD_V1 / "query_variants_v1.parquet")
    query_rows = query_table.to_pylist()
    query_csv, query_headers = read_csv(GOLD_V1 / "query_variants_v1.csv")
    require(len(query_rows) == len(query_csv) == 1080, "Unexpected Gold query count")
    changed_qrels = 0
    for row, csv_row in zip(query_rows, query_csv, strict=True):
        require(row["variant_id"] == csv_row["variant_id"], "Gold query CSV/Parquet order mismatch")
        old_intended = row["intended_poi_id"]
        new_intended = migration[old_intended]["canonical_poi_id"]
        require(new_intended in live, f"Missing intended POI: {new_intended}")
        acceptable = list(dict.fromkeys(migration[x]["canonical_poi_id"]
                                        for x in row["acceptable_poi_ids"]))
        require(all(x in live for x in acceptable), "Gold qrel has missing POI")
        require(new_intended in acceptable, "Intended POI absent from acceptable set")
        if old_intended != new_intended or acceptable != row["acceptable_poi_ids"]:
            changed_qrels += 1
        row["intended_poi_id"] = new_intended
        row["acceptable_poi_ids"] = acceptable
        row["n_acceptable"] = len(acceptable)
        row["is_multipositive"] = len(acceptable) > 1
        csv_row["intended_poi_id"] = new_intended
        csv_row["acceptable_poi_ids"] = "|".join(acceptable)

    gold_positive_ids = {x for row in query_rows for x in row["acceptable_poi_ids"]}
    train_table = pq.read_table(TRAIN / "target_pois_20k.parquet")
    train_csv, train_headers = read_csv(TRAIN / "target_pois_20k.csv")
    train_rows = train_table.to_pylist()
    require(len(train_rows) == len(train_csv) == 20000, "Unexpected train target count")
    removed = []
    keep_mask = []
    for row, csv_row in zip(train_rows, train_csv, strict=True):
        require(row["case_id"] == csv_row["case_id"] and row["poi_id"] == csv_row["poi_id"],
                "Train CSV/Parquet target mismatch")
        poi_id = row["poi_id"]
        move = migration[poi_id]
        reasons = []
        if move["action"] in {"merge_duplicate", "drop_short_name"}:
            reasons.append(move["action"])
        if poi_id in gold_positive_ids:
            reasons.append("gold_positive_leakage")
        if reasons:
            removed.append({"case_id": row["case_id"], "poi_id": poi_id,
                            "name": row["name"], "reasons": reasons})
        keep_mask.append(not reasons)
    require(len(removed) == 61, f"Expected 61 train removals, got {len(removed)}")
    retained_csv = [row for row, keep in zip(train_csv, keep_mask, strict=True) if keep]
    retained_table = train_table.filter(pa.array(keep_mask))
    require(retained_table.num_rows == len(retained_csv) == 19939, "Train count mismatch")
    require(not (set(retained_table["poi_id"].to_pylist()) & gold_positive_ids),
            "Gold-positive POI remains in train")
    require(all(x in live for x in retained_table["poi_id"].to_pylist()),
            "Train POI absent from v2 corpus")

    GOLD_V2.mkdir(parents=True)
    write_csv(GOLD_V2 / "target_pois.csv", gold_csv, gold_headers)
    pq.write_table(pa.Table.from_pylist(gold_rows, schema=gold_table.schema), GOLD_V2 / "target_pois.parquet")
    write_csv(GOLD_V2 / "query_variants.csv", query_csv, query_headers)
    pq.write_table(pa.Table.from_pylist(query_rows, schema=query_table.schema), GOLD_V2 / "query_variants.parquet")
    multi_rows = [row for row in query_rows if row["is_multipositive"]]
    write_json(GOLD_V2 / "qrels_policy.json", {
        "policy": "brand_multipositive_only_as_authored_mapped_to_corpus_v2",
        "n_rows": len(query_rows), "n_cases": len(gold_rows),
        "n_multipositive_rows": len(multi_rows),
        "n_multipositive_cases": len({r["case_id"] for r in multi_rows}),
        "note": "No automatic brand expansion. Only migration-map remap and deduplication of accepted IDs.",
    })
    write_json(GOLD_V2 / "manifest.json", {
        "dataset": "gold_stage1_v1_corpus_v2", "status": "locked_migration_snapshot",
        "corpus_version": "vn-poi-core-v2-address-name-dedup50",
        "source_gold": "gold_stage1_v1 (immutable historical replay)",
        "source_gold_manifest_sha256": digest(GOLD_V1 / "manifest.json"),
        "source_migration_sha256": digest(CORPUS / "poi_id_migration.parquet"),
        "n_target_pois": len(gold_rows), "n_query_variants": len(query_rows),
        "target_replacements": replacements, "query_rows_with_remapped_qrels": changed_qrels,
        "files": {name: {"sha256": digest(GOLD_V2 / name)} for name in
                  ("target_pois.csv", "target_pois.parquet", "query_variants.csv",
                   "query_variants.parquet", "qrels_policy.json")},
        "created_at_utc": datetime.now(UTC).isoformat(),
    })

    # Write validated replacements alongside the originals, then switch each file.
    csv_tmp = TRAIN / "target_pois_20k.csv.v2tmp"
    parquet_tmp = TRAIN / "target_pois_20k.parquet.v2tmp"
    write_csv(csv_tmp, retained_csv, train_headers)
    pq.write_table(retained_table, parquet_tmp)
    require(len(read_csv(csv_tmp)[0]) == pq.read_metadata(parquet_tmp).num_rows == 19939,
            "Temporary train artifacts failed verification")
    os.replace(csv_tmp, TRAIN / "target_pois_20k.csv")
    os.replace(parquet_tmp, TRAIN / "target_pois_20k.parquet")
    counts = Counter(row["reasons"][0] for row in removed)
    leak_count = sum("gold_positive_leakage" in row["reasons"] for row in removed)
    write_json(TRAIN / "corpus_v2_removal_audit.json", {
        "source_rows": 20000, "retained_rows": 19939,
        "removed_duplicate_or_short": counts["merge_duplicate"] + counts["drop_short_name"],
        "removed_gold_positive": leak_count,
        "removed": removed,
    })
    source_manifest["version"] = "v1.1-corpus-v2-filtered"
    source_manifest["total_target_pois"] = len(retained_csv)
    source_manifest["source_corpus"] = "data/vietnam/poi_corpus_v2/pois.parquet"
    source_manifest["gold_exclusion_count"] = len(gold_rows)
    source_manifest["gold_overlap_count"] = 0
    source_manifest["gold_positive_overlap_count"] = 0
    source_manifest["migration_removed_count"] = len(removed)
    source_manifest["files"] = {
        name: {"rows": len(retained_csv), "sha256": digest(TRAIN / name)}
        for name in ("target_pois_20k.csv", "target_pois_20k.parquet")
    }
    source_manifest["strata_distribution"] = dict(Counter(r["primary_sampling_stratum"] for r in retained_csv))
    source_manifest["regional_distribution"] = dict(Counter(r["region"] for r in retained_csv))
    source_manifest["province_count"] = len({r["province"] for r in retained_csv})
    source_manifest["provinces"] = dict(Counter(r["province"] for r in retained_csv))
    source_manifest["migration_audit"] = "corpus_v2_removal_audit.json"
    write_json(TRAIN / "manifest.json", source_manifest)

    workspace = json.loads((WORKSPACE / "manifest.json").read_text(encoding="utf-8"))
    workspace["target_count"] = len(retained_csv)
    workspace["sources"]["target_pois"] = {
        "path": "data/vietnam/train_stage1_20k/target_pois_20k.parquet",
        "sha256": digest(TRAIN / "target_pois_20k.parquet"),
    }
    workspace["sources"]["poi_corpus"] = {
        "path": "data/vietnam/poi_corpus_v2/pois.parquet",
        "sha256": digest(CORPUS / "pois.parquet"),
    }
    workspace["sources"]["gold_exclusion"] = {
        "path": "data/vietnam/gold_stage1_v1_corpus_v2/target_pois.parquet",
        "sha256": digest(GOLD_V2 / "target_pois.parquet"),
    }
    workspace["sources"]["gold_qrels"] = {
        "path": "data/vietnam/gold_stage1_v1_corpus_v2/query_variants.parquet",
        "sha256": digest(GOLD_V2 / "query_variants.parquet"),
    }
    workspace["note"] = "The locked 500-query checkpoint is historical and unchanged; all 500 target IDs survive corpus v2."
    write_json(WORKSPACE / "manifest.json", workspace)
    print(json.dumps({"gold_replaced": replacements, "gold_query_rows_updated": changed_qrels,
                      "train_removed": len(removed), "train_remaining": len(retained_csv),
                      "gold_positive_train_overlap": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
