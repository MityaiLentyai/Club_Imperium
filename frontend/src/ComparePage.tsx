import { useEffect, useState } from "react";
import { ArrowLeft, Check, LoaderCircle, MapPin, Plus, Trophy, X } from "lucide-react";
import { distance, meters } from "./geo";
import { homes } from "./demo";
import { compare } from "./api";
import { cats, placesOf, rowsOf, plural, samePlace, shortLabel } from "./ui";
import type { Analysis, Comparison, ComparisonRow, Location, Weights } from "./types";
import type { Target } from "./App";
import Field from "./Field";

// One table row, whichever source it came from: the backend's /api/compare (Live, two homes)
// or the local fallback (Demo, or fewer than two homes).
type ViewRow = {
  key: string;
  label: string;
  hint?: string;
  cells: string[];
  best: number; // column index of the better value, -1 when none
  note?: string; // why no advantage could be established
};

const letters = ["A", "B", "C"];
// "Koszyki · within 1 km", or the coordinates for a pinned spot, so similar names stay distinct.
const placeLine = (s: Analysis) => {
  const second = s.location.label.split(",")[1]?.trim();
  return second ? `${second} · within ${meters(s.radius_m)}` : `within ${meters(s.radius_m)}`;
};
const minutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`);

function localRows(saved: Analysis[], destination: Location | null): ViewRow[] {
  type Raw = { key: string; label: string; hint?: string; values: (number | undefined)[]; format: (n: number) => string; better: "higher" | "lower" };
  const raw: Raw[] = [
    ...(saved.some((s) => s.mobility)
      ? [{ key: "mobility", label: "Mobility score", hint: "out of 100", values: saved.map((s) => s.mobility?.score), format: (n: number) => `${Math.round(n)}`, better: "higher" as const }]
      : []),
    { key: "stop", label: "Nearest stop", values: saved.map((s) => placesOf(s, "transport")[0]?.distance_m ?? s.mobility?.nearest_stop_m), format: meters, better: "lower" },
    ...cats.map((c) => ({
      key: c.id,
      label: c.label,
      hint: "within radius",
      values: saved.map((s) => (s.unavailable.includes(c.id) ? undefined : rowsOf(s, c.id).length)),
      format: (n: number) => plural(n, c.id === "transport" ? "stop" : "place"),
      better: "higher" as const,
    })),
    ...(destination
      ? [{ key: "dest", label: `To ${shortLabel(destination.label)}`, hint: "straight line", values: saved.map((s) => distance(s.location, destination)), format: meters, better: "lower" as const }]
      : []),
  ];
  return raw.map((r) => {
    const known = r.values.map((v, i) => [v, i] as const).filter(([v]) => v !== undefined) as [number, number][];
    let best = -1;
    if (known.length >= 2) {
      const top = r.better === "higher" ? Math.max(...known.map(([v]) => v)) : Math.min(...known.map(([v]) => v));
      const leaders = known.filter(([v]) => v === top);
      if (leaders.length === 1) best = leaders[0][1];
    }
    return { key: r.key, label: r.label, hint: r.hint, cells: r.values.map((v) => (v === undefined ? "No data" : r.format(v))), best };
  });
}

const metricLabels: Record<string, [string, string?]> = {
  mobility_score: ["Mobility score", "out of 100"],
  partial_life_score: ["Partial LifeScore", "out of 100"],
  life_score: ["LifeScore", "out of 100"],
  nearest_stop_m: ["Nearest stop"],
  stop_groups_500m: ["Stop groups", "within 500 m"],
  nearest_park_m: ["Nearest park"],
  parks_within_radius: ["Parks", "within radius"],
  nearest_listed_parking_m: ["Nearest listed parking"],
  listed_parking_within_radius: ["Listed parking", "within radius"],
  nearest_sports_facility_m: ["Nearest sports site"],
  sports_facilities_within_radius: ["Sports sites", "within radius"],
  commute_straight_line_m: ["To destination", "straight line"],
  walking_distance_m: ["Walking distance"],
  walking_duration_minutes: ["Walking time", "provider estimate"],
  driving_distance_m: ["Driving distance"],
  driving_duration_minutes: ["Driving time", "estimate, no live traffic"],
};

function formatValue(v: number | null, unit: string) {
  if (v === null) return "No data";
  if (unit === "metres") return meters(v);
  if (unit === "minutes_estimated") return minutes(v);
  if (unit === "points") return `${Math.round(v)}`;
  if (unit === "stop_groups") return plural(v, "group");
  if (unit === "listed_sites") return plural(v, "site");
  return `${v}`;
}

function backendRows(c: Comparison, destination: Location | null, routesRequested: boolean): ViewRow[] {
  return c.rows
    // Route rows are always present; without the opt-in they only say "not requested".
    .filter((r) => routesRequested || !/^(walking|driving)_/.test(r.metric) || r.values.some((v) => v !== null))
    .map((r: ComparisonRow) => {
      const [label, hint] = metricLabels[r.metric] ?? [r.metric.replace(/_/g, " ")];
      return {
        key: r.metric,
        label: r.metric === "commute_straight_line_m" && destination ? `To ${shortLabel(destination.label)}` : label,
        hint,
        cells: r.values.map((v) => formatValue(v, r.unit)),
        best: r.status === "comparable" ? (r.advantage === "a" ? 0 : r.advantage === "b" ? 1 : -1) : -1,
        note:
          r.status === "incomparable"
            ? r.reason ?? "Not comparable"
            : r.status === "unavailable" && r.values.some((v) => v !== null)
              ? r.reason ?? undefined
              : undefined,
      };
    });
}

export default function ComparePage({
  saved,
  current,
  destination,
  mode,
  limit,
  weights,
  onRemove,
  onOpen,
  onAdd,
  onAddCurrent,
  onBack,
}: {
  saved: Analysis[];
  current: Analysis | null;
  destination: Location | null;
  mode: "demo" | "live";
  limit: number;
  weights?: Weights;
  onRemove: (a: Analysis) => void;
  onOpen: (a: Analysis) => void;
  onAdd: (t: Target) => Promise<Location[] | void>;
  onAddCurrent: () => void;
  onBack: () => void;
}) {
  const useBackend = mode === "live" && saved.length === 2;
  const [includeRoutes, setIncludeRoutes] = useState(false);
  const [remote, setRemote] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const pairKey = saved.map((s) => `${s.location.latitude},${s.location.longitude},${s.radius_m}`).join("|");
  const withRoutes = includeRoutes && !!destination;
  useEffect(() => {
    if (!useBackend) {
      setRemote(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    compare([saved[0], saved[1]], { weights, destination, includeRoutes: withRoutes })
      .then((c) => !cancelled && setRemote(c))
      .catch((e) => !cancelled && (setRemote(null), setError((e as Error).message)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [useBackend, pairKey, JSON.stringify(weights), destination?.latitude, destination?.longitude, withRoutes]);

  const rows = useBackend && remote ? backendRows(remote, destination, withRoutes) : localRows(saved, destination);
  const decided = rows.filter((r) => r.best >= 0).length;
  const wins = saved.map((_, i) => rows.filter((r) => r.best === i).length);
  const radii = new Set(saved.map((s) => s.radius_m));
  const canAdd = saved.length < limit;
  const currentAddable = current && !saved.some((s) => samePlace(s.location, current.location)) && canAdd;
  const showTable = saved.length > 0 && !(useBackend && !remote);

  const intro = saved.length < 2;
  const subtitle =
    saved.length === 0
      ? limit === 2
        ? "Put two homes side by side."
        : `Put up to ${limit} homes side by side.`
      : saved.length === 1
        ? "Add one more home to see which comes out ahead."
        : "Green marks the better value in each row.";
  const columns = Math.max(2, saved.length);
  const winsBadge = (i: number) =>
    saved.length > 1 &&
    (decided === 0 ? (
      <span className="wins">No differences found</span>
    ) : (
      <span className={`wins ${wins[i] === Math.max(...wins) && wins[i] > 0 ? "is-top" : ""}`}>
        {wins[i] === Math.max(...wins) && wins[i] > 0 && <Trophy size={13} />}
        Better in {wins[i]} of {decided}
      </span>
    ));

  return (
    <main className="compare">
      <div className="compare-head">
        <button className="ghost-btn" onClick={onBack}>
          <ArrowLeft size={17} /> Back to map
        </button>
        <h1>Compare homes</h1>
        <p>{subtitle}</p>
        {currentAddable && (
          <button className="quick-add" onClick={onAddCurrent}>
            <Plus size={16} />
            <span>
              Add <b>{shortLabel(current.location.label)}</b>, the address you’re exploring
            </span>
          </button>
        )}
      </div>
      {intro && (
        <ol className="steps">
          <li><span><b>Explore</b> an address on the map</span></li>
          <li><span>Press <b>Save to compare</b></span></li>
          <li><span>Add a second home here or on the map</span></li>
        </ol>
      )}
      {canAdd && <AddHome mode={mode} saved={saved} onAdd={onAdd} />}

      {useBackend && (
        <div className="compare-options">
          {destination ? (
            <label className="check">
              <input type="checkbox" checked={includeRoutes} onChange={(e) => setIncludeRoutes(e.target.checked)} />
              <span>
                Compare walking and driving routes to {shortLabel(destination.label)}
                <small>Sends both homes and the destination to the FOSSGIS OSRM routing service, which logs requests.</small>
              </span>
            </label>
          ) : (
            <p className="muted-note">Set a work or university address in Explore → Commute to compare trips too.</p>
          )}
          {loading && (
            <p className="loading-line">
              <LoaderCircle className="spin" size={15} /> {withRoutes ? "Comparing, including routes. This can take up to a minute…" : "Comparing…"}
            </p>
          )}
          {error && (
            <div className="alert" role="alert">
              <p>{error}</p>
            </div>
          )}
        </div>
      )}

      {showTable && (
        <div className="compare-scroll">
          <table className="compare-table">
            <colgroup>
              <col className="col-label" />
              {Array.from({ length: columns }, (_, i) => (
                <col key={i} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th scope="col" className="corner">
                  <span className="sr-only">Metric</span>
                </th>
                {Array.from({ length: columns }, (_, i) => {
                  const s = saved[i];
                  return (
                    <th scope="col" key={s?.location.label ?? `slot-${i}`} className="home-col">
                      {s ? (
                        <div className="home-card">
                          <div className="home-card-top">
                            <span className="home-letter">{letters[i]}</span>
                            <button className="icon-btn" aria-label={`Remove ${shortLabel(s.location.label)}`} onClick={() => onRemove(s)}>
                              <X size={16} />
                            </button>
                          </div>
                          <h2>{shortLabel(s.location.label)}</h2>
                          <p>
                            {placeLine(s)}
                            {s.demo && " · demo"}
                          </p>
                          {winsBadge(i)}
                          <button className="text-btn" onClick={() => onOpen(s)}>
                            Show on map
                          </button>
                        </div>
                      ) : (
                        <div className="home-card is-empty">
                          <span className="home-letter ghost">{letters[i]}</span>
                          <h2>Second home</h2>
                          <p>Add it with the form above.</p>
                        </div>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <th scope="row">
                    {r.label}
                    {r.hint && <small>{r.hint}</small>}
                    {r.note && <small className="row-note">{r.note}</small>}
                  </th>
                  {Array.from({ length: columns }, (_, i) =>
                    saved[i] ? (
                      <td key={i} className={r.best === i ? "is-best" : ""}>
                        {r.cells[i] === "No data" ? <span className="no-data">No data</span> : r.cells[i]}
                        {r.best === i && (
                          <span className="best-tag">
                            <Check size={12} strokeWidth={3} /> Better
                          </span>
                        )}
                      </td>
                    ) : (
                      <td key={i} className="empty-cell">—</td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {showTable && (
        <div className="compare-mobile">
          <div className="cards">
            {saved.map((s, i) => (
              <div className="home-card" key={s.location.label}>
                <div className="home-card-top">
                  <span className="home-letter">{letters[i]}</span>
                  <button className="icon-btn" aria-label={`Remove ${shortLabel(s.location.label)}`} onClick={() => onRemove(s)}>
                    <X size={16} />
                  </button>
                </div>
                <h2>{shortLabel(s.location.label)}</h2>
                <p>{placeLine(s)}{s.demo && " · demo"}</p>
                {winsBadge(i)}
                <button className="text-btn" onClick={() => onOpen(s)}>Show on map</button>
              </div>
            ))}
          </div>
          {rows.map((r) => (
            <section className="metric" key={r.key}>
              <h3>{r.label}{r.hint && <small>{r.hint}</small>}</h3>
              {r.note && <p className="row-note">{r.note}</p>}
              <ul>
                {saved.map((s, i) => (
                  <li key={s.location.label} className={r.best === i ? "is-best" : ""}>
                    <span className="home-letter">{letters[i]}</span>
                    <span>{shortLabel(s.location.label)}</span>
                    <b>{r.cells[i]}{r.best === i && " ✓"}</b>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {saved.length > 0 && (
        <ul className="compare-notes">
          {useBackend && remote
            ? remote.warnings.map((w) => <li key={w}>{w}</li>)
            : (
              <>
                {!destination && <li>Set a work or university address in Explore → Commute to compare trip distances too.</li>}
                {radii.size > 1 && <li>These homes were explored with different radii, so place counts aren’t directly comparable.</li>}
                <li>Distances are straight-line. Categories without a reliable data source show “No data”.</li>
              </>
            )}
        </ul>
      )}
    </main>
  );
}

function AddHome({ mode, saved, onAdd }: { mode: "demo" | "live"; saved: Analysis[]; onAdd: (t: Target) => Promise<Location[] | void> }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [options, setOptions] = useState<Location[]>([]);
  async function add(t: Target) {
    setBusy(true);
    setError("");
    setOptions([]);
    try {
      const out = await onAdd(t);
      if (out) setOptions(out);
      else setQ("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const suggestions = homes.filter((h) => !saved.some((s) => samePlace(s.location, h)));
  return (
    <div className="add-card">
      <h2>Add home</h2>
      <Field
        compact
        label="Address to add"
        value={q}
        onChange={setQ}
        onSubmit={() => (q.trim().length < 3 ? setError("Enter a street and building number.") : add({ address: q.trim() }))}
        placeholder="Street and number"
        action={
          <button type="submit" className="go-btn" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />}
            Add
          </button>
        }
      />
      {error && <p className="field-error">{error}</p>}
      {options.length > 0 && (
        <div className="matches">
          {options.map((o) => (
            <button key={o.label} onClick={() => add({ point: o })}>
              <MapPin size={15} />
              {o.label}
            </button>
          ))}
        </div>
      )}
      {suggestions.length > 0 && (
        <div className="examples">
          {suggestions.map((h) => (
            <button key={h.label} disabled={busy} onClick={() => add(mode === "demo" ? { point: h } : { address: h.label })}>
              + {shortLabel(h.label)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
