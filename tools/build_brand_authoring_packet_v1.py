"""Build a deterministic brand-query authoring packet from locked releases.

The packet never generates ``query_text``.  It emits exactly one row per
accepted brand family + namespace group, with source identity, alias review
state, and the complete accepted positive pool needed for later qrels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from validate_brand_groups_v1 import validate as validate_brand_release
from validate_brand_lookup_v2 import validate as validate_brand_lookup


PACKET_VERSION = "brand_authoring_packet_v1"
GROUP_VERSION = "brand_groups_v1"
LOOKUP_VERSION = "brand_lookup_v2"
DEFAULT_ALIAS_REVIEW_LIMIT = 20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _positive_pool_hash(poi_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(poi_ids) + "\n").encode()).hexdigest()


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _alias_payload(
    aliases: pd.DataFrame,
    family_id: str,
    canonical: str,
    review_limit: int,
) -> tuple[list[str], dict[str, Any]]:
    family_aliases = aliases[aliases["brand_family_id"] == family_id].copy()
    canonical_fold = " ".join(canonical.casefold().split())
    accepted = sorted(
        {
            str(row.alias_text).strip()
            for row in family_aliases.itertuples(index=False)
            if str(row.candidate_status) == "accepted"
            and " ".join(str(row.alias_text).casefold().split()) != canonical_fold
        },
        key=lambda value: value.casefold(),
    )
    review = family_aliases[family_aliases["candidate_status"] == "needs_review"]
    review = review.sort_values(
        ["source_poi_count", "alias_fold", "alias_text"],
        ascending=[False, True, True],
        kind="stable",
    )
    rows = [
        {
            "alias_text": str(row.alias_text),
            "source_poi_count": int(row.source_poi_count),
            "review_reason": str(row.review_reason),
        }
        for row in review.head(review_limit).itertuples(index=False)
    ]
    return accepted, {
        "candidate_count": int(len(review)),
        "sample": rows,
        "sample_truncated": len(review) > review_limit,
        "usage": "review_only_do_not_author_until_adjudicated",
    }


def build(
    brand_release: Path,
    brand_lookup: Path,
    output_dir: Path,
    *,
    alias_review_limit: int = DEFAULT_ALIAS_REVIEW_LIMIT,
) -> dict[str, Any]:
    if alias_review_limit < 0:
        raise ValueError("alias_review_limit must be non-negative")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output: {output_dir}")

    release_report = validate_brand_release(brand_release)
    if release_report["verdict"] != "PASS":
        raise ValueError(f"Brand release failed validation: {release_report['errors']}")
    lookup_report = validate_brand_lookup(brand_lookup, brand_release)
    if lookup_report["verdict"] != "PASS":
        raise ValueError(f"Brand lookup failed validation: {lookup_report['errors']}")

    release_manifest_path = brand_release / "manifest.json"
    lookup_manifest_path = brand_lookup / "manifest.json"
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    lookup_manifest = json.loads(lookup_manifest_path.read_text(encoding="utf-8"))
    if release_manifest.get("group_version") != GROUP_VERSION:
        raise ValueError("Unexpected brand group version")
    if lookup_manifest.get("lookup_version") != LOOKUP_VERSION:
        raise ValueError("Unexpected brand lookup version")

    members = pd.read_parquet(brand_release / "brand_group_members_v1.parquet")
    aliases = pd.read_parquet(brand_release / "brand_alias_candidates_v1.parquet")
    lookup_groups = pd.read_parquet(brand_lookup / "brand_group_summary_v2.parquet")

    accepted = members[
        (members["membership_status"] == "accepted")
        & members["destination_searchable"]
    ].copy()
    accepted_group_ids = set(accepted["brand_group_id"].astype(str))
    lookup_accepted_ids = set(
        lookup_groups.loc[
            lookup_groups["group_status"] == "accepted", "brand_group_id"
        ].astype(str)
    )
    if accepted_group_ids != lookup_accepted_ids:
        raise ValueError("Accepted group mismatch between membership and lookup releases")

    family_namespaces: dict[str, list[str]] = defaultdict(list)
    for row in (
        accepted[["brand_family_id", "brand_namespace"]]
        .drop_duplicates()
        .sort_values(["brand_family_id", "brand_namespace"])
        .itertuples(index=False)
    ):
        family_namespaces[str(row.brand_family_id)].append(str(row.brand_namespace))

    packet_rows: list[dict[str, Any]] = []
    for group_id, group in accepted.groupby("brand_group_id", sort=True):
        family_ids = sorted(set(group["brand_family_id"].astype(str)))
        canonicals = sorted(set(group["brand_canonical"].astype(str)))
        folds = sorted(set(group["brand_fold"].astype(str)))
        namespaces = sorted(set(group["brand_namespace"].astype(str)))
        if not (
            len(family_ids) == len(canonicals) == len(folds) == len(namespaces) == 1
        ):
            raise ValueError(f"Inconsistent identity fields for {group_id}")
        family_id = family_ids[0]
        canonical = canonicals[0]
        namespace = namespaces[0]
        positive_ids = sorted(set(group["poi_id"].astype(str)))
        if len(positive_ids) != len(group):
            raise ValueError(f"Duplicate accepted member in {group_id}")
        siblings = sorted(family_namespaces[family_id])
        verified_aliases, alias_review = _alias_payload(
            aliases, family_id, canonical, alias_review_limit
        )
        evidence_counts = Counter(group["membership_evidence"].astype(str))
        review_counts = Counter(group["review_status"].astype(str))
        packet_rows.append(
            {
                "packet_version": PACKET_VERSION,
                "intent_id": str(group_id),
                "intent_scope": "BRAND",
                "qrel_policy": "FAMILY_NAMESPACE",
                "brand_family_id": family_id,
                "brand_group_id": str(group_id),
                "brand_canonical": canonical,
                "brand_fold": folds[0],
                "brand_namespace": namespace,
                "namespace_scope": [namespace],
                "accepted_sibling_namespaces": siblings,
                "requires_namespace_token": len(siblings) > 1,
                "bare_brand_scope_hint": (
                    "needs_family_policy_review"
                    if len(siblings) > 1
                    else "single_namespace_family"
                ),
                "verified_aliases": verified_aliases,
                "alias_review": alias_review,
                "positive_poi_ids": positive_ids,
                "n_positive": len(positive_ids),
                "positive_pool_sha256": _positive_pool_hash(positive_ids),
                "membership_evidence_counts": dict(sorted(evidence_counts.items())),
                "membership_review_counts": dict(sorted(review_counts.items())),
                "province_count": int(group["province_region_id"].dropna().nunique()),
                "group_version": GROUP_VERSION,
                "lookup_version": LOOKUP_VERSION,
                "authoring_status": "ready",
            }
        )

    expected_keys = {
        (str(row.brand_family_id), str(row.brand_namespace))
        for row in accepted[["brand_family_id", "brand_namespace"]]
        .drop_duplicates()
        .itertuples(index=False)
    }
    packet_keys = {
        (row["brand_family_id"], row["brand_namespace"]) for row in packet_rows
    }
    if packet_keys != expected_keys or len(packet_keys) != len(packet_rows):
        raise ValueError("Packet must contain exactly one row per family + namespace")
    if sum(row["n_positive"] for row in packet_rows) != len(accepted):
        raise ValueError("Packet positive pools do not cover accepted membership exactly once")
    if any(not row["positive_poi_ids"] for row in packet_rows):
        raise ValueError("Packet row has an empty positive pool")

    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "brand_authoring_packet_v1.jsonl"
    manifest_path = output_dir / "authoring_packet_manifest_v1.json"
    with packet_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in packet_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    family_count = len({row["brand_family_id"] for row in packet_rows})
    multi_namespace_families = len(
        {
            row["brand_family_id"]
            for row in packet_rows
            if row["requires_namespace_token"]
        }
    )
    accepted_family_ids = {row["brand_family_id"] for row in packet_rows}
    unique_alias_review_candidates = int(
        len(
            aliases[
                aliases["brand_family_id"].astype(str).isin(accepted_family_ids)
                & (aliases["candidate_status"] == "needs_review")
            ]
        )
    )
    alias_review_references = int(
        sum(row["alias_review"]["candidate_count"] for row in packet_rows)
    )
    manifest = {
        "dataset": "train_stage1_brand_queries_v1_authoring_packet",
        "packet_version": PACKET_VERSION,
        "status": "READY_FOR_AUTHORING",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "sources": {
            "brand_release_manifest": _source_record(release_manifest_path),
            "brand_lookup_manifest": _source_record(lookup_manifest_path),
            "membership": _source_record(
                brand_release / "brand_group_members_v1.parquet"
            ),
            "aliases": _source_record(
                brand_release / "brand_alias_candidates_v1.parquet"
            ),
        },
        "output": _source_record(packet_path),
        "stats": {
            "packet_rows": len(packet_rows),
            "brand_families": family_count,
            "accepted_namespace_groups": len(packet_rows),
            "positive_members": sum(row["n_positive"] for row in packet_rows),
            "max_positive_pool": max(row["n_positive"] for row in packet_rows),
            "multi_namespace_families": multi_namespace_families,
            "rows_with_verified_aliases": sum(
                bool(row["verified_aliases"]) for row in packet_rows
            ),
            "unique_alias_review_candidates": unique_alias_review_candidates,
            "alias_review_candidate_references": alias_review_references,
        },
        "authoring_contract": {
            "one_row_per": ["brand_family_id", "brand_namespace"],
            "query_text_generated": False,
            "positive_pool": "accepted + destination_searchable members only",
            "alias_policy": (
                "verified_aliases may be authored; alias_review.sample is review-only"
            ),
            "multi_namespace_policy": (
                "requires_namespace_token=true forbids assigning bare brand to one namespace"
            ),
            "required_references": [
                ".cursor/skills/search20-stage1-brand-queries/references/query-contract.md",
                ".cursor/skills/search20-stage1-brand-queries/references/integration.md",
            ],
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "LOCKED.json").write_text(
        json.dumps(
            {
                "packet_version": PACKET_VERSION,
                "locked_at_utc": datetime.now(UTC).isoformat(),
                "manifest_sha256": sha256_file(manifest_path),
                "mutation_policy": "Do not edit packet in place; rebuild from locked sources.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--brand-release",
        type=Path,
        default=Path("data/vietnam/train_stage1_brand_v1"),
    )
    parser.add_argument(
        "--brand-lookup",
        type=Path,
        default=Path("data/vietnam/train_stage1_brand_lookup_v2"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/vietnam/train_stage1_brand_queries_v1"),
    )
    parser.add_argument(
        "--alias-review-limit", type=int, default=DEFAULT_ALIAS_REVIEW_LIMIT
    )
    args = parser.parse_args()
    manifest = build(
        args.brand_release,
        args.brand_lookup,
        args.output_dir,
        alias_review_limit=args.alias_review_limit,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
