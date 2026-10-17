from starlette.concurrency import run_in_threadpool

import os
from typing import Annotated

from fastapi import FastAPI, Query
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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

