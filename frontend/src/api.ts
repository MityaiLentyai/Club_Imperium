import type { Analysis, Category, Location, Place } from "./types";
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

// Turns FastAPI's {detail} envelope and HTTP status into a sentence a resident understands.
async function failure(r: Response): Promise<Error> {
  let detail = "";
  try {
    const body = await r.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    /* Body is not JSON. */
  }
  if (r.status === 404)
    return new Error("We couldn’t find this address in Warsaw. Check the street and building number, or click the spot on the map.");
  if (r.status === 422)
    return new Error(detail && !detail.startsWith("[") ? detail : "This address or spot can’t be analyzed. Try a Warsaw street and building number.");
  if (r.status === 503)
    return new Error("Address search isn’t set up on the server yet. Click the spot on the map instead.");
  if (r.status === 502 || r.status === 504)
    return new Error("Address search is temporarily unavailable. Try again in a moment, or click the spot on the map.");
  return new Error(`The data service failed (HTTP ${r.status}). Try again in a moment.`);
}

async function call(path: string, init?: RequestInit) {
  if (!API_BASE_URL)
    throw new Error("Live data is not connected in this build. Switch to Demo to try the app.");
  let r: Response;
  try {
    r = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    throw new Error("Can’t reach the data service. Check your connection or switch to Demo.");
  }
  if (!r.ok) throw await failure(r);
  return r.json();
}

const post = (path: string, body: unknown) =>
  call(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export function scorePoint(p: Location, radius: number) {
  return post("/api/score", {
    latitude: p.latitude,
    longitude: p.longitude,
    radius_m: radius,
  }).then((raw) => adaptScore(raw, radius, p.label));
}

export function scoreAddress(address: string, radius: number) {
  return post("/api/score/address", { address, radius_m: radius }).then(
    (raw) => adaptScore(raw, radius, address),
  );
}

export async function geocode(address: string): Promise<Location> {
  const raw = await call(`/api/geocode?${new URLSearchParams({ address })}`);
  const p = {
    label: String(raw?.address ?? address),
    latitude: Number(raw?.latitude),
    longitude: Number(raw?.longitude),
  };
  if (!inWarsaw(p)) throw new Error("This address is outside Warsaw.");
  return p;
}

function unsupported(raw: any, places: Place[]): Category[] {
  const listed: Category[] = Array.isArray(raw.unavailable) ? raw.unavailable : [];
  const reported = new Set<string>([
    "transport",
    ...places.map((p) => p.category),
    ...Object.keys(raw.datasets && typeof raw.datasets === "object" ? raw.datasets : {}),
  ]);
  return categories.filter((c) => listed.includes(c) || !reported.has(c));
}

const finite = (n: unknown) =>
  typeof n === "number" && Number.isFinite(n) ? n : undefined;

// Maps the /api/score response onto the UI model. A category counts as supported only
// when the backend reports on it (places, or a dataset entry); anything else stays
// "unavailable", so an older backend never shows "0 sports" for data it doesn't have.
// For a supported category an empty list means zero nearby places.
export function adaptScore(raw: any, radius: number, label: string): Analysis {
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
      lines: Array.isArray(p.lines) ? p.lines.map(String) : undefined,
    });
  }
  const score = finite(raw.scores?.mobility);
  return {
    location: {
      latitude,
      longitude,
      label: typeof raw.location?.address === "string" ? raw.location.address : label,
    },
    radius_m: finite(raw.radius_m) ?? radius,
    places,
    unavailable: unsupported(raw, places),
    mobility:
      score === undefined
        ? undefined
        : {
            score,
            nearest_stop_m: finite(raw.features?.nearest_stop_m),
            stop_groups_500m: finite(raw.features?.stop_groups_500m),
            stop_groups_1000m: finite(raw.features?.stop_groups_1000m),
          },
    nearby:
      raw.nearby && typeof raw.nearby.total === "number"
        ? { total: raw.nearby.total, truncated: !!raw.nearby.truncated }
        : undefined,
    sources: Array.isArray(raw.sources)
      ? raw.sources.filter((s: any) => typeof s?.name === "string")
      : [],
    retrieved_at: typeof raw.retrieved_at === "string" ? raw.retrieved_at : undefined,
    demo: false,
  };
}
