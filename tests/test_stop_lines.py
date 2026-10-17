import json
from pathlib import Path

import geopandas as gpd
import httpx
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from backend.main import app
from backend.services import scoring_service
from data_science import ingest_stop_lines as ingestion
from data_science.stop_lines import (
    SOURCE_URL, LineCache, calculate_line_features, parse_lines, read_cache,
)

STAMP = "2026-10-17T12:00:00+00:00"
HOME = {"latitude": 52.2297, "longitude": 21.0122}


@pytest.fixture(autouse=True)
def isolate_optional_categories(monkeypatch):
    monkeypatch.setattr(scoring_service, "get_parks", lambda: None)
    monkeypatch.setattr(scoring_service, "get_parking", lambda: None)
    monkeypatch.setattr(scoring_service, "get_sports", lambda: None)


def record(key, lines, error=""):
    return dict(stop_id=key[0], platform=key[1], lines=lines,
                status="success" if lines is not None else "error",
                retrieved_at=STAMP if lines is not None else "", attempted_at=STAMP,
                error_code=error, source_url=SOURCE_URL)


@pytest.fixture
def stops():
    origin = gpd.GeoSeries([Point(HOME["longitude"], HOME["latitude"])], crs=4326).to_crs(2180).iloc[0]
    result = gpd.GeoDataFrame({"stop_id": ["0001", "0001", "0002", "0003"],
                               "platform": ["01", "02", "01", "01"],
                               "stop_name": ["A", "A", "B", "C"]},
                              geometry=[Point(origin.x + x, origin.y) for x in [100, 400, 700, 1500]], crs=2180)
    geographic = result.to_crs(4326)
    result["longitude"], result["latitude"] = geographic.geometry.x, geographic.geometry.y
    return result


@pytest.fixture
def cache():
    items = [("0001", "01"), ("0001", "02"), ("0002", "01"), ("0003", "01")]
    return LineCache({k: record(k, v) for k, v in zip(items, [["01", "23"], ["23"], [], ["N01"]])}, "loaded")


def test_documented_parser_and_unique_identifiers():
    payload = json.loads((Path(__file__).parent / "fixtures/stop_lines_documented.json").read_text())
    assert parse_lines(payload) == ["20", "23", "24"]
    assert parse_lines(payload + payload + [{"values": [{"key": "linia", "value": "01"}]}]) == ["01", "20", "23", "24"]
    assert parse_lines([]) == []


@pytest.mark.parametrize("payload", [{"error": "bad token"}, None, "error", [None], [{}],
    [{"values": []}], [{"values": [{"key": "linia", "value": None}]}],
    [{"values": [{"key": "linia", "value": 23}]}], [{"values": [{"key": "other", "value": "23"}]}]])
def test_parser_rejects_errors_instead_of_inventing_empty_service(payload):
    with pytest.raises(ValueError):
        parse_lines(payload)


def test_spatial_features_join_platforms_and_do_not_double_count(stops, cache):
    result = calculate_line_features(**HOME, stops=stops, cache=cache, radius_m=2000)
    assert result["distinct_lines_500m"] == result["distinct_lines_1000m"] == 2
    assert result["distinct_lines_radius"] == 3
    assert result["nearest_stop_lines"] == ["01", "23"]
    assert result["line_data_coverage"]["within_500m"]["known_platforms"] == 2
    assert result["line_data_coverage"]["within_radius"]["status"] == "complete"
    assert calculate_line_features(**HOME, stops=stops, cache=cache, radius_m=200)["distinct_lines_radius"] == 2


def test_missing_partial_failed_and_known_empty(stops, cache):
    result = calculate_line_features(**HOME, stops=stops, cache=LineCache())
    assert result["nearest_stop_lines"] is None
    assert result["distinct_lines_500m"] is None
    assert result["line_data_coverage"]["within_radius"]["status"] == "missing"
    partial = LineCache({("0001", "02"): record(("0001", "02"), []),
                         ("0002", "01"): record(("0002", "01"), None, "TIMEOUT")}, "loaded")
    result = calculate_line_features(**HOME, stops=stops, cache=partial)
    assert result["distinct_lines_500m"] == 0  # observed empty; explicitly partial
    assert result["nearest_stop_lines"] is None  # platform 02 must not fill platform 01
    c = result["line_data_coverage"]["within_radius"]
    assert c["status"] == "partial" and c["fraction"] == pytest.approx(1 / 3)
    assert c["failed_platforms"] == 1
    empty = calculate_line_features(**HOME, stops=stops, cache=cache, radius_m=1)
    assert empty["distinct_lines_radius"] == 0
    assert empty["line_data_coverage"]["within_radius"]["status"] == "no_platforms"
    failure = LineCache({("0001", "01"): record(("0001", "01"), None, "TIMEOUT")}, "loaded")
    assert calculate_line_features(**HOME, stops=stops, cache=failure)["line_data_coverage"]["within_500m"]["status"] == "error"
    assert calculate_line_features(**HOME, stops=stops, cache=LineCache(status="error"))["distinct_lines_500m"] is None


