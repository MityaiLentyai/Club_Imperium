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
