#!/usr/bin/env python3
"""Lexical, hybrid dense-ANN, and exact dense on one GPU checkpoint.

Top 100. Same Gold v2.1 queries. ANN uses the Elasticsearch knn body the
hybrid API uses. Exact dense scores that query vector against every passage.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as functional
from transformers import AutoModel, AutoTokenizer

from es_client import ElasticsearchClient
from es_query import ann_body
from lexical import lexical_body
from textnorm import glue_code_spans

TOP_K = 100
KS = (1, 20, 50, 100)
RRF_K = 60
GOLD = Path(os.environ.get("GOLD_JSONL", "/gold/queries.jsonl"))
EMB = Path(os.environ.get("EMB_NPY", "/emb/corpus_embeddings.npy"))
IDS = Path(os.environ.get("EMB_IDS", "/emb/poi_ids.txt"))
OUT = Path(os.environ.get("BENCH_OUT", "/out/summary.json"))
ES_URL = os.environ["POI_ES_URL"]
INDEX = os.environ["POI_INDEX"]


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


def rrf(left: list[str], right: list[str]) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, int] = {}
    for branch in (left[:TOP_K], right[:TOP_K]):
        for rank, poi_id in enumerate(branch, 1):
            scores[poi_id] += 1 / (RRF_K + rank)
            best[poi_id] = min(best.get(poi_id, rank), rank)
    return sorted(scores, key=lambda poi_id: (-scores[poi_id], best[poi_id], poi_id))


def rank_of(ids: list[str], accepted: set[str]) -> int | None:
    return next((i for i, poi_id in enumerate(ids, 1) if poi_id in accepted), None)


def quantile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q))


def hits(ranks: list[int | None]) -> dict[str, float]:
    n = len(ranks)
    return {f"Hit@{k}": sum(rank is not None and rank <= k for rank in ranks) / n for k in KS}


def latency(values: list[float]) -> dict[str, float]:
    return {"p50_ms": quantile(values, 0.50), "p95_ms": quantile(values, 0.95)}


def search(client: ElasticsearchClient, body: dict) -> tuple[list[str], float]:
    began = time.perf_counter()
    response = client.request("POST", f"/{INDEX}/_search", body)
    elapsed = (time.perf_counter() - began) * 1000
    return [hit["_id"] for hit in response["hits"]["hits"]], elapsed


def encode(model, tokenizer, text: str, device: torch.device) -> tuple[np.ndarray, float]:
    began = time.perf_counter()
    tokens = tokenizer(["query: " + text], padding=True, truncation=True, max_length=64, return_tensors="pt")
    tokens = {key: value.to(device) for key, value in tokens.items()}
    with torch.no_grad():
        hidden = model(**tokens).last_hidden_state
        mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
        vector = functional.normalize(
            torch.sum(hidden * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9),
            p=2, dim=1,
        )[0]
    return vector.detach().float().cpu().numpy().astype(np.float32), (time.perf_counter() - began) * 1000


def exact_topk(vector: np.ndarray, corpus: torch.Tensor) -> tuple[list[int], float]:
    began = time.perf_counter()
    query = torch.from_numpy(vector).to(corpus.device)
    scores = query @ corpus.T
    k = min(TOP_K, scores.shape[0])
    values, index = torch.topk(scores, k)
    del values
    order = index.detach().cpu().tolist()
    return order, (time.perf_counter() - began) * 1000


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    source = os.environ["POI_MODEL_DIR"]
    tokenizer = AutoTokenizer.from_pretrained(source)
    model = AutoModel.from_pretrained(source).to(device).eval()
    corpus_np = np.load(EMB, mmap_mode="r")
    corpus = torch.from_numpy(np.asarray(corpus_np)).to(device)
    poi_ids = [line.strip() for line in IDS.read_text(encoding="utf-8").splitlines() if line.strip()]
    if corpus.shape[0] != len(poi_ids):
        raise SystemExit("Embedding rows do not match poi ids")
    sessions = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    client = ElasticsearchClient(ES_URL)
    rows = []
    buckets = {name: [] for name in ("lexical_ms", "ann_encode_ms", "ann_search_ms", "ann_total_ms", "exact_encode_ms", "exact_search_ms", "exact_total_ms", "fusion_ms", "exact_lexical_total_ms")}
    ranks = {name: [] for name in ("lexical", "dense_ann", "exact_dense", "exact_lexical")}
    for offset, record in enumerate(sessions):
        accepted = set(record["acceptable_poi_ids"])
        text = str(record["query_text"])
        lexical_ids, lexical_ms = search(client, lexical_body(text, TOP_K))
        vector, encode_ms = encode(model, tokenizer, glue_code_spans(text), device)
        ann_ids, ann_ms = search(client, ann_body(vector, TOP_K))
        exact_index, exact_ms = exact_topk(vector, corpus)
        exact_ids = [poi_ids[i] for i in exact_index]
        fuse_began = time.perf_counter()
        fused_ids = rrf(lexical_ids, exact_ids)
        fusion_ms = (time.perf_counter() - fuse_began) * 1000
        buckets["lexical_ms"].append(lexical_ms)
        buckets["ann_encode_ms"].append(encode_ms)
        buckets["ann_search_ms"].append(ann_ms)
        buckets["ann_total_ms"].append(encode_ms + ann_ms)
        buckets["exact_encode_ms"].append(encode_ms)
        buckets["exact_search_ms"].append(exact_ms)
        buckets["exact_total_ms"].append(encode_ms + exact_ms)
        buckets["fusion_ms"].append(fusion_ms)
        buckets["exact_lexical_total_ms"].append(lexical_ms + encode_ms + exact_ms + fusion_ms)
        ranks["lexical"].append(rank_of(lexical_ids, accepted))
        ranks["dense_ann"].append(rank_of(ann_ids, accepted))
        ranks["exact_dense"].append(rank_of(exact_ids, accepted))
        ranks["exact_lexical"].append(rank_of(fused_ids, accepted))
        rows.append(
            {
                "lexical": ranks["lexical"][-1],
                "dense_ann": ranks["dense_ann"][-1],
                "exact_dense": ranks["exact_dense"][-1],
                "exact_lexical": ranks["exact_lexical"][-1],
                "chars": len(text),
            }
        )
        if (offset + 1) % 100 == 0 or offset + 1 == len(sessions):
            print(f"{offset + 1}/{len(sessions)}", flush=True)
    def caught(left: str, right: str, k: int) -> int:
        return sum(
            (row[left] is None or row[left] > k) and row[right] is not None and row[right] <= k
            for row in rows
        )

    report = {
        "index": INDEX,
        "top_k": TOP_K,
        "n": len(sessions),
        "device": str(device),
        "note": "Lexical and dense ANN are the hybrid branches at k=100, not the fused hybrid ranking. Exact dense uses the same query vector against every passage.",
        "modes": {
            "lexical": {"hit": hits(ranks["lexical"]), "latency": latency(buckets["lexical_ms"])},
            "dense_ann": {
                "hit": hits(ranks["dense_ann"]),
                "latency": {
                    "encode": latency(buckets["ann_encode_ms"]),
                    "search": latency(buckets["ann_search_ms"]),
                    "total": latency(buckets["ann_total_ms"]),
                },
            },
            "exact_dense": {
                "hit": hits(ranks["exact_dense"]),
                "latency": {
                    "encode": latency(buckets["exact_encode_ms"]),
                    "search": latency(buckets["exact_search_ms"]),
                    "total": latency(buckets["exact_total_ms"]),
                },
            },
            "exact_dense_plus_lexical": {
                "hit": hits(ranks["exact_lexical"]),
                "latency": {
                    "fusion": latency(buckets["fusion_ms"]),
                    "total": latency(buckets["exact_lexical_total_ms"]),
                },
            },
        },
        "complement": {
            "exact_miss_1_lexical_hit_1": caught("exact_dense", "lexical", 1),
            "exact_miss_1_fused_hit_1": caught("exact_dense", "exact_lexical", 1),
            "fused_miss_1_exact_hit_1": caught("exact_lexical", "exact_dense", 1),
            "exact_miss_20_lexical_hit_20": caught("exact_dense", "lexical", 20),
            "exact_miss_100_lexical_hit_100": caught("exact_dense", "lexical", 100),
            "ann_miss_1_exact_hit_1": caught("dense_ann", "exact_dense", 1),
            "lexical_miss_1_exact_hit_1": caught("lexical", "exact_dense", 1),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
