# Backend coverage and verification follow-up

This iteration changes Python backend, Data Science, datasets and documentation only. `frontend/` remains identical to `origin/main`, the original Mobility Score formula is unchanged, and production configuration is untouched.

## Data assessment and actual coverage

| Dataset | Actual result | Score decision |
| --- | --- | --- |
| Stop platforms | Existing 6,652-platform snapshot | Original Mobility Score retained |
| Observed lines | Still 15 successful cached platforms; a specific 20-platform expansion is prepared but not executed | Observed lines do not establish frequency or a schedule |
| Parks | One bounded WFS refresh returned the same 430 named spaces and 60 qualifying Park objects, with unchanged source-ID membership | No Green Score: completeness is not verified |
| Parking | Existing 18 valid facilities; official catalogue scope reconfirmed without authentication | No Parking Score or current availability claim |
| Sports | Expanded from 7 to 16 located sites, in Mokotów, Praga-Północ, Ursynów, Wola, Śródmieście and Żoliborz | No Sports Score: only 16/308 educational source-site addresses, about 5.2%, are located |

Sports source still contains 1,227 records grouped into 308 distinct addresses. The ten-address enrichment batch used source-site indices `7,135,137,83,85,160,161,216,217,14` in that exact source hash. Nine were added; `Aleja Wojska Polskiego 1A` remains unresolved. No public or commercial bulk geocoding was used: queries used exact street/avenue, building number and district equality in the official municipal WFS, with at most five matches per query. Address points are proxies for sites, not mapped courts or entrances. No source-address/district conflicts were found in this saved source.

