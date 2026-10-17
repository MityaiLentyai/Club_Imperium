# OLO — Warsaw neighborhood explorer (frontend 2)

A redesigned frontend for the Warsaw LifeScore backend. React + TypeScript + Vite + Leaflet.

## Run

```bash
cd frontend
npm ci
cp .env.example .env.local   # optional: points Live mode at the FastAPI backend
npm run dev                  # http://localhost:5173
```

Without `VITE_API_BASE_URL` the app starts in Demo mode (made-up places around a real map). With it, the app starts in Live mode. The mode can be switched in **Data & sources**.

```bash
npm test        # model tests (API adapter, demo, geo helpers)
npm run build   # type check + production build
```

## Screens

- **Start** — address search, example addresses, radius and a large map. Clicking the map proposes a spot; the home moves only after "Explore this spot".
- **Explore** — left panel with the address summary (Mobility score and LifeScore with adjustable priorities in Live, nearest stop, stops in radius), then two tabs:
  - **Nearby places** — category chips toggle map layers and list groups; the chip color is the map legend. Clicking a row highlights its pin; clicking a pin selects its row. Platforms of one stop collapse into one row.
  - **Commute** — a work/university destination with straight-line distance, plus walking and driving routes on request (Live).
- **Compare** — top-level tab. Two homes in Live (backend comparison) or up to three in Demo, the better value per row is marked, and homes can be added directly on this page. On phones the table becomes one card per metric.

## Backend contract

Live mode implements the contract in `docs/frontend-integration-check.md`: `/api/score`, `/api/score/address`, `/api/geocode`, `/api/commute`, `/api/compare` and `/api/health`. The client and response adapters live in `src/api.ts`; `tests/model.test.mjs` checks them against the recorded examples in `docs/examples/backend-http.json`. A category counts as available only when its dataset status is `available`; otherwise it shows "No data yet". Routes are fetched only when the user asks, because they send both points to the FOSSGIS OSRM service.
