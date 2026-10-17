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
