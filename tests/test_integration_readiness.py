"""Regression checks for the existing frontend-facing endpoints, without live I/O."""
import asyncio
import copy
import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import RoutePoint
from backend.services import scoring_service as scoring, routing_service as routing
from data_science.infrastructure import load_snapshot

client = TestClient(app)
HOME = {'latitude': 52.2297, 'longitude': 21.0122}


@pytest.mark.parametrize('failure', [FileNotFoundError('private/path'), ValueError('bad columns'), 'empty'])
@pytest.mark.parametrize('endpoint', ['/api/score', '/api/score/address', '/api/compare'])
def test_missing_transport_is_sanitized_service_unavailable(monkeypatch, failure, endpoint):
    import backend.main as main
    import backend.services.comparison_service as comparison
    empty = scoring.load_stops().iloc[:0]
    scoring.get_stops.cache_clear()
    def unavailable():
        if failure == 'empty':
            return empty
        raise failure
    monkeypatch.setattr(scoring, 'load_stops', unavailable)
    location = {**HOME, 'address': 'Warszawa'}
    monkeypatch.setattr(main, 'geocode_address', AsyncMock(return_value=location))
    monkeypatch.setattr(comparison, 'geocode_address', AsyncMock(return_value=location))
    body = {'address': 'Warszawa'} if endpoint.endswith('/address') else HOME
    if endpoint.endswith('/compare'):
        body = {'locations': [HOME, {'address': 'Warszawa'}]}
    try:
        response = client.post(endpoint, json=body)
        assert response.status_code == 503
        assert response.json() == {'detail': 'Transport dataset unavailable'}
        assert client.get('/api/health').json() == {'status': 'ok'}
    finally:
        scoring.get_stops.cache_clear()


def test_malformed_optional_feature_preserves_valid_records(tmp_path):
    source = json.loads(Path('data/infrastructure/parking.geojson').read_text())
    valid = source['features'][0]
    source['features'] = [dict(valid, geometry=None), valid]
    path = tmp_path / 'partial.json'
    path.write_text(json.dumps(source))
    loaded = load_snapshot('parking', path)
    assert loaded is not None
    assert len(loaded['records']) == 1
    assert loaded['records'][0][0]['source_id'] == valid['properties']['source_id']


def test_missing_optional_datasets_are_null_not_zero(monkeypatch):
    for name in ('get_parks', 'get_parking', 'get_sports'):
        monkeypatch.setattr(scoring, name, lambda: None)
    response = client.post('/api/score', json=HOME)
    assert response.status_code == 200
    result = response.json()
    for category in ('green', 'parking', 'sports'):
        assert result['datasets'][category] == {'status': 'unavailable'}
        assert category in result['unavailable']
        assert category in result['life_score']['excluded']
    for key in ('parks_within_radius', 'listed_parking_within_radius', 'sports_facilities_within_radius'):
        assert result['features'][key] is None
    assert result['life_score']['value'] == result['scores']['mobility']
    assert result['life_score']['status'] == 'partial'


@pytest.mark.parametrize('endpoint', ['/api/score/address', '/api/compare'])
def test_async_endpoints_offload_scoring_to_worker_thread(monkeypatch, endpoint):
    import backend.main as main
    from backend.services import comparison_service as comparison
    result = scoring.get_location_score(**HOME)
    event_loop_threads, scoring_threads = [], []
    async def geocode(address):
        event_loop_threads.append(threading.get_ident())
        return {**HOME, 'address': address}
    def score(*args, **kwargs):
        scoring_threads.append(threading.get_ident())
        return copy.deepcopy(result)
    target = main if endpoint.endswith('/address') else comparison
    monkeypatch.setattr(target, 'geocode_address', geocode)
    monkeypatch.setattr(target, 'get_location_score', score)
    body = {'address': 'Marszałkowska 83'} if target is main else {
        'locations': [{'address': 'Marszałkowska 83'}, {'address': 'Stokłosy 7'}]}
    assert client.post(endpoint, json=body).status_code == 200
    assert scoring_threads and event_loop_threads
    assert set(scoring_threads).isdisjoint(event_loop_threads)


def test_busy_route_queue_returns_baseline_without_provider_request(monkeypatch):
    fetch = AsyncMock(side_effect=AssertionError('No provider request expected'))
    monkeypatch.setattr(routing, '_fetch_route', fetch)
    monkeypatch.setattr(routing, 'QUEUE_TIMEOUT', 0.01)
    async def scenario():
        lock = asyncio.Lock()
        monkeypatch.setattr(routing, '_lock', lock)
        await lock.acquire()
        try:
            result = await routing.get_commute(RoutePoint(**HOME), RoutePoint(latitude=52.239, longitude=21.022))
            assert result['baseline']['distance_m'] > 0
            assert result['transit']['status'] == 'unavailable'
            for mode in ('walking', 'driving'):
                assert result[mode]['status'] == 'unavailable'
                assert 'queue busy' in result[mode]['reason']
            assert lock.locked()  # Timeout must not release another caller's lock.
        finally:
            lock.release()
    asyncio.run(scenario())
    fetch.assert_not_awaited()


def test_route_cancellation_releases_queue_lock(monkeypatch):
    async def scenario():
        lock = asyncio.Lock()
        started = asyncio.Event()
        monkeypatch.setattr(routing, '_lock', lock)
        monkeypatch.setattr(routing, '_cache', {})
        monkeypatch.setattr(routing, '_cooldown_until', 0.0)
        async def wait_for_cancel(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(routing, '_fetch_route', wait_for_cancel)
        task = asyncio.create_task(routing.get_commute(RoutePoint(**HOME), RoutePoint(latitude=52.239, longitude=21.022)))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not lock.locked()
    asyncio.run(scenario())


@pytest.mark.parametrize('point', [HOME, {'latitude':52.158969,'longitude':21.031856}, {'latitude':52.253043,'longitude':21.039900}])
def test_score_contract_for_frontend_adapter(point):
    result = client.post('/api/score', json={**point, 'radius_m':1000}).json()
    assert result['location'] == point
    assert result['radius_m'] == 1000
    assert result['scores'] == {'mobility':result['life_score']['value']}
    assert result['life_score']['normalized_weights'] == {'mobility':100}
    assert {'grocery', 'pharmacy'} <= set(result['unavailable'])
    assert all(isinstance(s['name'], str) for s in result['sources'])
    for p in result['places']:
        assert {'id','category','label','latitude','longitude','distance_m','distance_type'} <= p.keys()
        assert p['distance_type'] == 'straight_line'
        assert 52.0 <= p['latitude'] <= 52.4 and 20.75 <= p['longitude'] <= 21.3
        assert 0 <= p['distance_m'] <= 1000
    # Compare embeds the same score contract and uses shared top-level weights.
    comparison = client.post('/api/compare', json={'locations':[point, HOME]}).json()
    assert comparison['locations'][0] == result
