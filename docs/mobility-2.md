# Mobility 2.0: observed transport line availability

The original Mobility Score and its `features` are unchanged. Line availability
is an optional, separate set of observations, not another score.

## Source and attribution

Source: Miasto Stołeczne Warszawa / Zarząd Transportu Miejskiego,
**Linie dostepne na przystanku**, Warsaw Open Data, Creative Commons Attribution
(as identified by the catalogue).

- Catalogue: https://dane.um.warszawa.pl/en/catalogue/8eb065b6-f3a0-41d4-a842-732c6c1c3063
- Official example: https://dane.um.warszawa.pl/files/ztm_linie_dostepne_na_przystanku_pw.json
- Endpoint: `POST https://dane.um.warszawa.pl/api/action/get_ztm_lista_linii_na_przystanku`
- JSON request: `{"busstopId":"5070","busstopNr":"03"}`
- Header: `Authorization: <token>` (not a query-string credential).

The documented response is a list of objects, each with a `values` list of
`{"key":"linia","value":"23"}` entries. The parser rejects malformed/error
payloads; only an empty top-level list means a successful result with no lines.
The documented example is saved as a test fixture, never as observations.

## Secure configuration

Set `WARSAW_API_TOKEN` in the environment of the manual ingestion process.
Do not put the token in frontend configuration. Python reads it with
`os.getenv("WARSAW_API_TOKEN")`; it does not automatically load `.env` files.
Use your shell or deployment secret manager to supply it without committing it.
Never put it in `VITE_` variables, the client, a command-line argument or logs.
Existing backend endpoints work without this token. The backend never fetches
line data while scoring and never returns the token.

The complete-MVP branch incorporates the existing Mobility 2.0 local snapshot:
15 successfully observed platforms across three stop groups, out of 6,652
platforms in the transport dataset. It was retrieved on 2026-10-17; the exact
per-platform timestamps are retained. No new line API calls were made for this
integration. This deliberately small sample is not representative of Warsaw.
The original branch, cache, reports and unfinished changes remain untouched.

## Small, bounded, resumable ingestion

Run from the repository root using the existing Python environment. Every
invocation selects at most 20 unique platforms; the default is 15. Selection uses
stable lexicographic `(stop_id, platform)` order, not a claim of representative
coverage. To target your demo address, use the stop/platform identifiers returned
by `/api/score` and select them explicitly.

Preview 15 selected platforms without a token, requests, or filesystem writes:

```bash
.venv/bin/python -m data_science.ingest_stop_lines --limit 15 --dry-run
```

After configuring the token, an operator can explicitly fetch that bounded sample:

```bash
.venv/bin/python -m data_science.ingest_stop_lines --limit 15
```

Resume the same sample with the same command. Successfully cached platforms,
including known-empty lists, are skipped. Failed/missing platforms are retried.
Fetch the next bounded batch or target specific real platform IDs:

```bash
.venv/bin/python -m data_science.ingest_stop_lines --limit 15 --offset 15 --dry-run
.venv/bin/python -m data_science.ingest_stop_lines --limit 15 --offset 15
.venv/bin/python -m data_science.ingest_stop_lines --platform 5070:03 --dry-run
.venv/bin/python -m data_science.ingest_stop_lines --platform 5070:03
```

Refresh a selected batch, including previous successful observations:

```bash
.venv/bin/python -m data_science.ingest_stop_lines --limit 15 --refresh
```

Do not automate these batches into a full-city download without approval.
The catalogue advertises daily updates: refresh deliberately, retain retrieval
dates, and do not interpret cached data as a live service guarantee.

Requests are sequential, spaced at least 1.1 seconds apart, with a 10-second
HTTPX timeout on each network phase, and at most three attempts per platform.
Network failures, timeouts, HTTP 429 and server errors get bounded exponential
backoff. Retry-After is respected; waits over 30 seconds stop retries for that
platform so a later invocation can resume. Other HTTP failures and malformed
responses are not retried. Authentication failures and exhausted rate limiting stop the selected batch.
Only safe error codes are saved, never response bodies or credentials.
Run one ingestion process per cache file at a time.

## Cache and failure states

Default file: `data/stop_lines.csv` (a 15-platform snapshot is included).
Use `--output <path>` for a different cache; scoring reads the default path.
No additional dependencies are required.

Columns:

