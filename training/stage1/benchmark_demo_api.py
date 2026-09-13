"""Measure end-to-end demo API latency on frozen dev inputs only."""

from __future__ import annotations

import argparse
import http.client
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pyarrow.parquet as pq


def summarize(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean_ms": float(np.mean(array)),
        "p50_ms": float(np.quantile(array, 0.50)),
        "p95_ms": float(np.quantile(array, 0.95)),
        "p99_ms": float(np.quantile(array, 0.99)),
        "max_ms": float(np.max(array)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=200)
    args = parser.parse_args()

    parsed = urlparse(args.base_url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)
    bundle = Path(args.bundle)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dev = pq.read_table(bundle / "dev_synthetic.parquet").to_pylist()
    overlay = {
        row["query_id"]: row
        for row in pq.read_table(bundle / "eligibility_v4.parquet").to_pylist()
    }
    core = [
        row
        for row in dev
        if row["track"] == "retrieval_core"
        and overlay[row["query_id"]]["main_metric_candidate"]
    ]
    session_events = [
        row
        for row in pq.read_table(bundle / "typing_sessions.parquet").to_pylist()
        if row["split"] == "dev_synthetic"
    ]
    core_sample = [
        core[index]
        for index in np.linspace(0, len(core) - 1, args.samples, dtype=int)
    ]
    typing_sample = [
        session_events[index]
        for index in np.linspace(0, len(session_events) - 1, args.samples, dtype=int)
    ]

    def call(query: str, state: str, mode: str) -> dict:
        body = json.dumps(
            {"query": query, "input_state": state, "mode": mode, "k": 10}
        ).encode("utf-8")
        connection.request(
            "POST", "/search", body=body, headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        payload = response.read()
        if response.status != 200:
            raise RuntimeError(f"API returned {response.status}: {payload!r}")
        return json.loads(payload)

    for row in core_sample[:10]:
        call(row["query"], "submitted", "hybrid")
    runs = {
        "submitted_lexical": (core_sample, "submitted", "lexical"),
        "submitted_dense": (core_sample, "submitted", "dense"),
        "submitted_hybrid": (core_sample, "submitted", "hybrid"),
        "typing_auto": (typing_sample, "typing", "auto"),
    }
    report = {
        "holdout_evaluated": False,
        "samples_per_run": args.samples,
        "runs": {},
    }
    for name, (rows, state, mode) in runs.items():
        observed: dict[str, list[float]] = {
            key: []
            for key in ("wall", "total", "encode", "lexical", "ann", "fusion", "document_fetch")
        }
        selected_modes: dict[str, int] = {}
        for row in rows:
            began = time.perf_counter()
            response = call(row["query"], state, mode)
            observed["wall"].append((time.perf_counter() - began) * 1000.0)
            for key in observed:
                if key != "wall":
                    observed[key].append(float(response["latency_ms"][key]))
            selected = response["selected_mode"]
            selected_modes[selected] = selected_modes.get(selected, 0) + 1
        report["runs"][name] = {
            "input_state": state,
            "requested_mode": mode,
            "selected_modes": selected_modes,
            "latency": {key: summarize(values) for key, values in observed.items()},
        }
        print(name, report["runs"][name]["latency"]["wall"], flush=True)
    connection.close()
    (output / "demo_api_latency.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
