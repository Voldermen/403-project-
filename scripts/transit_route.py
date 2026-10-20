"""
transit_route.py

Importable function that finds public transit options between two positions using
the Transit API and returns them in your Example.json format (Priority 3).

Usage from another file:

    from transit_route import get_transit_options
    import json

    options = get_transit_options(
        origin={"street": "201 Mayfield Avenue", "city": "Ruston", "state": "LA"},
        destination={"street": "500 Poydras Street", "zip_code": "70130"},
    )
    print(json.dumps(options, indent=2))

    # Coordinates work too:
    options = get_transit_options((32.5232, -92.6379), (29.9511, -90.0715))

Setup:
    pip install requests
    Create api_keys.txt in the same folder as this file, containing:
        transit = YOUR_API_KEY
    (Add api_keys.txt to .gitignore so it stays out of your repo.)
    You can also pass api_key=... directly, or set the TRANSIT_API_KEY env var.

    For get_nearest_stops_transitland (larger search radius), add a second line:
        transitland = YOUR_TRANSITLAND_KEY
    (or set the TRANSITLAND_API_KEY env var, or pass api_key=...)

API usage: one request per call (the trip planner finds the nearby boarding and
alighting stops itself), so each call to get_transit_options costs 1 API call.
"""

import os
import time
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

import requests

from address_coords import get_lat_long

BASE_URL = "https://external.transitapp.com"
PLAN_PATH = "/v3/otp/plan"   # OTP-style planner; override with plan_path=... if needed
PRIORITY = 3
TIMEOUT = 30
TRANSITLAND_STOPS_URL = "https://transit.land/api/v2/rest/stops"
TRANSITLAND_KEY_NAME = "transitland"     # line in api_keys.txt:  transitland = YOUR_KEY
TRANSITLAND_MAX_RADIUS_M = 10000         # Transitland's maximum search radius
TRANSITLAND_PAGE_LIMIT = 100             # stops requested per call
NEARBY_STOPS_PATH = "/v4/public/nearby_stops"   # documented in Transit's v4 docs
MAX_STOP_RADIUS_M = 1500                        # Transit's maximum search radius

# Key file: same folder as this script, with a line like:  transit = YOUR_API_KEY
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_keys.txt")
KEY_NAME = "transit"

# Transit API / OTP mode names -> display names used in the "Type" field.
MODE_NAMES = {
    "BUS": "Bus",
    "RAIL": "Rail",
    "SUBWAY": "Subway",
    "TRAM": "Tram",
    "FERRY": "Ferry",
    "CABLE_CAR": "Cable Car",
    "GONDOLA": "Gondola",
    "FUNICULAR": "Funicular",
    "TROLLEYBUS": "Trolleybus",
    "MONORAIL": "Monorail",
}
NON_TRANSIT_MODES = {"WALK", "BICYCLE", "CAR", "SCOOTER"}


class TransitAPIError(Exception):
    """Raised when the Transit API request fails."""


