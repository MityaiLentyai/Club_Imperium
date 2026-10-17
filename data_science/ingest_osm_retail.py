"""Offline full-extract OSM retail ingestion; PyOsmium is ingestion-only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from pyproj import Transformer
from shapely import from_wkb, transform
from shapely.geometry import Point, mapping
from shapely.errors import ShapelyError
from shapely.strtree import STRtree

from data_science.geography import load_boundaries, TO_METRES
from data_science.ingestion_io import atomic_bytes, atomic_json

KINDS = ('supermarket', 'convenience', 'grocery', 'pharmacy')
LICENSE_URL = 'https://opendatacommons.org/licenses/odbl/1-0/'
ATTRIBUTION = '© OpenStreetMap contributors'
TO_WGS = Transformer.from_crs(2180, 4326, always_xy=True).transform


def kind_for(tags):
    # A pharmacy with a shop tag remains one pharmacy, not two facilities.
    if tags.get('amenity') == 'pharmacy':
        return 'pharmacy'
    return tags.get('shop') if tags.get('shop') in KINDS[:3] else None


def extract_objects(path, city):
    import osmium

    factory = osmium.geom.WKBFactory()
    selected, assembled, records = {}, set(), []
    reasons = Counter()
    city_m = transform(city, TO_METRES, interleaved=False)
    filters = osmium.filter.TagFilter(('shop', 'supermarket'), ('shop', 'convenience'),
                                     ('shop', 'grocery'), ('amenity', 'pharmacy'))
    # Internal node-location and area assembly handlers see the full extract.
    # The output tag filter only reduces Python callbacks, never geometry inputs.
    processor = osmium.FileProcessor(str(path)).with_locations('flex_mem').with_areas().with_filter(filters)
    for obj in processor:
        tags = dict(obj.tags)
        kind = kind_for(tags)
        if kind is None:
            continue
        is_area = obj.is_area()
        osm_type = ('way' if obj.from_way() else 'relation') if is_area else {
            'n': 'node', 'w': 'way', 'r': 'relation'}[obj.type_str()]
        identifier = f'{osm_type}/{obj.orig_id() if is_area else obj.id}'
        if not is_area:
            selected[identifier] = {
                'osm_type': osm_type, 'osm_id': str(obj.id), 'osm_identifier': identifier,
                'kind': kind, 'category': 'pharmacy' if kind == 'pharmacy' else 'grocery',
                'name': tags.get('name'), 'tags': tags,
                'osm_timestamp': obj.timestamp.isoformat() if obj.timestamp else None,
                'address': {k[5:]: v for k, v in tags.items() if k.startswith('addr:')},
                'opening_hours': tags.get('opening_hours'),
                'member_ways': [str(m.ref) for m in obj.members if m.type == 'w'] if obj.is_relation() else [],
            }
        if not obj.is_node() and not is_area:
            continue
        assembled.add(identifier)
        try:
            geom = (from_wkb(factory.create_multipolygon(obj)) if is_area
                    else Point(obj.location.lon, obj.location.lat))
            if geom.is_empty or not geom.is_valid:
                reasons['invalid_geometry'] += 1
                continue
            metric = transform(geom, TO_METRES, interleaved=False)
            if not metric.intersects(city_m):
                reasons['outside_warsaw'] += 1
                continue
            clipped = metric.intersection(city_m)
            if clipped.is_empty or not clipped.is_valid or clipped.geom_type not in ('Point', 'Polygon', 'MultiPolygon'):
                reasons['invalid_or_non_area_clip'] += 1
                continue
            # Defer properties until all original objects have been visited.
            records.append((identifier, clipped, not metric.equals(clipped)))
        except (ValueError, RuntimeError, ShapelyError):
            reasons['geometry_error'] += 1
    for identifier in selected.keys() - assembled:
        reasons['unassembled_or_non_area'] += 1
    normalized = []
    for identifier, geom, clipped in records:
        if identifier not in selected:
            reasons['area_without_selected_original'] += 1
            continue
        normalized.append({**selected[identifier], 'metric_geometry': geom, 'boundary_clipped': clipped})
    return normalized, {'selected_source_objects': len(selected),
                        'selected_by_osm_type': dict(Counter(r['osm_type'] for r in selected.values())),
                        'rejected_or_excluded': dict(reasons),
                        'assembled_inside_warsaw_before_deduplication': len(normalized)}


def identity(value):
    return ' '.join(re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', value or '').casefold()).split())


def same_facility(a, b):
    if a['kind'] != b['kind']:
        return False
    # Conflicting known addresses are evidence of distinct facilities.
    for key in ('street', 'housenumber', 'unit'):
        x, y = a['address'].get(key), b['address'].get(key)
        if x and y and identity(x) != identity(y):
            return False
    names = identity(a['name']), identity(b['name'])
    brands = a['tags'].get('brand:wikidata') or identity(a['tags'].get('brand')), b['tags'].get('brand:wikidata') or identity(b['tags'].get('brand'))
    return bool((all(names) and names[0] == names[1]) or (all(brands) and brands[0] == brands[1]))


def deduplicate(records):
    """Merge only structurally linked or spatially contained matching identities."""
    records = sorted(records, key=lambda r: ({'relation': 0, 'way': 1, 'node': 2}[r['osm_type']], r['osm_identifier']))
    if not records:
        return [], []
    tree = STRtree([r['metric_geometry'] for r in records])
    removed, evidence = {}, []
    for i, keep in enumerate(records):
        if i in removed:
            continue
        for j in sorted(map(int, tree.query(keep['metric_geometry']))):
            if j <= i or j in removed:
                continue
            other = records[j]
            linked = keep['osm_type'] == 'relation' and other['osm_type'] == 'way' and other['osm_id'] in keep['member_ways']
            point_in_area = other['osm_type'] == 'node' and keep['osm_type'] in ('way', 'relation') and keep['metric_geometry'].covers(other['metric_geometry'])
            identical = keep['metric_geometry'].equals(other['metric_geometry'])
            if same_facility(keep, other) and (linked or point_in_area or identical):
                removed[j] = i
                evidence.append({'kept': keep['osm_identifier'], 'merged': other['osm_identifier'],
                                 'reason': 'matching_identity_and_member_way' if linked else 'matching_identity_and_containment_or_equal_geometry'})
    groups = {}
    for i, record in enumerate(records):
        groups.setdefault(removed.get(i, i), []).append(record)
    result = []
    for i, group in groups.items():
        keep = records[i]
        source_objects = [{k: v for k, v in r.items() if k not in ('metric_geometry', 'member_ways')} for r in group]
        marker = transform(keep['metric_geometry'].representative_point(), TO_WGS, interleaved=False)
        props = {k: v for k, v in keep.items() if k not in ('metric_geometry', 'member_ways')}
        props.update(source_id=keep['osm_identifier'], source_objects=source_objects,
                     latitude=marker.y, longitude=marker.x)
        result.append({'type': 'Feature', 'properties': props,
                       'geometry': mapping(transform(keep['metric_geometry'], TO_WGS, interleaved=False))})
    return sorted(result, key=lambda f: f['properties']['osm_identifier']), evidence


def process_extract(path, source, output):
    import osmium

    path, output = Path(path), Path(output)
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != source['sha256']:
        raise ValueError('Extract SHA256 does not match source manifest')
    boundaries = load_boundaries()
    if boundaries is None:
        raise ValueError('Verified official Warsaw boundary is required for ingestion')
    with osmium.io.Reader(str(path)) as reader:
        snapshot_at = reader.header().get('osmosis_replication_timestamp')
    if not snapshot_at:
        raise ValueError('Extract has no replication timestamp')
    records, report = extract_objects(path, boundaries['city'])
    features, duplicates = deduplicate(records)
    districts = Counter()
    for feature in features:
        p = feature['properties']; point = Point(p['longitude'], p['latitude'])
        matches = sorted(name for name, geom in boundaries['districts'].items() if geom.covers(point))
        p['district'] = matches[0] if matches else None
        if not matches:
            raise ValueError('Normalized marker outside municipal districts')
        districts[p['district']] += 1
    now = datetime.now(timezone.utc).isoformat()
    metadata = {**source, 'source_timestamp': snapshot_at, 'processed_at': now,
                'attribution': ATTRIBUTION, 'attribution_url': 'https://www.openstreetmap.org/copyright',
                'license': 'ODbL-1.0', 'license_url': LICENSE_URL,
                'coverage_status': 'osm_snapshot', 'citywide_inventory_complete': False,
                'boundary_sha256': boundaries['metadata']['sha256'], 'metric_crs': 'EPSG:2180',
                'limitations': ['Complete selected tags from this regional extract, not a complete real-world business inventory.',
                               'Names, addresses, opening hours and object timestamps may be absent or outdated.',
                               'Conservative deduplication can retain unresolved duplicates; proximity alone never merges facilities.']}
    report.update(processed_at=now, source_timestamp=snapshot_at, source=source,
                  full_extract_processed=True, output_facilities=len(features), merged_duplicate_objects=len(duplicates),
                  deduplication=duplicates, by_kind=dict(Counter(f['properties']['kind'] for f in features)),
                  by_osm_type=dict(Counter(f['properties']['osm_type'] for f in features)), by_district=dict(sorted(districts.items())),
                  by_district_and_kind={district: dict(Counter(f['properties']['kind'] for f in features if f['properties']['district'] == district)) for district in sorted(districts)},
                  without_name=sum(not f['properties']['name'] for f in features),
                  with_opening_hours=sum(bool(f['properties']['opening_hours']) for f in features),
                  with_any_address=sum(bool(f['properties']['address']) for f in features),
                  missing_object_timestamp=sum(not f['properties']['osm_timestamp'] for f in features),
                  boundary_clipped=sum(f['properties']['boundary_clipped'] for f in features))
    raw = (json.dumps({'type': 'FeatureCollection', 'metadata': metadata, 'features': features}, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    packed = gzip.compress(raw, mtime=0)
    name = 'retail-' + hashlib.sha256(packed).hexdigest()[:16] + '.geojson.gz'
    atomic_bytes(output / name, packed)
    atomic_json(output / 'retail-report.json', report)
    atomic_json(output / 'retail-manifest.json', {'file': name, 'sha256': hashlib.sha256(packed).hexdigest(),
                                                'record_count': len(features), 'metadata': metadata})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'data/osm')
    args = parser.parse_args()
    try:
        report = process_extract(args.extract, json.loads(args.source_manifest.read_text()), args.output)
        print(json.dumps({k: v for k, v in report.items() if k != 'deduplication'}, ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        parser.exit(1, f'OSM ingestion failed; previous manifest preserved: {exc}\n')


if __name__ == '__main__':
    main()
