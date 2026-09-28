#!/usr/bin/env python3
"""Lexical vs dense overlap / rescue diagnostic on gold_stage1 Round-1 ranks.

Answers (before analyzer tuning):
  - Where does BM25 hit while mE5 misses (rescue @K)?
  - Where does mE5 hit while BM25 misses (dense-only)?
  - How deep are BM25 hits when they succeed (precision / K@95 problem)?
  - Oracle union upper bound (min rank) as hybrid ceiling without RRF.

Winner of later lexical tuning should be chosen by hybrid gain, not standalone BM25.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
DEFAULT_RUNS = ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1"
OUT = Path(__file__).resolve().parent / "results" / "gold_stage1_lexical_rescue"

DEPTH = 1000
MISS = DEPTH + 1
RESCUE_KS = (20, 50, 100, 500, 1000)
PRECISION_KS = (10, 20, 50, 100)


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(x) for x in list(raw)]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


def load_best_ranks(path: Path, meta: dict[str, dict]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vid = str(row.get("variant_id") or "")
            if not vid:
                continue
            if "best_rank" in row and row["best_rank"] is not None:
                br = int(row["best_rank"])
                if br <= 0:
                    br = MISS
                ranks[vid] = br if br <= DEPTH else MISS
                continue
            m = meta.get(vid) or {}
            acceptable = set(parse_acceptable(row.get("acceptable_poi_ids")))
            if not acceptable:
                acceptable = set(parse_acceptable(m.get("acceptable_poi_ids")))
            if not acceptable:
                pid = str(row.get("intended_poi_id") or m.get("intended_poi_id") or "")
                if pid:
                    acceptable = {pid}
            br = MISS
            for i, pid in enumerate(row.get("top_ids") or [], start=1):
                if str(pid) in acceptable:
                    br = i
                    break
            ranks[vid] = br
    return ranks


def hit(rank: int, k: int) -> bool:
    return 1 <= rank <= k


def rate(n: int, d: int) -> float:
    return float(n) / float(d) if d else 0.0


def summarize_bucket(rows: list[dict], ks: tuple[int, ...] = RESCUE_KS) -> dict[str, Any]:
    n = len(rows)
    out: dict[str, Any] = {"n": n, "at_k": {}}
    for k in ks:
        both = sum(1 for r in rows if hit(r["dense"], k) and hit(r["lex"], k))
        dense_only = sum(1 for r in rows if hit(r["dense"], k) and not hit(r["lex"], k))
        lex_only = sum(1 for r in rows if not hit(r["dense"], k) and hit(r["lex"], k))
        both_miss = sum(1 for r in rows if not hit(r["dense"], k) and not hit(r["lex"], k))
        dense_hit = both + dense_only
        lex_hit = both + lex_only
        oracle = sum(1 for r in rows if hit(r["oracle"], k))
        out["at_k"][str(k)] = {
            "dense_hit": dense_hit,
            "lex_hit": lex_hit,
            "both_hit": both,
            "dense_only": dense_only,
            "lex_only_rescue": lex_only,
            "both_miss": both_miss,
            "oracle_union_hit": oracle,
            "dense_recall": rate(dense_hit, n),
            "lex_recall": rate(lex_hit, n),
            "oracle_recall": rate(oracle, n),
            "rescue_rate_of_dense_miss": rate(lex_only, both_miss + lex_only)
            if (both_miss + lex_only)
            else 0.0,
            "marginal_gain_vs_dense": rate(oracle - dense_hit, n),
        }
    # BM25 depth among lexical hits @1000
    lex_ranks = [r["lex"] for r in rows if hit(r["lex"], DEPTH)]
    if lex_ranks:
        arr = np.asarray(lex_ranks, dtype=np.float64)
        out["lex_hit_depth"] = {
            "n_hit_at_1000": int(len(arr)),
            "mean_rank": float(arr.mean()),
            "p50": float(np.median(arr)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "frac_rank_le_20": rate(sum(1 for x in arr if x <= 20), len(arr)),
            "frac_rank_le_50": rate(sum(1 for x in arr if x <= 50), len(arr)),
            "frac_rank_le_100": rate(sum(1 for x in arr if x <= 100), len(arr)),
            "frac_rank_gt_100": rate(sum(1 for x in arr if x > 100), len(arr)),
        }
    else:
        out["lex_hit_depth"] = None
    return out


def slice_counts(rows: list[dict], key: str, k: int = 100) -> list[dict[str, Any]]:
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        buckets[str(r.get(key) or "unknown")].append(r)
    table = []
    for label, items in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        s = summarize_bucket(items, ks=(k,))
        at = s["at_k"][str(k)]
        table.append(
            {
                key: label,
                "n": s["n"],
                "dense_recall": at["dense_recall"],
                "lex_recall": at["lex_recall"],
                "lex_only_rescue": at["lex_only_rescue"],
                "dense_only": at["dense_only"],
                "both_miss": at["both_miss"],
                "oracle_recall": at["oracle_recall"],
                "marginal_gain_vs_dense": at["marginal_gain_vs_dense"],
                "rescue_rate_of_dense_miss": at["rescue_rate_of_dense_miss"],
            }
        )
    return table


def standalone_metrics(ranks: list[int]) -> dict[str, Any]:
    n = len(ranks)
    out: dict[str, Any] = {"n": n, "recall": {}, "diagnostic": {}, "k_at_r": {}}
    for k in (20, 50, 100, 500, 1000):
        out["recall"][f"R@{k}"] = rate(sum(1 for r in ranks if hit(r, k)), n)
    for k in PRECISION_KS:
        out["diagnostic"][f"SR@{k}"] = rate(sum(1 for r in ranks if hit(r, k)), n)
    out["diagnostic"]["MRR@10"] = (
        sum(1.0 / r for r in ranks if hit(r, 10)) / n if n else 0.0
    )

    def k_at(rate_target: float) -> int | None:
        need = int(np.ceil(rate_target * n))
        ordered = sorted(ranks)
        if need > n or need <= 0:
            return None
        k = ordered[need - 1]
        return int(k) if k <= DEPTH else None

    out["k_at_r"]["K@95"] = k_at(0.95)
    out["k_at_r"]["K@98"] = k_at(0.98)
    return out


def md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def render_markdown(report: dict[str, Any]) -> str:
    o = report["overlap"]["overall"]
    lines: list[str] = []
    lines.append("# Gold Stage-1 — Lexical rescue / overlap diagnostic")
    lines.append("")
    lines.append(f"**Dataset:** `{report['dataset']}` · {report['n_variants']} queries · depth {report['depth']}")
    lines.append(
        f"**Profiles:** dense=`{report['dense_profile']}` · lexical=`{report['lex_profile']}`"
    )
    lines.append(f"**Sources:** `{report['dense_run']}` · `{report['lex_run']}`")
    lines.append("")
    lines.append("## Verdict (actionable)")
    lines.append("")
    v = report["verdict"]
    for bullet in v["bullets"]:
        lines.append(f"- {bullet}")
    lines.append("")
    lines.append("## Standalone ranks (context)")
    lines.append("")
    lines.append("| Profile | R@20 | R@50 | R@100 | R@500 | R@1000 | K@95 | K@98 | MRR@10 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, m in report["standalone"].items():
        lines.append(
            f"| {name} | {m['recall']['R@20']:.3f} | {m['recall']['R@50']:.3f} | "
            f"{m['recall']['R@100']:.3f} | {m['recall']['R@500']:.3f} | {m['recall']['R@1000']:.3f} | "
            f"{m['k_at_r']['K@95']} | {m['k_at_r']['K@98']} | {m['diagnostic']['MRR@10']:.3f} |"
        )
    lines.append("")
    lines.append("## Overlap & lexical rescue vs mE5")
    lines.append("")
    lines.append(
        "| K | dense R | lex R | both | dense-only | **lex rescue** | both-miss | "
        "oracle R | Δ vs dense |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k in RESCUE_KS:
        at = o["at_k"][str(k)]
        lines.append(
            f"| {k} | {at['dense_recall']:.3f} | {at['lex_recall']:.3f} | {at['both_hit']} | "
            f"{at['dense_only']} | **{at['lex_only_rescue']}** | {at['both_miss']} | "
            f"{at['oracle_recall']:.3f} | {at['marginal_gain_vs_dense']:+.3f} |"
        )
    lines.append("")
    lines.append(
        "Oracle = `min(dense_rank, lex_rank)` (union upper bound, perfect fusion). "
        "**Δ vs dense** = oracle − dense recall — ceiling of hybrid gain from this BM25."
    )
    lines.append("")
    depth = o.get("lex_hit_depth") or {}
    if depth:
        lines.append("## BM25 hit depth (among R@1000 hits)")
        lines.append("")
        lines.append(
            f"n={depth['n_hit_at_1000']} · mean={depth['mean_rank']:.1f} · "
            f"p50={depth['p50']:.0f} · p90={depth['p90']:.0f} · p95={depth['p95']:.0f}"
        )
        lines.append("")
        lines.append(
            f"| ≤20 | ≤50 | ≤100 | >100 |"
        )
        lines.append("|---:|---:|---:|---:|")
        lines.append(
            f"| {depth['frac_rank_le_20']:.3f} | {depth['frac_rank_le_50']:.3f} | "
            f"{depth['frac_rank_le_100']:.3f} | {depth['frac_rank_gt_100']:.3f} |"
        )
        lines.append("")
        lines.append(
            "High share of ranks >100 with R@1000 still high ⇒ precision / ranking problem, not coverage."
        )
        lines.append("")

    lines.append("## Rescue @100 by family")
    lines.append("")
    lines.append(
        "| Family | n | dense R@100 | lex R@100 | rescue | dense-only | both-miss | oracle | Δ |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in report["slices"]["family_at_100"]:
        lines.append(
            f"| {md_escape(row['query_variant_family'])} | {row['n']} | {row['dense_recall']:.3f} | "
            f"{row['lex_recall']:.3f} | **{row['lex_only_rescue']}** | {row['dense_only']} | "
            f"{row['both_miss']} | {row['oracle_recall']:.3f} | {row['marginal_gain_vs_dense']:+.3f} |"
        )
    lines.append("")
    lines.append("## Rescue @100 by stratum")
    lines.append("")
    lines.append(
        "| Stratum | n | dense R@100 | lex R@100 | rescue | dense-only | both-miss | oracle | Δ |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in report["slices"]["stratum_at_100"]:
        lines.append(
            f"| {md_escape(row['primary_sampling_stratum'])} | {row['n']} | {row['dense_recall']:.3f} | "
            f"{row['lex_recall']:.3f} | **{row['lex_only_rescue']}** | {row['dense_only']} | "
            f"{row['both_miss']} | {row['oracle_recall']:.3f} | {row['marginal_gain_vs_dense']:+.3f} |"
        )
    lines.append("")
    lines.append("## Rescue @100 by operator (top by rescue count)")
    lines.append("")
    lines.append("| Operator | n | rescue @100 | dense-only | both-miss | Δ |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    ops = sorted(
        report["slices"]["operator_at_100"],
        key=lambda r: (-r["lex_only_rescue"], -r["n"], r["variant_operator"]),
    )[:25]
    for row in ops:
        if row["lex_only_rescue"] == 0 and row["n"] < 10:
            continue
        lines.append(
            f"| {md_escape(row['variant_operator'])} | {row['n']} | **{row['lex_only_rescue']}** | "
            f"{row['dense_only']} | {row['both_miss']} | {row['marginal_gain_vs_dense']:+.3f} |"
        )
    lines.append("")
    lines.append("## Implications for Round L1 / L2")
    lines.append("")
    for bullet in report["verdict"]["next_steps"]:
        lines.append(f"- {bullet}")
    lines.append("")
    lines.append(
        "Hardness tier: chưa có SoT versioned trong gold — slice theo family/stratum/operator only."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def build_verdict(report: dict[str, Any]) -> dict[str, Any]:
    o = report["overlap"]["overall"]
    at100 = o["at_k"]["100"]
    at1000 = o["at_k"]["1000"]
    fam = report["slices"]["family_at_100"]
    strata = report["slices"]["stratum_at_100"]
    ops = report["slices"]["operator_at_100"]
    top_fam = sorted(fam, key=lambda r: (-r["lex_only_rescue"], -r["n"]))[:3]
    top_str = sorted(strata, key=lambda r: (-r["lex_only_rescue"], -r["n"]))[:3]
    top_ops = [
        r
        for r in sorted(ops, key=lambda r: (-r["lex_only_rescue"], -r["n"]))
        if r["lex_only_rescue"] > 0
    ][:5]
    depth = o.get("lex_hit_depth") or {}
    deep = depth.get("frac_rank_gt_100")
    bullets = [
        (
            f"Lexical rescue @100: **{at100['lex_only_rescue']}** / {report['n_variants']} queries "
            f"(oracle Δ vs dense = {at100['marginal_gain_vs_dense']:+.3f})."
        ),
        (
            f"Lexical rescue @1000: **{at1000['lex_only_rescue']}** "
            f"(Δ = {at1000['marginal_gain_vs_dense']:+.3f}) — ceiling hybrid từ BM25 hiện tại."
        ),
    ]
    if deep is not None:
        bullets.append(
            f"Trong các hit BM25@1000, **{deep:.1%}** có rank >100 "
            f"(p50={float(depth.get('p50') or 0):.0f}, p95={float(depth.get('p95') or 0):.0f}) "
            f"→ ưu tiên kéo rank lên top, không phải R@1000."
        )
    if top_fam:
        fam_s = ", ".join(f"{r['query_variant_family']}({r['lex_only_rescue']})" for r in top_fam)
        bullets.append(f"Rescue @100 tập trung family: {fam_s}.")
    if top_str:
        str_s = ", ".join(f"{r['primary_sampling_stratum']}({r['lex_only_rescue']})" for r in top_str)
        bullets.append(f"Rescue @100 tập trung stratum: {str_s}.")
    if top_ops:
        op_s = ", ".join(f"{r['variant_operator']}({r['lex_only_rescue']})" for r in top_ops)
        bullets.append(f"Rescue @100 tập trung operator: {op_s}.")

    next_steps = [
        "Round L1: field boost / exact phrase / address+code analyzers nhằm ↓K@95 và ↑R@50/R@100; giữ R@1000 ≥ baseline.",
        "Bảo toàn ORTHO (đặc biệt strip_diacritics / fold) + brand/street/housenumber/code — nơi lexical bổ sung dense.",
        "Không đầu tư synonym/fuzzy nặng cho ALIAS/TYPO/PHONO — dense đã mạnh; đo lại rescue sau mỗi thay đổi analyzer.",
        "Round L2: chọn analyzer winner bằng hybrid (RRF) gain, không bằng BM25 standalone.",
    ]
    return {"bullets": bullets, "next_steps": next_steps}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    ap.add_argument("--dense-run", type=str, default="run_dense_me5_exact.jsonl")
    ap.add_argument("--lex-run", type=str, default="run_lexical_bm25.jsonl")
    ap.add_argument("--queries", type=Path, default=GOLD / "query_variants_v1.csv")
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    dense_path = args.runs_dir / args.dense_run
    lex_path = args.runs_dir / args.lex_run
    if not dense_path.exists():
        raise SystemExit(f"missing dense run: {dense_path}")
    if not lex_path.exists():
        raise SystemExit(f"missing lex run: {lex_path}")

    sessions = pd.read_csv(args.queries)
    meta = {str(r.variant_id): r._asdict() for r in sessions.itertuples(index=False)}

    dense_ranks = load_best_ranks(dense_path, meta)
    lex_ranks = load_best_ranks(lex_path, meta)
    common = sorted(set(dense_ranks) & set(lex_ranks) & set(meta))
    if len(common) < len(meta):
        print(f"warn: joined {len(common)}/{len(meta)} variants")

    rows: list[dict[str, Any]] = []
    for vid in common:
        m = meta[vid]
        d = dense_ranks[vid]
        lx = lex_ranks[vid]
        rows.append(
            {
                "variant_id": vid,
                "case_id": str(m.get("case_id")),
                "query_variant_family": str(m.get("query_variant_family")),
                "primary_sampling_stratum": str(m.get("primary_sampling_stratum")),
                "variant_operator": str(m.get("variant_operator")),
                "dense": d,
                "lex": lx,
                "oracle": min(d, lx),
            }
        )

    report: dict[str, Any] = {
        "protocol": "gold_stage1_v1_lexical_rescue_diagnostic",
        "dataset": "gold_stage1_v1",
        "depth": DEPTH,
        "n_variants": len(rows),
        "dense_profile": "dense_me5_exact",
        "lex_profile": "lexical_bm25",
        "dense_run": str(dense_path.as_posix()),
        "lex_run": str(lex_path.as_posix()),
        "standalone": {
            "dense_me5": standalone_metrics([r["dense"] for r in rows]),
            "lexical_bm25": standalone_metrics([r["lex"] for r in rows]),
            "oracle_union": standalone_metrics([r["oracle"] for r in rows]),
        },
        "overlap": {"overall": summarize_bucket(rows)},
        "slices": {
            "family_at_100": slice_counts(rows, "query_variant_family", 100),
            "family_at_1000": slice_counts(rows, "query_variant_family", 1000),
            "stratum_at_100": slice_counts(rows, "primary_sampling_stratum", 100),
            "stratum_at_1000": slice_counts(rows, "primary_sampling_stratum", 1000),
            "operator_at_100": slice_counts(rows, "variant_operator", 100),
        },
        "note": (
            "Oracle union is an upper bound on hybrid recall if fusion never hurts. "
            "Production hybrid (RRF) may gain less; choose lexical variants by measured hybrid gain."
        ),
    }
    report["verdict"] = build_verdict(report)

    # compact rescue example lists for follow-up analyzer design
    examples: dict[str, list] = {"rescue_at_100": [], "dense_only_at_100": [], "deep_lex_hit": []}
    for r in rows:
        if not hit(r["dense"], 100) and hit(r["lex"], 100):
            examples["rescue_at_100"].append(
                {
                    "variant_id": r["variant_id"],
                    "family": r["query_variant_family"],
                    "stratum": r["primary_sampling_stratum"],
                    "operator": r["variant_operator"],
                    "dense_rank": r["dense"],
                    "lex_rank": r["lex"],
                }
            )
        if hit(r["dense"], 100) and not hit(r["lex"], 100):
            examples["dense_only_at_100"].append(
                {
                    "variant_id": r["variant_id"],
                    "family": r["query_variant_family"],
                    "stratum": r["primary_sampling_stratum"],
                    "operator": r["variant_operator"],
                    "dense_rank": r["dense"],
                    "lex_rank": r["lex"],
                }
            )
        if hit(r["lex"], DEPTH) and r["lex"] > 100:
            examples["deep_lex_hit"].append(
                {
                    "variant_id": r["variant_id"],
                    "family": r["query_variant_family"],
                    "stratum": r["primary_sampling_stratum"],
                    "operator": r["variant_operator"],
                    "lex_rank": r["lex"],
                    "dense_rank": r["dense"],
                }
            )
    for key in examples:
        examples[key] = sorted(examples[key], key=lambda x: x.get("lex_rank", MISS))[:80]
    report["examples"] = examples

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "lexical_rescue_report.json"
    md_path = args.out_dir / "LEXICAL_RESCUE_DIAGNOSTIC.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    # also publish under w1 evidence if present
    evidence = ROOT / "artifacts" / "results" / "diagnostic_reports" / "08_LEXICAL_RESCUE_DIAGNOSTIC.md"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(render_markdown(report), encoding="utf-8")

    at = report["overlap"]["overall"]["at_k"]
    print(
        f"n={len(rows)} rescue@100={at['100']['lex_only_rescue']} "
        f"rescue@1000={at['1000']['lex_only_rescue']} "
        f"oracle_delta@100={at['100']['marginal_gain_vs_dense']:+.3f} "
        f"oracle_delta@1000={at['1000']['marginal_gain_vs_dense']:+.3f}"
    )
    print("wrote", json_path)
    print("wrote", md_path)
    print("wrote", evidence)


if __name__ == "__main__":
    main()
