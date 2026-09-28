"""Suggest pipeline: retrieve, rescue, rank, expose. Runtime is injected by app.py."""
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from demo_users import history_snapshot, known_user
from geo import haversine
from ranking import (
    _dense_evidence,
    _hybrid_evidence,
    _lexical_evidence,
    _result_rows,
    apply_history_cohort,
    candidate_documents,
    candidate_document_stages,
    merge_nearby_name_rescue,
    name_match_class,
    nearby_name_rescue_body,
    rank_candidates,
    rank_candidates_traced,
)
from schemas import Origin, SuggestRequest
from settings import (
    CORPUS_VERSION,
    EMBEDDING_SPACE_ID,
    INDEX_NAME,
    MODEL_ID,
    PASSAGE_BUILDER_VERSION,
    POLICY,
    RANKING_POLICY,
    RANKING_PROFILE,
    ENCODER_NORMALIZER,
    RELEASE_ID,
    RETRIEVAL_PROFILE,
)
from textnorm import compact_length, fold, encoder_input

runtime = None  # set to Runtime() by app.py before serving

def versions() -> dict[str, Any]:
    geo_mode = str(RANKING_POLICY.get("geo_mode", "v6")).strip().lower()
    ranker = "heuristic-geo-v6" if geo_mode == "v6" else "heuristic-geo-v5"
    feature = (
        "equivalent-name-exp-decay-v6+nearby-name-rescue"
        if geo_mode == "v6"
        else "field-aware-bounded-geo-v5+nearby-name-rescue"
    )
    if not (RANKING_POLICY.get("nearby_name_rescue") or {}).get("enabled", False):
        feature = (
            "equivalent-name-exp-decay-v6"
            if geo_mode == "v6"
            else "field-aware-bounded-geo-v5"
        )
    if RANKING_PROFILE != "current":
        ranker = "retrieval-order" if RANKING_PROFILE in {"raw", "dedup_only"} else f"heuristic-{RANKING_PROFILE}"
        feature = f"ranking-profile:{RANKING_PROFILE}"
    return {
        "release_id": RELEASE_ID,
        "corpus_version": CORPUS_VERSION,
        "index_version": INDEX_NAME,
        "encoder_id": MODEL_ID,
        "embedding_space_id": EMBEDDING_SPACE_ID,
        "passage_builder_version": PASSAGE_BUILDER_VERSION,
        "scope_policy_version": "global-v1",
        "candidate_policy_version": f"{POLICY['policy_version']}:safe-candidates-v5:{RETRIEVAL_PROFILE}:{RANKING_PROFILE}",
        "ranker_id": ranker,
        "feature_version": feature,
        "model_source": getattr(runtime, "model_source", MODEL_ID),
        "device": str(getattr(runtime, "device", "cpu")),
        "ranking_profile": RANKING_PROFILE,
        "encoder_normalizer": ENCODER_NORMALIZER,
        "dense_backend": getattr(runtime, "dense_backend", "ann"),
        "brand_lookup_sha256": getattr(runtime, "brand_lookup_sha256", None),
        "brand_route_mode": getattr(runtime, "brand_route_mode", None),
        "name_lookup_enabled": getattr(runtime, 'name_lookup_enabled', False),
    }


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _origin_point(point: Any) -> dict[str, float]:
    raw = point.model_dump() if hasattr(point, "model_dump") else point
    return {"lat": float(raw["lat"]), "lon": float(raw["lon"])}


