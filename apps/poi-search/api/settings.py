"""Process settings: env, search policy, and retrieval constants."""
from __future__ import annotations

import json
import os
from pathlib import Path

MODEL_ID = os.environ.get("POI_MODEL_ID", "intfloat/multilingual-e5-small")
MODEL_DIR = Path(os.environ.get("POI_MODEL_DIR", os.environ.get("HANOI_POI_MODEL_DIR", "")))
ES_URL = os.environ.get(
    "POI_ES_URL",
    os.environ.get("HANOI_POI_OPENSEARCH_URL", "http://elasticsearch:9200"),
)
INDEX_NAME = os.environ.get("POI_INDEX", os.environ.get("HANOI_POI_INDEX", "vn-poi-core-v3-me5-small"))
EXPECTED_ROWS = int(
    os.environ.get("POI_EXPECTED_ROWS", os.environ.get("HANOI_POI_EXPECTED_ROWS", "179209"))
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
CORPUS_VERSION = os.environ.get("POI_CORPUS_VERSION", "vn-poi-core-v3-semantic-address-dedup50")
BRANCH_DEPTH = int(POLICY["retrieval"]["branch_depth"])
ANN_CANDIDATES = int(POLICY["retrieval"]["ann_candidates"])
RRF_CONSTANT = int(POLICY["retrieval"]["rrf_constant"])
RANKING_POLICY = POLICY["ranking"]
LEXICAL_CONFIG = POLICY["lexical"]
RELEASE_ID = os.environ.get("POI_RELEASE_ID", "vn-poi-demo-me5-r2")
EMBEDDING_SPACE_ID = os.environ.get("POI_EMBEDDING_SPACE_ID", "me5-small-passage-384")
PASSAGE_BUILDER_VERSION = os.environ.get("POI_PASSAGE_BUILDER_VERSION", "passage_context-v1")


def resolve_model_source() -> str:
    """Prefer local finetuned dir when present; otherwise Hugging Face model id."""
    if MODEL_DIR and (MODEL_DIR / "final_model").exists():
        return str(MODEL_DIR / "final_model")
    if MODEL_DIR and (MODEL_DIR / "config.json").exists():
        return str(MODEL_DIR)
    return MODEL_ID
