"""Bounded, sequential Warsaw stop-line ingestion. Run with --help."""
import argparse
import csv
import json
import math
import os
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from data_science.data_loader import load_stops
from data_science.stop_lines import CACHE_PATH, COLUMNS, SOURCE_URL, parse_lines, read_cache

API_URL = "https://dane.um.warszawa.pl/api/action/get_ztm_lista_linii_na_przystanku"


class IngestionError(Exception):
    """Safe error codes only: never include requests, headers or response bodies."""


class LineClient:
    def __init__(self, client, token, *, interval=1.1, retries=2, sleep=time.sleep, clock=time.monotonic):
        self.client, self.token = client, token
        self.interval, self.retries = interval, retries
        self.sleep, self.clock = sleep, clock
        self.last_request = None

    def fetch(self, stop_id, platform):
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                self.sleep(max(0, self.interval - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            retry_after = 0
            try:
                response = self.client.post(API_URL, json={"busstopId": stop_id, "busstopNr": platform},
                                            headers={"Authorization": self.token}, timeout=10.0)
                if response.status_code == 429 or response.status_code >= 500:
                    code = f"HTTP_{response.status_code}"
                    try:
                        retry_after = float(response.headers.get("Retry-After", "0"))
                    except ValueError:
                        try:
                            retry_after = (parsedate_to_datetime(response.headers["Retry-After"]) - datetime.now(timezone.utc)).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            raise IngestionError(code) from None
                    # Do not retry earlier than a long provider-requested wait.
                    # Leave this platform failed/resumable instead of blocking indefinitely.
                    if not math.isfinite(retry_after) or retry_after > 30:
                        raise IngestionError(code)
                elif response.is_error or response.is_redirect:
                    raise IngestionError(f"HTTP_{response.status_code}")
                else:
                    try:
                        return parse_lines(response.json())
                    except (ValueError, TypeError):
                        raise IngestionError("INVALID_RESPONSE") from None
            except httpx.TimeoutException:
                code = "TIMEOUT"
            except httpx.TransportError:
                code = "NETWORK_ERROR"
            if attempt == self.retries:
                raise IngestionError(code)
            self.sleep(max(min(2 ** attempt, 8), retry_after))


def save_cache(path, records):
    """Replace atomically after every platform so interrupted runs can resume."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as target:
            temporary = Path(target.name)
            writer = csv.DictWriter(target, fieldnames=COLUMNS)
            writer.writeheader()
            for key in sorted(records):
                row = dict(records[key])
                row["lines"] = json.dumps(row["lines"], ensure_ascii=False) if row["status"] == "success" else ""
                writer.writerow(row)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def ingest(platforms, path, fetch, *, refresh=False):
    platforms = list(dict.fromkeys(platforms))
    if not 1 <= len(platforms) <= 20:
        raise ValueError("Select between 1 and 20 platforms per invocation")
    cache = read_cache(path)
    if cache.status == "error":
        raise ValueError("Cache cannot be read; preserve it and choose a different --output path")
    records = cache.records
    summary = {"selected": len(platforms), "requested": 0, "skipped": 0, "succeeded": 0, "failed": 0}
    for key in platforms:
        previous = records.get(key)
        if previous and previous["status"] == "success" and not refresh:
            summary["skipped"] += 1
            continue
        now = datetime.now(timezone.utc).isoformat()
        summary["requested"] += 1
        try:
            lines = fetch(*key)
            retrieved = datetime.now(timezone.utc).isoformat()
            row = dict(zip(COLUMNS, [*key, lines, "success", retrieved, now, "", SOURCE_URL]))
            summary["succeeded"] += 1
        except IngestionError as exc:
            code = str(exc)
            # A failed refresh keeps the last successful observation and its time.
            row = dict(previous) if previous else dict(zip(COLUMNS, [*key, None, "error", "", now, code, SOURCE_URL]))
            row.update(attempted_at=now, error_code=code)
            summary["failed"] += 1
        records[key] = row
        save_cache(path, records)
        if row["error_code"] in {"HTTP_401", "HTTP_403", "HTTP_429"}:
            break
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=15, help="Maximum selected platforms (1–20; default 15)")
    parser.add_argument("--offset", type=int, default=0, help="Offset in stable stop_id/platform order")
    parser.add_argument("--platform", action="append", default=[], help="Select stop_id:platform explicitly; repeat up to --limit")
    parser.add_argument("--output", type=Path, default=CACHE_PATH)
    parser.add_argument("--refresh", action="store_true", help="Refetch selected successful records")
    parser.add_argument("--dry-run", action="store_true", help="Print selection without token, network or writes")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 20 or args.offset < 0:
        parser.error("--limit must be 1–20 and --offset must be nonnegative")
    stops = load_stops()
    available = sorted(set(zip(stops.stop_id, stops.platform)))
    if args.platform:
        selected = []
        for value in args.platform:
            parts = value.split(":")
            if len(parts) != 2 or tuple(parts) not in available:
                parser.error("--platform must match a stop_id:platform in stops_clean.csv")
            if tuple(parts) not in selected:
                selected.append(tuple(parts))
        if len(selected) > args.limit or args.offset:
            parser.error("Explicit platforms must fit --limit and cannot use --offset")
    else:
        selected = available[args.offset:args.offset + args.limit]
    if not selected:
        parser.error("No platforms selected")
    cache = read_cache(args.output)
    if cache.status == "error":
        parser.error("Cache cannot be read; preserve it and choose a different --output path")
    if args.dry_run:
        print(json.dumps({"dry_run": True, "selected": [":".join(k) for k in selected],
                          "would_request": sum(args.refresh or cache.records.get(k, {}).get("status") != "success" for k in selected)}))
        return 0
    pending = any(args.refresh or cache.records.get(k, {}).get("status") != "success" for k in selected)
    token = os.getenv("WARSAW_API_TOKEN", "").strip()
    if pending and not token:
        parser.error("Set WARSAW_API_TOKEN in the backend environment, or use --dry-run")
    with httpx.Client(follow_redirects=False, trust_env=False) as client:
        summary = ingest(selected, args.output, LineClient(client, token).fetch, refresh=args.refresh)
    print(json.dumps(summary))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
