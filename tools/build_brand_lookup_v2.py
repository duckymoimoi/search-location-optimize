"""Build immutable brand_lookup_v2 from locked brand_groups_v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from build_brand_groups_v1 import GROUP_VERSION, match_key
from validate_brand_groups_v1 import validate


LOOKUP_VERSION = "brand_lookup_v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_counts(values: pd.Series) -> str:
    counts = values.value_counts().sort_index()
    return json.dumps(
        {str(key): int(value) for key, value in counts.items()},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build(release_dir: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty lookup: {output_dir}")
    source_report = validate(release_dir)
    if source_report["verdict"] != "PASS":
        raise ValueError(f"Source brand release failed: {source_report['errors']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)

    families = pd.read_parquet(release_dir / "brand_family_candidates_v1.parquet")
    members = pd.read_parquet(release_dir / "brand_group_members_v1.parquet")
    aliases = pd.read_parquet(release_dir / "brand_alias_candidates_v1.parquet")

    group_rows: list[dict[str, Any]] = []
    for (group_id, family_id, canonical, namespace), group in members.groupby(
        ["brand_group_id", "brand_family_id", "brand_canonical", "brand_namespace"],
        sort=True,
        dropna=False,
    ):
        accepted = int((group["membership_status"] == "accepted").sum())
        excluded = int((group["membership_status"] == "excluded").sum())
        if accepted >= 2:
            status = "accepted"
        elif excluded == len(group):
            status = "excluded"
        else:
            status = "needs_review"
        group_rows.append(
            {
                "brand_group_id": group_id,
                "brand_family_id": family_id,
                "brand_canonical": canonical,
                "brand_namespace": namespace,
                "n_members": len(group),
                "n_accepted": accepted,
                "n_needs_review": int(
                    (group["membership_status"] == "needs_review").sum()
                ),
                "n_excluded": excluded,
                "province_count": int(group["province_region_id"].dropna().nunique()),
                "evidence_distribution_json": json_counts(group["membership_evidence"]),
                "group_status": status,
                "group_version": GROUP_VERSION,
            }
        )
    groups = pd.DataFrame(group_rows)
    accepted_family_ids = set(
        groups.loc[groups["group_status"] == "accepted", "brand_family_id"]
    )
    excluded_family_ids = {
        family_id
        for family_id, group in groups.groupby("brand_family_id")
        if len(group) and (group["group_status"] == "excluded").all()
    }
    known_family_ids = set(
        families.loc[
            families["candidate_source"] == "explicit_brand", "brand_family_id"
        ]
    )

    def family_status(family_id: str) -> str:
        if family_id in accepted_family_ids:
            return "accepted"
        if family_id in excluded_family_ids:
            return "excluded"
        return "needs_review"

    match_rows: list[dict[str, Any]] = []
    for row in families.itertuples(index=False):
        family_id = str(row.brand_family_id)
        match_rows.append(
            {
                "lookup_key": str(row.brand_match_key),
                "lookup_fold": str(row.brand_fold),
                "lookup_text": str(row.brand_canonical),
                "brand_family_id": family_id,
                "match_source": "canonical",
                "match_status": family_status(family_id),
                "source_poi_count": int(row.n_source_pois),
                "lookup_version": LOOKUP_VERSION,
            }
        )
    for row in aliases.itertuples(index=False):
        family_id = str(row.brand_family_id)
        if family_id not in known_family_ids:
            continue
        match_rows.append(
            {
                "lookup_key": match_key(row.alias_text),
                "lookup_fold": str(row.alias_fold),
                "lookup_text": str(row.alias_text),
                "brand_family_id": family_id,
                "match_source": "alias_candidate",
                "match_status": "needs_review",
                "source_poi_count": int(row.source_poi_count),
                "lookup_version": LOOKUP_VERSION,
            }
        )
    match_index = (
        pd.DataFrame(match_rows)
        .drop_duplicates(["lookup_key", "brand_family_id", "match_source"])
        .sort_values(["lookup_key", "brand_family_id", "match_source"])
        .reset_index(drop=True)
    )

    match_path = output_dir / "brand_match_index_v2.parquet"
    groups_path = output_dir / "brand_group_summary_v2.parquet"
    pq.write_table(
        pa.Table.from_pandas(match_index, preserve_index=False),
        match_path,
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pandas(groups, preserve_index=False),
        groups_path,
        compression="zstd",
    )

    db_path = output_dir / "brand_lookup_v2.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        families.to_sql("brand_families", connection, index=False, if_exists="replace")
        groups.to_sql("brand_groups", connection, index=False, if_exists="replace")
        members.to_sql("brand_members", connection, index=False, if_exists="replace")
        aliases.to_sql("brand_aliases", connection, index=False, if_exists="replace")
        match_index.to_sql(
            "brand_match_index", connection, index=False, if_exists="replace"
        )
        for statement in (
            "CREATE INDEX idx_match_key ON brand_match_index(lookup_key)",
            "CREATE INDEX idx_match_fold ON brand_match_index(lookup_fold)",
            "CREATE INDEX idx_match_family ON brand_match_index(brand_family_id)",
            "CREATE INDEX idx_family_id ON brand_families(brand_family_id)",
            "CREATE INDEX idx_group_family ON brand_groups(brand_family_id)",
            "CREATE INDEX idx_group_namespace ON brand_groups(brand_namespace)",
            "CREATE INDEX idx_member_poi ON brand_members(poi_id)",
            "CREATE INDEX idx_member_group_status ON brand_members(brand_group_id, membership_status)",
            "CREATE INDEX idx_alias_fold ON brand_aliases(alias_fold)",
        ):
            connection.execute(statement)
        connection.execute(
            "CREATE TABLE lookup_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        metadata = {
            "lookup_version": LOOKUP_VERSION,
            "group_version": GROUP_VERSION,
            "source_manifest_sha256": sha256_file(release_dir / "manifest.json"),
            "created_at_utc": datetime.now(UTC).isoformat(),
        }
        connection.executemany(
            "INSERT INTO lookup_metadata(key, value) VALUES (?, ?)", metadata.items()
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    completed = datetime.now(UTC)
    artifacts = [db_path, match_path, groups_path]
    manifest = {
        "dataset": "stage1_brand_lookup_v2",
        "lookup_version": LOOKUP_VERSION,
        "group_version": GROUP_VERSION,
        "status": "LOCKED",
        "created_at_utc": completed.isoformat(),
        "elapsed_seconds": round((completed - started).total_seconds(), 3),
        "source_release": str(release_dir),
        "source_manifest_sha256": sha256_file(release_dir / "manifest.json"),
        "stats": {
            "families": len(families),
            "known_explicit_families": len(known_family_ids),
            "groups": len(groups),
            "accepted_groups": int((groups["group_status"] == "accepted").sum()),
            "excluded_groups": int((groups["group_status"] == "excluded").sum()),
            "members": len(members),
            "match_keys": len(match_index),
            "accepted_match_rows": int(
                (match_index["match_status"] == "accepted").sum()
            ),
            "alias_candidates": len(aliases),
        },
        "artifacts": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in artifacts
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "LOCKED.json").write_text(
        json.dumps(
            {
                "lookup_version": LOOKUP_VERSION,
                "locked_at_utc": completed.isoformat(),
                "manifest_sha256": sha256_file(manifest_path),
                "mutation_policy": "Do not edit in place; rebuild as brand_lookup_v3.",
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
    parser.add_argument("--brand-release", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.brand_release, args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
