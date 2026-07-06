import unittest
from datetime import datetime, timedelta, timezone

from load_optimizer.app.costing import (
    estimate_cycle_cost,
    parse_ai_feed,
    parse_structured_rates,
    recommend_cycle,
)


class TariffParsingTests(unittest.TestCase):
    def test_ai_feed_becomes_utc_tariff_periods(self):
        periods = parse_ai_feed(
            "06/07 00:00=18.41p; 06/07 00:30=-2.5p;",
            reference_utc=datetime(2026, 7, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0]["start"], datetime(2026, 7, 5, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(periods[0]["price_p_per_kwh"], 18.41)
        self.assertEqual(periods[1]["price_p_per_kwh"], -2.5)

    def test_structured_gbp_rates_are_converted_to_pence(self):
        periods = parse_structured_rates([{
            "start": "2026-07-06T00:00:00Z",
            "end": "2026-07-06T00:30:00Z",
            "value_inc_vat": 0.241,
        }], price_unit="gbp_per_kwh")

        self.assertEqual(periods[0]["price_p_per_kwh"], 24.1)


class CostEstimationTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 7, 6, tzinfo=timezone.utc)
        self.model = {
            "program": "Eco",
            "expected_runtime_minutes": 60,
            "expected_energy_kwh": 1.0,
            "representative_profile_w": [100, 100],
            "confidence": 60,
        }

    def period(self, start_minutes, end_minutes, price):
        return {
            "start": self.start + timedelta(minutes=start_minutes),
            "end": self.start + timedelta(minutes=end_minutes),
            "price_p_per_kwh": price,
        }

    def test_profile_is_scaled_to_learned_energy(self):
        result = estimate_cycle_cost(
            self.start,
            self.model,
            [self.period(0, 60, 10)],
        )

        self.assertAlmostEqual(result["energy_kwh"], 1.0)
        self.assertAlmostEqual(result["energy_cost_pence"], 10.0)

    def test_tariff_gap_rejects_cost(self):
        with self.assertRaisesRegex(ValueError, "fully cover"):
            estimate_cycle_cost(
                self.start,
                self.model,
                [self.period(0, 30, 10)],
            )

    def test_recommendation_finds_cheapest_start(self):
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 2,
        }
        periods = [
            self.period(0, 60, 20),
            self.period(60, 120, 5),
        ]

        result = recommend_cycle(
            [self.model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=1,
            candidate_interval_minutes=30,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["start"], self.start + timedelta(hours=1))
        self.assertEqual(result["total_cost_pence"], 7.0)
        self.assertEqual(result["potential_saving_pence"], 15.0)

    def test_opportunistic_policy_only_uses_negative_window(self):
        model = {**self.model, "expected_runtime_minutes": 30}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": False,
            "allow_negative_price_run": True,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 30, 10),
            self.period(30, 60, -5),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=0.5,
            candidate_interval_minutes=30,
        )

        self.assertEqual(result["start"], self.start + timedelta(minutes=30))
        self.assertTrue(result["negative_price_run"])


if __name__ == "__main__":
    unittest.main()
