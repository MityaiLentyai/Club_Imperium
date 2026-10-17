import { TramFront, ShoppingBasket, Cross, TreePine, ParkingCircle, Dumbbell } from "lucide-react";
import type { Analysis, Category, Location, Place } from "./types";

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
export const COMPARE_LIMIT = 3;

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

// The backend lists every platform of a stop separately; residents think in stops,
// so rows with the same name collapse into one, keeping the nearest platform first.
export type Row = { place: Place; ids: string[] };
export function rowsOf(r: Analysis, c: Category): Row[] {
  const rows = new Map<string, Row>();
  for (const p of placesOf(r, c)) {
    const row = rows.get(p.label);
    if (row) row.ids.push(p.id);
    else rows.set(p.label, { place: p, ids: [p.id] });
  }
  return [...rows.values()];
}
