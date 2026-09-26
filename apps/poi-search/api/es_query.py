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
    began = time.perf_counter()
    response = client.request("POST", f"/{INDEX_NAME}/_search", body)
    return [hit["_id"] for hit in response["hits"]["hits"]], (time.perf_counter() - began) * 1000
