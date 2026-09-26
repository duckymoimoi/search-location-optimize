"""Classify locked Gold v2.1 misses from the existing baseline, without relabeling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from stage1_brand_v3_common import GOLD_POI, load_v3_core, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "artifacts/results/gold_stage1_v21_docker_baseline"


def classify(scores: pd.DataFrame, v3_ids: set[str]) -> dict:
    rows = []
    counts = {"target_absent": 0, "candidate_miss": 0, "rank_miss": 0, "hit20": 0}
    for row in scores.itertuples(index=False):
        intended = str(row.intended_poi_id)
        rank = int(row.rank_hybrid_api)
        if intended not in v3_ids:
            kind = "target_absent"
        elif rank > 50:
            kind = "candidate_miss"
        elif rank > 20:
            kind = "rank_miss"
        else:
            kind = "hit20"
        counts[kind] += 1
        if kind != "hit20":
            rows.append(
                {
                    "query_id": str(row.query_id),
                    "query_role": str(row.query_role),
                    "stratum": str(row.primary_sampling_stratum),
                    "intended_poi_id": intended,
                    "rank_hybrid_api": rank,
                    "rank_lexical_raw": int(row.rank_lexical_raw),
                    "miss_class": kind,
                }
            )
    return {"counts": counts, "n": int(len(scores)), "misses": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, default=BASELINE / "per_query_results.csv")
    parser.add_argument("--output", type=Path, default=BASELINE / "miss_taxonomy.json")
    args = parser.parse_args()
    scores = pd.read_csv(args.scores)
    v3_ids = set(load_v3_core()["poi_id"].astype(str))
    report = {
        "protocol": "gold_stage1_v21_miss_taxonomy_v1",
        "warning": "Derived from locked baseline only. Do not relabel Gold.",
        "gold_manifest_sha256": sha256_file(GOLD_POI / "manifest.json"),
        "scores_sha256": sha256_file(args.scores),
        **classify(scores, v3_ids),
    }
    write_json(args.output, report)
    print(json.dumps({"counts": report["counts"], "n": report["n"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
