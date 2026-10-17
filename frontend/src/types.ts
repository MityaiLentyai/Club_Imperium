export type Category =
  | "transport"
  | "grocery"
  | "pharmacy"
  | "green"
  | "parking"
  | "sports";
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
export interface Mobility {
  score: number;
  nearest_stop_m?: number;
  stop_groups_500m?: number;
  stop_groups_1000m?: number;
}
export interface Analysis {
  location: Location;
  radius_m: number;
  places: Place[];
  unavailable: Category[];
  mobility?: Mobility;
  // Set when the backend capped the transport list.
  nearby?: { total: number; truncated: boolean };
  sources: { name: string; url?: string; retrieved_at?: string }[];
  retrieved_at?: string;
  demo: boolean;
}
