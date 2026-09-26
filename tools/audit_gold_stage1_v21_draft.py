"""Independent consistency/leakage audit of serialized Gold v2.1 drafts.

This checks mechanical evidence. It does not declare query naturalness or
entity-equivalence correct; those still require source-based manual review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_v2_1"
TRAIN = ROOT / "data/vietnam/train_stage1_queries_v6/staging/003_hard_noise_500/query_variants_v6_hard_noise_500_final.parquet"
PUBLISHED_TRAIN = ROOT / "data/vietnam/train_stage1_queries_v6/query_variants.parquet"
PUBLISHED_TRAIN_MANIFEST = ROOT / "data/vietnam/train_stage1_queries_v6/manifest.json"
TRAIN_TARGETS = ROOT / "data/vietnam/train_stage1_20k/target_pois_20k.parquet"
TRAIN_TARGETS_V2_BACKUP = ROOT / "data/vietnam/train_stage1_20k/target_pois_20k.parquet.v2bak"
TRAIN_MANIFEST = ROOT / "data/vietnam/train_stage1_20k/manifest.json"
OLD_GOLD = ROOT / "data/vietnam/gold_stage1_v1/query_variants_v1.parquet"
CURRENT_GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2/query_sessions_v2.parquet"
CURRENT_GOLD_RELEASE = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fold(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("đ", "d")
    text = "".join(c for c in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(c))
    return " ".join(text.split())


def building_code(name: str) -> str | None:
    """Return the immutable tower discriminator, ignoring punctuation in S3.01."""
    if match := re.search(r"\b(S\d)\.(\d{2})\b", name, re.IGNORECASE):
        return (match.group(1) + match.group(2)).upper()
    if match := re.search(r"\b(\d{3})\s+(CMT\d)\b", name, re.IGNORECASE):
        return (match.group(1) + match.group(2)).upper()
    if match := re.search(r"\b(?:A\dB|A\d|8X)\b", name, re.IGNORECASE):
        return match.group(0).upper()
    if match := re.search(r"\b\d{2}T\d\b|\b(?:RIO|SOL)\b", name, re.IGNORECASE):
        return match.group(0).upper()
    return None


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ("coverage_tags", "acceptable_poi_ids"):
            row[key] = json.loads(row[key])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=STAGING)
    parser.add_argument("--require-complete", action="store_true",
                        help="Fail unless all 200 source-packet cases have four query sessions")
    args = parser.parse_args()
    staging = args.staging
    manifest = json.loads((staging / "authoring_packet_manifest.json").read_text(encoding="utf-8"))
    packet = staging / "authoring_packet.jsonl"
    packet_cards = {row["case_id"]: row for row in
                    (json.loads(line) for line in packet.read_text(encoding="utf-8").splitlines())}
    packet_cases = set(packet_cards)
    errors: list[str] = []
    train_manifest = json.loads(PUBLISHED_TRAIN_MANIFEST.read_text(encoding="utf-8"))
    expected_train_hash = train_manifest.get("published_train_table", {}).get("parquet", {}).get("sha256")
    if sha256(PUBLISHED_TRAIN) != expected_train_hash:
        errors.append("Published train-5k table changed after its manifest was written")
    old_lock = json.loads((CURRENT_GOLD_RELEASE / "LOCKED.json").read_text(encoding="utf-8"))
    old_manifest_path = CURRENT_GOLD_RELEASE / "manifest.json"
    if sha256(old_manifest_path) != old_lock["manifest_sha256"]:
        errors.append("Locked Gold v2 manifest hash changed")
    old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
    for filename, expected_hash in old_manifest["artifact_hashes"].items():
        if sha256(CURRENT_GOLD_RELEASE / filename) != expected_hash:
            errors.append(f"Locked Gold v2 artifact changed: {filename}")
    if sha256(packet) != manifest["packet_sha256"]:
        errors.append("Packet hash mismatch")
    for name, source_path in (
        ("target_pois_v2.parquet", ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2/target_pois_v2.parquet"),
        ("pois_core.parquet", ROOT / "data/vietnam/poi_corpus_v3/pois_core.parquet"),
        ("target_overrides_v1.json", staging / "target_overrides_v1.json"),
    ):
        if sha256(source_path) != manifest["source_hashes"][name]:
            errors.append(f"Source hash mismatch: {name}")
    pinned_train_hash = manifest["source_hashes"]["target_pois_20k_v2_pinned.parquet"]
    pinned_train = next((path for path in (TRAIN_TARGETS, TRAIN_TARGETS_V2_BACKUP)
                         if path.exists() and sha256(path) == pinned_train_hash), None)
    if pinned_train is None:
        errors.append("Pinned corpus-v2 train target snapshot unavailable or hash mismatch")
    if sha256(TRAIN_TARGETS) != manifest["source_hashes"]["target_pois_20k.parquet"]:
        errors.append("Current corpus-v3 train target snapshot changed after packet build")
    current_train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    if sha256(TRAIN_TARGETS) != current_train_manifest["files"]["target_pois_20k.parquet"]["sha256"]:
        errors.append("Current train target hash disagrees with its manifest")
    draft = staging / "draft"
    rows = pq.read_table(draft / "query_sessions_v2_1_draft.parquet").to_pylist()
    csv_rows = read_csv(draft / "query_sessions_v2_1_draft.csv")
    qrels = pq.read_table(draft / "qrels_v2_1_draft.parquet").to_pylist()
    prefixes = [json.loads(line) for line in
                (draft / "prefix_evidence_v2_1_draft.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows) != len(csv_rows):
        errors.append("CSV/Parquet row count mismatch")
    for a, b in zip(rows, csv_rows):
        for key in a:
            if str(a[key]) != str(b[key]):
                errors.append(f"CSV/Parquet mismatch: {a['query_id']}:{key}")
                break
    by_case: dict[str, list[dict]] = defaultdict(list)
    by_qrel: dict[str, list[dict]] = defaultdict(list)
    for row in qrels:
        by_qrel[row["qrel_set_id"]].append(row)
    train_target_ids = set(pq.read_table(TRAIN_TARGETS, columns=["poi_id"])["poi_id"].to_pylist())
    published_train = pq.read_table(PUBLISHED_TRAIN, columns=["query_text", "intended_poi_id"]).to_pylist()
    published_train_ids = {row["intended_poi_id"] for row in published_train}
    train_target_ids.update(published_train_ids)
    if pinned_train is not None:
        train_target_ids.update(pq.read_table(pinned_train, columns=["poi_id"])["poi_id"].to_pylist())
    ids = set()
    fold_surfaces = set()
    for row in rows:
        case_id, query_id = row["case_id"], row["query_id"]
        by_case[case_id].append(row)
        card = packet_cards.get(case_id)
        if card and card["primary_sampling_stratum"] == "building_code":
            code = building_code(card["source"]["name"])
            if code and code not in "".join(ch for ch in row["query_text"].upper() if ch.isalnum()):
                errors.append(f"Missing/changed immutable tower code: {query_id}:{code}")
            if not code:
                name_digits = re.findall(r"\d+", card["source"]["name"])
                query_digits = re.findall(r"\d+", row["query_text"])
                if any(number not in query_digits for number in name_digits):
                    errors.append(f"Missing/changed numeric building identifier: {query_id}:{name_digits}")
        if query_id in ids:
            errors.append(f"Duplicate query_id: {query_id}")
        ids.add(query_id)
        if row["review_status"] != "accepted":
            errors.append(f"Unaccepted query: {query_id}")
        surface = fold(row["query_text"])
        if surface in fold_surfaces:
            errors.append(f"Duplicate folded Gold-v2.1 surface: {query_id}")
        fold_surfaces.add(surface)
        accepted = set(row["acceptable_poi_ids"])
        actual = {q["target_id"] for q in by_qrel[row["qrel_set_id"]]
                  if q["label"] == "positive"}
        if accepted != actual or row["intended_poi_id"] not in accepted:
            errors.append(f"Qrel/session mismatch: {query_id}")
        if accepted & train_target_ids:
            errors.append(f"Gold positive in train targets: {query_id}")
        if len(by_qrel[row["qrel_set_id"]]) != len(accepted):
            errors.append(f"Unexpected nonpositive/duplicate qrel: {query_id}")
    for case_id, case_rows in by_case.items():
        if len(case_rows) != 4 or {r["query_role"] for r in case_rows} != {"q01", "q02", "q03", "q04"}:
            errors.append(f"Not four distinct roles: {case_id}")
    missing_cases = packet_cases - set(by_case)
    unexpected_cases = set(by_case) - packet_cases
    if unexpected_cases:
        errors.append(f"Cases absent from packet: {sorted(unexpected_cases)}")
    if args.require_complete and missing_cases:
        errors.append(f"Missing source-packet cases: {sorted(missing_cases)}")
    q01_ids = {r["query_id"] for r in rows if r["query_role"] == "q01"}
    if len(prefixes) != len(q01_ids) or {p["query_id"] for p in prefixes} != q01_ids:
        errors.append("Missing/duplicate q01 prefix evidence")
    for p in prefixes:
        if not 1 <= p["group_ready_grapheme"] <= p["entity_ready_grapheme"] <= p["full_graphemes"]:
            errors.append(f"Invalid prefix boundary: {p['query_id']}")
    entity_ready_at_full = sum(p["entity_ready_grapheme"] == p["full_graphemes"] for p in prefixes)
    if len(qrels) < len(rows):
        errors.append("Fewer qrels than query sessions")
    if len(by_qrel) != len(rows):
        errors.append("qrel_set_id not query-specific")
    for path in sorted((staging / "authored").glob("batch_*.jsonl")):
        review_path = path.with_name(path.stem + "_review.json")
        if not review_path.exists():
            errors.append(f"Missing review log: {review_path.name}")
    old_surfaces = {fold(x) for x in pq.read_table(OLD_GOLD, columns=["query_text"])["query_text"].to_pylist()}
    current_surfaces = {fold(x) for x in pq.read_table(CURRENT_GOLD, columns=["query_text"])["query_text"].to_pylist()}
    train_surfaces = {fold(x) for x in pq.read_table(TRAIN, columns=["query_text"])["query_text"].to_pylist()}
    published_train_surfaces = {fold(row["query_text"]) for row in published_train}
    old_overlap = [r["query_id"] for r in rows if fold(r["query_text"]) in old_surfaces]
    train_overlap = [r["query_id"] for r in rows if fold(r["query_text"]) in train_surfaces]
    published_train_overlap = [r["query_id"] for r in rows if fold(r["query_text"]) in published_train_surfaces]
    if old_overlap:
        errors.append(f"Fold overlap with historical Gold v1: {old_overlap[:12]}")
    if train_overlap:
        errors.append(f"Fold overlap with locked train-500: {train_overlap[:12]}")
    if published_train_overlap:
        errors.append(f"Fold overlap with published train-5k: {published_train_overlap[:12]}")
    tags = Counter(tag for row in rows for tag in row["coverage_tags"])
    role_difficulty = Counter(f"{r['query_role']}:{r['difficulty']}" for r in rows)
    noisy_count = sum(r["query_role"] != "q01" for r in rows)
    space_split_count = sum("space_split_inside_token" in r["coverage_tags"] for r in rows)
    space_merge_count = sum("space_merge" in r["coverage_tags"] for r in rows)
    if noisy_count >= 20 and space_split_count > max(2, noisy_count // 10):
        errors.append(f"Inside-token space error overrepresented: {space_split_count}/{noisy_count}")
    by_id = {r["query_id"]: r for r in rows}
    q02_same_as_q01_fold = sum(
        fold(next(r for r in cases if r["query_role"] == "q01")["query_text"])
        == fold(next(r for r in cases if r["query_role"] == "q02")["query_text"])
        for cases in by_case.values()
    )
    coverage_path = draft / "coverage_diagnostic.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else None
    coverage_gaps = coverage.get("unmet_explicit_tag_gates", []) if coverage else ["coverage_report_missing"]
    adjudication_path = staging / "coverage_shortfall_adjudication_v1.json"
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8")) if adjudication_path.exists() else None
    accepted_shortfall = None
    if adjudication and coverage:
        requirement = next((r for r in coverage["requirements"]
                            if r["id"] == adjudication.get("requirement_id")), None)
        if (adjudication.get("status") == "accepted" and requirement
                and requirement["minimum"] == adjudication.get("minimum")
                and requirement["explicit_tag_rows"] == adjudication.get("actual_explicit_tag_rows")
                and adjudication.get("decision_source") == "user_instruction_in_conversation"
                and adjudication.get("reason")):
            accepted_shortfall = adjudication["requirement_id"]
            coverage_gaps = [gap for gap in coverage_gaps if gap != accepted_shortfall]
    coverage_evidence_errors = coverage.get("tag_evidence_errors", []) if coverage else []
    name_street_path = draft / "name_street_no_house_coverage.json"
    name_street = json.loads(name_street_path.read_text(encoding="utf-8")) if name_street_path.exists() else None
    exception_path = staging / "name_street_exceptions_adjudication_v1.json"
    exception_decision = json.loads(exception_path.read_text(encoding="utf-8")) if exception_path.exists() else None
    accepted_name_street_exceptions = None
    if exception_decision and name_street:
        requested = sorted(set(name_street.get("needs_adjudication_cases", [])))
        approved = sorted(set(exception_decision.get("case_ids", [])))
        if (exception_decision.get("status") == "accepted"
                and exception_decision.get("decision_source") == "user_instruction_in_conversation"
                and exception_decision.get("source_packet_sha256") == manifest["packet_sha256"]
                and exception_decision.get("reason") and requested == approved):
            accepted_name_street_exceptions = approved
    signoff_path = draft / "quality_signoff.json"
    signoff = json.loads(signoff_path.read_text(encoding="utf-8")) if signoff_path.exists() else None
    manual_signoff = bool(signoff and signoff.get("status") == "approved"
                          and signoff.get("packet_sha256") == manifest["packet_sha256"]
                          and signoff.get("session_parquet_sha256") == sha256(draft / "query_sessions_v2_1_draft.parquet")
                          and signoff.get("qrels_parquet_sha256") == sha256(draft / "qrels_v2_1_draft.parquet")
                          and signoff.get("mutation_traces_sha256") == sha256(draft / "mutation_traces_v2_1_draft.jsonl")
                          and signoff.get("coverage_diagnostic_sha256") == sha256(coverage_path)
                          and signoff.get("name_street_coverage_sha256") == sha256(name_street_path))
    release_blockers = []
    if coverage_gaps:
        release_blockers.append(f"Coverage evidence pending for requirements: {coverage_gaps}")
    if coverage_evidence_errors:
        release_blockers.append(f"Coverage tags lack trace evidence: {coverage_evidence_errors[:12]}")
    if not name_street:
        release_blockers.append("Name-plus-street no-house coverage report missing")
    elif name_street.get("tag_validation_errors"):
        release_blockers.append(f"Name-plus-street tag validation errors: {name_street['tag_validation_errors'][:12]}")
    elif name_street.get("unresolved_cases") or (
        name_street.get("needs_adjudication_cases") and accepted_name_street_exceptions is None
    ):
        release_blockers.append("Name-plus-street no-house exceptions need adjudication: "
                                f"{name_street.get('unresolved_cases', []) + name_street.get('needs_adjudication_cases', [])}")
    if prefixes and entity_ready_at_full == len(prefixes):
        release_blockers.append("All q01 entity_ready boundaries equal full query; source-backed prefix review pending")
    if not manual_signoff:
        release_blockers.append("Hash-bound manual quality signoff missing")
    result = {
        "verdict": "FAIL" if errors else "PASS" if not missing_cases else "PARTIAL_PASS",
        "mechanical_gate_pass": not errors and not missing_cases,
        "ready_for_lock": not errors and not missing_cases and not release_blockers,
        "release_blockers": release_blockers,
        "accepted_coverage_shortfall": accepted_shortfall,
        "accepted_name_street_exceptions": accepted_name_street_exceptions,
        "cases": len(by_case), "query_rows": len(rows), "qrel_rows": len(qrels),
        "missing_cases": sorted(missing_cases),
        "q01_prefix_evidence_rows": len(prefixes),
        "q01_entity_ready_at_full_rows": entity_ready_at_full,
        "old_gold_v1_fold_overlap": old_overlap,
        "current_gold_v2_fold_overlap_count": sum(fold(r["query_text"]) in current_surfaces for r in rows),
        "train500_fold_overlap": train_overlap,
        "published_train5k_fold_overlap": published_train_overlap,
        "published_train5k_rows": len(published_train),
        "published_train5k_sha256": sha256(PUBLISHED_TRAIN),
        "locked_gold_v2_manifest_sha256": sha256(old_manifest_path),
        "q02_same_as_q01_after_accent_fold": q02_same_as_q01_fold,
        "noisy_query_rows": noisy_count,
        "space_split_inside_token_rows": space_split_count,
        "space_merge_rows": space_merge_count,
        "role_difficulty": dict(role_difficulty),
        "coverage_tags": dict(tags),
        "pinned_train_target_source": str(pinned_train.relative_to(ROOT)) if pinned_train else None,
        "current_train_target_version": current_train_manifest.get("version"),
        "errors": errors,
        "note": "Mechanical audit only; naturalness and entity-equivalence require manual review.",
    }
    (draft / "independent_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("verdict", "ready_for_lock", "cases", "query_rows", "qrel_rows",
                                              "old_gold_v1_fold_overlap", "train500_fold_overlap",
                                              "q02_same_as_q01_after_accent_fold", "errors")}, ensure_ascii=False))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