def test_cache_ignores_unmatched_stop_identifiers(stops):
    cache = LineCache({("1", "1"): record(("1", "1"), ["X"])}, "loaded")
    result = calculate_line_features(**HOME, stops=stops, cache=cache)
    assert result["line_data_coverage"]["known_platforms"] == 0
    assert result["distinct_lines_500m"] is None


def test_cache_roundtrip_resume_and_failed_refresh(tmp_path):
    path = tmp_path / "lines.csv"
    calls = []
    def fetch(*key):
        calls.append(key)
        if key[0] == "0002":
            raise ingestion.IngestionError("TIMEOUT")
        return []
    selected = [("0001", "01"), ("0002", "01")]
    first = ingestion.ingest(selected, path, fetch)
    assert first["succeeded"] == first["failed"] == 1
    stored = read_cache(path)
    assert stored.records[("0001", "01")]["lines"] == []
    assert stored.records[("0002", "01")]["status"] == "error"
    second = ingestion.ingest(selected, path, lambda *key: ["N01", "23"])
    assert second["skipped"] == second["succeeded"] == 1
    previous = read_cache(path).records[("0002", "01")]
    def failed(*key):
        raise ingestion.IngestionError("HTTP_503")
    ingestion.ingest([("0002", "01")], path, failed, refresh=True)
    refreshed = read_cache(path).records[("0002", "01")]
    assert refreshed["lines"] == ["23", "N01"]
    assert refreshed["retrieved_at"] == previous["retrieved_at"]
    assert refreshed["error_code"] == "HTTP_503" and refreshed["status"] == "success"
    assert calls == selected


def test_corrupt_cache_preserved(tmp_path):
    path = tmp_path / "lines.csv"
    path.write_text("bad columns\n")
    assert read_cache(path).status == "error"
    with pytest.raises(ValueError, match="preserve"):
        ingestion.ingest([("0001", "01")], path, lambda *key: [])
    assert path.read_text() == "bad columns\n"


@pytest.mark.parametrize("kind", ["timeout", "server", "rate_limit", "network"])
def test_transient_retry_then_success(kind):
    calls, waits = [], []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            if kind == "timeout": raise httpx.ReadTimeout("private", request=request)
            if kind == "network": raise httpx.ConnectError("private", request=request)
            return httpx.Response(429 if kind == "rate_limit" else 503, headers={"Retry-After": "2"})
        return httpx.Response(200, json=[{"values": [{"key": "linia", "value": "01"}]}])
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = ingestion.LineClient(http, "test-secret", sleep=waits.append)
        assert client.fetch("0001", "01") == ["01"]
    assert len(calls) == 2
    assert json.loads(calls[0].content) == {"busstopId": "0001", "busstopNr": "01"}
    assert calls[0].headers["Authorization"] == "test-secret"
    assert calls[0].extensions["timeout"]["read"] == 10
    assert waits and max(waits) >= 1


@pytest.mark.parametrize("status,expected,attempts", [(401, "HTTP_401", 1), (403, "HTTP_403", 1),
    (404, "HTTP_404", 1), (500, "HTTP_500", 3), (429, "HTTP_429", 3), (200, "INVALID_RESPONSE", 1)])
def test_api_failure_codes_and_bounded_attempts(status, expected, attempts):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "test-secret"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ingestion.IngestionError, match=expected) as exc:
            ingestion.LineClient(http, "test-secret", sleep=lambda _: None).fetch("0001", "01")
    assert "test-secret" not in str(exc.value) and len(calls) == attempts


def test_timeout_exhaustion_and_long_rate_limit():
    calls = []
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret", request=request)
    with httpx.Client(transport=httpx.MockTransport(timeout)) as http:
        with pytest.raises(ingestion.IngestionError, match="TIMEOUT"):
            ingestion.LineClient(http, "secret", sleep=lambda _: None).fetch("1", "01")
    assert len(calls) == 3
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "60"}))) as http:
        with pytest.raises(ingestion.IngestionError, match="HTTP_429"):
            ingestion.LineClient(http, "secret", sleep=lambda _: pytest.fail("must not retry early")).fetch("1", "01")


