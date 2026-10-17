import { useEffect, useRef, useState, type ReactElement } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Category, Location, Place } from "./types";
import { meters } from "./geo";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { House } from "lucide-react";
import { cats } from "./ui";

// Leaflet markers take HTML strings, so the icons are rendered to SVG markup once.
function renderToStaticMarkup(el: ReactElement) {
  const div = document.createElement("div");
  const root = createRoot(div);
  flushSync(() => root.render(el));
  const html = div.innerHTML;
  root.unmount();
  return html;
}
const pinIcons = Object.fromEntries(
  cats.map((c) => [c.id, renderToStaticMarkup(<c.icon size={15} strokeWidth={2.4} />)]),
) as Record<Category, string>;
const homeIcon = renderToStaticMarkup(<House size={20} strokeWidth={2.4} />);

function textNode(text: string) {
  const el = document.createElement("div");
  el.textContent = text;
  return el;
}

export default function NeighborhoodMap({
  location,
  radius,
  showHome,
  places,
  filters,
  focusedId,
  hoveredId,
  destination,
  centerTick,
  onFocusPlace,
  onPick,
}: {
  location: Location;
  radius: number;
  showHome: boolean;
  places: Place[];
  filters: Category[];
  focusedId: string | null;
  hoveredId: string | null;
  destination: Location | null;
  centerTick: number;
  onFocusPlace: (p: Place) => void;
  onPick: (p: Location) => void;
}) {
  const root = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    homeLayer = useRef<L.LayerGroup | null>(null),
    placeLayer = useRef<L.LayerGroup | null>(null),
    destLayer = useRef<L.LayerGroup | null>(null),
    markers = useRef(new Map<string, L.Marker>()),
    fit = useRef<() => void>(() => {}),
    pick = useRef(onPick),
    focus = useRef(onFocusPlace);
  const [tileError, setTileError] = useState(false);
  pick.current = onPick;
  focus.current = onFocusPlace;

  useEffect(() => {
    if (!root.current) return;
    const m = L.map(root.current, {
      zoomControl: false,
      scrollWheelZoom: true,
      zoomSnap: 0.25,
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
    homeLayer.current = L.layerGroup().addTo(m);
    destLayer.current = L.layerGroup().addTo(m);
    placeLayer.current = L.layerGroup().addTo(m);
    const pending = L.layerGroup().addTo(m);
    // A click only proposes a spot; the home moves after the user confirms,
    // so panning or a stray tap never throws away the current analysis.
    m.on("click", (e: L.LeafletMouseEvent) => {
      pending.clearLayers();
      const { lat, lng } = e.latlng;
      const content = document.createElement("div");
      content.className = "pick-popup";
      const coords = document.createElement("span");
      coords.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.textContent = "Explore this spot";
      confirm.onclick = () => {
        pending.clearLayers();
        pick.current({
          latitude: lat,
          longitude: lng,
          label: `Pinned spot, ${lat.toFixed(4)} N ${lng.toFixed(4)} E`,
        });
      };
      content.append(coords, confirm);
      const marker = L.marker(e.latlng, {
        icon: L.divIcon({ className: "pending-pin", iconSize: [18, 18] }),
      })
        .addTo(pending)
        .bindPopup(content, { offset: [0, -4] })
        .on("popupclose", () => pending.removeLayer(marker))
        .openPopup();
    });
    const resize = new ResizeObserver(() => {
      m.invalidateSize();
      fit.current();
    });
    resize.observe(root.current);
    return () => {
      resize.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const g = homeLayer.current;
    if (!g) return;
    g.clearLayers();
    L.circle([location.latitude, location.longitude], {
      radius,
      color: "#2a5379",
      weight: 1.5,
      dashArray: "6 6",
      fillColor: "#4a8ad0",
      fillOpacity: 0.08,
      interactive: false,
    }).addTo(g);
    if (!showHome) return;
    L.marker([location.latitude, location.longitude], {
      icon: L.divIcon({
        className: "home-pin",
        html: `<span>${homeIcon}</span>`,
        iconSize: [40, 40],
        iconAnchor: [20, 20],
      }),
      zIndexOffset: 1000,
    })
      .addTo(g)
      .bindTooltip(textNode(location.label), { direction: "top", offset: [0, -18] });
  }, [location, radius, showHome]);

  useEffect(() => {
    const g = destLayer.current;
    if (!g) return;
    g.clearLayers();
    if (!destination) return;
    L.marker([destination.latitude, destination.longitude], {
      icon: L.divIcon({
        className: "destination-pin",
        html: "<span>⚑</span>",
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      }),
    })
      .addTo(g)
      .bindTooltip(textNode(destination.label), { direction: "top", offset: [0, -16] });
    L.polyline(
      [
        [location.latitude, location.longitude],
        [destination.latitude, destination.longitude],
      ],
      { color: "#7a4fa8", weight: 2.5, dashArray: "6 8", interactive: false },
    ).addTo(g);
  }, [location, destination]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    fit.current = () => {
      const bounds = L.latLng(location.latitude, location.longitude).toBounds(radius * 2);
      if (destination) bounds.extend([destination.latitude, destination.longitude]);
      m.fitBounds(bounds, { padding: [24, 24], maxZoom: 16 });
    };
    fit.current();
  }, [location, radius, destination, centerTick]);

  useEffect(() => {
    const g = placeLayer.current;
    if (!g) return;
    g.clearLayers();
    markers.current.clear();
    places
      .filter((p) => filters.includes(p.category))
      .forEach((p) => {
        const marker = L.marker([p.latitude, p.longitude], {
          icon: L.divIcon({
            className: `place-pin cat-${p.category}`,
            html: `<span>${pinIcons[p.category]}</span>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
          }),
          keyboard: false,
          riseOnHover: true,
        })
          .addTo(g)
          .bindTooltip(
            textNode(p.distance_m === undefined ? p.label : `${p.label} · ${meters(p.distance_m)}`),
            { direction: "top", offset: [0, -12] },
          )
          .on("click", () => focus.current(p));
        markers.current.set(p.id, marker);
      });
  }, [places, filters]);

  // Focus and hover only restyle existing markers instead of rebuilding them.
  useEffect(() => {
    markers.current.forEach((marker, id) => {
      const el = marker.getElement();
      el?.classList.toggle("is-focused", id === focusedId);
      el?.classList.toggle("is-hovered", id === hoveredId);
      marker.setZIndexOffset(id === focusedId ? 900 : id === hoveredId ? 800 : 0);
    });
  }, [focusedId, hoveredId, places, filters]);

  useEffect(() => {
    // Only the selected place keeps its name label open.
    markers.current.forEach((m, id) => {
      if (id !== focusedId) m.closeTooltip();
    });
    const marker = focusedId ? markers.current.get(focusedId) : undefined;
    if (marker && map.current) {
      map.current.panInside(marker.getLatLng(), { padding: [60, 60] });
      marker.openTooltip();
    }
  }, [focusedId]);

  return (
    <>
      <div
        ref={root}
        className="map-canvas"
        aria-label="Map of Warsaw. Click a spot, then confirm to explore it."
      />
      {tileError && (
        <div className="map-error" role="status">
          Map tiles didn’t load. Check your connection; places still work.
        </div>
      )}
    </>
  );
}
