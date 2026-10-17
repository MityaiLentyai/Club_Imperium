"""Download one dated Geofabrik Mazowieckie extract with bounded verification."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

import httpx

from data_science.ingestion_io import atomic_json

MAX_BYTES = 500_000_000


def hashes(path):
    md5, sha256, count = hashlib.md5(), hashlib.sha256(), 0
    with Path(path).open('rb') as f:
        while chunk := f.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_BYTES:
                raise ValueError('Extract exceeds 500 MB limit')
            md5.update(chunk); sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest(), count


def download(url, output):
    if not re.fullmatch(r'https://download\.geofabrik\.de/europe/poland/mazowieckie-\d{6}\.osm\.pbf', url):
        raise ValueError('Use an immutable dated official Mazowieckie PBF URL')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    target = output / url.rsplit('/', 1)[1]
    manifest = target.with_suffix('.pbf.json')
    temporary = None
    try:
        with httpx.Client(timeout=httpx.Timeout(60, read=120), follow_redirects=False) as client:
            check = client.get(url + '.md5'); check.raise_for_status()
            expected = check.text.split()[0]
            if not re.fullmatch('[0-9a-f]{32}', expected):
                raise ValueError('Invalid provider MD5')
            if target.exists():
                md5, sha256, count = hashes(target)
                if md5 != expected:
                    raise ValueError('Existing cached extract checksum mismatch; file preserved')
                if manifest.exists():
                    metadata = json.loads(manifest.read_text())
                    if metadata['sha256'] != sha256 or metadata['source_url'] != url:
                        raise ValueError('Cached manifest mismatch; files preserved')
                    return target, manifest
                raise ValueError('Cached extract lacks freshness metadata; file preserved')
            deadline = time.monotonic() + 300
            with client.stream('GET', url) as response:
                response.raise_for_status()
                count = 0
                with tempfile.NamedTemporaryFile(dir=output, suffix='.part', delete=False) as stream:
                    temporary = Path(stream.name)
                    for chunk in response.iter_bytes(1024 * 1024):
                        count += len(chunk)
                        if count > MAX_BYTES or time.monotonic() > deadline:
                            raise ValueError('Extract byte/time budget exceeded')
                        stream.write(chunk)
                    stream.flush(); os.fsync(stream.fileno())
                md5, sha256, count = hashes(temporary)
                if md5 != expected:
                    raise ValueError('Provider MD5 mismatch')
                metadata = {'source_url': url, 'catalogue_url': 'https://download.geofabrik.de/europe/poland/mazowieckie.html',
                            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'bytes': count,
                            'md5': md5, 'sha256': sha256, 'http_last_modified': response.headers.get('last-modified')}
                os.replace(temporary, target); temporary = None
                atomic_json(manifest, metadata)
                return target, manifest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, default=Path('.local/osm-source'))
    args = parser.parse_args()
    try:
        target, manifest = download(args.url, args.output)
        print(json.dumps({'extract': str(target), 'source_manifest': str(manifest)}))
    except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
        parser.exit(1, f'Download failed; previous cache preserved: {exc}\n')


if __name__ == '__main__':
    main()
