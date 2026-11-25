"""Needed washing and profitable extra runs have different financial eligibility."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from legacy.app_runtime import normalise_program_policy
from legacy.costing import apply_operating_costs, estimate_cycle_cost, recommend_cycle
from legacy.config_validation import ConfigurationError, validate_appliance_options


class TotalBenefitTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 3, 22, tzinfo=timezone.utc)
        self.model = {"program": "Eco50", "representative_profile_w": [1000, 1000],
                      "expected_runtime_minutes": 60, "expected_energy_kwh": 1,
                      "confidence": 88, "recent_cycles": []}
        self.policy = {"program": "Eco50", "enabled": True,
                       "allow_normal_recommendation": True, "allow_negative_price_run": True,
                       "preference_rank": 50}

    def periods(self, price):
        return [{"start": self.start, "end": self.start + timedelta(hours=12),
                 "price_p_per_kwh": price}]

    def plan(self, price, **costs):
        policy = normalise_program_policy({**self.policy, **costs})
        return recommend_cycle([self.model], [policy], self.periods(price),
                               reference_utc=self.start, search_hours=2,
                               candidate_interval_minutes=30, forecast_hours=1)

    def test_five_pence_credit_with_ten_pence_costs_cannot_authorise_extra_run(self):
        result = self.plan(-5, consumables_cost_pence=10)
        self.assertEqual(result["negative_price_recommendation"]["reason"], "no_positive_net_benefit")
        normal = result["overnight_recommendation"]
        self.assertEqual(normal["status"], "ready")
        self.assertEqual(normal["cost_pence"], 5)
        self.assertFalse(normal["negative_price_run"])
        self.assertEqual(normal["net_benefit_pence"], -5)

    def test_every_configured_cost_is_included_in_net_return(self):
        result = self.plan(-10, fixed_cost_pence=1, consumables_cost_pence=2,
                           water_litres=8, water_cost_pence_per_litre=0.25, wear_cost_pence=3)
        extra = result["negative_price_recommendation"]
        self.assertTrue(extra["ready_to_start"])
        self.assertEqual(extra["net_benefit_pence"], 2)
        self.assertEqual(extra["operating_cost_breakdown"]["water_cost_pence"], 2)
        self.assertEqual(extra["unconfigured_costs"], [])

    def test_any_positive_return_qualifies_before_display_rounding(self):
        extra = self.plan(-0.000001)["negative_price_recommendation"]
        self.assertTrue(extra["positive_net_benefit"])
        self.assertTrue(extra["ready_to_start"])
        self.assertEqual(round(extra["cost_pence"], 4), 0)
        self.assertGreater(extra["net_benefit_pence"], 0)

    def test_tiny_loss_and_exact_break_even_do_not_qualify(self):
        for consumables in (0.000001, 0):
            with self.subTest(consumables=consumables):
                extra = self.plan(0, consumables_cost_pence=consumables)["negative_price_recommendation"]
                self.assertFalse(extra["ready_to_start"])
                self.assertEqual(extra["reason"], "no_positive_net_benefit")

    def test_decimal_component_costs_do_not_create_a_phantom_credit(self):
        self.model["expected_energy_kwh"] = 0.3
        result = self.plan(-1, fixed_cost_pence=0.1, wear_cost_pence=0.2)
        self.assertEqual(result["total_cost_pence"], 0)
        self.assertFalse(result["positive_net_benefit"])
        self.assertFalse(result["negative_price_recommendation"]["ready_to_start"])
        result = self.plan(-1, water_litres=3, water_cost_pence_per_litre=0.1)
        self.assertEqual(result["total_cost_pence"], 0)
        self.assertFalse(result["positive_net_benefit"])

    def test_repeating_profile_fractions_do_not_create_a_phantom_profit(self):
        self.model["representative_profile_w"] = [1000, 1000, 1000, 1000]
        periods = [{"start": self.start + timedelta(minutes=i * 20),
                    "end": self.start + timedelta(minutes=(i + 1) * 20),
                    "price_p_per_kwh": price} for i, price in enumerate((-1, -1, 2))]
        estimate = apply_operating_costs(estimate_cycle_cost(self.start, self.model, periods), self.policy)
        self.assertEqual(estimate["total_cost_pence"], 0)
        self.assertFalse(estimate["positive_net_benefit"])

    def test_omitted_costs_are_zero_and_visible_while_explicit_zero_is_configured(self):
        extra = self.plan(-5, wear_cost_pence=0)["negative_price_recommendation"]
        self.assertEqual(extra["net_benefit_pence"], 5)
        self.assertIn("consumables_cost_pence", extra["unconfigured_costs"])
        self.assertNotIn("wear_cost_pence", extra["unconfigured_costs"])
        self.assertEqual(extra["operating_cost_breakdown"]["consumables_cost_pence"], 0)

    def test_legacy_overhead_is_counted_once(self):
        result = self.plan(-10, estimated_overhead_cost_pence=2)
        self.assertEqual(result["negative_price_recommendation"]["net_benefit_pence"], 8)
        self.assertNotIn("fixed_cost_pence", result["unconfigured_costs"])

    def test_forecast_and_program_options_share_financial_eligibility(self):
        result = self.plan(-1, consumables_cost_pence=2)
        self.assertTrue(result["cost_forecast"])
        for row in result["cost_forecast"]:
            self.assertFalse(row["positive_net_benefit"])
            self.assertEqual(row["net_benefit_pence"], -1)
            self.assertIn("wear_cost_pence", row["unconfigured_costs"])
        for option in result["overnight_recommendation"]["program_options"]:
            self.assertFalse(option["negative_price_run"])
            self.assertEqual(option["net_benefit_pence"], -1)

    def test_positive_price_required_washing_remains_eligible(self):
        result = self.plan(25, consumables_cost_pence=10)
        self.assertEqual(result["overnight_recommendation"]["status"], "ready")
        self.assertEqual(result["overnight_recommendation"]["cost_pence"], 35)
        self.assertFalse(result["negative_price_recommendation"]["ready_to_start"])

    def test_net_return_wins_over_energy_consumption_and_priority(self):
        other = {**self.model, "program": "Quick45", "expected_energy_kwh": 0.8}
        policies = [normalise_program_policy({**self.policy, "consumables_cost_pence": 4, "negative_price_priority": 100}),
                    normalise_program_policy({**self.policy, "program": "Quick45", "negative_price_priority": 1})]
        result = recommend_cycle([self.model, other], policies, self.periods(-5),
                                 reference_utc=self.start, search_hours=1, candidate_interval_minutes=30, forecast_hours=0)
        self.assertEqual(result["negative_price_recommendation"]["program"], "Quick45")
        self.assertEqual(result["negative_price_recommendation"]["net_benefit_pence"], 4)

    def test_missing_cycle_tail_is_not_treated_as_zero(self):
        periods = self.periods(-5)
        periods[0]["end"] = self.start + timedelta(minutes=30)
        with self.assertRaises(ValueError):
            estimate_cycle_cost(self.start, self.model, periods)

    def test_invalid_operating_costs_fail_closed(self):
        for field in ("fixed_cost_pence", "consumables_cost_pence", "water_litres", "water_cost_pence_per_litre", "wear_cost_pence"):
            for value in (float("nan"), float("inf"), -1, True):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    normalise_program_policy({**self.policy, field: value})

    def test_appliance_configuration_validates_consumables_cost(self):
        for value in (-1, float("nan"), True):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                validate_appliance_options({"instances_yaml": [{"id": "1", "power_sensor": "sensor.power",
                    "program_policies": [{**self.policy, "consumables_cost_pence": value}]}]})
