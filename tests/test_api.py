
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_score():
    response = client.post(
        "/api/score",
        json={
            "latitude": 52.2297,
            "longitude": 21.0122,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert 0 <= data["scores"]["mobility"] <= 100
    assert data["features"]["nearest_stop_m"] >= 0


def test_invalid_coordinates():
    response = client.post(
        "/api/score",
        json={
            "latitude": 100,
            "longitude": 21.0122,
        },
    )

    assert response.status_code == 422
