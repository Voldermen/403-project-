"""Resolve selected U.S. cities to FlixBus/Greyhound city UUIDs.

The original Greyhound scraper accepts UUIDs, whereas the team's frontend takes
street addresses. This frontend-only adapter does not modify the original
scraper or backend API. The autocomplete endpoint is undocumented and may fail.
"""
from __future__ import annotations

import math
import re
from uuid import UUID

import requests
from django.core.cache import cache

AUTOCOMPLETE_URL = "https://global.api.flixbus.com/search/autocomplete/cities"

# These city IDs already come from the team's original Greyhound module. Keep
# known test routes working if the autocomplete service is temporarily offline.
from greyhound_search import DALLAS, HOUSTON
KNOWN_CITIES = {"dallas": DALLAS, "houston": HOUSTON}

STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
}
STATE_ABBREVIATIONS = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT "
    "VA WA WV WI WY DC".split()
)


class GreyhoundCityError(ValueError):
    """A frontend address could not be matched to a Greyhound city."""


def city_from_label(label: str) -> str:
    """Extract a likely city from e.g. '123 Main St, Dallas, Texas, 75201'.

    This is only a search hint; provider matches must still pass a proximity
    check before a city UUID is accepted.
    """
    parts = [part.strip() for part in (label or "").split(",") if part.strip()]
    while parts:
        tail = parts[-1].strip()
        norm = tail.casefold()
        if (norm in {"united states", "united states of america", "usa", "us"}
                or norm in STATE_NAMES or tail.upper() in STATE_ABBREVIATIONS
                or re.fullmatch(r"\d{5}(?:-\d{4})?", tail)):
            parts.pop()
            continue
        break
    return parts[-1] if parts else ""


def _miles(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    lat1, lat2 = math.radians(a_lat), math.radians(b_lat)
    d_lat, d_lon = lat2 - lat1, math.radians(b_lon - a_lon)
    x = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 3958.76 * 2 * math.asin(min(1, math.sqrt(x)))


def _coordinates(candidate: dict):
    pos = candidate.get("location") or candidate.get("coordinates") or {}
    try:
        lat = float(pos.get("lat", pos.get("latitude")))
        lon = float(pos.get("lon", pos.get("longitude")))
        return (lat, lon) if math.isfinite(lat) and math.isfinite(lon) else None
    except (TypeError, ValueError):
        return None


def _candidate_name(candidate: dict) -> str:
    return str(candidate.get("name") or (candidate.get("city") or {}).get("name") or "").split(",", 1)[0].strip()


def _us_city(candidate: dict) -> bool:
    country = candidate.get("country") or {}
    if isinstance(country, dict):
        code = country.get("code") or country.get("country_code")
    else:
        code = country
    code = code or candidate.get("country_code")
    # If the endpoint omits country entirely, require a coordinate match below.
    return not code or str(code).casefold() in {"us", "usa", "united states", "united states of america"}


def resolve_greyhound_city(place: dict) -> str:
    """Find a city UUID by name AND by the selected address's coordinates.

    Fail closed rather than treating two cities with similar names as the same
    place. Keeps nearby addresses usable while avoiding unrelated bus routes.
    """
    name = city_from_label(place.get("label", ""))
    if not name or len(name) < 2:
        raise GreyhoundCityError("Enter a U.S. city or select a complete address to search Greyhound.")

    # Known legacy mappings (Dallas/Houston) are retained, but only when the
    # searched city really is Dallas/Houston. No extra network request needed.
    known_id = KNOWN_CITIES.get(name.casefold())
    if known_id:
        return known_id

    key = f"greyhound-city:us:{name.casefold()}"
    options = cache.get(key)
    if options is None:
        response = requests.get(
            AUTOCOMPLETE_URL,
            params={"q": name, "lang": "en", "country": "us",
                    "flixbus_cities_only": "false", "stations": "false"},
            headers={"Accept": "application/json", "User-Agent": "Group3TravelAggregator/0.1"},
            timeout=10,
        )
        response.raise_for_status()
        options = response.json()
        if isinstance(options, dict):
            options = options.get("cities") or options.get("results") or options.get("data") or []
        if not isinstance(options, list):
            raise GreyhoundCityError("Greyhound's city lookup returned an unexpected response.")
        cache.set(key, options, timeout=12 * 60 * 60)

    try:
        place_lat, place_lon = float(place["lat"]), float(place["lon"])
    except (ValueError, TypeError, KeyError) as exc:
        raise GreyhoundCityError("Select an address suggestion with coordinates for Greyhound.") from exc
    matching = []
    for candidate in options:
        if not isinstance(candidate, dict) or not _us_city(candidate):
            continue
        candidate_name = _candidate_name(candidate)
        # Don't accept "New Orleans East" as the same city as "New Orleans".
        if candidate_name.casefold() != name.casefold():
            continue
        try:
            city_uuid = str(UUID(str(candidate.get("id", ""))))
        except (ValueError, TypeError, AttributeError):
            continue
        pos = _coordinates(candidate)
        if pos is None:
            continue  # Can't verify that an ambiguous city is close by.
        distance = _miles(place_lat, place_lon, *pos)
        if distance <= 60:
            matching.append((distance, city_uuid))

    if not matching:
        raise GreyhoundCityError(
            f"Greyhound could not match '{name}' to a nearby supported city. "
            "Try a city-center address or another route."
        )
    return min(matching)[1]
