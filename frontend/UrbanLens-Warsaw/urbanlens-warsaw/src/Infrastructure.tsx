import type { Analysis, Category, Place } from "./types";
import { meters } from "./geo";

export function InfrastructureSummary({ result, category }: { result: Analysis; category: Category }) {
  if (result.demo) return null;
  const data = result.datasets?.[category];
  const missing = result.unavailable.includes(category);
  const f = result.features;
  return <div className="infrastructure-summary" aria-live="polite">
    {category === "transport" && result.scores?.mobility !== undefined &&
      <p><strong>Mobility Score: {result.scores.mobility} / 100</strong></p>}
    {category === "green" && <>
      {!missing && <p>Nearest listed park: <strong>{meters(f?.nearest_park_m ?? undefined)}</strong> · {f?.parks_within_radius ?? 0} distinct parks within radius.</p>}
      <p>Straight-line distance to the park area, zero inside. This does not measure distance to an entrance or a walking route. Markers show representative locations.</p>
      <p>Named parks only; coverage of all Warsaw green space is unverified.</p>
    </>}
    {category === "parking" && <>
      {!missing && <p>Nearest listed parking: <strong>{meters(f?.nearest_listed_parking_m ?? undefined)}</strong> · {f?.listed_parking_within_radius ?? 0} listed facilities within radius.</p>}
      <p>Incomplete coverage: participating municipal operators only. No listed facilities does not mean no parking exists. Current space availability is unavailable.</p>
    </>}
    {data?.retrieved_at && <small>Snapshot retrieved: {data.retrieved_at}</small>}
    {data?.truncated && <p>Showing {data.limit} of {data.total} nearby places.</p>}
  </div>;
}

export function FacilityDetails({ place }: { place: Place }) {
  if (place.category !== "parking") return null;
  return <div className="facility-details">
    {place.address && <p>{place.address}</p>}
    {place.capacity !== undefined && <p>Listed capacity: {place.capacity}</p>}
    {place.opening_hours?.length ? <details><summary>Listed opening hours</summary>
      {place.opening_hours.map((days, i) => <p key={i}>{Object.entries(days).map(([day, hours]) => `${day}: ${hours}`).join(" · ")}</p>)}
    </details> : null}
    {place.tariffs?.length ? <details><summary>Listed tariffs (source units)</summary>
      {place.tariffs.map((tariff, i) => <p key={i}>{tariff.VehicleType}: {Array.isArray(tariff.Prices) ? tariff.Prices.map(p => `${p.StayLength}: ${p.StayPrice}`).join(" · ") : "Details unavailable"}</p>)}
      <small>Verify currency, duration units and current prices with the operator.</small>
    </details> : null}
    <p>Current availability unavailable; observation time unverified.</p>
  </div>;
}
