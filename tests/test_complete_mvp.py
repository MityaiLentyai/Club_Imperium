import asyncio
import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.main import app
from backend.schemas import RoutePoint
from backend.services import routing_service as routing
from data_science.life_score import calculate_life_score
from data_science.ingest_sports import parse_sites, parse_address, enrich_sites, address_parts
from data_science.sports import load_sports, calculate_sports_features
from data_science.stop_lines import read_cache

HTTPX_ASYNC_CLIENT = httpx.AsyncClient

FIXTURES = Path(__file__).parent / 'fixtures'
HOME = {'latitude': 52.2297, 'longitude': 21.0122}
DESTINATION = {'latitude': 52.239, 'longitude': 21.022}
client = TestClient(app)


def test_sports_source_parsing_distinct_sites_and_types():
    raw = json.loads((FIXTURES / 'sports/source-sample.json').read_text())
    sites = parse_sites(raw + raw + [None, {'Adres obiektu': None}])
    assert len(sites) == 3
    assert len(sites[0]['sport_types']) >= 2
    assert sites[0]['schedules'][0]['hours']['Poniedziałek']
    assert sites[0]['schedules'][0]['updated_at']
    with pytest.raises(ValueError):
        parse_sites({'error': 'not records'})


def test_exact_municipal_address_not_fuzzy_or_ambiguous():
    raw = (FIXTURES / 'sports/address-exact.gml').read_bytes()
    point = parse_address(raw, 'ulica Elbląska', '51', 'Żoliborz')
    assert point == {'longitude': 20.961636, 'latitude': 52.263332, 'address_id': '1435309'}
    assert parse_address(raw, 'ulica Elbląska', '52', 'Żoliborz') is None
    assert parse_address(raw, 'ulica Elbląska', '51', 'Wola') is None
    assert address_parts('ul. Elbląska 51') == ('ulica Elbląska', '51')
    assert address_parts('ambiguous address') is None
    assert parse_address(raw.replace(b'20.961636,52.263332', b'0,0'), 'ulica Elbląska', '51', 'Żoliborz') is None
    with pytest.raises(ValueError):
        parse_address(b'<!DOCTYPE a><a/>', 'street', '1', 'district')


def test_sports_bounded_cache_and_unresolved_states(tmp_path, monkeypatch):
    import data_science.ingest_sports as sports
    monkeypatch.setattr(sports.time, 'sleep', lambda _: None)
    site = parse_sites(json.loads((FIXTURES / 'sports/source-sample.json').read_text()))[0]
    calls = []
    def fetch(url, params):
        calls.append(params)
        return (FIXTURES / 'sports/address-exact.gml').read_bytes()
    features, metadata = enrich_sites([site], tmp_path, fetch=fetch, limit=1)
    assert len(features) == 1 and calls[0]['maxFeatures'] == 5
    assert 'NR_PORZADK' in calls[0]['filter'] and 'DZIELNICA' in calls[0]['filter']
    assert features[0]['properties']['coordinate_source'].startswith('Warsaw municipal address point')
    features2, _ = enrich_sites([site], tmp_path, fetch=lambda *a, **k: pytest.fail('Unexpected network'), offline=True)
    assert features2 == features
    unresolved = {**site, 'address': 'Aleja uncertain 1'}
    assert enrich_sites([unresolved], tmp_path, offline=True)[1]['unresolved_count'] == 1
    with pytest.raises(ValueError):
        enrich_sites([site], tmp_path, limit=11)


def test_real_sports_snapshot_counts_radius_missing_and_metadata():
    dataset = load_sports()
    assert len(dataset['records']) == dataset['metadata']['record_count'] >= 7
    assert dataset['metadata']['selected_sites'] >= len(dataset['records'])
    assert dataset['metadata']['source_sites'] == 308
    props, geom, _ = dataset['records'][0]
    f, places, state = calculate_sports_features(geom.y, geom.x, 1, dataset)
    assert f['nearest_sports_facility_m'] == 0
    assert f['sports_facilities_within_radius'] >= 1
    assert places[0]['sport_types'] and places[0]['coordinate_source']
    assert calculate_sports_features(**HOME)[0]['sports_facilities_within_radius'] is None


def test_weight_normalization_excludes_missing_instead_of_zero():
    index = calculate_life_score({'mobility': 80}, {'mobility': 1, 'green': 99})
    assert index['value'] == 80
    assert index['normalized_weights'] == {'mobility': 100}
    assert index['status'] == 'partial'
    assert index['excluded']['green'] == 'No validated numeric category score'
    assert calculate_life_score({'mobility': 80}, {'mobility': 0, 'green': 100})['value'] is None
    assert calculate_life_score({}, {})['status'] == 'unavailable'
    # Generic math is verified without claiming a real Green Score exists.
    example = calculate_life_score({'mobility': 80, 'green': 40}, {'mobility': 3, 'green': 1})
    assert example['value'] == 70
    assert sum(example['normalized_weights'].values()) == pytest.approx(100)


@pytest.mark.parametrize('value', [-1, 101, 'NaN', 'Infinity'])
@pytest.mark.parametrize('endpoint', ['/api/score', '/api/score/address'])
def test_invalid_weights_rejected_without_external_requests(value, endpoint):
    body = {'address': 'Warszawa'} if endpoint.endswith('address') else HOME
    assert client.post(endpoint, json={**body, 'weights': {'mobility': value}}).status_code == 422


