"""Explicit point-to-point OSRM routes; never inferred from transport density."""
import asyncio
from collections import OrderedDict
import copy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import os
import time
from urllib.parse import urlsplit

import httpx
from pyproj import Geod

DEFAULT_BASE_URL = "https://routing.openstreetmap.de"
USER_AGENT = "UrbanLens-Warsaw/1.0 (https://github.com/MityaiLentyai/Club_Imperium)"
CACHE_TTL = 86400
CACHE_LIMIT = 128
MAX_BYTES = 1_000_000
QUEUE_TIMEOUT = 2.0
_cache = OrderedDict()
_lock = asyncio.Lock()
_last_request = 0.0
_cooldown_until = 0.0


def baseline(origin, destination):
    _, _, distance = Geod(ellps="WGS84").inv(origin.longitude, origin.latitude, destination.longitude, destination.latitude)
    return round(distance, 1)


def parse_route(payload):
    if not isinstance(payload, dict) or payload.get("code") != "Ok":
        raise ValueError("Route unavailable")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
        raise ValueError("No route")
    route = routes[0]
    distance, seconds = route.get("distance"), route.get("duration")
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in (distance, seconds)):
        raise ValueError("Invalid route measurements")
    geometry = route.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
        raise ValueError("Invalid route geometry")
    coords = geometry.get("coordinates")
    if (not isinstance(coords, list) or not 2 <= len(coords) <= 10000
            or any(not isinstance(p, list) or len(p) != 2 or
                   any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                   or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in coords)):
        raise ValueError("Invalid route coordinates")
    waypoints = payload.get("waypoints")
    if (not isinstance(waypoints, list) or len(waypoints) != 2 or any(
            not isinstance(w, dict) or type(w.get("distance")) not in (float, int)
            or not math.isfinite(w["distance"]) or not 0 <= w["distance"] <= 100 for w in waypoints)):
        raise ValueError("Route endpoints snapped too far from selected points")
    return {"status": "available", "distance_m": round(distance, 1),
            "duration_minutes": round(seconds / 60, 1), "geometry": geometry,
            "snap_distances_m": [round(w["distance"], 1) for w in waypoints],
            "duration_type": "provider_estimate", "traffic": "not_live"}


async def _fetch_route(client, base_url, origin, destination, profile):
    global _last_request, _cooldown_until
    path, mode = ("routed-foot", "foot") if profile == "walking" else ("routed-car", "driving")
    coordinates = f"{origin.longitude:.6f},{origin.latitude:.6f};{destination.longitude:.6f},{destination.latitude:.6f}"
    url = f"{base_url}/{path}/route/v1/{mode}/{coordinates}"
    delay = 1.1 - (time.monotonic() - _last_request)
    if delay > 0:
        await asyncio.sleep(delay)
    _last_request = time.monotonic()
    async with client.stream("GET", url, params={"overview": "simplified", "geometries": "geojson",
            "steps": "false", "radiuses": "100;100"}, headers={"User-Agent": USER_AGENT}) as response:
        if response.status_code == 429:
            try:
                seconds = float(response.headers.get("Retry-After", "60"))
                seconds = max(60, min(seconds, 3600)) if math.isfinite(seconds) else 60
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(response.headers["Retry-After"])
                    seconds = max(60, (retry_at - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError, KeyError, OverflowError):
                    seconds = 60
            _cooldown_until = time.monotonic() + seconds
        response.raise_for_status()
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("Route response too large")
            chunks.append(chunk)
        import json
        result = parse_route(json.loads(b"".join(chunks)))
        result.update(retrieved_at=datetime.now(timezone.utc).isoformat(),
                      provider="FOSSGIS OSRM / OpenStreetMap" if base_url == DEFAULT_BASE_URL else "Configured OSRM / OpenStreetMap", provider_url=base_url)
        return result


async def get_commute(origin, destination, *, include_routes=True):
    result = {"origin": origin.model_dump(), "destination": destination.model_dump(),
              "baseline": {"distance_m": baseline(origin, destination), "distance_type": "straight_line"},
              "transit": {"status": "unavailable", "reason": "No verified timetable and transit routing service configured"},
              "attribution": {"name": "FOSSGIS OSRM / © OpenStreetMap contributors",
                              "url": "https://routing.openstreetmap.de/about.html",
                              "fix_map_url": "https://www.openstreetmap.org/fixthemap"}}
    base = os.getenv("ROUTING_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not include_routes or not base or os.getenv("ROUTING_ENABLED", "true").lower() != "true":
        reason = "Routes not requested" if not include_routes else "Routing disabled"
        result.update({mode: {"status": "unavailable", "reason": reason} for mode in ("walking", "driving")})
        return result
    try:
        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Invalid provider configuration")
    except ValueError:
        result.update({mode: {"status": "unavailable", "reason": "Routing provider configuration is invalid"} for mode in ("walking", "driving")})
        return result
    if base != DEFAULT_BASE_URL:
        result["attribution"].update(name="Configured OSRM / © OpenStreetMap contributors", url=base)
    try:
        await asyncio.wait_for(_lock.acquire(), timeout=QUEUE_TIMEOUT)
    except TimeoutError:
        result.update({mode: {"status": "unavailable", "reason": "Routing queue busy; retry later"} for mode in ("walking", "driving")})
        return result
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            for mode in ("walking", "driving"):
                key = (base, origin.latitude, origin.longitude, destination.latitude, destination.longitude, mode)
                cached = _cache.get(key)
                now = time.monotonic()
                if cached and now - cached[0] < (CACHE_TTL if cached[1]["status"] == "available" else 60):
                    _cache.move_to_end(key)
                    result[mode] = {**copy.deepcopy(cached[1]), "cached": True}
                    continue
                try:
                    if time.monotonic() < _cooldown_until:
                        raise ValueError("Provider rate limit cooldown")
                    # One request per profile, no retries; bound total time as well as HTTP phases.
                    route = await asyncio.wait_for(_fetch_route(client, base, origin, destination, mode), timeout=10)
                except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError):
                    route = {"status": "unavailable", "reason": "Routing provider unavailable or no verified route"}
                _cache[key] = (time.monotonic(), copy.deepcopy(route))
                _cache.move_to_end(key)
                while len(_cache) > CACHE_LIMIT:
                    _cache.popitem(last=False)
                result[mode] = {**route, "cached": False}
    finally:
        _lock.release()
    return result
