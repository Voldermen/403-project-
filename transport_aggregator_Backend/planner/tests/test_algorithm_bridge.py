"""Offline regression tests: no live scrapers, geocoding, or provider requests."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import shutil
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from planner.algorithm_bridge import (
    AlgorithmUnavailable, AlgorithmLocationError, RESULT_MARKER, present_algorithm_routes,
    run_main_algorithm, selected_exclusions,
)

ROUTE = {
    'query': {'origin': {'LAT': 32.5, 'LONG': -92.6},
              'destination': {'LAT': 39.7, 'LONG': -104.9}},
    'num_routes': 1,
    'routes': [{'rank': 1, 'total_cost': 100.0, 'currency': 'USD',
                'total_time_min': 240, 'departure': '2027-01-04T08:00',
                'arrival': '2027-01-04T12:00', 'num_legs': 2,
                'modes': ['Uber', 'Bus'],
                'legs': [{'leg_number': 1, 'type': 'Uber', 'name': 'Uber Ride',
                          'cost': 8.73, 'departure': '2027-01-04T08:00',
                          'arrival': '2027-01-04T08:10', 'duration_min': 10,
                          'wait_before_min': 0, 'from': {'Name': 'Start'},
                          'to': {'Name': 'Station'}},
                         {'leg_number': 2, 'type': 'Bus', 'name': 'Greyhound',
                          'cost': 91.27, 'departure': '2027-01-04T08:10',
                          'arrival': '2027-01-04T12:00', 'duration_min': 230,
                          'wait_before_min': 0, 'from': {'Name': 'Station'},
                          'to': {'Name': 'End'}}]}],
}

class BridgeTests(SimpleTestCase):
    def test_unchecked_modes_are_only_translated_to_exclusions(self):
        self.assertEqual(selected_exclusions(['planes']), ['train', 'bus'])
        self.assertEqual(selected_exclusions(['planes', 'trains', 'greyhound']), None)
        with self.assertRaises(ValueError):
            selected_exclusions(['public_buses'])

    def test_presenter_preserves_rank_cost_duration_and_legs(self):
        result = present_algorithm_routes(ROUTE)
        self.assertEqual(result[0]['rank'], 1)
        self.assertEqual(result[0]['cost'], 100.0)
        self.assertEqual(result[0]['duration_minutes'], 240)
        self.assertEqual(result[0]['mode_label'], 'Uber + Bus')
        self.assertEqual([leg['type'] for leg in result[0]['legs']], ['Uber', 'Bus'])
        self.assertTrue(result[0]['estimated_uber'])
        self.assertTrue(result[0]['legs'][0]['estimated_fare'])
        self.assertFalse(result[0]['legs'][1]['estimated_fare'])
        self.assertIn('estimated Uber fares', result[0]['source'])
        self.assertIn('estimated fare', result[0]['legs'][0]['name'])
        # Display projection never changes the route amount or mode order.
        self.assertEqual(result[0]['cost'], ROUTE['routes'][0]['total_cost'])


    def test_uber_only_route_keeps_algorithm_cost_and_estimation_label(self):
        sample = {
            'routes': [{
                'rank': 1, 'total_cost': 237.45, 'total_time_min': 190,
                'modes': ['Uber'], 'legs': [{
                    'type': 'Uber', 'name': 'Uber Ride', 'cost': 237.45,
                    'duration_min': 190, 'from': {'Name': 'Start'},
                    'to': {'Name': 'End'},
                }],
            }],
        }
        displayed = present_algorithm_routes(sample)[0]
        self.assertEqual(displayed['mode_label'], 'Uber')
        self.assertEqual(displayed['cost'], 237.45)
        self.assertEqual(displayed['legs'][0]['cost'], 237.45)
        self.assertTrue(displayed['estimated_uber'])
        self.assertIn('not live quotes', displayed['source'])

    def test_itinerary_without_uber_has_no_estimate_flag(self):
        sample = {'routes': [{
            'rank': 1, 'total_cost': 30, 'modes': ['Bus'],
            'legs': [{'type': 'Bus', 'cost': 30, 'from': {'Name': 'A'},
                      'to': {'Name': 'B'}}],
        }]}
        displayed = present_algorithm_routes(sample)[0]
        self.assertFalse(displayed['estimated_uber'])
        self.assertEqual(displayed['mode_label'], 'Bus')
        self.assertFalse(displayed['legs'][0]['estimated_fare'])

    def test_missing_real_datasets_is_explicit(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / 'Algorithm').mkdir()
            (Path(tmp) / 'Algorithm' / 'main_alg.py').write_text('')
            with override_settings(BASE_DIR=Path(tmp)):
                with self.assertRaisesRegex(AlgorithmUnavailable, 'cleaned_greyhound.csv'):
                    run_main_algorithm('A', 'B', date.today(), ['planes'])

    def test_single_subprocess_calls_main_alg_with_mapped_args(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Algorithm').mkdir()
            (root / 'Algorithm' / 'main_alg.py').write_text('# teammate source')
            for name in ('airports_database/cleaned_airport.csv',
                         'greyhound_database/cleaned_greyhound.csv',
                         'amtrack_database/cleaned_amtrack.csv'):
                target = root / 'data' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('stop_id,stop_lat,stop_lon\n')
            fake_process = SimpleNamespace(returncode=0, stdout=RESULT_MARKER + json.dumps(ROUTE), stderr='')
            with override_settings(BASE_DIR=root), patch('planner.algorithm_bridge.subprocess.run', return_value=fake_process) as run:
                result = run_main_algorithm('123 Main St, Ruston, LA 71270', 'Denver, CO',
                                            date(2027, 1, 4), ['planes'], objective='time',
                                            start_time='8:00 am')
            self.assertEqual(result, ROUTE)
            self.assertEqual(run.call_count, 1)
            command = run.call_args.args[0]
            self.assertIn('import main_alg as teammate_algorithm', command[2])
            self.assertIn('result = teammate_algorithm.main_alg(', command[2])
            params = json.loads(command[3])
            self.assertEqual(params['objective'], 'duration')
            self.assertEqual(params['exclude'], ['train', 'bus'])
            self.assertEqual(params['start_time'], '8:00 am')
            self.assertEqual(params['num_paths'], 3)
            self.assertIsNone(params['origin_coords'])
            self.assertIsNone(params['destination_coords'])

    def test_selected_coords_avoid_geocoder_in_real_child_process(self):
        """City labels may reach main_alg while GPS is supplied by the backend."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            algorithm_dir = root / 'Algorithm'
            algorithm_dir.mkdir()
            stub = '''def get_lat_long(*args):
    raise AssertionError('The geocoder must not run when GPS was supplied')

def main_alg(origin, destination, day, **kwargs):
    start = get_lat_long(origin, None, None, None)
    end = get_lat_long(destination, None, None, None)
    return {'query': {'origin': {'LAT': start[0], 'LONG': start[1]},
                      'destination': {'LAT': end[0], 'LONG': end[1]}},
            'routes': [], 'inputs': [origin, destination]}
'''
            (algorithm_dir / 'main_alg.py').write_text(stub, encoding='utf-8')
            for name in ('airports_database/cleaned_airport.csv',
                         'greyhound_database/cleaned_greyhound.csv',
                         'amtrack_database/cleaned_amtrack.csv'):
                target = root / 'data' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('stub')
            with override_settings(BASE_DIR=root):
                result = run_main_algorithm(
                    'New Orleans, Louisiana', 'Chicago, Illinois', date(2027, 1, 4),
                    ['planes', 'trains', 'greyhound'],
                    origin_lat=29.9574657, origin_lon=-90.0629493,
                    destination_lat=41.8755616, destination_lon=-87.6244212,
                )
            self.assertEqual(result['query']['origin'], {'LAT': 29.9574657, 'LONG': -90.0629493})
            self.assertEqual(result['query']['destination'], {'LAT': 41.8755616, 'LONG': -87.6244212})
            self.assertEqual(result['inputs'], ['New Orleans, Louisiana', 'Chicago, Illinois'])
            self.assertEqual((algorithm_dir / 'main_alg.py').read_text(), stub)

    def test_full_address_falls_back_to_supplied_algorithm_geocoder(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            algorithm_dir = root / 'Algorithm'
            algorithm_dir.mkdir()
            (algorithm_dir / 'main_alg.py').write_text('''def get_lat_long(street, city, state, zip_code):
    return (1.0, -1.0) if 'Ruston' in street else (2.0, -2.0)

def main_alg(origin, destination, day, **kwargs):
    start = get_lat_long(origin, None, None, None)
    end = get_lat_long(destination, None, None, None)
    return {'query': {'origin': start, 'destination': end}, 'routes': []}
''')
            for name in ('airports_database/cleaned_airport.csv',
                         'greyhound_database/cleaned_greyhound.csv',
                         'amtrack_database/cleaned_amtrack.csv'):
                target = root / 'data' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('stub')
            with override_settings(BASE_DIR=root):
                result = run_main_algorithm('123 Main St, Ruston, LA 71270',
                                            '100 Main St, Denver, CO 80203',
                                            date(2027, 1, 4), ['planes'])
            self.assertEqual(result['query']['origin'], [1.0, -1.0])
            self.assertEqual(result['query']['destination'], [2.0, -2.0])

    def test_reject_missing_and_nonfinite_coordinate_values(self):
        from planner.algorithm_bridge import _validated_coordinates
        with self.assertRaisesRegex(ValueError, 'requires both'):
            _validated_coordinates(29.9, None, 'Origin')
        with self.assertRaisesRegex(ValueError, 'valid GPS range'):
            _validated_coordinates(float('nan'), -90, 'Origin')
        with self.assertRaisesRegex(ValueError, 'valid GPS range'):
            _validated_coordinates(100, -90, 'Origin')

    def test_bad_street_geocoder_returns_helpful_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            algorithm_dir = root / 'Algorithm'
            algorithm_dir.mkdir()
            (algorithm_dir / 'main_alg.py').write_text('''def get_lat_long(*args):
    return None, None

def main_alg(origin, destination, day, **kwargs):
    get_lat_long(origin, None, None, None)
    return {'routes': []}
''')
            for name in ('airports_database/cleaned_airport.csv',
                         'greyhound_database/cleaned_greyhound.csv',
                         'amtrack_database/cleaned_amtrack.csv'):
                target = root / 'data' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('stub')
            with override_settings(BASE_DIR=root):
                with self.assertRaisesRegex(AlgorithmLocationError, 'origin coordinates'):
                    run_main_algorithm('123 Main St, Ruston, LA 71270',
                                       '100 Main St, Denver, CO 80203',
                                       date(2027, 1, 4), ['planes'])


class WebTests(TestCase):
    def test_results_and_saved_json_use_one_algorithm_call(self):
        with patch('planner.views.run_main_algorithm', return_value=ROUTE) as algorithm:
            response = self.client.get(reverse('planner:results'), {
                'origin': '1000 E Georgia Ave, Ruston, LA 71272',
                'destination': '1301 Pennsylvania St, Denver, CO 80203',
                'travel_date': (date.today() + timedelta(days=5)).isoformat(),
                'adults': 1, 'objective': 'time', 'modes': ['planes', 'greyhound'],
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'View 2 itinerary legs')
            self.assertContains(response, 'Greyhound')
            self.assertEqual(algorithm.call_count, 1)
            self.assertContains(response, 'not live Uber quotes')
            self.assertEqual(algorithm.call_args.args[3], ['planes', 'greyhound'])
            self.assertEqual(self.client.get(reverse('planner:saved_json')).json(), ROUTE)
            self.assertContains(self.client.get(reverse('planner:results')), 'Restored your last completed search')
            self.assertEqual(algorithm.call_count, 1)
        self.client.post(reverse('planner:clear_planner'))
        self.assertEqual(self.client.get(reverse('planner:saved_json')).json(), {})

    def test_city_suggestion_search_forwards_gps_from_web_and_api(self):
        params = {
            'origin': 'New Orleans, Louisiana',
            'origin_lat': 29.9574657, 'origin_lon': -90.0629493,
            'destination': 'Chicago, Illinois',
            'destination_lat': 41.8755616, 'destination_lon': -87.6244212,
            'travel_date': (date.today() + timedelta(days=5)).isoformat(),
            'adults': 1, 'objective': 'cost',
            'modes': ['planes', 'trains', 'greyhound'],
        }
        with patch('planner.views.run_main_algorithm', return_value=ROUTE) as algorithm:
            response = self.client.get(reverse('planner:results'), params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(algorithm.call_args.kwargs['origin_lat'], 29.9574657)
            self.assertEqual(algorithm.call_args.kwargs['destination_lon'], -87.6244212)
        with patch('planner.api.run_main_algorithm', return_value=ROUTE) as algorithm:
            response = self.client.get('/api/search/', params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(algorithm.call_args.kwargs['origin_lon'], -90.0629493)
            self.assertEqual(algorithm.call_args.kwargs['destination_lat'], 41.8755616)

    def test_missing_city_gps_returns_validation_error_before_algorithm(self):
        with patch('planner.views.run_main_algorithm') as algorithm:
            response = self.client.get(reverse('planner:results'), {
                'origin': 'New Orleans, Louisiana', 'destination': 'Chicago, Illinois',
                'travel_date': (date.today() + timedelta(days=5)).isoformat(),
                'modes': ['planes'], 'objective': 'cost', 'adults': 1,
            })
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, 'Select a location from the autocomplete suggestions',
                                status_code=400)
            algorithm.assert_not_called()

    def test_api_returns_exact_output_and_never_calls_separate_provider(self):
        with patch('planner.api.run_main_algorithm', return_value=ROUTE) as algorithm:
            response = self.client.get('/api/search/', {
                'origin': '1000 E Georgia Ave, Ruston, LA 71272',
                'destination': '1301 Pennsylvania St, Denver, CO 80203',
                'travel_date': (date.today() + timedelta(days=5)).isoformat(),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), ROUTE)
            self.assertEqual(algorithm.call_count, 1)
            self.assertEqual(algorithm.call_args.args[3], ['planes', 'trains', 'greyhound'])
            self.assertEqual(self.client.get('/api/flights/').status_code, 410)
