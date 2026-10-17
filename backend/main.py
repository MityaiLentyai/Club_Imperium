
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import ScoreRequest
from backend.services.scoring_service import get_location_score


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