def resolve_anchor(
    origin: Origin | None, *, now: datetime | None = None
) -> tuple[dict[str, float] | None, list[str]]:
    """Anchor for personalized scope. Stale or inaccurate GPS is dropped, not treated as 0 m."""
    if origin is None:
        return None, []
    max_accuracy_m = 200.0
    max_age_s = 120.0
    future_s = 30.0
    moment = _as_utc(now or datetime.now(UTC))
    if origin.kind in {"gps", "map"}:
        if origin.point is None:
            raise HTTPException(422, detail={"code": "origin_point_required", "message": "Origin point is required"})
        if origin.kind == "gps":
            if origin.observed_at is not None:
                observed = _as_utc(origin.observed_at)
                if (observed - moment).total_seconds() > future_s:
                    raise HTTPException(
                        422, detail={"code": "origin_in_future", "message": "GPS observation is in the future"}
                    )
                if (moment - observed).total_seconds() > max_age_s:
                    return None, ["gps_stale"]
            if origin.accuracy_m is not None and origin.accuracy_m > max_accuracy_m:
                return None, ["gps_accuracy"]
        return _origin_point(origin.point), []
    if not origin.poi_id:
        raise HTTPException(422, detail={"code": "origin_poi_required", "message": "Origin POI is required"})
    docs = runtime.documents([origin.poi_id])
    if not docs or not docs[0].get("origin_search_eligible"):
        raise HTTPException(422, detail={"code": "invalid_origin_poi", "message": "POI is not origin eligible"})
    return docs[0]["ranking_point"], []


def retrieve(
    query: str,
) -> tuple[list[str], str, dict[str, float], dict[str, dict[str, float | None]]]:
    result = retrieve_detailed(query)
    return result["ids"], result["route"], result["timings"], result["evidence"]


