# Group 3 Travel Aggregator — connected frontend + backend

This project integrates your teammate's **TravelAggregator_Django frontend** with the **transportation Django backend you previously developed**. **The existing frontend HTML/CSS/design is retained** (with a small Travelers field and subtle saved-search links), and the **original backend provider functions, JSON format, priorities, comparison logic, and API views are preserved**.

## Quick start — Windows / VS Code / PowerShell (Python 3.12)

1. Extract the ZIP into your team's local Git repository. Open the folder **containing `manage.py`** in VS Code or PowerShell.
2. (Recommended) Create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activating the environment, you can use `\.venv\Scripts\python.exe` instead of `python` in the commands below, or choose CMD and run `.venv\Scripts\activate.bat`. You do **not** need a virtual environment to run it, but it helps avoid conflicts.

3. Install all dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Generate a **private Django secret key**:

   ```powershell
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

5. Copy `.env.example` to `.env` and replace the placeholder with the generated key. Example:

   ```dotenv
   DJANGO_SECRET_KEY='PASTE_YOUR_PRIVATE_GENERATED_KEY_HERE'
   DJANGO_DEBUG=1
   DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
   ```

   **Do not upload `.env` or copy its secret to GitHub.** The code loads `.env` automatically using `python-dotenv`, even if your key contains `$`. You do **not** have to reenter `$env:DJANGO_SECRET_KEY` each time the terminal opens. Environment variables already defined in the terminal take precedence over `.env`; if you previously set an old key, use a fresh terminal to avoid confusion.

6. Create database tables and run the website:

   ```powershell
   python manage.py migrate
   python manage.py runserver
   ```

7. Visit <http://127.0.0.1:8000/>. Use **Car, Planes, Trains, Public Buses, or Greyhound** toggles and the address/date/travelers fields. An internet connection is needed for live providers, map tiles, and autocomplete.

### Run tests

```powershell
python manage.py check
python manage.py test
```

Provider calls are mocked in the automated integration tests; you don't need to pay for fares to run tests. You *will* need working third-party providers for a live search.

## What changed (and what did not)

- **Preserved:** all original HTML templates, CSS styling, logo, Leaflet map, autocomplete, route cards, About page, car (OSRM) and public bus integrations; the teammate's `legacy/` scripts remain as reference.
- **Preserved:** the backend files `routes/` (views, services, algorithms, adapters, tests), and its root `google_flights_scraper.py`, `Amtrak_Data.py`, and `greyhound_search.py`. The backend's original APIs remain mapped to their old paths.
- **Connected:** `planner/services.py` calls the original backend Google Flights function and Amtrak/Greyhound adapters **instead of duplicating those scrapers via `legacy/`**. Greyhound city names now resolve automatically through `planner/greyhound_cities.py` for supported U.S. cities. The frontend still sorts route cards by the user's choice of cost or travel time, independently of the backend's raw JSON.
- **Small UI changes:** added a Travelers field (1–9), a link to reopen a saved search, and a link to view stored provider JSON. The frontend's primary look and layout were left intact.
- **Saved state:** completed searches, displayed results, and original provider JSON are saved in Django's **database-backed browser sessions**. When visitors return with the same browser cookie, `/results/` restores the last results without repeating external requests. Browser `localStorage` also saves an unfinished form draft.
- **Privacy:** a user's IP address is **not** used as an account identifier. This avoids exposing one user's saved searches to other users sharing an IP. The original backend can still record connection IP information internally for diagnostics. Users may clear their saved data using the results page action. Session lifetime is 30 days from the most recent save, subject to cookie availability.

## Routes and what each handles

| URL | What it does |
| --- | --- |
| `/` | Teammate's original styled home page with form and map |
| `/about/` | Original About page |
| `/results/` | Styled frontend results; submitting a search saves state; opening it later without query parameters restores that state |
| `/api/addresses/?q=New%20Orleans` | Frontend address autocomplete (Photon) |
| `/api/planner/saved-results/` | Saved **raw provider Method JSON array** for the last search made from the styled frontend; no new scraper call |
| `/planner/clear-saved/` | POST only; clears session-based saved data |
| `/api/search/` | **Unchanged backend** combined transportation JSON API; requires airport codes and optional Amtrak/Greyhound IDs |
| `/api/flights/` | **Unchanged backend** raw Google Flights JSON array API |
| `/api/saved/` | **Unchanged backend** saved state from searches made through its own API or backend test page |
| `/api/draft/` | **Unchanged backend** draft-saving API (POST with CSRF token) |
| `/api/clear/` | **Unchanged backend** session-clearing API (POST) |
| `/backend/` | Original backend's own testing search webpage, separate from styled frontend |

`/api/saved/` and `/api/planner/saved-results/` intentionally reflect **different interfaces**: the former is the original backend's saved API workflow; the latter is the styled frontend's provider JSON download. The browser uses the same Django session for both, but the record structures are different.

## How the frontend talks to your backend

The two projects are **one Django site**, so the frontend's server-side `planner.services` imports functions directly from the original backend rather than calling localhost on a second port:

```text
Browser submits /results/ with address/date/mode selections
  └─ planner.views.results()
      ├─ Photon geocodes addresses (or accepts valid selected coordinates)
      └─ planner.services.search_routes()
          ├─ car → OSRM (unchanged frontend functionality)
          ├─ planes → google_flights_scraper.search_flights(...) (existing backend)
          ├─ trains → routes.amtrak_adapter.search_amtrak(...) (existing backend)
          ├─ greyhound → routes.greyhound_adapter.search_greyhound(...) (existing backend)
          └─ public_buses → legacy.transit_route (unchanged frontend functionality)
      └─ saves displayed routes, inputs, and raw backend JSON to Django session
