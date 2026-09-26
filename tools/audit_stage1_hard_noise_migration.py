#!/usr/bin/env python3
"""Audit reusable clean slots before migrating Stage-1 v6 to hard-noise v03-v06."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from stage1_v6_common import normalize_query, read_jsonl


def audit(rows_path: Path, target_path: Path, output_path: Path) -> dict[str, int]:
    rows_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in read_jsonl(rows_path):
        rows_by_case[str(row["case_id"])].append(row)
    target_rows = pq.read_table(target_path).to_pylist()
    queue: list[dict[str, Any]] = []
    reusable = 0
    for target in target_rows:
        case_id = str(target["case_id"])
        slots = {
            str(row["variant_id"])[-3:]: row for row in rows_by_case.get(case_id, [])
        }
        reasons: list[str] = []
        v01 = slots.get("v01")
        v02 = slots.get("v02")
        if not v01 or not v02:
            reasons.append("missing_clean_slot")
        else:
            official = normalize_query(target.get("name"))
            if official and official not in normalize_query(v01.get("query_text")):
                reasons.append("v01_missing_official_name")
            if any(
                str(row.get("canonical_query")) != str(v01.get("query_text"))
                for row in slots.values()
            ):
                reasons.append("canonical_query_stale")
            if str(v01.get("intended_poi_id")) != str(target["poi_id"]):
                reasons.append("intended_poi_mismatch")
            if str(v02.get("query_text")) == str(v01.get("query_text")):
                reasons.append("v01_v02_duplicate")
            if "." in str(v02.get("query_text")):
                reasons.append("v02_contains_period")
            acceptable = [str(value) for value in v02.get("acceptable_poi_ids") or []]
            if str(target["poi_id"]) not in acceptable:
                reasons.append("v02_qrels_missing_target")
        can_reuse = not reasons
        reusable += int(can_reuse)
        queue.append(
            {
                "case_id": case_id,
                "poi_id": str(target["poi_id"]),
                "reuse_v01_v02": can_reuse,
                "clean_slot_repair_reasons": reasons,
                "v01": None if v01 is None else v01.get("query_text"),
                "v02": None if v02 is None else v02.get("query_text"),
                "acceptable_poi_ids": []
                if v02 is None
                else v02.get("acceptable_poi_ids", []),
                "required_work": "reauthor_v03_v06_hard_noise",
            }
        )
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in queue),
        encoding="utf-8",
    )
    return {
        "target_cases": len(target_rows),
        "reusable_v01_v02": reusable,
        "repair_v01_v02": len(target_rows) - reusable,
        "reauthor_v03_v06": len(target_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.rows, args.target, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
