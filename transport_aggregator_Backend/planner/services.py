"""Adapters between the original Group 3 scripts and the web interface.

No fabricated itineraries: unavailable APIs and missing fares are reported as such.
Original scripts remain unchanged in /legacy for reference and further work.
"""
from __future__ import annotations

import csv
import importlib
import logging
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from functools import lru_cache

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)
LEGACY = Path(settings.BASE_DIR) / "legacy"
if str(LEGACY) not in sys.path:
    # Existing transit_route.py imports address_coords as an unqualified module.
    sys.path.insert(0, str(LEGACY))

USER_AGENT = os.environ.get("AGGREGATOR_USER_AGENT", "Group3TravelAggregator/0.1 (student-project)")
GEOCODER_URL = "https://photon.komoot.io/api/"
OSRM_ROUTE_URL = os.environ.get("OSRM_ROUTE_URL", "https://router.project-osrm.org/route/v1/driving")
MAX_SUGGESTIONS = 6


class LocationError(ValueError):
    pass


def _valid_us_coords(lat, lon):
    return -180 <= lon <= -60 and 18 <= lat <= 72 and math.isfinite(lat) and math.isfinite(lon)


def _geocode_label(properties):
    parts = []
    house = properties.get("housenumber")
    street = properties.get("street")
    if house and street:
        parts.append(f"{house} {street}")
    elif properties.get("name"):
        parts.append(str(properties["name"]))
    elif street:
        parts.append(str(street))
    for key in ("city", "state", "postcode"):
        value = properties.get(key)
        if value and str(value).casefold() not in [p.casefold() for p in parts]:
            parts.append(str(value))
    return ", ".join(parts) or "Location in the United States"


