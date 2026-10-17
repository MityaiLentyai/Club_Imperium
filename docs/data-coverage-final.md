# Complete available-source coverage and backend stabilization

> Address lookup and boundary validation have subsequently changed. See [citywide address handling](citywide-addresses.md) for the current contract and limitations. Older rectangular-boundary and external-only geocoding statements below describe the preceding version.

Base: `origin/main` at `7de3ef9` (PRs #8 and #9 merged). Python backend, Data Science, data evidence, tests and documentation only. No frontend, scoring formula, dependency or deployment-setting changes. No deployment or merge performed.

## Actual coverage

| Source | Available source records | Processed | Valid/served | Unresolved or excluded |
| --- | ---: | ---: | --- | --- |
| Existing `stops_clean.csv` | 6,652 platform records | 6,652 | 6,652 transport platforms | No new stop ingestion |
| Observed line cache | 6,652 eligible platform keys | 15 observed keys | 15 successful platforms / 3 stop groups / 33 distinct observed line identifiers | 6,637 keys not requested; bulk limits unverified |
| Otwarte boiska | 1,227 rows / 308 distinct site addresses | All rows and all 308 addresses | 293 located addresses (95.1%), consolidated into **291 unique coordinate points**, across all 18 districts | 15 unmatched addresses; 25 duplicate source rows and two co-located address duplicates reconciled; zero rejected source rows |
| `PLACE_SKWERY` | 430 named-space records | 430 | 60 validated named park objects | 172 square candidates require separate vegetation evidence; 198 other named spaces excluded |
| Listed parking API | 19 facility rows | 19 | 18 valid listed facilities | One row has invalid coordinates; no artificial replacement |
| Historic municipal P+R WFS | 14 facility points | 14 | 14 geometry-validated historic records, **not included** in live facility counts | All have source update text `kwiecień 2015`; current operation not independently verified; four possible overlaps with the listed facilities |

“Complete” refers to processing the available records in the selected saved source, not complete geographic or current-service coverage of Warsaw. The existing line sample was not silently enlarged with synthetic values. The normalized sports inventory covers educational sites, not all public, private or commercial sports facilities. A municipal address point is a proxy for the site, not a mapped field, building entrance or walking access point.

## Sources, provenance and limitations

- Sports: [Otwarte boiska catalogue](https://dane.um.warszawa.pl/en/catalogue/32a0ad2d-06d7-4e9c-acef-17a35c083d8c), endpoint `get_be_otwarte_boiska`. The existing complete 1,227-row archive was reused without another authenticated sports fetch. Its original retrieval time and SHA-256 were preserved. Processing time is separate from source retrieval time. Source schedules/update text are retained as supplied and can be old; no current opening/access guarantee.
- Address joins: official [municipal WFS](https://wfs.um.warszawa.pl/serwis), `wfs:PUNKTY_ADRESOWE_WGS84`. Exact street name, building number and district predicates. Source prefixes, explicit postal suffixes and district annotations are normalized; abbreviations are not guessed or fuzzily expanded. The source contains the district annotation spelling `(Białołeka)`, which is removed from the street field while retaining the separate authoritative source district. Ambiguous or missing matches never get invented coordinates.
- GetFeature form POST was verified. An XML-only POST returned a missing-service exception; the pipeline uses supported KVP form POST. An internal provider error in one larger query was isolated using smaller cached batches; all 308 addresses were eventually attempted. Prior positive/negative evidence is reused when changing batch size. Cache files retain request parameters, content hash and observation time; seven legacy coordinates have no invented observation timestamp. Checkpoints distinguish unmatched, ambiguous, pending and failed batches.
- Parks: `ns92528565:PLACE_SKWERY`, source geometries EPSG:2178, normalized EPSG:4326, distance calculations EPSG:2180. All 430 returned rows are below the explicit 500-row cap. The service ignored `resultType=hits` and returned the full collection again, so no separate total was inferred from that request. `OBIEKT=Park` objects with valid polygons are retained, with duplicate IDs merged. `Skwer`/`Skwerek` labels alone do not prove a whole polygon is green: all 172 are reported separately, not automatically scored or rendered as parks. Roundabouts, other squares and unrelated named spaces remain excluded.
- The official [ZZW inventory](https://zzw.waw.pl/nasze-tereny/parki/) names [Park Żerański](https://zzw.waw.pl/nasze-tereny/parki/park-zeranski/), whose name is absent from this snapshot. This is evidence against assuming inventory completeness, not proof of a geometric omission without checking aliases/boundaries. No polygon was inferred.
- Parking: [listed-facility catalogue](https://dane.um.warszawa.pl/en/catalogue/20ec668b-e5f3-4cbf-aeeb-eb825f3c8731), `get_m_parkingi_wolne_miejsca`. One explicitly authorized refresh returned the same 18 valid IDs from 19 rows. Opening hours, capacity and tariff details are preserved where supplied. Provider response timestamp is retained separately; it is not evidence that each free-space value was observed then. Current availability is not published.
- Additional P+R: the WFS advertises `wfs:PARKINGI_PARK_AND_RIDE`. All 14 returned points were validated and retained in raw evidence and a quality report. The official [WTP parking directory](https://www.wtp.waw.pl/parkingi/) was unavailable during the check. Mixing the 2015 layer into current facility counts without reconciling operation and overlaps would be misleading; it remains an audited historical source. [ZDM parking information](https://zdm.waw.pl/sprawy/parkowanie/) distinguishes parking facilities from street parking zones. Neither zones, meters nor individual street spaces were manufactured as facilities.
- Lines: [official catalogue](https://dane.um.warszawa.pl/en/catalogue/8eb065b6-f3a0-41d4-a842-732c6c1c3063), `get_ztm_lista_linii_na_przystanku`. The [official terms](https://dane.um.warszawa.pl/en/terms-of-use), [key page](https://dane.um.warszawa.pl/en/key-api) and catalogue were inspected. No numeric permitted request rate/quota for a 6,652-platform download was established. This is a verification blocker, not a statement that bulk use is prohibited. No authenticated line requests were made in this branch.

Machine-readable evidence is under `data/infrastructure/`: `sports-processing-report.json`, `green-processing-report.json`, `parking-processing-report.json`, `parkride-processing-report.json`. Reports reconcile every source/site row, status and rejection. `raw/` retains original source payloads; `sports_batches/` retains original municipal responses with checksum/time sidecars; `normalized_history/` preserves previous validated snapshots. No existing raw archive or teammate cache/report was removed. Repeated identical offline runs do not need new history copies. Unknown source dates remain null rather than becoming a new retrieval claim.

## Reproduce and resume

From the repository root using its Python environment:

```bash
# Full sports reproduction: zero network requests, preserves original source time.
python -m data_science.complete_sports --input data/infrastructure/raw/sports-965750657b6f133f.json --offline --batch-size 50
# Recompute every selected infrastructure audit from the saved complete payloads.
python -m data_science.audit_infrastructure
# Inspect the complete transport backlog: no token, writes or network.
python -m data_science.complete_lines --max-batches 400 --max-requests 20000 --dry-run
```

For an authorized sports refresh using the saved source and official address points, omit `--offline`. Batches contain at most 50 sites, responses are capped at 8 MB / 499 returned candidates, calls are sequential with 1.1-second spacing. On a provider query exception, reduce `--batch-size` (for example 25, 5 or 1): verified checkpoint evidence is reused instead of refetching the entire source. Network/transport failures stop further requests. Re-run until pending/failed counts are resolved; unresolved exact-address matches may legitimately remain. A partial run cannot remove a previously validated point, and a bounded legacy sample cannot replace a fuller snapshot. Restart backend workers after replacing optional snapshots because their existing caches are per-process.

The full line queue uses the existing CSV as its persistent cursor, preserving string identifiers and leading zeroes. Never-attempted keys come first. Successful empty lists are known-empty service; missing keys, retryable failures, permanent HTTP errors, authentication failures and rate limits are reported separately. Retryable requests have bounded backoff; successful refresh failures retain the last observation/time. Every attempted platform is saved atomically; progress includes eligible/attempted counts and state totals. Normal scoring does not call the transport API.

After the operator has independently verified the provider's allowed usage, a current policy file outside Git must contain:

```text
official_policy_url: official dane.um.warszawa.pl page establishing the usage terms
verified_at: actual timezone-aware verification timestamp (no older than 30 days)
minimum_interval_seconds: numeric verified spacing, at least 1.1 seconds
max_requests_per_run: numeric explicitly permitted total, including retries
```

Supply those keys as JSON. Do not fabricate an approved policy or treat the existing 1.1-second application limiter as proof of provider permission. The tool validates policy provenance/date/bounds but cannot independently certify the operator's evidence. Multi-batch live mode refuses to start without it. With verified terms, backend `WARSAW_API_TOKEN` and an explicitly permitted request budget:

```bash
python -m data_science.complete_lines --max-batches 400 --max-requests PERMITTED_TOTAL --policy-file PATH_TO_VERIFIED_POLICY
```

The runner is serial; each batch is at most 20 platforms. Total HTTP requests, including retries, have a hard cap. Restart skips saved observations; `--retry-errors` explicitly retries transient failures after missing keys. `--refresh-stale-hours HOURS` explicitly selects old successful observations for refresh. Authentication/rate-limit errors stop the run. Retry budget exhaustion never creates a false observation for an unrequested key. The same machinery was tested offline across more than one batch; do not launch an unverified bulk download.

## Existing API and exact examples

The six existing endpoints remain:

| Method/path | Request | Response behavior |
| --- | --- | --- |
| `GET /api/health` | None | `{"status":"ok"}`; liveness only |
| `GET /api/geocode` | `?address=Marszałkowska%2083` | One `{address,latitude,longitude}` object, not a list |
| `POST /api/score` | `{"latitude":52.2297,"longitude":21.0122,"radius_m":1}` | Existing score/features/places/datasets/LifeScore structure |
| `POST /api/score/address` | `{"address":"Marszałkowska 83","radius_m":1}` | Same structure, resolved `location.address` |
| `POST /api/commute` | `{"origin":{"latitude":52.2297,"longitude":21.0122},"destination":{"latitude":52.239,"longitude":21.022}}` | Baseline plus separate walking/driving/transit statuses; GeoJSON uses `[lon,lat]` |
| `POST /api/compare` | `{"locations":[{"latitude":52.2297,"longitude":21.0122},{"latitude":52.158969,"longitude":21.031856}],"weights":{"mobility":10,"sports":90}}` | Two existing score objects, measured comparison rows and warnings |

[Exact complete request/response examples](examples/backend-http.json) were captured from a real local Uvicorn process, including all six endpoints and a malformed numeric-input HTTP 422 example. Their timestamps/measurements are dated observations, not constants for future clients. Existing request schemas remain in `/openapi.json` and `/docs`. Successful responses still have no detailed response-model schema in OpenAPI; the exact examples and regression tests document payloads. No response fields were removed or renamed. `/api/data/status` is absent (404); no demonstrated integration blocker required adding it.

Coordinate service envelope: latitude 52.0–52.4, longitude 20.75–21.3; not an exact municipal boundary polygon. Radius: integer 1–2,000 m, default 1,000. Weights are finite 0–100 values; comparison weights are shared at top level. Missing optional data gives null counts/distances and category unavailable, not zero. Missing/empty/corrupt mandatory transport returns sanitized HTTP 503. Invalid requests give HTTP 422; application `detail` may be a string and validation `detail` a list. Geocoding can return 404/502/503/504. Route provider failures retain HTTP 200 with the baseline and per-profile unavailable statuses; clients must inspect profiles.

Mobility formula unchanged: `round(0.6 * max(0, 100 * (1 - nearest_stop_m / 800)) + 0.4 * min(100, 100 * stop_groups_500m / 8), 1)`. Marker radius does not change this formula. LifeScore uses a normalized weighted mean over eligible available scores only; Mobility remains the only eligible numeric category, so its value is explicitly partial, or null when its requested weight is zero. Educational source completeness does not justify a citywide Sports Score. No Green, Parking, Sports, Commute score or transit routing was added.

Comparisons reject per-home weights/ambiguous location inputs; optional radius counts with differing radii are incomparable. Route comparison requires `include_routes:true` and a destination. The default does not contact a routing provider. Public route estimates have no live traffic, transit remains unavailable, provider caches are bounded and the queue has a two-second wait bound. Plan client timeouts for up to two ten-second profile requests per commute (four for a two-home route comparison). The current frontend still calls `/analyze`; frontend integration needs existing `/api/score` and separate `/api/commute` handling. Its current category union does not include sports. Frontend files were not changed.

## Verification and startup

All Python tests pass: **243 passed**, one existing Starlette/httpx deprecation warning. Offline tests cover full-source batching/resume/resize, deduplication, exact coordinates and ambiguity, partial provider failures, cache/checkpoint integrity, state reconciliation, request-budget enforcement, missing data, response consistency, LifeScore and comparison. Added endpoint regressions verify non-finite validation error serialization, invalid routing configuration and HTTP-date rate-limit cooldowns. Simulated upstream failures include timeout, HTTP errors, malformed payloads, excessive snapping and unavailable routes; no live provider was deliberately overloaded.

Local Uvicorn on Python 3.11.8 verified all six endpoints and `/openapi.json`. Geocoding and address scoring returned 200 for Marszałkowska 83, Stokłosy 7 and Ząbkowska 12. Address LifeScores were 92.2, 72.2 and 88.0 (partial). Coordinate scores were also verified in Śródmieście, Ursynów, Praga-Północ, Wola, Bielany and Bemowo. All infrastructure snapshots loaded. CORS preflight allowed `http://localhost:5173` and rejected a different origin. All six walking/driving routes using the actual geocoded address points were available; repeat profiles used cache:

| Journey | Walking | Driving |
| --- | --- | --- |
| Marszałkowska 83 → Stokłosy 7 | 8,251.6 m / 109.4 min | 8,112.4 m / 15.1 min |
| Stokłosy 7 → Ząbkowska 12 | 12,382.5 m / 164.0 min | 13,638.7 m / 19.4 min |
| Ząbkowska 12 → Marszałkowska 83 | 4,551.1 m / 60.1 min | 5,531 m / 9.0 min |

Forty warm local HTTP score calls with all 291 sports points: median **20.18 ms**, p95 **21.60 ms**, maximum **23.58 ms**. First cold score was 83.30 ms. A separate in-memory-only simulation of line observations for all 6,652 platforms retained Mobility 92.7: 25 direct scoring calls, median 17.63 ms / p95 20.39 ms. These synthetic `TEST-ONLY` lines were never persisted or claimed as real coverage. No optimization was needed for the measured dataset size; local measurements are not a production SLA.

`pip check` found no broken requirements; all installed versions matched `configs/requirements.txt`. Existing Render YAML specifies root build `pip install -r configs/requirements.txt`, module `backend.main:app`, `$PORT`, one worker and health path `/api/health`. Local Uvicorn import/startup passed with the same application/one-worker arrangement. Render pins Python 3.11.11 while the checked local runtime is 3.11.8; this is a patch-version difference, not a verified Linux build. No production setting was edited or deployment attempted.

Required operator configuration: a real identifying `GEOCODING_USER_AGENT`; `CORS_ORIGINS` matching the frontend origin exactly, without a trailing slash. Uvicorn does not automatically load repository `.env` into the environment. `WARSAW_API_TOKEN` is needed only for authorized ingestion, never exposed in normal scores or used for public walking/driving routing. Keep the existing single-worker assumption for process-local provider rate limits/caches. A restart clears caches; saved snapshots remain the scoring input.

Local reproduction in a clean checkout:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r configs/requirements.txt
.venv/bin/python -m pytest -q
export GEOCODING_USER_AGENT='UrbanLens-Warsaw/1.0 (replace with your monitored contact URL or email)'
export CORS_ORIGINS='http://localhost:5173'
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
# In another terminal:
curl 'http://127.0.0.1:8000/api/health'
curl -X POST 'http://127.0.0.1:8000/api/score' -H 'Content-Type: application/json' -d '{"latitude":52.2297,"longitude":21.0122}'
```

Remaining blockers/limits: verified transport bulk quotas; 15 unresolved sports addresses and source schedule freshness; unverified green-space completeness/square vegetation; incomplete participating parking coverage and historical P+R currency; public provider availability and production capacity. The backend is ready for integration against its existing documented API with these explicit limitations. No readiness claim is based solely on `/api/health`.
