"""Validate locked brand_lookup_v2 and its source binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(release_dir: Path, brand_release: Path) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "brand_lookup_v2.sqlite",
        "brand_match_index_v2.parquet",
        "brand_group_summary_v2.parquet",
        "manifest.json",
        "LOCKED.json",
    }
    missing = sorted(name for name in required if not (release_dir / name).is_file())
    if missing:
        return {"verdict": "FAIL", "errors": [f"missing files: {missing}"]}
    manifest_path = release_dir / "manifest.json"
    source_manifest_path = brand_release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads((release_dir / "LOCKED.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "LOCKED" or manifest.get("lookup_version") != "brand_lookup_v2":
        errors.append("manifest status/version mismatch")
    if lock.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("lock manifest hash mismatch")
    if manifest.get("source_manifest_sha256") != sha256_file(source_manifest_path):
        errors.append("source brand release hash mismatch")
    for name, metadata in manifest.get("artifacts", {}).items():
        path = release_dir / name
        if not path.is_file() or sha256_file(path) != metadata.get("sha256"):
            errors.append(f"artifact hash mismatch: {name}")
        elif path.stat().st_size != metadata.get("bytes"):
            errors.append(f"artifact size mismatch: {name}")

    db_path = release_dir / "brand_lookup_v2.sqlite"
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            errors.append("sqlite integrity_check failed")
        metadata = dict(connection.execute("SELECT key, value FROM lookup_metadata"))
        if metadata.get("lookup_version") != "brand_lookup_v2":
            errors.append("sqlite lookup version mismatch")
        counts = {
            "families": connection.execute("SELECT COUNT(*) FROM brand_families").fetchone()[0],
            "groups": connection.execute("SELECT COUNT(*) FROM brand_groups").fetchone()[0],
            "members": connection.execute("SELECT COUNT(*) FROM brand_members").fetchone()[0],
            "match_keys": connection.execute("SELECT COUNT(*) FROM brand_match_index").fetchone()[0],
            "alias_candidates": connection.execute("SELECT COUNT(*) FROM brand_aliases").fetchone()[0],
            "accepted_groups": connection.execute(
                "SELECT COUNT(*) FROM brand_groups WHERE group_status = 'accepted'"
            ).fetchone()[0],
            "excluded_groups": connection.execute(
                "SELECT COUNT(*) FROM brand_groups WHERE group_status = 'excluded'"
            ).fetchone()[0],
            "accepted_match_rows": connection.execute(
                "SELECT COUNT(*) FROM brand_match_index WHERE match_status = 'accepted'"
            ).fetchone()[0],
        }
        for key, value in counts.items():
            if manifest.get("stats", {}).get(key) != value:
                errors.append(f"manifest count mismatch: {key}")
        if connection.execute(
            "SELECT COUNT(*) FROM (SELECT lookup_key, brand_family_id, match_source, COUNT(*) n "
            "FROM brand_match_index GROUP BY lookup_key, brand_family_id, match_source HAVING n > 1)"
        ).fetchone()[0]:
            errors.append("duplicate lookup key/family/source")
        if connection.execute(
            "SELECT COUNT(*) FROM brand_groups WHERE group_status = 'accepted' AND n_accepted < 2"
        ).fetchone()[0]:
            errors.append("accepted group has fewer than two members")
        if connection.execute(
            "SELECT COUNT(*) FROM brand_match_index m WHERE m.match_status = 'accepted' "
            "AND NOT EXISTS (SELECT 1 FROM brand_groups g WHERE g.brand_family_id = m.brand_family_id "
            "AND g.group_status = 'accepted')"
        ).fetchone()[0]:
            errors.append("accepted match has no accepted group")
        if connection.execute(
            "SELECT COUNT(*) FROM brand_match_index WHERE match_source = 'alias_candidate' "
            "AND match_status = 'accepted'"
        ).fetchone()[0]:
            errors.append("unreviewed alias candidate marked accepted")
        if connection.execute(
            "SELECT COUNT(*) FROM (SELECT lookup_key, COUNT(DISTINCT brand_family_id) n "
            "FROM brand_match_index WHERE match_status = 'accepted' "
            "GROUP BY lookup_key HAVING n > 1)"
        ).fetchone()[0]:
            errors.append("one lookup key resolves to multiple accepted families")
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'"
            )
        }
        if len(indexes) < 8:
            errors.append("required lookup indexes missing")
    finally:
        connection.close()

    if len(pd.read_parquet(release_dir / "brand_match_index_v2.parquet")) != counts[
        "match_keys"
    ]:
        errors.append("match parquet row count mismatch")
    if len(pd.read_parquet(release_dir / "brand_group_summary_v2.parquet")) != counts[
        "groups"
    ]:
        errors.append("group parquet row count mismatch")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors, "stats": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--brand-release", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.release_dir, args.brand_release)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