def lookup_addresses(query, limit=MAX_SUGGESTIONS):
    """Address suggestions via Photon, cached briefly to reduce public-API usage.

    The public instance is for low-traffic prototyping only; operate your own
    Photon instance or use a provider with an SLA before heavy deployment.
    """
    query = (query or "").strip()[:180]
    if len(query) < 3:
        return []
    limit = min(max(int(limit), 1), MAX_SUGGESTIONS)
    key = f"photon:us:{query.casefold()}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    response = requests.get(
        GEOCODER_URL,
        params={"q": query, "limit": limit * 2, "lang": "en"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=6,
    )
    response.raise_for_status()
    features = response.json().get("features", [])
    suggestions, seen = [], set()
    for feature in features:
        props = feature.get("properties") or {}
        if str(props.get("countrycode", "")).casefold() != "us":
            continue
        coords = (feature.get("geometry") or {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue
        if not _valid_us_coords(lat, lon):
            continue
        label = _geocode_label(props)
        fingerprint = (label, round(lat, 5), round(lon, 5))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        suggestions.append({"label": label, "lat": lat, "lon": lon})
        if len(suggestions) >= limit:
            break
    cache.set(key, suggestions, timeout=3600)
    return suggestions


def resolve_location(address, lat=None, lon=None):
    """Accept selected coordinates or geocode entered address text on submit."""
    address = address.strip()
    if lat is not None and lon is not None:
        if not _valid_us_coords(float(lat), float(lon)):
            raise LocationError("Selected coordinates are outside the supported area.")
        return {"label": address, "lat": float(lat), "lon": float(lon)}
    # Accept pasted coordinates as a convenient deterministic, offline test input.
    coordinate_match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", address)
    if coordinate_match:
        lat, lon = map(float, coordinate_match.groups())
        if not _valid_us_coords(lat, lon):
            raise LocationError("Coordinates must describe a United States location.")
        return {"label": address, "lat": lat, "lon": lon}
    try:
        suggestions = lookup_addresses(address, limit=5)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Geocoding unavailable: %s", exc)
        raise LocationError("Address lookup is temporarily unavailable. Try selecting an autocomplete suggestion.") from exc
    if not suggestions:
        raise LocationError(f"No U.S. address found for '{address}'. Please try a more complete address.")
    # The first search result is the provider's best guess; allow edits on the home page.
    return {"label": suggestions[0]["label"], "lat": suggestions[0]["lat"], "lon": suggestions[0]["lon"]}


def _haversine_miles(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.76 * 2 * math.asin(min(1, math.sqrt(x)))


@lru_cache(maxsize=1)
def _airports():
    airports = []
    with (LEGACY / "cleaned_airport.csv").open(encoding="utf-8", newline="") as file:
        for airport in csv.DictReader(file):
            if (airport.get("iso_country") == "US" and airport.get("iata_code")
                    and airport.get("scheduled_service") == "yes"
                    and airport.get("type") in ("large_airport", "medium_airport")):
                try:
                    airports.append((float(airport["latitude_deg"]), float(airport["longitude_deg"]), airport["iata_code"]))
                except (ValueError, TypeError):
                    continue
    return airports


def nearest_airport(place, max_miles=150):
    lat_lon = (place["lat"], place["lon"])
    selected = min(_airports(), key=lambda ap: _haversine_miles(lat_lon, (ap[0], ap[1])), default=None)
    if selected and _haversine_miles(lat_lon, selected[:2]) <= max_miles:
        return selected[2]
    return None


def nearest_station(place, max_miles=110):
    from legacy.Amtrak_Data import STATIONS  # requires pandas/gtfs_kit; see optional deps
    point = (place["lat"], place["lon"])
    stations = sorted(STATIONS.items(), key=lambda item: _haversine_miles(point, (item[1][1], item[1][2])))
    if stations and _haversine_miles(point, (stations[0][1][1], stations[0][1][2])) <= max_miles:
        return stations[0][0]
    return None


def _numeric(value):
    if value is None or value == "":
        return None
    try:
        num = float(value)
        if math.isfinite(num) and num >= 0:
            return num
    except (TypeError, ValueError):
        pass
    return None


def normalize_legacy(item, mode, source):
    """Handle both {Method:{...}} and {method:{info, ...}} source schemas."""
    if "Method" in item:
        method = item["Method"]
        start = method.get("Starting Location") or method.get("Staring Location") or {}
        dest = method.get("Destination") or {}
    else:
        wrapper = item.get("method", {})
        method = wrapper.get("info", {})
        start = wrapper.get("starting_location") or {}
        dest = wrapper.get("destination") or {}

    duration = _numeric(method.get("Travel Time (min)"))
    cost = _numeric(method.get("Cost"))
    return {
        "mode": mode,
        "mode_label": dict(MODE_LABELS)[mode],
        "name": method.get("Name") or {"planes": "Flight", "trains": "Amtrak train", "public_buses": "Public transit", "greyhound": "Greyhound bus"}.get(mode, "Route"),
        "source": source,
        "cost": cost,
        "duration_minutes": round(duration) if duration is not None else None,
        "departure": method.get("Departure") or "",
        "arrival": method.get("Arrival") or "",
        "date": method.get("Date") or "",
        "start_name": start.get("Name") or start.get("City") or "Origin",
        "end_name": dest.get("Name") or dest.get("City") or "Destination",
        "distance_miles": None,
        "geometry": None,
        "estimate": False,
        # Keep the exact backend Method JSON for session persistence/download.
        "raw_method": item if "Method" in item else None,
        "priority": method.get("Priority"),
    }


MODE_LABELS = (
    ("car", "Car"),
    ("planes", "Planes"),
    ("trains", "Trains"),
    ("public_buses", "Public Buses"),
    ("greyhound", "Greyhound"),
)


def _car_routes(origin, destination, travel_date, adults=1):
    """Return driving-route estimates from OSRM; never invent gas/toll prices."""
    coordinates = f'{origin["lon"]},{origin["lat"]};{destination["lon"]},{destination["lat"]}'
    response = requests.get(
        f"{OSRM_ROUTE_URL.rstrip('/')}/{coordinates}",
        params={"overview": "simplified", "geometries": "geojson", "steps": "false"},
        headers={"User-Agent": USER_AGENT}, timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    routes = payload.get("routes") or []
    if payload.get("code") != "Ok" or not routes:
        return []
    route = routes[0]
    duration = _numeric(route.get("duration"))
    distance = _numeric(route.get("distance"))
    if duration is None or distance is None:
        return []
    geometry = (route.get("geometry") or {}).get("coordinates") or []
    # GeoJSON coords are [longitude, latitude]. Keep this for Leaflet conversion.
    geometry = geometry[:3000] if len(geometry) <= 3000 else geometry[::max(1, math.ceil(len(geometry) / 3000))]
    return [{
        "mode": "car", "mode_label": "Car", "name": "Drive", "source": "OSRM route estimate",
        "cost": None, "duration_minutes": round(duration / 60),
        "departure": "", "arrival": "", "date": travel_date.isoformat(),
        "start_name": origin["label"], "end_name": destination["label"],
        "distance_miles": round(distance / 1609.344, 1),
        "geometry": geometry, "estimate": True,
    }]


def _plane_routes(origin, destination, travel_date, adults=1):
    """Use the ORIGINAL backend flight module, not the frontend's legacy copy."""
    start_code = nearest_airport(origin)
    end_code = nearest_airport(destination)
    if not start_code or not end_code or start_code == end_code:
        return [], "No distinct scheduled-service airports were found within 150 miles of both addresses."
    from google_flights_scraper import search_flights
    rows = search_flights(start_code, end_code, travel_date, adults=adults)
    return [normalize_legacy(row, "planes", "Google Flights scraper") for row in rows], None


def _train_routes(origin, destination, travel_date, adults=1):
    """Use the ORIGINAL backend's GTFS download/cache and Amtrak adapter."""
    from Amtrak_Data import STATIONS
    from routes.amtrak_adapter import search_amtrak
    def closest(place):
        point = (place["lat"], place["lon"])
        candidates = sorted(STATIONS, key=lambda code: _haversine_miles(point, (STATIONS[code][1], STATIONS[code][2])))
        return candidates[0] if candidates and _haversine_miles(point, (STATIONS[candidates[0]][1], STATIONS[candidates[0]][2])) <= 110 else None
    start_code, end_code = closest(origin), closest(destination)
    if not start_code or not end_code or start_code == end_code:
        return [], "No distinct stations were found within 110 miles of both addresses in the current station list."
    rows = search_amtrak(start_code, end_code, travel_date, adults=adults)
    return [normalize_legacy(row, "trains", "Amtrak GTFS schedule (fares unavailable)") for row in rows], None


def _bus_routes(origin, destination, travel_date, adults=1):
    if not os.environ.get("TRANSIT_API_KEY") or not os.environ.get("TRANSITLAND_API_KEY"):
        return [], "Public transit requires TRANSIT_API_KEY and TRANSITLAND_API_KEY."
    transit = importlib.import_module("legacy.transit_route")
    # Transit API uses current time for local datetime and Transitland finds nearby stops.
    # Requested date is preserved; provider results determine actual service availability.
    from datetime import time
    when = datetime.combine(travel_date, time(hour=9))
    rows = transit.get_transit_route(
        (origin["lat"], origin["lon"]), (destination["lat"], destination["lon"]),
        depart_at=when, max_options=3, radius=5000,
        transit_key=os.environ.get("TRANSIT_API_KEY"),
        transitland_key=os.environ.get("TRANSITLAND_API_KEY"),
    )
    # Don't label rail/subway or mixed itineraries as bus-only results.
    bus_only = [item for item in rows if all(part.strip().casefold() == "bus"
                for part in str(item.get("Method", {}).get("Type", "")).split("/"))]
    if not bus_only:
        return [], "No bus-only transit itineraries were returned."
    return [normalize_legacy(item, "public_buses", "Transit API / Transitland") for item in bus_only], None


def _greyhound_routes(origin, destination, travel_date, adults=1):
    """Resolve searched cities, then use the ORIGINAL Greyhound backend adapter.

    The backend's pricing, Method JSON and fixed one-adult limitation remain
    unchanged. The frontend adds city lookup for routes beyond Dallas/Houston.
    """
    from planner.greyhound_cities import GreyhoundCityError, resolve_greyhound_city
    from routes.greyhound_adapter import search_greyhound
    if adults != 1:
        return [], "Greyhound currently supports one adult only. Choose 1 traveler to see its fares."
    try:
        source_city = resolve_greyhound_city(origin)
        target_city = resolve_greyhound_city(destination)
    except GreyhoundCityError as exc:
        return [], str(exc)
    if source_city == target_city:
        return [], "Greyhound origin and destination resolve to the same city."
    rows = search_greyhound(source_city, target_city, travel_date, adults=adults)
    return [normalize_legacy(row, "greyhound", "Greyhound/FlixBus (unofficial endpoint)") for row in rows], None


PROVIDERS = {
    "car": _car_routes,
    "planes": _plane_routes,
    "trains": _train_routes,
    "public_buses": _bus_routes,
    "greyhound": _greyhound_routes,
}


def search_routes(origin, destination, travel_date, enabled_modes, objective="cost", adults=1):
    """Fetch only enabled modes. Return (routes, provider notices).

    These are direct alternatives, not a transfer-optimized multi-leg itinerary.
    The existing least_cost_path.py needs a unified, complete timetable, so it is
    preserved for future integration rather than misapplied to incompatible feeds.
    """
    result, notices = [], []
    for mode in enabled_modes:
        if mode not in PROVIDERS:
            continue
        try:
            response = PROVIDERS[mode](origin, destination, travel_date, adults)
            if isinstance(response, tuple):
                routes, notice = response
            else:
                routes, notice = response, None
            if routes:
                result.extend(routes)
            else:
                notices.append(f"{dict(MODE_LABELS)[mode]}: {notice or 'No matching routes were returned for this search.'}")
        except Exception:
            logger.exception("Provider %s failed", mode)
            notices.append(f"{dict(MODE_LABELS)[mode]}: the provider could not complete this search. Check its configuration or try again later.")

    if objective == "time":
        result.sort(key=lambda row: (row["duration_minutes"] is None, row["duration_minutes"] if row["duration_minutes"] is not None else math.inf, row["cost"] if row["cost"] is not None else math.inf))
    else:
        result.sort(key=lambda row: (row["cost"] is None, row["cost"] if row["cost"] is not None else math.inf, row["duration_minutes"] if row["duration_minutes"] is not None else math.inf))
    for position, route in enumerate(result, 1):
        route["rank"] = position
    return result, notices
