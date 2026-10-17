"""Explicit bounded sports-site enrichment using exact municipal address points."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from data_science.ingest_infrastructure import download, save_snapshot, input_provenance, WFS_URL, GML, MAX_BYTES
from data_science.infrastructure import DATA_DIR, valid_coordinates

SPORTS_URL = "https://dane.um.warszawa.pl/api/action/get_be_otwarte_boiska"
CATALOGUE = "https://dane.um.warszawa.pl/en/catalogue/32a0ad2d-06d7-4e9c-acef-17a35c083d8c"
DAYS = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]


def address_parts(address):
    match = re.fullmatch(r"(ul\.|ulica|al\.|aleja)\s+(.+?)\s+(\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?)", address.strip(), re.IGNORECASE)
    return (("aleja " if match[1].casefold() in ("al.", "aleja") else "ulica ") + match[2], match[3]) if match else None


def parse_sites(payload):
    if not isinstance(payload, list) or len(payload) > 2000:
        raise ValueError("Unexpected sports response or source record cap exceeded")
    sites = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        address, name = row.get("Adres obiektu"), row.get("Nazwa placówki oświatowej")
        if not isinstance(address, str) or not isinstance(name, str) or not address.strip() or not name.strip():
            continue
        key = " ".join(address.casefold().split())
        site = sites.setdefault(key, {"name": name.strip(), "address": address.strip(),
            "district": row.get("Dzielnica"), "sport_types": set(), "schedules": []})
        for field in ("Typ obiektu", "Boisk uniwersalne zawiera"):
            if isinstance(row.get(field), str) and row[field].strip():
                site["sport_types"].add(row[field].strip())
        schedule = {day: row[day] for day in DAYS if isinstance(row.get(day), str) and row[day].strip()}
        details = {"sport_type": row.get("Typ obiektu"), "hours": schedule,
                   "notes": row.get("Uwagi"), "updated_at": row.get("Data aktualizacji")}
        if details not in site["schedules"]:
            site["schedules"].append(details)
    return [{**site, "sport_types": sorted(site["sport_types"])} for site in sites.values()]


def parse_address(raw, street, number, district):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsupported XML entities")
    members = ET.fromstring(raw).findall(f"{GML}featureMember")
    if len(members) >= 5:
        return None
    matches = []
    for member in members:
        record = next(iter(member), None)
        if record is None:
            continue
        props = {e.tag.split("}")[-1]: e.text for e in record}
        if (props.get("NAZWA_PODST") != street or props.get("NR_PORZADK") != number
                or props.get("DZIELNICA") != district):
            continue
        coords = record.find(f".//{GML}Point/{GML}coordinates")
        try:
            lon, lat = map(float, coords.text.split(","))
            if valid_coordinates(lat, lon) and props.get("ID"):
                matches.append({"longitude": lon, "latitude": lat, "address_id": props["ID"]})
        except (ValueError, TypeError, AttributeError):
            continue
    return matches[0] if len(matches) == 1 else None


def address_filter(street, number, district):
    root = ET.Element("Filter", xmlns="http://www.opengis.net/ogc")
    both = ET.SubElement(root, "And")
    for key, value in [("NAZWA_PODST", street), ("NR_PORZADK", number), ("DZIELNICA", district)]:
        equal = ET.SubElement(both, "PropertyIsEqualTo")
        ET.SubElement(equal, "PropertyName").text = key
        ET.SubElement(equal, "Literal").text = value
    return ET.tostring(root, encoding="unicode")


def select_sites(sites, limit=8, offset=0, indices=None):
    if not 1 <= limit <= 10 or offset < 0:
        raise ValueError("Select 1–10 sites per run")
    if indices is not None:
        if offset or not 1 <= len(indices) <= limit or len(set(indices)) != len(indices) or any(i < 0 or i >= len(sites) for i in indices):
            raise ValueError("Invalid explicit site indices")
        return [sites[i] for i in indices]
    return sites[offset:offset + limit]


def enrich_sites(sites, cache_dir, limit=8, fetch=download, offline=False, offset=0, indices=None):
    selected = select_sites(sites, limit, offset, indices)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    features, unresolved = [], []
    seen_points = set()
    for site in selected:
        parts = address_parts(site["address"])
        if not parts or not isinstance(site.get("district"), str):
            unresolved.append(site["address"])
            continue
        key = hashlib.sha256((site["address"] + "|" + site["district"]).encode()).hexdigest()[:16]
        cache = cache_dir / f"{key}.gml"
        provenance = cache.with_suffix(".json")
        retrieved_at = None
        if cache.exists():
            raw = cache.read_bytes()
            if provenance.exists():
                try:
                    saved = json.loads(provenance.read_text())
                    if saved["sha256"] == hashlib.sha256(raw).hexdigest():
                        retrieved_at = saved["retrieved_at"]
                except (ValueError, KeyError, TypeError):
                    pass
        elif offline:
            unresolved.append(site["address"])
            continue
        else:
            try:
                raw = fetch(WFS_URL, params={"service": "WFS", "version": "1.1.0", "request": "GetFeature",
                    "typeName": "wfs:PUNKTY_ADRESOWE_WGS84", "maxFeatures": 5, "outputFormat": "GML2",
                    "filter": address_filter(*parts, site["district"])})
                # Validate XML and reject entities before caching even a negative match.
                parse_address(raw, *parts, site["district"])
                retrieved_at = datetime.now(timezone.utc).isoformat()
                cache.write_bytes(raw)
                provenance.write_text(json.dumps({"retrieved_at": retrieved_at, "source_url": WFS_URL,
                    "sha256": hashlib.sha256(raw).hexdigest(), "street": parts[0], "number": parts[1], "district": site["district"]}, ensure_ascii=False) + "\n")
            except Exception:
                unresolved.append(site["address"])
                continue
            finally:
                time.sleep(1.1)
        try:
            point = parse_address(raw, *parts, site["district"])
        except (ValueError, ET.ParseError):
            point = None
        if not point:
            unresolved.append(site["address"])
            continue
        coordinate_key = (point["longitude"], point["latitude"])
        if coordinate_key in seen_points:
            continue
        seen_points.add(coordinate_key)
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(coordinate_key)},
            "properties": {**site, "source_id": key, "address_id": point["address_id"],
                "coordinate_retrieved_at": retrieved_at,
                "coordinate_source": "Warsaw municipal address point; proxy for site, not field or entrance"}})
    return features, {"selected_sites": len(selected), "unresolved_addresses": unresolved,
        "unresolved_count": len(unresolved), "source_sites": len(sites)}


def merge_snapshot(raw, features, metadata, output):
    """A bounded enrichment batch adds sites; it never drops earlier located sites."""
    previous_path = Path(output) / "sports.geojson"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
    if previous is not None:
        if previous["metadata"]["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("Sports source changed; use a new output directory to preserve the old snapshot")
        merged = {f["properties"]["source_id"]: f for f in previous["features"]}
        merged.update({f["properties"]["source_id"]: f for f in features})
        unresolved = set(previous["metadata"].get("unresolved_addresses", [])) | set(metadata["unresolved_addresses"])
        unresolved -= {f["properties"]["address"] for f in merged.values()}
        metadata.update(retrieved_at=previous["metadata"]["retrieved_at"],
            unresolved_addresses=sorted(unresolved), unresolved_count=len(unresolved))
        features = list(merged.values())
    metadata["selected_sites"] = len(features) + metadata["unresolved_count"]
    metadata["located_fraction_of_source_sites"] = len(features) / metadata["source_sites"] if metadata["source_sites"] else None
    metadata["districts_with_located_sites"] = sorted({f["properties"]["district"] for f in features})
    return features, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Saved official sports response; otherwise one authenticated request")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--site-index", type=int, action="append", help="Explicit source-site index; at most --limit, no automatic next batch")
    parser.add_argument("--dry-run", action="store_true", help="Requires --input; show the bounded selection without requests or writes")
    parser.add_argument("--offline", action="store_true", help="Use saved source and municipal address responses only")
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10 or args.offset < 0 or ((args.offline or args.dry_run) and not args.input):
        parser.error("Use --limit 1–10; --offline requires --input")
    try:
        if args.input:
            raw = args.input.read_bytes()
        else:
            token = os.getenv("WARSAW_API_TOKEN")
            if not token:
                raise ValueError("Token required")
            raw = download(SPORTS_URL, token=token, method="POST")
        if len(raw) > MAX_BYTES:
            raise ValueError("Source exceeded byte cap")
        payload = json.loads(raw)
        sites = parse_sites(payload)
        selected = select_sites(sites, args.limit, args.offset, args.site_index)
        if args.dry_run:
            print(json.dumps({"selected": [{"address": s["address"], "district": s["district"]} for s in selected], "maximum_address_requests": len(selected)}, ensure_ascii=False))
            return
        features, metadata = enrich_sites(sites, args.output / "sports_addresses", args.limit, offline=args.offline, offset=args.offset, indices=args.site_index)
        if not features:
            raise ValueError("No reliably located sites; previous snapshot preserved")
        metadata.update(source_url=SPORTS_URL, catalogue_url=CATALOGUE, source_records=len(payload),
            coordinate_source_url=WFS_URL, source_crs="EPSG:4326",
            coverage="Small bounded sample of educational sports sites; incomplete Warsaw coverage; address-point proxies")
        if args.input:
            metadata.update(input_provenance(raw, "sports", args.input, args.output))
        features, metadata = merge_snapshot(raw, features, metadata, args.output)
        saved = save_snapshot("sports", raw, features, metadata, args.output)
        print(f"Saved {saved['record_count']} located sports sites; {metadata['unresolved_count']} unresolved in selected sample")
    except Exception:
        parser.exit(1, "Sports refresh failed; previous snapshot preserved. No credential details logged.\n")


if __name__ == "__main__":
    main()
