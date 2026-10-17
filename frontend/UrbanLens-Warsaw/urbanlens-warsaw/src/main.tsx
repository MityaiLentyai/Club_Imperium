import React, { useState, useMemo, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { ArrowUpRight, ArrowRight, MapPin, Search, TrainFront, ShoppingBasket, TreePine, Cross, ParkingCircle, Navigation, Info, X, ChevronDown, LoaderCircle, Compass, Moon, Sun, ArrowLeftRight, } from "lucide-react";
import NeighborhoodMap from "./Map";
import { InfrastructureSummary, FacilityDetails } from "./Infrastructure";
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
    const [mode, setMode] = useState<"demo" | "live">("demo"), [location, setLocation] = useState<Location>(homes[0]), [query, setQuery] = useState(homes[0].label), [radius, setRadius] = useState(1000), [filters, setFilters] = useState<Category[]>(cats.map((c) => c.id)), [response, setResult] = useState<Analysis | null>(null), [saved, setSaved] = useState<Analysis[]>([]), [tab, setTab] = useState("explore"), [busy, setBusy] = useState(false), [searching, setSearching] = useState(false), [error, setError] = useState(""), [matches, setMatches] = useState<Location[]>([]), [destination, setDestination] = useState<Location | null>(null), [destQuery, setDestQuery] = useState(""), [destMatches, setDestMatches] = useState<Location[]>([]), [about, setAbout] = useState(false), [centerTick, setCenterTick] = useState(0);
    const [expanded, setExpanded] = useState(false);
    const [category, setCategory] = useState<Category>("transport");
    const [focusedId, setFocusedId] = useState<string | null>(null);
    const initial = useMemo(() => ({ ...demoAnalysis(location, radius), radius_m: radius }), [location, radius]);
    const requestRevision = useRef(0);
    const modalRef = useRef<HTMLElement>(null);
    const [theme, setTheme] = useState(() => {
        try {
            return localStorage.getItem("urbanlens-theme") === "dark" ? "dark" : "light";
        }
        catch {
            return "light";
        }
    });
    useEffect(() => {
        document.documentElement.dataset.theme = theme;
        try {
            localStorage.setItem("urbanlens-theme", theme);
        }
        catch { /* Storage may be disabled. */ }
    }, [theme]);
    useEffect(() => {
        const close = (e: KeyboardEvent) => { if (e.key === "Escape")
            setAbout(false); };
        window.addEventListener("keydown", close);
        return () => window.removeEventListener("keydown", close);
    }, []);
    useEffect(() => {
        if (!about)
            return;
        const previous = document.activeElement as HTMLElement | null;
        const modal = modalRef.current;
        const focusable = () => Array.from(modal?.querySelectorAll<HTMLElement>('button, a[href], input, select, [tabindex="0"]') || []);
        focusable()[0]?.focus();
        const trap = (e: KeyboardEvent) => {
            if (e.key !== "Tab")
                return;
            const items = focusable(), first = items[0], last = items[items.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last?.focus();
            }
            else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first?.focus();
            }
        };
        document.addEventListener("keydown", trap);
        return () => { document.removeEventListener("keydown", trap); previous?.focus(); };
    }, [about]);
    const result = response || (mode === "demo" ? initial : null);
    const shown = result?.places || (mode === "demo" ? initial.places : []);
    const active = result?.location || location;
    function invalidatePending() {
        requestRevision.current += 1;
        setBusy(false);
        setSearching(false);
    }
    function chooseDestination(p: Location | null) {
        invalidatePending();
        setDestination(p);
        setDestQuery(p?.label || "");
        setDestMatches([]);
        setResult(previous => previous ? { ...previous, commute: undefined } : null);
    }
    function select(p: Location) {
        if (!inWarsaw(p)) {
            setError("Choose a location within Warsaw.");
            return;
        }
        invalidatePending();
        setExpanded(true);
        setFocusedId(null);
        setTab("explore");
        setLocation(p);
        setQuery(p.label);
        setResult(null);
        setMatches([]);
        setError("");
    }
    function changeMode(m: "demo" | "live") {
        invalidatePending();
        setExpanded(false);
        setFocusedId(null);
        setMode(m);
        setResult(null);
        setSaved([]);
        setError("");
        setMatches([]);
        setDestMatches([]);
        setDestination(null);
        setDestQuery("");
        setTab("explore");
    }
    async function searchAddress(dest = false) {
        const revision = ++requestRevision.current;
        setBusy(false);
        setError("");
        setSearching(true);
        try {
            const q = dest ? destQuery : query;
            if (mode === "demo") {
                const all = dest ? destinations : homes;
                const matches = all.filter((p) => p.label.toLowerCase().includes(q.toLowerCase().trim()));
                if (!matches.length)
                    throw new Error("Demo mode includes the example addresses below. Select one, or choose a point on the map.");
                dest ? setDestMatches(matches) : setMatches(matches);
            }
            else {
                const found = await geocode(q);
                if (revision !== requestRevision.current)
                    return;
                if (!found.length)
                    throw new Error("No matching Warsaw address. Try another address or select a point on the map.");
                dest ? setDestMatches(found) : setMatches(found);
            }
        }
        catch (e) {
            if (revision === requestRevision.current)
                setError((e as Error).message);
        }
        finally {
            if (revision === requestRevision.current)
                setSearching(false);
        }
    }
    async function run() {
        const revision = ++requestRevision.current;
        setSearching(false);
        setBusy(true);
        setError("");
        try {
            let target = location;
            if (query.trim() && query.trim() !== location.label) {
                const found = mode === "demo"
                    ? homes.filter((p) => p.label.toLowerCase().includes(query.toLowerCase().trim()))
                    : await geocode(query);
                if (revision !== requestRevision.current)
                    return;
                if (found.length !== 1) {
                    setMatches(found);
                    throw new Error(found.length
                        ? "Choose a matching address, then explore."
                        : "Address not found. Try an example or choose a point on the map.");
                }
                target = found[0];
                setLocation(target);
                setQuery(target.label);
            }
            setExpanded(true);
            const data = mode === "demo"
                ? demoAnalysis(target, radius)
                : await analyze({ ...target, radius_m: radius, destination });
            if (revision !== requestRevision.current)
                return;
            setResult({ ...data, radius_m: radius });
        }
        catch (e) {
            if (revision === requestRevision.current)
                setError((e as Error).message);
        }
        finally {
            if (revision === requestRevision.current)
                setBusy(false);
        }
    }
    function save() {
        if (!result)
            return;
        setSaved((prev) => {
            if (prev.some((p) => p.location.latitude === result.location.latitude &&
                p.location.longitude === result.location.longitude))
                return prev;
            return [...prev.slice(-1), result];
        });
        setTab("compare");
    }
    const selectedCategory = cats.find(c => c.id === category)!;
    const categoryPlaces = (result?.places || []).filter(p => p.category === category).sort((a,b) => (a.distance_m ?? Infinity) - (b.distance_m ?? Infinity));
    const focusedPlace = categoryPlaces.find(p => p.id === focusedId) || categoryPlaces[0];
    const savedCurrent = result &&
        saved.some((p) => p.location.latitude === result.location.latitude &&
            p.location.longitude === result.location.longitude);
    return (<>
      <header>
        <a className="brand" href="#" onClick={() => {
            setTab("explore");
            window.scrollTo({ top: 0, behavior: "smooth" });
        }}>
          <span className="brand-symbol">
            u<span>l</span>
          </span>
          UrbanLens<span className="brand-city">WARSAW</span>
        </a>
        <button className="header-sources" onClick={() => setAbout(true)}>Data & sources</button>
        <button className="theme-toggle" aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} onClick={() => setTheme(t => t === "light" ? "dark" : "light")}>
          {theme === "light" ? <Moon size={18}/> : <Sun size={18}/>}
        </button>
        <div className="mode" aria-label="Data mode">
          <button aria-pressed={mode === "demo"} className={mode === "demo" ? "selected" : ""} onClick={() => changeMode("demo")}>
            Demo
          </button>
          <button aria-pressed={mode === "live"} className={mode === "live" ? "selected" : ""} onClick={() => changeMode("live")}>
            Live <span className={API_BASE_URL ? "tiny-dot" : "offline-dot"}/>
          </button>
        </div>
      </header>
      <main>
        <section className={`hero ${expanded ? "is-expanded" : "is-start"}`}>
          <div className="search-panel">
            <form onSubmit={(e) => {
            e.preventDefault();
            searchAddress();
        }}>
              <label htmlFor="address">Your Warsaw address</label>
              <div className="address-field">
                <MapPin size={19}/>
                <input id="address" value={query} onChange={(e) => { invalidatePending(); setMatches([]); setQuery(e.target.value); }} placeholder="Enter a Warsaw address" autoComplete="off"/>
                <button className="search-icon" disabled={searching} aria-label="Search address">
                  {searching ? (<LoaderCircle className="spin" size={20}/>) : (<Search size={20}/>)}
                </button>
              </div>
              {matches.length > 0 && (<div className="matches">
                  {matches.map((p) => (<button type="button" key={p.label} onClick={() => select(p)}>
                      <MapPin size={15}/>
                      {p.label}
                    </button>))}
                </div>)}
            </form>
            <div className="example-row">
              <span>{mode === "demo" ? "TRY" : "SELECTED"}</span>
              {mode === "demo" ? (homes.slice(0, 2).map((p) => (<button key={p.label} className={location.label === p.label ? "current" : ""} onClick={() => select(p)}>
                    {p.label.split(",")[0]}
                  </button>))) : (<small>{location.label}</small>)}
            </div>
            <div className="radius-row">
              <label htmlFor="radius">Search within</label>
              <div className="radius-control">
                <select id="radius" value={radius} onChange={(e) => {
            invalidatePending();
            setRadius(Number(e.target.value));
            setResult(null);
        }}>
                  <option value={500}>500 m</option>
                  <option value={1000}>1 km</option>
                  <option value={1500}>1.5 km</option>
                  <option value={2000}>2 km</option>
                </select>
                <ChevronDown size={14}/>
              </div>
            </div>
            <button className="analyze" onClick={run} disabled={busy}>
              {busy ? (<>
                  <LoaderCircle size={19} className="spin"/>
                  Analyzing neighborhood…
                </>) : (<>
                  Explore neighborhood <ArrowRight size={21}/>
                </>)}
            </button>
            {expanded && <button className="back-to-search" onClick={() => setExpanded(false)}>← Back to search</button>}
        <div className="category-bar">
          <span className="filter-label">Show on map</span>
          <div className="filter-buttons">
            {cats.map((c) => (<button key={c.id} aria-pressed={filters.includes(c.id)} className={`${c.color} ${filters.includes(c.id) ? "on" : ""}`} onClick={() => setFilters((p) => p.includes(c.id)
                ? p.filter((x) => x !== c.id)
                : [...p, c.id])}>
                <c.icon size={17}/>
                {c.label}
                <span className="filter-dot"/>
              </button>))}
          </div>
        </div>
        <div className="status-note">
          <Info size={14}/>
          {mode === "demo"
            ? "Demo · Illustrative places, real map."
            : API_BASE_URL
                ? "Live · Backend configured."
                : "Live analysis isn’t connected yet. Try Demo."}
        </div>
        {error && (<div className="error" role="alert">
            <Info size={18}/>
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={17}/>
            </button>
          </div>)}
          </div>
          <div className="map-panel">
            <NeighborhoodMap location={active} radius={radius} places={shown} filters={filters} onPick={select} destination={destination} centerTick={centerTick}/>
            <div className="map-title">
              <span className="tiny-dot"/> Warsaw
            </div>
            <div className="map-demo">
              {mode === "demo" ? "Demo places" : "Live mode"}
            </div>
            <button className="map-center" aria-label="Recenter map" title="Recenter map" onClick={() => setCenterTick((t) => t + 1)}>
              <Navigation size={18}/>
            </button>
          </div>

          <div className="panel-content" hidden={!expanded}>
        <nav aria-label="Analysis views">
          <button className={tab === "explore" ? "active" : ""} onClick={() => {
            setTab("explore");
            window.scrollTo({ top: 0, behavior: "smooth" });
        }}>
            <Compass size={18}/><span>Nearby</span>
          </button>
          <button className={tab === "compare" ? "active" : ""} onClick={() => {
            setTab("compare");
        }}>
            <ArrowLeftRight size={18}/><span>Compare</span>
            {saved.length > 0 && <span className="count">{saved.length}</span>}
          </button>
          <button className={tab === "commute" ? "active" : ""} onClick={() => setTab("commute")}><Navigation size={18}/><span>Commute</span></button>
          <button onClick={() => setAbout(true)}><Info size={18}/><span>Sources</span></button>
        </nav>
