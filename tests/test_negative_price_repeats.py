"""Free-price scheduling stays executable, policy-gated and limit-aware."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"
sys.path.insert(0, str(ROOT))
from legacy.costing import recommend_cycle


class NegativePriceRepeatTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 13, 8, 30, tzinfo=timezone.utc)
        self.reference = self.start + timedelta(seconds=54, microseconds=183546)
        self.model = {"program": "Quick45", "representative_profile_w": [100, 100],
                      "expected_runtime_minutes": 28.4, "expected_energy_kwh": 0.7,
                      "confidence": 88, "recent_cycles": []}
        self.policy = {"program": "Quick45", "enabled": True,
                       "allow_normal_recommendation": False, "allow_negative_price_run": True,
                       "preference_rank": 50, "negative_price_priority": 50,
                       "maximum_runs_per_window": 2}
        self.periods = [
            {"start": self.start, "end": self.start + timedelta(hours=1), "price_p_per_kwh": -1},
            {"start": self.start + timedelta(hours=1), "end": self.start + timedelta(hours=3),
             "price_p_per_kwh": -5},
        ]

    def recommend(self, **kwargs):
        options = {"reference_utc": self.reference, "search_hours": 2,
                   "candidate_interval_minutes": 5, "forecast_hours": 0}
        options.update(kwargs)
        return recommend_cycle([self.model], [self.policy], self.periods, **options)

    def test_off_grid_scan_is_ready_now_instead_of_chasing_next_grid_point(self):
        recommendation = self.recommend()["negative_price_recommendation"]
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual(recommendation["start"], self.reference.isoformat())
        self.assertEqual(recommendation["program_options"][0]["start"], recommendation["start"])

    def test_ready_opportunity_is_not_displaced_by_cheaper_future_prices(self):
        recommendation = self.recommend(reference_utc=self.start)["negative_price_recommendation"]
        self.assertEqual(recommendation["start"], self.start.isoformat())
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual(recommendation["energy_cost_pence"], -0.7)

    def test_zero_price_also_allows_an_off_grid_start(self):
        self.periods[0]["price_p_per_kwh"] = 0
        recommendation = self.recommend()["negative_price_recommendation"]
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual(recommendation["energy_cost_pence"], 0)

    def test_future_high_priority_programme_does_not_starve_ready_programme(self):
        later = {**self.model, "program": "Later", "expected_runtime_minutes": 150}
        policies = [self.policy, {**self.policy, "program": "Later", "negative_price_priority": 100}]
        periods = [self.periods[0],
                   {"start": self.start + timedelta(hours=1), "end": self.start + timedelta(hours=2),
                    "price_p_per_kwh": 20},
                   {"start": self.start + timedelta(hours=2), "end": self.start + timedelta(hours=5),
                    "price_p_per_kwh": -5}]
        result = recommend_cycle([self.model, later], policies, periods, reference_utc=self.reference,
                                 search_hours=3, candidate_interval_minutes=5, forecast_hours=0)
        recommendation = result["negative_price_recommendation"]
        self.assertEqual(recommendation["program"], "Quick45")
        self.assertTrue(recommendation["ready_to_start"])

    def test_short_remaining_window_and_positive_now_do_not_start_immediately(self):
        result = self.recommend(reference_utc=self.start + timedelta(hours=2, minutes=50, seconds=54))
        self.assertFalse(result.get("negative_price_recommendation", {}).get("ready_to_start", False))
        self.periods[0]["price_p_per_kwh"] = 20
        recommendation = self.recommend()["negative_price_recommendation"]
        self.assertFalse(recommendation["ready_to_start"])
        self.assertGreater(datetime.fromisoformat(recommendation["start"]), self.reference)

    def test_repeat_bypasses_normal_cooldown_but_counts_against_window_limit(self):
        finish = self.reference + timedelta(minutes=28.4)
        self.model.update(last_seen=finish.isoformat(), recent_cycles=[{
            "finish": finish.isoformat(), "runtime_minutes": 28.4}])
        self.policy.update(allow_normal_recommendation=True, minimum_hours_between_runs=96)
        recommendation = self.recommend(reference_utc=finish + timedelta(minutes=2))["negative_price_recommendation"]
        self.assertTrue(recommendation["ready_to_start"])
        self.assertTrue(recommendation["cooldown_bypassed_for_negative_price"])
        self.assertEqual(recommendation["negative_window_runs"], 1)
        self.assertEqual(recommendation["maximum_runs_per_window"], 2)

    def test_exhausted_limit_remains_explained_when_no_other_programme_is_available(self):
        self.policy["maximum_runs_per_window"] = 1
        finish = self.reference + timedelta(minutes=28.4)
        self.model["recent_cycles"] = [{"finish": finish.isoformat(), "runtime_minutes": 28.4}]
        recommendation = self.recommend(reference_utc=finish + timedelta(minutes=2))["negative_price_recommendation"]
        self.assertEqual(recommendation["reason"], "maximum_runs_per_window_reached")
        self.assertFalse(recommendation["ready_to_start"])

    def test_next_separate_window_has_its_own_allowance(self):
        self.policy["maximum_runs_per_window"] = 1
        self.model["recent_cycles"] = [{"finish": (self.start + timedelta(minutes=30)).isoformat(),
                                        "runtime_minutes": 28.4}]
        self.periods[1] = {"start": self.start + timedelta(hours=1), "end": self.start + timedelta(hours=2),
                           "price_p_per_kwh": 20}
        self.periods.append({"start": self.start + timedelta(hours=2), "end": self.start + timedelta(hours=3),
                             "price_p_per_kwh": 0})
        recommendation = self.recommend(reference_utc=self.reference + timedelta(hours=2))["negative_price_recommendation"]
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual(recommendation["negative_window_runs"], 0)

    def test_other_negative_enabled_programme_can_run_after_first_reaches_limit(self):
        finish = self.reference + timedelta(minutes=28.4)
        self.model["recent_cycles"] = [{"finish": finish.isoformat(), "runtime_minutes": 28.4}]
        self.policy["maximum_runs_per_window"] = 1
        maintenance = {**self.model, "program": "MachineCare", "expected_runtime_minutes": 60,
                       "expected_energy_kwh": 1.2, "recent_cycles": []}
        excluded = {**maintenance, "program": "NormalOnly", "expected_energy_kwh": 5}
        policies = [self.policy, {**self.policy, "program": "MachineCare"},
                    {**self.policy, "program": "NormalOnly", "allow_normal_recommendation": True,
                     "allow_negative_price_run": False}]
        result = recommend_cycle([self.model, maintenance, excluded], policies, self.periods,
                                 reference_utc=finish + timedelta(minutes=2), search_hours=1,
                                 candidate_interval_minutes=5, forecast_hours=0)
        recommendation = result["negative_price_recommendation"]
        self.assertEqual(recommendation["program"], "MachineCare")
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual([item["program"] for item in recommendation["program_options"]], ["MachineCare"])

    def test_immediate_probe_obeys_constraints_full_cycle_blocks_and_permissions(self):
        for changes in (
            {"earliest_start_utc": self.reference + timedelta(minutes=15)},
            {"latest_finish_utc": self.reference + timedelta(minutes=10)},
            {"blocked_windows": [{"start": self.reference + timedelta(minutes=20),
                                  "end": self.reference + timedelta(minutes=40)}]},
            {"excluded_programs": ["Quick45"]},
        ):
            with self.subTest(changes=changes):
                recommendation = self.recommend(**changes).get("negative_price_recommendation", {})
                self.assertFalse(recommendation.get("ready_to_start", False))
        for changes in ({"enabled": False}, {"allow_negative_price_run": False}):
            with self.subTest(changes=changes):
                original = dict(self.policy)
                self.policy.update(changes)
                self.assertFalse(self.recommend().get("negative_price_recommendation", {}).get("ready_to_start", False))
                self.policy = original

    def test_normal_rounding_and_saved_inputs_remain_unchanged(self):
        self.policy.update(allow_normal_recommendation=True, allow_negative_price_run=False)
        self.periods[1]["price_p_per_kwh"] = -1
        before = deepcopy((self.model, self.policy, self.periods))
        result = self.recommend()
        self.assertEqual(result["now_recommendation"]["start"], (self.start + timedelta(minutes=5)).isoformat())
        self.assertFalse(result["negative_price_recommendation"]["ready_to_start"])
        self.assertEqual((self.model, self.policy, self.periods), before)

    def test_truncated_current_window_history_cannot_silently_bypass_a_finite_limit(self):
        self.policy["maximum_runs_per_window"] = 20
        self.model.update(runs=50, last_seen=self.reference.isoformat(), recent_cycles=[{
            "finish": self.reference.isoformat(), "runtime_minutes": 0.5}])
        recommendation = self.recommend()["negative_price_recommendation"]
        self.assertFalse(recommendation["ready_to_start"])
        self.assertEqual(recommendation["reason"], "negative_run_history_incomplete")

    def test_history_before_window_makes_current_count_verifiable(self):
        self.policy["maximum_runs_per_window"] = 20
        self.model.update(runs=50, recent_cycles=[{
            "finish": (self.start - timedelta(hours=1)).isoformat(), "runtime_minutes": 28.4},
            {"finish": self.reference.isoformat(), "runtime_minutes": 0.5}])
        recommendation = self.recommend()["negative_price_recommendation"]
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual(recommendation["negative_window_runs"], 1)

    def test_explicit_unlimited_policy_does_not_acquire_an_implicit_limit(self):
        self.policy["maximum_runs_per_window"] = 0
        self.model.update(runs=50, recent_cycles=[{
            "finish": self.reference.isoformat(), "runtime_minutes": 0.5}])
        self.assertTrue(self.recommend()["negative_price_recommendation"]["ready_to_start"])

    def test_truncated_history_recovers_for_a_later_separate_window(self):
        self.policy["maximum_runs_per_window"] = 20
        self.model.update(runs=50, last_seen=self.reference.isoformat(), recent_cycles=[{
            "finish": self.reference.isoformat(), "runtime_minutes": 0.5}])
        self.periods[1]["price_p_per_kwh"] = 20
        self.periods.append({"start": self.start + timedelta(hours=3), "end": self.start + timedelta(hours=5),
                             "price_p_per_kwh": -1})
        recommendation = self.recommend(reference_utc=self.reference + timedelta(hours=3))["negative_price_recommendation"]
        self.assertTrue(recommendation["ready_to_start"])
        self.assertEqual(recommendation["negative_window_runs"], 0)

    def test_stale_last_seen_cannot_override_retained_current_window_completions(self):
        self.policy["maximum_runs_per_window"] = 20
        self.model.update(runs=50, last_seen=(self.start - timedelta(days=1)).isoformat(), recent_cycles=[{
            "finish": self.reference.isoformat(), "runtime_minutes": 0.5}])
        recommendation = self.recommend()["negative_price_recommendation"]
        self.assertEqual(recommendation["reason"], "negative_run_history_incomplete")

    def test_native_and_compatibility_costing_copies_are_identical(self):
        self.assertEqual((ROOT / "legacy/costing.py").read_bytes(),
                         (ROOT / "optimizer/tariffs.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
