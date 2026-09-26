"""Compile a v3 authoring packet from locked membership v3 and packet v2 metadata."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from stage1_brand_query_v1_common import read_jsonl
from stage1_brand_v3_common import (
    LOOKUP_VERSION,
    MEMBERSHIP_V3,
    MEMBERSHIP_VIEW_VERSION,
    PACKET_V2,
    TRAIN_BRAND_V3,
    GROUP_VERSION,
    pool_hash,
    refuse_nonempty,
    sha256_file,
    source_record,
    write_json,
)


PACKET_VERSION = "brand_authoring_packet_v3"


def accepted_by_group(members: pd.DataFrame) -> dict[str, list[str]]:
    accepted = members[members["membership_status"] == "accepted"]
    pools: dict[str, set[str]] = defaultdict(set)
    for row in accepted.itertuples(index=False):
        pools[str(row.brand_group_id)].add(str(row.poi_id))
    return {key: sorted(values) for key, values in pools.items()}


def build(membership_dir: Path, packet_v2: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    members = pd.read_parquet(membership_dir / "brand_group_members_v3.parquet")
    pools = accepted_by_group(members)
    source_rows = read_jsonl(packet_v2)
    output_rows: list[dict] = []
    empty: list[str] = []
    for row in source_rows:
        group_ids = [str(row["brand_group_id"]), *list(row.get("merged_source_intents") or [])]
        positive: list[str] = []
        seen: set[str] = set()
        evidence: dict[str, int] = defaultdict(int)
        for group_id in group_ids:
            for poi_id in pools.get(group_id, []):
                if poi_id in seen:
                    continue
                seen.add(poi_id)
                positive.append(poi_id)
        if not positive:
            empty.append(str(row["intent_id"]))
            continue
        sub = members[
            (members["membership_status"] == "accepted")
            & (members["brand_group_id"].isin(group_ids))
        ]
        for value in sub["membership_evidence"].astype(str):
            evidence[value] += 1
        out = dict(row)
        out["packet_version"] = PACKET_VERSION
        out["positive_poi_ids"] = positive
        out["n_positive"] = len(positive)
        out["positive_pool_sha256"] = pool_hash(positive)
        out["membership_evidence_counts"] = dict(sorted(evidence.items()))
        out["membership_review_counts"] = {"accepted": len(positive)}
        out["group_version"] = GROUP_VERSION
        out["lookup_version"] = LOOKUP_VERSION
        out["membership_view_version"] = MEMBERSHIP_VIEW_VERSION
        out["authoring_status"] = "ready"
        output_rows.append(out)

    packet_path = output_dir / "brand_authoring_packet_v3.jsonl"
    with packet_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in output_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    manifest = {
        "dataset": "train_stage1_brand_queries_v3_authoring_packet",
        "packet_version": PACKET_VERSION,
        "status": "READY_FOR_COMPILE",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "sources": {
            "packet_v2": source_record(packet_v2),
            "membership_v3": source_record(membership_dir / "manifest.json"),
        },
        "stats": {
            "packet_rows": len(output_rows),
            "families": len({row["brand_family_id"] for row in output_rows}),
            "positive_members": sum(int(row["n_positive"]) for row in output_rows),
            "empty_intents_dropped": empty,
        },
        "output": {"path": str(packet_path.as_posix()), "sha256": sha256_file(packet_path)},
    }
    write_json(output_dir / "authoring_packet_manifest_v3.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--membership-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--packet-v2", type=Path, default=PACKET_V2)
    parser.add_argument("--output-dir", type=Path, default=TRAIN_BRAND_V3)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args()
    if not args.allow_existing:
        refuse_nonempty(args.output_dir)
    print(
        json.dumps(
            build(args.membership_dir, args.packet_v2, args.output_dir),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
