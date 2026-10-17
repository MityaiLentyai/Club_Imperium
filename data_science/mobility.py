
import geopandas as gpd
from shapely.geometry import Point

from data_science.data_loader import load_stops


def calculate_mobility_features(latitude, longitude, stops=None):
    """
    Calculate transport accessibility around a location.

    Distances are measured in metres, straight-line.
    """
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid coordinates")

    if stops is None:
        stops = load_stops()

    if stops.empty:
        raise ValueError("Stops dataset is empty")

    apartment = gpd.GeoSeries(
        [Point(longitude, latitude)],
        crs="EPSG:4326"
    ).to_crs(stops.crs).iloc[0]

    distances = stops.geometry.distance(apartment)

    nearby_500 = stops.loc[distances <= 500]
    nearby_1000 = stops.loc[distances <= 1000]

    return {
        "nearest_stop_m": round(float(distances.min()), 1),
        "stop_groups_500m": int(
            nearby_500["stop_id"].nunique()
        ),
        "stop_groups_1000m": int(
            nearby_1000["stop_id"].nunique()
        ),
    }


def calculate_mobility_score(features):
    """
    Return a preliminary mobility score between 0 and 100.
    """
    distance = features["nearest_stop_m"]
    stop_count = features["stop_groups_500m"]

    distance_score = max(
        0.0,
        100 * (1 - distance / 800)
    )

    density_score = min(
        100.0,
        100 * stop_count / 8
    )

    score = 0.6 * distance_score + 0.4 * density_score

    return round(score, 1)
