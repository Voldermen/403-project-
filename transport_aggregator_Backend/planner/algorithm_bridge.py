"""Backend-to-algorithm boundary. All routes come from the unmodified main_alg().

Do not import the algorithm into Django: it uses unqualified local imports,
process-relative CSV paths and debug JSON output files. Run it in a per-search
subprocess with an isolated working directory so Windows/Linux and concurrent
Gunicorn requests do not overwrite each other's debug JSON output.
"""
from __future__ import annotations

from datetime import date, datetime
import math
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from django.conf import settings

logger = logging.getLogger(__name__)

MODES = {'planes': 'plane', 'trains': 'train', 'greyhound': 'bus'}
REQUIRED_DATA = (
    'airports_database/cleaned_airport.csv',
    'greyhound_database/cleaned_greyhound.csv',
    'amtrack_database/cleaned_amtrack.csv',
)
RESULT_MARKER = '__GROUP3_MAIN_ALG_RESULT__='
LOCATION_ERROR_MARKER = '__GROUP3_LOCATION_ERROR__='

# This code runs only in the child process. It imports/calls the provided
# function. No pathfinding, ranking, fare calculation or scrapers live here.
CHILD_ENTRYPOINT = """
import json, sys
from datetime import date
import main_alg as teammate_algorithm

payload = json.loads(sys.argv[1])
original_geocoder = teammate_algorithm.get_lat_long
# main_alg() geocodes the origin first, then the destination. Provide the
# corresponding frontend-selected GPS pair at exactly that boundary.
# All route calculations and provider calls remain in the teammate module.
locations = iter(('origin', 'destination'))

class _UnresolvedLocation(ValueError):
    pass

def _resolve_search_location(street, city, state, zip_code):
    place = next(locations, None)
    pair = payload.get(place + '_coords') if place else None
    if pair is None:
        pair = original_geocoder(street, city, state, zip_code)
    if not pair or len(pair) != 2 or pair[0] is None or pair[1] is None:
        name = place or 'requested'
        raise _UnresolvedLocation(
            'Could not determine the ' + name + ' coordinates. '
            'Choose a location from the autocomplete suggestions, or enter a full US street address.'
        )
    return tuple(pair)

# This changes only the in-memory function reference in this child process;
# Algorithm/main_alg.py and its imports are not edited on disk.
teammate_algorithm.get_lat_long = _resolve_search_location
try:
    result = teammate_algorithm.main_alg(
        payload['origin'], payload['destination'], date.fromisoformat(payload['travel_date']),
        objective=payload['objective'], start_time=payload['start_time'],
        exclude=payload['exclude'], num_paths=payload['num_paths'],
    )
except _UnresolvedLocation as exc:
    print('__GROUP3_LOCATION_ERROR__=' + str(exc), file=sys.stderr)
    sys.exit(2)
print('__GROUP3_MAIN_ALG_RESULT__=' + json.dumps(result, default=str))
"""

class AlgorithmUnavailable(RuntimeError):
    """Missing prerequisites or runtime failure in the supplied algorithm."""


class AlgorithmLocationError(AlgorithmUnavailable):
    """The location could not be geocoded from the search input."""


def _validated_coordinates(latitude, longitude, label):
    """Validate the pair at the subprocess boundary, without selecting hubs."""
    if latitude is None and longitude is None:
        return None  # Legacy clients with complete street addresses still work.
    if latitude is None or longitude is None:
        raise ValueError(f'{label} requires both latitude and longitude.')
    try:
        lat, lon = float(latitude), float(longitude)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{label} coordinates must be numbers.') from exc
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f'{label} coordinates are outside the valid GPS range.')
    return [lat, lon]


def selected_exclusions(selected_modes):
    """Translate frontend checkbox names into main_alg(exclude=...)."""
    unknown = set(selected_modes).difference(MODES)
    if unknown:
        raise ValueError('Unsupported transportation type: ' + ', '.join(sorted(unknown)))
    if not selected_modes:
        raise ValueError('Select at least one transportation type.')
    enabled = set(selected_modes)
    return [algorithm_name for frontend_name, algorithm_name in MODES.items()
            if frontend_name not in enabled] or None


