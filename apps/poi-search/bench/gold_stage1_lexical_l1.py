#!/usr/bin/env python3
"""Local Round-L1 lexical optimization on gold_stage1_v1 (no Kaggle).

Compares fielded / exact / code-aware BM25 variants against the Round-1
passage-only BM25Okapi floor. Optionally measures lexical rescue vs frozen
mE5 ranks from prior Kaggle jsonl.

Usage:
  python apps/poi-search/bench/gold_stage1_lexical_l1.py
  python apps/poi-search/bench/gold_stage1_lexical_l1.py --variants baseline_passage,fielded_v1
  python apps/poi-search/bench/gold_stage1_lexical_l1.py --limit-queries 60   # smoke
"""
from __future__ import annotations

import argparse
import json
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
CORPUS_DOCS = ROOT / "data" / "vietnam" / "poi_corpus_v1" / "search_documents.parquet"
CORPUS_POIS = ROOT / "data" / "vietnam" / "poi_corpus_v1" / "pois_core.parquet"
ME5_RUN = ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1/run_dense_me5_exact.jsonl"
OUT = Path(__file__).resolve().parent / "results" / "gold_stage1_lexical_l1"
EVIDENCE = ROOT / "docs" / "deliveries" / "w1_evidence"

DEPTH = 1000
MISS = DEPTH + 1
RECALL_KS = (20, 50, 100, 500, 1000)
DIAG_KS = (1, 5, 10, 50)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)
    )
    return " ".join(text.casefold().split())


def tokenize(text: str) -> list[str]:
    return [t for t in fold(text).split() if t]


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(x) for x in list(raw)]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


def aliases_to_text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, float) and np.isnan(raw):
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (list, tuple, np.ndarray)):
        return " ".join(str(x) for x in raw if x is not None and str(x) not in ("", "None"))
    return str(raw)


def k_at_recall(ranks: list[int], rate: float, depth: int = DEPTH) -> int | None:
    n = len(ranks)
    if n == 0:
        return None
    need = int(np.ceil(rate * n))
    ordered = sorted(ranks)
    if need > n:
        return None
    k = ordered[need - 1]
    return int(k) if k <= depth else None


def summarize(ranks: list[int]) -> dict[str, Any]:
    n = len(ranks)
    out: dict[str, Any] = {"n": n, "recall": {}, "diagnostic": {}, "k_at_r": {}}
    for k in RECALL_KS:
        out["recall"][f"R@{k}"] = sum(1 for r in ranks if 1 <= r <= k) / n if n else 0.0
    for k in DIAG_KS:
        out["diagnostic"][f"SR@{k}"] = sum(1 for r in ranks if 1 <= r <= k) / n if n else 0.0
    out["diagnostic"]["MRR@10"] = sum(1.0 / r for r in ranks if 1 <= r <= 10) / n if n else 0.0
    out["k_at_r"]["K@95"] = k_at_recall(ranks, 0.95)
    out["k_at_r"]["K@98"] = k_at_recall(ranks, 0.98)
    return out


