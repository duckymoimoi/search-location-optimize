"""Verify the v2 cleaned corpus and its migration map."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from build_clean_poi_corpus_v2 import (
    DEFAULT_OUTPUT,
    MAX_DUPLICATE_DISTANCE_M,
    distance_m,
    fold,
    full_address_key,
    point,
    single_character,
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    source = Path(manifest["source_corpus_path"])
    for name, expected in manifest["source_hashes"].items():
        if digest(source / name) != expected:
            raise ValueError(f"Source hash changed: {name}")
    for name, expected in manifest["artifact_hashes"].items():
        if digest(output / name) != expected:
            raise ValueError(f"Artifact hash mismatch: {name}")

    core = pq.read_table(output / "pois_core.parquet").to_pylist()
    documents = pq.read_table(output / "search_documents.parquet").to_pylist()
    legacy = pq.read_table(output / "pois.parquet", columns=["poi_id", "name"]).to_pylist()
    access = pq.read_table(output / "pois_access_enrichment.parquet", columns=["poi_id"]).to_pylist()
    regions = pq.read_table(output / "poi_regions.parquet", columns=["poi_id"]).to_pylist()
    migration = pq.read_table(output / "poi_id_migration.parquet").to_pylist()

    ids = [str(row["poi_id"]) for row in core]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate POI ID in cleaned corpus")
    if any(single_character(row["name"]) for row in core):
        raise ValueError("A single-character name survived cleaning")
    for name, rows in (("documents", documents), ("legacy", legacy), ("access", access)):
        if [str(row["poi_id"]) for row in rows] != ids:
            raise ValueError(f"{name} ID order differs from core")
    renamed_ids = {
        row["old_poi_id"] for row in migration
        if row["action"] == "rename_to_address"
    }
    for core_row, doc_row, legacy_row in zip(core, documents, legacy):
        if core_row["name"] != doc_row["name"]:
            raise ValueError(f"Name mismatch for {core_row['poi_id']}")
        if core_row["poi_id"] in renamed_ids and core_row["name"] != legacy_row["name"]:
            raise ValueError(f"Renamed legacy row mismatch for {core_row['poi_id']}")
        if not doc_row["passage_context"].startswith(core_row["name"] + " |"):
            raise ValueError(f"Passage prefix mismatch for {core_row['poi_id']}")
    if {str(row["poi_id"]) for row in regions} - set(ids):
        raise ValueError("Region FK references removed POI")

    if len(migration) != len({row["old_poi_id"] for row in migration}):
        raise ValueError("Duplicate old ID in migration map")
    action_counts = Counter(row["action"] for row in migration)
    if dict(action_counts) != manifest["migration_actions"]:
        raise ValueError("Migration action counts differ from manifest")
    survivors = set(ids)
    for row in migration:
        old_id = row["old_poi_id"]
        target_id = row["canonical_poi_id"]
        if row["action"] == "drop_short_name":
            if target_id is not None or old_id in survivors:
                raise ValueError(f"Invalid dropped ID mapping: {old_id}")
        elif target_id not in survivors:
            raise ValueError(f"Migration points to missing survivor: {old_id}")
        elif row["action"] == "merge_duplicate":
            distance = row["distance_to_canonical_m"]
            if distance is None or not distance < MAX_DUPLICATE_DISTANCE_M:
                raise ValueError(f"Invalid duplicate distance for {old_id}")

    groups = defaultdict(list)
    for row in core:
        address = full_address_key(row)
        if address:
            groups[(fold(row["name"]), address)].append(row)
    for rows in groups.values():
        for index, left in enumerate(rows):
            for right in rows[index + 1 :]:
                if distance_m(point(left), point(right)) < MAX_DUPLICATE_DISTANCE_M:
                    raise ValueError(
                        f"Near duplicate survived: {left['poi_id']} {right['poi_id']}"
                    )

    expected_rows = manifest["counts"]["output_rows"]
    if len(core) != expected_rows:
        raise ValueError(f"Expected {expected_rows} output rows, got {len(core)}")
    return {"verdict": "PASS", "rows": len(core), "actions": dict(action_counts)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = verify(args.corpus.resolve())
    except Exception as error:
        result = {"verdict": "FAIL", "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
