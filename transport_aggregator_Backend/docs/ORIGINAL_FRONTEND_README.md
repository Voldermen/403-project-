# Group 3 — Travel Aggregator (CSC 4033 Sprint 2)

Django backend + HTML/CSS/vanilla JavaScript frontend, built from the provided **UI Notes.pdf**, using the team's original `Test_logo.png` and Python scripts.

## What you get

- **Home** (`/`): clickable logo, HOME and ABOUT navigation, six filter controls, Address A and Address B with address autocomplete, a **Find My Route** button, and an interactive U.S. map.
- **About** (`/about/`): the specified Group 3 project description and **Plan Your Route** button.
- **Results** (`/results/`): direct route alternatives ranked by **lowest reported fare** or **travel duration**, plus a map and provider notices. Missing fares are marked **unavailable**, never free.
- **API** (`/api/addresses/?q=Dallas`): a small JSON endpoint providing U.S. address suggestions.
- **Travel modes**: an **All Types** control and five independent filter toggles. Gray = excluded; enabled = considered for search. All Types turns all five on or off.
- **Future sprint**: the right-hand travel inspiration sidebar is an illustrated placeholder for the proposed carousel because no destination/transport photos were included.

## Quick start: Ubuntu / Linux / Windows

Python **3.11+** is recommended (and a version of Django compatible with your Python).

```bash
# Go to the folder that contains manage.py
cd TravelAggregator_Django

# Create / activate a virtual environment (Linux/macOS):
python3 -m venv .venv
source .venv/bin/activate

# On Windows instead: py -m venv .venv && .venv\Scripts\activate

python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Visit **http://127.0.0.1:8000/**. To check the app:

```bash
python manage.py check
python manage.py test
```

> Note: this project was source-checked, but Django runtime tests could not be run in the build environment because Django was not installed and network package downloads were unavailable. Run the commands above after installing requirements.

## Configuring provider integrations

The team's scripts are preserved **unchanged** in `legacy/` and accessed through `planner/services.py`. Original command-line test scripts are not executed automatically.

| Mode | Implementation | Additional setup / limitations |
|---|---|---|
| Car | OSRM HTTP routing | Development default `https://router.project-osrm.org/route/v1/driving` (public demo, **not production infrastructure**); override `OSRM_ROUTE_URL` with an authorized routing server. Produces distance/estimated drive time, **no price**. |
| Planes | `legacy/google_flights_scraper.py` | `pip install -r requirements-optional.txt`. The closest scheduled airport within 150 mi is selected from supplied `cleaned_airport.csv`. Live Google Flights scraping is brittle and may fail; live fares may change. |
| Trains | `legacy/Amtrak_Data.py` | `requirements-optional.txt`. Only a limited hardcoded list of station codes is supported within 110 mi. Live Amtrak GTFS can be slow and provides **schedules, not ticket prices**. |
| Public Buses | `legacy/transit_route.py` | Set **both** `TRANSIT_API_KEY` and `TRANSITLAND_API_KEY` environment variables. Only bus-only itineraries are displayed. Nearby-stop lookup is limited. |
| Greyhound | `legacy/greyhound_search.py` | The original script only provides the **Dallas ↔ Houston** city identifiers. Other cities need a city-ID lookup to be implemented. It uses an **undocumented** endpoint, which can change or become unavailable. |

The existing `legacy/least_cost_path.py` is retained for integration in a later sprint. It currently expects an absent `examples.json` file, assumes numeric fares and compatible timetable data, and does not safely support these live mixed-provider results. The website therefore ranks **direct alternatives**, not combined multi-leg paths or guaranteed globally optimal trips. Do not claim to offer finished end-to-end multimodal route optimization yet.

### Address autocomplete

The frontend waits for 3 typed characters and debounces requests by 500ms. The backend calls Photon and caches suggestions; users can also submit typed addresses without selecting a suggestion. Address and location services require internet access.

The public **Photon** instance and **OSM tile server** are for prototyping at low traffic; replace them with permitted providers or self-hosted services before production. Respect providers' quotas, attribution and terms. Requests for a large user base should add rate limiting and monitoring. A browser without internet will not display the map tiles, though the page remains navigable.

The search inputs also support direct coordinates like `32.77, -96.79` for development. Coordinates supplied by the browser are validated as geographic values but are **not independently verified** against the entered address.

## Environment variables

Copy `.env.example` to `.env` and edit it. Django **does not auto-load `.env` files**. For development on Linux, load it into your shell:

```bash
set -a
. ./.env
set +a
python manage.py runserver
```

Do not store `.env` in Git. The default debug settings are for a local prototype ONLY.

## Self-hosting on your personal Ubuntu server

1. Install Python and dependencies, create a dedicated unprivileged `travelapp` user, and clone/copy this project to `/srv/travel-aggregator`.
2. Make a strong `DJANGO_SECRET_KEY`; set `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS=yourdomain.example`, `DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.example`. When behind a *trusted* Nginx proxy that overwrites forwarded headers, set `DJANGO_TRUST_PROXY=1`.
3. For PostgreSQL, set `DB_ENGINE=postgresql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` and install `psycopg[binary]`. SQLite remains the default for the sprint demo.
4. Run `python manage.py migrate` and `python manage.py collectstatic --noinput`.
5. Use **Gunicorn** as the WSGI application server (`pip install gunicorn`) behind Nginx. Do not use Django's `runserver` as a production server.
6. Configure **Nginx** to serve `/static/` directly from `staticfiles/` and forward application requests to a Gunicorn Unix socket or `127.0.0.1:8000`. Use HTTPS certificates, or use Cloudflare Tunnel with a properly configured HTTPS origin/proxy.
7. Enable firewall rules, secure SSH, create scheduled database backups, keep the server patched, and follow `python manage.py check --deploy`. Only expose HTTPS through your chosen tunnel/reverse proxy.

Example Gunicorn command after activating the virtual environment:

```bash
gunicorn --workers 2 --bind 127.0.0.1:8000 config.wsgi:application
```

> A personal server is not always reachable from the internet without a public address, port forwarding, or a tunnel. Handle DNS, TLS, network firewalls, and ISP restrictions separately.

## Folder guide

```text
TravelAggregator_Django/
├── config/                         Django settings + URLs + WSGI/ASGI
├── planner/
│   ├── forms.py                     Input validation and mode choices
│   ├── services.py                  Geocoding, provider adapters, normalization, ranking
│   ├── views.py                     Home, About, Results, address suggestions
│   ├── urls.py
│   ├── templates/planner/          HTML pages
│   ├── static/planner/             CSS, browser JavaScript, original logo
│   └── tests/                      Django unit tests
├── legacy/                         Original supplied transportation scripts / airport CSV
├── docs/UI Notes.pdf               Original requirements
├── requirements.txt
├── requirements-optional.txt
├── .env.example
├── manage.py
└── README.md
```

### Constraints and next sprint

- Results are *not* bookings, guaranteed fares, real-time traffic data, or multi-leg itineraries.
- Public transit's legacy date handling starts at 9 AM local for the selected date; adding departure time and proper time-zone handling should be a future task.
- The provided logo's text is still a placeholder; update `Test_logo.png` when the final brand image is ready.
- Destination images and image-carousel behavior can be implemented when those assets are provided.
- Consider adding a route search model, more station/city identifiers, caching of live provider queries, background task workers, authentication, and a tested production deployment configuration.
