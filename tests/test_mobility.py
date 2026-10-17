
"python -m pytest tests/test_mobility.py -v"
import pytest

from data_science.data_loader import load_stops
from data_science.mobility import (
    calculate_mobility_features,
    calculate_mobility_score,
)


@pytest.fixture(scope="module")
def stops():
    return load_stops()


def test_mobility_features(stops):
    features = calculate_mobility_features(
        52.2297,
        21.0122,
        stops=stops,
    )

    assert features["nearest_stop_m"] >= 0
    assert features["stop_groups_500m"] >= 0
    assert features["stop_groups_1000m"] >= features["stop_groups_500m"]


def test_score_range():
    features = {
        "nearest_stop_m": 250,
        "stop_groups_500m": 4,
    }

    score = calculate_mobility_score(features)

    assert 0 <= score <= 100


def test_score_decreases_with_distance():
    close = {
        "nearest_stop_m": 100,
        "stop_groups_500m": 4,
    }

    far = {
        "nearest_stop_m": 600,
        "stop_groups_500m": 4,
    }

    assert calculate_mobility_score(
        close
    ) > calculate_mobility_score(far)


def test_invalid_coordinates(stops):
    with pytest.raises(ValueError):
        calculate_mobility_features(
            100,
            21.0122,
            stops=stops,
        )
