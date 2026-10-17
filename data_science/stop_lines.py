"""Offline stop-line cache and spatial features; never performs network I/O."""
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from data_science.data_loader import PROJECT_ROOT

CACHE_PATH = PROJECT_ROOT / "data" / "stop_lines.csv"
SOURCE_URL = "https://dane.um.warszawa.pl/en/catalogue/8eb065b6-f3a0-41d4-a842-732c6c1c3063"
COLUMNS = ["stop_id", "platform", "lines", "status", "retrieved_at", "attempted_at", "error_code", "source_url"]


def parse_lines(payload):
    """Parse the documented list of {values: [{key: linia, value: ...}]}.

    Only a genuinely empty top-level list means known-empty service. Malformed
    or error payloads must never become a successful empty result.
    """
    if not isinstance(payload, list):
        raise ValueError("Expected a list of line records")
    lines = set()
    for record in payload:
        if not isinstance(record, dict) or not isinstance(record.get("values"), list):
            raise ValueError("Invalid line record")
        found = False
        for entry in record["values"]:
            if not isinstance(entry, dict) or "key" not in entry or "value" not in entry:
                raise ValueError("Invalid key/value entry")
            if entry["key"] == "linia":
                value = entry["value"]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Invalid line identifier")
                lines.add(value.strip())
                found = True
        if not found:
            raise ValueError("Line record has no line identifier")
    return sorted(lines)


@dataclass
class LineCache:
    records: dict = field(default_factory=dict)
    status: str = "missing"


def _timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Cache timestamps must include a timezone")


def read_cache(path=CACHE_PATH):
    path = Path(path)
    if not path.exists():
        return LineCache()
    try:
        with path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != COLUMNS:
                raise ValueError("Unexpected cache columns")
            records = {}
            for row in reader:
                key = (row["stop_id"], row["platform"])
                if not all(key) or key in records or row["status"] not in {"success", "error"}:
                    raise ValueError("Invalid cache identifier or status")
                _timestamp(row["attempted_at"])
                if row["source_url"] != SOURCE_URL:
                    raise ValueError("Unexpected cache source")
                if row["status"] == "success":
                    _timestamp(row["retrieved_at"])
                    lines = json.loads(row["lines"])
                    if not isinstance(lines, list) or any(not isinstance(x, str) or not x.strip() for x in lines):
                        raise ValueError("Invalid cached lines")
                    row["lines"] = sorted(set(lines))
                else:
                    if row["retrieved_at"] or row["lines"] or not row["error_code"]:
                        raise ValueError("Invalid failure record")
                    row["lines"] = None
                records[key] = row
        return LineCache(records, "loaded" if records else "missing")
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        return LineCache(status="error")


def calculate_line_features(latitude, longitude, stops, cache, radius_m=1000):
    """Count observed unique lines, keeping coverage independent of marker limits."""
    point = gpd.GeoSeries([Point(longitude, latitude)], crs="EPSG:4326").to_crs(stops.crs).iloc[0]
    distances = stops.geometry.distance(point)
    keys = list(zip(stops.stop_id, stops.platform))
    # Only cache entries that join the current stop dataset count as coverage.
    matched = {key: cache.records[key] for key in keys if key in cache.records}

    def window(selected):
        rows = [matched.get(keys[i]) for i, include in enumerate(selected) if include]
        known = [r for r in rows if r and r["status"] == "success"]
        failed = sum(bool(r and r["status"] == "error") for r in rows)
        refresh_failed = sum(bool(r["error_code"]) for r in known)
        count = len(rows)
        status = ("no_platforms" if not count else "complete" if len(known) == count
                  else "partial" if known else "error" if failed or cache.status == "error" else "missing")
        coverage = {"status": status, "known_platforms": len(known), "total_platforms": count,
                    "failed_platforms": failed, "refresh_failed_platforms": refresh_failed,
                    "fraction": len(known) / count if count else None}
        lines = sorted({line for row in known for line in row["lines"]})
        return (len(lines) if known or not count else None), coverage

    count500, coverage500 = window(distances <= 500)
    count1000, coverage1000 = window(distances <= 1000)
    count_radius, coverage_radius = window(distances <= radius_m)
    # Stable tie-breaking agrees with the nearby-marker sort.
    order = stops.assign(_distance=distances).sort_values(["_distance", "stop_id", "platform"])
    nearest = order.iloc[0] if len(order) else None
    row = matched.get((nearest.stop_id, nearest.platform)) if nearest is not None else None
    known = [r for r in matched.values() if r["status"] == "success"]
    return {
        "distinct_lines_500m": count500,
        "distinct_lines_1000m": count1000,
        "distinct_lines_radius": count_radius,
        "radius_m": radius_m,
        "nearest_stop_lines": row["lines"] if row and row["status"] == "success" else None,
        "line_data_coverage": {
            "data_status": cache.status,
            "known_platforms": len(known), "total_platforms": len(stops),
            "failed_platforms": sum(r["status"] == "error" for r in matched.values()),
            "refresh_failed_platforms": sum(bool(r["error_code"]) for r in known),
            "latest_retrieved_at": max((r["retrieved_at"] for r in known), default=None),
            "within_500m": coverage500, "within_1000m": coverage1000,
            "within_radius": coverage_radius,
        },
    }
