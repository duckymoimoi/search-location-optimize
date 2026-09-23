"""Runnable POI Search demo API backed by Elasticsearch 9 + mE5-small."""

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
from demo_users import append_selection, history_snapshot, known_user, public_users
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from transformers import AutoModel, AutoTokenizer

class ElasticsearchClient:
    def __init__(self, base_url: str):
        parsed = urlparse(base_url)
        self.connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        self.connection.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        response = self.connection.getresponse()
        content = response.read()
        if response.status >= 400:
            raise RuntimeError(f"Elasticsearch {response.status}: {content.decode(errors='replace')}")
        return json.loads(content) if content else None


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join("".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)).casefold().split())


def alnum_compact(text: str) -> str:
    """Fold + strip non-alphanumerics so S2.02 / s2-02 / s202 share one key."""
    return "".join(ch for ch in fold(text) if ch.isalnum())


def glue_code_spans(query: str) -> str:
    """Collapse dotted or hyphenated codes into one token for the standard analyzer.

    The index analyzer splits on '.'. Without this, s10.2 is tokens s10 + 2 and
    matches every S10.* label, while s1.02 also matches S2.02 via the shared 02.
    No building-code pattern: any alphanumeric span with an internal . or -.
    Slash stays a separator so 16/2 does not become 162.
    """
    span = re.compile(r"[^\W_]+(?:[.\-][^\W_]+)+", re.UNICODE)
    return span.sub(lambda match: alnum_compact(match.group(0)), query or "")


def _token_kind(token: str) -> str:
    """letter = letters only, number = digits only, code = both."""
    has_letter = any(ch.isalpha() for ch in token)
    has_digit = any(ch.isdigit() for ch in token)
    if has_letter and has_digit:
        return "code"
    if has_letter:
        return "letter"
    if has_digit:
        return "number"
    return "other"


def is_code_key(compact: str) -> bool:
    """A code key has both a letter and a digit. A pure number is not a code."""
    return (
        len(compact) >= 2
        and any(ch.isalpha() for ch in compact)
        and any(ch.isdigit() for ch in compact)
    )


