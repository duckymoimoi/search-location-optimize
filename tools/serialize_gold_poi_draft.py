"""Serialize compact manually authored Gold v2.1 cases into draft artifacts.

Input: staging/gold_poi_draft/authored/batch_*.jsonl, one object per case.
This never writes to either locked Gold release and never uses model results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_poi_draft"
CORPUS = ROOT / "data/vietnam/poi_corpus_v3/pois_core.parquet"
SCHEMA = ROOT / "docs/specs/schemas/stage1_evaluation_v2.schema.json"
VERSION = "stage1-eval-suite-v2"
ROLES = ("q01", "q02", "q03", "q04")
DIFFICULTIES = {"clean", "mild", "compound", "challenge"}
STATUSES = {"accepted", "needs_review"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def graphemes(value: str) -> list[str]:
    chars: list[str] = []
    for ch in unicodedata.normalize("NFC", value):
        if chars and unicodedata.combining(ch):
            chars[-1] += ch
        else:
            chars.append(ch)
    return chars


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def mutation_points(evidence: list[str]) -> set[str]:
    """Count unique before→after spans, not multiple labels for one edit."""
    points = set()
    for item in evidence:
        text = str(item)
        if "→" not in text:
            raise ValueError(f"Malformed mutation evidence: {text}")
        before_after = text.split(":", 1)[1].strip() if ":" in text else text.strip()
        before, after = (part.strip() for part in before_after.split("→", 1))
        if not before or not after:
            raise ValueError(f"Empty mutation span: {text}")
        if normalized(before) == normalized(after):
            raise ValueError(f"No-op mutation span: {text}")
        points.add(before_after)
    return points


def prefix_index(full: str, prefix: str, label: str) -> int:
    normalized_full = unicodedata.normalize("NFC", full)
    normalized_prefix = unicodedata.normalize("NFC", prefix)
    if not normalized_prefix or not normalized_full.startswith(normalized_prefix):
        raise ValueError(f"{label} must be a nonempty exact prefix of q01")
    return len(graphemes(normalized_prefix))


def schema_part(full: dict, name: str) -> dict:
    return {"$schema": full["$schema"], "$defs": full["$defs"],
            **full["$defs"][name]}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False)
                             if isinstance(value, list) else value
                             for key, value in row.items()})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, default=STAGING)
    args = parser.parse_args()
    staging = args.staging
    packet_path = staging / "authoring_packet.jsonl"
    packet_manifest = json.loads((staging / "authoring_packet_manifest.json").read_text(encoding="utf-8"))
    if sha256(packet_path) != packet_manifest["packet_sha256"]:
        raise SystemExit("Packet hash mismatch; rebuild/review packet before serialization")
    cards = {row["case_id"]: row for row in
             (json.loads(line) for line in packet_path.read_text(encoding="utf-8").splitlines())}
    live_ids = set(pq.read_table(CORPUS, columns=["poi_id"])["poi_id"].to_pylist())
    full_schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    session_schema = schema_part(full_schema, "poiQuerySession")
    qrel_schema = schema_part(full_schema, "evaluationQrel")
    authored_paths = sorted((staging / "authored").glob("batch_*.jsonl"))
    if not authored_paths:
        raise SystemExit("No authored/batch_*.jsonl files")
    authored: dict[str, dict] = {}
    for path in authored_paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            case_id = row["case_id"]
            if case_id not in cards:
                raise ValueError(f"Unknown case {case_id} in {path}:{line_no}")
            if case_id in authored:
                raise ValueError(f"Duplicate authored case {case_id}")
            authored[case_id] = row
    sessions: list[dict] = []
    qrels: list[dict] = []
    prefix_evidence: list[dict] = []
    mutation_traces: list[dict] = []
    review_queue: list[dict] = []
    for case_id in cards:
        if case_id not in authored:
            continue
        compact = authored[case_id]
        card = cards[case_id]
        if set(compact["queries"]) != set(ROLES):
            raise ValueError(f"{case_id}: expected q01–q04 exactly")
        poi_id = card["poi_id"]
        seen_texts: set[str] = set()
        for role in ROLES:
            row = compact["queries"][role]
            text = str(row["text"]).strip()
            difficulty = row["difficulty"]
            status = row["review_status"]
            tags = row["tags"]
            if not text or normalized(text) in seen_texts:
                raise ValueError(f"{case_id}/{role}: blank or duplicate query")
            seen_texts.add(normalized(text))
            if difficulty not in DIFFICULTIES or status not in STATUSES:
                raise ValueError(f"{case_id}/{role}: invalid difficulty/status")
            if not isinstance(tags, list) or len(set(tags)) != len(tags):
                raise ValueError(f"{case_id}/{role}: tags must be a unique list")
            if role != "q01":
                mutations = row.get("mutation_evidence")
                if not isinstance(mutations, list) or len(mutation_points(mutations)) < 2:
                    raise ValueError(f"{case_id}/{role}: at least two distinct mutation points required")
                if not any(str(item).startswith("early:") for item in mutations):
                    raise ValueError(f"{case_id}/{role}: first mutable identity token needs an early: trace")
                for tag in ("space_merge", "space_split_inside_token"):
                    if tag in tags and not any(str(item).startswith(tag + ":") for item in mutations):
                        raise ValueError(f"{case_id}/{role}: {tag} tag lacks trace evidence")
                mutation_traces.append({"query_id": f"{case_id}-{role}",
                                        "mutation_evidence": mutations})
            raw_positive = row["positives"]
            positives = [poi_id] if raw_positive == "target" else list(raw_positive)
            if not positives or len(set(positives)) != len(positives) or poi_id not in positives:
                raise ValueError(f"{case_id}/{role}: invalid positive set")
            if set(positives) - live_ids:
                raise ValueError(f"{case_id}/{role}: positive absent from corpus")
            evidence = row["qrel_evidence"]
            if not isinstance(evidence, list) or not evidence or any(not str(x).strip() for x in evidence):
                raise ValueError(f"{case_id}/{role}: qrel_evidence required")
            query_id = f"{case_id}-{role}"
            qrel_set_id = f"qrel_{query_id}"
            session = {
                "schema_version": VERSION,
                "record_type": "poi_query_session",
                "suite_id": "gold_stage1_v2",
                "query_id": query_id,
                "query_family_id": f"qfam_{case_id}",
                "case_id": case_id,
                "query_role": role,
                "query_text": text,
                "difficulty": difficulty,
                "coverage_tags": tags,
                "intended_poi_id": poi_id,
                "acceptable_poi_ids": positives,
                "entity_group_id": card["source"].get("entity_group_id"),
                "qrel_set_id": qrel_set_id,
                "primary_sampling_stratum": card["primary_sampling_stratum"],
                "case_origin": card["case_origin"],
                "exposure_class": card["exposure_class"],
                "review_status": status,
            }
            jsonschema.validate(session, session_schema)
            sessions.append(session)
            for accepted_id in positives:
                qrel = {
                    "schema_version": VERSION,
                    "record_type": "evaluation_qrel",
                    "suite_id": "gold_stage1_v2",
                    "qrel_set_id": qrel_set_id,
                    "target_type": "poi",
                    "target_id": accepted_id,
                    "label": "positive",
                    "relevance": 3,
                    "label_reason": "intended_entity" if accepted_id == poi_id else "entity_equivalent",
                    "evidence_source": evidence,
                }
                jsonschema.validate(qrel, qrel_schema)
                qrels.append(qrel)
            if status == "needs_review":
                review_queue.append({"case_id": case_id, "role": role,
                                     "reason": row.get("review_note") or "manual review pending"})
            if role == "q01":
                group = prefix_index(text, row["group_ready_prefix"], "group_ready_prefix")
                entity = prefix_index(text, row["entity_ready_prefix"], "entity_ready_prefix")
                if group > entity:
                    raise ValueError(f"{case_id}: group_ready after entity_ready")
                prefix_evidence.append({
                    "query_id": query_id,
                    "case_id": case_id,
                    "group_ready_grapheme": group,
                    "entity_ready_grapheme": entity,
                    "full_graphemes": len(graphemes(text)),
                    "group_ready_prefix": row["group_ready_prefix"],
                    "entity_ready_prefix": row["entity_ready_prefix"],
                    "review_note": row.get("prefix_review_note", ""),
                })
    draft = staging / "draft"
    draft.mkdir(parents=True, exist_ok=True)
    suite_root = ROOT / "data/vietnam/stage1_eval_suite_v2"
    registry = json.loads((suite_root / "suite_registry.json").read_text(encoding="utf-8"))
    release = suite_root / registry["active_gold_poi_release"]
    session_files = list(release.glob("query_sessions_*.parquet"))
    qrel_files = list(release.glob("qrels_*.parquet"))
    if len(session_files) != 1 or len(qrel_files) != 1:
        raise ValueError("Active Gold release must have exactly one sessions and one qrels schema source")
    session_schema_arrow = pq.read_schema(session_files[0])
    qrel_schema_arrow = pq.read_schema(qrel_files[0])
    pq.write_table(pa.Table.from_pylist(sessions, schema=session_schema_arrow), draft / "query_sessions_v2_1_draft.parquet")
    pq.write_table(pa.Table.from_pylist(qrels, schema=qrel_schema_arrow), draft / "qrels_v2_1_draft.parquet")
    write_csv(draft / "query_sessions_v2_1_draft.csv", sessions)
    with (draft / "prefix_evidence_v2_1_draft.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in prefix_evidence:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (draft / "mutation_traces_v2_1_draft.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in mutation_traces:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {
        "status": "draft_not_locked",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "packet_sha256": sha256(packet_path),
        "authored_cases": len(authored),
        "query_rows": len(sessions),
        "qrel_rows": len(qrels),
        "q01_prefix_evidence_rows": len(prefix_evidence),
        "mutation_trace_rows": len(mutation_traces),
        "difficulty_by_role": dict(Counter(f"{r['query_role']}:{r['difficulty']}" for r in sessions)),
        "coverage_tags": dict(Counter(tag for r in sessions for tag in r["coverage_tags"])),
        "review_queue": review_queue,
    }
    (draft / "draft_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("authored_cases", "query_rows", "qrel_rows",
                                               "q01_prefix_evidence_rows")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
