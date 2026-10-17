import gzip
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from pyproj import Transformer
from shapely.geometry import Point, Polygon, box
from shapely import transform

from backend.main import app
from backend.services import scoring_service as scoring
from data_science import osm_retail as retail
from data_science.geography import DISTRICTS, load_boundaries, TO_METRES
from data_science.ingest_osm_retail import extract_objects, deduplicate, kind_for


@pytest.fixture
def osm_file(tmp_path):
    root = ET.Element('osm', version='0.6', generator='UrbanLens-test')
    def tags(obj, values):
        for key, value in values.items():
            ET.SubElement(obj, 'tag', k=key, v=value)
    def node(identifier, lon, lat, values=None):
        obj = ET.SubElement(root, 'node', id=str(identifier), lon=str(lon), lat=str(lat), timestamp='2026-10-01T00:00:00Z')
        tags(obj, values or {})
    def way(identifier, refs, values=None):
        obj = ET.SubElement(root, 'way', id=str(identifier), timestamp='2026-10-01T00:00:00Z')
        for ref in refs:ET.SubElement(obj, 'nd', ref=str(ref))
        tags(obj, values or {})
    # Supermarket area plus corresponding named node: one facility.
    for i, (lon, lat) in enumerate([(21.01,52.23),(21.011,52.23),(21.011,52.231),(21.01,52.231)],1):node(i,lon,lat)
    node(5,21.0105,52.2305,{'shop':'supermarket','name':'Test Market','addr:housenumber':'1'})
    node(6,21.0106,52.2306,{'shop':'convenience','name':'Distinct kiosk'})
    node(7,20.0,52.0,{'amenity':'pharmacy','name':'Outside'})
    # Multipolygon with a hole and an additional disconnected outer ring.
    for i,(lon,lat) in enumerate([(21.02,52.23),(21.022,52.23),(21.022,52.232),(21.02,52.232),
                                 (21.0205,52.2305),(21.021,52.2305),(21.021,52.231),(21.0205,52.231),
                                 (21.024,52.23),(21.025,52.23),(21.025,52.231),(21.024,52.231)],10):node(i,lon,lat)
    way(100,[1,2,3,4,1],{'shop':'supermarket','name':'Test Market','opening_hours':'24/7'})
    way(101,[10,11,12]);way(102,[12,13,10]);way(103,[14,15,16,17,14]);way(104,[18,19,20,21,18])
    # A tagged open way must be reported, never invented as a facility point.
    way(105,[1,2],{'shop':'grocery','name':'Broken'})
    rel=ET.SubElement(root,'relation',id='200',timestamp='2026-10-01T00:00:00Z')
    for ref,role in [(101,'outer'),(102,'outer'),(103,'inner'),(104,'outer')]:ET.SubElement(rel,'member',type='way',ref=str(ref),role=role)
    tags(rel,{'type':'multipolygon','amenity':'pharmacy','name':'Test Pharmacy','opening_hours':'Mo-Fr 08:00-20:00','addr:street':'Testowa'})
    path=tmp_path/'retail.osm';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    return path


def test_nodes_ways_multipolygons_holes_and_duplicate_facilities(osm_file):
    pytest.importorskip('osmium')
    rows,report=extract_objects(osm_file,load_boundaries()['city'])
    assert report['selected_source_objects']==6
    assert report['rejected_or_excluded']=={'outside_warsaw':1,'unassembled_or_non_area':1}
    relation=next(r for r in rows if r['osm_type']=='relation')
    assert relation['osm_id']=='200' and relation['metric_geometry'].geom_type=='MultiPolygon'
    assert len(relation['metric_geometry'].geoms)==2
    assert sum(len(g.interiors) for g in relation['metric_geometry'].geoms)==1
    features,merged=deduplicate(rows)
    assert len(features)==3 and len(merged)==1
    market=next(f['properties'] for f in features if f['properties']['kind']=='supermarket')
    assert {r['osm_identifier'] for r in market['source_objects']}=={'way/100','node/5'}
    assert market['opening_hours']=='24/7'
    pharmacy=next(f for f in features if f['properties']['kind']=='pharmacy')
    assert pharmacy['properties']['address']=={'street':'Testowa'}
    assert pharmacy['properties']['osm_timestamp']=='2026-10-01T00:00:00+00:00'
    from shapely.geometry import shape
    marker=Point(pharmacy['properties']['longitude'],pharmacy['properties']['latitude'])
    assert shape(pharmacy['geometry']).covers(marker)


