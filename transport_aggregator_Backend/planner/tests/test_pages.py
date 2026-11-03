from datetime import date, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse


class PageTests(SimpleTestCase):
    def test_home_includes_required_ui(self):
        response = self.client.get(reverse("planner:home"))
        self.assertEqual(response.status_code, 200)
        for term in ("All Types", "Car", "Planes", "Trains", "Public Buses", "Greyhound", "Address A", "Address B", "Find My Route"):
            self.assertContains(response, term)
        self.assertContains(response, "Test_logo.png")
        self.assertContains(response, 'id="home-map"')

    def test_about_has_required_description(self):
        response = self.client.get(reverse("planner:about"))
        self.assertContains(response, "Planning a Trip?")
        self.assertContains(response, "Need To Save Money?")
        self.assertContains(response, "Need To Save Time?")
        self.assertContains(response, "Group 3 presents")
        self.assertContains(response, "Plan Your Route")

    def test_results_before_search(self):
        response = self.client.get(reverse("planner:results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Results")

    def test_search_requires_mode(self):
        response = self.client.get(reverse("planner:results"), {
            "origin": "Dallas, Texas", "destination": "Houston, Texas",
            "travel_date": str(date.today()), "objective": "cost",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Select at least one transportation type", status_code=400)

    def test_invalid_past_date(self):
        response = self.client.get(reverse("planner:results"), {
            "origin": "Dallas, Texas", "destination": "Houston, Texas",
            "travel_date": str(date.today() - timedelta(days=1)), "objective": "cost",
            "modes": ["car"],
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Please select today or a future", status_code=400)

    def test_short_autocomplete_does_not_contact_provider(self):
        with patch("planner.views.lookup_addresses") as mock_lookup:
            response = self.client.get(reverse("planner:addresses"), {"q": "LA"})
        self.assertEqual(response.json(), {"suggestions": []})
        mock_lookup.assert_not_called()

    def test_autocomplete_uses_backend(self):
        suggestion = [{"label": "Dallas, Texas", "lat": 32.77, "lon": -96.79}]
        with patch("planner.views.lookup_addresses", return_value=suggestion):
            response = self.client.get(reverse("planner:addresses"), {"q": "Dallas"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"], suggestion)

    def test_selected_mode_only_appears_in_route_results(self):
        route = {
            "mode": "car", "mode_label": "Car", "name": "Drive",
            "source": "Test driving provider", "cost": None, "duration_minutes": 200,
            "departure": "", "arrival": "", "date": str(date.today()),
            "start_name": "Dallas", "end_name": "Houston",
            "distance_miles": 200, "geometry": None, "estimate": True,
        }
        with patch("planner.views.resolve_location", side_effect=[
            {"label": "Dallas", "lat": 32.77, "lon": -96.79},
            {"label": "Houston", "lat": 29.76, "lon": -95.36},
        ]), patch("planner.views.search_routes", return_value=([route], [])) as mock_search:
            response = self.client.get(reverse("planner:results"), {
                "origin": "Dallas", "destination": "Houston", "travel_date": str(date.today()),
                "objective": "time", "modes": ["car"],
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Drive")
        self.assertContains(response, "fare unavailable")
        self.assertEqual(mock_search.call_args.args[3], ["car"])
