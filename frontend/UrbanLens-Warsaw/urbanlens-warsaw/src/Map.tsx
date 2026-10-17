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
          .bindPopup(popupText(`${p.label}${p.distance_m !== undefined ? ` · ${Math.round(p.distance_m)} m straight line${p.distance_basis === "park_area" ? " to park area" : ""}` : ""}${p.capacity !== undefined ? ` · Capacity: ${p.capacity}` : ""}${p.category === "parking" ? " · Availability unverified" : ""}`));
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
