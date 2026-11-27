"""Regression for heating pulses lost by sparse point sampling."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components/load_optimizer'))
from legacy.app_runtime import update_program_model, program_summary, profile_energy_kwh, bootstrap_program_models, compact_profile_data
from legacy.minute_profile import capture, forecast, validate, segments, program_options
from legacy.costing import _profile_segments, estimate_cycle_cost, _negative_power_window_fit


def cycle(index=0, duration=266):
    points = [{'offset_seconds': second, 'power_w': 2400 if 600 <= second < 1200 or 6000 <= second < 6600 else 3.5}
              for second in range(0, duration * 60 + 1, 60)]
    return {'program': 'Eco50', 'start': (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat(),
            'finish': (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index, minutes=duration)).isoformat(),
            'runtime_minutes': duration, 'energy_kwh': profile_energy_kwh(points),
            'energy_sensor_delta_kwh': profile_energy_kwh(points), 'power_profile': points,
            'sample_count': len(points), 'energy_source': 'power_profile', 'peak_power': 2400}


class MinuteProfileTests(unittest.TestCase):
    def test_sparse_grid_cannot_erase_second_heating_pulse(self):
        instance = {}
        for index in range(5): update_program_model(instance, cycle(index))
        summary = program_summary('Eco50', instance['program_models']['Eco50'])
        self.assertEqual(summary['power_profile_basis'], 'minute_energy_v1')
        parts = _profile_segments(summary)
        self.assertGreater(max(s['power_w'] for s in parts if 6000 <= s['offset_start'] < 6600), 2300)
        total = sum((s['offset_end'] - s['offset_start']) * s['power_w'] / 3600000 for s in parts)
        self.assertAlmostEqual(total, summary['expected_energy_kwh'], places=9)
        self.assertEqual(parts[-1]['offset_end'], summary['expected_runtime_minutes'] * 60)
        chart = compact_profile_data(instance['program_models'], cycle(4))['program_profiles'][0]
        self.assertEqual(chart['power_profile_basis'], 'minute_energy_v1')
        self.assertLessEqual(len(chart['points']), 360)
        self.assertGreater(max(y for x, y in chart['points'] if 99 <= x <= 111), 1000)

    def test_partial_final_minute_and_duration_alignment_conserve_energy(self):
        raw = {'power_profile': [{'offset_seconds': 0, 'power_w': 1000}, {'offset_seconds': 90, 'power_w': 1000}],
               'runtime_minutes': 1.5, 'energy_kwh': .025}
        profile = capture(raw)
        self.assertEqual(profile['energy_wh'], [16.666667, 8.333333])
        output = forecast([profile] * 5, 123, .05)
        self.assertEqual(len(output['energy_wh']), 3)
        self.assertAlmostEqual(sum(output['energy_wh']), 50, places=5)
        parts = segments(output, .05)
        self.assertEqual(parts[-1]['offset_end'] - parts[-1]['offset_start'], 3)
        self.assertAlmostEqual(sum((p['offset_end'] - p['offset_start']) * p['power_w'] / 3600000 for p in parts), .05)

    def test_missing_duplicate_invalid_and_long_gap_captures_never_invent_energy(self):
        for mutation in ('gap', 'duplicate', 'nan', 'negative', 'missing_start', 'excluded', 'changed_options', 'counter_only'):
            with self.subTest(mutation=mutation):
                record = cycle()
                if mutation == 'gap': del record['power_profile'][10:14]
                if mutation == 'duplicate': record['power_profile'][1]['offset_seconds'] = 0
                if mutation == 'nan': record['power_profile'][1]['power_w'] = float('nan')
                if mutation == 'negative': record['power_profile'][1]['power_w'] = -1
                if mutation == 'missing_start': record['power_profile'].pop(0)
                if mutation == 'excluded': record['learning_excluded'] = True
                if mutation == 'changed_options': record['program_options_changed'] = True
                if mutation == 'counter_only': record['energy_kwh'] = 2
                self.assertIsNone(capture(record))
        self.assertFalse(validate({'version': 1, 'duration_seconds': 60, 'energy_wh': [float('inf')]}))
        self.assertFalse(validate({'version': 1, 'duration_seconds': 60, 'energy_wh': [1, 2]}))

    def test_upgrade_recovers_only_exact_retained_capture_and_preserves_history(self):
        instance = {}
        for index in range(5): update_program_model(instance, cycle(index))
        instance['last_cycle'] = cycle(4)
        model = instance['program_models']['Eco50']
        for row in model['recent_cycles']: row.pop('minute_energy_profile', None)
        old_stats = copy.deepcopy(model['statistics'])
        old_count = model['runs']
        bootstrap_program_models({'instances': {'1': instance}})
        summary = program_summary('Eco50', model)
        self.assertEqual(summary['power_profile_basis'], 'legacy_point_fallback')
        self.assertEqual(summary['minute_profile_sample_count'], 1)
        self.assertEqual(model['runs'], old_count)
        self.assertEqual(model['statistics'], old_stats)
        self.assertTrue(model['recent_cycles'][-1]['minute_profile_recovered_from_last_capture'])
        for index in range(5, 9): update_program_model(instance, cycle(index))
        before = copy.deepcopy(instance)
        self.assertEqual(program_summary('Eco50', model)['power_profile_basis'], 'minute_energy_v1')
        self.assertEqual(instance, before)

    def test_second_heating_phase_affects_price_and_negative_window_eligibility(self):
        instance = {}
        for index in range(5): update_program_model(instance, cycle(index))
        summary = program_summary('Eco50', instance['program_models']['Eco50'])
        start = datetime(2026, 1, 10, tzinfo=timezone.utc)
        split = start + timedelta(minutes=90)
        periods = [{'start': start, 'end': split, 'price_p_per_kwh': -10},
                   {'start': split, 'end': start + timedelta(hours=24), 'price_p_per_kwh': 50}]
        self.assertGreater(estimate_cycle_cost(start, summary, periods)['energy_cost_pence'], 10)
        self.assertFalse(_negative_power_window_fit(start, summary, periods)['fits'])
        all_free = [{'start': start, 'end': start + timedelta(hours=24), 'price_p_per_kwh': -10}]
        self.assertTrue(_negative_power_window_fit(start, summary, all_free)['fits'])
        corrupt = {**summary, 'minute_energy_profile': {**summary['minute_energy_profile'], 'duration_seconds': 60}}
        with self.assertRaises(ValueError): _profile_segments(corrupt)

    def test_option_metadata_is_bounded_and_different_settings_block_profile_promotion(self):
        key = 'Dishcare.Dishwasher.Option.ExtraDry'
        snapshot = program_options({'attributes': {'program_options': {key: {'value': True},
            'access_token': 'private', 'Dishcare.Dishwasher.Option.Private': 'private'}}})
        self.assertEqual(snapshot, {'status': 'observed', 'values': {key: True}})
        instance = {}
        for index in range(5):
            record = cycle(index)
            record['program_options'] = snapshot if index == 4 else {'status': 'not_exposed', 'values': {}}
            update_program_model(instance, record)
        summary = program_summary('Eco50', instance['program_models']['Eco50'])
        self.assertEqual(summary['minute_profile_fallback_reason'], 'programme_option_metadata_differs')
        self.assertEqual(summary['power_profile_basis'], 'legacy_point_fallback')