```

**Airport codes and station identifiers are not interchangeable.** The styled frontend still finds an airport or station near each submitted address (150 miles for airports, 110 miles for stations), so the route may start at a nearby hub rather than directly at the typed street address. Surface the route provider's station/airport names to the user when planning travel.

The backend's raw flight priority stays **1 for every flight**, and its own `search_flights` continues returning up to five of the retrieved results sorted by fare. Amtrak priority stays 2 with **unknown fares** (`null`); its GTFS feed provides schedules but not live fare quotes. The Greyhound adapter uses its own priority and supports **one adult**. The styled frontend now automatically resolves supported U.S. city names to provider UUIDs using an unofficial FlixBus city-autocomplete endpoint, instead of being limited to Dallas ↔ Houston. The original Greyhound backend remains unchanged and still requires UUIDs for direct API use. Greyhound may return missing station GPS. Don't compare bus itineraries from unrelated city pairs with flights.

The source websites are unofficial/unstable integrations; flight fares can differ from the public website, and a failed source may show a provider notice rather than results.

## Folder layout

```text
TravelAggregator_Integrated/
├── .env.example                 # Safe placeholder for secret; copy to private .env
├── .gitignore                   # Ignores .env, SQLite and temporary files
├── manage.py
├── requirements.txt
├── config/                      # Main Django project and shared settings/URL routing
├── planner/                     # Styled frontend, bridge, and greyhound_cities.py resolver
├── routes/                      # Original backend views/JSON API/adapters/algorithms (unchanged)
├── google_flights_scraper.py    # Original flight code (unchanged)
├── Amtrak_Data.py               # Original rail code (unchanged)
├── greyhound_search.py          # Original bus code (unchanged)
├── legacy/                      # Teammate's original reference scripts (unchanged)
└── docs/                        # Original frontend/backend READMEs + UI Notes.pdf
```

## Integrating with your group's GitHub branches

1. Create an integration branch in GitHub Desktop (for example `frontend-backend-integration`).
2. Copy this project's files into the **local checkout** of the team's repository (do not overwrite any newer teammate changes without reviewing the differences).
3. Do **not** copy `.env` or `db.sqlite3`. The ZIP intentionally excludes those files; each developer creates their own `.env` and database migrations.
4. Review GitHub Desktop's Changes tab. Commit the source files, `.gitignore`, `.env.example`, `README.md`, and `requirements.txt` only after checking for credentials.
5. Publish/push the branch and open a pull request for your teammates to review. The frontend developer should review `planner/` and the server developer should review `config/settings.py`, deployment, and secrets.

## Running on your teammate's local hosting computer

For **LAN testing only**, from the project directory run:

```powershell
# Example: update .env with the hosting PC's actual address, not the example below.
# DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,192.168.1.50
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Other machines on that LAN visit `http://<hosting-computer-IP>:8000/`. The host firewall must permit traffic. **Django's development server is not suitable for a public production website.** For public hosting, disable debug, use HTTPS, a production WSGI server and static-file handling, set a private stable key, and run `python manage.py check --deploy`. The frontend's old `config/settings.py` already contains additional optional PostgreSQL and reverse-proxy configuration.

