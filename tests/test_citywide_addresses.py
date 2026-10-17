import gzip
import json
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import box

from data_science import address_lookup as local
from data_science.ingest_addresses import process_source,publish_index

GML='{http://www.opengis.net/gml}'


def test_polish_normalization_is_conservative():
    assert local.street_key('UL.Marszałkowska')=='ulica marszałkowska'
    assert local.fold_key(local.street_key('Żółkiewskiego'))=='zolkiewskiego'
    assert local.street_key('pl. Wolności')!=local.street_key('ul. Wolności')
    assert local.building_key('12 a / 14')=='12A/14'
    assert local.building_key('01')!='1'
    assert local.parse_query('00-001 Warszawa, ul. Marszałkowska 83, Śródmieście')['building']=='83'
    assert local.parse_query('Marszałkowska 83 lok. 4')['building']=='83'
    assert local.parse_query('Marszałkowska 83/4')['building']=='83/4'
    assert local.parse_query('Marszałkowska') is None


def catalogue(tmp_path,monkeypatch):
    rows=[{'id':'001','street':'ulica Łąkowa','short_name':'ul. Łąkowa','building':'12A','district':'Wawer','latitude':52.2,'longitude':21.1},
          {'id':'002','street':'ulica Łąkowa','short_name':'ul. Łąkowa','building':'12A','district':'Wesoła','latitude':52.22,'longitude':21.2},
          {'id':'003','street':'ulica Stanisława Szobera','short_name':'ul. S. Szobera','building':'1/3','district':'Bemowo','latitude':52.24,'longitude':20.9}]
    publish_index(rows,{'complete_partition':True},tmp_path)
    monkeypatch.setattr(local,'MANIFEST',tmp_path/'address-index.json')
    local._load.cache_clear()
    return rows


def test_local_index_ambiguity_aliases_and_buildings(tmp_path,monkeypatch):
    catalogue(tmp_path,monkeypatch)
    assert local.lookup('Lakowa 12 a')['status']=='ambiguous'
    result=local.lookup('UL. LAKOWA 12a, Wawer')
    assert result['status']=='found' and result['address_id']=='001'
    assert local.lookup('S. Szobera 1 / 3')['address_id']=='003'
    assert local.lookup('S. Szobera 1')['status']=='not_found'
    assert local.lookup('Łąkowa')['status']=='invalid_address'
    assert local.lookup('Nieistniejąca 99')['status']=='not_found'


def test_missing_or_corrupt_index_is_optional(tmp_path,monkeypatch):
    monkeypatch.setattr(local,'MANIFEST',tmp_path/'missing.json')
    assert local.lookup('Marszałkowska 83')['status']=='unavailable'
    catalogue(tmp_path,monkeypatch)
    meta=json.loads((tmp_path/'address-index.json').read_text())
    (tmp_path/meta['database_file']).write_bytes(b'corrupt')
    local._load.cache_clear()
    assert local.lookup('Łąkowa 12A')['status']=='unavailable'


def gml(rows):
    root=ET.Element('FeatureCollection')
    for row in rows:
        record=ET.SubElement(ET.SubElement(root,GML+'featureMember'),'ADDRESS')
        for key,value in [('ID',row['id']),('NAZWA_PODST','ulica Testowa'),('NAZWA_SKROC','ul. Testowa'),('NR_PORZADK',row['id']),('DZIELNICA','Wola')]:ET.SubElement(record,key).text=value
        geom=ET.SubElement(ET.SubElement(record,'GEOMETRY'),GML+'Point')
        ET.SubElement(geom,GML+'coordinates').text=f"{row['lon']},{row['lat']}"
    return ET.tostring(root)


def test_complete_unfiltered_source_is_deduplicated_and_city_checked():
    city=box(21.0,52.2,21.04,52.24)
    rows=[{'id':str(i),'lon':21.0001+i*0.0005,'lat':52.2001} for i in range(30)]
    rows+=rows[:1]+[{'id':'outside','lon':21.5,'lat':52.2}]
    records,report=process_source(gml(rows),city,max_records=100)
    assert len(records)==30
    assert report['source_records']==32 and report['duplicate_id_records']==1
    assert report['outside_boundary_records']==1 and report['below_requested_record_cap']
    with pytest.raises(ValueError):process_source(gml(rows),city,max_records=32)


