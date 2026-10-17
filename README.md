# Warsaw LifeScore

Warsaw Open Data hackathon project (`MityaiLentyai/Club_Imperium`). The FastAPI backend scores transport accessibility using the committed `data/stops_clean.csv` dataset. It supports coordinates or a Warsaw address for integration with the team's React frontend.

The current Mobility Score is a preliminary 0–100 metric based on straight-line distance to the nearest stop and stop group density. It does not measure travel time or service frequency. No other LifeScore categories are implemented yet.

## Install and run locally

Use Python 3.11. From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
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
| `POST /api/score` | JSON `latitude`, `longitude` | Location, Mobility Score, transport features |
| `POST /api/score/address` | JSON `address` | Score response with resolved address in `location` |

Coordinates must be within latitude −90…90 and longitude −180…180. Address inputs must contain 3–300 characters after trimming. Geocoding additionally normalizes internal whitespace. Coordinate scoring retains global coordinate validation for compatibility; its Warsaw dataset is only meaningful near Warsaw.

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

Example `/api/score` response for the coordinates above, calculated using the committed CSV:

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

React can use the deployed backend's HTTPS URL (locally `http://localhost:8000`):

```javascript
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
| `PORT` | On Render | Render supplies it; local launch uses port 8000. |
| `PYTHON_VERSION` | In Render config | `3.11.11` in `render.yaml`. |

There are no API keys or credentials in the example configuration. CORS allows GET/POST and JSON headers; it is browser access configuration, not authentication.

## Nominatim usage and limits

Read the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before deploying. This app uses it only for explicitly submitted address searches. Public Nominatim permits at most one request per second across the whole application, requires an identifiable User-Agent, caching, and visible OpenStreetMap attribution. Do not connect this endpoint to autocomplete, bulk geocoding, or periodic searches.

The backend serializes outbound requests, spaces request starts by at least 1.1 seconds, and caches successful results and not-found responses for 24 hours, up to 500 entries with least-recently-used eviction. Concurrent identical searches share the cached result. Provider failures are not cached. Cache and limiter live in memory: **use one worker and one service instance**. Restarts clear the cache; scaling or heavier usage requires shared caching/rate limiting or a suitable provider. This public hackathon API has no authentication or per-user quotas.

Queries are constrained to Poland and a conservative Warsaw bounding box; responses are checked against that box and city/town/village fields when supplied. This rejects clearly foreign results, but is not an exact municipal-boundary check. No new boundary dataset is introduced.

The frontend must visibly display “© OpenStreetMap contributors” linked to <https://www.openstreetmap.org/copyright> when using geocoding results. OpenStreetMap data is under ODbL. This backend task does not change frontend files; the frontend team must add that attribution and submit searches only on explicit user action. Do not send confidential information to the public geocoder.

## Deploy on Render

`render.yaml` provides a Web Service blueprint. After reviewing and pushing this feature branch yourself, select that branch when creating the Render service/blueprint; deployment does not require merging into `main`. Set the real User-Agent/contact and frontend origin when Render prompts. No deployment or push is performed by this task.

For manual setup, connect `MityaiLentyai/Club_Imperium` as a Python Web Service, leave the root directory at the repository root, and configure:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1
Health check path: /api/health
Python version: 3.11.11
```

Set `CORS_ORIGINS` to the exact React origin and `GEOCODING_USER_AGENT` to your app identifier with real contact details. Set `GEOCODING_URL` if using a different compatible provider. Render supplies `PORT`; keep a single instance. The CSV must remain committed and included in the deployment. Render instructions follow its [FastAPI deployment guide](https://render.com/docs/deploy-fastapi), using this repository's `backend.main:app` entrypoint.

After deployment, check `/api/health`, `/docs`, and coordinate scoring. Test address scoring manually with one explicitly submitted Warsaw address after configuring the User-Agent. Health reports process liveness; it does not probe the external geocoder.