def query_code_compacts(query: str) -> list[str]:
    """One compact key per token that contains both a letter and a digit.

    Tokens are not joined. A house number plus the following words must not
    become a single code, and a pure number must not hit codes_compact.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in fold(glue_code_spans(query)).split():
        compact = alnum_compact(raw)
        if not is_code_key(compact) or compact in seen:
            continue
        seen.add(compact)
        out.append(compact)
    return out


def letter_runs(tokens: list[str]) -> list[list[str]]:
    """Maximal runs of letter-only tokens, in query order."""
    runs: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if _token_kind(token) == "letter":
            current.append(token)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def lexical_text_and_numbers(analyzed: str) -> tuple[str, list[str]]:
    """BM25 text, plus pure-number tokens that must not enter IDF.

    When the query has both a letter span and a pure number, BM25 sees only
    the letters. The number is scored later as a bounded bonus. Queries with
    no letter span, or no pure number, keep the full analyzed string.
    """
    tokens = text_tokens(analyzed)
    letters = [token for token in tokens if _token_kind(token) == "letter"]
    numbers = [token for token in tokens if _token_kind(token) == "number"]
    if letters and numbers:
        return " ".join(letters), numbers
    return analyzed, []


def number_bonus_clause(token: str, boost: float) -> dict[str, Any]:
    """Flat score for one pure-number token. The boost is the whole score."""
    fields = ("search_label", "search_aliases", "address", "context_text")
    return {
        "constant_score": {
            "filter": {
                "bool": {
                    "should": [
                        {"match_phrase": {field: {"query": token}}} for field in fields
                    ],
                    "minimum_should_match": 1,
                }
            },
            "boost": boost,
        }
    }


def letter_span_phrases(analyzed: str, lex: dict[str, Any]) -> list[dict[str, Any]]:
    """Phrase each letter run of length >= 2 when a pure number is also present."""
    tokens = text_tokens(analyzed)
    if not any(_token_kind(token) == "number" for token in tokens):
        return []
    clauses: list[dict[str, Any]] = []
    phrase_boost = lex["phrase"]
    address_boost = lex.get("phrase_address", 6.0)
    for run in letter_runs(tokens):
        if len(run) < 2:
            continue
        phrase = " ".join(run)
        clauses.append(
            {"match_phrase": {"search_label": {"query": phrase, "slop": 1, "boost": phrase_boost}}}
        )
        clauses.append(
            {
                "match_phrase": {
                    "address": {"query": phrase, "slop": 2, "boost": address_boost}
                }
            }
        )
    return clauses


def lexical_body(query: str, size: int) -> dict[str, Any]:
    """Fielded ES lexical: exact + phrase + cross/best OR + context.

    A pure number beside a letter span is a constant_score bonus, not a BM25
    term, so a rare house number cannot outrank the words. MSM=1; fuzzy off
    by default.
    """
    folded = fold(query)
    analyzed = glue_code_spans(query)
    text_query, number_tokens = lexical_text_and_numbers(analyzed)
    lex = LEXICAL_CONFIG
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": lex["exact"]}}},
        {"term": {"aliases_folded": {"value": folded, "boost": lex["alias_exact"]}}},
        {"match_phrase": {"search_label": {"query": analyzed, "slop": 1, "boost": lex["phrase"]}}},
        {
            "match_phrase": {
                "address": {"query": analyzed, "slop": 2, "boost": lex.get("phrase_address", 6.0)}
            }
        },
        {
            "multi_match": {
                "query": text_query,
                "fields": [
                    "search_label^8",
                    "search_aliases^5",
                    "address^6",
                    "context_text^3",
                ],
                "type": "cross_fields",
                "operator": "or",
                "minimum_should_match": "50%",
                "boost": lex.get("cross_or", 5.0),
            }
        },
        {
            "multi_match": {
                "query": text_query,
                "fields": ["search_label^4", "address^3", "context_text^2"],
                "type": "best_fields",
                "operator": "or",
                "boost": lex.get("best_or", 2.0),
            }
        },
        {
            "multi_match": {
                "query": text_query,
                "fields": ["search_label.prefix^5", "search_aliases.prefix^3"],
                "type": "best_fields",
                "operator": "or",
                "boost": lex["prefix_field"],
            }
        },
    ]
    should.extend(letter_span_phrases(analyzed, lex))
    number_boost = float(lex.get("number_bonus", 1.5))
    seen_numbers: set[str] = set()
    if number_boost > 0:
        for token in number_tokens:
            if token in seen_numbers:
                continue
            seen_numbers.add(token)
            should.append(number_bonus_clause(token, number_boost))
    code_keys = query_code_compacts(query)
    if code_keys:
        code_boost = float(lex.get("code_compact", 14.0))
        should.append({"terms": {"codes_compact": code_keys, "boost": code_boost}})
        # Prefix on compact codes: s20 → s202 (generic keyword prefix, not a fixed pattern).
        for key in code_keys:
            if len(key) >= 3:
                should.append(
                    {"prefix": {"codes_compact": {"value": key, "boost": code_boost * 0.7}}}
                )
    if len(folded) >= 2:
        should += [
            {"prefix": {"label_folded": {"value": folded, "boost": lex["leading_prefix"]}}},
            {
                "prefix": {
                    "aliases_folded": {
                        "value": folded,
                        "boost": lex["leading_prefix"] * 0.8,
                    }
                }
            },
        ]
    expanded = expand_query(query)
    if normalized_text(expanded) != normalized_text(query):
        expanded_analyzed = glue_code_spans(expanded)
        expanded_text, expanded_numbers = lexical_text_and_numbers(expanded_analyzed)
        should.append(
            {
                "multi_match": {
                    "query": expanded_text,
                    "fields": ["search_label^6", "address^4", "context_text^2"],
                    "type": "cross_fields",
                    "operator": "or",
                    "boost": 2.0,
                }
            }
        )
        if expanded_numbers:
            # Full rewritten phrase still requires the number, so an exact
            # expanded name keeps its phrase hit. BM25 above uses letters only.
            should.append(
                {
                    "match_phrase": {
                        "search_label": {
                            "query": expanded_analyzed,
                            "slop": 1,
                            "boost": lex["phrase"],
                        }
                    }
                }
            )
            should.append(
                {
                    "match_phrase": {
                        "address": {
                            "query": expanded_analyzed,
                            "slop": 2,
                            "boost": lex.get("phrase_address", 6.0),
                        }
                    }
                }
            )
            should.extend(letter_span_phrases(expanded_analyzed, lex))
            if number_boost > 0:
                for token in expanded_numbers:
                    if token in seen_numbers:
                        continue
                    seen_numbers.add(token)
                    should.append(number_bonus_clause(token, number_boost))
    fuzzy_boost = float(lex.get("fuzzy") or 0.0)
    if fuzzy_boost > 0:
        fuzzy_terms = [token for token in text_tokens(query) if token.isalpha() and len(token) >= 4]
        if fuzzy_terms:
            should.append(
                {
                    "multi_match": {
                        "query": " ".join(fuzzy_terms),
                        "fields": ["search_label^4", "search_aliases^3"],
                        "type": "best_fields",
                        "operator": "or",
                        "fuzziness": "AUTO",
                        "prefix_length": 1,
                        "max_expansions": 50,
                        "boost": fuzzy_boost,
                    }
                }
            )
    # Always 1: requiring ≥2 should-clauses zeroed recall on multi-token gold queries.
    minimum_should_match = int(lex.get("minimum_should_match", 1))
    return {
        "size": size,
        "track_total_hits": False,
        "_source": False,
        "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [{"term": {"destination_searchable": True}}],
                "should": should,
                "minimum_should_match": minimum_should_match,
            }
        },
    }


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


def rrf(left: list[str], right: list[str]) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, int] = {}
    for branch in (left[:BRANCH_DEPTH], right[:BRANCH_DEPTH]):
        for rank, poi_id in enumerate(branch, 1):
            scores[poi_id] += 1 / (RRF_CONSTANT + rank)
            best[poi_id] = min(best.get(poi_id, rank), rank)
    return sorted(scores, key=lambda poi_id: (-scores[poi_id], best[poi_id], poi_id))

MODEL_ID = os.environ.get("POI_MODEL_ID", "intfloat/multilingual-e5-small")
MODEL_DIR = Path(os.environ.get("POI_MODEL_DIR", os.environ.get("HANOI_POI_MODEL_DIR", "")))
ES_URL = os.environ.get(
    "POI_ES_URL",
    os.environ.get("HANOI_POI_OPENSEARCH_URL", "http://elasticsearch:9200"),
)
INDEX_NAME = os.environ.get("POI_INDEX", os.environ.get("HANOI_POI_INDEX", "vn-poi-core-v1-me5-small"))
EXPECTED_ROWS = int(
    os.environ.get("POI_EXPECTED_ROWS", os.environ.get("HANOI_POI_EXPECTED_ROWS", "186322"))
)
POLICY_PATH = Path(
    os.environ.get(
        "POI_SEARCH_POLICY",
        os.environ.get("HANOI_POI_SEARCH_POLICY", str(Path(__file__).with_name("search_policy.json"))),
    )
)
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
RETRIEVAL_PROFILE = os.environ.get(
    "POI_RETRIEVAL_PROFILE",
    os.environ.get("HANOI_POI_RETRIEVAL_PROFILE", POLICY["default_retrieval_profile"]),
)
GOONG_API_KEY = os.environ.get("GOONG_API_KEY", "").strip()
GOONG_DIRECTION_URL = os.environ.get("GOONG_DIRECTION_URL", "https://rsapi.goong.io/Direction").strip()
if RETRIEVAL_PROFILE not in {"lexical_only", "dense_only", "hybrid"}:
    raise ValueError(f"Unsupported retrieval profile: {RETRIEVAL_PROFILE}")
CORPUS_VERSION = os.environ.get("POI_CORPUS_VERSION", "vn-poi-core-v1")
BRANCH_DEPTH = int(POLICY["retrieval"]["branch_depth"])
ANN_CANDIDATES = int(POLICY["retrieval"]["ann_candidates"])
RRF_CONSTANT = int(POLICY["retrieval"]["rrf_constant"])
RANKING_POLICY = POLICY["ranking"]
LEXICAL_CONFIG = POLICY["lexical"]
RELEASE_ID = os.environ.get("POI_RELEASE_ID", "vn-poi-demo-me5-r1")
EMBEDDING_SPACE_ID = os.environ.get("POI_EMBEDDING_SPACE_ID", "me5-small-passage-384")
PASSAGE_BUILDER_VERSION = os.environ.get("POI_PASSAGE_BUILDER_VERSION", "passage_context-v1")


def resolve_model_source() -> str:
    """Prefer local finetuned dir when present; otherwise Hugging Face model id."""
    if MODEL_DIR and (MODEL_DIR / "final_model").exists():
        return str(MODEL_DIR / "final_model")
    if MODEL_DIR and (MODEL_DIR / "config.json").exists():
        return str(MODEL_DIR)
    return MODEL_ID


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


runtime = Runtime()
app = FastAPI(title="VN POI Search Demo", version="1.0.0")
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
            runtime.dense(runtime.encode(glue_code_spans(query)))


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
        "equivalent-name-exp-decay-v6+nearby-name-rescue"
        if geo_mode == "v6"
        else "field-aware-bounded-geo-v5+nearby-name-rescue"
    )
    if not (RANKING_POLICY.get("nearby_name_rescue") or {}).get("enabled", False):
        feature = (
            "equivalent-name-exp-decay-v6"
            if geo_mode == "v6"
            else "field-aware-bounded-geo-v5"
        )
    return {
        "release_id": RELEASE_ID,
        "corpus_version": CORPUS_VERSION,
        "index_version": INDEX_NAME,
        "encoder_id": MODEL_ID,
        "embedding_space_id": EMBEDDING_SPACE_ID,
        "passage_builder_version": PASSAGE_BUILDER_VERSION,
        "scope_policy_version": "global-v1",
        "candidate_policy_version": f"{POLICY['policy_version']}:safe-candidates-v5:{RETRIEVAL_PROFILE}",
        "ranker_id": ranker,
        "feature_version": feature,
        "model_source": getattr(runtime, "model_source", MODEL_ID),
    }


def compact_length(value: str) -> int:
    """Character length used to skip dense on short queries.

    Dots and hyphens inside codes do not count, so s10.2 and s102 take the same route.
    """
    text = unicodedata.normalize("NFKC", value or "")
    text = "".join(ch for ch in text if ch not in ".-")
    return len("".join(text.split()))


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


def mixed_text_number_signals(query: str, document: dict[str, Any]) -> tuple[int, float, float]:
    """Letter-span length, letter coverage, number coverage.

    All three stay 0 unless the query has both a letter run and a pure number,
    so letter-only ranking is unchanged. A longer contiguous letter run outranks
    a number hit. The number only breaks ties inside the same letter span.
    """
    tokens = text_tokens(query)
    letters = [token for token in tokens if _token_kind(token) == "letter"]
    numbers = [token for token in tokens if _token_kind(token) == "number"]
    if not letters or not numbers:
        return 0, 0.0, 0.0

    name_tokens = text_tokens(
        " ".join([document.get("search_label", ""), *(document.get("search_aliases") or [])])
    )
    addr_tokens = text_tokens(document.get("address", "") or "")
    best = 0
    for run in letter_runs(tokens):
        for length in range(len(run), 0, -1):
            found = False
            for start in range(len(run) - length + 1):
                span = run[start : start + length]
                allow_prefix = span[-1] == tokens[-1]
                if _contiguous_span_in_field(
                    span, name_tokens, allow_final_prefix=allow_prefix
                ) or _contiguous_span_in_field(
                    span, addr_tokens, allow_final_prefix=allow_prefix
                ):
                    best = max(best, length)
                    found = True
                    break
            if found:
                break

    available = set(name_tokens) | set(addr_tokens)
    letter_hits = 0.0
    for index, token in enumerate(tokens):
        if _token_kind(token) != "letter":
            continue
        if _token_in_set(token, available, allow_prefix=(index == len(tokens) - 1)):
            letter_hits += 1.0
    number_hits = sum(1 for token in numbers if token in available)
    return best, letter_hits / len(letters), number_hits / len(numbers)


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

    When the query mixes a letter run with a pure number, the letter span is the
    next key after name class. The number only orders hits that share that span.
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
        span, letter_cov, number_cov = mixed_text_number_signals(query, doc)
        # `position` keeps post-geo order when phrase quality ties.
        decorated.append(
            (level, accent_hit, span, letter_cov, number_cov, coverage, position, score, rank, distance, doc)
        )
    decorated.sort(
        key=lambda row: (
            -row[0], -row[1], -row[2], -row[3], -row[4], -row[5], row[6], -row[7], row[10]["canonical_id"]
        )
    )
    return [
        (score, rank, distance, doc)
        for _, _, _, _, _, _, _, score, rank, distance, doc in decorated
    ]


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


def exponential_distance_points(distance_m: float | None) -> float:
    """Capped exponential decay. The cap stays below one match tier, so a nearer partial cannot pass an exact hit."""
    cap = min(0.99, max(0.0, float(RANKING_POLICY.get("geo_score_cap", RANKING_POLICY.get("geo_blend", 0.35)))))
    decay_m = max(1.0, float(RANKING_POLICY.get("geo_decay_m", 5000)))
    if distance_m is None:
        return 0.0
    return cap * math.exp(-max(0.0, float(distance_m)) / decay_m)


def rank_candidates_v6(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Reorder only the head's equivalent-name cohort by capped exp(-d/tau).

    A stricter name/code match is a different class and is not moved. The decay
    term is at most geo_score_cap < 1, so it cannot cross one match tier.
    Outside the cohort, order is unchanged. RRF itself is not rewritten.
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
    cohort = sorted(
        (ranked[i] for i in slots),
        key=lambda row: (-exponential_distance_points(row[2]), row[1]),
    )
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


def _history_cohort_key(query: str, doc: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Same name class, and the same address/code evidence, may be reordered by history."""
    match = name_match_class(query, doc)
    if match is None:
        return None
    codes = [token for token in text_tokens(query) if any(ch.isdigit() for ch in token)]
    fields = set(text_tokens(" ".join([
        doc.get("search_label", ""),
        doc.get("address", ""),
        " ".join(doc.get("search_aliases") or []),
    ])))
    code_hit = int(bool(codes) and all(token in fields for token in codes))
    address_hit = int(name_address_evidence(query, doc) > 0)
    return (int(match[0]), int(match[1]), address_hit, code_hit)


