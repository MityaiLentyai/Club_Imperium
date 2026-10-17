"""Sports-site features: verified address points, with explicitly partial coverage."""
from data_science.infrastructure import load_snapshot, nearby_features


def load_sports(path=None):
    return load_snapshot("sports", path)


def calculate_sports_features(latitude, longitude, radius_m=1000, dataset=None):
    return nearby_features(latitude, longitude, radius_m, dataset, "sports")
