"""Offline complete-source audits; no green-square or live-availability inference."""
from collections import Counter
import hashlib
import xml.etree.ElementTree as ET

from data_science.ingest_infrastructure import parse_parks, parse_parking, GML, MAX_BYTES
from data_science.infrastructure import valid_coordinates


def audit_parks(raw):
    features,meta=parse_parks(raw)
    records=[]
    for member in ET.fromstring(raw).findall(f'{GML}featureMember'):
        record=next(iter(member),None)
        if record is None:continue
        props={el.tag.split('}')[-1]:el.text for el in record}
        kind=props.get('OBIEKT')
        decision='eligible_park' if kind=='Park' else 'green_square_needs_vegetation_evidence' if kind in ('Skwer','Skwerek') else 'excluded_other_named_space'
        records.append({'source_id':props.get('ID'),'name':props.get('NAZWA_PODST'),'classification':kind,'decision':decision})
    return features,{**meta,'source_sha256':hashlib.sha256(raw).hexdigest(),'processed_records':len(records),
                     'valid_park_objects':len(features),'decisions':dict(Counter(r['decision'] for r in records)),
                     'records':records,'coverage':'All returned named-space records processed below the explicit 500-record cap; not all Warsaw green space'}


def audit_parking(payload):
    features,meta=parse_parking(payload)
    rows=payload.get('carParks',payload.get('Parkings'))
    rejected=Counter();seen_ids=set();seen_coords=set()
    for row in rows:
        if not isinstance(row,dict):rejected['invalid_record']+=1;continue
        name=str(row.get('name') or '').strip();lat=row.get('latitude');lon=row.get('longitude')
        if not name:rejected['missing_name']+=1;continue
        if not valid_coordinates(lat,lon):rejected['invalid_coordinates']+=1;continue
        xy=(round(float(lat),6),round(float(lon),6))
        identifier=str(row.get('id') or hashlib.sha256(f'{float(lat):.6f},{float(lon):.6f}'.encode()).hexdigest()[:16])
        if identifier in seen_ids or xy in seen_coords:rejected['duplicate_id_or_coordinate']+=1;continue
        seen_ids.add(identifier);seen_coords.add(xy)
    return features,{**meta,'processed_records':len(rows),'valid_records':len(features),'rejections':dict(rejected),
                     'facility_kind':'listed parking facility; not street zones or individual spaces',
                     'current_availability':'not published: observation timestamp unverified'}


def audit_parkride(raw):
    """Validate all advertised P+R points without treating old source dates as current."""
    if len(raw)>MAX_BYTES or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Unsafe XML')
    root=ET.fromstring(raw)
    if root.tag.split('}')[-1]!='FeatureCollection':raise ValueError('Unexpected WFS response')
    members=root.findall(f'{GML}featureMember')
    if not members or len(members)>=200:raise ValueError('Empty or capped source')
    valid=[];rejected=Counter();seen=set()
    for member in members:
        record=next(iter(member),None)
        if record is None:rejected['invalid_record']+=1;continue
        props={e.tag.split('}')[-1]:e.text for e in record}
        coord=record.find(f'.//{GML}Point/{GML}coordinates')
        try:
            lon,lat=map(float,coord.text.split(','))
            if not props.get('OBJECTID') or not props.get('NAZWA') or not valid_coordinates(lat,lon):raise ValueError()
            identifier=props['OBJECTID']
            if identifier in seen:rejected['duplicate_id']+=1;continue
            seen.add(identifier)
            # AUTA is retained as supplied: disability spaces may be a subset; do not sum.
            valid.append({'source_id':identifier,'name':props['NAZWA'],'longitude':lon,'latitude':lat,
                          'source_updated_at_text':props.get('AKTU_DAN'),'source_properties':props})
        except (ValueError,TypeError,AttributeError):rejected['invalid_geometry_or_properties']+=1
    return {'source_records':len(members),'processed_records':len(members),'valid_records':len(valid),
            'rejections':dict(rejected),'records':valid,'source_sha256':hashlib.sha256(raw).hexdigest(),
            'imported_into_live_facilities':False,
            'reason':'Historical P+R layer; current operation/membership not verified against current WTP directory. Retained for review, not mixed into current listed-facility counts.'}


def main():
    """Reproduce all selected-source quality reports without network access."""
    import argparse
    from datetime import datetime,timezone
    import json
    from pathlib import Path
    from data_science.infrastructure import DATA_DIR
    from data_science.ingestion_io import atomic_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=DATA_DIR)
    parser.add_argument('--category',choices=['all','green','parking','parkride'],default='all')
    args=parser.parse_args()
    categories=['green','parking','parkride'] if args.category=='all' else [args.category]
    try:
        for category in categories:
            report_path=args.directory/f'{category}-processing-report.json'
            previous=json.loads(report_path.read_text()) if report_path.exists() else {}
            if category=='parkride':
                meta=previous;raw=(args.directory/meta['raw_file']).read_bytes();report=audit_parkride(raw)
            else:
                meta=json.loads((args.directory/f'{category}.geojson').read_text())['metadata']
                raw=(args.directory/meta['raw_file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Snapshot source checksum mismatch')
                _,report=audit_parks(raw) if category=='green' else audit_parking(json.loads(raw))
            report={**previous,**report,'processed_at':datetime.now(timezone.utc).isoformat(),
                    'source_url':meta.get('source_url'),'source_retrieved_at':meta.get('retrieved_at')}
            if category=='parkride':
                # Different source IDs need explicit reconciliation before a union.
                from pyproj import Geod
                parking=json.loads((args.directory/'parking.geojson').read_text())
                candidates=[]
                geod=Geod(ellps='WGS84')
                for point in report['records']:
                    for facility in parking['features']:
                        lon,lat=facility['geometry']['coordinates']
                        distance=geod.inv(point['longitude'],point['latitude'],lon,lat)[2]
                        if distance<=150:
                            candidates.append({'historic_source_id':point['source_id'],'historic_name':point['name'],
                                               'listed_source_id':facility['properties']['source_id'],
                                               'listed_name':facility['properties']['name'],'distance_m':round(distance,1),
                                               'decision':'overlap candidate only; not counted as a new live facility'})
                report['cross_source_overlap_candidates']=candidates
            atomic_json(report_path,report)
            print(json.dumps({'category':category,'source_records':report['source_records'],
                              'processed_records':report['processed_records'],
                              'valid_records':report.get('valid_records',report.get('valid_park_objects'))}))
    except (OSError,ValueError,KeyError,TypeError):
        parser.exit(1,'Offline audit failed; preserve existing source files and inspect checksums.\n')


if __name__=='__main__':main()
