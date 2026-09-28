"""Runnable POI Search demo API backed by Elasticsearch 9 + mE5-small."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pipeline
from demo_users import append_selection, public_users
from es_query import search
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from geo import goong_directions, haversine
from lexical import lexical_body
from pipeline import _build_map_geojson, pipeline_trace, suggest, versions
from ranking import classify_target_loss
from runtime import Runtime
from schemas import (
    DisplayRequest,
    RouteRequest,
    SelectRequest,
    SuggestRequest,
    TraceSuggestRequest,
)
from settings import (
    CORPUS_VERSION,
    EXPECTED_ROWS,
    GOONG_API_KEY,
    INDEX_NAME,
    POLICY,
    RETRIEVAL_PROFILE,
)
from textnorm import glue_code_spans

runtime = Runtime()
pipeline.runtime = runtime

app = FastAPI(title="VN POI Search Demo", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=POLICY["cors_origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def warmup() -> None:
    """Keep the first user request out of model/index cold-start cost."""
    for query in POLICY["warmup_queries"]:
        if RETRIEVAL_PROFILE != "dense_only":
            runtime.lexical(query)
        if RETRIEVAL_PROFILE != "lexical_only":
            runtime.dense(runtime.encode(glue_code_spans(query)))


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": detail.get("code", f"http_{exc.status_code}"),
            "message": detail.get("message", str(exc.detail)),
            "request_id": None,
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    count = runtime.client().request("GET", f"/{INDEX_NAME}/_count")["count"]
    return {
        "status": "ok" if count == EXPECTED_ROWS else "degraded",
        "index": INDEX_NAME,
        "corpus_rows": count,
        "device": str(runtime.device),
    }


@app.post("/v1/sessions")
def create_session(response: Response) -> dict[str, str]:
    session_id = f"session-{uuid.uuid4()}"
    runtime.sessions.add(session_id)
    response.set_cookie("poi_session", session_id, httponly=True, samesite="lax")
    return {"session_id": session_id}


@app.get("/v1/status")
def status() -> dict[str, Any]:
    count = runtime.client().request("GET", f"/{INDEX_NAME}/_count")["count"]
    return {
        "ready": count == EXPECTED_ROWS,
        "versions": versions(),
        "coverage_id": CORPUS_VERSION,
        "profile": RETRIEVAL_PROFILE,
        "capabilities": [
            RETRIEVAL_PROFILE,
            "geo_heuristic",
            "demo_users",
            "straight_line_preview",
            *(["goong_road_route"] if GOONG_API_KEY else []),
        ],
        }


@app.get("/v1/map/pois")
def map_pois() -> dict[str, Any]:
    """Return the searchable catalog for the clustered MapLibre map source."""
    if runtime.map_geojson is None:
        with runtime.map_lock:
            if runtime.map_geojson is None:
                runtime.map_geojson = _build_map_geojson()
    return runtime.map_geojson


@app.get("/v1/demo/users")
def list_demo_users() -> list[dict[str, str]]:
    return public_users()


@app.get("/v1/origins")
def origins(q: str = "", limit: int = 20) -> dict[str, Any]:
    body = lexical_body(q.strip(), max(1, min(limit, 50)))
    if not q.strip():
        body["query"] = {"bool": {"filter": []}}
    body["query"]["bool"]["filter"] = [{"term": {"origin_search_eligible": True}}]
    ids, _ = search(runtime.client(), body)
    items = [{"poi_id": d["canonical_id"], "name": d["search_label"], "ranking_point": d["ranking_point"],
              "pickup_access_verified": d.get("pickup_access_verified", False)} for d in runtime.documents(ids)]
    return {"corpus_version": CORPUS_VERSION, "items": items, "next_cursor": None}


@app.post("/v1/suggest")
def suggest_query_only(payload: SuggestRequest) -> dict[str, Any]:
    return suggest(payload, False)


@app.post("/v1/suggest/personalized")
def suggest_personalized(payload: SuggestRequest) -> dict[str, Any]:
    return suggest(payload, True)


@app.post("/v1/debug/trace_suggest")
def debug_trace_suggest(payload: TraceSuggestRequest) -> dict[str, Any]:
    """Freeze/replay diagnostics only. Same pipeline as suggest; no exposure write."""
    if payload.expected_corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})
    if payload.session_id not in runtime.sessions:
        raise HTTPException(401, detail={"code": "invalid_session", "message": "Unknown session"})
    query = " ".join(payload.query.split())
    if not query:
        empty_stages = {
            "lexical": [], "dense": [], "rrf": [], "nearby_rescue_hits": [],
            "after_nearby_rescue": [], "after_dedup_cap": [], "after_geo": [],
            "after_name_address": [], "after_name_match_quality": [], "final_top_k": [],
        }
        return {
            "request_id": payload.request_id,
            "route": "empty_query",
            "stages": empty_stages,
            "results": [],
            "failure_class": None,
            "target_ranks": {},
        }
    traced = pipeline_trace(
        query,
        origin=payload.origin,
        personalized=payload.personalized,
        top_k=payload.top_k,
    )
    stages = traced["stages"]
    target = payload.target_poi_id
    ranks = {}
    if target:
        for name, ids in stages.items():
            if name == "nearby_rescue_hits":
                continue
            try:
                ranks[name] = ids.index(target) + 1
            except ValueError:
                ranks[name] = None
    return {
        "request_id": payload.request_id,
        "versions": versions(),
        "route": traced["route"],
        "timings_ms": traced["timings_ms"],
        "profile": traced["profile"],
        "policy_version": traced["policy_version"],
        "geo_mode": traced["geo_mode"],
        "rescued_n": traced["rescued_n"],
        "candidate_count": traced["candidate_count"],
        "stages": {key: value[:80] for key, value in stages.items()},
        "stage_sizes": {key: len(value) for key, value in stages.items()},
        "trace_truncated": any(len(value) > 80 for value in stages.values()),
        "branch_candidates": traced.get("branch_candidates", {}),
        "encoder_input": traced.get("encoder_input"),
        "results": traced["results"],
        "target_poi_id": target,
        "target_ranks": ranks,
        "failure_class": classify_target_loss(target, stages, top_k=min(5, payload.top_k)),
    }


@app.post("/v1/exposures/displayed")
def displayed(payload: DisplayRequest) -> dict[str, Any]:
    exposure = runtime.exposures.get(payload.exposure_id)
    if not exposure:
        raise HTTPException(404, detail={"code": "exposure_not_found", "message": "Exposure not found"})
    if exposure["session_id"] != payload.session_id or exposure["context_revision"] != payload.context_revision:
        raise HTTPException(409, detail={"code": "exposure_conflict", "message": "Exposure context mismatch"})
    exposure["displayed"] = True
    return {"exposure_id": payload.exposure_id, "displayed": True}


@app.post("/v1/select")
def select(payload: SelectRequest) -> dict[str, Any]:
    exposure = runtime.exposures.get(payload.exposure_id)
    if exposure and (exposure["session_id"] != payload.session_id or exposure["context_revision"] != payload.context_revision):
        raise HTTPException(409, detail={"code": "exposure_conflict", "message": "Exposure context mismatch"})
    key = (payload.session_id, payload.idempotency_key)
    if key in runtime.selections:
        cached = runtime.selections[key]
        if cached["selected_poi_id"] != payload.selected_poi_id or cached["exposure_id"] != payload.exposure_id:
            raise HTTPException(409, detail={"code": "idempotency_conflict", "message": "Key reused with another POI"})
        return cached
    exposure = runtime.exposures.get(payload.exposure_id)
    if not exposure or not exposure["displayed"] or payload.selected_poi_id not in exposure["shown_ids"]:
        raise HTTPException(409, detail={"code": "invalid_selection", "message": "Selection is not in a displayed exposure"})
    recorded_at = datetime.now(UTC)
    history_version = "in-memory-demo-v1"
    demo_user_id = exposure.get("demo_user_id")
    if demo_user_id:
        history_version = append_selection(
            payload.session_id, demo_user_id, payload.selected_poi_id, recorded_at
        )
    result = {"selection_id": f"sel-{uuid.uuid4()}", "exposure_id": payload.exposure_id,
              "selected_poi_id": payload.selected_poi_id, "corpus_version": CORPUS_VERSION,
              "recorded_at": recorded_at.isoformat(), "history_version": history_version,
              "event_source": "demo_selection"}
    runtime.selections[key] = result
    return result


@app.post("/v1/route-preview")
def route_preview(payload: RouteRequest) -> dict[str, Any]:
    if payload.corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})

    def point_from_poi(poi_id: str | None) -> dict[str, float] | None:
        if not poi_id:
            return None
        docs = runtime.documents([poi_id])
        if not docs:
            raise HTTPException(404, detail={"code": "poi_not_found", "message": f"POI missing: {poi_id}"})
        return docs[0]["ranking_point"]

    origin = payload.origin_point.model_dump() if payload.origin_point else point_from_poi(payload.origin_poi_id)
    destination = (
        payload.destination_point.model_dump()
        if payload.destination_point
        else point_from_poi(payload.destination_poi_id)
    )
    if origin is None:
        return {
            "status": "missing_origin",
            "corpus_version": CORPUS_VERSION,
            "mode_used": None,
            "geometry": None,
            "geodesic_distance_m": None,
            "route_distance_m": None,
            "route_duration_s": None,
            "reason": "missing_origin",
        }
    if destination is None:
        raise HTTPException(422, detail={"code": "missing_destination", "message": "Destination point or POI is required"})

    geodesic = round(haversine(origin, destination))
    if payload.mode == "road":
        try:
            road = goong_directions(origin, destination, payload.vehicle)
            return {
                "status": "ok",
                "corpus_version": CORPUS_VERSION,
                "mode_used": "road",
                "geometry": {"type": "LineString", "coordinates": road["coordinates"]},
                "geodesic_distance_m": geodesic,
                "route_distance_m": road["distance_m"],
                "route_duration_s": road["duration_s"],
                "reason": f"goong_directions:{payload.vehicle}",
            }
        except RuntimeError as exc:
            if not payload.allow_fallback:
                return {
                    "status": "unavailable",
                    "corpus_version": CORPUS_VERSION,
                    "mode_used": None,
                    "geometry": None,
                    "geodesic_distance_m": geodesic,
                    "route_distance_m": None,
                    "route_duration_s": None,
                    "reason": str(exc),
                }
            # fall through to straight line

    return {
        "status": "ok",
        "corpus_version": CORPUS_VERSION,
        "mode_used": "straight_line",
        "geometry": {
            "type": "LineString",
            "coordinates": [[origin["lon"], origin["lat"]], [destination["lon"], destination["lat"]]],
        },
        "geodesic_distance_m": geodesic,
        "route_distance_m": None,
        "route_duration_s": None,
        "reason": "straight_line_illustration_not_road_route",
    }
