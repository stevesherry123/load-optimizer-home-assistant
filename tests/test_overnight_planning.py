"""Whole-night coverage, independent of tariff publication time or slot count."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from legacy.app_runtime import overnight_planning_coverage, publish_cost_entities
from unittest.mock import patch


class OvernightPlanningTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)
        self.config = {"schedule_overnight_start": "20:00", "schedule_overnight_end": "07:00",
                       "tariff_timezone": "Europe/London", "cost_search_hours": 18}
        self.models = [{"program": "Quick65", "expected_runtime_minutes": 51},
                       {"program": "Eco50", "expected_runtime_minutes": 244}]
        self.policies = [{"program": p["program"], "enabled": True, "allow_normal_recommendation": True}
                         for p in self.models]

    def periods(self, first, last):
        return [{"start": first + timedelta(minutes=30 * i),
                 "end": first + timedelta(minutes=30 * (i + 1)), "price_p_per_kwh": 25}
                for i in range(int((last - first).total_seconds() / 1800))]

    def check(self, periods, **kwargs):
        return overnight_planning_coverage(self.config, self.models, self.policies, periods, self.now, **kwargs)

    def test_late_publication_requires_whole_night_but_not_whole_tomorrow(self):
        midnight = datetime(2026, 10, 13, 23, tzinfo=timezone.utc)
        initial = self.periods(self.now, midnight - timedelta(hours=1))
        self.assertFalse(self.check(initial)["complete"])
        # Tomorrow's final slots are absent, but all overnight starts and tails are priced.
        complete = self.periods(self.now, midnight + timedelta(hours=23))
        self.assertTrue(self.check(complete)["complete"])
        self.assertEqual(self.check(complete)["required_end"], "2026-10-14T10:04:00+00:00")

    def test_gaps_conflicts_nonfinite_prices_and_missing_cycle_tails_fail_closed(self):
        end = self.now + timedelta(hours=24)
        periods = self.periods(self.now, end)
        self.assertTrue(self.check(periods + periods)["complete"])
        for broken in (periods[:20] + periods[21:], periods[:30],
                       periods + [{**periods[20], "price_p_per_kwh": 99}],
                       periods[:20] + [{**periods[20], "price_p_per_kwh": float("nan")}] + periods[21:]):
            self.assertFalse(self.check(broken)["complete"])

    def test_deadline_clips_tail_and_short_search_is_explained(self):
        deadline = datetime(2026, 10, 14, 6, tzinfo=timezone.utc)
        self.assertTrue(self.check(self.periods(self.now, deadline), latest=deadline)["complete"])
        self.config["cost_search_hours"] = 6
        coverage = self.check(self.periods(self.now, self.now + timedelta(hours=48)))
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["reason"], "overnight_search_horizon_incomplete")

    def test_disabled_long_programmes_do_not_extend_coverage(self):
        self.policies[1]["allow_normal_recommendation"] = False
        coverage = self.check(self.periods(self.now, self.now + timedelta(hours=17)))
        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["required_end"], "2026-10-14T06:51:00+00:00")

    def test_dst_nights_use_actual_utc_coverage(self):
        for day in (datetime(2026, 10, 24, 15, tzinfo=timezone.utc),
                    datetime(2026, 3, 28, 15, tzinfo=timezone.utc)):
            self.now = day
            coverage = self.check(self.periods(day, day + timedelta(hours=30)))
            self.assertTrue(coverage["complete"])
            first = datetime.fromisoformat(coverage["window_start"])
            last = datetime.fromisoformat(coverage["window_end"])
            self.assertEqual((last - first).total_seconds() / 3600, 12 if day.month == 10 else 10)

    def test_coverage_published_on_the_same_recommendation_as_the_plan(self):
        coverage = self.check(self.periods(self.now, self.now + timedelta(hours=24)))
        rows = {}
        def capture(_token, entity, value, attributes):
            rows[entity] = attributes
        result = {"status": "ready", "start": self.now, "finish": self.now + timedelta(hours=1),
                  "overnight_planning_coverage": coverage,
                  "overnight_recommendation": {"status": "ready", "program": "Eco50"}}
        with patch("legacy.app_runtime.publish_entity", side_effect=capture):
            publish_cost_entities("test", "sensor.synthetic", "Synthetic", result)
        self.assertEqual(rows["sensor.synthetic_overnight_recommendation"]["overnight_planning_coverage"], coverage)
