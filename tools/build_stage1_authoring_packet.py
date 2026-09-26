"""Build compact POI authoring context without making an agent scan the corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from build_brand_groups_v1 import namespace_for
from query_brand_lookup_v2 import lookup_poi, lookup_text
from stage1_v6_common import (
    COMPOUND_PAIRS,
    CONTRACT_VERSION,
    DEFORMING_ERROR_TAGS,
    ERROR_TAGS,
    GENERATOR_VERSION,
    SCHEMA_COLUMNS,
    SLOT_SPECS,
    TRACE_COLUMNS,
    normalize_query,
    strip_diacritics,
)


PACKET_VERSION = "stage1_authoring_packet_v2"
MAX_COLLISION_IDS = 50
MAX_COLLISION_SAMPLES = 12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "as_py"):
        return json_value(value.as_py())
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value) if not isinstance(value, (str, bool)) else False:
        return None
    return value


def alias_values(value: Any) -> list[str]:
    cleaned = json_value(value)
    if not isinstance(cleaned, list):
        return []
    return [str(item).strip() for item in cleaned if str(item).strip()]


def accent_key(value: Any) -> str:
    return normalize_query(strip_diacritics(value))


def address_fields(value: Any) -> dict[str, Any]:
    address = json_value(value)
    return address if isinstance(address, dict) else {}


def verify_brand_lookup(lookup_dir: Path) -> dict[str, Any]:
    manifest_path = lookup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("lookup_version") != "brand_lookup_v2":
        raise RuntimeError("Authoring packet requires brand_lookup_v2")
    for name, metadata in manifest.get("artifacts", {}).items():
        path = lookup_dir / name
        if not path.is_file() or sha256_file(path) != metadata.get("sha256"):
            raise RuntimeError(f"Invalid brand lookup artifact: {name}")
    return manifest


def collision_payload(
    indices: set[int], corpus_rows: list[dict[str, Any]], target_poi_id: str
) -> dict[str, Any]:
    ordered = sorted(
        indices,
        key=lambda index: (
            str(corpus_rows[index]["poi_id"]) != target_poi_id,
            str(corpus_rows[index]["poi_id"]),
        ),
    )
    ids = [str(corpus_rows[index]["poi_id"]) for index in ordered]
    samples: list[dict[str, Any]] = []
    for index in ordered[:MAX_COLLISION_SAMPLES]:
        row = corpus_rows[index]
        address = address_fields(row.get("address"))
        samples.append(
            {
                "poi_id": str(row["poi_id"]),
                "name": json_value(row.get("name")),
                "brand": json_value(row.get("brand")),
                "ref": json_value(row.get("ref")),
                "category": json_value(row.get("category")),
                "housenumber": address.get("housenumber"),
                "street": address.get("street"),
                "subdistrict": address.get("subdistrict") or address.get("ward"),
                "province": address.get("province") or address.get("city"),
            }
        )
    return {
        "searchable_count": len(ordered),
        "candidate_poi_ids": ids if len(ids) <= MAX_COLLISION_IDS else ids[:MAX_COLLISION_IDS],
        "candidate_ids_truncated": len(ids) > MAX_COLLISION_IDS,
        "samples": samples,
    }


def build(
    target_path: Path,
    corpus_path: Path,
    brand_lookup_dir: Path,
    output_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    brand_manifest = verify_brand_lookup(brand_lookup_dir)
    targets = pd.read_parquet(target_path)
    corpus_columns = [
        "poi_id",
        "name",
        "aliases",
        "brand",
        "ref",
        "category",
        "address",
        "destination_searchable",
    ]
    corpus = pd.read_parquet(corpus_path, columns=corpus_columns)
    corpus = corpus[corpus["destination_searchable"]].reset_index(drop=True)
    corpus_rows = corpus.to_dict("records")
    corpus_by_id = {str(row["poi_id"]): row for row in corpus_rows}

    name_index: dict[str, set[int]] = defaultdict(set)
    accent_name_index: dict[str, set[int]] = defaultdict(set)
    alias_index: dict[str, set[int]] = defaultdict(set)
    ref_index: dict[str, set[int]] = defaultdict(set)
    for index, row in enumerate(corpus_rows):
        name_key = normalize_query(row.get("name"))
        if name_key:
            name_index[name_key].add(index)
            accent_name_index[accent_key(row.get("name"))].add(index)
        for alias in alias_values(row.get("aliases")):
            alias_index[normalize_query(alias)].add(index)
        ref_key = normalize_query(row.get("ref"))
        if ref_key:
            ref_index[ref_key].add(index)

    packet_rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(
        f"file:{(brand_lookup_dir / 'brand_lookup_v2.sqlite').as_posix()}?mode=ro",
        uri=True,
    )
    try:
        for target in targets.to_dict("records"):
            case_id = str(target["case_id"])
            poi_id = str(target["poi_id"])
            corpus_row = corpus_by_id.get(poi_id)
            official_name = str(target.get("name") or "").strip()
            name_key = normalize_query(official_name)
            exact_indices = set(name_index.get(name_key, set())) | set(
                alias_index.get(name_key, set())
            )
            accent_indices = set(
                accent_name_index.get(accent_key(official_name), set())
            )
            ref_key = normalize_query(target.get("ref"))
            ref_indices = set(ref_index.get(ref_key, set())) if ref_key else set()

            direct = lookup_poi(connection, poi_id)
            namespace = namespace_for(target.get("category"))
            brand_surface = str(target.get("brand") or official_name).strip()
            text_lookup = (
                lookup_text(connection, brand_surface, namespace)
                if brand_surface
                else {
                    "hits": [],
                    "review_alternatives": [],
                    "ambiguous": False,
                    "has_accepted_decision": False,
                }
            )

            accepted_memberships: list[dict[str, Any]] = []
            for membership in direct["accepted_memberships"]:
                family = next(
                    (
                        item
                        for item in direct["families"]
                        if item["brand_family_id"] == membership["brand_family_id"]
                    ),
                    {"usable_groups": []},
                )
                family_count = sum(
                    int(group["n_accepted"]) for group in family["usable_groups"]
                )
                accepted_memberships.append(
                    {
                        **membership,
                        "family_accepted_count": family_count,
                        "requires_branch_discriminator": family_count > 1,
                        "bare_brand_owner": "brand_dataset",
                    }
                )

            target_payload = {key: json_value(value) for key, value in target.items()}
            corpus_payload = None
            if corpus_row:
                corpus_payload = {
                    "name": json_value(corpus_row.get("name")),
                    "aliases": alias_values(corpus_row.get("aliases")),
                    "brand": json_value(corpus_row.get("brand")),
                    "ref": json_value(corpus_row.get("ref")),
                    "category": json_value(corpus_row.get("category")),
                    "address": address_fields(corpus_row.get("address")),
                }
            discriminator_candidates = [
                {"field": field, "value": target_payload.get(field)}
                for field in (
                    "ref",
                    "housenumber",
                    "street",
                    "subdistrict",
                    "province",
                )
                if target_payload.get(field) not in (None, "")
            ]
            packet_rows.append(
                {
                    "packet_version": PACKET_VERSION,
                    "case_id": case_id,
                    "poi_id": poi_id,
                    "target": target_payload,
                    "corpus_match": corpus_payload,
                    "corpus_poi_found": corpus_row is not None,
                    "discriminator_candidates": discriminator_candidates,
                    "collisions": {
                        "exact_name_or_alias": collision_payload(
                            exact_indices, corpus_rows, poi_id
                        ),
                        "accent_fold_name": collision_payload(
                            accent_indices, corpus_rows, poi_id
                        ),
                        "exact_ref": collision_payload(
                            ref_indices, corpus_rows, poi_id
                        ),
                    },
                    "brand_context": {
                        "accepted_memberships": accepted_memberships,
                        "review_memberships": direct["review_memberships"],
                        "excluded_memberships": direct["excluded_memberships"],
                        "accepted_text_hits": [
                            hit
                            for hit in text_lookup["hits"]
                            if hit["decision_status"] == "accepted"
                        ],
                        "review_alternatives": [
                            hit
                            for hit in text_lookup["hits"]
                            + text_lookup["review_alternatives"]
                            if hit["decision_status"] != "accepted"
                        ],
                        "surface_is_ambiguous": bool(text_lookup["ambiguous"]),
                        "policy": "Keep brand in POI queries only with a branch discriminator; bare-brand intent belongs to the brand dataset.",
                    },
                    "authoring_flags": {
                        "needs_target_review": not bool(target.get("clean_pass", True)),
                        "needs_brand_review": bool(
                            target.get("brand") and not accepted_memberships
                        ),
                        "avoid_full_corpus_scan": True,
                    },
                }
            )
    finally:
        connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in packet_rows),
        encoding="utf-8",
    )
    slot_contract = {
        slot: {
            **spec,
            "accepted_slot_tags": str(spec["slot_tag"]).split("|"),
        }
        for slot, spec in SLOT_SPECS.items()
    }
    manifest = {
        "packet_version": PACKET_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "row_count": len(packet_rows),
        "inputs": {
            "target": {"path": str(target_path), "sha256": sha256_file(target_path)},
            "corpus": {"path": str(corpus_path), "sha256": sha256_file(corpus_path)},
            "brand_lookup_manifest": {
                "path": str(brand_lookup_dir / "manifest.json"),
                "sha256": sha256_file(brand_lookup_dir / "manifest.json"),
                "lookup_version": brand_manifest["lookup_version"],
                "source_group_version": brand_manifest["group_version"],
            },
        },
        "output": {"path": str(output_path), "sha256": sha256_file(output_path)},
        "authoring_contract": {
            "row_schema_columns": list(SCHEMA_COLUMNS),
            "trace_schema_columns": list(TRACE_COLUMNS),
            "generator_version": GENERATOR_VERSION,
            "contract_version": CONTRACT_VERSION,
            "slot_specs": slot_contract,
            "language_tags": ["lang_vi", "lang_en", "lang_mixed"],
            "review_status_for_validation": "authored",
            "trace_reviewer_status": ["authored", "accepted"],
            "affected_spans_format": ["source text -> mutated text"],
            "error_tags": sorted(ERROR_TAGS),
            "deforming_error_tags": sorted(DEFORMING_ERROR_TAGS),
            "compound_pairs": sorted("+".join(sorted(pair)) for pair in COMPOUND_PAIRS),
            "controlled_coverage": {
                "slots": ["v03", "v04", "v05", "v06"],
                "mutation_points_min": 2,
                "mutation_points_preferred": [2, 3],
                "mutation_points_max": 4,
                "deforming_error_types_min": 2,
                "first_non_numeric_token_must_be_locally_deformed": True,
                "full_or_partial_diacritic_strip_does_not_count_as_deforming": True,
            },
        },
        "agent_read_policy": {
            "read_packet_rows_for_assigned_cases": True,
            "read_manifest_contract_once": True,
            "do_not_scan_full_corpus_per_poi": True,
            "targeted_corpus_fallback_only_for_flagged_cases": True,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--brand-lookup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        args.target,
        args.corpus,
        args.brand_lookup,
        args.output,
        args.manifest,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
