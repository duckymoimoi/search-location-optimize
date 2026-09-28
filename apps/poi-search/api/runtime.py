"""Encoder + Elasticsearch session used by the demo API process."""
from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional
from transformers import AutoModel, AutoTokenizer

from es_client import ElasticsearchClient
from es_query import ann_body, search, search_candidates
from lexical import lexical_body
from settings import BRANCH_DEPTH, ES_URL, INDEX_NAME, resolve_model_source

class Runtime:
    def __init__(self) -> None:
        source = resolve_model_source()
        self.model_source = source
        self.brand_router = None
        self.brand_lookup_sha256 = None
        self.brand_route_mode = None
        self.name_lookup_enabled = os.environ.get('POI_NAME_LOOKUP') == '1'
        if os.environ.get("POI_RETRIEVAL_PROFILE") == "dense_first":
            from brand_router import BrandRouter
            lookup = Path(os.environ["POI_BRAND_LOOKUP"])
            self.brand_router = BrandRouter(lookup)
            self.brand_lookup_sha256 = hashlib.sha256(lookup.read_bytes()).hexdigest()
            self.brand_route_mode = {"fuzzy": os.environ.get("POI_BRAND_FUZZY") == "1", "membership": os.environ.get("POI_BRAND_MEMBERSHIP") == "1"}
        device_name = os.environ.get("POI_DEVICE", "auto").lower()
        if device_name == "auto":
            device_name = "cuda" if torch.cuda.is_available() else "cpu"
        if device_name == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("POI_DEVICE=cuda but CUDA is unavailable in this container")
        self.device = torch.device(device_name)
        self.tokenizer = AutoTokenizer.from_pretrained(source)
        self.model = AutoModel.from_pretrained(source).to(self.device).eval()
        self.dense_backend = os.environ.get("POI_DENSE_BACKEND", "ann")
        self.exact_corpus = None
        self.exact_ids = None
        if self.dense_backend not in {"ann", "exact"}:
            raise ValueError("POI_DENSE_BACKEND must be ann or exact")
        if self.dense_backend == "exact":
            bundle_path = Path(os.environ["POI_BUNDLE_MANIFEST"])
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            if bundle["index"] != INDEX_NAME:
                raise ValueError("Bundle index mismatch")
            for key, path in [("model_sha256", Path(source) / "model.safetensors"),
                              ("vectors_sha256", Path(bundle["vectors_path"])),
                              ("ids_sha256", Path(bundle["ids_path"]))]:
                h = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest() != bundle[key]:
                    raise ValueError(f"Bundle hash mismatch: {key}")
            vectors = np.load(bundle["vectors_path"])
            self.exact_ids = Path(bundle["ids_path"]).read_text(encoding="utf-8").splitlines()
            if vectors.shape != (len(self.exact_ids), 384) or len(set(self.exact_ids)) != len(self.exact_ids):
                raise ValueError("Exact vectors/IDs mismatch")
            if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
                raise ValueError("Exact vectors must be normalized")
            count = ElasticsearchClient(ES_URL).request("POST", f"/{INDEX_NAME}/_count", {"query": {"term": {"destination_searchable": True}}})["count"]
            if count != len(self.exact_ids):
                raise ValueError("Exact corpus/index count mismatch")
            self.exact_corpus = torch.from_numpy(vectors).to(self.device)
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

    def brand_family(self, query):
        return self.brand_router.family(query, fuzzy=os.environ.get("POI_BRAND_FUZZY") == "1") if self.brand_router else None

    def brand_members(self, family):
        return self.brand_router.members(family) if self.brand_router and os.environ.get("POI_BRAND_MEMBERSHIP") == "1" else None

    def name_lookup(self, query):
        if not self.name_lookup_enabled:
            return [], 0.0
        from name_lookup import lookup_name_candidates
        candidates, elapsed = lookup_name_candidates(self.client(), query)
        # Full-name aliases on bank/ATM and other chain branches are not
        # evidence of namespace intent. Leave those to the brand route/dense.
        if self.brand_router:
            candidates = [row for row in candidates if row['poi_id'] not in self.brand_router.all_member_ids]
        return candidates, elapsed

    def encode(self, query: str) -> np.ndarray:
        started = time.perf_counter()
        tokens = self.tokenizer(
            ["query: " + query], padding=True, truncation=True,
            max_length=64, return_tensors="pt",
        )
        tokens = {key: value.to(self.device) for key, value in tokens.items()}
        queue_start = time.perf_counter()
        with self.lock:
            queue_ms = (time.perf_counter() - queue_start) * 1000
            with torch.no_grad():
                hidden = self.model(**tokens).last_hidden_state
                mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
                vector = functional.normalize(
                    torch.sum(hidden * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9),
                    p=2, dim=1,
                )[0]
                result = vector.cpu().numpy().astype(np.float32, copy=False)
        self.local.encode_timings = {"encode_queue": queue_ms, "encode_wall": (time.perf_counter() - started) * 1000}
        return result

    def lexical(self, query: str) -> tuple[list[str], float]:
        ids, elapsed = search(self.client(), lexical_body(query, BRANCH_DEPTH))
        return ids, elapsed

    def dense(self, vector: np.ndarray) -> tuple[list[str], float]:
        if self.dense_backend == "exact":
            candidates, elapsed = self.dense_candidates(vector)
            return [row["poi_id"] for row in candidates], elapsed
        ids, elapsed = search(self.client(), ann_body(vector, BRANCH_DEPTH))
        return ids, elapsed

    def lexical_candidates(self, query: str):
        return search_candidates(self.client(), lexical_body(query, BRANCH_DEPTH))

    def dense_candidates(self, vector: np.ndarray):
        if self.dense_backend == "exact":
            started = time.perf_counter()
            with torch.inference_mode():
                query = torch.from_numpy(vector).to(self.device)
                scores, indices = torch.topk(query @ self.exact_corpus.T, min(BRANCH_DEPTH, len(self.exact_ids)))
                score_values, index_values = scores.cpu().tolist(), indices.cpu().tolist()
            candidates = [{"poi_id": self.exact_ids[i], "source": "dense", "branch_rank": rank,
                           "raw_score": score, "score_kind": "cosine"}
                          for rank, (i, score) in enumerate(zip(index_values, score_values), 1)]
            return candidates, (time.perf_counter() - started) * 1000
        return search_candidates(self.client(), ann_body(vector, BRANCH_DEPTH))

    def documents(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        response = self.client().request("POST", f"/{INDEX_NAME}/_mget", {"docs": [{"_id": poi_id, "_source": {"excludes": ["embedding"]}} for poi_id in ids]})
        by_id = {item["_id"]: item["_source"] for item in response["docs"] if item.get("found")}
        return [by_id[poi_id] for poi_id in ids if poi_id in by_id]
