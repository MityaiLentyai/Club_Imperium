# Backend integration review

Historical review of PR #9. For current dataset counts, final validation and exact response examples, see [the current coverage and handoff](data-coverage-final.md).

Reviewed from `origin/main` commit `380268c` on 2026-10-17. Backend and Data Science fixes only: no new endpoint, dataset, score, formula, frontend change or deployment setting.

## Endpoint contract

| Endpoint | Input | Successful response | Important failure behavior |
| --- | --- | --- | --- |
| `GET /api/health` | None | `{"status":"ok"}` | Liveness only; does not promise dataset/provider readiness |
| `GET /api/geocode` | Required `address` query, 3–300 trimmed characters | Object with `address`, `latitude`, `longitude` | 404 no Warsaw match; 422 invalid address; 503 missing geocoder configuration; 502 upstream failure; 504 upstream timeout |
| `POST /api/score` | `latitude`, `longitude`, optional `radius_m` (default 1000; 1–2000), optional `weights` | `location`, `scores`, `life_score`, `features`, `line_features`, `places`, `datasets`, `unavailable`, `nearby`, `sources`, `radius_m` | 422 unsupported/non-finite coordinates or invalid weights/radius; 503 unavailable mandatory transport snapshot |
| `POST /api/score/address` | `address`, optional radius and weights | Same score structure; `location.address` contains geocoder display name | Geocoding errors above, plus score errors |
| `POST /api/commute` | `origin` and `destination`, each `{latitude,longitude}` | `origin`, `destination`, straight-line `baseline`, separate `walking`, `driving`, `transit`, `attribution` | 422 invalid points; individual route failures are HTTP 200 with profile `status: unavailable` |
| `POST /api/compare` | Exactly two `locations`, each coordinates OR address, optional shared `weights`, `destination`, `include_routes` | `locations` containing full score results, `comparisons` rows and `warnings` | 422 ambiguous locations, per-location weights, or routes without destination; propagates address/mandatory-data failures |

Supported coordinate envelope is latitude 52.0–52.4, longitude 20.75–21.3; this is not a municipal boundary polygon. Weights use category keys `mobility`, `green`, `parking`, `sports`, `commute`, each 0–100. Omitted weights use existing defaults; explicitly supplied weights assign zero to unspecified categories. The only eligible numeric score remains Mobility: unavailable scores never become zero, and selecting only unavailable categories yields `life_score.value: null`.

OpenAPI at `/openapi.json` documents validated request models and `/docs` renders them. Existing successful responses have no explicit response models in OpenAPI; use this contract and the response regression tests, rather than treating the generated empty success schema as a detailed client type. No existing response fields were removed or renamed.

## Frontend integration requirements

The current tracked frontend `src/api.ts` posts to `${VITE_API_BASE_URL}/analyze`. This backend has no `/analyze` endpoint: use `POST /api/score` for coordinate analysis and a separate `POST /api/commute` for destination routes. The frontend currently geocodes directly through Nominatim; the backend alternative is `GET /api/geocode?address=...`, which returns one object, not a list. Backend address routes require `GEOCODING_USER_AGENT` in the backend environment. No configuration was changed by this review.

- `places` items expose `id`, `category`, `label`, `latitude`, `longitude`, `distance_m` and `distance_type`. Current frontend's adapter can consume these existing fields, but its category union does not yet include `sports`.
- Respect `unavailable` and category `datasets.status`. For missing optional datasets, both nearest-distance and count features are `null`; an available dataset with no nearby objects has count zero. Missing optional data does not remove the Mobility result.
- Label LifeScore using the returned `label` and `status`; do not present its partial Mobility-only value as complete residential quality. Requested weights and normalized effective weights are separate.
- Route geometry is GeoJSON `[longitude,latitude]`, while Leaflet commonly consumes `[latitude,longitude]`. Read `walking` and `driving` separately; the frontend's current flat optional `commute` shape does not represent this response. Check each profile status before reading measurements or geometry.
- Route durations are provider estimates without live traffic. Transit remains explicitly unavailable. A busy routing queue now returns the baseline and unavailable profiles after at most two seconds of queue waiting. Existing per-profile total timeout is ten seconds; a two-home comparison with `include_routes:true` can need four sequential requests. A fixed 20-second client timeout is insufficient for the worst case; choose a suitable timeout or request the two commutes separately.
- `/api/compare` defaults to no external route requests. Shared weights apply to both homes; compare rows have `status`, nullable `advantage` and, where applicable, reasons for unavailable/incomparable values. Counts measured using different radii are incomparable.
- Health stays HTTP 200 if datasets are unavailable: use actual score results to show data errors. HTTP error JSON uses `detail`; validation details may be a list while application errors use a string.

