"""Validate a brand_authoring_packet_v1 against its locked source release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from build_brand_authoring_packet_v1 import (
    GROUP_VERSION,
    LOOKUP_VERSION,
    PACKET_VERSION,
    _positive_pool_hash,
    sha256_file,
)
from validate_brand_groups_v1 import validate as validate_brand_release
from validate_brand_lookup_v2 import validate as validate_brand_lookup


REQUIRED_ROW_FIELDS = {
    "packet_version",
    "intent_id",
    "intent_scope",
    "qrel_policy",
    "brand_family_id",
    "brand_group_id",
    "brand_canonical",
    "brand_fold",
    "brand_namespace",
    "namespace_scope",
    "accepted_sibling_namespaces",
    "requires_namespace_token",
    "bare_brand_scope_hint",
    "verified_aliases",
    "alias_review",
    "positive_poi_ids",
    "n_positive",
    "positive_pool_sha256",
    "membership_evidence_counts",
    "membership_review_counts",
    "province_count",
    "group_version",
    "lookup_version",
    "authoring_status",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} is not an object")
            rows.append(value)
    return rows


def validate(
    packet_dir: Path, brand_release: Path, brand_lookup: Path
) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "brand_authoring_packet_v1.jsonl",
        "authoring_packet_manifest_v1.json",
        "LOCKED.json",
    }
    missing = sorted(name for name in required if not (packet_dir / name).is_file())
    if missing:
        return {"verdict": "FAIL", "errors": [f"missing files: {missing}"]}

    release_report = validate_brand_release(brand_release)
    lookup_report = validate_brand_lookup(brand_lookup, brand_release)
    if release_report["verdict"] != "PASS":
        errors.append("source brand release failed validation")
    if lookup_report["verdict"] != "PASS":
        errors.append("source brand lookup failed validation")

    packet_path = packet_dir / "brand_authoring_packet_v1.jsonl"
    manifest_path = packet_dir / "authoring_packet_manifest_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads((packet_dir / "LOCKED.json").read_text(encoding="utf-8"))
    rows = _read_jsonl(packet_path)

    if manifest.get("packet_version") != PACKET_VERSION:
        errors.append("manifest packet version mismatch")
    if manifest.get("status") != "READY_FOR_AUTHORING":
        errors.append("manifest status mismatch")
    if lock.get("packet_version") != PACKET_VERSION:
        errors.append("lock packet version mismatch")
    if lock.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("lock manifest hash mismatch")
    output_meta = manifest.get("output", {})
    if output_meta.get("sha256") != sha256_file(packet_path):
        errors.append("packet hash mismatch")
    if output_meta.get("bytes") != packet_path.stat().st_size:
        errors.append("packet byte count mismatch")
    source_manifest = brand_release / "manifest.json"
    lookup_manifest = brand_lookup / "manifest.json"
    sources = manifest.get("sources", {})
    if sources.get("brand_release_manifest", {}).get("sha256") != sha256_file(
        source_manifest
    ):
        errors.append("source brand manifest hash mismatch")
    if sources.get("brand_lookup_manifest", {}).get("sha256") != sha256_file(
        lookup_manifest
    ):
        errors.append("source lookup manifest hash mismatch")

    members = pd.read_parquet(brand_release / "brand_group_members_v1.parquet")
    accepted = members[
        (members["membership_status"] == "accepted")
        & members["destination_searchable"]
    ].copy()
    expected_pools = {
        str(group_id): sorted(set(group["poi_id"].astype(str)))
        for group_id, group in accepted.groupby("brand_group_id", sort=True)
    }
    expected_keys = {
        (str(row.brand_family_id), str(row.brand_namespace))
        for row in accepted[["brand_family_id", "brand_namespace"]]
        .drop_duplicates()
        .itertuples(index=False)
    }

    seen_groups: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    positive_references = 0
    for index, row in enumerate(rows, start=1):
        missing_fields = sorted(REQUIRED_ROW_FIELDS - set(row))
        if missing_fields:
            errors.append(f"row {index} missing fields: {missing_fields}")
            continue
        group_id = str(row["brand_group_id"])
        family_id = str(row["brand_family_id"])
        namespace = str(row["brand_namespace"])
        key = (family_id, namespace)
        if group_id in seen_groups:
            errors.append(f"duplicate group row: {group_id}")
        if key in seen_keys:
            errors.append(f"duplicate family + namespace row: {key}")
        seen_groups.add(group_id)
        seen_keys.add(key)
        if group_id != f"{family_id}:{namespace}":
            errors.append(f"group identity mismatch: {group_id}")
        if row["packet_version"] != PACKET_VERSION:
            errors.append(f"wrong packet version: {group_id}")
        if row["group_version"] != GROUP_VERSION:
            errors.append(f"wrong group version: {group_id}")
        if row["lookup_version"] != LOOKUP_VERSION:
            errors.append(f"wrong lookup version: {group_id}")
        if row["intent_id"] != group_id or row["intent_scope"] != "BRAND":
            errors.append(f"wrong intent identity: {group_id}")
        if row["qrel_policy"] != "FAMILY_NAMESPACE":
            errors.append(f"wrong qrel policy: {group_id}")
        if row["namespace_scope"] != [namespace]:
            errors.append(f"wrong namespace scope: {group_id}")
        pool = [str(value) for value in row["positive_poi_ids"]]
        if pool != sorted(set(pool)):
            errors.append(f"positive pool must be sorted and unique: {group_id}")
        if pool != expected_pools.get(group_id):
            errors.append(f"positive pool differs from accepted membership: {group_id}")
        if row["n_positive"] != len(pool) or not pool:
            errors.append(f"positive count mismatch/empty: {group_id}")
        if row["positive_pool_sha256"] != _positive_pool_hash(pool):
            errors.append(f"positive pool hash mismatch: {group_id}")
        if not isinstance(row["verified_aliases"], list):
            errors.append(f"verified_aliases must be a list: {group_id}")
        if row["alias_review"].get("usage") != (
            "review_only_do_not_author_until_adjudicated"
        ):
            errors.append(f"alias review usage missing: {group_id}")
        positive_references += len(pool)

    if seen_groups != set(expected_pools):
        errors.append("packet group set differs from accepted membership groups")
    if seen_keys != expected_keys:
        errors.append("packet family + namespace keys differ from accepted membership")
    stats = manifest.get("stats", {})
    expected_stats = {
        "packet_rows": len(rows),
        "accepted_namespace_groups": len(expected_pools),
        "positive_members": len(accepted),
    }
    for key, value in expected_stats.items():
        if stats.get(key) != value:
            errors.append(f"manifest count mismatch: {key}")
    if positive_references != len(accepted):
        errors.append("positive pool references do not cover accepted membership once")

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "stats": {
            "packet_rows": len(rows),
            "brand_families": len({row.get("brand_family_id") for row in rows}),
            "positive_members": positive_references,
            "verified_alias_rows": sum(bool(row.get("verified_aliases")) for row in rows),
            "multi_namespace_rows": sum(
                bool(row.get("requires_namespace_token")) for row in rows
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--brand-release", type=Path, required=True)
    parser.add_argument("--brand-lookup", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.packet_dir, args.brand_release, args.brand_lookup)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
