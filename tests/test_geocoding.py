import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from backend.services import geocoding_service as geo


WARSAW = [{
    "lat": "52.2297", "lon": "21.0122",
    "display_name": "Marszałkowska, Warszawa, Polska",
    "address": {"city": "Warszawa", "country_code": "pl", "house_number": "1"},
}]


@pytest.fixture
def upstream(monkeypatch):
    geo._cache.clear()
    monkeypatch.setattr(geo, "lookup_address", lambda _: {"status": "not_found"})
    monkeypatch.setattr(geo, "_request_lock", asyncio.Lock())
    monkeypatch.setattr(geo, "_last_request_time", 0.0)
    monkeypatch.setenv("GEOCODING_USER_AGENT", "WarsawLifeScore-tests/1.0")
    mock = AsyncMock(return_value=httpx.Response(
        200, json=WARSAW, request=httpx.Request("GET", geo.GEOCODING_URL)
    ))
    monkeypatch.setattr(httpx.AsyncClient, "get", mock)
    yield mock
    geo._cache.clear()


def test_cache_normalization_and_copy(upstream):
    async def scenario():
        first = await geo.geocode_address("  Marszałkowska   1  ")
        first["latitude"] = 0
        second = await geo.geocode_address("marszałkowska 1")
        assert second["latitude"] == 52.2297
    asyncio.run(scenario())
    upstream.assert_awaited_once()
    kwargs = upstream.call_args.kwargs
    assert kwargs["headers"]["User-Agent"] == "WarsawLifeScore-tests/1.0"
    assert kwargs["params"]["bounded"] == 1
    assert kwargs["params"]["countrycodes"] == "pl"


def test_concurrent_identical_requests(upstream):
    async def scenario():
        results = await asyncio.gather(*(geo.geocode_address("Marszałkowska 1") for _ in range(5)))
        assert all(result == results[0] for result in results)
    asyncio.run(scenario())
    upstream.assert_awaited_once()


def test_expiry_and_eviction(upstream, monkeypatch):
    monkeypatch.setattr(geo, "CACHE_MAXSIZE", 1)
    monkeypatch.setattr(geo.asyncio, "sleep", AsyncMock())
    async def scenario():
        await geo.geocode_address("First address 1")
        stamp, result = geo._cache["first address 1"]
        geo._cache["first address 1"] = (stamp - geo.CACHE_TTL, result)
        await geo.geocode_address("First address 1")
        await geo.geocode_address("Second address 1")
        assert list(geo._cache) == ["second address 1"]
    asyncio.run(scenario())
    assert upstream.await_count == 3


def test_rate_limit(upstream, monkeypatch):
    monkeypatch.setattr(geo.time, "monotonic", lambda: 100.0)
    sleep = AsyncMock()
    monkeypatch.setattr(geo.asyncio, "sleep", sleep)
    async def scenario():
        await geo.geocode_address("First address 1")
        await geo.geocode_address("Second address 1")
    asyncio.run(scenario())
    sleep.assert_awaited_once_with(1.1)


@pytest.mark.parametrize("payload", [
    [],
    [{**WARSAW[0], "lat": "50.06", "lon": "19.94"}],
    [{**WARSAW[0], "address": {"town": "Pruszków", "country_code": "pl"}}],
    [{**WARSAW[0], "address": {"country_code": "de"}}],
])
def test_not_found_cached(upstream, payload):
    upstream.return_value = httpx.Response(200, json=payload, request=httpx.Request("GET", geo.GEOCODING_URL))
    async def scenario():
        for _ in range(2):
            with pytest.raises(HTTPException) as error:
                await geo.geocode_address("Unknown address 1")
            assert error.value.status_code == 404
    asyncio.run(scenario())
    upstream.assert_awaited_once()


@pytest.mark.parametrize("payload", [{}, [None], [{}], [{**WARSAW[0], "lat": "nan"}], [{**WARSAW[0], "address": None}]])
def test_malformed_response(upstream, payload):
    upstream.return_value = httpx.Response(200, json=payload, request=httpx.Request("GET", geo.GEOCODING_URL))
    with pytest.raises(HTTPException) as error:
        asyncio.run(geo.geocode_address("Some address 1"))
    assert error.value.status_code == 502
    assert not geo._cache


@pytest.mark.parametrize("failure,status", [
    (httpx.ReadTimeout("slow"), 504),
    (httpx.ConnectError("offline"), 502),
    (ValueError("invalid JSON"), 502),
])
def test_upstream_failure(upstream, failure, status):
    upstream.side_effect = failure
    with pytest.raises(HTTPException) as error:
        asyncio.run(geo.geocode_address("Some address 1"))
    assert error.value.status_code == status
    assert not geo._cache


@pytest.mark.parametrize("status", [403, 429, 500])
def test_upstream_http_error(upstream, status):
    upstream.return_value = httpx.Response(status, request=httpx.Request("GET", geo.GEOCODING_URL))
    with pytest.raises(HTTPException) as error:
        asyncio.run(geo.geocode_address("Some address 1"))
    assert error.value.status_code == 502


def test_missing_configuration(upstream, monkeypatch):
    monkeypatch.delenv("GEOCODING_USER_AGENT")
    with pytest.raises(HTTPException) as error:
        asyncio.run(geo.geocode_address("Some address 1"))
    assert error.value.status_code == 503
    upstream.assert_not_awaited()


def test_invalid_json(upstream):
    upstream.return_value = httpx.Response(200, text="not JSON", request=httpx.Request("GET", geo.GEOCODING_URL))
    with pytest.raises(HTTPException) as error:
        asyncio.run(geo.geocode_address("Some address 1"))
    assert error.value.status_code == 502


def test_address_routes_use_shared_cache(upstream):
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        geocoded = client.get("/api/geocode", params={"address": "Marszałkowska 1"})
        scored = client.post("/api/score/address", json={"address": "marszałkowska 1"})
    assert geocoded.status_code == scored.status_code == 200
    assert scored.json()["location"] == geocoded.json()
    assert 0 <= scored.json()["scores"]["mobility"] <= 100
    upstream.assert_awaited_once()


@pytest.mark.parametrize('house_number', [None, '', '999'])
def test_fallback_never_uses_a_street_or_different_building(upstream,house_number):
    payload=[{**WARSAW[0],'address':{**WARSAW[0]['address'],'house_number':house_number}}]
    upstream.return_value=httpx.Response(200,json=payload,request=httpx.Request('GET',geo.GEOCODING_URL))
    with pytest.raises(HTTPException) as error:
        asyncio.run(geo.geocode_address('Marszałkowska 1'))
    assert error.value.status_code==404
