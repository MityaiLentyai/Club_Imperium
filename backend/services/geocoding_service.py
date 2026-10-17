
import asyncio
import os
import time
from collections import OrderedDict

import httpx
from fastapi import HTTPException


GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

CACHE_MAXSIZE = 500
CACHE_TTL = 24 * 60 * 60

_cache = OrderedDict()
_request_lock = asyncio.Lock()
_last_request_time = 0.0


async def geocode_address(address: str):
    global _last_request_time

    address = " ".join(address.strip().split())
    if not address:
        raise HTTPException(
            status_code=422,
            detail="Address cannot be empty",
        )

    cache_key = address.casefold()
    now = time.monotonic()

    cached = _cache.get(cache_key)
    if cached is not None:
        timestamp, result = cached
        if now - timestamp < CACHE_TTL:
            _cache.move_to_end(cache_key)
            return result.copy()
        del _cache[cache_key]

    async with _request_lock:
        # Check again: another request may have filled the cache.
        cached = _cache.get(cache_key)
        now = time.monotonic()

        if cached is not None:
            timestamp, result = cached
            if now - timestamp < CACHE_TTL:
                _cache.move_to_end(cache_key)
                return result.copy()
            del _cache[cache_key]

        elapsed = time.monotonic() - _last_request_time
        if _last_request_time and elapsed < 1.1:
            await asyncio.sleep(1.1 - elapsed)

        headers = {
            "User-Agent": os.environ["GEOCODING_USER_AGENT"],
        }

        params = {
            "q": f"{address}, Warszawa, Poland",
            "format": "jsonv2",
            "limit": 1,
        }

        # Reserve the request slot before the network call.
        _last_request_time = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    GEOCODING_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                results = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Geocoding service unavailable",
            ) from exc

        if not results:
            raise HTTPException(
                status_code=404,
                detail="Address not found",
            )

        first = results[0]
        result = {
            "address": first["display_name"],
            "latitude": float(first["lat"]),
            "longitude": float(first["lon"]),
        }

        _cache[cache_key] = (time.monotonic(), result.copy())
        _cache.move_to_end(cache_key)

        if len(_cache) > CACHE_MAXSIZE:
            _cache.popitem(last=False)

        return result
