#!/usr/bin/env python3
"""Expand manually authored compact Stage-1 v6 specs without inventing query text."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stage1_v6_common import GENERATOR_VERSION, SLOT_SPECS


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def expand(spec_path: Path, packet_path: Path, rows_path: Path, trace_path: Path) -> tuple[int, int]:
    packet = {row["case_id"]: row for row in read_jsonl(packet_path)}
    authored: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for spec in read_jsonl(spec_path):
        case_id = str(spec["case_id"])
        context = packet[case_id]
        target = context["target"]
        canonical = str(spec["v01"])
        queries = {
            slot: str(spec[slot])
            if slot in {"v01", "v02"}
            else str(spec[slot]["query_text"])
            for slot in SLOT_SPECS
        }
        acceptable = spec.get("acceptable_poi_ids") or [target["poi_id"]]
        language_tag = str(spec.get("language_tag", "lang_vi"))
        for slot, contract in SLOT_SPECS.items():
            if slot == "v01":
                subtype = "canonical_anchor"
            elif slot == "v02":
                subtype = "standalone_or_natural_address"
            else:
                subtype = str(spec[slot]["variant_subtype"])
            slot_tag = (
                "canonical_anchor" if slot == "v01" else
                str(spec.get("v02_slot_tag", "standalone_name")) if slot == "v02" else
                "controlled_compound"
            )
            authored.append({
                "case_id": case_id,
                "variant_id": f"{case_id}-{slot}",
                "query_text": queries[slot],
                "canonical_query": canonical,
                "query_variant_family": contract["family"],
                "variant_operator": contract["operator"],
                "variant_subtype": subtype,
                "severity": contract["severity"],
                "query_types": f"{target['primary_sampling_stratum']}|{slot_tag}|{language_tag}",
                "intended_poi_id": target["poi_id"],
                "acceptable_poi_ids": acceptable,
                "primary_sampling_stratum": target["primary_sampling_stratum"],
                "review_status": "authored",
                "generator_version": GENERATOR_VERSION,
                "n_acceptable": len(acceptable),
                "is_multipositive": len(acceptable) > 1,
            })
        for slot in ("v03", "v04", "v05", "v06"):
            item = spec[slot]
            parent_slot = str(item.get("parent_slot", "v02"))
            traces.append({
                "variant_id": f"{case_id}-{slot}",
                "parent_variant_id": f"{case_id}-{parent_slot}",
                "error_tags": item["error_tags"],
                "affected_spans": item["affected_spans"],
                "before_text": queries[parent_slot],
                "after_text": queries[slot],
                "reviewer_status": str(item.get("reviewer_status", "authored")),
            })
    dump_jsonl(rows_path, authored)
    dump_jsonl(trace_path, traces)
    return len(authored), len(traces)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--rows-output", type=Path, required=True)
    parser.add_argument("--trace-output", type=Path, required=True)
    args = parser.parse_args()
    print(*expand(args.spec, args.packet, args.rows_output, args.trace_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
