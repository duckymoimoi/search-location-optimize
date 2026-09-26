"""Expand manually authored compact brand-query specs into the locked schema.

The input must already contain every ``query_text``.  This tool only copies
packet metadata and deterministic operator labels; it never invents query text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stage1_brand_query_v1_common import (
    GENERATOR_VERSION,
    OPERATOR_SPECS,
    QUERY_COLUMNS,
    read_jsonl,
)


def expand(spec_path: Path, packet_path: Path, output_path: Path) -> int:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite batch: {output_path}")
    specs = read_jsonl(spec_path)
    packet_rows = read_jsonl(packet_path)
    packet_by_id = {str(row["intent_id"]): row for row in packet_rows}
    packet_index = {
        str(row["intent_id"]): int(row.get("intent_index", index))
        for index, row in enumerate(packet_rows, start=1)
    }
    output: list[dict] = []
    seen_intents: set[str] = set()
    for spec in specs:
        intent_id = str(spec["intent_id"])
        if intent_id in seen_intents:
            raise ValueError(f"Duplicate intent spec: {intent_id}")
        seen_intents.add(intent_id)
        packet = packet_by_id.get(intent_id)
        if packet is None:
            raise ValueError(f"Unknown intent: {intent_id}")
        intent_index = int(spec["intent_index"])
        if packet_index[intent_id] != intent_index:
            raise ValueError(f"Wrong packet index for {intent_id}: {intent_index}")
        variants = list(spec.get("variants") or [])
        canonical = [
            variant
            for variant in variants
            if variant.get("variant_operator") == "brand_canonical"
        ]
        if len(canonical) != 1:
            raise ValueError(f"{intent_id}: expected one brand_canonical variant")
        canonical_query = str(canonical[0]["query_text"])
        for variant_index, variant in enumerate(variants, start=1):
            operator = str(variant["variant_operator"])
            if operator not in OPERATOR_SPECS:
                raise ValueError(f"{intent_id}: unknown operator {operator}")
            family, severity = OPERATOR_SPECS[operator]
            row = {
                "query_id": f"brandq1-{intent_index:05d}-v{variant_index:02d}",
                "query_text": str(variant["query_text"]),
                "canonical_brand_query": canonical_query,
                "brand_family_id": str(packet["brand_family_id"]),
                "namespace_scope": list(packet["namespace_scope"]),
                "intent_scope": "BRAND",
                "intent_id": intent_id,
                "qrel_policy": "FAMILY_NAMESPACE",
                "query_variant_family": family,
                "variant_operator": operator,
                "severity": severity,
                "language_tag": str(variant["language_tag"]),
                "review_status": str(variant.get("review_status", "authored")),
                "generator_version": GENERATOR_VERSION,
            }
            if tuple(row) != QUERY_COLUMNS:
                raise AssertionError("Expanded query column order mismatch")
            output.append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(expand(args.spec, args.packet, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
