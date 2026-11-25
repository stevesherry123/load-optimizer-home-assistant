from copy import deepcopy
import unittest
from dev.replay_estimates import replay_model


def model(values, older=()):
    all_values = [*older, *values]
    return {'recent_cycles': [{'finish': f'2026-11-{i + 1:02d}T00:00:00+00:00',
                              'runtime_minutes': value, 'energy_kwh': value / 100}
                             for i, value in enumerate(values)],
            'statistics': {field: {'count': len(all_values), 'mean': sum(all_values) / len(all_values) / scale}
                           for field, scale in [('runtime_minutes', 1), ('energy_kwh', 100)]}}


class EstimateReplayTests(unittest.TestCase):
    def test_reconstructs_older_history_without_using_the_holdout(self):
        data = model([20] * 5 + [30], older=[10] * 4)
        before = deepcopy(data)
        result = replay_model(data)['metrics']['runtime_minutes']
        self.assertAlmostEqual(result['all_history']['mean_signed_error'], 140 / 9 - 30)
        self.assertEqual(result['recent']['mean_signed_error'], -10)
        self.assertEqual(data, before)

    def test_changing_holdout_changes_actual_error_but_not_prediction(self):
        for actual in (30, 300):
            result = replay_model(model([20] * 5 + [actual]))['metrics']['runtime_minutes']
            self.assertEqual(result['recent']['mean_signed_error'] + actual, 20)
            self.assertEqual(result['all_history']['mean_signed_error'] + actual, 20)

    def test_rejects_nonchronological_or_inconsistent_history(self):
        data = model([20] * 6)
        data['recent_cycles'].reverse()
        with self.assertRaises(ValueError):
            replay_model(data)
        data = model([20] * 6)
        data['statistics']['energy_kwh']['mean'] = 0
        with self.assertRaises(ValueError):
            replay_model(data)

    def test_orders_finish_times_by_actual_instant_not_offset_text(self):
        data = model([20] * 6)
        data['recent_cycles'][0]['finish'] = '2026-10-25T01:10:00+01:00'
        data['recent_cycles'][1]['finish'] = '2026-10-25T01:05:00+00:00'
        self.assertEqual(replay_model(data)['metrics']['runtime_minutes']['holdout_runs'], 1)
        data['recent_cycles'][0]['finish'] = '2026-10-25T01:10:00'
        with self.assertRaises(ValueError):
            replay_model(data)
