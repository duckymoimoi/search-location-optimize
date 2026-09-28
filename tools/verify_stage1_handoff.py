"""Verify frozen Stage-1 evidence and serving parity. Inference only, never trains.

Uses an independent metric implementation and streams the large traces.
Optional live check compares hydration/cap and returned IDs with frozen candidates.
This validates a retrieval handoff, not a trained Stage-2 ranker or production SLA.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
RUNS = ("gated_members_dev_20260928", "cold_entity_v2_gated_20260928")
MODES = ("gated_candidate", "hybrid_raw")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def query_metrics(ids, accepted):
    rank = next((i for i, poi in enumerate(ids, 1) if poi in accepted), None)
    return {**{f"Hit@{k}": float(rank is not None and rank <= k) for k in (1, 5, 10, 20, 100)},
            "MRR@10": 1 / rank if rank is not None and rank <= 10 else 0.0,
            "coverage@20": len(set(ids[:20]) & accepted) / len(accepted)}


def request(base, path, body=None):
    req = urllib.request.Request(base + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def verify(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    snapshot_path = ROOT / "docs/deliveries/w3/handoff/evidence_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    report = {"schema": "stage1-handoff-verification-v1", "status": "running",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "runner_sha256": digest(__file__), "snapshot_sha256": digest(snapshot_path),
              "training": False, "stage2_model_tested": False, "sla_tested": False,
              "hashes_verified": 0, "offline": {}, "failures": []}
    # Verify all locked inputs, not only aggregate JSON summaries.
    for path, expected in snapshot["sources"].items():
        if digest(ROOT / path) != expected["sha256"]:
            raise ValueError(f"Frozen input changed: {path}")
        report["hashes_verified"] += 1
    bundle = snapshot["bundle"]
    for key, path in [("model_sha256", "artifacts/models/me5_6k_devlock_serving/model.safetensors"),
                      ("vectors_sha256", "artifacts/embeddings/me5_small_v3_6k_devlock/corpus_embeddings.npy"),
                      ("ids_sha256", "artifacts/results/dense_first/serving/poi_ids.txt")]:
        if digest(ROOT / path) != bundle[key]:
            raise ValueError(f"Bundle changed: {key}")
        report["hashes_verified"] += 1
    corpus = set((ROOT / "artifacts/results/dense_first/serving/poi_ids.txt").read_text().splitlines())
    assert len(corpus) == 179209
    seen = set()
    samples = defaultdict(list)
    for run in RUNS:
        sums = defaultdict(lambda: defaultdict(list))
        counts = defaultdict(int)
        empty = defaultdict(int)
        source = ROOT / "artifacts/results/dense_first" / run / "queries.jsonl"
        with source.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["normalizer"] != "raw":
                    continue
                key = (row["suite"], row["query_id"])
                if key in seen:
                    raise ValueError(f"Duplicate query: {key}")
                seen.add(key)
                assert row["status"] == "ok", key
                accepted = set(row["accepted_poi_ids"])
                assert accepted and accepted <= corpus, key
                suite = row["suite"] + ":raw"
                counts[suite] += 1
                for mode in MODES:
                    ids = row["stages"][mode]
                    assert len(ids) <= 100 and len(ids) == len(set(ids)), (key, mode)
                    assert set(ids) <= corpus, (key, mode)
                    empty[(suite, mode)] += not ids
                    group = row["group_id"] if row["suite"] == "brand_dev" else row["query_id"]
                    sums[(suite, mode)][group].append(query_metrics(ids, accepted))
                # Keep just handoff fields, not the heavy branch/document trace.
                samples[(suite, row["gated_route"])].append({
                    "suite": row["suite"], "query_id": row["query_id"], "query_text": row["query_text"],
                    "route": row["gated_route"], "stages": {m: row["stages"][m] for m in MODES}})
        for (suite, mode), groups in sums.items():
            metrics = {}
            for metric in next(iter(groups.values()))[0]:
                means = [sum(r[metric] for r in rows) / len(rows) for rows in groups.values()]
                metrics[metric] = sum(means) / len(means)
            expected = snapshot["quality"][run][suite]
            assert counts[suite] == expected["n"], (run, suite)
            for metric, value in metrics.items():
                assert abs(value - expected["modes"][mode][metric]) < 1e-10, (run, suite, mode, metric)
            report["offline"][f"{suite}/{mode}"] = {
                "queries": counts[suite], "empty_pools": empty[(suite, mode)], "metrics": metrics,
                "metric_replay_matches": True, "unique_ids_in_corpus": True, "depth_at_most_100": True}
    report["offline_query_count"] = len(seen)
    if args.api:
        health = request(args.api, "/health")
        assert health["index"] == bundle["index"] and health["corpus_rows"] == len(corpus), health
        assert health["device"] == "cuda", health
        session = request(args.api, "/v1/sessions", {})["session_id"]
        rng = random.Random(42)
        selected = []
        for (suite, _), rows in sorted(samples.items()):
            selected += rows if suite == "brand_dev:raw" else rng.sample(rows, min(args.sample_per_route, len(rows)))
        live = {"api": args.api, "profile": args.profile, "health": health,
                "queries": len(selected), "passed": 0, "failures": [], "route_counts": {}}
        mode = "gated_candidate" if args.profile == "s1-a" else "hybrid_raw"
        with (out / "live_queries.jsonl").open("w", encoding="utf-8") as sink:
            for n, row in enumerate(selected):
                body = {"request_id": f"handoff-{n}", "session_id": session, "context_revision": 1,
                        "query": row["query_text"], "top_k": 10,
                        "expected_corpus_version": "vn-poi-core-v3-semantic-address-dedup50"}
                start = time.perf_counter()
                trace = request(args.api, "/v1/debug/trace_suggest", body)
                result = request(args.api, "/v1/suggest", body)
                expected = row["stages"][mode]
                v = trace["versions"]
                checks = {
                    "profile": trace["profile"] == ("dense_first" if args.profile == "s1-a" else "hybrid"),
                    "raw_ranking": v["ranking_profile"] == "raw",
                    "raw_encoder": v["encoder_normalizer"] == "raw",
                    "ann": v["dense_backend"] == "ann", "name_lookup_off": not v["name_lookup_enabled"],
                    "live_pool_count": trace["candidate_count"] == len(expected),
                    "live_pool_prefix80": trace["stages"]["after_cap"] == expected[:80],
                    "debug_top10": trace["stages"]["final_top_k"] == expected[:10],
                    "serving_top10": [r["poi_id"] for r in result["results"]] == expected[:10],
                }
                if args.profile == "s1-a":
                    checks["brand_flags"] = v["brand_route_mode"] == {"fuzzy": True, "membership": True}
                failed = [k for k, ok in checks.items() if not ok]
                if failed:
                    live["failures"].append({"query_id": row["query_id"], "checks": failed})
                else:
                    live["passed"] += 1
                live["route_counts"][trace["route"]] = live["route_counts"].get(trace["route"], 0) + 1
                sink.write(json.dumps({"query_id": row["query_id"], "checks": checks,
                                       "elapsed_ms_two_requests": (time.perf_counter()-start)*1000,
                                       "versions": v}, ensure_ascii=False) + "\n")
                if (n+1) % 40 == 0:
                    print("Live parity", n+1, "failures", len(live["failures"]), flush=True)
        report["live"] = live
        report["failures"] += live["failures"]
    report["status"] = "pass" if not report["failures"] else "fail"
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "offline_queries": len(seen),
                      "live_passed": report.get("live", {}).get("passed"), "out": str(out)}), flush=True)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--api")
    parser.add_argument("--profile", choices=["s1-a", "s1-b"], default="s1-a")
    parser.add_argument("--sample-per-route", type=int, default=32)
    args = parser.parse_args()
    raise SystemExit(verify(args))
