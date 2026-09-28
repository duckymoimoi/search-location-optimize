#!/usr/bin/env python3
"""Iterate ES lexical query structure; measure lexical-only + hybrid RRF(mE5) each step.

  python apps/poi-search/bench/gold_stage1_lexical_iterate.py
  python apps/poi-search/bench/gold_stage1_lexical_iterate.py --variants v0_current,v1_msm1,v3_context_or
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
POLICY_PATH = ROOT / "apps" / "poi-search" / "api" / "search_policy.json"
ME5_RUN = ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1/run_dense_me5_exact.jsonl"
OUT = Path(__file__).resolve().parent / "results" / "gold_stage1_lexical_iterate"
EVIDENCE = ROOT / "artifacts" / "results" / "diagnostic_reports"

DEPTH = 1000
MISS = DEPTH + 1
RRF_K = 60
RECALL_KS = (20, 50, 100, 500, 1000)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
    return " ".join(
        "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
        .casefold()
        .split()
    )


def text_tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", fold(value))


def expand_query(query: str, rewrites: list[dict[str, str]]) -> str:
    value = unicodedata.normalize("NFKC", query)
    for rule in rewrites:
        value = re.sub(rule["pattern"], rule["replacement"], value, flags=re.IGNORECASE)
    return " ".join(value.split())


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


def rrf_fuse(left: list[str], right: list[str], depth: int = DEPTH, k: int = RRF_K) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, int] = {}
    for branch in (left[:depth], right[:depth]):
        for rank, poi_id in enumerate(branch, 1):
            scores[poi_id] += 1.0 / (k + rank)
            best[poi_id] = min(best.get(poi_id, rank), rank)
    return sorted(scores, key=lambda pid: (-scores[pid], best[pid], pid))[:depth]


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


def wrap(should: list[dict], msm: int | str) -> dict[str, Any]:
    return {
        "size": DEPTH,
        "track_total_hits": False,
        "_source": False,
        "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [{"term": {"destination_searchable": True}}],
                "should": should,
                "minimum_should_match": msm,
            }
        },
    }


LexBuilder = Callable[[str, dict[str, float], list[dict[str, str]]], dict[str, Any]]


def build_v0_current(query: str, lex: dict[str, float], rewrites: list[dict[str, str]]) -> dict[str, Any]:
    """Production lexical_body before this iteration (strict MSM / AND)."""
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
    if fold(expanded) != fold(query):
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
            {"prefix": {"aliases_folded": {"value": folded, "boost": lex["leading_prefix"] * 0.8}}},
        ]
    msm = 2 if len(text_tokens(query)) > 2 else 1
    return wrap(should, msm)


def build_v1_msm1(query: str, lex: dict[str, float], rewrites: list[dict[str, str]]) -> dict[str, Any]:
    body = build_v0_current(query, lex, rewrites)
    body["query"]["bool"]["minimum_should_match"] = 1
    return body


def build_v2_cross_or(query: str, lex: dict[str, float], rewrites: list[dict[str, str]]) -> dict[str, Any]:
    """MSM=1; cross_fields OR; drop single-field AND; keep exact/phrase/prefix; weak fuzzy."""
    folded = fold(query)
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": lex["exact"]}}},
        {"term": {"aliases_folded": {"value": folded, "boost": lex["alias_exact"]}}},
        {"match_phrase": {"search_label": {"query": query, "boost": lex["phrase"]}}},
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^6", "search_aliases^4", "address^3"],
                "type": "cross_fields",
                "operator": "or",
                "boost": 4.0,
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^4", "search_aliases^2", "address^2"],
                "type": "best_fields",
                "operator": "or",
                "boost": 2.0,
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label.prefix^4", "search_aliases.prefix^2"],
                "type": "best_fields",
                "operator": "or",
                "boost": lex["prefix_field"],
            }
        },
    ]
    expanded = expand_query(query, rewrites)
    if fold(expanded) != fold(query):
        should.append(
            {
                "multi_match": {
                    "query": expanded,
                    "fields": ["search_label^5", "search_aliases^3", "address^2"],
                    "type": "cross_fields",
                    "operator": "or",
                    "boost": 1.5,
                }
            }
        )
    if len(folded) >= 2:
        should += [
            {"prefix": {"label_folded": {"value": folded, "boost": lex["leading_prefix"]}}},
            {"prefix": {"aliases_folded": {"value": folded, "boost": lex["leading_prefix"] * 0.8}}},
        ]
    return wrap(should, 1)


def build_v3_context_or(query: str, lex: dict[str, float], rewrites: list[dict[str, str]]) -> dict[str, Any]:
    """v2 + context_text (passage) OR — closest to offline BM25 passage floor."""
    body = build_v2_cross_or(query, lex, rewrites)
    should = body["query"]["bool"]["should"]
    should.append(
        {
            "match": {
                "context_text": {
                    "query": query,
                    "operator": "or",
                    "boost": 3.0,
                }
            }
        }
    )
    expanded = expand_query(query, rewrites)
    if fold(expanded) != fold(query):
        should.append(
            {"match": {"context_text": {"query": expanded, "operator": "or", "boost": 1.5}}}
        )
    return body


def build_v4_photonish(query: str, lex: dict[str, float], rewrites: list[dict[str, str]]) -> dict[str, Any]:
    """Structured-ish: strong name/address cross + context + exact; MSM=1; no fuzzy."""
    folded = fold(query)
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": 20.0}}},
        {"term": {"aliases_folded": {"value": folded, "boost": 16.0}}},
        {"match_phrase": {"search_label": {"query": query, "slop": 1, "boost": 10.0}}},
        {"match_phrase": {"address": {"query": query, "slop": 2, "boost": 6.0}}},
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^8", "search_aliases^5", "address^6", "context_text^3"],
                "type": "cross_fields",
                "operator": "or",
                "minimum_should_match": "50%",
                "boost": 5.0,
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label^4", "address^3", "context_text^2"],
                "type": "best_fields",
                "operator": "or",
                "boost": 2.0,
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": ["search_label.prefix^5", "search_aliases.prefix^3"],
                "type": "best_fields",
                "operator": "or",
                "boost": 8.0,
            }
        },
    ]
    if len(folded) >= 2:
        should += [
            {"prefix": {"label_folded": {"value": folded, "boost": 10.0}}},
            {"prefix": {"aliases_folded": {"value": folded, "boost": 8.0}}},
        ]
    expanded = expand_query(query, rewrites)
    if fold(expanded) != fold(query):
        should.append(
            {
                "multi_match": {
                    "query": expanded,
                    "fields": ["search_label^6", "address^4", "context_text^2"],
                    "type": "cross_fields",
                    "operator": "or",
                    "boost": 2.0,
                }
            }
        )
    return wrap(should, 1)


VARIANTS: dict[str, LexBuilder] = {
    "v0_current": build_v0_current,
    "v1_msm1": build_v1_msm1,
    "v2_cross_or": build_v2_cross_or,
    "v3_context_or": build_v3_context_or,
    "v4_photonish": build_v4_photonish,
}


def load_me5_tops(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vid = str(row.get("variant_id") or "")
            tops = [str(x) for x in (row.get("top_ids") or [])[:DEPTH]]
            if vid and tops:
                out[vid] = tops
    return out


def run_variant(
    name: str,
    builder: LexBuilder,
    sessions: pd.DataFrame,
    lex: dict[str, float],
    rewrites: list[dict[str, str]],
    me5_tops: dict[str, list[str]],
    es_url: str,
    index: str,
) -> dict[str, Any]:
    lex_ranks: list[int] = []
    hyb_ranks: list[int] = []
    by_family_lex: dict[str, list[int]] = defaultdict(list)
    by_family_hyb: dict[str, list[int]] = defaultdict(list)
    rescue100 = 0
    t0 = time.time()
    for i, row in enumerate(sessions.itertuples(index=False), start=1):
        vid = str(row.variant_id)
        q = str(row.query_text)
        acceptable = set(parse_acceptable(row.acceptable_poi_ids)) or {str(row.intended_poi_id)}
        body = builder(q, lex, rewrites)
        lex_ids = es_search(es_url, index, body)
        dense_ids = me5_tops.get(vid) or []
        hyb_ids = rrf_fuse(lex_ids, dense_ids) if dense_ids else lex_ids

        lr = best_rank(lex_ids, acceptable)
        hr = best_rank(hyb_ids, acceptable)
        lex_ranks.append(lr)
        hyb_ranks.append(hr)
        fam = str(row.query_variant_family)
        by_family_lex[fam].append(lr)
        by_family_hyb[fam].append(hr)

        dense_rank = best_rank(dense_ids, acceptable) if dense_ids else MISS
        if not (1 <= dense_rank <= 100) and (1 <= lr <= 100):
            rescue100 += 1

        if i % 100 == 0 or i == len(sessions):
            print(f"  [{name}] {i}/{len(sessions)} ({time.time() - t0:.0f}s)", flush=True)

    return {
        "variant": name,
        "retrieve_s": round(time.time() - t0, 1),
        "lexical": summarize(lex_ranks),
        "hybrid_rrf": summarize(hyb_ranks),
        "rescue@100": rescue100,
        "ortho_lex_r100": summarize(by_family_lex.get("ORTHOGRAPHIC_IME", [])).get("recall", {}).get(
            "R@100"
        ),
        "ortho_hyb_r100": summarize(by_family_hyb.get("ORTHOGRAPHIC_IME", [])).get("recall", {}).get(
            "R@100"
        ),
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Gold Stage-1 — Lexical structure iteration (ES) + hybrid RRF",
        "",
        f"n={report['n']} · index=`{report['index']}` · RRF k={RRF_K} · dense=frozen mE5 top-1000",
        "",
        "Mỗi bước đo **lexical riêng** và **hybrid = RRF(lexical, mE5)**.",
        "",
        "## Gate",
        "",
        "| Variant | lex R@100 | lex R@1000 | lex K@95 | lex MRR@10 | "
        "hyb R@100 | hyb R@1000 | hyb K@95 | hyb MRR@10 | rescue@100 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, p in report["profiles"].items():
        L, H = p["lexical"], p["hybrid_rrf"]
        lines.append(
            f"| `{name}` | {L['recall']['R@100']:.3f} | {L['recall']['R@1000']:.3f} | "
            f"{L['k_at_r']['K@95']} | {L['diagnostic']['MRR@10']:.3f} | "
            f"{H['recall']['R@100']:.3f} | {H['recall']['R@1000']:.3f} | "
            f"{H['k_at_r']['K@95']} | {H['diagnostic']['MRR@10']:.3f} | {p['rescue@100']} |"
        )
    lines += ["", "## Winner", ""]
    for b in report.get("verdict", {}).get("bullets", []):
        lines.append(f"- {b}")
    lines += [
        "",
        "## Variant notes",
        "",
        "- `v0_current` — production policy body (MSM≥2, field AND)",
        "- `v1_msm1` — same clauses, MSM=1",
        "- `v2_cross_or` — cross/best OR, no field AND, MSM=1",
        "- `v3_context_or` — v2 + `context_text` match (passage-like)",
        "- `v4_photonish` — stronger exact/phrase/cross + context, no fuzzy",
        "",
    ]
    return "\n".join(lines) + "\n"


def pick_winner(profiles: dict[str, dict]) -> dict[str, Any]:
    """Prefer hybrid R@100, then hybrid K@95, then lexical R@100; reject hyb R@1000 drop vs densish."""
    rows = []
    for name, p in profiles.items():
        H = p["hybrid_rrf"]
        L = p["lexical"]
        k95 = H["k_at_r"]["K@95"] or 9999
        rows.append(
            (
                H["recall"]["R@100"],
                H["recall"]["R@1000"],
                -k95,
                H["diagnostic"]["MRR@10"],
                L["recall"]["R@100"],
                name,
            )
        )
    rows.sort(reverse=True)
    best = rows[0][-1]
    base = profiles.get("v0_current", profiles[best])
    Hb, Hl = profiles[best]["hybrid_rrf"], profiles[best]["lexical"]
    H0, L0 = base["hybrid_rrf"], base["lexical"]
    bullets = [
        f"**Winner:** `{best}` — hybrid R@100={Hb['recall']['R@100']:.3f} "
        f"R@1000={Hb['recall']['R@1000']:.3f} K@95={Hb['k_at_r']['K@95']} "
        f"MRR@10={Hb['diagnostic']['MRR@10']:.3f}.",
        f"Lexical riêng: R@100={Hl['recall']['R@100']:.3f} R@1000={Hl['recall']['R@1000']:.3f} "
        f"K@95={Hl['k_at_r']['K@95']}.",
    ]
    if best != "v0_current" and "v0_current" in profiles:
        bullets.append(
            f"Vs v0: hyb R@100 {H0['recall']['R@100']:.3f}→{Hb['recall']['R@100']:.3f}, "
            f"lex R@100 {L0['recall']['R@100']:.3f}→{Hl['recall']['R@100']:.3f}."
        )
    return {"name": best, "bullets": bullets}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--es-url", default="http://127.0.0.1:9200")
    ap.add_argument("--index", default="vn-poi-core-v1-me5-small")
    ap.add_argument(
        "--variants",
        default="v0_current,v1_msm1,v2_cross_or,v3_context_or,v4_photonish",
    )
    ap.add_argument("--limit-queries", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    lex = policy["lexical"]
    rewrites = policy.get("query_rewrites") or []
    sessions = pd.read_csv(GOLD / "query_variants_v1.csv")
    if args.limit_queries > 0:
        sessions = sessions.head(args.limit_queries).copy()

    print("loading mE5 tops…", flush=True)
    me5_tops = load_me5_tops(ME5_RUN)
    print(f"mE5 tops: {len(me5_tops)}", flush=True)

    wanted = [v.strip() for v in args.variants.split(",") if v.strip()]
    profiles: dict[str, dict] = {}
    for name in wanted:
        if name not in VARIANTS:
            raise SystemExit(f"unknown variant {name}")
        print(f"=== {name} ===", flush=True)
        profiles[name] = run_variant(
            name, VARIANTS[name], sessions, lex, rewrites, me5_tops, args.es_url, args.index
        )
        L, H = profiles[name]["lexical"], profiles[name]["hybrid_rrf"]
        print(
            f"  lex R@100={L['recall']['R@100']:.3f} R@1000={L['recall']['R@1000']:.3f} "
            f"K@95={L['k_at_r']['K@95']} | "
            f"hyb R@100={H['recall']['R@100']:.3f} R@1000={H['recall']['R@1000']:.3f} "
            f"K@95={H['k_at_r']['K@95']} rescue@100={profiles[name]['rescue@100']}",
            flush=True,
        )

    report = {
        "protocol": "gold_stage1_v1_lexical_iterate_es_hybrid",
        "n": len(sessions),
        "index": args.index,
        "rrf_k": RRF_K,
        "profiles": profiles,
        "verdict": pick_winner(profiles),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "lexical_iterate_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md = render_md(report)
    (args.out_dir / "LEXICAL_ITERATE.md").write_text(md, encoding="utf-8")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "12_LEXICAL_ITERATE.md").write_text(md, encoding="utf-8")
    print("winner:", report["verdict"]["name"])
    print("wrote", args.out_dir)


if __name__ == "__main__":
    main()
