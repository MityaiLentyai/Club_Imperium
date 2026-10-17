"""Complete bounded unfiltered WFS address download with compressed evidence.

The provider's KVP BBOX produced out-of-box points during verification, so no
partition-based completeness claim is made. One full unfiltered response below
an explicit record/byte cap is normalized and checked against municipal geometry.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import xml.etree.ElementTree as ET

import httpx
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Polygon,mapping,Point,shape
from shapely.ops import unary_union

from data_science.geography import DISTRICTS,TO_METRES
from data_science.ingestion_io import atomic_bytes,atomic_json
from data_science.ingest_infrastructure import WFS_URL,GML

ROOT = Path(__file__).resolve().parents[1] / 'data/geography'
ADDRESS_LAYER = 'wfs:PUNKTY_ADRESOWE_WGS84'
MAX_BYTES = 128_000_000
FEATURE_CAP = 200000


def xml_root(raw):
    if len(raw)>MAX_BYTES or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unsafe XML')
    root=ET.fromstring(raw)
    if root.tag.split('}')[-1]!='FeatureCollection':
        raise ValueError('WFS exception; never treat as empty coverage')
    return root


def normalize_boundaries(raw):
    root=xml_root(raw);features=[];names=set()
    to_wgs=Transformer.from_crs(2178,4326,always_xy=True).transform
    for member in root.findall(f'{GML}featureMember'):
        record=next(iter(member),None)
        if record is None:raise ValueError('Malformed district')
        props={e.tag.split('}')[-1]:e.text for e in record}
        name=props.get('DZIELNICA')
        if name not in DISTRICTS or name in names:raise ValueError('Unexpected district set')
        polygons=[]
        for polygon in record.iter(f'{GML}Polygon'):
            if polygon.get('srsName')!='EPSG:2178':raise ValueError('Unexpected district CRS')
            def ring(element):
                return [tuple(map(float,pair.split(','))) for pair in element.find(f'.//{GML}coordinates').text.split()]
            geom=Polygon(ring(polygon.find(f'{GML}outerBoundaryIs')),[ring(h) for h in polygon.findall(f'{GML}innerBoundaryIs')])
            if geom.is_empty or not geom.is_valid:raise ValueError('Invalid district polygon')
            polygons.append(geom)
        if not polygons:raise ValueError('Missing district polygon')
        geom=transform(unary_union(polygons),to_wgs,interleaved=False)
        features.append({'type':'Feature','properties':{'source_id':props['OBJECTID'],'name':name,
                        'source_updated_at_text':props.get('AKTU_DAN'),'source_authority':props.get('POCH_DAN')},'geometry':mapping(geom)})
        names.add(name)
    if names!=DISTRICTS:raise ValueError('All 18 official districts required')
    city=unary_union([shape(f['geometry']) for f in features])
    if not city.is_valid or not 400e6<transform(city,TO_METRES,interleaved=False).area<650e6:
        raise ValueError('Implausible city union')
    return features,city


def publish_boundaries(raw,retrieved_at,output=ROOT):
    output=Path(output);features,city=normalize_boundaries(raw)
    digest=hashlib.sha256(raw).hexdigest();archive=output/'raw'/f'districts-{digest[:16]}.gml.gz'
    if not archive.exists():atomic_bytes(archive,gzip.compress(raw,mtime=0))
    data={'type':'FeatureCollection','metadata':{'source_url':WFS_URL,'type_name':'ns92528565:GRANICE_DZIELNIC',
          'source_crs':'EPSG:2178','normalized_crs':'EPSG:4326','record_count':18,'retrieved_at':retrieved_at,
          'sha256':digest,'raw_file':str(archive.relative_to(output)),
          'scope':'Official district union; source update dates retained, not a claim of current legal boundary survey'},'features':features}
    atomic_json(output/'warsaw-districts.geojson',data)
    return city


def fetch_source(output=ROOT,max_records=FEATURE_CAP):
    params={'service':'WFS','version':'1.1.0','request':'GetFeature','typeName':ADDRESS_LAYER,
            'maxFeatures':str(max_records),'outputFormat':'GML2'}
    chunks=[];size=0
    with httpx.Client(timeout=120,follow_redirects=False) as client:
        with client.stream('GET',WFS_URL,params=params) as response:
            if response.status_code!=200:raise ValueError('Municipal full source unavailable')
            for chunk in response.iter_bytes():
                size+=len(chunk)
                if size>MAX_BYTES:raise ValueError('Municipal full source exceeds explicit byte bound')
                chunks.append(chunk)
    raw=b''.join(chunks)
    # Do not persist an exception response as a valid complete source.
    xml_root(raw)
    digest=hashlib.sha256(raw).hexdigest();output=Path(output)
    path=output/'raw'/f'addresses-{digest[:16]}.gml.gz'
    if not path.exists():atomic_bytes(path,gzip.compress(raw,mtime=0))
    meta={'source_url':WFS_URL,'request_parameters':params,'retrieved_at':datetime.now(timezone.utc).isoformat(),
          'sha256':digest,'raw_file':str(path.relative_to(output)),'uncompressed_bytes':size,'max_bytes':MAX_BYTES}
    atomic_json(path.with_suffix('.json'),meta);atomic_json(output/'address-source.json',meta)
    return raw,meta


def process_source(raw,city,*,max_records=FEATURE_CAP,source_metadata=None):
    import math
    from collections import Counter
    from shapely.prepared import prep
    root=xml_root(raw);members=root.findall(f'{GML}featureMember')
    if not members or len(members)>=max_records:
        raise ValueError('Empty or capped response cannot establish full source processing')
    rows={};duplicates=0;rejected=Counter()
    for member in members:
        record=next(iter(member),None)
        if record is None:rejected['missing_record']+=1;continue
        props={e.tag.split('}')[-1]:e.text for e in record}
        try:
            coords=record.find(f'.//{GML}Point/{GML}coordinates')
            point=record.find(f'.//{GML}Point')
            if point.get('srsName','EPSG:4326') not in ('EPSG:4326','urn:ogc:def:crs:EPSG::4326'):
                raise ValueError('Unexpected address CRS')
            lon,lat=map(float,coords.text.split(','))
            if not math.isfinite(lon) or not math.isfinite(lat) or not -180<=lon<=180 or not -90<=lat<=90:
                raise ValueError('Invalid geographic coordinate')
            if not all(isinstance(props.get(k),str) and props[k].strip() for k in ['ID','NAZWA_PODST','NR_PORZADK']):
                raise ValueError('Missing address properties')
            row={'id':props['ID'],'street':props['NAZWA_PODST'],'short_name':props.get('NAZWA_SKROC') or '',
                 'building':props['NR_PORZADK'],'district':props.get('DZIELNICA') or '',
                 'latitude':lat,'longitude':lon}
        except (ValueError,TypeError,AttributeError):
            rejected['invalid_geometry_or_properties']+=1;continue
        if row['id'] in rows:
            if rows[row['id']]!=row:raise RuntimeError('Conflicting duplicate municipal ID')
            duplicates+=1
        else:rows[row['id']]=row
    municipal=transform(city,TO_METRES,interleaved=False);prepared=prep(municipal)
    valid=[];outside=[]
    for row in rows.values():
        point=transform(Point(row['longitude'],row['latitude']),TO_METRES,interleaved=False)
        if prepared.covers(point) or municipal.distance(point)<=0.5:valid.append(row)
        else:outside.append(row['id'])
    report={'source_url':WFS_URL,'type_name':ADDRESS_LAYER,'source_records':len(members),
            'processed_records':len(members),'unique_source_records':len(rows),'duplicate_id_records':duplicates,
            'rejected_records':sum(rejected.values()),'rejections':dict(rejected),
            'outside_boundary_records':len(outside),'outside_boundary_ids':outside,'valid_city_addresses':len(valid),
            'unfiltered_source':True,'below_requested_record_cap':True,'record_cap':max_records,
            'completeness_basis':'Full unfiltered WFS response below requested cap; no independent upstream count available',
            'bbox_partition_supported':False,'by_source_district':dict(Counter(r['district'] for r in valid)),
            'source_metadata':source_metadata or {},
            'limitation':'Observed municipal snapshot, not a guarantee that every current or future address is present'}
    return valid,report


def publish_index(records,report,output=ROOT):
    from data_science.address_lookup import street_key,street_without_type,fold_key,building_key,district_key
    output=Path(output)
    with tempfile.TemporaryDirectory(prefix='urbanlens-index-') as directory:
        path=Path(directory)/'addresses.sqlite'
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE addresses(id TEXT PRIMARY KEY,street TEXT,short_name TEXT,building TEXT,district TEXT,latitude REAL,longitude REAL);'
                             'CREATE TABLE lookup(kind TEXT,street_key TEXT,building_key TEXT,district_key TEXT,id TEXT,PRIMARY KEY(kind,street_key,building_key,district_key,id));')
            for r in sorted(records,key=lambda r:r['id']):
                db.execute('INSERT INTO addresses VALUES(?,?,?,?,?,?,?)',tuple(r[k] for k in ['id','street','short_name','building','district','latitude','longitude']))
                for name in set([r['street'],r['short_name'],street_without_type(r['street']),street_without_type(r['short_name'])]):
                    if not name:continue
                    key=street_key(name)
                    for kind,value in [('unicode',key),('folded',fold_key(key))]:
                        db.execute('INSERT OR IGNORE INTO lookup VALUES(?,?,?,?,?)',(kind,value,building_key(r['building']),district_key(r['district']),r['id']))
            db.execute('CREATE INDEX lookup_street ON lookup(kind,street_key)')
            db.commit();db.execute('VACUUM')
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('SELECT COUNT(*) FROM addresses').fetchone()[0]==len(records)
        raw=path.read_bytes();compressed=gzip.compress(raw,mtime=0)
    digest=hashlib.sha256(raw).hexdigest();name=f'addresses-{digest[:16]}.sqlite.gz'
    # Content-addressed indices + atomic manifest avoid mixed old/new generations.
    atomic_bytes(output/name,compressed)
    atomic_json(output/'address-index.json',{'database_file':name,'sha256':digest,'compressed_sha256':hashlib.sha256(compressed).hexdigest(),
                                           'record_count':len(records),'report':report})
    atomic_json(output/'address-processing-report.json',report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--refresh-source',action='store_true')
    parser.add_argument('--max-records',type=int,default=FEATURE_CAP)
    args=parser.parse_args()
    if not 1<=args.max_records<=FEATURE_CAP or args.offline and args.refresh_source:
        parser.error('Invalid bounded source request')
    try:
        boundaries=json.loads((args.output/'warsaw-districts.geojson').read_text())
        if {f['properties']['name'] for f in boundaries['features']}!=DISTRICTS:
            raise ValueError('All municipal districts required')
        city=unary_union([shape(f['geometry']) for f in boundaries['features']])
        pointer=args.output/'address-source.json'
        if args.refresh_source or not pointer.exists():
            if args.offline:raise ValueError('Missing saved source')
            raw,meta=fetch_source(args.output,args.max_records)
        else:
            meta=json.loads(pointer.read_text())
            if not (args.output/meta['raw_file']).resolve().is_relative_to(args.output.resolve()):
                raise ValueError('Unsafe raw source path')
            raw=gzip.decompress((args.output/meta['raw_file']).read_bytes())
            if len(raw)>MAX_BYTES or hashlib.sha256(raw).hexdigest()!=meta['sha256']:
                raise ValueError('Corrupt source archive')
        records,report=process_source(raw,city,max_records=int(meta['request_parameters']['maxFeatures']),source_metadata=meta)
        if not records or set(report['by_source_district'])!=DISTRICTS:
            raise ValueError('Citywide snapshot does not represent all 18 source districts')
        publish_index(records,report,args.output)
        print(json.dumps({k:v for k,v in report.items() if k!='outside_boundary_ids'},ensure_ascii=False))
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,ET.ParseError,httpx.HTTPError):
        parser.exit(1,'Address ingestion incomplete; cached source and previous index preserved.\n')


if __name__=='__main__':main()
