"""Resumable complete-platform queue. Multi-batch live runs require verified usage limits.

Dry runs never require a key/policy, make requests or write files. This module is
never imported by normal scoring. The source cache itself is the restart cursor.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import httpx

from data_science.data_loader import load_stops
from data_science.stop_lines import read_cache, CACHE_PATH, SOURCE_URL
from data_science.ingest_stop_lines import LineClient, ingest
from data_science.ingestion_io import atomic_json


def error_kind(code):
    if code in ('HTTP_401','HTTP_403'):return 'authentication_or_permission'
    if code=='HTTP_429':return 'rate_limited'
    if code.startswith('HTTP_4') and code!='HTTP_408':return 'permanent_error'
    return 'transient_error'


def queue(available, records, *, retry_errors=False, stale_hours=None, attempted=()):
    attempted = set(attempted)
    missing, refresh = [], []
    now=datetime.now(timezone.utc)
    for key in sorted(set(available)):
        if key in attempted:continue
        row=records.get(key)
        if row is None:
            missing.append(key)
        elif row['status']=='error' and retry_errors and error_kind(row['error_code'])=='transient_error':
            refresh.append(key)
        elif row['status']=='success' and stale_hours is not None:
            if (now-datetime.fromisoformat(row['retrieved_at'])).total_seconds()>=stale_hours*3600:
                refresh.append(key)
    return missing+refresh


def coverage(available, records):
    kinds=Counter()
    for key in set(available):
        row=records.get(key)
        if row is None:kinds['missing']+=1
        elif row['status']=='success':
            kinds['known_empty' if not row['lines'] else 'known_with_lines']+=1
            if row['error_code']:kinds['failed_refresh']+=1
        else:kinds[error_kind(row['error_code'])]+=1
    return {'eligible_platforms':len(set(available)), 'attempted_platforms':sum(k in records for k in set(available)),
            'states':dict(kinds)}


def verified_policy(path):
    if Path(path).stat().st_size>100_000:raise ValueError('Policy artifact too large')
    policy=json.loads(Path(path).read_text())
    url=policy['official_policy_url']
    if not isinstance(url,str) or not url.startswith('https://dane.um.warszawa.pl/'):
        raise ValueError('Official usage-policy provenance required')
    verified=datetime.fromisoformat(policy['verified_at'])
    if verified.tzinfo is None or not 0 <= (datetime.now(timezone.utc)-verified).total_seconds()<=30*86400:
        raise ValueError('Usage-policy verification must be current and timezone-aware')
    interval=policy['minimum_interval_seconds'];budget=policy['max_requests_per_run']
    if type(interval) not in (float,int) or not math.isfinite(interval) or interval<1.1:
        raise ValueError('Conservative verified rate limit required')
    if type(budget) is not int or not 1<=budget<=20_000:
        raise ValueError('Verified finite request budget required')
    return policy


def run_batches(available, output, fetch, *, batch_size=20, max_batches=1, retry_errors=False,
                stale_hours=None, progress_path=None):
    if not 1<=batch_size<=20 or not 1<=max_batches<=1000:
        raise ValueError('Invalid batch bound')
    attempted=set();summaries=[]
    for _ in range(max_batches):
        cache=read_cache(output)
        if cache.status=='error':raise ValueError('Corrupt cache; preserve it')
        pending=queue(available,cache.records,retry_errors=retry_errors,stale_hours=stale_hours,attempted=attempted)
        selected=pending[:batch_size]
        if not selected:break
        summary=ingest(selected,output,fetch,refresh=stale_hours is not None)
        summaries.append(summary);attempted.update(selected)
        cache=read_cache(output)
        progress={**coverage(available,cache.records),'source_url':SOURCE_URL,
                  'processed_at':datetime.now(timezone.utc).isoformat(),'batches':summaries,
                  'eligible_keys_sha256':hashlib.sha256(json.dumps(sorted(set(available))).encode()).hexdigest()}
        if progress_path:atomic_json(progress_path,progress)
        recent=[cache.records[k] for k in selected if k in cache.records]
        if summary.get('budget_exhausted') or any(r['error_code'] in ('HTTP_401','HTTP_403','HTTP_429') for r in recent):break
    return {**coverage(available,read_cache(output).records),'batches':summaries}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=CACHE_PATH)
    parser.add_argument('--batch-size',type=int,default=20)
    parser.add_argument('--max-batches',type=int,default=1)
    parser.add_argument('--max-requests',type=int,default=60,help='Hard HTTP request budget including retries')
    parser.add_argument('--retry-errors',action='store_true',help='Retry transient failures after never-attempted platforms')
    parser.add_argument('--refresh-stale-hours',type=float)
    parser.add_argument('--policy-file',type=Path,help='Operator-verified official limits; mandatory for multi-batch live runs')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    if (not 1<=args.batch_size<=20 or not 1<=args.max_batches<=1000 or not 1<=args.max_requests<=20_000
            or args.refresh_stale_hours is not None and (not math.isfinite(args.refresh_stale_hours) or args.refresh_stale_hours<=0)):
        parser.error('Invalid finite ingestion bounds')
    stops=load_stops();available=list(zip(stops.stop_id,stops.platform));cache=read_cache(args.output)
    if cache.status=='error':parser.error('Corrupt cache; choose another output or repair offline')
    pending=queue(available,cache.records,retry_errors=args.retry_errors,stale_hours=args.refresh_stale_hours)
    if args.dry_run:
        print(json.dumps({'dry_run':True,**coverage(available,cache.records),'pending':len(pending),
                          'selected_platform_limit':min(len(pending),args.batch_size*args.max_batches),
                          'next_batch':[':'.join(k) for k in pending[:args.batch_size]]}))
        return 0
    interval,budget=1.1,args.max_requests
    if args.max_batches>1 or args.policy_file:
        if not args.policy_file:parser.error('Verified provider usage policy is required for multi-batch live ingestion')
        try:
            policy=verified_policy(args.policy_file)
            interval=policy['minimum_interval_seconds'];budget=min(budget,policy['max_requests_per_run'])
        except (OSError,ValueError,KeyError,TypeError):parser.error('Usage policy missing, stale or invalid; no requests made')
    token=os.getenv('WARSAW_API_TOKEN','').strip()
    if pending and not token:parser.error('Set backend WARSAW_API_TOKEN; no requests made')
    with httpx.Client(follow_redirects=False,trust_env=False) as http:
        client=LineClient(http,token,interval=interval,max_requests=budget)
        report=run_batches(available,args.output,client.fetch,batch_size=args.batch_size,max_batches=args.max_batches,
                           retry_errors=args.retry_errors,stale_hours=args.refresh_stale_hours,
                           progress_path=args.output.with_suffix('.progress.json'))
        report['http_requests']=client.requests
    print(json.dumps(report))
    return 0


if __name__=='__main__':raise SystemExit(main())
