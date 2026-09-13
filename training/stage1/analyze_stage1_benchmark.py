"""Paired cluster bootstrap for selected Stage 1 branch comparisons on dev."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_stage1_branches import rrf  # noqa: E402


def rank(ids: list[str], target: str) -> int:
    try:
        return ids.index(target) + 1
    except ValueError:
        return len(ids) + 1


def arrays(rows: list[dict[str, Any]], field: str, track: str) -> dict[str, np.ndarray]:
    if track == "core":
        selected = [
            row
            for row in rows
            if row["track"] == "retrieval_core" and row["main_metric_candidate"]
        ]
        ranks = np.asarray([rank(row[field], row["intended_poi_id"]) for row in selected])
        return {
            "hit_5": (ranks <= 5).astype(float),
            "candidate_hit_20": (ranks <= 20).astype(float),
            "candidate_hit_50": (ranks <= 50).astype(float),
            "mrr_10": np.where(ranks <= 10, 1.0 / ranks, 0.0),
            "family": np.asarray([row["query_family_id"] for row in selected]),
        }
    selected = [row for row in rows if row["track"] == "autocomplete"]
    ranks = np.asarray([rank(row[field], row["intended_poi_id"]) for row in selected])
    return {
        "hit_5": (ranks <= 5).astype(float),
        "candidate_hit_20": (ranks <= 20).astype(float),
        "candidate_hit_50": (ranks <= 50).astype(float),
        "mrr_5": np.where(ranks <= 5, 1.0 / ranks, 0.0),
        "family": np.asarray([row["query_family_id"] for row in selected]),
    }


def compare(
    rows: list[dict[str, Any]],
    candidate_field: str,
    baseline_field: str,
    track: str,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    candidate = arrays(rows, candidate_field, track)
    baseline = arrays(rows, baseline_field, track)
    families = candidate.pop("family")
    baseline.pop("family")
    groups = {
        family: np.flatnonzero(families == family) for family in sorted(set(families))
    }
    family_ids = list(groups)
    rng = np.random.default_rng(seed)
    draws = {metric: [] for metric in candidate}
    for _ in range(samples):
        chosen = rng.choice(family_ids, size=len(family_ids), replace=True)
        indices = np.concatenate([groups[family] for family in chosen])
        for metric in draws:
            draws[metric].append(
                float(np.mean(candidate[metric][indices] - baseline[metric][indices]))
            )
    return {
        "track": track,
        "queries": len(families),
        "families": len(family_ids),
        "candidate": candidate_field,
        "baseline": baseline_field,
        "point_delta": {
            metric: float(np.mean(candidate[metric] - baseline[metric]))
            for metric in candidate
        },
        "ci95": {
            metric: [
                float(np.quantile(values, 0.025)),
                float(np.quantile(values, 0.975)),
            ]
            for metric, values in draws.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branches", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20_260_914)
    args = parser.parse_args()

    rows = pq.read_table(args.branches).to_pylist()
    for row in rows:
        row["hybrid_exact"] = rrf(
            row["L1_prefix_heavy_ids"], row["exact_dense_ids"], 50, 10
        )
        row["hybrid_ann"] = rrf(
            row["L1_prefix_heavy_ids"], row["ann_ids"], 50, 10
        )
    comparisons = {
        "method": "paired cluster bootstrap by query_family_id",
        "bootstrap_samples": args.samples,
        "holdout_evaluated": False,
        "core_lexical_vs_exact_dense": compare(
            rows, "L1_prefix_heavy_ids", "exact_dense_ids", "core", args.samples, args.seed
        ),
        "core_hybrid_exact_vs_lexical": compare(
            rows, "hybrid_exact", "L1_prefix_heavy_ids", "core", args.samples, args.seed
        ),
        "core_hybrid_ann_vs_hybrid_exact": compare(
            rows, "hybrid_ann", "hybrid_exact", "core", args.samples, args.seed
        ),
        "autocomplete_lexical_vs_exact_dense": compare(
            rows, "L1_prefix_heavy_ids", "exact_dense_ids", "autocomplete", args.samples, args.seed
        ),
        "autocomplete_lexical_vs_hybrid_exact": compare(
            rows, "L1_prefix_heavy_ids", "hybrid_exact", "autocomplete", args.samples, args.seed
        ),
    }
    Path(args.output).write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(comparisons, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
