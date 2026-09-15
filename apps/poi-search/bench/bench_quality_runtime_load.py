"""Full quality + runtime + load bench: lexical / dense / hybrid.

Slices (dev_synthetic):
  prefix     = track autocomplete
  typo       = track ime_keystream
  address    = retrieval_core + address case_types + main_metric_candidate
  structured = structured_code + structured_metric_candidate

Runs two profile orders. Separates cold vs warm. Load ramp 1/5/10/20 QPS.
"""
from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "HANOI_QUERIES_20K" / "hanoi_queries_20k_stable_v1"
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROFILES = {
    "lexical_only": "http://127.0.0.1:8002",
    "dense_only": "http://127.0.0.1:8001",
    "hybrid": "http://127.0.0.1:8000",
}
ORDERS = [
    ["lexical_only", "dense_only", "hybrid"],
    ["hybrid", "dense_only", "lexical_only"],
]
FINAL_K = 50
SAMPLE_PER_SLICE = 40
LOAD_QPS = [1, 5, 10, 20]
LOAD_DURATION_S = 20
LOAD_TIMEOUT_S = 5.0
ORIGIN = {
    "kind": "gps",
    "point": {"lat": 21.0285, "lon": 105.8542},
    "accuracy_m": 25.0,
    "observed_at": "2026-09-15T04:00:00Z",
}
ADDRESS_CASE_TYPES = {
    "address_exact",
    "address_first",
    "address_namespace",
    "address_order",
    "address_input_variant",
    "name_address",
    "slash_alley_address",
}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)


def summarize_ms(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values),
    }


def docker_stats() -> dict[str, dict[str, float]]:
    proc = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, dict[str, float]] = {}
    for line in proc.stdout.strip().splitlines():
        name, mem, cpu = line.split("\t")
        used = mem.split("/")[0].strip()
        if used.endswith("GiB"):
            mb = float(used[:-3]) * 1024
        elif used.endswith("MiB"):
            mb = float(used[:-3])
        else:
            mb = float("nan")
        out[name] = {"mem_mib": mb, "cpu_pct": float(cpu.strip("%"))}
    return out


