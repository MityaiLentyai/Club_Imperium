
import asyncio
import math
import os
import time
from collections import OrderedDict

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from data_science.address_lookup import lookup as lookup_address, parse_query, building_key
from data_science.geography import membership, DISTRICTS


GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

CACHE_MAXSIZE = 500
CACHE_TTL = 24 * 60 * 60

_cache = OrderedDict()
_request_lock = asyncio.Lock()
_last_request_time = 0.0


def _cached_result(result):
    if result is None:
        raise HTTPException(status_code=404, detail="Address not found in Warsaw")
    return result.copy()


def _save_result(key, result):
    _cache[key] = (time.monotonic(), result.copy() if result else None)
    _cache.move_to_end(key)
    if len(_cache) > CACHE_MAXSIZE:
        _cache.popitem(last=False)


async def geocode_address(address: str):
    global _last_request_time

    address = " ".join(address.strip().split())
    if not 3 <= len(address) <= 300:
        raise HTTPException(
            status_code=422,
            detail="Address must contain between 3 and 300 characters",
        )

    parsed = parse_query(address)
    if parsed is None:
        raise HTTPException(status_code=422, detail="Include a street and building number, or select a map point")
    local = await run_in_threadpool(lookup_address, address)
    if local["status"] == "invalid_address":
        raise HTTPException(status_code=422, detail="Include a street and building number, or select a map point")
    if local["status"] == "ambiguous":
        raise HTTPException(status_code=422, detail="Address is ambiguous; include the district or select a map point")
    if local["status"] == "found":
        result = local["result"]
        if membership(result["latitude"], result["longitude"])[0]:
            return result.copy()

    cache_key = address.casefold()
    now = time.monotonic()

    cached = _cache.get(cache_key)
    if cached is not None:
        timestamp, result = cached
        if now - timestamp < CACHE_TTL:
            _cache.move_to_end(cache_key)
            return _cached_result(result)
        del _cache[cache_key]

    async with _request_lock:
        # Check again: another request may have filled the cache.
        cached = _cache.get(cache_key)
        now = time.monotonic()

        if cached is not None:
            timestamp, result = cached
            if now - timestamp < CACHE_TTL:
                _cache.move_to_end(cache_key)
                return _cached_result(result)
            del _cache[cache_key]

        user_agent = os.getenv("GEOCODING_USER_AGENT", "").strip()
        if not user_agent:
            raise HTTPException(
                status_code=503, detail="Geocoding is not configured"
            )

        elapsed = time.monotonic() - _last_request_time
        if _last_request_time and elapsed < 1.1:
            await asyncio.sleep(1.1 - elapsed)

        headers = {
            "User-Agent": user_agent,
        }

        params = {
            "q": f"{address}, Warszawa, Poland",
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "pl",
            "addressdetails": 1,
            "viewbox": "20.75,52.4,21.3,52.0",
            "bounded": 1,
        }

        # Reserve the request slot before the network call.
        _last_request_time = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    os.getenv("GEOCODING_URL", GEOCODING_URL),
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                results = response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=504, detail="Geocoding service timed out"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Geocoding service unavailable",
            ) from exc

        try:
            if not isinstance(results, list):
                raise ValueError("Expected a list")
            result = None
            if results:
                first = results[0]
                latitude, longitude = float(first["lat"]), float(first["lon"])
                display_name = first["display_name"]
                if not (math.isfinite(latitude) and math.isfinite(longitude)):
                    raise ValueError("Non-finite coordinates")
                if not isinstance(display_name, str) or not display_name.strip():
                    raise ValueError("Missing display name")
                details = first.get("address", {})
                city = next(
                    (details[k] for k in ("city", "town", "village") if details.get(k)),
                    None,
                )
                in_warsaw = (
                    membership(latitude, longitude)[0]
                    and details.get("country_code", "pl").casefold() == "pl"
                    and (city is None or city.casefold() in {"warszawa", "warsaw"} | {d.casefold() for d in DISTRICTS})
                    and isinstance(details.get("house_number"), str)
                    and building_key(details["house_number"]) == parsed["building"]
                )
                if in_warsaw:
                    result = {
                        "address": display_name,
                        "latitude": latitude,
                        "longitude": longitude,
                    }
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise HTTPException(
                status_code=502, detail="Invalid response from geocoding service"
            ) from exc

        _save_result(cache_key, result)
        return _cached_result(result)