def apply_history_cohort(
    query: str,
    ranked: list[tuple[float, int, float | None, dict]],
    preferred_ids: list[str],
) -> list[tuple[float, int, float | None, dict]]:
    """Move history hits to the front of the head's equivalent-name window.

    Slots outside that name class, or with different address/code evidence, stay put.
    A preferred id that is not already in the window is not pulled in.
    """
    if not ranked or not preferred_ids:
        return ranked
    head_key = _history_cohort_key(query, ranked[0][3])
    if head_key is None:
        return ranked
    window = max(1, min(20, int(RANKING_POLICY.get("geo_equivalent_window", 10))))
    slots = [
        index
        for index, row in enumerate(ranked[:window])
        if _history_cohort_key(query, row[3]) == head_key
    ]
    if len(slots) < 2:
        return ranked
    preferred_rank = {poi_id: index for index, poi_id in enumerate(preferred_ids)}
    if not any(ranked[index][3]["canonical_id"] in preferred_rank for index in slots):
        return ranked
    cohort = [ranked[index] for index in slots]
    chosen = [row for row in cohort if row[3]["canonical_id"] in preferred_rank]
    chosen.sort(key=lambda row: preferred_rank[row[3]["canonical_id"]])
    rest = [row for row in cohort if row[3]["canonical_id"] not in preferred_rank]
    updated = list(ranked)
    for slot, row in zip(slots, chosen + rest):
        updated[slot] = row
    return updated


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


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _origin_point(point: Any) -> dict[str, float]:
    raw = point.model_dump() if hasattr(point, "model_dump") else point
    return {"lat": float(raw["lat"]), "lon": float(raw["lon"])}