## Known limits and troubleshooting

- `KeyError: DJANGO_SECRET_KEY` / `RuntimeError: Missing DJANGO_SECRET_KEY`: create `.env` **beside** `manage.py`, then use a fresh terminal; no need to set a shell variable manually.
- `ModuleNotFoundError`: run `python -m pip install -r requirements.txt` in the same Python environment that runs Django.
- `no such table: django_session`: run `python manage.py migrate`.
- `Invalid HTTP_HOST header`: add the correct host/IP to `DJANGO_ALLOWED_HOSTS` in `.env`.
- The address autocomplete/map tiles require internet and rely on public low-traffic prototype services.
- The exact routes and prices returned by external scrapers are **not guaranteed**. Provider failures are shown separately in the results.
- To use the original backend's `/api/search/`, provide its expected airport, station code and city UUID parameters (see `docs/ORIGINAL_BACKEND_README.md`); it is **not** the same request shape as the styled page's address-based `/results/` URL.

### Validation performed for this package

Python source compilation and integrity comparisons against the supplied original backend files succeeded. The added integration tests are designed to check the unchanged backend API, provider wiring, and session restoration with mock data. **Full Django tests and live external-service retrieval could not be executed in the artifact environment because Django and the scraper dependencies could not be installed there.** Run `python manage.py check` and `python manage.py test` after installing dependencies on your computer.

## Greyhound on the styled frontend

The **Greyhound** checkbox is on the main page alongside Car, Planes, Trains and Public Buses. Selecting it sends the **same address, destination and date** through the existing search form. The frontend now:

1. Extracts each city from the entered or selected U.S. address.
2. Looks up the city's Greyhound/FlixBus UUID using the unofficial autocomplete endpoint. Dallas/Houston keep the original known city IDs for reliable local tests.
3. Calls `routes.greyhound_adapter.search_greyhound(...)` (the original backend adapter, unchanged).
4. Shows a Greyhound result card for returned fares, terminal names, departure and arrival times, and duration. These options are included in the frontend's cheapest/fastest sorting.
5. Saves the original backend `Method` JSON alongside displayed results in the same Django session as the other modes.

**Example to try:** Enter **Dallas, TX** and **Houston, TX**, a future date, select **Greyhound**, and set **Travelers = 1**. The backend's original one-adult limit still applies, and unsupported routes give a notice rather than fabricated fares. An internet connection is required for city autocomplete and the live provider. The search uses an **undocumented endpoint**, which may become unavailable or change. City matching requires a nearby provider city coordinate to prevent selecting a similarly named city far away.

**Map limitations:** The map shows the entered route endpoints (and a road route if Car is selected); it does not show a verified Greyhound bus path. Your teammate's Greyhound data often omits bus-station coordinates, so we display station names but do not invent GPS values. The prices are the source's returned one-adult fares; the UI does not assume two-traveler totals.

**Tests:** `python manage.py test planner.tests.test_integration.GreyhoundCityLookupTests`. These tests mock the provider and test city lookup, sorting hand-off, fallback behavior and passenger limits. Live API availability is not tested in this package.
