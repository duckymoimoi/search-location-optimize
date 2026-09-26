"""Validate a compiled gold_stage1_brand_v1 or brand-dev/train view."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import jsonschema
import pandas as pd

from stage1_brand_query_v1_common import normalize_query, read_jsonl
from stage1_brand_v3_common import (
    GOLD_BRAND,
    GOLD_BRAND_STAGING,
    GOLD_POI,
    LEFT_OVER_FAMILIES,
    MEMBERSHIP_V3,
    SCHEMA,
    SPLITS_V1,
    TRAIN_BRAND_V3,
    TRAIN_V6,
    fold_text,
    has_namespace_token,
    load_v3_core,
    sha256_file,
    write_json,
)


def _jsonable(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def validate(release_dir: Path, *, require_lock: bool = False, split_name: str | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    required = {
        "brand_queries_v1.parquet",
        "brand_qrels_v1.parquet",
        "prefix_evidence_v1.jsonl",
        "manifest.json",
        "independent_family_review.json",
    }
    missing = sorted(name for name in required if not (release_dir / name).is_file())
    if missing:
        return {"verdict": "FAIL", "errors": [f"missing files: {missing}"], "warnings": []}

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    queries = pd.read_parquet(release_dir / "brand_queries_v1.parquet")
    qrels = pd.read_parquet(release_dir / "brand_qrels_v1.parquet")
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assignment = {
        row["brand_family_id"]: row["split"]
        for row in json.loads((SPLITS_V1 / "family_split.json").read_text(encoding="utf-8"))["families"]
    }
    split_name = split_name or manifest.get("split")
    members = pd.read_parquet(MEMBERSHIP_V3 / "brand_group_members_v3.parquet")
    accepted = set(
        members.loc[members["membership_status"] == "accepted", "poi_id"].astype(str)
    )
    core = load_v3_core()
    v3_ids = set(core["poi_id"].astype(str))
    searchable = set(core.loc[core["destination_searchable"] == True, "poi_id"].astype(str))
    gold_targets = pd.read_parquet(GOLD_POI / "target_pois_v2_1.parquet")
    gold_ids = set(gold_targets["poi_id"].astype(str))
    gold_sessions = pd.read_parquet(GOLD_POI / "query_sessions_v2_1.parquet")
    gold_norm = {normalize_query(text) for text in gold_sessions["query_text"].astype(str)}
    gold_fold = {fold_text(text) for text in gold_sessions["query_text"].astype(str)}

    if require_lock:
        lock_path = release_dir / "LOCKED.json"
        if not lock_path.exists():
            errors.append("LOCKED.json missing")
        else:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            if sha256_file(release_dir / "manifest.json") != lock.get("manifest_sha256"):
                errors.append("lock hash mismatch")

    for raw in queries.to_dict("records"):
        row = {key: _jsonable(value) for key, value in raw.items()}
        schema_row = {
            key: row[key]
            for key in (
                "schema_version",
                "record_type",
                "suite_id",
                "query_id",
                "query_family_id",
                "query_text",
                "query_role",
                "difficulty",
                "brand_group_id",
                "namespace",
                "acceptable_poi_ids",
                "qrel_set_id",
                "review_status",
            )
            if key in row
        }
        try:
            jsonschema.validate(schema_row, schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"{row.get('query_id')}: schema {exc.message}")
        family_id = str(row["brand_family_id"])
        if family_id in LEFT_OVER_FAMILIES:
            errors.append(f"{row['query_id']}: leftover family")
        if assignment.get(family_id) != split_name:
            errors.append(f"{row['query_id']}: family split {assignment.get(family_id)} != {split_name}")
        ids = [str(pid) for pid in row["acceptable_poi_ids"]]
        if not ids:
            errors.append(f"{row['query_id']}: empty positives")
        missing_ids = [pid for pid in ids if pid not in v3_ids or pid not in searchable or pid not in accepted]
        if missing_ids:
            errors.append(f"{row['query_id']}: {len(missing_ids)} IDs not accepted/searchable v3")
        if split_name == "train" and (set(ids) & gold_ids):
            errors.append(f"{row['query_id']}: Gold POI target in train positives")
        if normalize_query(row["query_text"]) in gold_norm or fold_text(row["query_text"]) in gold_fold:
            errors.append(f"{row['query_id']}: query collides with Gold POI")
        if row["query_role"] == "namespace_qualified" and not has_namespace_token(
            str(row["query_text"]), str(row["namespace"])
        ):
            warnings.append(f"{row['query_id']}: namespace role without token")
        if row["query_role"] == "verified_alias":
            warnings.append(f"{row['query_id']}: unexpected verified alias")

    by_qrel = defaultdict(set)
    compatible = qrels[qrels["label"] == "compatible"]
    for row in compatible.itertuples(index=False):
        by_qrel[str(row.qrel_set_id)].add(str(row.target_id))
    for row in queries.to_dict("records"):
        if set(row["acceptable_poi_ids"]) != by_qrel.get(str(row["qrel_set_id"]), set()):
            errors.append(f"{row['query_id']}: qrel/query positive parity")
        if len(errors) > 40:
            errors.append("too many errors; stopping early")
            break

    families = set(queries["brand_family_id"].astype(str))
    other = {fam for fam, split in assignment.items() if split != split_name}
    if families & other:
        errors.append("family leakage into another split")

    review = json.loads((release_dir / "independent_family_review.json").read_text(encoding="utf-8"))
    if not review.get("alias_shortfall_adjudicated"):
        errors.append("alias shortfall not adjudicated")

    report = {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "queries": int(len(queries)),
            "qrels": int(len(qrels)),
            "families": int(queries["brand_family_id"].nunique()),
            "roles": queries["query_role"].value_counts().to_dict(),
            "split": split_name,
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=GOLD_BRAND_STAGING)
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--require-lock", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.release_dir, require_lock=args.require_lock, split_name=args.split)
    target = args.report or (args.release_dir / "validation_report.json")
    write_json(target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
