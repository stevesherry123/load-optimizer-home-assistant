import unittest
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "load_optimizer"
    / "optimizer"
    / "ev_charging.py"
)
SPEC = importlib.util.spec_from_file_location("integration_ev_charging", MODULE_PATH)
ev_charging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev_charging)


class IntegrationEvChargePlannerTests(unittest.TestCase):
    def test_selects_cheapest_slots_for_required_energy(self):
        start = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
        periods = [
            {"start": start, "end": start + timedelta(minutes=30), "price_p_per_kwh": 20},
            {"start": start + timedelta(minutes=30), "end": start + timedelta(minutes=60), "price_p_per_kwh": -5},
            {"start": start + timedelta(minutes=60), "end": start + timedelta(minutes=90), "price_p_per_kwh": 10},
        ]

        plan = ev_charging.plan_ev_charge(
            periods=periods,
            battery_percent=50,
            battery_capacity_kwh=6,
            charge_power_kw=3,
            charger_efficiency=1,
            reference_utc=start,
        )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["slots_needed"], 2)
        self.assertEqual([slot["price_p_per_kwh"] for slot in plan["selected_slots"]], [-5, 10])
        self.assertEqual(plan["estimated_cost_pence"], 7.5)

    def test_reports_net_profit_for_negative_price_plan(self):
        start = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
        periods = [
            {"start": start, "end": start + timedelta(minutes=30), "price_p_per_kwh": -10},
            {"start": start + timedelta(minutes=30), "end": start + timedelta(minutes=60), "price_p_per_kwh": -8},
        ]

        plan = ev_charging.plan_ev_charge(
            periods=periods,
            battery_percent=50,
            battery_capacity_kwh=3,
            charge_power_kw=3,
            charger_efficiency=1,
            reference_utc=start,
        )

        self.assertEqual(plan["estimated_cost_pence"], -15)
        self.assertEqual(plan["estimated_profit_pence"], 15)

    def test_connection_status_blocks_disconnected_vehicle(self):
        self.assertFalse(ev_charging.connection_is_available({"state": "disconnected"}))
        self.assertTrue(ev_charging.connection_is_available({"state": "connected"}))

    def test_ready_by_resolves_to_next_local_deadline(self):
        reference = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)

        deadline = ev_charging.deadline_from_ready_by(
            "07:00",
            reference_utc=reference,
            timezone_name="Europe/London",
        )

        self.assertEqual(deadline, datetime(2026, 9, 25, 6, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
