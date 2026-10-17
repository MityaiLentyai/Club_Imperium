# OLO — Warsaw neighborhood explorer

Warsaw Open Data hackathon project (`MityaiLentyai/Club_Imperium`). The FastAPI backend scores transport accessibility using the committed `data/stops_clean.csv` dataset. It supports coordinates or a Warsaw address for integration with the team's React + TypeScript + Vite frontend.

The current Mobility Score is a preliminary 0–100 metric based on straight-line distance to the nearest stop and stop group density. It does not measure travel time or service frequency. Park, listed-parking and verified educational sports-site proximity features are available from official local snapshots. Observed transport lines, actual walking/driving routes, personalized partial LifeScore and measured address comparisons are available through backend APIs. See [Backend MVP setup and contracts](docs/complete-mvp.md). See [Parks + Parking documentation](docs/parks-parking.md) for sources, refresh commands, response fields and limitations. No Green, Parking, Sports or Commute Score is inferred from incomplete evidence.

## Configuration layout

- `configs/requirements.txt`: backend Python dependencies.
- `configs/.env.example`: example backend environment variables without credentials.
- `render.yaml`, `.gitignore`, `.python-version`, and `README.md`: kept in the repository root.
- Frontend-specific configuration belongs in `frontend/`.

Python source files remain in `backend/` and `data_science/`.

## Install and run locally

Use Python 3.11. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r configs/requirements.txt
cp configs/.env.example .env
```

Municipal address lookup works offline from the committed index. For Nominatim fallback, edit `.env`: set `GEOCODING_USER_AGENT` to identify Warsaw LifeScore and include your team's real contact email or URL. The example contact is a placeholder. Then load the environment and start FastAPI:

```bash
set -a
source .env
set +a
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Interactive API docs: <http://localhost:8000/docs>. OpenAPI: <http://localhost:8000/openapi.json>. Environment files are loaded by the shell; the application does not automatically read `.env`.

```bash
python -m pytest -q
```

Tests use the actual committed transport CSV and mocked geocoding responses. Unmocked outbound HTTP is blocked in tests. The loader resolves its CSV path relative to its module, independent of the working directory. Uvicorn must still be able to import `backend`, so run the commands from the repository root.

## API

Existing response shapes are preserved.

| Endpoint | Input | Result |
| --- | --- | --- |
| `GET /api/health` | None | `{"status":"ok"}` (process liveness) |
| `GET /api/geocode` | `address` query parameter | Address and coordinates |
| `POST /api/score` | JSON `latitude`, `longitude`, optional `radius_m` | Location, Mobility Score, transport features |
| `POST /api/score/address` | JSON `address`, optional `radius_m`, `weights` | Score response with resolved address in `location` |
| `POST /api/commute` | JSON `origin`, `destination` coordinate objects | Straight-line baseline, walking/driving routes or explicit unavailability; transit unavailable |
| `POST /api/compare` | Exactly two `locations`, optional shared `weights`, `destination`, `include_routes` | Measured feature/score comparisons with missing-data and comparability warnings |

Scoring coordinates must be finite and inside the validated official Warsaw district union, including a 0.5 m boundary precision band. If boundary data is unavailable, the legacy rectangle is used with explicit degraded evidence in `area_validation`. See [citywide address handling](docs/citywide-addresses.md) for source coverage, address normalization, fallback behavior and known limitations. Unsupported coordinates and unsafe projection results return HTTP 422. Address inputs must contain 3–300 characters after trimming. Geocoding additionally normalizes internal whitespace.

```bash
curl http://localhost:8000/api/health
curl --get http://localhost:8000/api/geocode --data-urlencode 'address=Stokłosy 7'
curl -X POST http://localhost:8000/api/score \
  -H 'Content-Type: application/json' \
  -d '{"latitude":52.2297,"longitude":21.0122}'
curl -X POST http://localhost:8000/api/score/address \
  -H 'Content-Type: application/json' \
  -d '{"address":"Stokłosy 7"}'
```

The existing `location`, `scores`, and `features` fields retain their meanings. The example below shows those fields; responses additionally include `radius_m`, `places`, `unavailable`, `nearby`, and `sources` as described below. Values are calculated using the committed CSV:

```json
{
  "location": {"latitude": 52.2297, "longitude": 21.0122},
  "scores": {"mobility": 92.7},
  "features": {
    "nearest_stop_m": 30.7,
    "stop_groups_500m": 7,
    "stop_groups_1000m": 24
  }
}
```

`/api/geocode` returns `{"address": <resolved string>, "latitude": <number>, "longitude": <number>}`. `/api/score/address` returns the score structure above plus `location.address`.

## Live transport contract

Both scoring endpoints accept optional integer `radius_m` (1–2000 metres; default 1000). The radius filters map markers only. Mobility Score and `features.stop_groups_500m` / `stop_groups_1000m` always use their original fixed radii and unchanged formula.

Additional response fields:

