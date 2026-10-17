
from functools import lru_cache
import math

from fastapi import HTTPException
from pyproj.exceptions import ProjError

from backend.schemas import validate_supported_coordinates

from data_science.data_loader import load_stops
from data_science.mobility import (
    calculate_mobility_features,
    calculate_mobility_score,
)


@lru_cache(maxsize=1)
def get_stops():
    return load_stops()


def get_location_score(latitude, longitude):
    validate_supported_coordinates(latitude, longitude)
    stops = get_stops()

    try:
        features = calculate_mobility_features(
            latitude,
            longitude,
            stops=stops,
        )
    except (ProjError, OverflowError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Coordinates could not be projected safely for Warsaw scoring",
        ) from exc

    if not all(math.isfinite(value) for value in features.values()):
        raise HTTPException(
            status_code=422,
            detail="Coordinates produced non-finite distances during Warsaw scoring",
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
