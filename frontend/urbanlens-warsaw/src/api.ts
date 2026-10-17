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
  const r = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: signal || AbortSignal.timeout(20000),
  });
  if (!r.ok)
    throw new Error(
      `Analysis unavailable (HTTP ${r.status}). Please try again.`,
    );
  return adaptAnalysis(await r.json(), request);
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
    location: { ...request, label: raw.location?.label || "Selected location" },
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
let lastSearch = 0;
const cache = new Map<string, Location[]>();
export async function geocode(query: string): Promise<Location[]> {
  const q = query.trim();
  if (q.length < 3) throw new Error("Enter a street and building number.");
  const cached = cache.get(q.toLowerCase());
  if (cached) return cached;
  if (Date.now() - lastSearch < 1100)
    throw new Error("Please wait a moment before searching again.");
  lastSearch = Date.now();
  const u = new URL(
    env.VITE_GEOCODER_URL || "https://nominatim.openstreetmap.org/search",
  );
  u.search = new URLSearchParams({
    q: `${q}, Warsaw, Poland`,
    format: "jsonv2",
    limit: "5",
    countrycodes: "pl",
    viewbox: "20.75,52.39,21.28,52.09",
    bounded: "1",
  }).toString();
  const r = await fetch(u, {
    signal: AbortSignal.timeout(12000),
    referrerPolicy: "strict-origin-when-cross-origin",
  });
  if (!r.ok)
    throw new Error("Address search unavailable. Select a point on the map.");
  const raw = await r.json();
  const points = raw
    .map((p: any) => ({
      label: String(p.display_name),
      latitude: Number(p.lat),
      longitude: Number(p.lon),
    }))
    .filter(inWarsaw);
  cache.set(q.toLowerCase(), points);
  return points;
}
