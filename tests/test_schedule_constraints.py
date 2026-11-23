"""Use the same constraint semantics in the planner and final adapter check."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'custom_components/load_optimizer'))
from legacy.app_runtime import schedule_constraints


class ScheduleConstraintTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 19, 23, tzinfo=timezone.utc)
        self.config = {'schedule_latest_finish_entity': 'input_datetime.deadline',
                       'tariff_timezone': 'Europe/London'}
        self.states = {'input_datetime.deadline': {'state': '2026-11-19 04:29:00'}}

    def read(self):
        return schedule_constraints(self.config, self.now, self.states.get)

    def test_old_travel_deadline_is_ignored(self):
        self.assertIsNone(self.read()['latest_finish_utc'])
        self.config['schedule_request_created_at'] = '2026-11-19T16:00:35+00:00'
        self.assertIsNone(self.read()['latest_finish_utc'])

    def test_valid_request_deadline_remains_binding_after_it_passes(self):
        self.config['schedule_request_created_at'] = '2026-11-19T03:00:00+00:00'
        self.assertEqual(self.read()['latest_finish_utc'].hour, 4)

    def test_saved_deadline_survives_cleared_helper_and_cannot_be_extended(self):
        deadline = '2026-11-20T04:00:00+00:00'
        self.config['schedule_request_latest_finish'] = deadline
        self.config['schedule_latest_finish_entity'] = ''
        self.assertEqual(self.read()['latest_finish_utc'].isoformat(), deadline)
        self.config['schedule_latest_finish_entity'] = 'input_datetime.deadline'
        self.states['input_datetime.deadline']['state'] = '2026-11-20T06:00:00+00:00'
        self.assertEqual(self.read()['latest_finish_utc'].isoformat(), deadline)
        self.states['input_datetime.deadline']['state'] = '2026-11-20T02:00:00+00:00'
        self.assertEqual(self.read()['latest_finish_utc'].hour, 2)

    def test_unavailable_and_invalid_helpers_are_distinct_from_stale(self):
        for value in ['unavailable', 'unknown', 'bad date', '']:
            with self.subTest(value=value):
                self.states['input_datetime.deadline']['state'] = value
                self.assertEqual(self.read()['unreadable'], ['input_datetime.deadline'])
        self.states.clear()
        self.assertEqual(self.read()['unreadable'], ['input_datetime.deadline'])

    def test_earliest_start_expires_but_future_value_is_enforced(self):
        self.config['schedule_earliest_start_entity'] = 'input_datetime.earliest'
        self.states['input_datetime.earliest'] = {'state': self.now.isoformat()}
        self.assertIsNone(self.read()['earliest_start_utc'])
        self.states['input_datetime.earliest']['state'] = (self.now + timedelta(hours=1)).isoformat()
        self.assertEqual(self.read()['earliest_start_utc'], self.now + timedelta(hours=1))

    def test_naive_deadline_uses_tariff_timezone_in_summer(self):
        self.now = datetime(2026, 7, 1, 0, tzinfo=timezone.utc)
        self.states['input_datetime.deadline']['state'] = '2026-07-01 07:00:00'
        self.assertEqual(self.read()['latest_finish_utc'].hour, 6)
