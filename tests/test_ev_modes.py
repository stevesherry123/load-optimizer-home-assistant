"""EV modes preserve useful energy, price ceilings and honest shortfalls."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/optimizer/ev_charging.py"
SPEC = importlib.util.spec_from_file_location("ev_mode_planner", SOURCE)
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class EVModeTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 3, 21, tzinfo=timezone.utc)
        self.periods = [{"start": self.start + timedelta(minutes=i * 30),
                         "end": self.start + timedelta(minutes=(i + 1) * 30),
                         "price_p_per_kwh": price} for i, price in enumerate((20, 0, -10, 5, 10, 30))]

    def plan(self, **overrides):
        return planner.plan_ev_charge(**{
            "periods": self.periods, "battery_percent": 20, "battery_capacity_kwh": 10,
            "target_percent": 80, "charge_power_kw": 2, "charger_efficiency": 1,
            "reference_utc": self.start, **overrides})

    def test_existing_entries_default_to_required_and_can_use_paid_prices(self):
        plan = self.plan()
        self.assertEqual(plan["charging_mode"], "required")
        self.assertEqual(plan["status"], "ready")
        self.assertTrue(plan["target_reachable"])
        self.assertEqual(plan["planned_wall_energy_kwh"], 6)
        self.assertEqual(plan["estimated_cost_pence"], 55)
        self.assertTrue(plan["charge_now"])

    def test_opportunistic_default_ceiling_allows_free_and_negative_only(self):
        plan = self.plan(charging_mode="opportunistic")
        self.assertEqual(plan["status"], "ready")
        self.assertFalse(plan["target_reachable"])
        self.assertEqual(plan["shortfall_battery_kwh"], 4)
        self.assertEqual(plan["projected_battery_percent"], 40)
        self.assertEqual(plan["estimated_cost_pence"], -10)
        self.assertEqual({slot["price_p_per_kwh"] for slot in plan["selected_slots"]}, {0, -10})
        self.assertFalse(plan["charge_now"])

    def test_ceiling_is_inclusive_and_can_be_negative_or_positive(self):
        for ceiling, expected in ((5, {-10, 0, 5}), (-0.01, {-10})):
            plan = self.plan(charging_mode="opportunistic", maximum_price_p_per_kwh=ceiling)
            self.assertEqual({slot["price_p_per_kwh"] for slot in plan["selected_slots"]}, expected)

    def test_required_mode_does_not_apply_the_opportunistic_ceiling(self):
        plan = self.plan(maximum_price_p_per_kwh=-100)
        self.assertTrue(plan["target_reachable"])
        self.assertIsNone(plan["maximum_price_p_per_kwh"])

    def test_required_shortfall_keeps_a_useful_charging_recommendation(self):
        deadline = self.start + timedelta(hours=2)
        plan = self.plan(deadline_utc=deadline)
        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["reason"], "target_shortfall")
        self.assertTrue(plan["ready_to_charge"])
        self.assertTrue(plan["charge_now"])
        self.assertFalse(plan["target_reachable"])
        self.assertEqual(plan["shortfall_battery_kwh"], 2)
        self.assertEqual(plan["projected_battery_percent"], 60)
        self.assertTrue(all(datetime.fromisoformat(slot["end"]) <= deadline for slot in plan["selected_slots"]))

    def test_required_shortfall_reports_charging_losses(self):
        plan = self.plan(charger_efficiency=0.8, deadline_utc=self.start + timedelta(hours=1))
        self.assertEqual(plan["planned_wall_energy_kwh"], 2)
        self.assertEqual(plan["planned_battery_kwh"], 1.6)
        self.assertEqual(plan["shortfall_battery_kwh"], 4.4)

    def test_active_partial_slot_is_usable_after_a_scan_between_boundaries(self):
        now = self.start + timedelta(hours=1, minutes=7)
        plan = self.plan(reference_utc=now, target_percent=25, charging_mode="opportunistic")
        self.assertTrue(plan["charge_now"])
        self.assertEqual(plan["selected_slots"][0]["start"], now.isoformat())
        self.assertEqual(plan["selected_slots"][0]["end"], (now + timedelta(minutes=15)).isoformat())
        self.assertEqual(plan["planned_wall_energy_kwh"], 0.5)

    def test_final_slot_is_shortened_instead_of_planning_past_target(self):
        plan = self.plan(target_percent=25)
        self.assertEqual(len(plan["selected_slots"]), 1)
        self.assertEqual(plan["selected_slots"][0]["energy_kwh"], 0.5)
        self.assertEqual(plan["selected_slots"][0]["end"], (self.start + timedelta(hours=1, minutes=15)).isoformat())
        self.assertEqual(plan["estimated_cost_pence"], -5)

    def test_battery_and_price_changes_recompute_the_plan(self):
        before = self.plan(charging_mode="opportunistic")
        self.assertTrue(before["selected_slots"])
        for period in self.periods:
            period["price_p_per_kwh"] = 20
        after = self.plan(charging_mode="opportunistic")
        self.assertEqual(after["status"], "waiting")
        self.assertFalse(after["ready_to_charge"])
        self.assertFalse(after["charge_now"])
        self.assertEqual(after["selected_slots"], [])
        met = self.plan(battery_percent=80)
        self.assertEqual(met["reason"], "target_already_met")
        self.assertFalse(met["charge_now"])
        self.assertEqual(met["planned_wall_energy_kwh"], 0)

    def test_price_gaps_are_not_filled_and_irregular_boundaries_are_usable(self):
        self.periods = [{"start": self.start, "end": self.start + timedelta(minutes=20), "price_p_per_kwh": 1},
                        {"start": self.start + timedelta(minutes=40), "end": self.start + timedelta(hours=1), "price_p_per_kwh": 2}]
        plan = self.plan(reference_utc=self.start + timedelta(minutes=10))
        self.assertEqual(plan["planned_wall_energy_kwh"], 1)
        self.assertEqual(plan["status"], "partial")
        self.assertTrue(all(datetime.fromisoformat(slot["end"]) <= self.start + timedelta(minutes=20)
                            or datetime.fromisoformat(slot["start"]) >= self.start + timedelta(minutes=40)
                            for slot in plan["selected_slots"]))

    def test_duplicate_intervals_are_deduplicated_and_conflicting_ones_rejected(self):
        duplicate = self.plan(periods=[*self.periods, dict(self.periods[0])])
        self.assertEqual(duplicate["published_slots_available"], 6)
        conflict = self.plan(periods=[*self.periods, {**self.periods[0], "price_p_per_kwh": -20}])
        self.assertEqual(conflict["reason"], "invalid_tariff_periods")
        self.assertFalse(conflict["ready_to_charge"])

    def test_invalid_or_elapsed_time_never_suggests_charging(self):
        for value in (self.start, self.start - timedelta(seconds=1)):
            self.assertEqual(self.plan(deadline_utc=value)["reason"], "deadline_passed")
        self.assertEqual(self.plan(deadline_utc=self.start.replace(tzinfo=None))["reason"], "invalid_planning_time")

    def test_invalid_modes_prices_and_readings_fail_closed(self):
        for value in ("unsupported", None, []):
            self.assertEqual(self.plan(charging_mode=value)["reason"], "invalid_charging_mode")
        for value in (float("nan"), float("inf"), True, 1001):
            self.assertFalse(self.plan(maximum_price_p_per_kwh=value)["ready_to_charge"])
        for value in (float("nan"), float("inf")):
            self.assertIsNone(planner.state_float({"state": value}))
        for state in ("disconnected", "off", "unavailable", "unknown", "unexpected"):
            self.assertFalse(planner.connection_is_available({"state": state}))
        for state in ("on", "connected", "charging"):
            self.assertTrue(planner.connection_is_available({"state": state}))

    def test_deadline_uses_the_remaining_repeated_hour(self):
        deadline = planner.deadline_from_ready_by("01:30", reference_utc=datetime(2026, 10, 25, 0, 45, tzinfo=timezone.utc),
                                                 timezone_name="Europe/London")
        self.assertEqual(deadline, datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc))

    def test_skipped_deadline_moves_forward_with_the_clock_change(self):
        deadline = planner.deadline_from_ready_by("01:30", reference_utc=datetime(2026, 3, 28, 23, tzinfo=timezone.utc),
                                                 timezone_name="Europe/London")
        self.assertEqual(deadline, datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc))

    def test_invalid_deadline_or_timezone_does_not_silently_remove_a_constraint(self):
        for clock, zone in (("25:00", "Europe/London"), ("07:00", "Invalid/Timezone")):
            with self.assertRaises(ValueError):
                planner.deadline_from_ready_by(clock, reference_utc=self.start, timezone_name=zone)
