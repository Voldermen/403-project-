"""Server-rendered pages and small address-autocomplete JSON endpoint."""
import logging
import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from .forms import ALL_MODES, SearchForm
from .services import LocationError, lookup_addresses, resolve_location, search_routes

logger = logging.getLogger(__name__)


def home(request):
    form = SearchForm(initial={"modes": ALL_MODES})
    return render(request, "planner/home.html", {"form": form, "active": "home"})


def about(request):
    return render(request, "planner/about.html", {"active": "about"})


def results(request):
    form = SearchForm(request.GET or None)
    context = {"active": "results", "form": form, "routes": [], "notices": [], "search_ok": False}
    if not request.GET:
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
    routes, notices = search_routes(origin, destination, data["travel_date"], data["modes"], data["objective"])
    context.update({
        "routes": routes,
        "notices": notices,
        "search_ok": True,
        "origin": origin,
        "destination": destination,
        "travel_date": data["travel_date"],
        "objective": data["objective"],
        "selected_modes": data["modes"],
        "map_data": {
            "origin": origin, "destination": destination,
            "geometry": next((route["geometry"] for route in routes if route.get("geometry")), None),
        },
    })
    return render(request, "planner/results.html", context)


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
