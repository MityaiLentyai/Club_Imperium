# UrbanLens interface update

Changed: src/main.tsx, src/style.css, README.md, START_HERE_RU.md, PROJECT_CONTEXT.md and the regenerated ALL_SOURCE_CODE.md. UPDATE-NOTES.md is new. API client, map component, fixtures, helpers and backend contracts are unchanged. No dependencies added.

- Desktop viewport shell: map on the right, internal details-panel scrolling.
- Search at the top; no oversized slogan or footer.
- Expandable infrastructure rows with distances and counts.
- Explore / Commute / Compare preserve the selected location.
- Light and dark themes include map tiles, markers, controls, popups, comparison and source dialog. Preference persists locally.
- Demo data remains labeled. Parking, air quality and noise remain unavailable where unsupported.
- Responsive mobile layout, keyboard focus trap and Escape support in the source dialog.
- Stale async responses are ignored after changing selection, radius or mode.

## Apply

Replace src/main.tsx and src/style.css in your existing frontend; keep your local environment settings. Or extract this source archive, run npm install, then npm run dev.

## Validation and limitations

npm run build passed (TypeScript and Vite). npm test passed all 6 existing tests.
Browser interaction and visual viewport checks could not run: Chromium was unavailable and its download failed. Check 1440x900, 1366x768, mobile, theme persistence, map controls, commute and comparison locally before presenting.

Live analysis requires your FastAPI URL in VITE_API_BASE_URL. No backend is included. Travel times depend on the backend; the destination line and client-calculated distance are straight-line only. Air quality and noise are not part of the current API contract.

## Two-state layout revision

Implemented the supplied two sketches: large starting map, compact upper-right map after selection, search above the lower full-width analysis workspace, category navigation and place detail panel. All 6 tests and the production build passed again. Browser visual verification remains pending.
