import type {
  Analysis,
  Category,
  Commute,
  Comparison,
  ComparisonRow,
  LifeScore,
  Location,
  Nearest,
  Place,
  Route,
  WeightKey,
  Weights,
} from "./types";
import { inWarsaw } from "./geo";

const env =
  (import.meta as ImportMeta & { env?: Record<string, string> }).env || {};
export const API_BASE_URL = env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";

export const categories: Category[] = [
  "transport",
  "grocery",
  "pharmacy",
  "green",
  "parking",
  "sports",
];
export const weightKeys: WeightKey[] = ["mobility", "green", "parking", "sports", "commute"];

// Request timeouts follow the backend's own bounds (docs/frontend-integration-check.md):
// geocoding waits up to 10 s, each route profile up to 10 s after a 2 s queue wait, and a
// compare with routes can make four sequential route requests.
const TIMEOUT = {
  score: 20_000,
  address: 30_000,
  commute: 35_000,
  compare: 40_000,
  compareWithRoutes: 75_000,
  health: 5_000,
};

// FastAPI errors use {detail}: a string for application errors, a list for validation.
function detailText(body: any): string {
  const d = body?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d
      .map((e) => (typeof e?.msg === "string" ? e.msg : ""))
      .filter(Boolean)
      .join("; ");
  return "";
}

// Turns an HTTP failure into a sentence a resident understands.
async function failure(r: Response): Promise<Error> {
  let detail = "";
  try {
    detail = detailText(await r.json());
  } catch {
    /* Body is not JSON. */
  }
  if (r.status === 404)
    return new Error("We couldn’t find this address in Warsaw. Check the street and building number, or click the spot on the map.");
  if (r.status === 422)
    return new Error(
      detail.startsWith("Coordinates are outside")
        ? "This spot is outside the area we cover. Choose a place inside Warsaw."
        : detail
          ? `This request can’t be analyzed: ${detail}.`
          : "This address or spot can’t be analyzed. Try a Warsaw street and building number.",
    );
  if (r.status === 503)
    return new Error(
      /geocod/i.test(detail)
        ? "Address search isn’t set up on the server yet. Click the spot on the map instead."
        : "Transport data is temporarily unavailable on the server. Try again later.",
    );
  if (r.status === 502 || r.status === 504)
    return new Error("Address search is temporarily unavailable. Try again in a moment, or click the spot on the map.");
  return new Error(`The data service failed (HTTP ${r.status}). Try again in a moment.`);
}

async function call(path: string, timeout: number, init?: RequestInit) {
  if (!API_BASE_URL)
    throw new Error("Live data is not connected in this build. Switch to Demo to try the app.");
  let r: Response;
  try {
    r = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: AbortSignal.timeout(timeout),
    });
  } catch (e) {
    throw new Error(
      (e as Error)?.name === "TimeoutError"
        ? "The data service is taking too long. Try again in a moment."
        : "Can’t reach the data service. Check your connection or switch to Demo.",
    );
  }
  if (!r.ok) throw await failure(r);
  return r.json();
}

const post = (path: string, body: unknown, timeout: number) =>
  call(path, timeout, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// Liveness only: a healthy service can still lack datasets, which score responses report.
export async function health(): Promise<boolean> {
  try {
    const raw = await call("/api/health", TIMEOUT.health);
    return raw?.status === "ok";
  } catch {
    return false;
  }
}

// Omitted weights mean "backend defaults"; supplying them zeroes unspecified categories.
const withWeights = <T extends object>(body: T, weights?: Weights): T & { weights?: Weights } =>
  weights ? { ...body, weights } : body;

export function scorePoint(p: Location, radius: number, weights?: Weights) {
  return post(
    "/api/score",
    withWeights({ latitude: p.latitude, longitude: p.longitude, radius_m: radius }, weights),
    TIMEOUT.score,
  ).then((raw) => adaptScore(raw, radius, p.label, weights));
}

export function scoreAddress(address: string, radius: number, weights?: Weights) {
  return post("/api/score/address", withWeights({ address, radius_m: radius }, weights), TIMEOUT.address).then(
    (raw) => adaptScore(raw, radius, address, weights),
  );
}

export async function geocode(address: string): Promise<Location> {
  const raw = await call(`/api/geocode?${new URLSearchParams({ address })}`, TIMEOUT.address);
  const p = {
    label: readableAddress(raw?.address, address),
    latitude: Number(raw?.latitude),
    longitude: Number(raw?.longitude),
  };
  if (!inWarsaw(p)) throw new Error("This address is outside Warsaw.");
  return p;
}

export async function commute(origin: Location, destination: Location): Promise<Commute> {
  const point = (l: Location) => ({ latitude: l.latitude, longitude: l.longitude });
  const raw = await post("/api/commute", { origin: point(origin), destination: point(destination) }, TIMEOUT.commute);
  return adaptCommute(raw);
}

export async function compare(
  homes: [Analysis, Analysis],
  options: { weights?: Weights; destination?: Location | null; includeRoutes?: boolean },
): Promise<Comparison> {
  const body = withWeights(
    {
      // Coordinates (not addresses) keep the comparison offline and match what the user saw.
      locations: homes.map((h) => ({
        latitude: h.location.latitude,
        longitude: h.location.longitude,
        radius_m: h.radius_m,
      })),
      ...(options.destination
        ? { destination: { latitude: options.destination.latitude, longitude: options.destination.longitude } }
        : {}),
      include_routes: !!(options.includeRoutes && options.destination),
    },
    options.weights,
  );
  const raw = await post("/api/compare", body, body.include_routes ? TIMEOUT.compareWithRoutes : TIMEOUT.compare);
  return adaptComparison(raw, homes, options.weights);
}

const finite = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n) ? n : undefined;
const finiteOrNull = (n: unknown) => finite(n) ?? null;

