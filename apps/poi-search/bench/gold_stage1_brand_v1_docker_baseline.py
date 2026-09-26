"""Replay locked brand Gold against corpus-v3 lexical raw and hybrid API."""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

import gold_stage1_v2_docker_baseline as common

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1"
MEMBERSHIP = ROOT / "data/vietnam/train_stage1_brand_membership_v3/brand_group_members_v3.parquet"
OUT = ROOT / "artifacts/results/gold_stage1_brand_v1_docker_baseline"
KS = (1, 5, 10, 20, 50)


def _ids(value) -> list[str]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [str(item) for item in value]


def any_rank(ids: list[str], accepted: set[str]) -> int | None:
    return next((i for i, poi_id in enumerate(ids, 1) if poi_id in accepted), None)


def coverage(ids: list[str], accepted: set[str], k: int) -> float:
    if not accepted:
        return 0.0
    return len(set(ids[:k]) & accepted) / len(accepted)


def family_mean(values_by_family: dict[str, list[float]]) -> float:
    family_means = [sum(values) / len(values) for values in values_by_family.values() if values]
    return sum(family_means) / len(family_means) if family_means else 0.0


def paired_ci(values_by_family: dict[str, list[float]], n_boot: int = 1000, seed: int = 20260926) -> dict:
    families = [sum(values) / len(values) for values in values_by_family.values() if values]
    if not families:
        return {"mean": 0.0, "low": 0.0, "high": 0.0, "n_families": 0}
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [families[rng.randrange(len(families))] for _ in families]
        boots.append(sum(sample) / len(sample))
    boots.sort()
    return {
        "mean": sum(families) / len(families),
        "low": boots[int(0.025 * (n_boot - 1))],
        "high": boots[int(0.975 * (n_boot - 1))],
        "n_families": len(families),
    }


def size_bucket(n: int) -> str:
    if n <= 4:
        return "xs_1_4"
    if n <= 19:
        return "sm_5_19"
    if n <= 79:
        return "md_20_79"
    return "lg_80p"


def brand_metrics(rows: list[dict], rankings: list[list[str]], sibling: dict[str, set[str]]) -> dict:
    hit_fams: dict[int, dict[str, list[float]]] = {k: defaultdict(list) for k in KS}
    mrr_fams: dict[str, list[float]] = defaultdict(list)
    cov_fams: dict[int, dict[str, list[float]]] = {k: defaultdict(list) for k in KS}
    cov_size: dict[str, list[float]] = defaultdict(list)
    false_branch = 0
    namespace_n = 0
    query_rows = []
    for row, ids in zip(rows, rankings, strict=True):
        accepted = set(row["acceptable_poi_ids"])
        family_id = row["brand_family_id"]
        first = any_rank(ids, accepted)
        for k in KS:
            hit_fams[k][family_id].append(1.0 if first is not None and first <= k else 0.0)
            cov_fams[k][family_id].append(coverage(ids, accepted, k))
        mrr_fams[family_id].append(1.0 / first if first is not None and first <= 10 else 0.0)
        cov_size[size_bucket(len(accepted))].append(coverage(ids, accepted, 20))
        if row["query_role"] == "namespace_qualified":
            namespace_n += 1
            others = sibling.get(row["brand_group_id"], set())
            if any(poi_id in others for poi_id in ids[:20]) and (first is None or first > 20):
                false_branch += 1
        query_rows.append(
            {
                "query_id": row["query_id"],
                "brand_family_id": family_id,
                "query_role": row["query_role"],
                "exposure_class": row.get("exposure_class"),
                "n_acceptable": len(accepted),
                "rank_any_compatible": first or 51,
                "coverage20": coverage(ids, accepted, 20),
            }
        )
    return {
        "n_queries": len(rows),
        "AnyCompatibleHit": {str(k): family_mean(hit_fams[k]) for k in KS},
        "AnyCompatibleHit_query_micro": {
            str(k): sum(value for values in hit_fams[k].values() for value in values) / len(rows)
            for k in KS
        },
        "group_MRR@10": family_mean(mrr_fams),
        "compatible_coverage@20": family_mean(cov_fams[20]),
        "compatible_coverage@20_by_size": {
            key: sum(values) / len(values) for key, values in sorted(cov_size.items())
        },
        "namespace_false_branch@20": (false_branch / namespace_n) if namespace_n else None,
        "family_weighted_ci": {
            "AnyCompatibleHit@20": paired_ci(hit_fams[20]),
            "group_MRR@10": paired_ci(mrr_fams),
        },
        "query_rows": query_rows,
    }


