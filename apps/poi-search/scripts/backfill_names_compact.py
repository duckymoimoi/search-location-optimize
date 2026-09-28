"""Add names_compact mapping + values without full reindex (no embeddings)."""

from __future__ import annotations

import argparse
import json
import os
import time
import unicodedata
import urllib.error
import urllib.request
from typing import Any


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


def letter_compact(text: str) -> str:
    return "".join(ch for ch in fold(text) if ch.isalpha())


def names_compact_values(*parts: object) -> list[str]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("POI_ES_URL", "http://127.0.0.1:9200"))
    parser.add_argument("--index", default=os.environ.get("POI_INDEX", "vn-poi-core-v3-me5-small"))
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    props = request(args.base_url, "GET", f"/{args.index}/_mapping")[args.index]["mappings"][
        "properties"
    ]
    if "names_compact" not in props:
        print("adding names_compact keyword mapping", flush=True)
        request(
            args.base_url,
            "PUT",
            f"/{args.index}/_mapping",
            {"properties": {"names_compact": {"type": "keyword"}}},
        )
    else:
        print("names_compact mapping already present", flush=True)

    began = time.perf_counter()
    updated = 0
    scroll = request(
        args.base_url,
        "POST",
        f"/{args.index}/_search?scroll=2m",
        {
            "size": args.batch_size,
            "_source": ["search_label", "search_aliases"],
            "query": {"match_all": {}},
            "sort": ["_doc"],
        },
    )
    scroll_id = scroll["_scroll_id"]
    hits = scroll["hits"]["hits"]
    while hits:
        lines: list[str] = []
        for hit in hits:
            source = hit.get("_source") or {}
            keys = names_compact_values(source.get("search_label"), source.get("search_aliases"))
            lines.append(json.dumps({"update": {"_index": args.index, "_id": hit["_id"]}}))
            lines.append(json.dumps({"doc": {"names_compact": keys}}))
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        response = request(
            args.base_url,
            "POST",
            "/_bulk",
            payload,
            content_type="application/x-ndjson",
            timeout=600,
        )
        if response.get("errors"):
            first = next(
                (
                    item
                    for item in response.get("items", [])
                    if "error" in item.get("update", {})
                ),
                None,
            )
            raise RuntimeError(f"Bulk update errors: {first}")
        updated += len(hits)
        if updated % 10000 == 0 or len(hits) < args.batch_size:
            print(f"  updated {updated}", flush=True)
        scroll = request(
            args.base_url,
            "POST",
            "/_search/scroll",
            {"scroll": "2m", "scroll_id": scroll_id},
        )
        scroll_id = scroll["_scroll_id"]
        hits = scroll["hits"]["hits"]

    try:
        request(args.base_url, "DELETE", "/_search/scroll", {"scroll_id": [scroll_id]})
    except RuntimeError:
        pass
    request(args.base_url, "POST", f"/{args.index}/_refresh")

    sample = request(
        args.base_url,
        "POST",
        f"/{args.index}/_search",
        {
            "size": 3,
            "query": {"term": {"names_compact": "vanhanhmall"}},
            "_source": ["search_label", "names_compact"],
        },
    )
    print(
        json.dumps(
            {
                "updated": updated,
                "seconds": round(time.perf_counter() - began, 1),
                "term_vanhanhmall_hits": sample["hits"]["total"]["value"],
                "samples": [
                    {
                        "label": hit["_source"].get("search_label"),
                        "names_compact": hit["_source"].get("names_compact"),
                    }
                    for hit in sample["hits"]["hits"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
