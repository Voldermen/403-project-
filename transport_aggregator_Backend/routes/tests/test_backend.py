"""No external HTTP in these tests; provider calls are mocked."""
from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from routes.algorithms import recommend_routes, sort_by_price

FUTURE = (date.today() + timedelta(days=7)).isoformat()
FORM = {"origin": "MSY", "destination": "ORD", "travel_date": FUTURE, "adults": 1}


def route(mode="Air", cost=200, priority=1, start="New Orleans", end="Chicago"):
    return {"Method": {
        "Type": mode, "Priority": priority, "Cost": cost,
        "Travel Time (min)": 175, "Departure": "3:15", "Arrival": "6:10",
        "Date": "11/5/2026",
        "Staring Location": {"City": start, "Name": "TEST", "GPS": {"LAT": 1.0, "LONG": 2.0}},
        "Destination": {"City": end, "Name": "TEST", "GPS": {"LAT": 3.0, "LONG": 4.0}},
    }}


class AlgorithmTests(SimpleTestCase):
    def test_sorted_prices_keep_mode_priority(self):
        rows = sort_by_price([route(cost=300), route(cost=100), route(cost=None, mode="Rail", priority=2)])
        self.assertEqual([x["Method"]["Cost"] for x in rows], [100, 300, None])
        self.assertEqual([x["Method"]["Priority"] for x in rows], [1, 1, 2])

    def test_unpriced_rail_is_not_recommended_as_cheapest(self):
        rows = [route(cost=200), route(mode="Rail", cost=None, priority=2)]
        self.assertEqual(recommend_routes(rows)["cheapest"]["Method"]["Cost"], 200)


class ApiAndPersistenceTests(TestCase):
    @patch("routes.services.search_flights")
    def test_flight_json_exact_format_and_saved_results(self, flight):
        flight.return_value = [route(cost=250), route(cost=180)]
        resp = self.client.get(reverse("flights_api"), FORM)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([x["Method"]["Cost"] for x in resp.json()], [180, 250])
        self.assertEqual(set(resp.json()[0]["Method"]), set(route()["Method"]))
        self.assertEqual(self.client.get(reverse("saved_api")).json()["latest"]["result"]["routes"][0]["Method"]["Cost"], 180)
        self.assertEqual(flight.call_count, 1)
        # Loading saved results on a new request MUST NOT run the scraper again.
        home = self.client.get(reverse("home"))
        self.assertContains(home, "Restored your last completed search")
        self.assertContains(home, "$180")
        self.assertEqual(flight.call_count, 1)

    @patch("routes.services.search_flights")
    def test_amtrak_and_greyhound_merge_with_matching_cities(self, flight):
        flight.return_value = [route(cost=210)]
        with patch("routes.services.search_amtrak", return_value=[route(mode="Rail", cost=None, priority=2)]), \
             patch("routes.services.search_greyhound", return_value=[route(mode="Bus", cost=99, priority=99)]):
            resp = self.client.get(reverse("search_api"), {**FORM,
                "include_train": "on", "train_origin": "NOL", "train_destination": "CHI",
                "include_bus": "on", "bus_origin": "54f13a66-59ee-41d4-b017-e4240add0403",
                "bus_destination": "364040d5-ebfc-4628-b7b0-13e2377203c6"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([r["Method"]["Type"] for r in resp.json()["routes"]], ["Bus", "Air", "Rail"])
        self.assertEqual([r["Method"]["Priority"] for r in resp.json()["routes"]], [99, 1, 2])

    @patch("routes.services.search_flights")
    def test_unrelated_bus_is_not_compared_with_flight(self, flight):
        flight.return_value = [route(cost=200)]
        with patch("routes.services.search_greyhound", return_value=[route(mode="Bus", cost=40, start="Dallas", end="Houston")]):
            resp = self.client.get(reverse("search_api"), {**FORM,
                "include_bus": "on", "bus_origin": "54f13a66-59ee-41d4-b017-e4240add0403",
                "bus_destination": "364040d5-ebfc-4628-b7b0-13e2377203c6"})
        self.assertEqual([r["Method"]["Cost"] for r in resp.json()["routes"]], [200])
        self.assertEqual([r["Method"]["Cost"] for r in resp.json()["unmatched_routes"]], [40])
        self.assertEqual(resp.json()["providers"]["buses"]["status"], "different_route")

    @patch("routes.services.search_flights")
    def test_draft_persists_and_clear_erases_it(self, flight):
        draft = {**FORM, "origin": "DFW", "destination": "IAH"}
        resp = self.client.post(reverse("save_draft_api"), draft)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get(reverse("saved_api")).json()["draft"]["origin"], "DFW")
        flight.return_value = [route(cost=100, start="Dallas", end="Houston")]
        self.client.get(reverse("search_api"), {**FORM, "origin": "DFW", "destination": "IAH"})
        self.client.post(reverse("clear_saved_api"))
        self.assertIsNone(self.client.get(reverse("saved_api")).json()["latest"])
        self.assertEqual(self.client.get(reverse("saved_api")).json()["draft"], {})

    @patch("routes.services.search_flights")
    def test_browser_sessions_are_isolated(self, flight):
        from django.test import Client
        flight.return_value = [route(cost=123)]
        self.client.get(reverse("search_api"), FORM)
        stranger = Client()
        self.assertIsNone(stranger.get(reverse("saved_api")).json()["latest"])
        self.assertNotIn("request_ip", str(self.client.get(reverse("saved_api")).json()))

    def test_invalid_date_gets_400(self):
        self.assertEqual(self.client.get(reverse("search_api"), {**FORM, "travel_date": "2000-01-01"}).status_code, 400)

    @patch("routes.services.search_flights")
    def test_bus_failure_does_not_block_flights(self, flight):
        flight.return_value = [route(cost=100)]
        with patch("routes.services.search_greyhound", side_effect=ValueError("One adult only")):
            resp = self.client.get(reverse("search_api"), {**FORM,
                "include_bus": "on", "bus_origin": "54f13a66-59ee-41d4-b017-e4240add0403",
                "bus_destination": "364040d5-ebfc-4628-b7b0-13e2377203c6"})
        self.assertEqual(resp.json()["providers"]["buses"]["status"], "error")
        self.assertEqual(resp.json()["routes"][0]["Method"]["Cost"], 100)
