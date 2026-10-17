"""Final MVP regressions: standards-safe validation and provider error handling."""
import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import routing_service as routing

client = TestClient(app)
HTTP_CLIENT = httpx.AsyncClient
HOME = {'latitude':52.2297, 'longitude':21.0122}
DESTINATION = {'latitude':52.239, 'longitude':21.022}


@pytest.mark.parametrize('number', ['NaN','Infinity','-Infinity','1e309'])
@pytest.mark.parametrize('endpoint,body', [
    ('/api/score', '{"latitude":52.2297,"longitude":21.0122,"radius_m":NUMBER}'),
    ('/api/score/address', '{"address":"Warszawa","radius_m":NUMBER}'),
    ('/api/compare', '{"locations":[{"latitude":52.2297,"longitude":21.0122},{"latitude":52.239,"longitude":21.022}],"include_routes":NUMBER}'),
    ('/api/commute', '{"origin":{"latitude":52.2297,"longitude":21.0122},"destination":NUMBER}'),
])
def test_nonfinite_validation_errors_remain_json_422(number, endpoint, body):
    response = client.post(endpoint, content=body.replace('NUMBER', number), headers={'content-type':'application/json'})
    assert response.status_code == 422
    errors = response.json()['detail']
    assert isinstance(errors, list) and errors
    assert errors[0]['loc'][0] == 'body'
    json.dumps(response.json(), allow_nan=False)


def test_regular_validation_error_shape_is_unchanged():
    response = client.post('/api/score', json={'longitude':21.0122})
    assert response.status_code == 422
    assert response.json()['detail'][0]['loc'] == ['body','latitude']
    assert response.json()['detail'][0]['type'] == 'missing'


@pytest.fixture
def isolated_routing(monkeypatch):
    monkeypatch.setattr(routing, '_cache', OrderedDict())
    monkeypatch.setattr(routing, '_lock', asyncio.Lock())
    monkeypatch.setattr(routing, '_last_request', 0.0)
    monkeypatch.setattr(routing, '_cooldown_until', 0.0)
    monkeypatch.setenv('ROUTING_ENABLED','true')
    monkeypatch.setenv('ROUTING_BASE_URL',routing.DEFAULT_BASE_URL)


def test_provider_http_date_retry_after_is_respected(monkeypatch, isolated_routing):
    calls = []
    retry_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    def limited(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After':format_datetime(retry_at, usegmt=True)})
    monkeypatch.setattr(routing.httpx, 'AsyncClient', lambda **kwargs: HTTP_CLIENT(transport=httpx.MockTransport(limited), **kwargs))
    start = routing.time.monotonic()
    result = client.post('/api/commute', json={'origin':HOME,'destination':DESTINATION})
    assert result.status_code == 200
    assert result.json()['baseline']['distance_m'] > 0
    assert result.json()['walking']['status'] == result.json()['driving']['status'] == 'unavailable'
    assert len(calls) == 1
    assert 590 <= routing._cooldown_until - start <= 610


@pytest.mark.parametrize('base', [
    'https://example.invalid?key=example-only',
    'https://example.invalid#fragment',
    'https://example-user:example-password@example.invalid',
    'ftp://example.invalid',
    'https://example.invalid:bad-port',
])
def test_invalid_route_configuration_never_requested_or_echoed(monkeypatch, isolated_routing, base):
    monkeypatch.setenv('ROUTING_BASE_URL',base)
    calls = []
    def unexpected(request):
        calls.append(request)
        return httpx.Response(503)
    monkeypatch.setattr(routing.httpx, 'AsyncClient', lambda **kwargs: HTTP_CLIENT(transport=httpx.MockTransport(unexpected), **kwargs))
    result = client.post('/api/commute', json={'origin':HOME,'destination':DESTINATION})
    assert result.status_code == 200
    assert result.json()['baseline']['distance_m'] > 0
    assert result.json()['walking']['status'] == 'unavailable'
    assert base not in result.text
    assert not calls
