"""JSON API: thin input/output wrapper for Algorithm/main_alg.main_alg()."""
from datetime import date
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from .forms import ALL_MODES, SearchForm
from .algorithm_bridge import AlgorithmUnavailable, AlgorithmLocationError, run_main_algorithm
from .algorithm_version import algorithm_revision, discard_outdated_results

@never_cache
@require_GET
def search_api(request):
    discard_outdated_results(request)
    parameters = request.GET.copy()
    # A caller without mode filters requests all three supported modes.
    if 'modes' not in parameters:
        parameters.setlist('modes', ALL_MODES)
    if 'adults' not in parameters:
        parameters['adults'] = '1'
    # The original JSON API treated an omitted objective as lowest cost.
    # Form initial values are not applied to a bound request query.
    if 'objective' not in parameters:
        parameters['objective'] = 'cost'
    form = SearchForm(parameters)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    values = form.cleaned_data
    departure = (values['start_time'].strftime('%I:%M %p').lstrip('0').lower()
                 if values.get('start_time') else '12:01 am')
    try:
        output = run_main_algorithm(
            values['origin'], values['destination'], values['travel_date'],
            values['modes'], objective=values['objective'], start_time=departure,
            origin_lat=values.get('origin_lat'), origin_lon=values.get('origin_lon'),
            destination_lat=values.get('destination_lat'),
            destination_lon=values.get('destination_lon'),
        )
    except AlgorithmLocationError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except AlgorithmUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    inputs = {
        'origin': values['origin'], 'destination': values['destination'],
        'travel_date': values['travel_date'].isoformat(),
        'objective': values['objective'], 'modes': values['modes'],
        'origin_lat': values.get('origin_lat'), 'origin_lon': values.get('origin_lon'),
        'destination_lat': values.get('destination_lat'),
        'destination_lon': values.get('destination_lon'),
    }
    history = request.session.get('search_history', [])
    request.session['search_history'] = [
        {'inputs': inputs, 'result': output, 'saved_at': timezone.now().isoformat()}, *history,
    ][:3]
    request.session['planner_saved_json'] = output
    request.session['planner_algorithm_revision'] = algorithm_revision()
    request.session.set_expiry(30 * 24 * 60 * 60)
    return JsonResponse(output)

@require_GET
def flights_api(request):
    return JsonResponse({'error': ('This separate direct-provider endpoint was retired. '
                                   'Use /api/search/?modes=planes to call main_alg().')}, status=410)

@never_cache
@require_GET
def saved_api(request):
    discard_outdated_results(request)
    try:
        index = int(request.GET.get('index', '0'))
    except ValueError:
        return JsonResponse({'error': 'index must be 0, 1 or 2'}, status=400)
    history = request.session.get('search_history', [])
    if index not in (0, 1, 2):
        return JsonResponse({'error': 'index must be 0, 1 or 2'}, status=400)
    return JsonResponse({
        'draft': request.session.get('saved_draft', {}),
        'latest': history[index] if index < len(history) else None,
        'history': [{'inputs': rec['inputs'], 'saved_at': rec['saved_at']}
                    for rec in history],
    })

@require_POST
def save_draft_api(request):
    allowed = {'origin', 'destination', 'travel_date', 'adults', 'objective', 'start_time'}
    request.session['saved_draft'] = {
        key: str(request.POST[key])[:180] for key in allowed if key in request.POST
    }
    request.session.set_expiry(30 * 24 * 60 * 60)
    return JsonResponse({'saved': True})

@require_POST
def clear_saved(request):
    request.session.flush()
    return JsonResponse({'cleared': True}) if request.path.startswith('/api/') else redirect('planner:home')
