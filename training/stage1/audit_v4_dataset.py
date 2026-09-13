"""Read-only integrity audit for the hnq20k-pilot-v4 bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("ᴄ", "c").replace("Ｃ", "C").replace("ｃ", "c")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/]+", " ", text.lower())).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.bundle)
    manifest = read_json(root / "dataset_manifest.json")

    file_checks: dict[str, bool] = {}
    for item in manifest["files"]:
        path = root / item["path"]
        file_checks[item["path"]] = bool(
            path.exists()
            and path.stat().st_size == item["bytes"]
            and sha256(path) == item["sha256"]
        )

    rows = pq.read_table(root / "queries_20k.parquet").to_pylist()
    by_id = {row["query_id"]: row for row in rows}
    old_rows_preserved = True
    with (root / "source_v3" / "queries_10k.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            old = json.loads(line)
            current = by_id.get(old["query_id"])
            if current is None or any(current[key] != value for key, value in old.items()):
                old_rows_preserved = False
                break

    jsonl_parity = True
    with (root / "queries_20k.jsonl").open(encoding="utf-8") as stream:
        for expected, line in zip(rows, stream, strict=True):
            if json.loads(line) != expected:
                jsonl_parity = False
                break

    split_files: dict[str, bool] = {}
    for split in ("train", "dev_synthetic", "test_synthetic", "architecture_holdout"):
        split_rows = pq.read_table(root / f"{split}.parquet").to_pylist()
        split_files[split] = [row["query_id"] for row in split_rows] == [
            row["query_id"] for row in rows if row["split"] == split
        ]

    overlay_rows = pq.read_table(root / "eligibility_v4.parquet").to_pylist()
    overlay = {row["query_id"]: row for row in overlay_rows}
    overlay_complete = len(overlay) == len(rows) and set(overlay) == set(by_id)
    overlay_matches = overlay_complete and all(
        row["split"] == overlay[row["query_id"]]["split"]
        and row["supervised_training_eligible"]
        == overlay[row["query_id"]]["supervised_training_eligible"]
        and row["main_metric_candidate"]
        == overlay[row["query_id"]]["main_metric_candidate"]
        for row in rows
    )
    eligible_rows = pq.read_table(root / "train_eligible_v4.parquet").to_pylist()
    eligible_ids = [row["query_id"] for row in eligible_rows]
    train_eligible_matches = eligible_ids == [
        row["query_id"]
        for row in rows
        if overlay[row["query_id"]]["supervised_training_eligible"]
    ]

    corpus = pq.read_table(
        root / "corpus_search_view.parquet",
        columns=["canonical_id", "destination_searchable", "entity_group_id"],
    ).to_pylist()
    corpus_by_id = {row["canonical_id"]: row for row in corpus}
    split_disjoint: dict[str, bool] = {}
    splits = sorted({row["split"] for row in rows})
    for field in ("intended_poi_id", "query_family_id", "leakage_group_id"):
        values = {
            split: {row[field] for row in rows if row["split"] == split}
            for split in splits
        }
        split_disjoint[field] = all(
            not values[left] & values[right]
            for index, left in enumerate(splits)
            for right in splits[index + 1 :]
        )
    entities = {
        split: {
            corpus_by_id[row["intended_poi_id"]]["entity_group_id"]
            for row in rows
            if row["split"] == split
        }
        for split in splits
    }
    split_disjoint["entity_group_id"] = all(
        not entities[left] & entities[right]
        for index, left in enumerate(splits)
        for right in splits[index + 1 :]
    )

    compatible_contract = all(
        row["intended_poi_id"] in row["known_compatible_poi_ids"]
        and row["compatible_count"] == len(row["known_compatible_poi_ids"])
        for row in rows
    )
    eligible_safe = all(
        row["split"] == "train"
        and row["track"] == "retrieval_core"
        and row["query_surface"] == "committed_text"
        and row["compatible_count"] == 1
        and not row["cross_split_compatible"]
        and not row["normalized_query_cross_split"]
        for row in eligible_rows
    )

    normalized_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        normalized_splits[normalized(row["query"])].add(row["split"])
    duplicate_normalized_cross_split = sum(
        len(normalized_splits[normalized(row["query"])]) > 1 for row in rows
    )
    normalized_overlay_flags_match = all(
        overlay[row["query_id"]]["normalized_query_cross_split"]
        == (len(normalized_splits[normalized(row["query"])]) > 1)
        for row in rows
    )
    v4_row_flags_match_overlay = all(
        row["normalized_query_cross_split"]
        == overlay[row["query_id"]]["normalized_query_cross_split"]
        for row in rows
        if row["dataset_version"] == manifest["dataset_version"]
    )
    immutable_v3_flag_differences = sum(
        row["normalized_query_cross_split"]
        != overlay[row["query_id"]]["normalized_query_cross_split"]
        for row in rows
        if row["dataset_version"] != manifest["dataset_version"]
    )

    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in pq.read_table(root / "typing_sessions.parquet").to_pylist():
        sessions[event["session_id"]].append(event)
    session_checks = True
    session_splits: Counter[str] = Counter()
    for events in sessions.values():
        events.sort(key=lambda row: row["event_index"])
        replay = ""
        for index, event in enumerate(events, start=1):
            replay += event["input_event"].lower()
            session_checks &= bool(
                event["event_index"] == index
                and event["keystroke_index"] == index
                and event["query"] == replay
            )
        session_checks &= bool(
            len({event["split"] for event in events}) == 1
            and len({event["intended_poi_id"] for event in events}) == 1
            and events[-1]["is_final"]
            and not any(event["is_final"] for event in events[:-1])
        )
        session_splits[events[0]["split"]] += 1

    audit = {
        "bundle_version": manifest["dataset_version"],
        "passed": bool(
            all(file_checks.values())
            and len(rows) == manifest["rows"] == 20_000
            and len(by_id) == len(rows)
            and len({(row["query"], row["intended_poi_id"]) for row in rows})
            == len(rows)
            and old_rows_preserved
            and jsonl_parity
            and all(split_files.values())
            and overlay_matches
            and train_eligible_matches
            and all(split_disjoint.values())
            and compatible_contract
            and eligible_safe
            and normalized_overlay_flags_match
            and v4_row_flags_match_overlay
            and session_checks
        ),
        "manifest_files": len(file_checks),
        "manifest_hashes_pass": all(file_checks.values()),
        "rows": len(rows),
        "split_counts": dict(Counter(row["split"] for row in rows)),
        "track_split_counts": {
            split: dict(Counter(row["track"] for row in rows if row["split"] == split))
            for split in splits
        },
        "record_source_versions": dict(Counter(row["dataset_version"] for row in rows)),
        "targets": len({row["intended_poi_id"] for row in rows}),
        "old_rows_preserved": old_rows_preserved,
        "jsonl_parity": jsonl_parity,
        "split_files_match": split_files,
        "overlay_complete_and_matches": overlay_matches,
        "train_eligible_rows": len(eligible_rows),
        "train_eligible_matches_overlay": train_eligible_matches,
        "train_eligible_contract_safe": eligible_safe,
        "split_disjoint": split_disjoint,
        "known_compatible_contract": compatible_contract,
        "duplicate_normalized_queries_cross_split": duplicate_normalized_cross_split,
        "normalized_overlay_flags_match": normalized_overlay_flags_match,
        "v4_row_flags_match_overlay": v4_row_flags_match_overlay,
        "immutable_v3_row_flag_differences": immutable_v3_flag_differences,
        "typing_sessions": len(sessions),
        "typing_events": sum(map(len, sessions.values())),
        "typing_session_splits": dict(session_splits),
        "typing_sessions_replay": session_checks,
        "holdout_model_evaluated_by_this_audit": False,
    }
    if args.output:
        Path(args.output).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not audit["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
