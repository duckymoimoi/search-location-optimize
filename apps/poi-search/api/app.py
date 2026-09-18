"""Runnable POI Search demo API backed by the stable OpenSearch index."""

from __future__ import annotations

import math
import http.client
import json
import os
import re
import threading
import time
import unicodedata
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

import numpy as np
import torch
import torch.nn.functional as functional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from transformers import AutoModel, AutoTokenizer

class OpenSearchClient:
    def __init__(self, base_url: str):
        parsed = urlparse(base_url)
        self.connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        self.connection.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        response = self.connection.getresponse()
        content = response.read()
        if response.status >= 400:
            raise RuntimeError(f"OpenSearch {response.status}: {content.decode(errors='replace')}")
        return json.loads(content) if content else None


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join("".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)).casefold().split())


def lexical_body(query: str, size: int) -> dict[str, Any]:
    folded = fold(query)
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": LEXICAL_CONFIG["exact"]}}},
        {"term": {"aliases_folded": {"value": folded, "boost": LEXICAL_CONFIG["alias_exact"]}}},
        {"match_phrase": {"search_label": {"query": query, "boost": LEXICAL_CONFIG["phrase"]}}},
        {"multi_match": {"query": query, "fields": ["search_label^6", "search_aliases^4", "address^2", "category_text"],
                         "type": "best_fields", "operator": "and", "boost": LEXICAL_CONFIG["and_match"]}},
        {"multi_match": {"query": query, "fields": ["search_label.prefix^5", "search_aliases.prefix^3"],
                         "type": "best_fields", "operator": "and", "boost": LEXICAL_CONFIG["prefix_field"]}},
    ]
    fuzzy_terms = [token for token in text_tokens(query) if token.isalpha() and len(token) >= 4]
    if fuzzy_terms:
        should.append({"multi_match": {"query": " ".join(fuzzy_terms),
            "fields": ["search_label^4", "search_aliases^3"], "type": "best_fields",
            "operator": "and", "fuzziness": "AUTO", "prefix_length": 1,
            "max_expansions": 50, "boost": LEXICAL_CONFIG["fuzzy"]}})
    expanded = expand_query(query)
    if normalized_text(expanded) != normalized_text(query):
        should.append({"multi_match": {"query": expanded,
            "fields": ["search_label^6", "search_aliases^4", "address^2"],
            "type": "cross_fields", "operator": "and", "boost": 0.5}})
    # A query can span the POI name and its address.
    should.append({"multi_match": {"query": query,
        "fields": ["search_label", "search_aliases", "address"], "type": "cross_fields",
        "operator": "and", "boost": LEXICAL_CONFIG["and_match"]}})
    if len(folded) >= 2:
        should += [
            {"prefix": {"label_folded": {"value": folded, "boost": LEXICAL_CONFIG["leading_prefix"]}}},
            {"prefix": {"aliases_folded": {"value": folded, "boost": LEXICAL_CONFIG["leading_prefix"] * .8}}},
        ]
    # Multi-token queries must satisfy ≥2 lexical signals so a single weak
    # address token (e.g. "hàng") cannot retrieve alone.
    token_n = len(text_tokens(query))
    minimum_should_match = 2 if token_n > 2 else 1
    return {"size": size, "track_total_hits": False, "_source": False,
            "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
            "query": {"bool": {"filter": [{"term": {"destination_searchable": True}}],
                               "should": should, "minimum_should_match": minimum_should_match}}}


def ann_body(vector: np.ndarray, size: int) -> dict[str, Any]:
    return {"size": size, "track_total_hits": False, "_source": False,
            "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
            "query": {"knn": {"embedding": {"vector": vector.tolist(), "k": ANN_CANDIDATES,
                                               "filter": {"term": {"destination_searchable": True}}}}}}


def search(client: OpenSearchClient, body: dict[str, Any]) -> tuple[list[str], float]:
    began = time.perf_counter()
    response = client.request("POST", f"/{INDEX_NAME}/_search", body)
    return [hit["_id"] for hit in response["hits"]["hits"]], (time.perf_counter() - began) * 1000


def rrf(left: list[str], right: list[str]) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, int] = {}
    for branch in (left[:BRANCH_DEPTH], right[:BRANCH_DEPTH]):
        for rank, poi_id in enumerate(branch, 1):
            scores[poi_id] += 1 / (RRF_CONSTANT + rank)
            best[poi_id] = min(best.get(poi_id, rank), rank)
    return sorted(scores, key=lambda poi_id: (-scores[poi_id], best[poi_id], poi_id))

MODEL_DIR = Path(os.environ.get("HANOI_POI_MODEL_DIR", "/model"))
OPENSEARCH_URL = os.environ.get("HANOI_POI_OPENSEARCH_URL", "http://opensearch:9200")
INDEX_NAME = os.environ.get("HANOI_POI_INDEX", "hanoi-poi-stable-v1-release1")
EXPECTED_ROWS = int(os.environ.get("HANOI_POI_EXPECTED_ROWS", "45692"))
POLICY_PATH = Path(os.environ.get("HANOI_POI_SEARCH_POLICY", Path(__file__).with_name("search_policy.json")))
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
RETRIEVAL_PROFILE = os.environ.get("HANOI_POI_RETRIEVAL_PROFILE", POLICY["default_retrieval_profile"])
GOONG_API_KEY = os.environ.get("GOONG_API_KEY", "").strip()
GOONG_DIRECTION_URL = os.environ.get("GOONG_DIRECTION_URL", "https://rsapi.goong.io/Direction").strip()
if RETRIEVAL_PROFILE not in {"lexical_only", "dense_only", "hybrid"}:
    raise ValueError(f"Unsupported retrieval profile: {RETRIEVAL_PROFILE}")
