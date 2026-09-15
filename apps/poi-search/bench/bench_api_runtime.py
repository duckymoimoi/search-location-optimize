"""API latency + resource benchmark for hybrid (:8000) vs dense-only (:8001)."""
from __future__ import annotations

import json
import statistics
import subprocess
import time
import uuid
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "hybrid": "http://127.0.0.1:8000",
    "dense_only": "http://127.0.0.1:8001",
}

# Prefer long queries so hybrid/dense both encode (short may skip dense on hybrid).
QUERIES = [
    "vincom",
    "highlands",
    "bệnh viện bạch mai",
    "bv việt đức",
    "trung học đa",
    "phở bò nam định",
    "23 nguyễn trãi",
    "lotte center",
    "aeon mall",
    "vinuni",
    "ga hà nội",
    "times city",
    "royal city",
    "keangnam",
    "đại học bách khoa",
    "nhà thuốc an khang",
    "công viên thống nhất",
    "chợ đồng xuân",
    "bảo tàng dân tộc học",
    "sân bay nội bài",
]

WARMUP = 5
ROUNDS = 5  # per query → 100 timed requests / profile
ORIGIN = {
    "kind": "gps",
    "point": {"lat": 21.0285, "lon": 105.8542},
    "accuracy_m": 25.0,
    "observed_at": "2026-09-15T03:00:00Z",
}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def docker_stats() -> dict[str, dict[str, float]]:
    proc = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, dict[str, float]] = {}
    for line in proc.stdout.strip().splitlines():
        name, mem, mem_pct, cpu = line.split("\t")
        used = mem.split("/")[0].strip()
        # e.g. 557.9MiB or 1.3GiB
        if used.endswith("GiB"):
            mb = float(used[:-3]) * 1024
        elif used.endswith("MiB"):
            mb = float(used[:-3])
        else:
            mb = float("nan")
        out[name] = {
            "mem_mib": mb,
            "mem_pct": float(mem_pct.strip("%")),
            "cpu_pct": float(cpu.strip("%")),
        }
    return out


def call_suggest(base: str, query: str, session_id: str, revision: int) -> tuple[float, dict]:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = {
        "request_id": str(uuid.uuid4()),
        "session_id": session_id,
        "context_revision": revision,
        "query": query,
        "top_k": 5,
        "expected_corpus_version": "hn-poi-stable-v1",
        "search_kind": "destination",
        "origin": ORIGIN,
        "demo_user_id": None,
        "context_time": None,
        "preferred_region_id": None,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/v1/suggest/personalized",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"},
    )
    started = time.perf_counter()
    with opener.open(req, timeout=120) as resp:
        payload = json.loads(resp.read())
    client_ms = (time.perf_counter() - started) * 1000
    return client_ms, payload


