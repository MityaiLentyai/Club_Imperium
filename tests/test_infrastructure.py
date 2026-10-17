import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest
from pyproj import Transformer
from shapely.geometry import Point, box, shape
from shapely import transform

from backend.main import app
from backend.services import scoring_service
from data_science.green import calculate_green_features, load_parks
from data_science.parking import calculate_parking_features, load_parking
from data_science.infrastructure import load_snapshot, valid_coordinates, TO_METRES
from data_science.ingest_infrastructure import parse_parks, parse_parking, save_snapshot

FIXTURES = Path(__file__).parent / 'fixtures' / 'infrastructure'
client = TestClient(app)
LOCATION = {'latitude': 52.2297, 'longitude': 21.0122}


def test_actual_wfs_schema_classification_and_crs():
    records, metadata = parse_parks((FIXTURES / 'parks-sample.gml').read_bytes())
    assert len(records) == 1
    assert metadata['classifications'] == {'Park': 1, 'Skwer': 1, 'Rondo': 1, 'Plac': 1}
    assert metadata['source_crs'] == 'EPSG:2178'
    bounds = shape(records[0]['geometry']).bounds
    assert valid_coordinates(bounds[1], bounds[0])
    assert valid_coordinates(bounds[3], bounds[2])
    assert records[0]['properties']['classification'] == 'Park'


def test_wfs_rejects_unknown_crs_malformed_or_capped_response():
    raw = (FIXTURES / 'parks-sample.gml').read_bytes()
    with pytest.raises(ValueError):
        parse_parks(raw.replace(b'EPSG:2178', b'EPSG:4326'))
    with pytest.raises(ValueError):
        parse_parks(b'<!DOCTYPE x [<!ENTITY e "bad">]><x/>')
    with pytest.raises(ValueError):
        parse_parks(b'<FeatureCollection/>')


def test_live_parking_schema_details_and_deduplication():
    payload = json.loads((FIXTURES / 'parking-live-sample.json').read_text())
    payload['carParks'] += [copy.deepcopy(payload['carParks'][0]), {'name': 'bad', 'latitude': 'NaN', 'longitude': 21}]
    records, metadata = parse_parking(payload)
    assert len(records) == 2
    assert metadata['source_records'] == 4
    assert metadata['provider_response_timestamp']
    assert records[0]['properties']['capacity'] == 47
    assert records[0]['properties']['tariffs']
    assert 'free_places_total' not in records[0]['properties']
    assert 'available_spaces' not in records[0]['properties']


def test_parking_rejects_error_payload_and_all_invalid_records():
    for payload in [{}, {'Status': 0, 'carParks': []}, {'Parkings': [{}]}, {'Parkings': [{}] * 500}]:
        with pytest.raises(ValueError):
            parse_parking(payload)
    assert parse_parking({'Status': 1, 'carParks': []})[0] == []


@pytest.mark.parametrize('lat,lon', [(float('nan'), 21), (52.2, float('inf')), (0, 0), (None, 21), ('bad', 21), (21, 52)])
def test_parking_coordinate_validation(lat, lon):
    assert not valid_coordinates(lat, lon)


def test_polygon_distance_inside_and_nearest_boundary():
    point = transform(Point(21.0122, 52.2297), TO_METRES, interleaved=False)
    polygon = box(point.x + 100, point.y - 50, point.x + 300, point.y + 50)
    geographic = transform(polygon, Transformer.from_crs(2180, 4326, always_xy=True).transform, interleaved=False)
    dataset = {'metadata': {}, 'records': [({'source_id': 'p', 'name': 'Test park'}, geographic, polygon)]}
    f, places, state = calculate_green_features(**LOCATION, radius_m=101, dataset=dataset)
    assert f == {'nearest_park_m': 100, 'parks_within_radius': 1}
    assert places[0]['distance_basis'] == 'park_area'
    assert state['total'] == 1
    assert calculate_green_features(**LOCATION, radius_m=99, dataset=dataset)[0]['parks_within_radius'] == 0
    # Inside the area means zero proximity, rather than distance back to its edge.
    dataset['records'][0] = ({'source_id': 'p', 'name': 'Test park'}, geographic, point.buffer(100))
    assert calculate_green_features(**LOCATION, dataset=dataset)[0]['nearest_park_m'] == 0