CORPUS_VERSION = "hn-poi-stable-v1"
BRANCH_DEPTH = int(POLICY["retrieval"]["branch_depth"])
ANN_CANDIDATES = int(POLICY["retrieval"]["ann_candidates"])
RRF_CONSTANT = int(POLICY["retrieval"]["rrf_constant"])
RANKING_POLICY = POLICY["ranking"]
LEXICAL_CONFIG = POLICY["lexical"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Point(StrictModel):
    model_config = ConfigDict(extra="ignore")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Origin(StrictModel):
    kind: Literal["poi", "gps", "map"]
    poi_id: str | None = None
    point: Point | None = None
    accuracy_m: float | None = None
    observed_at: datetime | None = None


class SuggestRequest(StrictModel):
    request_id: str
    session_id: str
    context_revision: int = Field(ge=1)
    query: str = Field(max_length=200)
    top_k: int = Field(default=5, ge=1, le=50)
    expected_corpus_version: str
    search_kind: str | None = None
    origin: Origin | None = None
    demo_user_id: str | None = None
    context_time: datetime | None = None
    preferred_region_id: str | None = None


class DisplayRequest(StrictModel):
    session_id: str
    exposure_id: str
    context_revision: int


class SelectRequest(DisplayRequest):
    selected_poi_id: str
    idempotency_key: str


class RouteRequest(StrictModel):
    corpus_version: str
    origin_poi_id: str | None = None
    destination_poi_id: str | None = None
    origin_point: Point | None = None
    destination_point: Point | None = None
    mode: Literal["straight_line", "road"] = "straight_line"
    vehicle: Literal["car", "bike", "taxi", "truck", "hd"] = "car"
    allow_fallback: bool = False


class Runtime:
    def __init__(self) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR / "final_model")
        self.model = AutoModel.from_pretrained(MODEL_DIR / "final_model").cpu().eval()
        torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
        self.lock = threading.Lock()
        self.local = threading.local()
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.sessions: set[str] = set()
        self.exposures: dict[str, dict[str, Any]] = {}
        self.selections: dict[tuple[str, str], dict[str, Any]] = {}

    def client(self) -> OpenSearchClient:
        value = getattr(self.local, "client", None)
        if value is None:
            value = OpenSearchClient(OPENSEARCH_URL)
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


runtime = Runtime()
app = FastAPI(title="Hanoi POI Search Demo", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=POLICY["cors_origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def warmup() -> None:
    """Keep the first user request out of model/index cold-start cost."""
    for query in POLICY["warmup_queries"]:
        if RETRIEVAL_PROFILE != "dense_only":
            runtime.lexical(query)
        if RETRIEVAL_PROFILE != "lexical_only":
            runtime.dense(runtime.encode(query))


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": detail.get("code", f"http_{exc.status_code}"),
            "message": detail.get("message", str(exc.detail)),
            "request_id": None,
        },
    )


def versions() -> dict[str, Any]:
    geo_mode = str(RANKING_POLICY.get("geo_mode", "v6")).strip().lower()
    ranker = "heuristic-geo-v6" if geo_mode == "v6" else "heuristic-geo-v5"
    feature = (
        "equivalent-name-band-geo-v6+nearby-name-rescue"
        if geo_mode == "v6"
        else "field-aware-bounded-geo-v5+nearby-name-rescue"
    )
    if not (RANKING_POLICY.get("nearby_name_rescue") or {}).get("enabled", False):
        feature = (
            "equivalent-name-band-geo-v6"
            if geo_mode == "v6"
            else "field-aware-bounded-geo-v5"
        )
    return {
        "release_id": "hanoi-poi-demo-r1", "corpus_version": CORPUS_VERSION,
        "index_version": INDEX_NAME, "encoder_id": "e5-v4-finetuned",
        "embedding_space_id": "e5-v4-context-384", "passage_builder_version": "stable-v1-context",
        "scope_policy_version": "global-v1",
        "candidate_policy_version": f"{POLICY['policy_version']}:safe-candidates-v5:{RETRIEVAL_PROFILE}",
        "ranker_id": ranker, "feature_version": feature,
    }


def compact_length(value: str) -> int:
    return len("".join(unicodedata.normalize("NFKC", value).split()))


def normalized_text(value: str) -> str:
    """Normalize spacing/case while preserving Vietnamese accents."""
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def is_exact_text_match(query: str, document: dict[str, Any]) -> bool:
    names = [document.get("search_label", ""), *(document.get("search_aliases") or [])]
    return bool(normalized_text(query)) and any(normalized_text(query) == normalized_text(name) for name in names)


def expand_query(query: str) -> str:
    """One optional lexical alternative; never replace the encoder input."""
    value = unicodedata.normalize("NFKC", query)
    for rewrite in POLICY.get("query_rewrites", []):
        value = re.sub(rewrite["pattern"], rewrite["replacement"], value, flags=re.IGNORECASE)
    return " ".join(value.split())


def text_tokens(value: str) -> list[str]:
    # Keep slash/hyphen inside address numbers and building identifiers.
    return re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", fold(value))


def token_overlap(query: str, document: dict[str, Any]) -> float:
    tokens = text_tokens(query)
    fields = [document.get("search_label", ""), *(document.get("search_aliases") or []),
              document.get("address", "")]
    available = set(text_tokens(" ".join(fields)))
    if not tokens:
        return 0.0
    matched = 0.0
    for index, token in enumerate(tokens):
        if token in available:
            matched += 1.0
        elif index == len(tokens) - 1 and len(token) >= 3 and token.isalpha():
            # Only unfinished final text can prefix-match. B12 must never match B1.
            matched += 0.5 if any(t.startswith(token) for t in available) else 0.0
    return matched / len(tokens)


def _token_in_set(token: str, available: set[str], *, allow_prefix: bool) -> bool:
    if token in available:
        return True
    if allow_prefix and token.isalpha() and len(token) >= 3:
        return any(item.startswith(token) for item in available)
    return False


def _contiguous_span_in_field(
    span: list[str],
    field_tokens: list[str],
    *,
    allow_final_prefix: bool,
) -> bool:
    """True if `span` appears as an adjacent subsequence of `field_tokens`."""
    if not span or not field_tokens or len(span) > len(field_tokens):
        return False
    last = len(span) - 1
    for start in range(len(field_tokens) - len(span) + 1):
        ok = True
        for offset, token in enumerate(span):
            field = field_tokens[start + offset]
            if token == field:
                continue
            if (
                allow_final_prefix
                and offset == last
                and token.isalpha()
                and len(token) >= 2
                and field.startswith(token)
            ):
                continue
            ok = False
            break
        if ok:
            return True
    return False


