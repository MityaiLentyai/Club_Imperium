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
