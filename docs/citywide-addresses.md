# Citywide address handling — backend integration

This chapter supersedes older rectangular-boundary and external-only geocoding descriptions. Backend/Data Science changes only; Mobility and LifeScore formulas, dependencies and frontend files are unchanged.

## Verified sources and coverage

The committed public municipal WFS snapshot contains **126,923 unique address points** from `wfs:PUNKTY_ADRESOWE_WGS84`, captured at **2026-10-17T22:05:13Z** (18 October in Warsaw). Source endpoint: <https://wfs.um.warszawa.pl/serwis>. The request was one unfiltered `GetFeature`, WFS 1.1.0, GML2, with `maxFeatures=200000`, a 128 MB response ceiling and a 120-second timeout. No API key, retries or citywide series of requests was used. The response is below the cap; there is no independent upstream total proving current completeness. All records have usable coordinates inside the published district union, with no rejected records or duplicate IDs.

| District | Address points |
| --- | ---: |
| Bemowo | 5,265 |
| Białołęka | 15,724 |
| Bielany | 5,560 |
| Mokotów | 9,527 |
| Ochota | 2,332 |
| Praga-Południe | 6,872 |
| Praga-Północ | 1,444 |
| Rembertów | 5,365 |
| Śródmieście | 3,418 |
| Targówek | 6,780 |
| Ursus | 4,050 |
| Ursynów | 8,637 |
| Wawer | 26,334 |
| Wesoła | 6,741 |
| Wilanów | 6,596 |
| Włochy | 6,502 |
| Wola | 3,728 |
| Żoliborz | 2,048 |

`data/geography/` retains the compressed original GML, source hashes, processing report, content-addressed compressed SQLite index and 18 reproducible verification samples. The runtime expands the approximately 19 MB compressed index to an approximately 88 MB read-only database in a private temporary directory once per process. Allow disk space and first-request initialization time; lookup does not unpack the full XML source. Missing or corrupt optional address files fall back to Nominatim.

Official district polygons form an approximately **516.724 km²** city union. All 18 district names, polygon validity and plausible total area are checked before use. Published source update labels are 2017/2018: this is verified official published geometry, not a claim of a current legal survey. Boundary points are included with a documented **0.5 m** precision band. If geometry is unavailable or corrupt, the existing latitude 52.0–52.4 / longitude 20.75–21.3 envelope remains a degraded fallback, explicitly identified in `area_validation`.

Existing infrastructure coverage is unchanged: 6,652 transport platforms, line observations for only 15 platforms; 60 named parks, 18 parking points and 291 sports points. Named parks are not a verified complete green-space inventory; parking and sports inventories are partial. Full source processing is not proof of a complete inventory of real-world facilities. See [the coverage report](data-coverage-final.md).

## Lookup and API contract

The local index is tried before Nominatim and before its cached misses. Official canonical names and official short-name aliases support case/spacing normalization, Polish diacritic fallback and recognized street abbreviations (`ul.`, `al.`, `pl.`). Building suffixes, leading zeroes, slash/range notation and literal sub-building periods are preserved. Explicit apartment labels can be removed; a bare slash is not assumed to mean an apartment. A district qualifier can disambiguate a match. Distinct matching coordinates are rejected rather than arbitrarily selected.

**Known limitation intentionally left for later:** an existing canonical audit found 20 round-trip normalization mismatches for the numeric street name `ulica Bitwy Warszawskiej 1920 r.`. These were not investigated further in this delivery. One ambiguous district-qualified alias key is also recorded. The retained `address-lookup-audit.json` is evidence, not a promise that every free-text address resolves. Future addresses, unsupported spelling variants and ambiguous names may still require direct map coordinates.

| Endpoint | Integration behavior |
| --- | --- |
| `GET /api/health` | Existing `{"status":"ok"}` liveness response. |
| `GET /api/geocode?address=...` | Existing `{address,latitude,longitude}` object; municipal lookup needs no external geocoding configuration. |
| `POST /api/score` | Existing coordinate request; independent of address lookup. Adds `area_validation` evidence to the existing response. |
| `POST /api/score/address` | Existing address request and score payload, including resolved `location.address`. |
| `POST /api/commute` | Existing origin/destination coordinate request and baseline/profile statuses; routes are provider estimates, transit remains unavailable. |
| `POST /api/compare` | Existing exactly-two-locations request, shared weights and optional routing behavior. |

No fields were removed or renamed. Intentional validation tightening: an address without a building number gives **422**, as does an ambiguous local match; points outside available official city geometry give **422**, including points formerly accepted by the rectangular envelope. A valid point selected on a map can always be submitted directly, regardless of geocoder failure, subject to mandatory transport availability.

