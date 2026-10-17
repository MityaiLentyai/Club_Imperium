from copy import deepcopy
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.services import comparison_service
from backend.services.scoring_service import get_location_score
from data_science.comparison import compare_results

client = TestClient(app)
HOME_A = {"latitude": 52.2297, "longitude": 21.0122, "radius_m": 1000}
HOME_B = {"latitude": 52.263332, "longitude": 20.961636, "radius_m": 1000}
DESTINATION = {"latitude": 52.239, "longitude": 21.022}


def test_coordinate_comparison_preserves_measured_scores_and_features():
    response = client.post('/api/compare', json={'locations': [HOME_A, HOME_B]})
    assert response.status_code == 200
    result = response.json()
    assert len(result['locations']) == 2
    assert result['locations'][0]['scores'] == {'mobility': 92.7}
    assert result['locations'][1]['features']['nearest_sports_facility_m'] == 0
    rows = {row['metric']: row for row in result['comparisons']}
    assert rows['nearest_sports_facility_m']['advantage'] == 'b'
    assert rows['nearest_sports_facility_m']['status'] == 'comparable'
    assert rows['mobility_score']['values'] == [location['scores']['mobility'] for location in result['locations']]
    assert rows['partial_life_score']['values'] == rows['mobility_score']['values']
    assert result['warnings']
    assert 'commute' not in result['locations'][0]


def test_counts_with_different_radii_are_not_comparable():
    response = client.post('/api/compare', json={'locations': [HOME_A, {**HOME_B, 'radius_m': 500}]})
    rows = {row['metric']: row for row in response.json()['comparisons']}
    for key in ('parks_within_radius', 'listed_parking_within_radius', 'sports_facilities_within_radius'):
        assert rows[key]['status'] == 'incomparable'
        assert rows[key]['advantage'] is None
        assert 'Different radii' in rows[key]['reason']
    assert rows['nearest_sports_facility_m']['status'] == 'comparable'


def test_comparison_uses_shared_weights_and_excludes_unavailable_scores():
    result = client.post('/api/compare', json={'locations': [HOME_A, HOME_B], 'weights': {'mobility': 1, 'sports': 99}}).json()
    assert all(r['life_score']['normalized_weights'] == {'mobility': 100} for r in result['locations'])
    disabled = client.post('/api/compare', json={'locations': [HOME_A, HOME_B], 'weights': {'sports': 100}}).json()
    row = next(row for row in disabled['comparisons'] if row['metric'] == 'partial_life_score')
    assert row['values'] == [None, None]
    assert row['status'] == 'unavailable' and row['advantage'] is None


def test_comparison_accepts_addresses_and_revalidates_geocoder_result(monkeypatch):
    geocode = AsyncMock(return_value={**HOME_B, 'address': 'Verified address'})
    monkeypatch.setattr(comparison_service, 'geocode_address', geocode)
    result = client.post('/api/compare', json={'locations': [HOME_A, {'address': 'Elbląska 51'}]})
    assert result.status_code == 200
    assert result.json()['locations'][1]['location']['address'] == 'Verified address'
    geocode.assert_awaited_once_with('Elbląska 51')
    geocode.return_value = {'address': 'Invalid provider point', 'latitude': 0, 'longitude': 0}
    assert client.post('/api/compare', json={'locations': [HOME_A, {'address': 'Warszawa'}]}).status_code == 422


def test_comparison_destination_baseline_does_not_call_routing(monkeypatch):
    from backend.services import routing_service
    monkeypatch.setattr(routing_service, '_fetch_route', AsyncMock(side_effect=AssertionError('Unexpected external request')))
    result = client.post('/api/compare', json={'locations': [HOME_A, HOME_B], 'destination': DESTINATION}).json()
    for location in result['locations']:
        assert location['commute']['baseline']['distance_m'] > 0
        assert location['commute']['walking']['reason'] == 'Routes not requested'
    rows = {row['metric']: row for row in result['comparisons']}
    assert rows['commute_straight_line_m']['status'] == 'comparable'
    assert rows['walking_duration_minutes']['status'] == 'unavailable'


def test_comparison_routes_are_explicit_and_use_the_correct_origins(monkeypatch):
    calls = []
    async def commute(origin, destination, *, include_routes):
        calls.append((origin.model_dump(), destination.model_dump(), include_routes))
        duration = 15 if origin.latitude == HOME_A['latitude'] else 25
        return {'baseline': {'distance_m': 1000}, 'walking': {'status': 'available', 'distance_m': 1500, 'duration_minutes': duration, 'provider_url': 'same'},
                'driving': {'status': 'unavailable'}, 'transit': {'status': 'unavailable'}}
    monkeypatch.setattr(comparison_service, 'get_commute', commute)
    result = client.post('/api/compare', json={'locations': [HOME_A, HOME_B], 'destination': DESTINATION, 'include_routes': True}).json()
    assert len(calls) == 2
    assert calls[0][0]['latitude'] == HOME_A['latitude']
    assert calls[1][0]['latitude'] == HOME_B['latitude']
    assert all(call[1] == DESTINATION and call[2] for call in calls)
    rows = {row['metric']: row for row in result['comparisons']}
    assert rows['walking_duration_minutes']['advantage'] == 'a'
    assert rows['driving_duration_minutes']['values'] == [None, None]


@pytest.mark.parametrize('body', [
    {'locations': []}, {'locations': [HOME_A]}, {'locations': [HOME_A, HOME_B, HOME_A]},
    {'locations': [HOME_A, {'address': 'A'}]},
    {'locations': [HOME_A, {'latitude': 'NaN', 'longitude': 21}]},
    {'locations': [HOME_A, {'address': 'Warszawa', 'latitude': 52.2, 'longitude': 21}]},
    {'locations': [HOME_A, {**HOME_B, 'weights': {'mobility': 100}}]},
    {'locations': [HOME_A, HOME_B], 'include_routes': True},
])
def test_invalid_comparisons_do_not_request_external_data(body):
    assert client.post('/api/compare', json=body).status_code == 422


def test_different_sources_missing_values_and_equal_measurements():
    first = get_location_score(HOME_A['latitude'], HOME_A['longitude'])
    second = deepcopy(first)
    second['datasets']['green']['sha256'] = 'different'
    second['unavailable'].append('sports')
    rows = {row['metric']: row for row in compare_results([first, second])}
    assert rows['nearest_park_m']['status'] == 'incomparable'
    assert rows['nearest_sports_facility_m']['values'][1] is None
    assert rows['mobility_score']['advantage'] == 'equal'
    second['life_score']['contributions'] = []
    row = next(row for row in compare_results([first, second]) if row['metric'] == 'partial_life_score')
    assert row['status'] == 'incomparable'
