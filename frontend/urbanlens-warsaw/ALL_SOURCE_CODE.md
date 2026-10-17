# UrbanLens Warsaw — все исходники

Создайте файлы по указанным путям. Проще использовать готовую папку из ZIP: там также есть lockfile для npm ci и инструкции запуска. Для ручной сборки из этого текста выполните npm install, затем npm run dev.

## package.json

```json
{
  "name": "urbanlens-warsaw",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "tsc --noEmit && vite build",
    "test": "node --test tests/*.test.mjs"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "leaflet": "^1.9.4",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "typescript": "^5.7.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@types/leaflet": "^1.9.15"
  }
}
```

## tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "allowImportingTsExtensions": true
  },
  "include": ["src"]
}
```

## index.html

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta name="theme-color" content="#2568df" />
    <meta
      name="description"
      content="Understand the neighborhood before choosing your next home. Explore Warsaw with UrbanLens."
    />
    <title>UrbanLens Warsaw — Find your everyday</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

## .env.example

```text
VITE_API_BASE_URL=http://localhost:8000
# Optional replacement provider with a Nominatim-compatible search endpoint.
VITE_GEOCODER_URL=https://nominatim.openstreetmap.org/search
```

## .gitignore

```text
node_modules/
dist/
.env
.env.local
```

## src/types.ts

```typescript
export type Category =
  | "transport"
  | "grocery"
  | "pharmacy"
  | "green"
  | "parking";
export interface Location {
  latitude: number;
  longitude: number;
  label: string;
}
export interface Place extends Location {
  id: string;
  category: Category;
  distance_m?: number;
  distance_type?: "straight_line" | "walking";
  lines?: string[];
}
export interface Analysis {
  location: Location;
  radius_m?: number;
  places: Place[];
  unavailable: Category[];
  sources: { name: string; url?: string; retrieved_at?: string }[];
  retrieved_at?: string;
  commute?: {
    distance_m?: number;
    duration_minutes?: number;
    mode?: string;
    status?: string;
  };
  demo: boolean;
}
export interface AnalyzeRequest {
  latitude: number;
  longitude: number;
  radius_m: number;
  destination: Location | null;
}
```

## src/geo.ts

```typescript
import type { Location } from "./types";
export function distance(a: Location, b: Location): number {
  const rad = (d: number) => (d * Math.PI) / 180;
  const p = rad(b.latitude - a.latitude),
    l = rad(b.longitude - a.longitude);
  const h =
    Math.sin(p / 2) ** 2 +
    Math.cos(rad(a.latitude)) *
      Math.cos(rad(b.latitude)) *
      Math.sin(l / 2) ** 2;
  return Math.round(6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h)));
}
export const inWarsaw = (p: Location) =>
  Number.isFinite(p.latitude) &&
  Number.isFinite(p.longitude) &&
  p.latitude >= 52.09 &&
  p.latitude <= 52.39 &&
  p.longitude >= 20.75 &&
  p.longitude <= 21.28;
export const meters = (n: number | undefined) =>
  n === undefined
    ? "Unavailable"
    : n >= 1000
      ? `${(n / 1000).toFixed(1)} km`
      : `${Math.round(n)} m`;
