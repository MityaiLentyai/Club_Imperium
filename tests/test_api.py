
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

from unittest.mock import AsyncMock, patch


def test_score_by_address():
    fake_location = {
        "address": "Stokłosy 7, Warszawa",
        "latitude": 52.1589611,
        "longitude": 21.0317969,
    }

    with patch(
        "backend.main.geocode_address",
        new_callable=AsyncMock,
        return_value=fake_location,
    ) as mock_geocode:
        response = client.post(
            "/api/score/address",
            json={"address": "Stokłosy 7"},
        )

    assert response.status_code == 200

    data = response.json()

    assert data["location"]["address"] == fake_location["address"]
    assert data["location"]["latitude"] == fake_location["latitude"]
    assert 0 <= data["scores"]["mobility"] <= 100
    assert "nearest_stop_m" in data["features"]

    mock_geocode.assert_awaited_once_with("Stokłosy 7")


def test_short_address():
    response = client.post(
        "/api/score/address",
        json={"address": "A"},
    )

    assert response.status_code == 422