The municipal [ZZW park inventory](https://zzw.waw.pl/nasze-tereny/parki/) names Park Żerański, whose name is absent from the current named-park snapshot. This is evidence against assuming completeness, not a license to invent a polygon or assert a spatial omission without further validation. Park-area distance does not measure greenery, entrance access or walking routes. The [parking catalogue](https://dane.um.warszawa.pl/en/catalogue/20ec668b-e5f3-4cbf-aeeb-eb825f3c8731) explicitly covers participating Public Areas Authority, Municipal Roads Authority and Palace of Culture and Science facilities. It does not establish all parking in Warsaw.

Machine-readable evidence and actual results are in `data/verification/`. The original sports source archive and earlier address responses remain preserved. No automated citywide enrichment, deletion of existing cache records or fabricated facility was introduced.

## Credential-operation status

The existing backend token is available, but automatic approval review rejected its use for the new line-expansion batch without separate confirmation of that exact credential-dependent action. The requested approval covers up to 20 line requests and one parking refresh. Until approved, neither operation is executed; no authentication failure or token validity is inferred from that policy rejection.

`data/verification/line-selection.json` is a **plan**, not observations: it selects the nearest previously uncached platforms around three independently verified municipal address points, with quotas 7/7/6 and a 1,500 m bound. The committed line CSV remains the existing 15-platform observations. Parking membership/availability is not represented as freshly authenticated data; only its public catalogue scope was checked in this iteration.

Preview without token, network or cache writes:

```bash
python -m data_science.ingest_stop_lines --selection-file data/verification/line-selection.json --limit 20 --max-attempts 1 --dry-run
```

After the credential-dependent action is authorized and the existing token supplied through the operator's environment:

```bash
python -m data_science.ingest_stop_lines --selection-file data/verification/line-selection.json --limit 20 --max-attempts 1
python -m data_science.ingest_infrastructure parking
```

Selection files are capped at 100 KB and 20 platforms. Identifiers must remain strings and match the existing stop snapshot. Platform responses are streamed with a 256 KB limit; no token, header or raw error body is logged. Successes are cached; failed refreshes preserve earlier observations and original retrieval dates. Never automate offset/selection batches into a citywide download.

## Reproduce sports expansion without network

With the committed source, address caches and snapshot in place:

```bash
python -m data_science.ingest_sports --input data/infrastructure/raw/sports-965750657b6f133f.json --limit 10 --site-index 7 --site-index 135 --site-index 137 --site-index 83 --site-index 85 --site-index 160 --site-index 161 --site-index 216 --site-index 217 --site-index 14 --offline
```

Use the same command with `--dry-run` for a selection-only preview; omit `--offline` only for an explicitly authorized bounded public address refresh. Existing cached matches, including negative matches, are reused. There is no implicit refresh of an existing address response. To revalidate coordinates, use a new output/cache directory and preserve the old one.

Each run selects at most ten sites, then merges them with earlier located sites from the same source hash. A new sports source hash is rejected for in-place merge; use a new output directory rather than silently relabeling old observations as newly retrieved data. Sports `retrieved_at` remains the original source snapshot time; `processed_at` changes when normalization/enrichment runs. Each new municipal response has a checksum and retrieval sidecar. Nine current located sites have explicit coordinate retrieval times; the seven legacy located-site times remain unknown. School source-update dates and retrieval times describe different facts and are reported separately.

## Offline status and frontend API contract

`GET /api/data/status` performs no external calls and returns:

- `datasets.transport`: availability, usable platform count and an explicitly unknown original retrieval time for the legacy CSV.
- `datasets.lines`: matched successful platform count, denominator/fraction, distinct observed line count, oldest/latest known retrieval timestamps and scope limitation.
- `datasets.green`, `.parking`, `.sports`: source metadata, retrieval/processing dates, usable/rejected counts and available coverage evidence.
- Sports additionally exposes `located_fraction_of_source_sites`, districts, coordinate-timestamp count/range, unresolved count and the source's update-date range. These are fractions of the educational source, not all Warsaw sports infrastructure.
- `score_eligibility`: eligible flag and evidence-based reason per category. Only Mobility is currently eligible. The same policy is returned with scoring results and used to explain LifeScore exclusions.
- `external_requests:false` and a freshness interpretation note. Missing evidence stays null rather than zero.

No Green or Sports Score was introduced because the assessment does not justify one. LifeScore remains the documented normalized weighted mean over eligible numeric scores; it is explicitly partial while Mobility alone qualifies. Desired weights cannot turn missing evidence into a score.

Optional snapshots now reload when their file timestamp/size changes; no restart is needed after atomically replacing a park/parking/sports snapshot. Valid geometries survive partial file corruption, with rejected-record counts exposed. Missing/corrupt optional categories remain independently unavailable. Missing or invalid mandatory transport data returns a sanitized HTTP 503 from scoring; `/api/data/status` still reports its absence, while `/api/health` retains process-liveness semantics.

Geospatial work from asynchronous address/comparison endpoints runs in the thread pool rather than blocking the event loop. Routing limits waiting for its shared queue to two seconds and returns a baseline plus unavailable profiles when busy. Both numeric and HTTP-date Retry-After cooldowns are respected. Misconfigured routing URLs, including embedded credentials/query strings, are rejected without disclosing them.

## Real-world route and API checks

Municipal WFS verified these exact address points:

| Address | Latitude | Longitude | Municipal ID |
| --- | --- | --- | --- |
| Marszałkowska 83 | 52.225763 | 21.013683 | 1323047 |
| Stokłosy 7 | 52.158969 | 21.031856 | 1348303 |
| Ząbkowska 12 | 52.253043 | 21.039900 | 1312064 |

Three separate address requests through `/api/score/address` returned HTTP 200. Returned geocoding coordinates are retained in `api-checks.json`; they need not be identical to the municipal points and are not silently substituted. Six public routing requests used the municipal points above, with the existing limiter and size/time bounds:

| Direction | Walking route | Walking estimate | Driving route | Driving estimate |
| --- | --- | --- | --- | --- |
| Marszałkowska 83 → Stokłosy 7 | 8,333.7 m | 110.5 min | 8,112.4 m | 15.1 min |
| Stokłosy 7 → Ząbkowska 12 | 12,465 m | 165.1 min | 13,638.7 m | 19.4 min |
| Ząbkowska 12 → Marszałkowska 83 | 4,551.4 m | 60.1 min | 5,531 m | 9.0 min |

All six route profiles were available; repeating the first pair used the in-memory cache for both modes. These are network routes with provider estimates, not actual elapsed journeys, live traffic, entrance/accessibility verification or transit durations. GeoJSON, source timestamps, snapped-endpoint offsets and checked results are retained in `commute-checks.json`.

Thirty local warm-process `/api/score` requests returned HTTP 200; the saved measurement was median 15.71 ms, p95 30.69 ms, maximum 58.12 ms. This is a hardware-specific TestClient observation, not a production SLA. `/api/data/status` and `/api/compare` with a destination baseline also returned 200 without external requests. Exact performance/check timestamps are in `api-checks.json`.

## Public transport journey blocker

The [official ZTM timetable download page](https://www.ztm.waw.pl/pliki-do-pobrania/dane-rozkladowe/) returned HTTP 403/a JavaScript anti-bot challenge during this bounded check. It was not bypassed. This application has neither a current validated full timetable graph nor a configured schedule-aware itinerary provider. The stop-line endpoint answers which lines were observed at a platform; it does not provide a complete trip/calendar/transfer graph.

Reliable transit implementation would require a validated current feed or trusted journey API, stable mappings for source stop/platform/line IDs, service-day/calendar and Europe/Warsaw departure-time handling, and walking-transfer access. The [GTFS Schedule specification](https://gtfs.org/documentation/schedule/reference/) documents the relevant stops/routes/trips/stop_times/calendars and transfer structures. Community conversions are not automatically treated as verified official feeds. No full-network download, large routing-engine installation or schedule-to-GTFS conversion was attempted under a bounded verification task.

Therefore `transit.status` stays `unavailable`: no fictional total time, walking segment, waiting time, transfer count, transport line itinerary or departure time is returned. This is a current integration/data-validation blocker, not a claim that transit routing is impossible in Warsaw.

## Tests and verification commands

```bash
python -m pytest -q
git diff --exit-code origin/main -- frontend
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Inspect `/docs`, `/api/data/status`, the existing score/address endpoints, `/api/commute` and `/api/compare`. Automated tests use saved fixtures and mocked HTTP; they never call live external APIs. New regressions cover sports selection/merge/freshness, partial corruption, snapshot reload, coverage/eligibility, missing transport, streamed response caps, queue overload, Retry-After dates and invalid routing configuration. Existing Mobility Score and API compatibility checks remain in the full suite. Final result for this iteration: 206 Python tests passed, with one existing FastAPI/Starlette test-client deprecation warning.
