#!/usr/bin/env python3
"""Aggregate gold_stage1 Round-1 selection report from Kaggle run jsonl files."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
OUT = Path(__file__).resolve().parent / "results" / "gold_stage1_selection"

RECALL_KS = (100, 500, 1000)
DIAG_KS = (1, 5, 10, 50)
DEPTH = 1000


def parse_acceptable(raw) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(x) for x in list(raw)]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x for x in s.split("|") if x]


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


def summarize_ranks(rows: list[dict], label: str) -> dict:
    ranks = [r["best_rank"] for r in rows]
    n = len(ranks)
    out: dict = {"n": n, "label": label, "recall": {}, "diagnostic": {}, "k_at_r": {}}
    for k in RECALL_KS:
        out["recall"][f"Recall@{k}"] = sum(1 for r in ranks if r <= k) / n if n else 0.0
    for k in DIAG_KS:
        out["diagnostic"][f"SR@{k}"] = sum(1 for r in ranks if r <= k) / n if n else 0.0
    out["diagnostic"]["MRR@10"] = sum(1.0 / r for r in ranks if r <= 10) / n if n else 0.0
    out["k_at_r"]["K@95"] = k_at_recall(ranks, 0.95)
    out["k_at_r"]["K@98"] = k_at_recall(ranks, 0.98)
    return out


def load_run(path: Path, meta: dict[str, dict]) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            vid = str(row.get("variant_id") or "")
            m = meta.get(vid)
            if "best_rank" in row and row["best_rank"] is not None:
                br = int(row["best_rank"])
            else:
                acceptable = set(parse_acceptable(row.get("acceptable_poi_ids")))
                if not acceptable and m is not None:
                    acceptable = set(parse_acceptable(m.get("acceptable_poi_ids")))
                if not acceptable:
                    acceptable = {str(row.get("intended_poi_id") or (m or {}).get("intended_poi_id"))}
                br = DEPTH + 1
                for i, pid in enumerate(row.get("top_ids") or [], start=1):
                    if str(pid) in acceptable:
                        br = i
                        break
                if br > DEPTH:
                    r = row.get("rank")
                    if r is not None and not (isinstance(r, float) and np.isnan(r)):
                        br = int(r) if int(r) <= DEPTH else DEPTH + 1
            rows.append(
                {
                    "variant_id": vid,
                    "case_id": str(row.get("case_id") or (m or {}).get("case_id")),
                    "query_variant_family": str(
                        row.get("query_variant_family") or (m or {}).get("query_variant_family")
                    ),
                    "primary_sampling_stratum": str(
                        row.get("primary_sampling_stratum")
                        or (m or {}).get("primary_sampling_stratum")
                    ),
                    "best_rank": br,
                }
            )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--runs-dir",
        type=Path,
        default=ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1",
    )
    ap.add_argument("--queries", type=Path, default=GOLD / "query_variants_v1.csv")
    args = ap.parse_args()

    sessions = pd.read_csv(args.queries)
    meta = {str(r.variant_id): r._asdict() for r in sessions.itertuples(index=False)}

    report: dict = {
        "depth": DEPTH,
        "protocol": "SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL",
        "dataset": "gold_stage1_v1",
        "bm25_note": "BM25Okapi defaults — untuned lexical floor",
        "profiles": {},
    }

    run_files = sorted(args.runs_dir.glob("run_*.jsonl")) if args.runs_dir.exists() else []
    if not run_files:
        print(f"no run_*.jsonl under {args.runs_dir} — download Kaggle output first")
    for path in run_files:
        name = path.stem.replace("run_", "")
        rows = load_run(path, meta)
        profile = {
            "overall": summarize_ranks(rows, "overall"),
            "by_family": {},
            "by_stratum": {},
        }
        by_f: dict[str, list] = defaultdict(list)
        by_s: dict[str, list] = defaultdict(list)
        for r in rows:
            by_f[r["query_variant_family"]].append(r)
            by_s[r["primary_sampling_stratum"]].append(r)
        for k, items in by_f.items():
            profile["by_family"][k] = summarize_ranks(items, k)
        for k, items in by_s.items():
            profile["by_stratum"][k] = summarize_ranks(items, k)
        report["profiles"][name] = profile
        o = profile["overall"]
        print(
            f"{name}: R@100={o['recall']['Recall@100']:.3f} "
            f"@500={o['recall']['Recall@500']:.3f} @1000={o['recall']['Recall@1000']:.3f} "
            f"K@95={o['k_at_r']['K@95']} K@98={o['k_at_r']['K@98']} "
            f"MRR@10={o['diagnostic']['MRR@10']:.3f}"
        )

    # Prefer Kaggle summary if present
    kaggle_summary = args.runs_dir / "summary.json"
    if kaggle_summary.exists():
        report["kaggle_summary"] = json.loads(kaggle_summary.read_text(encoding="utf-8"))
        gate = args.runs_dir / "gate_table.json"
        if gate.exists():
            report["gate_table"] = json.loads(gate.read_text(encoding="utf-8"))

    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / "stage1_selection_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out_path)


if __name__ == "__main__":
    main()
