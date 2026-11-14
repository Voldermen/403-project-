"""Web, JSON and saved-state endpoints. Save by anonymous browser session, not IP."""
from datetime import date
import ipaddress
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .forms import SearchForm
from .services import aggregate_routes, display_route

# Session data is stored SERVER-SIDE in SQLite via django.contrib.sessions.
# Browser receives an opaque, HttpOnly session cookie, never the stored JSON.
DRAFT_FIELDS = {"origin", "destination", "travel_date", "adults",
                "include_train", "train_origin", "train_destination",
                "include_bus", "bus_origin", "bus_destination"}


def initial_values(request):
    initial = {"origin": "MSY", "destination": "ORD", "adults": 1, "travel_date": date.today()}
    from_server = request.session.get("saved_draft") or request.session.get("saved_inputs") or {}
    initial.update(from_server)
    return initial


def _browser_values(data):
    """JSON-serializable strings and checkboxes; never store arbitrary POST keys."""
    result = {}
    for key in DRAFT_FIELDS:
        if key in ("include_train", "include_bus"):
            result[key] = str(data.get(key, "")).lower() in ("on", "true", "1", "yes")
        elif key in data:
            result[key] = str(data[key])[:100]
    return result


def _save_result(request, values, result):
    """Persist latest completed search and up to three past searches on the server."""
    inputs = _browser_values({key: value.isoformat() if isinstance(value, date) else value
                              for key, value in values.items()})
    record = {"inputs": inputs, "result": result, "saved_at": timezone.now().isoformat()}
    # Diagnostic metadata stays in the private server session; never return it
    # with the saved JSON and NEVER look up users by an IP address.
    # Ignore untrusted X-Forwarded-For; proxy setups need separate configuration.
    try:
        request.session["last_request_ip"] = str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        request.session["last_request_ip"] = None
    # Keep at most three completed searches to avoid unbounded database growth.
    prior = request.session.get("search_history", [])
    request.session["search_history"] = [record, *prior][:3]
    request.session["saved_inputs"] = inputs
    request.session["saved_draft"] = inputs
    request.session.set_expiry(30 * 24 * 60 * 60)


def _view_context(form, result=None, restored=False):
    context = {"form": form, "today": date.today().isoformat(), "restored": restored}
    if result is not None:
        context.update({
            "searched": True,
            "routes": [display_route(row) for row in result.get("routes", [])],
            "unmatched_routes": [display_route(row) for row in result.get("unmatched_routes", [])],
            "providers": result.get("providers", {}),
            "recommendations": {
                label: display_route(row) for label, row in result.get("recommendations", {}).items()
            },
        })
    return context


@never_cache
@require_http_methods(["GET", "POST"])
def home(request):
    """On return, restore last search and form from the DB-backed session."""
    if request.method == "POST":
        request.session["saved_draft"] = _browser_values(request.POST)
        form = SearchForm(request.POST)
        if form.is_valid():
            result = aggregate_routes(form.cleaned_data)
            _save_result(request, form.cleaned_data, result)
            return render(request, "routes/home.html", _view_context(form, result))
        return render(request, "routes/home.html", _view_context(form))
    form = SearchForm(initial=initial_values(request))
    saved = request.session.get("search_history", [])
    return render(request, "routes/home.html",
                  _view_context(form, saved[0]["result"] if saved else None, restored=bool(saved)))


@never_cache
@require_GET
def search_api(request):
    """GET /api/search/ returns all requested providers and saves search in session."""
    form = SearchForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    result = aggregate_routes(form.cleaned_data)
    _save_result(request, form.cleaned_data, result)
    return JsonResponse(result)


@never_cache
@require_GET
def flights_api(request):
    """GET /api/flights/ keeps the exact original flight-array response format."""
    form = SearchForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    values = {**form.cleaned_data, "include_train": False, "include_bus": False}
    result = aggregate_routes(values)
    if result["providers"]["flights"]["status"] == "error":
        return JsonResponse({"error": "Google Flights is currently unavailable."}, status=502)
    _save_result(request, values, result)
    return JsonResponse(result["routes"], safe=False)


@never_cache
@require_GET
def saved_api(request):
    """Frontend restores its own saved inputs/results without calling providers."""
    history = request.session.get("search_history", [])
    # ?index=1 or ?index=2 retrieves an older completed JSON search.
    try:
        index = int(request.GET.get("index", "0"))
    except ValueError:
        return JsonResponse({"error": "index must be an integer from 0 to 2"}, status=400)
    if not 0 <= index <= 2:
        return JsonResponse({"error": "index must be between 0 and 2"}, status=400)
    return JsonResponse({
        "draft": request.session.get("saved_draft", {}),
        "latest": history[index] if index < len(history) else None,
        "history": [
            {"inputs": rec["inputs"], "saved_at": rec["saved_at"]}
            for rec in history
        ],
    })


@never_cache
@require_POST
def save_draft_api(request):
    """Called while typing; saves fields, NOT a new live search."""
    request.session["saved_draft"] = _browser_values(request.POST)
    request.session.set_expiry(30 * 24 * 60 * 60)
    return JsonResponse({"saved": True})


@never_cache
@require_POST
def clear_saved(request):
    """Delete this browser session and its server-side JSON/search history."""
    request.session.flush()
    if request.path.startswith("/api/"):
        return JsonResponse({"cleared": True})
    return redirect("home")