def test_combined_api_mobility_lines_sources_and_optional_categories():
    data = client.post('/api/score', json={**HOME, 'radius_m': 1000, 'weights': {'mobility': 10, 'parking': 90}}).json()
    assert data['scores'] == {'mobility': 92.7}
    assert data['life_score']['value'] == 92.7
    assert data['life_score']['normalized_weights'] == {'mobility': 100}
    assert all(data['datasets'][key]['status'] == 'available' for key in ['green', 'parking', 'sports'])
    assert data['line_features']['line_data_coverage']['known_platforms'] == 15
    assert len(data['sources']) == 5
    assert 'nearest_sports_facility_m' in data['features']
    assert len(read_cache().records) == 15


@pytest.fixture
def routes(monkeypatch):
    original_client = HTTPX_ASYNC_CLIENT
    calls = []
    def handler(request):
        calls.append(request)
        mode = 'walking' if '/routed-foot/' in request.url.path else 'driving'
        return httpx.Response(200, json=json.loads((FIXTURES / f'routing/{mode}.json').read_text()))
    monkeypatch.setattr(routing.httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(routing, '_lock', asyncio.Lock())
    monkeypatch.setattr(routing, '_cache', __import__('collections').OrderedDict())
    monkeypatch.setattr(routing, '_last_request', 0)
    monkeypatch.setattr(routing, '_cooldown_until', 0)
    monkeypatch.setenv('ROUTING_ENABLED', 'true')
    monkeypatch.setenv('ROUTING_BASE_URL', routing.DEFAULT_BASE_URL)
    async def no_wait(*args): pass
    monkeypatch.setattr(routing.asyncio, 'sleep', no_wait)
    return calls


def test_actual_route_parser_profiles_and_cache(routes):
    body = {'origin': HOME, 'destination': DESTINATION}
    result = client.post('/api/commute', json=body)
    assert result.status_code == 200
    data = result.json()
    assert data['walking']['status'] == data['driving']['status'] == 'available'
    assert data['walking']['distance_m'] == 1771.2
    assert data['walking']['duration_minutes'] == round(1417.4 / 60, 1)
    assert data['walking']['geometry']['type'] == 'LineString'
    assert data['transit']['status'] == 'unavailable'
    assert len(routes) == 2
    assert '/routed-foot/route/v1/foot/' in routes[0].url.path
    assert '/routed-car/route/v1/driving/' in routes[1].url.path
    assert all('Authorization' not in r.headers for r in routes)
    cached = client.post('/api/commute', json=body).json()
    assert cached['walking']['cached'] and cached['driving']['cached']
    assert len(routes) == 2


@pytest.mark.parametrize('kind', ['timeout', 'http', 'malformed', 'no_route', 'bad_snap', 'nonfinite'])
def test_route_provider_failure_preserves_baseline_and_scoring(routes, monkeypatch, kind):
    def handler(request):
        if kind == 'timeout': raise httpx.ReadTimeout('provider failed', request=request)
        if kind == 'http': return httpx.Response(503)
        data = json.loads((FIXTURES / 'routing/walking.json').read_text())
        if kind == 'malformed': data = {'code': 'Ok', 'routes': []}
        if kind == 'no_route': data = {'code': 'NoRoute'}
        if kind == 'bad_snap': data['waypoints'][0]['distance'] = 1000
        if kind == 'nonfinite': data['routes'][0]['distance'] = -1
        return httpx.Response(200, json=data)
    original_client = HTTPX_ASYNC_CLIENT
    monkeypatch.setattr(routing.httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    data = client.post('/api/commute', json={'origin': HOME, 'destination': DESTINATION}).json()
    assert data['walking']['status'] == data['driving']['status'] == 'unavailable'
    assert data['baseline']['distance_m'] > 0
    assert 'duration_minutes' not in data['walking']
    assert client.post('/api/score', json=HOME).json()['scores']['mobility'] == 92.7


def test_routing_disabled_and_invalid_destination_do_not_request_network(monkeypatch):
    monkeypatch.setenv('ROUTING_ENABLED', 'false')
    data = client.post('/api/commute', json={'origin': HOME, 'destination': DESTINATION}).json()
    assert data['walking']['reason'] == 'Routing disabled'
    assert data['baseline']['distance_type'] == 'straight_line'
    for bad in [{'latitude': 0, 'longitude': 0}, {'latitude': 'NaN', 'longitude': 21}]:
        assert client.post('/api/commute', json={'origin': HOME, 'destination': bad}).status_code == 422


def test_provider_rate_limit_stops_remaining_requests(routes, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After': '120'})
    monkeypatch.setattr(routing.httpx, 'AsyncClient', lambda **kwargs: HTTPX_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs))
    data = client.post('/api/commute', json={'origin': HOME, 'destination': DESTINATION}).json()
    assert len(calls) == 1
    assert data['walking']['status'] == data['driving']['status'] == 'unavailable'


def test_missing_sports_does_not_hide_other_categories(monkeypatch):
    from backend.services import scoring_service
    monkeypatch.setattr(scoring_service, 'get_sports', lambda: None)
    data = client.post('/api/score', json=HOME).json()
    assert 'sports' in data['unavailable'] and 'green' not in data['unavailable']
    assert data['features']['sports_facilities_within_radius'] is None
    assert data['life_score']['value'] == data['scores']['mobility']