// Short street-type forms as written on Warsaw street signs; "ulica" is usually omitted.
const streetTypes: [RegExp, string][] = [
  [/^ulica\s+/i, ""],
  [/^aleja\s+/i, "al. "],
  [/^plac\s+/i, "pl. "],
];

// Makes geocoder labels read like a resident would write them. Nominatim display names
// start with the house number ("83, Marszałkowska, Koszyki, …") and the municipal index
// spells out the street type ("ulica Marszałkowska 83, …"); both become "Marszałkowska 83, …".
export function readableAddress(display: unknown, fallback: string): string {
  if (typeof display !== "string" || !display.trim()) return fallback;
  const parts = display.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length > 1 && /^\d+[\w/-]*$/.test(parts[0])) parts.splice(0, 2, `${parts[1]} ${parts[0]}`);
  parts[0] = streetTypes.reduce((s, [re, short]) => s.replace(re, short), parts[0]);
  return parts.join(", ");
}

// A category counts as supported only when the backend reports on it (places, or an
// available dataset); anything else stays "unavailable", so an older backend never shows
// "0 sports" for data it doesn't have. A supported empty list means zero nearby places.
function unsupported(raw: any, places: Place[]): Category[] {
  const listed: Category[] = Array.isArray(raw.unavailable) ? raw.unavailable : [];
  const datasets = raw.datasets && typeof raw.datasets === "object" ? raw.datasets : {};
  const reported = new Set<string>(["transport", ...places.map((p) => p.category)]);
  for (const [c, d] of Object.entries<any>(datasets)) if (d?.status === "available") reported.add(c);
  return categories.filter((c) => listed.includes(c) || !reported.has(c));
}

function placeDetails(p: any): string[] {
  const out: string[] = [];
  if (typeof p.address === "string") out.push(p.address);
  if (Array.isArray(p.sport_types) && p.sport_types.length) out.push(p.sport_types.map(String).join(", "));
  if (finite(p.capacity) !== undefined) out.push(`${p.capacity} spaces`);
  if (p.category === "parking") out.push("Free spaces not published");
  return out;
}

const featureKeys: Partial<Record<Category, [string, string]>> = {
  green: ["nearest_park_m", "parks_within_radius"],
  parking: ["nearest_listed_parking_m", "listed_parking_within_radius"],
  sports: ["nearest_sports_facility_m", "sports_facilities_within_radius"],
};

function adaptLifeScore(raw: any): LifeScore | undefined {
  const ls = raw?.life_score;
  if (!ls || typeof ls !== "object") return undefined;
  const pick = (o: any) =>
    Object.fromEntries(
      weightKeys.filter((k) => finite(o?.[k]) !== undefined).map((k) => [k, o[k] as number]),
    ) as Weights;
  return {
    value: finiteOrNull(ls.value),
    status: String(ls.status ?? "unavailable"),
    label: String(ls.label ?? "LifeScore"),
    requested: pick(ls.requested_weights),
    normalized: pick(ls.normalized_weights),
    excluded: Object.fromEntries(
      weightKeys.filter((k) => typeof ls.excluded?.[k] === "string").map((k) => [k, ls.excluded[k]]),
    ),
    explanation: typeof ls.explanation === "string" ? ls.explanation : undefined,
  };
}

