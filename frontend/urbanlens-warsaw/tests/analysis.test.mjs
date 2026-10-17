import { test, after } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
const dir = await mkdtemp(join(tmpdir(), "urbanlens-tests-"));
const output = join(dir, "model.mjs");
await build({
  stdin: {
    contents:
      "export * from './src/api'; export * from './src/geo'; export * from './src/demo';",
    resolveDir: process.cwd(),
  },
  bundle: true,
  platform: "node",
  format: "esm",
  outfile: output,
  define: { "import.meta.env": "{}" },
});
const { distance, inWarsaw, adaptAnalysis, demoAnalysis, analyze, homes } =
  await import(pathToFileURL(output));

test("distance is zero at origin and symmetric", () => {
  assert.equal(distance(homes[0], homes[0]), 0);
  assert.equal(distance(homes[0], homes[1]), distance(homes[1], homes[0]));
  assert.ok(distance(homes[0], homes[1]) > 2000);
});
test("Warsaw bounds reject invalid coordinates", () => {
  assert.ok(inWarsaw(homes[0]));
  assert.equal(inWarsaw({ latitude: 0, longitude: 0 }), false);
  assert.equal(inWarsaw({ latitude: NaN, longitude: 21 }), false);
});
test("demo is explicit, radius constrained, no parking claims", () => {
  const r = demoAnalysis(homes[0], 200);
  assert.equal(r.demo, true);
  assert.ok(r.places.length > 0);
  assert.ok(
    r.places.every(
      (p) => p.distance_m <= 200 && p.distance_type === "straight_line",
    ),
  );
  assert.deepEqual(r.unavailable, ["parking"]);
  assert.equal(r.retrieved_at, undefined);
});
const req = { ...homes[0], radius_m: 1000, destination: null };
test("missing groups stay unavailable; empty group is different", () => {
  const a = adaptAnalysis({ stops: [] }, req);
  assert.equal(a.unavailable.includes("transport"), false);
  assert.equal(a.unavailable.includes("parking"), true);
  assert.equal(a.places.length, 0);
});
test("adapter drops invalid coordinates and does not invent distance types", () => {
  const a = adaptAnalysis(
    {
      shops: [
        { name: "Shop", lat: 52.22, lon: 21.01, distance_m: 150 },
        { name: "Bad coordinates" },
      ],
    },
    req,
  );
  assert.equal(a.places.length, 1);
  assert.equal(a.places[0].distance_type, undefined);
  assert.equal(a.demo, false);
});
test("live without backend fails explicitly", async () => {
  await assert.rejects(analyze(req), /not connected/);
});
after(async () => {
  await rm(dir, { recursive: true, force: true });
});

const liveOutput = join(dir, 'live.mjs');
await build({
  stdin: { contents: "export * from './src/api';", resolveDir: process.cwd() },
  bundle: true, platform: 'node', format: 'esm', outfile: liveOutput,
  define: { 'import.meta.env': JSON.stringify({ VITE_API_BASE_URL: 'http://backend.test' }) },
});
const live = await import(pathToFileURL(liveOutput));
const scoreResponse = {
  location: { latitude: req.latitude, longitude: req.longitude },
  scores: { mobility: 92.7 },
  features: { nearest_stop_m: 30.7, stop_groups_500m: 7, stop_groups_1000m: 24 },
  places: [], unavailable: ['grocery', 'pharmacy', 'green', 'parking'],
  radius_m: 1000, nearby: { total: 0, limit: 200, truncated: false },
};

test('live sends only supported scoring fields and retains score contract', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'http://backend.test/api/score');
    assert.deepEqual(JSON.parse(options.body), { latitude: req.latitude, longitude: req.longitude, radius_m: 1000 });
    return Response.json(scoreResponse);
  });
  const result = await live.analyze(req);
  assert.deepEqual(result.scores, scoreResponse.scores);
  assert.deepEqual(result.features, scoreResponse.features);
  assert.deepEqual(result.nearby, scoreResponse.nearby);
  assert.equal(result.location.label, req.label);
  assert.equal(result.unavailable.includes('transport'), false);
  assert.equal(result.demo, false);
});

test('backend geocode object becomes a selectable Location', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    const endpoint = new URL(url);
    assert.equal(endpoint.origin, 'http://backend.test');
    assert.equal(endpoint.pathname, '/api/geocode');
    assert.equal(endpoint.searchParams.get('address'), 'Marszałkowska 83');
    return Response.json({ address: 'Resolved Warsaw address', latitude: 52.2252, longitude: 21.0131 });
  });
  assert.deepEqual(await live.geocode(' Marszałkowska 83 '), [
    { label: 'Resolved Warsaw address', latitude: 52.2252, longitude: 21.0131 },
  ]);
});

test('backend errors remain meaningful without falling back to demo', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Address not found in Warsaw' }, { status: 404 }));
  await assert.rejects(live.geocode('Missing address'), /Address not found in Warsaw/);
  await assert.rejects(live.analyze(req), /Address not found in Warsaw/);
});

test('validation lists and malformed success responses fail explicitly', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: [{ msg: 'Radius too large' }] }, { status: 422 }));
  await assert.rejects(live.analyze(req), /Radius too large/);
  fetch.mock.mockImplementation(async () => Response.json({ places: [] }));
  await assert.rejects(live.analyze(req), /invalid score response/);
});
