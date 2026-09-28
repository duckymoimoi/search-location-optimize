#!/usr/bin/env python3
"""Slice a Stage-1 exact-dense Gold jsonl by role and stratum.

Reads run_*_gold.jsonl written by the hardneg kernel. Does not change Gold.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/query_sessions_v2_1.parquet"
KS = (1, 20, 50)


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    frame = pd.DataFrame(rows)
    frame["best_rank"] = pd.to_numeric(frame["best_rank"], errors="coerce")
    return frame


def metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    ranks = frame["best_rank"]
    n = int(len(frame))
    out: dict[str, float | int] = {"n": n}
    if n == 0:
        return out
    for k in KS:
        out[f"Hit@{k}"] = float((ranks <= k).sum() / n)
    mrr = ranks.map(lambda rank: (1.0 / rank) if pd.notna(rank) and rank <= 10 else 0.0)
    out["MRR@10"] = float(mrr.sum() / n)
    out["miss@50"] = int((ranks.isna() | (ranks > 50)).sum())
    out["rank_miss_21_50"] = int(((ranks >= 21) & (ranks <= 50)).sum())
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=None)
    args = parser.parse_args()
    frame = load_jsonl(args.jsonl)
    sessions = pd.read_parquet(GOLD, columns=["query_id", "query_role", "primary_sampling_stratum"])
    sessions = sessions.rename(columns={"query_id": "variant_id"})
    frame = frame.merge(sessions, on="variant_id", how="left", suffixes=("", "_gold"))
    if "query_role" not in frame.columns:
        raise SystemExit("Gold sessions did not attach query_role")
    report = {
        "jsonl": str(args.jsonl),
        "overall": metrics(frame),
        "by_role": {role: metrics(part) for role, part in frame.groupby("query_role")},
        "by_stratum": {stratum: metrics(part) for stratum, part in frame.groupby("primary_sampling_stratum")},
    }
    if args.baseline is not None:
        base = load_jsonl(args.baseline)[["variant_id", "best_rank"]].rename(columns={"best_rank": "base_rank"})
        joined = frame.merge(base, on="variant_id", how="left")
        lost = joined.loc[(joined["base_rank"] == 1) & (joined["best_rank"].isna() | (joined["best_rank"] > 1))]
        miss20 = joined.loc[(joined["query_role"] == "q03") & (joined["best_rank"].isna() | (joined["best_rank"] > 20))]
        report["lost_rank1"] = int(len(lost))
        report["q03_miss20"] = int(len(miss20))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
