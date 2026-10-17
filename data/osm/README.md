# Warsaw OSM retail database — ODbL 1.0

© OpenStreetMap contributors. This normalized derivative database is made available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/). See [OpenStreetMap copyright and contributors](https://www.openstreetmap.org/copyright).

`retail-manifest.json` identifies the full machine-readable gzip GeoJSON database in this directory and its SHA256. Download or clone the entire dataset without charge; it contains all normalized facilities, retained geometries, original tags and identifiers, and merged source-object records. `retail-report.json` records exclusions and deduplication. The original dated regional PBF can be obtained from the `source_url` in the manifest; its checksum and ingestion code are supplied for reproduction.

Changes to OSM data: select supermarket/convenience/grocery/pharmacy tags; clip to the official Warsaw district union; conservatively merge duplicate representations; add metric representative markers and district labels. The resulting OSM derivative database is kept separately from other infrastructure snapshots. Preserve this notice and license URI when redistributing this database. Public products using it must display attribution and identify the ODbL license; recipients must be offered the derivative database or the alterations needed to reconstruct it, as required by ODbL sections 4.2–4.6.

The API carries attribution/license/source fields. The frontend team must display visible attribution near the map or other data output and link the downloadable database; API metadata alone does not ensure visible product attribution. Frontend files are outside this change.

See [ingestion, exact counts, timestamps and API contract](../../docs/osm-retail.md). OSM mapping is not an exhaustive or independently verified inventory of operating businesses.
