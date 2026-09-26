"""Find POI-train rows that are bare-brand singletons and should move to brand data."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from stage1_brand_query_v1_common import NAMESPACE_TOKENS, normalize_query, read_jsonl
from stage1_brand_v3_common import (
    GOLD_POI,
    MEMBERSHIP_V3,
    SPLITS_V1,
    TRAIN_BRAND_V3,
    TRAIN_V6,
    fold_text,
    load_v3_core,
    parse_id_list,
    remap_lookup,
    source_record,
    write_json,
)


def audit(
    train_csv: Path,
    membership_dir: Path,
    packet_path: Path,
    gold_dir: Path,
    output_dir: Path,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = read_jsonl(packet_path)
    composed = pd.read_parquet(membership_dir / "composed_poi_id_migration_v1_v3.parquet")
    v3_ids = set(load_v3_core()["poi_id"].astype(str))
    remap = remap_lookup(composed, v3_ids)
    allowed: dict[str, tuple[str, str, str]] = {}

    def add_allowed(text: str, family_id: str, canonical: str, namespace: str) -> None:
        allowed.setdefault(normalize_query(text), (family_id, canonical, namespace))
        allowed.setdefault(fold_text(text), (family_id, canonical, namespace))

    for row in packet:
        family_id = str(row["brand_family_id"])
        names = [str(row["brand_canonical"]), *list(row.get("verified_aliases") or [])]
        namespace = str(row["brand_namespace"])
        tokens = NAMESPACE_TOKENS.get(namespace, ())
        for name in names:
            add_allowed(name, family_id, name, namespace)
            for token in tokens:
                add_allowed(f"{name} {token}", family_id, name, namespace)
                add_allowed(f"{token} {name}", family_id, name, namespace)

    train = pd.read_csv(train_csv)
    gold_sessions = pd.read_parquet(gold_dir / "query_sessions_v2_1.parquet")
    gold_norm = {normalize_query(text) for text in gold_sessions["query_text"].astype(str)}
    gold_fold = {fold_text(text) for text in gold_sessions["query_text"].astype(str)}

    hits: list[dict] = []
    for raw in train.to_dict("records"):
        query = str(raw["query_text"])
        norm = normalize_query(query)
        folded = fold_text(query)
        match = allowed.get(norm) or allowed.get(folded)
        if not match:
            continue
        family_id, canonical, namespace = match
        intended = str(raw["intended_poi_id"])
        dest, action, _ = remap.get(intended, (None, "no_map", ""))
        hits.append(
            {
                "case_id": str(raw["case_id"]),
                "variant_id": str(raw["variant_id"]),
                "query_text": query,
                "brand_family_id": family_id,
                "brand_canonical": canonical,
                "intended_poi_id": intended,
                "mapped_poi_id": dest or "",
                "mapping_action": action,
                "acceptable_count": len(parse_id_list(raw.get("acceptable_poi_ids"))),
                "gold_norm_overlap": norm in gold_norm,
                "gold_fold_overlap": folded in gold_fold,
                "decision": "handoff_or_exclude_singleton",
            }
        )

    by_family = defaultdict(int)
    for row in hits:
        by_family[row["brand_family_id"]] += 1
    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "sources": {
            "train_v6": source_record(train_csv),
            "packet_v3": source_record(packet_path),
            "membership_v3": source_record(membership_dir / "manifest.json"),
        },
        "stats": {
            "train_rows": int(len(train)),
            "bare_brand_rows": len(hits),
            "bare_brand_cases": len({row["case_id"] for row in hits}),
            "families": len(by_family),
            "gold_norm_collisions": sum(1 for row in hits if row["gold_norm_overlap"]),
        },
        "rows": hits,
        "note": "Do not rewrite published train v6 in bulk. Review each proven singleton before handoff.",
    }
    write_json(output_dir / "bare_brand_poi_train_audit.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-csv", type=Path, default=TRAIN_V6 / "query_variants.csv")
    parser.add_argument("--membership-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--packet", type=Path, default=TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl")
    parser.add_argument("--gold-dir", type=Path, default=GOLD_POI)
    parser.add_argument("--output-dir", type=Path, default=SPLITS_V1)
    args = parser.parse_args()
    report = audit(args.train_csv, args.membership_dir, args.packet, args.gold_dir, args.output_dir)
    print(json.dumps({key: report[key] for key in ("stats", "note")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