def name_address_evidence(query: str, document: dict[str, Any]) -> float:
    """Brand∩street evidence via name hits + contiguous address phrase.

    Address side must match a contiguous query span (≥2 tokens) that is not
    already a contiguous span on the name/alias side. No admin stopword list —
    single-token overlaps like «thành» in «Thành phố» cannot satisfy a span.
    """
    tokens = text_tokens(query)
    min_tokens = max(2, int(RANKING_POLICY.get("name_address_min_query_tokens", 4)))
    if len(tokens) < min_tokens:
        return 0.0
    if name_match_class(query, document) is not None:
        return 0.0

    name_tokens = text_tokens(
        " ".join([document.get("search_label", ""), *(document.get("search_aliases") or [])])
    )
    addr_tokens = text_tokens(document.get("address", "") or "")
    if not name_tokens or not addr_tokens:
        return 0.0

    name_set = set(name_tokens)
    name_hit_idxs = [
        index
        for index, token in enumerate(tokens)
        if _token_in_set(token, name_set, allow_prefix=(index == len(tokens) - 1))
    ]
    if not name_hit_idxs:
        return 0.0

    min_span = max(2, int(RANKING_POLICY.get("name_address_min_addr_span", 2)))
    name_hit_set = set(name_hit_idxs)
    best_span = 0
    best_start = -1
    for length in range(len(tokens), min_span - 1, -1):
        for start in range(len(tokens) - length + 1):
            span = tokens[start : start + length]
            allow_prefix = start + length == len(tokens)
            if not _contiguous_span_in_field(span, addr_tokens, allow_final_prefix=allow_prefix):
                continue
            # Span already explained as a name phrase → not address-side evidence.
            if _contiguous_span_in_field(span, name_tokens, allow_final_prefix=False):
                continue
            # Need a real residual street phrase: ≥min_span query tokens in the
            # span that the name side did not already cover (avoids «Phố»+«Bồ Đề»
            # matching brand query «pho bo …» without the extra street tokens).
            residual = sum(
                1 for index in range(start, start + length) if index not in name_hit_set
            )
            if residual < min_span:
                continue
            best_span = length
            best_start = start
            break
        if best_span:
            break
    if best_span < min_span:
        return 0.0

    covered = set(name_hit_idxs) | set(range(best_start, best_start + best_span))
    return len(covered) / len(tokens)


def prioritize_name_address(
    query: str,
    ranked: list[tuple[float, int, float | None, dict]],
) -> list[tuple[float, int, float | None, dict]]:
    """Promote candidates with name∩address evidence above partial one-field hits."""
    if not ranked or not bool(RANKING_POLICY.get("name_address_priority", True)):
        return ranked
    min_tokens = max(2, int(RANKING_POLICY.get("name_address_min_query_tokens", 4)))
    if len(text_tokens(query)) < min_tokens:
        return ranked
    threshold = min(1.0, max(0.0, float(RANKING_POLICY.get("name_address_min_evidence", 0.5))))
    decorated = []
    for score, rank, distance, doc in ranked:
        evidence = name_address_evidence(query, doc)
        decorated.append((1 if evidence >= threshold else 0, evidence, score, rank, distance, doc))
    decorated.sort(
        key=lambda row: (-row[0], -row[1], -row[2], row[3], row[5]["canonical_id"])
    )
    return [(score, rank, distance, doc) for _, _, score, rank, distance, doc in decorated]


def _accented_tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", normalized_text(value))


def query_has_accents(query: str) -> bool:
    """True when stripping diacritics changes the query (user typed accents)."""
    return bool(normalized_text(query)) and normalized_text(query) != fold(query)


def accent_token_coverage(query: str, document: dict[str, Any]) -> float:
    """Share of accent-preserving query tokens found in name/alias (not folded)."""
    tokens = _accented_tokens(query)
    if not tokens or not query_has_accents(query):
        return 0.0
    available = set(
        _accented_tokens(
            " ".join([document.get("search_label", ""), *(document.get("search_aliases") or [])])
        )
    )
    if not available:
        return 0.0
    matched = 0.0
    for index, token in enumerate(tokens):
        if token in available:
            matched += 1.0
        elif index == len(tokens) - 1 and len(token) >= 2 and token.isalpha():
            matched += 0.5 if any(item.startswith(token) for item in available) else 0.0
    return matched / len(tokens)


def prioritize_name_match_quality(
    query: str,
    ranked: list[tuple[float, int, float | None, dict]],
) -> list[tuple[float, int, float | None, dict]]:
    """Prefer contiguous name/alias phrase coverage over weak single-token fold hits.

    Fixes both:
    - accented «lăng chủ tịch» vs «Chùa Láng» (fold collision)
    - unaccented «lang chu tich» vs «Chùa Láng» (3-token phrase vs 1-token hit)
    When phrase/coverage tiers tie, keep prior geo/retrieval order.
    """
    if not ranked or not bool(RANKING_POLICY.get("name_match_quality_priority", True)):
        return ranked
    # Backward-compatible alias for the older accent-only flag.
    if RANKING_POLICY.get("accent_match_priority") is False and (
        RANKING_POLICY.get("name_match_quality_priority") is None
    ):
        return ranked
    accented = query_has_accents(query)
    decorated = []
    for position, (score, rank, distance, doc) in enumerate(ranked):
        match = name_match_class(query, doc)
        level = int(match[0]) if match else 0
        accent_hit = int(match[1]) if match and accented else 0
        coverage = token_overlap(query, doc)
        if accented:
            coverage = max(coverage, accent_token_coverage(query, doc))
        # `position` keeps post-geo order when phrase quality ties.
        decorated.append((level, accent_hit, coverage, position, score, rank, distance, doc))
    decorated.sort(
        key=lambda row: (-row[0], -row[1], -row[2], row[3], -row[4], row[7]["canonical_id"])
    )
    return [(score, rank, distance, doc) for _, _, _, _, score, rank, distance, doc in decorated]


def entity_key(document: dict[str, Any]) -> tuple[str, ...]:
    canonical = str(document["canonical_id"])
    category = str(document.get("category", ""))
    access_point = document.get("preserve_individual_access_point") or any(
        marker in category for marker in ("public_transport=platform", "railway=platform", "entrance=")
    )
    group = document.get("entity_group_id")
    if access_point or not group or not RANKING_POLICY.get("deduplication", {}).get("entity_group_id", True):
        return ("poi", canonical)
    # Different branches/access points are not duplicates of the parent complex.
    return ("entity", str(group), str(document.get("branch_id") or ""))


def is_near_name_duplicate(kept: dict[str, Any], candidate: dict[str, Any], within_m: float) -> bool:
    """Same folded label within `within_m`; keeps distinct branch_id only.

    Access-point tags still collapse when the visible name matches and the points
    are near — OSM often duplicates platforms/nodes for one place.
    """
    if within_m <= 0:
        return False
    left_branch, right_branch = kept.get("branch_id"), candidate.get("branch_id")
    if (left_branch or right_branch) and left_branch != right_branch:
        return False
    if fold(kept.get("search_label", "")) != fold(candidate.get("search_label", "")):
        return False
    if not fold(kept.get("search_label", "")):
        return False
    left, right = kept.get("ranking_point"), candidate.get("ranking_point")
    if not left or not right:
        return False
    return haversine(left, right) <= within_m


