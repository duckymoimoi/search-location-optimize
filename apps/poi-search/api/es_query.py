"""Index search helpers (lexical/ANN bodies executed against Elasticsearch)."""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from es_client import ElasticsearchClient
from settings import ANN_CANDIDATES, INDEX_NAME

def ann_body(vector: np.ndarray, size: int) -> dict[str, Any]:
    # Elasticsearch 9 knn (dense_vector); filter keeps destination-only docs.
    return {
        "size": size,
        "track_total_hits": False,
        "_source": False,
        "knn": {
            "field": "embedding",
            "query_vector": vector.tolist(),
            "k": size,
            "num_candidates": max(ANN_CANDIDATES, size),
            "filter": {"term": {"destination_searchable": True}},
        },
    }


def search(client: ElasticsearchClient, body: dict[str, Any]) -> tuple[list[str], float]:
    candidates, elapsed = search_candidates(client, body)
    return [row["poi_id"] for row in candidates], elapsed


def search_candidates(client: ElasticsearchClient, body: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    """Keep backend scores for diagnostics; ES knn scores are not raw cosine."""
    began = time.perf_counter()
    response = client.request("POST", f"/{INDEX_NAME}/_search", body)
    source = "dense" if "knn" in body else "lexical"
    return [
        {"poi_id": hit["_id"], "source": source, "branch_rank": rank,
         "raw_score": hit.get("_score"), "score_kind": "es_knn" if source == "dense" else "bm25_composite"}
        for rank, hit in enumerate(response["hits"]["hits"], 1)
    ], (time.perf_counter() - began) * 1000
