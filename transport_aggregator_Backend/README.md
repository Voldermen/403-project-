# Group 3 Transportation Aggregator — algorithm integrated

This ZIP contains the original Django `planner` frontend, a minimal web/API
adapter, and the teammate's **unchanged** `Algorithm/` directory.

**Important:** There is no backend route-finding, airport selection, sorting,
fare calculation, or separate provider scraping. A browser search and
`/api/search/` both call `main_alg()` from `Algorithm/main_alg.py`. That
algorithm also fetches data from its *own* scrapers. The frontend converts
the resulting data **for presentation only** without changing its ranking.

## Included location datasets

All three required station/airport CSV files are included:

- `data/airports_database/cleaned_airport.csv` — the airport file from the
  original backend, copied unchanged.
- `data/amtrack_database/cleaned_amtrack.csv` — generated from the Amtrak
  GTFS `stops.txt` data previously supplied with the original backend.
  **amtrack** is intentionally spelled this way because the supplied algorithm
  references that exact directory name.
- `data/greyhound_database/cleaned_greyhound.csv` — the user's supplied
  cleaned Greyhound CSV (1,031 station rows), copied without modification.

The supplied algorithm expects airport columns `name`, `latitude_deg`,
`longitude_deg`, `icao_code`, `iata_code`, `gps_code`, `local_code`. Train and
Greyhound datasets require `stop_id`, `stop_lat`, and `stop_lon`. The backend
checks that these files exist before launching the algorithm.

## Windows (PowerShell)

From the directory with `manage.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit `.env` and paste the generated key into `DJANGO_SECRET_KEY` (single
quotes recommended). Keep `.env` out of Git. Then:

```powershell
python manage.py migrate
python manage.py runserver
```

## Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Edit .env with the secret from the previous command, then:
chmod 600 .env
python manage.py migrate
python manage.py runserver
```

Use a proper production web server, DEBUG=0, configured allowed hosts,
HTTPS, and static-file serving when deploying. `python manage.py runserver`
is only for development. A long-running live algorithm may require adjusting
`ALGORITHM_TIMEOUT_SECONDS` and your deployment worker's timeout.

## How the integration works

1. `/` retains the team's original visual frontend.
2. The user enters full US street addresses including city, state and ZIP,
   a date, optional earliest start time, chooses travel modes, and selects
   cost / shortest duration / earliest arrival.
3. `planner.views.results()` validates the form and invokes
   `planner.algorithm_bridge.run_main_algorithm()`.
4. That bridge starts an **isolated Python subprocess** which imports the
   supplied `main_alg` module and calls its `main_alg(add1, add2, date, ...)`
   **once**. All pathfinding and provider calls stay inside `Algorithm/`.
   Isolation is necessary because the unmodified algorithm uses relative
   `../data/` paths, unqualified imports and fixed debug JSON output names.
   Temporary workspaces avoid conflicts across simultaneous requests.
5. `planner.algorithm_bridge.present_algorithm_routes()` renders the
   algorithm's `routes` in their **original rank order** and exposes every
   returned itinerary leg. It does **not** sort or recompute routes.
6. Browser-session storage retains the most recent full raw algorithm JSON
   and displayed search. The saved JSON link works without running the
   algorithm again. `Clear saved search` removes this browser's session.
7. `/api/search/` returns the algorithm JSON **unmodified in structure**.

## Exact input mapping

| Frontend option | Value passed to `main_alg` |
| --- | --- |
| From / To | Original entered address text (`add1`, `add2`) |
| Travel date | Python `date` |
| Lowest cost | `objective='cost'` |
| Shortest duration | `objective='duration'` |
| Earliest arrival | `objective='arrival'` |
| Earliest start time | `start_time='8:00 am'`, or `'12:01 am'` |
| Unchecked planes | Add `'plane'` to `exclude` |
| Unchecked trains | Add `'train'` to `exclude` |
| Unchecked Greyhound | Add `'bus'` to `exclude` |
| Number of options | `num_paths=3` |

Public buses are no longer listed separately. The supplied algorithm only
exposes **plane, train and bus (Greyhound)** as filterable modes; it also
inserts walking transfers itself. The algorithm's README says walking may
later become rideshare; it has **not** been changed. The algorithm's
provider wrappers support **one traveler**, so the UI now requires one.
We did not patch the algorithm to change that limitation.

## API

- `GET /api/search/?origin=...&destination=...&travel_date=YYYY-MM-DD&modes=planes&modes=trains`
  invokes `main_alg()` and returns the raw output. Omit `modes` to use all
  three. Optional: `objective=cost|time|arrival`, `start_time=08:00`.
- `GET /api/planner/saved-results/` returns full JSON from latest web/API call.
- `GET /api/saved/` returns up to three API search records in this session.
- `POST /api/draft/` saves draft data. `POST /api/clear/` clears history.
- `GET /api/flights/` returns **410 Gone**, because a separate direct flight
  scraper would violate the request to use only `main_alg()`; use
  `/api/search/?modes=planes` instead.
- `/backend/` redirects to `/`; the old duplicate search UI was removed.

## Notes and current limitations

- The provided algorithm files are copied without edits. Their behavior,
  errors, scraper dependencies, fare choices, walking connections and route
  ranking are solely under the algorithm teammate's control.
- **Known issue in the supplied algorithm (left unchanged):**
  `Algorithm/aggregator.py` calls `search_amtrak_gtfs(origin, dest, date)`
  with three arguments, but `Algorithm/Amtrack_Scraper/Amtrak_Data.py`
  declares a fourth required argument, `adult_passengers`. The algorithm's
  `collect_all_info` catches and suppresses that exception, so train legs
  may be missing. This must be corrected by the algorithm teammate; the
  Django backend does not override it.
- The algorithm's address parsing/geocoding (US Census) requires complete
  addresses. Frontend address autocomplete is a convenience only; it does
  not bypass or replace the algorithm geocoder.
- Searches may take time and depend on network services. Configure your
  Django/Gunicorn timeouts accordingly.
- Provider outages or issues inside the supplied algorithm may cause it
  to return zero routes. Do not mistake the included JSON examples for live
  searches; no silent sample-data fallback has been added.
- The only backend conversion of routes is display formatting (date labels,
  leg names and map endpoint markers); the ranking and leg details come
  from the original output.

## Offline tests

`python manage.py test planner`

These tests mock the `main_alg()` subprocess boundary. They do not issue
live provider requests.

## Source preservation check

All 27 original files in the uploaded `Algorithm(1).zip` are present
**byte-for-byte unchanged** in `Algorithm/`, including its README and sample
JSON files. The backend runs a temporary **copy** of these files, so live
requests do not overwrite the original algorithm's debug JSON samples.
