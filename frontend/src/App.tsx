import { useEffect, useRef, useState } from "react";
import { ArrowRight, ArrowUpRight, ChevronDown, Info, LoaderCircle, MapPin, Moon, Navigation, Search, Sun, X } from "lucide-react";
import NeighborhoodMap from "./Map";
import Field from "./Field";
import ResultsPanel from "./ResultsPanel";
import ComparePage from "./ComparePage";
import { homes, destinations, demoAnalysis } from "./demo";
import { API_BASE_URL, commute, geocode, health, scoreAddress, scorePoint } from "./api";
import { inWarsaw, meters } from "./geo";
import { cats, compareLimit, nameSpot, radii, samePlace, shortLabel } from "./ui";
import type { Analysis, Category, Commute, Location, Place, Weights } from "./types";

type View = "start" | "results" | "compare";
export type Target = { address: string } | { point: Location };
type Mode = "demo" | "live";

const OUTSIDE = "Choose a spot inside Warsaw.";

// Resolves an address or map point into an analysis. Demo mode can return several
// matching example addresses for the user to pick from.
async function fetchAnalysis(mode: Mode, t: Target, radius: number, weights?: Weights): Promise<Analysis | Location[]> {
  if ("point" in t && !inWarsaw(t.point)) throw new Error(OUTSIDE);
  if (mode === "live")
    return "point" in t ? nameSpot(await scorePoint(t.point, radius, weights)) : scoreAddress(t.address, radius, weights);
  if ("point" in t) return nameSpot(demoAnalysis(t.point, radius));
  const needle = t.address.toLowerCase().trim();
  const found = homes.filter((h) => h.label.toLowerCase().includes(needle) || needle.includes(shortLabel(h.label).toLowerCase()));
  if (found.length > 1) return found;
  if (!found.length)
    throw new Error(`Demo mode knows only ${homes.map((h) => shortLabel(h.label)).join(", ")}. Pick one of them or click a spot on the map.`);
  return demoAnalysis(found[0], radius);
}