def create_session(base: str) -> str:
    data = b"{}"
    req = urllib.request.Request(
        f"{base}/v1/sessions",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["session_id"]


def summarize(samples: list[dict]) -> dict:
    def col(key: str) -> list[float]:
        return [float(s[key]) for s in samples if s.get(key) is not None]

    def block(values: list[float]) -> dict:
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

    return {
        "client_total": block(col("client_ms")),
        "server_total": block(col("server_total_ms")),
        "encode": block(col("encode_ms")),
        "lexical": block(col("lexical_ms")),
        "ann": block(col("ann_ms")),
        "fusion": block(col("fusion_ms")),
        "result_count_mean": statistics.fmean(col("n_results")) if col("n_results") else None,
    }


def run_profile(name: str, base: str) -> dict:
    session_id = create_session(base)
    # warm-up
    for query in QUERIES[:WARMUP]:
        call_suggest(base, query, session_id, 1)

    samples: list[dict] = []
    mem_samples: list[dict[str, dict[str, float]]] = []
    revision = 1
    for round_idx in range(ROUNDS):
        mem_samples.append(docker_stats())
        for query in QUERIES:
            revision += 1
            client_ms, payload = call_suggest(base, query, session_id, revision)
            timings = payload.get("timings_ms") or {}
            samples.append(
                {
                    "query": query,
                    "round": round_idx,
                    "client_ms": client_ms,
                    "server_total_ms": timings.get("total"),
                    "encode_ms": timings.get("encode"),
                    "lexical_ms": timings.get("lexical"),
                    "ann_ms": timings.get("ann"),
                    "fusion_ms": timings.get("fusion"),
                    "n_results": len(payload.get("results") or []),
                    "notes": (payload.get("scope_summary") or {}).get("notes"),
                }
            )
    mem_samples.append(docker_stats())

    # map container names
    api_keys = {
        "hybrid": "hanoi-poi-stage1-api",
        "dense_only": "hanoi-poi-stage1-api-dense",
    }
    os_key = "hanoi-poi-opensearch"
    api_name = api_keys[name]
    api_mem = [m[api_name]["mem_mib"] for m in mem_samples if api_name in m]
    os_mem = [m[os_key]["mem_mib"] for m in mem_samples if os_key in m]

    return {
        "profile": name,
        "base_url": base,
        "warmup_queries": WARMUP,
        "timed_requests": len(samples),
        "queries": QUERIES,
        "rounds": ROUNDS,
        "summary": summarize(samples),
        "resources": {
            "api_container": api_name,
            "api_mem_mib": {
                "samples": len(api_mem),
                "mean": statistics.fmean(api_mem) if api_mem else None,
                "min": min(api_mem) if api_mem else None,
                "max": max(api_mem) if api_mem else None,
            },
            "opensearch_mem_mib": {
                "samples": len(os_mem),
                "mean": statistics.fmean(os_mem) if os_mem else None,
                "min": min(os_mem) if os_mem else None,
                "max": max(os_mem) if os_mem else None,
            },
            "docker_stats_samples": mem_samples,
        },
        "samples": samples,
    }


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    idle = docker_stats()
    profiles = {}
    for name, base in TARGETS.items():
        print(f"running {name} ...", flush=True)
        profiles[name] = run_profile(name, base)
        print(json.dumps(profiles[name]["summary"], indent=2), flush=True)
        print(json.dumps(profiles[name]["resources"]["api_mem_mib"], indent=2), flush=True)

    report = {
        "created_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "corpus": "hn-poi-stable-v1",
        "index": "hanoi-poi-stable-v1-release1",
        "note": (
            "End-to-end via FastAPI suggest/personalized after warm-up. "
            "client_total = wall clock; encode/lexical/ann/fusion/server_total from timings_ms. "
            "RAM from docker stats during the run (MiB)."
        ),
        "idle_docker_stats": idle,
        "profiles": {k: {kk: vv for kk, vv in v.items() if kk != "samples"} for k, v in profiles.items()},
        "profiles_with_samples": profiles,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUT_DIR / f"api_latency_resources_{stamp}.json"
    latest = OUT_DIR / "api_latency_resources_latest.json"
    # keep samples only in stamped file to avoid huge latest? user may want latest full - keep both slim latest
    slim = dict(report)
    slim.pop("profiles_with_samples", None)
    for path, payload in ((json_path, report), (latest, slim)):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown summary
    lines = [
        "# API runtime — hybrid vs dense-only",
        "",
        f"Measured: `{started}` → `{report['finished_at']}`",
        "",
        "Corpus `hn-poi-stable-v1`, index `hanoi-poi-stable-v1-release1`.",
        f"{len(QUERIES)} queries × {ROUNDS} rounds after {WARMUP} warm-up queries per profile.",
        "Origin fixed GPS near Hoàn Kiếm. Endpoint: `POST /v1/suggest/personalized`.",
        "",
        "| Profile | Client p50/p95 (ms) | Server total p95 | Encode p95 | Lexical p95 | ANN p95 | API RAM mean/max (MiB) | OS RAM mean (MiB) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("hybrid", "dense_only"):
        s = profiles[name]["summary"]
        r = profiles[name]["resources"]
        lines.append(
            "| {name} | {cp50:.1f} / {cp95:.1f} | {sp95:.1f} | {ep95:.1f} | {lp95:.1f} | {ap95:.1f} | {rmean:.0f} / {rmax:.0f} | {os:.0f} |".format(
                name=name,
                cp50=s["client_total"]["p50_ms"],
                cp95=s["client_total"]["p95_ms"],
                sp95=s["server_total"]["p95_ms"],
                ep95=s["encode"]["p95_ms"],
                lp95=s["lexical"].get("p95_ms", float("nan")),
                ap95=s["ann"]["p95_ms"],
                rmean=r["api_mem_mib"]["mean"],
                rmax=r["api_mem_mib"]["max"],
                os=r["opensearch_mem_mib"]["mean"],
            )
        )
    lines.extend(
        [
            "",
            f"JSON: `{json_path.as_posix()}`",
            f"Latest slim: `{latest.as_posix()}`",
            "",
            "Notes:",
            "- Hybrid may still run lexical+encode+ANN; dense-only skips lexical retrieval.",
            "- Encode p95 is model forward only (from API `timings_ms.encode`).",
            "- RAM is container RSS via `docker stats`, not process PSS; OpenSearch is shared.",
        ]
    )
    md_path = OUT_DIR / "API_LATENCY_RESOURCES.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