# --------------------------------------------------------------------------- #
# API key
# --------------------------------------------------------------------------- #
def _load_api_key(key_file=KEY_FILE, key_name=KEY_NAME):
    """Read 'transit = APIKEY' from the key file. Returns None if not found."""
    try:
        with open(key_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip().lower() == key_name.lower():
                    return value.strip().strip("'\"") or None
    except FileNotFoundError:
        return None
    return None


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
def _resolve_place(place):
    """Accept (lat, long) or an address dict. Return (lat, long, city)."""
    if isinstance(place, (tuple, list)) and len(place) == 2:
        return float(place[0]), float(place[1]), ""

    if isinstance(place, dict):
        street = place.get("street")
        zip_code = place.get("zip_code")
        city = place.get("city", "")
        state = place.get("state")
        if street and zip_code:
            coords = get_lat_long(street=street, zip_code=zip_code)
        elif street and city and state:
            coords = get_lat_long(street=street, city=city, state=state)
        else:
            raise ValueError("Address dict needs street plus either city+state or zip_code.")
        if not coords or coords[0] is None or coords[1] is None:
            raise ValueError(f"Could not find coordinates for {place}.")
        return float(coords[0]), float(coords[1]), city

    raise ValueError("Place must be a (lat, long) tuple or an address dict.")


# --------------------------------------------------------------------------- #
# API call
# --------------------------------------------------------------------------- #
def _request_plan(api_key, origin, destination, when, plan_path, debug):
    params = {
        "fromPlace": f"{origin[0]},{origin[1]}",
        "toPlace": f"{destination[0]},{destination[1]}",
        "date": when.strftime("%Y-%m-%d"),
        "time": when.strftime("%H:%M"),
    }
    headers = {"apiKey": api_key}

    for attempt in range(2):
        resp = requests.get(BASE_URL + plan_path, params=params, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 429 and attempt == 0:
            time.sleep(15)  # free tier is rate limited; wait once and retry
            continue
        if resp.status_code in (401, 403):
            raise TransitAPIError(f"Authentication failed ({resp.status_code}). Check your API key.")
        if not resp.ok:
            raise TransitAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if debug:
            import json
            print(json.dumps(data, indent=2)[:4000])
        plan = data.get("plan", data)
        return plan.get("itineraries", [])

    raise TransitAPIError("Rate limited by the Transit API; try again in a minute.")


# --------------------------------------------------------------------------- #
# Nearby stops
# --------------------------------------------------------------------------- #
def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _stops_to_method(start, end, origin_city, dest_city):
    """Wrap the nearest start/end stops in the Example.json format.

    Returns [] if either stop is missing. Fields a stop lookup can't know (cost,
    times, travel time, date) are null, and Type is a generic "Transit".
    """
    if start is None or end is None:
        return []

    def block(city, stop):
        return {"City": city, "Name": stop["Name"], "GPS": stop["GPS"]}

    return [
        {
            "Method": {
                "Type": "Transit",
                "Priority": PRIORITY,
                "Cost": None,
                "Travel Time (min)": None,
                "Departure": None,
                "Arrival": None,
                "Date": None,
                "Staring Location": block(origin_city, start),
                "Destination": block(dest_city, end),
            }
        }
    ]


def _require_key(api_key):
    api_key = api_key or _load_api_key() or os.environ.get("TRANSIT_API_KEY")
    if not api_key:
        raise TransitAPIError(
            f"Missing API key. Add a line 'transit = YOUR_KEY' to {KEY_FILE}, "
            "or pass api_key=..."
        )
    return api_key


def _request_nearest_stop(api_key, lat, lng, radius, debug):
    """Return the closest stop to (lat, lng) as a dict, or None if none in range."""
    params = {
        "lat": lat,
        "lon": lng,
        "max_distance": max(1, min(int(radius), MAX_STOP_RADIUS_M)),
        "stop_filter": "Routable",  # only stops that are actually served by routes
    }
    headers = {"apiKey": api_key}

    for attempt in range(2):
        resp = requests.get(BASE_URL + NEARBY_STOPS_PATH, params=params, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 429 and attempt == 0:
            time.sleep(15)
            continue
        if resp.status_code in (401, 403):
            raise TransitAPIError(f"Authentication failed ({resp.status_code}). Check your API key.")
        if not resp.ok:
            raise TransitAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if debug:
            import json
            print(json.dumps(data, indent=2)[:4000])
        break
    else:
        raise TransitAPIError("Rate limited by the Transit API; try again in a minute.")

    stops = []
    for s in data.get("stops", []):
        s_lat = s.get("stop_lat", s.get("lat"))
        s_lng = s.get("stop_lon", s.get("lon"))
        if s_lat is None or s_lng is None:
            continue
        dist = s.get("distance")
        if dist is None:
            dist = _haversine_m(lat, lng, float(s_lat), float(s_lng))
        stops.append(
            {
                "Name": s.get("stop_name", s.get("name", "")),
                "GPS": {"LAT": float(s_lat), "LONG": float(s_lng)},
                "Distance (m)": round(float(dist)),
            }
        )
    if not stops:
        return None
    return min(stops, key=lambda s: s["Distance (m)"])


def get_nearest_stops(origin, destination, radius=MAX_STOP_RADIUS_M, api_key=None, debug=False,
                      raw=False):
    """
    Find the closest transit stop to origin and the closest to destination.

    origin / destination : (lat, long) tuple, or address dict (see get_transit_options).
    radius               : search radius in meters (Transit's maximum is 1500).

    Costs 2 API calls. By default returns a list with one item in the Example.json
    format (Priority 3): Starting Location = closest stop to origin, Destination =
    closest stop to destination; [] if either has no stop in range. Cost, times, date
    and travel time are null, and Type is "Transit". With raw=True, returns:
        {
          "Starting Stop":    {"Name": ..., "GPS": {"LAT": ..., "LONG": ...}, "Distance (m)": ...},
          "Destination Stop": {...}
        }
    A value is None if no stop was found within the radius.
    """
    api_key = _require_key(api_key)
    o_lat, o_lng, o_city = _resolve_place(origin)
    d_lat, d_lng, d_city = _resolve_place(destination)

    start = _request_nearest_stop(api_key, o_lat, o_lng, radius, debug)
    end = _request_nearest_stop(api_key, d_lat, d_lng, radius, debug)
    if raw:
        return {"Starting Stop": start, "Destination Stop": end}
    return _stops_to_method(start, end, o_city, d_city)


# --------------------------------------------------------------------------- #
# Nearby stops via Transitland (larger radius, up to 10 km)
# --------------------------------------------------------------------------- #
def _transitland_get(api_key, params, debug):
    headers = {"apikey": api_key}
    for attempt in range(2):
        resp = requests.get(TRANSITLAND_STOPS_URL, params=params, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 429 and attempt == 0:
            time.sleep(15)
            continue
        if resp.status_code in (401, 403):
            raise TransitAPIError(f"Transitland authentication failed ({resp.status_code}). Check your key.")
        if not resp.ok:
            raise TransitAPIError(f"Transitland HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if debug:
            import json
            print(json.dumps(data, indent=2)[:4000])
        return data
    raise TransitAPIError("Rate limited by Transitland; try again in a minute.")


def _request_nearest_stop_transitland(api_key, lat, lng, radius, debug):
    """Return the closest stop to (lat, lng) as a dict, or None if none in range."""
    radius = max(1, min(int(radius), TRANSITLAND_MAX_RADIUS_M))
    best = None

    # Transitland doesn't guarantee results are sorted by distance. If a call comes back
    # full (possibly truncated), retry with a smaller radius so the closest stop isn't missed.
    for _ in range(4):
        data = _transitland_get(
            api_key,
            {
                "lat": lat,
                "lon": lng,
                "radius": radius,
                "limit": TRANSITLAND_PAGE_LIMIT,
                "location_type": 0,   # stops/platforms (skips station entrances and generic nodes)
            },
            debug,
        )
        raw_stops = data.get("stops", [])

        for s in raw_stops:
            coords = (s.get("geometry") or {}).get("coordinates")
            if not coords or len(coords) < 2:
                continue
            s_lng, s_lat = float(coords[0]), float(coords[1])  # GeoJSON order is lon, lat
            dist = round(_haversine_m(lat, lng, s_lat, s_lng))
            if best is None or dist < best["Distance (m)"]:
                best = {
                    "Name": s.get("stop_name") or "",
                    "GPS": {"LAT": s_lat, "LONG": s_lng},
                    "Distance (m)": dist,
                }

        if len(raw_stops) < TRANSITLAND_PAGE_LIMIT or radius <= 100:
            break  # complete result set, so `best` is the true closest
        radius = max(100, radius // 4)

    return best


def get_nearest_stops_transitland(origin, destination, radius=5000, api_key=None, debug=False,
                                  raw=False):
    """
    Like get_nearest_stops, but uses Transitland so the radius can go up to 10,000 m.

    origin / destination : (lat, long) tuple, or address dict (see get_transit_options).
    radius               : search radius in meters (max 10,000; default 5,000).
    api_key              : Transitland key (default: 'transitland' entry in api_keys.txt,
                           then the TRANSITLAND_API_KEY env var).

    Any type of stop is returned (bus, rail, etc.). Normally 2 API calls; a location in a
    very dense area can use a few extra calls to make sure the closest stop is found.
    Returns the same format as get_nearest_stops: by default a list with one item in the
    Example.json format ([] if either location has no stop in range); with raw=True, the
    {"Starting Stop": ..., "Destination Stop": ...} dict that includes distances.
    """
    api_key = (
        api_key
        or _load_api_key(key_name=TRANSITLAND_KEY_NAME)
        or os.environ.get("TRANSITLAND_API_KEY")
    )
    if not api_key:
        raise TransitAPIError(
            f"Missing Transitland key. Add a line 'transitland = YOUR_KEY' to {KEY_FILE}, "
            "or pass api_key=..."
        )

    o_lat, o_lng, o_city = _resolve_place(origin)
    d_lat, d_lng, d_city = _resolve_place(destination)

    start = _request_nearest_stop_transitland(api_key, o_lat, o_lng, radius, debug)
    end = _request_nearest_stop_transitland(api_key, d_lat, d_lng, radius, debug)
    if raw:
        return {"Starting Stop": start, "Destination Stop": end}
    return _stops_to_method(start, end, o_city, d_city)


# --------------------------------------------------------------------------- #
# Output formatting
# --------------------------------------------------------------------------- #
def _place_block(city, leg_end, fallback_coords):
    """Build a Starting Location / Destination block from a leg endpoint."""
    leg_end = leg_end or {}
    lat = leg_end.get("lat", fallback_coords[0])
    lon = leg_end.get("lon", fallback_coords[1])
    return {
        "City": city,
        "Name": leg_end.get("name", ""),
        "GPS": {"LAT": lat, "LONG": lon},
    }


def _clock(dt):
    return f"{dt.hour}:{dt.minute:02d}"


def _build_option(itinerary, origin, destination, origin_city, dest_city):
    legs = itinerary.get("legs", [])
    transit_legs = [
        leg for leg in legs
        if leg.get("transitLeg") or (leg.get("mode") and leg["mode"] not in NON_TRANSIT_MODES)
    ]
    if not transit_legs:
        return None  # walking-only results are not a transit option

    first, last = transit_legs[0], transit_legs[-1]

    # Type: the transport mode(s) used, e.g. "Bus" or "Bus/Subway".
    modes = []
    for leg in transit_legs:
        name = MODE_NAMES.get(str(leg.get("mode", "")).upper(), str(leg.get("mode", "Transit")).title())
        if name not in modes:
            modes.append(name)

    depart = datetime.fromtimestamp(first["startTime"] / 1000)
    arrive = datetime.fromtimestamp(last["endTime"] / 1000)
    minutes = round((arrive - depart).total_seconds() / 60)

    fare = itinerary.get("fare")
    cost = fare if isinstance(fare, (int, float)) else None

    return {
        "Method": {
            "Type": "/".join(modes),
            "Priority": PRIORITY,
            "Cost": cost,
            "Travel Time (min)": minutes,
            "Departure": _clock(depart),
            "Arrival": _clock(arrive),
            "Date": depart.strftime("%m/%d/%Y"),
            "Staring Location": _place_block(origin_city, first.get("from"), origin),
            "Destination": _place_block(dest_city, last.get("to"), destination),
        }
    }


# --------------------------------------------------------------------------- #
# Public function
# --------------------------------------------------------------------------- #
def get_transit_options(origin, destination, depart_at=None, max_options=1,
                        api_key=None, plan_path=PLAN_PATH, debug=False):
    """
    Find public transit options from origin to destination.

    origin / destination : (lat, long) tuple, or dict with street and either
                           city+state or zip_code (geocoded with address_coords).
    depart_at            : datetime to depart at (default: now).
    max_options          : how many routes to return (default 1).
    api_key              : Transit API key (default: the 'transit' entry in
                           api_keys.txt next to this file, then TRANSIT_API_KEY).

    Returns a list of dicts in the Example.json format (Priority 3, Type = the
    transport used). Departure/Arrival/Travel Time run from boarding the first
    transit vehicle to leaving the last one, and Starting Location / Destination
    are those boarding and exit stops. Returns [] if no transit route exists.
    Cost is null unless the API supplies a fare.

    Raises TransitAPIError on API failures and ValueError on bad inputs.
    """
    api_key = api_key or _load_api_key() or os.environ.get("TRANSIT_API_KEY")
    if not api_key:
        raise TransitAPIError(
            f"Missing API key. Add a line 'transit = YOUR_KEY' to {KEY_FILE}, "
            "or pass api_key=..."
        )

    o_lat, o_lng, o_city = _resolve_place(origin)
    d_lat, d_lng, d_city = _resolve_place(destination)

    itineraries = _request_plan(
        api_key, (o_lat, o_lng), (d_lat, d_lng),
        depart_at or datetime.now(), plan_path, debug,
    )

    options = []
    for itin in itineraries:
        option = _build_option(itin, (o_lat, o_lng), (d_lat, d_lng), o_city, d_city)
        if option:
            options.append(option)
        if len(options) >= max_options:
            break
    return options


def get_transit_route(origin, destination, radius=5000, depart_at=None, max_options=1,
                      transit_key=None, transitland_key=None, plan_path=PLAN_PATH,
                      fallback_to_stops=False, debug=False):
    """
    Full pipeline in one call:
      1. Transitland: find the closest stop to origin and to destination (2 API calls).
      2. Transit API: plan a route between those two stops (1 API call).
      3. Return the result in the Example.json format (Priority 3).

    origin / destination : (lat, long) tuple, or address dict (see get_transit_options).
    radius               : stop search radius in meters (Transitland max 10,000; default 5,000).
    depart_at            : datetime to depart at (default: now).
    max_options          : routes to return (default 1; extra routes cost no extra calls).
    transit_key          : Transit API key (default: 'transit' in api_keys.txt).
    transitland_key      : Transitland key (default: 'transitland' in api_keys.txt).
    fallback_to_stops    : if the stops are found but no route connects them, return the
                           stops-only result (Type "Transit", times/cost null) instead of [].

    In each result, Staring Location / Destination are the closest stops found in step 1.
    Type, Cost, Travel Time (min), Departure, Arrival and Date come from the planned route.
    Returns [] if no stop is found near one of the locations or no route connects them.
    """
    o_lat, o_lng, o_city = _resolve_place(origin)   # geocode once, reuse for both steps
    d_lat, d_lng, d_city = _resolve_place(destination)

    stops = get_nearest_stops_transitland(
        (o_lat, o_lng), (d_lat, d_lng), radius=radius, api_key=transitland_key,
        debug=debug, raw=True,
    )
    start, end = stops["Starting Stop"], stops["Destination Stop"]
    if start is None or end is None:
        return []

    options = get_transit_options(
        (start["GPS"]["LAT"], start["GPS"]["LONG"]),
        (end["GPS"]["LAT"], end["GPS"]["LONG"]),
        depart_at=depart_at, max_options=max_options, api_key=transit_key,
        plan_path=plan_path, debug=debug,
    )
    if not options:
        return _stops_to_method(start, end, o_city, d_city) if fallback_to_stops else []

    for option in options:
        method = option["Method"]
        method["Staring Location"] = {"City": o_city, "Name": start["Name"], "GPS": start["GPS"]}
        method["Destination"] = {"City": d_city, "Name": end["Name"], "GPS": end["GPS"]}
    return options


if __name__ == "__main__":
    # Quick test: python transit_route.py 32.5232,-92.6379 29.9511,-90.0715
    import json
    import sys

    if len(sys.argv) != 3:
        sys.exit("Usage: python transit_route.py LAT,LONG LAT,LONG")
    a = tuple(float(x) for x in sys.argv[1].split(","))
    b = tuple(float(x) for x in sys.argv[2].split(","))
    print(json.dumps(get_transit_options(a, b), indent=2))