def resolve_anchor(
    origin: Origin | None, *, now: datetime | None = None
) -> tuple[dict[str, float] | None, list[str]]:
    """Anchor for personalized scope. Stale or inaccurate GPS is dropped, not treated as 0 m."""
    if origin is None:
        return None, []
    max_accuracy_m = 200.0
    max_age_s = 120.0
    future_s = 30.0
    moment = _as_utc(now or datetime.now(UTC))
    if origin.kind in {"gps", "map"}:
        if origin.point is None:
            raise HTTPException(422, detail={"code": "origin_point_required", "message": "Origin point is required"})
        if origin.kind == "gps":
            if origin.observed_at is not None:
                observed = _as_utc(origin.observed_at)
                if (observed - moment).total_seconds() > future_s:
                    raise HTTPException(
                        422, detail={"code": "origin_in_future", "message": "GPS observation is in the future"}
                    )
                if (moment - observed).total_seconds() > max_age_s:
                    return None, ["gps_stale"]
            if origin.accuracy_m is not None and origin.accuracy_m > max_accuracy_m:
                return None, ["gps_accuracy"]
        return _origin_point(origin.point), []
    if not origin.poi_id:
        raise HTTPException(422, detail={"code": "origin_poi_required", "message": "Origin POI is required"})
    docs = runtime.documents([origin.poi_id])
    if not docs or not docs[0].get("origin_search_eligible"):
        raise HTTPException(422, detail={"code": "invalid_origin_poi", "message": "POI is not origin eligible"})
    return docs[0]["ranking_point"], []


