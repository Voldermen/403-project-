# Transportation Aggregator — Django backend

This is the **integrated** backend for the group's transportation-aggregator website. It contains the Google Flights, Amtrak, and Greyhound Python modules, a Django website and JSON endpoints, price-comparison helpers, and saved searches. This version also includes the **Amtrak schedule display fix** and automatically loads `DJANGO_SECRET_KEY` from a local `.env` file.

> **Who this is for:** group members using Windows, PowerShell in VS Code, and Python 3.12. The same Django code can run on a properly configured local server.

## 1. Files and responsibilities

| File/folder | What it does |
| --- | --- |
| `manage.py` | Starts Django and runs Django management commands |
| `requirements.txt` | Installs the packages needed by the backend and both data-processing libraries |
| `.env` (you create locally) | Stores your PRIVATE Django secret key and local settings; **not uploaded to GitHub** |
| `.env.example` | Safe template your teammates can copy |
| `aggregator_site/settings.py` | Loads `.env` using `python-dotenv`; configures sessions and SQLite |
| `google_flights_scraper.py` | Searches flights using an unofficial third-party library |
| `Amtrak_Data.py` and `routes/amtrak_adapter.py` | Searches Amtrak's GTFS **timetables**, not fares |
| `greyhound_search.py` and `routes/greyhound_adapter.py` | Retrieves Greyhound-branded options via an undocumented endpoint |
| `routes/services.py` | Calls providers, validates route matching, combines results |
| `routes/algorithms.py` | Compares fares and travel times |
| `routes/views.py` | Handles requests, saves inputs/results in sessions, returns JSON |
| `routes/templates/routes/home.html` | Test webpage, including the updated Amtrak departure/arrival display |
| `db.sqlite3` (created on first use) | Stores Django sessions and saved searches; **do not commit** |

**The server teammate** hosts Django and the frontend. **The frontend teammate** sends HTTP requests to Django. Scraper developers own their provider modules; the backend exposes them through a common JSON format.

## 2. One-time setup on each developer's computer

Open the folder containing `manage.py` in VS Code. Open **Terminal → New Terminal**. Confirm your Python version:

```powershell
python --version
```

Python 3.12 is the team's tested target. If `python` is not recognized, install/configure Python before continuing. The following commands work in **PowerShell**, not just CMD.

**Option A — fastest setup (existing Python environment):**

```powershell
python -m pip install -r requirements.txt
```

**Option B — recommended isolated project environment:**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For Option B, replace `python` with `.\.venv\Scripts\python.exe` in subsequent commands. This avoids PowerShell execution-policy issues with activating virtual environments. Do **not** commit `.venv`.

`requirements.txt` includes **Django, python-dotenv, fast-flights, airportsdata, typing_extensions, gtfs-kit, and pandas**. Greyhound's Python module uses the standard library and needs no extra package.

## 3. Set up Django's secret key (important)

**A secret key is not a Google/Amtrak/Greyhound API key.** Django uses it for cryptographic signing and security-sensitive features such as signed session data. It **does not encrypt your saved JSON or IP addresses**. A key is **not generated or saved to `.env` automatically**.

### 3A. Generate a private key

Run this command in your project folder:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the printed value **privately**. Do not paste it in GitHub issues, group messages, screenshots, or chat. You only need to generate it once for your local setup.

### 3B. Make `.env` next to `manage.py`

Copy `.env.example` to `.env` in VS Code, or run:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholder with the key you generated:

```dotenv
DJANGO_SECRET_KEY='PASTE_YOUR_REAL_GENERATED_KEY_HERE'
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_SECURE_COOKIES=0
```

**Why single quotes?** Your key may contain `$`. In a PowerShell command, double-quoted strings can expand `$variables`. Keeping the key in the quoted `.env` value avoids retyping it in the shell. `python-dotenv` reads the literal value. A Django-generated key is suitable to place in this quoted format. This `.env` file is private and is excluded by `.gitignore`.

### 3C. Understand how Django reads it

