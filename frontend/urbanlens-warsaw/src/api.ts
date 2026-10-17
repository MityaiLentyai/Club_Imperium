import type {
  Analysis,
  AnalyzeRequest,
  Location,
  Place,
  Category,
} from "./types";
import { inWarsaw } from "./geo";
const env =
  (import.meta as ImportMeta & { env: Record<string, string> }).env || {};
export const API_BASE_URL = env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";
export async function analyze(
  request: AnalyzeRequest,
  signal?: AbortSignal,
): Promise<Analysis> {
  if (!API_BASE_URL)
    throw new Error(
      "Live analysis is not connected yet. Add VITE_API_BASE_URL and rebuild, or explore Demo mode.",
    );
  const r = await fetch(`${API_BASE_URL}/api/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ latitude: request.latitude, longitude: request.longitude, radius_m: request.radius_m }),
    signal: signal || AbortSignal.timeout(20000),
  });
  if (!r.ok) throw new Error(await responseError(r));
  const raw = await r.json();
  if (!Number.isFinite(raw?.scores?.mobility) || raw.scores.mobility < 0 || raw.scores.mobility > 100 ||
      !Number.isFinite(raw?.features?.nearest_stop_m) || !Array.isArray(raw?.places))
    throw new Error("The backend returned an invalid score response.");
  return adaptAnalysis(raw, request);
}
const categories: Category[] = [
  "transport",
  "grocery",
  "pharmacy",
  "green",
  "parking",
];
// Adapt the team's final response contract here; preserve unavailable data explicitly.
export function adaptAnalysis(raw: any, request: AnalyzeRequest): Analysis {
  if (!raw || typeof raw !== "object")
    throw new Error("The backend returned an invalid analysis.");
  const grouped: Record<Category, string> = {
    transport: "stops",
    grocery: "shops",
    pharmacy: "pharmacies",
    green: "parks",
    parking: "parking",
  };
  const supplied = Array.isArray(raw.places);
  const unavailable: Category[] = [];
  const places: Place[] = [];
  for (const category of categories) {
    const key = grouped[category];
    const list = supplied
      ? raw.places.filter((p: any) => p.category === category)
      : (raw[key] ?? raw[`nearby_${key}`]);
    if (!Array.isArray(list)) {
      unavailable.push(category);
      continue;
    }
    for (const [i, p] of list.entries()) {
      const latitude = Number(p.latitude ?? p.lat),
        longitude = Number(p.longitude ?? p.lon);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
      places.push({
        id: String(p.id ?? `${category}-${i}`),
        category,
        label: String(p.label ?? p.name ?? "Unnamed location"),
        latitude,
        longitude,
        distance_m:
          typeof p.distance_m === "number" && p.distance_m >= 0
            ? p.distance_m
            : undefined,
        distance_type:
          p.distance_type === "walking"
            ? "walking"
            : p.distance_type === "straight_line"
              ? "straight_line"
              : undefined,
        lines: Array.isArray(p.lines) ? p.lines.map(String) : undefined,
      });
    }
  }
  return {
    location: {
      latitude: raw.location?.latitude ?? request.latitude,
      longitude: raw.location?.longitude ?? request.longitude,
      label: raw.location?.address || raw.location?.label || request.label || "Selected location",
    },
    radius_m: raw.radius_m ?? request.radius_m,
    scores: raw.scores,
    features: raw.features,
    nearby: raw.nearby,
    places,
    unavailable: [
      ...new Set([
        ...unavailable,
        ...(Array.isArray(raw.unavailable)
          ? raw.unavailable.filter((x: Category) => categories.includes(x))
          : []),
      ]),
    ],
    sources: Array.isArray(raw.sources)
      ? raw.sources.filter((s: any) => typeof s.name === "string")
      : [],
    retrieved_at:
      typeof raw.retrieved_at === "string" ? raw.retrieved_at : undefined,
    commute: raw.commute,
    demo: false,
  };
}
async function responseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail))
      return body.detail.map((error: { msg?: string }) => error.msg || "Invalid input").join("; ");
  } catch { /* Fall back to the HTTP status for non-JSON errors. */ }
  return `Service unavailable (HTTP ${response.status}). Please try again.`;
}

export async function geocode(query: string): Promise<Location[]> {
  const q = query.trim();
  if (q.length < 3 || q.length > 300) throw new Error("Enter an address between 3 and 300 characters.");
  if (!API_BASE_URL) throw new Error("Address search is not connected. Set VITE_API_BASE_URL.");
  const response = await fetch(`${API_BASE_URL}/api/geocode?${new URLSearchParams({ address: q })}`, {
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(await responseError(response));
  const raw = await response.json();
  const location = { label: raw.address, latitude: raw.latitude, longitude: raw.longitude };
  if (typeof location.label !== "string" || !inWarsaw(location))
    throw new Error("The address service returned an invalid Warsaw location.");
  return [location];
}
