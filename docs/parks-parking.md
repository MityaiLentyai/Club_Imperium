# Parks + Parking MVP

The API scores transport as before and adds independently measured park and listed-parking proximity. Scoring reads committed snapshots only; it never calls the WFS or parking service. No new dependencies or production settings are required.

## Verified sources and loaded data

Retrieved on 2026-10-17. Exact UTC retrieval times, source URLs, source counts and SHA-256 hashes are embedded in `data/infrastructure/*.geojson`. These files retain EPSG:4326 geometries and source identifiers. Content-addressed raw source responses are archived alongside them for reproduction.

* [Warsaw WFS capabilities](https://wfs.um.warszawa.pl/serwis?service=WFS&request=GetCapabilities). WFS 1.1.0 advertises `ns92528565:PLACE_SKWERY` with default EPSG:2178. `DescribeFeatureType` confirms ID, NAZWA_PODST, NAZWA_SKROC, NAZW_DOPEL, OBIEKT, DZIELNICE and surface GEOMETRY. The returned GML2 polygon coordinates explicitly identify EPSG:2178 and use easting/northing. The single capped GetFeature response contained **430** objects: 60 Park, 171 Skwer, 121 Rondo, 67 Plac and 11 other objects. **60 validated Park records loaded**. Only exact `OBIEKT=Park` is accepted. Squares are excluded because this naming layer does not establish green cover. Empty, invalid and non-polygon geometry is skipped. Source IDs define distinct parks; multipart geometries are united by ID. EPSG:4326 geometry is retained and EPSG:2180 geometry is calculated once per backend worker for measurements.
* [Wolne miejsca parkingowe / Available parking spaces catalogue](https://dane.um.warszawa.pl/en/catalogue/20ec668b-e5f3-4cbf-aeeb-eb825f3c8731). [Official parameters](https://dane.um.warszawa.pl/files/m_parkingi_wolne_miejsca_pa.json) and [examples](https://dane.um.warszawa.pl/files/m_parkingi_wolne_miejsca_pw.json) specify `POST https://dane.um.warszawa.pl/api/action/get_m_parkingi_wolne_miejsca` with `Authorization: <WARSAW_API_TOKEN>`. The **actual authenticated response** has `Status: 1`, `Timestamp` and `carParks`, unlike the documentation's `Parkings` example. **19 source rows; 18 validated distinct facilities loaded**. Coordinates are validated against the backend Warsaw envelope and facilities deduplicated by coordinates rounded to six decimals. Stable identifiers are provider IDs if present, otherwise hashes of those coordinates. No API token is stored in snapshots.

The parking source lists participating ZTP, ZDM and PKiN facilities; it does not cover all street, private or municipal parking. The response supplies names, coordinates, `adress`, `opening_hours`, `tariffs`, per-level `total_places` and `free_places_total`. Capacity sums standard, disabled and electric spaces only when every per-level count is a nonnegative integer. Pricing and opening hours retain source values; currency and duration units are not inferred. The provider response Timestamp is timezone-naive and does not establish when any facility's availability was measured. Dynamic counts remain in the raw archive and are **never exposed as current availability**.

## Refresh and reproduce

From the repository root with the existing Python environment activated:

```bash
python -m data_science.ingest_infrastructure green
# Supply WARSAW_API_TOKEN through your existing backend environment first:
python -m data_science.ingest_infrastructure parking
```

The application and refresh script do not automatically load `.env`. Use your established environment loader. Never set the token in a `VITE_` variable, frontend file or command line argument. Only parking refresh needs it; scoring runs without credentials.

Each refresh makes one request, with a 30-second timeout per HTTP operation and an 8 MB decompressed response limit. WFS requests at most 500 objects, with no paging; a response reaching the cap is rejected so partial coverage cannot silently replace the dataset. Parking responses with 500 or more records are also rejected. No periodic or citywide ingestion loop is introduced. Failed HTTP, authentication, schema or normalization checks preserve the previous snapshot. Successful replacement is atomic and raw archives are preserved.

Offline reproduction (choose a content-addressed archive filename from the committed metadata):

```bash
python -m data_science.ingest_infrastructure green --input data/infrastructure/raw/green-ee33fa4d25b1815c.gml --output /tmp/urbanlens-reparse
python -m data_science.ingest_infrastructure parking --input data/infrastructure/raw/parking-569a61c2815eae59.json --output /tmp/urbanlens-reparse
```

Offline reparse records a new normalization/retrieval timestamp; original provenance remains in the committed snapshot. Restart the backend after a refresh: each worker caches its validated datasets. Missing or corrupt snapshots mark only that category unavailable. Valid empty snapshots return zero nearby facilities and a null nearest distance.

## Response contract

`POST /api/score` and `POST /api/score/address` keep their request formats and all previous fields. Both add these flat `features`:

| Feature | Meaning |
| --- | --- |
| `nearest_park_m` | Shortest straight-line distance to a listed park area, or zero inside it; null if unavailable/empty |
| `parks_within_radius` | Distinct source parks whose areas lie within the requested radius; null if unavailable |
| `nearest_listed_parking_m` | Straight-line distance to nearest listed facility point; null if unavailable/empty |
| `listed_parking_within_radius` | Distinct listed facilities inside the requested radius; null if unavailable |

Distances use EPSG:2180 metres. Nearest-distance features search the entire loaded snapshot and can exceed the selected radius. Counts and markers use the selected radius (1–2000 metres). Park distance is to the area, **not its entrance or a walking route**; park markers are interior representative points, which may lie beyond the radius when part of a large park is nearby.

`places` retains all transport markers and adds `category: "green"` or `"parking"`, names, representative coordinates, source-based IDs, `distance_m`, `distance_type: "straight_line"` and `distance_basis: "park_area" | "facility_point"`. Parking markers may additionally contain `capacity`, `address`, `opening_hours`, `tariffs` and `availability_status: "unknown_observation_time"`. No available-space count is returned. Each new category is sorted by distance and limited to 50 markers independently of transport's existing 200-platform cap.

`datasets.green` and `datasets.parking` identify availability and include source metadata, retrieval times, coverage limitations and per-category `{total, limit, truncated}` nearby counts. `unavailable` contains a new category only when its snapshot cannot be loaded. `sources` adds the available official-source URLs and retrieval timestamps. Legacy `nearby` continues to describe **transport platforms only**. Category counts are not marker-list lengths when truncation occurs.

`scores.mobility` and all transport features/formulas remain unchanged. Neither `scores.green` nor `scores.parking` is emitted: named-park coverage has not been verified as representative of all green space, and parking coverage is explicitly partial. No overall LifeScore is invented.

## Backend verification and frontend handoff

This branch retains the backend/data portion of PR #7. Its frontend changes were reverted, so `frontend/` is identical to `origin/main`. The API returns categorized markers, nearest distances, counts, timestamps and limitations, but this branch does not render those fields in React.

Run the backend from the repository root:

```bash
source .venv/bin/activate
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
python -m pytest -q
curl -X POST http://127.0.0.1:8000/api/score -H 'Content-Type: application/json' -d '{"latitude":52.2297,"longitude":21.0122,"radius_m":1000}'
git diff --exit-code origin/main -- frontend
```

Tests use saved official fixtures and synthetic geometry only in tests. They cover CRS, strict park classification, inside/outside polygon distances, coordinate rejection, duplicate facilities, missing/corrupt/empty snapshots, category limits, radius filtering, old API contracts and unchanged Mobility Score. See [Complete backend MVP](complete-mvp.md) for sports, lines, LifeScore, commute and comparison APIs.

## Remaining verification

Verify completeness and update policy of the named parks layer before considering a Green Score. Verify parking operator coverage, source timestamp semantics, capacity category interpretation, tariff units and reuse terms before production use. Snapshots describe retrieval-time facility listings; current availability is intentionally absent. No park entrances, pedestrian network, polygon overlays, scheduled refresh, production deployment or Mobility 2.0 changes are included.
