"""Publish validated brand Gold staging as an immutable release. Never edits Gold POI."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from stage1_brand_v3_common import (
    GOLD_BRAND,
    GOLD_BRAND_STAGING,
    refuse_nonempty,
    sha256_file,
    write_json,
)
from validate_gold_stage1_brand_v1 import validate


def lock(staging: Path, release: Path) -> dict:
    refuse_nonempty(release)
    report = validate(staging, split_name="test")
    if report["verdict"] != "PASS":
        raise SystemExit(f"Brand Gold staging failed: {report['errors']}")
    shutil.copytree(staging, release)
    lock_doc = {
        "suite_id": "gold_stage1_brand_v1",
        "release_id": "gold_stage1_brand_v1",
        "status": "locked",
        "locked_at_utc": datetime.now(UTC).isoformat(),
        "verdict": "PASS_WITH_ACCEPTED_ALIAS_SHORTFALL",
        "n_queries": report["stats"]["queries"],
        "n_families": report["stats"]["families"],
        "n_qrels": report["stats"]["qrels"],
        "manifest_sha256": sha256_file(release / "manifest.json"),
        "alias_shortfall": "No verified-alias rows existed in source; none were invented.",
    }
    write_json(release / "LOCKED.json", lock_doc)
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    manifest["status"] = "locked"
    write_json(release / "manifest.json", manifest)
    lock_doc["manifest_sha256"] = sha256_file(release / "manifest.json")
    write_json(release / "LOCKED.json", lock_doc)
    return lock_doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, default=GOLD_BRAND_STAGING)
    parser.add_argument("--release", type=Path, default=GOLD_BRAND)
    args = parser.parse_args()
    print(json.dumps(lock(args.staging, args.release), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