This project already has the following code in `aggregator_site/settings.py`; you **do not need to add it again**:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is missing. See README.md.")
```

The real settings file has a more detailed error message. The order matters: `BASE_DIR`, then `load_dotenv()`, then `SECRET_KEY`. Django reads the key automatically at startup; your scrapers do **not** need it.

**If you used a PowerShell variable earlier:** Existing shell environment variables take precedence over `.env` values by default. To clear an old test value in the current PowerShell terminal, run:

```powershell
Remove-Item Env:DJANGO_SECRET_KEY -ErrorAction SilentlyContinue
```

Then run Django normally; it will load `.env`. To set the variable *manually* instead, the correct PowerShell syntax is `$env:DJANGO_SECRET_KEY = 'your-real-key'`, using **single quotes**, but that only lasts for that terminal session. Don't use CMD's `set "DJANGO_SECRET_KEY=..."` in PowerShell.

If the terminal shows `>>`, press **Ctrl+C**. It usually means a quote or bracket was not closed. Avoid printing your real secret while debugging.

### 3D. Different developers vs the hosted server

Each backend developer can generate **their own development key**. The frontend doesn't need any key. **Your server teammate generates one different, stable hosted key** and stores it securely on the server, outside Git. Don't rotate it on every restart: existing signed sessions may be invalidated.

## 4. Create database and run

Run from the project folder (the one containing `manage.py`):

```powershell
python manage.py migrate
python manage.py check
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in a browser on the same computer. Leave the terminal running; stop with **Ctrl+C**. On subsequent runs, you normally only need `python manage.py runserver`.

