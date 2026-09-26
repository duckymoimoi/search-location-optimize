"""Build a versioned POI corpus with address names and 50 m duplicate removal.

The v1 source is immutable. Every old ID receives a migration decision so
training targets and qrels can be checked before adopting the new release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "vietnam" / "poi_corpus_v1"
DEFAULT_OUTPUT = ROOT / "data" / "vietnam" / "poi_corpus_v2"
VERSION = "vn-poi-core-v2-address-name-dedup50"
MAX_DUPLICATE_DISTANCE_M = 50.0
SOURCE_TABLES = (
    "pois_core.parquet",
    "search_documents.parquet",
    "poi_regions.parquet",
    "pois_access_enrichment.parquet",
    "pois.parquet",
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(text.casefold().split())


def single_character(value: Any) -> bool:
    name = unicodedata.normalize("NFKC", str(value or ""))
    return len([char for char in name if not char.isspace()]) == 1


def usable_address(row: dict[str, Any]) -> str | None:
    address = row.get("address") or {}
    house = " ".join(str(address.get("housenumber") or "").split())
    street = " ".join(str(address.get("street") or address.get("place") or "").split())
    compact = "".join(char for char in street if char.isalnum())
    if not house or len(compact) < 3 or not any(char.isalpha() for char in street):
        return None
    # The short form remains a natural address; admin stays in address_text.
    return f"{house} {street}"


def full_address_key(row: dict[str, Any]) -> tuple[str, str, str, str] | None:
    address = row.get("address") or {}
    house = re.sub(r"\s+", "", fold(address.get("housenumber")))
    street = fold(address.get("street") or address.get("place"))
    if not house or not street:
        return None
    province = str(row.get("province_region_id") or fold(row.get("province")))
    subdistrict = str(
        row.get("subdistrict_region_id") or fold(row.get("subdistrict"))
    )
    return house, street, province, subdistrict


def point(row: dict[str, Any]) -> tuple[float, float]:
    raw = row.get("ranking_point") or {}
    lat, lon = float(raw["lat"]), float(raw["lon"])
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError(f"Invalid ranking_point for {row['poi_id']}")
    return lat, lon


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dlambda = math.radians(b[1] - a[1])
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(h))


def priority(row: dict[str, Any], renamed: bool) -> tuple[Any, ...]:
    category = str(row.get("category") or "")
    is_named_category = not (
        category.startswith("address=") or category.startswith("building=")
    )
    return (
        -int(bool(row.get("preserve_individual_access_point"))),
        -int(is_named_category),
        -int(not renamed),
        -int(bool(row.get("aliases"))),
        -int(row.get("osm_type") == "node"),
        str(row["poi_id"]),
    )


def read_source() -> tuple[dict[str, pa.Table], dict[str, list[dict[str, Any]]]]:
    tables = {name: pq.read_table(SOURCE / name) for name in SOURCE_TABLES}
    rows = {name: table.to_pylist() for name, table in tables.items()}
    core_ids = [str(row["poi_id"]) for row in rows["pois_core.parquet"]]
    if len(core_ids) != len(set(core_ids)):
        raise ValueError("Source pois_core contains duplicate poi_id")
    for name in ("search_documents.parquet", "pois_access_enrichment.parquet", "pois.parquet"):
        ids = [str(row["poi_id"]) for row in rows[name]]
        if ids != core_ids:
            raise ValueError(f"{name} does not match pois_core row order")
    if {str(row["poi_id"]) for row in rows["poi_regions.parquet"]} - set(core_ids):
        raise ValueError("poi_regions contains unknown POI IDs")
    return tables, rows


def plan_decisions(
    core_rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], dict[str, float], Counter[str]]:
    renamed: dict[str, str] = {}
    removed: dict[str, str] = {}
    duplicate_distance: dict[str, float] = {}
    counts: Counter[str] = Counter()
    row_by_id = {str(row["poi_id"]): row for row in core_rows}

    for row in core_rows:
        poi_id = str(row["poi_id"])
        if not single_character(row.get("name")):
            continue
        counts["single_character_name"] += 1
        new_name = usable_address(row)
        if new_name is None:
            removed[poi_id] = "single_character_without_usable_address"
            counts["removed_short_name"] += 1
        else:
            renamed[poi_id] = new_name
            counts["renamed_to_address"] += 1

    groups: dict[tuple[str, tuple[str, str, str, str]], list[str]] = defaultdict(list)
    for row in core_rows:
        poi_id = str(row["poi_id"])
        if poi_id in removed:
            continue
        address_key = full_address_key(row)
        name_key = fold(renamed.get(poi_id, row.get("name")))
        if address_key and name_key:
            groups[(name_key, address_key)].append(poi_id)

    for poi_ids in groups.values():
        if len(poi_ids) < 2:
            continue
        pending = sorted(poi_ids, key=lambda poi_id: priority(row_by_id[poi_id], poi_id in renamed))
        while pending:
            keeper = pending[0]
            keeper_point = point(row_by_id[keeper])
            remaining = []
            for candidate in pending[1:]:
                distance = distance_m(keeper_point, point(row_by_id[candidate]))
                if distance < MAX_DUPLICATE_DISTANCE_M:
                    removed[candidate] = keeper
                    duplicate_distance[candidate] = round(distance, 3)
                    counts["merged_duplicate"] += 1
                else:
                    remaining.append(candidate)
            pending = remaining

    if set(renamed) & {poi_id for poi_id, reason in removed.items() if reason == "single_character_without_usable_address"}:
        raise AssertionError("A short-name row cannot be renamed and filtered")
    counts["renamed_survivors"] = sum(poi_id not in removed for poi_id in renamed)
    counts["output_rows"] = len(core_rows) - len(removed)
    return renamed, removed, duplicate_distance, counts


def build(output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output}")
    tables, source_rows = read_source()
    core_rows = source_rows["pois_core.parquet"]
    renamed, removed, duplicate_distance, counts = plan_decisions(core_rows)
    output.mkdir(parents=True, exist_ok=True)
    survivor_ids = {str(row["poi_id"]) for row in core_rows} - set(removed)
    core_before = {str(row["poi_id"]): str(row["name"]) for row in core_rows}

    output_rows: dict[str, list[dict[str, Any]]] = {}
    for name, rows in source_rows.items():
        filtered = [dict(row) for row in rows if str(row["poi_id"]) in survivor_ids]
        if name in {"pois_core.parquet", "pois.parquet"}:
            for row in filtered:
                poi_id = str(row["poi_id"])
                if poi_id in renamed:
                    row["name"] = renamed[poi_id]
                    row["aliases"] = [
                        alias for alias in (row.get("aliases") or [])
                        if not single_character(alias)
                    ]
        elif name == "search_documents.parquet":
            for row in filtered:
                poi_id = str(row["poi_id"])
                if poi_id not in renamed:
                    continue
                old, new = core_before[poi_id], renamed[poi_id]
                row["name"] = new
                row["aliases"] = [
                    alias for alias in (row.get("aliases") or [])
                    if not single_character(alias)
                ]
                for field in ("passage_address", "passage_context"):
                    before = str(row[field])
                    prefix = f"{old} |"
                    if not before.startswith(prefix):
                        raise ValueError(f"Unexpected passage form for {poi_id}: {field}")
                    row[field] = new + before[len(old):]
        output_rows[name] = filtered
        pq.write_table(
            pa.Table.from_pylist(filtered, schema=tables[name].schema), output / name
        )

    migration = []
    for row in core_rows:
        poi_id = str(row["poi_id"])
        if poi_id in removed:
            reason = removed[poi_id]
            if reason == "single_character_without_usable_address":
                action, canonical = "drop_short_name", None
            else:
                action, canonical = "merge_duplicate", reason
        elif poi_id in renamed:
            action, canonical = "rename_to_address", poi_id
        else:
            action, canonical = "keep", poi_id
        migration.append({
            "old_poi_id": poi_id,
            "canonical_poi_id": canonical,
            "action": action,
            "old_name": core_before[poi_id],
            "new_name": renamed.get(poi_id) if poi_id in renamed else (
                renamed.get(canonical, core_before[canonical])
                if canonical and canonical != poi_id else core_before[poi_id]
            ),
            "distance_to_canonical_m": duplicate_distance.get(poi_id),
            "reason": "same_name_address_lt_50m" if action == "merge_duplicate" else (
                "single_character_without_usable_address" if action == "drop_short_name" else None
            ),
        })
    pq.write_table(pa.Table.from_pylist(migration), output / "poi_id_migration.parquet")

    ordered_ids = [str(row["poi_id"]) for row in output_rows["pois_core.parquet"]]
    for name in ("search_documents.parquet", "pois_access_enrichment.parquet", "pois.parquet"):
        if [str(row["poi_id"]) for row in output_rows[name]] != ordered_ids:
            raise AssertionError(f"Output order mismatch: {name}")
    if {str(row["poi_id"]) for row in output_rows["poi_regions.parquet"]} - survivor_ids:
        raise AssertionError("Output regions contain removed IDs")
    if any(single_character(row["name"]) for row in output_rows["pois_core.parquet"]):
        raise AssertionError("Single-character name survived cleaning")
    for core, doc in zip(output_rows["pois_core.parquet"], output_rows["search_documents.parquet"]):
        if core["name"] != doc["name"]:
            raise AssertionError(f"Core/document name mismatch for {core['poi_id']}")

    schema_source = SOURCE / "schema_core.json"
    schema_target = output / "schema_core.json"
    schema_target.write_bytes(schema_source.read_bytes())
    source_hashes = {name: digest(SOURCE / name) for name in SOURCE_TABLES}
    source_hashes["schema_core.json"] = digest(schema_source)
    artifact_names = [*SOURCE_TABLES, "poi_id_migration.parquet", "schema_core.json"]
    manifest = {
        "corpus_version": VERSION,
        "status": "built_not_activated",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_corpus_version": "vn-poi-core-v1",
        "source_corpus_path": str(SOURCE),
        "builder": "tools/build_clean_poi_corpus_v2.py",
        "policy": {
            "single_character_name": "rename to housenumber + street/place when usable; otherwise drop",
            "usable_address": "housenumber present; street/place has >=3 alphanumeric characters and >=1 letter",
            "duplicate": "same folded final name, same normalized housenumber/street/province/subdistrict, distance to retained POI <50 m",
            "representative_priority": "preserved access point, named category, unchanged name, aliases, node, poi_id",
        },
        "counts": dict(counts),
        "source_hashes": source_hashes,
        "artifact_hashes": {name: digest(output / name) for name in artifact_names},
        "migration_actions": dict(Counter(row["action"] for row in migration)),
        "index_activation": "requires fresh embeddings and index; runtime remains on v1 until explicitly switched",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = [
        f"# {VERSION}",
        "",
        f"Source: `data/vietnam/poi_corpus_v1/` ({len(core_rows):,} POI).",
        f"Output: **{counts['output_rows']:,} POI**.",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    for action, count in manifest["migration_actions"].items():
        report.append(f"| {action} | {count:,} |")
    report += [
        "",
        "All removed IDs and retained representatives are recorded in `poi_id_migration.parquet`.",
        "The v1 corpus and live index were not modified. A new embedding matrix and index are required before activation.",
        "",
    ]
    (output / "cleaning_report.md").write_text("\n".join(report), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build(args.output.resolve())
    print(json.dumps({"corpus_version": manifest["corpus_version"], "counts": manifest["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
