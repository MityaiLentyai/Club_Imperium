# UrbanLens Warsaw — continuation context

## Product

Warsaw Open Data Hackathon 2026, Track 2. Three-person team, 24 hours. Help people inspect an apartment's neighborhood before renting or buying. Journey: address → nearby infrastructure → daily commute → compare homes. Not a tourism or event-discovery product.

## Current implementation

React + TypeScript + Vite + Leaflet. src/main.tsx: UI/state. src/style.css: responsive styles. src/Map.tsx: Leaflet. src/types.ts: data models. src/api.ts: FastAPI client, response adapter and submitted-address geocoding. src/demo.ts: synthetic fixtures. src/geo.ts: Haversine straight-line distances. tests/analysis.test.mjs: six meaningful tests. No backend is bundled.

## User design preferences

User disliked generic dashboards, too much small text, repetitive icons and visually dull screens. Latest revision: powder-blue panel, navy headline, strong blue action, larger readable text, fewer labels and generous spacing. Keep the map on the right on desktop. Expand results down the page, not in a tiny sidebar. Stack search and map on mobile. Do not return to dark green. References favor strong visual hierarchy and uncluttered layouts. Scope future changes to user requests.

## Features

Address and manual map selection, radius, category filters, neighborhood report, expandable lists, university/work destination distance and two-home comparison. Demo explicitly labels synthetic objects; map is real. Live exclusively requests POST /analyze at VITE_API_BASE_URL. Errors never silently fall back to demo. Nominatim uses explicit submitted queries, caching and per-client throttling, not autocomplete. At scale use a centrally rate-limited geocoder or replacement provider. Comparison is in-memory and retains each home's selected radius. Reload clears it.

## Architecture

Frontend → separate Python FastAPI → separate data-science module → processed CSV/JSON/GeoJSON. No second backend, database or auth by default. Final API contract pending: adapt src/api.ts. Planned mandatory source: Warsaw Open Data stops. OSM amenities may be supplied by the backend. Real datasets are not bundled. Transit itineraries and actual walking routing await backend support.

## Data honesty

No arbitrary lifestyle/AI score. Never invent lines, travel times, parking availability or opening hours. Distinguish missing data from zero, walking from straight-line distances and demo from live data. Keep OSM attribution, sources and timestamps when returned. Parking remains unavailable without reliable backend data. Destination line is straight geometry, not a pedestrian route.

## Validation and limits

Export has a successful TypeScript/Vite production build and six passing tests. Browser visual QA was unavailable in the original environment: do not claim it was performed. Check desktop/mobile, map, search, filters, reports, commute and comparison in a real browser before broader delivery. API integration remains pending the team's backend.

## Portable export

The folder contains full frontend source. Hosting identity, Git credentials, node_modules and dist are excluded. Published reference: https://urbanlens-warsaw-neighborhood.blondwave4.chatgpt.site.