export default function App() {
  const [mode, setMode] = useState<Mode>(API_BASE_URL ? "live" : "demo");
  const [view, setView] = useState<View>("start");
  const [query, setQuery] = useState(homes[0].label);
  const [radius, setRadius] = useState(1000);
  const [mapCenter, setMapCenter] = useState<Location>(homes[0]);
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [matches, setMatches] = useState<Location[]>([]);
  const [saved, setSaved] = useState<Analysis[]>([]);
  const [destination, setDestination] = useState<Location | null>(null);
  const [filters, setFilters] = useState<Category[]>(cats.map((c) => c.id));
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [tab, setTab] = useState<"nearby" | "commute">("nearby");
  const [about, setAbout] = useState(false);
  const [centerTick, setCenterTick] = useState(0);
  // undefined = backend default weights; set once the user adjusts priorities.
  const [weights, setWeights] = useState<Weights | undefined>();
  // Routes belong to one home + destination pair and are fetched only on request.
  const [routes, setRoutes] = useState<{ key: string; data: Commute } | null>(null);
  const [routesBusy, setRoutesBusy] = useState(false);
  const [routesError, setRoutesError] = useState("");
  const [alive, setAlive] = useState<boolean | null>(null);
  const revision = useRef(0);
  const limit = compareLimit(mode);
  const modalRef = useRef<HTMLElement>(null);
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("olo-theme") === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("olo-theme", theme);
    } catch {
      /* Storage may be disabled. */
    }
  }, [theme]);
  useEffect(() => {
    if (!about || mode !== "live" || !API_BASE_URL) return;
    setAlive(null);
    health().then(setAlive);
  }, [about, mode]);
  useEffect(() => {
    if (!about) return;
    const previous = document.activeElement as HTMLElement | null;
    const modal = modalRef.current;
    const focusable = () => Array.from(modal?.querySelectorAll<HTMLElement>("button, a[href], input, select") || []);
    focusable()[0]?.focus();
    const keys = (e: KeyboardEvent) => {
      if (e.key === "Escape") return setAbout(false);
      if (e.key !== "Tab") return;
      const items = focusable(), first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keys);
    return () => {
      document.removeEventListener("keydown", keys);
      previous?.focus();
    };
  }, [about]);

  async function openHome(t: Target, r = radius, w = weights) {
    const rev = ++revision.current;
    setBusy(true);
    setError("");
    setMatches([]);
    try {
      const out = await fetchAnalysis(mode, t, r, w);
      if (rev !== revision.current) return;
      if (Array.isArray(out)) {
        setMatches(out);
        return;
      }
      setResult(out);
      setMapCenter(out.location);
      setQuery(out.location.label);
      setRadius(out.radius_m);
      setFocusedId(null);
      setHoveredId(null);
      setView("results");
    } catch (e) {
      if (rev === revision.current) setError((e as Error).message);
    } finally {
      if (rev === revision.current) setBusy(false);
    }
  }
  function submitQuery() {
    const q = query.trim();
    if (q.length < 3) return setError("Enter a street and building number, or click a spot on the map.");
    if (result && q === result.location.label) return openHome({ point: result.location });
    openHome({ address: q });
  }
  function changeRadius(r: number) {
    setRadius(r);
    if (view === "results" && result) openHome({ point: result.location }, r);
  }
  function changeMode(m: Mode) {
    if (m === mode) return;
    revision.current += 1;
    setMode(m);
    setBusy(false);
    setResult(null);
    setSaved([]);
    setDestination(null);
    setRoutes(null);
    setWeights(undefined);
    setMatches([]);
    setError("");
    setView("start");
  }
  function applyWeights(w: Weights | undefined) {
    setWeights(w);
    if (result) openHome({ point: result.location }, result.radius_m, w);
  }
  const routeKey = (home: Location, dest: Location) => `${home.latitude},${home.longitude}>${dest.latitude},${dest.longitude}`;
  async function checkRoutes() {
    if (!result || !destination) return;
    const key = routeKey(result.location, destination);
    setRoutesBusy(true);
    setRoutesError("");
    try {
      setRoutes({ key, data: await commute(result.location, destination) });
    } catch (e) {
      setRoutesError((e as Error).message);
    } finally {
      setRoutesBusy(false);
    }
  }
  const currentRoutes =
    result && destination && routes?.key === routeKey(result.location, destination) ? routes.data : null;
  const isSaved = (a: Analysis) => saved.some((s) => samePlace(s.location, a.location));
  function toggleSave(a: Analysis) {
    setSaved((prev) =>
      prev.some((s) => samePlace(s.location, a.location))
        ? prev.filter((s) => !samePlace(s.location, a.location))
        : prev.length >= limit
          ? prev
          : [...prev, a],
    );
  }
  // Used by the Compare page to add a home without leaving it.
  async function addToCompare(t: Target): Promise<Location[] | void> {
    const out = await fetchAnalysis(mode, t, radius, weights);
    if (Array.isArray(out)) return out;
    if (isSaved(out)) throw new Error(`${shortLabel(out.location.label)} is already in your comparison.`);
    setSaved((prev) => (prev.length >= limit ? prev : [...prev, out]));
  }
  async function findDestination(q: string): Promise<Location[]> {
    if (mode === "live") return [await geocode(q)];
    const needle = q.toLowerCase().trim();
    const found = destinations.filter((d) => d.label.toLowerCase().includes(needle));
    if (!found.length) throw new Error(`Demo mode knows only ${destinations.map((d) => d.label).join(", ")}.`);
    return found;
  }
  function focusPlace(p: Place) {
    setView("results");
    setTab("nearby");
    setFilters((f) => (f.includes(p.category) ? f : [...f, p.category]));
    setFocusedId(p.id);
  }
  function openSaved(a: Analysis) {
    setResult(a);
    setMapCenter(a.location);
    setQuery(a.location.label);
    setRadius(a.radius_m);
    setFocusedId(null);
    setView("results");
  }

  const errorBox = error && (
    <div className="alert" role="alert">
      <Info size={18} />
      <div>
        <p>{error}</p>
        {mode === "live" && /Demo/.test(error) && (
          <button className="text-btn" onClick={() => changeMode("demo")}>Switch to Demo</button>
        )}
      </div>
      <button className="icon-btn" aria-label="Dismiss" onClick={() => setError("")}>
        <X size={16} />
      </button>
    </div>
  );
  const location = view === "results" && result ? result.location : mapCenter;

  return (
    <>
      <header className="topbar">
        <button className="brand" onClick={() => setView("start")} aria-label="OLO, start page">
          OLO
        </button>
        <nav className="main-nav" aria-label="Sections">
          <button aria-current={view !== "compare"} onClick={() => setView(result ? "results" : "start")}>
            Explore
          </button>
          <button aria-current={view === "compare"} onClick={() => setView("compare")}>
            Compare
            <span className={`pill ${saved.length ? "is-filled" : ""}`}>{saved.length}</span>
          </button>
        </nav>
        <div className="topbar-end">
          {mode === "demo" && (
            <button className="demo-badge" onClick={() => setAbout(true)} title="Places are illustrative examples">
              Demo data
            </button>
          )}
          <button className="ghost-btn sources-btn" aria-label="Data & sources" onClick={() => setAbout(true)}>
            <Info size={16} />
            <span>Data & sources</span>
          </button>
          <button
            className="icon-btn round"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
          >
            {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
          </button>
        </div>
      </header>

      {view === "compare" ? (
        <ComparePage
          saved={saved}
          current={result}
          destination={destination}
          mode={mode}
          limit={limit}
          weights={weights}
          onRemove={(a) => toggleSave(a)}
          onOpen={openSaved}
          onAdd={addToCompare}
          onAddCurrent={() => result && toggleSave(result)}
          onBack={() => setView(result ? "results" : "start")}
        />
      ) : (
        <main className={`layout is-${view}`}>
          <aside className="panel">
            {view === "start" || !result ? (
              <div className="start">
                <div className="intro">
                  <h1>Check a neighborhood before you move in</h1>
                  <p>Enter an address or click a spot on the map.</p>
                </div>
                <div>
                  <label htmlFor="address" className="field-label">Warsaw address</label>
                  <Field
                    id="address"
                    value={query}
                    onChange={(v) => {
                      setQuery(v);
                      setMatches([]);
                    }}
                    onSubmit={submitQuery}
                    placeholder="Street and building number"
                    action={
                      <button type="submit" className="icon-btn" aria-label="Search" disabled={busy}>
                        <Search size={18} />
                      </button>
                    }
                  />
                </div>
                {matches.length > 0 && (
                  <div className="matches">
                    <span>Which one?</span>
                    {matches.map((m) => (
                      <button key={m.label} onClick={() => openHome({ point: m })}>
                        <MapPin size={15} />
                        {m.label}
                      </button>
                    ))}
                  </div>
                )}
                <div className="examples">
                  <span>Try</span>
                  {homes.map((h) => (
                    <button
                      key={h.label}
                      className={query === h.label ? "is-current" : ""}
                      onClick={() => {
                        setQuery(h.label);
                        setMatches([]);
                        setError("");
                      }}
                    >
                      {shortLabel(h.label)}
                    </button>
                  ))}
                </div>
                <div className="radius">
                  <label htmlFor="radius">Within</label>
                  <div className="select">
                    <select id="radius" value={radius} onChange={(e) => changeRadius(Number(e.target.value))}>
                      {radii.map((r) => (
                        <option key={r} value={r}>{meters(r)}</option>
                      ))}
                    </select>
                    <ChevronDown size={14} />
                  </div>
                </div>
                <button className="primary-btn" onClick={submitQuery} disabled={busy}>
                  {busy ? "Analyzing neighborhood…" : "Explore neighborhood"}
                  {busy ? <LoaderCircle className="spin" size={20} /> : <ArrowRight size={20} />}
                </button>
                {mode === "demo" && <p className="demo-line">Demo mode: nearby places are made-up examples.</p>}
                {result && (
                  <button className="text-btn" onClick={() => setView("results")}>
                    Back to results for {shortLabel(result.location.label)}
                  </button>
                )}
                {errorBox}
              </div>
            ) : (
              <ResultsPanel
                result={result}
                query={query}
                onQuery={setQuery}
                onSubmit={submitQuery}
                radius={radius}
                onRadius={changeRadius}
                busy={busy}
                error={errorBox}
                matches={matches}
                onPickMatch={(m) => openHome({ point: m })}
                onNewSearch={() => setView("start")}
                saved={isSaved(result)}
                compareFull={saved.length >= limit}
                compareLimit={limit}
                live={mode === "live"}
                onApplyWeights={applyWeights}
                routes={currentRoutes}
                routesBusy={routesBusy}
                routesError={routesError}
                onCheckRoutes={checkRoutes}
                savedCount={saved.length}
                onToggleSave={() => toggleSave(result)}
                onOpenCompare={() => setView("compare")}
                tab={tab}
                onTab={setTab}
                filters={filters}
                onToggleFilter={(c) => setFilters((f) => (f.includes(c) ? f.filter((x) => x !== c) : [...f, c]))}
                focusedId={focusedId}
                onFocus={setFocusedId}
                onHover={setHoveredId}
                destination={destination}
                onDestination={setDestination}
                findDestination={findDestination}
                quickDestinations={destinations}
                savedHomes={saved}
              />
            )}
          </aside>
          <section className="map-area" aria-label="Map">
            <NeighborhoodMap
              location={location}
              radius={view === "results" && result ? result.radius_m : radius}
              showHome
              places={view === "results" && result ? result.places : []}
              filters={filters}
              focusedId={focusedId}
              hoveredId={hoveredId}
              destination={view === "results" ? destination : null}
              routes={view === "results" ? currentRoutes : null}
              centerTick={centerTick}
              onFocusPlace={focusPlace}
              onPick={(p) => openHome({ point: p })}
            />
            {view === "start" && <div className="map-hint">Click the map to explore any spot</div>}
            <button className="map-btn" aria-label="Recenter map" title="Recenter map" onClick={() => setCenterTick((t) => t + 1)}>
              <Navigation size={17} />
            </button>
            {busy && (
              <div className="map-loading" role="status">
                <LoaderCircle className="spin" size={18} /> Analyzing…
              </div>
            )}
          </section>
        </main>
      )}

      {about && (
        <div className="modal-backdrop" onClick={() => setAbout(false)}>
          <section ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="about-title" onClick={(e) => e.stopPropagation()}>
            <button className="icon-btn modal-close" aria-label="Close" onClick={() => setAbout(false)}>
              <X size={18} />
            </button>
            <h2 id="about-title">Data & sources</h2>
            <h3>Data mode</h3>
            <div className="segmented" role="group" aria-label="Data mode">
              <button aria-pressed={mode === "demo"} onClick={() => changeMode("demo")}>Demo</button>
              <button aria-pressed={mode === "live"} onClick={() => changeMode("live")}>
                Live <span className={`dot ${API_BASE_URL && alive !== false ? "is-on" : ""}`} />
              </button>
            </div>
            <p>
              {mode === "demo"
                ? "Demo: places are made-up examples placed around the chosen point. The map itself is real."
                : API_BASE_URL
                  ? "Live: stops, parks, listed parking and school sports fields come from Warsaw Open Data through our service. Categories without a reliable source show “No data yet”."
                  : "Live: the data service isn’t connected in this build."}
            </p>
            {mode === "live" && API_BASE_URL && (
              <p className={alive === false ? "warning" : ""}>
                {alive === null ? "Checking the data service…" : alive ? "Data service is reachable." : "Data service isn’t reachable right now."}
              </p>
            )}
            {(saved.length > 0 || destination) && <p className="warning">Switching mode clears your comparison and commute destination.</p>}
            <h3>Sources</h3>
            <div className="source-links">
              <a href="https://dane.um.warszawa.pl/en/catalogue/009fce84-0024-431a-aa5e-9515c539899e" target="_blank" rel="noreferrer">
                Warsaw Open Data: public transport stops <ArrowUpRight size={16} />
              </a>
              <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
                © OpenStreetMap contributors: map and address search <ArrowUpRight size={16} />
              </a>
              <a href="https://routing.openstreetmap.de/about.html" target="_blank" rel="noreferrer">
                FOSSGIS OSRM: walking and driving routes (on request) <ArrowUpRight size={16} />
              </a>
            </div>
            {result?.sources.map((s, i) => (
              <p key={i} className="source-note">
                {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}
                {s.retrieved_at && ` · retrieved ${new Date(s.retrieved_at).toLocaleDateString()}`}
              </p>
            ))}
            <p className="source-note">
              Distances to places are straight-line (“as the crow flies”). Walking and driving times are provider estimates without live traffic; public transport journeys aren’t available.
            </p>
          </section>
        </div>
      )}
    </>
  );
}
