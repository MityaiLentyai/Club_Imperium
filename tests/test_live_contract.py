from unittest.mock import AsyncMock, patch

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from backend.main import app
from backend.services import scoring_service

client = TestClient(app)
COORDINATES = {"latitude": 52.2297, "longitude": 21.0122}


@pytest.fixture(autouse=True)
def mobility_contract_without_optional_datasets(monkeypatch):
    monkeypatch.setattr(scoring_service, 'get_parks', lambda: None)
    monkeypatch.setattr(scoring_service, 'get_parking', lambda: None)
    monkeypatch.setattr(scoring_service, 'get_sports', lambda: None)


def test_radius_filters_real_platforms_without_changing_score():
    small = client.post('/api/score', json={**COORDINATES, 'radius_m': 500}).json()
    large = client.post('/api/score', json={**COORDINATES, 'radius_m': 2000}).json()
    assert small['scores'] == large['scores'] == {'mobility': 92.7}
    assert small['features'] == large['features']
    assert small['places']
    assert small['nearby']['total'] <= large['nearby']['total']
    assert small['unavailable'] == ['grocery', 'pharmacy', 'green', 'parking', 'sports']
    stops = scoring_service.get_stops()
    point = gpd.GeoSeries([Point(COORDINATES['longitude'], COORDINATES['latitude'])], crs='EPSG:4326').to_crs(stops.crs).iloc[0]
    for result in (small, large):
        assert len(result['places']) <= result['nearby']['limit']
        assert len({p['id'] for p in result['places']}) == len(result['places'])
        assert [p['distance_m'] for p in result['places']] == sorted(p['distance_m'] for p in result['places'])
        for place in result['places']:
            row = stops[(stops.stop_id == place['stop_id']) & (stops.platform == place['platform'])].iloc[0]
            assert place['id'] == f"{row.stop_id}:{row.platform}"
            assert place['label'] == row.stop_name
            assert place['latitude'] == row.latitude and place['longitude'] == row.longitude
            assert place['category'] == 'transport' and place['distance_type'] == 'straight_line'
            assert place['distance_m'] == round(float(row.geometry.distance(point)), 1)
            assert place['distance_m'] <= result['radius_m']


def test_empty_transport_is_available():
    result = client.post('/api/score', json={**COORDINATES, 'radius_m': 1}).json()
    assert result['places'] == []
    assert result['nearby']['total'] == 0
    assert 'transport' not in result['unavailable']
    assert result['scores']['mobility'] == 92.7


def test_stop_limit_is_explicit(monkeypatch):
    monkeypatch.setattr(scoring_service, 'MAX_NEARBY_STOPS', 1)
    result = client.post('/api/score', json=COORDINATES).json()
    assert len(result['places']) == 1
    assert result['nearby']['truncated'] is True
    assert result['nearby']['total'] > 1


@pytest.mark.parametrize('radius', [0, -1, 2001, 'NaN', None, 1.5])
@pytest.mark.parametrize('endpoint', ['/api/score', '/api/score/address'])
def test_invalid_radius(endpoint, radius):
    body = {'address': 'Warszawa'} if endpoint.endswith('address') else COORDINATES
    response = client.post(endpoint, json={**body, 'radius_m': radius})
    assert response.status_code == 422


def test_address_and_coordinate_contract_match():
    location = {**COORDINATES, 'address': 'Warszawa'}
    with patch('backend.main.geocode_address', new=AsyncMock(return_value=location)):
        by_address = client.post('/api/score/address', json={'address': 'Warszawa', 'radius_m': 500})
    by_coordinates = client.post('/api/score', json={**COORDINATES, 'radius_m': 500})
    assert by_address.status_code == by_coordinates.status_code == 200
    address_result = by_address.json()
    assert address_result['location'].pop('address') == 'Warszawa'
    assert address_result == by_coordinates.json()
