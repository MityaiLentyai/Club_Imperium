import re

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


def test_cors_origins_are_normalized():
    from backend.main import cors_settings
    origins, regex = cors_settings({
        "CORS_ORIGINS": ' https://club-imperium-qrbl.vercel.app/ , "http://localhost:5173",,',
    })
    assert origins == ["https://club-imperium-qrbl.vercel.app", "http://localhost:5173"]
    assert regex is None


def test_cors_defaults_to_local_frontend():
    from backend.main import cors_settings
    assert cors_settings({}) == (["http://localhost:5173"], None)


def test_cors_preflight_with_dashboard_style_values():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from backend.main import cors_settings

    origins, regex = cors_settings({
        "CORS_ORIGINS": "https://club-imperium-qrbl.vercel.app/",
        "CORS_ORIGIN_REGEX": r"^https://club-imperium-qrbl(-[a-z0-9-]+)?\.vercel\.app$",
    })
    probe = FastAPI()
    probe.add_middleware(CORSMiddleware, allow_origins=origins, allow_origin_regex=regex,
                         allow_methods=["GET", "POST"], allow_headers=["*"])
    probe_client = TestClient(probe)

    def preflight(origin):
        return probe_client.options("/api/score", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })

    for origin in ("https://club-imperium-qrbl.vercel.app",
                   "https://club-imperium-qrbl-git-main-team.vercel.app"):
        response = preflight(origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
    assert preflight("https://evil.example").status_code == 400


def test_invalid_cors_regex_fails_fast():
    from backend.main import cors_settings
    with pytest.raises(re.error):
        cors_settings({"CORS_ORIGIN_REGEX": "("})


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
    (52.12, 21.08),  # southern Warsaw within official boundary
    (52.2, 20.87),  # western service area
])
def test_warsaw_coordinates_preserve_response(latitude, longitude):
    response = client.post("/api/score", json={"latitude": latitude, "longitude": longitude})
    assert response.status_code == 200
    data = response.json()
    assert {"location", "scores", "features"} <= set(data)
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
