"""Frozen Gold v2 replay against the current Docker lexical and hybrid paths.

Full-query: all 800 sessions. Optional raw prefix diagnostic: all q01 grapheme
checkpoints for a selected number of cases. Prefix metrics do not claim
entity-ready intent accuracy because Gold v2 has no checkpoint-state labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
API_CODE = ROOT / "apps/poi-search/api"
sys.path.insert(0, str(API_CODE))
from lexical import lexical_body  # noqa: E402

GOLD = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2"
OUT = ROOT / "artifacts/results/gold_stage1_v2_docker_baseline"
CORPUS_VERSION = "vn-poi-core-v3-semantic-address-dedup50"
INDEX = "vn-poi-core-v3-me5-small"
KS = (1, 5, 10, 20, 50)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def request_json(url: str, payload: dict | None = None, timeout: int = 120) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def lexical_rankings(es_url: str, queries: list[str], batch_size: int = 30) -> list[list[str]]:
    result: list[list[str]] = []
    for start in range(0, len(queries), batch_size):
        lines = []
        for query in queries[start:start + batch_size]:
            lines.append(json.dumps({"index": INDEX}, ensure_ascii=False))
            lines.append(json.dumps(lexical_body(query, 50), ensure_ascii=False))
        req = urllib.request.Request(
            f"{es_url}/_msearch", data=("\n".join(lines) + "\n").encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as response:
            body = json.load(response)
        for item in body["responses"]:
            if "error" in item:
                raise RuntimeError(f"Elasticsearch msearch failed: {item['error']}")
            result.append([str(hit["_id"]) for hit in item["hits"]["hits"]])
        if (start // batch_size) % 10 == 0 or start + batch_size >= len(queries):
            print(f"lexical {min(start + batch_size, len(queries))}/{len(queries)}", flush=True)
    if len(result) != len(queries):
        raise RuntimeError("Lexical result count mismatch")
    return result


def hybrid_rankings(api_url: str, queries: list[str], workers: int = 4) -> list[list[str]]:
    session = request_json(f"{api_url}/v1/sessions", {})["session_id"]
    result: list[list[str] | None] = [None] * len(queries)

    def one(i: int, query: str) -> tuple[int, list[str]]:
        response = request_json(f"{api_url}/v1/suggest", {
            "request_id": f"gold-v2-baseline-{i}",
            "session_id": session,
            "context_revision": 1,
            "query": query,
            "top_k": 50,
            "expected_corpus_version": CORPUS_VERSION,
        })
        if response.get("versions", {}).get("corpus_version") != CORPUS_VERSION:
            raise RuntimeError(f"Wrong API corpus at query {i}")
        return i, [str(item["poi_id"]) for item in response["results"]]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, i, query) for i, query in enumerate(queries)]
        for done, future in enumerate(as_completed(futures), 1):
            i, ids = future.result()
            result[i] = ids
            if done % 100 == 0 or done == len(queries):
                print(f"hybrid {done}/{len(queries)}", flush=True)
    if any(ids is None for ids in result):
        raise RuntimeError("Hybrid result count mismatch")
    return [ids for ids in result if ids is not None]


def rank(ids: list[str], accepted: set[str]) -> int | None:
    return next((i for i, poi_id in enumerate(ids, 1) if poi_id in accepted), None)


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    return {
        "n": n,
        **{f"Hit@{k}": sum(r is not None and r <= k for r in ranks) / n for k in KS},
        "MRR@10": sum(1 / r for r in ranks if r is not None and r <= 10) / n,
        "miss@50": sum(r is None or r > 50 for r in ranks),
    }


def graphemes(value: str) -> list[str]:
    result: list[str] = []
    for char in unicodedata.normalize("NFC", value):
        if result and unicodedata.combining(char):
            result[-1] += char
        else:
            result.append(char)
    return result


def prefix_summary(rows: list[dict], rankings: list[list[str]]) -> dict:
    by_case: dict[str, list[tuple[int, int | None]]] = {}
    for row, ids in zip(rows, rankings, strict=True):
        by_case.setdefault(row["case_id"], []).append(
            (row["checkpoint_index"], rank(ids, set(row["acceptable_poi_ids"])))
        )
    result: dict = {"cases": len(by_case), "checkpoints": len(rows), "k": {}}
    for k in (5, 10, 50):
        first_hits: list[int] = []
        stable_hits: list[int] = []
        aucs: list[float] = []
        for items in by_case.values():
            items.sort()
            hits = [r is not None and r <= k for _, r in items]
            positions = [n for n, _ in items]
            first = next((positions[i] for i, hit in enumerate(hits) if hit), None)
            stable = next((positions[i] for i in range(len(hits) - 2)
                           if all(hits[i:i + 3])
                           and positions[i + 2] == positions[i] + 2), None)
            if first is not None:
                first_hits.append(first)
            if stable is not None:
                stable_hits.append(stable)
            aucs.append(sum(hits) / len(hits))
        n = len(by_case)
        result["k"][str(k)] = {
            "FHC_found_rate": len(first_hits) / n,
            "FHC_median_conditional": float(pd.Series(first_hits).median()) if first_hits else None,
            "SHC_w3_found_rate": len(stable_hits) / n,
            "SHC_w3_median_conditional": float(pd.Series(stable_hits).median()) if stable_hits else None,
            "PrefixAUC_mean": sum(aucs) / n,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--es-url", default="http://127.0.0.1:9200")
    parser.add_argument("--prefix-cases", type=int, default=0)
    parser.add_argument("--prefix-hybrid", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    began = time.perf_counter()
    status = request_json(f"{args.api_url}/v1/status")
    health = request_json(f"{args.api_url}/health")
    if not status.get("ready") or status.get("coverage_id") != CORPUS_VERSION:
        raise SystemExit("API is not ready on Gold-compatible corpus v3")
    if health.get("index") != INDEX or health.get("corpus_rows") != 179209:
        raise SystemExit("API index/count mismatch")
    sessions = pd.read_parquet(GOLD / "query_sessions_v2.parquet")
    qrels = pd.read_parquet(GOLD / "qrels_v2.parquet")
    positive = {r.qrel_set_id: {x.target_id for x in qrels.itertuples()
                                 if x.qrel_set_id == r.qrel_set_id and x.label == "positive"}
                for r in qrels.itertuples()}
    accepted = [set(ids) for ids in sessions["acceptable_poi_ids"]]
    for row, ids in zip(sessions.itertuples(), accepted, strict=True):
        if ids != positive[row.qrel_set_id]:
            raise SystemExit(f"Qrel/session mismatch: {row.query_id}")
    queries = sessions["query_text"].astype(str).tolist()
    print(f"full-query rows={len(queries)}", flush=True)
    lexical = lexical_rankings(args.es_url, queries)
    hybrid = hybrid_rankings(args.api_url, queries, args.workers)
    scores = sessions[["case_id", "query_id", "query_role", "difficulty",
                       "query_text", "intended_poi_id", "primary_sampling_stratum"]].copy()
    scores["rank_lexical_raw"] = [rank(ids, a) or 51 for ids, a in zip(lexical, accepted, strict=True)]
    scores["rank_hybrid_api"] = [rank(ids, a) or 51 for ids, a in zip(hybrid, accepted, strict=True)]
    scores["top5_lexical_raw"] = [json.dumps(ids[:5], ensure_ascii=False) for ids in lexical]
    scores["top5_hybrid_api"] = [json.dumps(ids[:5], ensure_ascii=False) for ids in hybrid]
    report = {
        "protocol": "gold_stage1_v2_docker_baseline_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "warning": "First replay of locked Gold; no model-guided relabeling permitted. Lexical raw vs hybrid final policy are not identical ranking stages.",
        "corpus_version": CORPUS_VERSION,
        "index": INDEX,
        "index_count": health["corpus_rows"],
        "gold_manifest_sha256": sha256(GOLD / "manifest.json"),
        "query_sessions_sha256": sha256(GOLD / "query_sessions_v2.parquet"),
        "policy_sha256": sha256(API_CODE / "search_policy.json"),
        "profiles": {},
    }
    for profile, column in (("lexical_raw", "rank_lexical_raw"),
                            ("hybrid_api", "rank_hybrid_api")):
        report["profiles"][profile] = {
            "overall": metrics(scores[column].tolist()),
            "by_role": {role: metrics(part[column].tolist())
                        for role, part in scores.groupby("query_role", sort=True)},
            "by_stratum": {group: metrics(part[column].tolist())
                           for group, part in scores.groupby("primary_sampling_stratum", sort=True)},
        }
    if args.prefix_cases:
        selected = sessions[sessions.query_role == "q01"].head(args.prefix_cases)
        prefix_rows = []
        for row in selected.itertuples():
            chars = graphemes(row.query_text)
            for n in range(1, len(chars) + 1):
                prefix = "".join(chars[:n])
                if prefix.strip():
                    prefix_rows.append({"case_id": row.case_id, "query_id": row.query_id,
                                        "checkpoint_index": n, "prefix_text": prefix,
                                        "acceptable_poi_ids": list(row.acceptable_poi_ids)})
        prefix_queries = [row["prefix_text"] for row in prefix_rows]
        print(f"q01 prefix cases={len(selected)} checkpoints={len(prefix_rows)}", flush=True)
        prefix_lexical = lexical_rankings(args.es_url, prefix_queries)
        report["prefix_diagnostic"] = {
            "warning": "Raw target-hit trajectories only; no pre_identity/group_ready/entity_ready labels in Gold v2.",
            "lexical_raw": prefix_summary(prefix_rows, prefix_lexical),
        }
        if args.prefix_hybrid:
            prefix_hybrid = hybrid_rankings(args.api_url, prefix_queries, args.workers)
            report["prefix_diagnostic"]["hybrid_api"] = prefix_summary(prefix_rows, prefix_hybrid)
    report["elapsed_seconds"] = round(time.perf_counter() - began, 2)
    OUT.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(OUT / "per_query_results.parquet", index=False)
    scores.to_csv(OUT / "per_query_results.csv", index=False, encoding="utf-8-sig")
    (OUT / "baseline_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"elapsed_seconds": report["elapsed_seconds"],
                      "profiles": {p: v["overall"] for p, v in report["profiles"].items()},
                      "prefix_diagnostic": report.get("prefix_diagnostic")}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
