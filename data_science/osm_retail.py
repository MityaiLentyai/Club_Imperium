"""Optional immutable OSM snapshot; no PyOsmium or outbound requests at runtime."""
from functools import lru_cache
import gzip
import hashlib
import json
import math
import zlib
from pathlib import Path

from shapely import distance, from_wkb, transform
from shapely.geometry import Point, shape
from shapely.errors import ShapelyError

from data_science.geography import TO_METRES

MANIFEST = Path(__file__).resolve().parents[1] / 'data/osm/retail-manifest.json'
FEATURES = ('nearest_supermarket_m', 'supermarkets_within_radius',
            'nearest_grocery_convenience_m', 'grocery_convenience_within_radius',
            'nearest_grocery_m', 'grocery_stores_within_radius',
            'nearest_pharmacy_m', 'pharmacies_within_radius')


@lru_cache(maxsize=1)
def _load(path, modified, size):
    try:
        manifest = json.loads(Path(path).read_text())
        name = manifest['file']
        if Path(name).name != name or not name.endswith('.geojson.gz'):
            return None
        packed = (Path(path).parent / name).read_bytes()
        if len(packed) > 25_000_000 or hashlib.sha256(packed).hexdigest() != manifest['sha256']:
            return None
        with gzip.open(Path(path).parent / name, 'rb') as f:
            raw = f.read(100_000_001)
        if len(raw) > 100_000_000:
            return None
        data = json.loads(raw)
        if (data['type'] != 'FeatureCollection' or data['metadata'] != manifest['metadata']
                or len(data['features']) != manifest['record_count']
                or not data['metadata']['source_timestamp'] or not data['metadata']['retrieved_at']
                or data['metadata']['license'] != 'ODbL-1.0'):
            return None
        records, geometries, seen = [], [], set()
        for feature in data['features']:
            props = feature['properties']; geom = shape(feature['geometry'])
            required = {'osm_identifier', 'osm_type', 'osm_id', 'kind', 'category', 'name', 'tags',
                        'source_objects', 'address', 'opening_hours', 'osm_timestamp', 'latitude', 'longitude'}
            if not required <= props.keys():
                return None
            key = props['osm_identifier']
            if (key in seen or props['osm_type'] not in ('node', 'way', 'relation')
                    or not isinstance(props['osm_id'], str) or not props['osm_id'].isdigit()
                    or key != f"{props['osm_type']}/{props['osm_id']}"
                    or not isinstance(props['address'], dict)
                    or (props['name'] is not None and not isinstance(props['name'], str))
                    or props['kind'] not in ('supermarket', 'convenience', 'grocery', 'pharmacy')
                    or props['category'] != ('pharmacy' if props['kind'] == 'pharmacy' else 'grocery')
                    or geom.is_empty or not geom.is_valid or geom.geom_type not in ('Point', 'Polygon', 'MultiPolygon')
                    or not isinstance(props['tags'], dict) or not isinstance(props['source_objects'], list)):
                return None
            lat, lon = props['latitude'], props['longitude']
            if not (math.isfinite(lat) and math.isfinite(lon) and 52.0 <= lat <= 52.4 and 20.75 <= lon <= 21.3):
                return None
            if geom.distance(Point(lon, lat)) > 1e-7:
                return None
            projected = transform(geom, TO_METRES, interleaved=False)
            if not all(math.isfinite(v) for v in projected.bounds):
                return None
            records.append(props); geometries.append(projected.wkb); seen.add(key)
        return {'metadata': {**data['metadata'], 'source_sha256': data['metadata'].get('sha256'),
                             'sha256': manifest['sha256']},
                'records': records, 'geometries': from_wkb(geometries)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ShapelyError, EOFError, zlib.error):
        return None


def load_retail():
    try:
        info = MANIFEST.stat()
        return _load(str(MANIFEST), info.st_mtime_ns, info.st_size)
    except OSError:
        return None


def calculate_retail_features(latitude, longitude, radius_m, dataset, limit=50):
    if dataset is None:
        return dict.fromkeys(FEATURES), [], {c: {'status': 'unavailable'} for c in ('grocery', 'pharmacy')}
    point = transform(Point(longitude, latitude), TO_METRES, interleaved=False)
    distances = distance(dataset['geometries'], point)
    ordered = sorted(enumerate(distances), key=lambda row: (row[1], dataset['records'][row[0]]['osm_identifier']))
    features = {}
    for kinds, nearest, count in (
        ({'supermarket'}, FEATURES[0], FEATURES[1]),
        ({'convenience', 'grocery'}, FEATURES[2], FEATURES[3]),
        ({'supermarket', 'convenience', 'grocery'}, FEATURES[4], FEATURES[5]),
        ({'pharmacy'}, FEATURES[6], FEATURES[7]),
    ):
        selected = [(i, d) for i, d in ordered if dataset['records'][i]['kind'] in kinds]
        features[nearest] = round(float(selected[0][1]), 1) if selected else None
        features[count] = int(sum(d <= radius_m for _, d in selected))
    places, metadata = [], {}
    for category in ('grocery', 'pharmacy'):
        selected = [(i, d) for i, d in ordered if d <= radius_m and dataset['records'][i]['category'] == category]
        for i, d in selected[:limit]:
            props = dataset['records'][i]
            places.append({'id': f"osm:{props['osm_identifier']}", 'category': category,
                           'label': props['name'] or props['tags'].get('brand') or props['kind'].capitalize(),
                           'name': props['name'], 'latitude': props['latitude'], 'longitude': props['longitude'],
                           'distance_m': round(float(d), 1), 'distance_type': 'straight_line',
                           'distance_basis': 'osm_facility_geometry',
                           **{k: props[k] for k in ('osm_identifier', 'osm_type', 'osm_id', 'kind', 'tags',
                                                   'address', 'opening_hours', 'osm_timestamp', 'source_objects')}})
        metadata[category] = {**dataset['metadata'], 'status': 'available',
                              'total': len(selected), 'snapshot_facilities': sum(p['category'] == category for p in dataset['records']),
                              'limit': limit, 'truncated': len(selected) > limit,
                              'count_basis': 'mapped_osm_snapshot_facilities'}
    return features, places, metadata
