
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


import pytest
from fastapi import HTTPException


@pytest.mark.parametrize("address", ["", "   ", " A ", "x" * 301])
def test_invalid_addresses_on_both_routes(address):
    assert client.get("/api/geocode", params={"address": address}).status_code == 422
    assert client.post("/api/score/address", json={"address": address}).status_code == 422


def test_geocode_success():
    location = {"address": "Warszawa", "latitude": 52.2297, "longitude": 21.0122}
    with patch("backend.main.geocode_address", new=AsyncMock(return_value=location)):
        response = client.get("/api/geocode", params={"address": "Marszałkowska 1"})
    assert response.status_code == 200
    assert response.json() == location


@pytest.mark.parametrize("status", [404, 502, 503, 504])
def test_geocoding_errors_on_both_routes(status):
    with patch("backend.main.geocode_address", new=AsyncMock(side_effect=HTTPException(status, "Geocoding error"))):
        responses = [
            client.get("/api/geocode", params={"address": "Unknown address"}),
            client.post("/api/score/address", json={"address": "Unknown address"}),
        ]
    for response in responses:
        assert response.status_code == status
        assert response.json() == {"detail": "Geocoding error"}


@pytest.mark.parametrize("body", [
    {"latitude": -91, "longitude": 21},
    {"latitude": 52, "longitude": 181},
    {"latitude": 52, "longitude": -181},
    {"latitude": "NaN", "longitude": 21},
    {"latitude": 52},
])
def test_invalid_coordinate_inputs(body):
    assert client.post("/api/score", json=body).status_code == 422


def test_react_cors_preflight():
    response = client.options("/api/score", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_dataset_path_independent_of_cwd(tmp_path, monkeypatch):
    from data_science.data_loader import load_stops
    monkeypatch.chdir(tmp_path)
    assert not load_stops().empty
