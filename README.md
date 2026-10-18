# OLO — eksplorator okolic Warszawy

Wybór miejsca do życia w Warszawie wymaga złożenia dojazdu, przystanków, parków, parkingów i obiektów sportowych z osobnych źródeł. OLO bierze adres albo punkt na mapie i zwraca wstępny Mobility Score (0–100): odległość w linii prostej do najbliższego przystanku oraz zagęszczenie grup przystanków z `data/stops_clean.csv`. Do wyniku dochodzą pobliskie parki, parkingi z wykazu i szkolne obiekty sportowe z lokalnych migawek, częściowy LifeScore z wagami użytkownika oraz porównanie dwóch adresów.

## Co dzieje się w czasie działania

Frontend (`frontend/src/api.ts`, baza `VITE_API_BASE_URL`) woła tylko własne API FastAPI:

- `POST /api/score` i `POST /api/score/address` — wynik i miejsca
- `GET /api/geocode` — cel w zakładce dojazd
- `POST /api/commute` — trasy na żądanie
- `POST /api/compare` — dwa domy
- `GET /api/health`

Kafelki mapy idą z `https://tile.openstreetmap.org` w `frontend/src/Map.tsx`. Scoring czyta pliki lokalne.

### Adresy

Jedno zewnętrzne zapytanie o adres jest w `backend/services/geocoding_service.py`. Gdy lokalny indeks nie znajdzie budynku, `GET` idzie do Nominatim (`GEOCODING_URL`, domyślnie `https://nominatim.openstreetmap.org/search`), wyłącznie po jawnym wyszukaniu i z odstępem co najmniej 1,1 s.

### Trasy

Trasy piesze i samochodowe liczy `backend/services/routing_service.py` w FOSSGIS OSRM (`ROUTING_BASE_URL`, domyślnie `https://routing.openstreetmap.de`, osobno `routed-foot` i `routed-car`) dla `/api/commute` oraz dla `/api/compare` z `include_routes`. Komunikacja zbiorowa zostaje oznaczona jako niedostępna, bo nie ma podłączonego rozkładu.

## Skąd biorą się dane

API danych Warszawy (`WARSAW_API_TOKEN`) działa przy ręcznym odświeżaniu migawek w `data_science/`.

| Skrypt | Zapytanie | Co pobiera |
| --- | --- | --- |
| `ingest_stop_lines.py`, `complete_lines.py` | `POST` `https://dane.um.warszawa.pl/api/action/get_ztm_lista_linii_na_przystanku` | linie ZTM na przystanku |
| `ingest_infrastructure.py` | `POST` `get_m_parkingi_wolne_miejsca` | wolne miejsca parkingowe |
| `ingest_infrastructure.py` | `GET` WFS `https://wfs.um.warszawa.pl/serwis` | parki |
| `ingest_sports.py` | `POST` `get_be_otwarte_boiska` | otwarte boiska |
| `ingest_sports.py` | ten sam WFS | punkty adresowe |
| `ingest_addresses.py` | ten sam WFS | granice dzielnic i adresy |

Sklepy i apteki pochodzą z lokalnej migawki OSM składanej przez `data_science/ingest_osm_retail.py`.

Po MVP można zastąpić odległość w linii prostej czasem przejazdu i częstotliwością kursów, dociągnąć linie ZTM na całe miasto (obecny cache linii to mała próbka), podłączyć planowanie podróży komunikacją miejską, dodać osobne oceny zieleni, parkowania, sportu i dojazdu przy pełniejszym pokryciu, pokazywać aktualną liczbę wolnych miejsc parkingowych, objąć obiekty sportowe poza boiskami szkolnymi oraz wynieść cache geokodowania i tras poza pamięć jednego workera.
