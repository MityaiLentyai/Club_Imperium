"""Bounded official-source refresh: python -m data_science.ingest_infrastructure."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import httpx
from pyproj import Transformer
from shapely.geometry import Polygon, mapping, Point, shape
from shapely import transform
from shapely.ops import unary_union
from shapely.errors import ShapelyError

from data_science.infrastructure import DATA_DIR, valid_coordinates

WFS_URL = "https://wfs.um.warszawa.pl/serwis"
PARKING_URL = "https://dane.um.warszawa.pl/api/action/get_m_parkingi_wolne_miejsca"
CATALOGUE_URL = "https://dane.um.warszawa.pl/en/catalogue/20ec668b-e5f3-4cbf-aeeb-eb825f3c8731"
PARKS_PARAMS = {"service": "WFS", "version": "1.1.0", "request": "GetFeature",
                "typeName": "ns92528565:PLACE_SKWERY", "maxFeatures": 500,
                "outputFormat": "GML2"}
MAX_BYTES = 8_000_000
MAX_PARKING_RECORDS = 500
GML = "{http://www.opengis.net/gml}"


def parse_parks(raw):
    """Actual GML2 layer: EPSG:2178 easting/northing; OBIEKT=Park only."""
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML entities are unsupported")
    root = ET.fromstring(raw)
    members = root.findall(f"{GML}featureMember")
    if not members or len(members) >= 500:
        raise ValueError("Empty, unexpected, or capped WFS response; preserve prior snapshot")
    to_wgs = Transformer.from_crs(2178, 4326, always_xy=True).transform
    groups, classifications = {}, Counter()
    for member in members:
        record = next(iter(member), None)
        if record is None:
            continue
        props = {el.tag.split("}")[-1]: el.text for el in record}
        classifications[props.get("OBIEKT")] += 1
        if props.get("OBIEKT") != "Park" or not props.get("ID") or not props.get("NAZWA_PODST"):
            continue
        polygons = []
        try:
            for polygon in record.iter(f"{GML}Polygon"):
                if polygon.get("srsName") != "EPSG:2178":
                    raise ValueError("Unexpected source CRS")
                def ring(element):
                    coords = element.find(f".//{GML}coordinates")
                    return [tuple(map(float, pair.split(","))) for pair in coords.text.split()]
                exterior = polygon.find(f"{GML}outerBoundaryIs")
                holes = [ring(el) for el in polygon.findall(f"{GML}innerBoundaryIs")]
                geom = Polygon(ring(exterior), holes)
                if not geom.is_empty and geom.is_valid:
                    polygons.append(geom)
            if not polygons:
                continue
            geom = transform(unary_union(polygons), to_wgs, interleaved=False)
            minx, miny, maxx, maxy = geom.bounds
            if (geom.geom_type not in ("Polygon", "MultiPolygon") or not geom.is_valid
                    or not valid_coordinates(miny, minx) or not valid_coordinates(maxy, maxx)):
                continue
            identifier = str(props["ID"])
            if identifier in groups:
                groups[identifier]["geometry"] = mapping(unary_union([
                    geom, shape(groups[identifier]["geometry"])]))
            else:
                groups[identifier] = {"type": "Feature", "geometry": mapping(geom),
                    "properties": {"source_id": identifier, "name": props["NAZWA_PODST"],
                                   "classification": "Park", "districts": props.get("DZIELNICE")}}
        except (TypeError, ValueError, AttributeError, ShapelyError):
            continue
    if not groups:
        raise ValueError("No validated parks; preserve prior snapshot")
    return list(groups.values()), {"source_records": len(members),
                                   "classifications": dict(classifications), "source_crs": "EPSG:2178"}


def parse_parking(payload):
    if not isinstance(payload, dict):
        raise ValueError("Unexpected parking response; preserve prior snapshot")
    # The live envelope differs from the catalogue's illustrative Parkings example.
    if "carParks" in payload and payload.get("Status") != 1:
        raise ValueError("Parking provider reports failure")
    rows = payload.get("carParks", payload.get("Parkings"))
    if not isinstance(rows, list):
        raise ValueError("Unexpected parking response; preserve prior snapshot")
    if len(rows) >= MAX_PARKING_RECORDS:
        raise ValueError("Parking record cap reached")
    records, seen, seen_ids = [], set(), set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        lat, lon = row.get("latitude"), row.get("longitude")
        name = str(row.get("name") or "").strip()
        if not name or not valid_coordinates(lat, lon):
            continue
        lat, lon = float(lat), float(lon)
        key = (round(lat, 6), round(lon, 6))
        if key in seen:
            continue
        seen.add(key)
        source_id = row.get("id") or hashlib.sha256(f"{lat:.6f},{lon:.6f}".encode()).hexdigest()[:16]
        if str(source_id) in seen_ids:
            continue
        seen_ids.add(str(source_id))
        props = {"source_id": str(source_id), "name": name}
        for source, target in (("adress", "address"), ("opening_hours", "opening_hours"),
                               ("tariffs", "tariffs")):
            value = row.get(source)
            if isinstance(value, (str, list, dict)) and value:
                # Bound individual facility details as well as whole response size.
                if len(json.dumps(value, ensure_ascii=False)) <= 12000:
                    props[target] = value
        levels = row.get("total_places")
        if isinstance(levels, list) and levels:
            counts = [level.get(kind) for level in levels if isinstance(level, dict)
                      for kind in ("standard", "disabled", "electric")]
            if (len(counts) == len(levels) * 3 and all(type(n) is int and n >= 0 for n in counts)):
                props["capacity"] = sum(counts)
        # free_places_total has no observation timestamp in the documented schema.
        # Retain it in raw snapshots only, never publish it as current availability.
        records.append({"type": "Feature", "properties": props,
                        "geometry": mapping(Point(lon, lat))})
    if rows and not records:
        raise ValueError("No valid parking coordinates")
    return records, {"source_records": len(rows), "provider_response_timestamp": payload.get("Timestamp")}


def download(url, *, params=None, token=None, method="GET"):
    headers = {"Authorization": token} if token else {}
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        with client.stream(method, url, params=params, headers=headers) as response:
            if response.status_code != 200:
                raise ValueError(f"Official source returned HTTP {response.status_code}")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Source response exceeded 8 MB")
                chunks.append(chunk)
    return b"".join(chunks)


def save_snapshot(category, raw, features, metadata, output=DATA_DIR):
    """Archive by content hash; atomic replace leaves old snapshots safe on failure."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    suffix = "gml" if category == "green" else "json"
    archive = output / "raw"
    archive.mkdir(exist_ok=True)
    raw_path = archive / f"{category}-{digest[:16]}.{suffix}"
    if not raw_path.exists():
        raw_path.write_bytes(raw)
    metadata = {**metadata, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest, "record_count": len(features), "raw_file": f"raw/{raw_path.name}"}
    content = {"type": "FeatureCollection", "metadata": metadata, "features": features}
    with tempfile.NamedTemporaryFile(mode="w", dir=output, delete=False, suffix=".tmp") as f:
        json.dump(content, f, ensure_ascii=False, allow_nan=False)
    os.replace(f.name, output / f"{category}.geojson")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category", choices=["green", "parking"])
    parser.add_argument("--input", type=Path, help="Reparse a saved official response without network")
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    try:
        if args.input:
            raw = args.input.read_bytes()
            if len(raw) > MAX_BYTES:
                raise ValueError("Input exceeds 8 MB")
        elif args.category == "green":
            raw = download(WFS_URL, params=PARKS_PARAMS)
        else:
            token = os.getenv("WARSAW_API_TOKEN")
            if not token:
                raise ValueError("Set backend-only WARSAW_API_TOKEN before parking refresh")
            raw = download(PARKING_URL, token=token, method="POST")
        if args.category == "green":
            features, metadata = parse_parks(raw)
            metadata.update(source_url=WFS_URL, request_parameters=PARKS_PARAMS,
                            coverage="Named park polygons only; completeness of Warsaw green space is unverified")
        else:
            features, metadata = parse_parking(json.loads(raw))
            metadata.update(source_url=PARKING_URL, catalogue_url=CATALOGUE_URL,
                            coverage="Participating ZTP, ZDM and PKiN facilities only; incomplete coverage",
                            availability="Observation timestamp absent; no current availability published")
        result = save_snapshot(args.category, raw, features, metadata, args.output)
        print(f"Saved {result['record_count']} {args.category} records")
    except (ValueError, OSError, httpx.HTTPError, ET.ParseError):
        # Never print request headers, environment values or exception URLs.
        parser.exit(1, "Refresh failed (source, credentials or schema unavailable); prior snapshot preserved.\n")


if __name__ == "__main__":
    main()
