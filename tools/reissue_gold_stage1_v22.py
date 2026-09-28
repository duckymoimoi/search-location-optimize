"""Reissue existing Gold payloads with reproducible, present-day provenance.

Does not recreate missing historical authorship or claim an untouched holdout.
The v2.1 release is read-only. Build uses only payloads matching its locked hashes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil

import jsonschema
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1"
NEW = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_2"
SCHEMA = ROOT / "docs/specs/schemas/stage1_evaluation_v2.schema.json"
CORPUS = ROOT / "data/vietnam/poi_corpus_v3/pois_core.parquet"
TRAIN = ROOT / "data/vietnam/train_stage1_20k/target_pois_20k.parquet"
PAYLOADS = {
    "query_sessions_v2_1.parquet": "query_sessions_v2_2.parquet",
    "qrels_v2_1.parquet": "qrels_v2_2.parquet",
    "target_pois_v2_1.parquet": "target_pois_v2_2.parquet",
    "prefix_evidence_v2_1.jsonl": "prefix_evidence_v2_2.jsonl",
    "mutation_traces_v2_1.jsonl": "mutation_traces_v2_2.jsonl",
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def audit_payload(folder):
    sessions = pq.read_table(folder / "query_sessions_v2_2.parquet").to_pylist()
    qrels = pq.read_table(folder / "qrels_v2_2.parquet").to_pylist()
    targets = pq.read_table(folder / "target_pois_v2_2.parquet").to_pylist()
    prefixes = [json.loads(x) for x in (folder / "prefix_evidence_v2_2.jsonl").read_text(encoding="utf-8").splitlines()]
    corpus_rows = pq.read_table(CORPUS, columns=["poi_id", "destination_searchable"]).to_pylist()
    corpus_ids = {r["poi_id"] for r in corpus_rows if r["destination_searchable"]}
    train_ids = set(pq.read_table(TRAIN, columns=["poi_id"])["poi_id"].to_pylist())
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validators = {key: jsonschema.Draft202012Validator({"$defs": schema["$defs"], **schema["$defs"][key]})
                  for key in ("poiQuerySession", "evaluationQrel")}
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    check((len(sessions), len(qrels), len(targets), len(prefixes)) == (800, 820, 200, 200), "cardinality")
    by_qrel = defaultdict(set)
    seen_qrel = set()
    for row in qrels:
        for e in validators["evaluationQrel"].iter_errors(row):
            errors.append("qrel schema: " + e.message)
        pair = row["qrel_set_id"], row["target_id"]
        check(pair not in seen_qrel, "duplicate qrel " + str(pair))
        seen_qrel.add(pair)
        check(row["label"] == "positive", "unexpected nonpositive label")
        by_qrel[row["qrel_set_id"]].add(row["target_id"])
    roles = defaultdict(set)
    query_ids = set()
    target_ids = {r["poi_id"] for r in targets}
    target_cases = {r["case_id"]: r["poi_id"] for r in targets}
    for row in sessions:
        for e in validators["poiQuerySession"].iter_errors(row):
            errors.append("query schema: " + e.message)
        query_id = row["query_id"]
        check(query_id not in query_ids, "duplicate query_id " + query_id)
        query_ids.add(query_id)
        accepted = set(row["acceptable_poi_ids"])
        check(bool(accepted) and accepted == by_qrel[row["qrel_set_id"]], "qrel mismatch " + query_id)
        check(row["intended_poi_id"] in accepted, "intended missing " + query_id)
        check(target_cases.get(row["case_id"]) == row["intended_poi_id"], "case target mismatch " + query_id)
        check(accepted <= corpus_ids, "positive absent from searchable corpus " + query_id)
        check(not (accepted & train_ids), "positive in training target pool " + query_id)
        check(row["review_status"] == "accepted", "inherited label not accepted " + query_id)
        check(bool(row["query_text"].strip()), "empty query " + query_id)
        roles[row["case_id"]].add(row["query_role"])
    check(len(target_ids) == 200 and len(target_cases) == 200, "duplicate targets/cases")
    check(target_ids <= corpus_ids and not (target_ids & train_ids), "target scope/leakage")
    check(len(roles) == 200 and all(v == {"q01", "q02", "q03", "q04"} for v in roles.values()), "query roles")
    check(len(by_qrel) == len(sessions) and set(by_qrel) == {r["qrel_set_id"] for r in sessions}, "qrel set coverage")
    q01 = {r["query_id"]: r for r in sessions if r["query_role"] == "q01"}
    check({r["query_id"] for r in prefixes} == set(q01), "prefix coverage")
    for row in prefixes:
        check(0 < row["group_ready_grapheme"] <= row["entity_ready_grapheme"] <= row["full_graphemes"], "prefix boundary")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors,
            "counts": {"targets": len(targets), "sessions": len(sessions), "qrels": len(qrels), "prefixes": len(prefixes)},
            "role_counts": dict(Counter(r["query_role"] for r in sessions)),
            "positive_overlap_train_targets": len(set().union(*by_qrel.values()) & train_ids),
            "label_review": "inherited accepted labels; structural and corpus linkage revalidated; no new independent human review",
            "holdout_status": "previously exposed regression set; not a new holdout"}


def build(out):
    old_manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    for name in PAYLOADS:
        if sha(OLD / name) != old_manifest["artifact_hashes"][name]:
            raise ValueError("Legacy data payload differs from locked hash: " + name)
    out.mkdir(parents=True, exist_ok=False)
    for old, new in PAYLOADS.items():
        shutil.copyfile(OLD / old, out / new)
    source_paths = [OLD / p for p in PAYLOADS] + [OLD / "manifest.json", OLD / "source_files.json", SCHEMA, CORPUS, TRAIN, Path(__file__)]
    dump(out / "source_files.json", {str(p.relative_to(ROOT)).replace("\\", "/"): {"sha256": sha(p)} for p in source_paths})
    historical_sources = json.loads((OLD / "source_files.json").read_text(encoding="utf-8"))
    unresolved = [name for name, r in historical_sources.items()
                  if not (ROOT / r["path"]).exists() or sha(ROOT / r["path"]) != r["sha256"]]
    dump(out / "lineage.json", {
        "parent_release": "gold_stage1_v2_1", "logical_suite_id": "gold_stage1_v2",
        "operation": "byte_identical_payload_reissue", "new_independent_holdout": False,
        "authorization": "User requested reissue of existing queries/qrels with revalidation and reproducible provenance.",
        "historical_provenance_recovered": False, "historical_missing_or_changed_sources": unresolved,
        "historical_readme_hash_matches": sha(OLD / "README.md") == old_manifest["artifact_hashes"]["README.md"],
        "scope": "Provenance begins at existing locked data payloads and current corpus/schema. Does not certify missing historical authoring packet.",
        "payload_mapping": PAYLOADS,
    })
    audit = audit_payload(out)
    dump(out / "validation_report.json", audit)
    if audit["verdict"] != "PASS":
        raise ValueError(audit)
    (out / "README.md").write_text(
        "# Gold POI v2.2 — reproducible reissue\n\n"
        "200 POI, 800 query sessions, 820 positive qrels, 200 prefix records. "
        "Payloads are byte-identical to the locked data payloads of v2.1; filenames carry v2.2, logical suite IDs stay gold_stage1_v2.\n\n"
        "This is a previously exposed regression set, not a new holdout. Historical labels are inherited; "
        "structural validity, corpus membership, qrel consistency and train-target overlap were rechecked. "
        "No new independent human label review is claimed.\n\n"
        "v2.1 full historical provenance remains incomplete. This reissue pins present source files and the builder, "
        "without claiming to recover the missing authoring packet. See lineage.json, source_files.json and validation_report.json.\n\n"
        "Verify: `python tools/reissue_gold_stage1_v22.py verify`. "
        "Reproduce in a new folder: `python tools/reissue_gold_stage1_v22.py build --out artifacts/results/gold_v22_rebuild`. "
        "Do not edit this signed directory.\n", encoding="utf-8", newline="\n")
    manifest = {"schema_version": "gold-reissue-v1", "release_id": "gold_stage1_v2_2",
                "logical_suite_id": "gold_stage1_v2", "release_date": "2026-09-28",
                "status": "reissued_payload_verified", "new_independent_holdout": False,
                "counts": audit["counts"], "artifact_hashes": {p.name: sha(p) for p in sorted(out.iterdir())}}
    dump(out / "manifest.json", manifest)
    dump(out / "LOCKED.json", {"status": "locked_reissue", "manifest_sha256": sha(out / "manifest.json")})
    return verify(out)


def verify(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((folder / "LOCKED.json").read_text(encoding="utf-8"))
    assert lock["status"] == "locked_reissue" and lock["manifest_sha256"] == sha(folder / "manifest.json")
    assert manifest["status"] == "reissued_payload_verified" and manifest["new_independent_holdout"] is False
    for name, expected in manifest["artifact_hashes"].items():
        assert sha(folder / name) == expected, "Artifact changed: " + name
    for name, record in json.loads((folder / "source_files.json").read_text(encoding="utf-8")).items():
        assert sha(ROOT / name) == record["sha256"], "Source changed: " + name
    for old, new in PAYLOADS.items():
        assert sha(folder / new) == sha(OLD / old), "Payload changed during reissue: " + new
    report = audit_payload(folder)
    assert report["counts"] == manifest["counts"]
    if report["verdict"] != "PASS":
        raise ValueError(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "verify"])
    parser.add_argument("--out", type=Path, default=NEW)
    args = parser.parse_args()
    print(json.dumps(build(args.out.resolve()) if args.action == "build" else verify(args.out.resolve()), ensure_ascii=False, indent=2))