<div className="results-scroll">
        {!result && tab === "explore" && <div className="empty-comparison"><h2>Explore this address</h2><p>Run a live analysis to see nearby places.</p></div>}
        {result && (<section className="report" id="report" hidden={tab === "compare"}>
            <div className="section-heading" hidden={tab === "commute"}>
              <div>
                <span className="section-kicker">
                  {result.demo ? "Demo report" : "Neighborhood report"}
                </span>
                <h2>Nearby essentials</h2>
                <p>
                  {result.location.label}{" "}
                  <span className="muted">· Within {meters(radius)}</span>
                </p>
              </div>
              <button className="outline-btn" onClick={save}>
                {savedCurrent ? "Added to comparison" : "Compare this home"}
              </button>
            </div>
            <div className="report-detail" hidden={tab !== "explore"}>
              <div className="category-list" aria-label="Infrastructure categories">
                {cats.map(c => {
                  const places = result.places.filter(p => p.category === c.id);
                  const unavailable = result.unavailable.includes(c.id);
                  return <button key={c.id} aria-pressed={category === c.id} onClick={() => { setCategory(c.id); setFocusedId(null); }}>
                    <c.icon size={18}/><span>{c.label}<small>{unavailable ? "Unavailable" : `${result.datasets?.[c.id]?.total ?? places.length} nearby`}</small></span><ChevronDown size={14}/>
                  </button>;
                })}
                <div className="environment"><span>Air quality<strong>Unavailable</strong></span><span>Noise<strong>Unavailable</strong></span></div>
              </div>
              <div className="category-detail">
                <div className="detail-heading"><div><span className="section-kicker">Within {meters(radius)}</span><h3>{selectedCategory.label}</h3></div><span className="distance-note">{result.demo ? "Demo · Straight-line distances" : "Distance type shown per place"}</span></div>
                <InfrastructureSummary result={result} category={category}/>
                {result.unavailable.includes(category) ? <div className="empty-comparison"><selectedCategory.icon size={30}/><h3>Data unavailable</h3><p>No reliable dataset is connected for this category.</p></div> : !categoryPlaces.length ? <div className="empty-comparison"><h3>No places returned</h3><p>Try a larger search radius.</p></div> : <div className="places-and-detail">
                  <div className="place-list">{categoryPlaces.map(p => <button className={`place-row ${focusedPlace?.id === p.id ? "chosen" : ""}`} key={p.id} onClick={() => setFocusedId(p.id)}><span>{p.label}{p.lines?.length ? <small>Lines: {p.lines.join(", ")}</small> : null}</span><span><strong>{meters(p.distance_m)}</strong><small>{p.distance_type === "walking" ? "Walking" : p.distance_type === "straight_line" ? "Straight line" : "Type unspecified"}</small></span></button>)}</div>
                  {focusedPlace && <div className="place-inspector"><selectedCategory.icon size={26}/><span className="section-kicker">{result.demo ? "Illustrative place" : selectedCategory.label}</span><h3>{focusedPlace.label}</h3><strong>{meters(focusedPlace.distance_m)}</strong><p>{focusedPlace.distance_type === "walking" ? "Walking distance" : focusedPlace.distance_type === "straight_line" ? "Straight-line distance" : "Distance type unspecified"}</p>{focusedPlace.lines?.length ? <p>Lines {focusedPlace.lines.join(" · ")}</p> : null}<FacilityDetails place={focusedPlace}/><small>{focusedPlace.latitude.toFixed(5)}, {focusedPlace.longitude.toFixed(5)}</small></div>}
                </div>}
              </div>
            </div>
          </section>)}
            <section className="commute" id="commute" hidden={tab !== "commute"}>
              <div>
                <span className="section-kicker">Your daily journey</span>
                <h2>Your commute</h2>
                <p>Choose your work or university.</p>
              </div>
              <div className="commute-form">
                <label htmlFor="dest">Your destination</label>
                <form className="address-field" onSubmit={(e) => {
            e.preventDefault();
            searchAddress(true);
        }}>
                  <MapPin size={18}/>
                  <input id="dest" placeholder="Search a destination" value={destQuery} onChange={(e) => { invalidatePending(); setDestMatches([]); setDestQuery(e.target.value); }}/>
                  <button aria-label="Search destination" disabled={searching}>
                    <Search size={18}/>
                  </button>
                </form>
                {destMatches.length > 0 && (<div className="matches">
                    {destMatches.map((p) => (<button key={p.label} onClick={() => {
                    chooseDestination(p);
                }}>
                        {p.label}
                      </button>))}
                  </div>)}
                <div className="destination-chips">
                  {destinations.map((p) => (<button className={destination?.label === p.label ? "chosen" : ""} key={p.label} onClick={() => {
                chooseDestination(p);
            }}>
                      {p.label}
                    </button>))}
                </div>
                {destination && (<div className="commute-result">
                    <div>
                      <strong>
                        {meters(distance(active, destination))}
                      </strong>
                      <span>Straight-line distance · {destination.label}</span>
                    </div>
                    <button aria-label="Remove destination" onClick={() => {
                chooseDestination(null);
            }}>
                      <X size={17}/>
                    </button>
                  </div>)}
                {destination && mode === "live" && (<button className="outline-btn" onClick={run} disabled={busy}>
                    Check journey <ArrowRight size={16}/>
                  </button>)}
                {result?.commute && (<p className="empty-small">
                    {result?.commute.status || "Backend commute"}{" "}
                    {result?.commute.distance_m !== undefined &&
                `· ${meters(result?.commute.distance_m)}`}{" "}
                    {result?.commute.duration_minutes !== undefined &&
                `· ${result?.commute.duration_minutes} min (${result?.commute.mode || "mode unspecified"})`}
                  </p>)}
              </div>
            </section>
        {(tab === "compare") && (<section className="comparison" id="comparison">
            <div className="section-heading">
              <div>
                <span className="section-kicker">Side by side</span>
                <h2>Compare homes</h2>
              </div>
              <button className="outline-btn" onClick={() => {
                setTab("explore");
                window.scrollTo({ top: 0, behavior: "smooth" });
            }}>
                Add another home <ArrowRight size={16}/>
              </button>
            </div>
            {saved.length === 0 ? (<div className="empty-comparison">
                <h3>Your shortlist starts here.</h3>
                <p>Explore an address, then select “Compare this home”.</p>
              </div>) : (<div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>In your neighborhood</th>
                      {[0, 1].map((i) => (<th key={i}>
                          {saved[i] ? (<>
                              <span className="table-tag">
                                HOME {i === 0 ? "A" : "B"} ·{" "}
                                {saved[i].demo ? "DEMO" : "LIVE"}
                              </span>
                              {saved[i].location.label}
                              <button className="remove-home" aria-label={`Remove home ${i === 0 ? "A" : "B"}`} onClick={() => setSaved((p) => p.filter((_, n) => n !== i))}>
                                <X size={16}/>
                              </button>
                            </>) : (<span className="muted">Add a second address</span>)}
                        </th>))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Search radius</td>
                      {[0, 1].map((i) => (<td key={i}>
                          {saved[i] ? meters(saved[i].radius_m) : "—"}
                        </td>))}
                    </tr>
                    {cats.map((c) => (<tr key={c.id}>
                        <td>
                          <c.icon size={16}/>
                          {c.label}
                        </td>
                        {[0, 1].map((i) => (<td key={i}>
                            {!saved[i]
                            ? "—"
                            : saved[i].unavailable.includes(c.id)
                                ? "Unavailable"
                                : `${saved[i].datasets?.[c.id]?.total ?? saved[i].places.filter((p) => p.category === c.id).length} places`}
                          </td>))}
                      </tr>))}
                    <tr>
                      <td>
                        <Navigation size={16}/>
                        Nearest transport
                      </td>
                      {[0, 1].map((i) => (<td key={i}>
                          {saved[i]
                        ? meters(saved[i].places
                            .filter((p) => p.category === "transport")
                            .sort((a, b) => (a.distance_m ?? Infinity) -
                            (b.distance_m ?? Infinity))[0]?.distance_m)
                        : "—"}
                          {saved[i] && (<small>See report for distance type</small>)}
                        </td>))}
                    </tr>
                    {destination && (<tr>
                        <td>Distance to {destination.label}</td>
                        {[0, 1].map((i) => (<td key={i}>
                            {saved[i]
                            ? meters(distance(saved[i].location, destination))
                            : "—"}
                            <small>Straight line</small>
                          </td>))}
                      </tr>)}
                  </tbody>
                </table>
                <p className="comparison-note">
                  {saved.length === 1
                    ? "Explore a second address to complete your comparison."
                    : "Each home uses the radius shown above."}
                </p>
              </div>)}
          </section>)}
                    </div>
          </div>

        </section>
      </main>
      {about && (<div className="modal-backdrop" onKeyDown={(e) => {
                if (e.key === "Escape")
                    setAbout(false);
            }} onClick={() => setAbout(false)}>
          <section ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="data-title" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" aria-label="Close data information" onClick={() => setAbout(false)}>
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
              <a href="https://dane.um.warszawa.pl/en/catalogue/009fce84-0024-431a-aa5e-9515c539899e" target="_blank" rel="noreferrer">
                Warsaw Open Data — planned stop dataset{" "}
                <ArrowUpRight size={16}/>
              </a>
              <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
                OpenStreetMap contributors — base map <ArrowUpRight size={16}/>
              </a>
              <a href="https://operations.osmfoundation.org/policies/nominatim/" target="_blank" rel="noreferrer">
                Nominatim — submitted live address searches{" "}
                <ArrowUpRight size={16}/>
              </a>
            </div>
            {result && <p>{result.demo ? "Illustrative dataset · no retrieval timestamp" : `Retrieved: ${result.retrieved_at || "Timestamp unavailable"}`}</p>}
            {result?.sources.map((s, i) => (<p key={i}>
                {s.name}
                {s.retrieved_at && ` · ${s.retrieved_at}`}
              </p>))}
            <button className="analyze" onClick={() => setAbout(false)}>
              Back to exploring <ArrowRight size={19}/>
            </button>
          </section>
        </div>)}
    </>);
}
createRoot(document.getElementById("root")!).render(<React.StrictMode>
    <App />
  </React.StrictMode>);
