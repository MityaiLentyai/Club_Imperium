import { useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Check, ChevronDown, Info, LoaderCircle, MapPin, Search, Star, X } from "lucide-react";
import { distance, meters } from "./geo";
import Field from "./Field";
import { cats, catById, placesOf, rowsOf, plural, radii, shortLabel, COMPARE_LIMIT, samePlace } from "./ui";
import type { Analysis, Category, Location } from "./types";

const PREVIEW = 5;

export default function ResultsPanel(props: {
  result: Analysis;
  query: string;
  onQuery: (q: string) => void;
  onSubmit: () => void;
  radius: number;
  onRadius: (r: number) => void;
  busy: boolean;
  error: ReactNode;
  matches: Location[];
  onPickMatch: (l: Location) => void;
  onNewSearch: () => void;
  saved: boolean;
  compareFull: boolean;
  savedCount: number;
  onToggleSave: () => void;
  onOpenCompare: () => void;
  tab: "nearby" | "commute";
  onTab: (t: "nearby" | "commute") => void;
  filters: Category[];
  onToggleFilter: (c: Category) => void;
  focusedId: string | null;
  onFocus: (id: string | null) => void;
  onHover: (id: string | null) => void;
  destination: Location | null;
  onDestination: (l: Location | null) => void;
  findDestination: (q: string) => Promise<Location[]>;
  quickDestinations: Location[];
  savedHomes: Analysis[];
}) {
  const { result } = props;
  const transport = placesOf(result, "transport");
  const dirty = props.query.trim() !== result.location.label;

  return (
    <div className="results">
      <div className="results-search">
        <button className="icon-btn" aria-label="New search" title="New search" onClick={props.onNewSearch}>
          <ArrowLeft size={18} />
        </button>
        <Field
          compact
          label="Address"
          value={props.query}
          onChange={props.onQuery}
          onSubmit={props.onSubmit}
          placeholder="Another address"
          action={
            dirty && props.query.trim() ? (
              <button type="submit" className="go-btn" disabled={props.busy}>
                Go <ArrowRight size={15} />
              </button>
            ) : (
              <button type="submit" className="icon-btn" aria-label="Refresh" disabled={props.busy}>
                {props.busy ? <LoaderCircle className="spin" size={17} /> : <Search size={17} />}
              </button>
            )
          }
        />
        <div className="select">
          <select aria-label="Search radius" value={props.radius} onChange={(e) => props.onRadius(Number(e.target.value))}>
            {radii.map((r) => (
              <option key={r} value={r}>{meters(r)}</option>
            ))}
          </select>
          <ChevronDown size={14} />
        </div>
      </div>
      {props.matches.length > 0 && (
        <div className="matches inset">
          <span>Which one?</span>
          {props.matches.map((m) => (
            <button key={m.label} onClick={() => props.onPickMatch(m)}>
              <MapPin size={15} />
              {m.label}
            </button>
          ))}
        </div>
      )}
      {props.error && <div className="inset">{props.error}</div>}

      <div className="results-scroll">
        <section className="summary">
          <div className="summary-head">
            <div className="summary-title">
              <h2>{shortLabel(result.location.label)}</h2>
              <p>{result.location.label.split(",").slice(1).join(",").trim() || "Warsaw"} · within {meters(result.radius_m)}</p>
            </div>
            <button
              className={`save-btn ${props.saved ? "is-saved" : ""}`}
              onClick={props.onToggleSave}
              disabled={!props.saved && props.compareFull}
              title={!props.saved && props.compareFull ? `Compare holds ${COMPARE_LIMIT} homes. Remove one first.` : undefined}
            >
              {props.saved ? <Check size={16} /> : <Star size={16} />}
              {props.saved ? "Saved" : "Save to compare"}
            </button>
          </div>
          {props.savedCount > 0 && (
            <button className="compare-hint" onClick={props.onOpenCompare}>
              <span>{props.savedCount === 1 ? "1 home saved. Save one more to compare." : `${props.savedCount} homes saved`}</span>
              <span className="compare-hint-cta">Open Compare <ArrowRight size={14} /></span>
            </button>
          )}
          <div className="stats">
            {result.mobility && (
              <div className="stat score">
                <span className="stat-label">
                  Mobility score
                  <span className="info" tabIndex={0} data-tip="Based on straight-line distance to the nearest stop and how many stop groups are within 500 m and 1 km. It doesn't measure travel time or service frequency." aria-label="Based on straight-line distance to the nearest stop and how many stop groups are within 500 m and 1 km. It doesn't measure travel time or service frequency.">
                    <Info size={13} />
                  </span>
                </span>
                <strong>
                  {Math.round(result.mobility.score)}
                  <small>/100</small>
                </strong>
                <span className="meter" aria-hidden="true">
                  <span style={{ width: `${Math.max(2, Math.min(100, result.mobility.score))}%` }} />
                </span>
              </div>
            )}
            <div className="stat">
              <span className="stat-label">Nearest stop</span>
              <strong>{transport.length ? meters(transport[0].distance_m) : result.mobility?.nearest_stop_m !== undefined ? meters(result.mobility.nearest_stop_m) : "—"}</strong>
              <span className="stat-sub">{transport[0] ? transport[0].label : "none in radius"}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Stops in radius</span>
              <strong>{rowsOf(result, "transport").length}</strong>
              <span className="stat-sub">{plural(result.nearby?.total ?? transport.length, "platform")} within {meters(result.radius_m)}</span>
            </div>
          </div>
          {result.demo && <p className="demo-note">Demo: these places are made-up examples. Switch to Live in Data & sources for real stops.</p>}
        </section>

        <div className="tabs" role="tablist" aria-label="Analysis">
          <button role="tab" aria-selected={props.tab === "nearby"} onClick={() => props.onTab("nearby")}>
            Nearby places
          </button>
          <button role="tab" aria-selected={props.tab === "commute"} onClick={() => props.onTab("commute")}>
            Commute
            {props.destination && <span className="tab-dot" />}
          </button>
        </div>

        {props.tab === "nearby" ? <Nearby {...props} /> : <Commute {...props} />}
      </div>
    </div>
  );
}

