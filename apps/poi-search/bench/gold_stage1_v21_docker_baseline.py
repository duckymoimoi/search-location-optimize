"""Replay locked Gold v2.1 against the current corpus-v3 Docker search paths.

Gold artifacts are read-only. Results are written outside the release folder.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

import gold_stage1_v2_docker_baseline as common

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1"
OUT = ROOT / "artifacts/results/gold_stage1_v21_docker_baseline"


def prefix_metrics(rows: list[dict], rankings: list[list[str]]) -> dict:
    raw = common.prefix_summary(rows, rankings)
    ready_rows = []
    ready_rankings = []
    for row, ids in zip(rows, rankings, strict=True):
        if row["checkpoint_index"] >= row["entity_ready_grapheme"]:
            ready_rows.append(row)
            ready_rankings.append(ids)
    ready = common.prefix_summary(ready_rows, ready_rankings)
    eligible_w3 = sum(
        len([row for row in ready_rows if row["case_id"] == case_id]) >= 3
        for case_id in {row["case_id"] for row in rows}
    )
    for values in ready["k"].values():
        values["SHC_w3_eligible_cases"] = eligible_w3
        values["SHC_w3_found_rate_eligible"] = (
            values["SHC_w3_found_rate"] * ready["cases"] / eligible_w3
            if eligible_w3 else None
        )
    return {
        "raw": raw,
        "entity_ready": ready,
        "entity_ready_checkpoints": len(ready_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--es-url", default="http://127.0.0.1:9200")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prefix-hybrid", action="store_true")
    args = parser.parse_args()
    began = time.perf_counter()

    lock = json.loads((GOLD / "LOCKED.json").read_text(encoding="utf-8"))
    if lock["status"] != "locked":
        raise SystemExit("Gold v2.1 is not locked")
    if common.sha256(GOLD / "manifest.json") != lock["manifest_sha256"]:
        raise SystemExit("Gold v2.1 manifest hash mismatch")
    status = common.request_json(f"{args.api_url}/v1/status")
    health = common.request_json(f"{args.api_url}/health")
    if not status.get("ready") or status.get("coverage_id") != common.CORPUS_VERSION:
        raise SystemExit("API is not ready on corpus v3")
    if health.get("index") != common.INDEX or health.get("corpus_rows") != 179209:
        raise SystemExit("API index/count mismatch")

    sessions = pd.read_parquet(GOLD / "query_sessions_v2_1.parquet")
    qrels = pd.read_parquet(GOLD / "qrels_v2_1.parquet")
    positive: dict[str, set[str]] = {}
    for row in qrels.itertuples():
        if row.label == "positive":
            positive.setdefault(row.qrel_set_id, set()).add(row.target_id)
    accepted = [set(ids) for ids in sessions["acceptable_poi_ids"]]
    for row, ids in zip(sessions.itertuples(), accepted, strict=True):
        if ids != positive.get(row.qrel_set_id, set()):
            raise SystemExit(f"Qrel/session mismatch: {row.query_id}")
    if len(sessions) != 800:
        raise SystemExit(f"Wrong Gold session count: {len(sessions)}")

    queries = sessions["query_text"].astype(str).tolist()
    print(f"full-query rows={len(queries)}", flush=True)
    lexical = common.lexical_rankings(args.es_url, queries)
    hybrid = common.hybrid_rankings(args.api_url, queries, args.workers)
    scores = sessions[["case_id", "query_id", "query_role", "difficulty",
                       "query_text", "intended_poi_id", "primary_sampling_stratum"]].copy()
    scores["rank_lexical_raw"] = [common.rank(ids, a) or 51 for ids, a in zip(lexical, accepted, strict=True)]
    scores["rank_hybrid_api"] = [common.rank(ids, a) or 51 for ids, a in zip(hybrid, accepted, strict=True)]
    scores["top5_lexical_raw"] = [json.dumps(ids[:5], ensure_ascii=False) for ids in lexical]
    scores["top5_hybrid_api"] = [json.dumps(ids[:5], ensure_ascii=False) for ids in hybrid]

    report = {
        "protocol": "gold_stage1_v21_docker_baseline_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "warning": "First replay after lock; do not relabel Gold from model results. Lexical raw and hybrid API are different ranking stages.",
        "corpus_version": common.CORPUS_VERSION,
        "index": common.INDEX,
        "index_count": health["corpus_rows"],
        "api_versions": status["versions"],
        "gold_manifest_sha256": common.sha256(GOLD / "manifest.json"),
        "query_sessions_sha256": common.sha256(GOLD / "query_sessions_v2_1.parquet"),
        "policy_sha256": common.sha256(common.API_CODE / "search_policy.json"),
        "profiles": {},
    }
    for profile, column in (("lexical_raw", "rank_lexical_raw"),
                            ("hybrid_api", "rank_hybrid_api")):
        report["profiles"][profile] = {
            "overall": common.metrics(scores[column].tolist()),
            "by_role": {role: common.metrics(part[column].tolist())
                        for role, part in scores.groupby("query_role", sort=True)},
            "by_stratum": {group: common.metrics(part[column].tolist())
                           for group, part in scores.groupby("primary_sampling_stratum", sort=True)},
            "by_difficulty": {group: common.metrics(part[column].tolist())
                              for group, part in scores.groupby("difficulty", sort=True)},
        }

    evidence = {}
    for line in (GOLD / "prefix_evidence_v2_1.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        evidence[item["query_id"]] = item
    prefix_rows = []
    for row in sessions[sessions.query_role == "q01"].itertuples():
        boundary = evidence[row.query_id]["entity_ready_grapheme"]
        chars = common.graphemes(row.query_text)
        if not 1 <= boundary <= len(chars):
            raise SystemExit(f"Invalid entity_ready boundary: {row.query_id}")
        for n in range(1, len(chars) + 1):
            prefix = "".join(chars[:n])
            if prefix.strip():
                prefix_rows.append({"case_id": row.case_id, "query_id": row.query_id,
                                    "checkpoint_index": n, "prefix_text": prefix,
                                    "entity_ready_grapheme": boundary,
                                    "acceptable_poi_ids": list(row.acceptable_poi_ids)})
    if len(evidence) != 200:
        raise SystemExit(f"Wrong prefix evidence count: {len(evidence)}")
    prefix_queries = [row["prefix_text"] for row in prefix_rows]
    print(f"q01 prefix cases=200 checkpoints={len(prefix_rows)}", flush=True)
    prefix_lexical = common.lexical_rankings(args.es_url, prefix_queries)
    report["prefix_diagnostic"] = {
        "lexical_raw": prefix_metrics(prefix_rows, prefix_lexical),
        "hybrid_api": None,
    }
    if args.prefix_hybrid:
        prefix_hybrid = common.hybrid_rankings(args.api_url, prefix_queries, args.workers)
        report["prefix_diagnostic"]["hybrid_api"] = prefix_metrics(prefix_rows, prefix_hybrid)

    report["elapsed_seconds"] = round(time.perf_counter() - began, 2)
    OUT.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(OUT / "per_query_results.parquet", index=False)
    scores.to_csv(OUT / "per_query_results.csv", index=False, encoding="utf-8-sig")
    (OUT / "baseline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"elapsed_seconds": report["elapsed_seconds"],
                      "profiles": {p: v["overall"] for p, v in report["profiles"].items()},
                      "prefix_diagnostic": report["prefix_diagnostic"]},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
