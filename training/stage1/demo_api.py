"""FastAPI demo for the frozen Stage 1 lexical, ANN, and hybrid candidates."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
import torch.nn.functional as functional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModel, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_stage1_branches import (  # noqa: E402
    LEXICAL_CONFIGS,
    OpenSearchClient,
    ann_body,
    lexical_body,
    rrf,
    search,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(
    os.environ.get(
        "HANOI_POI_MODEL_DIR",
        ROOT / "training" / "kaggle" / "outputs_v4" / "stage1_outputs",
    )
)
OPENSEARCH_URL = os.environ.get("HANOI_POI_OPENSEARCH_URL", "http://127.0.0.1:9200")
INDEX_NAME = os.environ.get("HANOI_POI_INDEX", "hanoi-poi-stage1-v4-hnsw-hq")
BRANCH_DEPTH = 50
ANN_CANDIDATES = 200
RRF_CONSTANT = 10


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    input_state: Literal["typing", "submitted"]
    mode: Literal["auto", "lexical", "dense", "hybrid"] = "auto"
    k: int = Field(default=10, ge=1, le=50)


class Runtime:
    def __init__(self) -> None:
        self.inference = json.loads(
            (ARTIFACTS / "inference_config.json").read_text(encoding="utf-8")
        )
        self.manifest = json.loads(
            (ARTIFACTS / "final_model_manifest.json").read_text(encoding="utf-8")
        )
        torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
        self.tokenizer = AutoTokenizer.from_pretrained(ARTIFACTS / "final_model")
        self.model = AutoModel.from_pretrained(ARTIFACTS / "final_model").cpu().eval()
        self.model_lock = threading.Lock()
        self.thread_local = threading.local()
        self.executor = ThreadPoolExecutor(max_workers=4)

    def client(self) -> OpenSearchClient:
        instance = getattr(self.thread_local, "client", None)
        if instance is None:
            instance = OpenSearchClient(OPENSEARCH_URL)
            self.thread_local.client = instance
        return instance

    def encode(self, query: str) -> np.ndarray:
        encoded = self.tokenizer(
            [self.inference["query_prefix"] + query],
            padding=True,
            truncation=True,
            max_length=self.inference["max_query_tokens"],
            return_tensors="pt",
        )
        with self.model_lock, torch.no_grad():
            hidden = self.model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            pooled = torch.sum(hidden * mask, dim=1) / torch.clamp(
                mask.sum(dim=1), min=1e-9
            )
            vector = functional.normalize(pooled, p=2, dim=1)[0]
        return vector.numpy().astype(np.float32, copy=False)

    def lexical(self, query: str) -> tuple[list[str], float]:
        ids, _, _, client_ms = search(
            self.client(),
            INDEX_NAME,
            lexical_body(query, LEXICAL_CONFIGS["L1_prefix_heavy"], BRANCH_DEPTH),
        )
        return ids, client_ms

    def ann(self, vector: np.ndarray) -> tuple[list[str], float]:
        ids, _, _, client_ms = search(
            self.client(),
            INDEX_NAME,
            ann_body(vector, BRANCH_DEPTH, ANN_CANDIDATES),
        )
        return ids, client_ms

    def documents(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        response = self.client().request(
            "POST",
            f"/{INDEX_NAME}/_mget",
            {
                "docs": [
                    {
                        "_id": canonical_id,
                        "_source": [
                            "canonical_id",
                            "search_label",
                            "address",
                            "category",
                        ],
                    }
                    for canonical_id in ids
                ]
            },
        )
        return [document["_source"] for document in response["docs"] if document["found"]]


runtime = Runtime()
app = FastAPI(title="Hanoi POI Stage 1 Demo", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    began = time.perf_counter()
    server = runtime.client().request("GET", "/")
    count = runtime.client().request("GET", f"/{INDEX_NAME}/_count")["count"]
    return {
        "status": "ok" if count == 45_693 else "degraded",
        "opensearch_version": server["version"]["number"],
        "index": INDEX_NAME,
        "corpus_rows": count,
        "model": runtime.manifest["selected_run"],
        "latency_ms": (time.perf_counter() - began) * 1000.0,
    }


@app.post("/search")
def search_endpoint(payload: SearchRequest) -> dict[str, Any]:
    query = " ".join(payload.query.split())
    if not query:
        raise HTTPException(status_code=422, detail="query must contain visible text")
    selected_mode = payload.mode
    route_reason = "explicit_mode"
    if selected_mode == "auto":
        if payload.input_state == "typing":
            selected_mode = "lexical"
            route_reason = "explicit_ui_typing_state"
        else:
            selected_mode = "hybrid"
            route_reason = "explicit_ui_submitted_state"

    began = time.perf_counter()
    encode_ms = 0.0
    lexical_ms = 0.0
    ann_ms = 0.0
    fusion_ms = 0.0
    if selected_mode == "lexical":
        ids, lexical_ms = runtime.lexical(query)
    elif selected_mode == "dense":
        encode_began = time.perf_counter()
        vector = runtime.encode(query)
        encode_ms = (time.perf_counter() - encode_began) * 1000.0
        ids, ann_ms = runtime.ann(vector)
    else:
        lexical_future = runtime.executor.submit(runtime.lexical, query)
        encode_began = time.perf_counter()
        vector = runtime.encode(query)
        encode_ms = (time.perf_counter() - encode_began) * 1000.0
        dense_ids, ann_ms = runtime.ann(vector)
        lexical_ids, lexical_ms = lexical_future.result()
        fusion_began = time.perf_counter()
        ids = rrf(lexical_ids, dense_ids, BRANCH_DEPTH, RRF_CONSTANT)
        fusion_ms = (time.perf_counter() - fusion_began) * 1000.0

    documents_began = time.perf_counter()
    results = runtime.documents(ids[: payload.k])
    documents_ms = (time.perf_counter() - documents_began) * 1000.0
    return {
        "query": query,
        "input_state": payload.input_state,
        "requested_mode": payload.mode,
        "selected_mode": selected_mode,
        "route_reason": route_reason,
        "results": results,
        "latency_ms": {
            "total": (time.perf_counter() - began) * 1000.0,
            "encode": encode_ms,
            "lexical": lexical_ms,
            "ann": ann_ms,
            "fusion": fusion_ms,
            "document_fetch": documents_ms,
        },
        "configuration": {
            "branch_depth": BRANCH_DEPTH,
            "ann_candidates": ANN_CANDIDATES,
            "rrf_constant": RRF_CONSTANT,
            "note": "auto routing is an evaluated candidate, not a frozen production decision",
        },
    }