def test_dry_run_has_no_token_network_or_cache_writes(tmp_path, monkeypatch, stops, capsys):
    monkeypatch.delenv("WARSAW_API_TOKEN", raising=False)
    monkeypatch.setattr(ingestion, "load_stops", lambda: stops)
    monkeypatch.setattr(ingestion.LineClient, "fetch", lambda *args: pytest.fail("network attempted"))
    path = tmp_path / "lines.csv"
    assert ingestion.main(["--limit", "2", "--dry-run", "--output", str(path)]) == 0
    assert not path.exists()
    assert json.loads(capsys.readouterr().out)["selected"] == ["0001:01", "0001:02"]
    with pytest.raises(SystemExit):
        ingestion.main(["--limit", "21", "--dry-run"])
    with pytest.raises(SystemExit):
        ingestion.main(["--platform", "1:1", "--dry-run"])
    with pytest.raises(SystemExit):
        ingestion.main(["--limit", "2", "--output", str(path)])
    assert not path.exists()


def test_api_backward_compatibility_and_marker_limits(monkeypatch, stops, cache):
    monkeypatch.setattr(scoring_service, "get_stops", lambda: stops)
    monkeypatch.setattr(scoring_service, "get_stop_lines", lambda: LineCache())
    client = TestClient(app)
    original = client.post("/api/score", json=HOME).json()
    monkeypatch.setattr(scoring_service, "get_stop_lines", lambda: cache)
    monkeypatch.setattr(scoring_service, "MAX_NEARBY_STOPS", 1)
    updated = client.post("/api/score", json=HOME).json()
    assert updated["scores"] == original["scores"] and updated["features"] == original["features"]
    assert len(updated["places"]) == 1 and updated["nearby"]["total"] == 3
    assert updated["places"][0]["lines"] == ["01", "23"]
    assert updated["line_features"]["distinct_lines_1000m"] == 2
    assert updated["line_features"]["line_data_coverage"]["within_radius"]["known_platforms"] == 3
    assert "lines" not in original["places"][0]
    assert original["line_features"]["distinct_lines_500m"] is None
    assert "token" not in json.dumps(updated).lower()
    narrow = client.post("/api/score", json={**HOME, "radius_m": 200}).json()
    assert narrow["line_features"]["line_data_coverage"]["within_radius"]["total_platforms"] == 1
    assert narrow["line_features"]["distinct_lines_500m"] == updated["line_features"]["distinct_lines_500m"]


def test_backend_cache_reloads_and_survives_corruption(tmp_path, monkeypatch):
    path = tmp_path / "lines.csv"
    monkeypatch.setattr(scoring_service, "CACHE_PATH", path)
    assert scoring_service.get_stop_lines().status == "missing"
    ingestion.save_cache(path, {("0001", "01"): record(("0001", "01"), ["23"])})
    assert scoring_service.get_stop_lines().records[("0001", "01")]["lines"] == ["23"]
    path.write_text("invalid\n")
    assert scoring_service.get_stop_lines().status == "error"


@pytest.mark.parametrize("code", ["HTTP_401", "HTTP_403", "HTTP_429"])
def test_auth_or_rate_limiting_stops_batch(tmp_path, code):
    calls = []
    def failed(*key):
        calls.append(key)
        raise ingestion.IngestionError(code)
    result = ingestion.ingest([("0001", "01"), ("0002", "01")], tmp_path / "cache.csv", failed)
    assert result["requested"] == result["failed"] == 1
    assert calls == [("0001", "01")]


def test_no_citywide_ingestion_and_empty_cache(tmp_path):
    with pytest.raises(ValueError, match="20"):
        ingestion.ingest([(str(i), "01") for i in range(21)], tmp_path / "cache.csv", lambda *args: [])
    ingestion.save_cache(tmp_path / "cache.csv", {})
    assert read_cache(tmp_path / "cache.csv").status == "missing"


def test_failed_refresh_has_explicit_coverage(stops, cache):
    cache.records[("0001", "01")]["error_code"] = "TIMEOUT"
    result = calculate_line_features(**HOME, stops=stops, cache=cache)
    assert result["line_data_coverage"]["within_500m"]["status"] == "complete"
    assert result["line_data_coverage"]["within_500m"]["refresh_failed_platforms"] == 1
    assert result["nearest_stop_lines"] == ["01", "23"]


def test_address_response_contains_line_features_and_known_empty_markers(monkeypatch, stops, cache):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(scoring_service, "get_stops", lambda: stops)
    monkeypatch.setattr(scoring_service, "get_stop_lines", lambda: cache)
    monkeypatch.setattr("backend.main.geocode_address", AsyncMock(return_value={**HOME, "address": "Warszawa"}))
    client = TestClient(app)
    by_address = client.post("/api/score/address", json={"address": "Warszawa"}).json()
    direct = client.post("/api/score", json=HOME).json()
    assert by_address["location"].pop("address") == "Warszawa"
    assert by_address == direct
    assert direct["places"][2]["lines"] == []
    assert direct["places"][2]["line_data_status"] == "available"
