"""Keep the teammate's original frontend, powered by the existing provider backend.

The two web projects share one Django process. No HTTP request to a second local
Django server is needed: planner.services imports the backend's provider modules.
"""
from datetime import date
import logging

import requests
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import ALL_MODES, SearchForm
from .services import LocationError, lookup_addresses, resolve_location, search_routes

logger = logging.getLogger(__name__)
SAVED_INPUT_KEYS = {
    "origin", "destination", "travel_date", "adults", "objective",
    "origin_lat", "origin_lon", "destination_lat", "destination_lon",
}


def _saved_inputs(query):
    """Save only known fields; the HTML UI submits repeated 'modes' values."""
    values = {key: str(query.get(key, ""))[:180] for key in SAVED_INPUT_KEYS if key in query}
    values["modes"] = [mode for mode in query.getlist("modes") if mode in ALL_MODES]
    return values


def _initial_from_saved(inputs):
    """Convert saved dates to native date objects for the existing date widget."""
    if not inputs:
        return {"modes": ALL_MODES, "adults": 1, "travel_date": date.today(), "objective": "cost"}
    initial = dict(inputs)
    try:
        initial["travel_date"] = date.fromisoformat(initial.get("travel_date", ""))
    except ValueError:
        initial["travel_date"] = date.today()
    initial.setdefault("adults", 1)
    initial.setdefault("modes", ALL_MODES)
    initial.setdefault("objective", "cost")
    return initial


@never_cache
def home(request):
    """Display the frontend unchanged and prefill the last completed search."""
    initial = _initial_from_saved(request.session.get("planner_saved_inputs", {}))
    return render(request, "planner/home.html", {
        "form": SearchForm(initial=initial),
        "selected_modes": initial.get("modes", ALL_MODES),
        "selected_objective": initial.get("objective", "cost"),
        "has_saved_search": "planner_saved_display" in request.session,
        "active": "home",
    })


def about(request):
    return render(request, "planner/about.html", {"active": "about"})


@never_cache
def results(request):
    """Search enabled providers or restore results without re-scraping."""
    form = SearchForm(request.GET or None)
    context = {"active": "results", "form": form, "routes": [], "notices": [],
               "search_ok": False, "restored": False}
    if not request.GET:
        last = request.session.get("planner_saved_display")
        if last:
            context.update(last)
            context["restored"] = True
        return render(request, "planner/results.html", context)
    if not form.is_valid():
        return render(request, "planner/results.html", context, status=400)

    data = form.cleaned_data
    try:
        origin = resolve_location(data["origin"], data.get("origin_lat"), data.get("origin_lon"))
        destination = resolve_location(data["destination"], data.get("destination_lat"), data.get("destination_lon"))
    except LocationError as exc:
        form.add_error(None, str(exc))
        return render(request, "planner/results.html", context, status=400)

    # The existing provider backend is used through planner.services adapters;
    # no original scraper, sorting, priority, or JSON field is modified.
    routes, notices = search_routes(origin, destination, data["travel_date"],
                                    data["modes"], data["objective"], adults=data["adults"])
    display = {
        "routes": routes,
        "notices": notices,
        "search_ok": True,
        "origin": origin,
        "destination": destination,
        "travel_date": data["travel_date"].isoformat(),
        "travel_date_display": data["travel_date"].strftime("%B %d, %Y"),
        "objective": data["objective"],
        "selected_modes": data["modes"],
        "map_data": {"origin": origin, "destination": destination,
                     "geometry": next((r["geometry"] for r in routes if r.get("geometry")), None)},
    }
    # Django's database-backed session stores the last completed search and the
    # original provider JSON. A returning browser uses its opaque session cookie;
    # IP addresses are NOT used to identify users.
    request.session["planner_saved_inputs"] = _saved_inputs(request.GET)
    request.session["planner_saved_display"] = display
    request.session["planner_saved_json"] = [r["raw_method"] for r in routes if r.get("raw_method") is not None]
    request.session.set_expiry(30 * 24 * 60 * 60)
    context.update(display)
    return render(request, "planner/results.html", context)


@never_cache
@require_GET
def saved_json(request):
    """Download/inspect provider JSON from the last browser session search."""
    response = JsonResponse(request.session.get("planner_saved_json", []), safe=False)
    response["Cache-Control"] = "private, no-store"
    return response


@require_POST
def clear_planner(request):
    """Remove saved inputs, JSON and results for this browser session."""
    # Clear the backend's own saved history too, for a consistent user action.
    request.session.flush()
    return redirect("planner:home")


@require_GET
def addresses(request):
    query = request.GET.get("q", "")[:180].strip()
    if len(query) < 3:
        return JsonResponse({"suggestions": []})
    try:
        return JsonResponse({"suggestions": lookup_addresses(query)})
    except (ValueError, requests.RequestException):
        logger.warning("Autocomplete service unavailable")
        return JsonResponse({"suggestions": [], "error": "Address suggestions are currently unavailable."}, status=503)
