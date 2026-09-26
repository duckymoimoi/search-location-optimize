"""End-to-end contract smoke against local POI Search API."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.environ.get("POI_API_BASE_URL", "http://127.0.0.1:8000")
OBSERVED_AT = (datetime.now(UTC) - timedelta(seconds=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"},
        )
        try:
            with opener.open(req, timeout=60) as resp:
                raw = resp.read()
                payload = json.loads(raw) if raw else {}
                return resp.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else {"message": str(exc)}
            except json.JSONDecodeError:
                payload = {"message": raw.decode(errors="replace")}
            return exc.code, payload

    checks: list[tuple[str, bool, str]] = []

    code, health = call("GET", "/health")
    checks.append(("health", code == 200 and health.get("status") == "ok", str(health)))

    code, status = call("GET", "/v1/status")
    checks.append(("status", code == 200 and status.get("ready") is True, str(status)[:200]))

    code, session = call("POST", "/v1/sessions", {})
    session_id = session.get("session_id")
    checks.append(("session", code == 200 and bool(session_id), str(session)))

    code, users = call("GET", "/v1/demo/users")
    user_ids = [item.get("demo_user_id") for item in users] if isinstance(users, list) else []
    users_ok = (
        code == 200
        and user_ids[:3] == ["demo-cold", "demo-repeat", "demo-session"]
        and all(set(item) == {"demo_user_id", "label"} for item in users)
    )
    checks.append(("demo_users", users_ok, json.dumps(users, ensure_ascii=False)[:300]))

    corpus_version = "vn-poi-core-v3-semantic-address-dedup50"
    coverage_ok = status.get("coverage_id") == corpus_version
    checks.append(("coverage", coverage_ok, str(status.get("coverage_id"))))

    code, forbidden = call(
        "POST",
        "/v1/suggest/personalized",
        {
            "request_id": "smoke-unknown-user",
            "session_id": session_id,
            "context_revision": 1,
            "query": "ga",
            "top_k": 5,
            "expected_corpus_version": corpus_version,
            "demo_user_id": "not-a-user",
        },
    )
    checks.append((
        "unknown_demo_user",
        code == 403 and forbidden.get("code") == "unknown_demo_user",
        str(forbidden)[:200],
    ))

    code, query_only = call(
        "POST",
        "/v1/suggest",
        {
            "request_id": "smoke-query-only",
            "session_id": session_id,
            "context_revision": 1,
            "query": "vincom",
            "top_k": 5,
            "expected_corpus_version": corpus_version,
            "origin": {
                "kind": "gps",
                "point": {"lat": 21.0285, "lon": 105.8542},
                "accuracy_m": 25,
                "observed_at": OBSERVED_AT,
            },
            "demo_user_id": "demo-repeat",
            "context_time": "2026-06-01T03:00:00Z",
        },
    )
    query_scope = query_only.get("scope_summary") or {}
    checks.append((
        "query_only_ignores_context",
        code == 200
        and query_scope.get("mode") == "global"
        and query_scope.get("coverage_id") == corpus_version
        and query_only.get("history_version") is None
        and bool(query_only.get("results")),
        json.dumps({
            "code": code,
            "mode": query_scope.get("mode"),
            "coverage": query_scope.get("coverage_id"),
            "history": query_only.get("history_version"),
        }, ensure_ascii=False),
    ))

    # short → lexical
    code, short = call(
        "POST",
        "/v1/suggest/personalized",
        {
            "request_id": "smoke-short",
            "session_id": session_id,
            "context_revision": 1,
            "query": "ga",
            "top_k": 5,
            "expected_corpus_version": corpus_version,
            "search_kind": "destination",
            "origin": {
                "kind": "gps",
                "point": {"lat": 21.0285, "lon": 105.8542},
                "accuracy_m": 25,
                "observed_at": OBSERVED_AT,
            },
            "demo_user_id": None,
            "context_time": None,
            "preferred_region_id": None,
        },
    )
    short_ok = (
        code == 200
        and short.get("exposure_id")
        and len(short.get("results") or []) > 0
        and any("ga" in (r.get("name") or "").casefold() for r in short["results"])
    )
    checks.append(("suggest_short_lexical", short_ok, json.dumps({
        "code": code,
        "n": len(short.get("results") or []),
        "names": [r.get("name") for r in (short.get("results") or [])[:3]],
        "notes": (short.get("scope_summary") or {}).get("notes"),
        "timings": short.get("timings_ms"),
    }, ensure_ascii=False)))

    # long → hybrid
    code, long = call(
        "POST",
        "/v1/suggest/personalized",
        {
            "request_id": "smoke-long",
            "session_id": session_id,
            "context_revision": 1,
            "query": "vincom",
            "top_k": 5,
            "expected_corpus_version": corpus_version,
            "search_kind": "destination",
            "origin": {
                "kind": "gps",
                "point": {"lat": 21.0285, "lon": 105.8542},
                "accuracy_m": 25,
                "observed_at": OBSERVED_AT,
            },
            "demo_user_id": None,
            "context_time": None,
            "preferred_region_id": None,
        },
    )
    long_ok = code == 200 and long.get("exposure_id") and len(long.get("results") or []) > 0
    checks.append(("suggest_long_hybrid", long_ok, json.dumps({
        "code": code,
        "n": len(long.get("results") or []),
        "names": [r.get("name") for r in (long.get("results") or [])[:3]],
        "notes": (long.get("scope_summary") or {}).get("notes"),
        "timings": long.get("timings_ms"),
        "dist0": (long.get("results") or [{}])[0].get("ranking_distance_m"),
    }, ensure_ascii=False)))

    code, cold = call(
        "POST",
        "/v1/suggest/personalized",
        {
            "request_id": "smoke-cold-user",
            "session_id": session_id,
            "context_revision": 2,
            "query": "vincom",
            "top_k": 5,
            "expected_corpus_version": corpus_version,
            "demo_user_id": "demo-cold",
            "context_time": None,
        },
    )
    checks.append((
        "personalized_history_version",
        code == 200 and str(cold.get("history_version") or "").startswith("demo-history-v1:demo-cold:live-0"),
        str(cold.get("history_version")),
    ))

    # Ambiguous partial query under geo-v6: distance only reorders same name cohort.
    # Nationwide corpus has many "trung học *" hits — use a more distinctive query.
    code, nearby = call(
        "POST",
        "/v1/suggest/personalized",
        {
            "request_id": "smoke-nearby-priority",
            "session_id": session_id,
            "context_revision": 1,
            "query": "tr\u01b0\u1eddng thcs \u0111a t\u1ed1n",
            "top_k": 10,
            "expected_corpus_version": corpus_version,
            "search_kind": "destination",
            "origin": {"kind": "map", "point": {"lat": 20.9960, "lon": 105.9327}},
            "demo_user_id": None,
            "context_time": None,
            "preferred_region_id": None,
        },
    )
    # Geo-v6 only reorders same name-match cohort; keep asserting nearby intended
    # is retrieved close to origin within top results (not always forced to #1).
    nearby_results = nearby.get("results") or []
    nearby_first = nearby_results[0] if nearby_results else {}
    da_ton_rank = next(
        (i + 1 for i, r in enumerate(nearby_results) if r.get("poi_id") == "osm:way/244377861"),
        None,
    )
    da_ton = nearby_results[da_ton_rank - 1] if da_ton_rank else None
    nearby_ok = (
        code == 200
        and da_ton is not None
        and da_ton_rank is not None
        and da_ton_rank <= 10
        and (da_ton.get("ranking_distance_m") or 10_000) < 1_500
    )
    checks.append((
        "nearby_priority_within_relevance_tier",
        nearby_ok,
        json.dumps({
            "first": nearby_first.get("name"),
            "first_id": nearby_first.get("poi_id"),
            "distance_m": nearby_first.get("ranking_distance_m"),
            "da_ton_rank": da_ton_rank,
            "da_ton_distance_m": None if da_ton is None else da_ton.get("ranking_distance_m"),
            "notes": (nearby.get("scope_summary") or {}).get("notes"),
        }, ensure_ascii=False),
    ))

    exposure_id = long.get("exposure_id")
    poi_id = (long.get("results") or [{}])[0].get("poi_id")
    code, disp = call(
        "POST",
        "/v1/exposures/displayed",
        {
            "session_id": session_id,
            "exposure_id": exposure_id,
            "context_revision": 1,
        },
    )
    checks.append(("displayed", code == 200 and disp.get("displayed") is True, str(disp)))

    code, sel = call(
        "POST",
        "/v1/select",
        {
            "session_id": session_id,
            "exposure_id": exposure_id,
            "context_revision": 1,
            "selected_poi_id": poi_id,
            "idempotency_key": "smoke-idem-1",
        },
    )
    checks.append(("select", code == 200 and sel.get("selected_poi_id") == poi_id, str(sel)[:300]))

    # CORS preflight-ish: Origin response headers via GET status
    req = urllib.request.Request(
        f"{BASE}/v1/status",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    with opener.open(req, timeout=30) as resp:
        acao = resp.headers.get("Access-Control-Allow-Origin")
        acac = resp.headers.get("Access-Control-Allow-Credentials")
        checks.append(
            (
                "cors_credentials",
                acao in {"http://127.0.0.1:5173", "*"} and (acac or "").lower() == "true",
                f"acao={acao} acac={acac}",
            )
        )

    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if failed:
        raise SystemExit(1)
    print("ALL_SMOKE_PASSED")


if __name__ == "__main__":
    main()
