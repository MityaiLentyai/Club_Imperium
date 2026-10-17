import { useState } from "react";
import { ArrowLeft, Check, LoaderCircle, MapPin, Plus, Trophy, X } from "lucide-react";
import { distance, meters } from "./geo";
import { homes } from "./demo";
import { cats, placesOf, rowsOf, plural, samePlace, shortLabel, COMPARE_LIMIT } from "./ui";
import type { Analysis, Location } from "./types";
import type { Target } from "./App";
import Field from "./Field";

type Row = {
  label: string;
  hint?: string;
  values: (number | undefined)[];
  format: (n: number) => string;
  better: "higher" | "lower";
};

const letters = ["A", "B", "C"];

export default function ComparePage({
  saved,
  current,
  destination,
  mode,
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
  onRemove: (a: Analysis) => void;
  onOpen: (a: Analysis) => void;
  onAdd: (t: Target) => Promise<Location[] | void>;
  onAddCurrent: () => void;
  onBack: () => void;
}) {
  const rows: Row[] = [
    ...(saved.some((s) => s.mobility)
      ? [{ label: "Mobility score", hint: "out of 100", values: saved.map((s) => s.mobility?.score), format: (n: number) => `${Math.round(n)}`, better: "higher" as const }]
      : []),
    { label: "Nearest stop", values: saved.map((s) => placesOf(s, "transport")[0]?.distance_m ?? s.mobility?.nearest_stop_m), format: meters, better: "lower" },
    ...cats.map((c) => ({
      label: c.label,
      hint: "within radius",
      values: saved.map((s) => (s.unavailable.includes(c.id) ? undefined : rowsOf(s, c.id).length)),
      format: (n: number) => plural(n, c.id === "transport" ? "stop" : "place"),
      better: "higher" as const,
    })),
    ...(destination
      ? [{ label: `To ${shortLabel(destination.label)}`, hint: "straight line", values: saved.map((s) => distance(s.location, destination)), format: meters, better: "lower" as const }]
      : []),
  ];
  // Index of the best home per row, or -1 when there is nothing to compare.
  const winner = (r: Row) => {
    const known = r.values.map((v, i) => [v, i] as const).filter(([v]) => v !== undefined) as [number, number][];
    if (known.length < 2) return -1;
    const best = r.better === "higher" ? Math.max(...known.map(([v]) => v)) : Math.min(...known.map(([v]) => v));
    const leaders = known.filter(([v]) => v === best);
    return leaders.length === 1 ? leaders[0][1] : -1;
  };
  const winners = rows.map(winner);
  const wins = saved.map((_, i) => winners.filter((w) => w === i).length);
  const decided = winners.filter((w) => w >= 0).length;
  const radii = new Set(saved.map((s) => s.radius_m));
  const canAdd = saved.length < COMPARE_LIMIT;
  const currentAddable = current && !saved.some((s) => samePlace(s.location, current.location)) && canAdd;

  const intro = saved.length < 2;
  const subtitle =
    saved.length === 0
      ? `Put up to ${COMPARE_LIMIT} homes side by side.`
      : saved.length === 1
        ? "Add one more home to see which comes out ahead."
        : "Green marks the better value in each row.";
  const columns = Math.max(2, saved.length);

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

      {saved.length > 0 && (
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
                            within {meters(s.radius_m)}
                            {s.demo && " · demo"}
                          </p>
                          {saved.length > 1 &&
                            (decided === 0 ? (
                              <span className="wins">No differences found</span>
                            ) : (
                              <span className={`wins ${wins[i] === Math.max(...wins) && wins[i] > 0 ? "is-top" : ""}`}>
                                {wins[i] === Math.max(...wins) && wins[i] > 0 && <Trophy size={13} />}
                                Better in {wins[i]} of {decided}
                              </span>
                            ))}
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
              {rows.map((r, ri) => (
                <tr key={r.label}>
                  <th scope="row">
                    {r.label}
                    {r.hint && <small>{r.hint}</small>}
                  </th>
                  {Array.from({ length: columns }, (_, i) =>
                    saved[i] ? (
                      <td key={i} className={winners[ri] === i ? "is-best" : ""}>
                        {r.values[i] === undefined ? <span className="no-data">No data</span> : r.format(r.values[i]!)}
                        {winners[ri] === i && (
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
      {saved.length > 0 && (
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
                <p>within {meters(s.radius_m)}{s.demo && " · demo"}</p>
                <button className="text-btn" onClick={() => onOpen(s)}>Show on map</button>
              </div>
            ))}
          </div>
          {rows.map((r, ri) => (
            <section className="metric" key={r.label}>
              <h3>{r.label}{r.hint && <small>{r.hint}</small>}</h3>
              <ul>
                {saved.map((s, i) => (
                  <li key={s.location.label} className={winners[ri] === i ? "is-best" : ""}>
                    <span className="home-letter">{letters[i]}</span>
                    <span>{shortLabel(s.location.label)}</span>
                    <b>{r.values[i] === undefined ? "No data" : r.format(r.values[i]!)}{winners[ri] === i && " ✓"}</b>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      {saved.length > 0 && (
        <ul className="compare-notes">
          {!destination && <li>Set a work or university address in Explore → Commute to compare trip distances too.</li>}
          {radii.size > 1 && <li>These homes were explored with different radii, so place counts aren’t directly comparable.</li>}
          <li>Distances are straight-line. Categories without a reliable data source show “No data”.</li>
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