- `radius_m`: the requested marker radius.
- `places`: transport platform objects with `id` (`stop_id:platform`), `stop_id`, `platform`, `category: "transport"`, `label` (CSV stop name), `latitude`, `longitude`, `distance_m`, and `distance_type: "straight_line"`. Coordinates come from the real CSV; distances use the projected EPSG:2180 geometry. Lists are sorted nearest first and limited to 200 platforms.
- `nearby`: `{ "total": <platform count within radius>, "limit": 200, "truncated": <boolean> }`. Counts refer to platforms, while scoring density counts unique stop groups. A capped list is explicitly marked.
- `unavailable`: always includes grocery/pharmacy; includes green/parking only if their optional local snapshots cannot be loaded. An empty transport list means zero nearby platforms, not unavailable data.
- `sources`: a source-name list identifying `stops_clean.csv`. No live retrieval timestamp is invented for this static dataset.

`POST /api/score/address` uses the same contract and adds `location.address`. `/api/geocode` retains its single-object response. No `/analyze` endpoint is needed. Grocery/pharmacy data and transit journey routing are not implemented. Walking/driving routes are available separately through `/api/commute`. Parks and listed parking extend this contract as documented in [Parks + Parking](docs/parks-parking.md). Scoring remains offline. Destination baselines and optional walking/driving routes are exposed separately through `/api/commute` and `/api/compare`.

## Frontend

The OLO web app lives in `frontend/` (React + TypeScript + Vite + Leaflet). See [frontend/README.md](frontend/README.md) for its screens and behavior. Start the backend first, then run the app from the repository root in a second terminal (Node 22):

```bash
cd frontend
npm ci
cp .env.example .env.local   # VITE_API_BASE_URL=http://localhost:8000
npm run dev -- --port 5173 --strictPort
```

Open http://localhost:5173. With `VITE_API_BASE_URL` set the app starts in Live mode; without it, in Demo mode with illustrative places. The mode can be switched in **Data & sources**. `VITE_API_BASE_URL` is public client configuration; never place secrets in `VITE_` variables. Restart Vite after changing environment variables.

Live mode implements the endpoint contract in [docs/frontend-integration-check.md](docs/frontend-integration-check.md):

- `POST /api/score` and `POST /api/score/address`: Mobility Score, the returned LifeScore `label`/`status` with requested vs. effective weights (adjustable under **Priorities**), transport stops, and park, listed-parking and sports places. A category counts as available only when `datasets.<category>.status` is `available`; otherwise it shows "No data yet". When nothing is within the radius, the nearest object outside it is shown from `features`.
- `GET /api/geocode`: destination search in the Commute tab.
- `POST /api/commute`: walking and driving routes, requested explicitly by the user, drawn on the map (GeoJSON is converted to Leaflet order). Each profile's `status` is checked; transit is shown as unavailable with the backend's reason. OSRM attribution and "Fix the map" are displayed.
- `POST /api/compare`: used for exactly two saved homes (coordinates with each home's own radius, shared weights, optional destination and an explicit opt-in for routes). Rows show the backend's `advantage`, and `incomparable`/`unavailable` reasons; `warnings` are listed under the table. Demo mode compares up to three homes in the browser.
- `GET /api/health`: shown in **Data & sources**; data problems are reported from score responses.

Request timeouts follow the backend bounds (35 s for commute, 75 s for a comparison with routes). FastAPI `detail` errors are shown as plain sentences, including list-style validation errors.

```bash
# From frontend/:
npm test        # model tests
npm run build   # type check + production build
```

Set the backend's `CORS_ORIGINS` to the exact frontend origin (`http://localhost:5173` by default). CORS is already environment-configurable; the frontend does not need to add CORS response headers. Send JSON with `Content-Type: application/json`:

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const response = await fetch(`${API_BASE_URL}/api/score/address`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ address: 'Stokłosy 7' }),
});
const data = await response.json();
if (!response.ok) throw new Error(JSON.stringify(data.detail));
// data.scores.mobility, data.features, data.location
```

Errors use FastAPI's `detail` envelope: validation errors return a list; service errors return a string, e.g. `{"detail":"Address not found in Warsaw"}`.

| Status | Meaning |
| --- | --- |
| 422 | Missing or invalid coordinates/address |
| 404 | No address found in Warsaw, or result rejected as outside Warsaw |
| 502 | Upstream network/HTTP failure (including 429) or malformed response |
| 503 | Geocoding User-Agent not configured |
| 504 | Upstream timeout (10 seconds per HTTP operation) |

## Environment

| Variable | Required | Default / purpose |
| --- | --- | --- |
| `GEOCODING_USER_AGENT` | For address routes | No default; app identifier and real team contact. Coordinate scoring and health work without it. |
| `CORS_ORIGINS` | For deployed React integration | `http://localhost:5173`; comma-separated origins, e.g. `https://your-frontend.example,http://localhost:5173`. Surrounding quotes and a trailing slash are ignored. Restart after changing; the allowed list is logged at startup. |
| `CORS_ORIGIN_REGEX` | No | Unset. Optional regular expression for generated hostnames such as Vercel previews, e.g. `^https://club-imperium-qrbl(-[a-z0-9-]+)?\.vercel\.app$`. Keep it anchored to your own project. |
| `GEOCODING_URL` | No | `https://nominatim.openstreetmap.org/search`; switch to another Nominatim-compatible provider without code changes. |
| `WARSAW_API_TOKEN` | Only for parking snapshot refresh | Backend-only token for the official parking endpoint; scoring uses local files and needs no token. |
| `ROUTING_ENABLED` | No | `true`; disable external route calls with `false`. |
| `ROUTING_BASE_URL` | No | `https://routing.openstreetmap.de`; OSRM base with separate routed-foot/routed-car endpoints. |
| `PORT` | On Render | Render supplies it; local launch uses port 8000. |
| `PYTHON_VERSION` | In Render config | `3.11.11` in `render.yaml`. |