def record(identifier, geom, kind='convenience', name='Market', address=None, member_ways=None):
    typ,osm_id=identifier.split('/')
    marker=transform(geom.representative_point(),Transformer.from_crs(2180,4326,always_xy=True).transform,interleaved=False)
    return {'latitude':marker.y,'longitude':marker.x,'osm_identifier':identifier,'osm_type':typ,'osm_id':osm_id,'metric_geometry':geom,
            'kind':kind,'category':'pharmacy' if kind=='pharmacy' else 'grocery','name':name,
            'tags':{'name':name} if name else {},'address':address or {},'opening_hours':None,
            'osm_timestamp':None,'boundary_clipped':False,'member_ways':member_ways or []}


def test_conservative_deduplication_does_not_merge_neighboring_chain_branches():
    area=box(500000,400000,500020,400020)
    rows=[record('way/1',area),record('node/1',Point(500010,400010)),
          record('node/2',Point(500025,400010)),record('node/3',Point(500010,400010),name='Other'),
          record('node/4',Point(500012,400010),name=None),
          record('node/5',Point(500013,400010),address={'unit':'2'})]
    rows[0]['address']={'unit':'1'}
    features,merged=deduplicate(rows)
    assert len(features)==5 and merged[0]['merged']=='node/1'


def test_relation_member_way_is_not_counted_twice():
    area=box(500000,400000,500020,400020)
    features,evidence=deduplicate([record('relation/1',area,member_ways=['5']),record('way/5',area)])
    assert len(features)==1 and evidence[0]['reason']=='matching_identity_and_member_way'


def test_projection_is_metric_and_radius_is_not_measured_in_degrees():
    origin=transform(Point(21.0122,52.2297),TO_METRES,interleaved=False)
    shifted=Point(origin.x+100,origin.y)
    p=record('node/1',shifted,kind='pharmacy')
    p['source_objects']=[]
    snapshot={'records':[p],'geometries':[shifted], 'metadata':{}}
    f,places,metadata=retail.calculate_retail_features(52.2297,21.0122,99,snapshot)
    assert f['nearest_pharmacy_m']==100 and f['pharmacies_within_radius']==0 and places==[]
    assert metadata['pharmacy']['status']=='available'
    f,places,_=retail.calculate_retail_features(52.2297,21.0122,101,snapshot)
    # Coordinates normally populated by normalization; the previous test checks them.
    assert f['pharmacies_within_radius']==1


def test_missing_dataset_never_breaks_transport_or_lifescore(monkeypatch):
    monkeypatch.setattr(scoring,'load_retail',lambda:None)
    response=TestClient(app).post('/api/score',json={'latitude':52.2297,'longitude':21.0122})
    assert response.status_code==200
    data=response.json()
    assert data['scores']=={'mobility':92.7} and data['life_score']['value']==92.7
    assert all(data['features'][key] is None for key in retail.FEATURES)
    assert {'grocery','pharmacy'}<=set(data['unavailable'])


def test_valid_empty_snapshot_means_verified_zero_not_unavailable():
    f,places,metadata=retail.calculate_retail_features(52.2297,21.0122,1,{'records':[],'geometries':[],'metadata':{'citywide_inventory_complete':False}})
    assert f['grocery_stores_within_radius']==0 and f['pharmacies_within_radius']==0
    assert f['nearest_pharmacy_m'] is None and places==[]
    assert metadata['grocery']['status']=='available' and not metadata['grocery']['citywide_inventory_complete']


