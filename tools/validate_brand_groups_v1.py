"""Validate a locked brand_groups_v1 membership release without modifying it."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


GROUP_VERSION = "brand_groups_v1"
NAMESPACES = {
    "fuel",
    "bank",
    "atm",
    "cafe",
    "restaurant",
    "convenience_store",
    "supermarket",
    "pharmacy",
    "hotel",
    "retail",
    "other_reviewed",
}
MEMBER_COLUMNS = {
    "brand_family_id",
    "brand_group_id",
    "brand_canonical",
    "brand_fold",
    "brand_namespace",
    "poi_id",
    "destination_searchable",
    "province_region_id",
    "subdistrict_region_id",
    "membership_status",
    "membership_evidence",
    "evidence_text",
    "group_version",
    "review_status",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return " ".join(text.split())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(release_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "brand_group_members_v1.parquet",
        "brand_family_candidates_v1.parquet",
        "brand_alias_candidates_v1.parquet",
        "brand_family_review_overrides_v1.csv",
        "top_multibranch_review_v1.csv",
        "audit_report.json",
        "manifest.json",
        "LOCKED.json",
    }
    missing = sorted(name for name in required if not (release_dir / name).is_file())
    if missing:
        return {"verdict": "FAIL", "errors": [f"missing files: {missing}"], "warnings": []}

    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads((release_dir / "LOCKED.json").read_text(encoding="utf-8"))
    if manifest.get("group_version") != GROUP_VERSION or manifest.get("status") != "LOCKED":
        errors.append("manifest version/status mismatch")
    if lock.get("group_version") != GROUP_VERSION:
        errors.append("lock version mismatch")
    if lock.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("lock manifest hash mismatch")
    for name, metadata in manifest.get("artifacts", {}).items():
        path = release_dir / name
        if not path.is_file():
            errors.append(f"manifest artifact missing: {name}")
            continue
        if metadata.get("sha256") != sha256_file(path):
            errors.append(f"artifact hash mismatch: {name}")
        if metadata.get("bytes") != path.stat().st_size:
            errors.append(f"artifact size mismatch: {name}")

    members_path = release_dir / "brand_group_members_v1.parquet"
    schema_names = set(pq.read_schema(members_path).names)
    if schema_names != MEMBER_COLUMNS:
        errors.append(
            f"membership schema mismatch missing={sorted(MEMBER_COLUMNS-schema_names)} "
            f"extra={sorted(schema_names-MEMBER_COLUMNS)}"
        )
    members = pd.read_parquet(members_path)
    if members.duplicated(["brand_group_id", "poi_id"]).any():
        errors.append("duplicate brand_group_id + poi_id")
    if not set(members["brand_namespace"]).issubset(NAMESPACES):
        errors.append("unknown namespace")
    if set(members["membership_status"]) - {"accepted", "needs_review", "excluded"}:
        errors.append("unknown membership_status")
    if set(members["review_status"]) - {"authored", "accepted", "needs_review"}:
        errors.append("unknown review_status")
    if (members["group_version"] != GROUP_VERSION).any():
        errors.append("wrong membership group_version")
    if not (
        members["brand_group_id"]
        == members["brand_family_id"] + ":" + members["brand_namespace"]
    ).all():
        errors.append("brand_group_id is not family + namespace")
    if not (
        members["brand_fold"] == members["brand_canonical"].map(normalize_text)
    ).all():
        errors.append("brand_fold mismatch")
    accepted = members[members["membership_status"] == "accepted"]
    if not accepted["destination_searchable"].all():
        errors.append("accepted non-searchable member")
    if (accepted["review_status"] == "needs_review").any():
        errors.append("accepted membership still has needs_review review_status")
    if (accepted["brand_namespace"] == "other_reviewed").any():
        errors.append("other_reviewed membership cannot be accepted in v1")
    accepted_group_sizes = accepted.groupby("brand_group_id").size()
    if (accepted_group_sizes < 2).any():
        errors.append("accepted group has fewer than two accepted members")

    families = pd.read_parquet(release_dir / "brand_family_candidates_v1.parquet")
    if (families["group_version"] != GROUP_VERSION).any():
        errors.append("wrong family candidate group_version")
    known_families = set(families.loc[families["candidate_source"] == "explicit_brand", "brand_family_id"])
    if not set(members["brand_family_id"]).issubset(known_families):
        errors.append("membership references non-explicit candidate family")

    audit = json.loads((release_dir / "audit_report.json").read_text(encoding="utf-8"))
    if audit.get("verdict") != "PASS":
        errors.append("embedded audit did not PASS")
    manifest_stats = manifest.get("stats", {})
    if manifest_stats.get("membership_rows") != len(members):
        errors.append("manifest membership row count mismatch")
    if manifest_stats.get("accepted_members") != len(accepted):
        errors.append("manifest accepted row count mismatch")

    review_groups = members[members["membership_status"] == "needs_review"].groupby(
        "brand_group_id"
    ).size()
    if len(review_groups):
        warnings.append(f"{len(review_groups)} groups retain needs_review members")
    return {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "membership_rows": len(members),
            "accepted_members": len(accepted),
            "accepted_groups": int(accepted["brand_group_id"].nunique()),
            "needs_review_members": int((members["membership_status"] == "needs_review").sum()),
            "excluded_members": int((members["membership_status"] == "excluded").sum()),
            "known_families": len(known_families),
            "family_candidate_rows": len(families),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.release_dir)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
