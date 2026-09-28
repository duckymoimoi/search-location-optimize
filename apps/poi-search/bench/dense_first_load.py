"""Closed-loop endpoint characterization; no training, no production SLA claim."""
import argparse
import hashlib
import http.client
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import time
import threading
import urllib.request
from urllib.parse import urlparse

import numpy as np

local = threading.local()
connection_mode = "per_request"


def request(base, path, body=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    if connection_mode == "keepalive":
        parsed = urlparse(base)
        if parsed.scheme != 'http':
            raise ValueError('Local characterization supports HTTP only')
        if not hasattr(local, 'connection'):
            local.connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=30)
        try:
            local.connection.request('GET' if body is None else 'POST', path, body=payload,
                                     headers={'Content-Type':'application/json'})
            response = local.connection.getresponse()
            content = response.read()
            if response.status >= 400:
                raise RuntimeError(f'HTTP {response.status}')
            return json.loads(content)
        except Exception:
            local.connection.close()
            del local.connection
            raise
    req = urllib.request.Request(base + path, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main(args):
    global connection_mode
    connection_mode = args.connection_mode
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=False)
    records = [json.loads(x) for x in Path(args.queries).read_text(encoding="utf-8").splitlines()]
    records = [r for r in records if r.get("normalizer") == "raw"]
    health = None
    for attempt in range(120):
        try:
            health = request(args.api, "/health")
            break
        except Exception:
            time.sleep(0.5)
    if health is None:
        raise RuntimeError("API did not become healthy within startup wait")
    if health["index"] != "vn-poi-core-v3-me5-6k-devlock":
        raise ValueError("Unexpected index")
    session = request(args.api, "/v1/sessions", {})["session_id"]
    rng = random.Random(42)
    # Explicit mixed workload: 80% POI, 20% brand (research assumption).
    poi = [r for r in records if r["suite"] == "poi_dev"]
    brand = [r for r in records if r["suite"] == "brand_dev"]
    if not poi or not brand:
        raise ValueError("Need both dev suites")
    workload = [rng.choice(brand if i % 5 == 0 else poi) for i in range(args.requests)]

    def invoke(item):
        i, row = item
        start = time.perf_counter()
        body = {"request_id": f"load-{i}", "session_id": session, "context_revision": 1, "query": row["query_text"], "top_k": 10, "expected_corpus_version": "vn-poi-core-v3-semantic-address-dedup50"}
        try:
            result = request(args.api, "/v1/suggest", body)
            return {"query_id": row["query_id"], "status": "ok", "client_ms": (time.perf_counter()-start)*1000, "timings_ms": result["timings_ms"], "versions": result["versions"], "route": result["scope_summary"]["notes"][0]}
        except Exception as exc:
            return {"query_id": row["query_id"], "status": "error", "client_ms": (time.perf_counter()-start)*1000, "error": str(exc)}

    for i, row in enumerate(workload[:16]):
        if invoke((i, row))["status"] != "ok":
            raise RuntimeError("Warmup failed")
    manifest = {"api": args.api, "health": health, "requests_per_cell": args.requests, "repetitions": 3, "concurrency": [1, 4, 8, 16], "traffic_mix": {"poi": .8, "brand": .2}, "load_model": "closed_loop", "sla": "unconfigured; characterization only", "background": args.background,
                "input_sha256": hashlib.sha256(Path(args.queries).read_bytes()).hexdigest(), "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "seed": 42}
    manifest['connection_mode'] = args.connection_mode
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    report = []
    with (folder / "requests.jsonl").open("w", encoding="utf-8") as stream:
        for repeat in range(3):
            levels = [1, 4, 8, 16]
            rng.shuffle(levels)
            for concurrency in levels:
                began = time.perf_counter()
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    rows = list(pool.map(invoke, enumerate(workload)))
                wall = time.perf_counter() - began
                for row in rows:
                    stream.write(json.dumps(dict(row, repeat=repeat, concurrency=concurrency), ensure_ascii=False) + "\n")
                values = [r["client_ms"] for r in rows]
                errors = sum(r["status"] != "ok" for r in rows)
                item = {"repeat": repeat, "concurrency": concurrency, "n": len(rows), "errors": errors, "qps_completed": (len(rows)-errors)/wall, "client_ms": dict(zip(("p50", "p95", "p99"), np.quantile(values, [.5, .95, .99]).tolist())), "versions": next((r["versions"] for r in rows if r["status"] == "ok"), None)}
                report.append(item)
                print(json.dumps(item), flush=True)
                stream.flush()
    (folder / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--requests", type=int, default=128)
    parser.add_argument("--background", default="must record background GPU services")
    parser.add_argument('--connection-mode', choices=('per_request','keepalive'), default='per_request')
    args = parser.parse_args()
    if args.requests < 16:
        parser.error("requests must be at least 16")
    main(args)