def retrieve(
    query: str,
) -> tuple[list[str], str, dict[str, float], dict[str, dict[str, float | None]]]:
    result = retrieve_detailed(query)
    return result["ids"], result["route"], result["timings"], result["evidence"]


def _lexical_evidence(ids: list[str]) -> dict[str, dict[str, float | None]]:
    return {
        poi_id: {"lexical_rank": rank, "dense_rank": None, "rrf": 1 / (RRF_CONSTANT + rank)}
        for rank, poi_id in enumerate(ids, 1)
    }


def _dense_evidence(ids: list[str]) -> dict[str, dict[str, float | None]]:
    return {
        poi_id: {"lexical_rank": None, "dense_rank": rank, "rrf": 1 / (RRF_CONSTANT + rank)}
        for rank, poi_id in enumerate(ids, 1)
    }


def _hybrid_evidence(lexical_ids: list[str], dense_ids: list[str]) -> tuple[list[str], dict[str, dict[str, float | None]]]:
    ids = rrf(lexical_ids, dense_ids)
    lexical_ranks = {poi_id: rank for rank, poi_id in enumerate(lexical_ids, 1)}
    dense_ranks = {poi_id: rank for rank, poi_id in enumerate(dense_ids, 1)}
    evidence: dict[str, dict[str, float | None]] = {}
    for poi_id in ids:
        lexical_rank = lexical_ranks.get(poi_id)
        dense_rank = dense_ranks.get(poi_id)
        evidence[poi_id] = {
            "lexical_rank": lexical_rank,
            "dense_rank": dense_rank,
            "rrf": (1 / (RRF_CONSTANT + lexical_rank) if lexical_rank else 0)
            + (1 / (RRF_CONSTANT + dense_rank) if dense_rank else 0),
        }
    return ids, evidence


