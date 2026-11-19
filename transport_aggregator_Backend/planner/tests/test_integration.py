"""Tests for the current Django -> main_alg boundary.

Legacy tests calling planner.services._plane_routes/_train_routes/_greyhound_routes
are obsolete: routing now belongs to the supplied algorithm only.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


ALGORITHM_RESULT = {
    "query": {
        "origin": {"LAT": 29.9574657, "LONG": -90.0629493},
        "destination": {"LAT": 41.8755616, "LONG": -87.6244212},
    },
    "num_routes": 0,
    "routes": [],
}


class IntegrationTests(TestCase):
    def test_results_page_delegates_to_main_algorithm_with_selected_gps(self):
        query = {
            "origin": "New Orleans, Louisiana",
            "origin_lat": "29.9574657",
            "origin_lon": "-90.0629493",
            "destination": "Chicago, Illinois",
            "destination_lat": "41.8755616",
            "destination_lon": "-87.6244212",
            "travel_date": (date.today() + timedelta(days=4)).isoformat(),
            "objective": "cost", "adults": "1", "modes": ["planes", "greyhound"],
        }
        with patch("planner.views.run_main_algorithm", return_value=ALGORITHM_RESULT) as run:
            response = self.client.get(reverse("planner:results"), query)
        self.assertEqual(response.status_code, 200)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[3], ["planes", "greyhound"])
        self.assertEqual(run.call_args.kwargs["origin_lat"], 29.9574657)
        self.assertEqual(run.call_args.kwargs["destination_lon"], -87.6244212)

    def test_api_returns_unmodified_algorithm_response(self):
        query = {
            "origin": "New Orleans, Louisiana",
            "origin_lat": "29.9574657", "origin_lon": "-90.0629493",
            "destination": "Chicago, Illinois",
            "destination_lat": "41.8755616", "destination_lon": "-87.6244212",
            "travel_date": (date.today() + timedelta(days=4)).isoformat(),
        }
        with patch("planner.api.run_main_algorithm", return_value=ALGORITHM_RESULT) as run:
            response = self.client.get("/api/search/", query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), ALGORITHM_RESULT)
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["objective"], "cost")
        self.assertEqual(run.call_args.args[3], ["planes", "trains", "greyhound"])

    def test_map_options_follow_algorithm_legs_and_survive_restore(self):
        from copy import deepcopy
        raw = deepcopy(ALGORITHM_RESULT)
        start = {"Name": "Origin", "GPS": {"LAT": 29.95, "LONG": -90.06}}
        station = {"Name": "Bus station", "GPS": {"LAT": 30.0, "LONG": -90.1}}
        end = {"Name": "Chicago", "GPS": {"LAT": 41.87, "LONG": -87.62}}
        raw['routes'] = [{
            "rank": 1, "total_cost": 140, "modes": ["Uber", "Bus", "Air"],
            "legs": [
                {"type": "Uber", "from": start, "to": station},
                {"type": "Bus", "from": station, "to": end},
                {"type": "Air", "from": end,
                 "to": {"Name": "Unknown", "GPS": {"LAT": None, "LONG": None}}},
            ],
        }]
        query = {
            "origin": "New Orleans, Louisiana", "destination": "Chicago, Illinois",
            "origin_lat": "29.95", "origin_lon": "-90.06",
            "destination_lat": "41.87", "destination_lon": "-87.62",
            "travel_date": (date.today() + timedelta(days=4)).isoformat(),
            "objective": "cost", "adults": "1", "modes": ["planes", "greyhound"],
        }
        with patch("planner.views.run_main_algorithm", return_value=raw) as run:
            response = self.client.get(reverse("planner:results"), query)
            restored = self.client.get(reverse("planner:results"))
        run.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(self.client.get(reverse("planner:saved_json")).json(), raw)
        for page in (response, restored):
            self.assertContains(page, 'data-map-route="0"')
            self.assertContains(page, 'View 3 itinerary legs')
            legs = page.context['route_map_options'][0]['legs']
            self.assertEqual([leg['mode'] for leg in legs], ['uber', 'bus', 'air'])
            self.assertEqual(legs[1]['origin'], {
                'lat': 30.0, 'lon': -90.1, 'label': 'Bus station'})
            self.assertEqual(legs[1]['destination']['lat'], 41.87)
            self.assertIsNone(legs[2]['destination'])
