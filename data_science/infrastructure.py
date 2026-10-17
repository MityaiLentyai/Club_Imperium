"""Validated local infrastructure snapshots; scoring never makes network calls."""
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.errors import ShapelyError
from shapely import transform

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "infrastructure"
TO_METRES = Transformer.from_crs(4326, 2180, always_xy=True).transform


def valid_coordinates(latitude, longitude):
    try:
        return (math.isfinite(float(latitude)) and math.isfinite(float(longitude))
                and 52.0 <= float(latitude) <= 52.4
                and 20.75 <= float(longitude) <= 21.3)
    except (TypeError, ValueError, OverflowError):
        return False


def load_snapshot(category, path=None):
    """Missing/corrupt snapshots are unavailable, never an empty coverage claim."""
    try:
        data = json.loads(Path(path or DATA_DIR / f"{category}.geojson").read_text())
        if (data.get("type") != "FeatureCollection"
                or not isinstance(data.get("features"), list)
                or not isinstance(data.get("metadata"), dict)
                or not data["metadata"].get("retrieved_at")
                or not data["metadata"].get("source_url")):
            return None
        records, seen, seen_points = [], set(), set()
        for feature in data["features"]:
            try:
                props = feature["properties"]
                identifier = str(props["source_id"])
                geom = shape(feature["geometry"])
                if (identifier in seen or not props.get("name") or geom.is_empty
                        or not geom.is_valid):
                    continue
                if category == "green" and (props.get("classification") != "Park"
                        or geom.geom_type not in ("Polygon", "MultiPolygon")):
                    continue
                if category == "parking" and geom.geom_type != "Point":
                    continue
                if category == "parking":
                    key = (round(geom.x, 6), round(geom.y, 6))
                    if key in seen_points:
                        continue
                minx, miny, maxx, maxy = geom.bounds
                if not (valid_coordinates(miny, minx) and valid_coordinates(maxy, maxx)):
                    continue
                projected = transform(geom, TO_METRES, interleaved=False)
                if not all(math.isfinite(v) for v in projected.bounds):
                    continue
                seen.add(identifier)
                if category == "parking":
                    seen_points.add(key)
                records.append((props, geom, projected))
            except (KeyError, TypeError, ValueError, ShapelyError):
                continue
        # Nonempty files with no usable geometry are corrupt, not empty coverage.
        if data["features"] and not records:
            return None
        return {"metadata": data["metadata"], "records": records}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def nearby_features(latitude, longitude, radius_m, dataset, category, limit=50):
    if not valid_coordinates(latitude, longitude):
        raise ValueError("Invalid Warsaw coordinates")
    if not 1 <= radius_m <= 2000:
        raise ValueError("Invalid radius")
    keys = (("nearest_park_m", "parks_within_radius") if category == "green"
            else ("nearest_listed_parking_m", "listed_parking_within_radius"))
    if dataset is None:
        return {keys[0]: None, keys[1]: None}, [], {"status": "unavailable"}
    point = transform(Point(longitude, latitude), TO_METRES, interleaved=False)
    measured = []
    for props, geographic, projected in dataset["records"]:
        # Zero inside a park; otherwise distance to its closest boundary.
        distance = float(projected.distance(point))
        measured.append((distance, str(props["source_id"]), props, geographic))
    measured.sort(key=lambda row: (row[0], row[1]))
    nearby = [row for row in measured if row[0] <= radius_m]
    places = []
    for distance, identifier, props, geom in nearby[:limit]:
        marker = geom.representative_point()
        place = {"id": f"{category}:{identifier}", "category": category,
                 "label": props["name"], "latitude": marker.y, "longitude": marker.x,
                 "distance_m": round(distance, 1), "distance_type": "straight_line",
                 "distance_basis": "park_area" if category == "green" else "facility_point"}
        if category == "parking":
            # Availability is deliberately not shown: provider has no observation timestamp.
            for key in ("capacity", "tariffs", "opening_hours", "address"):
                if key in props:
                    place[key] = props[key]
            place["availability_status"] = "unknown_observation_time"
        places.append(place)
    return ({keys[0]: round(measured[0][0], 1) if measured else None,
             keys[1]: len(nearby)}, places,
            {"status": "available", "total": len(nearby), "limit": limit,
             "truncated": len(nearby) > limit, **dataset["metadata"]})
