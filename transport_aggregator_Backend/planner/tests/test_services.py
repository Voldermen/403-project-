"""Autocomplete-only tests. Route selection is owned by Algorithm/main_alg.py."""
from unittest.mock import patch

from django.test import SimpleTestCase

from planner.services import lookup_addresses


class AddressAutocompleteTests(SimpleTestCase):
    def test_short_query_does_not_call_photon(self):
        with patch("planner.services.requests.get") as get:
            self.assertEqual(lookup_addresses("NY"), [])
        get.assert_not_called()

    def test_us_suggestions_include_coordinates_and_exclude_other_countries(self):
        features = [
            {"properties": {"countrycode": "us", "name": "Chicago", "city": "Chicago", "state": "Illinois"},
             "geometry": {"coordinates": [-87.6244212, 41.8755616]}},
            {"properties": {"countrycode": "ca", "name": "Toronto"},
             "geometry": {"coordinates": [-79.38, 43.65]}},
        ]
        with patch("planner.services.cache") as cache, patch("planner.services.requests.get") as get:
            cache.get.return_value = None
            get.return_value.json.return_value = {"features": features}
            result = lookup_addresses("Chicago")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["lat"], 41.8755616)
        self.assertEqual(result[0]["lon"], -87.6244212)
        self.assertIn("Chicago", result[0]["label"])
        cache.set.assert_called_once()
        get.assert_called_once()
