
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import ScoreRequest
from backend.services.scoring_service import get_location_score
from backend.services.geocoding_service import geocode_address
from backend.schemas import ScoreRequest, AddressScoreRequest
app = FastAPI(
    title="Warsaw LifeScore API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
async def geocode_location(address: str):
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

