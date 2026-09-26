"""Read-only verification of the locked Gold Stage-1 v2.1 release."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1"
SCHEMA = ROOT / "docs/specs/schemas/stage1_evaluation_v2.schema.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    errors: list[str] = []
    lock = json.loads((RELEASE / "LOCKED.json").read_text(encoding="utf-8"))
    manifest_path = RELEASE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if lock.get("status") != "locked" or manifest.get("status") != "locked":
        errors.append("Release status is not locked")
    if lock.get("manifest_sha256") != sha256(manifest_path):
        errors.append("LOCKED.json manifest hash mismatch")
    full_schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    part = lambda name: {"$schema": full_schema["$schema"], "$defs": full_schema["$defs"],
                         **full_schema["$defs"][name]}
    jsonschema.validate(manifest, part("suiteManifest"))
    for name, expected in manifest["artifact_hashes"].items():
        path = RELEASE / name
        if not path.exists() or sha256(path) != expected:
            errors.append(f"Artifact missing or changed: {name}")
    source_files = json.loads((RELEASE / "source_files.json").read_text(encoding="utf-8"))
    for name, record in source_files.items():
        path = ROOT / record["path"]
        if not path.exists() or sha256(path) != record["sha256"]:
            errors.append(f"Pinned source missing or changed: {name}")
        if record["sha256"] != manifest["source_hashes"][name]:
            errors.append(f"Manifest source hash mismatch: {name}")
    targets = pq.read_table(RELEASE / "target_pois_v2_1.parquet").to_pylist()
    sessions = pq.read_table(RELEASE / "query_sessions_v2_1.parquet").to_pylist()
    qrels = pq.read_table(RELEASE / "qrels_v2_1.parquet").to_pylist()
    prefixes = [json.loads(line) for line in
                (RELEASE / "prefix_evidence_v2_1.jsonl").read_text(encoding="utf-8").splitlines()]
    expected_counts = manifest["counts"]
    for key, actual in (("n_target_pois", len(targets)), ("n_query_sessions", len(sessions)),
                        ("n_qrels", len(qrels)), ("n_q01_prefix_evidence", len(prefixes))):
        if expected_counts[key] != actual:
            errors.append(f"Count mismatch {key}: {actual}")
    if len(targets) != 200 or len(sessions) != 800 or len(qrels) != 820 or len(prefixes) != 200:
        errors.append("Gold v2.1 cardinality mismatch")
    target_ids = {row["poi_id"] for row in targets}
    if len(target_ids) != 200:
        errors.append("Duplicate target POI ID")
    train_ids = set(pq.read_table(ROOT / "data/vietnam/train_stage1_20k/target_pois_20k.parquet",
                                  columns=["poi_id"])["poi_id"].to_pylist())
    if target_ids & train_ids:
        errors.append("Target overlap with current train pool")
    roles = defaultdict(set)
    by_qrel = defaultdict(set)
    for row in qrels:
        jsonschema.validate(row, part("evaluationQrel"))
        if row["label"] == "positive":
            by_qrel[row["qrel_set_id"]].add(row["target_id"])
    for row in sessions:
        jsonschema.validate(row, part("poiQuerySession"))
        roles[row["case_id"]].add(row["query_role"])
        if set(row["acceptable_poi_ids"]) != by_qrel[row["qrel_set_id"]]:
            errors.append(f"Qrel mismatch: {row['query_id']}")
        if set(row["acceptable_poi_ids"]) & train_ids:
            errors.append(f"Positive overlaps train: {row['query_id']}")
    if len(roles) != 200 or any(value != {"q01", "q02", "q03", "q04"} for value in roles.values()):
        errors.append("Query roles not exactly q01-q04 per case")
    if len(by_qrel) != 800:
        errors.append("qrel_set_id not query-specific")
    q01_ids = {row["query_id"] for row in sessions if row["query_role"] == "q01"}
    if {row["query_id"] for row in prefixes} != q01_ids:
        errors.append("Prefix evidence not complete")
    audit = json.loads((RELEASE / "selection_and_leakage_audit.json").read_text(encoding="utf-8"))
    signoff = json.loads((RELEASE / "quality_signoff.json").read_text(encoding="utf-8"))
    if not audit.get("ready_for_lock") or signoff.get("status") != "approved":
        errors.append("Copied audit/signoff does not approve lock")
    if signoff["session_parquet_sha256"] != sha256(RELEASE / "query_sessions_v2_1.parquet"):
        errors.append("Session hash differs from signed draft")
    if signoff["qrels_parquet_sha256"] != sha256(RELEASE / "qrels_v2_1.parquet"):
        errors.append("Qrel hash differs from signed draft")
    if signoff["mutation_traces_sha256"] != sha256(RELEASE / "mutation_traces_v2_1.jsonl"):
        errors.append("Mutation trace hash differs from signed draft")
    if errors:
        print(json.dumps({"verdict": "FAIL", "errors": errors}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"verdict": "PASS", "release": str(RELEASE.relative_to(ROOT)),
                      "counts": {"targets": len(targets), "sessions": len(sessions),
                                 "qrels": len(qrels), "q01_prefixes": len(prefixes)},
                      "role_counts": dict(Counter(row["query_role"] for row in sessions))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
