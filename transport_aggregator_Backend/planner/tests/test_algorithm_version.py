"""Tests that saved results from previous algorithms are never displayed."""
from django.test import TestCase, override_settings, SimpleTestCase
from django.urls import reverse
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from planner.algorithm_version import algorithm_revision, discard_outdated_results
from planner.algorithm_bridge import AlgorithmUnavailable, run_main_algorithm

class StaleResultTests(TestCase):
    def test_outdated_results_cleared_on_home(self):
        session = self.client.session
        session['planner_saved_display'] = {'search_ok': True, 'routes': [
            {'name': 'Old walking route'}]}
        session['planner_saved_json'] = {'routes': [{'modes': ['Walking']}]}
        session['planner_saved_inputs'] = {'origin': 'New Orleans', 'destination': 'Chicago'}
        session['planner_algorithm_revision'] = 'outdated'
        session.save()
        response = self.client.get(reverse('planner:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('planner_saved_display', self.client.session)
        self.assertNotIn('planner_saved_json', self.client.session)
        self.assertIn('planner_saved_inputs', self.client.session)

    def test_current_results_remain_available(self):
        session = self.client.session
        session['planner_saved_display'] = {'search_ok': True, 'routes': []}
        session['planner_algorithm_revision'] = algorithm_revision()
        session.save()
        response = self.client.get(reverse('planner:results'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Restored your last completed search')

class LegacyAlgorithmTests(SimpleTestCase):
    def test_old_walking_algorithm_returns_actionable_error(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'Algorithm').mkdir()
            (root / 'Algorithm' / 'main_alg.py').write_text('def add_walking_connections(): pass')
            with override_settings(BASE_DIR=root):
                with self.assertRaisesMessage(AlgorithmUnavailable, 'older walking-only'):
                    run_main_algorithm('A', 'B', '2027-01-04', ['planes'])
