# UrbanLens Warsaw

React + TypeScript + Leaflet frontend for a separately maintained FastAPI backend. No database, authentication, or second backend.

## Run

`npm install`, then `npm run dev`. Production: `npm run build`.

## Connect FastAPI

Copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` to your HTTPS API origin. Rebuild after changes. Allow the deployed frontend origin in FastAPI CORSMiddleware. Local HTTP backends cannot be called from an HTTPS deployment. Live errors never fall back to demo data.

`src/api.ts` calls `POST /api/score` with `{latitude, longitude, radius_m}` and preserves the real Mobility Score and fixed-radius features in the report and comparison. The backend returns:

- `location`: requested coordinates (and resolved `address` for `/api/score/address`).
- `scores.mobility`: unchanged 0–100 score.
- `features`: nearest-stop distance and unique stop groups within fixed 500/1000 m radii.
- `radius_m`: selected map radius (1–2000 m, default 1000).
- `places`: real transport platforms with stable `stop_id:platform` IDs, names in `label`, coordinates, metre distances, and `distance_type: "straight_line"`.
- `nearby`: total within radius, response limit (200), and truncation flag.
- `unavailable`: grocery, pharmacy, green, parking. Empty transport means no platforms within radius; it does not mean unavailable data.
- `sources`: the committed transport CSV source.

The selected radius changes markers, not the score formula. Score density counts unique stop groups; marker counts refer to individual platforms. No grocery/pharmacy/park/parking data or journey times are invented. Destination comparisons remain straight-line only.

Address searches call the backend `GET /api/geocode?address=...`; its `{address, latitude, longitude}` response becomes one selectable frontend Location. Backend caching and rate limiting apply. Errors retain backend messages and never fall back to fixtures.

Backend setup and the complete API contract are documented in the root README. The frontend folder is `frontend/urbanlens-warsaw`. From this folder:

```bash
npm ci
cp .env.example .env.local
npm run dev -- --port 5173 --strictPort
# Verification:
./node_modules/.bin/tsc --noEmit
npm test
npm run build
```

For static hosting, use build `npm ci && npm run build`, publish `dist`, and set `VITE_API_BASE_URL` before building. The root Render blueprint deploys only the backend.

## Data and demo

Demo fixtures are synthetic and explicitly labeled everywhere. They are placed relative to the selected coordinate; computed distances are straight line, not walking estimates. Parking is unavailable. No scores, fabricated transport lines, opening times or live claims. Changing mode clears results and comparisons. Comparisons are held in memory and discarded on reload. Live transport platforms and scores use the backend's committed Warsaw stop dataset; it is not bundled into the frontend.

Map tiles use OpenStreetMap with visible attribution. Live address searches go exclusively through the backend on explicit submit. Do not configure a frontend Nominatim URL; provider configuration belongs on the backend. Map tiles and live geocoding require internet access.

## Layout

Powder-blue search panel, navy editorial typography, and a clear blue primary action. Short labels, larger readable text, and expandable nearby-place sections reduce initial density. Desktop map stays on the right. Reports expand vertically underneath. Mobile stacks search above the map. Typed addresses are resolved before primary analysis; ambiguous matches require selection.
