"""Normal washing prefers a complete fit without moving the start window."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from legacy.costing import operational_overnight_window, recommend_cycle


class OvernightWindowTests(unittest.TestCase):
    def setUp(self):
        self.reference = datetime(2026, 11, 3, 20, tzinfo=timezone.utc)
        self.models = [{"program": "Eco50", "representative_profile_w": [1000, 1000],
                        "expected_runtime_minutes": 120, "expected_energy_kwh": 2,
                        "confidence": 88, "recent_cycles": []}]
        self.policies = [{"program": "Eco50", "enabled": True,
                          "allow_normal_recommendation": True,
                          "allow_negative_price_run": False, "preference_rank": 50}]
        self.periods = []
        for index in range(48):
            start = self.reference + timedelta(minutes=30 * index)
            self.periods.append({"start": start, "end": start + timedelta(minutes=30),
                                 "price_p_per_kwh": -10 if start.hour >= 6 and start.hour < 15 else 20})

    def plan(self, **kwargs):
        options = {"reference_utc": self.reference, "search_hours": 24,
                   "candidate_interval_minutes": 30, "forecast_hours": 0}
        options.update(kwargs)
        return recommend_cycle(self.models, self.policies, self.periods, **options).get("overnight_recommendation", {})

    def test_fitting_option_wins_over_cheaper_late_finish(self):
        plan = self.plan()
        self.assertLessEqual(datetime.fromisoformat(plan["finish"]), datetime(2026, 11, 4, 7, tzinfo=timezone.utc))
        self.assertEqual(plan["reason"], "best_overnight")

    def test_when_nothing_fits_choose_cheapest_start_inside_window(self):
        plan = self.plan(reference_utc=datetime(2026, 11, 4, 6, tzinfo=timezone.utc))
        self.assertEqual(plan["reason"], "cheapest_start_in_window_late_finish")
        self.assertGreater(datetime.fromisoformat(plan["finish"]), datetime(2026, 11, 4, 7, tzinfo=timezone.utc))
        self.assertLess(datetime.fromisoformat(plan["start"]), datetime(2026, 11, 4, 7, tzinfo=timezone.utc))

    def test_entirely_unpriced_cycle_tail_is_never_free(self):
        self.periods = [period for period in self.periods if period["end"] <= datetime(2026, 11, 4, 7, tzinfo=timezone.utc)]
        plan = self.plan(reference_utc=datetime(2026, 11, 4, 6, tzinfo=timezone.utc))
        self.assertNotEqual(plan.get("status"), "ready")

    def test_persisted_window_cannot_roll_forward_after_expiry(self):
        window = (datetime(2026, 11, 3, 21, tzinfo=timezone.utc), datetime(2026, 11, 4, 7, tzinfo=timezone.utc))
        plan = self.plan(reference_utc=datetime(2026, 11, 4, 12, tzinfo=timezone.utc), overnight_window_utc=window)
        self.assertNotEqual(plan.get("status"), "ready")

    def test_cheapest_eligible_programme_is_selected_without_preference_penalty(self):
        self.models.append({**self.models[0], "program": "Quick45", "expected_energy_kwh": 1,
                            "expected_runtime_minutes": 60})
        self.policies.append({**self.policies[0], "program": "Quick45", "preference_rank": 100})
        self.policies[0]["preference_rank"] = 1
        plan = self.plan(preference_weight_pence=100)
        self.assertEqual(plan["program"], "Quick45")

    def test_local_overnight_window_across_both_clock_changes(self):
        for reference, expected_hours in ((datetime(2026, 3, 28, 12, tzinfo=timezone.utc), 9),
                                          (datetime(2026, 10, 24, 12, tzinfo=timezone.utc), 11)):
            start, end = operational_overnight_window(reference, "21:00", "07:00", "Europe/London")
            self.assertEqual((end - start).total_seconds() / 3600, expected_hours)
