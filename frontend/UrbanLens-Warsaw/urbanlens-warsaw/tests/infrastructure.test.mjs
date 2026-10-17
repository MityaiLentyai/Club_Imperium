import { test, after } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const dir = await mkdtemp(join(tmpdir(), "urbanlens-infrastructure-"));
// Resolve React from the workspace, independent of the temporary output directory.
// Bundle the server renderer as CommonJS to preserve Node built-in requires.
await build({
  stdin: {
    contents: `import React from 'react';
      import {renderToStaticMarkup} from 'react-dom/server';
      import {InfrastructureSummary, FacilityDetails} from './src/Infrastructure';
      export * from './src/api';
      export const summary = (result, category) => renderToStaticMarkup(React.createElement(InfrastructureSummary, {result,category}));
      export const details = (place) => renderToStaticMarkup(React.createElement(FacilityDetails, {place}));`,
    resolveDir: process.cwd(),
  },
  bundle: true, platform: "node", format: "cjs", outfile: join(dir, "components.cjs"),
  define: { "import.meta.env": '{"VITE_API_BASE_URL":"https://backend.example"}' },
});
const { default: { adaptAnalysis, analyze, summary, details } } = await import(pathToFileURL(join(dir, "components.cjs")));
const req = { latitude: 52.2297, longitude: 21.0122, label: "Selected home", radius_m: 500, destination: null };
const raw = {
  scores: { mobility: 92.7 }, features: { nearest_park_m: 80, parks_within_radius: 1, nearest_listed_parking_m: 160, listed_parking_within_radius: 1 },
  places: [
    { id: "green:1", category: "green", label: "Real park", latitude: 52.23, longitude: 21.01, distance_m: 80, distance_type: "straight_line", distance_basis: "park_area" },
    { id: "parking:1", category: "parking", label: "Listed parking", latitude: 52.23, longitude: 21.01, distance_m: 160, distance_type: "straight_line", capacity: 47, free_places_total: { public: 30 }, opening_hours: [{ monday: "00:00-23:59" }], tariffs: [{ VehicleType: "Car", Prices: [{ StayLength: "1.00", StayPrice: "5.00" }] }] },
  ],
  unavailable: ["grocery", "pharmacy"],
  datasets: { green: { status: "available", total: 1, retrieved_at: "2026-10-17T12:00:00+00:00" }, parking: { status: "available", total: 1, retrieved_at: "2026-10-17T12:00:00+00:00" } },
};

test("live adapter preserves new categories, backend score and selected address", () => {
  const result = adaptAnalysis(raw, req);
  assert.equal(result.demo, false);
  assert.equal(result.location.label, req.label);
  assert.equal(result.scores.mobility, 92.7);
  assert.equal(result.features.parks_within_radius, 1);
  assert.equal(result.places[0].distance_basis, "park_area");
  assert.equal(result.places[1].capacity, 47);
  assert.equal(result.places[1].free_places_total, undefined);
  assert.ok(!result.unavailable.includes("green"));
});

test("park and parking rendering communicates proximity, details and limitations", () => {
  const result = adaptAnalysis(raw, req);
  assert.match(summary(result, "green"), /Nearest listed park/);
  assert.match(summary(result, "green"), /does not measure distance to an entrance/);
  assert.match(summary(result, "parking"), /Incomplete coverage/);
  assert.match(summary(result, "parking"), /Snapshot retrieved/);
  const html = details(result.places[1]);
  assert.match(html, /Listed capacity: 47/);
  assert.match(html, /monday: 00:00-23:59/);
  assert.match(html, /5.00/);
  assert.match(html, /Current availability unavailable/);
});

test("missing and empty datasets render different states with no invented live places", () => {
  const missing = adaptAnalysis({ places: [], unavailable: ["green", "parking"], datasets: { green: {status: "unavailable"} } }, req);
  assert.ok(missing.unavailable.includes("green"));
  assert.doesNotMatch(summary(missing, "green"), /Nearest listed park/);
  assert.equal(missing.places.length, 0);
  const empty = adaptAnalysis({ ...raw, places: [], features: { parks_within_radius: 0, nearest_park_m: null } }, req);
  assert.ok(!empty.unavailable.includes("green"));
  assert.match(summary(empty, "green"), /0 distinct parks/);
  assert.equal(summary({...empty, demo: true}, "green"), "");
});

test("adapter excludes out-of-radius markers while respecting park area distances", () => {
  const result = adaptAnalysis({ ...raw, places: [...raw.places, {...raw.places[1], distance_m: 501}] }, req);
  assert.equal(result.places.length, 2);
});

test("live requests use the existing FastAPI endpoint without leaking destination or token", async () => {
  const previous = globalThis.fetch;
  let call;
  globalThis.fetch = async (url, options) => { call = {url, options}; return {ok: true, json: async () => raw}; };
  try {
    const result = await analyze(req);
    assert.equal(call.url, "https://backend.example/api/score");
    assert.deepEqual(JSON.parse(call.options.body), { latitude: req.latitude, longitude: req.longitude, radius_m: 500 });
    assert.deepEqual(call.options.headers, {"Content-Type": "application/json"});
    assert.equal(result.places.length, 2);
  } finally { globalThis.fetch = previous; }
});

after(async () => { await rm(dir, {recursive: true, force: true}); });
