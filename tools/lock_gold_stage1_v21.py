"""Publish the signed Gold Stage-1 v2.1 draft as an immutable new release.

The locked Gold v2 directory is never written. This command refuses to
overwrite an existing v2.1 release and leaves a failed temporary build for
inspection instead of deleting it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "data/vietnam/stage1_eval_suite_v2"
STAGING = SUITE / "staging/gold_stage1_v2_1"
DRAFT = STAGING / "draft"
RELEASE = SUITE / "gold_stage1_v2_1"
CORPUS = ROOT / "data/vietnam/poi_corpus_v3"
TRAIN = ROOT / "data/vietnam/train_stage1_20k/target_pois_20k.parquet"
PUBLISHED_TRAIN = ROOT / "data/vietnam/train_stage1_queries_v6/query_variants.parquet"
OLD_MANIFEST = SUITE / "gold_stage1_v2/manifest.json"
SCHEMA = ROOT / "docs/specs/schemas/stage1_evaluation_v2.schema.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_targets(target: Path, cards: list[dict]) -> None:
    wanted = {card["poi_id"] for card in cards}
    core = {row["poi_id"]: row for row in
            pq.read_table(CORPUS / "pois_core.parquet", columns=["poi_id", "address_status", "destination_searchable"]).to_pylist()
            if row["poi_id"] in wanted}
    if set(core) != wanted or not all(core[poi_id]["destination_searchable"] for poi_id in wanted):
        raise ValueError("Gold targets must be present and searchable in pinned corpus v3")
    rows = []
    for card in cards:
        source = card["source"]
        rows.append({
            "case_id": card["case_id"], "poi_id": card["poi_id"],
            "name": source["name"], "brand": source.get("brand"), "ref": source.get("ref"),
            "category": source["category"], "province": source.get("province"),
            "subdistrict": source.get("subdistrict"), "housenumber": source.get("housenumber"),
            "street": source.get("street"), "address_text": source.get("address_text"),
            "address_status": core[card["poi_id"]]["address_status"],
            "primary_sampling_stratum": card["primary_sampling_stratum"],
            "case_origin": card["case_origin"], "exposure_class": card["exposure_class"],
            "entity_group_id": source.get("entity_group_id"),
            "clean_reason": "source_only_gold_v21_v3_review",
            "clean_pass": True,
            "clean_notes": "Validated against corpus-v3 and source-only authoring packet",
        })
    if len(rows) != 200 or len({row["poi_id"] for row in rows}) != 200:
        raise ValueError("Expected exactly 200 distinct target POIs")
    pq.write_table(pa.Table.from_pylist(rows), target / "target_pois_v2_1.parquet")
    with (target / "target_pois_v2_1.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if RELEASE.exists():
        raise SystemExit(f"Refusing to overwrite existing release: {RELEASE}")
    audit = json.loads((DRAFT / "independent_audit.json").read_text(encoding="utf-8"))
    if audit.get("verdict") != "PASS" or not audit.get("ready_for_lock"):
        raise SystemExit(f"Draft is not signed and ready for lock: {audit.get('release_blockers')}")
    packet_path = STAGING / "authoring_packet.jsonl"
    cards = [json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines()]
    packet_manifest = json.loads((STAGING / "authoring_packet_manifest.json").read_text(encoding="utf-8"))
    if sha256(packet_path) != packet_manifest["packet_sha256"]:
        raise ValueError("Packet hash mismatch")
    corpus_manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    for filename in ("pois_core.parquet", "search_documents.parquet"):
        if sha256(CORPUS / filename) != corpus_manifest["artifact_hashes"][filename]:
            raise ValueError(f"Corpus v3 hash mismatch: {filename}")
    if sha256(PUBLISHED_TRAIN) != audit["published_train5k_sha256"]:
        raise ValueError("Published train snapshot changed after signed audit")
    temp = Path(tempfile.mkdtemp(prefix=".gold_stage1_v2_1.", dir=SUITE))
    copies = {
        "query_sessions_v2_1_draft.parquet": "query_sessions_v2_1.parquet",
        "query_sessions_v2_1_draft.csv": "query_sessions_v2_1.csv",
        "qrels_v2_1_draft.parquet": "qrels_v2_1.parquet",
        "prefix_evidence_v2_1_draft.jsonl": "prefix_evidence_v2_1.jsonl",
        "mutation_traces_v2_1_draft.jsonl": "mutation_traces_v2_1.jsonl",
        "coverage_diagnostic.json": "coverage_report_v2_1.json",
        "name_street_no_house_coverage.json": "name_street_no_house_coverage.json",
        "quality_signoff.json": "quality_signoff.json",
        "independent_audit.json": "selection_and_leakage_audit.json",
    }
    for source_name, release_name in copies.items():
        shutil.copy2(DRAFT / source_name, temp / release_name)
    for name in ("coverage_shortfall_adjudication_v1.json", "name_street_exceptions_adjudication_v1.json"):
        shutil.copy2(STAGING / name, temp / name)
    make_targets(temp, cards)
    sources = {
        "corpus_v3_pois_core": CORPUS / "pois_core.parquet",
        "corpus_v3_search_documents": CORPUS / "search_documents.parquet",
        "train_targets_current": TRAIN,
        "published_train_v6_queries": PUBLISHED_TRAIN,
        "gold_v2_manifest": OLD_MANIFEST,
        "authoring_packet": packet_path,
        "authoring_packet_manifest": STAGING / "authoring_packet_manifest.json",
        "target_overrides": STAGING / "target_overrides_v1.json",
        "schema": SCHEMA,
    }
    source_files = {name: {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                           "sha256": sha256(path)} for name, path in sources.items()}
    write_json(temp / "source_files.json", source_files)
    (temp / "README.md").write_text(
        "# Gold Stage 1 v2.1 — locked release\n\n"
        "200 POI, 800 completed query sessions, 820 query-specific positive qrels, "
        "200 q01 prefix-evidence records. Corpus/index snapshot: POI corpus v3.\n\n"
        "This is a new release of the `gold_stage1_v2` logical suite. The locked v2 "
        "directory remains unchanged. See `manifest.json`, `source_files.json`, "
        "`quality_signoff.json`, and the two exception-adjudication files before "
        "interpreting scores. Shared-suite address requirement 18 is pending.\n",
        encoding="utf-8",
    )
    artifact_hashes = {path.name: sha256(path) for path in temp.iterdir() if path.is_file()}
    full_schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": "stage1-eval-suite-v2", "record_type": "suite_manifest",
        "suite_id": "gold_stage1_v2", "status": "locked",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "corpus_version": corpus_manifest["corpus_version"],
        "normalizer_version": "v2-nfkc-casefold",
        "entity_snapshot_version": None, "brand_snapshot_version": None,
        "address_snapshot_version": None, "prefix_expander_version": "v2-grapheme-nfc",
        "label_policy_version": "v2-strict-poi-positive",
        "source_hashes": {name: item["sha256"] for name, item in source_files.items()},
        "artifact_hashes": artifact_hashes,
        "counts": {
            "n_target_pois": 200, "n_query_sessions": 800, "n_qrels": 820,
            "n_q01_prefix_evidence": 200, "n_name_street_no_house_covered": 131,
            "n_name_street_accepted_exceptions": 3,
            "n_coverage_accepted_shortfalls": 1,
        },
    }
    manifest_schema = {"$schema": full_schema["$schema"], "$defs": full_schema["$defs"],
                       **full_schema["$defs"]["suiteManifest"]}
    jsonschema.validate(manifest, manifest_schema)
    write_json(temp / "manifest.json", manifest)
    lock = {
        "suite_id": "gold_stage1_v2", "release_id": "gold_stage1_v2_1",
        "status": "locked", "locked_at_utc": datetime.now(UTC).isoformat(),
        "verdict": "PASS_WITH_ACCEPTED_EXCEPTIONS", "n_target_pois": 200,
        "n_query_sessions": 800, "n_qrels": 820,
        "train_overlap": 0, "manifest_sha256": sha256(temp / "manifest.json"),
    }
    write_json(temp / "LOCKED.json", lock)
    if RELEASE.exists():
        raise RuntimeError(f"Release appeared during packaging: {RELEASE}")
    temp.rename(RELEASE)
    print(json.dumps({"release": str(RELEASE.relative_to(ROOT)),
                      "manifest_sha256": lock["manifest_sha256"],
                      "counts": manifest["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
