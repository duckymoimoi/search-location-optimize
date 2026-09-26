"""Distance, polyline, and Goong Directions helpers."""
from __future__ import annotations

import json
import math
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from settings import GOONG_API_KEY, GOONG_DIRECTION_URL

def haversine(left: dict[str, float], right: dict[str, float]) -> float:
    radius = 6_371_008.8
    lat1, lat2 = math.radians(left["lat"]), math.radians(right["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(right["lon"] - left["lon"])
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def decode_polyline(encoded: str) -> list[list[float]]:
    """Decode Google/Goong encoded polyline into [lon, lat] coordinates."""
    coordinates: list[list[float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    while index < length:
        result = 0
        shift = 0
        while True:
            value = ord(encoded[index]) - 63
            index += 1
            result |= (value & 0x1F) << shift
            shift += 5
            if value < 0x20:
                break
        delta_lat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += delta_lat

        result = 0
        shift = 0
        while True:
            value = ord(encoded[index]) - 63
            index += 1
            result |= (value & 0x1F) << shift
            shift += 5
            if value < 0x20:
                break
        delta_lon = ~(result >> 1) if result & 1 else (result >> 1)
        lon += delta_lon
        coordinates.append([lon / 1e5, lat / 1e5])
    return coordinates


def goong_directions(origin: dict[str, float], destination: dict[str, float], vehicle: str) -> dict[str, Any]:
    if not GOONG_API_KEY:
        raise RuntimeError("goong_api_key_missing")
    query = urlencode(
        {
            "origin": f"{origin['lat']},{origin['lon']}",
            "destination": f"{destination['lat']},{destination['lon']}",
            "vehicle": vehicle,
            "api_key": GOONG_API_KEY,
        }
    )
    request = UrlRequest(
        f"{GOONG_DIRECTION_URL}?{query}",
        headers={
            # Cloudflare rejects Python-urllib's default UA (error 1010).
            "User-Agent": "poi-search-api/0.1 (+https://localhost; Goong Directions)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"goong_http_{exc.code}:{body or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"goong_network:{exc.reason}") from exc
    routes = payload.get("routes") or []
    if not routes:
        raise RuntimeError("goong_no_route")
    route = routes[0]
    legs = route.get("legs") or []
    if not legs:
        raise RuntimeError("goong_no_legs")
    encoded = ((route.get("overview_polyline") or {}).get("points")) or ""
    if not encoded:
        raise RuntimeError("goong_missing_polyline")
    coordinates = decode_polyline(encoded)
    if len(coordinates) < 2:
        raise RuntimeError("goong_polyline_too_short")
    return {
        "coordinates": coordinates,
        "distance_m": int((legs[0].get("distance") or {}).get("value") or 0),
        "duration_s": int((legs[0].get("duration") or {}).get("value") or 0),
    }
