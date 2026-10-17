
from functools import lru_cache

from data_science.data_loader import load_stops
from data_science.mobility import (
    calculate_mobility_features,
    calculate_mobility_score,
)


@lru_cache(maxsize=1)
def get_stops():
    return load_stops()


def get_location_score(latitude, longitude):
    stops = get_stops()

    features = calculate_mobility_features(
        latitude,
        longitude,
        stops=stops,
    )

    mobility_score = calculate_mobility_score(features)

    return {
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "scores": {
            "mobility": mobility_score,
        },
        "features": features,
    }
