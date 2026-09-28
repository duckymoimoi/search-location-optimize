#!/usr/bin/env python3
"""Hybrid Gold v2.1 replay against a new serving index.

Refuses the demo index vn-poi-core-v3-me5-small. Latency is one request at a
time: client wall clock and the API timings_ms.total. Exact-dense Kaggle Hit@1
is not this number.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1"
OUT = ROOT / "artifacts/results/stage1_v6_6k_devlock_hybrid"
CORPUS_VERSION = "vn-poi-core-v3-semantic-address-dedup50"
DEMO_INDEX = "vn-poi-core-v3-me5-small"
KS = (1, 20, 50)


def request_json(url: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_ids(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    if hasattr(raw, "tolist") and not isinstance(raw, str):
        return [str(item) for item in raw.tolist()]
    text = str(raw).strip()
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def rank_of(ids: list[str], accepted: set[str]) -> int | None:
    return next((index for index, poi_id in enumerate(ids, start=1) if poi_id in accepted), None)


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), q))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--expect-index", required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if args.expect_index == DEMO_INDEX and args.out.resolve() == OUT.resolve():
        raise SystemExit(f"Refusing to write demo index {DEMO_INDEX} into the devlock result directory")
    health = request_json(f"{args.api_url}/health")
    status = request_json(f"{args.api_url}/v1/status")
    if health.get("index") != args.expect_index:
        raise SystemExit(f"API index is {health.get('index')}, expected {args.expect_index}")
    if health.get("corpus_rows") != 179209 or status.get("coverage_id") != CORPUS_VERSION:
        raise SystemExit("API is not on corpus v3 with 179209 rows")
    sessions = pd.read_parquet(GOLD / "query_sessions_v2_1.parquet")
    session_id = request_json(f"{args.api_url}/v1/sessions", {})["session_id"]
    rows = []
    client_ms: list[float] = []
    server_ms: list[float] = []
    for index, record in enumerate(sessions.itertuples(index=False)):
        body = {
            "request_id": f"devlock-hybrid-{index}",
            "session_id": session_id,
            "context_revision": 1,
            "query": str(record.query_text),
            "top_k": 50,
            "expected_corpus_version": CORPUS_VERSION,
        }
        started = time.perf_counter()
        response = request_json(f"{args.api_url}/v1/suggest", body)
        elapsed = (time.perf_counter() - started) * 1000
        ids = [str(item["poi_id"]) for item in response.get("results") or []]
        accepted = set(parse_ids(record.acceptable_poi_ids))
        rank = rank_of(ids, accepted)
        client_ms.append(elapsed)
        total = (response.get("timings_ms") or {}).get("total")
        if total is not None:
            server_ms.append(float(total))
        rows.append(
            {
                "query_id": str(record.query_id),
                "query_role": str(record.query_role),
                "stratum": str(record.primary_sampling_stratum),
                "rank": rank,
                "client_ms": elapsed,
                "server_total_ms": total,
            }
        )
        if (index + 1) % 100 == 0 or index + 1 == len(sessions):
            print(f"hybrid {index + 1}/{len(sessions)}", flush=True)
    n = len(rows)
    ranks = [row["rank"] for row in rows]
    report = {
        "index": args.expect_index,
        "corpus_version": CORPUS_VERSION,
        "n": n,
        "Hit@1": sum(rank is not None and rank <= 1 for rank in ranks) / n,
        "Hit@20": sum(rank is not None and rank <= 20 for rank in ranks) / n,
        "Hit@50": sum(rank is not None and rank <= 50 for rank in ranks) / n,
        "client_ms": {"p50": quantile(client_ms, 0.50), "p95": quantile(client_ms, 0.95)},
        "server_total_ms": {"p50": quantile(server_ms, 0.50), "p95": quantile(server_ms, 0.95)},
        "note": "Serial /v1/suggest. Not comparable to Kaggle exact-dense Hit@1.",
    }
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "queries.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