def candidate_documents(ids: list[str], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable retrieval order, entity + nearby same-name collapse, fixed Stage 1 budget."""
    by_id = {doc["canonical_id"]: doc for doc in docs}
    seen = set()
    output = []
    budget = int(POLICY["retrieval"]["candidate_budget"])
    within_m = float(RANKING_POLICY.get("deduplication", {}).get("normalized_name_within_m") or 0)
    for poi_id in ids:
        doc = by_id.get(poi_id)
        if doc is None:
            continue
        key = entity_key(doc)
        if key in seen:
            continue
        if within_m > 0 and any(is_near_name_duplicate(kept, doc, within_m) for kept in output):
            continue
        seen.add(key)
        output.append(doc)
        if len(output) >= budget:
            break
    return output


def name_match_class(query: str, doc: dict[str, Any]) -> tuple[int, int] | None:
    """Conservative equivalence: contiguous name/alias phrase, not bag-of-words.

    A numeric/code token must match in full. Address-only and fuzzy matches do
    not establish enough equivalence to let distance override retrieval.
    """
    query_tokens = text_tokens(query)
    if not query_tokens:
        return None
    classes: list[tuple[int, int]] = []
    names = [doc.get("search_label", ""), *(doc.get("search_aliases") or [])]
    accented_query = normalized_text(query) != fold(query)
    for name in names:
        tokens = text_tokens(name)
        if len(tokens) < len(query_tokens):
            continue
        for start in range(len(tokens) - len(query_tokens) + 1):
            span = tokens[start : start + len(query_tokens)]
            if span[:-1] != query_tokens[:-1]:
                continue
            last = query_tokens[-1]
            complete = span[-1] == last
            prefix = last.isalpha() and len(last) >= 2 and span[-1].startswith(last)
            if not (complete or prefix):
                continue
            # Full name/alias > complete phrase > unfinished final token.
            level = 3 if tokens == query_tokens else 2 if complete else 1
            accent_tokens = re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", normalized_text(name))
            raw_query = re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", normalized_text(query))
            raw_span = accent_tokens[start : start + len(raw_query)]
            accent_match = bool(
                raw_span
                and raw_span[:-1] == raw_query[:-1]
                and (
                    raw_span[-1] == raw_query[-1]
                    if complete
                    else raw_span[-1].startswith(raw_query[-1])
                )
            )
            classes.append((level, int(accent_match) if accented_query else 0))
    return max(classes) if classes else None


def rank_candidates_v5(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Personalized blend: relevance_blend * text_rel + geo_blend * exp(-d/decay)."""
    best = max((float(evidence[d["canonical_id"]]["rrf"] or 0) for d in docs), default=1.0) or 1.0
    retrieval_w = float(RANKING_POLICY.get("retrieval_weight", 0.65))
    overlap_w = float(RANKING_POLICY.get("name_token_overlap_weight", 0.35))
    relevance_blend = float(RANKING_POLICY.get("relevance_blend", 0.65))
    geo_blend = float(RANKING_POLICY.get("geo_blend", 0.35))
    decay = max(1.0, float(RANKING_POLICY.get("geo_decay_m", 5000)))
    exact_bonus = float(RANKING_POLICY.get("exact_text_bonus", 0.04))
    protect_exact = bool(RANKING_POLICY.get("protect_exact_name_or_alias", True))

    ranked: list[tuple[float, int, float | None, dict]] = []
    for rank, doc in enumerate(docs, 1):
        rrf_norm = float(evidence[doc["canonical_id"]]["rrf"] or 0) / best
        distance = haversine(anchor, doc["ranking_point"]) if anchor and doc.get("ranking_point") else None

        if anchor is None:
            ranked.append((rrf_norm, rank, distance, doc))
            continue

        coverage = token_overlap(query, doc)
        names = [doc.get("search_label", ""), *(doc.get("search_aliases") or [])]
        exact = is_exact_text_match(query, doc)
        folded_exact = bool(fold(query)) and any(fold(query) == fold(name) for name in names)
        text_rel = retrieval_w * rrf_norm + overlap_w * coverage
        if exact:
            text_rel += exact_bonus
        elif folded_exact:
            text_rel += 0.5 * exact_bonus
        if protect_exact and (exact or folded_exact):
            text_rel = max(text_rel, retrieval_w * rrf_norm + overlap_w)

        fields = " ".join([*names, doc.get("address", "")])
        available = set(text_tokens(fields))
        structured = [token for token in text_tokens(query) if any(c.isdigit() for c in token)]
        compatible = all(token in available for token in structured)
        geo = 0.0
        if distance is not None and compatible:
            geo = math.exp(-distance / decay)

        score = relevance_blend * text_rel + geo_blend * geo
        ranked.append((score, rank, distance, doc))
    return sorted(ranked, key=lambda item: (-item[0], item[1], item[3]["canonical_id"]))


def rank_candidates_v6(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Rerank only equivalent-name slots near the retrieval head (geo-v6).

    Outside this cohort, order and positions are unchanged. RRF is an ordinal
    fusion score, not calibrated relevance: do not add distance to that score.
    """
    best = max((float(evidence[d["canonical_id"]]["rrf"] or 0) for d in docs), default=1.0) or 1.0
    ranked: list[tuple[float, int, float | None, dict]] = []
    for rank, doc in enumerate(docs, 1):
        distance = haversine(anchor, doc["ranking_point"]) if anchor and doc.get("ranking_point") else None
        score = float(evidence[doc["canonical_id"]]["rrf"] or 0) / best
        ranked.append((score, rank, distance, doc))
    if anchor is None or not ranked or ranked[0][2] is None:
        return ranked
    head_class = name_match_class(query, ranked[0][3])
    if head_class is None:
        return ranked
    window = max(1, min(20, int(RANKING_POLICY.get("geo_equivalent_window", 10))))
    floor = min(1.0, max(0.0, float(RANKING_POLICY.get("geo_min_retrieval_ratio", 0.5))))
    slots = [
        i
        for i, row in enumerate(ranked[:window])
        if row[2] is not None and row[0] >= floor and name_match_class(query, row[3]) == head_class
    ]
    if len(slots) < 2:
        return ranked
    band_m = max(100.0, float(RANKING_POLICY.get("geo_distance_band_m", 500)))
    cohort = sorted((ranked[i] for i in slots), key=lambda row: (int(row[2] / band_m), row[1]))
    for slot, row in zip(slots, cohort):
        ranked[slot] = row
    return ranked


def rank_candidates(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Dispatch Stage-2 geo by policy `geo_mode` (`v5` blend | `v6` cohort swap)."""
    return rank_candidates_traced(query, docs, evidence, anchor)["final"]


def rank_candidates_traced(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> dict[str, list[tuple[float, int, float | None, dict]]]:
    """Same as rank_candidates, but keep intermediate lists for freeze diagnostics."""
    mode = str(RANKING_POLICY.get("geo_mode", "v6")).strip().lower()
    if mode == "v5":
        after_geo = rank_candidates_v5(query, docs, evidence, anchor)
    else:
        after_geo = rank_candidates_v6(query, docs, evidence, anchor)
    after_name_address = prioritize_name_address(query, after_geo)
    after_name_match = prioritize_name_match_quality(query, after_name_address)
    return {
        "after_geo": after_geo,
        "after_name_address": after_name_address,
        "final": after_name_match,
    }


def haversine(left: dict[str, float], right: dict[str, float]) -> float:
    radius = 6_371_008.8
    lat1, lat2 = math.radians(left["lat"]), math.radians(right["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(right["lon"] - left["lon"])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def decode_polyline(encoded: str) -> list[list[float]]:
    """Decode Google/Goong encoded polyline into [lon, lat] coordinates."""
    coordinates: list[list[float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    while index < length:
        result = 0
        shift = 0
        while True:
            value = ord(encoded[index]) - 63
            index += 1
            result |= (value & 0x1F) << shift
            shift += 5
            if value < 0x20:
                break
        delta_lat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += delta_lat

        result = 0
        shift = 0
        while True:
            value = ord(encoded[index]) - 63
            index += 1
            result |= (value & 0x1F) << shift
            shift += 5
            if value < 0x20:
                break
        delta_lon = ~(result >> 1) if result & 1 else (result >> 1)
        lon += delta_lon
        coordinates.append([lon / 1e5, lat / 1e5])
    return coordinates


def goong_directions(origin: dict[str, float], destination: dict[str, float], vehicle: str) -> dict[str, Any]:
    if not GOONG_API_KEY:
        raise RuntimeError("goong_api_key_missing")
    query = urlencode(
        {
            "origin": f"{origin['lat']},{origin['lon']}",
            "destination": f"{destination['lat']},{destination['lon']}",
            "vehicle": vehicle,
            "api_key": GOONG_API_KEY,
        }
    )
    request = UrlRequest(
        f"{GOONG_DIRECTION_URL}?{query}",
        headers={
            # Cloudflare rejects Python-urllib's default UA (error 1010).
            "User-Agent": "poi-search-api/0.1 (+https://localhost; Goong Directions)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"goong_http_{exc.code}:{body or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"goong_network:{exc.reason}") from exc
    routes = payload.get("routes") or []
    if not routes:
        raise RuntimeError("goong_no_route")
    route = routes[0]
    legs = route.get("legs") or []
    if not legs:
        raise RuntimeError("goong_no_legs")
    encoded = ((route.get("overview_polyline") or {}).get("points")) or ""
    if not encoded:
        raise RuntimeError("goong_missing_polyline")
    coordinates = decode_polyline(encoded)
    if len(coordinates) < 2:
        raise RuntimeError("goong_polyline_too_short")
    return {
        "coordinates": coordinates,
        "distance_m": int((legs[0].get("distance") or {}).get("value") or 0),
        "duration_s": int((legs[0].get("duration") or {}).get("value") or 0),
    }


def resolve_anchor(origin: Origin | None) -> dict[str, float] | None:
    if origin is None:
        return None
    if origin.kind in {"gps", "map"}:
        if origin.point is None:
            raise HTTPException(422, detail={"code": "origin_point_required", "message": "Origin point is required"})
        if origin.kind == "gps" and origin.accuracy_m is not None and origin.accuracy_m > 200:
            return None
        return origin.point.model_dump()
    if not origin.poi_id:
        raise HTTPException(422, detail={"code": "origin_poi_required", "message": "Origin POI is required"})
    docs = runtime.documents([origin.poi_id])
    if not docs or not docs[0].get("origin_search_eligible"):
        raise HTTPException(422, detail={"code": "invalid_origin_poi", "message": "POI is not origin eligible"})
    return docs[0]["ranking_point"]


def retrieve(
    query: str,
) -> tuple[list[str], str, dict[str, float], dict[str, dict[str, float | None]]]:
    result = retrieve_detailed(query)
    return result["ids"], result["route"], result["timings"], result["evidence"]


def retrieve_detailed(query: str) -> dict[str, Any]:
    """Retrieve with explicit branch id lists for freeze/replay traces."""
    timings = {"encode": 0.0, "lexical": 0.0, "ann": 0.0, "fusion": 0.0}
    lexical_ids: list[str] = []
    dense_ids: list[str] = []
    if RETRIEVAL_PROFILE == "lexical_only" or (
        RETRIEVAL_PROFILE == "hybrid"
        and compact_length(query) < int(POLICY["retrieval"]["dense_min_compact_chars"])
    ):
        lexical_ids, timings["lexical"] = runtime.lexical(query)
        ids = list(lexical_ids)
        evidence = {
            poi_id: {"lexical_rank": rank, "dense_rank": None, "rrf": 1 / (RRF_CONSTANT + rank)}
            for rank, poi_id in enumerate(ids, 1)
        }
        route = "lexical_only" if RETRIEVAL_PROFILE == "lexical_only" else "lexical_short_query"
        return {
            "ids": ids,
            "route": route,
            "timings": timings,
            "evidence": evidence,
            "lexical_ids": lexical_ids,
            "dense_ids": dense_ids,
        }
    if RETRIEVAL_PROFILE == "dense_only":
        began = time.perf_counter()
        vector = runtime.encode(query)
        timings["encode"] = (time.perf_counter() - began) * 1000
        dense_ids, timings["ann"] = runtime.dense(vector)
        ids = list(dense_ids)
        evidence = {
            poi_id: {"lexical_rank": None, "dense_rank": rank, "rrf": 1 / (RRF_CONSTANT + rank)}
            for rank, poi_id in enumerate(ids, 1)
        }
        return {
            "ids": ids,
            "route": "dense_only",
            "timings": timings,
            "evidence": evidence,
            "lexical_ids": lexical_ids,
            "dense_ids": dense_ids,
        }
    lexical_future = runtime.pool.submit(runtime.lexical, query)
    began = time.perf_counter()
    vector = runtime.encode(query)
    timings["encode"] = (time.perf_counter() - began) * 1000
    dense_ids, timings["ann"] = runtime.dense(vector)
    lexical_ids, timings["lexical"] = lexical_future.result()
    began = time.perf_counter()
    ids = rrf(lexical_ids, dense_ids)
    timings["fusion"] = (time.perf_counter() - began) * 1000
    lexical_ranks = {poi_id: rank for rank, poi_id in enumerate(lexical_ids, 1)}
    dense_ranks = {poi_id: rank for rank, poi_id in enumerate(dense_ids, 1)}
    evidence = {}
    for poi_id in ids:
        lexical_rank = lexical_ranks.get(poi_id)
        dense_rank = dense_ranks.get(poi_id)
        evidence[poi_id] = {
            "lexical_rank": lexical_rank,
            "dense_rank": dense_rank,
            "rrf": (1 / (RRF_CONSTANT + lexical_rank) if lexical_rank else 0)
            + (1 / (RRF_CONSTANT + dense_rank) if dense_rank else 0),
        }
    return {
        "ids": ids,
        "route": "hybrid_long_query",
        "timings": timings,
        "evidence": evidence,
        "lexical_ids": lexical_ids,
        "dense_ids": dense_ids,
    }


def nearby_name_rescue_body(
    query: str,
    anchor: dict[str, float],
    *,
    size: int,
    radius_m: float,
) -> dict[str, Any] | None:
    """BBox + folded label/alias match. ranking_point is lat/lon doubles, not geo_point."""
    folded = fold(query)
    if len(folded) < 2:
        return None
    lat, lon = float(anchor["lat"]), float(anchor["lon"])
    dlat = radius_m / 111_195.0
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = radius_m / (111_195.0 * cos_lat)
    return {
        "size": size,
        "track_total_hits": False,
        "_source": ["ranking_point", "search_label", "search_aliases"],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"destination_searchable": True}},
                    {"range": {"ranking_point.lat": {"gte": lat - dlat, "lte": lat + dlat}}},
                    {"range": {"ranking_point.lon": {"gte": lon - dlon, "lte": lon + dlon}}},
                ],
                "should": [
                    {"term": {"label_folded": folded}},
                    {"prefix": {"label_folded": folded}},
                    {"term": {"aliases_folded": folded}},
                    {"prefix": {"aliases_folded": folded}},
                ],
                "minimum_should_match": 1,
            }
        },
    }


def merge_nearby_name_rescue(
    query: str,
    ids: list[str],
    evidence: dict,
    rescued: list[str],
) -> tuple[list[str], dict, int]:
    """Prepend nearby same-name hits so geo-v6 window can see them. Query-only unused."""
    if not rescued:
        return ids, evidence, 0
    seen = set(ids)
    new_ids = [poi_id for poi_id in rescued if poi_id not in seen]
    if not new_ids:
        return ids, evidence, 0
    best = max((float(evidence[poi_id]["rrf"] or 0) for poi_id in ids if poi_id in evidence), default=0.0)
    base = max(best, 1.0 / (RRF_CONSTANT + 1))
    for index, poi_id in enumerate(new_ids):
        evidence[poi_id] = {
            "lexical_rank": None,
            "dense_rank": None,
            "rrf": base + (len(new_ids) - index) * 1e-6,
            "nearby_rescue": True,
        }
    return new_ids + ids, evidence, len(new_ids)


def fetch_nearby_name_rescue(query: str, anchor: dict[str, float]) -> tuple[list[str], float]:
    """Return nearby POI ids with label/alias matching query, nearest first."""
    cfg = RANKING_POLICY.get("nearby_name_rescue") or {}
    if not bool(cfg.get("enabled", False)):
        return [], 0.0
    compact = compact_length(query)
    if compact < int(cfg.get("min_query_chars", 3)):
        return [], 0.0
    radius_m = float(cfg.get("radius_m", 5000))
    limit = max(1, int(cfg.get("limit", 15)))
    fetch_size = max(limit, int(cfg.get("fetch_size", 40)))
    body = nearby_name_rescue_body(query, anchor, size=fetch_size, radius_m=radius_m)
    if body is None:
        return [], 0.0
    began = time.perf_counter()
    response = runtime.client().request("POST", f"/{INDEX_NAME}/_search", body)
    elapsed = (time.perf_counter() - began) * 1000
    scored: list[tuple[float, str]] = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source") or {}
        point = source.get("ranking_point") or {}
        if point.get("lat") is None or point.get("lon") is None:
            continue
        distance = haversine(anchor, point)
        if distance > radius_m:
            continue
        doc = {
            "search_label": source.get("search_label", ""),
            "search_aliases": source.get("search_aliases") or [],
            "address": "",
            "canonical_id": hit["_id"],
        }
        # Keep exact/prefix name hits only — avoid weak cross-field noise inside bbox.
        label_fold = fold(doc["search_label"])
        q_fold = fold(query)
        aliases_fold = [fold(a) for a in doc["search_aliases"]]
        if not (
            label_fold == q_fold
            or label_fold.startswith(q_fold)
            or any(a == q_fold or a.startswith(q_fold) for a in aliases_fold)
            or name_match_class(query, doc) is not None
        ):
            continue
        scored.append((distance, hit["_id"]))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [poi_id for _, poi_id in scored[:limit]], elapsed


def _result_rows(
    ranked: list[tuple[float, int, float | None, dict]], top_k: int
) -> list[dict[str, Any]]:
    results = []
    for _, _, distance, doc in ranked[:top_k]:
        results.append({
            "poi_id": doc["canonical_id"], "name": doc["search_label"], "rank": len(results) + 1,
            "address_text": doc.get("address", ""), "context_text": doc.get("context_text", ""),
            "ranking_point": doc["ranking_point"], "routing_point": doc.get("routing_point"),
            "pickup_access_verified": doc.get("pickup_access_verified", False),
            "ranking_distance_m": round(distance) if distance is not None else None,
        })
    return results


def pipeline_trace(
    query: str,
    *,
    origin: Origin | None,
    personalized: bool,
    top_k: int,
) -> dict[str, Any]:
    """Full suggest pipeline with stage id lists for freeze failure classification."""
    timings: dict[str, float] = {"encode": 0.0, "lexical": 0.0, "ann": 0.0, "fusion": 0.0, "nearby_rescue": 0.0}
    began = time.perf_counter()
    retrieved = retrieve_detailed(query)
    timings.update(retrieved["timings"])
    ids = list(retrieved["ids"])
    evidence = retrieved["evidence"]
    route = retrieved["route"]
    lexical_ids = list(retrieved["lexical_ids"])
    dense_ids = list(retrieved["dense_ids"])
    after_rrf = list(ids)
    after_rescue = list(ids)
    rescued_n = 0
    rescued_ids: list[str] = []
    anchor = resolve_anchor(origin) if personalized else None
    if anchor is not None:
        rescued_ids, timings["nearby_rescue"] = fetch_nearby_name_rescue(query, anchor)
        ids, evidence, rescued_n = merge_nearby_name_rescue(query, ids, evidence, rescued_ids)
        after_rescue = list(ids)
        if rescued_n:
            route = f"{route}+nearby_name_rescue:{rescued_n}"
    docs = candidate_documents(ids, runtime.documents(ids))
    after_dedup_cap = [doc["canonical_id"] for doc in docs]
    stages = rank_candidates_traced(query, docs, evidence, anchor)
    ranked = stages["final"]
    results = _result_rows(ranked, top_k)
    timings["total"] = (time.perf_counter() - began) * 1000

    def ids_of(rows: list[tuple[float, int, float | None, dict]]) -> list[str]:
        return [doc["canonical_id"] for _, _, _, doc in rows]

    return {
        "route": route,
        "timings_ms": timings,
        "profile": RETRIEVAL_PROFILE,
        "policy_version": POLICY["policy_version"],
        "geo_mode": str(RANKING_POLICY.get("geo_mode", "v6")),
        "anchor": anchor,
        "rescued_n": rescued_n,
        "stages": {
            "lexical": lexical_ids,
            "dense": dense_ids,
            "rrf": after_rrf,
            "nearby_rescue_hits": rescued_ids,
            "after_nearby_rescue": after_rescue,
            "after_dedup_cap": after_dedup_cap,
            "after_geo": ids_of(stages["after_geo"]),
            "after_name_address": ids_of(stages["after_name_address"]),
            "after_name_match_quality": ids_of(stages["final"]),
            "final_top_k": [row["poi_id"] for row in results],
        },
        "results": results,
        "candidate_count": len(docs),
    }


def classify_target_loss(target: str | None, stages: dict[str, list[str]], top_k: int = 5) -> str | None:
    """Map missing intended POI to the earliest pipeline stage that dropped it."""
    if not target:
        return None
    final = stages.get("final_top_k") or []
    if target in final[:top_k]:
        return None
    lexical = stages.get("lexical") or []
    dense = stages.get("dense") or []
    rrf_ids = stages.get("rrf") or []
    after_rescue = stages.get("after_nearby_rescue") or []
    after_dedup = stages.get("after_dedup_cap") or []
    after_geo = stages.get("after_geo") or []
    after_addr = stages.get("after_name_address") or []
    after_match = stages.get("after_name_match_quality") or []
    in_retrieval = target in lexical or target in dense or target in rrf_ids
    if not in_retrieval and target not in after_rescue:
        return "retrieval_miss"
    if target in after_rescue and target not in after_dedup:
        return "lost_at_dedup_or_cap"
    if target in after_dedup and target not in after_geo:
        return "lost_at_geo"
    if target in after_geo and target not in after_addr:
        return "lost_at_name_address"
    if target in after_addr and target not in after_match:
        return "lost_at_name_match_quality"
    if target in after_match and target not in final[:top_k]:
        return "lost_below_top_k"
    if target in after_match:
        return "lost_below_top_k"
    return "ranking_miss"


def suggest(payload: SuggestRequest, personalized: bool) -> dict[str, Any]:
    if payload.expected_corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})
    if payload.session_id not in runtime.sessions:
        raise HTTPException(401, detail={"code": "invalid_session", "message": "Unknown session"})
    query = " ".join(payload.query.split())
    if not query:
        return response_payload(payload, [], None, {}, "empty_query", personalized, None)
    began = time.perf_counter()
    ids, route, timings, evidence = retrieve(query)
    anchor = resolve_anchor(payload.origin) if personalized else None
    rescued_n = 0
    if anchor is not None:
        rescued_ids, timings["nearby_rescue"] = fetch_nearby_name_rescue(query, anchor)
        ids, evidence, rescued_n = merge_nearby_name_rescue(query, ids, evidence, rescued_ids)
        if rescued_n:
            route = f"{route}+nearby_name_rescue:{rescued_n}"
    docs = candidate_documents(ids, runtime.documents(ids))
    ranked = rank_candidates(query, docs, evidence, anchor)
    results = _result_rows(ranked, payload.top_k)
    timings["total"] = (time.perf_counter() - began) * 1000
    exposure_id = f"exp-{uuid.uuid4()}" if results else None
    if exposure_id:
        runtime.exposures[exposure_id] = {
            "session_id": payload.session_id, "context_revision": payload.context_revision,
            "shown_ids": [item["poi_id"] for item in results], "displayed": False,
            "created_at": time.time(),
        }
    return response_payload(payload, results, exposure_id, timings, route, personalized, anchor, len(docs))


def response_payload(payload: SuggestRequest, results: list[dict], exposure_id: str | None,
                     timings: dict, route: str, personalized: bool, anchor: dict | None, candidate_count: int = 0) -> dict[str, Any]:
    return {
        "request_id": payload.request_id, "context_revision": payload.context_revision,
        "exposure_id": exposure_id, "selectable": exposure_id is not None, "versions": versions(),
        "scope_summary": {
            "mode": "global_with_geo_heuristic" if personalized and anchor else "global",
            "coverage_id": "hanoi-osm-stable-v1", "primary_region_id": None,
            "primary_radius_m": None,
            "notes": [
                route,
                f"Stage 2 policy {POLICY['policy_version']}: {RETRIEVAL_PROFILE}, bounded text-compatible geo; no user/time model",
            ],
        },
        "resolved_context_time": (payload.context_time or datetime.now(UTC)).isoformat(),
        "history_version": None, "candidate_count": candidate_count, "results": results,
        "degraded_reasons": [], "timings_ms": timings,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    count = runtime.client().request("GET", f"/{INDEX_NAME}/_count")["count"]
    return {"status": "ok" if count == EXPECTED_ROWS else "degraded", "index": INDEX_NAME, "corpus_rows": count}


@app.post("/v1/sessions")
def create_session(response: Response) -> dict[str, str]:
    session_id = f"session-{uuid.uuid4()}"
    runtime.sessions.add(session_id)
    response.set_cookie("poi_session", session_id, httponly=True, samesite="lax")
    return {"session_id": session_id}


@app.get("/v1/status")
def status() -> dict[str, Any]:
    count = runtime.client().request("GET", f"/{INDEX_NAME}/_count")["count"]
    return {"ready": count == EXPECTED_ROWS, "versions": versions(), "coverage_id": "hanoi-osm-stable-v1",
            "profile": RETRIEVAL_PROFILE,
            "capabilities": [
                RETRIEVAL_PROFILE,
                "geo_heuristic",
                "straight_line_preview",
                *(["goong_road_route"] if GOONG_API_KEY else []),
            ],
        }


@app.get("/v1/demo/users")
def demo_users() -> list[dict[str, str]]:
    return []


@app.get("/v1/origins")
def origins(q: str = "", limit: int = 20) -> dict[str, Any]:
    body = lexical_body(q.strip(), max(1, min(limit, 50)))
    if not q.strip():
        body["query"] = {"bool": {"filter": []}}
    body["query"]["bool"]["filter"] = [{"term": {"origin_search_eligible": True}}]
    ids, _ = search(runtime.client(), body)
    items = [{"poi_id": d["canonical_id"], "name": d["search_label"], "ranking_point": d["ranking_point"],
              "pickup_access_verified": d.get("pickup_access_verified", False)} for d in runtime.documents(ids)]
    return {"corpus_version": CORPUS_VERSION, "items": items, "next_cursor": None}


class TraceSuggestRequest(StrictModel):
    request_id: str
    session_id: str
    context_revision: int = Field(ge=1)
    query: str = Field(max_length=200)
    top_k: int = Field(default=50, ge=1, le=50)
    expected_corpus_version: str
    personalized: bool = False
    origin: Origin | None = None
    target_poi_id: str | None = None


@app.post("/v1/suggest")
def suggest_query_only(payload: SuggestRequest) -> dict[str, Any]:
    return suggest(payload, False)


@app.post("/v1/suggest/personalized")
def suggest_personalized(payload: SuggestRequest) -> dict[str, Any]:
    return suggest(payload, True)


@app.post("/v1/debug/trace_suggest")
def debug_trace_suggest(payload: TraceSuggestRequest) -> dict[str, Any]:
    """Freeze/replay diagnostics only. Same pipeline as suggest; no exposure write."""
    if payload.expected_corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})
    if payload.session_id not in runtime.sessions:
        raise HTTPException(401, detail={"code": "invalid_session", "message": "Unknown session"})
    query = " ".join(payload.query.split())
    if not query:
        empty_stages = {
            "lexical": [], "dense": [], "rrf": [], "nearby_rescue_hits": [],
            "after_nearby_rescue": [], "after_dedup_cap": [], "after_geo": [],
            "after_name_address": [], "after_name_match_quality": [], "final_top_k": [],
        }
        return {
            "request_id": payload.request_id,
            "route": "empty_query",
            "stages": empty_stages,
            "results": [],
            "failure_class": None,
            "target_ranks": {},
        }
    traced = pipeline_trace(
        query,
        origin=payload.origin,
        personalized=payload.personalized,
        top_k=payload.top_k,
    )
    stages = traced["stages"]
    target = payload.target_poi_id
    ranks = {}
    if target:
        for name, ids in stages.items():
            if name == "nearby_rescue_hits":
                continue
            try:
                ranks[name] = ids.index(target) + 1
            except ValueError:
                ranks[name] = None
    return {
        "request_id": payload.request_id,
        "versions": versions(),
        "route": traced["route"],
        "timings_ms": traced["timings_ms"],
        "profile": traced["profile"],
        "policy_version": traced["policy_version"],
        "geo_mode": traced["geo_mode"],
        "rescued_n": traced["rescued_n"],
        "candidate_count": traced["candidate_count"],
        "stages": {key: value[:80] for key, value in stages.items()},
        "results": traced["results"],
        "target_poi_id": target,
        "target_ranks": ranks,
        "failure_class": classify_target_loss(target, stages, top_k=min(5, payload.top_k)),
    }


@app.post("/v1/exposures/displayed")
def displayed(payload: DisplayRequest) -> dict[str, Any]:
    exposure = runtime.exposures.get(payload.exposure_id)
    if not exposure:
        raise HTTPException(404, detail={"code": "exposure_not_found", "message": "Exposure not found"})
    if exposure["session_id"] != payload.session_id or exposure["context_revision"] != payload.context_revision:
        raise HTTPException(409, detail={"code": "exposure_conflict", "message": "Exposure context mismatch"})
    exposure["displayed"] = True
    return {"exposure_id": payload.exposure_id, "displayed": True}


@app.post("/v1/select")
def select(payload: SelectRequest) -> dict[str, Any]:
    exposure = runtime.exposures.get(payload.exposure_id)
    if exposure and (exposure["session_id"] != payload.session_id or exposure["context_revision"] != payload.context_revision):
        raise HTTPException(409, detail={"code": "exposure_conflict", "message": "Exposure context mismatch"})
    key = (payload.session_id, payload.idempotency_key)
    if key in runtime.selections:
        cached = runtime.selections[key]
        if cached["selected_poi_id"] != payload.selected_poi_id or cached["exposure_id"] != payload.exposure_id:
            raise HTTPException(409, detail={"code": "idempotency_conflict", "message": "Key reused with another POI"})
        return cached
    exposure = runtime.exposures.get(payload.exposure_id)
    if not exposure or not exposure["displayed"] or payload.selected_poi_id not in exposure["shown_ids"]:
        raise HTTPException(409, detail={"code": "invalid_selection", "message": "Selection is not in a displayed exposure"})
    result = {"selection_id": f"sel-{uuid.uuid4()}", "exposure_id": payload.exposure_id,
              "selected_poi_id": payload.selected_poi_id, "corpus_version": CORPUS_VERSION,
              "recorded_at": datetime.now(UTC).isoformat(), "history_version": "in-memory-demo-v1",
              "event_source": "demo_selection"}
    runtime.selections[key] = result
    return result


@app.post("/v1/route-preview")
def route_preview(payload: RouteRequest) -> dict[str, Any]:
    if payload.corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})

    def point_from_poi(poi_id: str | None) -> dict[str, float] | None:
        if not poi_id:
            return None
        docs = runtime.documents([poi_id])
        if not docs:
            raise HTTPException(404, detail={"code": "poi_not_found", "message": f"POI missing: {poi_id}"})
        return docs[0]["ranking_point"]

    origin = payload.origin_point.model_dump() if payload.origin_point else point_from_poi(payload.origin_poi_id)
    destination = (
        payload.destination_point.model_dump()
        if payload.destination_point
        else point_from_poi(payload.destination_poi_id)
    )
    if origin is None:
        return {
            "status": "missing_origin",
            "corpus_version": CORPUS_VERSION,
            "mode_used": None,
            "geometry": None,
            "geodesic_distance_m": None,
            "route_distance_m": None,
            "route_duration_s": None,
            "reason": "missing_origin",
        }
    if destination is None:
        raise HTTPException(422, detail={"code": "missing_destination", "message": "Destination point or POI is required"})

    geodesic = round(haversine(origin, destination))
    if payload.mode == "road":
        try:
            road = goong_directions(origin, destination, payload.vehicle)
            return {
                "status": "ok",
                "corpus_version": CORPUS_VERSION,
                "mode_used": "road",
                "geometry": {"type": "LineString", "coordinates": road["coordinates"]},
                "geodesic_distance_m": geodesic,
                "route_distance_m": road["distance_m"],
                "route_duration_s": road["duration_s"],
                "reason": f"goong_directions:{payload.vehicle}",
            }
        except RuntimeError as exc:
            if not payload.allow_fallback:
                return {
                    "status": "unavailable",
                    "corpus_version": CORPUS_VERSION,
                    "mode_used": None,
                    "geometry": None,
                    "geodesic_distance_m": geodesic,
                    "route_distance_m": None,
                    "route_duration_s": None,
                    "reason": str(exc),
                }
            # fall through to straight line

    return {
        "status": "ok",
        "corpus_version": CORPUS_VERSION,
        "mode_used": "straight_line",
        "geometry": {
            "type": "LineString",
            "coordinates": [[origin["lon"], origin["lat"]], [destination["lon"], destination["lat"]]],
        },
        "geodesic_distance_m": geodesic,
        "route_distance_m": None,
        "route_duration_s": None,
        "reason": "straight_line_illustration_not_road_route",
    }
