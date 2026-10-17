"""Park-area proximity in EPSG:2180; no entrance or walking-distance claims."""
from data_science.infrastructure import load_snapshot, nearby_features


def load_parks(path=None):
    return load_snapshot("green", path)


def calculate_green_features(latitude, longitude, radius_m=1000, dataset=None):
    return nearby_features(latitude, longitude, radius_m, dataset, "green")
