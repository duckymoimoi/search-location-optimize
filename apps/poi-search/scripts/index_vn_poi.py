"""Create and bulk-load vn-poi-core-v1 into Elasticsearch 9 (lexical + dense_vector)."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

DEFAULT_INDEX = "vn-poi-core-v3-me5-small"
DEFAULT_EXPECTED = 179209
EMBEDDING_DIM = 384


def request(
    base_url: str,
    method: str,
    path: str,
    body: Any | None = None,
    content_type: str = "application/json",
    timeout: int = 300,
) -> Any:
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Elasticsearch {method} {path} failed: {error.code} {details}") from error


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(character)
    )
    return " ".join(text.casefold().split())


def alnum_compact(text: str) -> str:
    """Fold + drop non-alphanumerics. S2.02 / s2-02 / s202 → s202 (no pattern hardcode)."""
    return "".join(ch for ch in fold(text) if ch.isalnum())


def letter_compact(text: str) -> str:
    """Fold + letters only. Spaced and glued names share one key."""
    return "".join(ch for ch in fold(text) if ch.isalpha())


def names_compact_values(*parts: object) -> list[str]:
    """Space-insensitive name keys. Full name/alias only; no adjacent-pair explosion."""
    out: set[str] = set()
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple)):
            values = [str(item) for item in part if item is not None and str(item).strip()]
        else:
            text = str(part).strip()
            if not text or text in {"None", "nan"}:
                continue
            values = [text]
        for value in values:
            key = letter_compact(value)
            if len(key) >= 6:
                out.add(key)
    return sorted(out)


_PATH_SPLIT = re.compile(r"[/-]+")
_TOKEN_KEEP = re.compile(r"[^\W_]+(?:[/-][^\W_]+)*")


def _path_atoms(value: str) -> list[str]:
    atoms: list[str] = []
    for token in _TOKEN_KEEP.findall(fold(value)):
        if _PATH_SPLIT.search(token) and any(ch.isdigit() for ch in token):
            atoms.extend(part for part in _PATH_SPLIT.split(token) if part)
        else:
            atoms.append(token)
    return atoms


def housenumber_path_key(housenumber: str) -> str:
    """Same key as API parse_query_structure: '259/15' → '259 15'."""
    parts = [atom for atom in _path_atoms(housenumber) if any(ch.isdigit() for ch in atom)]
    return " ".join(parts)


def name_is_address_row(name: str, category: str, housenumber: str, street: str, place: str) -> bool:
    """True when the visible name is the structured address, not a brand/entity."""
    if (category or "").startswith("address="):
        return True
    loc = (street or place or "").strip()
    house = (housenumber or "").strip()
    label = (name or "").strip()
    if not label or not house or not loc:
        return False
    folded_name = fold(label)
    return folded_name in {fold(f"{house} {loc}"), fold(f"{house}, {loc}")}


def codes_compact_values(*parts: object) -> list[str]:
    """Indexable compact codes from names/aliases/refs (token + full-string forms)."""
    out: set[str] = set()
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple)):
            values = [str(x) for x in part if x is not None and str(x).strip()]
        else:
            text = str(part).strip()
            if not text or text in {"None", "nan"}:
                continue
            values = [text]
        for value in values:
            full = alnum_compact(value)
            # Keep only alnum keys that include a digit (codes/refs), not plain words.
            if len(full) >= 2 and any(ch.isdigit() for ch in full):
                out.add(full)
            for token in fold(value).split():
                compact = alnum_compact(token)
                if len(compact) >= 2 and any(ch.isdigit() for ch in compact):
                    out.add(compact)
    return sorted(out)


def index_body(dimension: int) -> dict[str, Any]:
    return {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "-1",
            },
            "analysis": {
                "char_filter": {
                    "vietnamese_d": {
                        "type": "mapping",
                        "mappings": ["đ => d", "Đ => D"],
                    }
                },
                "filter": {
                    "poi_edge": {
                        "type": "edge_ngram",
                        "min_gram": 1,
                        "max_gram": 20,
                    }
                },
                "analyzer": {
                    "vi_folded": {
                        "type": "custom",
                        "char_filter": ["vietnamese_d"],
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    },
                    "vi_prefix": {
                        "type": "custom",
                        "char_filter": ["vietnamese_d"],
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "poi_edge"],
                    },
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "canonical_id": {"type": "keyword"},
                "search_label": {
                    "type": "text",
                    "analyzer": "vi_folded",
                    "fields": {
                        "prefix": {
                            "type": "text",
                            "analyzer": "vi_prefix",
                            "search_analyzer": "vi_folded",
                        }
                    },
                },
                "search_aliases": {
                    "type": "text",
                    "analyzer": "vi_folded",
                    "fields": {
                        "prefix": {
                            "type": "text",
                            "analyzer": "vi_prefix",
                            "search_analyzer": "vi_folded",
                        }
                    },
                },
                "label_folded": {"type": "keyword"},
                "aliases_folded": {"type": "keyword"},
                "codes_compact": {"type": "keyword"},
                "names_compact": {"type": "keyword"},
                "address": {"type": "text", "analyzer": "vi_folded"},
                "housenumber": {"type": "keyword"},
                "housenumber_path_key": {"type": "keyword"},
                "street": {"type": "text", "analyzer": "vi_folded"},
                "street_folded": {"type": "keyword"},
                "place": {"type": "text", "analyzer": "vi_folded"},
                "place_folded": {"type": "keyword"},
                "address_status": {"type": "keyword"},
                "name_is_address": {"type": "boolean"},
                "province_region_id": {"type": "keyword"},
                "subdistrict_region_id": {"type": "keyword"},
                "category": {"type": "keyword"},
                "category_text": {"type": "text", "analyzer": "vi_folded"},
                "destination_searchable": {"type": "boolean"},
                "entity_group_id": {"type": "keyword"},
                "context_text": {"type": "text", "analyzer": "vi_folded"},
                "ranking_point": {
                    "properties": {
                        "lat": {"type": "double"},
                        "lon": {"type": "double"},
                        "quality": {"type": "keyword"},
                    }
                },
                "embedding": {
                    "type": "dense_vector",
                    "dims": dimension,
                    "index": True,
                    "similarity": "cosine",
                },
            },
        },
    }


def index_exists(base_url: str, index: str) -> bool:
    try:
        request(base_url, "HEAD", f"/{index}")
        return True
    except RuntimeError as error:
        if " 404 " in str(error):
            return False
        raise


def wait_for_es(base_url: str, attempts: int = 90) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            request(base_url, "GET", "/")
            return
        except Exception as error:  # noqa: BLE001 — retry until ready
            last_error = error
            time.sleep(1)
    raise RuntimeError(f"Elasticsearch not ready at {base_url}: {last_error}")


def load_corpus(
    pois_path: Path,
    documents_path: Path,
    embeddings_path: Path,
    id_map_path: Path,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    embeddings = np.load(embeddings_path, mmap_mode="r")
    id_table = pq.read_table(id_map_path)
    if "poi_id" in id_table.column_names:
        id_map = [str(value) for value in id_table.column("poi_id").to_pylist()]
    else:
        id_map = [str(value) for value in id_table.column(0).to_pylist()]

    pois = {
        str(row["poi_id"]): row
        for row in pq.read_table(
            pois_path,
            columns=[
                "poi_id",
                "name",
                "category",
                "destination_searchable",
                "entity_group_id",
                "ranking_point",
                "ref",
                "address",
                "address_status",
                "province_region_id",
                "subdistrict_region_id",
            ],
        ).to_pylist()
    }
    documents = pq.read_table(documents_path).to_pylist()
    if [str(doc["poi_id"]) for doc in documents] != id_map:
        raise ValueError("search_documents order does not match poi_ids.parquet")
    if embeddings.shape != (len(id_map), EMBEDDING_DIM):
        raise ValueError(
            f"Embeddings shape {embeddings.shape} != ({len(id_map)}, {EMBEDDING_DIM})"
        )

    corpus: list[dict[str, Any]] = []
    for document in documents:
        poi_id = str(document["poi_id"])
        poi = pois.get(poi_id)
        if poi is None:
            raise ValueError(f"Missing pois_core row for {poi_id}")
        if not poi.get("destination_searchable", True):
            continue
        aliases = document.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = list(aliases)
        category = poi.get("category") or ""
        address = poi.get("address") or {}
        if not isinstance(address, dict):
            address = {}
        housenumber = str(address.get("housenumber") or "").strip()
        street = str(address.get("street") or "").strip()
        place = str(address.get("place") or "").strip()
        label = document.get("name") or poi.get("name") or ""
        corpus.append(
            {
                "canonical_id": poi_id,
                "search_label": label,
                "search_aliases": aliases,
                "address": document.get("address_text") or "",
                "housenumber": fold(housenumber) if housenumber else "",
                "housenumber_path_key": housenumber_path_key(housenumber),
                "street": street,
                "street_folded": fold(street) if street else "",
                "place": place,
                "place_folded": fold(place) if place else "",
                "address_status": poi.get("address_status") or "missing",
                "name_is_address": name_is_address_row(
                    str(label), str(category), housenumber, street, place
                ),
                "province_region_id": poi.get("province_region_id") or "",
                "subdistrict_region_id": poi.get("subdistrict_region_id") or "",
                "category": category,
                "category_text": category.replace("=", " ").replace("_", " "),
                "destination_searchable": True,
                "entity_group_id": poi.get("entity_group_id") or poi_id,
                "context_text": document.get("passage_context") or "",
                "ranking_point": poi.get("ranking_point"),
                "ref": poi.get("ref") or "",
            }
        )
    if [row["canonical_id"] for row in corpus] != id_map:
        raise ValueError("Filtered corpus order drifted from embedding id map")
    return corpus, embeddings


def bulk_index(
    base_url: str,
    index: str,
    corpus: list[dict[str, Any]],
    embeddings: np.ndarray,
    bulk_size: int,
) -> None:
    for start in range(0, len(corpus), bulk_size):
        lines: list[str] = []
        batch = corpus[start : start + bulk_size]
        for offset, row in enumerate(batch):
            index_row = start + offset
            aliases = row["search_aliases"]
            lines.append(
                json.dumps(
                    {"index": {"_index": index, "_id": row["canonical_id"]}},
                    separators=(",", ":"),
                )
            )
            lines.append(
                json.dumps(
                    {
                        "canonical_id": row["canonical_id"],
                        "search_label": row["search_label"],
                        "search_aliases": aliases,
                        "label_folded": fold(row["search_label"]),
                        "aliases_folded": [fold(value) for value in aliases],
                        "codes_compact": codes_compact_values(
                            row["search_label"], aliases, row.get("ref")
                        ),
                        "names_compact": names_compact_values(
                            row["search_label"], aliases
                        ),
                        "address": row["address"],
                        "housenumber": row.get("housenumber") or "",
                        "housenumber_path_key": row.get("housenumber_path_key") or "",
                        "street": row.get("street") or "",
                        "street_folded": row.get("street_folded") or "",
                        "place": row.get("place") or "",
                        "place_folded": row.get("place_folded") or "",
                        "address_status": row.get("address_status") or "missing",
                        "name_is_address": bool(row.get("name_is_address")),
                        "province_region_id": row.get("province_region_id") or "",
                        "subdistrict_region_id": row.get("subdistrict_region_id") or "",
                        "category": row["category"],
                        "category_text": row["category_text"],
                        "destination_searchable": True,
                        "entity_group_id": row["entity_group_id"],
                        "context_text": row["context_text"],
                        "ranking_point": row["ranking_point"],
                        "embedding": np.asarray(embeddings[index_row], dtype=np.float32).tolist(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        response = request(
            base_url,
            "POST",
            "/_bulk",
            payload,
            content_type="application/x-ndjson",
            timeout=600,
        )
        if response.get("errors"):
            first = next(
                (item for item in response.get("items", []) if "error" in item.get("index", {})),
                None,
            )
            raise RuntimeError(f"Bulk indexing errors: {first}")
        done = min(start + bulk_size, len(corpus))
        if done == len(corpus) or done % (bulk_size * 10) == 0:
            print(f"  bulk {done}/{len(corpus)}", flush=True)


def resolve_repo_root() -> Path | None:
    """Return repo root when running from apps/poi-search/scripts/; else None (container)."""
    here = Path(__file__).resolve()
    try:
        if here.parent.name == "scripts" and here.parents[1].name == "poi-search":
            return here.parents[3]
    except IndexError:
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("POI_ES_URL", "http://127.0.0.1:9200"))
    parser.add_argument("--index", default=os.environ.get("POI_INDEX", DEFAULT_INDEX))
    parser.add_argument(
        "--expected-rows",
        type=int,
        default=int(os.environ.get("POI_EXPECTED_ROWS", str(DEFAULT_EXPECTED))),
    )
    parser.add_argument("--pois", type=Path, default=None)
    parser.add_argument("--documents", type=Path, default=None)
    parser.add_argument("--embeddings", type=Path, default=None)
    parser.add_argument("--id-map", type=Path, default=None)
    parser.add_argument("--bulk-size", type=int, default=200)
    parser.add_argument(
        "--recreate",
        action="store_true",
        default=os.environ.get("RECREATE_INDEX", "").strip() in {"1", "true", "True", "yes"},
    )
    args = parser.parse_args()

    root = resolve_repo_root()
    if root is not None:
        corpus_dir = root / "data" / "vietnam" / "poi_corpus_v3"
        emb_dir = root / "artifacts" / "embeddings" / "me5_small_v3"
        default_pois = corpus_dir / "pois_core.parquet"
        default_docs = corpus_dir / "search_documents.parquet"
        default_emb = emb_dir / "corpus_embeddings.npy"
        default_ids = emb_dir / "poi_ids.parquet"
    else:
        default_pois = Path("/data/corpus/pois_core.parquet")
        default_docs = Path("/data/corpus/search_documents.parquet")
        default_emb = Path("/data/embeddings/corpus_embeddings.npy")
        default_ids = Path("/data/embeddings/poi_ids.parquet")

    pois_path = args.pois or Path(os.environ.get("POI_POIS_PATH", str(default_pois)))
    documents_path = args.documents or Path(
        os.environ.get("POI_DOCUMENTS_PATH", str(default_docs))
    )
    embeddings_path = args.embeddings or Path(
        os.environ.get("POI_EMBEDDINGS_PATH", str(default_emb))
    )
    id_map_path = args.id_map or Path(os.environ.get("POI_ID_MAP_PATH", str(default_ids)))

    wait_for_es(args.base_url)
    print(f"loading corpus from {documents_path}", flush=True)
    corpus, embeddings = load_corpus(pois_path, documents_path, embeddings_path, id_map_path)
    if len(corpus) != args.expected_rows:
        raise SystemExit(f"Corpus rows {len(corpus)} != expected {args.expected_rows}")

    exists = index_exists(args.base_url, args.index)
    if exists and not args.recreate:
        count = request(args.base_url, "GET", f"/{args.index}/_count")["count"]
        if count == args.expected_rows:
            print(f"index {args.index} already has {count} docs; skip (set RECREATE_INDEX=1 to rebuild)")
            return
        raise SystemExit(
            f"Index {args.index} exists with count={count}; pass --recreate or RECREATE_INDEX=1"
        )
    if exists and args.recreate:
        print(f"deleting index {args.index}", flush=True)
        request(args.base_url, "DELETE", f"/{args.index}")

    print(f"creating index {args.index}", flush=True)
    request(args.base_url, "PUT", f"/{args.index}", index_body(EMBEDDING_DIM))
    began = time.perf_counter()
    bulk_index(args.base_url, args.index, corpus, embeddings, args.bulk_size)
    request(args.base_url, "POST", f"/{args.index}/_refresh")
    request(
        args.base_url,
        "PUT",
        f"/{args.index}/_settings",
        {"index": {"refresh_interval": "1s"}},
    )
    count = request(args.base_url, "GET", f"/{args.index}/_count")["count"]
    if count != args.expected_rows:
        raise SystemExit(f"Count assert failed: {count} != {args.expected_rows}")
    print(f"indexed {count} docs into {args.index} in {time.perf_counter() - began:.1f}s", flush=True)


if __name__ == "__main__":
    main()
