"""Listed parking facilities only. Coverage does not justify a parking score."""
from data_science.infrastructure import load_snapshot, nearby_features


def load_parking(path=None):
    return load_snapshot("parking", path)


def calculate_parking_features(latitude, longitude, radius_m=1000, dataset=None):
    return nearby_features(latitude, longitude, radius_m, dataset, "parking")
