"""Measure Docker OpenSearch branch latency and throughput under concurrency."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_stage1_branches import (  # noqa: E402
    LEXICAL_CONFIGS,
    OpenSearchClient,
    ann_body,
    latency,
    lexical_body,
    search,
)


THREAD_LOCAL = threading.local()


def client(base_url: str) -> OpenSearchClient:
    instance = getattr(THREAD_LOCAL, "client", None)
    if instance is None:
        instance = OpenSearchClient(base_url)
        THREAD_LOCAL.client = instance
    return instance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="hanoi-poi-stage1-v4-hnsw-hq")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--result-size", type=int, default=50)
    parser.add_argument("--ann-candidates", type=int, default=200)
    parser.add_argument("--concurrency", default="1,4,8")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    cache = Path(args.cache)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    queries = (
        pq.read_table(bundle / "dev_synthetic.parquet", columns=["query"])
        .column(0)
        .to_pylist()
    )
    embeddings = np.load(cache / "dev_query_embeddings.npy", mmap_mode="r")
    if len(queries) != len(embeddings):
        raise ValueError("Dev queries and embeddings are not aligned")
    sample_indices = np.linspace(0, len(queries) - 1, args.requests, dtype=int)

    warm_client = OpenSearchClient(args.base_url)
    for index in sample_indices[:20]:
        search(
            warm_client,
            args.index,
            lexical_body(
                queries[index], LEXICAL_CONFIGS["L1_prefix_heavy"], args.result_size
            ),
        )
        search(
            warm_client,
            args.index,
            ann_body(embeddings[index], args.result_size, args.ann_candidates),
        )
    warm_client.close()

    report: dict[str, Any] = {
        "index": args.index,
        "requests_per_run": args.requests,
        "result_size": args.result_size,
        "ann_candidates": args.ann_candidates,
        "holdout_evaluated": False,
        "runs": {},
    }
    for method in ("lexical_L1", "ann"):
        report["runs"][method] = {}
        for concurrency in [int(value) for value in args.concurrency.split(",")]:
            def execute(index: int) -> float:
                instance = client(args.base_url)
                body = (
                    lexical_body(
                        queries[index],
                        LEXICAL_CONFIGS["L1_prefix_heavy"],
                        args.result_size,
                    )
                    if method == "lexical_L1"
                    else ann_body(
                        embeddings[index], args.result_size, args.ann_candidates
                    )
                )
                _, _, _, client_ms = search(instance, args.index, body)
                return client_ms

            began = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                durations = list(pool.map(execute, sample_indices.tolist()))
            elapsed = time.perf_counter() - began
            report["runs"][method][f"concurrency_{concurrency}"] = {
                "wall_seconds": elapsed,
                "throughput_qps": args.requests / elapsed,
                "latency": latency(durations),
            }
            print(
                method,
                concurrency,
                report["runs"][method][f"concurrency_{concurrency}"],
                flush=True,
            )
    (output / "opensearch_load_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
