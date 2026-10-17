# UrbanLens Warsaw — backend MVP

This branch integrates the backend/data portions of Parks + Parking from PR #7 and the existing Mobility 2.0 source/cache. It adds sports-site features, walking/driving routing, a partial personalized index, a two-location comparison API and offline `/api/data/status` coverage evidence. Frontend changes were explicitly reverted: `git diff origin/main -- frontend` is empty. The source branches and original uncommitted work were not modified. No new dependencies or production deployment configuration were introduced.

## Run locally

Use Python 3.11. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r configs/requirements.txt
export GEOCODING_USER_AGENT='UrbanLens-Warsaw/1.0 (https://github.com/MityaiLentyai/Club_Imperium)'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Open http://127.0.0.1:8000/docs to exercise the API. The React frontend is outside this branch's scope and remains unchanged from `origin/main`. Its new-category displays, routing, weight controls and comparison UI are not implemented by this branch; consumers must integrate the API contract below separately.

Backend CORS defaults to http://localhost:5173. Coordinate scoring needs neither credentials nor external access. `GEOCODING_USER_AGENT` identifies address requests to Nominatim; set your own real project/contact identification as appropriate. Environment files are not loaded automatically. Do not copy any backend secret into a `VITE_` variable.

## Actual source coverage

| Category | Shipped data | Interpretation |
| --- | --- | --- |
| Transport | 6,652 stop platforms in existing `stops_clean.csv` | Original Mobility Score is unchanged |
| Observed lines | 15 platforms at 3 stop groups; 33 distinct observed line identifiers | Existing Mobility 2.0 cache; small sample, not citywide service coverage |
| Parks | 60 `OBIEKT=Park` polygons from 430 named public spaces | Parks only; square greenery and completeness are unverified |
| Parking | 18 valid facilities from 19 source rows | Participating ZTP/ZDM/PKiN operators; one row lacked coordinates |
| Sports | 16 located sites across six districts; 1 unresolved selected address | Source has 1,227 records grouped into 308 distinct site addresses; only 16/308 source sites are located (about 5.2%); coverage remains limited |
| Routing | Actual network routes for walking/driving via FOSSGIS OSRM | Provider estimates; no live traffic or transit journey service |

Snapshot files include exact retrieval timestamps and source metadata. Stop IDs, platform IDs and line identifiers remain strings, preserving leading zeroes. Cached lines are observed availability, not a timetable, frequency or live service guarantee. Missing/failed line observations are distinct from known-empty observations.

Official infrastructure sources:

