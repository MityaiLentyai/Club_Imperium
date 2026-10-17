import json
from pathlib import Path

from data_science.infrastructure import load_snapshot

def test_complete_parks_and_parking_audit_reconciles_all_rows():
    from data_science.audit_infrastructure import audit_parks,audit_parking,audit_parkride
    from data_science.ingest_infrastructure import input_provenance
    root=Path('data/infrastructure')
    green=json.loads((root/'green.geojson').read_text())
    _,report=audit_parks((root/green['metadata']['raw_file']).read_bytes())
    assert report['processed_records']==report['source_records']==430
    assert report['valid_park_objects']==60
    assert report['decisions']['green_square_needs_vegetation_evidence']==172
    assert sum(report['decisions'].values())==430
    parking=json.loads((root/'parking.geojson').read_text())
    raw=(root/parking['metadata']['raw_file']).read_bytes()
    _,report=audit_parking(json.loads(raw))
    assert report['processed_records']==19 and report['valid_records']==18
    assert report['rejections']=={'invalid_coordinates':1}
    p=input_provenance(raw,'parking',root/parking['metadata']['raw_file'],root)
    assert p['retrieved_at']==parking['metadata']['retrieved_at']
    parkride=json.loads((root/'parkride-processing-report.json').read_text())
    report=audit_parkride((root/parkride['raw_file']).read_bytes())
    assert report['processed_records']==report['valid_records']==14
    assert not report['imported_into_live_facilities']


def test_complete_sports_snapshot_integrity_and_all_addresses_reconciled():
    report=json.loads(Path('data/infrastructure/sports-processing-report.json').read_text())
    dataset=load_snapshot('sports')
    assert report['source_records']==1227 and report['source_sites']==308
    assert report['processed_sites']==report['attempted_sites']==308
    assert report['geolocated_addresses']==293 and report['unresolved_addresses']==15
    assert len({s['source_id'] for s in report['sites']})==308
    assert len(dataset['records'])==report['valid_facility_points']==291
    assert report['co_located_address_duplicates']==2
    assert sum(report['status_counts'].values())==308
    assert all(s['point'] is None for s in report['sites'] if s['status']!='located')
    assert all(props['names'] and props['schedules'] and props['sport_types'] for props,_,_ in dataset['records'])
