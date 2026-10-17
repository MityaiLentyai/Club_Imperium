"""Offline municipal membership, independent of address/infrastructure coverage."""
from functools import lru_cache
import json
from pathlib import Path

from pyproj import Transformer
from shapely import transform
from shapely.errors import ShapelyError
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

PATH = Path(__file__).resolve().parents[1] / 'data/geography/warsaw-districts.geojson'
DISTRICTS = frozenset(['Bemowo','Białołęka','Bielany','Mokotów','Ochota','Praga-Południe',
                      'Praga-Północ','Rembertów','Śródmieście','Targówek','Ursus','Ursynów',
                      'Wawer','Wesoła','Wilanów','Włochy','Wola','Żoliborz'])
TO_METRES = Transformer.from_crs(4326,2180,always_xy=True).transform
BOUNDARY_TOLERANCE_M = 0.5


@lru_cache(maxsize=1)
def _load(path, modified, size):
    try:
        data = json.loads(Path(path).read_text())
        if data['metadata'].get('source_url') != 'https://wfs.um.warszawa.pl/serwis':
            return None
        features = data['features']
        if data['type'] != 'FeatureCollection' or len(features) != 18:
            return None
        districts = {f['properties']['name']:shape(f['geometry']) for f in features}
        if districts.keys() != DISTRICTS or any(g.is_empty or not g.is_valid or g.geom_type not in ('Polygon','MultiPolygon') for g in districts.values()):
            return None
        city = unary_union(list(districts.values()))
        projected = transform(city,TO_METRES,interleaved=False)
        if not projected.is_valid or not 400e6 < projected.area < 650e6:
            return None
        return {'city':city,'projected':projected,'prepared':prep(projected),'districts':districts,
                'metadata':data['metadata']}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ShapelyError):
        return None


def load_boundaries():
    try:
        info = PATH.stat()
        return _load(PATH,info.st_mtime_ns,info.st_size)
    except OSError:
        return None


def membership(latitude,longitude):
    dataset = load_boundaries()
    if dataset is None:
        return (52.0 <= latitude <= 52.4 and 20.75 <= longitude <= 21.3), {
            'method':'legacy_service_envelope','boundary_status':'unavailable','boundary_inclusive':True}
    # Reject implausible global coordinates before projection, including direct helper callers.
    if not (51.0 <= latitude <= 53.0 and 20.0 <= longitude <= 22.0):
        return False, {'method':'official_district_union','boundary_status':'available'}
    point = transform(Point(longitude,latitude),TO_METRES,interleaved=False)
    city = dataset['projected']
    inside = dataset['prepared'].covers(point) or city.distance(point) <= BOUNDARY_TOLERANCE_M
    on_boundary = city.boundary.distance(point) <= BOUNDARY_TOLERANCE_M
    return inside, {'method':'official_district_union','boundary_status':'available','boundary_inclusive':True,
                    'tolerance_m':BOUNDARY_TOLERANCE_M,'on_boundary':on_boundary,
                    'source_url':dataset['metadata']['source_url']}
