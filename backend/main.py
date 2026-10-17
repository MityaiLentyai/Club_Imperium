
import os
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import Address, AddressScoreRequest, ScoreRequest
from backend.services.geocoding_service import geocode_address
from backend.services.scoring_service import get_location_score


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
    )


@app.get("/api/geocode")
async def geocode_location(address: Annotated[Address, Query()]):
    return await geocode_address(address)


@app.post("/api/score/address")
async def score_address(request: AddressScoreRequest):
    location = await geocode_address(request.address)

    result = get_location_score(
        location["latitude"],
        location["longitude"],
    )

    result["location"]["address"] = location["address"]

    return result