def run_main_algorithm(origin, destination, travel_date, selected_modes,
                       objective='cost', start_time='12:01 am', num_paths=3,
                       origin_lat=None, origin_lon=None,
                       destination_lat=None, destination_lon=None):
    """The *sole* backend entrypoint for route computation.

    `objective=time` from the existing frontend maps to the provided
    algorithm's `duration` objective. When selected-location GPS is supplied,
    adapt only the two geocoder calls; main_alg() owns all route computation.
    Complete street addresses without GPS can still use its original geocoder.
    """
    algorithm_dir = Path(settings.BASE_DIR) / 'Algorithm'
    data_dir = Path(settings.BASE_DIR) / 'data'
    if not (algorithm_dir / 'main_alg.py').is_file():
        raise AlgorithmUnavailable('Missing Algorithm/main_alg.py from the supplied teammate ZIP.')
    # Guard against deploying a newer Uber-ready backend on the older
    # walking-only Algorithm/. The backend must never invent Uber fares.
    source_text = (algorithm_dir / 'main_alg.py').read_text(encoding='utf-8', errors='replace')
    if 'add_walking_connections' in source_text and 'add_uber_connections' not in source_text:
        raise AlgorithmUnavailable(
            'The server still has the older walking-only Algorithm/main_alg.py. '
            'Install the new Algorithm(2) directory provided by the algorithm teammate; '
            'the Django backend cannot calculate or substitute Uber prices.'
        )
    missing = [str(Path('data') / rel) for rel in REQUIRED_DATA
               if not (data_dir / rel).is_file()]
    if missing:
        raise AlgorithmUnavailable('Required algorithm datasets are missing: ' + ', '.join(missing)
                                   + '. Obtain the actual CSV files from the algorithm teammate.')

    if isinstance(travel_date, date):
        travel_date = travel_date.isoformat()
    goal = {'cost': 'cost', 'time': 'duration', 'duration': 'duration', 'arrival': 'arrival'}.get(objective)
    if goal is None:
        raise ValueError('Unsupported optimization objective.')
    payload = {
        'origin': str(origin), 'destination': str(destination),
        'travel_date': str(travel_date), 'objective': goal,
        'start_time': start_time, 'exclude': selected_exclusions(selected_modes),
        'num_paths': int(num_paths),
        'origin_coords': _validated_coordinates(origin_lat, origin_lon, 'Origin'),
        'destination_coords': _validated_coordinates(destination_lat, destination_lon, 'Destination'),
    }
    try:
        timeout = max(1, int(os.environ.get('ALGORITHM_TIMEOUT_SECONDS', '180')))
    except ValueError:
        timeout = 180
    try:
        with tempfile.TemporaryDirectory(prefix='group3-algorithm-') as tmp:
            scratch = Path(tmp)
            isolated_algorithm = scratch / 'Algorithm'
            # Python sources & data from user-provided Algorithm/ are copied,
            # never edited in the original project. Ignore only bytecode and
            # output/debug JSON because main_alg() regenerates those itself.
            shutil.copytree(
                algorithm_dir, isolated_algorithm,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'M_output.json',
                                             'M_output_unified.json', 'M_routes.json'),
            )
            scratch_data = scratch / 'data'
            if os.name == 'nt':  # Windows symlink creation often needs admin rights
                scratch_data.mkdir()
                for relative in REQUIRED_DATA:
                    target = scratch_data / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(data_dir / relative, target)
            else:
                scratch_data.symlink_to(data_dir.resolve(), target_is_directory=True)
            proc = subprocess.run(
                [sys.executable, '-c', CHILD_ENTRYPOINT, json.dumps(payload)],
                cwd=isolated_algorithm, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise AlgorithmUnavailable('The route algorithm exceeded its configured execution time.') from exc
    except OSError as exc:
        logger.exception('Unable to start the route algorithm')
        raise AlgorithmUnavailable('Unable to start the route algorithm process; check server logs.') from exc

    if proc.returncode == 2:
        messages = [line[len(LOCATION_ERROR_MARKER):] for line in proc.stderr.splitlines()
                    if line.startswith(LOCATION_ERROR_MARKER)]
        if messages:
            raise AlgorithmLocationError(messages[-1])
    if proc.returncode != 0:
        logger.error('main_alg failed (exit code %s): %s', proc.returncode, proc.stderr[-5000:])
        raise AlgorithmUnavailable('The supplied route algorithm failed. Check the Django server logs for details.')
    # Scrapers may print diagnostics to stdout, so locate only our JSON marker.
    result_lines = [line[len(RESULT_MARKER):] for line in proc.stdout.splitlines()
                    if line.startswith(RESULT_MARKER)]
    if not result_lines:
        logger.error('main_alg returned no parseable result: %s', proc.stdout[-3000:])
        raise AlgorithmUnavailable('The route algorithm did not return a result.')
    try:
        output = json.loads(result_lines[-1])
    except (ValueError, TypeError) as exc:
        raise AlgorithmUnavailable('The route algorithm returned invalid JSON.') from exc
    if not isinstance(output, dict) or not isinstance(output.get('routes'), list):
        raise AlgorithmUnavailable('The route algorithm returned an unexpected result format.')
    return output


def _display_timestamp(value):
    if not value:
        return ''
    try:
        return datetime.fromisoformat(value).strftime('%b %-d, %Y %-I:%M %p') if os.name != 'nt' else datetime.fromisoformat(value).strftime('%b %d, %Y %I:%M %p')
    except (ValueError, TypeError):
        return str(value)


def _location_name(location):
    if not isinstance(location, dict):
        return ''
    return location.get('Name') or location.get('City') or location.get('Station ID') or ''


def present_algorithm_routes(output):
    """Display-only projection of the supplied algorithm's routes, in its order.

    The newer algorithm replaces walking connectors with Uber legs, priced
    by its own estimate_uber() helper. We expose that fact, but NEVER estimate,
    add up, filter, optimize, or replace any backend route or price here.
    Raw algorithm JSON is returned unchanged by /api/search/ and saved JSON.
    """
    displayed = []
    for route in output.get('routes', []):
        legs = []
        has_estimated_uber = False
        for leg in route.get('legs', []):
            is_uber = str(leg.get('type', '')).casefold() == 'uber'
            # The supplied algorithm's Uber fares are approximations, not
            # live prices. Its per-leg source record marks these as estimated.
            if is_uber:
                has_estimated_uber = True
            name = leg.get('name', '')
            if is_uber:
                name = (name or 'Uber Ride') + ' (estimated fare)'
            legs.append({
                'leg_number': leg.get('leg_number'),
                'type': leg.get('type', ''), 'name': name,
                'cost': leg.get('cost'), 'departure': _display_timestamp(leg.get('departure')),
                'arrival': _display_timestamp(leg.get('arrival')),
                'duration_min': leg.get('duration_min'),
                'wait_before_min': leg.get('wait_before_min'),
                'from_name': _location_name(leg.get('from')),
                'to_name': _location_name(leg.get('to')),
                'estimated_fare': is_uber,
            })
        all_types = list(dict.fromkeys(str(m) for m in route.get('modes', [])))
        # Keep Uber visible in the mode summary; unlike the previous walking
        # connectors, an Uber leg has an estimated price and should be shown.
        modes_label = ' + '.join(all_types) or 'Multi-leg route'
        source = 'Ranked by the supplied route algorithm'
        if has_estimated_uber:
            source += ' · includes estimated Uber fares (not live quotes)'
        displayed.append({
            'rank': route.get('rank'), 'mode': 'multi', 'mode_label': modes_label,
            'name': 'Itinerary ' + str(route.get('rank', '')),
            'source': source,
            'cost': route.get('total_cost'), 'currency': route.get('currency', 'USD'),
            'duration_minutes': route.get('total_time_min'),
            'departure': _display_timestamp(route.get('departure')),
            'arrival': _display_timestamp(route.get('arrival')),
            'start_name': legs[0]['from_name'] if legs else '',
            'end_name': legs[-1]['to_name'] if legs else '',
            'num_legs': route.get('num_legs', len(legs)), 'legs': legs,
            'estimated_uber': has_estimated_uber,
        })
    return displayed


def map_locations(output, origin_text, destination_text):
    """Use coordinates returned by main_alg; never re-geocode in the backend."""
    query = output.get('query') or {}
    origin = query.get('origin') or {}
    destination = query.get('destination') or {}
    return ({'label': origin_text, 'lat': origin.get('LAT'), 'lon': origin.get('LONG')},
            {'label': destination_text, 'lat': destination.get('LAT'), 'lon': destination.get('LONG')})
