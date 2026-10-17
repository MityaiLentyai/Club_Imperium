
import os

import httpx
from fastapi import HTTPException



GEOCODING_URL = "https://nominatim.openstreetmap.org/search"


async def geocode_address(address: str):
    headers = {
        "User-Agent": os.getenv(
            "GEOCODING_USER_AGENT",
            "WarsawLifeScore/0.1 (student hackathon project)",
        )
    }

    params = {
        "q": f"{address}, Warszawa, Poland",
        "format": "jsonv2",
        "limit": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GEOCODING_URL,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="Geocoding service unavailable",
        ) from exc

    results = response.json()

    if not results:
        raise HTTPException(
            status_code=404,
            detail="Address not found",
        )

    result = results[0]

    return {
        "address": result["display_name"],
        "latitude": float(result["lat"]),
        "longitude": float(result["lon"]),
    }