def retrieve_detailed(query: str) -> dict[str, Any]:
    """Retrieve with explicit branch id lists for freeze/replay traces.

    A disabled profile is not degraded. A hybrid branch that raises falls back
    to the branch that still returned; both failing is a hard error.
    """
    timings = {"encode": 0.0, "lexical": 0.0, "ann": 0.0, "fusion": 0.0}
    lexical_ids: list[str] = []
    dense_ids: list[str] = []
    degraded: list[str] = []
    branch_candidates: dict[str, list[dict[str, Any]]] = {}
    brand_family = None
    if RETRIEVAL_PROFILE == "dense_first":
        brand_family = runtime.brand_family(query)

    def branch(name, value):
        detailed = getattr(runtime, f"{name}_candidates", None)
        if detailed is None:
            return getattr(runtime, name)(value)
        candidates, elapsed = detailed(value)
        branch_candidates[name] = candidates
        return [item["poi_id"] for item in candidates], elapsed
    if RETRIEVAL_PROFILE == "lexical_only" or (
        RETRIEVAL_PROFILE == "hybrid"
        and compact_length(query) < int(POLICY["retrieval"]["dense_min_compact_chars"])
    ) or (
        RETRIEVAL_PROFILE == "dense_first" and not brand_family
        and compact_length(query) < int(POLICY["retrieval"]["dense_min_compact_chars"])
    ):
        lexical_ids, timings["lexical"] = branch("lexical", query)
        ids = list(lexical_ids)
        route = "lexical_only" if RETRIEVAL_PROFILE == "lexical_only" else "lexical_short_query"
        return {
            "ids": ids,
            "route": route,
            "timings": timings,
            "evidence": _lexical_evidence(ids),
            "lexical_ids": lexical_ids,
            "dense_ids": dense_ids,
            "degraded_reasons": degraded,
            "branch_candidates": branch_candidates,
        }
    if RETRIEVAL_PROFILE == "dense_only" or (RETRIEVAL_PROFILE == "dense_first" and not brand_family):
        lookup_future = runtime.pool.submit(runtime.name_lookup, query) if RETRIEVAL_PROFILE == 'dense_first' and hasattr(runtime,'name_lookup') else None
        began = time.perf_counter()
        try:
            vector = runtime.encode(encoder_input(query))
            timings["encode"] = (time.perf_counter() - began) * 1000
            timings.update(getattr(getattr(runtime, "local", None), "encode_timings", {}))
            dense_ids, timings["ann"] = branch("dense", vector)
        except Exception:
            if RETRIEVAL_PROFILE != "dense_first":
                raise
            degraded.append("dense_unavailable")
            try:
                lexical_ids, timings["lexical"] = branch("lexical", query)
            except Exception as exc:
                raise HTTPException(503, detail={"code": "search_unavailable", "message": "No retrieval branch available"}) from exc
            return {"ids": lexical_ids, "route": "dense_first_lexical_fallback", "timings": timings,
                    "evidence": _lexical_evidence(lexical_ids), "lexical_ids": lexical_ids,
                    "dense_ids": [], "degraded_reasons": degraded, "branch_candidates": branch_candidates}
        ids = list(dense_ids)
        lookup_candidates = []
        if lookup_future is not None:
            try:
                lookup_candidates, timings['name_lookup'] = lookup_future.result()
                branch_candidates['name_lookup'] = lookup_candidates
            except Exception:
                degraded.append('name_lookup_unavailable')
        evidence = _dense_evidence(dense_ids)
        if lookup_candidates:
            lookup_ids = [row['poi_id'] for row in lookup_candidates]
            ids = list(dict.fromkeys(lookup_ids + dense_ids))
            top = max((row['rrf'] for row in evidence.values()), default=0.0)
            for poi_id in lookup_ids:
                evidence[poi_id] = {**evidence.get(poi_id, {'lexical_rank':None,'dense_rank':None}), 'rrf':top+1e-6}
        return {
            "ids": ids,
            "route": "dense_first_entity" if RETRIEVAL_PROFILE == "dense_first" else "dense_only",
            "timings": timings,
            "evidence": evidence,
            "lexical_ids": lexical_ids,
            "dense_ids": dense_ids,
            "degraded_reasons": degraded,
            "branch_candidates": branch_candidates,
            "name_lookup_ids": [row['poi_id'] for row in lookup_candidates],
        }
    lexical_future = runtime.pool.submit(lambda value: branch("lexical", value), query)
    dense_failed = False
    lexical_failed = False
    began = time.perf_counter()
    try:
        vector = runtime.encode(encoder_input(query))
        timings["encode"] = (time.perf_counter() - began) * 1000
        timings.update(getattr(getattr(runtime, "local", None), "encode_timings", {}))
        dense_ids, timings["ann"] = branch("dense", vector)
    except Exception:
        dense_failed = True
        degraded.append("dense_unavailable")
        dense_ids = []
    try:
        lexical_ids, timings["lexical"] = lexical_future.result()
    except Exception:
        lexical_failed = True
        degraded.append("lexical_unavailable")
        lexical_ids = []
    if dense_failed and lexical_failed:
        raise HTTPException(503, detail={"code": "search_unavailable", "message": "No retrieval branch available"})
    began = time.perf_counter()
    if brand_family and hasattr(runtime, "brand_members"):
        members = runtime.brand_members(brand_family)
        if members:
            lexical_ids = [poi_id for poi_id in lexical_ids if poi_id in members]
            dense_ids = [poi_id for poi_id in dense_ids if poi_id in members]
    if lexical_ids and dense_ids:
        ids, evidence = _hybrid_evidence(lexical_ids, dense_ids)
        route = "dense_first_brand_exact" if brand_family else "hybrid_long_query"
    elif lexical_ids:
        ids = list(lexical_ids)
        evidence = _lexical_evidence(ids)
        route = "hybrid_dense_fallback" if dense_failed else "hybrid_long_query"
    else:
        ids = list(dense_ids)
        evidence = _dense_evidence(ids)
        route = "hybrid_lexical_fallback" if lexical_failed else "hybrid_long_query"
    timings["fusion"] = (time.perf_counter() - began) * 1000
    return {
        "ids": ids,
        "route": route,
        "timings": timings,
        "evidence": evidence,
        "lexical_ids": lexical_ids,
        "dense_ids": dense_ids,
        "degraded_reasons": degraded,
        "branch_candidates": branch_candidates,
    }


