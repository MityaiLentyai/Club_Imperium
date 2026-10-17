# Citywide OpenStreetMap groceries and pharmacies

Backend and Data Science only. Existing score formulas and comparison metrics are unchanged; no new numeric category score or routing behavior is introduced. `/api/score` and `/api/score/address` expose the same additive infrastructure fields, and `/api/compare` embeds them in each location without adding comparison rows.

## Source and reproducibility

Source catalogue: [Geofabrik Mazowieckie](https://download.geofabrik.de/europe/poland/mazowieckie.html). The complete dated [mazowieckie-261016.osm.pbf](https://download.geofabrik.de/europe/poland/mazowieckie-261016.osm.pbf), **300,997,920 bytes**, was downloaded once, along with its provider MD5. SHA256: `3053758704befb8d4824f25a2bf25f841dd3a62cab3f37c18baa0e19707ad5a5`; provider MD5: `51e3c3a99056fabba1cf15bb3af806e8`. The PBF stays in the ignored `.local/osm-source/` cache and is not committed.

Timestamp meanings:

- `source_timestamp`: **2026-10-16T20:21:21Z**, the PBF header replication timestamp; it dates the extract, not a facility survey.
- `http_last_modified`: **2026-10-17T00:14:38Z**, when Geofabrik published the file.
- `retrieved_at`: **2026-10-17T22:48:04.085870Z**, the actual local download time (18 October in Warsaw).
- `processed_at`: snapshot normalization time; it can change when rebuilding the same source.
- `osm_timestamp`: each original OSM object's last edit timestamp, not confirmation that a business is currently open. Merged source objects retain their own timestamps.

Install existing runtime requirements plus the separate ingestion-only requirement in a project virtual environment:

```bash
python -m pip install -r configs/requirements.txt -r configs/requirements-osm.txt
python -m data_science.download_osm_extract \
  --url https://download.geofabrik.de/europe/poland/mazowieckie-261016.osm.pbf
python -m data_science.ingest_osm_retail \
  --extract .local/osm-source/mazowieckie-261016.osm.pbf \
  --source-manifest .local/osm-source/mazowieckie-261016.osm.pbf.json
python -m pytest -q
```

The downloader accepts only dated official Mazowieckie URLs. It uses one MD5 request and one full-file request, no retries, a 500 MB ceiling and a five-minute streaming deadline. A valid cached file is reused with its original freshness metadata; corrupt cached files are preserved and reported. Reprocessing the saved PBF needs no network. Choose a newer dated extract explicitly when refreshing; there is no automatic ingestion during requests or startup.

PyOsmium **4.3.1** is required only by ingestion/tests of OSM parsing. The backend needs only its existing runtime requirements; Render configuration and runtime dependency pins are unchanged. No system-wide installation is needed. In this verification PyOsmium was installed only in the worktree's ignored `.local/osm-deps/` directory. If using that arrangement, prefix Python commands with `PYTHONPATH=.local/osm-deps`.

Processing reads the whole extract, with all nodes available to the location cache and both relation/way passes available to the area assembler. An output tag filter reduces Python callbacks after internal geometry processing. Selected tags are `shop=supermarket`, `shop=convenience`, `shop=grocery`, `amenity=pharmacy`. A pharmacy carrying a selected shop tag is counted once as a pharmacy. Other shop/medical tags are outside this inventory.

The existing verified official Warsaw district union is mandatory during ingestion. Its retained 2017/2018 source update labels and limitations still apply. Geometries are projected from EPSG:4326 into **EPSG:2180**, intersected with the municipal union, validated and transformed back. Polygons and multipolygons retain holes; their metric representative point is used for markers. Distances use the retained projected facility geometry, so a point inside a shop polygon has zero distance. They are straight-line geometric distances, not walking routes or distances to a verified entrance.

## Exact processing results

The complete regional extract contained **8,555 selected source objects**: **6,279 nodes**, **2,276 ways**, **0 relations** with the requested tags. **5,723** selected objects were outside Warsaw. There were **0 geometry failures, 0 unassembled selected areas and 0 clipped boundary-crossing facilities** in this snapshot. **2,832** objects remained before deduplication; one corresponding node/polygon pair was merged, leaving **2,831 facilities**:

| OSM kind | Facilities |
| --- | ---: |
| supermarket | 500 |
| convenience | 1,716 |
| grocery | 32 |
| pharmacy | 583 |
| All groceries, including supermarkets | 2,248 |

Final primary representations: **2,537 nodes and 294 ways**. Although the real selected data contains no relations, a synthetic OSM fixture verifies a multipolygon relation assembled from open member ways, two outer components and an inner hole. No relations were invented to increase coverage.

Deduplication merged `node/2343054807` into `way/34571702`. Merging requires the same detailed kind, compatible known addresses and matching normalized name or brand, plus containment/equal geometry or an explicit relation/member-way link. Nearby chain branches, conflicting units, unnamed facilities and distinct identities remain separate. Both original records, all original tags and timestamps survive in `source_objects`. This conservative rule can leave unresolved duplicates; it does not claim perfect entity matching.

**162** facilities lack `name`; markers use brand or kind as a display fallback while `name` remains null. **2,205** have opening-hours tags; **1,708** have at least one address tag; **0** lack an object timestamp. Tags are retained as provided, without inventing addresses, interpreting schedules or claiming live availability.

| District | Supermarket | Convenience | Grocery | Pharmacy | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bemowo | 27 | 82 | 1 | 32 | 142 |
| Białołęka | 46 | 108 | 0 | 32 | 186 |
| Bielany | 34 | 77 | 0 | 35 | 146 |
| Mokotów | 49 | 254 | 9 | 69 | 381 |
| Ochota | 21 | 77 | 1 | 32 | 131 |
| Praga-Południe | 43 | 157 | 2 | 61 | 263 |
| Praga-Północ | 15 | 65 | 1 | 24 | 105 |
| Rembertów | 10 | 14 | 0 | 7 | 31 |
| Targówek | 28 | 97 | 0 | 35 | 160 |
| Ursus | 18 | 75 | 0 | 16 | 109 |
| Ursynów | 37 | 121 | 4 | 46 | 208 |
| Wawer | 31 | 48 | 0 | 25 | 104 |
| Wesoła | 15 | 15 | 0 | 8 | 38 |
| Wilanów | 17 | 37 | 3 | 14 | 71 |
| Wola | 47 | 207 | 4 | 55 | 313 |
| Włochy | 21 | 61 | 2 | 15 | 99 |
| Śródmieście | 30 | 170 | 3 | 59 | 262 |
| Żoliborz | 11 | 51 | 2 | 18 | 82 |

## Response contract

All values below are additional keys in `features`. Distances are metres; counts use the requested integer radius of 1–2,000 m. Nearest distances consider the entire clipped city snapshot, independently of radius.

| Distance | Radius count | Included kinds |
| --- | --- | --- |
| `nearest_supermarket_m` | `supermarkets_within_radius` | supermarket |
| `nearest_grocery_convenience_m` | `grocery_convenience_within_radius` | convenience + grocery, excluding supermarkets |
| `nearest_grocery_m` | `grocery_stores_within_radius` | all three grocery kinds, including supermarkets |
| `nearest_pharmacy_m` | `pharmacies_within_radius` | pharmacy |

For `(52.2297,21.0122)` with a 1,000 m radius, the saved snapshot gives supermarket **278.3 m / 12**, grocery/convenience **109.8 m / 81**, all groceries **109.8 m / 93**, pharmacy **141.3 m / 25**. These are snapshot observations, not assertions about all operating businesses.

Missing/corrupt snapshot: all eight new feature keys are **null**; `datasets.grocery` and `datasets.pharmacy` report `status: unavailable`, and both categories appear in `unavailable`. Existing transport scoring still succeeds. Valid snapshot with no matching nearby objects: radius count is **0**, with `status: available`; nearest is null only when that kind has no objects anywhere in the loaded snapshot. A zero means zero mapped snapshot objects, not proof of no real facilities.

Available dataset entries include `source_url`, extract `source_sha256` and normalized snapshot `sha256`, `source_timestamp`, `retrieved_at`, `processed_at`, attribution/license URLs, `coverage_status: osm_snapshot`, `citywide_inventory_complete: false`, `count_basis: mapped_osm_snapshot_facilities`, `snapshot_facilities`, radius `total`, marker `limit` and `truncated`. The normalized snapshot is checksummed, bounded while decompressing and cached by immutable manifest generation. Replacing the manifest reloads it; a missing/corrupt optional dataset never triggers live recovery.

New `places` use the existing `category: grocery` or `category: pharmacy`, `label`, `latitude`, `longitude`, `distance_m`, `distance_type: straight_line`. Additions include `kind`, nullable original `name`, `osm_identifier` (for example `way/34571702`), string `osm_id`, `osm_type`, original `tags`, `address` as an object of `addr:*` suffixes, nullable `opening_hours`, `osm_timestamp`, and `source_objects`. IDs are namespaced, for example `osm:way/34571702`. `distance_basis: osm_facility_geometry` distinguishes footprint distances from marker distances.

At most **50 grocery and 50 pharmacy markers** are returned, ordered by distance and OSM identifier within each category. Exact counts are computed before marker truncation. Use feature counts and dataset totals rather than the number of returned markers. Existing top-level `nearby` continues to describe transport markers only; category-specific truncation lives in `datasets`. Existing fields, transport marker limit, scoring formulas, eligible LifeScore categories and comparison rows retain their meanings. `grocery` and `pharmacy` are not accepted weight keys because no numeric scores exist for them; existing weight validation remains unchanged.

[Complete captured HTTP requests/responses](examples/osm-retail-http.json) cover coordinate scoring, address scoring and comparison. For local checks:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
curl -X POST http://127.0.0.1:8000/api/score \
  -H 'Content-Type: application/json' \
  -d '{"latitude":52.2297,"longitude":21.0122,"radius_m":1000}'
curl -X POST http://127.0.0.1:8000/api/score/address \
  -H 'Content-Type: application/json' \
  -d '{"address":"Marszałkowska 83","radius_m":500}'
```

## License and frontend handoff

**© OpenStreetMap contributors**, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), via Geofabrik. The complete normalized derivative database and original-tag evidence are distributed free of charge in [`data/osm/`](../data/osm/README.md), with source URLs and the reconstruction method. Preserve the license/attribution notices and offer the derivative data or the alterations required by ODbL when using it publicly. See [OSM copyright](https://www.openstreetmap.org/copyright) and [attribution guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines).

The API includes attribution in `sources` and dataset metadata. The frontend team must render visible attribution with the copyright/license links, provide access to the derivative dataset, and show coverage/truncation warnings. Existing grocery/pharmacy category conventions are compatible; no frontend files were modified. OSM is community mapping, not an official exhaustive inventory. No business-operation, opening-now, stock, accessibility or dispensing guarantees are inferred.

## Verification results

All-district HTTP verification used a fresh single-worker Uvicorn process with no PyOsmium on its runtime import path and no external geocoding configuration. Both scoring endpoints returned matching features for all 18 representative municipal addresses/coordinates. Comparison returned the existing metrics and normalized Mobility contribution. The first complete coordinate score took **216.42 ms**; 30 warm requests had median **28.47 ms**, p95 **30.00 ms**, maximum **30.29 ms**. These are local macOS observations, not production latency guarantees.

The committed normalized snapshot is **377,980 compressed bytes**. Reprocessing the entire saved PBF into a separate local output produced identical normalized features, including source tags and deduplication results; processing timestamps and therefore archive hashes may differ between runs. Source freshness remains unchanged on offline rebuild.

Tests cover all districts, metric projection, nodes/ways, multipolygon assembly with holes, conservative duplicate handling and linked relation/member ways, boundary clipping, exact counts with marker truncation, empty radius, missing/corrupt snapshots, checksum/byte-limit download failures, cache reuse, both score APIs, existing LifeScore/Compare contracts and unsupported numeric grocery weights. Run the suite with ingestion dependencies installed so the parser fixtures execute; without PyOsmium those parser-only tests are skipped. Existing external-HTTP blocking remains active throughout the test suite.

Final complete suite: **332 passed**, **0 skipped**, one existing Starlette/httpx deprecation warning, Python 3.11.8. The source cache is retained locally. Geofabrik may remove older daily extracts under its retention policy; the dated URL and hashes identify this input but do not guarantee permanent upstream hosting. Preserve the cached PBF for long-term reprocessing. The complete normalized derivative database remains distributed in the repository independently of upstream PBF retention.
