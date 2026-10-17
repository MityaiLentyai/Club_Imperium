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
  distance_basis?: "park_area" | "facility_point";
  capacity?: number;
  address?: string;
  opening_hours?: Record<string, string>[];
  tariffs?: { VehicleType: string; Prices: { StayLength: string; StayPrice: string }[] }[];
  availability_status?: string;
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
  scores?: { mobility?: number; green?: number };
  features?: {
    nearest_park_m?: number | null;
    parks_within_radius?: number | null;
    nearest_listed_parking_m?: number | null;
    listed_parking_within_radius?: number | null;
  };
  datasets?: Partial<Record<Category, {
    status: string;
    retrieved_at?: string;
    total?: number;
    limit?: number;
    truncated?: boolean;
    coverage?: string;
  }>>;
}
export interface AnalyzeRequest {
  latitude: number;
  longitude: number;
  radius_m: number;
  destination: Location | null;
}
