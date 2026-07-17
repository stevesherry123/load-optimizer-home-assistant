import unittest
from datetime import datetime, timedelta, timezone

from load_optimizer.app.costing import (
    estimate_cycle_cost,
    parse_ai_feed,
    parse_structured_rates,
    recommend_cycle,
    tariff_periods_from_entity,
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

    def test_nested_event_rates_are_supported(self):
        periods = tariff_periods_from_entity(
            {
                "attributes": {
                    "event_type": "octopus_energy_electricity_current_day_rates",
                    "last_event_attributes": {
                        "rates": [{
                            "start": "2026-07-06T00:00:00+01:00",
                            "end": "2026-07-06T00:30:00+01:00",
                            "value_inc_vat": 0.241,
                        }],
                    },
                },
            },
            reference_utc=datetime(2026, 7, 6, tzinfo=timezone.utc),
            timezone_name="Europe/London",
            price_unit="gbp_per_kwh",
        )

        self.assertEqual(periods[0]["start"], datetime(2026, 7, 5, 23, 0, tzinfo=timezone.utc))
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
        self.assertEqual(result["cost_breakdown"][0]["energy_kwh"], 1.0)
        self.assertEqual(result["cost_breakdown"][0]["energy_cost_pence"], 10.0)

    def test_cost_breakdown_uses_power_timing_not_flat_average(self):
        model = {
            "program": "Intensive",
            "expected_runtime_minutes": 60,
            "expected_energy_kwh": 1.0,
            "representative_profile_w": [2000, 2000, 0],
        }

        result = estimate_cycle_cost(
            self.start,
            model,
            [
                self.period(0, 30, 0),
                self.period(30, 60, 50),
            ],
        )

        self.assertEqual(result["energy_kwh"], 1.0)
        self.assertEqual(result["energy_cost_pence"], 16.6667)
        self.assertEqual(result["cost_breakdown"], [
            {
                "start": "2026-07-06T00:00:00+00:00",
                "end": "2026-07-06T00:30:00+00:00",
                "price_p_per_kwh": 0,
                "energy_kwh": 0.666667,
                "energy_cost_pence": 0.0,
            },
            {
                "start": "2026-07-06T00:30:00+00:00",
                "end": "2026-07-06T01:00:00+00:00",
                "price_p_per_kwh": 50,
                "energy_kwh": 0.333333,
                "energy_cost_pence": 16.6667,
            },
        ])

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
        self.assertEqual(result["cost_breakdown"][0]["energy_cost_pence"], 5.0)
        self.assertEqual(result["cost_if_started_now_breakdown"][0]["energy_cost_pence"], 20.0)

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
        self.assertEqual(result["negative_price_recommendation"]["program"], "Eco")

    def test_negative_price_recommendation_prefers_energy_intensity(self):
        short_hot = {
            **self.model,
            "program": "ShortHot",
            "expected_runtime_minutes": 30,
            "expected_energy_kwh": 1.0,
        }
        long_eco = {
            **self.model,
            "program": "LongEco",
            "expected_runtime_minutes": 120,
            "expected_energy_kwh": 2.0,
        }
        policies = [
            {
                "program": "ShortHot",
                "enabled": True,
                "allow_normal_recommendation": False,
                "allow_negative_price_run": True,
                "preference_rank": 50,
                "estimated_overhead_cost_pence": 0,
            },
            {
                "program": "LongEco",
                "enabled": True,
                "allow_normal_recommendation": False,
                "allow_negative_price_run": True,
                "preference_rank": 50,
                "estimated_overhead_cost_pence": 0,
            },
        ]
        periods = [self.period(0, 180, -10)]

        result = recommend_cycle(
            [short_hot, long_eco],
            policies,
            periods,
            reference_utc=self.start,
            search_hours=1,
            candidate_interval_minutes=30,
        )

        self.assertEqual(result["negative_price_candidate_count"], 6)
        self.assertEqual(result["negative_price_recommendation"]["program"], "ShortHot")
        self.assertEqual(result["negative_price_recommendation"]["intent"], "negative_price")
        self.assertGreater(
            result["negative_price_recommendation"]["energy_kwh_per_minute"],
            0,
        )

    def test_negative_price_priority_beats_energy_intensity(self):
        short_hot = {
            **self.model,
            "program": "ShortHot",
            "expected_runtime_minutes": 30,
            "expected_energy_kwh": 1.0,
        }
        maintenance = {
            **self.model,
            "program": "MachineCare",
            "expected_runtime_minutes": 120,
            "expected_energy_kwh": 2.0,
        }
        policies = [
            {
                "program": "ShortHot",
                "enabled": True,
                "allow_normal_recommendation": False,
                "allow_negative_price_run": True,
                "preference_rank": 50,
                "negative_price_priority": 50,
                "estimated_overhead_cost_pence": 0,
            },
            {
                "program": "MachineCare",
                "enabled": True,
                "allow_normal_recommendation": False,
                "allow_negative_price_run": True,
                "preference_rank": 50,
                "negative_price_priority": 100,
                "estimated_overhead_cost_pence": 0,
            },
        ]
        periods = [self.period(0, 180, -10)]

        result = recommend_cycle(
            [short_hot, maintenance],
            policies,
            periods,
            reference_utc=self.start,
            search_hours=1,
            candidate_interval_minutes=30,
        )

        self.assertEqual(result["negative_price_recommendation"]["program"], "MachineCare")

    def test_latest_finish_deadline_rejects_late_cheap_slot(self):
        model = {**self.model, "expected_runtime_minutes": 60}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 60, 30),
            self.period(60, 120, 5),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=1,
            candidate_interval_minutes=60,
            latest_finish_utc=self.start + timedelta(minutes=90),
        )

        self.assertEqual(result["start"], self.start)
        self.assertEqual(result["latest_allowed_finish"], (self.start + timedelta(minutes=90)).isoformat())
        self.assertEqual(result["rejected_constraints"], 1)

    def test_cheapest_earliest_finish_uses_first_near_equivalent_slot(self):
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 60, 10),
            self.period(60, 120, 10.5),
            self.period(120, 180, 10),
        ]

        result = recommend_cycle(
            [self.model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=2,
            candidate_interval_minutes=60,
            schedule_strategy="cheapest_earliest_finish",
            equivalent_cost_tolerance_pence=1,
        )

        self.assertEqual(result["start"], self.start)
        self.assertEqual(result["finish"], self.start + timedelta(hours=1))
        self.assertEqual(result["schedule_strategy"], "cheapest_earliest_finish")

    def test_cheapest_latest_finish_uses_last_near_equivalent_slot(self):
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 60, 10),
            self.period(60, 120, 10.5),
            self.period(120, 180, 10),
        ]

        result = recommend_cycle(
            [self.model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=2,
            candidate_interval_minutes=60,
            schedule_strategy="cheapest_latest_finish",
            equivalent_cost_tolerance_pence=1,
        )

        self.assertEqual(result["start"], self.start + timedelta(hours=2))
        self.assertEqual(result["finish"], self.start + timedelta(hours=3))
        self.assertEqual(result["schedule_strategy"], "cheapest_latest_finish")

    def test_cheapest_absolute_ignores_more_expensive_equivalent_slots(self):
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 60, 10.5),
            self.period(60, 120, 10),
        ]

        result = recommend_cycle(
            [self.model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=1,
            candidate_interval_minutes=60,
            schedule_strategy="cheapest_absolute",
            equivalent_cost_tolerance_pence=1,
        )

        self.assertEqual(result["start"], self.start + timedelta(hours=1))

    def test_overnight_only_filters_daytime_candidates(self):
        model = {**self.model, "expected_runtime_minutes": 30}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 30, 10),
            self.period(480, 510, 1),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=8,
            candidate_interval_minutes=30,
            window_preference="overnight_only",
            overnight_start="20:00",
            overnight_end="08:00",
            schedule_timezone="UTC",
        )

        self.assertEqual(result["start"], self.start)
        self.assertTrue(result["is_overnight_start"])

    def test_prefer_daytime_uses_daytime_slot_within_tolerance(self):
        model = {**self.model, "expected_runtime_minutes": 30}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 30, 10),
            self.period(480, 510, 10.5),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=8,
            candidate_interval_minutes=30,
            schedule_strategy="cheapest_earliest_finish",
            equivalent_cost_tolerance_pence=1,
            window_preference="prefer_daytime",
            overnight_start="20:00",
            overnight_end="08:00",
            schedule_timezone="UTC",
        )

        self.assertEqual(result["start"], self.start + timedelta(hours=8))
        self.assertTrue(result["is_daytime_start"])
        self.assertEqual(result["window_preference"], "prefer_daytime")

    def test_recommendation_includes_daytime_and_overnight_comparisons(self):
        model = {**self.model, "expected_runtime_minutes": 30}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 30, 20),
            self.period(480, 510, 5),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=8,
            candidate_interval_minutes=30,
            overnight_start="20:00",
            overnight_end="08:00",
            schedule_timezone="UTC",
        )

        self.assertEqual(result["overnight_comparison"]["cost_pence"], 20.0)
        self.assertEqual(result["overnight_comparison"]["saving_vs_now_pence"], 0.0)
        self.assertEqual(result["daytime_comparison"]["cost_pence"], 5.0)
        self.assertEqual(result["daytime_comparison"]["saving_vs_now_pence"], 15.0)
        self.assertEqual(result["comparison_candidate_count"], 2)

    def test_recommendation_includes_frontend_intents(self):
        model = {**self.model, "expected_runtime_minutes": 30}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        reference = self.start + timedelta(hours=12)
        periods = [
            self.period(720, 750, 30),
            self.period(750, 780, 10),
            self.period(1200, 1230, 5),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=reference,
            search_hours=8,
            candidate_interval_minutes=30,
            overnight_start="20:00",
            overnight_end="08:00",
            schedule_timezone="UTC",
        )

        self.assertEqual(result["now_recommendation"]["intent"], "now")
        self.assertTrue(result["now_recommendation"]["ready_to_start"])
        self.assertEqual(result["now_recommendation"]["cost_pence"], 30.0)
        self.assertEqual(result["soon_recommendation"]["intent"], "soon")
        self.assertEqual(result["soon_recommendation"]["cost_pence"], 10.0)
        self.assertFalse(result["soon_recommendation"]["ready_to_start"])
        self.assertEqual(result["overnight_recommendation"]["intent"], "overnight")
        self.assertEqual(result["overnight_recommendation"]["cost_pence"], 5.0)
        self.assertEqual(result["overnight_recommendation"]["seconds_until_start"], 28800)

    def test_recommendation_includes_cost_forecast(self):
        model = {**self.model, "expected_runtime_minutes": 30}
        policy = {
            "program": "Eco",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "estimated_overhead_cost_pence": 0,
        }
        periods = [
            self.period(0, 30, 20),
            self.period(30, 60, 10),
            self.period(60, 90, 5),
        ]

        result = recommend_cycle(
            [model],
            [policy],
            periods,
            reference_utc=self.start,
            search_hours=2,
            candidate_interval_minutes=5,
            forecast_hours=1,
            forecast_interval_minutes=30,
        )

        self.assertEqual(result["forecast_hours"], 1)
        self.assertEqual(result["forecast_interval_minutes"], 30)
        self.assertEqual(len(result["cost_forecast"]), 3)
        self.assertEqual(result["forecast_diagnostics"][0]["program"], "Eco")
        self.assertEqual(result["forecast_diagnostics"][0]["priced_points"], 3)
        self.assertEqual(result["cost_forecast"][0]["program"], "Eco")
        self.assertEqual(result["cost_forecast"][0]["cost_pence"], 20.0)
        self.assertEqual(result["cost_forecast"][1]["start"], "2026-07-06T00:30:00+00:00")

    def test_cooldown_excludes_recent_program_and_uses_next_candidate(self):
        quick = {
            **self.model,
            "program": "Quick65",
            "last_seen": (self.start - timedelta(hours=12)).isoformat(),
        }
        super60 = {
            **self.model,
            "program": "Super60",
            "expected_energy_kwh": 1.2,
        }
        policies = [
            {
                "program": "Quick65",
                "enabled": True,
                "allow_normal_recommendation": True,
                "allow_negative_price_run": False,
                "preference_rank": 1,
                "minimum_hours_between_runs": 46,
                "estimated_overhead_cost_pence": 0,
            },
            {
                "program": "Super60",
                "enabled": True,
                "allow_normal_recommendation": True,
                "allow_negative_price_run": False,
                "preference_rank": 50,
                "minimum_hours_between_runs": 0,
                "estimated_overhead_cost_pence": 0,
            },
        ]

        result = recommend_cycle(
            [quick, super60],
            policies,
            [self.period(0, 180, 10)],
            reference_utc=self.start,
            search_hours=2,
            candidate_interval_minutes=30,
        )

        self.assertEqual(result["program"], "Super60")
        self.assertGreater(result["rejected_cooldowns"], 0)
        quick_diagnostic = next(item for item in result["program_diagnostics"] if item["program"] == "Quick65")
        self.assertEqual(quick_diagnostic["status"], "excluded")
        self.assertEqual(quick_diagnostic["reason"], "cooldown_active")
        self.assertEqual(quick_diagnostic["cooldown_until"], "2026-07-07T10:00:00+00:00")

    def test_cooldown_allows_program_after_cooldown_expires_in_window(self):
        quick = {
            **self.model,
            "program": "Quick65",
            "last_seen": (self.start - timedelta(hours=1)).isoformat(),
        }
        policy = {
            "program": "Quick65",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "preference_rank": 1,
            "minimum_hours_between_runs": 2,
            "estimated_overhead_cost_pence": 0,
        }

        result = recommend_cycle(
            [quick],
            [policy],
            [self.period(0, 240, 10)],
            reference_utc=self.start,
            search_hours=3,
            candidate_interval_minutes=30,
        )

        self.assertEqual(result["program"], "Quick65")
        self.assertEqual(result["start"], self.start + timedelta(hours=1))
        self.assertGreater(result["rejected_cooldowns"], 0)
        diagnostic = result["program_diagnostics"][0]
        self.assertEqual(diagnostic["status"], "included")
        self.assertEqual(diagnostic["rejected_cooldown_points"], 2)


if __name__ == "__main__":
    unittest.main()