function Nearby({ result, filters, onToggleFilter, focusedId, onFocus, onHover }: Parameters<typeof ResultsPanel>[0]) {
  const [open, setOpen] = useState<Category[]>([]);
  // A marker clicked on the map may sit below the preview cut: expand its group, then scroll to it.
  useEffect(() => {
    if (!focusedId) return;
    const p = result.places.find((x) => x.id === focusedId);
    if (!p) return;
    const rows = rowsOf(result, p.category);
    const index = rows.findIndex((row) => row.ids.includes(focusedId));
    if (index >= PREVIEW) setOpen((o) => (o.includes(p.category) ? o : [...o, p.category]));
    requestAnimationFrame(() =>
      document.getElementById(`place-${CSS.escape(rows[index].place.id)}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }),
    );
  }, [focusedId, result]);
  const available = cats.filter((c) => !result.unavailable.includes(c.id));
  const missing = cats.filter((c) => result.unavailable.includes(c.id));
  const shown = available.filter((c) => filters.includes(c.id));

  return (
    <div className="nearby" role="tabpanel">
      <div className="chips" role="group" aria-label="Show on map">
        {available.map((c) => {
          const n = rowsOf(result, c.id).length;
          return (
            <button key={c.id} className={`chip cat-${c.id}`} aria-pressed={filters.includes(c.id)} onClick={() => onToggleFilter(c.id)}>
              <span className="chip-dot" aria-hidden="true">{filters.includes(c.id) && <Check size={11} strokeWidth={3} />}</span>
              {c.label}
              <span className="chip-count">{n}</span>
            </button>
          );
        })}
      </div>
      {missing.length > 0 && (
        <p className="muted-note">
          No data yet for {missing.map((c) => c.label.toLowerCase()).join(", ")}. We show nothing rather than guess.
        </p>
      )}
      {result.nearby?.truncated && (
        <p className="muted-note">
          Showing the nearest {placesOf(result, "transport").length} of {result.nearby.total} stops in this radius.
        </p>
      )}
      {shown.length === 0 && <p className="muted-note">All categories are hidden. Turn one on above.</p>}
      {shown.map((c) => {
        const list = rowsOf(result, c.id);
        const expanded = open.includes(c.id);
        const visible = expanded ? list : list.slice(0, PREVIEW);
        return (
          <section key={c.id} className={`group cat-${c.id}`}>
            <header>
              <c.icon size={17} />
              <h3>{c.label}</h3>
              <span>{list.length ? `${plural(list.length, c.id === "transport" ? "stop" : "place")} · nearest ${meters(list[0].place.distance_m)}` : `none within ${meters(result.radius_m)}`}</span>
            </header>
            {list.length > 0 && (
              <ol>
                {visible.map(({ place: p, ids }) => (
                  <li key={p.id}>
                    <button
                      id={`place-${p.id}`}
                      className="place"
                      aria-pressed={!!focusedId && ids.includes(focusedId)}
                      onClick={() => onFocus(focusedId && ids.includes(focusedId) ? null : p.id)}
                      onMouseEnter={() => onHover(p.id)}
                      onMouseLeave={() => onHover(null)}
                      onFocus={() => onHover(p.id)}
                      onBlur={() => onHover(null)}
                    >
                      <span className="place-dot" aria-hidden="true">{(() => { const Icon = catById[p.category].icon; return <Icon size={13} strokeWidth={2.4} />; })()}</span>
                      <span className="place-name">
                        {p.label}
                        {p.lines?.length ? <small>Lines {p.lines.join(" · ")}</small> : null}
                        {ids.length > 1 && <small>{ids.length} platforms · nearest shown</small>}
                      </span>
                      <span className="place-dist">{meters(p.distance_m)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
            {list.length > PREVIEW && (
              <button className="text-btn more" onClick={() => setOpen((o) => (expanded ? o.filter((x) => x !== c.id) : [...o, c.id]))}>
                {expanded ? "Show fewer" : `Show all ${list.length}`}
              </button>
            )}
          </section>
        );
      })}
      <p className="muted-note">Distances are straight-line from the home pin.</p>
    </div>
  );
}

function Commute({ result, destination, onDestination, findDestination, quickDestinations, savedHomes }: Parameters<typeof ResultsPanel>[0]) {
  const [q, setQ] = useState(destination?.label ?? "");
  const [options, setOptions] = useState<Location[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function search() {
    if (q.trim().length < 3) return setError("Enter at least 3 characters.");
    setBusy(true);
    setError("");
    setOptions([]);
    try {
      const found = await findDestination(q);
      if (found.length === 1) choose(found[0]);
      else setOptions(found);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function choose(l: Location | null) {
    onDestination(l);
    setQ(l?.label ?? "");
    setOptions([]);
    setError("");
  }
  const others = destination ? savedHomes.filter((s) => !samePlace(s.location, result.location)) : [];

  return (
    <div className="commute" role="tabpanel">
      <p className="lead">Where do you go most days? Add your work or university to see how far it is.</p>
      <Field
        label="Destination"
        value={q}
        onChange={setQ}
        onSubmit={search}
        placeholder="Work or university address"
        action={
          <button type="submit" className="icon-btn" aria-label="Search destination" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={17} /> : <Search size={17} />}
          </button>
        }
      />
      {error && <p className="field-error">{error}</p>}
      {options.length > 0 && (
        <div className="matches">
          {options.map((o) => (
            <button key={o.label} onClick={() => choose(o)}>
              <MapPin size={15} />
              {o.label}
            </button>
          ))}
        </div>
      )}
      <div className="examples">
        {quickDestinations.map((d) => (
          <button key={d.label} className={destination?.label === d.label ? "is-current" : ""} onClick={() => choose(d)}>
            {d.label}
          </button>
        ))}
      </div>
      {destination ? (
        <div className="commute-card">
          <div className="commute-card-head">
            <span>To {destination.label}</span>
            <button className="icon-btn" aria-label="Remove destination" onClick={() => choose(null)}>
              <X size={16} />
            </button>
          </div>
          <strong>{meters(distance(result.location, destination))}</strong>
          <p>Straight line from {shortLabel(result.location.label)}. The real route is longer; travel times aren’t available yet.</p>
          {others.length > 0 && (
            <ul>
              {others.map((s) => (
                <li key={s.location.label}>
                  <span>From {shortLabel(s.location.label)}</span>
                  <b>{meters(distance(s.location, destination))}</b>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="muted-note">The destination appears on the map with a line from your home.</p>
      )}
    </div>
  );
}
