import { TramFront, ShoppingBasket, Cross, TreePine, ParkingCircle, Dumbbell } from "lucide-react";
import type { Analysis, Category, Location, Place, WeightKey } from "./types";

export const cats: {
  id: Category;
  label: string;
  // Also drawn inside map pins and list dots; the chip's color dot doubles as the map legend.
  icon: typeof TramFront;
}[] = [
  { id: "transport", label: "Transport", icon: TramFront },
  { id: "grocery", label: "Groceries", icon: ShoppingBasket },
  { id: "pharmacy", label: "Pharmacies", icon: Cross },
  { id: "green", label: "Green spaces", icon: TreePine },
  { id: "parking", label: "Parking", icon: ParkingCircle },
  { id: "sports", label: "Sports", icon: Dumbbell },
];
export const catById = Object.fromEntries(cats.map((c) => [c.id, c])) as Record<
  Category,
  (typeof cats)[number]
>;

export const radii = [500, 1000, 1500, 2000];
// The backend's /api/compare takes exactly two homes; Demo compares up to three locally.
export const compareLimit = (mode: "demo" | "live") => (mode === "live" ? 2 : 3);
export const weightLabels: Record<WeightKey, string> = {
  mobility: "Mobility",
  green: "Parks",
  parking: "Parking",
  sports: "Sports",
  commute: "Commute",
};

export const plural = (n: number, one: string, many = `${one}s`) =>
  `${n} ${n === 1 ? one : many}`;
export const samePlace = (a: Location, b: Location) =>
  Math.abs(a.latitude - b.latitude) < 1e-6 &&
  Math.abs(a.longitude - b.longitude) < 1e-6;
export const byDistance = (a: Place, b: Place) =>
  (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity);
export const placesOf = (r: Analysis, c: Category) =>
  r.places.filter((p) => p.category === c).sort(byDistance);
// The first comma-separated part of an address, used where space is tight.
export const shortLabel = (label: string) => label.split(",")[0];

// The backend has no reverse geocoding, so a spot picked on the map is named after the
// nearest stop it returned ("Near Hoża, 52.2223 N 21.0084 E"); coordinates stay visible.
export const PINNED = "Pinned spot";
export function nameSpot(a: Analysis): Analysis {
  if (!a.location.label.startsWith(PINNED)) return a;
  const stop = placesOf(a, "transport")[0];
  if (!stop) return a;
  const coords = a.location.label.slice(a.location.label.indexOf(",") + 1).trim();
  return { ...a, location: { ...a.location, label: `Near ${stop.label}, ${coords}` } };
}

// The backend lists every platform of a stop separately; residents think in stops,
// so transport rows with the same name collapse into one, keeping the nearest platform
// first. Other categories keep every place: two shops of one chain are two shops.
export type Row = { place: Place; ids: string[] };
export function rowsOf(r: Analysis, c: Category): Row[] {
  if (c !== "transport") return placesOf(r, c).map((place) => ({ place, ids: [place.id] }));
  const rows = new Map<string, Row>();
  for (const p of placesOf(r, c)) {
    const row = rows.get(p.label);
    if (row) row.ids.push(p.id);
    else rows.set(p.label, { place: p, ids: [p.id] });
  }
  return [...rows.values()];
}
