"""Evaluate lexical, exact dense, ANN, and RRF branches on v4 dev only."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import statistics
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


LEXICAL_CONFIGS = {
    "L0_balanced": {
        "exact": 12.0,
        "alias_exact": 10.0,
        "leading_prefix": 6.0,
        "phrase": 8.0,
        "prefix_field": 5.0,
        "and_match": 4.0,
        "fuzzy": 2.0,
    },
    "L1_prefix_heavy": {
        "exact": 16.0,
        "alias_exact": 12.0,
        "leading_prefix": 12.0,
        "phrase": 6.0,
        "prefix_field": 10.0,
        "and_match": 3.0,
        "fuzzy": 1.0,
    },
}
RRF_CONSTANTS = (10, 60)
BRANCH_DEPTHS = (50, 100)
FINAL_KS = (5, 20, 50)


class OpenSearchClient:
    def __init__(self, base_url: str):
        parsed = urlparse(base_url)
        if parsed.scheme != "http":
            raise ValueError("This local benchmark expects an HTTP loopback endpoint")
        self.connection = http.client.HTTPConnection(
            parsed.hostname, parsed.port or 80, timeout=60
        )

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        self.connection.request(
            method,
            path,
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        content = response.read()
        if response.status >= 400:
            raise RuntimeError(
                f"OpenSearch {method} {path}: {response.status} "
                + content.decode("utf-8", errors="replace")
            )
        return json.loads(content) if content else None

    def close(self) -> None:
        self.connection.close()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(character)
    )
    return " ".join(text.casefold().split())


def lexical_body(query: str, config: dict[str, float], size: int) -> dict[str, Any]:
    folded = fold(query)
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": config["exact"]}}},
        {"term": {"aliases_folded": {"value": folded, "boost": config["alias_exact"]}}},
        {
            "match_phrase": {
                "search_label": {"query": query, "boost": config["phrase"]}
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^6", "search_aliases^4", "address^2", "category_text"],
                "type": "best_fields",
                "operator": "and",
                "boost": config["and_match"],
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label.prefix^5", "search_aliases.prefix^3"],
                "type": "best_fields",
                "operator": "and",
                "boost": config["prefix_field"],
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^4", "search_aliases^3", "address"],
                "type": "best_fields",
                "fuzziness": "AUTO",
                "prefix_length": 1,
                "max_expansions": 50,
                "boost": config["fuzzy"],
            }
        },
    ]
    if len(folded) >= 2:
        should.extend(
            [
                {
                    "prefix": {
                        "label_folded": {
                            "value": folded,
                            "boost": config["leading_prefix"],
                        }
                    }
                },
                {
                    "prefix": {
                        "aliases_folded": {
                            "value": folded,
                            "boost": config["leading_prefix"] * 0.8,
                        }
                    }
                },
            ]
        )
    return {
        "size": size,
        "track_total_hits": False,
        "_source": False,
        "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [{"term": {"destination_searchable": True}}],
                "should": should,
                "minimum_should_match": 1,
            }
        },
    }


def ann_body(
    vector: np.ndarray, size: int, candidates: int | None = None
) -> dict[str, Any]:
    return {
        "size": size,
        "track_total_hits": False,
        "_source": False,
        "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
        "query": {
            "knn": {
                "embedding": {
                    "vector": vector.tolist(),
                    "k": candidates or size,
                    "filter": {"term": {"destination_searchable": True}},
                }
            }
        },
    }


def search(
    client: OpenSearchClient, index: str, body: dict[str, Any]
) -> tuple[list[str], list[float], float, float]:
    began = time.perf_counter()
    response = client.request("POST", f"/{index}/_search", body)
    client_ms = (time.perf_counter() - began) * 1000.0
    hits = response["hits"]["hits"]
    return (
        [hit["_id"] for hit in hits],
        [float(hit["_score"]) for hit in hits],
        float(response.get("took", 0)),
        client_ms,
    )


def rrf(left: list[str], right: list[str], depth: int, constant: int) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for branch in (left[:depth], right[:depth]):
        for rank, canonical_id in enumerate(branch, start=1):
            scores[canonical_id] += 1.0 / (constant + rank)
            best_rank[canonical_id] = min(best_rank.get(canonical_id, rank), rank)
    return sorted(scores, key=lambda item: (-scores[item], best_rank[item], item))


def rank(ids: list[str], target: str) -> int:
    try:
        return ids.index(target) + 1
    except ValueError:
        return len(ids) + 1


def summarize_ranks(ranks: list[int], ks: tuple[int, ...] = FINAL_KS) -> dict[str, Any]:
    array = np.asarray(ranks)
    result: dict[str, Any] = {"count": len(ranks)}
    for k in ks:
        result[f"hit_{k}"] = float(np.mean(array <= k))
    result["mrr_10"] = float(np.mean(np.where(array <= 10, 1.0 / array, 0.0)))
    return result


def latency(values: list[float]) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean_ms": float(np.mean(array)),
        "p50_ms": float(np.quantile(array, 0.50)),
        "p95_ms": float(np.quantile(array, 0.95)),
        "p99_ms": float(np.quantile(array, 0.99)),
        "max_ms": float(np.max(array)),
    }


def method_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    slices = {
        "retrieval_core_main": [
            row for row in rows if row["track"] == "retrieval_core" and row["main_metric_candidate"]
        ],
        "autocomplete": [row for row in rows if row["track"] == "autocomplete"],
        "ambiguity_stress": [row for row in rows if row["track"] == "ambiguity_stress"],
        "ime_keystream": [row for row in rows if row["track"] == "ime_keystream"],
        "structured_metric": [
            row for row in rows if row["track"] == "structured_code" and row["structured_metric_candidate"]
        ],
    }
    for name, subset in slices.items():
        if not subset:
            continue
        ranks = [rank(row[field], row["intended_poi_id"]) for row in subset]
        values = summarize_ranks(ranks)
        if name == "autocomplete":
            values["mrr_5"] = float(
                np.mean([1.0 / value if value <= 5 else 0.0 for value in ranks])
            )
        if name == "ambiguity_stress":
            for k in FINAL_KS:
                recalls = []
                coverages = []
                for row in subset:
                    compatible = set(row["known_compatible_poi_ids"])
                    found = compatible & set(row[field][:k])
                    recalls.append(len(found) / len(compatible))
                    coverages.append(bool(found))
                values[f"known_compatible_recall_{k}"] = float(np.mean(recalls))
                values[f"known_compatible_coverage_{k}"] = float(np.mean(coverages))
        output[name] = values
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="hanoi-poi-stage1-v4-lexical-dense")
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--ann-candidates", type=int, default=100)
    args = parser.parse_args()

    bundle = Path(args.bundle)
    cache = Path(args.cache)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dense_rows = pq.read_table(cache / "dev_dense_exact_top100.parquet").to_pylist()
    query_embeddings = np.load(cache / "dev_query_embeddings.npy", mmap_mode="r")
    dev_rows = pq.read_table(bundle / "dev_synthetic.parquet").to_pylist()
    overlay = {
        row["query_id"]: row
        for row in pq.read_table(bundle / "eligibility_v4.parquet").to_pylist()
    }
    if [row["query_id"] for row in dense_rows] != [row["query_id"] for row in dev_rows]:
        raise ValueError("Dense cache and dev rows are not aligned")
    for row in dev_rows:
        row["main_metric_candidate"] = overlay[row["query_id"]]["main_metric_candidate"]
        row["structured_metric_candidate"] = overlay[row["query_id"]]["structured_metric_candidate"]

    client = OpenSearchClient(args.base_url)
    server = client.request("GET", "/")
    index_count = client.request("GET", f"/{args.index}/_count")["count"]
    if index_count != 45_693:
        raise ValueError(f"Expected 45693 indexed POIs, got {index_count}")
    for row, dense in zip(dev_rows[:20], dense_rows[:20]):
        search(client, args.index, lexical_body(row["query"], LEXICAL_CONFIGS["L0_balanced"], 10))
        search(
            client,
            args.index,
            ann_body(query_embeddings[0], 10, args.ann_candidates),
        )

    records: list[dict[str, Any]] = []
    lexical_latency: dict[str, list[float]] = {name: [] for name in LEXICAL_CONFIGS}
    lexical_took: dict[str, list[float]] = {name: [] for name in LEXICAL_CONFIGS}
    ann_latency: list[float] = []
    ann_took: list[float] = []
    for index, (row, dense) in enumerate(zip(dev_rows, dense_rows)):
        result: dict[str, Any] = {
            "query_id": row["query_id"],
            "query": row["query"],
            "track": row["track"],
            "case_type": row["case_type"],
            "query_family_id": row["query_family_id"],
            "intended_poi_id": row["intended_poi_id"],
            "known_compatible_poi_ids": row["known_compatible_poi_ids"],
            "compatible_count": row["compatible_count"],
            "main_metric_candidate": row["main_metric_candidate"],
            "structured_metric_candidate": row["structured_metric_candidate"],
            "exact_dense_ids": dense["top_ids"],
        }
        for name, config in LEXICAL_CONFIGS.items():
            ids, scores, took_ms, client_ms = search(
                client, args.index, lexical_body(row["query"], config, args.top_k)
            )
            result[f"{name}_ids"] = ids
            result[f"{name}_scores"] = scores
            lexical_latency[name].append(client_ms)
            lexical_took[name].append(took_ms)
        ids, scores, took_ms, client_ms = search(
            client,
            args.index,
            ann_body(query_embeddings[index], args.top_k, args.ann_candidates),
        )
        result["ann_ids"] = ids
        result["ann_scores"] = scores
        ann_latency.append(client_ms)
        ann_took.append(took_ms)
        records.append(result)
        if index and index % 250 == 0:
            print(f"queried={index}", flush=True)
    client.close()

    methods: dict[str, list[list[str]]] = {
        "exact_dense": [row["exact_dense_ids"] for row in records],
        "ann": [row["ann_ids"] for row in records],
    }
    for lexical_name in LEXICAL_CONFIGS:
        methods[lexical_name] = [row[f"{lexical_name}_ids"] for row in records]
        for depth in BRANCH_DEPTHS:
            for constant in RRF_CONSTANTS:
                exact_name = f"H_exact_{lexical_name}_d{depth}_c{constant}"
                ann_name = f"H_ann_{lexical_name}_d{depth}_c{constant}"
                methods[exact_name] = [
                    rrf(row[f"{lexical_name}_ids"], row["exact_dense_ids"], depth, constant)
                    for row in records
                ]
                methods[ann_name] = [
                    rrf(row[f"{lexical_name}_ids"], row["ann_ids"], depth, constant)
                    for row in records
                ]
    for method_name, lists in methods.items():
        for row, ids in zip(records, lists):
            row[method_name] = ids

    quality = {name: method_metrics(records, name) for name in methods}
    ann_recall: dict[str, float] = {}
    ann_target_delta: dict[str, float] = {}
    for k in FINAL_KS:
        ann_recall[f"overlap_recall_{k}"] = float(
            np.mean(
                [
                    len(set(row["ann_ids"][:k]) & set(row["exact_dense_ids"][:k])) / k
                    for row in records
                ]
            )
        )
        core = [
            row
            for row in records
            if row["track"] == "retrieval_core" and row["main_metric_candidate"]
        ]
        exact_hit = np.mean(
            [row["intended_poi_id"] in row["exact_dense_ids"][:k] for row in core]
        )
        ann_hit = np.mean([row["intended_poi_id"] in row["ann_ids"][:k] for row in core])
        ann_target_delta[f"candidate_hit_{k}_ann_minus_exact"] = float(ann_hit - exact_hit)

    hybrid_ann_delta: dict[str, Any] = {}
    for lexical_name in LEXICAL_CONFIGS:
        for depth in BRANCH_DEPTHS:
            for constant in RRF_CONSTANTS:
                exact_name = f"H_exact_{lexical_name}_d{depth}_c{constant}"
                ann_name = f"H_ann_{lexical_name}_d{depth}_c{constant}"
                hybrid_ann_delta[ann_name] = {
                    metric: quality[ann_name]["retrieval_core_main"][metric]
                    - quality[exact_name]["retrieval_core_main"][metric]
                    for metric in ("hit_5", "hit_20", "hit_50", "mrr_10")
                }

    report = {
        "split": "dev_synthetic",
        "holdout_evaluated": False,
        "server": server,
        "index": args.index,
        "index_count": index_count,
        "ann_candidates": args.ann_candidates,
        "final_ks": list(FINAL_KS),
        "branch_depths": list(BRANCH_DEPTHS),
        "rrf_constants": list(RRF_CONSTANTS),
        "lexical_configs": LEXICAL_CONFIGS,
        "quality": quality,
        "ann_vs_exact": {**ann_recall, **ann_target_delta},
        "hybrid_ann_minus_exact": hybrid_ann_delta,
        "latency": {
            name: {
                "client": latency(lexical_latency[name]),
                "server_took": latency(lexical_took[name]),
            }
            for name in LEXICAL_CONFIGS
        }
        | {
            "ann": {
                "client": latency(ann_latency),
                "server_took": latency(ann_took),
            }
        },
        "latency_note": "Branch requests were sequential over a persistent localhost HTTP connection; dense encoder latency is stored separately in dense_runtime.json. Hybrid fusion is computed locally and this report does not claim parallel end-to-end API latency.",
    }
    (output / "stage1_dev_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    branch_rows = []
    saved_fields = [
        "query_id",
        "query",
        "track",
        "case_type",
        "query_family_id",
        "intended_poi_id",
        "known_compatible_poi_ids",
        "compatible_count",
        "main_metric_candidate",
        "structured_metric_candidate",
        "exact_dense_ids",
        "ann_ids",
        *[f"{name}_ids" for name in LEXICAL_CONFIGS],
    ]
    for row in records:
        branch_rows.append({field: row[field] for field in saved_fields})
    pq.write_table(
        pa.Table.from_pylist(branch_rows),
        output / "dev_branch_top100.parquet",
        compression="zstd",
    )
    print(
        json.dumps(
            {
                "queries": len(records),
                "ann_recall_50": ann_recall["overlap_recall_50"],
                "exact_dense_core_ch50": quality["exact_dense"]["retrieval_core_main"]["hit_50"],
                "lexical_l0_core_ch50": quality["L0_balanced"]["retrieval_core_main"]["hit_50"],
                "ann_p95_ms": latency(ann_latency)["p95_ms"],
                "lexical_l0_p95_ms": latency(lexical_latency["L0_balanced"])["p95_ms"],
            }
        )
    )


if __name__ == "__main__":
    main()