def prefix_group_ready(evidence_rows: list[dict], checkpoints: list[dict], rankings: list[list[str]]) -> dict:
    ready_at = {row["query_id"]: int(row["group_ready_grapheme"]) for row in evidence_rows}
    ready_rows = []
    ready_rankings = []
    for row, ids in zip(checkpoints, rankings, strict=True):
        if int(row["checkpoint_index"]) >= ready_at.get(row["query_id"], 10**9):
            ready_rows.append(row)
            ready_rankings.append(ids)
    raw = common.prefix_summary(checkpoints, rankings)
    ready = common.prefix_summary(ready_rows, ready_rankings) if ready_rows else {}
    return {
        "raw": raw,
        "group_ready": ready,
        "group_ready_checkpoints": len(ready_rows),
        "group_ready_queries": len({row["query_id"] for row in ready_rows}),
    }


def sibling_namespaces(members: pd.DataFrame) -> dict[str, set[str]]:
    accepted = members[members["membership_status"] == "accepted"]
    by_group: dict[str, set[str]] = defaultdict(set)
    by_family: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in accepted.itertuples(index=False):
        by_group[str(row.brand_group_id)].add(str(row.poi_id))
        by_family[str(row.brand_family_id)][str(row.brand_group_id)].add(str(row.poi_id))
    sibling: dict[str, set[str]] = {}
    for family_id, groups in by_family.items():
        all_ids = set().union(*groups.values()) if groups else set()
        for group_id, ids in groups.items():
            sibling[group_id] = all_ids - ids
    return sibling


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
        raise SystemExit("Brand Gold is not locked")
    if common.sha256(GOLD / "manifest.json") != lock["manifest_sha256"]:
        raise SystemExit("Brand Gold manifest hash mismatch")
    status = common.request_json(f"{args.api_url}/v1/status")
    health = common.request_json(f"{args.api_url}/health")
    if not status.get("ready") or status.get("coverage_id") != common.CORPUS_VERSION:
        raise SystemExit("API is not ready on corpus v3")
    if health.get("index") != common.INDEX or health.get("corpus_rows") != 179209:
        raise SystemExit("API index/count mismatch")

    queries = pd.read_parquet(GOLD / "brand_queries_v1.parquet")
    members = pd.read_parquet(MEMBERSHIP)
    rows = []
    for raw in queries.to_dict("records"):
        rows.append(
            {
                **raw,
                "acceptable_poi_ids": _ids(raw["acceptable_poi_ids"]),
                "case_id": str(raw["brand_family_id"]),
            }
        )
    texts = [str(row["query_text"]) for row in rows]
    print(f"brand full-query rows={len(texts)}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    lexical = common.lexical_rankings(args.es_url, texts)
    hybrid = common.hybrid_rankings(args.api_url, texts, args.workers)
    sibling = sibling_namespaces(members)
    report = {
        "protocol": "gold_stage1_brand_v1_docker_baseline_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "warning": "Do not relabel brand Gold from model results. Family-weighted metrics are the headline.",
        "corpus_version": common.CORPUS_VERSION,
        "index": common.INDEX,
        "index_count": health["corpus_rows"],
        "gold_manifest_sha256": common.sha256(GOLD / "manifest.json"),
        "membership_sha256": common.sha256(MEMBERSHIP),
        "profiles": {},
    }
    for name, rankings in (("lexical_raw", lexical), ("hybrid_api", hybrid)):
        metrics = brand_metrics(rows, rankings, sibling)
        scores = metrics.pop("query_rows")
        report["profiles"][name] = metrics
        pd.DataFrame(scores).to_csv(OUT.joinpath(f"per_query_{name}.csv"), index=False, encoding="utf-8-sig")

    evidence = [
        json.loads(line)
        for line in (GOLD / "prefix_evidence_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    checkpoints = [
        json.loads(line)
        for line in (GOLD / "prefix_checkpoints_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in checkpoints:
        row["case_id"] = row["query_id"]
        query = next(item for item in rows if item["query_id"] == row["query_id"])
        row["acceptable_poi_ids"] = query["acceptable_poi_ids"]
    prefix_texts = [row["prefix_text"] for row in checkpoints]
    print(f"brand prefix checkpoints={len(prefix_texts)}", flush=True)
    prefix_lexical = common.lexical_rankings(args.es_url, prefix_texts)
    report["prefix_diagnostic"] = {
        "lexical_raw": prefix_group_ready(evidence, checkpoints, prefix_lexical),
        "hybrid_api": None,
    }
    if args.prefix_hybrid:
        prefix_hybrid = common.hybrid_rankings(args.api_url, prefix_texts, args.workers)
        report["prefix_diagnostic"]["hybrid_api"] = prefix_group_ready(
            evidence, checkpoints, prefix_hybrid
        )
    report["elapsed_seconds"] = round(time.perf_counter() - began, 2)
    (OUT / "baseline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "elapsed_seconds": report["elapsed_seconds"],
                "profiles": {
                    name: {key: value for key, value in profile.items() if key != "query_rows"}
                    for name, profile in report["profiles"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