Frontend files were inspected read-only and remain unchanged.

## Real checks and retained data

Checked at 2026-10-17 21:18 UTC using FastAPI TestClient against the application and real public geocoder/routing providers: three geocoder requests and six route requests, no API token or ingestion. All six requested endpoints were exercised successfully. Address score calls and address comparison reused the geocoder cache.

| Address | Coordinate score (lat, lon) | Mobility | Geocode / coordinate score / address score |
| --- | --- | --- | --- |
| Marszałkowska 83 | 52.225763, 21.013683 | 92.6 | 200 / 200 / 200 |
| Stokłosy 7 | 52.158969, 21.031856 | 72.0 | 200 / 200 / 200 |
| Ząbkowska 12 | 52.253043, 21.039900 | 87.6 | 200 / 200 / 200 |

Address-geocoded results can differ from scores at the specified coordinates: address comparison returned partial LifeScores 92.2 and 72.2, using its actual geocoder coordinates. This is not a formula change. All three infrastructure snapshot categories were available at all three scoring points; this does not imply nearby objects or complete coverage.

| Journey | Walking | Driving |
| --- | --- | --- |
| Marszałkowska 83 → Stokłosy 7 | 8,333.7 m / 110.5 min | 8,112.4 m / 15.1 min |
| Stokłosy 7 → Ząbkowska 12 | 12,465 m / 165.1 min | 13,638.7 m / 19.4 min |
| Ząbkowska 12 → Marszałkowska 83 | 4,551.4 m / 60.1 min | 5,531 m / 9.0 min |

All six profiles were available and all transit profiles unavailable as documented. These are dated provider observations, not guarantees of future availability. External checks were local; no deployed service was changed or tested.

Unchanged main snapshots: 6,652 transport platforms, 15 observed-line platforms; 60 named park objects from 430 source rows; 18 listed parking facilities from 19 rows; seven located educational sports sites from 308 distinct source addresses / 1,227 rows. Coverage remains limited. No snapshots were refreshed or expanded in this branch.

## Fixes and reproducible validation

- Missing, invalid or empty mandatory transport data returns sanitized HTTP 503 rather than an unhandled HTTP 500 or non-finite score.
- A malformed optional geometry is skipped without discarding the other valid features in that snapshot.
- Address scoring and comparison run CPU/geospatial scoring in the worker thread pool, preserving the async event loop for other requests.
- Routing queue acquisition has a two-second bound, and acquired locks are released on cancellation and failure. Timeout never releases another request's lock.

Run `python -m pytest -q` using the repository Python environment. Result: **208 passed**, one existing Starlette/httpx deprecation warning. Tests mock/block external HTTP. New regressions cover all fixes, missing optional datasets, three realistic coordinate contracts, score/compare consistency and cancellation. Existing tests cover weights, coordinate validation, route failures/cache/size bounds, comparison opt-in and geocoder failure modes. `git diff --check` passes; frontend, data snapshots, Mobility formula and production configuration have no changes against the branch base.

For a bounded manual check against a local backend (external providers are contacted), configure the existing geocoder environment, then call:

```bash
curl --get 'http://127.0.0.1:8000/api/geocode' --data-urlencode 'address=Marszałkowska 83'
curl -X POST 'http://127.0.0.1:8000/api/score' -H 'Content-Type: application/json' -d '{"latitude":52.225763,"longitude":21.013683}'
curl -X POST 'http://127.0.0.1:8000/api/commute' -H 'Content-Type: application/json' -d '{"origin":{"latitude":52.225763,"longitude":21.013683},"destination":{"latitude":52.158969,"longitude":21.031856}}'
```

For other requests and limitations, see [the existing backend API guide](complete-mvp.md).
