import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest

from backend.main import app
from backend.schemas import RoutePoint
from backend.services import routing_service, scoring_service
from data_science.data_quality import describe_data, timestamp_range
from data_science.ingest_infrastructure import save_snapshot, input_provenance
from data_science.ingest_sports import address_parts, enrich_sites, merge_snapshot, select_sites
from data_science.ingest_stop_lines import LineClient, IngestionError
from data_science.infrastructure import load_snapshot
from data_science.stop_lines import LineCache

client = TestClient(app)
FIXTURES = Path(__file__).parent / 'fixtures'


def test_bounded_explicit_sports_selection_and_avenue_support():
    sites = [{'address': str(i)} for i in range(25)]
    assert select_sites(sites, limit=2, offset=10) == sites[10:12]
    assert select_sites(sites, limit=3, indices=[20, 1]) == [sites[20], sites[1]]
    for kwargs in [{'limit': 11}, {'offset': -1}, {'indices': [1, 1]}, {'indices': [25]}, {'offset': 1, 'indices': [1]}]:
        with pytest.raises(ValueError):
            select_sites(sites, **kwargs)
    assert address_parts('Aleja Wojska Polskiego 1A') == ('aleja Wojska Polskiego', '1A')


def test_sports_batches_merge_without_losing_previous_sites_or_freshness(tmp_path):
    raw = b'saved source'
    feature = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [21, 52.2]},
               'properties': {'source_id': 'old', 'address': 'Old 1', 'district': 'A'}}
    stamp = '2025-01-01T00:00:00+00:00'
    save_snapshot('sports', raw, [feature], {'retrieved_at': stamp, 'unresolved_addresses': ['New 1']}, tmp_path)
    new = deepcopy(feature)
    new['properties'].update(source_id='new', address='New 1', district='B')
    new['geometry']['coordinates'] = [21.01, 52.21]
    merged, metadata = merge_snapshot(raw, [new], {'unresolved_addresses': [], 'unresolved_count': 0, 'source_sites': 10}, tmp_path)
    assert {f['properties']['source_id'] for f in merged} == {'old', 'new'}
    assert metadata['retrieved_at'] == stamp
    assert metadata['unresolved_count'] == 0
    assert metadata['located_fraction_of_source_sites'] == .2
    assert metadata['districts_with_located_sites'] == ['A', 'B']
    with pytest.raises(ValueError, match='source changed'):
        merge_snapshot(b'new source', [new], {}, tmp_path)
    original = json.loads((tmp_path / 'sports.geojson').read_text())
    assert original['features'] == [feature]


def test_offline_reparse_does_not_fabricate_source_retrieval_time(tmp_path):
    raw = b'saved response'
    provenance = input_provenance(raw, 'sports', tmp_path / 'input.json', tmp_path)
    assert provenance['retrieved_at'] is None
    feature = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [21, 52.2]},
               'properties': {'source_id': 'site', 'name': 'Saved site'}}
    saved = save_snapshot('sports', raw, [feature], {**provenance, 'source_url': 'https://source.example'}, tmp_path)
    assert saved['retrieved_at'] is None and saved['processed_at']
    assert load_snapshot('sports', tmp_path / 'sports.geojson') is not None
    assert input_provenance(raw, 'sports', tmp_path / 'input.json', tmp_path)['retrieval_time_basis'] == 'preserved_matching_snapshot'


def test_coordinate_cache_records_real_fetch_time_and_reuses_it(tmp_path, monkeypatch):
    from data_science import ingest_sports
    monkeypatch.setattr(ingest_sports.time, 'sleep', lambda _: None)
    site = {'name': 'Site', 'address': 'ul. Elbląska 51', 'district': 'Żoliborz'}
    raw = (FIXTURES / 'sports/address-exact.gml').read_bytes()
    features, _ = enrich_sites([site], tmp_path, limit=1, fetch=lambda *a, **kw: raw)
    stamp = features[0]['properties']['coordinate_retrieved_at']
    assert datetime.fromisoformat(stamp).tzinfo is not None
    cached, _ = enrich_sites([site], tmp_path, limit=1, offline=True)
    assert cached[0]['properties']['coordinate_retrieved_at'] == stamp
    metadata = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert metadata['sha256'] == hashlib.sha256(raw).hexdigest()


def test_partial_geometry_corruption_does_not_discard_valid_records(tmp_path):
    features = json.loads((Path(__file__).parents[1] / 'data/infrastructure/sports.geojson').read_text())
    features['features'][0]['geometry'] = None
    path = tmp_path / 'sports.geojson'
    path.write_text(json.dumps(features))
    dataset = load_snapshot('sports', path)
    assert len(dataset['records']) == len(features['features']) - 1
    assert dataset['metadata']['rejected_record_count'] == 1


def test_optional_snapshots_reload_after_atomic_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(scoring_service, 'DATA_DIR', tmp_path)
    assert scoring_service.get_sports() is None
    payload = json.loads((Path(__file__).parents[1] / 'data/infrastructure/sports.geojson').read_text())
    path = tmp_path / 'sports.geojson'
    path.write_text(json.dumps(payload))
    first = scoring_service.get_sports()
    assert first is not None
    payload['features'] = payload['features'][:1]
    payload['metadata']['record_count'] = 1
    replacement = tmp_path / 'replacement'
    replacement.write_text(json.dumps(payload))
    replacement.replace(path)
    assert len(scoring_service.get_sports()['records']) == 1
    path.write_text('{broken')
    assert scoring_service.get_sports() is None


