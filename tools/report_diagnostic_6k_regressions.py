#!/usr/bin/env python3
"""List rank-1 losses and q03 miss@20 on the diagnostic 6k run.

Reads local jsonl only. Does not change Gold or the checkpoint.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "training" / "kaggle" / "output_stage1_v6_hardneg_6k" / "stage1_v6_hardneg"
GOLD = ROOT / "data" / "vietnam" / "stage1_eval_suite_v2" / "gold_stage1_v2_1" / "query_sessions_v2_1.parquet"
CORE = ROOT / "data" / "vietnam" / "poi_corpus_v3" / "pois_core.parquet"
OUT = ROOT / "artifacts" / "results" / "diagnostic_reports" / "02_DIAGNOSTIC_REGRESSIONS.md"


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    frame = pd.DataFrame(rows)
    frame["best_rank"] = frame["best_rank"].astype("Int64")
    return frame


def rank_text(value) -> str:
    if pd.isna(value):
        return "miss"
    return str(int(value))


def main() -> None:
    zero = load_jsonl(RUN / "run_zero_shot_gold.jsonl")
    epoch2 = load_jsonl(RUN / "run_epoch2_gold.jsonl")
    sessions = pd.read_parquet(
        GOLD,
        columns=["query_id", "query_role", "difficulty", "primary_sampling_stratum", "intended_poi_id", "query_text"],
    )
    sessions = sessions.rename(columns={"query_id": "variant_id"})
    core = pd.read_parquet(CORE, columns=["poi_id", "name", "address_text"])
    names = dict(zip(core["poi_id"].astype(str), core["name"].astype(str)))
    addresses = dict(zip(core["poi_id"].astype(str), core["address_text"].fillna("").astype(str)))

    left = zero[["variant_id", "best_rank", "intended_poi_id", "query_text"]].rename(columns={"best_rank": "zs_rank"})
    right = epoch2[["variant_id", "best_rank"]].rename(columns={"best_rank": "e2_rank"})
    merged = left.merge(right, on="variant_id").merge(sessions, on="variant_id", how="left", suffixes=("", "_gold"))
    lost = merged.loc[(merged["zs_rank"] == 1) & (merged["e2_rank"].isna() | (merged["e2_rank"] > 1))].copy()
    q03_miss = merged.loc[
        (merged["query_role"] == "q03") & (merged["e2_rank"].isna() | (merged["e2_rank"] > 20))
    ].copy()

    def lines_for(frame: pd.DataFrame) -> list[str]:
        out = []
        ordered = frame.sort_values(["query_role", "primary_sampling_stratum", "variant_id"])
        for row in ordered.itertuples(index=False):
            poi = str(row.intended_poi_id)
            out.append(
                f"- `{row.variant_id}` {row.query_role} / {row.primary_sampling_stratum} / {row.difficulty}: "
                f"zs {rank_text(row.zs_rank)} → e2 {rank_text(row.e2_rank)}. "
                f"{row.query_text} → {names.get(poi, poi)} ({addresses.get(poi, '')})"
            )
        return out

    body = [
        "# Diagnostic 6k — rank regressions",
        "",
        "Nguồn: `training/kaggle/output_stage1_v6_hardneg_6k/stage1_v6_hardneg/` "
        "`run_zero_shot_gold.jsonl` và `run_epoch2_gold.jsonl`. "
        "Đây là run Gold-gated `352867030`, không phải checkpoint dev-lock.",
        "",
        f"Query mất rank 1 so với zero-shot: **{len(lost)}**. "
        f"q03 còn ngoài top-20 ở epoch 2: **{len(q03_miss)}**.",
        "",
        "Không sửa Gold và không chọn checkpoint từ danh sách này.",
        "",
        "## Mất rank 1",
        "",
        *lines_for(lost),
        "",
        "## q03 miss@20 ở epoch 2",
        "",
        *lines_for(q03_miss),
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(body), encoding="utf-8")
    print(json.dumps({"lost_rank1": int(len(lost)), "q03_miss20": int(len(q03_miss)), "out": str(OUT)}))


if __name__ == "__main__":
    main()
