"""Encoder + Elasticsearch session used by the demo API process."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional
from transformers import AutoModel, AutoTokenizer

from es_client import ElasticsearchClient
from es_query import ann_body, search
from lexical import lexical_body
from settings import BRANCH_DEPTH, ES_URL, INDEX_NAME, resolve_model_source

class Runtime:
    def __init__(self) -> None:
        source = resolve_model_source()
        self.model_source = source
        self.tokenizer = AutoTokenizer.from_pretrained(source)
        self.model = AutoModel.from_pretrained(source).cpu().eval()
        torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
        self.lock = threading.Lock()
        self.local = threading.local()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.sessions: set[str] = set()
        self.exposures: dict[str, dict[str, Any]] = {}
        self.selections: dict[tuple[str, str], dict[str, Any]] = {}
        self.map_geojson: dict[str, Any] | None = None
        self.map_lock = threading.Lock()

    def client(self) -> ElasticsearchClient:
        value = getattr(self.local, "client", None)
        if value is None:
            value = ElasticsearchClient(ES_URL)
            self.local.client = value
        return value

    def encode(self, query: str) -> np.ndarray:
        tokens = self.tokenizer(
            ["query: " + query], padding=True, truncation=True,
            max_length=64, return_tensors="pt",
        )
        with self.lock, torch.no_grad():
            hidden = self.model(**tokens).last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            vector = functional.normalize(
                torch.sum(hidden * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9),
                p=2, dim=1,
            )[0]
        return vector.numpy().astype(np.float32, copy=False)

    def lexical(self, query: str) -> tuple[list[str], float]:
        ids, elapsed = search(self.client(), lexical_body(query, BRANCH_DEPTH))
        return ids, elapsed

    def dense(self, vector: np.ndarray) -> tuple[list[str], float]:
        ids, elapsed = search(self.client(), ann_body(vector, BRANCH_DEPTH))
        return ids, elapsed

    def documents(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        response = self.client().request("POST", f"/{INDEX_NAME}/_mget", {"ids": ids})
        by_id = {item["_id"]: item["_source"] for item in response["docs"] if item.get("found")}
        return [by_id[poi_id] for poi_id in ids if poi_id in by_id]
