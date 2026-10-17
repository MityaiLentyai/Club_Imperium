import { test, after } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

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
const { adaptScore, demoAnalysis, homes, inWarsaw, distance, scorePoint } = await import(pathToFileURL(output));

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
  const a = adaptScore({ ...live, unavailable: ["grocery", "pharmacy"], datasets: { green: {}, parking: {}, sports: {} } }, 500, "x");
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
after(() => rm(dir, { recursive: true, force: true }));
