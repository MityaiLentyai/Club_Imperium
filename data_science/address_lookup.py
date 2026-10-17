"""Read-only local municipal address lookup with conservative Polish normalization."""
from functools import lru_cache
from contextlib import closing
import threading
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata

from data_science.geography import DISTRICTS

_load_lock = threading.Lock()

MANIFEST = Path(__file__).resolve().parents[1] / 'data/geography/address-index.json'
PREFIX = re.compile(r'^(ulica|ul\.?|aleja|aleje|al\.?|plac|pl\.?|rondo|skwer|rynek|pasaż)(?:\s+|(?<=\.))',re.I)


def fold_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',value.replace('ł','l').replace('Ł','L')) if not unicodedata.combining(c))


def street_key(value):
    value=unicodedata.normalize('NFKC',value).casefold().strip()
    value=re.sub('[–—−]','-',value)
    match=PREFIX.match(value)
    if match:
        prefix={'ul':'ulica','ul.':'ulica','al':'aleja','al.':'aleja','pl':'plac','pl.':'plac'}.get(match[1],match[1])
        value=prefix+' '+value[match.end():]
    value=re.sub(r'[.\s]+',' ',value)
    value=re.sub(r'\s*-\s*','-',value)
    return value.strip()


def street_without_type(value):
    return re.sub(r'^(?:ulica|aleja|aleje|plac|rondo|skwer|rynek|pasaż)\s+','',street_key(value))


def building_key(value):
    value=unicodedata.normalize('NFKC',value).upper()
    return re.sub(r'\s+','',re.sub('[–—−]','-',value))


def district_key(value):
    return fold_key(' '.join(value.casefold().split()))


def parse_query(address):
    text=unicodedata.normalize('NFKC',address).strip()
    text=re.sub(r'(?<!\d)\d{2}-\d{3}(?!\d)','',text)
    parts=[p.strip() for p in text.split(',') if p.strip()]
    district=None;remaining=[]
    names={district_key(d):d for d in DISTRICTS}
    for part in parts:
        norm=' '.join(part.casefold().split())
        candidate=re.sub(r'^dzielnica\s+','',norm)
        if candidate in ('warszawa','warsaw','polska','poland','m.st. warszawa'):
            continue
        if district_key(candidate) in names:
            if district and district!=names[district_key(candidate)]:return None
            district=names[district_key(candidate)]
        else:remaining.append(part)
    text=' '.join(remaining)
    text=re.sub(r'^(?:warszawa|warsaw)\s+','',text,flags=re.I)
    text=re.sub(r'\s+(?:warszawa|warsaw)$','',text,flags=re.I)
    # An explicitly labelled apartment can be omitted; a bare slash is never guessed.
    text=re.sub(r'\s+(?:m\.?|mieszkanie|lok\.?|lokal)\s*\d+[A-Za-z]?\s*$','',text,flags=re.I)
    number = r"\d+(?:\s*[^\W\d_]+[^\W_]*(?:\.\s*\d+[^\W_]*)?)?"
    building = number + r"(?:\s*[/\-–—]\s*" + number + r")*"
    match=re.fullmatch(r"(.+?)(?:\s+|(?<=[^\W\d_]))(" + building + ")",text.strip())
    if not match or not re.search(r'[^\d\W]',match[1],re.UNICODE):return None
    return {'street':match[1].strip(),'building':building_key(match[2]),'district':district}


