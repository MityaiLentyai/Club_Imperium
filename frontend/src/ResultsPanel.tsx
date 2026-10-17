import { useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Car, Check, ChevronDown, Footprints, Info, LoaderCircle, MapPin, Route as RouteIcon, Search, SlidersHorizontal, Star, TramFront, X } from "lucide-react";
import { distance, meters } from "./geo";
import Field from "./Field";
import { weightKeys } from "./api";
import { cats, catById, placesOf, rowsOf, plural, radii, shortLabel, samePlace, weightLabels } from "./ui";
import type { Analysis, Category, Commute as CommuteData, Location, Route, Weights } from "./types";

const PREVIEW = 5;

export type Props = {
  result: Analysis;
  live: boolean;
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
  compareLimit: number;
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
  onApplyWeights: (w: Weights | undefined) => void;
  routes: CommuteData | null;
  routesBusy: boolean;
  routesError: string;
  onCheckRoutes: () => void;
};

export default function ResultsPanel(props: Props) {
  const { result } = props;
  const transport = placesOf(result, "transport");
  const dirty = props.query.trim() !== result.location.label;
  const area = result.location.label.split(",").slice(1, 3).join(",").trim() || "Warsaw";

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
              <p>{area} · within {meters(result.radius_m)}</p>
            </div>
            <button
              className={`save-btn ${props.saved ? "is-saved" : ""}`}
              onClick={props.onToggleSave}
              disabled={!props.saved && props.compareFull}
              title={!props.saved && props.compareFull ? `Compare holds ${props.compareLimit} homes. Remove one first.` : undefined}
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
                  <Tip text="Based on straight-line distance to the nearest stop and how many stop groups are within 500 m. It doesn't measure travel time or service frequency." />
                </span>
                <strong>
                  {Math.round(result.mobility.score)}
                  <small>/100</small>
                </strong>
                <Meter value={result.mobility.score} />
              </div>
            )}
            <div className="stat">
              <span className="stat-label">Nearest stop</span>
              <strong>{transport.length ? meters(transport[0].distance_m) : result.mobility?.nearest_stop_m !== undefined ? meters(result.mobility.nearest_stop_m) : "—"}</strong>
              <span className="stat-sub">
                {transport[0] ? transport[0].label : "none in radius"}
                {result.nearestStopLines && ` · lines ${result.nearestStopLines.join(", ")}`}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Stops in radius</span>
              <strong>{rowsOf(result, "transport").length}</strong>
              <span className="stat-sub">{plural(result.nearby?.total ?? transport.length, "platform")} within {meters(result.radius_m)}</span>
            </div>
          </div>
          {result.lifeScore && <LifeScoreCard result={result} onApply={props.onApplyWeights} busy={props.busy} />}
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

function Tip({ text }: { text: string }) {
  return (
    <span className="info" tabIndex={0} data-tip={text} aria-label={text}>
      <Info size={13} />
    </span>
  );
}

function Meter({ value }: { value: number }) {
  return (
    <span className="meter" aria-hidden="true">
      <span style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
    </span>
  );
}

