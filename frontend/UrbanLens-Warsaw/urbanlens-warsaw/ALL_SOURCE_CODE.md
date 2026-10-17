# UrbanLens Warsaw — все исходники

Актуальная версия с двумя состояниями экрана.

## package.json

```json
{
  "name": "urbanlens-warsaw",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "tsc --noEmit && vite build",
    "test": "node --test tests/*.test.mjs"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "leaflet": "^1.9.4",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "vite": "^6.0.0",
    "typescript": "^5.7.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@types/leaflet": "^1.9.15"
  }
}
```

## index.html

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta name="theme-color" content="#2568df" />
    <meta
      name="description"
      content="Understand the neighborhood before choosing your next home. Explore Warsaw with UrbanLens."
    />
    <title>UrbanLens Warsaw — Find your everyday</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

## tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "allowImportingTsExtensions": true
  },
  "include": ["src"]
}
```

## .env.example

```text
VITE_API_BASE_URL=http://localhost:8000
# Optional replacement provider with a Nominatim-compatible search endpoint.
VITE_GEOCODER_URL=https://nominatim.openstreetmap.org/search
```

## src/main.tsx

```tsx
import React, { useState, useMemo, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { ArrowUpRight, ArrowRight, MapPin, Search, TrainFront, ShoppingBasket, TreePine, Cross, ParkingCircle, Navigation, Info, X, ChevronDown, LoaderCircle, Compass, Moon, Sun, ArrowLeftRight, } from "lucide-react";
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
                    <c.icon size={18}/><span>{c.label}<small>{unavailable ? "Unavailable" : `${places.length} nearby`}</small></span><ChevronDown size={14}/>
                  </button>;
                })}
                <div className="environment"><span>Air quality<strong>Unavailable</strong></span><span>Noise<strong>Unavailable</strong></span></div>
              </div>
              <div className="category-detail">
                <div className="detail-heading"><div><span className="section-kicker">Within {meters(radius)}</span><h3>{selectedCategory.label}</h3></div><span className="distance-note">{result.demo ? "Demo · Straight-line distances" : "Distance type shown per place"}</span></div>
                {result.unavailable.includes(category) ? <div className="empty-comparison"><selectedCategory.icon size={30}/><h3>Data unavailable</h3><p>No reliable dataset is connected for this category.</p></div> : !categoryPlaces.length ? <div className="empty-comparison"><h3>No places returned</h3><p>Try a larger search radius.</p></div> : <div className="places-and-detail">
                  <div className="place-list">{categoryPlaces.map(p => <button className={`place-row ${focusedPlace?.id === p.id ? "chosen" : ""}`} key={p.id} onClick={() => setFocusedId(p.id)}><span>{p.label}{p.lines?.length ? <small>Lines: {p.lines.join(", ")}</small> : null}</span><span><strong>{meters(p.distance_m)}</strong><small>{p.distance_type === "walking" ? "Walking" : p.distance_type === "straight_line" ? "Straight line" : "Type unspecified"}</small></span></button>)}</div>
                  {focusedPlace && <div className="place-inspector"><selectedCategory.icon size={26}/><span className="section-kicker">{result.demo ? "Illustrative place" : selectedCategory.label}</span><h3>{focusedPlace.label}</h3><strong>{meters(focusedPlace.distance_m)}</strong><p>{focusedPlace.distance_type === "walking" ? "Walking distance" : focusedPlace.distance_type === "straight_line" ? "Straight-line distance" : "Distance type unspecified"}</p>{focusedPlace.lines?.length ? <p>Lines {focusedPlace.lines.join(" · ")}</p> : null}<small>{focusedPlace.latitude.toFixed(5)}, {focusedPlace.longitude.toFixed(5)}</small></div>}
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
                                : `${saved[i].places.filter((p) => p.category === c.id).length} places`}
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
```

## src/style.css

```css
:root {
  font-family:Inter,"Segoe UI",Arial,sans-serif;
  --bg:#f3f5f7;
  --surface:#fff;
  --soft:#edf2f6;
  --text:#20334a;
  --muted:#65778b;
  --line:#dfe6ec;
  --accent:#315e88;
  --tint:#e8f0f7;
  color:var(--text);
  background:var(--bg);
  color-scheme:light;
  font-synthesis:none
}
:root[data-theme=dark] {
  --bg:#101922;
  --surface:#182430;
  --soft:#202f3d;
  --text:#e0e9f1;
  --muted:#a0b1c2;
  --line:#304150;
  --accent:#a0c5e6;
  --tint:#263c50;
  color-scheme:dark
}
* {
  box-sizing:border-box
}
body {
  margin:0
}
button,input,select {
  font:inherit
}
button {
  cursor:pointer;
  color:inherit;
  background:none;
  border:0
}
button:disabled {
  opacity:.55;
  cursor:wait
}
a {
  color:inherit;
  text-decoration:none
}
button:hover {
  color:var(--accent)
}
button:focus-visible,a:focus-visible,summary:focus-visible {
  outline:2px solid var(--accent);
  outline-offset:3px
}
input:focus {
  outline:none
}
h1,h2,h3,p {
  margin:0
}
[hidden] {
  display:none!important
}
#root {
  height:100dvh;
  display:flex;
  flex-direction:column;
  overflow:hidden
}
header {
  height:76px;
  flex-shrink:0;
  padding:0 30px;
  display:flex;
  align-items:center;
  gap:26px;
  background:var(--surface);
  border-bottom:1px solid var(--line)
}
.brand {
  display:flex;
  align-items:center;
  gap:10px;
  font-size:22px;
  font-weight:650;
  letter-spacing:-.8px;
  white-space:nowrap
}
.brand-symbol {
  display:grid;
  place-items:center;
  width:30px;
  height:34px;
  background:var(--text);
  color:var(--surface);
  font-family:Georgia,serif;
  font-size:27px;
  border-radius:3px
}
.brand-symbol>span {
  display:none
}
.brand-city {
  font-size:10px;
  letter-spacing:1.8px;
  margin-left:5px;
  color:var(--muted);
  font-weight:500
}
nav {
  display:flex;
  align-items:center;
  gap:24px;
  margin:auto
}
nav button {
  height:76px;
  font-size:13px;
  color:var(--muted);
  position:relative;
  padding:0 2px
}
nav button.active {
  color:var(--text)
}
nav button.active:after {
  content:"";
  position:absolute;
  height:2px;
  bottom:0;
  left:0;
  right:0;
  background:var(--accent)
}
.count {
  margin-left:7px;
  font-size:10px;
  background:var(--tint);
  padding:2px 5px;
  border-radius:4px
}
.mode {
  display:flex;
  background:var(--soft);
  padding:3px;
  border-radius:6px;
  font-size:11px;
  white-space:nowrap
}
.mode button {
  padding:7px 10px;
  border-radius:4px;
  display:flex;
  align-items:center;
  gap:6px
}
.mode .selected {
  background:var(--surface);
  box-shadow:0 1px 4px #0001
}
.tiny-dot,.offline-dot {
  width:5px;
  height:5px;
  border-radius:50%;
  background:#608d7d;
  display:inline-block
}
.offline-dot {
  background:#a99571
}
.theme-toggle {
  display:grid;
  place-items:center;
  width:32px;
  height:32px;
  border:1px solid var(--line);
  border-radius:50%
}
main {
  flex:1;
  min-height:0;
  padding:20px
}
.hero {
  height:100%;
  display:grid;
  grid-template-columns:minmax(370px,38%) minmax(0,1fr);
  border:1px solid var(--line);
  background:var(--surface);
  border-radius:10px;
  overflow:hidden;
  box-shadow:0 8px 32px #152a4012
}
.workspace-panel {
  min-width:0;
  min-height:0;
  display:flex;
  flex-direction:column
}
.search-panel {
  padding:24px 26px 20px;
  border-bottom:1px solid var(--line);
  flex-shrink:0
}
.search-panel form>label {
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:1.4px;
  color:var(--muted);
  display:block;
  margin-bottom:10px
}
.address-field {
  display:flex;
  align-items:center;
  gap:10px;
  background:var(--surface);
  border:1px solid var(--line);
  border-radius:6px;
  padding:0 12px;
  min-height:46px;
  color:var(--accent)
}
.address-field:focus-within {
  border-color:var(--accent);
  box-shadow:0 0 0 2px var(--tint)
}
.address-field input {
  min-width:0;
  flex:1;
  width:100%;
  border:0;
  background:none;
  color:var(--text);
  font-size:13px;
  height:44px
}
.address-field button {
  display:grid;
  place-items:center;
  padding:5px
}
.example-row {
  display:flex;
  align-items:center;
  gap:10px;
  margin:11px 0 17px;
  font-size:10px;
  color:var(--muted);
  flex-wrap:wrap
}
.example-row>span {
  letter-spacing:1px;
  font-size:9px
}
.example-row button {
  font-size:11px;
  padding:0;
  border-bottom:1px solid transparent
}
.example-row button.current {
  color:var(--accent);
  border-color:var(--accent)
}
.radius-row {
  display:flex;
  align-items:center;
  justify-content:space-between;
  font-size:12px;
  color:var(--muted);
  margin-bottom:13px
}
.radius-control {
  display:flex;
  align-items:center;
  position:relative
}
.radius-control select {
  appearance:none;
  border:1px solid var(--line);
  border-radius:4px;
  background:var(--surface);
  color:var(--text);
  padding:6px 28px 6px 10px;
  font-size:12px
}
.radius-control svg {
  position:absolute;
  right:8px;
  pointer-events:none
}
.analyze {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  width:100%;
  background:#315e88;
  color:#fff;
  border-radius:5px;
  padding:12px 15px;
  font-size:13px;
  font-weight:550;
  min-height:42px
}
.analyze:hover {
  background:#254d72;
  color:#fff
}
.panel-content {
  min-height:0;
  flex:1;
  overflow:auto;
  overscroll-behavior:contain;
  scrollbar-width:thin;
  scrollbar-color:var(--line) transparent;
  padding:0 26px
}
.status-note {
  font-size:10px;
  line-height:1.6;
  color:var(--muted);
  display:flex;
  align-items:center;
  gap:6px;
  padding:12px 0
}
.status-note svg {
  flex-shrink:0
}
.report {
  padding:8px 0
}
.section-heading {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:7px 0 18px
}
.section-kicker {
  font-size:10px;
  letter-spacing:1.1px;
  color:var(--muted);
  text-transform:uppercase
}
.section-heading h2 {
  font-size:23px;
  letter-spacing:-.6px;
  margin:5px 0
}
.section-heading p {
  font-size:11px;
  line-height:1.5;
  color:var(--muted);
  max-width:230px
}
.outline-btn {
  display:flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  padding:9px 10px;
  border:1px solid var(--line);
  background:var(--surface);
  border-radius:5px;
  font-size:11px;
  color:var(--accent)
}
.section-heading>.outline-btn {
  max-width:115px;
  text-align:center;
  flex-shrink:0
}
.detail-title h3 {
  display:none
}
.distance-note {
  display:flex;
  align-items:center;
  gap:5px;
  color:var(--muted);
  font-size:10px;
  padding:0 0 8px
}
.distance-note svg {
  width:12px;
  height:12px
}
.place-groups details {
  border-bottom:1px solid var(--line)
}
summary {
  list-style:none;
  cursor:pointer;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:15px 0;
  font-size:13px
}
summary::-webkit-details-marker {
  display:none
}
summary>span {
  display:flex;
  align-items:center;
  gap:10px
}
summary>span:first-child svg {
  color:var(--accent);
  width:16px
}
summary>span:last-child {
  font-size:10px;
  color:var(--muted);
  white-space:nowrap
}
summary>span:last-child svg {
  transition:transform .2s
}
details[open] summary>span:last-child svg {
  transform:rotate(180deg)
}
.place-list {
  padding:0 0 9px
}
.place-row {
  display:flex;
  justify-content:space-between;
  gap:10px;
  padding:10px 0;
  font-size:12px;
  border-top:1px solid var(--soft)
}
.place-row>span:last-child {
  text-align:right;
  flex-shrink:0
}
.place-row small,table small {
  display:block;
  color:var(--muted);
  font-size:10px;
  margin-top:4px;
  line-height:1.5
}
.place-row strong {
  font-weight:550
}
.empty-small {
  font-size:12px;
  color:var(--muted);
  line-height:1.6;
  padding:8px 0 14px
}
.environment {
  display:flex;
  gap:20px;
  padding:18px 0;
  border-bottom:1px solid var(--line);
  font-size:11px;
  color:var(--muted)
}
.environment span {
  flex:1
}
.environment strong {
  display:block;
  font-size:12px;
  font-weight:500;
  color:var(--text);
  margin-top:5px
}
.source-line {
  font-size:10px;
  color:var(--muted);
  line-height:1.6;
  padding:14px 0 18px;
  display:flex;
  align-items:center;
  gap:8px;
  flex-wrap:wrap
}
.source-line>svg {
  display:none
}
.source-line button {
  font-size:10px;
  color:var(--accent);
  display:flex;
  gap:4px;
  align-items:center;
  padding:0
}
.commute {
  padding:8px 0
}
.commute h2 {
  font-size:24px;
  margin:7px 0
}
.commute p {
  font-size:12px;
  color:var(--muted);
  line-height:1.6
}
.commute-form {
  margin-top:22px
}
.commute-form>label {
  display:block;
  font-size:11px;
  color:var(--muted);
  margin-bottom:8px
}
.destination-chips {
  display:flex;
  flex-wrap:wrap;
  gap:7px;
  margin:12px 0
}
.destination-chips button {
  font-size:10px;
  border:1px solid var(--line);
  border-radius:4px;
  padding:7px 9px;
  text-align:left
}
.destination-chips button.chosen {
  background:var(--tint);
  border-color:var(--accent)
}
.commute-result {
  display:flex;
  align-items:start;
  justify-content:space-between;
  gap:8px;
  border-top:1px solid var(--line);
  padding:20px 0
}
.commute-result strong {
  font-size:28px;
  font-weight:550;
  letter-spacing:-1px
}
.commute-result span {
  display:block;
  font-size:11px;
  color:var(--muted);
  line-height:1.6;
  margin-top:6px
}
.commute-form>.outline-btn {
  margin:10px 0
}
.comparison {
  padding-top:8px
}
.empty-comparison {
  padding:25px 0
}
.empty-comparison h3,.empty-comparison h2 {
  font-size:20px;
  margin-bottom:10px
}
.empty-comparison p {
  font-size:12px;
  line-height:1.7;
  color:var(--muted)
}
.table-wrap {
  overflow:auto
}
table {
  border-collapse:collapse;
  width:100%;
  table-layout:fixed;
  font-size:11px;
  line-height:1.5
}
th,td {
  border-bottom:1px solid var(--line);
  padding:13px 9px;
  vertical-align:top;
  overflow-wrap:anywhere;
  text-align:left
}
th {
  position:relative;
  background:var(--soft);
  font-weight:550;
  padding-top:25px
}
th:first-child {
  font-weight:400
}
td:first-child {
  color:var(--muted)
}
td svg {
  display:none
}
.table-tag {
  display:block;
  font-size:9px;
  color:var(--muted);
  margin-bottom:7px
}
.remove-home {
  position:absolute;
  right:4px;
  top:4px
}
.comparison-note {
  font-size:11px;
  color:var(--muted);
  padding:15px 0;
  line-height:1.6
}
.matches {
  background:var(--soft);
  padding:4px;
  border-radius:5px;
  max-height:150px;
  overflow:auto;
  margin-top:6px
}
.matches button {
  display:flex;
  gap:6px;
  width:100%;
  text-align:left;
  font-size:12px;
  padding:10px;
  border-radius:3px;
  line-height:1.5
}
.matches button:hover {
  background:var(--surface)
}
.error {
  display:flex;
  align-items:start;
  gap:8px;
  background:var(--tint);
  padding:12px;
  font-size:12px;
  line-height:1.5;
  border-left:2px solid var(--accent);
  margin:8px 0
}
.error svg {
  flex-shrink:0
}
.error button {
  margin-left:auto;
  padding:0
}
.map-panel {
  position:relative;
  min-height:0;
  border-left:1px solid var(--line);
  background:var(--soft)
}
.map-canvas {
  position:absolute;
  inset:0;
  z-index:1
}
.map-title,.map-demo,.map-center,.map-hint {
  position:absolute;
  z-index:500;
  background:var(--surface);
  color:var(--text);
  box-shadow:0 2px 12px #152a4015;
  border:1px solid var(--line)
}
.map-title {
  top:20px;
  left:20px;
  display:flex;
  align-items:center;
  gap:8px;
  padding:10px 14px;
  border-radius:5px;
  font-size:12px
}
.map-demo {
  top:20px;
  right:20px;
  padding:10px 12px;
  border-radius:5px;
  font-size:10px;
  letter-spacing:.3px
}
.map-center {
  right:20px;
  top:70px;
  width:34px;
  height:34px;
  display:grid;
  place-items:center;
  border-radius:5px
}
.map-hint {
  bottom:90px;
  left:20px;
  padding:8px 11px;
  border-radius:4px;
  font-size:10px;
  color:var(--muted)
}
.category-bar {
  position:absolute;
  left:20px;
  bottom:30px;
  right:60px;
  z-index:500;
  display:flex;
  align-items:center;
  gap:8px
}
.filter-label {
  display:none
}
.filter-buttons {
  display:flex;
  gap:5px;
  flex-wrap:wrap
}
.filter-buttons button {
  display:flex;
  align-items:center;
  gap:6px;
  padding:9px 10px;
  border:1px solid var(--line);
  border-radius:4px;
  background:var(--surface);
  font-size:10px;
  color:var(--muted);
  box-shadow:0 2px 8px #0001
}
.filter-buttons button.on {
  background:var(--text);
  color:var(--surface);
  border-color:var(--text)
}
.filter-buttons svg {
  width:13px;
  height:13px
}
.filter-dot {
  display:none
}
.map-error {
  position:absolute;
  top:120px;
  left:20px;
  right:20px;
  z-index:501;
  background:var(--surface);
  color:var(--text);
  padding:12px;
  border:1px solid var(--line);
  font-size:12px;
  border-radius:5px
}
.leaflet-container {
  font-family:inherit;
  background:var(--soft)
}
.leaflet-control-attribution {
  font-size:9px!important;
  background:var(--surface)!important;
  color:var(--muted)!important
}
.leaflet-control-attribution a {
  color:var(--accent)!important
}
.leaflet-bar a {
  background:var(--surface)!important;
  color:var(--text)!important;
  border-color:var(--line)!important
}
.leaflet-popup-content-wrapper,.leaflet-popup-tip {
  background:var(--surface);
  color:var(--text)
}
.leaflet-popup-content {
  font-size:12px;
  line-height:1.6
}
.leaflet-popup-close-button {
  color:var(--muted)!important
}
.home-pin {
  background:#315e88;
  color:white;
  border:3px solid #fff;
  border-radius:50%;
  box-shadow:0 0 0 8px #315e8828,0 3px 10px #0003;
  text-align:center;
  line-height:32px;
  font-size:27px
}
.place-pin {
  background:var(--surface);
  border:1px solid var(--accent);
  border-radius:50%;
  color:var(--accent);
  line-height:26px;
  text-align:center;
  font-size:18px;
  box-shadow:0 2px 7px #0002
}
.place-pin.green {
  color:#578678
}
.destination-pin {
  font-size:26px;
  color:var(--accent)
}
[data-theme=dark] .leaflet-tile-pane {
  filter:invert(1) hue-rotate(180deg) brightness(.72) saturate(.55)
}
.modal-backdrop {
  position:fixed;
  inset:0;
  z-index:2000;
  background:#07121d99;
  backdrop-filter:blur(4px);
  display:flex;
  align-items:center;
  justify-content:center;
  padding:20px
}
.modal {
  background:var(--surface);
  color:var(--text);
  width:560px;
  max-width:100%;
  max-height:85dvh;
  overflow:auto;
  padding:32px;
  position:relative;
  border-radius:10px;
  border:1px solid var(--line)
}
.modal-close {
  position:absolute;
  right:15px;
  top:15px
}
.modal h2 {
  font-size:28px;
  letter-spacing:-.7px;
  margin:10px 0 22px
}
.modal h3 {
  font-size:14px;
  margin:18px 0 8px
}
.modal p {
  font-size:12px;
  color:var(--muted);
  line-height:1.8
}
.source-links {
  margin:20px 0
}
.source-links a {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  font-size:12px;
  color:var(--accent);
  padding:13px 0;
  border-bottom:1px solid var(--line)
}
.source-links svg {
  flex-shrink:0
}
.modal .analyze {
  margin-top:20px
}
.spin {
  animation:spin 1s linear infinite
}
@keyframes spin {
  to {
    transform:rotate(360deg)
  }
  
}