def load_slices() -> dict[str, list[dict]]:
    queries = pd.read_parquet(DATA / "queries_20k.parquet")
    eligibility = pd.read_parquet(DATA / "eligibility.parquet")
    df = queries.merge(eligibility, on="query_id", how="left")
    df = df[df["split"] == "dev_synthetic"].copy()

    def take(mask, n: int | None = SAMPLE_PER_SLICE) -> list[dict]:
        part = df.loc[mask].sort_values("query_id")
        if n is not None and len(part) > n:
            idx = [int(i * (len(part) - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]
            part = part.iloc[sorted(set(idx))]
        rows = []
        for row in part.itertuples(index=False):
            rows.append(
                {
                    "query_id": row.query_id,
                    "query": row.query,
                    "intended_poi_id": row.intended_poi_id,
                    "track": row.track,
                    "case_type": row.case_type,
                }
            )
        return rows

    structured_mask = (df["track"] == "structured_code") & (df["structured_metric_candidate"] == True)  # noqa: E712
    address_mask = (
        (df["track"] == "retrieval_core")
        & (df["main_metric_candidate"] == True)  # noqa: E712
        & df["case_type"].isin(ADDRESS_CASE_TYPES)
    )
    return {
        "prefix": take(df["track"] == "autocomplete"),
        "typo": take(df["track"] == "ime_keystream"),
        "address": take(address_mask),
        "structured": take(structured_mask, n=None),
    }


def http_json(method: str, url: str, body: dict | None = None, timeout: float = 60.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw) if raw else {}
            return resp.status, payload, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else {"message": str(exc)}
        except json.JSONDecodeError:
            payload = {"message": raw.decode(errors="replace")}
        return exc.code, payload, (time.perf_counter() - started) * 1000
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        return 0, {"message": str(exc), "timeout_or_error": True, "timeout": "timed out" in msg}, (
            time.perf_counter() - started
        ) * 1000


def create_session(base: str) -> str:
    code, payload, _ = http_json("POST", f"{base}/v1/sessions", {})
    if code != 200:
        raise RuntimeError(f"session failed {base}: {code} {payload}")
    return payload["session_id"]


def suggest(base: str, session_id: str, query: str, revision: int, top_k: int, timeout: float = 60.0):
    body = {
        "request_id": str(uuid.uuid4()),
        "session_id": session_id,
        "context_revision": revision,
        "query": query,
        "top_k": top_k,
        "expected_corpus_version": "hn-poi-stable-v1",
        "search_kind": "destination",
        "origin": ORIGIN,
        "demo_user_id": None,
        "context_time": None,
        "preferred_region_id": None,
    }
    return http_json("POST", f"{base}/v1/suggest/personalized", body, timeout=timeout)


def dense_ran(timings: dict, notes) -> bool:
    encode = float(timings.get("encode") or 0.0)
    ann = float(timings.get("ann") or 0.0)
    note_text = " ".join(notes or [])
    return encode > 0.05 and ann > 0.05 and ("dense" in note_text or "hybrid" in note_text)


def rank_of(ids: list[str], target: str) -> int | None:
    try:
        return ids.index(target) + 1
    except ValueError:
        return None


def mrr_at(rank: int | None, k: int) -> float:
    if rank is None or rank > k:
        return 0.0
    return 1.0 / rank


def quality_block(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    hit5 = [1.0 if (r["rank"] is not None and r["rank"] <= 5) else 0.0 for r in rows]
    hit50 = [1.0 if (r["rank"] is not None and r["rank"] <= FINAL_K) else 0.0 for r in rows]
    mrr10 = [mrr_at(r["rank"], 10) for r in rows]
    return {
        "n": len(rows),
        "CandidateHit@5": statistics.fmean(hit5),
        "CandidateHit@50": statistics.fmean(hit50),
        "MRR@10": statistics.fmean(mrr10),
        "dense_ran_rate": statistics.fmean([1.0 if r["dense_ran"] else 0.0 for r in rows]),
        "errors": sum(1 for r in rows if r["error"]),
        "client": summarize_ms([r["client_ms"] for r in rows]),
        "server_total": summarize_ms([r["server_total_ms"] for r in rows if r["server_total_ms"] is not None]),
        "encode": summarize_ms([r["encode_ms"] for r in rows]),
        "lexical": summarize_ms([r["lexical_ms"] for r in rows]),
        "ann": summarize_ms([r["ann_ms"] for r in rows]),
        "queue_approx": summarize_ms([r["queue_ms"] for r in rows if r["queue_ms"] is not None]),
        "result_count_mean": statistics.fmean([r["n_results"] for r in rows]),
    }


def run_pass(profile: str, base: str, labeled: list[tuple[str, dict]], cache_kind: str, order_name: str):
    session_id = create_session(base)
    revision = 1
    rows = []
    for slice_name, item in labeled:
        revision += 1
        code, payload, client_ms = suggest(base, session_id, item["query"], revision, FINAL_K)
        timings = payload.get("timings_ms") or {}
        notes = (payload.get("scope_summary") or {}).get("notes") or []
        ids = [r.get("poi_id") for r in (payload.get("results") or []) if r.get("poi_id")]
        server_total = timings.get("total")
        queue_ms = None if server_total is None else max(0.0, client_ms - float(server_total))
        error = code != 200 or bool(payload.get("timeout_or_error"))
        rows.append(
            {
                "order": order_name,
                "profile": profile,
                "cache": cache_kind,
                "slice": slice_name,
                "query_id": item["query_id"],
                "query": item["query"],
                "intended_poi_id": item["intended_poi_id"],
                "http_code": code,
                "error": error,
                "rank": None if error else rank_of(ids, item["intended_poi_id"]),
                "n_results": 0 if error else len(ids),
                "client_ms": client_ms,
                "server_total_ms": None if server_total is None else float(server_total),
                "encode_ms": float(timings.get("encode") or 0.0),
                "lexical_ms": float(timings.get("lexical") or 0.0),
                "ann_ms": float(timings.get("ann") or 0.0),
                "fusion_ms": float(timings.get("fusion") or 0.0),
                "queue_ms": queue_ms,
                "dense_ran": False if error else dense_ran(timings, notes),
                "notes": notes,
                "degraded_reasons": payload.get("degraded_reasons") or [],
            }
        )
    return rows


def run_load(profile: str, base: str, queries: list[str], target_qps: int, order_check: bool = False) -> dict:
    session_id = create_session(base)
    revision_box = [1]
    for q in queries[:5]:
        suggest(base, session_id, q, revision_box[0], top_k=5)
        revision_box[0] += 1

    results: list[dict] = []
    lock = threading.Lock()
    stop_at = time.perf_counter() + LOAD_DURATION_S
    interval = 1.0 / target_qps
    next_at = time.perf_counter()
    idx = 0

    def one(q: str):
        revision_box[0] += 1
        code, payload, client_ms = suggest(base, session_id, q, revision_box[0], top_k=5, timeout=LOAD_TIMEOUT_S)
        timings = payload.get("timings_ms") or {}
        server_total = timings.get("total")
        return {
            "http_code": code,
            "error": code != 200 or bool(payload.get("timeout_or_error")),
            "timeout": bool(payload.get("timeout")) or (
                code == 0 and "timed out" in str(payload.get("message", "")).lower()
            ),
            "client_ms": client_ms,
            "server_total_ms": None if server_total is None else float(server_total),
            "queue_ms": None if server_total is None else max(0.0, client_ms - float(server_total)),
            "encode_ms": float(timings.get("encode") or 0.0),
            "dense_ran": dense_ran(timings, (payload.get("scope_summary") or {}).get("notes")),
            "degraded": bool(payload.get("degraded_reasons")),
        }

    with ThreadPoolExecutor(max_workers=max(8, target_qps * 2)) as pool:
        futures = []
        while True:
            now = time.perf_counter()
            if now >= stop_at:
                break
            if now < next_at:
                time.sleep(min(0.002, next_at - now))
                continue
            q = queries[idx % len(queries)]
            idx += 1
            next_at += interval
            futures.append(pool.submit(one, q))
        for fut in as_completed(futures):
            with lock:
                results.append(fut.result())

    return {
        "profile": profile,
        "target_qps": target_qps,
        "duration_s": LOAD_DURATION_S,
        "order_check": order_check,
        "submitted": len(results),
        "achieved_qps": len(results) / LOAD_DURATION_S,
        "ok": sum(1 for r in results if not r["error"]),
        "errors": sum(1 for r in results if r["error"]),
        "timeouts": sum(1 for r in results if r["timeout"]),
        "degraded": sum(1 for r in results if r["degraded"]),
        "dense_ran_rate": statistics.fmean([1.0 if r["dense_ran"] else 0.0 for r in results]) if results else None,
        "client": summarize_ms([r["client_ms"] for r in results]),
        "queue_approx": summarize_ms([r["queue_ms"] for r in results if r["queue_ms"] is not None]),
        "encode": summarize_ms([r["encode_ms"] for r in results]),
    }


def aggregate_quality(all_rows: list[dict]) -> dict:
    out: dict = {}
    for profile in PROFILES:
        out[profile] = {}
        for cache in ("cold", "warm"):
            out[profile][cache] = {}
            for slice_name in ("prefix", "typo", "address", "structured", "all"):
                if slice_name == "all":
                    rows = [r for r in all_rows if r["profile"] == profile and r["cache"] == cache]
                else:
                    rows = [
                        r
                        for r in all_rows
                        if r["profile"] == profile and r["cache"] == cache and r["slice"] == slice_name
                    ]
                out[profile][cache][slice_name] = quality_block(rows)
    out["order_comparison"] = {}
    for order_name in sorted({r["order"] for r in all_rows}):
        out["order_comparison"][order_name] = {}
        for profile in PROFILES:
            rows = [
                r
                for r in all_rows
                if r["order"] == order_name and r["profile"] == profile and r["cache"] == "warm"
            ]
            out["order_comparison"][order_name][profile] = quality_block(rows)
    return out


def wait_healthy(timeout_s: float = 120.0) -> None:
    deadline = time.time() + timeout_s
    pending = set(PROFILES)
    while pending and time.time() < deadline:
        for name in list(pending):
            code, payload, _ = http_json("GET", f"{PROFILES[name]}/health", timeout=5)
            if code == 200 and payload.get("status") in {"ok", "degraded"}:
                pending.discard(name)
        if pending:
            time.sleep(2)
    if pending:
        raise RuntimeError(f"APIs not healthy: {sorted(pending)}")


def write_markdown(report: dict, latest: Path, rows_path: Path) -> Path:
    quality = report["quality"]
    lines = [
        "# Quality + runtime + load — lexical / dense / hybrid",
        "",
        f"Measured: `{report['created_at']}` → `{report['finished_at']}`",
        "",
        f"Dev slices (sampled): `{json.dumps(report['slice_counts'], ensure_ascii=False)}`",
        f"Final K={report['final_k']}. Profile orders: `{ORDERS[0]}` then `{ORDERS[1]}`.",
        "",
        "CandidateHit / MRR are on **API top_k after Stage-2 gates** (not raw Stage-1 branch).",
        "`dense_ran` = encode>0.05ms and ann>0.05ms and notes contain dense/hybrid.",
        "cold = first pass of the query set; warm = immediate repeat. "
        "`queue_approx` = max(0, client_ms − server timings_ms.total).",
        "",
        "## Warm quality by slice (orders pooled)",
        "",
        "| Profile | Slice | N | CandidateHit@5 | CandidateHit@50 | MRR@10 | Encode p95 | Client p95 | Dense ran |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in PROFILES:
        for slice_name in ("prefix", "typo", "address", "structured", "all"):
            b = quality[profile]["warm"][slice_name]
            if not b.get("n"):
                continue
            ep = b["encode"].get("p95_ms")
            cp = b["client"].get("p95_ms")
            lines.append(
                "| {p} | {s} | {n} | {h5:.3f} | {h50:.3f} | {mrr:.3f} | {ep} | {cp} | {dr:.2f} |".format(
                    p=profile,
                    s=slice_name,
                    n=b["n"],
                    h5=b.get("CandidateHit@5") or 0,
                    h50=b.get("CandidateHit@50") or 0,
                    mrr=b.get("MRR@10") or 0,
                    ep="-" if ep is None else f"{ep:.1f}",
                    cp="-" if cp is None else f"{cp:.1f}",
                    dr=b.get("dense_ran_rate") or 0,
                )
            )

    lines += [
        "",
        "## Cold vs warm (all slices)",
        "",
        "| Profile | Cache | Client p95 | Encode p95 | Dense ran | CandidateHit@50 | MRR@10 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for profile in PROFILES:
        for cache in ("cold", "warm"):
            b = quality[profile][cache]["all"]
            lines.append(
                "| {p} | {c} | {cp:.1f} | {ep:.1f} | {dr:.2f} | {h50:.3f} | {mrr:.3f} |".format(
                    p=profile,
                    c=cache,
                    cp=b["client"].get("p95_ms") or math.nan,
                    ep=b["encode"].get("p95_ms") or 0.0,
                    dr=b.get("dense_ran_rate") or 0,
                    h50=b.get("CandidateHit@50") or 0,
                    mrr=b.get("MRR@10") or 0,
                )
            )

    lines += [
        "",
        "## Order comparison (warm, all slices)",
        "",
        "| Order | Profile | CandidateHit@50 | MRR@10 | Client p95 | Dense ran |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for order_name, by_profile in quality["order_comparison"].items():
        for profile, b in by_profile.items():
            if not b.get("n"):
                continue
            lines.append(
                "| {o} | {p} | {h50:.3f} | {mrr:.3f} | {cp:.1f} | {dr:.2f} |".format(
                    o=order_name,
                    p=profile,
                    h50=b.get("CandidateHit@50") or 0,
                    mrr=b.get("MRR@10") or 0,
                    cp=b["client"].get("p95_ms") or math.nan,
                    dr=b.get("dense_ran_rate") or 0,
                )
            )

    lines += [
        "",
        "## Load ramp (top_k=5, 20s each)",
        "",
        "| Profile | Target QPS | Achieved | p95 | p99 | Timeouts | Errors | Degraded | Queue p95 | Dense ran | Order-check |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["load"]:
        lines.append(
            "| {p} | {t} | {a:.2f} | {p95} | {p99} | {to} | {er} | {deg} | {q} | {dr} | {oc} |".format(
                p=item["profile"],
                t=item["target_qps"],
                a=item["achieved_qps"],
                p95="-" if not item["client"].get("p95_ms") else f"{item['client']['p95_ms']:.1f}",
                p99="-" if not item["client"].get("p99_ms") else f"{item['client']['p99_ms']:.1f}",
                to=item["timeouts"],
                er=item["errors"],
                deg=item["degraded"],
                q="-" if not item["queue_approx"].get("p95_ms") else f"{item['queue_approx']['p95_ms']:.1f}",
                dr="-" if item["dense_ran_rate"] is None else f"{item['dense_ran_rate']:.2f}",
                oc="yes" if item.get("order_check") else "",
            )
        )

    mem_lines = []
    for name, stats in sorted((report.get("docker_stats_after") or {}).items()):
        if "hanoi-poi" in name:
            mem_lines.append(f"- `{name}`: {stats['mem_mib']:.0f} MiB, CPU {stats['cpu_pct']:.1f}%")
    lines += ["", "## RAM after run", "", *mem_lines, "", f"JSON: `{latest.as_posix()}`", f"Rows: `{rows_path.as_posix()}`", ""]
    md_path = OUT_DIR / "QUALITY_RUNTIME_LOAD.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    # also copy to training benchmark folder for discoverability
    mirror = ROOT / "training" / "stage1" / "benchmark_stable_v1" / "api_runtime" / "QUALITY_RUNTIME_LOAD.md"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    slices = load_slices()
    labeled: list[tuple[str, dict]] = []
    for slice_name, items in slices.items():
        for item in items:
            labeled.append((slice_name, item))
    print("slices", {k: len(v) for k, v in slices.items()}, "total", len(labeled), flush=True)

    wait_healthy()
    idle_stats = docker_stats()

    all_rows: list[dict] = []
    for order_idx, order in enumerate(ORDERS, start=1):
        order_name = f"order{order_idx}_" + "_".join(p.split("_")[0] for p in order)
        print(f"=== {order_name}: {order}", flush=True)
        for profile in order:
            base = PROFILES[profile]
            print(f"  cold {profile}", flush=True)
            all_rows.extend(run_pass(profile, base, labeled, "cold", order_name))
            print(f"  warm {profile}", flush=True)
            all_rows.extend(run_pass(profile, base, labeled, "warm", order_name))

    quality = aggregate_quality(all_rows)

    load_queries = [q["query"] for q in slices["address"] + slices["structured"] + slices["typo"]]
    load_results = []
    seen: set[str] = set()
    for profile in ["lexical_only", "dense_only", "hybrid", "hybrid", "dense_only", "lexical_only"]:
        base = PROFILES[profile]
        if profile not in seen:
            seen.add(profile)
            for qps in LOAD_QPS:
                print(f"load {profile} @{qps} qps", flush=True)
                load_results.append(run_load(profile, base, load_queries, qps))
        else:
            print(f"load-order-check {profile} @10 qps", flush=True)
            load_results.append(run_load(profile, base, load_queries, 10, order_check=True))

    finished = datetime.now(timezone.utc).isoformat()
    report = {
        "created_at": started,
        "finished_at": finished,
        "corpus": "hn-poi-stable-v1",
        "index": "hanoi-poi-stable-v1-release1",
        "final_k": FINAL_K,
        "sample_per_slice": SAMPLE_PER_SLICE,
        "slice_counts": {k: len(v) for k, v in slices.items()},
        "profiles": PROFILES,
        "orders": ORDERS,
        "idle_docker_stats": idle_stats,
        "docker_stats_after": docker_stats(),
        "quality": quality,
        "load": load_results,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUT_DIR / f"quality_runtime_load_{stamp}.json"
    latest = OUT_DIR / "quality_runtime_load_latest.json"
    rows_path = OUT_DIR / f"quality_runtime_load_{stamp}_rows.jsonl"
    with rows_path.open("w", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    json_path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    md_path = write_markdown(report, latest, rows_path)
    print(f"wrote {md_path}", flush=True)
    print(f"wrote {latest}", flush=True)


if __name__ == "__main__":
    main()
