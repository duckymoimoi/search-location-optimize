"""Validate the corpus-v3 brand membership view."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from stage1_brand_v3_common import (
    CORPUS_V3,
    MEMBERSHIP_V3,
    MEMBERSHIP_VIEW_VERSION,
    load_v3_core,
    sha256_file,
    write_json,
)


REQUIRED_COLUMNS = {
    "brand_family_id",
    "brand_group_id",
    "brand_canonical",
    "brand_fold",
    "brand_namespace",
    "poi_id",
    "source_poi_id",
    "mapped_poi_id",
    "mapping_action",
    "mapping_evidence",
    "destination_searchable",
    "membership_status",
    "group_version",
}


def validate(release_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "brand_group_members_v3.parquet",
        "composed_poi_id_migration_v1_v3.parquet",
        "id_migration_audit.json",
        "missing_id_adjudication.json",
        "gold_poi_overlap.json",
        "manifest.json",
        "LOCKED.json",
    }
    missing = sorted(name for name in required if not (release_dir / name).is_file())
    if missing:
        return {"verdict": "FAIL", "errors": [f"missing files: {missing}"], "warnings": []}

    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((release_dir / "LOCKED.json").read_text(encoding="utf-8"))
    if sha256_file(release_dir / "manifest.json") != lock.get("manifest_sha256"):
        errors.append("LOCKED.json manifest_sha256 mismatch")
    if manifest.get("membership_view_version") != MEMBERSHIP_VIEW_VERSION:
        errors.append("unexpected membership_view_version")

    members = pd.read_parquet(release_dir / "brand_group_members_v3.parquet")
    missing_cols = sorted(REQUIRED_COLUMNS - set(members.columns))
    if missing_cols:
        errors.append(f"missing columns: {missing_cols}")
        return {"verdict": "FAIL", "errors": errors, "warnings": warnings}

    core = load_v3_core()
    v3_ids = set(core["poi_id"].astype(str))
    searchable = set(
        core.loc[core["destination_searchable"] == True, "poi_id"].astype(str)
    )
    accepted = members[members["membership_status"] == "accepted"]
    if accepted.empty:
        errors.append("no accepted members")
    accepted_ids = set(accepted["poi_id"].astype(str))
    missing_ids = sorted(accepted_ids - v3_ids)
    if missing_ids:
        errors.append(f"{len(missing_ids)} accepted IDs missing from corpus v3")
    not_searchable = sorted(accepted_ids - searchable)
    if not_searchable:
        errors.append(f"{len(not_searchable)} accepted IDs are not destination_searchable")
    if not (accepted["poi_id"] == accepted["mapped_poi_id"]).all():
        errors.append("accepted poi_id must equal mapped_poi_id")
    if accepted["membership_status"].eq("accepted").any() and (
        accepted["mapping_action"] == "dropped_no_successor"
    ).any():
        errors.append("dropped IDs must not enter the accepted pool")

    review_as_positive = members[
        (members["membership_status"] != "accepted")
        & (members["poi_id"].isin(accepted_ids))
    ]
    # same dest can have review status on a different source; not an error
    adjudication = json.loads(
        (release_dir / "missing_id_adjudication.json").read_text(encoding="utf-8")
    )
    if not adjudication.get("rows"):
        warnings.append("no dropped accepted IDs recorded")
    for row in adjudication.get("rows", []):
        if row.get("decision") != "dropped_no_successor":
            errors.append(f"unadjudicated missing ID: {row}")
        if row.get("source_poi_id") in accepted_ids:
            errors.append(f"dropped ID still in accepted pool: {row['source_poi_id']}")

    audit = json.loads((release_dir / "id_migration_audit.json").read_text(encoding="utf-8"))
    if int(audit.get("queries_losing_all_positives_without_remap", -1)) != 0:
        warnings.append("audit reports queries that lose all positives without remap")

    overlap = json.loads((release_dir / "gold_poi_overlap.json").read_text(encoding="utf-8"))
    if overlap.get("extra_entity_equivalent_accepted"):
        warnings.append("gold entity-equivalent extras present in accepted pool")

    report = {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "membership_rows": int(len(members)),
            "accepted_rows": int(len(accepted)),
            "accepted_unique_poi": int(accepted["poi_id"].nunique()),
            "accepted_families": int(accepted["brand_family_id"].nunique()),
            "dropped_adjudicated": len(adjudication.get("rows", [])),
            "gold_overlap": int(overlap.get("n_overlap_v3_ids", 0)),
            "corpus_v3_rows": int(len(v3_ids)),
            "corpus_path": str((CORPUS_V3 / "pois_core.parquet").as_posix()),
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.release_dir)
    target = args.report or (args.release_dir / "validation_report.json")
    write_json(target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
