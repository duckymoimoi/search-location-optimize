"""HTTP request models for the demo API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Point(StrictModel):
    model_config = ConfigDict(extra="ignore")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Origin(StrictModel):
    kind: Literal["poi", "gps", "map"]
    poi_id: str | None = None
    point: Point | None = None
    accuracy_m: float | None = None
    observed_at: datetime | None = None


class SuggestRequest(StrictModel):
    request_id: str
    session_id: str
    context_revision: int = Field(ge=1)
    query: str = Field(max_length=200)
    top_k: int = Field(default=5, ge=1, le=50)
    expected_corpus_version: str
    search_kind: str | None = None
    origin: Origin | None = None
    demo_user_id: str | None = None
    context_time: datetime | None = None
    preferred_region_id: str | None = None


class DisplayRequest(StrictModel):
    session_id: str
    exposure_id: str
    context_revision: int


class SelectRequest(DisplayRequest):
    selected_poi_id: str
    idempotency_key: str


class RouteRequest(StrictModel):
    corpus_version: str
    origin_poi_id: str | None = None
    destination_poi_id: str | None = None
    origin_point: Point | None = None
    destination_point: Point | None = None
    mode: Literal["straight_line", "road"] = "straight_line"
    vehicle: Literal["car", "bike", "taxi", "truck", "hd"] = "car"
    allow_fallback: bool = False


class TraceSuggestRequest(StrictModel):
    request_id: str
    session_id: str
    context_revision: int = Field(ge=1)
    query: str = Field(max_length=200)
    top_k: int = Field(default=50, ge=1, le=50)
    expected_corpus_version: str
    personalized: bool = False
    origin: Origin | None = None
    target_poi_id: str | None = None
