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
