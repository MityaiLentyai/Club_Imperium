"""Process EVERY source site using cached, exact, batched municipal WFS joins.

python -m data_science.complete_sports --input data/infrastructure/raw/sports-HASH.json --offline
Network mode uses at most one sequential request per 1–50-site batch, never commercial geocoding.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import httpx

from data_science.ingestion_io import atomic_bytes, atomic_json
from data_science.ingest_sports import parse_sites, address_parts, address_filter, parse_address, SPORTS_URL, CATALOGUE
from data_science.ingest_infrastructure import WFS_URL, GML, MAX_BYTES, save_snapshot
from data_science.infrastructure import DATA_DIR, valid_coordinates

MAX_FEATURES = 500


class WFSQueryError(ValueError):
    """Provider rejected this query; not a negative address observation."""


def site_key(site):
    return hashlib.sha256((site['address'] + '|' + str(site['district'])).encode()).hexdigest()[:16]


def batch_parameters(sites):
    if not 1 <= len(sites) <= 50:
        raise ValueError('Select 1–50 sites per batch')
    root = ET.Element('{http://www.opengis.net/ogc}Filter')
    either = ET.SubElement(root, '{http://www.opengis.net/ogc}Or') if len(sites) > 1 else root
    for site in sites:
        parts = address_parts(site['address'])
        if not parts or not isinstance(site.get('district'), str):
            raise ValueError('Unsupported address')
        either.append(ET.fromstring(address_filter(*parts, site['district']))[0])
    return {'service':'WFS','version':'1.1.0','request':'GetFeature',
            'typeName':'wfs:PUNKTY_ADRESOWE_WGS84','maxFeatures':str(MAX_FEATURES),
            'outputFormat':'GML2','filter':ET.tostring(root,encoding='unicode')}


def parse_points(raw):
    if len(raw) > MAX_BYTES or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unsafe or oversized municipal XML')
    root = ET.fromstring(raw)
    if root.tag.split('}')[-1] != 'FeatureCollection':
        raise WFSQueryError('Municipal WFS exception, not an empty match')
    members = root.findall(f'{GML}featureMember')
    if len(members) >= MAX_FEATURES:
        raise ValueError('Municipal result cap reached; use a smaller batch')
    points = {}
    for member in members:
        record = next(iter(member), None)
        if record is None:
            continue
        props = {el.tag.split('}')[-1]:el.text for el in record}
        key = (props.get('NAZWA_PODST'), props.get('NR_PORZADK'), props.get('DZIELNICA'))
        coords = record.find(f'.//{GML}Point/{GML}coordinates')
        try:
            if coords is None or not props.get('ID'):
                continue
            point = record.find(f'.//{GML}Point')
            if point.get('srsName', 'EPSG:4326') not in ('EPSG:4326', 'urn:ogc:def:crs:EPSG::4326'):
                raise ValueError('Unexpected address CRS')
            lon, lat = map(float, coords.text.split(','))
            if not valid_coordinates(lat, lon):
                continue
            value = {'longitude':lon,'latitude':lat,'address_id':props['ID']}
            # Repeated identical IDs are duplicates; distinct candidates are ambiguous.
            bucket = points.setdefault(key,{})
            if props['ID'] in bucket and bucket[props['ID']] != value:
                raise WFSQueryError('Conflicting coordinates for one municipal address ID')
            bucket[props['ID']] = value
        except WFSQueryError:
            raise
        except (TypeError, ValueError, AttributeError):
            continue
    return {key:list(values.values()) for key,values in points.items()}


def fetch_batch(params):
    # This municipal MapGuide endpoint accepts KVP form POST, not XML-only POST.
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        with client.stream('POST', WFS_URL, data=params) as response:
            if response.status_code != 200:
                raise ValueError('Municipal source unavailable')
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('Municipal response too large')
                chunks.append(chunk)
    return b''.join(chunks)


def source_report(payload):
    serialized = [json.dumps(row, sort_keys=True, ensure_ascii=False) for row in payload]
    rejected = sum(not isinstance(row,dict) or not all(isinstance(row.get(k),str) and row[k].strip()
                   for k in ('Adres obiektu','Nazwa placówki oświatowej')) for row in payload)
    return {'source_records':len(payload), 'duplicate_source_records':len(serialized)-len(set(serialized)),
            'rejected_source_records':rejected}


def process_all(raw, output=DATA_DIR, *, batch_size=50, offline=False, fetch=fetch_batch, sleep=time.sleep):
    if not 1 <= batch_size <= 50 or len(raw) > MAX_BYTES:
        raise ValueError('Invalid sports processing bound')
    payload = json.loads(raw)
    sites = parse_sites(payload)
    if not sites:
        raise ValueError('No usable source sites; preserve existing snapshot')
    output = Path(output)
    cache = output / 'sports_batches'
    checkpoint = output / 'sports-processing-report.json'
    digest = hashlib.sha256(raw).hexdigest()
    report = {**source_report(payload), 'source_sha256':digest,'source_url':SPORTS_URL,
              'coordinate_source_url':WFS_URL,'source_sites':len(sites),'processed_sites':0,
              'batch_size':batch_size,'network_requests':0,'sites':[]}
    resolved, pending = {}, []
    previous_report = {}
    try:
        saved = json.loads(checkpoint.read_text())
        if saved.get('source_sha256') == digest:
            previous_report = {row['source_id']:row for row in saved['sites']}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    evidence_cache = {}
    for site in sites:
        key = site_key(site)
        parts = address_parts(site['address'])
        if not parts or not isinstance(site.get('district'),str):
            resolved[key] = {'status':'unsupported_address','point':None,'retrieved_at':None}
            continue
        old = previous_report.get(key, {})
        if old.get('status') in ('located', 'unmatched', 'ambiguous') and old.get('evidence'):
            evidence = output / old['evidence']
            try:
                if not evidence.resolve().is_relative_to(output.resolve()):
                    raise ValueError('Evidence must stay in output directory')
                if evidence not in evidence_cache:
                    content = evidence.read_bytes()
                    meta_path = evidence.with_suffix('.json')
                    observed = None
                    if meta_path.exists():
                        meta = json.loads(meta_path.read_text())
                        if meta['sha256'] != hashlib.sha256(content).hexdigest():
                            raise ValueError('Corrupt checkpoint evidence')
                        observed = meta.get('retrieved_at')
                    evidence_cache[evidence] = (parse_points(content), observed)
                points, observed = evidence_cache[evidence]
                matches = points.get((*parts, site['district']), [])
                point = matches[0] if len(matches)==1 else None
                resolved[key] = {'status':'located' if point else 'ambiguous' if matches else 'unmatched',
                                 'point':point,'retrieved_at':observed,'evidence':old['evidence']}
                continue
            except (OSError, ValueError, TypeError, KeyError, ET.ParseError):
                pass
        legacy = output / 'sports_addresses' / f'{key}.gml'
        if legacy.exists():
            try:
                point = parse_address(legacy.read_bytes(),*parts,site['district'])
                if point:
                    resolved[key] = {'status':'located','point':point,'retrieved_at':None,'evidence':str(legacy.relative_to(output))}
                    continue
            except (ValueError, ET.ParseError):
                pass
        pending.append(site)

    def save_report():
        report['processed_at'] = datetime.now(timezone.utc).isoformat()
        report['sites'] = [{'source_id':site_key(s),'address':s['address'],'district':s['district'],
                           **resolved.get(site_key(s),{'status':'pending','point':None,'retrieved_at':None})} for s in sites]
        statuses = Counter(s['status'] for s in report['sites'])
        report.update(status_counts=dict(statuses),processed_sites=sum(v for k,v in statuses.items() if k not in ('pending','batch_failed')),
                      geolocated_addresses=statuses['located'], unresolved_addresses=len(sites)-statuses['located'],
                      attempted_sites=len(sites)-statuses['pending'])
        atomic_json(checkpoint,report)

    for offset in range(0,len(pending),batch_size):
        batch = pending[offset:offset+batch_size]
        params = batch_parameters(batch)
        query_hash = hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
        path = cache / f'{query_hash[:20]}.gml'
        meta_path = path.with_suffix('.json')
        observed = None
        try:
            if path.exists():
                content = path.read_bytes()
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text())
                    if meta['sha256'] != hashlib.sha256(content).hexdigest() or meta['query_sha256'] != query_hash:
                        raise ValueError('Corrupt batch cache; preserve it for review')
                    observed = meta.get('retrieved_at')
            elif offline:
                save_report()
                continue
            else:
                report['network_requests'] += 1
                try:
                    content = fetch(params)
                    parse_points(content)
                    observed = datetime.now(timezone.utc).isoformat()
                    atomic_bytes(path,content)
                    atomic_json(meta_path,{'sha256':hashlib.sha256(content).hexdigest(),'query_sha256':query_hash,
                                'retrieved_at':observed,'source_url':WFS_URL,'request_parameters':params})
                finally:
                    sleep(1.1)
            points = parse_points(content)
            for site in batch:
                matches = points.get((*address_parts(site['address']),site['district']),[])
                point = matches[0] if len(matches)==1 else None
                resolved[site_key(site)] = {'status':'located' if point else 'ambiguous' if matches else 'unmatched',
                                          'point':point,'retrieved_at':observed,'evidence':str(path.relative_to(output))}
        except WFSQueryError:
            for site in batch:
                resolved[site_key(site)] = {'status':'batch_failed','point':None,'retrieved_at':None}
            save_report()
            continue
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError, httpx.HTTPError):
            for site in batch:
                resolved[site_key(site)] = {'status':'batch_failed','point':None,'retrieved_at':None}
            save_report()
            # Source failure is not a negative geocoding observation. Resume later.
            break
        save_report()
    save_report()
    groups = {}
    for site in sites:
        match = resolved.get(site_key(site),{})
        point = match.get('point')
        if not point:
            continue
        xy = (point['longitude'],point['latitude'])
        group = groups.setdefault(xy,{'sites':[],'matches':[]})
        group['sites'].append(site);group['matches'].append(match)
    features = []
    for xy,group in groups.items():
        primary = group['sites'][0]
        names = sorted({row['Nazwa placówki oświatowej'].strip() for row in payload if isinstance(row,dict)
                        and any(row.get('Adres obiektu')==site['address'] and row.get('Dzielnica')==site['district'] for site in group['sites'])})
        schedules = []
        for site in group['sites']:
            for schedule in site['schedules']:
                if schedule not in schedules:schedules.append(schedule)
        props = {**primary,'source_id':site_key(primary),'name':' / '.join(names) or primary['name'],
                 'names':names,'addresses':[s['address'] for s in group['sites']],
                 'source_site_ids':[site_key(s) for s in group['sites']],
                 'sport_types':sorted({t for s in group['sites'] for t in s['sport_types']}),'schedules':schedules,
                 'address_id':group['matches'][0]['point']['address_id'],
                 'coordinate_source':'Warsaw municipal address point; proxy for site, not field or entrance',
                 'coordinate_retrieved_at':group['matches'][0]['retrieved_at']}
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':list(xy)},'properties':props})
    report.update(valid_facility_points=len(features),co_located_address_duplicates=report['geolocated_addresses']-len(features))
    atomic_json(checkpoint,report)
    if not features:
        raise ValueError('No reliably located facilities; existing snapshot preserved')
    previous = output / 'sports.geojson'
    prior = json.loads(previous.read_text()) if previous.exists() else {}
    metadata = prior.get('metadata',{})
    # Never drop a previously verified point when a later provider batch fails.
    previous_points = {tuple(f['geometry']['coordinates']) for f in prior.get('features',[])}
    if not previous_points.issubset(groups):
        report['snapshot_updated'] = False
        atomic_json(checkpoint,report)
        return report
    retrieved = metadata.get('retrieved_at') if metadata.get('sha256')==digest else None
    metadata = {**metadata, 'source_url':SPORTS_URL,'catalogue_url':CATALOGUE,'retrieved_at':retrieved,
                'source_crs':'EPSG:4326','source_records':len(payload),'source_sites':len(sites),
                'selected_sites':len(sites),'processed_sites':report['processed_sites'],'attempted_sites':report['attempted_sites'],'unresolved_count':report['unresolved_addresses'],
                'unresolved_addresses':[s['address'] for s in report['sites'] if s['status']!='located'],
                'geolocated_addresses':report['geolocated_addresses'],'coordinate_source_url':WFS_URL,
                'coverage':f"Saved educational sports source: {report['attempted_sites']}/{len(sites)} site addresses attempted; incomplete Warsaw sports inventory; address-point proxies"}
    # Preserve previous snapshots (and their metadata) without overwriting the archive.
    if previous.exists() and (prior.get('features') != features or prior.get('metadata',{}).get('sha256') != digest):
        archive = output / 'normalized_history' / ('sports-'+hashlib.sha256(previous.read_bytes()).hexdigest()[:16]+'.geojson')
        if not archive.exists():atomic_bytes(archive,previous.read_bytes())
    save_snapshot('sports',raw,features,metadata,output)
    report['snapshot_updated'] = True
    atomic_json(checkpoint,report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=DATA_DIR)
    parser.add_argument('--batch-size',type=int,default=50)
    parser.add_argument('--offline',action='store_true')
    args = parser.parse_args()
    try:
        report = process_all(args.input.read_bytes(),args.output,batch_size=args.batch_size,offline=args.offline)
        print(json.dumps({key:value for key,value in report.items() if key!='sites'},ensure_ascii=False))
    except (OSError,ValueError,TypeError,KeyError):
        parser.exit(1,'Sports processing failed; prior snapshots and caches preserved.\n')


if __name__=='__main__':main()