- [Warsaw WFS capabilities](https://wfs.um.warszawa.pl/serwis?service=WFS&request=GetCapabilities), park layer `ns92528565:PLACE_SKWERY`, native EPSG:2178. Geographic polygons are preserved as EPSG:4326; measurements use EPSG:2180. See [Parks + Parking](parks-parking.md).
- [Available parking spaces](https://dane.um.warszawa.pl/en/catalogue/20ec668b-e5f3-4cbf-aeeb-eb825f3c8731). The actual response uses `Status`, `Timestamp`, `carParks`. Current availability is not published because observation time is not established. Capacity, source tariff tables and opening information are retained where supplied.
- [Available lines at a stop](https://dane.um.warszawa.pl/en/catalogue/8eb065b6-f3a0-41d4-a842-732c6c1c3063). Existing bounded ingestion/cache is reused. See [Mobility 2.0](mobility-2.md).
- [Otwarte boiska / Open sports fields](https://dane.um.warszawa.pl/en/catalogue/32a0ad2d-06d7-4e9c-acef-17a35c083d8c), Biuro Edukacji, catalogue license Creative Commons Attribution. [Parameters](https://dane.um.warszawa.pl/files/be_otwarte_boiska_pa.json), [examples](https://dane.um.warszawa.pl/files/be_otwarte_boiska_pw.json). Actual response is a list of Polish-named fields: district, address, school name, facility type, equipment, surface, weekday opening information, notes and source update dates. It has no coordinates. One capped authenticated request retrieved the source; no bulk geocoding was performed.
- Sports coordinates use the official municipal `wfs:PUNKTY_ADRESOWE_WGS84` layer. Exact `NAZWA_PODST`, `NR_PORZADK` and `DZIELNICA` equality is required. The address point is a **proxy for a sports site**, not a court, campus entrance or walking access point. Ambiguous, unmatched, malformed or unsupported addresses stay unresolved and do not create markers. The current unmatched `Aleja Wojska Polskiego 1A` still has no unambiguous exact match and no invented location; street/avenue syntax alone does not establish a match. Counts describe sites, not individual courts.

Sports schedules retain each facility type's source hours, notes and update dates; some source dates are old. Clients should ask users to verify current access. The API does not claim that a site is currently open.

## Ingestion, preservation and refresh

Parks/parking commands remain unchanged:

```bash
python -m data_science.ingest_infrastructure green
# Requires backend-only WARSAW_API_TOKEN in the operator's environment:
python -m data_science.ingest_infrastructure parking
python -m data_science.ingest_stop_lines --limit 15 --dry-run
```

The existing line pipeline caps each explicit run at 20 platforms, caches/resumes successful observations, preserves failures and uses no network during scoring. No additional line requests were made for this branch.

Sports refresh (manual operator action, never part of scoring):

```bash
# One authenticated sports-source request plus at most 8 public exact-address WFS queries:
python -m data_science.ingest_sports --limit 8
# Reproduce the committed sample with zero external requests:
python -m data_science.ingest_sports --input data/infrastructure/raw/sports-965750657b6f133f.json --limit 8 --offline --output data/infrastructure
```

`--input` can reuse any saved official sports response without another authenticated request. `--limit` accepts 1–10 sites, defaults to 8 and never automatically advances to another batch. Exact-address requests cap responses at five features. Responses and negative matches are cached under `data/infrastructure/sports_addresses/`; there is no automatic geocoding or citywide enrichment. Only supported street/avenue formats and exact municipal matches are accepted; unresolved cases remain explicit. Batches merge with earlier located sites from the same source hash and never silently drop them. `--offset`, repeated `--site-index`, and `--dry-run` support deliberate bounded expansion; there is no automatic next batch. A changed source hash requires a new output directory so earlier snapshots remain intact. Address responses are preserved for offline reproduction. Successful snapshot replacement is atomic and content-addressed raw archives are retained. The original sports `retrieved_at` is preserved during enrichment; `processed_at` identifies normalization time. New address responses have checksum/timestamp sidecars, and legacy address-cache retrieval times remain unknown rather than being invented. Empty/failed enrichment preserves the previous sports snapshot.

All official downloads are capped at 8 MB with HTTP timeouts. Sports source arrays above 2,000 rows are rejected. No new optional snapshot is required to keep transport scoring responsive. Park/parking/sports snapshots are cached and reload automatically when their file timestamp/size changes, including after atomic replacement. Corrupt optional files become unavailable without hiding other categories; valid records survive partial geometry corruption. Transport still uses the existing process cache; restart after replacing its CSV. The line cache reloads when its file timestamp/size changes. No token, `.env`, generated cache or personal report is committed. Local inspection artifacts are kept in ignored `.local/` rather than discarded.

## Scores and personalization

The original Mobility Score remains:

```text
distance_score = max(0, 100 * (1 - nearest_stop_m / 800))
density_score = min(100, 100 * stop_groups_500m / 8)
mobility = round(0.6 * distance_score + 0.4 * density_score, 1)
```

No numeric Green, Parking, Sports or Commute Score is introduced. Park coverage is still unverified; parking and sports coverage are explicitly partial; real route distances do not establish a calibrated residential-quality score.

Personalized LifeScore includes only numeric validated category scores with positive selected weights:

```text
effective_weight[i] = selected_weight[i] / sum(selected_weight for eligible selected categories)
LifeScore = round(sum(score[i] * effective_weight[i]), 1)
```

Weights are finite values from 0–100. Missing category scores are excluded, never zero. The default requested weight is 20 for each of five categories. Currently Mobility is the sole eligible category, so its effective weight is 100% and the result is explicitly labeled **Partial LifeScore**, a limited transport index. If its weight is zero, `life_score.value` is null. Clients can submit requested weights through the API and display the returned exclusions and effective percentages. The comparison endpoint applies the same top-level weights to both homes and flags different contributing category sets as noncomparable.

## API contracts

Existing score requests and response fields remain valid. Both `POST /api/score` and `POST /api/score/address` accept optional `weights`, for example `{"mobility":60,"green":40}`. Supplying a weights object treats omitted categories as zero requested weight. New response fields:

- `line_features`: observed distinct lines in 500 m, 1,000 m and the selected radius; nearest platform's known lines; matched local/global platform coverage and observation timestamps. Enriched transport markers include `lines`, `line_data_status`, `lines_retrieved_at`.
- `features.nearest_sports_facility_m`, `features.sports_facilities_within_radius`: EPSG:2180 straight-line distances/counts using verified address-point proxies. Nearest distance can exceed the marker radius. Missing dataset means null features plus `sports` in `unavailable`; available empty search means zero count.
- `places` extends existing categories with `sports`, site names, source types, address, schedules and coordinate provenance. Each optional category has an independent 50-marker cap; transport retains its 200-marker cap. `datasets.sports` reports sample/source counts, coverage, unresolved addresses, source hash and retrieval metadata. Legacy `nearby` still describes transport only.
- `life_score`: value, availability/partial status, requested and normalized weights, actual contributing category scores, excluded-category reasons and formula explanation. `scores.mobility` is unchanged and no unsupported score is added.
- `score_eligibility` explicitly explains why each category is eligible or excluded; LifeScore exclusions carry these evidence-based reasons.
- `sources` includes all available infrastructure and observed-line sources, including real retrieval times.

Routing is deliberately separate so scoring remains offline:

```http
POST /api/commute
Content-Type: application/json

{"origin":{"latitude":52.2297,"longitude":21.0122},"destination":{"latitude":52.239,"longitude":21.022}}
```

Both points use the same Warsaw coordinate validation as scoring. The response includes `origin`, `destination`, ellipsoidal straight-line `baseline`, independent `walking`/`driving` results and explicitly unavailable `transit`. Successful routes include actual provider route distance, estimated minutes, GeoJSON LineString geometry, retrieval time, endpoint snap distances and cache status. Endpoint snaps over 100 m are rejected. Failed routes contain only an unavailable status/reason, not an invented duration. No transit duration, wait time, walking segment, transfer, line or departure-time estimate is fabricated.

A client can request the offline report separately from commute. Route-provider failures return unavailable profile results and preserve the straight-line baseline. No request to `/api/score` calls an external routing or infrastructure service. Route geometry and attribution are returned for clients to render; no frontend changes are included.

## Routing provider and limits

Provider: [FOSSGIS OSRM](https://routing.openstreetmap.de/about.html), using OpenStreetMap data and documented [OSRM HTTP route responses](https://project-osrm.org/docs/v5.24.0/api/). Walking and driving were each verified with one bounded public sample request. Separate `routed-foot/route/v1/foot` and `routed-car/route/v1/driving` endpoints are used: changing the profile name on a driving-only server is insufficient.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `ROUTING_ENABLED` | `true` | Set `false` to disable external routing while keeping baseline/scoring |
| `ROUTING_BASE_URL` | `https://routing.openstreetmap.de` | Trusted backend configuration; replacement must support the same two mode-specific endpoint paths |
| `GEOCODING_USER_AGENT` | Required for address search | Identifiable app/project/contact for existing Nominatim service |
| `WARSAW_API_TOKEN` | No default | Only explicit official-data refresh; never scoring or public routing |

The public routing service is for light use, not a production SLA. Requests are serialized at least 1.1 seconds apart across modes; each mode makes one request with no retries, an 8-second per-phase HTTP timeout, a 10-second total bound and a 1 MB response cap. Queue acquisition is limited to two seconds; overload returns unavailable route profiles with the baseline rather than waiting indefinitely. URLs containing credentials/query strings are rejected without exposing them. HTTP 429 starts a cooldown rather than continuing to call the provider. A bounded in-memory LRU holds 128 profile results, successful for 24 hours and unavailable results for 60 seconds. Cache keys include provider, direction, exact points and mode. A restart clears this cache. Keep one backend worker/instance for this limiter; scale only with a shared limiter/cache or an appropriate routing provider. The API returns attribution and a Fix the map URL. Integrating clients must display them and explain that explicit route checks transmit selected endpoints to FOSSGIS, which logs requests. No API key is needed for this provider.

Driving estimates exclude live traffic. Walking estimates are provider profile estimates, not measured travel times or accessibility guarantees. No GTFS/transit journey router is configured. The bounded check of the official ZTM download page returned HTTP 403 and an anti-bot challenge. A validated current timetable graph and schedule-aware routing service are required before trip duration, waiting, transfers or departure-time queries can be supported; nearby line lists cannot supply those values. See [coverage and verification follow-up](coverage-verification.md).

## Comparison API

`POST /api/compare` accepts exactly two locations, each using either coordinates or an address, an optional shared `weights` object, an optional `destination`, and `include_routes` (default false). Each location retains its own `radius_m`. Nested per-location weights and ambiguous address-plus-coordinate objects are rejected with HTTP 422.

```json
{
  "locations": [
    {"latitude":52.2297,"longitude":21.0122,"radius_m":1000},
    {"latitude":52.263332,"longitude":20.961636,"radius_m":1000}
  ],
  "weights":{"mobility":60,"green":40},
  "destination":{"latitude":52.239,"longitude":21.022},
  "include_routes":false
}
```

The response includes both complete score results in `locations`, measured comparison rows in `comparisons`, and coverage/interpretation `warnings`. Each row identifies `metric`, raw `values` for A/B, `unit`, the preferred direction (`higher`/`lower`), a `status` (`comparable`, `incomparable`, `unavailable`), `advantage` (`a`, `b`, `equal`, or null), and a reason when no advantage can be established.

Rows cover Mobility Score, Partial LifeScore, nearest stops, stop groups within 500 m, nearest listed parks/parking/sports and their radius counts. Different radii make optional-site counts noncomparable. Different or unverified source snapshots make infrastructure comparisons noncomparable. Missing data remains null and is never ranked as zero. Different score components/weights make LifeScore comparisons noncomparable. Advantages describe only the measured quantities, not overall residential quality.

A destination adds straight-line baseline comparison without calling a routing provider. Walking/driving measurements remain unavailable unless the caller explicitly sets `include_routes:true`. That opt-in requests at most four profile routes for the two homes, subject to the existing limiter/cache; it also adds distance and estimated-duration rows. Transit journeys remain unavailable. An address location invokes the existing bounded geocoder; a coordinate-only comparison without route opt-in is fully offline.

Example local checks:

```bash
curl -X POST http://127.0.0.1:8000/api/score -H 'Content-Type: application/json' -d '{"latitude":52.2297,"longitude":21.0122,"radius_m":1000,"weights":{"mobility":60,"green":40}}'
curl -X POST http://127.0.0.1:8000/api/compare -H 'Content-Type: application/json' -d '{"locations":[{"latitude":52.2297,"longitude":21.0122},{"latitude":52.263332,"longitude":20.961636}],"destination":{"latitude":52.239,"longitude":21.022}}'
# This request explicitly contacts the public routing provider unless routing is disabled:
curl -X POST http://127.0.0.1:8000/api/commute -H 'Content-Type: application/json' -d '{"origin":{"latitude":52.2297,"longitude":21.0122},"destination":{"latitude":52.239,"longitude":21.022}}'
```

## Verification

```bash
# Repository root, active Python environment
python -m pytest -q
git diff --exit-code origin/main -- frontend
```

Automated tests use saved real source/routing fixtures, synthetic spatial test geometry and mocked HTTP; outbound HTTP transports are blocked. Checks cover valid/invalid addresses and coordinates, exact municipal matching, sports parsing/deduplication, missing sources, radius geometry, line coverage, provider failures and rate limits, weight normalization, comparison validity and old API contracts. Walking/driving provider responses were verified separately using two bounded public requests. Frontend files are unchanged and no UI work is delivered in this branch.

Try the sports-site point `(52.263332, 20.961636)` in `/api/score` to inspect the verified Elbląska 51 site. Transport cache coverage can be inspected around the existing `1001`–`1003` stop groups in the CSV. These examples are verified points, not fabricated residential-address geocoding results.

## Production considerations and remaining limits

Before deployment, verify park completeness and source reuse terms, sports sample expansion and access-hour freshness, parking operator coverage/timestamp/tariff semantics, and routing-provider capacity/privacy/availability. Sports sample expansion is an explicit bounded operator action, not an automatic citywide job. Full transit journeys require a verified routing service and timetable data. Broader LifeScore eligibility requires justified category scores; adjusting weights cannot create missing evidence. No production service, deployment setting or shared branch was changed, and this PR must be reviewed before merge.

The follow-up verification, exact expanded sample, data-status contract, source-freshness distinctions and current credential-operation blocker are recorded in [Coverage and verification](coverage-verification.md).