def test_data_status_is_offline_and_explains_ineligible_scores():
    response = client.get('/api/data/status')
    assert response.status_code == 200
    data = response.json()
    assert data['external_requests'] is False
    assert data['datasets']['sports']['record_count'] >= 16
    assert data['datasets']['sports']['coordinate_timestamp_count'] >= 9
    assert data['datasets']['sports']['located_fraction_of_source_sites'] < .1
    assert data['score_eligibility']['mobility']['eligible'] is True
    assert not data['score_eligibility']['sports']['eligible']
    assert not data['score_eligibility']['green']['eligible']
    score = client.post('/api/score', json={'latitude': 52.2297, 'longitude': 21.0122}).json()
    assert score['scores'] == {'mobility': 92.7}
    assert 'bounded sample' in score['life_score']['excluded']['sports']


def test_missing_transport_returns_503_and_status_is_still_readable(monkeypatch):
    def missing(): raise FileNotFoundError('private path must not be exposed')
    scoring_service.get_stops.cache_clear()
    monkeypatch.setattr(scoring_service, 'load_stops', missing)
    response = client.post('/api/score', json={'latitude': 52.2297, 'longitude': 21.0122})
    assert response.status_code == 503
    assert response.json() == {'detail': 'Transport snapshot is unavailable or invalid'}
    data = client.get('/api/data/status').json()
    assert data['datasets']['transport']['record_count'] is None
    assert not data['score_eligibility']['mobility']['eligible']
    scoring_service.get_stops.cache_clear()


def test_timestamp_range_compares_instants_and_retains_unknowns():
    result = timestamp_range([None, 'invalid', '2026-01-01T10:00:00+02:00', '2026-01-01T09:00:00+00:00'])
    assert result['oldest_retrieved_at'] == '2026-01-01T10:00:00+02:00'
    assert result['latest_retrieved_at'] == '2026-01-01T09:00:00+00:00'
    assert timestamp_range([None, '2026-01-01'])['latest_retrieved_at'] is None


def test_line_response_size_is_bounded_and_error_does_not_expose_token():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b' ' * 256001))) as http:
        with pytest.raises(IngestionError, match='RESPONSE_TOO_LARGE'):
            LineClient(http, 'private-test-value', retries=0).fetch('0001', '01')


def test_busy_routing_queue_returns_baseline_without_external_calls(monkeypatch):
    async def run():
        lock = asyncio.Lock()
        await lock.acquire()
        monkeypatch.setattr(routing_service, '_lock', lock)
        monkeypatch.setattr(routing_service, 'QUEUE_TIMEOUT', .01)
        monkeypatch.setenv('ROUTING_ENABLED', 'true')
        monkeypatch.setenv('ROUTING_BASE_URL', routing_service.DEFAULT_BASE_URL)
        result = await routing_service.get_commute(RoutePoint(latitude=52.2297, longitude=21.0122), RoutePoint(latitude=52.24, longitude=21.02))
        assert result['baseline']['distance_m'] > 0
        assert result['walking']['reason'] == 'Routing queue busy; retry later'
        assert lock.locked()
        lock.release()
    asyncio.run(run())


@pytest.mark.parametrize('url', ['https://user:private@host.test', 'https://host.test?token=private', 'not-a-url'])
def test_invalid_routing_configuration_does_not_expose_credentials(monkeypatch, url):
    monkeypatch.setenv('ROUTING_BASE_URL', url)
    monkeypatch.setenv('ROUTING_ENABLED', 'true')
    data = client.post('/api/commute', json={'origin': {'latitude': 52.2297, 'longitude': 21.0122}, 'destination': {'latitude': 52.24, 'longitude': 21.02}}).json()
    assert data['walking']['status'] == 'unavailable'
    assert 'private' not in json.dumps(data)


def test_retry_after_http_date_starts_provider_cooldown(monkeypatch):
    import time
    from email.utils import format_datetime
    deadline = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)
    monkeypatch.setattr(routing_service, '_last_request', 0)
    monkeypatch.setattr(routing_service, '_cooldown_until', 0)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={'Retry-After': deadline}))) as http:
            with pytest.raises(httpx.HTTPStatusError):
                await routing_service._fetch_route(http, routing_service.DEFAULT_BASE_URL,
                    RoutePoint(latitude=52.2297, longitude=21.0122), RoutePoint(latitude=52.24, longitude=21.02), 'walking')
        assert routing_service._cooldown_until - time.monotonic() > 110
    asyncio.run(run())


def test_line_manifest_dry_run_has_no_credentials_requests_or_writes(tmp_path, monkeypatch, capsys):
    from data_science import ingest_stop_lines
    from data_science.data_loader import load_stops
    stops = load_stops().iloc[:2]
    path = tmp_path / 'selection.json'
    selection = [{'stop_id': str(row.stop_id), 'platform': str(row.platform)} for row in stops.itertuples()]
    path.write_text(json.dumps({'platforms': selection}))
    output = tmp_path / 'lines.csv'
    monkeypatch.delenv('WARSAW_API_TOKEN', raising=False)
    monkeypatch.setattr(ingest_stop_lines, 'load_stops', lambda: stops)
    assert ingest_stop_lines.main(['--selection-file', str(path), '--limit', '2', '--dry-run', '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['would_request'] == 2
    assert not output.exists()
    path.write_text(json.dumps([{'stop_id': 1, 'platform': '01'}]))
    with pytest.raises(SystemExit):
        ingest_stop_lines.main(['--selection-file', str(path), '--dry-run'])
