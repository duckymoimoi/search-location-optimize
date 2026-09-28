#!/usr/bin/env python3
"""Group-compatible brand metrics from an exact-dense ranking jsonl.

Each line needs query_id, brand_family_id, brand_group_id, query_role,
acceptable_poi_ids, and top_ids. Family means are the headline.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MEMBERSHIP = ROOT / "data/vietnam/train_stage1_brand_membership_v3/brand_group_members_v3.parquet"
KS = (1, 5, 10, 20, 50)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sibling_namespaces(members: pd.DataFrame) -> dict[str, set[str]]:
    accepted = members[members["membership_status"] == "accepted"]
    by_family: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in accepted.itertuples(index=False):
        by_family[str(row.brand_family_id)][str(row.brand_group_id)].add(str(row.poi_id))
    sibling: dict[str, set[str]] = {}
    for groups in by_family.values():
        all_ids = set().union(*groups.values()) if groups else set()
        for group_id, ids in groups.items():
            sibling[group_id] = all_ids - ids
    return sibling


def any_rank(ids: list[str], accepted: set[str]) -> int | None:
    return next((index for index, poi_id in enumerate(ids, start=1) if poi_id in accepted), None)


def coverage(ids: list[str], accepted: set[str], k: int) -> float:
    if not accepted:
        return 0.0
    return len(set(ids[:k]) & accepted) / len(accepted)


def family_mean(values_by_family: dict[str, list[float]]) -> float | None:
    means = [sum(values) / len(values) for values in values_by_family.values() if values]
    if not means:
        return None
    return sum(means) / len(means)


def score(rows: list[dict], sibling: dict[str, set[str]]) -> dict:
    hit_fams: dict[int, dict[str, list[float]]] = {k: defaultdict(list) for k in KS}
    mrr_fams: dict[str, list[float]] = defaultdict(list)
    cov_fams: dict[str, list[float]] = defaultdict(list)
    false_branch = 0
    namespace_n = 0
    for row in rows:
        accepted = set(str(poi_id) for poi_id in row["acceptable_poi_ids"])
        ids = [str(poi_id) for poi_id in row["top_ids"]]
        family_id = str(row["brand_family_id"])
        first = any_rank(ids, accepted)
        for k in KS:
            hit_fams[k][family_id].append(1.0 if first is not None and first <= k else 0.0)
        mrr_fams[family_id].append(1.0 / first if first is not None and first <= 10 else 0.0)
        cov_fams[family_id].append(coverage(ids, accepted, 20))
        if row.get("query_role") == "namespace_qualified":
            namespace_n += 1
            others = sibling.get(str(row["brand_group_id"]), set())
            if any(poi_id in others for poi_id in ids[:20]) and (first is None or first > 20):
                false_branch += 1
    return {
        "n_queries": len(rows),
        "n_families": len({str(row["brand_family_id"]) for row in rows}),
        "AnyCompatibleHit": {str(k): family_mean(hit_fams[k]) for k in KS},
        "group_MRR@10": family_mean(mrr_fams),
        "compatible_coverage@20": family_mean(cov_fams),
        "namespace_false_branch@20": (false_branch / namespace_n) if namespace_n else None,
        "namespace_n": namespace_n,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--membership", type=Path, default=MEMBERSHIP)
    args = parser.parse_args()
    members = pd.read_parquet(args.membership)
    report = score(load_jsonl(args.jsonl), sibling_namespaces(members))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