def fetch_nearby_name_rescue(query: str, anchor: dict[str, float]) -> tuple[list[str], float]:
    """Return nearby POI ids with label/alias matching query, nearest first."""
    cfg = RANKING_POLICY.get("nearby_name_rescue") or {}
    if RANKING_PROFILE != "current" or not bool(cfg.get("enabled", False)):
        return [], 0.0
    compact = compact_length(query)
    if compact < int(cfg.get("min_query_chars", 3)):
        return [], 0.0
    radius_m = float(cfg.get("radius_m", 5000))
    limit = max(1, int(cfg.get("limit", 15)))
    fetch_size = max(limit, int(cfg.get("fetch_size", 40)))
    body = nearby_name_rescue_body(query, anchor, size=fetch_size, radius_m=radius_m)
    if body is None:
        return [], 0.0
    began = time.perf_counter()
    response = runtime.client().request("POST", f"/{INDEX_NAME}/_search", body)
    elapsed = (time.perf_counter() - began) * 1000
    scored: list[tuple[float, str]] = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source") or {}
        point = source.get("ranking_point") or {}
        if point.get("lat") is None or point.get("lon") is None:
            continue
        distance = haversine(anchor, point)
        if distance > radius_m:
            continue
        doc = {
            "search_label": source.get("search_label", ""),
            "search_aliases": source.get("search_aliases") or [],
            "address": "",
            "canonical_id": hit["_id"],
        }
        # Keep exact/prefix name hits only — avoid weak cross-field noise inside bbox.
        label_fold = fold(doc["search_label"])
        q_fold = fold(query)
        aliases_fold = [fold(a) for a in doc["search_aliases"]]
        if not (
            label_fold == q_fold
            or label_fold.startswith(q_fold)
            or any(a == q_fold or a.startswith(q_fold) for a in aliases_fold)
            or name_match_class(query, doc) is not None
        ):
            continue
        scored.append((distance, hit["_id"]))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [poi_id for _, poi_id in scored[:limit]], elapsed


def pipeline_trace(
    query: str,
    *,
    origin: Origin | None,
    personalized: bool,
    top_k: int,
) -> dict[str, Any]:
    """Full suggest pipeline with stage id lists for freeze failure classification."""
    timings: dict[str, float] = {"encode": 0.0, "lexical": 0.0, "ann": 0.0, "fusion": 0.0, "nearby_rescue": 0.0}
    began = time.perf_counter()
    retrieved = retrieve_detailed(query)
    timings.update(retrieved["timings"])
    ids = list(retrieved["ids"])
    evidence = retrieved["evidence"]
    route = retrieved["route"]
    lexical_ids = list(retrieved["lexical_ids"])
    dense_ids = list(retrieved["dense_ids"])
    after_rrf = list(ids)
    after_rescue = list(ids)
    rescued_n = 0
    rescued_ids: list[str] = []
    anchor, _anchor_notes = resolve_anchor(origin) if personalized else (None, [])
    if anchor is not None:
        rescued_ids, timings["nearby_rescue"] = fetch_nearby_name_rescue(query, anchor)
        ids, evidence, rescued_n = merge_nearby_name_rescue(query, ids, evidence, rescued_ids)
        after_rescue = list(ids)
        if rescued_n:
            route = f"{route}+nearby_name_rescue:{rescued_n}"
    hydrate_start = time.perf_counter()
    documents = runtime.documents(ids)
    timings["hydrate"] = (time.perf_counter() - hydrate_start) * 1000
    document_stages = candidate_document_stages(ids, documents, dedup=RANKING_PROFILE != "raw")
    docs = document_stages["after_cap"]
    after_dedup_cap = [doc["canonical_id"] for doc in docs]
    stages = rank_candidates_traced(query, docs, evidence, anchor)
    ranked = stages["final"]
    results = _result_rows(ranked, top_k)
    timings["total"] = (time.perf_counter() - began) * 1000

    def ids_of(rows: list[tuple[float, int, float | None, dict]]) -> list[str]:
        return [doc["canonical_id"] for _, _, _, doc in rows]

    return {
        "route": route,
        "timings_ms": timings,
        "profile": RETRIEVAL_PROFILE,
        "policy_version": POLICY["policy_version"],
        "geo_mode": str(RANKING_POLICY.get("geo_mode", "v6")),
        "anchor": anchor,
        "rescued_n": rescued_n,
        "branch_candidates": retrieved.get("branch_candidates", {}),
        "encoder_input": encoder_input(query),
        "stages": {
            "lexical": lexical_ids,
            "dense": dense_ids,
            "name_lookup": retrieved.get('name_lookup_ids', []),
            "rrf": after_rrf,
            "nearby_rescue_hits": rescued_ids,
            "after_nearby_rescue": after_rescue,
            "after_dedup_cap": after_dedup_cap,
            "after_dedup": [doc["canonical_id"] for doc in document_stages["after_dedup"]],
            "after_cap": after_dedup_cap,
            "after_geo": ids_of(stages["after_geo"]),
            "after_name_address": ids_of(stages["after_name_address"]),
            "after_name_match_quality": ids_of(stages["final"]),
            "final_top_k": [row["poi_id"] for row in results],
        },
        "results": results,
        "candidate_count": len(docs),
    }


