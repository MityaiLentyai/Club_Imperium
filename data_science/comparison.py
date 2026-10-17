"""Compare measured values, preserving missingness and coverage restrictions."""
import math


def compare_results(results):
    if len(results) != 2:
        raise ValueError("Exactly two location results are required")
    rows = []

    def add(metric, values, preference, unit, reason=None):
        values = [value if type(value) in (int, float) and math.isfinite(value) else None for value in values]
        status, advantage = "comparable", None
        if any(value is None for value in values):
            status, reason = "unavailable", "One or both measured values are unavailable"
        elif reason:
            status = "incomparable"
        else:
            difference = values[0] - values[1]
            advantage = "equal" if abs(difference) < 0.05 else (
                "a" if (difference > 0) == (preference == "higher") else "b")
        rows.append({"metric": metric, "values": values, "unit": unit, "preference": preference,
                     "status": status, "advantage": advantage, "reason": reason})

    add("mobility_score", [r["scores"].get("mobility") for r in results], "higher", "points")
    components = [{c["category"]: c["weight_percent"] for c in r["life_score"]["contributions"]} for r in results]
    add("partial_life_score", [r["life_score"]["value"] for r in results], "higher", "points",
        "Different contributing score categories or effective weights" if components[0] != components[1] else None)
    add("nearest_stop_m", [r["features"].get("nearest_stop_m") for r in results], "lower", "metres")
    add("stop_groups_500m", [r["features"].get("stop_groups_500m") for r in results], "higher", "stop_groups")
    for category, nearest, count in (
        ("green", "nearest_park_m", "parks_within_radius"),
        ("parking", "nearest_listed_parking_m", "listed_parking_within_radius"),
        ("sports", "nearest_sports_facility_m", "sports_facilities_within_radius"),
    ):
        hashes = [r.get("datasets", {}).get(category, {}).get("sha256") for r in results]
        reason = "Different or unverified source snapshots" if not hashes[0] or hashes[0] != hashes[1] else None
        values = lambda key: [None if category in r["unavailable"] else r["features"].get(key) for r in results]
        add(nearest, values(nearest), "lower", "metres", reason)
        add(count, values(count), "higher", "listed_sites",
            "Different radii; nearby counts are not comparable" if results[0]["radius_m"] != results[1]["radius_m"] else reason)
    if all("commute" in r for r in results):
        add("commute_straight_line_m", [r["commute"]["baseline"]["distance_m"] for r in results], "lower", "metres")
        for mode in ("walking", "driving"):
            routes = [r["commute"][mode] for r in results]
            reason = "Different routing providers" if routes[0].get("provider_url") != routes[1].get("provider_url") else None
            for field, unit in (("distance_m", "metres"), ("duration_minutes", "minutes_estimated")):
                add(f"{mode}_{field}", [route.get(field) if route["status"] == "available" else None for route in routes],
                    "lower", unit, reason)
    return rows
