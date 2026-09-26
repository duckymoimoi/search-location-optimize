"""Deterministic family-level train/dev/test split. Does not split queries or branches."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from stage1_brand_query_v1_common import read_jsonl
from stage1_brand_v3_common import (
    DEV_FAMILY_TARGET,
    LEFT_OVER_FAMILIES,
    MEMBERSHIP_V3,
    SPLIT_SEED,
    SPLIT_VERSION,
    SPLITS_V1,
    TEST_FAMILY_TARGET,
    TRAIN_BRAND_V3,
    family_stratum,
    refuse_nonempty,
    sha256_file,
    source_record,
    write_json,
)


def family_features(packet_rows: list[dict], members: pd.DataFrame) -> list[dict]:
    accepted = members[members["membership_status"] == "accepted"]
    counts = accepted.groupby("brand_family_id")["poi_id"].nunique().to_dict()
    namespaces = accepted.groupby("brand_family_id")["brand_namespace"].nunique().to_dict()
    features: list[dict] = []
    seen: set[str] = set()
    for row in packet_rows:
        family_id = str(row["brand_family_id"])
        if family_id in seen or family_id in LEFT_OVER_FAMILIES:
            continue
        seen.add(family_id)
        n_members = int(counts.get(family_id, 0))
        n_ns = int(namespaces.get(family_id, 1))
        canonical = str(row["brand_canonical"])
        features.append(
            {
                "brand_family_id": family_id,
                "brand_canonical": canonical,
                "n_accepted_v3": n_members,
                "n_namespaces": n_ns,
                "stratum": family_stratum(n_members, n_ns, canonical),
            }
        )
    if not features:
        raise ValueError("no families to split")
    return features


def allocate(features: list[dict], seed: int, n_test: int, n_dev: int) -> dict[str, str]:
    rng = random.Random(seed)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for row in features:
        by_stratum[row["stratum"]].append(row["brand_family_id"])
    assignment: dict[str, str] = {}
    remaining_test = n_test
    remaining_dev = n_dev
    strata = sorted(by_stratum)
    total = len(features)
    for stratum in strata:
        families = list(by_stratum[stratum])
        rng.shuffle(families)
        take_test = min(remaining_test, max(0, round(len(families) * n_test / total)))
        take_dev = min(remaining_dev, max(0, round(len(families) * n_dev / total)))
        if take_test + take_dev > len(families):
            take_dev = max(0, len(families) - take_test)
        for family_id in families[:take_test]:
            assignment[family_id] = "test"
        for family_id in families[take_test : take_test + take_dev]:
            assignment[family_id] = "dev"
        for family_id in families[take_test + take_dev :]:
            assignment[family_id] = "train"
        remaining_test -= take_test
        remaining_dev -= take_dev

    def refill(target: str, needed: int) -> None:
        if needed <= 0:
            return
        pool = [row["brand_family_id"] for row in features if assignment.get(row["brand_family_id"]) == "train"]
        rng.shuffle(pool)
        for family_id in pool[:needed]:
            assignment[family_id] = target

    refill("test", n_test - sum(1 for value in assignment.values() if value == "test"))
    refill("dev", n_dev - sum(1 for value in assignment.values() if value == "dev"))
    return assignment


def split(
    packet_path: Path,
    membership_dir: Path,
    output_dir: Path,
    *,
    seed: int = SPLIT_SEED,
    n_test: int = TEST_FAMILY_TARGET,
    n_dev: int = DEV_FAMILY_TARGET,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_rows = read_jsonl(packet_path)
    members = pd.read_parquet(membership_dir / "brand_group_members_v3.parquet")
    features = family_features(packet_rows, members)
    if n_test + n_dev >= len(features):
        raise ValueError("test+dev would consume the family pool")
    assignment = allocate(features, seed, n_test, n_dev)
    for row in features:
        row["split"] = assignment[row["brand_family_id"]]
    features.sort(key=lambda row: (row["split"], row["stratum"], row["brand_family_id"]))
    counts = Counter(row["split"] for row in features)
    strata = sorted({row["stratum"] for row in features})
    split_doc = {
        "split_version": SPLIT_VERSION,
        "seed": seed,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "policy": "Split by brand_family_id. Every namespace/alias/variant stays in the same split.",
        "targets": {"test": n_test, "dev": n_dev, "train": len(features) - n_test - n_dev},
        "counts": dict(counts),
        "families": features,
        "leftover_families_excluded": LEFT_OVER_FAMILIES,
    }
    write_json(output_dir / "family_split.json", split_doc)
    write_json(
        output_dir / "stratification_report.json",
        {
            "n_families": len(features),
            "n_strata": len(strata),
            "strata": {
                name: {
                    "n": sum(1 for row in features if row["stratum"] == name),
                    "by_split": dict(
                        Counter(row["split"] for row in features if row["stratum"] == name)
                    ),
                }
                for name in strata
            },
            "size_summary": {
                split_name: {
                    "n_families": counts[split_name],
                    "median_members": int(
                        pd.Series(
                            [row["n_accepted_v3"] for row in features if row["split"] == split_name]
                        ).median()
                    ),
                }
                for split_name in ("train", "dev", "test")
            },
        },
    )
    write_json(
        output_dir / "LOCKED.json",
        {
            "split_version": SPLIT_VERSION,
            "status": "locked",
            "locked_at_utc": datetime.now(UTC).isoformat(),
            "family_split_sha256": sha256_file(output_dir / "family_split.json"),
            "mutation_policy": "Do not reshuffle after Gold authoring starts.",
        },
    )
    return {
        "counts": dict(counts),
        "n_strata": len(strata),
        "family_split": source_record(output_dir / "family_split.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=TRAIN_BRAND_V3 / "brand_authoring_packet_v3.jsonl")
    parser.add_argument("--membership-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--output-dir", type=Path, default=SPLITS_V1)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args()
    if not args.allow_existing:
        refuse_nonempty(args.output_dir)
    print(json.dumps(split(args.packet, args.membership_dir, args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
