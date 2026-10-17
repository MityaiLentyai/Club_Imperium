
import math
from functools import lru_cache

import geopandas as gpd
from fastapi import HTTPException
from pyproj.exceptions import ProjError
from shapely.geometry import Point

from backend.schemas import validate_supported_coordinates

from data_science.data_loader import load_stops
from data_science.stop_lines import CACHE_PATH, SOURCE_URL, LineCache, read_cache, calculate_line_features
from data_science.green import load_parks, calculate_green_features
from data_science.parking import load_parking, calculate_parking_features
from data_science.sports import load_sports, calculate_sports_features
from data_science.life_score import calculate_life_score
from data_science.mobility import (
    calculate_mobility_features,
    calculate_mobility_score,
)


@lru_cache(maxsize=1)
def get_stops():
    try:
        stops = load_stops()
        if stops.empty:
            raise ValueError("Empty transport snapshot")
        return stops
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Transport dataset unavailable") from exc


@lru_cache(maxsize=1)
def get_parks():
    return load_parks()


@lru_cache(maxsize=1)
def get_parking():
    return load_parking()


@lru_cache(maxsize=1)
def get_sports():
    return load_sports()


@lru_cache(maxsize=1)
def _cached_lines(path, modified, size):
    return read_cache(path)


def get_stop_lines():
    try:
        info = CACHE_PATH.stat()
        return _cached_lines(CACHE_PATH, info.st_mtime_ns, info.st_size)
    except FileNotFoundError:
        return LineCache()
    except OSError:
        return LineCache(status="error")


MAX_NEARBY_STOPS = 200


def get_location_score(latitude, longitude, radius_m=1000, weights=None):
    validate_supported_coordinates(latitude, longitude)
    if not 1 <= radius_m <= 2000:
        raise HTTPException(status_code=422, detail="Radius must be between 1 and 2000 metres")
    stops = get_stops()

    try:
        features = calculate_mobility_features(
            latitude,
            longitude,
            stops=stops,
        )
        # Marker radius is independent of the fixed scoring feature radii.
        point = gpd.GeoSeries(
            [Point(longitude, latitude)], crs="EPSG:4326"
        ).to_crs(stops.crs).iloc[0]
        distances = stops.geometry.distance(point)
        nearby = stops.loc[distances <= radius_m].copy()
        nearby["distance_m"] = distances.loc[nearby.index]
        nearby = nearby.sort_values(["distance_m", "stop_id", "platform"])
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

    places = [
        {
            "id": f"{stop.stop_id}:{stop.platform}",
            "stop_id": str(stop.stop_id),
            "platform": str(stop.platform),
            "category": "transport",
            "label": str(stop.stop_name),
            "latitude": float(stop.latitude),
            "longitude": float(stop.longitude),
            "distance_m": round(float(stop.distance_m), 1),
            "distance_type": "straight_line",
        }
        for stop in nearby.head(MAX_NEARBY_STOPS).itertuples()
    ]

    line_cache = get_stop_lines()
    line_features = calculate_line_features(latitude, longitude, stops, line_cache, radius_m)
    for place in places:
        row = line_cache.records.get((place["stop_id"], place["platform"]))
        if row and row["status"] == "success":
            place.update(lines=row["lines"], lines_retrieved_at=row["retrieved_at"],
                         line_data_status="refresh_failed" if row["error_code"] else "available")
        else:
            place["line_data_status"] = "error" if (row or line_cache.status == "error") else "missing"

    datasets = {}
    sources = [{"name": "Warsaw transport stops (stops_clean.csv)"}]
    if line_features["line_data_coverage"]["known_platforms"]:
        sources.append({"name": "Warsaw Open Data / ZTM — observed transport lines", "url": SOURCE_URL,
                        "retrieved_at": line_features["line_data_coverage"]["latest_retrieved_at"]})
    unavailable = ["grocery", "pharmacy"]
    for category, calculate, dataset in (
        ("green", calculate_green_features, get_parks()),
        ("parking", calculate_parking_features, get_parking()),
        ("sports", calculate_sports_features, get_sports()),
    ):
        extra_features, extra_places, metadata = calculate(latitude, longitude, radius_m, dataset)
        features.update(extra_features)
        places.extend(extra_places)
        datasets[category] = metadata
        if metadata["status"] == "unavailable":
            unavailable.append(category)
        else:
            sources.append({"name": f"Warsaw {category} snapshot", "url": metadata["source_url"],
                            "retrieved_at": metadata["retrieved_at"]})

    return {
        "life_score": calculate_life_score({"mobility": mobility_score}, weights),
        "line_features": line_features,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "scores": {
            "mobility": mobility_score,
        },
        "features": features,
        "radius_m": radius_m,
        "places": places,
        "unavailable": unavailable,
        "datasets": datasets,
        "nearby": {
            "total": len(nearby),
            "limit": MAX_NEARBY_STOPS,
            "truncated": len(nearby) > MAX_NEARBY_STOPS,
        },
        "sources": sources,
    }
