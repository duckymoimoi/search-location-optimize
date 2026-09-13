"""Audit downloaded Kaggle Stage 1 artifacts and compute paired uncertainty."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rank_metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    ranks = np.asarray([row["rank"] for row in rows], dtype=np.float64)
    return {
        "count": int(len(ranks)),
        "hit_1": float(np.mean(ranks <= 1)),
        "hit_5": float(np.mean(ranks <= 5)),
        "mrr_10": float(np.mean(np.where(ranks <= 10, 1.0 / ranks, 0.0))),
        "candidate_hit_20": float(np.mean(ranks <= 20)),
        "candidate_hit_50": float(np.mean(ranks <= 50)),
        "mean_rank": float(np.mean(ranks)),
        "median_rank": float(np.median(ranks)),
    }


def metric_arrays(rows: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    ranks = np.asarray([row["rank"] for row in rows], dtype=np.float64)
    return {
        "hit_1": (ranks <= 1).astype(np.float64),
        "mrr_10": np.where(ranks <= 10, 1.0 / ranks, 0.0),
        "candidate_hit_50": (ranks <= 50).astype(np.float64),
    }


def cluster_bootstrap(
    candidate: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    seed: int,
    samples: int,
) -> dict[str, Any]:
    if [row["query_id"] for row in candidate] != [row["query_id"] for row in baseline]:
        raise ValueError("Paired files do not contain the same ordered query IDs")
    candidate_values = metric_arrays(candidate)
    baseline_values = metric_arrays(baseline)
    families = np.asarray([row["query_family_id"] for row in candidate])
    groups = {
        family: np.flatnonzero(families == family)
        for family in sorted(set(families))
    }
    family_ids = list(groups)
    random_generator = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {metric: [] for metric in candidate_values}
    for _ in range(samples):
        selected_families = random_generator.choice(
            family_ids, size=len(family_ids), replace=True
        )
        indices = np.concatenate([groups[family] for family in selected_families])
        for metric in draws:
            delta = candidate_values[metric][indices] - baseline_values[metric][indices]
            draws[metric].append(float(np.mean(delta)))
    return {
        "queries": len(candidate),
        "query_families": len(family_ids),
        "bootstrap_samples": samples,
        "point_delta": {
            metric: float(np.mean(candidate_values[metric] - baseline_values[metric]))
            for metric in draws
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
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--executed-script")
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20_260_913)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    source_dir = Path(args.source_dir)
    ranks_dir = output_dir / "per_query_runs"
    selection = read_json(output_dir / "model_selection.json")
    manifest = read_json(output_dir / "final_model_manifest.json")
    preflight = read_json(output_dir / "input_manifest_verified.json")
    config = read_json(output_dir / "config_resolved.json")

    model_hashes = {
        relative: sha256(output_dir / "final_model" / relative) == expected
        for relative, expected in manifest["model_files"].items()
    }
    embeddings = np.load(output_dir / "corpus_embeddings.npy", mmap_mode="r")
    norms: list[float] = []
    finite = True
    for start in range(0, len(embeddings), 4096):
        chunk = np.asarray(embeddings[start : start + 4096])
        finite &= bool(np.isfinite(chunk).all())
        norms.extend(np.linalg.norm(chunk, axis=1).tolist())

    id_map = pq.read_table(output_dir / "corpus_id_map.parquet").to_pylist()
    corpus = [
        row
        for row in pq.read_table(
            source_dir / "corpus_search_view.parquet",
            columns=["canonical_id", "destination_searchable"],
        ).to_pylist()
        if row["destination_searchable"]
    ]
    rank_files: dict[str, Any] = {}
    rank_rows: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(ranks_dir.glob("*.parquet")):
        rows = pq.read_table(path).to_pylist()
        rank_rows[path.name] = rows
        rank_files[path.name] = {
            "rows": len(rows),
            "split": rows[0]["split"],
            "valid_ranks": all(row["rank"] >= 1 for row in rows),
            "metrics": rank_metrics(rows),
        }

    selected_dev = rank_files["selected_dev.parquet"]["metrics"]
    selected_test = rank_files["selected_test.parquet"]["metrics"]
    metrics_match = {
        "dev": all(
            math.isclose(
                float(selected_dev[key]),
                float(selection["dev_metrics"]["overall"][key]),
                rel_tol=0,
                abs_tol=1e-12,
            )
            for key in selected_dev
        ),
        "test": all(
            math.isclose(
                float(selected_test[key]),
                float(selection["test_metrics"]["overall"][key]),
                rel_tol=0,
                abs_tol=1e-12,
            )
            for key in selected_test
        ),
    }
    candidates = [
        candidate for candidate in selection["candidates"] if candidate["guardrail_passed"]
    ]
    selection_key = lambda candidate: tuple(
        candidate["metrics"]["overall"][name]
        for name in config["selection_metrics"]
    )
    recomputed_selection = max(candidates, key=selection_key)["name"]

    audit = {
        "passed": bool(
            preflight["passed"]
            and preflight["verification"]["passed"]
            and all(model_hashes.values())
            and finite
            and manifest["corpus_rows"] == embeddings.shape[0]
            and manifest["embedding_dimension"] == embeddings.shape[1]
            and len(id_map) == len(corpus)
            and [row["canonical_id"] for row in id_map]
            == [row["canonical_id"] for row in corpus]
            and all(item["valid_ranks"] for item in rank_files.values())
            and all(metrics_match.values())
            and recomputed_selection == selection["selected"]
        ),
        "selected_run": selection["selected"],
        "model_hashes": model_hashes,
        "embeddings": {
            "shape": list(embeddings.shape),
            "dtype": str(embeddings.dtype),
            "finite": finite,
            "norm_min": min(norms),
            "norm_max": max(norms),
            "norm_mean": float(np.mean(norms)),
        },
        "id_map_rows": len(id_map),
        "id_map_unique": len({row["canonical_id"] for row in id_map}) == len(id_map),
        "id_map_matches_source_order": [row["canonical_id"] for row in id_map]
        == [row["canonical_id"] for row in corpus],
        "rank_files": rank_files,
        "metrics_match_model_selection": metrics_match,
        "selection_recomputed": recomputed_selection,
        "executed_script_sha256": sha256(Path(args.executed_script))
        if args.executed_script
        else None,
    }
    models_by_key = {model["key"]: model for model in config["models"]}
    reference_key = config.get("global_guardrail_baseline_key", config["models"][0]["key"])
    reference_model = models_by_key[reference_key]
    reference_name = reference_model.get(
        "baseline_name", f"D0_{reference_key}_zero_shot"
    )
    comparison_candidates = [
        candidate
        for candidate in candidates
        if candidate["name"] != selection["selected"]
        and f"{candidate['name']}_dev.parquet" in rank_rows
    ]
    best_alternative = (
        max(comparison_candidates, key=selection_key)
        if comparison_candidates
        else None
    )
    comparisons: dict[str, Any] = {
        "method": "paired cluster bootstrap by query_family_id",
        "reference_run": reference_name,
        "dev_selected_vs_reference": cluster_bootstrap(
            rank_rows["selected_dev.parquet"],
            rank_rows[f"{reference_name}_dev.parquet"],
            args.seed,
            args.bootstrap_samples,
        ),
        "test_selected_vs_reference": cluster_bootstrap(
            rank_rows["selected_test.parquet"],
            rank_rows[f"{reference_name}_test.parquet"],
            args.seed,
            args.bootstrap_samples,
        ),
    }
    if best_alternative:
        comparisons["best_alternative_run"] = best_alternative["name"]
        comparisons["dev_selected_vs_best_alternative"] = cluster_bootstrap(
            rank_rows["selected_dev.parquet"],
            rank_rows[f"{best_alternative['name']}_dev.parquet"],
            args.seed,
            args.bootstrap_samples,
        )
    write_json(output_dir / "LOCAL_AUDIT.json", audit)
    write_json(output_dir / "STATISTICAL_COMPARISON.json", comparisons)
    print(
        json.dumps(
            {
                "passed": audit["passed"],
                "selected_run": audit["selected_run"],
                "embedding_shape": audit["embeddings"]["shape"],
                "rank_files": len(rank_files),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
