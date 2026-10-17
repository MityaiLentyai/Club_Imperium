# UrbanLens Warsaw

React + TypeScript + Leaflet frontend for a separately maintained FastAPI backend. No database, authentication, or second backend.

## Run

`npm install`, then `npm run dev`. Production: `npm run build`.

## Connect FastAPI

Copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` to your HTTPS API origin. Rebuild after changes. Allow the deployed frontend origin in FastAPI CORSMiddleware. Local HTTP backends cannot be called from an HTTPS deployment. Live errors never fall back to demo data.

`src/api.ts` owns requests and the response adapter. Finalize this file with your backend developer. `POST /analyze` accepts `{latitude, longitude, radius_m, destination: {latitude, longitude, label} | null}`. Canonical response:

```json
{
  "location": { "label": "Selected address" },
  "places": [
    {
      "id": "1",
      "category": "transport",
      "label": "Stop name",
      "latitude": 52.22,
      "longitude": 21.01,
      "distance_m": 120,
      "distance_type": "straight_line",
      "lines": ["10"]
    }
  ],
  "unavailable": ["parking"],
  "sources": [
    { "name": "Warsaw Open Data", "retrieved_at": "2026-10-17T12:00:00Z" }
  ],
  "retrieved_at": "2026-10-17T12:00:00Z",
  "commute": {
    "distance_m": 1700,
    "duration_minutes": 22,
    "mode": "walking",
    "status": "available"
  }
}
```

Categories: transport, grocery, pharmacy, green, parking. `places` declares a complete category collection; use `unavailable` for missing categories. The adapter also accepts grouped `stops`, `shops`, `pharmacies`, `parks`, `parking` arrays (or `nearby_` prefixes); absent groups remain unavailable. Explicit empty arrays mean no objects returned. Distances without a type remain labeled unspecified. Route geometry is not currently rendered; the destination line is straight-line geometry only. Transit itinerary rendering awaits the final backend contract.

## Data and demo

Demo fixtures are synthetic and explicitly labeled everywhere. They are placed relative to the selected coordinate; computed distances are straight line, not walking estimates. Parking is unavailable. No scores, fabricated transport lines, opening times or live claims. Changing mode clears results and comparisons. Comparisons are held in memory and discarded on reload. Warsaw stop dataset is a planned backend source, not a dataset bundled into this frontend.

Map tiles: OpenStreetMap with visible attribution. Live address searches use Nominatim on explicit submit only, cached in memory, with at least 1.1 seconds between requests per client. This client throttle is suitable for a small manual hackathon demo; shared public deployments need a centrally rate-limited backend geocoder or another provider. No autocomplete. The provider can be replaced using VITE_GEOCODER_URL. No API keys are included.

## Layout

The interface has two states. Initially, the search sits beside a large map. Selecting a search match, a demo address, a map point, or running analysis opens the analysis workspace: search at the upper left, a smaller interactive map at the upper right, and a full-width analysis rectangle underneath. Back to search restores the large map without discarding results.

The lower workspace contains a narrow navigation rail, infrastructure categories and selected-category details. Choose a place to inspect its distance, type and available transport lines. Commute, Compare and Sources remain accessible. Desktop uses one viewport with internal overflow; mobile stacks the sections. Light/Dark persists in localStorage. No backend contracts changed.

## Applying this update

Replace `src/main.tsx` and `src/style.css` in the existing project with the matching files from this archive. Other source files and API contracts are unchanged. Keep your existing local environment settings. Run `npm install` if dependencies are not installed, then `npm run dev` (or `npm run build`). This archive excludes dependencies and build output.
