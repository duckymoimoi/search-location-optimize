"""Compare fine-tuned and zero-shot E5 exact runs on identical stable-v1 rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def values(rows: list[dict]) -> dict[str, np.ndarray]:
    ranks = np.asarray([row["target_rank"] for row in rows])
    return {
        "hit_5": (ranks <= 5).astype(float), "hit_20": (ranks <= 20).astype(float),
        "hit_50": (ranks <= 50).astype(float),
        "mrr_10": np.where(ranks <= 10, 1 / ranks, 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finetuned", type=Path, required=True)
    parser.add_argument("--zeroshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260914)
    args = parser.parse_args()
    report = {"passage": "context", "similarity": "normalized dot product", "splits": {}}
    rng = np.random.default_rng(args.seed)
    for split in ("dev_synthetic", "test_synthetic", "architecture_holdout"):
        name = f"{split}_context_dense_exact_top100.parquet"
        tuned = pq.read_table(args.finetuned / name).to_pylist()
        zero = pq.read_table(args.zeroshot / name).to_pylist()
        if [r["query_id"] for r in tuned] != [r["query_id"] for r in zero]:
            raise ValueError(f"Rows do not align for {split}")
        split_result = {}
        slices = {
            "retrieval_core_main": [i for i, row in enumerate(tuned) if row["track"] == "retrieval_core" and row["main_metric_candidate"]],
            "autocomplete": [i for i, row in enumerate(tuned) if row["track"] == "autocomplete"],
            "ambiguity_diagnostic": [i for i, row in enumerate(tuned) if row["track"] == "ambiguity_stress"],
            "ime_keystream": [i for i, row in enumerate(tuned) if row["track"] == "ime_keystream"],
            "structured": [i for i, row in enumerate(tuned) if row["track"] == "structured_code" and row["structured_metric_candidate"]],
        }
        for label, indices in slices.items():
            if not indices:
                continue
            left_rows = [tuned[i] for i in indices]
            right_rows = [zero[i] for i in indices]
            left, right = values(left_rows), values(right_rows)
            result = {
                "count": len(indices),
                "finetuned": {metric: float(array.mean()) for metric, array in left.items()},
                "zeroshot": {metric: float(array.mean()) for metric, array in right.items()},
                "finetuned_minus_zeroshot": {metric: float(np.mean(left[metric] - right[metric])) for metric in left},
            }
            if split == "dev_synthetic":
                families = np.asarray([row["query_family_id"] for row in left_rows])
                groups = {family: np.flatnonzero(families == family) for family in sorted(set(families))}
                family_ids = list(groups)
                draws = {metric: [] for metric in left}
                for _ in range(args.samples):
                    chosen = rng.choice(family_ids, size=len(family_ids), replace=True)
                    sample = np.concatenate([groups[family] for family in chosen])
                    for metric in draws:
                        draws[metric].append(float(np.mean(left[metric][sample] - right[metric][sample])))
                result["dev_cluster_bootstrap_ci95"] = {
                    metric: [float(np.quantile(draw, .025)), float(np.quantile(draw, .975))]
                    for metric, draw in draws.items()
                }
            split_result[label] = result
        report["splits"][split] = split_result
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