def test_snapshot_integrity_and_cache(tmp_path,monkeypatch):
    meta={'source_timestamp':'2026-10-16T20:21:21Z','retrieved_at':'2026-10-17T22:48:04Z','license':'ODbL-1.0'}
    raw=json.dumps({'type':'FeatureCollection','metadata':meta,'features':[]}).encode()
    packed=gzip.compress(raw)
    p=tmp_path/'snapshot.geojson.gz';p.write_bytes(packed)
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'file':p.name,'sha256':hashlib.sha256(packed).hexdigest(),'record_count':0,'metadata':meta}))
    monkeypatch.setattr(retail,'MANIFEST',manifest);retail._load.cache_clear()
    first=retail.load_retail();assert first is not None and retail.load_retail() is first
    p.write_bytes(b'corrupt');retail._load.cache_clear();assert retail.load_retail() is None
    manifest.unlink();assert retail.load_retail() is None


SAMPLES=json.loads(Path('data/geography/verification-samples.json').read_text())['samples']


@pytest.mark.parametrize('sample',SAMPLES,ids=[s['district'] for s in SAMPLES])
def test_real_snapshot_and_api_cover_every_warsaw_district(sample):
    snapshot=retail.load_retail()
    assert snapshot is not None and len(snapshot['records'])==2831
    assert any(p['district']==sample['district'] for p in snapshot['records'])
    client=TestClient(app)
    body={'latitude':sample['latitude'],'longitude':sample['longitude'],'radius_m':1000}
    result=client.post('/api/score',json=body)
    assert result.status_code==200
    data=result.json()
    assert data['scores']['mobility']==data['life_score']['value']
    for category in ('grocery','pharmacy'):
        assert category not in data['unavailable']
        assert data['datasets'][category]['coverage_status']=='osm_snapshot'
        assert data['datasets'][category]['citywide_inventory_complete'] is False
    for place in (p for p in data['places'] if p['category'] in ('grocery','pharmacy')):
        assert place['osm_identifier'] in {r['osm_identifier'] for r in snapshot['records']}
        assert place['distance_m']<=1000 and place['distance_basis']=='osm_facility_geometry'
    address=client.post('/api/score/address',json={'address':sample['query'],'radius_m':1000}).json()
    assert address['features']==data['features']


def test_actual_snapshot_types_and_exact_counts():
    from collections import Counter
    snapshot=retail.load_retail()
    assert Counter(p['kind'] for p in snapshot['records'])=={'supermarket':500,'convenience':1716,'grocery':32,'pharmacy':583}
    assert {p['district'] for p in snapshot['records']}==DISTRICTS
    assert len({p['osm_identifier'] for p in snapshot['records']})==2831
    assert kind_for({'amenity':'pharmacy','shop':'convenience'})=='pharmacy'


def test_boundary_clipping_uses_polygon_intersection(osm_file):
    pytest.importorskip('osmium')
    city=box(21.009,52.229,21.01075,52.232)
    rows,report=extract_objects(osm_file,city)
    polygon=next(r for r in rows if r['osm_type']=='way')
    assert polygon['boundary_clipped']
    expected=transform(city,TO_METRES,interleaved=False)
    # GEOS intersection can differ by sub-micrometre rounding at a shared edge.
    assert expected.buffer(1e-6).covers(polygon['metric_geometry'])


def test_polygon_distance_is_zero_inside_facility_not_distance_to_marker():
    origin=transform(Point(21.0122,52.2297),TO_METRES,interleaved=False)
    geom=box(origin.x-10,origin.y-10,origin.x+50,origin.y+20)
    props=record('way/1',geom,kind='supermarket');props['source_objects']=[]
    f,places,_=retail.calculate_retail_features(52.2297,21.0122,1,{'records':[props],'geometries':[geom],'metadata':{}})
    assert f['nearest_supermarket_m']==0 and f['supermarkets_within_radius']==1
    assert places[0]['distance_m']==0


