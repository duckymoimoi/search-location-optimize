"""Evaluate an observable query-length router without using dataset track labels."""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_stage1_branches import rrf  # noqa: E402
from evaluate_typing_sessions import session_metrics  # noqa: E402


def compact_length(query: str) -> int:
    return len("".join(ch for ch in unicodedata.normalize("NFKC", query).strip() if not ch.isspace()))


def rank(ids: list[str], target: str) -> int:
    return ids.index(target) + 1 if target in ids else len(ids) + 1


def metrics(rows: list[dict], field: str) -> dict:
    slices = {
        "retrieval_core_main": [r for r in rows if r["track"] == "retrieval_core" and r["main_metric_candidate"]],
        "autocomplete": [r for r in rows if r["track"] == "autocomplete"],
        "ambiguity_diagnostic": [r for r in rows if r["track"] == "ambiguity_stress"],
        "ime_keystream": [r for r in rows if r["track"] == "ime_keystream"],
        "structured": [r for r in rows if r["track"] == "structured_code" and r["structured_metric_candidate"]],
    }
    output = {}
    for name, subset in slices.items():
        if not subset:
            continue
        ranks = np.asarray([rank(row[field], row["intended_poi_id"]) for row in subset])
        output[name] = {
            "count": len(subset), "hit_5": float(np.mean(ranks <= 5)),
            "hit_20": float(np.mean(ranks <= 20)), "hit_50": float(np.mean(ranks <= 50)),
            "mrr_10": float(np.mean(np.where(ranks <= 10, 1 / ranks, 0))),
        }
    return output


def load(path: Path, threshold: int) -> list[dict]:
    rows = pq.read_table(path).to_pylist()
    for row in rows:
        hybrid = rrf(row["L1_prefix_heavy_ids"], row["ann_ids"], 50, 60)
        row["router"] = row["L1_prefix_heavy_ids"] if compact_length(row["query"]) <= threshold else hybrid
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--typing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selected-threshold", type=int, default=4)
    args = parser.parse_args()

    dev_sweep = {}
    for threshold in (2, 3, 4, 5, 6, 8, 10, 12):
        dev_sweep[str(threshold)] = metrics(load(args.dev, threshold), "router")
    selected = {
        "rule": f"lexical when NFKC compact query length <= {args.selected_threshold}; otherwise hybrid ANN",
        "runtime_signals_only": True,
        "uses_track_or_error_label": False,
        "dev": metrics(load(args.dev, args.selected_threshold), "router"),
        "test": metrics(load(args.test, args.selected_threshold), "router"),
        "architecture_validation_not_blind": metrics(load(args.holdout, args.selected_threshold), "router"),
    }
    typing = pq.read_table(args.typing).to_pylist()
    for row in typing:
        hybrid = rrf(row["L1_prefix_heavy"], row["ann"], 50, 60)
        row["router"] = row["L1_prefix_heavy"] if compact_length(row["query"]) <= args.selected_threshold else hybrid
    selected["typing_dev_top5"] = session_metrics(typing, "router", 5)
    report = {"dev_threshold_sweep": dev_sweep, "selected": selected}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(selected, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