def validate_suggest_request(payload: SuggestRequest, personalized: bool) -> None:
    """Session and corpus pin. Unknown demo users are rejected on both suggest routes."""
    del personalized
    if payload.expected_corpus_version != CORPUS_VERSION:
        raise HTTPException(409, detail={"code": "corpus_version_mismatch", "message": "Corpus version mismatch"})
    if payload.session_id not in runtime.sessions:
        raise HTTPException(401, detail={"code": "invalid_session", "message": "Unknown session"})
    demo_user_id = getattr(payload, "demo_user_id", None)
    if demo_user_id is not None and not known_user(demo_user_id):
        raise HTTPException(403, detail={"code": "unknown_demo_user", "message": "demo_user_id is not in the demo registry"})


def pin_suggest_context(payload: SuggestRequest, personalized: bool) -> dict[str, Any]:
    """Request clock and history snapshot. Query-only drops origin, user, and client time."""
    request_time = datetime.now(UTC)
    if not personalized:
        return {
            "anchor": None,
            "notes": [],
            "context_time": request_time,
            "history_version": None,
            "preferred_ids": [],
            "demo_user_id": None,
        }
    context_time = getattr(payload, "context_time", None) or request_time
    anchor, notes = resolve_anchor(getattr(payload, "origin", None), now=context_time)
    demo_user_id = getattr(payload, "demo_user_id", None)
    history_version = None
    preferred_ids: list[str] = []
    if demo_user_id:
        snapshot = history_snapshot(demo_user_id, payload.session_id, context_time)
        history_version = snapshot["history_version"]
        preferred_ids = list(snapshot["poi_ids"])
    return {
        "anchor": anchor,
        "notes": notes,
        "context_time": context_time,
        "history_version": history_version,
        "preferred_ids": preferred_ids,
        "demo_user_id": demo_user_id,
    }


def persist_exposure(
    payload: SuggestRequest,
    results: list[dict[str, Any]],
    demo_user_id: str | None,
) -> str | None:
    if not results:
        return None
    exposure_id = f"exp-{uuid.uuid4()}"
    runtime.exposures[exposure_id] = {
        "session_id": payload.session_id,
        "context_revision": payload.context_revision,
        "shown_ids": [item["poi_id"] for item in results],
        "displayed": False,
        "created_at": time.time(),
        "demo_user_id": demo_user_id,
    }
    return exposure_id


def suggest(payload: SuggestRequest, personalized: bool) -> dict[str, Any]:
    validate_suggest_request(payload, personalized)
    context = pin_suggest_context(payload, personalized)
    query = " ".join(payload.query.split())
    if not query:
        return response_payload(
            payload, [], None, {}, "empty_query", personalized, None,
            history_version=context["history_version"],
            context_notes=context["notes"],
            resolved_time=context["context_time"],
        )
    began = time.perf_counter()
    retrieved = retrieve_detailed(query)
    ids = list(retrieved["ids"])
    route = retrieved["route"]
    timings = dict(retrieved["timings"])
    evidence = retrieved["evidence"]
    anchor = context["anchor"]
    rescued_n = 0
    if anchor is not None:
        rescued_ids, timings["nearby_rescue"] = fetch_nearby_name_rescue(query, anchor)
        ids, evidence, rescued_n = merge_nearby_name_rescue(query, ids, evidence, rescued_ids)
        if rescued_n:
            route = f"{route}+nearby_name_rescue:{rescued_n}"
    hydrate_start = time.perf_counter()
    documents = runtime.documents(ids)
    timings["hydrate"] = (time.perf_counter() - hydrate_start) * 1000
    rank_start = time.perf_counter()
    docs = candidate_documents(ids, documents)
    ranked = rank_candidates(query, docs, evidence, anchor)
    timings["ranking"] = (time.perf_counter() - rank_start) * 1000
    if context["preferred_ids"]:
        ranked = apply_history_cohort(query, ranked, context["preferred_ids"])
    results = _result_rows(ranked, payload.top_k)
    timings["total"] = (time.perf_counter() - began) * 1000
    exposure_id = persist_exposure(payload, results, context["demo_user_id"])
    return response_payload(
        payload, results, exposure_id, timings, route, personalized, anchor, len(docs),
        history_version=context["history_version"],
        degraded_reasons=list(retrieved.get("degraded_reasons") or []),
        context_notes=context["notes"],
        resolved_time=context["context_time"],
    )