// Maps the /api/score response onto the UI model.
export function adaptScore(raw: any, radius: number, label: string, weights?: Weights): Analysis {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.places))
    throw new Error("The data service returned an unexpected response.");
  const latitude = Number(raw.location?.latitude),
    longitude = Number(raw.location?.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude))
    throw new Error("The data service returned an unexpected response.");
  const places: Place[] = [];
  for (const [i, p] of raw.places.entries()) {
    const lat = Number(p?.latitude),
      lon = Number(p?.longitude);
    if (!categories.includes(p?.category) || !Number.isFinite(lat) || !Number.isFinite(lon))
      continue;
    const details = placeDetails(p);
    places.push({
      id: String(p.id ?? `${p.category}-${i}`),
      category: p.category,
      label: String(p.label ?? "Unnamed place"),
      latitude: lat,
      longitude: lon,
      distance_m: finite(p.distance_m),
      distance_type:
        p.distance_type === "walking" || p.distance_type === "straight_line"
          ? p.distance_type
          : undefined,
      lines: Array.isArray(p.lines) && p.lines.length ? p.lines.map(String) : undefined,
      details: details.length ? details : undefined,
    });
  }
  const unavailable = unsupported(raw, places);
  const nearest: Partial<Record<Category, Nearest>> = {};
  for (const [c, [d, n]] of Object.entries(featureKeys) as [Category, [string, string]][]) {
    if (unavailable.includes(c)) continue;
    nearest[c] = { distance_m: finiteOrNull(raw.features?.[d]), within_radius: finiteOrNull(raw.features?.[n]) };
  }
  const score = finite(raw.scores?.mobility);
  const stopLines = raw.line_features?.nearest_stop_lines;
  return {
    location: {
      latitude,
      longitude,
      label: readableAddress(raw.location?.address, label),
    },
    radius_m: finite(raw.radius_m) ?? radius,
    places,
    unavailable,
    mobility:
      score === undefined
        ? undefined
        : {
            score,
            nearest_stop_m: finite(raw.features?.nearest_stop_m),
            stop_groups_500m: finite(raw.features?.stop_groups_500m),
            stop_groups_1000m: finite(raw.features?.stop_groups_1000m),
          },
    lifeScore: adaptLifeScore(raw),
    nearest,
    nearestStopLines: Array.isArray(stopLines) && stopLines.length ? stopLines.map(String) : undefined,
    nearby:
      raw.nearby && typeof raw.nearby.total === "number"
        ? { total: raw.nearby.total, truncated: !!raw.nearby.truncated }
        : undefined,
    sources: Array.isArray(raw.sources)
      ? raw.sources.filter((s: any) => typeof s?.name === "string")
      : [],
    retrieved_at: typeof raw.retrieved_at === "string" ? raw.retrieved_at : undefined,
    weights,
    demo: false,
  };
}

// Reads one routing profile. Measurements and geometry are trusted only when the profile
// says "available"; GeoJSON [longitude, latitude] pairs become Leaflet [latitude, longitude].
function adaptRoute(raw: any): Route {
  if (raw?.status !== "available")
    return { status: "unavailable", reason: typeof raw?.reason === "string" ? raw.reason : "Not available" };
  const distance = finite(raw.distance_m),
    minutes = finite(raw.duration_minutes);
  const coords = raw.geometry?.type === "LineString" && Array.isArray(raw.geometry.coordinates) ? raw.geometry.coordinates : [];
  const path = coords
    .filter((c: any) => Array.isArray(c) && finite(c[0]) !== undefined && finite(c[1]) !== undefined)
    .map((c: number[]) => [c[1], c[0]] as [number, number]);
  if (distance === undefined || minutes === undefined)
    return { status: "unavailable", reason: "The routing service returned incomplete data" };
  return { status: "available", distance_m: distance, duration_minutes: minutes, path };
}

export function adaptCommute(raw: any): Commute {
  const baseline = finite(raw?.baseline?.distance_m);
  if (baseline === undefined) throw new Error("The routing service returned an unexpected response.");
  return {
    baseline_m: baseline,
    walking: adaptRoute(raw.walking),
    driving: adaptRoute(raw.driving),
    transit: adaptRoute(raw.transit),
    attribution:
      raw.attribution && typeof raw.attribution.name === "string"
        ? { name: raw.attribution.name, url: raw.attribution.url, fix_map_url: raw.attribution.fix_map_url }
        : undefined,
  };
}

export function adaptComparison(raw: any, homes: Analysis[], weights?: Weights): Comparison {
  if (!raw || !Array.isArray(raw.locations) || !Array.isArray(raw.comparisons))
    throw new Error("The comparison service returned an unexpected response.");
  const rows: ComparisonRow[] = raw.comparisons
    .filter((r: any) => typeof r?.metric === "string" && Array.isArray(r.values))
    .map((r: any) => ({
      metric: r.metric,
      values: r.values.map(finiteOrNull),
      unit: String(r.unit ?? ""),
      preference: r.preference === "lower" ? "lower" : "higher",
      status: r.status === "comparable" || r.status === "incomparable" ? r.status : "unavailable",
      advantage: ["a", "b", "equal"].includes(r.advantage) ? r.advantage : null,
      reason: typeof r.reason === "string" ? r.reason : null,
    }));
  return {
    locations: raw.locations.map((l: any, i: number) =>
      adaptScore(l, homes[i]?.radius_m ?? 1000, homes[i]?.location.label ?? "Home", weights),
    ),
    rows,
    warnings: Array.isArray(raw.warnings) ? raw.warnings.filter((w: unknown) => typeof w === "string") : [],
  };
}