| Column | Meaning |
|---|---|
| `stop_id`, `platform` | Source identifiers; always strings, including leading zeroes |
| `lines` | JSON-encoded sorted unique string identifiers; `[]` is known-empty |
| `status` | `success` or `error` |
| `retrieved_at` | UTC timestamp of the last successful observation |
| `attempted_at` | UTC timestamp of the latest attempt |
| `error_code` | Empty on success; sanitized failure code otherwise |
| `source_url` | Official catalogue attribution |

The CSV is atomically replaced after each attempted platform. An interrupted run
retains completed records. A failed first request is an `error` record, not `[]`.
A failed refresh retains the previous successful lines and retrieval time, with
an error code identifying the failed latest attempt. Use `--refresh` to retry
those previously successful records. A corrupt cache is preserved and ingestion
refuses to overwrite it; inspect it or choose a different output file.

The API caches parsed records and reloads on file timestamp/size changes.
A missing or unreadable cache does not break scoring. Only records matching
current stop/platform identifiers count toward coverage. Data age is exposed;
there is no automatic expiry or background refresh.

## Spatial calculations and extended API

All spatial calculations use the existing EPSG:2180 stop geometries in metres.
Lines are unioned across platform identifiers: line 23 at five platforms counts
once in a window. Marker radius remains independent of the fixed 500/1,000 m
windows. Feature counts use all eligible platforms, not the 200-marker subset.

Existing `/api/score`, `/api/score/address`, and `/api/geocode` routes remain.
The score responses retain `scores.mobility`, the existing `features`, marker
radius, sorting and limit, and add the following top-level object:

```json
{
  "line_features": {
    "distinct_lines_500m": null,
    "distinct_lines_1000m": null,
    "distinct_lines_radius": null,
    "radius_m": 1000,
    "nearest_stop_lines": null,
    "line_data_coverage": {
      "data_status": "missing",
      "known_platforms": 0,
      "total_platforms": 6652,
      "failed_platforms": 0,
      "refresh_failed_platforms": 0,
      "latest_retrieved_at": null,
      "within_500m": {
        "status": "missing",
        "known_platforms": 0,
        "total_platforms": 12,
        "failed_platforms": 0,
        "refresh_failed_platforms": 0,
        "fraction": 0.0
      },
      "within_1000m": {"status": "missing", "known_platforms": 0, "total_platforms": 30, "failed_platforms": 0, "refresh_failed_platforms": 0, "fraction": 0.0},
      "within_radius": {"status": "missing", "known_platforms": 0, "total_platforms": 30, "failed_platforms": 0, "refresh_failed_platforms": 0, "fraction": 0.0}
    }
  }
}
```

The JSON above illustrates the schema, not measured platform counts at a real
address. `distinct_lines_radius` uses the selected `radius_m` (1–2,000 m).
`nearest_stop_lines` describes the globally nearest platform, even when it falls
outside the marker radius; tie-breaking uses distance, stop ID and platform.

Window coverage status is `complete`, `partial`, `missing`, `error`, or
`no_platforms`. `fraction` is successful platforms / total eligible platforms;
it is null when there are no platforms. Counts are null if no eligible platform
has successful line data, and are observed unique counts under partial coverage.
Zero is valid for known-empty observations or a window containing no platforms;
under partial coverage it does not establish an absence of lines citywide.
`data_status` distinguishes a loaded file, no records/file, and a read error.
Failed refreshes remain visible even when successful old records cover a window.

Enriched transport markers add `lines`, `lines_retrieved_at`, and
`line_data_status` (`available` or `refresh_failed`). Unenriched markers omit
`lines` and expose `line_data_status` (`missing` or `error`). A `lines: []` marker
is known-empty. Source attribution is appended when matching successful data
exists. Existing JSON consumers may ignore the new fields.

## Backend integration and limits of interpretation

This branch integrates only backend/Data Science changes. The API exposes optional line fields for frontend consumers, while `frontend/` remains identical to `origin/main`. No line-number display or frontend API adapter is delivered here.

Line count measures choice, not frequency, reliability, connectivity, walking access or useful destinations. Counts in partial samples are observed counts, not full-area totals. A spatial window containing no stops differs from a window whose stop lines have not been ingested. Current shipped coverage is 15/6,652 platforms across three stop groups, with 33 distinct observed line identifiers. Per-platform timestamps and local/global coverage are included in API responses.

## Verification

```bash
.venv/bin/python -m pytest -q
git diff --exit-code origin/main -- frontend
```

Tests use the documented example, synthetic spatial fixtures, temporary caches,
and mocked HTTP. External HTTP transports are blocked during Python tests.