```

## src/demo.ts

```typescript
import type { Analysis, Location, Place, Category } from "./types";
import { distance } from "./geo";
export const homes: Location[] = [
  { label: "Marszałkowska 83, Warsaw", latitude: 52.2252, longitude: 21.0131 },
  { label: "Puławska 24, Warsaw", latitude: 52.2064, longitude: 21.0225 },
  { label: "Ząbkowska 12, Warsaw", latitude: 52.2544, longitude: 21.0385 },
];
export const destinations: Location[] = [
  { label: "University of Warsaw", latitude: 52.2403, longitude: 21.0186 },
  {
    label: "Warsaw University of Technology",
    latitude: 52.2201,
    longitude: 21.0105,
  },
  { label: "Warsaw Central Station", latitude: 52.2286, longitude: 21.0031 },
];
export function demoAnalysis(location: Location, radius: number): Analysis {
  const items: [Category, string, number, number][] = [
    ["transport", "Example tram stop", 0.001, 0.001],
    ["transport", "Example bus stop", -0.002, 0.002],
    ["transport", "Example metro entrance", 0.004, -0.002],
    ["grocery", "Example neighborhood grocery", -0.0008, -0.0012],
    ["grocery", "Example supermarket", 0.003, 0.004],
    ["grocery", "Example convenience store", -0.003, -0.003],
    ["pharmacy", "Example local pharmacy", 0.0004, 0.0028],
    ["green", "Example pocket park", -0.0025, 0.005],
    ["green", "Example garden entrance", 0.005, -0.005],
  ];
  const places: Place[] = items
    .map(([category, label, y, x], i) => {
      const p = {
        id: `demo-${i}`,
        category,
        label,
        latitude: location.latitude + y,
        longitude: location.longitude + x,
        distance_type: "straight_line" as const,
      };
      return { ...p, distance_m: distance(location, p) };
    })
    .filter((p) => p.distance_m <= radius);
  return {
    location,
    places,
    unavailable: ["parking"],
    sources: [
      { name: "Illustrative fixture — not verified city data" },
      {
        name: "OpenStreetMap (base map only)",
        url: "https://www.openstreetmap.org/copyright",
      },
    ],
    demo: true,
  };
}
```

## src/api.ts

```typescript
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
```

## src/Map.tsx

```tsx
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Location, Place, Category } from "./types";
function popupText(text: string) {
  const el = document.createElement("div");
  el.textContent = text;
  return el;
}
export const symbols: Record<Category, string> = {
  transport: "↔",
  grocery: "▤",
  pharmacy: "+",
  green: "♧",
  parking: "P",
};
export default function NeighborhoodMap({
  location,
  places,
  radius,
  filters,
  onPick,
  destination,
  centerTick,
}: {
  location: Location;
  places: Place[];
  radius: number;
  filters: Category[];
  onPick: (p: Location) => void;
  destination: Location | null;
  centerTick: number;
}) {
  const root = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    layer = useRef<L.LayerGroup | null>(null),
    pick = useRef(onPick);
  const [tileError, setTileError] = useState(false);
  pick.current = onPick;
  useEffect(() => {
    if (!root.current) return;
    const m = L.map(root.current, {
      zoomControl: false,
      scrollWheelZoom: false,
    }).setView([location.latitude, location.longitude], 14);
    map.current = m;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    })
      .on("tileerror", () => setTileError(true))
      .addTo(m);
    L.control.zoom({ position: "bottomright" }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) =>
      pick.current({
        latitude: e.latlng.lat,
        longitude: e.latlng.lng,
        label: `Map location · ${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`,
      }),
    );
    const resize = new ResizeObserver(() => m.invalidateSize());
    resize.observe(root.current);
    return () => {
      resize.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current,
      g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    m.setView([location.latitude, location.longitude], radius > 1100 ? 13 : 14);
    L.circle([location.latitude, location.longitude], {
      radius,
      color: "#2867d9",
      weight: 1,
      dashArray: "5 6",
      fillColor: "#85baff",
      fillOpacity: 0.12,
    }).addTo(g);
    L.marker([location.latitude, location.longitude], {
      icon: L.divIcon({
        className: "home-pin",
        html: "<span>⌂</span>",
        iconSize: [42, 42],
        iconAnchor: [21, 21],
      }),
    })
      .addTo(g)
      .bindPopup(popupText(location.label));
    places
      .filter((p) => filters.includes(p.category))
      .forEach((p) => {
        L.marker([p.latitude, p.longitude], {
          icon: L.divIcon({
            className: `place-pin ${p.category}`,
            html: `<span>${symbols[p.category]}</span>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          }),
        })
          .addTo(g)
          .bindPopup(popupText(p.label));
      });
    if (destination) {
      L.marker([destination.latitude, destination.longitude], {
        icon: L.divIcon({
          className: "destination-pin",
          html: "<span>⚑</span>",
          iconSize: [32, 32],
        }),
      })
        .addTo(g)
        .bindPopup(popupText(destination.label));
      L.polyline(
        [
          [location.latitude, location.longitude],
          [destination.latitude, destination.longitude],
        ],
        { color: "#805a9a", weight: 2, dashArray: "5 7" },
      ).addTo(g);
      m.fitBounds(
        [
          [location.latitude, location.longitude],
          [destination.latitude, destination.longitude],
        ],
        { padding: [45, 45] },
      );
    }
  }, [location, places, radius, filters, destination, centerTick]);
  return (
    <>
      <div
        ref={root}
        className="map-canvas"
        aria-label="Interactive Warsaw map. Click to select a home location."
      />
      {tileError && (
        <div className="map-error">
          Map tiles unavailable. Pins still work; check your connection.
        </div>
      )}
      <div className="map-hint">Or pick a spot on the map</div>
    </>
  );
}
```

## src/main.tsx

```tsx
import React, { useState, useMemo } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  ArrowRight,
  MapPin,
  Search,
  SlidersHorizontal,
  TrainFront,
  ShoppingBasket,
  TreePine,
  Cross,
  ParkingCircle,
  ArrowLeftRight,
  Navigation,
  Info,
  X,
  Check,
  ChevronDown,
  LoaderCircle,
  Compass,
} from "lucide-react";
import NeighborhoodMap from "./Map";
import { homes, destinations, demoAnalysis } from "./demo";
import { analyze, geocode, API_BASE_URL } from "./api";
import { distance, meters, inWarsaw } from "./geo";
import type { Category, Location, Analysis } from "./types";
import "./style.css";
const cats: {
  id: Category;
  label: string;
  icon: typeof TrainFront;
  color: string;
}[] = [
  { id: "transport", label: "Transport", icon: TrainFront, color: "blue" },
  { id: "grocery", label: "Groceries", icon: ShoppingBasket, color: "orange" },
  { id: "pharmacy", label: "Pharmacies", icon: Cross, color: "pink" },
  { id: "green", label: "Green spaces", icon: TreePine, color: "green" },
  { id: "parking", label: "Parking", icon: ParkingCircle, color: "purple" },
];
function App() {
  const [mode, setMode] = useState<"demo" | "live">("demo"),
    [location, setLocation] = useState<Location>(homes[0]),
    [query, setQuery] = useState(homes[0].label),
    [radius, setRadius] = useState(1000),
    [filters, setFilters] = useState<Category[]>(cats.map((c) => c.id)),
    [result, setResult] = useState<Analysis | null>(null),
    [saved, setSaved] = useState<Analysis[]>([]),
    [tab, setTab] = useState("explore"),
    [busy, setBusy] = useState(false),
    [searching, setSearching] = useState(false),
    [error, setError] = useState(""),
    [matches, setMatches] = useState<Location[]>([]),
    [destination, setDestination] = useState<Location | null>(null),
    [destQuery, setDestQuery] = useState(""),
    [destMatches, setDestMatches] = useState<Location[]>([]),
    [about, setAbout] = useState(false),
    [centerTick, setCenterTick] = useState(0);
  const initial = useMemo(
    () => demoAnalysis(location, radius),
    [location, radius],
  );
  const shown = result?.places || (mode === "demo" ? initial.places : []);
  const active = result?.location || location;
  function select(p: Location) {
    if (!inWarsaw(p)) {
      setError("Choose a location within Warsaw.");
      return;
    }
    setLocation(p);
    setQuery(p.label);
    setResult(null);
    setMatches([]);
    setError("");
  }
  function changeMode(m: "demo" | "live") {
    setMode(m);
    setResult(null);
    setSaved([]);
    setError("");
    setMatches([]);
    setDestMatches([]);
    setDestination(null);
    setTab("explore");
  }
  async function searchAddress(dest = false) {
    setError("");
    setSearching(true);
    try {
      const q = dest ? destQuery : query;
      if (mode === "demo") {
        const all = dest ? destinations : homes;
        const matches = all.filter((p) =>
          p.label.toLowerCase().includes(q.toLowerCase().trim()),
        );
        if (!matches.length)
          throw new Error(
            "Demo mode includes the example addresses below. Select one, or choose a point on the map.",
          );
        dest ? setDestMatches(matches) : setMatches(matches);
      } else {
        const found = await geocode(q);
        if (!found.length)
          throw new Error(
            "No matching Warsaw address. Try another address or select a point on the map.",
          );
        dest ? setDestMatches(found) : setMatches(found);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSearching(false);
    }
  }
  async function run() {
    setBusy(true);
    setError("");
    try {
      let target = location;
      if (query.trim() && query.trim() !== location.label) {
        const found =
          mode === "demo"
            ? homes.filter((p) =>
                p.label.toLowerCase().includes(query.toLowerCase().trim()),
              )
            : await geocode(query);
        if (found.length !== 1) {
          setMatches(found);
          throw new Error(
            found.length
              ? "Choose a matching address, then explore."
              : "Address not found. Try an example or choose a point on the map.",
          );
        }
        target = found[0];
        setLocation(target);
        setQuery(target.label);
      }
      const data =
        mode === "demo"
          ? demoAnalysis(target, radius)
          : await analyze({ ...target, radius_m: radius, destination });
      setResult({ ...data, radius_m: radius });
      setTab("explore");
      setTimeout(
        () =>
          document
            .getElementById("report")
            ?.scrollIntoView({ behavior: "smooth", block: "start" }),
        80,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function save() {
    if (!result) return;
    setSaved((prev) => {
      if (
        prev.some(
          (p) =>
            p.location.latitude === result.location.latitude &&
            p.location.longitude === result.location.longitude,
        )
      )
        return prev;
      return [...prev.slice(-1), result];
    });
    setTab("compare");
    setTimeout(
      () =>
        document
          .getElementById("comparison")
          ?.scrollIntoView({ behavior: "smooth" }),
      50,
    );
  }
  const savedCurrent =
    result &&
    saved.some(
      (p) =>
        p.location.latitude === result.location.latitude &&
        p.location.longitude === result.location.longitude,
    );
  return (
    <>
      <header>
        <a
          className="brand"
          href="#"
          onClick={() => {
            setTab("explore");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          <span className="brand-symbol">
            u<span>l</span>
          </span>
          UrbanLens<span className="brand-city">WARSAW</span>
        </a>
        <nav aria-label="Main navigation">
          <button
            className={tab === "explore" ? "active" : ""}
            onClick={() => {
              setTab("explore");
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          >
            Explore
          </button>
          <button
            className={tab === "compare" ? "active" : ""}
            onClick={() => {
              setTab("compare");
              setTimeout(
                () =>
                  document
                    .getElementById("comparison")
                    ?.scrollIntoView({ behavior: "smooth" }),
                50,
              );
            }}
          >
            Compare
            {saved.length > 0 && <span className="count">{saved.length}</span>}
          </button>
          <button onClick={() => setAbout(true)}>Data & sources</button>
        </nav>
        <div className="mode" aria-label="Data mode">
          <button
            aria-pressed={mode === "demo"}
            className={mode === "demo" ? "selected" : ""}
            onClick={() => changeMode("demo")}
          >
            Demo
          </button>
          <button
            aria-pressed={mode === "live"}
            className={mode === "live" ? "selected" : ""}
            onClick={() => changeMode("live")}
          >
            Live <span className={API_BASE_URL ? "tiny-dot" : "offline-dot"} />
          </button>
        </div>
      </header>
      <main>
        <section className="hero">
          <div className="search-panel">
            <div className="eyebrow">Make yourself at home.</div>
            <h1>
              Find your
              <br />
              kind of <span>Warsaw.</span>
            </h1>
            <p className="intro">Look beyond the apartment.</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                searchAddress();
              }}
            >
              <label htmlFor="address">Your Warsaw address</label>
              <div className="address-field">
                <MapPin size={19} />
                <input
                  id="address"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Enter a Warsaw address"
                  autoComplete="off"
                />
                <button
                  className="search-icon"
                  disabled={searching}
                  aria-label="Search address"
                >
                  {searching ? (
                    <LoaderCircle className="spin" size={20} />
                  ) : (
                    <Search size={20} />
                  )}
                </button>
              </div>
              {matches.length > 0 && (
                <div className="matches">
                  {matches.map((p) => (
                    <button
                      type="button"
                      key={p.label}
                      onClick={() => select(p)}
                    >
                      <MapPin size={15} />
                      {p.label}
                    </button>
                  ))}
                </div>
              )}
            </form>
            <div className="example-row">
              <span>{mode === "demo" ? "TRY" : "SELECTED"}</span>
              {mode === "demo" ? (
                homes.slice(0, 2).map((p) => (
                  <button
                    key={p.label}
                    className={location.label === p.label ? "current" : ""}
                    onClick={() => select(p)}
                  >
                    {p.label.split(",")[0]}
                  </button>
                ))
              ) : (
                <small>{location.label}</small>
              )}
            </div>
            <div className="radius-row">
              <label htmlFor="radius">Search within</label>
              <div className="radius-control">
                <select
                  id="radius"
                  value={radius}
                  onChange={(e) => {
                    setRadius(Number(e.target.value));
                    setResult(null);
                  }}
                >
                  <option value={500}>500 m</option>
                  <option value={1000}>1 km</option>
                  <option value={1500}>1.5 km</option>
                  <option value={2000}>2 km</option>
                </select>
                <ChevronDown size={14} />
              </div>
            </div>
            <button className="analyze" onClick={run} disabled={busy}>
              {busy ? (
                <>
                  <LoaderCircle size={19} className="spin" />
                  Analyzing neighborhood…
                </>
              ) : (
                <>
                  Explore neighborhood <ArrowRight size={21} />
                </>
              )}
            </button>
          </div>
          <div className="map-panel">
            <NeighborhoodMap
              location={active}
              radius={radius}
              places={shown}
              filters={filters}
              onPick={select}
              destination={destination}
              centerTick={centerTick}
            />
            <div className="map-title">
              <span className="tiny-dot" /> Warsaw
            </div>
            <div className="map-demo">
              {mode === "demo" ? "Demo places" : "Live mode"}
            </div>
            <button
              className="map-center"
              aria-label="Recenter map"
              title="Recenter map"
              onClick={() => setCenterTick((t) => t + 1)}
            >
              <Navigation size={18} />
            </button>
          </div>
        </section>
        <div className="category-bar">
          <span className="filter-label">Show on map</span>
          <div className="filter-buttons">
            {cats.map((c) => (
              <button
                key={c.id}
                aria-pressed={filters.includes(c.id)}
                className={`${c.color} ${filters.includes(c.id) ? "on" : ""}`}
                onClick={() =>
                  setFilters((p) =>
                    p.includes(c.id)
                      ? p.filter((x) => x !== c.id)
                      : [...p, c.id],
                  )
                }
              >
                <c.icon size={17} />
                {c.label}
                <span className="filter-dot" />
              </button>
            ))}
          </div>
        </div>
        <div className="status-note">
          <Info size={14} />
          {mode === "demo"
            ? "Demo · Illustrative places on a real map."
            : API_BASE_URL
              ? "Live · Connected to your data service."
              : "Live analysis isn’t connected yet. Try Demo."}
        </div>
        {error && (
          <div className="error" role="alert">
            <Info size={18} />
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={17} />
            </button>
          </div>
        )}
        {!result && tab === "explore" && (
          <section className="before-report">
            <h2>
              A place for <span>your everyday.</span>
            </h2>
            <p>Essentials nearby. Your commute in view.</p>
            <div className="city-doodle" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </section>
        )}
        {result && (
          <section className="report" id="report">
            <div className="section-heading">
              <div>
                <span className="section-kicker">
                  {result.demo ? "Demo report" : "Neighborhood report"}
                </span>
                <h2>Around your address.</h2>
                <p>
                  {result.location.label}{" "}
                  <span className="muted">· Within {meters(radius)}</span>
                </p>
              </div>
              <button className="outline-btn" onClick={save}>
                {savedCurrent ? "Added to comparison" : "Compare this home"}
              </button>
            </div>
            <div className="metrics">
              {cats.map((c) => {
                const list = result.places
                  .filter((p) => p.category === c.id)
                  .sort(
                    (a, b) =>
                      (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity),
                  );
                const unavailable = result.unavailable.includes(c.id);
                return (
                  <a
                    className="metric"
                    key={c.id}
                    href={`#list-${c.id}`}
                    onClick={() => {
                      const el = document.getElementById(
                        `list-${c.id}`,
                      ) as HTMLDetailsElement | null;
                      if (el) el.open = true;
                    }}
                  >
                    <div className={`metric-icon ${c.color}`}>
                      <c.icon size={22} />
                    </div>
                    <span className="metric-title">{c.label}</span>
                    <strong>{unavailable ? "—" : list.length}</strong>
                    <span className="metric-desc">
                      {unavailable
                        ? "Data unavailable"
                        : list.length
                          ? `Nearest: ${meters(list[0].distance_m)}`
                          : "No objects returned"}
                    </span>
                  </a>
                );
              })}
            </div>
            <div className="report-detail">
              <div className="detail-title">
                <h3>Nearby places</h3>
                <div className="distance-note">
                  <Compass size={18} />
                  <span>
                    {result.demo
                      ? "Straight-line distances. Demo places."
                      : "Distance types are shown per place."}
                  </span>
                </div>
              </div>
              <div className="place-groups">
                {cats.map((c) => (
                  <details id={`list-${c.id}`} key={c.id}>
                    <summary>
                      <span>
                        <c.icon size={17} />
                        {c.label}
                      </span>
                      <span>
                        {result.unavailable.includes(c.id)
                          ? "Unavailable"
                          : `${result.places.filter((p) => p.category === c.id).length} places`}{" "}
                        <ChevronDown size={16} />
                      </span>
                    </summary>
                    <div className="place-list">
                      {result.unavailable.includes(c.id) ? (
                        <p className="empty-small">
                          No reliable dataset connected for this category.
                        </p>
                      ) : (
                        result.places
                          .filter((p) => p.category === c.id)
                          .sort(
                            (a, b) =>
                              (a.distance_m ?? Infinity) -
                              (b.distance_m ?? Infinity),
                          )
                          .map((p) => (
                            <div className="place-row" key={p.id}>
                              <span>
                                {p.label}
                                {p.lines?.length ? (
                                  <small>Lines: {p.lines.join(", ")}</small>
                                ) : null}
                              </span>
                              <span>
                                <strong>{meters(p.distance_m)}</strong>
                                <small>
                                  {p.distance_type === "straight_line"
                                    ? "Straight line"
                                    : p.distance_type === "walking"
                                      ? "Walking distance"
                                      : "Distance type unspecified"}
                                </small>
                              </span>
                            </div>
                          ))
                      )}
                      {!result.unavailable.includes(c.id) &&
                        !result.places.some((p) => p.category === c.id) && (
                          <p className="empty-small">
                            No objects returned within this radius.
                          </p>
                        )}
                    </div>
                  </details>
                ))}
              </div>
            </div>
            <section className="commute" id="commute">
              <div>
                <span className="section-kicker">Your daily journey</span>
                <h2>How far is your everyday?</h2>
                <p>Choose your work or university.</p>
              </div>
              <div className="commute-form">
                <label htmlFor="dest">Your destination</label>
                <form
                  className="address-field"
                  onSubmit={(e) => {
                    e.preventDefault();
                    searchAddress(true);
                  }}
                >
                  <MapPin size={18} />
                  <input
                    id="dest"
                    placeholder="Search a destination"
                    value={destQuery}
                    onChange={(e) => setDestQuery(e.target.value)}
                  />
                  <button aria-label="Search destination" disabled={searching}>
                    <Search size={18} />
                  </button>
                </form>
                {destMatches.length > 0 && (
                  <div className="matches">
                    {destMatches.map((p) => (
                      <button
                        key={p.label}
                        onClick={() => {
                          setDestination(p);
                          setDestQuery(p.label);
                          setDestMatches([]);
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                )}
                <div className="destination-chips">
                  {destinations.map((p) => (
                    <button
                      className={destination?.label === p.label ? "chosen" : ""}
                      key={p.label}
                      onClick={() => {
                        setDestination(p);
                        setDestQuery(p.label);
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                {destination && (
                  <div className="commute-result">
                    <div>
                      <strong>
                        {meters(distance(result.location, destination))}
                      </strong>
                      <span>Straight-line distance · {destination.label}</span>
                    </div>
                    <button
                      aria-label="Remove destination"
                      onClick={() => {
                        setDestination(null);
                        setDestQuery("");
                      }}
                    >
                      <X size={17} />
                    </button>
                  </div>
                )}
                {destination && mode === "live" && (
                  <button className="outline-btn" onClick={run} disabled={busy}>
                    Check journey <ArrowRight size={16} />
                  </button>
                )}
                {result.commute && (
                  <p className="empty-small">
                    {result.commute.status || "Backend commute"}{" "}
                    {result.commute.distance_m !== undefined &&
                      `· ${meters(result.commute.distance_m)}`}{" "}
                    {result.commute.duration_minutes !== undefined &&
                      `· ${result.commute.duration_minutes} min (${result.commute.mode || "mode unspecified"})`}
                  </p>
                )}
              </div>
            </section>
            <div className="source-line">
              <Info size={15} />
              <span>
                {result.demo
                  ? "Illustrative dataset — no retrieval timestamp."
                  : "Retrieved: " +
                    (result.retrieved_at || "Timestamp unavailable")}
                {result.retrieved_at &&
                  Date.now() - Date.parse(result.retrieved_at) > 86400000 &&
                  " · More than 24 hours old"}
              </span>
              <button onClick={() => setAbout(true)}>
                View data sources <ArrowUpRight size={13} />
              </button>
            </div>
          </section>
        )}
        {(tab === "compare" || saved.length > 0) && (
          <section className="comparison" id="comparison">
            <div className="section-heading">
              <div>
                <span className="section-kicker">Side by side</span>
                <h2>Which feels like home?</h2>
              </div>
              <button
                className="outline-btn"
                onClick={() => {
                  setTab("explore");
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              >
                Add another home <ArrowRight size={16} />
              </button>
            </div>
            {saved.length === 0 ? (
              <div className="empty-comparison">
                <h3>Your shortlist starts here.</h3>
                <p>Explore an address, then select “Compare this home”.</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>In your neighborhood</th>
                      {[0, 1].map((i) => (
                        <th key={i}>
                          {saved[i] ? (
                            <>
                              <span className="table-tag">
                                HOME {i === 0 ? "A" : "B"} ·{" "}
                                {saved[i].demo ? "DEMO" : "LIVE"}
                              </span>
                              {saved[i].location.label}
                              <button
                                className="remove-home"
                                aria-label={`Remove home ${i === 0 ? "A" : "B"}`}
                                onClick={() =>
                                  setSaved((p) => p.filter((_, n) => n !== i))
                                }
                              >
                                <X size={16} />
                              </button>
                            </>
                          ) : (
                            <span className="muted">Add a second address</span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Search radius</td>
                      {[0, 1].map((i) => (
                        <td key={i}>
                          {saved[i] ? meters(saved[i].radius_m) : "—"}
                        </td>
                      ))}
                    </tr>
                    {cats.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <c.icon size={16} />
                          {c.label}
                        </td>
                        {[0, 1].map((i) => (
                          <td key={i}>
                            {!saved[i]
                              ? "—"
                              : saved[i].unavailable.includes(c.id)
                                ? "Unavailable"
                                : `${saved[i].places.filter((p) => p.category === c.id).length} places`}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr>
                      <td>
                        <Navigation size={16} />
                        Nearest transport
                      </td>
                      {[0, 1].map((i) => (
                        <td key={i}>
                          {saved[i]
                            ? meters(
                                saved[i].places
                                  .filter((p) => p.category === "transport")
                                  .sort(
                                    (a, b) =>
                                      (a.distance_m ?? Infinity) -
                                      (b.distance_m ?? Infinity),
                                  )[0]?.distance_m,
                              )
                            : "—"}
                          {saved[i] && (
                            <small>See report for distance type</small>
                          )}
                        </td>
                      ))}
                    </tr>
                    {destination && (
                      <tr>
                        <td>Distance to {destination.label}</td>
                        {[0, 1].map((i) => (
                          <td key={i}>
                            {saved[i]
                              ? meters(distance(saved[i].location, destination))
                              : "—"}
                            <small>Straight line</small>
                          </td>
                        ))}
                      </tr>
                    )}
                  </tbody>
                </table>
                <p className="comparison-note">
                  {saved.length === 1
                    ? "Explore a second address to complete your comparison."
                    : "Each home uses the radius shown above."}
                </p>
              </div>
            )}
          </section>
        )}
      </main>
      <footer>
        <a className="footer-brand" href="#">
          UrbanLens <span>WARSAW</span>
        </a>
        <button onClick={() => setAbout(true)}>Data & sources</button>
        <small>Warsaw Open Data Hackathon 2026</small>
      </footer>
      {about && (
        <div
          className="modal-backdrop"
          onKeyDown={(e) => {
            if (e.key === "Escape") setAbout(false);
          }}
          onClick={() => setAbout(false)}
        >
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="data-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              autoFocus
              className="modal-close"
              aria-label="Close data information"
              onClick={() => setAbout(false)}
            >
              <X />
            </button>
            <span className="section-kicker">Data & sources</span>
            <h2 id="data-title">Behind the map.</h2>
            <h3>Demonstration mode</h3>
            <p>
              All nearby objects are synthetic examples. Distances are
              calculated from their illustrative coordinates. The OpenStreetMap
              base map is real.
            </p>
            <h3>Live mode</h3>
            <p>
              Neighborhood analysis comes exclusively from your team’s FastAPI
              service. Failed requests never fall back to demo data. Missing
              data is marked unavailable.
            </p>
            <div className="source-links">
              <a
                href="https://dane.um.warszawa.pl/en/catalogue/009fce84-0024-431a-aa5e-9515c539899e"
                target="_blank"
                rel="noreferrer"
              >
                Warsaw Open Data — planned stop dataset{" "}
                <ArrowUpRight size={16} />
              </a>
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
              >
                OpenStreetMap contributors — base map <ArrowUpRight size={16} />
              </a>
              <a
                href="https://operations.osmfoundation.org/policies/nominatim/"
                target="_blank"
                rel="noreferrer"
              >
                Nominatim — submitted live address searches{" "}
                <ArrowUpRight size={16} />
              </a>
            </div>
            {result?.sources.map((s, i) => (
              <p key={i}>
                {s.name}
                {s.retrieved_at && ` · ${s.retrieved_at}`}
              </p>
            ))}
            <button className="analyze" onClick={() => setAbout(false)}>
              Back to exploring <ArrowRight size={19} />
            </button>
          </section>
        </div>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

## src/style.css

```css
@import url("https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;650;700&family=Manrope:wght@500;600;700;750;800&display=swap");
:root {
  font-family: "DM Sans", Arial, sans-serif;
  color: #18314e;
  background: #fbfcfe;
  font-synthesis: none;
  font-weight: 400;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
}
button,
input,
select {
  font: inherit;
}
button,
a {
  touch-action: manipulation;
}
button {
  cursor: pointer;
  border: 0;
  background: none;
  color: inherit;
}
a {
  color: inherit;
  text-decoration: none;
}
button:disabled {
  opacity: 0.6;
  cursor: wait;
}
button:focus-visible,
a:focus-visible,
summary:focus-visible {
  outline: 3px solid #3078f1;
  outline-offset: 4px;
}
input:focus,
select:focus {
  outline: none;
}
html {
  scroll-behavior: smooth;
}
h1,
h2,
h3,
p {
  margin: 0;
}
h1,
h2,
h3 {
  font-family: Manrope, Arial, sans-serif;
}
.tiny-dot,
.offline-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  background: #4c91f3;
  border-radius: 50%;
  flex-shrink: 0;
}
.offline-dot {
  background: #a4b0be;
}
header {
  max-width: 1600px;
  margin: auto;
  height: 100px;
  display: flex;
  align-items: center;
  padding: 0 5%;
  gap: 35px;
}
.brand {
  display: flex;
  align-items: center;
  font-family: Manrope, sans-serif;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -1.2px;
  gap: 11px;
}
.brand-symbol {
  border: 2px solid #2364d2;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -6px;
  padding-right: 5px;
  color: #2364d2;
}
.brand-symbol > span {
  font-weight: 500;
  transform: rotate(22deg);
  display: inline-block;
}
.brand-city {
  font-family: "DM Sans", sans-serif;
  font-size: 11px;
  letter-spacing: 1.3px;
  font-weight: 500;
  border-left: 1px solid #c7d6e8;
  padding-left: 13px;
  margin-left: 3px;
  color: #70839b;
}
nav {
  display: flex;
  gap: 30px;
  margin: auto;
  font-size: 15px;
}
nav button {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #6a7b91;
  height: 44px;
  padding: 0;
}
nav button:hover,
nav button.active {
  color: #2364d2;
}
nav button.active {
  font-weight: 700;
}
.count {
  background: #dceafe;
  border-radius: 50%;
  font-size: 12px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
}
.mode {
  border-radius: 30px;
  padding: 4px;
  display: flex;
  gap: 2px;
  font-size: 13px;
  background: #edf2f9;
}
.mode button {
  padding: 9px 15px;
  border-radius: 24px;
  display: flex;
  gap: 7px;
  align-items: center;
}
.mode .selected {
  background: #fff;
  color: #225ab0;
  box-shadow: 0 2px 5px #193c6b12;
}
main {
  max-width: 1600px;
  margin: auto;
  padding: 0 5%;
}
.hero {
  display: grid;
  grid-template-columns: 46% 54%;
  border-radius: 22px;
  overflow: hidden;
  min-height: 590px;
  background: #e8f2ff;
}
.search-panel {
  padding: 43px 42px;
  background: #e8f2ff;
  position: relative;
  overflow: hidden;
}
.search-panel:before {
  content: "";
  position: absolute;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  border: 40px solid #dceaff;
  right: -125px;
  top: -125px;
  pointer-events: none;
}
.eyebrow {
  font-size: 15px;
  color: #4c72a3;
  font-weight: 500;
  margin-bottom: 22px;
  position: relative;
}
h1 {
  font-size: clamp(45px, 4.5vw, 70px);
  font-weight: 800;
  line-height: 1.06;
  letter-spacing: -3.3px;
  position: relative;
}
h1 > span {
  color: #2468dc;
}
.intro {
  font-size: 18px;
  color: #637e9c;
  line-height: 1.5;
  margin: 20px 0 30px;
}
.search-panel label {
  display: block;
  font-size: 14px;
  color: #3d5d82;
  margin-bottom: 10px;
  font-weight: 500;
}
.address-field {
  display: flex;
  gap: 12px;
  align-items: center;
  border: 1px solid #d7e3f2;
  background: #fff;
  color: #6f8bb0;
  border-radius: 13px;
  padding: 6px 8px 6px 16px;
  min-height: 58px;
  box-shadow: 0 3px 8px #254a7d03;
}
.address-field:focus-within {
  box-shadow: 0 0 0 3px #2872e726;
  border-color: #82b0f7;
}
.address-field input {
  background: none;
  border: 0;
  min-width: 0;
  width: 100%;
  font-size: 15px;
  color: #28435e;
  height: 40px;
}
.address-field input::placeholder {
  color: #8a9db4;
}
.address-field button {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  border-radius: 10px;
  width: 39px;
  height: 39px;
}
.search-icon {
  background: #eff5ff;
}
.example-row {
  display: flex;
  align-items: center;
  gap: 13px;
  flex-wrap: wrap;
  margin: 12px 0 26px;
  font-size: 12px;
  min-height: 18px;
}
.example-row > span {
  font-size: 11px;
  color: #738cab;
}
.example-row button {
  color: #5d7da5;
  padding: 2px 0;
  border-bottom: 1px solid #b7cbe7;
  font-size: 12px;
}
.example-row button.current {
  color: #2364d2;
  border-color: #779fe0;
}
.example-row small {
  font-size: 12px;
  overflow-wrap: anywhere;
}
.radius-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.radius-row label {
  margin: 0;
  font-size: 14px;
}
.radius-control {
  position: relative;
  display: flex;
  align-items: center;
}
.radius-control select {
  appearance: none;
  background: #ffffff90;
  border: 1px solid #c9dcf5;
  color: #315887;
  padding: 9px 36px 9px 15px;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
}
.radius-control svg {
  position: absolute;
  right: 12px;
  pointer-events: none;
}
.analyze {
  background: #2568df;
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 18px 22px;
  border-radius: 13px;
  font-size: 16px;
  font-weight: 600;
  box-shadow: 0 6px 15px #2468dc18;
  transition:
    background 0.2s,
    transform 0.2s;
}
.analyze:hover {
  background: #1657c8;
  transform: translateY(-1px);
}
.map-panel {
  position: relative;
  min-height: 500px;
  background: #e7edf4;
}
.map-canvas {
  position: absolute;
  inset: 0;
  z-index: 1;
}
.map-title {
  position: absolute;
  z-index: 500;
  top: 22px;
  left: 22px;
  padding: 12px 16px;
  border-radius: 25px;
  background: #fffffff5;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 3px 15px #1a416d10;
}
.map-demo {
  position: absolute;
  z-index: 500;
  right: 20px;
  top: 24px;
  background: #f7fbfff2;
  color: #42678f;
  font-size: 12px;
  border-radius: 25px;
  padding: 10px 14px;
  box-shadow: 0 3px 15px #1a416d10;
}
.map-center {
  position: absolute;
  z-index: 500;
  right: 20px;
  top: 80px;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  background: white;
  box-shadow: 0 2px 8px #23466f18;
  border-radius: 10px;
  color: #376596;
}
.map-hint {
  position: absolute;
  bottom: 27px;
  left: 20px;
  z-index: 500;
  background: #fffffff2;
  color: #647e9c;
  padding: 10px 14px;
  border-radius: 25px;
  font-size: 12px;
  box-shadow: 0 2px 10px #163e6b0a;
}
.map-error {
  position: absolute;
  z-index: 501;
  top: 130px;
  left: 15px;
  right: 15px;
  background: #fff2d4;
  padding: 12px;
  font-size: 14px;
  border-radius: 8px;
}
.home-pin {
  background: #296be0;
  border: 4px solid white;
  border-radius: 50%;
  box-shadow:
    0 0 0 10px #296be021,
    0 3px 8px #24436844;
  color: #fff;
  font-size: 27px;
  text-align: center;
  line-height: 30px;
}
.place-pin {
  border-radius: 50%;
  background: #fff;
  border: 1px solid #bad1ef;
  box-shadow: 0 2px 7px #253d692b;
  text-align: center;
  line-height: 26px;
  color: #386ec0;
  font-size: 18px;
}
.place-pin.transport {
  color: #3568be;
}
.place-pin.grocery {
  color: #cb8b47;
}
.place-pin.pharmacy {
  color: #bf7b8d;
}
.place-pin.green {
  color: #5a917e;
}
.destination-pin {
  color: #7b6eb2;
  font-size: 25px;
}
.leaflet-container {
  font-family: "DM Sans", sans-serif;
  background: #e8eef6;
}
.leaflet-control-attribution {
  font-size: 10px !important;
}
.leaflet-popup-content {
  font-size: 14px;
  line-height: 1.5;
}
.category-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 25px 0 12px;
  gap: 24px;
  flex-wrap: wrap;
}
.filter-label {
  font-size: 14px;
  color: #7a8da3;
}
.filter-buttons {
  display: flex;
  gap: 9px;
  flex-wrap: wrap;
  justify-content: center;
}
.filter-buttons button {
  display: flex;
  gap: 9px;
  align-items: center;
  border: 1px solid #e4eaf2;
  border-radius: 24px;
  padding: 11px 17px;
  font-size: 14px;
  color: #93a1b3;
  background: #fbfcfe;
  transition: 0.2s;
}
.filter-buttons button svg {
  display: none;
}
.filter-buttons button.on {
  background: #eaf2ff;
  color: #2b62b7;
  border-color: #ccdef8;
}
.filter-buttons button:hover {
  border-color: #8ab0ed;
}
.filter-dot {
  display: none;
}
.status-note {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  font-size: 12px;
  color: #8495aa;
  padding: 6px 0 15px;
  line-height: 1.5;
}
.status-note svg {
  display: none;
}
.error {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff0e8;
  border: 1px solid #e7bdab;
  border-radius: 10px;
  color: #87442e;
  font-size: 14px;
  padding: 16px;
  margin: 14px 0;
  line-height: 1.6;
}
.error button {
  margin-left: auto;
}
.error svg {
  flex-shrink: 0;
}
.before-report {
  position: relative;
  text-align: center;
  padding: 49px 0 60px;
  overflow: hidden;
}
.before-report h2 {
  font-size: 31px;
  letter-spacing: -1.3px;
  font-weight: 700;
}
.before-report h2 > span {
  color: #668ab9;
}
.before-report p {
  font-size: 16px;
  color: #8a9bb0;
  margin-top: 13px;
}
.city-doodle {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: 63px;
  gap: 5px;
  margin-top: 28px;
}
.city-doodle > span {
  width: 22px;
  height: 30px;
  border: 1.5px solid #b5cff3;
  border-radius: 4px 4px 0 0;
  background: #f0f6ff;
}
.city-doodle > span:nth-child(2) {
  height: 41px;
  background: #dceafe;
}
.city-doodle > span:nth-child(3) {
  height: 56px;
  width: 18px;
  border-color: #72a2e8;
  background: #b9d5ff;
  clip-path: polygon(
    40% 0,
    60% 0,
    60% 15%,
    100% 15%,
    100% 100%,
    0 100%,
    0 15%,
    40% 15%
  );
}
.city-doodle > span:nth-child(4) {
  height: 36px;
  width: 32px;
}
.city-doodle > span:nth-child(5) {
  height: 46px;
  background: #dceafe;
}
.city-doodle > span:nth-child(6) {
  height: 24px;
  width: 34px;
  border-radius: 20px 20px 0 0;
}
.section-kicker {
  font-size: 13px;
  color: #6788b1;
  font-weight: 500;
}
h2 {
  font-size: 36px;
  font-weight: 750;
  letter-spacing: -1.4px;
  line-height: 1.2;
}
.report,
.comparison {
  padding: 55px 0 25px;
  scroll-margin-top: 20px;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 30px;
}
.section-heading h2 {
  margin-top: 10px;
}
.section-heading p {
  font-size: 15px;
  margin-top: 14px;
  color: #546f90;
  line-height: 1.6;
}
.muted {
  color: #8a9db4;
}
.outline-btn {
  border: 1px solid #ccdbee;
  border-radius: 12px;
  padding: 13px 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #356bb8;
  background: #fff;
  white-space: nowrap;
}
.outline-btn:hover {
  background: #eef5ff;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.metric {
  padding: 24px 21px;
  position: relative;
  border-radius: 15px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 11px;
  background: #edf4ff;
  border: 1px solid #e2edff;
  transition: transform 0.2s;
}
.metric:nth-child(2) {
  background: #f6f1eb;
  border-color: #eee7de;
}
.metric:nth-child(3) {
  background: #f9eff2;
  border-color: #f2e5eb;
}
.metric:nth-child(4) {
  background: #edf5f2;
  border-color: #dfede6;
}
.metric:nth-child(5) {
  background: #f1f0fa;
  border-color: #e8e5f4;
}
.metric:hover {
  transform: translateY(-3px);
}
.metric-icon {
  display: none;
}
.metric-title {
  font-size: 15px;
  color: #61738c;
}
.metric strong {
  font-family: Manrope, sans-serif;
  font-size: 47px;
  font-weight: 600;
  line-height: 1.05;
  letter-spacing: -2px;
}
.metric-desc {
  font-size: 13px;
  color: #8190a4;
  line-height: 1.4;
}
.report-detail {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 65px;
  padding: 46px 0;
}
.detail-title h3 {
  font-size: 25px;
  letter-spacing: -0.8px;
}
.distance-note {
  display: flex;
  font-size: 14px;
  color: #8092aa;
  line-height: 1.7;
  margin-top: 12px;
  max-width: 240px;
}
.distance-note svg {
  display: none;
}
.place-groups details {
  border-bottom: 1px solid #dfe7f1;
  scroll-margin: 25px;
}
.place-groups summary {
  list-style: none;
  cursor: pointer;
  padding: 20px 0;
  display: flex;
  justify-content: space-between;
  font-size: 16px;
}
.place-groups summary::-webkit-details-marker {
  display: none;
}
.place-groups summary > span {
  display: flex;
  align-items: center;
  gap: 10px;
}
.place-groups summary > span > svg {
  display: none;
}
.place-groups summary > span:last-child {
  font-size: 13px;
  color: #8a9bb0;
}
.place-groups summary > span:last-child svg {
  display: block;
  transition: transform 0.2s;
}
details[open] summary > span:last-child svg {
  transform: rotate(180deg);
}
.place-row {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 17px 0;
  border-top: 1px solid #edf1f7;
  font-size: 15px;
}
.place-row > span:last-child {
  text-align: right;
  flex-shrink: 0;
}
.place-row strong {
  font-weight: 500;
}
.place-row small,
table small {
  display: block;
  font-size: 12px;
  color: #899ab1;
  margin-top: 5px;
}
.empty-small {
  font-size: 14px;
  line-height: 1.7;
  color: #8093ac;
  padding: 8px 0 20px;
}
.commute {
  background: #e8f2ff;
  border-radius: 20px;
  display: grid;
  grid-template-columns: 1fr 1.25fr;
  gap: 60px;
  padding: 38px;
}
.commute h2 {
  margin: 12px 0;
  font-size: 32px;
  max-width: 290px;
}
.commute p {
  font-size: 16px;
  color: #728bac;
  line-height: 1.7;
}
.commute-form label {
  font-size: 14px;
  display: block;
  margin-bottom: 12px;
  color: #56759c;
}
.commute-form .address-field {
  min-height: 54px;
}
.destination-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.destination-chips button {
  font-size: 12px;
  border: 1px solid #ccdef6;
  border-radius: 18px;
  padding: 8px 11px;
  color: #6586b1;
  background: #ffffff60;
  text-align: left;
}
.destination-chips button.chosen {
  background: #cce1ff;
  border-color: #7aa9ee;
  color: #2a62b6;
}
.commute-result {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-top: 20px;
}
.commute-result strong {
  font-size: 32px;
  font-family: Manrope, sans-serif;
  color: #2867ce;
}
.commute-result span {
  display: block;
  font-size: 13px;
  margin-top: 7px;
  color: #7892b3;
  line-height: 1.6;
}
.commute-form > .outline-btn {
  margin-top: 15px;
}
.source-line {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #8a9cb3;
  font-size: 12px;
  padding: 21px 0;
  line-height: 1.6;
}
.source-line > svg {
  display: none;
}
.source-line button {
  display: flex;
  gap: 5px;
  align-items: center;
  margin-left: auto;
  color: #6887b0;
  font-size: 13px;
}
.comparison {
  padding-bottom: 55px;
}
.empty-comparison {
  padding: 45px;
  text-align: center;
  border-radius: 18px;
  background: #edf4ff;
}
.empty-comparison h3 {
  font-size: 24px;
  margin: 0 0 15px;
}
.empty-comparison p {
  font-size: 15px;
  color: #7b93b2;
  line-height: 1.8;
}
.table-wrap {
  border: 1px solid #e0e9f5;
  border-radius: 17px;
  overflow: auto;
  background: white;
}
table {
  border-collapse: collapse;
  width: 100%;
  table-layout: fixed;
  font-size: 15px;
}
th,
td {
  padding: 23px;
  text-align: left;
  border-bottom: 1px solid #e8eef6;
  line-height: 1.6;
}
th {
  background: #edf4ff;
  font-size: 16px;
  position: relative;
}
th:first-child {
  font-weight: 400;
  color: #7d95b4;
}
td:first-child {
  color: #6d87a9;
}
td svg {
  display: none;
}
td + td,
th + th {
  border-left: 1px solid #e5ecf6;
}
.table-tag {
  font-size: 12px;
  color: #6687b3;
  display: block;
  margin-bottom: 8px;
}
.remove-home {
  position: absolute;
  right: 8px;
  top: 8px;
  color: #8a9fbb;
}
.comparison-note {
  padding: 18px 23px;
  color: #8299b8;
  font-size: 13px;
  line-height: 1.7;
}
.matches {
  background: #fff;
  border: 1px solid #d3e2f7;
  padding: 5px;
  border-radius: 12px;
  color: #315f9f;
  margin: 8px 0;
}
.matches button {
  display: flex;
  align-items: center;
  gap: 7px;
  text-align: left;
  font-size: 14px;
  padding: 12px;
  border-radius: 7px;
  width: 100%;
  line-height: 1.6;
}
.matches button:hover {
  background: #edf4ff;
}
footer {
  background: #f1f6fd;
  color: #6d8aaf;
  padding: 30px 5%;
  display: flex;
  align-items: center;
  gap: 30px;
  flex-wrap: wrap;
  font-size: 14px;
}
.footer-brand {
  font-family: Manrope, sans-serif;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.6px;
  color: #315888;
}
.footer-brand span {
  font:
    11px "DM Sans",
    sans-serif;
  letter-spacing: 1px;
  color: #88a0bf;
  margin-left: 8px;
}
footer > button {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
}
footer > small {
  font-size: 12px;
  color: #94a8c2;
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: #142c50a8;
  backdrop-filter: blur(5px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modal {
  background: #fbfcff;
  padding: 40px;
  border-radius: 20px;
  max-width: 610px;
  max-height: 90vh;
  overflow: auto;
  position: relative;
  box-shadow: 0 20px 80px #152c5630;
}
.modal-close {
  position: absolute;
  right: 17px;
  top: 17px;
}
.modal h2 {
  margin: 17px 0;
}
.modal > p {
  font-size: 15px;
  color: #7188a6;
  line-height: 1.8;
  margin-bottom: 15px;
}
.modal h3 {
  font-size: 17px;
  margin: 24px 0 9px;
}
.source-links {
  margin: 22px 0;
  border-top: 1px solid #d7e3f3;
}
.source-links a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  padding: 16px 0;
  border-bottom: 1px solid #d7e3f3;
  gap: 12px;
  color: #4b79b5;
  line-height: 1.6;
}
.source-links svg {
  flex-shrink: 0;
}
.modal .analyze {
  margin-top: 23px;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (min-width: 1450px) {
  .search-panel {
    padding: 50px;
  }
  .hero {
    min-height: 640px;
  }
  h1 {
    font-size: 76px;
  }
  .intro {
    margin: 22px 0 35px;
  }
  .example-row {
    margin-bottom: 30px;
  }
  .analyze {
    padding: 20px 23px;
  }
}
@media (max-width: 1100px) {
  header {
    gap: 20px;
  }
  .brand-city {
    display: none;
  }
  nav {
    gap: 23px;
    font-size: 14px;
  }
  .search-panel {
    padding: 35px 30px;
  }
  h1 {
    font-size: 54px;
    letter-spacing: -2.8px;
  }
  .hero {
    grid-template-columns: 47% 53%;
    min-height: 560px;
  }
  .intro {
    font-size: 17px;
  }
  .example-row {
    gap: 9px;
  }
  .metric {
    padding: 20px 15px;
  }
  .metric-title {
    font-size: 14px;
  }
  .metric-desc {
    font-size: 12px;
  }
  .commute {
    gap: 30px;
  }
  .map-title {
    left: 15px;
  }
  .map-demo {
    right: 15px;
  }
  .filter-label {
    font-size: 13px;
  }
  .filter-buttons button {
    font-size: 13px;
  }
  .category-bar {
    gap: 17px;
  }
}
@media (max-width: 760px) {
  header {
    height: auto;
    min-height: 104px;
    padding: 17px 5% 0;
    flex-wrap: wrap;
    gap: 12px;
  }
  .brand {
    font-size: 23px;
  }
  .brand-symbol {
    width: 31px;
    height: 31px;
    font-size: 23px;
  }
  .mode {
    margin-left: auto;
    font-size: 12px;
  }
  .mode button {
    padding: 8px 12px;
  }
  nav {
    order: 3;
    width: 100%;
    height: 45px;
    justify-content: center;
    gap: 35px;
    font-size: 14px;
  }
  nav button {
    height: 40px;
  }
  main {
    padding: 12px 5% 0;
  }
  .hero {
    display: flex;
    flex-direction: column;
    border-radius: 20px;
    min-height: 0;
  }
  .search-panel {
    padding: 31px 26px;
  }
  h1 {
    font-size: 53px;
    letter-spacing: -2.8px;
  }
  .eyebrow {
    font-size: 14px;
    margin-bottom: 20px;
  }
  .intro {
    font-size: 17px;
    margin: 18px 0 27px;
  }
  .example-row {
    font-size: 12px;
    gap: 12px;
    margin-bottom: 24px;
  }
  .example-row button {
    font-size: 12px;
  }
  .radius-row {
    margin-bottom: 18px;
  }
  .address-field input {
    font-size: 14px;
  }
  .analyze {
    font-size: 15px;
    padding: 18px 20px;
  }
  .map-panel {
    min-height: 370px;
  }
  .map-title {
    font-size: 13px;
    top: 18px;
    left: 16px;
    padding: 10px 14px;
  }
  .map-demo {
    top: 19px;
    right: 16px;
    font-size: 11px;
  }
  .map-center {
    top: 72px;
    right: 16px;
  }
  .map-hint {
    font-size: 11px;
    left: 15px;
  }
  .category-bar {
    gap: 13px;
    padding: 23px 0 13px;
  }
  .filter-label {
    display: none;
  }
  .filter-buttons {
    gap: 7px;
  }
  .filter-buttons button {
    font-size: 13px;
    padding: 10px 13px;
  }
  .status-note {
    font-size: 12px;
    text-align: center;
    padding: 4px 10px 13px;
  }
  .before-report {
    padding: 35px 0 43px;
  }
  .before-report h2 {
    font-size: 25px;
    line-height: 1.4;
    letter-spacing: -1px;
  }
  .before-report p {
    font-size: 14px;
    line-height: 1.7;
    max-width: 240px;
    margin: 10px auto 0;
  }
  .city-doodle {
    margin-top: 21px;
    height: 55px;
  }
  .report,
  .comparison {
    padding-top: 35px;
  }
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 20px;
    margin-bottom: 25px;
  }
  .section-heading h2 {
    font-size: 29px;
  }
  .section-heading p {
    font-size: 14px;
  }
  .section-kicker {
    font-size: 12px;
  }
  .metrics {
    grid-template-columns: repeat(2, 1fr);
    gap: 9px;
  }
  .metric {
    padding: 21px 18px;
    gap: 10px;
  }
  .metric:last-child {
    grid-column: 1/-1;
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
  }
  .metric:last-child .metric-desc {
    grid-column: 1;
  }
  .metric:last-child strong {
    grid-column: 2;
    grid-row: 1/3;
  }
  .metric-title {
    font-size: 15px;
  }
  .metric strong {
    font-size: 41px;
  }
  .metric-desc {
    font-size: 13px;
  }
  .report-detail {
    grid-template-columns: 1fr;
    gap: 12px;
    padding: 32px 0;
  }
  .detail-title h3 {
    font-size: 24px;
  }
  .distance-note {
    max-width: none;
    font-size: 13px;
    margin-top: 9px;
  }
  .place-groups summary {
    font-size: 15px;
    padding: 19px 0;
  }
  .place-row {
    font-size: 14px;
  }
  .place-row small {
    font-size: 11px;
  }
  .commute {
    grid-template-columns: 1fr;
    padding: 27px 23px;
    gap: 25px;
    border-radius: 17px;
  }
  .commute h2 {
    font-size: 29px;
    max-width: none;
  }
  .commute p {
    font-size: 15px;
  }
  .commute-form label {
    font-size: 14px;
  }
  .destination-chips button {
    font-size: 12px;
  }
  .source-line {
    flex-wrap: wrap;
    font-size: 12px;
    gap: 10px;
  }
  .source-line button {
    margin: 0;
  }
  .comparison {
    padding-bottom: 35px;
  }
  .table-wrap {
    overflow-x: auto;
  }
  table {
    min-width: 600px;
    font-size: 14px;
  }
  th,
  td {
    padding: 18px;
  }
  .comparison-note {
    font-size: 12px;
  }
  .empty-comparison {
    padding: 30px 23px;
  }
  .empty-comparison h3 {
    font-size: 22px;
  }
  .empty-comparison p {
    font-size: 14px;
  }
  footer {
    padding: 26px 5%;
    gap: 20px;
  }
  footer > small {
    width: 100%;
    font-size: 11px;
  }
  .footer-brand {
    font-size: 20px;
  }
  .footer-brand span {
    font-size: 10px;
  }
  .modal {
    padding: 32px 25px;
  }
  .modal h2 {
    font-size: 30px;
  }
  .modal > p {
    font-size: 14px;
  }
  .source-links a {
    font-size: 13px;
  }
  .error {
    font-size: 13px;
  }
}
@media (max-width: 360px) {
  h1 {
    font-size: 46px;
  }
  .search-panel {
    padding: 28px 21px;
  }
  .example-row {
    gap: 8px;
  }
  .example-row button {
    font-size: 11px;
  }
  .mode button {
    padding: 7px 10px;
  }
  .brand {
    font-size: 21px;
  }
  nav {
    gap: 25px;
  }
}
@media (prefers-reduced-motion: reduce) {
  html {
    scroll-behavior: auto;
  }
  .spin {
    animation: none;
  }
  * {
    transition: none !important;
  }
}
```

## tests/analysis.test.mjs

```javascript
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
```
