# Warsaw LifeScore

Warsaw Open Data hackathon project (`MityaiLentyai/Club_Imperium`). The FastAPI backend scores transport accessibility using the committed `data/stops_clean.csv` dataset. It supports coordinates or a Warsaw address for integration with the team's React + TypeScript + Vite frontend.

The current Mobility Score is a preliminary 0–100 metric based on straight-line distance to the nearest stop and stop group density. It does not measure travel time or service frequency. Park and listed-parking proximity features are also available from official local snapshots. See [Parks + Parking documentation](docs/parks-parking.md) for sources, refresh commands, response fields and limitations. No Green or Parking Score is inferred from incomplete coverage.

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

Edit `.env`: set `GEOCODING_USER_AGENT` to identify Warsaw LifeScore and include your team's real contact email or URL. The example contact is a placeholder. Then load the environment and start FastAPI:

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
| `POST /api/score/address` | JSON `address`, optional `radius_m` | Score response with resolved address in `location` |

Scoring coordinates must be finite and within the supported Warsaw service envelope: latitude 52.0–52.4 and longitude 20.75–21.3, inclusive. These conservative bounds cover outer neighborhoods and are not an exact municipal-boundary check. Unsupported coordinates and unsafe projection results return HTTP 422. Address inputs must contain 3–300 characters after trimming. Geocoding additionally normalizes internal whitespace.

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

`POST /api/score/address` uses the same contract and adds `location.address`. `/api/geocode` retains its single-object response. No `/analyze` endpoint is needed. Grocery/pharmacy data and travel-time routing are not implemented. Parks and listed parking extend this contract as documented in [Parks + Parking](docs/parks-parking.md). Destination straight-line comparisons remain a frontend calculation; destinations are not sent to scoring.

## TypeScript and Vite frontend integration

The React or TypeScript + HTML/CSS frontend can use the same API. Keep Vite configuration and frontend dependencies inside `frontend/UrbanLens-Warsaw/urbanlens-warsaw/`. Set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/UrbanLens-Warsaw/urbanlens-warsaw/.env.local` for local development; use the deployed backend's HTTPS URL for production. Restart Vite after changing environment variables. This URL is public client configuration; never place secrets in `VITE_` variables.

Run the frontend in a second terminal from the repository root (Node 22 was used for verification):

```bash
cd frontend/UrbanLens-Warsaw/urbanlens-warsaw
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --port 5173 --strictPort
```

Open <http://localhost:5173>, select **Live**, submit an address or pick a map location, then explore. Demo mode uses its existing illustrative fixtures and never calls scoring/geocoding. Live mode never falls back to fixtures. Stops shown on the map are individual platforms.

```bash
# From frontend/UrbanLens-Warsaw/urbanlens-warsaw:
./node_modules/.bin/tsc --noEmit
npm test
npm run build
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
| `CORS_ORIGINS` | For deployed React integration | `http://localhost:5173`; comma-separated exact origins, e.g. `https://your-frontend.example,http://localhost:5173`. No trailing slash. Restart after changing. |
| `GEOCODING_URL` | No | `https://nominatim.openstreetmap.org/search`; switch to another Nominatim-compatible provider without code changes. |
| `WARSAW_API_TOKEN` | Only for parking snapshot refresh | Backend-only token for the official parking endpoint; scoring uses local files and needs no token. |
| `PORT` | On Render | Render supplies it; local launch uses port 8000. |
| `PYTHON_VERSION` | In Render config | `3.11.11` in `render.yaml`. |

There are no API keys or credentials in the example configuration. CORS allows GET/POST and JSON headers; it is browser access configuration, not authentication.

## Nominatim usage and limits

Read the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before deploying. This app uses it only for explicitly submitted address searches. Public Nominatim permits at most one request per second across the whole application, requires an identifiable User-Agent, caching, and visible OpenStreetMap attribution. Do not connect this endpoint to autocomplete, bulk geocoding, or periodic searches.

The backend serializes outbound requests, spaces request starts by at least 1.1 seconds, and caches successful results and not-found responses for 24 hours, up to 500 entries with least-recently-used eviction. Concurrent identical searches share the cached result. Provider failures are not cached. Cache and limiter live in memory: **use one worker and one service instance**. Restarts clear the cache; scaling or heavier usage requires shared caching/rate limiting or a suitable provider. This public hackathon API has no authentication or per-user quotas.

Queries are constrained to Poland and a conservative Warsaw bounding box; responses are checked against that box and city/town/village fields when supplied. This rejects clearly foreign results, but is not an exact municipal-boundary check. No new boundary dataset is introduced.

The frontend must visibly display “© OpenStreetMap contributors” linked to <https://www.openstreetmap.org/copyright> when using geocoding results. OpenStreetMap data is under ODbL. The frontend displays OpenStreetMap attribution and submits searches only on explicit user action. Do not send confidential information to the public geocoder.

## Deploy on Render

`render.yaml` provides a Web Service blueprint. After reviewing and pushing this feature branch yourself, select that branch when creating the Render service/blueprint; deployment does not require merging into `main`. Set the real User-Agent/contact and frontend origin when Render prompts. No deployment or push is performed by this task.

For manual setup, connect `MityaiLentyai/Club_Imperium` as a Python Web Service, leave the root directory at the repository root, and configure:

```text
Build command: pip install -r configs/requirements.txt
Start command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
Health check path: /api/health
Python version: 3.11.11
```

Set `CORS_ORIGINS` to the exact React origin and `GEOCODING_USER_AGENT` to your app identifier with real contact details. Set `GEOCODING_URL` if using a different compatible provider. Render supplies `PORT`; keep a single instance. The CSV must remain committed and included in the deployment. Render instructions follow its [FastAPI deployment guide](https://render.com/docs/deploy-fastapi), using this repository's `backend.main:app` entrypoint.

After deployment, check `/api/health`, `/docs`, and coordinate scoring. Test address scoring manually with one explicitly submitted Warsaw address after configuring the User-Agent. Health reports process liveness; it does not probe the external geocoder.

Frontend hosting: configure a separate static site with root `frontend/UrbanLens-Warsaw/urbanlens-warsaw`, build command `npm ci && npm run build`, and publish directory `dist`. Set `VITE_API_BASE_URL` to the backend HTTPS origin before building and `CORS_ORIGINS` on the backend to the frontend origin. Rebuild the frontend after environment changes. `render.yaml` configures only the backend. Live frontend address searches retain the existing direct Nominatim integration; backend address routes use the backend provider/contact settings. Map tiles still require access to OpenStreetMap.
