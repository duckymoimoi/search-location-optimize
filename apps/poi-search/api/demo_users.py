"""In-app demo user registry. History stays server-side; fixtures are not overwritten."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any

FIXTURE_VERSION = "demo-history-v1"

# poi_id values already used by the geo scenario set in this app.
_USERS: list[dict[str, Any]] = [
    {
        "demo_user_id": "demo-cold",
        "label": "Người mới — chưa có lịch sử",
        "events": [],
    },
    {
        "demo_user_id": "demo-repeat",
        "label": "Hay chọn Tiểu học Đại Hưng",
        "events": [
            {"poi_id": "osm:way/1386515333", "occurred_at": "2026-01-15T02:00:00+00:00"},
            {"poi_id": "osm:node/10621408635", "occurred_at": "2025-11-02T03:30:00+00:00"},
        ],
    },
    {
        "demo_user_id": "demo-session",
        "label": "Chỉ nhớ lựa chọn trong phiên",
        "events": [],
    },
]

_lock = Lock()
_live: dict[tuple[str, str], list[dict[str, str]]] = {}


def public_users() -> list[dict[str, str]]:
    """Registry for the demo panel. No history payload."""
    return [{"demo_user_id": user["demo_user_id"], "label": user["label"]} for user in _USERS]


def known_user(user_id: str) -> bool:
    return any(user["demo_user_id"] == user_id for user in _USERS)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def history_snapshot(user_id: str, session_id: str, cutoff: datetime) -> dict[str, Any]:
    """Fixture events plus this session's selections, at or before cutoff.

    Most recent poi_id first. A poi absent from the current candidate set is
    ignored by the caller; this snapshot does not join on name.
    """
    user = next(item for item in _USERS if item["demo_user_id"] == user_id)
    cutoff_utc = _parse_time(cutoff)
    with _lock:
        live = list(_live.get((session_id, user_id), []))
    kept: list[tuple[datetime, str]] = []
    for event in [*user["events"], *live]:
        moment = _parse_time(event["occurred_at"])
        if moment <= cutoff_utc:
            kept.append((moment, event["poi_id"]))
    kept.sort(key=lambda item: item[0], reverse=True)
    poi_ids: list[str] = []
    for _, poi_id in kept:
        if poi_id not in poi_ids:
            poi_ids.append(poi_id)
    return {
        "history_version": f"{FIXTURE_VERSION}:{user_id}:live-{len(live)}",
        "poi_ids": poi_ids,
    }


def append_selection(session_id: str, user_id: str, poi_id: str, occurred_at: datetime) -> str:
    """Append one live selection. Does not mutate the fixture event list."""
    if not known_user(user_id):
        raise KeyError(user_id)
    event = {"poi_id": poi_id, "occurred_at": _parse_time(occurred_at).isoformat()}
    with _lock:
        bucket = _live.setdefault((session_id, user_id), [])
        bucket.append(event)
        live_count = len(bucket)
    return f"{FIXTURE_VERSION}:{user_id}:live-{live_count}"