def load_me5_ranks(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    out: dict[str, int] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vid = str(row.get("variant_id") or "")
            br = row.get("best_rank")
            if not vid or br is None:
                continue
            br = int(br)
            out[vid] = br if 1 <= br <= DEPTH else MISS
    return out


def rescue_stats(lex_ranks: dict[str, int], dense_ranks: dict[str, int], ks=(100, 1000)) -> dict:
    common = sorted(set(lex_ranks) & set(dense_ranks))
    out: dict[str, Any] = {"n": len(common)}
    for k in ks:
        rescue = sum(
            1
            for vid in common
            if not (1 <= dense_ranks[vid] <= k) and (1 <= lex_ranks[vid] <= k)
        )
        dense_hit = sum(1 for vid in common if 1 <= dense_ranks[vid] <= k)
        oracle = sum(
            1 for vid in common if min(dense_ranks[vid], lex_ranks[vid]) <= k
        )
        out[f"rescue@{k}"] = rescue
        out[f"dense_r@{k}"] = dense_hit / len(common) if common else 0.0
        out[f"oracle_r@{k}"] = oracle / len(common) if common else 0.0
        out[f"oracle_delta@{k}"] = (oracle - dense_hit) / len(common) if common else 0.0
    return out


@dataclass
class CorpusFields:
    poi_ids: list[str]
    name_toks: list[list[str]]
    brand_toks: list[list[str]]
    alias_toks: list[list[str]]
    addr_toks: list[list[str]]
    ref_toks: list[list[str]]
    passage_toks: list[list[str]]
    name_fold: list[str]
    alias_folds: list[set[str]]
    code_token_sets: list[set[str]]  # tokens with digit or from ref


def load_corpus() -> CorpusFields:
    docs = pd.read_parquet(CORPUS_DOCS)
    pois = pd.read_parquet(
        CORPUS_POIS, columns=["poi_id", "name", "aliases", "brand", "ref", "address_text"]
    )
    merged = docs.merge(pois, on="poi_id", how="left", suffixes=("", "_poi"))
    # Prefer pois_core name/address when present
    names = merged["name"].fillna(merged.get("name_poi", "")).fillna("").astype(str)
    addrs = merged["address_text"].fillna("").astype(str)
    brands = merged["brand"].fillna("").astype(str).replace({"None": "", "nan": ""})
    refs = merged["ref"].fillna("").astype(str).replace({"None": "", "nan": ""})
    alias_raw = merged["aliases"] if "aliases" in merged.columns else merged.get("aliases_poi")

    poi_ids = merged["poi_id"].astype(str).tolist()
    name_toks, brand_toks, alias_toks, addr_toks, ref_toks, passage_toks = [], [], [], [], [], []
    name_fold, alias_folds, code_sets = [], [], []

    passages = merged["passage_context"].fillna("").astype(str).tolist()
    for i in range(len(merged)):
        name = names.iloc[i]
        brand = brands.iloc[i]
        addr = addrs.iloc[i]
        ref = refs.iloc[i]
        alias_text = aliases_to_text(alias_raw.iloc[i] if alias_raw is not None else "")
        nf = fold(name)
        afs = {fold(a) for a in alias_text.split() if fold(a)}  # weak; also full alias strings
        # Better: fold each alias phrase from list
        raw_aliases = alias_raw.iloc[i] if alias_raw is not None else None
        afull: set[str] = set()
        if isinstance(raw_aliases, (list, tuple, np.ndarray)):
            for a in raw_aliases:
                fa = fold(str(a))
                if fa:
                    afull.add(fa)
        elif alias_text:
            afull.add(fold(alias_text))

        nt = tokenize(name)
        bt = tokenize(brand)
        at = tokenize(alias_text)
        adt = tokenize(addr)
        rt = tokenize(ref)
        pt = tokenize(passages[i])

        codes = {t for t in nt + rt + at if any(ch.isdigit() for ch in t) or (len(t) <= 6 and any(ch.isdigit() for ch in t))}
        codes |= set(rt)

        name_toks.append(nt)
        brand_toks.append(bt)
        alias_toks.append(at)
        addr_toks.append(adt)
        ref_toks.append(rt)
        passage_toks.append(pt)
        name_fold.append(nf)
        alias_folds.append(afull)
        code_sets.append(codes)

    return CorpusFields(
        poi_ids=poi_ids,
        name_toks=name_toks,
        brand_toks=brand_toks,
        alias_toks=alias_toks,
        addr_toks=addr_toks,
        ref_toks=ref_toks,
        passage_toks=passage_toks,
        name_fold=name_fold,
        alias_folds=alias_folds,
        code_token_sets=code_sets,
    )


class FieldBM25:
    """Weighted multi-field BM25 with candidate pruning (inverted index)."""

    def __init__(
        self,
        corpus: CorpusFields,
        field_weights: dict[str, float],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        exact_name_boost: float = 0.0,
        exact_alias_boost: float = 0.0,
        all_tokens_name_addr_boost: float = 0.0,
        code_overlap_boost: float = 0.0,
    ) -> None:
        from rank_bm25 import BM25Okapi

        self.corpus = corpus
        self.weights = field_weights
        self.exact_name_boost = exact_name_boost
        self.exact_alias_boost = exact_alias_boost
        self.all_tokens_name_addr_boost = all_tokens_name_addr_boost
        self.code_overlap_boost = code_overlap_boost
        self.indexes: dict[str, Any] = {}
        mapping = {
            "name": corpus.name_toks,
            "brand": corpus.brand_toks,
            "alias": corpus.alias_toks,
            "addr": corpus.addr_toks,
            "ref": corpus.ref_toks,
            "passage": corpus.passage_toks,
        }
        # token -> doc ids (union of active fields) for candidate pruning
        inv: dict[str, set[int]] = defaultdict(set)
        for key, weight in field_weights.items():
            if weight == 0:
                continue
            toks_list = mapping[key]
            self.indexes[key] = BM25Okapi(toks_list, k1=k1, b=b)
            for doc_id, toks in enumerate(toks_list):
                for t in toks:
                    inv[t].add(doc_id)
        self.inv = {t: np.fromiter(ids, dtype=np.int32) for t, ids in inv.items()}

        # exact-fold lookup
        self.name_fold_to_ids: dict[str, list[int]] = defaultdict(list)
        for i, nf in enumerate(corpus.name_fold):
            if nf:
                self.name_fold_to_ids[nf].append(i)
        self.alias_fold_to_ids: dict[str, list[int]] = defaultdict(list)
        for i, afs in enumerate(corpus.alias_folds):
            for af in afs:
                self.alias_fold_to_ids[af].append(i)

        # precompute name|brand|addr token sets only if needed
        self.cover_bags: list[set[str]] | None = None
        if all_tokens_name_addr_boost:
            self.cover_bags = [
                set(corpus.name_toks[i]) | set(corpus.addr_toks[i]) | set(corpus.brand_toks[i])
                for i in range(len(corpus.poi_ids))
            ]

    def _candidates(self, q: list[str]) -> np.ndarray:
        if not q:
            return np.array([], dtype=np.int32)
        acc: set[int] | None = None
        # OR of postings (any query token) — recall-oriented
        buckets = []
        for t in q:
            ids = self.inv.get(t)
            if ids is not None and len(ids):
                buckets.append(ids)
        if not buckets:
            return np.array([], dtype=np.int32)
        return np.unique(np.concatenate(buckets))

    def rank(self, query: str, depth: int = DEPTH) -> list[str]:
        q = tokenize(query)
        n = len(self.corpus.poi_ids)
        cand = self._candidates(q)
        if cand.size == 0:
            return []

        scores = np.zeros(cand.size, dtype=np.float64)
        cand_list = cand.tolist()
        if q:
            for key, bm25 in self.indexes.items():
                w = self.weights[key]
                # get_batch_scores only over candidates
                scores += w * np.asarray(bm25.get_batch_scores(q, cand_list), dtype=np.float64)

        qf = fold(query)
        qset = set(q)
        if self.exact_name_boost and qf:
            hit = set(self.name_fold_to_ids.get(qf, ()))
            if hit:
                for j, doc_id in enumerate(cand_list):
                    if doc_id in hit:
                        scores[j] += self.exact_name_boost
        if self.exact_alias_boost and qf:
            hit = set(self.alias_fold_to_ids.get(qf, ()))
            if hit:
                for j, doc_id in enumerate(cand_list):
                    if doc_id in hit:
                        scores[j] += self.exact_alias_boost
        if self.all_tokens_name_addr_boost and qset and self.cover_bags is not None:
            for j, doc_id in enumerate(cand_list):
                if qset <= self.cover_bags[doc_id]:
                    scores[j] += self.all_tokens_name_addr_boost
        if self.code_overlap_boost and qset:
            for j, doc_id in enumerate(cand_list):
                ov = qset & self.corpus.code_token_sets[doc_id]
                if ov:
                    scores[j] += self.code_overlap_boost * len(ov)

        if not np.any(scores > 0):
            return []

        depth = min(depth, cand.size)
        part = np.argpartition(-scores, depth - 1)[:depth]
        part_sorted = part[np.argsort(-scores[part])]
        return [self.corpus.poi_ids[cand_list[i]] for i in part_sorted]



VariantBuilder = Callable[[CorpusFields], FieldBM25]


def variant_catalog() -> dict[str, VariantBuilder]:
    return {
        # Round-1 floor
        "baseline_passage": lambda c: FieldBM25(c, {"passage": 1.0}, k1=1.5, b=0.75),
        # Fielded structured (L1 primary bet)
        "fielded_v1": lambda c: FieldBM25(
            c,
            {"name": 4.0, "brand": 3.0, "alias": 2.5, "addr": 2.0, "ref": 5.0, "passage": 1.0},
            k1=1.5,
            b=0.75,
        ),
        # Less length-norm on short names / codes
        "fielded_shortnorm": lambda c: FieldBM25(
            c,
            {"name": 4.0, "brand": 3.0, "alias": 2.5, "addr": 2.0, "ref": 5.0, "passage": 1.0},
            k1=1.2,
            b=0.4,
        ),
        # Exact fold + all-token coverage (ORTHO / address disambiguation)
        "fielded_exact": lambda c: FieldBM25(
            c,
            {"name": 4.0, "brand": 3.0, "alias": 2.5, "addr": 2.0, "ref": 5.0, "passage": 1.0},
            k1=1.5,
            b=0.75,
            exact_name_boost=25.0,
            exact_alias_boost=18.0,
            all_tokens_name_addr_boost=8.0,
            code_overlap_boost=6.0,
        ),
        # Name+address heavy (brand_branch / address strata)
        "name_addr_heavy": lambda c: FieldBM25(
            c,
            {"name": 6.0, "brand": 4.0, "alias": 2.0, "addr": 4.0, "ref": 5.0, "passage": 0.5},
            k1=1.5,
            b=0.6,
            exact_name_boost=20.0,
            exact_alias_boost=14.0,
            all_tokens_name_addr_boost=10.0,
            code_overlap_boost=8.0,
        ),
    }


def best_rank(top_ids: list[str], acceptable: set[str]) -> int:
    for i, pid in enumerate(top_ids, start=1):
        if pid in acceptable:
            return i
    return MISS


def run_variant(
    name: str,
    retriever: FieldBM25,
    sessions: pd.DataFrame,
    dense_ranks: dict[str, int],
) -> dict[str, Any]:
    t0 = time.time()
    ranks: list[int] = []
    by_family: dict[str, list[int]] = defaultdict(list)
    by_stratum: dict[str, list[int]] = defaultdict(list)
    lex_by_vid: dict[str, int] = {}

    for i, row in enumerate(sessions.itertuples(index=False), start=1):
        acceptable = set(parse_acceptable(row.acceptable_poi_ids))
        if not acceptable:
            acceptable = {str(row.intended_poi_id)}
        top = retriever.rank(str(row.query_text), DEPTH)
        br = best_rank(top, acceptable)
        ranks.append(br)
        vid = str(row.variant_id)
        lex_by_vid[vid] = br
        by_family[str(row.query_variant_family)].append(br)
        by_stratum[str(row.primary_sampling_stratum)].append(br)
        if i % 100 == 0 or i == len(sessions):
            print(f"    … {i}/{len(sessions)} queries ({time.time() - t0:.0f}s)", flush=True)

    elapsed = time.time() - t0
    profile = {
        "variant": name,
        "retrieve_s": round(elapsed, 1),
        "overall": summarize(ranks),
        "by_family": {k: summarize(v) for k, v in sorted(by_family.items())},
        "by_stratum": {k: summarize(v) for k, v in sorted(by_stratum.items())},
    }
    if dense_ranks:
        profile["vs_me5"] = rescue_stats(lex_by_vid, dense_ranks)
        # ORTHO rescue @100 specifically
        ortho_vids = [
            str(r.variant_id)
            for r in sessions.itertuples(index=False)
            if str(r.query_variant_family) == "ORTHOGRAPHIC_IME"
        ]
        ortho_rescue = sum(
            1
            for vid in ortho_vids
            if vid in dense_ranks
            and vid in lex_by_vid
            and not (1 <= dense_ranks[vid] <= 100)
            and (1 <= lex_by_vid[vid] <= 100)
        )
        profile["vs_me5"]["ortho_rescue@100"] = ortho_rescue
    return profile


def render_md(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Gold Stage-1 — Lexical L1 local experiments")
    lines.append("")
    lines.append(
        f"**Mode:** local CPU · no Kaggle · n={report['n_queries']} · depth={report['depth']}"
    )
    lines.append(f"**Corpus:** `{report['corpus']}` ({report['n_docs']} docs)")
    lines.append("")
    lines.append("Objective L1: ↑ R@20/50/100 · ↓ K@95 · ↑ MRR@10 · giữ R@1000 ≥ baseline · bảo toàn rescue ORTHO.")
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(
        "| Variant | R@20 | R@50 | R@100 | R@1000 | K@95 | K@98 | MRR@10 | "
        "rescue@100 | ortho_rescue@100 | oracleΔ@100 | s |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, p in report["profiles"].items():
        o = p["overall"]
        vs = p.get("vs_me5") or {}
        lines.append(
            f"| {name} | {o['recall']['R@20']:.3f} | {o['recall']['R@50']:.3f} | "
            f"{o['recall']['R@100']:.3f} | {o['recall']['R@1000']:.3f} | "
            f"{o['k_at_r']['K@95']} | {o['k_at_r']['K@98']} | {o['diagnostic']['MRR@10']:.3f} | "
            f"{vs.get('rescue@100', '—')} | {vs.get('ortho_rescue@100', '—')} | "
            f"{vs.get('oracle_delta@100', float('nan')) if 'oracle_delta@100' in vs else '—'} | "
            f"{p['retrieve_s']} |"
        )
    # fix formatting for delta
    # rewrite last table properly
    lines = lines[: lines.index("## Gate") + 1]
    lines.append("")
    lines.append(
        "| Variant | R@20 | R@50 | R@100 | R@1000 | K@95 | MRR@10 | rescue@100 | ortho@100 | Δoracle@100 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    baseline_r1000 = None
    for name, p in report["profiles"].items():
        o = p["overall"]
        vs = p.get("vs_me5") or {}
        if name == "baseline_passage":
            baseline_r1000 = o["recall"]["R@1000"]
        delta = vs.get("oracle_delta@100")
        delta_s = f"{delta:+.3f}" if isinstance(delta, float) else "—"
        lines.append(
            f"| `{name}` | {o['recall']['R@20']:.3f} | {o['recall']['R@50']:.3f} | "
            f"{o['recall']['R@100']:.3f} | {o['recall']['R@1000']:.3f} | "
            f"{o['k_at_r']['K@95']} | {o['diagnostic']['MRR@10']:.3f} | "
            f"{vs.get('rescue@100', '—')} | {vs.get('ortho_rescue@100', '—')} | {delta_s} |"
        )
    lines.append("")
    winner = report.get("winner") or {}
    lines.append("## Verdict")
    lines.append("")
    for b in winner.get("bullets", []):
        lines.append(f"- {b}")
    if baseline_r1000 is not None:
        lines.append(f"- Baseline R@1000 = {baseline_r1000:.3f} (floor screening Round-1).")
    lines.append("")
    lines.append("## ORTHOGRAPHIC_IME R@100 (preserve advantage)")
    lines.append("")
    lines.append("| Variant | R@100 ORTHO |")
    lines.append("|---|---:|")
    for name, p in report["profiles"].items():
        fam = p.get("by_family", {}).get("ORTHOGRAPHIC_IME", {})
        r = (fam.get("recall") or {}).get("R@100")
        if r is not None:
            lines.append(f"| `{name}` | {r:.3f} |")
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.append("- Chọn winner L1 theo gate trên (ưu tiên R@100 + K@95 + rescue, không chỉ R@1000).")
    lines.append("- Round L2: đo hybrid RRF với mE5 trên máy local (ES hoặc fusion offline) — winner cuối = hybrid gain.")
    lines.append("- Kaggle chỉ khi train/fine-tune encoder.")
    lines.append("")
    return "\n".join(lines) + "\n"


def pick_winner(profiles: dict[str, dict]) -> dict[str, Any]:
    """Score L1: prioritize R@100, K@95 (lower better), MRR, keep R@1000, rescue."""
    rows = []
    base = profiles.get("baseline_passage", {}).get("overall", {})
    base_r1000 = (base.get("recall") or {}).get("R@1000", 0.0)
    for name, p in profiles.items():
        o = p["overall"]
        vs = p.get("vs_me5") or {}
        r1000 = o["recall"]["R@1000"]
        if r1000 + 1e-9 < base_r1000 - 0.005:
            # soft reject if drops R@1000 by >0.5pp
            continue
        k95 = o["k_at_r"]["K@95"] or 9999
        rows.append(
            (
                o["recall"]["R@100"],
                -k95,
                o["diagnostic"]["MRR@10"],
                vs.get("rescue@100", 0),
                vs.get("oracle_delta@100", 0.0),
                r1000,
                name,
            )
        )
    rows.sort(reverse=True)
    bullets = []
    if not rows:
        bullets.append("Không có variant nào giữ R@1000 gần baseline.")
        return {"name": None, "bullets": bullets}
    best = rows[0][-1]
    o = profiles[best]["overall"]
    vs = profiles[best].get("vs_me5") or {}
    bullets.append(
        f"**L1 winner (local):** `{best}` — R@100={o['recall']['R@100']:.3f}, "
        f"K@95={o['k_at_r']['K@95']}, MRR@10={o['diagnostic']['MRR@10']:.3f}, "
        f"R@1000={o['recall']['R@1000']:.3f}, rescue@100={vs.get('rescue@100')}."
    )
    if "baseline_passage" in profiles and best != "baseline_passage":
        b = profiles["baseline_passage"]["overall"]
        bullets.append(
            f"Vs baseline_passage: R@100 {b['recall']['R@100']:.3f}→{o['recall']['R@100']:.3f}, "
            f"K@95 {b['k_at_r']['K@95']}→{o['k_at_r']['K@95']}, "
            f"MRR {b['diagnostic']['MRR@10']:.3f}→{o['diagnostic']['MRR@10']:.3f}."
        )
    bullets.append(
        "Chưa phải winner production — cần Round L2 hybrid với mE5 trước khi khóa analyzer/ES boosts."
    )
    return {"name": best, "bullets": bullets}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--variants",
        type=str,
        default="baseline_passage,fielded_v1,fielded_shortnorm,fielded_exact,name_addr_heavy",
    )
    ap.add_argument("--limit-queries", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    try:
        import rank_bm25  # noqa: F401
    except ImportError as e:
        raise SystemExit("pip install rank_bm25") from e

    sessions = pd.read_csv(GOLD / "query_variants_v1.csv")
    if args.limit_queries and args.limit_queries > 0:
        sessions = sessions.head(args.limit_queries).copy()

    print(f"loading corpus ({CORPUS_DOCS}) …", flush=True)
    t0 = time.time()
    corpus = load_corpus()
    print(f"corpus ready: {len(corpus.poi_ids)} docs in {time.time() - t0:.1f}s", flush=True)

    dense_ranks = load_me5_ranks(ME5_RUN)
    if dense_ranks:
        print(f"loaded mE5 ranks: {len(dense_ranks)}", flush=True)
    else:
        print("warn: no mE5 ranks — rescue metrics skipped", flush=True)

    catalog = variant_catalog()
    wanted = [v.strip() for v in args.variants.split(",") if v.strip()]
    for v in wanted:
        if v not in catalog:
            raise SystemExit(f"unknown variant {v}; choose from {list(catalog)}")

    profiles: dict[str, dict] = {}
    for name in wanted:
        print(f"building {name} …", flush=True)
        t1 = time.time()
        retriever = catalog[name](corpus)
        print(f"  index {time.time() - t1:.1f}s; retrieving {len(sessions)} queries …", flush=True)
        profiles[name] = run_variant(name, retriever, sessions, dense_ranks)
        o = profiles[name]["overall"]
        print(
            f"  {name}: R@100={o['recall']['R@100']:.3f} R@1000={o['recall']['R@1000']:.3f} "
            f"K@95={o['k_at_r']['K@95']} MRR@10={o['diagnostic']['MRR@10']:.3f} "
            f"({profiles[name]['retrieve_s']}s)",
            flush=True,
        )

    report = {
        "protocol": "gold_stage1_v1_lexical_l1_local",
        "n_queries": len(sessions),
        "n_docs": len(corpus.poi_ids),
        "depth": DEPTH,
        "corpus": str(CORPUS_DOCS.as_posix()),
        "me5_run": str(ME5_RUN.as_posix()) if dense_ranks else None,
        "profiles": profiles,
        "winner": pick_winner(profiles),
        "note": "Local L1 only. Production ES lexical_body may differ; port winner boosts after L2 hybrid.",
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "lexical_l1_report.json"
    md_path = args.out_dir / "LEXICAL_L1_LOCAL.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render_md(report)
    md_path.write_text(md, encoding="utf-8")
    evidence_path = EVIDENCE / "10_LEXICAL_L1_LOCAL.md"
    evidence_path.write_text(md, encoding="utf-8")
    print("wrote", json_path)
    print("wrote", md_path)
    print("wrote", evidence_path)
    if report["winner"].get("name"):
        print("winner:", report["winner"]["name"])


if __name__ == "__main__":
    main()