Run tests (mocked providers — they don't make live booking requests):

```powershell
python manage.py test
```

The `migrate` command creates the SQLite session tables required to restore previously completed searches. Do not delete `db.sqlite3` if you want to preserve saved session data. The session survives server restart, provided you preserve the database and stable secret key.

## 5. Test the transportation sources

Start at the homepage. Example trip (**choose a future date**, not the date shown in older screenshots):

| Form item | Example |
| --- | --- |
| Airport from | `MSY` (New Orleans) |
| Airport to | `ORD` (Chicago O'Hare) |
| Travel date | A valid future date, `YYYY-MM-DD` |
| Travelers | `1` |
| Also search Amtrak | Check the box |
| Amtrak from / to | `NOL` / `CHI` |

**Google Flights:** Returns up to the configured limit of flights, sorted by price. Every flight keeps `"Priority": 1` because **Air** is the team's travel-mode priority 1; priority is **not** the flight's price rank. Flight fares come from the unofficial library and may omit options or differ from Google's current website.

**Amtrak:** Fetches official GTFS schedule data using a cached ZIP file in `data_cache/` (cached around 24 hours). Look for *Rail* in the results. Train departure time, arrival time, date, and duration appear even in **Other retrieved schedules (not compared)**. GTFS does **not** supply current fares, bookings, live train delays, or seat availability, so `"Cost": null` is intentional. The current module mainly supports direct trips and can skip overnight cases.

**Greyhound:** Requires *city UUIDs*, not IATA airport codes. The sample UUIDs in the form are **Dallas → Houston**; only compare that trip to Dallas → Houston flights, e.g. `DFW` → `IAH`, not New Orleans → Chicago. Current Greyhound support is **one adult**, may not have verified station GPS, and uses an unofficial endpoint subject to change.

The comparison algorithm only compares modes whose **origin and destination city names match**. Provider schedules for other city pairs appear separately rather than being mixed into the recommendations. Missing fares do not participate in the cheapest-price recommendation. A provider failure should not stop the other providers.

## 6. Frontend API for your teammate

The existing endpoints are:

| Method / URL | Purpose |
| --- | --- |
| `GET /` | Website and restored last search |
| `GET /api/search/` | Combined matching routes, unmatched routes, recommendations, provider status |
| `GET /api/flights/` | Original flight JSON array, without combined wrapper |
| `GET /api/saved/` | Draft, most recent saved search and short history; use `?index=1` for second-most-recent |
| `POST /api/draft/` | Save an unfinished form draft (CSRF protection applies) |
| `POST /api/clear/` | Clear this browser's saved session data (CSRF protection applies) |
| `POST /clear-saved/` | Clear saved data and redirect to homepage |

Example of a combined GET request (replace date with a future date):

```text
http://127.0.0.1:8000/api/search/?origin=MSY&destination=ORD&travel_date=2026-11-16&adults=1&include_train=on&train_origin=NOL&train_destination=CHI
```

The resulting JSON contains `routes`, `unmatched_routes`, `recommendations`, and `providers`. Each individual route uses the team's `{"Method": {...}}` format with a `"Staring Location"` field (spelling preserved for compatibility). `/api/flights/` returns a JSON **array** of those flight objects. The displayed fares are not guaranteed to be booking totals.

To add buses to the combined request, provide `include_bus=on`, `bus_origin=<city-uuid>`, and `bus_destination=<city-uuid>`.

The frontend should call Django, **not** call the scrapers directly from browser JavaScript. If the frontend is served under the same origin, `fetch('/api/saved/', {credentials: 'same-origin'})` preserves session cookies. POST endpoints need valid CSRF tokens. If building React on a different port, use a development proxy and discuss cookie/CSRF settings with the backend teammate — do not disable CSRF globally.

## 7. Saved searches and IP addresses

- Completed searches and their **generated JSON results** are saved in SQLite via **Django database-backed sessions**. The last **three** are retained; reopening the homepage or using `/api/saved/` restores them without scraping again.
- Draft form fields are saved in browser `localStorage` and sent to the session via `/api/draft/` while the user types.
- The browser holds a random session cookie, not all the result data. Data is associated with the browser session, **not by IP address**. The app records the direct connecting IP only for diagnostics; it cannot identify a returning user reliably.
- Sessions last up to about **30 days since last saved activity**, depending on cookies and server maintenance. Restoring requires the same browser profile and hostname with the cookie intact; another device or deleted cookies will not restore the same session.
- Saved fares and schedules are a snapshot. To refresh prices, submit a new search.
- The website's *Clear my saved searches* button removes saved server-side results and local draft data.

### Privacy / hosting

Stored JSON is not encrypted by Django's `SECRET_KEY`. Restrict database access, avoid logging secrets and personal data, and provide users with a clear way to delete saved searches. Keep regular backups if needed; delete expired sessions with `python manage.py clearsessions`.

## 8. GitHub — what to push and what not to push

**Commit:** Django code, frontend files, scraper modules, `.gitignore`, `requirements.txt`, `README.md`, and `.env.example`.

**Do not commit:** `.env`, real keys, `db.sqlite3` (saved user session data), `.venv`, `data_cache`, or logs.

Before pushing:

```powershell
git status
git add .
git status
git commit -m "Document Django setup and secret-key configuration"
git push
```

**Review the staged files before committing.** If `.env` or `db.sqlite3` was already tracked, `.gitignore` alone will not untrack it. For already tracked files only, use `git rm --cached .env` and/or `git rm --cached db.sqlite3` to stop tracking while keeping local copies. If a real secret was committed previously, replace/rotate it; removing the file now does not erase older Git history.

Each teammate clones the repository, runs `python -m pip install -r requirements.txt`, creates their **own** `.env`, runs `python manage.py migrate`, then starts Django. No one needs to exchange their development secret keys.

## 9. Local-network server handoff

The hosting teammate should install dependencies on the hosting computer and create that computer's **own stable private key**. For local network testing in PowerShell (replace with the actual server LAN IP):

```powershell
$env:DJANGO_ALLOWED_HOSTS = '127.0.0.1,localhost,192.168.1.50'
python manage.py runserver 0.0.0.0:8000
```

Other computers on the same LAN visit `http://192.168.1.50:8000/`. Their firewalls must permit the connection. **The IP is an example.** `localhost` only refers to each person's own computer.

Django's `runserver` is **development-only**, not a production host. Before hosting outside a trusted local network, use an appropriate production WSGI/ASGI server, HTTPS, `DJANGO_DEBUG=0`, `DJANGO_SECURE_COOKIES=1`, explicit `DJANGO_ALLOWED_HOSTS`, a stable secret, static-file serving, database backups, and request rate limits. If you change hosts to HTTPS, plan a proper proxy and CSRF setup. `python manage.py check --deploy` highlights security items to review; it is not itself a full audit.

## 10. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `KeyError: 'DJANGO_SECRET_KEY'` or `DJANGO_SECRET_KEY is missing` | Create `.env` **beside `manage.py`**, use the exact variable name, check `python-dotenv` is installed, and verify `load_dotenv` runs before reading `SECRET_KEY` |
| PowerShell shows `>>` | Press Ctrl+C; there is likely an unmatched quote/bracket. Use the `.env` method instead of pasting keys into PowerShell |
| `$` occurs in the key | In PowerShell use **single quotes** (`$env:DJANGO_SECRET_KEY = '...'`); single-quoted `.env` value also works |
| `ModuleNotFoundError: dotenv` | Run `python -m pip install -r requirements.txt` using the same Python interpreter that runs Django |
| `ModuleNotFoundError: django` | Install `requirements.txt`; verify you are in the correct Python/virtual environment |
| `No module named typing_extensions` | Install/update requirements; `typing_extensions` is listed |
| `no such table: django_session` | Run `python manage.py migrate` |
| Port 8000 in use | Use `python manage.py runserver 8001`, then browse `http://127.0.0.1:8001/` |
| Amtrak schedule has no price | Expected: GTFS is timetable data, not ticket fares |
| Train displays under other schedules | Its origin/destination city labels did not exactly match the flight city pair; the page still displays its times |
| Greyhound fails for 2+ adults | Current uploaded Greyhound client supports one adult only |
| Search returns no live results | Provider may have no routes, changed its response, blocked scraping, or have an incomplete feed; review provider status |
| Saved search doesn't reappear | Same browser, same hostname, intact cookie, same database, and stable server key are needed |

**Important:** Live Google Flights, Amtrak, and Greyhound results were not verified in the build environment. API integration depends on the external providers remaining accessible and returning the expected structures.