def retrieve_detailed(query: str) -> dict[str, Any]:
    """Retrieve with explicit branch id lists for freeze/replay traces.

    A disabled profile is not degraded. A hybrid branch that raises falls back
    to the branch that still returned; both failing is a hard error.
    """
    timings = {"encode": 0.0, "lexical": 0.0, "ann": 0.0, "fusion": 0.0}
    lexical_ids: list[str] = []
    dense_ids: list[str] = []
    degraded: list[str] = []
    if RETRIEVAL_PROFILE == "lexical_only" or (
        RETRIEVAL_PROFILE == "hybrid"
        and compact_length(query) < int(POLICY["retrieval"]["dense_min_compact_chars"])
    ):
        lexical_ids, timings["lexical"] = runtime.lexical(query)
        ids = list(lexical_ids)
        route = "lexical_only" if RETRIEVAL_PROFILE == "lexical_only" else "lexical_short_query"
        return {
            "ids": ids,
            "route": route,
            "timings": timings,
            "evidence": _lexical_evidence(ids),
            "lexical_ids": lexical_ids,
            "dense_ids": dense_ids,
            "degraded_reasons": degraded,
        }
    if RETRIEVAL_PROFILE == "dense_only":
        began = time.perf_counter()
        vector = runtime.encode(glue_code_spans(query))
        timings["encode"] = (time.perf_counter() - began) * 1000
        dense_ids, timings["ann"] = runtime.dense(vector)
        ids = list(dense_ids)
        return {
            "ids": ids,
            "route": "dense_only",
            "timings": timings,
            "evidence": _dense_evidence(ids),
            "lexical_ids": lexical_ids,
            "dense_ids": dense_ids,
            "degraded_reasons": degraded,
        }
    lexical_future = runtime.pool.submit(runtime.lexical, query)
    dense_failed = False
    lexical_failed = False
    began = time.perf_counter()
    try:
        vector = runtime.encode(glue_code_spans(query))
        timings["encode"] = (time.perf_counter() - began) * 1000
        dense_ids, timings["ann"] = runtime.dense(vector)
    except Exception:
        dense_failed = True
        degraded.append("dense_unavailable")
        dense_ids = []
    try:
        lexical_ids, timings["lexical"] = lexical_future.result()
    except Exception:
        lexical_failed = True
        degraded.append("lexical_unavailable")
        lexical_ids = []
    if dense_failed and lexical_failed:
        raise HTTPException(503, detail={"code": "search_unavailable", "message": "No retrieval branch available"})
    began = time.perf_counter()
    if lexical_ids and dense_ids:
        ids, evidence = _hybrid_evidence(lexical_ids, dense_ids)
        route = "hybrid_long_query"
    elif lexical_ids:
        ids = list(lexical_ids)
        evidence = _lexical_evidence(ids)
        route = "hybrid_dense_fallback" if dense_failed else "hybrid_long_query"
    else:
        ids = list(dense_ids)
        evidence = _dense_evidence(ids)
        route = "hybrid_lexical_fallback" if lexical_failed else "hybrid_long_query"
    timings["fusion"] = (time.perf_counter() - began) * 1000
    return {
        "ids": ids,
        "route": route,
        "timings": timings,
        "evidence": evidence,
        "lexical_ids": lexical_ids,
        "dense_ids": dense_ids,
        "degraded_reasons": degraded,
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
    anchor, _anchor_notes = resolve_anchor(origin) if personalized else (None, [])
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


def validate_suggest_request(payload: SuggestRequest, personalized: bool) -> None:
    """Session and corpus pin. Unknown demo users are rejected on both suggest routes."""
    del personalized
    if payload.expected_corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})
    if payload.session_id not in runtime.sessions:
        raise HTTPException(401, detail={"code": "invalid_session", "message": "Unknown session"})
    demo_user_id = getattr(payload, "demo_user_id", None)
    if demo_user_id is not None and not known_user(demo_user_id):
        raise HTTPException(403, detail={"code": "unknown_demo_user", "message": "demo_user_id is not in the demo registry"})


