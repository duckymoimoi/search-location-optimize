"""Evaluate session-level autocomplete entry, retention, and top-K churn on dev."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_stage1_branches import (  # noqa: E402
    LEXICAL_CONFIGS,
    OpenSearchClient,
    ann_body,
    latency,
    lexical_body,
    rrf,
    search,
)


METHODS = (
    "exact_dense",
    "ann",
    "L1_prefix_heavy",
    "hybrid_exact_d50_c10",
    "hybrid_ann_d50_c10",
)
KS = (5, 20, 50)


def session_metrics(rows: list[dict[str, Any]], field: str, k: int) -> dict[str, Any]:
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sessions[row["session_id"]].append(row)
    first_steps: list[int | None] = []
    stable_steps: list[int | None] = []
    final_hits: list[bool] = []
    retained_after_first: list[bool] = []
    censored_first: list[int] = []
    censored_stable: list[int] = []
    saved_after_stable: list[int] = []
    churn_values: list[float] = []
    for events in sessions.values():
        events.sort(key=lambda row: row["event_index"])
        target = events[0]["intended_poi_id"]
        present = [target in event[field][:k] for event in events]
        first = next((index + 1 for index, value in enumerate(present) if value), None)
        stable = next(
            (
                index + 1
                for index in range(len(present))
                if present[index] and all(present[index:])
            ),
            None,
        )
        first_steps.append(first)
        stable_steps.append(stable)
        final_hits.append(present[-1])
        retained_after_first.append(
            bool(first is not None and all(present[first - 1 :]))
        )
        censored_first.append(first if first is not None else len(events) + 1)
        censored_stable.append(stable if stable is not None else len(events) + 1)
        saved_after_stable.append(len(events) - stable if stable is not None else 0)
        for left, right in zip(events, events[1:]):
            left_set = set(left[field][:k])
            right_set = set(right[field][:k])
            union = left_set | right_set
            churn_values.append(
                0.0 if not union else 1.0 - len(left_set & right_set) / len(union)
            )
    first_found = [value for value in first_steps if value is not None]
    stable_found = [value for value in stable_steps if value is not None]
    ever_count = len(first_found)
    return {
        "sessions": len(sessions),
        "found_rate": ever_count / len(sessions),
        "stable_found_rate": len(stable_found) / len(sessions),
        "final_hit_rate": float(np.mean(final_hits)),
        "retained_after_first_rate_given_found": (
            sum(retained_after_first) / ever_count if ever_count else 0.0
        ),
        "transient_without_final_rate": float(
            np.mean(
                [first is not None and not final for first, final in zip(first_steps, final_hits)]
            )
        ),
        "first_step_mean_found_only": float(np.mean(first_found)) if first_found else None,
        "stable_step_mean_found_only": float(np.mean(stable_found)) if stable_found else None,
        "first_step_censored_mean": float(np.mean(censored_first)),
        "stable_step_censored_mean": float(np.mean(censored_stable)),
        "keystrokes_saved_after_stable_mean_all_sessions": float(
            np.mean(saved_after_stable)
        ),
        "consecutive_topk_churn_mean": float(np.mean(churn_values)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="hanoi-poi-stage1-v4-hnsw-hq")
    parser.add_argument("--ann-candidates", type=int, default=200)
    parser.add_argument("--top-k", type=int, default=100)
    args = parser.parse_args()

    cache = Path(args.cache)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dense_rows = pq.read_table(
        cache / "dev_sessions_dense_exact_top100.parquet"
    ).to_pylist()
    embeddings = np.load(cache / "dev_session_embeddings.npy", mmap_mode="r")
    if len(dense_rows) != len(embeddings):
        raise ValueError("Session dense rows and embeddings are not aligned")

    client = OpenSearchClient(args.base_url)
    server = client.request("GET", "/")
    count = client.request("GET", f"/{args.index}/_count")["count"]
    if count != 45_693:
        raise ValueError(f"Expected 45693 indexed POIs, got {count}")
    lexical_times: list[float] = []
    ann_times: list[float] = []
    results: list[dict[str, Any]] = []
    for index, row in enumerate(dense_rows):
        lexical_ids, _, _, lexical_ms = search(
            client,
            args.index,
            lexical_body(row["query"], LEXICAL_CONFIGS["L1_prefix_heavy"], args.top_k),
        )
        ann_ids, _, _, ann_ms = search(
            client,
            args.index,
            ann_body(embeddings[index], args.top_k, args.ann_candidates),
        )
        results.append(
            {
                "session_id": row["session_id"],
                "event_index": row["event_index"],
                "query": row["query"],
                "is_final": row["is_final"],
                "intended_poi_id": row["intended_poi_id"],
                "query_family_id": row["query_family_id"],
                "exact_dense": row["top_ids"],
                "ann": ann_ids,
                "L1_prefix_heavy": lexical_ids,
                "hybrid_exact_d50_c10": rrf(
                    lexical_ids, row["top_ids"], 50, 10
                ),
                "hybrid_ann_d50_c10": rrf(lexical_ids, ann_ids, 50, 10),
            }
        )
        lexical_times.append(lexical_ms)
        ann_times.append(ann_ms)
        if index and index % 500 == 0:
            print(f"session_events={index}", flush=True)
    client.close()

    pq.write_table(
        pa.Table.from_pylist(results),
        output / "typing_session_dev_top100.parquet",
        compression="zstd",
    )
    metrics = {
        method: {f"top_{k}": session_metrics(results, method, k) for k in KS}
        for method in METHODS
    }
    report = {
        "split": "dev_synthetic",
        "holdout_evaluated": False,
        "session_event_model": "virtual_unicode_character",
        "server": server,
        "index": args.index,
        "ann_candidates": args.ann_candidates,
        "sessions": len({row["session_id"] for row in results}),
        "events": len(results),
        "metrics": metrics,
        "latency": {
            "L1_prefix_heavy": latency(lexical_times),
            "ann": latency(ann_times),
        },
        "limitations": [
            "Sessions model direct Unicode character append, not physical key timing.",
            "intended_poi_id is a weak generated intent, especially for short prefixes.",
            "No holdout sessions were evaluated.",
        ],
    }
    (output / "typing_session_dev_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "sessions": report["sessions"],
                "events": report["events"],
                "lexical_top5": metrics["L1_prefix_heavy"]["top_5"],
                "dense_top5": metrics["exact_dense"]["top_5"],
            }
        )
    )


if __name__ == "__main__":
    main()