def test_capped_or_exception_response_cannot_claim_source_completeness():
    city=box(21.0,52.2,21.04,52.24)
    with pytest.raises(ValueError):process_source(b'<ExceptionReport/>',city)
    with pytest.raises(ValueError):process_source(b'<FeatureCollection/>',city)


def test_unicode_and_multiletter_buildings():
    for number in ['58Ł','95CA','17ES15','5/7/9','12A-14B','123S.4']:
        assert local.parse_query('ul. Testowa '+number)['building']==number
    assert local.parse_query('Dywizji 303 1')['street']=='Dywizji 303'
    assert local.parse_query('Puławska123')['building']=='123'


SAMPLES=json.loads(Path('data/geography/verification-samples.json').read_text())['samples']


@pytest.mark.parametrize('sample',SAMPLES,ids=[s['district'] for s in SAMPLES])
def test_every_district_local_address_and_arbitrary_point_score(sample,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services import geocoding_service as geo,scoring_service as scoring
    from data_science.stop_lines import LineCache
    monkeypatch.delenv('GEOCODING_USER_AGENT',raising=False)
    for name in ['get_parks','get_parking','get_sports']:monkeypatch.setattr(scoring,name,lambda:None)
    monkeypatch.setattr(scoring,'get_stop_lines',lambda:LineCache())
    client=TestClient(app)
    resolved=client.get('/api/geocode',params={'address':sample['query']})
    assert resolved.status_code==200
    assert resolved.json()['latitude']==sample['latitude']
    assert resolved.json()['longitude']==sample['longitude']
    response=client.post('/api/score/address',json={'address':sample['query'],'radius_m':1})
    assert response.status_code==200
    result=response.json()
    assert result['area_validation']['method']=='official_district_union'
    assert result['life_score']['status']=='partial'
    for key in ['parks_within_radius','listed_parking_within_radius','sports_facilities_within_radius']:
        assert result['features'][key] is None
    direct=client.post('/api/score',json={'latitude':sample['latitude'],'longitude':sample['longitude'],'radius_m':1})
    assert direct.status_code==200
    assert direct.json()['scores']==result['scores']
    assert direct.json()['line_features']['nearest_stop_lines'] is None


def test_arbitrary_non_dataset_grid_points_are_not_rejected_for_missing_neighbors():
    from fastapi.testclient import TestClient
    from backend.main import app
    from data_science.geography import load_boundaries
    from shapely.geometry import Point
    city=load_boundaries()['city'];a,b,c,d=city.bounds
    client=TestClient(app);tested=0
    for i in range(1,9):
        for j in range(1,9):
            lon=a+(c-a)*i/9;lat=b+(d-b)*j/9
            if not city.covers(Point(lon,lat)):continue
            result=client.post('/api/score',json={'latitude':lat,'longitude':lon,'radius_m':1})
            assert result.status_code==200
            assert 0<=result.json()['scores']['mobility']<=100
            tested+=1
    assert tested>=20


def test_boundary_inclusive_precision_band_and_outside_city():
    from fastapi.testclient import TestClient
    from backend.main import app
    from data_science.geography import load_boundaries,membership
    from pyproj import Transformer
    from shapely import get_coordinates
    city=load_boundaries()['projected'];point=max(get_coordinates(city),key=lambda p:p[0])
    to_wgs=Transformer.from_crs(2180,4326,always_xy=True)
    client=TestClient(app)
    for shift,expected in [(0,200),(0.2,200),(2,422)]:
        lon,lat=to_wgs.transform(point[0]+shift,point[1])
        response=client.post('/api/score',json={'latitude':lat,'longitude':lon})
        assert response.status_code==expected
        if expected==200:assert response.json()['area_validation']['on_boundary']
    # These old service-envelope corners and a southern point are outside the actual union.
    for lat,lon in [(52.,20.75),(52.4,21.3),(52.09,21.1)]:
        assert client.post('/api/score',json={'latitude':lat,'longitude':lon}).status_code==422


def test_missing_boundary_falls_back_explicitly_without_breaking_map_points(tmp_path,monkeypatch):
    from data_science import geography
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setattr(geography,'PATH',tmp_path/'missing.geojson')
    result=TestClient(app).post('/api/score',json={'latitude':52.2297,'longitude':21.0122})
    assert result.status_code==200
    assert result.json()['area_validation']['method']=='legacy_service_envelope'
    assert result.json()['area_validation']['boundary_status']=='unavailable'


def test_missing_number_and_ambiguous_address_never_trigger_fallback(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services import geocoding_service as geo
    client=TestClient(app)
    for address in ['Warszawa','ul. Marszałkowska','nonsense','Dywizjonu 303']:
        assert client.get('/api/geocode',params={'address':address}).status_code==422
    monkeypatch.setattr(geo,'lookup_address',lambda _: {'status':'ambiguous','candidate_count':2})
    result=client.get('/api/geocode',params={'address':'Testowa 1'})
    assert result.status_code==422 and 'ambiguous' in result.json()['detail']


def test_coordinate_score_survives_address_geocoder_failure(monkeypatch):
    from unittest.mock import AsyncMock
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    import backend.main as main
    client=TestClient(main.app)
    monkeypatch.setattr(main,'geocode_address',AsyncMock(side_effect=HTTPException(502,'Provider unavailable')))
    assert client.post('/api/score/address',json={'address':'Marszałkowska 83'}).status_code==502
    assert client.post('/api/score',json={'latitude':52.225763,'longitude':21.013683}).status_code==200


def test_zero_verified_objects_keeps_incomplete_coverage_separate():
    from data_science.sports import load_sports,calculate_sports_features
    from data_science.parking import load_parking,calculate_parking_features
    for dataset,calculate,count_key in [(load_sports(),calculate_sports_features,'sports_facilities_within_radius'),
                                        (load_parking(),calculate_parking_features,'listed_parking_within_radius')]:
        features,places,meta=calculate(52.1,21.1,1,dataset)
        assert features[count_key]==0 and places==[]
        assert meta['coverage_status']=='partial'
        assert meta['citywide_inventory_complete'] is False
        assert meta['count_basis']=='verified_snapshot_objects'


@pytest.mark.parametrize('sample',SAMPLES,ids=[s['district'] for s in SAMPLES])
def test_ascii_case_and_official_alias_lookup_in_every_district(sample):
    parsed=local.parse_query(sample['query'])
    query=f"{local.fold_key(parsed['street']).upper()} {parsed['building']}, {local.fold_key(parsed['district'])}"
    result=local.lookup(query)
    assert result['status']=='found'
    assert result['address_id']==sample['address_id']


def test_literal_subbuilding_and_slash_are_preserved():
    result=local.lookup('ul. Czwartaków 123s.4, Rembertów')
    assert result['status']=='found' and result['address_id']=='1315166'
    assert local.lookup('ul. Czwartaków 123s4, Rembertów')['status']=='not_found'


def test_source_snapshot_and_index_counts_reconcile():
    root=Path('data/geography')
    report=json.loads((root/'address-processing-report.json').read_text())
    assert report['source_records']==report['processed_records']==report['valid_city_addresses']==126923
    assert report['duplicate_id_records']==report['rejected_records']==report['outside_boundary_records']==0
    assert len(report['by_source_district'])==18
    assert sum(report['by_source_district'].values())==126923
    data=local.load_index()
    assert data['metadata']['record_count']==126923


def test_local_resolution_overrides_cached_external_miss(monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services import geocoding_service as geo
    monkeypatch.delenv('GEOCODING_USER_AGENT',raising=False)
    monkeypatch.setitem(geo._cache,'marszałkowska 83',(time.monotonic(),None))
    response=TestClient(app).get('/api/geocode',params={'address':'Marszałkowska 83'})
    assert response.status_code==200 and response.json()['latitude']==52.225763
