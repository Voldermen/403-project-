from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase
from planner.services import LocationError, normalize_legacy, resolve_location, search_routes


class ServiceTests(SimpleTestCase):
    def test_normalize_flight_fare_and_spelling(self):
        record = {"Method": {
            "Type": "Air", "Cost": 125.5, "Travel Time (min)": 60,
            "Staring Location": {"Name": "MSY"}, "Destination": {"Name": "ORD"},
        }}
        out = normalize_legacy(record, "planes", "test")
        self.assertEqual(out["cost"], 125.5)
        self.assertEqual(out["start_name"], "MSY")
        self.assertEqual(out["end_name"], "ORD")

    def test_null_train_fare_is_not_free(self):
        record = {"Method": {"Type": "Rail", "Cost": None, "Travel Time (min)": 90}}
        self.assertIsNone(normalize_legacy(record, "trains", "test")["cost"])

    def test_greyhound_schema(self):
        record = {"method": {"info": {"Name": "Greyhound", "Cost": 35},
                  "starting_location": {"Name": "A"}, "destination": {"Name": "B"}}}
        self.assertEqual(normalize_legacy(record, "greyhound", "test")["cost"], 35)

    def test_coordinate_input(self):
        self.assertEqual(resolve_location("32.77, -96.79")["lat"], 32.77)
        with self.assertRaises(LocationError):
            resolve_location("-20, 10")

    def test_excluded_providers_are_not_called(self):
        record = {"mode": "car", "cost": None, "duration_minutes": 40}
        with patch("planner.services.PROVIDERS", {
            "car": lambda *args: [record],
            "planes": lambda *args: self.fail("disabled provider called"),
        }):
            result, notices = search_routes({"lat": 30, "lon": -90}, {"lat": 31, "lon": -90}, date.today(), ["car"])
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(notices, [])

    def test_cost_ranking_puts_missing_prices_last(self):
        car = {"mode": "car", "cost": None, "duration_minutes": 60}
        bus = {"mode": "greyhound", "cost": 29, "duration_minutes": 100}
        with patch("planner.services.PROVIDERS", {"car": lambda *args: [car], "greyhound": lambda *args: [bus]}):
            rows, _ = search_routes({}, {}, date.today(), ["car", "greyhound"], objective="cost")
        self.assertEqual([r["mode"] for r in rows], ["greyhound", "car"])
