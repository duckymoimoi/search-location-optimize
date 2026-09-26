"""Add codes_compact mapping + values without full reindex (no embeddings)."""

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


def alnum_compact(text: str) -> str:
    return "".join(ch for ch in fold(text) if ch.isalnum())


def codes_compact_values(*parts: object) -> list[str]:
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
            if len(full) >= 2 and any(ch.isdigit() for ch in full):
                out.add(full)
            for token in fold(value).split():
                compact = alnum_compact(token)
                if len(compact) >= 2 and any(ch.isdigit() for ch in compact):
                    out.add(compact)
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("POI_ES_URL", "http://127.0.0.1:9200"))
    parser.add_argument("--index", default=os.environ.get("POI_INDEX", "vn-poi-core-v1-me5-small"))
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    props = request(args.base_url, "GET", f"/{args.index}/_mapping")[args.index]["mappings"][
        "properties"
    ]
    if "codes_compact" not in props:
        print("adding codes_compact keyword mapping", flush=True)
        request(
            args.base_url,
            "PUT",
            f"/{args.index}/_mapping",
            {"properties": {"codes_compact": {"type": "keyword"}}},
        )
    else:
        print("codes_compact mapping already present", flush=True)

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
            codes = codes_compact_values(source.get("search_label"), source.get("search_aliases"))
            lines.append(json.dumps({"update": {"_index": args.index, "_id": hit["_id"]}}))
            lines.append(json.dumps({"doc": {"codes_compact": codes}}))
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
        request(args.base_url, "DELETE", f"/_search/scroll", {"scroll_id": [scroll_id]})
    except RuntimeError:
        pass
    request(args.base_url, "POST", f"/{args.index}/_refresh")

    sample = request(
        args.base_url,
        "POST",
        f"/{args.index}/_search",
        {
            "size": 3,
            "query": {"term": {"codes_compact": "s202"}},
            "_source": ["search_label", "address", "codes_compact"],
        },
    )
    print(
        json.dumps(
            {
                "updated": updated,
                "seconds": round(time.perf_counter() - began, 1),
                "term_s202_hits": sample["hits"]["total"]["value"],
                "samples": [
                    {
                        "label": h["_source"].get("search_label"),
                        "codes": h["_source"].get("codes_compact"),
                    }
                    for h in sample["hits"]["hits"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
