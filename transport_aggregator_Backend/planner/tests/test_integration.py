"""Offline integration tests: no live Google Flights, Amtrak or Greyhound calls."""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from planner.services import _plane_routes, _train_routes, _greyhound_routes

FUTURE = (date.today() + timedelta(days=4)).isoformat()
ORIGIN = {"label": "New Orleans, Louisiana", "lat": 29.95, "lon": -90.08}
DEST = {"label": "Chicago, Illinois", "lat": 41.88, "lon": -87.64}


def backend_record(mode="Air", cost=140, priority=1):
    return {"Method": {
        "Type": mode, "Priority": priority, "Cost": cost,
        "Travel Time (min)": 195, "Departure": "9:00", "Arrival": "12:15",
        "Date": "11/16/2026",
        "Staring Location": {"City": "New Orleans", "Name": "MSY", "GPS": {"LAT": 29.99, "LONG": -90.25}},
        "Destination": {"City": "Chicago", "Name": "ORD", "GPS": {"LAT": 41.97, "LONG": -87.90}},
    }}


class FrontendConnectionTests(TestCase):
    @patch("planner.views.search_routes")
    @patch("planner.views.resolve_location")
    def test_browser_restores_original_json_and_form_without_provider_calls(self, resolve, search):
        resolve.side_effect = [ORIGIN, DEST]
        raw = backend_record()
        display = {
            "mode": "planes", "mode_label": "Planes", "name": "Flight", "source": "Google Flights scraper",
            "cost": 140, "duration_minutes": 195, "departure": "9:00", "arrival": "12:15",
            "date": "11/16/2026", "start_name": "MSY", "end_name": "ORD",
            "distance_miles": None, "geometry": None, "estimate": False, "raw_method": raw, "priority": 1,
        }
        search.return_value = ([display], [])
        response = self.client.get(reverse("planner:results"), {
            "origin": ORIGIN["label"], "destination": DEST["label"], "travel_date": FUTURE,
            "adults": 2, "objective": "cost", "modes": ["planes"],
            "origin_lat": ORIGIN["lat"], "origin_lon": ORIGIN["lon"],
            "destination_lat": DEST["lat"], "destination_lon": DEST["lon"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(search.call_args.kwargs["adults"], 2)
        self.assertEqual(self.client.get(reverse("planner:saved_json")).json(), [raw])
        restored = self.client.get(reverse("planner:results"))
        self.assertContains(restored, "Restored your last completed search")
        self.assertContains(restored, "$140")
        self.assertEqual(search.call_count, 1)
        self.assertContains(self.client.get(reverse("planner:home")), 'value="2"')

        # A different browser must not see this browser's saved search.
        from django.test import Client
        self.assertEqual(Client().get(reverse("planner:saved_json")).json(), [])

    @patch("planner.views.search_routes", return_value=([], []))
    @patch("planner.views.resolve_location", side_effect=[ORIGIN, DEST])
    def test_clear_session_removes_saved_provider_json(self, resolve, search):
        self.client.get(reverse("planner:results"), {
            "origin": "New Orleans", "destination": "Chicago", "travel_date": FUTURE,
            "modes": ["car"], "adults": 1,
        })
        self.assertIn("planner_saved_display", self.client.session)
        self.client.post(reverse("planner:clear_planner"))
        self.assertEqual(self.client.get(reverse("planner:saved_json")).json(), [])
        self.assertNotIn("planner_saved_display", self.client.session)


class BackendAdapterTests(TestCase):
    @patch("google_flights_scraper.search_flights")
    @patch("planner.services.nearest_airport", side_effect=["MSY", "ORD"])
    def test_frontend_flies_using_original_backend_without_priority_changes(self, nearest, search):
        search.return_value = [backend_record()]
        rows, notice = _plane_routes(ORIGIN, DEST, date.fromisoformat(FUTURE), adults=2)
        self.assertIsNone(notice)
        self.assertEqual(search.call_args.kwargs["adults"], 2)
        self.assertEqual(rows[0]["priority"], 1)
        self.assertEqual(rows[0]["raw_method"], backend_record())

    @patch("routes.amtrak_adapter.search_amtrak")
    def test_frontend_train_uses_original_backend_amtrak_adapter(self, search):
        search.return_value = [backend_record("Rail", None, 2)]
        rows, notice = _train_routes(ORIGIN, DEST, date.fromisoformat(FUTURE))
        self.assertEqual(rows[0]["mode"], "trains")
        self.assertIsNone(rows[0]["cost"])
        self.assertEqual(rows[0]["departure"], "9:00")
        self.assertIsNone(notice)

    @patch("routes.greyhound_adapter.search_greyhound")
    def test_frontend_greyhound_uses_original_adapter(self, search):
        search.return_value = [backend_record("Bus", 44, 99)]
        rows, notice = _greyhound_routes(
            {"label": "Dallas, TX"}, {"label": "Houston, TX"}, date.fromisoformat(FUTURE))
        self.assertEqual(rows[0]["cost"], 44)
        self.assertEqual(rows[0]["priority"], 99)
        self.assertIsNone(notice)


class GreyhoundCityLookupTests(TestCase):
    """Unit tests use mocked city lookups; no live provider requests are made."""

    def test_city_extraction_from_street_and_state(self):
        from planner.greyhound_cities import city_from_label
        self.assertEqual(city_from_label("123 Main St, New Orleans, Louisiana, 70130"), "New Orleans")
        self.assertEqual(city_from_label("Chicago, IL, United States"), "Chicago")
        self.assertEqual(city_from_label("Dallas, TX"), "Dallas")

    @patch("planner.greyhound_cities.requests.get")
    def test_lookup_uses_provider_uuid_and_nearby_coordinates(self, get):
        from django.core.cache import cache
        from planner.greyhound_cities import resolve_greyhound_city
        cache.clear()
        example_id = "22222222-2222-4222-8222-222222222222"
        get.return_value.json.return_value = [
            {"id": "11111111-1111-4111-8111-111111111111", "name": "New Orleans",
             "country": {"code": "US"}, "location": {"lat": 33.0, "lon": -90.1}},
            {"id": example_id, "name": "New Orleans, LA", "country": {"code": "US"},
             "location": {"lat": 29.95, "lon": -90.08}},
        ]
        place = {"label": "New Orleans, Louisiana", "lat": 29.95, "lon": -90.08}
        self.assertEqual(resolve_greyhound_city(place), example_id)
        self.assertEqual(resolve_greyhound_city(place), example_id)  # cached
        get.assert_called_once()

    @patch("planner.greyhound_cities.requests.get")
    def test_wrong_city_or_missing_coordinates_does_not_pick_random_provider(self, get):
        from django.core.cache import cache
        from planner.greyhound_cities import resolve_greyhound_city, GreyhoundCityError
        cache.clear()
        get.return_value.json.return_value = [
            {"id": "11111111-1111-4111-8111-111111111111", "name": "New Orleans",
             "country": {"code": "US"}, "location": {"lat": 33.0, "lon": -90.1}},
        ]
        with self.assertRaises(GreyhoundCityError):
            resolve_greyhound_city({"label": "New Orleans, Louisiana", "lat": 29.95, "lon": -90.08})

    @patch("routes.greyhound_adapter.search_greyhound")
    @patch("planner.greyhound_cities.resolve_greyhound_city")
    def test_automatic_city_mapping_uses_original_backend(self, resolver, search):
        resolver.side_effect = ["11111111-1111-4111-8111-111111111111",
                                "22222222-2222-4222-8222-222222222222"]
        search.return_value = [backend_record("Bus", 55, 99)]
        rows, notice = _greyhound_routes(ORIGIN, DEST, date.fromisoformat(FUTURE))
        self.assertIsNone(notice)
        self.assertEqual(rows[0]["cost"], 55)
        self.assertEqual(rows[0]["priority"], 99)
        self.assertEqual(search.call_args.args[0], "11111111-1111-4111-8111-111111111111")

    @patch("routes.greyhound_adapter.search_greyhound")
    def test_greyhound_multiple_travelers_declined_clearly(self, search):
        rows, notice = _greyhound_routes(ORIGIN, DEST, date.fromisoformat(FUTURE), adults=2)
        self.assertEqual(rows, [])
        self.assertIn("one adult only", notice)
        search.assert_not_called()