Nominatim remains the fallback for local misses or unavailable index. It requires an identifying `GEOCODING_USER_AGENT`. A fallback result must be inside Warsaw, have a compatible locality/country and an exact normalized requested house number; street centroids or different buildings are rejected. Existing **404/502/503/504** responses remain relevant. Missing-house input does not contact the external provider. Application error `detail` may be a string; validation errors use a list. HTTP 200 commute responses can contain unavailable profiles after provider failure; inspect profile status.

Missing optional parks, parking, sports or line observations do not prevent coordinate scoring. Missing infrastructure counts/distances are **null**, not zero. An available snapshot can return zero nearby verified objects while its `datasets` entry still declares `coverage_status: partial` (or `unverified` for green), `citywide_inventory_complete: false` and `count_basis: verified_snapshot_objects`. A missing dataset retains `status: unavailable`. Do not present a snapshot zero as proof that no facilities exist. LifeScore remains explicitly partial over eligible available scores; Mobility is still the only numeric category.

`/api/data/status` remains absent (404). Exact six-endpoint request/response examples are in [citywide-http.json](examples/citywide-http.json); older provider/error examples remain in [backend-http.json](examples/backend-http.json). OpenAPI documents request validation; successful response payloads are still specified through examples and regression tests rather than detailed response models.

## Reproduction and local verification

From the repository root with the existing Python 3.11 environment and requirements installed:

```bash
python -m data_science.ingest_addresses --offline
python -m pytest -q
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Offline processing verifies and rebuilds the index from the saved source and validated boundaries, preserving source freshness metadata. Only when explicitly refreshing the public source, use `python -m data_science.ingest_addresses --refresh-source`; this makes one bounded request and retains content-addressed evidence. Existing data is not deleted. The committed normalized boundary file and its compressed raw GML provide the boundary evidence; address refresh does not silently refresh boundary geometry.

```bash
curl --get http://127.0.0.1:8000/api/geocode --data-urlencode 'address=ulica Borecka 4B, Białołęka'
curl -X POST http://127.0.0.1:8000/api/score/address -H 'Content-Type: application/json' -d '{"address":"ulica Borecka 4B, Białołęka"}'
curl -X POST http://127.0.0.1:8000/api/score -H 'Content-Type: application/json' -d '{"latitude":52.327116,"longitude":21.006675}'
```

Regression coverage includes all 18 districts, ASCII/Polish variants, arbitrary interior grid points independent of source addresses, boundary precision, invalid and missing numbers, ambiguity, incomplete/missing optional data, corrupt local index and provider failures. The Python suite passes **295 tests**, with one existing Starlette/httpx deprecation warning.

Existing Render startup configuration is unchanged: install `configs/requirements.txt`, run `backend.main:app` with `$PORT` and one worker, use `/api/health`. Environment variables must be exported by the host; `.env` is not automatically loaded. `CORS_ORIGINS` remains an explicit comma-separated allowlist. No deployment or production configuration change was made. Local macOS verification does not certify a Render Linux deployment.

### Local HTTP verification, 18 October 2026 Warsaw time

A fresh single-worker Uvicorn process resolved the saved representative address in **every district** with `GEOCODING_USER_AGENT` unset, then returned matching address/coordinate scores for all 18. All six endpoints returned successful responses. First municipal lookup took **2,190 ms** including index initialization; subsequent sample lookups took **1.63–2.08 ms**. Twenty warm HTTP score requests had median **22.63 ms**, maximum **26.25 ms**. These are local observations, not a deployment SLA.

For `(52.2297, 21.0122)` → `(52.239, 21.022)`, the public routing provider returned walking **1,771.2 m / 23.6 min** and driving **2,647.2 m / 5.1 min**; transit was explicitly unavailable. These are dated provider estimates with no live traffic. Missing building number and a point outside the municipal polygon returned 422; `/api/data/status` returned 404. Configured localhost CORS preflight returned 200 with its allow-origin header; an unrelated origin returned 400 without it. Provider failure paths are tested offline rather than induced against the live service.

### Frontend handoff against current `origin/main`

The redesigned `frontend/src/api.ts` was inspected read-only. It already calls `/api/score`, `/api/score/address` and `/api/geocode`, accepts the existing payload fields and ignores additive metadata. Its geographic envelope contains the entire verified city union. However, its adapter does not expose `coverage_status`, `citywide_inventory_complete`, `area_validation` or LifeScore to the UI: displaying partial-inventory warnings requires frontend team integration. Its current 20-second fetch timeout can also expire before two sequential slow routing profiles finish; consumers of `/api/commute` should handle that explicitly. No frontend changes are included here.