def test_place_truncation_keeps_exact_category_counts():
    origin=transform(Point(21.0122,52.2297),TO_METRES,interleaved=False)
    rows=[record(f'node/{i+1}',Point(origin.x+i,origin.y)) for i in range(5)]
    for r in rows:r['source_objects']=[]
    f,places,meta=retail.calculate_retail_features(52.2297,21.0122,100,{'records':rows,'geometries':[r['metric_geometry'] for r in rows],'metadata':{}},limit=2)
    assert f['grocery_stores_within_radius']==5 and len(places)==2
    assert meta['grocery']['total']==5 and meta['grocery']['truncated']


def test_download_is_bounded_verified_and_reuses_original_freshness(tmp_path,monkeypatch):
    import httpx
    from data_science import download_osm_extract as downloader
    url='https://download.geofabrik.de/europe/poland/mazowieckie-261016.osm.pbf'
    raw=b'test-pbf';calls=[]
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200,content=(hashlib.md5(raw).hexdigest()+'  extract').encode() if str(request.url).endswith('.md5') else raw)
    original=httpx.Client
    monkeypatch.setattr(downloader.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    target,manifest=downloader.download(url,tmp_path)
    assert target.read_bytes()==raw and len(calls)==2
    saved=manifest.read_bytes()
    downloader.download(url,tmp_path)
    assert len(calls)==3 and manifest.read_bytes()==saved
    target.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='preserved'):downloader.download(url,tmp_path)
    assert target.read_bytes()==b'corrupt'
    with pytest.raises(ValueError):downloader.download('https://example.com/data.pbf',tmp_path)


def test_compare_keeps_existing_metrics_and_partial_lifescore():
    client=TestClient(app)
    locations=[{'latitude':52.2297,'longitude':21.0122},{'latitude':52.327116,'longitude':21.006675}]
    response=client.post('/api/compare',json={'locations':locations,'weights':{'mobility':10,'sports':90}})
    assert response.status_code==200
    data=response.json()
    assert all(r['life_score']['normalized_weights']=={'mobility':100} for r in data['locations'])
    assert all('nearest_pharmacy_m' in r['features'] for r in data['locations'])
    assert not any('grocery' in row['metric'] or 'pharmacy' in row['metric'] for row in data['comparisons'])


def test_empty_one_metre_radius_keeps_nonzero_citywide_nearest():
    snapshot=retail.load_retail()
    f,places,meta=retail.calculate_retail_features(52.2297,21.0122,1,snapshot)
    assert all(f[k]==0 for k in retail.FEATURES if k.endswith('within_radius'))
    assert f['nearest_pharmacy_m']>1 and places==[]
    assert all(m['status']=='available' for m in meta.values())


def test_failed_ingestion_preserves_last_published_manifest(tmp_path):
    pytest.importorskip('osmium')
    from data_science.ingest_osm_retail import process_extract
    target=tmp_path/'retail-manifest.json';target.write_text('previous generation')
    extract=tmp_path/'source.pbf';extract.write_bytes(b'bad')
    with pytest.raises(ValueError,match='SHA256'):process_extract(extract,{'sha256':'wrong'},tmp_path)
    assert target.read_text()=='previous generation'


@pytest.mark.parametrize('failure',['byte_limit','checksum'])
def test_download_failure_does_not_publish_partial_snapshot(tmp_path,monkeypatch,failure):
    import httpx
    from data_science import download_osm_extract as downloader
    raw=b'test-pbf'
    def respond(request):
        expected=hashlib.md5(raw).hexdigest() if failure=='byte_limit' else '0'*32
        return httpx.Response(200,content=expected.encode() if str(request.url).endswith('.md5') else raw)
    original=httpx.Client
    monkeypatch.setattr(downloader.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    if failure=='byte_limit':monkeypatch.setattr(downloader,'MAX_BYTES',4)
    with pytest.raises(ValueError):downloader.download('https://download.geofabrik.de/europe/poland/mazowieckie-261016.osm.pbf',tmp_path)
    assert not list(tmp_path.iterdir())


def test_retail_categories_do_not_create_numeric_score_weights():
    result=TestClient(app).post('/api/score',json={'latitude':52.2297,'longitude':21.0122,'weights':{'grocery':100}})
    assert result.status_code==422