@media(min-width:1600px) {
  .hero {
    grid-template-columns:minmax(420px,34%) 1fr
  }
  .search-panel {
    padding:30px 34px
  }
  .panel-content {
    padding:0 34px
  }
  main {
    padding:24px 30px
  }
  
}
@media(max-width:1100px) {
  header {
    padding:0 20px;
    gap:15px
  }
  .brand-city {
    display:none
  }
  nav {
    gap:18px
  }
  .hero {
    grid-template-columns:minmax(350px,43%) 1fr
  }
  .filter-buttons button {
    padding:8px
  }
  .filter-buttons button svg {
    display:none
  }
  .map-hint {
    bottom:115px
  }
  
}
@media(max-width:760px) {
  #root {
    height:auto;
    min-height:100dvh;
    overflow:visible
  }
  header {
    height:auto;
    min-height:100px;
    flex-wrap:wrap;
    padding:15px 16px 0;
    gap:10px
  }
  .brand {
    font-size:20px;
    margin-right:auto
  }
  .mode {
    order:2
  }
  .theme-toggle {
    order:1
  }
  nav {
    order:3;
    width:100%;
    justify-content:space-between;
    gap:10px
  }
  nav button {
    height:40px;
    font-size:12px
  }
  main {
    padding:12px;
    flex:none
  }
  .hero {
    display:flex;
    flex-direction:column;
    height:auto;
    overflow:hidden
  }
  .workspace-panel {
    display:contents
  }
  .search-panel {
    order:0;
    padding:20px
  }
  .map-panel {
    order:1;
    min-height:360px;
    height:45dvh;
    max-height:500px;
    border-left:0;
    border-top:1px solid var(--line);
    border-bottom:1px solid var(--line)
  }
  .panel-content {
    order:2;
    overflow:visible;
    padding:0 20px
  }
  .map-title {
    left:12px;
    top:12px
  }
  .map-demo {
    right:12px;
    top:12px
  }
  .map-center {
    right:12px;
    top:60px
  }
  .category-bar {
    left:12px;
    right:48px;
    bottom:28px
  }
  .map-hint {
    left:12px;
    bottom:110px
  }
  .filter-buttons button {
    padding:8px;
    font-size:9px
  }
  .section-heading p {
    max-width:none
  }
  .modal {
    padding:28px 22px
  }
  .source-line {
    padding-bottom:20px
  }
  
}
@media(prefers-reduced-motion:reduce) {
  *,*:before,*:after {
    animation:none!important;
    transition:none!important
  }
  
}

