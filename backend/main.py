from starlette.concurrency import run_in_threadpool

import logging
import os
import math
import re
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import Address, AddressScoreRequest, ScoreRequest, CommuteRequest, ComparisonRequest
from backend.services.geocoding_service import geocode_address
from backend.services.scoring_service import get_location_score
from backend.services.routing_service import get_commute
from backend.services.comparison_service import get_comparison


app = FastAPI(
    title="Warsaw LifeScore API",
    version="0.2.0",
)

def cors_settings(environ=os.environ):
    """Read allowed browser origins from CORS_ORIGINS and optional CORS_ORIGIN_REGEX.

    Browsers send the Origin header without a trailing slash or quotes, so values pasted
    from the address bar ("https://site.vercel.app/") or quoted in a dashboard are
    normalized instead of silently rejecting every request. The regex covers deployments
    with generated hostnames, such as Vercel previews.
    """
    origins = []
    for item in environ.get("CORS_ORIGINS", "http://localhost:5173").split(","):
        origin = item.strip().strip("\"'").strip().rstrip("/")
        if origin:
            origins.append(origin)
    regex = environ.get("CORS_ORIGIN_REGEX", "").strip().strip("\"'").strip() or None
    if regex is not None:
        re.compile(regex)  # fail at startup rather than on the first request
    return origins, regex


CORS_ALLOWED_ORIGINS, CORS_ALLOWED_ORIGIN_REGEX = cors_settings()
# Visible in the hosting provider's logs, so a mismatched origin is easy to spot.
logging.getLogger("uvicorn.error").info(
    "CORS allowed origins: %s; origin regex: %s", CORS_ALLOWED_ORIGINS, CORS_ALLOWED_ORIGIN_REGEX
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ALLOWED_ORIGIN_REGEX,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_response(request, exc):
    # Python's JSON parser accepts NaN/Infinity, but JSONResponse rejects them.
    # Preserve the standard 422 detail structure with JSON-safe error inputs.
    detail = jsonable_encoder(
        exc.errors(), custom_encoder={float: lambda value: value if math.isfinite(value) else str(value)}
    )
    return JSONResponse(status_code=422, content={"detail": detail})


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/score")
def score_location(request: ScoreRequest):
    return get_location_score(
        request.latitude,
        request.longitude,
        request.radius_m,
        weights=request.weights,
    )


@app.get("/api/geocode")
async def geocode_location(address: Annotated[Address, Query()]):
    return await geocode_address(address)


@app.post("/api/score/address")
async def score_address(request: AddressScoreRequest):
    location = await geocode_address(request.address)

    result = await run_in_threadpool(
        get_location_score,
        location["latitude"],
        location["longitude"],
        request.radius_m,
        weights=request.weights,
    )

    result["location"]["address"] = location["address"]

    return result


@app.post("/api/commute")
async def commute(request: CommuteRequest):
    return await get_commute(request.origin, request.destination)


@app.post("/api/compare")
async def compare_locations(request: ComparisonRequest):
    return await get_comparison(request)

