import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from data_science.complete_sports import process_all, parse_points, batch_parameters
from data_science.ingest_sports import address_parts
from data_science.ingest_infrastructure import save_snapshot
from data_science.infrastructure import load_snapshot

GML = 'http://www.opengis.net/gml'


def source(n):
    return [{'Adres obiektu':f'ul. Testowa {i}', 'Nazwa placówki oświatowej':f'Szkoła {i}',
             'Dzielnica':'Mokotów','Typ obiektu':'Boisko','Poniedziałek':'8–16'} for i in range(1,n+1)]


def response(params):
    root = ET.Element('{http://www.opengis.net/wfs}FeatureCollection')
    filt = ET.fromstring(params['filter'])
    ns = '{http://www.opengis.net/ogc}'
    conditions = list(filt[0]) if filt[0].tag.endswith('Or') else list(filt)
    for condition in conditions:
        values = {c.find(ns+'PropertyName').text:c.find(ns+'Literal').text for c in condition}
        number = int(values['NR_PORZADK'])
        record = ET.SubElement(ET.SubElement(root, f'{{{GML}}}featureMember'), 'ADDRESS')
        for key,value in {**values,'ID':str(number)}.items():ET.SubElement(record,key).text=value
        p=ET.SubElement(ET.SubElement(record,'GEOMETRY'),f'{{{GML}}}Point',srsName='EPSG:4326')
        ET.SubElement(p,f'{{{GML}}}coordinates').text=f'{21+number/10000},52.2'
    return ET.tostring(root)


def test_process_all_batches_resume_and_reproduce_offline(tmp_path):
    calls=[]
    def fetch(params):calls.append(params);return response(params)
    raw=json.dumps(source(123)+source(1)).encode()
    report=process_all(raw,tmp_path,batch_size=50,fetch=fetch,sleep=lambda _:None)
    assert len(calls)==3
    assert report['source_records']==124 and report['duplicate_source_records']==1
    assert report['processed_sites']==report['geolocated_addresses']==123
    assert report['unresolved_addresses']==report['co_located_address_duplicates']==0
    assert len(load_snapshot('sports',tmp_path/'sports.geojson')['records'])==123
    first=json.loads((tmp_path/'sports.geojson').read_text())
    again=process_all(raw,tmp_path,batch_size=50,offline=True,fetch=lambda _:pytest.fail('Unexpected network'))
    assert again['geolocated_addresses']==123 and again['network_requests']==0
    second=json.loads((tmp_path/'sports.geojson').read_text())
    assert first['features']==second['features']
    assert first['metadata']['retrieved_at'] is None  # Offline input is not a fresh sports observation.
    assert second['metadata']['retrieved_at'] is None
    assert all(f['properties']['coordinate_retrieved_at'] for f in second['features'])


def test_partial_failure_preserves_snapshot_and_resumes(tmp_path):
    raw=json.dumps(source(12)).encode()
    prior={'metadata':{'retrieved_at':'2026-01-01T00:00:00+00:00'},'features':[]}
    (tmp_path/'sports.geojson').write_text(json.dumps(prior))
    calls=[]
    def fail_second(params):
        calls.append(params)
        if len(calls)==2:raise ValueError('Unavailable provider')
        return response(params)
    report=process_all(raw,tmp_path,batch_size=5,fetch=fail_second,sleep=lambda _:None)
    assert report['status_counts']=={'located':5,'batch_failed':5,'pending':2}
    assert len(json.loads((tmp_path/'sports.geojson').read_text())['features'])==5
    assert any(json.loads(p.read_text())==prior for p in (tmp_path/'normalized_history').glob('*.geojson'))
    resumed=[]
    def fetch(params):resumed.append(params);return response(params)
    report=process_all(raw,tmp_path,batch_size=5,fetch=fetch,sleep=lambda _:None)
    assert len(resumed)==2 and report['geolocated_addresses']==12
    assert len(list((tmp_path/'normalized_history').glob('*.geojson')))==2


def test_wfs_errors_and_ambiguity_never_become_coordinates(tmp_path):
    with pytest.raises(ValueError):parse_points(b'<ExceptionReport/>')
    with pytest.raises(ValueError):parse_points(b'<!DOCTYPE a><FeatureCollection/>')
    raw=json.dumps(source(1)).encode()
    def ambiguous(params):
        root=ET.fromstring(response(params));other=ET.fromstring(ET.tostring(root[0]));other[0].find('ID').text='another';root.append(other)
        return ET.tostring(root)
    with pytest.raises(ValueError,match='No reliably located'):
        process_all(raw,tmp_path,fetch=ambiguous,sleep=lambda _:None)
    report=json.loads((tmp_path/'sports-processing-report.json').read_text())
    assert report['status_counts']=={'ambiguous':1}
    assert report['geolocated_addresses']==0


def test_batch_limit_and_address_normalization():
    assert address_parts('Aleja Jana Pawła II 26A')==('aleja Jana Pawła II','26A')
    assert address_parts('Plac Stanisława Małachowskiego 1')==('plac Stanisława Małachowskiego','1')
    assert address_parts('Leszczynowa 5, 03-197 Warszawa')==('ulica Leszczynowa','5')
    with pytest.raises(ValueError):batch_parameters([])
    with pytest.raises(ValueError):batch_parameters(source(51))


def test_snapshot_preserves_observed_date_and_separates_processing(tmp_path):
    stamp='2025-01-01T00:00:00+00:00'
    metadata=save_snapshot('sports',b'[]',[],{'retrieved_at':stamp},tmp_path)
    assert metadata['retrieved_at']==stamp
    assert metadata['processed_at']!=stamp


def test_resize_failed_batch_reuses_verified_checkpoint(tmp_path):
    raw=json.dumps(source(17)).encode();calls=[]
    def fail_second(params):
        calls.append(params)
        if len(calls)==2:raise ValueError('WFS error')
        return response(params)
    process_all(raw,tmp_path,batch_size=10,fetch=fail_second,sleep=lambda _:None)
    resumed=[]
    def fetch(params):resumed.append(params);return response(params)
    report=process_all(raw,tmp_path,batch_size=3,fetch=fetch,sleep=lambda _:None)
    assert len(resumed)==3  # Seven unresolved sites; first ten are never fetched again.
    assert report['geolocated_addresses']==17

