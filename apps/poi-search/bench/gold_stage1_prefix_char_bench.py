#!/usr/bin/env python3
"""Gold Stage-1 Round-1b: deterministic char-prefix FHC / SHC / PrefixAUC.

Prefixes are NOT stored in gold CSV. At bench time, expand NFC grapheme prefixes
from locked `query_variants_v1.query_text`, then retrieve and score.

Metrics (char unit):
  FHC-char@K  — first prefix length where acceptable POI enters top-K
  SHC-char@K  — first length where a window of w=3 consecutive prefixes all hit
  PrefixAUC@K — fraction of prefix lengths with hit@K

Usage:
  # Expand only (for Kaggle / inspection)
  python apps/poi-search/bench/gold_stage1_prefix_char_bench.py --expand-only

  # BM25 smoke (local; full 1080×~32 prefixes is heavy)
  python apps/poi-search/bench/gold_stage1_prefix_char_bench.py --backend bm25 --limit-queries 20

  # Score from checkpoints jsonl (variant_id, prefix_index, rank | top_ids)
  python apps/poi-search/bench/gold_stage1_prefix_char_bench.py --from-checkpoints path/to/prefix_ranks.jsonl
"""
from __future__ import annotations

import argparse
import json
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v1" / "search_documents.parquet"
OUT = Path(__file__).resolve().parent / "results" / "gold_stage1_prefix_char"

K_LIST = (1, 5, 10)
SHC_WINDOW = 3


def grapheme_clusters(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", str(text or ""))
    out: list[str] = []
    for ch in text:
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(x) for x in list(raw)]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


