import React, { useState, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  ArrowRight,
  MapPin,
  Search,
  SlidersHorizontal,
  TrainFront,
  ShoppingBasket,
  TreePine,
  Cross,
  ParkingCircle,
  ArrowLeftRight,
  Navigation,
  Info,
  X,
  Check,
  ChevronDown,
  LoaderCircle,
  Compass,
} from "lucide-react";
import NeighborhoodMap from "./Map";
import { homes, destinations, demoAnalysis } from "./demo";
import { analyze, geocode, API_BASE_URL } from "./api";
import { distance, meters, inWarsaw } from "./geo";
import type { Category, Location, Analysis } from "./types";
import "./style.css";
const cats: {
  id: Category;
  label: string;
  icon: typeof TrainFront;
  color: string;
}[] = [
  { id: "transport", label: "Transport", icon: TrainFront, color: "blue" },
  { id: "grocery", label: "Groceries", icon: ShoppingBasket, color: "orange" },
  { id: "pharmacy", label: "Pharmacies", icon: Cross, color: "pink" },
  { id: "green", label: "Green spaces", icon: TreePine, color: "green" },
  { id: "parking", label: "Parking", icon: ParkingCircle, color: "purple" },
];
function App() {
  const viewGeneration = useRef(0);
  const [mode, setMode] = useState<"demo" | "live">("demo"),
    [location, setLocation] = useState<Location>(homes[0]),
    [query, setQuery] = useState(homes[0].label),
    [radius, setRadius] = useState(1000),
    [filters, setFilters] = useState<Category[]>(cats.map((c) => c.id)),
    [result, setResult] = useState<Analysis | null>(null),
    [saved, setSaved] = useState<Analysis[]>([]),
    [tab, setTab] = useState("explore"),
    [busy, setBusy] = useState(false),
    [searching, setSearching] = useState(false),
    [error, setError] = useState(""),
    [matches, setMatches] = useState<Location[]>([]),
    [destination, setDestination] = useState<Location | null>(null),
    [destQuery, setDestQuery] = useState(""),
    [destMatches, setDestMatches] = useState<Location[]>([]),
    [about, setAbout] = useState(false),
    [centerTick, setCenterTick] = useState(0);
  const initial = useMemo(
    () => demoAnalysis(location, radius),
    [location, radius],
  );
  const shown = result?.places || (mode === "demo" ? initial.places : []);
  const active = result?.location || location;
  function select(p: Location) {
    if (!inWarsaw(p)) {
      setError("Choose a location within Warsaw.");
      return;
    }
    viewGeneration.current += 1;
    setBusy(false);
    setSearching(false);
    setLocation(p);
    setQuery(p.label);
    setResult(null);
    setMatches([]);
    setError("");
  }
  function changeMode(m: "demo" | "live") {
    viewGeneration.current += 1;
    setBusy(false);
    setSearching(false);
    setMode(m);
    setResult(null);
    setSaved([]);
    setError("");
    setMatches([]);
    setDestMatches([]);
    setDestination(null);
    setTab("explore");
  }
  async function searchAddress(dest = false) {
    const generation = viewGeneration.current;
    setError("");
    setSearching(true);
    try {
      const q = dest ? destQuery : query;
      if (mode === "demo") {
        const all = dest ? destinations : homes;
        const matches = all.filter((p) =>
          p.label.toLowerCase().includes(q.toLowerCase().trim()),
        );
        if (!matches.length)
          throw new Error(
            "Demo mode includes the example addresses below. Select one, or choose a point on the map.",
          );
        dest ? setDestMatches(matches) : setMatches(matches);
      } else {
        const found = await geocode(q);
        if (generation !== viewGeneration.current) return;
        if (!found.length)
          throw new Error(
            "No matching Warsaw address. Try another address or select a point on the map.",
          );
        dest ? setDestMatches(found) : setMatches(found);
      }
    } catch (e) {
      if (generation === viewGeneration.current) setError((e as Error).message);
    } finally {
      if (generation === viewGeneration.current) setSearching(false);
    }
  }
  async function run() {
    const generation = viewGeneration.current;
    setBusy(true);
    setError("");
    try {
      let target = location;
      if (query.trim() && query.trim() !== location.label) {
        const found =
          mode === "demo"
            ? homes.filter((p) =>
                p.label.toLowerCase().includes(query.toLowerCase().trim()),
              )
            : await geocode(query);
        if (generation !== viewGeneration.current) return;
        if (found.length !== 1) {
          setMatches(found);
          throw new Error(
            found.length
              ? "Choose a matching address, then explore."
              : "Address not found. Try an example or choose a point on the map.",
          );
        }
        target = found[0];
        setLocation(target);
        setQuery(target.label);
      }
      const data =
        mode === "demo"
          ? demoAnalysis(target, radius)
          : await analyze({ ...target, radius_m: radius, destination });
      if (generation !== viewGeneration.current) return;
      setResult({ ...data, radius_m: radius });
      setTab("explore");
      setTimeout(
        () =>
          document
            .getElementById("report")
            ?.scrollIntoView({ behavior: "smooth", block: "start" }),
        80,
      );
    } catch (e) {
      if (generation === viewGeneration.current) setError((e as Error).message);
    } finally {
      if (generation === viewGeneration.current) setBusy(false);
    }
  }
  function save() {
    if (!result) return;
    setSaved((prev) => {
      if (
        prev.some(
          (p) =>
            p.location.latitude === result.location.latitude &&
            p.location.longitude === result.location.longitude,
        )
      )
        return prev;
      return [...prev.slice(-1), result];
    });
    setTab("compare");
    setTimeout(
      () =>
        document
          .getElementById("comparison")
          ?.scrollIntoView({ behavior: "smooth" }),
      50,
    );
  }
  const savedCurrent =
    result &&
    saved.some(
      (p) =>
        p.location.latitude === result.location.latitude &&
        p.location.longitude === result.location.longitude,
    );
  return (
    <>
      <header>
        <a
          className="brand"
          href="#"
          onClick={() => {
            setTab("explore");
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          <span className="brand-symbol">
            u<span>l</span>
          </span>
          UrbanLens<span className="brand-city">WARSAW</span>
        </a>
        <nav aria-label="Main navigation">
          <button
            className={tab === "explore" ? "active" : ""}
            onClick={() => {
              setTab("explore");
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          >
            Explore
          </button>
          <button
            className={tab === "compare" ? "active" : ""}
            onClick={() => {
              setTab("compare");
              setTimeout(
                () =>
                  document
                    .getElementById("comparison")
                    ?.scrollIntoView({ behavior: "smooth" }),
                50,
              );
            }}
          >
            Compare
            {saved.length > 0 && <span className="count">{saved.length}</span>}
          </button>
          <button onClick={() => setAbout(true)}>Data & sources</button>
        </nav>
        <div className="mode" aria-label="Data mode">
          <button
            aria-pressed={mode === "demo"}
            className={mode === "demo" ? "selected" : ""}
            onClick={() => changeMode("demo")}
          >
            Demo
          </button>
          <button
            aria-pressed={mode === "live"}
            className={mode === "live" ? "selected" : ""}
            onClick={() => changeMode("live")}
          >
            Live <span className={API_BASE_URL ? "tiny-dot" : "offline-dot"} />
          </button>
        </div>
      </header>
      <main>
        <section className="hero">
          <div className="search-panel">
            <div className="eyebrow">Make yourself at home.</div>
            <h1>
              Find your
              <br />
              kind of <span>Warsaw.</span>
            </h1>
            <p className="intro">Look beyond the apartment.</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                searchAddress();
              }}
            >
              <label htmlFor="address">Your Warsaw address</label>
              <div className="address-field">
                <MapPin size={19} />
                <input
                  id="address"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Enter a Warsaw address"
                  autoComplete="off"
                />
                <button
                  className="search-icon"
                  disabled={searching}
                  aria-label="Search address"
                >
                  {searching ? (
                    <LoaderCircle className="spin" size={20} />
                  ) : (
                    <Search size={20} />
                  )}
                </button>
              </div>
              {matches.length > 0 && (
                <div className="matches">
                  {matches.map((p) => (
                    <button
                      type="button"
                      key={p.label}
                      onClick={() => select(p)}
                    >
                      <MapPin size={15} />
                      {p.label}
                    </button>
                  ))}
                </div>
              )}
            </form>
            <div className="example-row">
              <span>{mode === "demo" ? "TRY" : "SELECTED"}</span>
              {mode === "demo" ? (
                homes.slice(0, 2).map((p) => (
                  <button
                    key={p.label}
                    className={location.label === p.label ? "current" : ""}
                    onClick={() => select(p)}
                  >
                    {p.label.split(",")[0]}
                  </button>
                ))
              ) : (
                <small>{location.label}</small>
              )}
            </div>
            <div className="radius-row">
              <label htmlFor="radius">Search within</label>
              <div className="radius-control">
                <select
                  id="radius"
                  value={radius}
                  onChange={(e) => {
                    viewGeneration.current += 1;
                    setBusy(false);
                    setSearching(false);
                    setRadius(Number(e.target.value));
                    setResult(null);
                  }}
                >
                  <option value={500}>500 m</option>
                  <option value={1000}>1 km</option>
                  <option value={1500}>1.5 km</option>
                  <option value={2000}>2 km</option>
                </select>
                <ChevronDown size={14} />
              </div>
            </div>
            <button className="analyze" onClick={run} disabled={busy}>
              {busy ? (
                <>
                  <LoaderCircle size={19} className="spin" />
                  Analyzing neighborhood…
                </>
              ) : (
                <>
                  Explore neighborhood <ArrowRight size={21} />
                </>
              )}
            </button>
          </div>
          <div className="map-panel">
            <NeighborhoodMap
              location={active}
              radius={radius}
              places={shown}
              filters={filters}
              onPick={select}
              destination={destination}
              centerTick={centerTick}
            />
            <div className="map-title">
              <span className="tiny-dot" /> Warsaw
            </div>
            <div className="map-demo">
              {mode === "demo" ? "Demo places" : "Live mode"}
            </div>
            <button
              className="map-center"
              aria-label="Recenter map"
              title="Recenter map"
              onClick={() => setCenterTick((t) => t + 1)}
            >
              <Navigation size={18} />
            </button>
          </div>
        </section>
        <div className="category-bar">
          <span className="filter-label">Show on map</span>
          <div className="filter-buttons">
            {cats.map((c) => (
              <button
                key={c.id}
                aria-pressed={filters.includes(c.id)}
                className={`${c.color} ${filters.includes(c.id) ? "on" : ""}`}
                onClick={() =>
                  setFilters((p) =>
                    p.includes(c.id)
                      ? p.filter((x) => x !== c.id)
                      : [...p, c.id],
                  )
                }
              >
                <c.icon size={17} />
                {c.label}
                <span className="filter-dot" />
              </button>
            ))}
          </div>
        </div>
        <div className="status-note">
          <Info size={14} />
          {mode === "demo"
            ? "Demo · Illustrative places on a real map."
            : API_BASE_URL
              ? "Live · Connected to your data service."
              : "Live analysis isn’t connected yet. Try Demo."}
        </div>
        {error && (
          <div className="error" role="alert">
            <Info size={18} />
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={17} />
            </button>
          </div>
        )}
        {!result && tab === "explore" && (
          <section className="before-report">
            <h2>
              A place for <span>your everyday.</span>
            </h2>
            <p>Essentials nearby. Your commute in view.</p>
            <div className="city-doodle" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </section>
        )}
        {result && (
          <section className="report" id="report">
            <div className="section-heading">
              <div>
                <span className="section-kicker">
                  {result.demo ? "Demo report" : "Neighborhood report"}
                </span>
                <h2>Around your address.</h2>
                <p>
                  {result.location.label}{" "}
                  <span className="muted">· Within {meters(radius)}</span>
                </p>
              </div>
              <button className="outline-btn" onClick={save}>
                {savedCurrent ? "Added to comparison" : "Compare this home"}
              </button>
            </div>
            {result.scores && result.features && (
              <div className="status-note" aria-label="Mobility Score">
                <TrainFront size={20} />
                <span>
                  <strong>Mobility Score: {result.scores.mobility}/100</strong>
                  {" · "}Nearest stop: {meters(result.features.nearest_stop_m)}
                  {" · "}{result.features.stop_groups_500m} stop groups within 500 m
                  {" · "}{result.features.stop_groups_1000m} within 1 km.
                  {" "}Score uses fixed radii; map markers use your selected radius.
                </span>
              </div>
            )}
            {result.nearby?.truncated && (
              <p className="status-note">Showing the nearest {result.places.length} of {result.nearby.total} transport platforms within this radius.</p>
            )}
            <div className="metrics">
              {cats.map((c) => {
                const list = result.places
                  .filter((p) => p.category === c.id)
                  .sort(
                    (a, b) =>
                      (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity),
                  );
                const unavailable = result.unavailable.includes(c.id);
                return (
                  <a
                    className="metric"
                    key={c.id}
                    href={`#list-${c.id}`}
                    onClick={() => {
                      const el = document.getElementById(
                        `list-${c.id}`,
                      ) as HTMLDetailsElement | null;
                      if (el) el.open = true;
                    }}
                  >
                    <div className={`metric-icon ${c.color}`}>
                      <c.icon size={22} />
                    </div>
                    <span className="metric-title">{c.label}</span>
                    <strong>{unavailable ? "—" : list.length}</strong>
                    <span className="metric-desc">
                      {unavailable
                        ? "Data unavailable"
                        : list.length
                          ? `Nearest: ${meters(list[0].distance_m)}`
                          : "No objects returned"}
                    </span>
                  </a>
                );
              })}
            </div>
            <div className="report-detail">
              <div className="detail-title">
                <h3>Nearby places</h3>
                <div className="distance-note">
                  <Compass size={18} />
                  <span>
                    {result.demo
                      ? "Straight-line distances. Demo places."
                      : "Distance types are shown per place."}
                  </span>
                </div>
              </div>
              <div className="place-groups">
                {cats.map((c) => (
                  <details id={`list-${c.id}`} key={c.id}>
                    <summary>
                      <span>
                        <c.icon size={17} />
                        {c.label}
                      </span>
                      <span>
                        {result.unavailable.includes(c.id)
                          ? "Unavailable"
                          : `${result.places.filter((p) => p.category === c.id).length} places`}{" "}
                        <ChevronDown size={16} />
                      </span>
                    </summary>
                    <div className="place-list">
                      {result.unavailable.includes(c.id) ? (
                        <p className="empty-small">
                          No reliable dataset connected for this category.
                        </p>
                      ) : (
                        result.places
                          .filter((p) => p.category === c.id)
                          .sort(
                            (a, b) =>
                              (a.distance_m ?? Infinity) -
                              (b.distance_m ?? Infinity),
                          )
                          .map((p) => (
                            <div className="place-row" key={p.id}>
                              <span>
                                {p.label}
                                {p.lines?.length ? (
                                  <small>Lines: {p.lines.join(", ")}</small>
                                ) : null}
                              </span>
                              <span>
                                <strong>{meters(p.distance_m)}</strong>
                                <small>
                                  {p.distance_type === "straight_line"
                                    ? "Straight line"
                                    : p.distance_type === "walking"
                                      ? "Walking distance"
                                      : "Distance type unspecified"}
                                </small>
                              </span>
                            </div>
                          ))
                      )}
                      {!result.unavailable.includes(c.id) &&
                        !result.places.some((p) => p.category === c.id) && (
                          <p className="empty-small">
                            No objects returned within this radius.
                          </p>
                        )}
                    </div>
                  </details>
                ))}
              </div>
            </div>
            <section className="commute" id="commute">
              <div>
                <span className="section-kicker">Your daily journey</span>
                <h2>How far is your everyday?</h2>
                <p>Choose your work or university.</p>
              </div>
              <div className="commute-form">
                <label htmlFor="dest">Your destination</label>
                <form
                  className="address-field"
                  onSubmit={(e) => {
                    e.preventDefault();
                    searchAddress(true);
                  }}
                >
                  <MapPin size={18} />
                  <input
                    id="dest"
                    placeholder="Search a destination"
                    value={destQuery}
                    onChange={(e) => setDestQuery(e.target.value)}
                  />
                  <button aria-label="Search destination" disabled={searching}>
                    <Search size={18} />
                  </button>
                </form>
                {destMatches.length > 0 && (
                  <div className="matches">
                    {destMatches.map((p) => (
                      <button
                        key={p.label}
                        onClick={() => {
                          setDestination(p);
                          setDestQuery(p.label);
                          setDestMatches([]);
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                )}
                <div className="destination-chips">
                  {destinations.map((p) => (
                    <button
                      className={destination?.label === p.label ? "chosen" : ""}
                      key={p.label}
                      onClick={() => {
                        setDestination(p);
                        setDestQuery(p.label);
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                {destination && (
                  <div className="commute-result">
                    <div>
                      <strong>
                        {meters(distance(result.location, destination))}
                      </strong>
                      <span>Straight-line distance · {destination.label}</span>
                    </div>
                    <button
                      aria-label="Remove destination"
                      onClick={() => {
                        setDestination(null);
                        setDestQuery("");
                      }}
                    >
                      <X size={17} />
                    </button>
                  </div>
                )}
                {mode === "live" && (
                  <p className="empty-small">Journey times and routing are unavailable. Destination distances are straight line only.</p>
                )}
                {result.commute && (
                  <p className="empty-small">
                    {result.commute.status || "Backend commute"}{" "}
                    {result.commute.distance_m !== undefined &&
                      `· ${meters(result.commute.distance_m)}`}{" "}
                    {result.commute.duration_minutes !== undefined &&
                      `· ${result.commute.duration_minutes} min (${result.commute.mode || "mode unspecified"})`}
                  </p>
                )}
              </div>
            </section>
            <div className="source-line">
              <Info size={15} />
              <span>
                {result.demo
                  ? "Illustrative dataset — no retrieval timestamp."
                  : "Retrieved: " +
                    (result.retrieved_at || "Timestamp unavailable")}
                {result.retrieved_at &&
                  Date.now() - Date.parse(result.retrieved_at) > 86400000 &&
                  " · More than 24 hours old"}
              </span>
              <button onClick={() => setAbout(true)}>
                View data sources <ArrowUpRight size={13} />
              </button>
            </div>
          </section>
        )}
        {(tab === "compare" || saved.length > 0) && (
          <section className="comparison" id="comparison">
            <div className="section-heading">
              <div>
                <span className="section-kicker">Side by side</span>
                <h2>Which feels like home?</h2>
              </div>
              <button
                className="outline-btn"
                onClick={() => {
                  setTab("explore");
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              >
                Add another home <ArrowRight size={16} />
              </button>
            </div>
            {saved.length === 0 ? (
              <div className="empty-comparison">
                <h3>Your shortlist starts here.</h3>
                <p>Explore an address, then select “Compare this home”.</p>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>In your neighborhood</th>
                      {[0, 1].map((i) => (
                        <th key={i}>
                          {saved[i] ? (
                            <>
                              <span className="table-tag">
                                HOME {i === 0 ? "A" : "B"} ·{" "}
                                {saved[i].demo ? "DEMO" : "LIVE"}
                              </span>
                              {saved[i].location.label}
                              <button
                                className="remove-home"
                                aria-label={`Remove home ${i === 0 ? "A" : "B"}`}
                                onClick={() =>
                                  setSaved((p) => p.filter((_, n) => n !== i))
                                }
                              >
                                <X size={16} />
                              </button>
                            </>
                          ) : (
                            <span className="muted">Add a second address</span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {saved.some((home) => home.scores) && (
                      <tr>
                        <td>Mobility Score</td>
                        {[0, 1].map((i) => <td key={i}>{saved[i]?.scores ? `${saved[i].scores!.mobility}/100` : "—"}</td>)}
                      </tr>
                    )}
                    <tr>
                      <td>Search radius</td>
                      {[0, 1].map((i) => (
                        <td key={i}>
                          {saved[i] ? meters(saved[i].radius_m) : "—"}
                        </td>
                      ))}
                    </tr>
                    {cats.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <c.icon size={16} />
                          {c.label}
                        </td>
                        {[0, 1].map((i) => (
                          <td key={i}>
                            {!saved[i]
                              ? "—"
                              : saved[i].unavailable.includes(c.id)
                                ? "Unavailable"
                                : `${saved[i].places.filter((p) => p.category === c.id).length} places`}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr>
                      <td>
                        <Navigation size={16} />
                        Nearest transport
                      </td>
                      {[0, 1].map((i) => (
                        <td key={i}>
                          {saved[i]
                            ? meters(
                                saved[i].places
                                  .filter((p) => p.category === "transport")
                                  .sort(
                                    (a, b) =>
                                      (a.distance_m ?? Infinity) -
                                      (b.distance_m ?? Infinity),
                                  )[0]?.distance_m,
                              )
                            : "—"}
                          {saved[i] && (
                            <small>See report for distance type</small>
                          )}
                        </td>
                      ))}
                    </tr>
                    {destination && (
                      <tr>
                        <td>Distance to {destination.label}</td>
                        {[0, 1].map((i) => (
                          <td key={i}>
                            {saved[i]
                              ? meters(distance(saved[i].location, destination))
                              : "—"}
                            <small>Straight line</small>
                          </td>
                        ))}
                      </tr>
                    )}
                  </tbody>
                </table>
                <p className="comparison-note">
                  {saved.length === 1
                    ? "Explore a second address to complete your comparison."
                    : "Each home uses the radius shown above."}
                </p>
              </div>
            )}
          </section>
        )}
      </main>
      <footer>
        <a className="footer-brand" href="#">
          UrbanLens <span>WARSAW</span>
        </a>
        <button onClick={() => setAbout(true)}>Data & sources</button>
        <small>Warsaw Open Data Hackathon 2026</small>
      </footer>
      {about && (
        <div
          className="modal-backdrop"
          onKeyDown={(e) => {
            if (e.key === "Escape") setAbout(false);
          }}
          onClick={() => setAbout(false)}
        >
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="data-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              autoFocus
              className="modal-close"
              aria-label="Close data information"
              onClick={() => setAbout(false)}
            >
              <X />
            </button>
            <span className="section-kicker">Data & sources</span>
            <h2 id="data-title">Behind the map.</h2>
            <h3>Demonstration mode</h3>
            <p>
              All nearby objects are synthetic examples. Distances are
              calculated from their illustrative coordinates. The OpenStreetMap
              base map is real.
            </p>
            <h3>Live mode</h3>
            <p>
              Neighborhood analysis comes exclusively from your team’s FastAPI
              service. Failed requests never fall back to demo data. Missing
              data is marked unavailable.
            </p>
            <div className="source-links">
              <a
                href="https://dane.um.warszawa.pl/en/catalogue/009fce84-0024-431a-aa5e-9515c539899e"
                target="_blank"
                rel="noreferrer"
              >
                Warsaw Open Data — transport stop dataset{" "}
                <ArrowUpRight size={16} />
              </a>
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
              >
                OpenStreetMap contributors — base map <ArrowUpRight size={16} />
              </a>
              <a
                href="https://operations.osmfoundation.org/policies/nominatim/"
                target="_blank"
                rel="noreferrer"
              >
                Nominatim — submitted live address searches{" "}
                <ArrowUpRight size={16} />
              </a>
            </div>
            {result?.sources.map((s, i) => (
              <p key={i}>
                {s.name}
                {s.retrieved_at && ` · ${s.retrieved_at}`}
              </p>
            ))}
            <button className="analyze" onClick={() => setAbout(false)}>
              Back to exploring <ArrowRight size={19} />
            </button>
          </section>
        </div>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
