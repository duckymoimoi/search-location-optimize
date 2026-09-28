#!/usr/bin/env python3
"""Eval production ES lexical (search_policy-driven) on gold_stage1_v1.

This is the real "policy + lexical" path — not offline fielded BM25Okapi.
Requires local ES with index vn-poi-core-v1-me5-small (search-dev / demo stack).

  python apps/poi-search/bench/gold_stage1_es_lexical_policy_bench.py
  POI_ES_URL=http://127.0.0.1:9200 python ...
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
POLICY_PATH = ROOT / "apps" / "poi-search" / "api" / "search_policy.json"
ME5_RUN = ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1/run_dense_me5_exact.jsonl"
OUT = Path(__file__).resolve().parent / "results" / "gold_stage1_es_lexical_policy"
EVIDENCE = ROOT / "artifacts" / "results" / "diagnostic_reports"

DEPTH = 1000
MISS = DEPTH + 1
RECALL_KS = (20, 50, 100, 500, 1000)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join(
        "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
        .casefold()
        .split()
    )


def text_tokens(text: str) -> list[str]:
    return [t for t in fold(text).split() if t]


def normalized_text(text: str) -> str:
    return fold(text)


def expand_query(query: str, rewrites: list[dict[str, str]]) -> str:
    out = query
    for rule in rewrites:
        out = re.sub(rule["pattern"], rule["replacement"], out, flags=re.IGNORECASE)
    return out


def lexical_body(query: str, size: int, lex: dict[str, float], rewrites: list[dict[str, str]]) -> dict[str, Any]:
    """Mirror apps/poi-search/api/app.py::lexical_body (policy-driven)."""
    folded = fold(query)
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": lex["exact"]}}},
        {"term": {"aliases_folded": {"value": folded, "boost": lex["alias_exact"]}}},
        {"match_phrase": {"search_label": {"query": query, "boost": lex["phrase"]}}},
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^6", "search_aliases^4", "address^2", "category_text"],
                "type": "best_fields",
                "operator": "and",
                "boost": lex["and_match"],
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label.prefix^5", "search_aliases.prefix^3"],
                "type": "best_fields",
                "operator": "and",
                "boost": lex["prefix_field"],
            }
        },
    ]
    fuzzy_terms = [t for t in text_tokens(query) if t.isalpha() and len(t) >= 4]
    if fuzzy_terms:
        should.append(
            {
                "multi_match": {
                    "query": " ".join(fuzzy_terms),
                    "fields": ["search_label^4", "search_aliases^3"],
                    "type": "best_fields",
                    "operator": "and",
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                    "max_expansions": 50,
                    "boost": lex["fuzzy"],
                }
            }
        )
    expanded = expand_query(query, rewrites)
    if normalized_text(expanded) != normalized_text(query):
        should.append(
            {
                "multi_match": {
                    "query": expanded,
                    "fields": ["search_label^6", "search_aliases^4", "address^2"],
                    "type": "cross_fields",
                    "operator": "and",
                    "boost": 0.5,
                }
            }
        )
    should.append(
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label", "search_aliases", "address"],
                "type": "cross_fields",
                "operator": "and",
                "boost": lex["and_match"],
            }
        }
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
    token_n = len(text_tokens(query))
    minimum_should_match = 2 if token_n > 2 else 1
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


def es_search(es_url: str, index: str, body: dict[str, Any]) -> list[str]:
    req = Request(
        f"{es_url.rstrip('/')}/{index}/_search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [hit["_id"] for hit in data["hits"]["hits"]]


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(x) for x in list(raw)]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


def best_rank(ids: list[str], acceptable: set[str]) -> int:
    for i, pid in enumerate(ids, 1):
        if pid in acceptable:
            return i
    return MISS


def k_at_recall(ranks: list[int], rate: float) -> int | None:
    n = len(ranks)
    need = int(np.ceil(rate * n))
    ordered = sorted(ranks)
    if need > n:
        return None
    k = ordered[need - 1]
    return int(k) if k <= DEPTH else None


def summarize(ranks: list[int]) -> dict[str, Any]:
    n = len(ranks)
    out: dict[str, Any] = {"n": n, "recall": {}, "diagnostic": {}, "k_at_r": {}}
    for k in RECALL_KS:
        out["recall"][f"R@{k}"] = sum(1 for r in ranks if 1 <= r <= k) / n if n else 0.0
    for k in (1, 5, 10, 50):
        out["diagnostic"][f"SR@{k}"] = sum(1 for r in ranks if 1 <= r <= k) / n if n else 0.0
    out["diagnostic"]["MRR@10"] = sum(1.0 / r for r in ranks if 1 <= r <= 10) / n if n else 0.0
    out["k_at_r"]["K@95"] = k_at_recall(ranks, 0.95)
    out["k_at_r"]["K@98"] = k_at_recall(ranks, 0.98)
    return out


def load_me5(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    out: dict[str, int] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vid = str(row.get("variant_id") or "")
            br = row.get("best_rank")
            if vid and br is not None:
                br = int(br)
                out[vid] = br if 1 <= br <= DEPTH else MISS
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--es-url", default=__import__("os").environ.get("POI_ES_URL", "http://127.0.0.1:9200"))
    ap.add_argument("--index", default=__import__("os").environ.get("POI_INDEX", "vn-poi-core-v1-me5-small"))
    ap.add_argument("--policy", type=Path, default=POLICY_PATH)
    ap.add_argument("--limit-queries", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    lex = policy["lexical"]
    rewrites = policy.get("query_rewrites") or []

    sessions = pd.read_csv(GOLD / "query_variants_v1.csv")
    if args.limit_queries > 0:
        sessions = sessions.head(args.limit_queries).copy()

    dense = load_me5(ME5_RUN)
    print(f"ES={args.es_url} index={args.index} n={len(sessions)} policy={policy.get('policy_version')}", flush=True)

    ranks: list[int] = []
    by_family: dict[str, list[int]] = defaultdict(list)
    lex_by_vid: dict[str, int] = {}
    t0 = time.time()
    for i, row in enumerate(sessions.itertuples(index=False), start=1):
        q = str(row.query_text)
        body = lexical_body(q, DEPTH, lex, rewrites)
        ids = es_search(args.es_url, args.index, body)
        acceptable = set(parse_acceptable(row.acceptable_poi_ids)) or {str(row.intended_poi_id)}
        br = best_rank(ids, acceptable)
        ranks.append(br)
        lex_by_vid[str(row.variant_id)] = br
        by_family[str(row.query_variant_family)].append(br)
        if i % 50 == 0 or i == len(sessions):
            print(f"  {i}/{len(sessions)} ({time.time() - t0:.0f}s)", flush=True)

    overall = summarize(ranks)
    rescue100 = rescue1000 = None
    oracle_d100 = None
    if dense:
        common = [vid for vid in lex_by_vid if vid in dense]
        rescue100 = sum(
            1
            for vid in common
            if not (1 <= dense[vid] <= 100) and (1 <= lex_by_vid[vid] <= 100)
        )
        rescue1000 = sum(
            1
            for vid in common
            if not (1 <= dense[vid] <= 1000) and (1 <= lex_by_vid[vid] <= 1000)
        )
        oracle_d100 = (
            sum(1 for vid in common if min(dense[vid], lex_by_vid[vid]) <= 100)
            - sum(1 for vid in common if 1 <= dense[vid] <= 100)
        ) / len(common)

    report = {
        "protocol": "gold_stage1_v1_es_lexical_policy",
        "policy_version": policy.get("policy_version"),
        "es_url": args.es_url,
        "index": args.index,
        "n": len(sessions),
        "retrieve_s": round(time.time() - t0, 1),
        "overall": overall,
        "by_family": {k: summarize(v) for k, v in sorted(by_family.items())},
        "vs_me5": {
            "rescue@100": rescue100,
            "rescue@1000": rescue1000,
            "oracle_delta@100": oracle_d100,
        },
        "compare_note": (
            "Offline L1 fielded BM25 lost to passage baseline. "
            "This run is production ES bool-should + policy boosts (exact/phrase/prefix/MSM/rewrites)."
        ),
        "related_work": [
            "komoot/photon — AddressQueryBuilder field boosts (housenumber^10, street^5, …)",
            "maikereis/lfas — BM25F field-aware address retrieval (two-level)",
            "ViDRILL (VLSP 2025) — BM25 + multilingual dense + cross-encoder rerank",
            "Robertson BM25F / fielded retrieval — classic multi-field weighting",
            "Hybrid RRF (Cormack et al.) — fuse lexical + dense ranks (already in API)",
        ],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "es_lexical_policy_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    o = overall
    lines = [
        "# Gold Stage-1 — ES lexical + search_policy",
        "",
        f"**Policy:** `{report['policy_version']}` · index `{args.index}` · n={len(sessions)}",
        "",
        "Production path: `search_policy.json` → `lexical_body` (exact / phrase / prefix / AND / fuzzy / rewrites / MSM).",
        "Khác L1 offline fielded BM25 — đây là query ES thật.",
        "",
        "## Gate",
        "",
        "| Profile | R@20 | R@50 | R@100 | R@1000 | K@95 | MRR@10 | rescue@100 | Δoracle@100 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| es_policy_lexical | {o['recall']['R@20']:.3f} | {o['recall']['R@50']:.3f} | "
            f"{o['recall']['R@100']:.3f} | {o['recall']['R@1000']:.3f} | "
            f"{o['k_at_r']['K@95']} | {o['diagnostic']['MRR@10']:.3f} | "
            f"{rescue100} | {oracle_d100:+.3f} |"
            if oracle_d100 is not None
            else f"| es_policy_lexical | {o['recall']['R@20']:.3f} | … |"
        ),
        "",
        "## ORTHO R@100",
        "",
    ]
    ortho = report["by_family"].get("ORTHOGRAPHIC_IME", {})
    if ortho:
        lines.append(f"- ORTHOGRAPHIC_IME R@100 = **{ortho['recall']['R@100']:.3f}**")
    lines += [
        "",
        "## Related work (tham chiếu)",
        "",
        "- **komoot/photon** — geocoder ES/OS; boost có cấu trúc (housenumber ≫ street ≫ city).",
        "- **LFAS** — BM25F field-aware + two-level retrieval cho địa chỉ.",
        "- **ViDRILL (VLSP 2025)** — BM25 + E5/GTE + cross-encoder rerank (legal VI; pipeline tương tự hybrid).",
        "- **BM25F / fielded IR** — trọng số theo field; L1 offline thuần chưa thắng passage trên gold này.",
        "- **RRF hybrid** — đã có trong API; đo marginal gain = Round L2.",
        "",
        "## Next",
        "",
        "- So với offline baseline_passage (R@100≈0.906, K@95≈313): nếu ES+policy tốt hơn → giữ/port boost; nếu kém → chỉnh policy boost / MSM / bỏ fuzzy.",
        "- Round L2: RRF(es_lexical, mE5) trên cùng gold.",
        "",
    ]
    md = "\n".join(lines)
    (args.out_dir / "ES_LEXICAL_POLICY.md").write_text(md, encoding="utf-8")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "11_ES_LEXICAL_POLICY.md").write_text(md, encoding="utf-8")
    print(
        f"es_policy: R@100={o['recall']['R@100']:.3f} R@1000={o['recall']['R@1000']:.3f} "
        f"K@95={o['k_at_r']['K@95']} MRR@10={o['diagnostic']['MRR@10']:.3f} "
        f"rescue@100={rescue100}"
    )
    print("wrote", args.out_dir)


if __name__ == "__main__":
    main()
