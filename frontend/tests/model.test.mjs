import { test, after } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { readFile } from "node:fs/promises";

const dir = await mkdtemp(join(tmpdir(), "olo-tests-"));
const output = join(dir, "model.mjs");
await build({
  stdin: {
    contents: "export * from './src/api'; export * from './src/geo'; export * from './src/demo';",
    resolveDir: process.cwd(),
  },
  bundle: true,
  platform: "node",
  format: "esm",
  outfile: output,
  define: { "import.meta.env": "{}" },
});
const { adaptScore, adaptCommute, adaptComparison, readableAddress, demoAnalysis, homes, inWarsaw, distance, scorePoint } =
  await import(pathToFileURL(output));
// Real request/response pairs recorded by the backend team (docs/frontend-integration-check.md).
const examples = JSON.parse(await readFile(new URL("../../docs/examples/backend-http.json", import.meta.url), "utf8")).examples;
const example = (path, status = 200) =>
  examples.find((e) => e.request.path === path && e.response.status_code === status).response.json;

// Shape returned by POST /api/score (see backend/services/scoring_service.py).
const live = {
  location: { latitude: 52.2297, longitude: 21.0122 },
  scores: { mobility: 92.7 },
  features: { nearest_stop_m: 30.7, stop_groups_500m: 7, stop_groups_1000m: 24 },
  radius_m: 500,
  places: [
    { id: "7013:01", category: "transport", label: "Centrum", latitude: 52.2301, longitude: 21.0118, distance_m: 30.7, distance_type: "straight_line" },
    { id: "bad", category: "transport", label: "No coordinates" },
  ],
  unavailable: ["grocery", "pharmacy", "green", "parking"],
  nearby: { total: 2, limit: 200, truncated: false },
  sources: [{ name: "Warsaw transport stops (stops_clean.csv)" }],
};

test("adaptScore maps the live score contract", () => {
  const a = adaptScore(live, 500, "Typed address");
  assert.equal(a.mobility.score, 92.7);
  assert.equal(a.mobility.stop_groups_500m, 7);
  assert.equal(a.places.length, 1);
  assert.equal(a.places[0].distance_type, "straight_line");
  assert.deepEqual(a.unavailable, ["grocery", "pharmacy", "green", "parking", "sports"]);
  assert.equal(a.location.label, "Typed address");
  assert.equal(a.demo, false);
});
test("adaptScore prefers the backend's resolved address", () => {
  const a = adaptScore({ ...live, location: { ...live.location, address: "Marszałkowska 83, Warszawa" } }, 500, "marszalkowska 83");
  assert.equal(a.location.label, "Marszałkowska 83, Warszawa");
});
test("categories with a dataset are supported even when empty", () => {
  const a = adaptScore({ ...live, unavailable: ["grocery", "pharmacy"], datasets: { green: { status: "available" }, parking: { status: "available" }, sports: { status: "available" } } }, 500, "x");
  assert.deepEqual(a.unavailable, ["grocery", "pharmacy"]);
});
test("adaptScore rejects malformed responses", () => {
  assert.throws(() => adaptScore({ detail: "oops" }, 500, "x"), /unexpected/);
});
test("demo is labeled and respects the radius", () => {
  const r = demoAnalysis(homes[0], 200);
  assert.equal(r.demo, true);
  assert.equal(r.radius_m, 200);
  assert.ok(r.places.every((p) => p.distance_m <= 200));
});
test("Warsaw bounds and distance helpers", () => {
  assert.ok(inWarsaw(homes[0]));
  assert.equal(inWarsaw({ latitude: 0, longitude: 0 }), false);
  assert.equal(distance(homes[0], homes[1]), distance(homes[1], homes[0]));
});
test("live without a configured backend fails with a clear message", async () => {
  await assert.rejects(scorePoint(homes[0], 1000), /not connected/);
});
test("documented /api/score example: LifeScore, datasets and nearest features", () => {
  const a = adaptScore(example("/api/score"), 1, "Centrum");
  assert.equal(a.lifeScore.label, "Partial LifeScore");
  assert.equal(a.lifeScore.status, "partial");
  assert.equal(a.lifeScore.value, 92.7);
  assert.deepEqual(a.lifeScore.normalized, { mobility: 100 });
  assert.ok(a.lifeScore.excluded.green);
  // Parks, parking and sports datasets are available even with nothing inside a 1 m radius.
  assert.deepEqual(a.unavailable, ["grocery", "pharmacy"]);
  assert.equal(a.nearest.green.distance_m, 786.3);
  assert.equal(a.nearest.green.within_radius, 0);
});
test("a missing optional dataset stays unavailable, not zero", () => {
  const raw = structuredClone(example("/api/score"));
  raw.datasets.sports = { status: "unavailable" };
  raw.features.nearest_sports_facility_m = null;
  raw.features.sports_facilities_within_radius = null;
  const a = adaptScore(raw, 1, "x");
  assert.ok(a.unavailable.includes("sports"));
  assert.equal(a.nearest.sports, undefined);
});
test("documented /api/score/address example gets a readable label", () => {
  const a = adaptScore(example("/api/score/address"), 1000, "Marszałkowska 83");
  assert.match(a.location.label, /^Marszałkowska 83, /);
  assert.equal(readableAddress("83, Marszałkowska, Koszyki", "x"), "Marszałkowska 83, Koszyki");
  assert.equal(readableAddress(undefined, "typed"), "typed");
});
test("documented /api/commute example: GeoJSON order is swapped for Leaflet", () => {
  const raw = example("/api/commute");
  const c = adaptCommute(raw);
  assert.equal(c.baseline_m, 7530.3);
  assert.equal(c.walking.status, "available");
  assert.equal(c.walking.duration_minutes, 109.4);
  const [lon, lat] = raw.walking.geometry.coordinates[0];
  assert.deepEqual(c.walking.path[0], [lat, lon]);
  assert.equal(c.transit.status, "unavailable");
  assert.match(c.transit.reason, /transit/);
  assert.equal(c.attribution.fix_map_url, "https://www.openstreetmap.org/fixthemap");
});
test("an unavailable route profile carries no measurements", () => {
  const c = adaptCommute({ baseline: { distance_m: 100 }, walking: { status: "unavailable", reason: "Routes not requested" }, driving: {}, transit: {} });
  assert.deepEqual(c.walking, { status: "unavailable", reason: "Routes not requested" });
  assert.equal(c.driving.status, "unavailable");
});
test("documented /api/compare example keeps statuses, advantages and warnings", () => {
  const homesIn = [demoAnalysis(homes[0], 1), demoAnalysis(homes[1], 1)];
  const c = adaptComparison(example("/api/compare"), homesIn);
  assert.equal(c.locations.length, 2);
  const mobility = c.rows.find((r) => r.metric === "mobility_score");
  assert.equal(mobility.advantage, "a");
  assert.equal(mobility.status, "comparable");
  const walking = c.rows.find((r) => r.metric === "walking_distance_m");
  assert.equal(walking.status, "unavailable");
  assert.equal(walking.advantage, null);
  assert.deepEqual(walking.values, [null, null]);
  assert.ok(c.warnings.length > 0);
});
after(() => rm(dir, { recursive: true, force: true }));