def test_snapshot_validation_missing_corrupt_empty_and_distinct_ids(tmp_path):
    path = tmp_path / 'snapshot.geojson'
    assert load_parks(path) is None
    path.write_text('{broken')
    assert load_parks(path) is None
    features, metadata = parse_parks((FIXTURES / 'parks-sample.gml').read_bytes())
    save_snapshot('green', b'saved-fixture', features * 2,
                  {**metadata, 'source_url': 'https://wfs.um.warszawa.pl/serwis'}, tmp_path)
    data = load_parks(tmp_path / 'green.geojson')
    assert len(data['records']) == 1
    payload = json.loads((tmp_path / 'green.geojson').read_text())
    payload['features'][0]['geometry'] = None
    payload['features'][1]['geometry'] = {'type': 'Polygon', 'coordinates': [[[1, 2]]]}
    path.write_text(json.dumps(payload))
    assert load_parks(path) is None
    payload['features'] = []
    path.write_text(json.dumps(payload))
    empty = load_parks(path)
    assert empty is not None
    assert calculate_green_features(**LOCATION, dataset=empty)[0] == {'nearest_park_m': None, 'parks_within_radius': 0}
    assert calculate_green_features(**LOCATION)[0] == {'nearest_park_m': None, 'parks_within_radius': None}


def test_api_real_snapshots_radius_mobility_and_backward_compatibility():
    small = client.post('/api/score', json={**LOCATION, 'radius_m': 500}).json()
    large = client.post('/api/score', json={**LOCATION, 'radius_m': 2000}).json()
    assert small['scores'] == large['scores'] == {'mobility': 92.7}
    assert small['features']['nearest_stop_m'] == large['features']['nearest_stop_m']
    assert small['features']['parks_within_radius'] <= large['features']['parks_within_radius']
    assert small['features']['listed_parking_within_radius'] <= large['features']['listed_parking_within_radius']
    assert {'green', 'parking'} <= {p['category'] for p in large['places']}
    for result in (small, large):
        assert all(p['distance_m'] <= result['radius_m'] for p in result['places'])
        assert len(result['places']) <= 300
        assert len({p['id'] for p in result['places']}) == len(result['places'])
        assert 'green' not in result['unavailable']
        assert 'parking' not in result['unavailable']
        assert all('available_spaces' not in p for p in result['places'])
    with patch('backend.main.geocode_address', new=AsyncMock(return_value={**LOCATION, 'address': 'Warszawa'})):
        by_address = client.post('/api/score/address', json={'address': 'Warszawa', 'radius_m': 500}).json()
    assert by_address['location'].pop('address') == 'Warszawa'
    assert by_address == small


def test_partial_and_missing_datasets_keep_mobility_responsive(monkeypatch):
    monkeypatch.setattr(scoring_service, 'get_parking', lambda: None)
    result = client.post('/api/score', json=LOCATION).json()
    assert 'parking' in result['unavailable'] and 'green' not in result['unavailable']
    assert result['features']['listed_parking_within_radius'] is None
    monkeypatch.setattr(scoring_service, 'get_parks', lambda: None)
    result = client.post('/api/score', json=LOCATION).json()
    assert result['scores'] == {'mobility': 92.7}
    assert {'green', 'parking'} <= set(result['unavailable'])


def test_marker_limit_reports_total_and_does_not_limit_features():
    from data_science.infrastructure import nearby_features
    data = load_parking()
    features, places, metadata = nearby_features(**LOCATION, radius_m=2000, dataset=data, category='parking', limit=1)
    assert len(places) == 1
    assert metadata['truncated']
    assert features['listed_parking_within_radius'] == metadata['total'] > 1