There are no API keys or credentials in the example configuration. CORS allows GET/POST and JSON headers; it is browser access configuration, not authentication.

## Nominatim usage and limits

Read the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before deploying. This app uses it only for explicitly submitted address searches. Public Nominatim permits at most one request per second across the whole application, requires an identifiable User-Agent, caching, and visible OpenStreetMap attribution. Do not connect this endpoint to autocomplete, bulk geocoding, or periodic searches.

The backend serializes outbound requests, spaces request starts by at least 1.1 seconds, and caches successful results and not-found responses for 24 hours, up to 500 entries with least-recently-used eviction. Concurrent identical searches share the cached result. Provider failures are not cached. Cache and limiter live in memory: **use one worker and one service instance**. Restarts clear the cache; scaling or heavier usage requires shared caching/rate limiting or a suitable provider. This public hackathon API has no authentication or per-user quotas.

Queries are constrained to Poland and a conservative Warsaw bounding box; responses are checked against that box and city/town/village fields when supplied. This rejects clearly foreign results, but is not an exact municipal-boundary check. No new boundary dataset is introduced.

The frontend must visibly display “© OpenStreetMap contributors” linked to <https://www.openstreetmap.org/copyright> when using geocoding results. OpenStreetMap data is under ODbL. Frontend consumers must display OpenStreetMap attribution and submit searches only on explicit user action. Do not send confidential information to the public geocoder.

## Deploy on Render

`render.yaml` provides a Web Service blueprint. After reviewing and pushing this feature branch yourself, select that branch when creating the Render service/blueprint; deployment does not require merging into `main`. Set the real User-Agent/contact and frontend origin when Render prompts. Deployment is not performed by this task; only the feature branch is pushed for review.

For manual setup, connect `MityaiLentyai/Club_Imperium` as a Python Web Service, leave the root directory at the repository root, and configure:

```text
Build command: pip install -r configs/requirements.txt
Start command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
Health check path: /api/health
Python version: 3.11.11
```

Set `CORS_ORIGINS` to the exact React origin and `GEOCODING_USER_AGENT` to your app identifier with real contact details. Set `GEOCODING_URL` if using a different compatible provider. Render supplies `PORT`; keep a single instance. The CSV must remain committed and included in the deployment. Render instructions follow its [FastAPI deployment guide](https://render.com/docs/deploy-fastapi), using this repository's `backend.main:app` entrypoint.

After deployment, check `/api/health`, `/docs`, and coordinate scoring. Test address scoring manually with one explicitly submitted Warsaw address after configuring the User-Agent. Health reports process liveness; it does not probe the external geocoder.

Frontend hosting: configure a separate static site with root `frontend`, build command `npm ci && npm run build`, and publish directory `dist`. Set `VITE_API_BASE_URL` to the backend HTTPS origin before building and `CORS_ORIGINS` on the backend to the frontend origin. Rebuild the frontend after environment changes. `render.yaml` configures only the backend. Address search goes through the backend's `/api/geocode`, so provider/contact settings stay server-side. Map tiles still require access to OpenStreetMap.

Current source coverage, sports refresh/reproduction, weight normalization, route cache limits and comparison warnings are documented in [Backend MVP](docs/complete-mvp.md). Review those limitations before deployment; this feature does not change production configuration.

Current full-source processing, quality reports, API examples and frontend handoff: [Data coverage and stabilization](docs/data-coverage-final.md). The complete saved sports source has 308 addresses: 293 located addresses consolidated into 291 facility points, with 15 unresolved. This does not imply complete Warsaw sports coverage.

## OpenStreetMap groceries and pharmacies

The optional local OSM snapshot covers mapped supermarkets, convenience/grocery stores and pharmacies across all 18 Warsaw districts. See [source counts, ingestion and API contract](docs/osm-retail.md) and [ODbL attribution/data-sharing notice](data/osm/README.md). Existing scoring formulas are unchanged; the frontend must display attribution and incomplete-coverage warnings.
