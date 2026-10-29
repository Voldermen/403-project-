# RouteWise — Integrated Django transportation backend

This project extends your earlier Django prototype. It connects the **three supplied Python modules**: Google Flights, Amtrak_Data.py, and greyhound_search.py. It saves completed JSON and unsubmitted form inputs so a returning browser can resume after a disconnection.

run python -m pip install -r requirements.txt in terminal
BEFORE SETUP PLEASE REFER TO SECTION 3 TO MAKE A SECRET KEY!
## Setup for Windows 10/11 (Python 3.12)

In CMD, open the folder containing `manage.py`, then run:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```
after you do all of those commands the next time you use cmd do:
$env:DJANGO_SECRET_KEY = 'insert key here'
python manage.py runserver

Visit `http://127.0.0.1:8000/` on the same PC.

**Important: `python manage.py migrate` is mandatory.** It creates the `django_session` SQLite table where Django stores browser sessions and saved search JSON. The `db.sqlite3` file is created on the hosting machine; don't delete it if you want to keep saved results.

## How sources work

- **Google Flights** (`google_flights_scraper.py`): original flight JSON with `Priority=1`, sorted by fare. The scraper may omit available prices or return stale ones.
- **Amtrak** (`Amtrak_Data.py`, `routes/amtrak_adapter.py`): downloads Amtrak's published GTFS **timetable** to `data_cache/amtrak_gtfs.zip` (24-hour local cache). `Cost` is `null` because GTFS does not contain live fares, availability, or bookability. Its module may fail when the upstream GTFS feed or stop identifiers don't match. The adapter sets rail mode `Priority=2`. It downloads the official GTFS ZIP before asking `gtfs-kit` to read a local path. It uses the teammate's original direct-only itinerary search, which does not build transfers and may exclude valid overnight results.
- **Greyhound** (`greyhound_search.py`, `routes/greyhound_adapter.py`): uses the teammate's unofficial FlixBus/Greyhound JSON endpoint. **One adult only** in this version, because the supplied code requests one adult. Enter *city UUIDs* rather than station or airport codes. The prefilled IDs are **Dallas → Houston only**. Bus mode `Priority=99` preserves the teammate's stated default. Station coordinates are `null` unless verified values become available (important for geographic route algorithms).

The website asks for airport codes plus optional train station codes or bus city UUIDs. Only results with **the same origin and destination city names** as the flight search enter the main list and comparison algorithm. Mismatched provider results are shown separately under `unmatched_routes` to avoid comparing Dallas → Houston bus trips against New Orleans → Chicago flights. Alias and metropolitan differences may exclude otherwise valid matches until the group adds a validated city mapping. Missing prices appear last; Amtrak never participates in priced recommendations.

## Saved sessions / returning visitors

- When a user types, JavaScript saves the form immediately in browser `localStorage` and also sends a debounced POST to `/api/draft/` to store a server-side draft.
- When a user runs a successful search, Django saves **the latest three completed searches** (inputs, JSON, provider statuses, comparison output, timestamp) in the **SQLite-backed Django session**. Reopening `/` restores the last result without calling external providers.
- Django associates the server data with a random **HttpOnly session cookie**, kept for up to **30 days from its last write**. Same browser/profile, same hostname, cookies retained are required. IP address **is not the visitor ID**: shared and changing IPs cannot safely restore data. The direct peer IP (`REMOTE_ADDR`) is stored *only as diagnostic metadata* on saved searches; never displayed or used to retrieve records. Behind a reverse proxy this may be the proxy address. Don't trust X-Forwarded-For without configuring trusted proxies.
- The button **Clear my saved searches** removes the server session and this website's local draft. Once the cookie is deleted or expires, data cannot be restored. For cross-device recovery, add user accounts or an explicit recovery code.
- Saved values are historical; restarting a browser does **not** update fares. The user must search again.

## API endpoints (for the frontend teammate)

**GET** `/api/search/?origin=MSY&destination=ORD&travel_date=2026-11-16&adults=1&include_train=on&train_origin=NOL&train_destination=CHI`

Response includes:

```json
{
  "routes": [],
  "unmatched_routes": [],
  "recommendations": {},
  "providers": {"flights": {}, "trains": {}, "buses": {}}
}
```

(Empty arrays are structural examples; live results depend on providers.)

To search buses, add `include_bus=on`, `bus_origin=<city-uuid>`, and `bus_destination=<city-uuid>`; you'll typically need DFW/IAH as flight airports when testing the prefilled Dallas/Houston bus route, and the same geographic city names.

**GET** `/api/flights/?origin=MSY&destination=ORD&travel_date=2026-11-16&adults=1` — flight array, preserving your original `[{"Method": {...}}]` shape. Each search also saves state.

**GET** `/api/saved/` (or `/api/saved/?index=1` for the second-most-recent result) — return the current session's draft, most recent search JSON, and the three search timestamps/inputs; it does **not** rerun scrapers. Use `credentials: 'same-origin'` in JS fetch requests when hosted under the same origin.

**POST** `/api/draft/` — form-encoded fields (and CSRF token) to save unfinished input.

**POST** `/api/clear/` — delete session data and create a fresh session on the next request (requires CSRF token). HTML POST `/clear-saved/` clears and redirects to `/`.

For frontend on a separate origin/port, coordinate a reverse proxy and CSRF/CORS/cookie settings with the server teammate. Avoid turning off CSRF checks.

## Server handoff / data management

On the hosting machine, keep **one shared** database (`db.sqlite3`) and a stable `DJANGO_SECRET_KEY` across deployments. Make periodic backups of the DB if saved results matter. `python manage.py clearsessions` can remove expired session rows; schedule regular cleanup. Configure HTTPS and `DJANGO_SECURE_COOKIES=1` plus `DJANGO_DEBUG=0` on a production deployment. Never expose Django's development server publicly. Use rate limits, caching, API timeouts and terms-of-service review before production. No account authentication is included; each browser session is isolated.

## Run tests

```cmd
python manage.py test
```

These tests mock external provider network calls; **no live external scraping was verified** in this build. For real integration, test each provider on the local server with working internet access.

`requirements.txt` includes **Django, python-dotenv, fast-flights, airportsdata, typing_extensions, gtfs-kit, and pandas**. Greyhound's Python module uses the standard library and needs no extra package.

## 3 Set up Django's secret key (important)

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