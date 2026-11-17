"""Address autocomplete only. Route selection belongs exclusively to Algorithm/main_alg.py."""
import math
import os
import requests
from django.core.cache import cache

USER_AGENT = os.environ.get('AGGREGATOR_USER_AGENT', 'Group3TravelAggregator/0.1 (student-project)')
GEOCODER_URL = 'https://photon.komoot.io/api/'
MAX_SUGGESTIONS = 6

def _valid_us_coords(lat, lon):
    return -180 <= lon <= -60 and 18 <= lat <= 72 and math.isfinite(lat) and math.isfinite(lon)

def _geocode_label(properties):
    parts = []
    house, street = properties.get('housenumber'), properties.get('street')
    if house and street:
        parts.append(f'{house} {street}')
    elif properties.get('name'):
        parts.append(str(properties['name']))
    elif street:
        parts.append(str(street))
    for key in ('city', 'state', 'postcode'):
        value = properties.get(key)
        if value and str(value).casefold() not in [part.casefold() for part in parts]:
            parts.append(str(value))
    return ', '.join(parts) or 'Location in the United States'

def lookup_addresses(query, limit=MAX_SUGGESTIONS):
    """Autocomplete suggestions only; never chooses transport hubs or routes."""
    query = (query or '').strip()[:180]
    if len(query) < 3:
        return []
    limit = min(max(int(limit), 1), MAX_SUGGESTIONS)
    key = f'photon:us:{query.casefold()}:{limit}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    response = requests.get(
        GEOCODER_URL,
        params={'q': query, 'limit': limit * 2, 'lang': 'en'},
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'},
        timeout=6,
    )
    response.raise_for_status()
    suggestions, seen = [], set()
    for feature in response.json().get('features', []):
        props = feature.get('properties') or {}
        if str(props.get('countrycode', '')).casefold() != 'us':
            continue
        coords = (feature.get('geometry') or {}).get('coordinates', [])
        if len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (ValueError, TypeError):
            continue
        if not _valid_us_coords(lat, lon):
            continue
        label = _geocode_label(props)
        identity = (label, round(lat, 5), round(lon, 5))
        if identity in seen:
            continue
        seen.add(identity)
        suggestions.append({'label': label, 'lat': lat, 'lon': lon})
        if len(suggestions) >= limit:
            break
    cache.set(key, suggestions, timeout=3600)
    return suggestions