// The backend's personalized index. Only categories with a validated score count; the
// returned label and status say how complete it is, so the UI never calls it "overall".
function LifeScoreCard({ result, onApply, busy }: { result: Analysis; onApply: (w: Weights | undefined) => void; busy: boolean }) {
  const ls = result.lifeScore!;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const counted = weightKeys.filter((k) => ls.normalized[k] !== undefined);
  // The backend explains each exclusion: either no validated score exists yet, or the weight is zero.
  const zeroWeight = weightKeys.filter((k) => ls.excluded[k] && /zero/i.test(ls.excluded[k]!));
  const notScored = weightKeys.filter((k) => ls.excluded[k] && !zeroWeight.includes(k));
  function open() {
    setDraft(Object.fromEntries(weightKeys.map((k) => [k, ls.requested[k] ?? 0])));
    setEditing(true);
  }
  return (
    <div className="life">
      <div className="life-head">
        <div>
          <span className="stat-label">
            {ls.label}
            {ls.status !== "available" && !ls.label.toLowerCase().includes(ls.status.toLowerCase()) && <span className="status-pill">{ls.status}</span>}
            <Tip text={ls.explanation ?? "Weighted mean of the categories that have a validated score."} />
          </span>
          <strong>
            {ls.value === null ? "—" : Math.round(ls.value)}
            {ls.value !== null && <small>/100</small>}
          </strong>
        </div>
        <button className="ghost-btn" onClick={() => (editing ? setEditing(false) : open())} aria-expanded={editing}>
          <SlidersHorizontal size={15} /> Priorities
        </button>
      </div>
      {ls.value !== null && <Meter value={ls.value} />}
      <p className="life-note">
        {ls.value === null
          ? "No score: none of the categories you gave weight to has a validated score yet."
          : counted.length
            ? `Counts ${counted.map((k) => `${weightLabels[k]} ${Math.round(ls.normalized[k]!)}%`).join(", ")}.`
            : ""}
        {zeroWeight.length > 0 && ` Turned off by you: ${zeroWeight.map((k) => weightLabels[k].toLowerCase()).join(", ")}.`}
        {notScored.length > 0 && ` Not scored yet: ${notScored.map((k) => weightLabels[k].toLowerCase()).join(", ")}.`}
      </p>
      {editing && (
        <form
          className="weights"
          onSubmit={(e) => {
            e.preventDefault();
            onApply(draft as Weights);
            setEditing(false);
          }}
        >
          <p className="life-note">How much does each matter to you? Categories without a validated score are skipped, never counted as zero.</p>
          {weightKeys.map((k) => (
            <label key={k} className="weight">
              <span>{weightLabels[k]}</span>
              <input
                type="range"
                min={0}
                max={100}
                step={10}
                value={draft[k] ?? 0}
                onChange={(e) => setDraft((d) => ({ ...d, [k]: Number(e.target.value) }))}
              />
              <b>{draft[k] ?? 0}</b>
            </label>
          ))}
          <div className="weights-actions">
            <button type="submit" className="go-btn" disabled={busy}>
              Apply
            </button>
            <button
              type="button"
              className="text-btn"
              onClick={() => {
                onApply(undefined);
                setEditing(false);
              }}
            >
              Reset to defaults
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Nearby({ result, filters, onToggleFilter, focusedId, onFocus, onHover }: Props) {
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
        const outside = result.nearest?.[c.id]?.distance_m;
        return (
          <section key={c.id} className={`group cat-${c.id}`}>
            <header>
              <c.icon size={17} />
              <h3>{c.label}</h3>
              <span>
                {list.length
                  ? `${plural(list.length, c.id === "transport" ? "stop" : "place")} · nearest ${meters(list[0].place.distance_m)}`
                  : outside != null
                    ? `none within ${meters(result.radius_m)} · nearest ${meters(outside)}`
                    : `none within ${meters(result.radius_m)}`}
              </span>
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
                        {p.details?.length ? <small>{p.details.join(" · ")}</small> : null}
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

function Commute({ result, live, destination, onDestination, findDestination, quickDestinations, savedHomes, routes, routesBusy, routesError, onCheckRoutes }: Props) {
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
          <strong>{meters(routes?.baseline_m ?? distance(result.location, destination))}</strong>
          <p>Straight line from {shortLabel(result.location.label)}.</p>
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
          {live ? (
            routes ? (
              <RouteList routes={routes} />
            ) : (
              <div className="route-ask">
                <button className="go-btn" onClick={onCheckRoutes} disabled={routesBusy}>
                  {routesBusy ? <LoaderCircle className="spin" size={15} /> : <RouteIcon size={15} />}
                  {routesBusy ? "Finding routes…" : "Get walking and driving routes"}
                </button>
                <p>Sends both points to the FOSSGIS OSRM routing service, which logs requests.</p>
                {routesError && <p className="field-error">{routesError}</p>}
              </div>
            )
          ) : (
            <p className="muted-note">Walking and driving routes are available in Live mode.</p>
          )}
        </div>
      ) : (
        <p className="muted-note">The destination appears on the map with a line from your home.</p>
      )}
    </div>
  );
}

const minutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)} h ${Math.round(m % 60)} min` : `${Math.round(m)} min`);

function RouteRow({ icon, label, route, note }: { icon: ReactNode; label: string; route: Route; note: string }) {
  return (
    <li className={`route ${route.status === "available" ? "" : "is-unavailable"}`}>
      {icon}
      <span>
        {label}
        <small>{route.status === "available" ? note : route.reason}</small>
      </span>
      {route.status === "available" ? (
        <span className="route-values">
          <b>{minutes(route.duration_minutes)}</b>
          <small>{meters(route.distance_m)}</small>
        </span>
      ) : (
        <span className="route-values"><small>Not available</small></span>
      )}
    </li>
  );
}

function RouteList({ routes }: { routes: CommuteData }) {
  return (
    <>
      <ul className="routes">
        <RouteRow icon={<Footprints size={17} />} label="Walking" route={routes.walking} note="Estimate from the routing provider" />
        <RouteRow icon={<Car size={17} />} label="Driving" route={routes.driving} note="Estimate without live traffic" />
        <RouteRow icon={<TramFront size={17} />} label="Public transport" route={routes.transit} note="" />
      </ul>
      {routes.attribution && (
        <p className="attribution">
          Routes: {routes.attribution.url ? <a href={routes.attribution.url} target="_blank" rel="noreferrer">{routes.attribution.name}</a> : routes.attribution.name}
          {routes.attribution.fix_map_url && (
            <>
              {" · "}
              <a href={routes.attribution.fix_map_url} target="_blank" rel="noreferrer">Fix the map</a>
            </>
          )}
        </p>
      )}
    </>
  );
}