def expand_char_prefixes(sessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in sessions.itertuples(index=False):
        chars = grapheme_clusters(row.query_text)
        if not chars:
            continue
        acceptable = parse_acceptable(getattr(row, "acceptable_poi_ids", None))
        if not acceptable:
            acceptable = [str(row.intended_poi_id)]
        for n in range(1, len(chars) + 1):
            prefix = "".join(chars[:n])
            if not prefix.strip():
                continue
            rows.append(
                {
                    "variant_id": row.variant_id,
                    "case_id": row.case_id,
                    "query_variant_family": row.query_variant_family,
                    "variant_operator": getattr(row, "variant_operator", None),
                    "primary_sampling_stratum": row.primary_sampling_stratum,
                    "intended_poi_id": str(row.intended_poi_id),
                    "acceptable_poi_ids": "|".join(acceptable),
                    "full_query_text": row.query_text,
                    "prefix_text": prefix,
                    "prefix_unit": "char",
                    "prefix_index": n,
                    "full_unit_count": len(chars),
                    "is_full_query": n == len(chars),
                }
            )
    return pd.DataFrame(rows)


def best_rank(top_ids: list[str], acceptable: set[str]) -> int | None:
    for i, pid in enumerate(top_ids, start=1):
        if str(pid) in acceptable:
            return i
    return None


def compute_variant_prefix_metrics(
    ranks_by_t: list[int | None], k_list: tuple[int, ...], w: int = SHC_WINDOW
) -> dict:
    t_q = len(ranks_by_t)
    out: dict = {"T_q": t_q, "fhc": {}, "shc": {}, "prefix_auc": {}}
    for k in k_list:
        hits = [r is not None and r <= k for r in ranks_by_t]
        fhc = next((t + 1 for t, h in enumerate(hits) if h), None)
        out["fhc"][k] = {"found": fhc is not None, "value": fhc}
        shc = None
        for t0 in range(t_q):
            end = min(t0 + w, t_q)
            if all(hits[s] for s in range(t0, end)):
                shc = t0 + 1
                break
        out["shc"][k] = {"found": shc is not None, "value": shc, "w": w}
        out["prefix_auc"][k] = (sum(1 for h in hits if h) / t_q) if t_q else 0.0
    return out


def summarize(prefix_rows: list[dict], by_variant: dict[str, dict], k_list: tuple[int, ...]) -> dict:
    n_var = len(by_variant)
    out: dict = {
        "n_variants": n_var,
        "n_prefix_checkpoints": len(prefix_rows),
        "prefix_unit": "char_grapheme",
        "shc_window": SHC_WINDOW,
        "k_list": list(k_list),
        "fhc": {},
        "shc": {},
        "prefix_auc": {},
        "by_family": {},
    }

    def agg(metric: str, k: int) -> dict:
        vals, miss = [], 0
        for info in by_variant.values():
            cell = info[metric][k]
            if not cell["found"]:
                miss += 1
            else:
                vals.append(cell["value"])
        arr = np.asarray(vals, dtype=np.float64) if vals else np.asarray([], dtype=np.float64)
        return {
            "hit_rate": (n_var - miss) / n_var if n_var else 0.0,
            "n_found": n_var - miss,
            "n_miss": miss,
            "mean_conditional": float(arr.mean()) if len(arr) else None,
            "p50_conditional": float(np.quantile(arr, 0.5)) if len(arr) else None,
        }

    for k in k_list:
        out["fhc"][f"@{k}"] = agg("fhc", k)
        out["shc"][f"@{k}"] = agg("shc", k)
        aucs = [info["prefix_auc"][k] for info in by_variant.values()]
        arr = np.asarray(aucs, dtype=np.float64)
        out["prefix_auc"][f"@{k}"] = {
            "mean": float(arr.mean()) if len(arr) else 0.0,
            "p50": float(np.quantile(arr, 0.5)) if len(arr) else 0.0,
        }

    by_f: dict[str, list] = defaultdict(list)
    for info in by_variant.values():
        by_f[info["query_variant_family"]].append(info)
    for fam, items in by_f.items():
        n = len(items)
        out["by_family"][fam] = {
            "n": n,
            **{
                f"FHC-char-HitRate@{k}": sum(1 for x in items if x["fhc"][k]["found"]) / n if n else 0.0
                for k in k_list
            },
            **{
                f"PrefixAUC-char@{k}_mean": float(np.mean([x["prefix_auc"][k] for x in items])) if n else 0.0
                for k in k_list
            },
        }
    return out


def fold_metrics_from_rows(prefix_rows: list[dict], k_list: tuple[int, ...]) -> tuple[dict, dict]:
    by_vid: dict[str, list] = defaultdict(list)
    meta: dict[str, dict] = {}
    for r in prefix_rows:
        by_vid[r["variant_id"]].append(r)
        meta[r["variant_id"]] = {
            "case_id": r["case_id"],
            "query_variant_family": r["query_variant_family"],
            "primary_sampling_stratum": r["primary_sampling_stratum"],
            "full_unit_count": r["full_unit_count"],
        }
    by_variant: dict[str, dict] = {}
    for vid, rows in by_vid.items():
        rows = sorted(rows, key=lambda x: x["prefix_index"])
        ranks = [x.get("rank") for x in rows]
        m = compute_variant_prefix_metrics(ranks, k_list)
        m.update(meta[vid])
        by_variant[vid] = m
    return summarize(prefix_rows, by_variant, k_list), by_variant


def run_bm25(prefixes: pd.DataFrame, max_k: int) -> list[dict]:
    from rank_bm25 import BM25Okapi

    def fold(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "").replace("đ", "d").replace("Đ", "D")
        return " ".join(
            "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
            .casefold()
            .split()
        )

    def tokenize(text: str) -> list[str]:
        return [t for t in fold(text).split() if t]

    docs = pd.read_parquet(CORPUS, columns=["poi_id", "passage_context"])
    ids = docs["poi_id"].astype(str).tolist()
    print("building BM25 …", flush=True)
    t0 = time.time()
    bm25 = BM25Okapi([tokenize(t) for t in docs["passage_context"].fillna("").tolist()])
    print(f"BM25 ready in {time.time() - t0:.1f}s; scoring {len(prefixes)} prefixes", flush=True)

    out: list[dict] = []
    t1 = time.time()
    for i, row in enumerate(prefixes.itertuples(index=False), start=1):
        scores = np.asarray(bm25.get_scores(tokenize(row.prefix_text)), dtype=np.float64)
        k = min(max_k, len(scores))
        idx = np.argpartition(scores, -k)[-k:]
        idx = idx[np.argsort(scores[idx])[::-1]]
        top = [ids[j] for j in idx]
        acceptable = set(parse_acceptable(row.acceptable_poi_ids))
        out.append(
            {
                "variant_id": row.variant_id,
                "case_id": row.case_id,
                "query_variant_family": row.query_variant_family,
                "primary_sampling_stratum": row.primary_sampling_stratum,
                "prefix_index": int(row.prefix_index),
                "full_unit_count": int(row.full_unit_count),
                "is_full_query": bool(row.is_full_query),
                "prefix_text": row.prefix_text,
                "rank": best_rank(top, acceptable),
            }
        )
        if i % 500 == 0 or i == len(prefixes):
            print(f"  {i}/{len(prefixes)} elapsed={time.time() - t1:.1f}s", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=Path, default=GOLD / "query_variants_v1.csv")
    ap.add_argument("--expand-only", action="store_true")
    ap.add_argument("--backend", choices=["bm25", "none"], default="none")
    ap.add_argument("--limit-queries", type=int, default=0)
    ap.add_argument("--max-k", type=int, default=10)
    ap.add_argument("--from-checkpoints", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    k_list = tuple(k for k in K_LIST if k <= args.max_k)

    sessions = pd.read_csv(args.queries)
    if args.limit_queries:
        # keep whole cases: first N case_ids
        cases = sessions["case_id"].drop_duplicates().head(args.limit_queries).tolist()
        sessions = sessions[sessions["case_id"].isin(cases)]

    prefixes = expand_char_prefixes(sessions)
    pref_path = args.out_dir / "char_prefixes.parquet"
    prefixes.to_parquet(pref_path, index=False)
    print(
        f"expanded {len(prefixes)} char prefixes from {sessions.variant_id.nunique()} variants "
        f"({sessions.case_id.nunique()} cases) → {pref_path}"
    )
    if args.expand_only or args.backend == "none" and not args.from_checkpoints:
        return

    if args.from_checkpoints:
        rows = []
        with args.from_checkpoints.open(encoding="utf-8") as f:
            for line in f:
                rows.append(json.loads(line))
        # join meta from expand if missing
        meta = prefixes.set_index(["variant_id", "prefix_index"])
        enriched = []
        for r in rows:
            key = (r["variant_id"], int(r["prefix_index"]))
            m = meta.loc[key] if key in meta.index else None
            if m is not None:
                r.setdefault("case_id", m["case_id"])
                r.setdefault("query_variant_family", m["query_variant_family"])
                r.setdefault("primary_sampling_stratum", m["primary_sampling_stratum"])
                r.setdefault("full_unit_count", int(m["full_unit_count"]))
            if "rank" not in r and r.get("top_ids"):
                acc = set(parse_acceptable(m["acceptable_poi_ids"] if m is not None else r.get("acceptable_poi_ids")))
                r["rank"] = best_rank([str(x) for x in r["top_ids"]], acc)
            enriched.append(r)
        prefix_rows = enriched
    else:
        prefix_rows = run_bm25(prefixes, max(k_list))

    summary, _ = fold_metrics_from_rows(prefix_rows, k_list)
    summary["backend"] = "checkpoints" if args.from_checkpoints else args.backend
    out_json = args.out_dir / "prefix_char_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out_json)
    for k in k_list:
        fhc = summary["fhc"][f"@{k}"]
        auc = summary["prefix_auc"][f"@{k}"]
        print(
            f"FHC-char@{k}: hit_rate={fhc['hit_rate']:.3f} p50_cond={fhc['p50_conditional']} | "
            f"PrefixAUC@{k}_mean={auc['mean']:.3f}"
        )


if __name__ == "__main__":
    main()