def response_payload(payload: SuggestRequest, results: list[dict], exposure_id: str | None,
                     timings: dict, route: str, personalized: bool, anchor: dict | None, candidate_count: int = 0,
                     *, history_version: str | None = None, degraded_reasons: list[str] | None = None,
                     context_notes: list[str] | None = None, resolved_time: datetime | None = None) -> dict[str, Any]:
    moment = resolved_time or datetime.now(UTC)
    notes = [route, *(context_notes or [])]
    if personalized and history_version:
        notes.append(f"demo history {history_version}")
    elif personalized:
        ranking_description = "geo heuristic" if RANKING_PROFILE == "current" else f"{RANKING_PROFILE} ranking; geo disabled"
        notes.append(
            f"Ranking policy {POLICY['policy_version']}: {RETRIEVAL_PROFILE}, {ranking_description}; no learned ranker"
        )
    else:
        notes.append("query-only fixed global scope")
    if personalized and anchor is not None and RANKING_PROFILE != 'current':
        notes.append('origin_not_applied_by_ranking_profile')
    return {
        "request_id": payload.request_id, "context_revision": payload.context_revision,
        "exposure_id": exposure_id, "selectable": exposure_id is not None, "versions": versions(),
        "scope_summary": {
            "mode": "global_with_geo_heuristic" if personalized and anchor and RANKING_PROFILE == 'current' else "global",
            "coverage_id": CORPUS_VERSION, "primary_region_id": None,
            "primary_radius_m": None,
            "notes": notes,
        },
        "resolved_context_time": moment.isoformat(),
        "history_version": history_version, "candidate_count": candidate_count, "results": results,
        "degraded_reasons": list(degraded_reasons or []), "timings_ms": timings,
    }


def _build_map_geojson() -> dict[str, Any]:
    """Load the searchable catalog once for the MapLibre clustered source."""
    features: list[dict[str, Any]] = []
    search_after: list[Any] | None = None
    page_size = 10_000

    while True:
        body: dict[str, Any] = {
            "size": page_size,
            "track_total_hits": False,
            "sort": [{"canonical_id": {"order": "asc"}}],
            "_source": ["canonical_id", "search_label", "address", "ranking_point"],
            "query": {"bool": {"filter": [{"term": {"destination_searchable": True}}]}},
        }
        if search_after is not None:
            body["search_after"] = search_after
        response = runtime.client().request("POST", f"/{INDEX_NAME}/_search", body)
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            break
        for hit in hits:
            source = hit.get("_source") or {}
            point = source.get("ranking_point") or {}
            lat, lon = point.get("lat"), point.get("lon")
            if lat is None or lon is None:
                continue
            features.append({
                "type": "Feature",
                "id": hit.get("_id"),
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "poi_id": source.get("canonical_id") or hit.get("_id"),
                    "name": source.get("search_label") or "",
                    "address": source.get("address") or "",
                },
            })
        if len(hits) < page_size:
            break
        search_after = hits[-1].get("sort")
        if not search_after:
            break

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {"corpus_version": CORPUS_VERSION, "count": len(features)},
    }