.nearest {
  display:block;
  font-size:10px;
  font-weight:400;
  color:var(--muted);
  margin-top:4px
}
.report>.section-heading .section-kicker,.report>.section-heading p {
  display:none
}
.source-line {
  display:none
}
.report>.section-heading {
  padding:0 0 12px
}
.report>.section-heading h2 {
  font-size:20px
}
summary {
  padding:12px 0
}
.muted {
  color:var(--muted)
}
.home-pin {
  border-color:var(--surface)
}


/* Keep the overview compact at laptop viewport heights. */
.report > .section-heading h2 { margin: 0; }
.environment { padding: 14px 0; }

/* Two-stage workspace: address selection, then a compact map above analysis. */
.header-sources { margin-left:auto; font-size:12px; color:var(--muted); }
.hero { grid-template-columns:minmax(360px,40%) minmax(0,1fr); grid-template-rows: minmax(0,1fr) 0fr; transition:grid-template-rows .45s ease; }
.hero.is-start { grid-template-columns:minmax(330px,34%) minmax(0,1fr); }
.hero.is-expanded { grid-template-rows: minmax(245px,36%) minmax(0,1fr); }
.search-panel { grid-column:1; grid-row:1; min-height:0; border:0; display:flex; flex-direction:column; justify-content:center; padding:34px; overflow:auto; }
.is-start .search-panel { background:var(--tint); }
.is-expanded .search-panel { justify-content:flex-start; padding:20px 26px 12px; }
.search-panel form { width:100%; }
.search-panel .analyze { margin-top:0; }
.is-expanded .radius-row { position:absolute; top:21px; right:26px; margin:0; gap:8px; }
.is-expanded .radius-row>label { display:none; }
.is-expanded .search-panel { position:relative; }
.is-expanded .search-panel form>label { padding-right:80px; }
.is-expanded .radius-control select { padding-top:2px; padding-bottom:2px; }
.is-expanded .address-field { min-height:40px; }
.is-expanded .address-field input { height:38px; }
.is-expanded .example-row { margin:8px 0 10px; }
.is-expanded .analyze { min-height:34px; padding:8px 12px; font-size:12px; width:auto; align-self:flex-start; }
.back-to-search { position:absolute; top:155px; right:26px; font-size:10px; padding:5px 0; color:var(--muted); }
.is-expanded .back-to-search { top:133px; }
.map-panel { grid-column:2; grid-row:1; }
.category-bar { position:static; display:none; box-shadow:none; margin-top:12px; }
.is-expanded .category-bar { display:block; }
.filter-buttons { gap:5px; }
.filter-buttons button { font-size:10px; padding:5px 7px; box-shadow:none; }
.filter-buttons button svg { display:none; }
.status-note { padding:10px 0 0; font-size:10px; }
.is-expanded .status-note { padding-top:7px; }
.map-hint { bottom:22px; left:16px; }
.is-expanded .map-title,.is-expanded .map-demo { top:12px; }
.is-expanded .map-title { left:14px; padding:8px 11px; }
.is-expanded .map-demo { right:14px; padding:8px 10px; }
.is-expanded .map-center { top:54px; right:14px; }
.is-expanded .map-error { top:95px; padding:8px; font-size:11px; }
.panel-content { grid-column:1/-1; grid-row:2; display:grid; grid-template-columns:78px minmax(0,1fr); padding:0; border-top:1px solid var(--line); overflow:hidden; min-height:0; }
.panel-content nav { height:100%; min-height:0; margin:0; padding:20px 8px; display:flex; flex-direction:column; justify-content:flex-start; gap:12px; background:var(--soft); border-right:1px solid var(--line); }
.panel-content nav button { width:100%; height:54px; flex-shrink:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; padding:6px 0; border-radius:6px; font-size:10px; }
.panel-content nav button.active { background:var(--surface); color:var(--accent); }
.panel-content nav button.active:after { display:none; }
.panel-content nav button .count { position:absolute; top:3px; right:3px; margin:0; }
.panel-content nav button:last-child { margin-top:auto; }
.results-scroll { min-width:0; min-height:0; overflow:auto; padding:20px 26px; overscroll-behavior:contain; scrollbar-width:thin; scrollbar-color:var(--line) transparent; }
.report { padding:0; }
.report>.section-heading { padding:0 0 17px; }
.report>.section-heading h2 { font-size:21px; }
.section-heading>.outline-btn { max-width:none; }
.report-detail { display:grid; grid-template-columns:220px minmax(0,1fr); gap:26px; }
.category-list { border-right:1px solid var(--line); padding-right:20px; }
.category-list>button { display:flex; align-items:center; gap:10px; width:100%; padding:10px 12px; text-align:left; border-radius:5px; font-size:12px; margin-bottom:3px; }
.category-list>button[aria-pressed=true] { background:var(--tint); color:var(--accent); }
.category-list>button span { flex:1; }
.category-list>button small { display:block; margin-top:4px; font-size:10px; color:var(--muted); }
.category-list>button>svg:last-child { transform:rotate(-90deg); }
.environment { display:flex; gap:12px; border:0; border-top:1px solid var(--line); margin-top:14px; padding:14px 4px 0; font-size:10px; }
.environment strong { font-size:11px; }
.category-detail { min-width:0; }
.detail-heading { display:flex; justify-content:space-between; align-items:center; gap:15px; margin-bottom:16px; }
.detail-heading h3 { font-size:20px; font-weight:550; margin-top:5px; }
.detail-heading .distance-note { padding:0; text-align:right; }
.places-and-detail { display:grid; grid-template-columns:minmax(210px,1fr) minmax(210px,1fr); gap:24px; }
.place-list { min-width:0; }
.place-list .place-row { width:100%; text-align:left; padding:14px 12px; border-radius:4px; border-top:0; border-bottom:1px solid var(--line); }
.place-list .place-row.chosen { background:var(--soft); }
.place-inspector { border-left:1px solid var(--line); padding:18px 24px; display:flex; flex-direction:column; align-items:flex-start; gap:12px; }
.place-inspector>svg { color:var(--accent); margin-bottom:4px; }
.place-inspector h3 { font-size:20px; line-height:1.3; font-weight:550; }
.place-inspector>strong { font-size:30px; font-weight:500; letter-spacing:-1px; margin-top:10px; }
.place-inspector p,.place-inspector small { font-size:11px; color:var(--muted); line-height:1.5; }
.place-inspector p { margin-top:-6px; }
.place-inspector small { margin-top:8px; }
.commute { max-width:820px; display:grid; grid-template-columns:1fr 1.3fr; gap:40px; padding-top:6px; }
.commute-form { margin-top:0; }
.comparison { max-width:1100px; padding-top:0; }
.comparison .section-heading h2 { font-size:23px; }
.comparison table { font-size:12px; }
.error { margin-bottom:0; flex-shrink:0; }
@media (min-width:1600px) { .hero,.hero.is-start { grid-template-columns:minmax(400px,36%) 1fr; } }
@media (max-width:1100px) and (min-width:761px) {
 .hero,.hero.is-start { grid-template-columns:minmax(330px,40%) 1fr; }
 .search-panel { padding:24px; }
 .is-expanded .search-panel { padding:18px 20px 8px; }
 .is-expanded .radius-row { right:20px; top:18px; }
 .is-expanded .back-to-search { right:20px; }
 .filter-buttons button { font-size:9px; padding:5px; }
 .report-detail { grid-template-columns:180px minmax(0,1fr); gap:18px; }
 .category-list { padding-right:12px; }
 .places-and-detail { grid-template-columns:1fr; gap:10px; }
 .place-inspector { border-left:0; border-top:1px solid var(--line); padding:18px 12px; }
 .detail-heading { align-items:flex-start; }
 .detail-heading .distance-note { max-width:140px; }
}
@media(max-width:760px) {
 .hero,.hero.is-expanded,.hero.is-start { display:flex; height:auto; flex-direction:column; }
 .search-panel,.is-expanded .search-panel { order:0; padding:22px 20px; overflow:visible; }
 .is-expanded .radius-row { top:22px; right:20px; }
 .is-start .search-panel { min-height:260px; }
 .map-panel { order:1; min-height:300px; height:42dvh; }
 .is-expanded .map-panel { min-height:230px; height:30dvh; }
 .panel-content { order:2; display:flex; flex-direction:column; overflow:visible; }
 .panel-content nav { order:0; flex-direction:row; width:100%; height:auto; padding:7px 12px; gap:6px; border-right:0; border-bottom:1px solid var(--line); justify-content:space-between; }
 .panel-content nav button { width:auto; min-width:58px; height:48px; flex:1; }
 .panel-content nav button:last-child { margin-top:0; }
 .results-scroll { padding:20px 16px; overflow:visible; }
 .report-detail { display:flex; flex-direction:column; gap:20px; }
 .category-list { border:0; padding:0; display:flex; flex-wrap:wrap; gap:5px; }
 .category-list>button { width:auto; flex:1 0 30%; padding:10px 8px; font-size:11px; background:var(--soft); }
 .category-list>button>svg:last-child { display:none; }
 .category-list .environment { width:100%; flex-basis:100%; margin-top:5px; padding-top:12px; }
 .detail-heading { gap:10px; }
 .detail-heading .distance-note { max-width:130px; }
 .places-and-detail { grid-template-columns:1fr; }
 .place-inspector { border-left:0; border-top:1px solid var(--line); padding:20px 12px; }
 .commute { display:block; }
 .commute-form { margin-top:20px; }
 .header-sources { font-size:10px; margin-left:0; }
 .is-expanded .back-to-search { right:20px; top:135px; }
 .is-expanded .category-bar { margin-top:14px; }
}
```

## src/Map.tsx

```tsx
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Location, Place, Category } from "./types";
function popupText(text: string) {
  const el = document.createElement("div");
  el.textContent = text;
  return el;
}
export const symbols: Record<Category, string> = {
  transport: "↔",
  grocery: "▤",
  pharmacy: "+",
  green: "♧",
  parking: "P",
};
export default function NeighborhoodMap({
  location,
  places,
  radius,
  filters,
  onPick,
  destination,
  centerTick,
}: {
  location: Location;
  places: Place[];
  radius: number;
  filters: Category[];
  onPick: (p: Location) => void;
  destination: Location | null;
  centerTick: number;
}) {
  const root = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    layer = useRef<L.LayerGroup | null>(null),
    pick = useRef(onPick);
  const [tileError, setTileError] = useState(false);
  pick.current = onPick;
  useEffect(() => {
    if (!root.current) return;
    const m = L.map(root.current, {
      zoomControl: false,
      scrollWheelZoom: false,
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
    layer.current = L.layerGroup().addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) =>
      pick.current({
        latitude: e.latlng.lat,
        longitude: e.latlng.lng,
        label: `Map location · ${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`,
      }),
    );
    const resize = new ResizeObserver(() => m.invalidateSize());
    resize.observe(root.current);
    return () => {
      resize.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current,
      g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    m.setView([location.latitude, location.longitude], radius > 1100 ? 13 : 14);
    L.circle([location.latitude, location.longitude], {
      radius,
      color: "#2867d9",
      weight: 1,
      dashArray: "5 6",
      fillColor: "#85baff",
      fillOpacity: 0.12,
    }).addTo(g);
    L.marker([location.latitude, location.longitude], {
      icon: L.divIcon({
        className: "home-pin",
        html: "<span>⌂</span>",
        iconSize: [42, 42],
        iconAnchor: [21, 21],
      }),
    })
      .addTo(g)
      .bindPopup(popupText(location.label));
    places
      .filter((p) => filters.includes(p.category))
      .forEach((p) => {
        L.marker([p.latitude, p.longitude], {
          icon: L.divIcon({
            className: `place-pin ${p.category}`,
            html: `<span>${symbols[p.category]}</span>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
          }),
        })
          .addTo(g)
          .bindPopup(popupText(p.label));
      });
    if (destination) {
      L.marker([destination.latitude, destination.longitude], {
        icon: L.divIcon({
          className: "destination-pin",
          html: "<span>⚑</span>",
          iconSize: [32, 32],
        }),
      })
        .addTo(g)
        .bindPopup(popupText(destination.label));
      L.polyline(
        [
          [location.latitude, location.longitude],
          [destination.latitude, destination.longitude],
        ],
        { color: "#805a9a", weight: 2, dashArray: "5 7" },
      ).addTo(g);
      m.fitBounds(
        [
          [location.latitude, location.longitude],
          [destination.latitude, destination.longitude],
        ],
        { padding: [45, 45] },
      );
    }
  }, [location, places, radius, filters, destination, centerTick]);
  return (
    <>
      <div
        ref={root}
        className="map-canvas"
        aria-label="Interactive Warsaw map. Click to select a home location."
      />
      {tileError && (
        <div className="map-error">
          Map tiles unavailable. Pins still work; check your connection.
        </div>
      )}
      <div className="map-hint">Or pick a spot on the map</div>
    </>
  );
}
```

## src/types.ts

```ts
export type Category =
  | "transport"
  | "grocery"
  | "pharmacy"
  | "green"
  | "parking";
export interface Location {
  latitude: number;
  longitude: number;
  label: string;
}
export interface Place extends Location {
  id: string;
  category: Category;
  distance_m?: number;
  distance_type?: "straight_line" | "walking";
  lines?: string[];
}
export interface Analysis {
  location: Location;
  radius_m?: number;
  places: Place[];
  unavailable: Category[];
  sources: { name: string; url?: string; retrieved_at?: string }[];
  retrieved_at?: string;
  commute?: {
    distance_m?: number;
    duration_minutes?: number;
    mode?: string;
    status?: string;
  };
  demo: boolean;
}
export interface AnalyzeRequest {
  latitude: number;
  longitude: number;
  radius_m: number;
  destination: Location | null;
}
```

## src/api.ts

```ts
import type {
  Analysis,
  AnalyzeRequest,
  Location,
  Place,
  Category,
} from "./types";
import { inWarsaw } from "./geo";
const env =
  (import.meta as ImportMeta & { env: Record<string, string> }).env || {};
export const API_BASE_URL = env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";
export async function analyze(
  request: AnalyzeRequest,
  signal?: AbortSignal,
): Promise<Analysis> {
  if (!API_BASE_URL)
    throw new Error(
      "Live analysis is not connected yet. Add VITE_API_BASE_URL and rebuild, or explore Demo mode.",
    );
  const r = await fetch(`${API_BASE_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: signal || AbortSignal.timeout(20000),
  });
  if (!r.ok)
    throw new Error(
      `Analysis unavailable (HTTP ${r.status}). Please try again.`,
    );
  return adaptAnalysis(await r.json(), request);
}
const categories: Category[] = [
  "transport",
  "grocery",
  "pharmacy",
  "green",
  "parking",
];
// Adapt the team's final response contract here; preserve unavailable data explicitly.
export function adaptAnalysis(raw: any, request: AnalyzeRequest): Analysis {
  if (!raw || typeof raw !== "object")
    throw new Error("The backend returned an invalid analysis.");
  const grouped: Record<Category, string> = {
    transport: "stops",
    grocery: "shops",
    pharmacy: "pharmacies",
    green: "parks",
    parking: "parking",
  };
  const supplied = Array.isArray(raw.places);
  const unavailable: Category[] = [];
  const places: Place[] = [];
  for (const category of categories) {
    const key = grouped[category];
    const list = supplied
      ? raw.places.filter((p: any) => p.category === category)
      : (raw[key] ?? raw[`nearby_${key}`]);
    if (!Array.isArray(list)) {
      unavailable.push(category);
      continue;
    }
    for (const [i, p] of list.entries()) {
      const latitude = Number(p.latitude ?? p.lat),
        longitude = Number(p.longitude ?? p.lon);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
      places.push({
        id: String(p.id ?? `${category}-${i}`),
        category,
        label: String(p.label ?? p.name ?? "Unnamed location"),
        latitude,
        longitude,
        distance_m:
          typeof p.distance_m === "number" && p.distance_m >= 0
            ? p.distance_m
            : undefined,
        distance_type:
          p.distance_type === "walking"
            ? "walking"
            : p.distance_type === "straight_line"
              ? "straight_line"
              : undefined,
        lines: Array.isArray(p.lines) ? p.lines.map(String) : undefined,
      });
    }
  }
  return {
    location: { ...request, label: raw.location?.label || "Selected location" },
    places,
    unavailable: [
      ...new Set([
        ...unavailable,
        ...(Array.isArray(raw.unavailable)
          ? raw.unavailable.filter((x: Category) => categories.includes(x))
          : []),
      ]),
    ],
    sources: Array.isArray(raw.sources)
      ? raw.sources.filter((s: any) => typeof s.name === "string")
      : [],
    retrieved_at:
      typeof raw.retrieved_at === "string" ? raw.retrieved_at : undefined,
    commute: raw.commute,
    demo: false,
  };
}
let lastSearch = 0;
const cache = new Map<string, Location[]>();
export async function geocode(query: string): Promise<Location[]> {
  const q = query.trim();
  if (q.length < 3) throw new Error("Enter a street and building number.");
  const cached = cache.get(q.toLowerCase());
  if (cached) return cached;
  if (Date.now() - lastSearch < 1100)
    throw new Error("Please wait a moment before searching again.");
  lastSearch = Date.now();
  const u = new URL(
    env.VITE_GEOCODER_URL || "https://nominatim.openstreetmap.org/search",
  );
  u.search = new URLSearchParams({
    q: `${q}, Warsaw, Poland`,
    format: "jsonv2",
    limit: "5",
    countrycodes: "pl",
    viewbox: "20.75,52.39,21.28,52.09",
    bounded: "1",
  }).toString();
  const r = await fetch(u, {
    signal: AbortSignal.timeout(12000),
    referrerPolicy: "strict-origin-when-cross-origin",
  });
  if (!r.ok)
    throw new Error("Address search unavailable. Select a point on the map.");
  const raw = await r.json();
  const points = raw
    .map((p: any) => ({
      label: String(p.display_name),
      latitude: Number(p.lat),
      longitude: Number(p.lon),
    }))
    .filter(inWarsaw);
  cache.set(q.toLowerCase(), points);
  return points;
}
```

## src/demo.ts

```ts
import type { Analysis, Location, Place, Category } from "./types";
import { distance } from "./geo";
export const homes: Location[] = [
  { label: "Marszałkowska 83, Warsaw", latitude: 52.2252, longitude: 21.0131 },
  { label: "Puławska 24, Warsaw", latitude: 52.2064, longitude: 21.0225 },
  { label: "Ząbkowska 12, Warsaw", latitude: 52.2544, longitude: 21.0385 },
];
export const destinations: Location[] = [
  { label: "University of Warsaw", latitude: 52.2403, longitude: 21.0186 },
  {
    label: "Warsaw University of Technology",
    latitude: 52.2201,
    longitude: 21.0105,
  },
  { label: "Warsaw Central Station", latitude: 52.2286, longitude: 21.0031 },
];
export function demoAnalysis(location: Location, radius: number): Analysis {
  const items: [Category, string, number, number][] = [
    ["transport", "Example tram stop", 0.001, 0.001],
    ["transport", "Example bus stop", -0.002, 0.002],
    ["transport", "Example metro entrance", 0.004, -0.002],
    ["grocery", "Example neighborhood grocery", -0.0008, -0.0012],
    ["grocery", "Example supermarket", 0.003, 0.004],
    ["grocery", "Example convenience store", -0.003, -0.003],
    ["pharmacy", "Example local pharmacy", 0.0004, 0.0028],
    ["green", "Example pocket park", -0.0025, 0.005],
    ["green", "Example garden entrance", 0.005, -0.005],
  ];
  const places: Place[] = items
    .map(([category, label, y, x], i) => {
      const p = {
        id: `demo-${i}`,
        category,
        label,
        latitude: location.latitude + y,
        longitude: location.longitude + x,
        distance_type: "straight_line" as const,
      };
      return { ...p, distance_m: distance(location, p) };
    })
    .filter((p) => p.distance_m <= radius);
  return {
    location,
    places,
    unavailable: ["parking"],
    sources: [
      { name: "Illustrative fixture — not verified city data" },
      {
        name: "OpenStreetMap (base map only)",
        url: "https://www.openstreetmap.org/copyright",
      },
    ],
    demo: true,
  };
}
```

## src/geo.ts

```ts
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
```

## tests/analysis.test.mjs

```javascript
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { build } from "esbuild";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
const dir = await mkdtemp(join(tmpdir(), "urbanlens-tests-"));
const output = join(dir, "model.mjs");
await build({
  stdin: {
    contents:
      "export * from './src/api'; export * from './src/geo'; export * from './src/demo';",
    resolveDir: process.cwd(),
  },
  bundle: true,
  platform: "node",
  format: "esm",
  outfile: output,
  define: { "import.meta.env": "{}" },
});
const { distance, inWarsaw, adaptAnalysis, demoAnalysis, analyze, homes } =
  await import(pathToFileURL(output));

test("distance is zero at origin and symmetric", () => {
  assert.equal(distance(homes[0], homes[0]), 0);
  assert.equal(distance(homes[0], homes[1]), distance(homes[1], homes[0]));
  assert.ok(distance(homes[0], homes[1]) > 2000);
});
test("Warsaw bounds reject invalid coordinates", () => {
  assert.ok(inWarsaw(homes[0]));
  assert.equal(inWarsaw({ latitude: 0, longitude: 0 }), false);
  assert.equal(inWarsaw({ latitude: NaN, longitude: 21 }), false);
});
test("demo is explicit, radius constrained, no parking claims", () => {
  const r = demoAnalysis(homes[0], 200);
  assert.equal(r.demo, true);
  assert.ok(r.places.length > 0);
  assert.ok(
    r.places.every(
      (p) => p.distance_m <= 200 && p.distance_type === "straight_line",
    ),
  );
  assert.deepEqual(r.unavailable, ["parking"]);
  assert.equal(r.retrieved_at, undefined);
});
const req = { ...homes[0], radius_m: 1000, destination: null };
test("missing groups stay unavailable; empty group is different", () => {
  const a = adaptAnalysis({ stops: [] }, req);
  assert.equal(a.unavailable.includes("transport"), false);
  assert.equal(a.unavailable.includes("parking"), true);
  assert.equal(a.places.length, 0);
});
test("adapter drops invalid coordinates and does not invent distance types", () => {
  const a = adaptAnalysis(
    {
      shops: [
        { name: "Shop", lat: 52.22, lon: 21.01, distance_m: 150 },
        { name: "Bad coordinates" },
      ],
    },
    req,
  );
  assert.equal(a.places.length, 1);
  assert.equal(a.places[0].distance_type, undefined);
  assert.equal(a.demo, false);
});
test("live without backend fails explicitly", async () => {
  await assert.rejects(analyze(req), /not connected/);
});
after(async () => {
  await rm(dir, { recursive: true, force: true });
});
```

