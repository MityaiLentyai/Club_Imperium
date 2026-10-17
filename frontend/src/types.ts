export type Category =
  | "transport"
  | "grocery"
  | "pharmacy"
  | "green"
  | "parking"
  | "sports";
// Categories the backend's personalized LifeScore accepts weights for.
export type WeightKey = "mobility" | "green" | "parking" | "sports" | "commute";
export type Weights = Partial<Record<WeightKey, number>>;
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
  // Short facts from the source dataset (address, capacity, sport types…).
  details?: string[];
}
export interface Mobility {
  score: number;
  nearest_stop_m?: number;
  stop_groups_500m?: number;
  stop_groups_1000m?: number;
}
export interface LifeScore {
  value: number | null;
  status: string;
  label: string;
  requested: Weights;
  normalized: Weights;
  excluded: Partial<Record<WeightKey, string>>;
  explanation?: string;
}
// Nearest object of an optional category, even when it lies outside the radius.
export interface Nearest {
  distance_m: number | null;
  within_radius: number | null;
}
export interface Analysis {
  location: Location;
  radius_m: number;
  places: Place[];
  unavailable: Category[];
  mobility?: Mobility;
  lifeScore?: LifeScore;
  nearest?: Partial<Record<Category, Nearest>>;
  nearestStopLines?: string[];
  // Set when the backend capped the transport list.
  nearby?: { total: number; truncated: boolean };
  sources: { name: string; url?: string; retrieved_at?: string }[];
  retrieved_at?: string;
  weights?: Weights;
  demo: boolean;
}
export type Route =
  | { status: "available"; distance_m: number; duration_minutes: number; path: [number, number][] }
  | { status: "unavailable"; reason: string };
export interface Commute {
  baseline_m: number;
  walking: Route;
  driving: Route;
  transit: Route;
  attribution?: { name: string; url?: string; fix_map_url?: string };
}
export interface ComparisonRow {
  metric: string;
  values: (number | null)[];
  unit: string;
  preference: "higher" | "lower";
  status: "comparable" | "incomparable" | "unavailable";
  advantage: "a" | "b" | "equal" | null;
  reason: string | null;
}
export interface Comparison {
  locations: Analysis[];
  rows: ComparisonRow[];
  warnings: string[];
}