def pin_suggest_context(payload: SuggestRequest, personalized: bool) -> dict[str, Any]:
    """Request clock and history snapshot. Query-only drops origin, user, and client time."""
    request_time = datetime.now(UTC)
    if not personalized:
        return {
            "anchor": None,
            "notes": [],
            "context_time": request_time,
            "history_version": None,
            "preferred_ids": [],
            "demo_user_id": None,
        }
    context_time = getattr(payload, "context_time", None) or request_time
    anchor, notes = resolve_anchor(getattr(payload, "origin", None), now=context_time)
    demo_user_id = getattr(payload, "demo_user_id", None)
    history_version = None
    preferred_ids: list[str] = []
    if demo_user_id:
        snapshot = history_snapshot(demo_user_id, payload.session_id, context_time)
        history_version = snapshot["history_version"]
        preferred_ids = list(snapshot["poi_ids"])
    return {
        "anchor": anchor,
        "notes": notes,
        "context_time": context_time,
        "history_version": history_version,
        "preferred_ids": preferred_ids,
        "demo_user_id": demo_user_id,
    }


def persist_exposure(
    payload: SuggestRequest,
    results: list[dict[str, Any]],
    demo_user_id: str | None,
) -> str | None:
    if not results:
        return None
    exposure_id = f"exp-{uuid.uuid4()}"
    runtime.exposures[exposure_id] = {
        "session_id": payload.session_id,
        "context_revision": payload.context_revision,
        "shown_ids": [item["poi_id"] for item in results],
        "displayed": False,
        "created_at": time.time(),
        "demo_user_id": demo_user_id,
    }
    return exposure_id


def suggest(payload: SuggestRequest, personalized: bool) -> dict[str, Any]:
    validate_suggest_request(payload, personalized)
    context = pin_suggest_context(payload, personalized)
    query = " ".join(payload.query.split())
    if not query:
        return response_payload(
            payload, [], None, {}, "empty_query", personalized, None,
            history_version=context["history_version"],
            context_notes=context["notes"],
            resolved_time=context["context_time"],
        )
    began = time.perf_counter()
    retrieved = retrieve_detailed(query)
    ids = list(retrieved["ids"])
    route = retrieved["route"]
    timings = dict(retrieved["timings"])
    evidence = retrieved["evidence"]
    anchor = context["anchor"]
    rescued_n = 0
    if anchor is not None:
        rescued_ids, timings["nearby_rescue"] = fetch_nearby_name_rescue(query, anchor)
        ids, evidence, rescued_n = merge_nearby_name_rescue(query, ids, evidence, rescued_ids)
        if rescued_n:
            route = f"{route}+nearby_name_rescue:{rescued_n}"
    docs = candidate_documents(ids, runtime.documents(ids))
    ranked = rank_candidates(query, docs, evidence, anchor)
    if context["preferred_ids"]:
        ranked = apply_history_cohort(query, ranked, context["preferred_ids"])
    results = _result_rows(ranked, payload.top_k)
    timings["total"] = (time.perf_counter() - began) * 1000
    exposure_id = persist_exposure(payload, results, context["demo_user_id"])
    return response_payload(
        payload, results, exposure_id, timings, route, personalized, anchor, len(docs),
        history_version=context["history_version"],
        degraded_reasons=list(retrieved.get("degraded_reasons") or []),
        context_notes=context["notes"],
        resolved_time=context["context_time"],
    )