@lru_cache(maxsize=1)
def _load(path,modified,size):
    directory=None
    try:
        meta=json.loads(Path(path).read_text());name=meta['database_file']
        if Path(name).name!=name or not name.endswith('.sqlite.gz'):return None
        source=Path(path).parent/name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=meta['compressed_sha256']:return None
        directory=tempfile.TemporaryDirectory(prefix='urbanlens-address-lookup-')
        database=Path(directory.name)/'addresses.sqlite';digest=hashlib.sha256();total=0
        with gzip.open(source,'rb') as src,database.open('wb') as target:
            while chunk:=src.read(1_000_000):
                total+=len(chunk)
                if total>200_000_000:raise ValueError('Index exceeds supported size')
                digest.update(chunk);target.write(chunk)
        if digest.hexdigest()!=meta['sha256']:raise ValueError('Index checksum mismatch')
        with closing(sqlite3.connect(f'file:{database}?mode=ro',uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid index')
            if db.execute('SELECT COUNT(*) FROM addresses').fetchone()[0]!=meta['record_count']:raise ValueError('Invalid count')
        return {'directory':directory,'database':database,'metadata':meta}
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,EOFError):
        if directory:directory.cleanup()
        return None


def load_index():
    try:
        info=MANIFEST.stat()
        with _load_lock:
            return _load(MANIFEST,info.st_mtime_ns,info.st_size)
    except OSError:return None


def lookup(address):
    parsed=parse_query(address)
    if parsed is None:return {'status':'invalid_address'}
    data=load_index()
    if data is None:return {'status':'unavailable'}
    unicode_key=street_key(parsed['street']);number=parsed['building']
    try:
        with closing(sqlite3.connect(f"file:{data['database']}?mode=ro",uri=True)) as db:
            db.row_factory=sqlite3.Row
            # A complete known street name ending in digits is not a house address.
            full=street_key(parsed['street']+' '+parsed['building'])
            if db.execute('SELECT 1 FROM lookup WHERE kind=? AND street_key=? LIMIT 1',('unicode',full)).fetchone():
                return {'status':'invalid_address'}
            kind,key='unicode',unicode_key
            exact_street=db.execute('SELECT 1 FROM lookup WHERE kind=? AND street_key=? LIMIT 1',(kind,key)).fetchone()
            if not exact_street:kind,key='folded',fold_key(unicode_key)
            sql=('SELECT DISTINCT a.* FROM lookup l JOIN addresses a ON a.id=l.id '
                 'WHERE l.kind=? AND l.street_key=? AND l.building_key=?')
            params=[kind,key,number]
            if parsed['district']:
                sql+=' AND l.district_key=?';params.append(district_key(parsed['district']))
            rows=db.execute(sql+' ORDER BY a.id',params).fetchall()
    except sqlite3.Error:return {'status':'unavailable'}
    distinct={ (r['latitude'],r['longitude']):r for r in rows }
    if len(distinct)>1:return {'status':'ambiguous','candidate_count':len(distinct)}
    if not distinct:return {'status':'not_found'}
    row=next(iter(distinct.values()))
    return {'status':'found','address_id':row['id'],'result':{'latitude':row['latitude'],'longitude':row['longitude'],
             'address':f"{row['street']} {row['building']}, {row['district']}, Warszawa"}}


def audit_index():
    """Read-only audit of canonical round trips and ambiguous lookup keys."""
    data=load_index()
    if data is None:raise ValueError('Local index unavailable')
    invalid=[];mismatches=[];canonical=[]
    with closing(sqlite3.connect(f"file:{data['database']}?mode=ro",uri=True)) as db:
        rows=db.execute('SELECT id,street,building,district FROM addresses').fetchall()
        for identifier,street,building,district in rows:
            parsed=parse_query(f'{street} {building}, {district}')
            if parsed is None:
                invalid.append(identifier);continue
            expected=(street_key(street),building_key(building),district_key(district))
            actual=(street_key(parsed['street']),parsed['building'],district_key(parsed['district'] or ''))
            if expected!=actual:mismatches.append(identifier)
            canonical.append((identifier,expected))
        ambiguous={}
        for kind in ['unicode','folded']:
            groups=db.execute('WITH coordinates AS (SELECT DISTINCT l.street_key,l.building_key,l.district_key,a.latitude,a.longitude '
                              'FROM lookup l JOIN addresses a ON a.id=l.id WHERE l.kind=?) '
                              'SELECT street_key,building_key,district_key FROM coordinates '
                              'GROUP BY street_key,building_key,district_key HAVING COUNT(*)>1',(kind,)).fetchall()
            ambiguous[kind]=set(groups)
    unresolved=[identifier for identifier,key in canonical if key in ambiguous['unicode']]
    return {'record_count':len(rows),'canonical_queries_unparseable':len(invalid),'canonical_round_trip_mismatches':len(mismatches),
            'ambiguous_district_qualified_canonical_records':len(unresolved),
            'ambiguous_district_qualified_unicode_alias_keys':len(ambiguous['unicode']),
            'ambiguous_district_qualified_folded_alias_keys':len(ambiguous['folded']),
            'unparseable_ids':invalid,'round_trip_mismatch_ids':mismatches,'ambiguous_canonical_ids':unresolved,
            'scope':'Canonical source-address audit only; not universal free-text resolution or current address completeness'}


def main():
    import argparse
    from data_science.ingestion_io import atomic_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',action='store_true',required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        report=audit_index()
        if args.output:atomic_json(args.output,report)
        print(json.dumps(report,ensure_ascii=False))
    except (OSError,ValueError,sqlite3.Error):parser.exit(1,'Address-index audit unavailable.\n')


if __name__=='__main__':main()
