"""Web pages use exclusively Algorithm/main_alg.py to compute travel routes."""
from datetime import date
from math import isfinite
import logging
import requests
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from .forms import ALL_MODES, SearchForm
from .algorithm_bridge import (AlgorithmUnavailable, AlgorithmLocationError, run_main_algorithm,
                               present_algorithm_routes, map_locations)
from .services import lookup_addresses
from .algorithm_version import algorithm_revision, discard_outdated_results

logger = logging.getLogger(__name__)
SAVED_INPUT_KEYS = {
    'origin', 'destination', 'travel_date', 'adults', 'objective', 'start_time',
    'origin_lat', 'origin_lon', 'destination_lat', 'destination_lon',
}

def _saved_inputs(query):
    values = {key: str(query.get(key, ''))[:180] for key in SAVED_INPUT_KEYS if key in query}
    values['modes'] = [mode for mode in query.getlist('modes') if mode in ALL_MODES]
    return values

def _initial_from_saved(inputs):
    if not inputs:
        return {'modes': ALL_MODES, 'adults': 1, 'travel_date': date.today(), 'objective': 'cost'}
    initial = dict(inputs)
    try:
        initial['travel_date'] = date.fromisoformat(initial.get('travel_date', ''))
    except ValueError:
        initial['travel_date'] = date.today()
    initial.setdefault('adults', 1)
    initial.setdefault('modes', ALL_MODES)
    initial.setdefault('objective', 'cost')
    return initial

@never_cache
def home(request):
    discard_outdated_results(request)
    initial = _initial_from_saved(request.session.get('planner_saved_inputs', {}))
    return render(request, 'planner/home.html', {
        'form': SearchForm(initial=initial),
        'selected_modes': initial.get('modes', ALL_MODES),
        'selected_objective': initial.get('objective', 'cost'),
        'has_saved_search': 'planner_saved_display' in request.session,
        'active': 'home',
    })

def about(request):
    return render(request, 'planner/about.html', {'active': 'about'})

def _map_point(location):
    location = location or {}
    gps = location.get("GPS") or {}
    try:
        lat, lon = float(gps["LAT"]), float(gps["LONG"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return {"lat": lat, "lon": lon,
                "label": location.get("Name") or location.get("City") or "Trip location"}
    return None


def _route_map_options(raw):
    """Project map data in the algorithm's itinerary/leg order without reranking."""
    options = []
    for route in raw.get("routes", []):
        legs = [{"mode": str(leg.get("type", "")).casefold(),
                 "origin": _map_point(leg.get("from")),
                 "destination": _map_point(leg.get("to")),
                 "geometry": None}
                for leg in route.get("legs", [])]
        options.append({"legs": legs})
    return options


@never_cache
def results(request):
    discard_outdated_results(request)
    form = SearchForm(request.GET or None)
    context = {'active': 'results', 'form': form, 'routes': [], 'notices': [],
               'search_ok': False, 'restored': False}
    if not request.GET:
        previous = request.session.get('planner_saved_display')
        if previous:
            context.update(previous)
            context['restored'] = True
            context['route_map_options'] = _route_map_options(
                request.session.get('planner_saved_json', {}))
        return render(request, 'planner/results.html', context)
    if not form.is_valid():
        return render(request, 'planner/results.html', context, status=400)

    data = form.cleaned_data
    departure = (data['start_time'].strftime('%I:%M %p').lstrip('0').lower()
                 if data.get('start_time') else '12:01 am')
    try:
        raw = run_main_algorithm(
            data['origin'], data['destination'], data['travel_date'],
            data['modes'], objective=data['objective'], start_time=departure,
            num_paths=3,
            origin_lat=data.get('origin_lat'), origin_lon=data.get('origin_lon'),
            destination_lat=data.get('destination_lat'),
            destination_lon=data.get('destination_lon'),
        )
    except AlgorithmLocationError as exc:
        form.add_error(None, str(exc))
        return render(request, 'planner/results.html', context, status=400)
    except AlgorithmUnavailable as exc:
        form.add_error(None, str(exc))
        return render(request, 'planner/results.html', context, status=503)
    origin, destination = map_locations(raw, data['origin'], data['destination'])
    displayed_routes = present_algorithm_routes(raw)
    notices = []
    if any(route['estimated_uber'] for route in displayed_routes):
        notices.append(
            'Uber ride prices and travel times are estimates generated by the route algorithm, '
            'not live Uber quotes. Route totals include those estimated fares; actual prices '
            'and pickup times may vary.'
        )
    display = {
        'routes': displayed_routes,
        'notices': notices, 'search_ok': True,
        'origin': origin, 'destination': destination,
        'travel_date': data['travel_date'].isoformat(),
        'travel_date_display': data['travel_date'].strftime('%B %d, %Y'),
        'objective': data['objective'], 'selected_modes': data['modes'],
        'map_data': {'origin': origin, 'destination': destination, 'geometry': None},
    }
    request.session['planner_saved_inputs'] = _saved_inputs(request.GET)
    request.session['planner_saved_display'] = display
    # Keep the provided algorithm's full source JSON, including legs and ranking.
    request.session['planner_saved_json'] = raw
    request.session['planner_algorithm_revision'] = algorithm_revision()
    request.session.set_expiry(30 * 24 * 60 * 60)
    context.update(display)
    context["route_map_options"] = _route_map_options(raw)
    return render(request, 'planner/results.html', context)

@never_cache
@require_GET
def saved_json(request):
    discard_outdated_results(request)
    response = JsonResponse(request.session.get('planner_saved_json', {}))
    response['Cache-Control'] = 'private, no-store'
    return response

@require_POST
def clear_planner(request):
    request.session.flush()
    return redirect('planner:home')

@require_GET
def addresses(request):
    query = request.GET.get('q', '')[:180].strip()
    if len(query) < 3:
        return JsonResponse({'suggestions': []})
    try:
        return JsonResponse({'suggestions': lookup_addresses(query)})
    except (ValueError, requests.RequestException):
        logger.warning('Autocomplete service unavailable')
        return JsonResponse({'suggestions': [], 'error': 'Address suggestions are currently unavailable.'}, status=503)