def response_payload(payload: SuggestRequest, results: list[dict], exposure_id: str | None,
                     timings: dict, route: str, personalized: bool, anchor: dict | None, candidate_count: int = 0,
                     *, history_version: str | None = None, degraded_reasons: list[str] | None = None,
                     context_notes: list[str] | None = None, resolved_time: datetime | None = None) -> dict[str, Any]:
    moment = resolved_time or datetime.now(UTC)
    notes = [route, *(context_notes or [])]
    if personalized and history_version:
        notes.append(f"demo history {history_version}")
    elif personalized:
        notes.append(
            f"Stage 2 policy {POLICY['policy_version']}: {RETRIEVAL_PROFILE}, geo heuristic; no learned ranker"
        )
    else:
        notes.append("query-only fixed global scope")
    return {
        "request_id": payload.request_id, "context_revision": payload.context_revision,
        "exposure_id": exposure_id, "selectable": exposure_id is not None, "versions": versions(),
        "scope_summary": {
            "mode": "global_with_geo_heuristic" if personalized and anchor else "global",
            "coverage_id": CORPUS_VERSION, "primary_region_id": None,
            "primary_radius_m": None,
            "notes": notes,
        },
        "resolved_context_time": moment.isoformat(),
        "history_version": history_version, "candidate_count": candidate_count, "results": results,
        "degraded_reasons": list(degraded_reasons or []), "timings_ms": timings,
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
    return {
        "ready": count == EXPECTED_ROWS,
        "versions": versions(),
        "coverage_id": CORPUS_VERSION,
        "profile": RETRIEVAL_PROFILE,
        "capabilities": [
            RETRIEVAL_PROFILE,
            "geo_heuristic",
            "demo_users",
            "straight_line_preview",
            *(["goong_road_route"] if GOONG_API_KEY else []),
        ],
        }


def _build_map_geojson() -> dict[str, Any]:
    """Load the searchable catalog once for the MapLibre clustered source."""
    features: list[dict[str, Any]] = []
    search_after: list[Any] | None = None
    page_size = 10_000

    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "track_total_hits": False,
            "sort": [{"canonical_id": {"order": "asc"}}],
            "_source": ["canonical_id", "search_label", "address", "ranking_point"],
            "query": {"bool": {"filter": [{"term": {"destination_searchable": True}}]}},
        }
        if search_after is not None:
            body["search_after"] = search_after
        response = runtime.client().request("POST", f"/{INDEX_NAME}/_search", body)
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            break
        for hit in hits:
            source = hit.get("_source") or {}
            point = source.get("ranking_point") or {}
            lat, lon = point.get("lat"), point.get("lon")
            if lat is None or lon is None:
                continue
            features.append({
                "type": "Feature",
                "id": hit.get("_id"),
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "poi_id": source.get("canonical_id") or hit.get("_id"),
                    "name": source.get("search_label") or "",
                    "address": source.get("address") or "",
                },
            })
        if len(hits) < page_size:
            break
        search_after = hits[-1].get("sort")
        if not search_after:
            break

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {"corpus_version": CORPUS_VERSION, "count": len(features)},
    }


@app.get("/v1/map/pois")
def map_pois() -> dict[str, Any]:
    """Return the searchable catalog for the clustered MapLibre map source."""
    if runtime.map_geojson is None:
        with runtime.map_lock:
            if runtime.map_geojson is None:
                runtime.map_geojson = _build_map_geojson()
    return runtime.map_geojson


@app.get("/v1/demo/users")
def list_demo_users() -> list[dict[str, str]]:
    return public_users()


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
    recorded_at = datetime.now(UTC)
    history_version = "in-memory-demo-v1"
    demo_user_id = exposure.get("demo_user_id")
    if demo_user_id:
        history_version = append_selection(
            payload.session_id, demo_user_id, payload.selected_poi_id, recorded_at
        )
    result = {"selection_id": f"sel-{uuid.uuid4()}", "exposure_id": payload.exposure_id,
              "selected_poi_id": payload.selected_poi_id, "corpus_version": CORPUS_VERSION,
              "recorded_at": recorded_at.isoformat(), "history_version": history_version,
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
