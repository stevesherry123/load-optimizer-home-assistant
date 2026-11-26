"""Prediction behavior across a historical change, without rewriting history."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components/load_optimizer'))
from legacy.app_runtime import program_summary, update_program_model, planning_window_end, estimated_cycle_finish
from legacy.costing import _profile_segments


class RecentPredictionTests(unittest.TestCase):
    def model(self):
        instance = {}
        for index in range(25):
            duration, energy = (220, .7) if index < 20 else (266, .94)
            update_program_model(instance, {
                'program': 'Eco50', 'finish': (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat(),
                'runtime_minutes': duration, 'energy_kwh': energy, 'peak_power': 2400,
                'sample_count': 3, 'energy_source': 'power_profile',
                'power_profile': [{'offset_seconds': 0, 'power_w': 20},
                                  {'offset_seconds': duration * 30, 'power_w': 2400},
                                  {'offset_seconds': duration * 60, 'power_w': 2}],
            })
        return instance['program_models']['Eco50']

    def test_changed_regime_uses_recent_duration_energy_and_shape_without_mutation(self):
        model = self.model()
        before = copy.deepcopy(model)
        summary = program_summary('Eco50', model)
        self.assertEqual(summary['expected_runtime_minutes'], 266)
        self.assertEqual(summary['expected_energy_kwh'], .94)
        self.assertEqual(summary['prediction_sample_count'], 5)
        self.assertLess(summary['lifetime_runtime_minutes'], 266)
        segments = _profile_segments(summary)
        self.assertAlmostEqual(segments[-1]['offset_end'], 266 * 60)
        self.assertAlmostEqual(sum((p['offset_end'] - p['offset_start']) * p['power_w'] / 3600000 for p in segments), .94)
        self.assertEqual(model, before)

    def test_calendar_tail_and_running_finish_use_the_same_prediction(self):
        model = self.model()
        start = datetime(2026, 11, 26, tzinfo=timezone.utc)
        instance = {'program_models': {'Eco50': model}, 'program': 'Eco50', 'cycle_start': start.isoformat()}
        horizon = planning_window_end({'cost_search_hours': 24, 'cost_forecast_hours': 12}, instance, start)
        self.assertEqual(horizon, start + timedelta(hours=24, minutes=266))
        finish, _ = estimated_cycle_finish(instance)
        self.assertEqual(datetime.fromisoformat(finish), start + timedelta(minutes=266))

    def test_fallback_for_insufficient_duplicate_or_invalid_evidence(self):
        model = self.model()
        for changes in ('few', 'duplicate', 'invalid', 'excluded', 'naive'):
            with self.subTest(changes=changes):
                sample = copy.deepcopy(model)
                sample['recent_cycles'] = sample['recent_cycles'][-5:]
                if changes == 'few': sample['recent_cycles'].pop()
                if changes == 'duplicate': sample['recent_cycles'][0]['finish'] = sample['recent_cycles'][1]['finish']
                if changes == 'invalid': sample['recent_cycles'][0]['energy_kwh'] = float('nan')
                if changes == 'excluded': sample['recent_cycles'][0]['learning_excluded'] = True
                if changes == 'naive': sample['recent_cycles'][0]['finish'] = '2026-01-01T00:00:00'
                self.assertEqual(program_summary('Eco50', sample)['prediction_basis'], 'lifetime_fallback')

    def test_predictions_are_chronological_and_not_affected_by_current_holdout(self):
        model = self.model()
        model['recent_cycles'] = list(reversed(model['recent_cycles']))
        predicted = program_summary('Eco50', model)
        # Current actual is not an input until learning accepts the completion.
        actual_duration = 280
        self.assertEqual(predicted['expected_runtime_minutes'], 266)
        self.assertEqual(actual_duration - predicted['expected_runtime_minutes'], 14)
