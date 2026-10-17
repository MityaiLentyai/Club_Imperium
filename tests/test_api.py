
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


@pytest.mark.parametrize("latitude,longitude", [
    (0, 111), (0, -69), (50.06, 19.94),
    (51.999, 21.0), (52.401, 21.0), (52.2, 20.749), (52.2, 21.301),
])
def test_unsupported_service_coordinates(latitude, longitude):
    with patch("backend.main.get_location_score") as score:
        response = client.post("/api/score", json={"latitude": latitude, "longitude": longitude})
    assert response.status_code == 422
    assert "Warsaw service area" in response.json()["detail"]
    score.assert_not_called()


@pytest.mark.parametrize("axis", ["latitude", "longitude"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_coordinate_strings(axis, value):
    coordinates = {"latitude": 52.2297, "longitude": 21.0122, axis: value}
    response = client.post("/api/score", json=coordinates)
    assert response.status_code == 422
    assert "finite" in response.json()["detail"]


@pytest.mark.parametrize("axis", ["latitude", "longitude"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_non_finite_json_numbers(axis, value):
    # Raw JSON also exercises Python's acceptance of non-standard numeric tokens.
    other = '"longitude":21.0122' if axis == "latitude" else '"latitude":52.2297'
    response = client.post("/api/score", content='{"' + axis + '":' + value + ',' + other + '}',
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "finite" in response.json()["detail"]


@pytest.mark.parametrize("latitude,longitude", [
    (52.2297, 21.0122),  # central Warsaw
    (52.1589611, 21.0317969),  # existing Ursynów example
    (52.35, 20.97),  # northern service area
    (52.22, 21.25),  # eastern service area
    (52.09, 21.1),  # southern service area
    (52.2, 20.87),  # western service area
    (52.0, 20.75), (52.4, 21.3),  # inclusive service-envelope corners
])
def test_warsaw_coordinates_preserve_response(latitude, longitude):
    response = client.post("/api/score", json={"latitude": latitude, "longitude": longitude})
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"location", "scores", "features"}
    assert data["location"] == {"latitude": latitude, "longitude": longitude}
    assert 0 <= data["scores"]["mobility"] <= 100
    assert data["features"]["nearest_stop_m"] >= 0


@pytest.mark.parametrize("failure", ["projection", "overflow", "nonfinite"])
@pytest.mark.parametrize("endpoint", ["/api/score", "/api/score/address"])
def test_scoring_projection_failures(endpoint, failure):
    from pyproj.exceptions import ProjError

    location = {"address": "Warszawa", "latitude": 52.2297, "longitude": 21.0122}
    body = {"address": "Warszawa"} if endpoint.endswith("address") else {
        "latitude": location["latitude"], "longitude": location["longitude"]}
    with patch("backend.main.geocode_address", new=AsyncMock(return_value=location)), patch(
        "backend.services.scoring_service.calculate_mobility_features"
    ) as features:
        if failure == "nonfinite":
            features.return_value = {"nearest_stop_m": float("inf"), "stop_groups_500m": 0, "stop_groups_1000m": 0}
        else:
            features.side_effect = ProjError("projection failed") if failure == "projection" else OverflowError()
        response = client.post(endpoint, json=body)
    assert response.status_code == 422
    assert "Warsaw scoring" in response.json()["detail"]


@pytest.mark.parametrize("latitude,longitude", [(0, 111), (float("nan"), 21.0), (52.2, float("inf"))])
def test_address_scoring_rechecks_resolved_coordinates(latitude, longitude):
    location = {"address": "Bad provider result", "latitude": latitude, "longitude": longitude}
    with patch("backend.main.geocode_address", new=AsyncMock(return_value=location)), patch(
        "backend.services.scoring_service.get_stops"
    ) as stops:
        response = client.post("/api/score/address", json={"address": "Warszawa"})
    assert response.status_code == 422
    stops.assert_not_called()
