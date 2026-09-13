"""Build the frozen Hanoi POI lexical + ANN OpenSearch index."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq


def request(
    base_url: str,
    method: str,
    path: str,
    body: Any | None = None,
    content_type: str = "application/json",
    timeout: int = 120,
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
        raise RuntimeError(f"OpenSearch {method} {path} failed: {error.code} {details}") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(character)
    )
    return " ".join(text.casefold().split())


def address_text(value: str) -> str:
    fields = json.loads(value or "{}")
    return " ".join(
        str(fields.get(key, "")).strip()
        for key in ("housenumber", "street", "subdistrict", "district", "housename", "unit")
        if str(fields.get(key, "")).strip()
    )


def index_body(dimension: int, ef_construction: int, m: int) -> dict[str, Any]:
    return {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "-1",
                "knn": True,
                "knn.algo_param.ef_search": 100,
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
                "address": {"type": "text", "analyzer": "vi_folded"},
                "category": {"type": "keyword"},
                "category_text": {"type": "text", "analyzer": "vi_folded"},
                "destination_searchable": {"type": "boolean"},
                "entity_group_id": {"type": "keyword"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": dimension,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": ef_construction, "m": m},
                    },
                },
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="hanoi-poi-stage1-v4-lexical-dense")
    parser.add_argument("--bulk-size", type=int, default=200)
    parser.add_argument("--ef-construction", type=int, default=100)
    parser.add_argument("--m", type=int, default=16)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    if not args.index.startswith("hanoi-poi-stage1-v4-"):
        raise ValueError("Index name must stay inside the v4 benchmark namespace")
    bundle = Path(args.bundle)
    artifacts = Path(args.artifacts)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    server = request(args.base_url, "GET", "/")
    manifest = json.loads(
        (artifacts / "final_model_manifest.json").read_text(encoding="utf-8")
    )
    embeddings = np.load(artifacts / "corpus_embeddings.npy", mmap_mode="r")
    id_map = (
        pq.read_table(artifacts / "corpus_id_map.parquet", columns=["canonical_id"])
        .column(0)
        .to_pylist()
    )
    columns = [
        "canonical_id",
        "search_label",
        "search_aliases",
        "address_fields_json",
        "category",
        "destination_searchable",
        "entity_group_id",
    ]
    corpus = [
        row
        for row in pq.read_table(
            bundle / "corpus_search_view.parquet", columns=columns
        ).to_pylist()
        if row["destination_searchable"]
    ]
    if [row["canonical_id"] for row in corpus] != id_map:
        raise ValueError("Corpus order does not match the frozen embedding ID map")
    if embeddings.shape != (len(corpus), manifest["embedding_dimension"]):
        raise ValueError("Corpus embeddings do not match the model manifest")

    exists = False
    try:
        request(args.base_url, "HEAD", f"/{args.index}")
        exists = True
    except RuntimeError as error:
        if " 404 " not in str(error):
            raise
    if exists:
        if not args.recreate:
            raise RuntimeError("Index exists; pass --recreate to replace this generated index")
        request(args.base_url, "DELETE", f"/{args.index}")

    request(
        args.base_url,
        "PUT",
        f"/{args.index}",
        index_body(manifest["embedding_dimension"], args.ef_construction, args.m),
    )
    began = time.perf_counter()
    bulk_latencies: list[float] = []
    for start in range(0, len(corpus), args.bulk_size):
        lines: list[str] = []
        for offset, row in enumerate(corpus[start : start + args.bulk_size]):
            index = start + offset
            lines.append(
                json.dumps(
                    {"index": {"_index": args.index, "_id": row["canonical_id"]}},
                    separators=(",", ":"),
                )
            )
            lines.append(
                json.dumps(
                    {
                        "canonical_id": row["canonical_id"],
                        "search_label": row["search_label"],
                        "search_aliases": row["search_aliases"],
                        "label_folded": fold(row["search_label"]),
                        "aliases_folded": [fold(value) for value in row["search_aliases"]],
                        "address": address_text(row["address_fields_json"]),
                        "category": row["category"] or "",
                        "category_text": (row["category"] or "").replace("=", " ").replace("_", " "),
                        "destination_searchable": True,
                        "entity_group_id": row["entity_group_id"],
                        "embedding": np.asarray(embeddings[index]).tolist(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        batch_began = time.perf_counter()
        response = request(
            args.base_url,
            "POST",
            "/_bulk",
            payload,
            content_type="application/x-ndjson",
            timeout=300,
        )
        bulk_latencies.append((time.perf_counter() - batch_began) * 1000.0)
        if response.get("errors"):
            failures = [item for item in response["items"] if item["index"].get("error")]
            raise RuntimeError(f"Bulk indexing errors: {failures[:3]}")
        if start % 2000 == 0:
            print(f"indexed={min(start + args.bulk_size, len(corpus))}", flush=True)
    indexing_seconds = time.perf_counter() - began
    request(args.base_url, "POST", f"/{args.index}/_refresh")
    merge_began = time.perf_counter()
    request(
        args.base_url,
        "POST",
        f"/{args.index}/_forcemerge?max_num_segments=1",
        timeout=600,
    )
    merge_seconds = time.perf_counter() - merge_began
    request(
        args.base_url,
        "PUT",
        f"/{args.index}/_settings",
        {"index": {"refresh_interval": "1s"}},
    )
    count = request(args.base_url, "GET", f"/{args.index}/_count")["count"]
    if count != len(corpus):
        raise RuntimeError(f"Indexed {count}, expected {len(corpus)}")
    stats = request(args.base_url, "GET", f"/{args.index}/_stats/store,segments")
    report = {
        "holdout_evaluated": False,
        "server": server,
        "index": args.index,
        "mapping": index_body(
            manifest["embedding_dimension"], args.ef_construction, args.m
        ),
        "hnsw": {"ef_construction": args.ef_construction, "m": args.m},
        "model_manifest": manifest,
        "corpus_rows": len(corpus),
        "corpus_embeddings_sha256": sha256(artifacts / "corpus_embeddings.npy"),
        "indexing_seconds": indexing_seconds,
        "documents_per_second": len(corpus) / indexing_seconds,
        "force_merge_seconds": merge_seconds,
        "bulk_size": args.bulk_size,
        "bulk_latency_ms": {
            "mean": float(np.mean(bulk_latencies)),
            "p95": float(np.quantile(bulk_latencies, 0.95)),
            "max": float(np.max(bulk_latencies)),
        },
        "index_stats": stats["indices"][args.index],
    }
    (output / "opensearch_index_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "index": args.index,
                "documents": count,
                "indexing_seconds": indexing_seconds,
                "store_bytes": stats["indices"][args.index]["total"]["store"]["size_in_bytes"],
            }
        )
    )


if __name__ == "__main__":
    main()
