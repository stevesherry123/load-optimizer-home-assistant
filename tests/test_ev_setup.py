"""Read-only guided checks must use the same planner as live EV coordination."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"
sys.path.insert(0, str(ROOT))
from optimizer.ev_setup import build_ev_plan, inspect_ev_setup


class EVSetupTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 21, 0, tzinfo=timezone.utc)
        self.config = {"tariff_entity": "sensor.rates", "battery_entity": "sensor.battery",
            "battery_capacity_entity": "sensor.capacity", "charge_power_kw": 1,
            "charger_efficiency": 1, "slot_minutes": 30, "tariff_timezone": "Europe/London",
            "tariff_price_unit": "p_per_kwh", "ev_charger_switch": "switch.charger",
            "connection_status_entity": "sensor.connection", "ev_charge_power_entity": "sensor.power",
            "ev_charge_energy_entity": "sensor.energy", "ev_charging_status_entity": "sensor.status"}
        self.states = {}
        for name, value, unit in (("sensor.battery", "0", "%"), ("sensor.capacity", "6", "kWh"),
            ("switch.charger", "off", None), ("sensor.connection", "connected", None),
            ("sensor.power", "0", "W"), ("sensor.energy", "100", "kWh"), ("sensor.status", "idle", None)):
            self.states[name] = {"state": value, "attributes": {"unit_of_measurement": unit},
                                 "last_reported": self.now.isoformat()}
        rates = [{"start": (self.now + timedelta(minutes=30 * i)).isoformat(),
                  "end": (self.now + timedelta(minutes=30 * (i + 1))).isoformat(),
                  "value_inc_vat": -20 if i % 2 else -1} for i in range(24)]
        self.states["sensor.rates"] = {"state": "ready", "attributes": {"rates": rates}}

    def inspect(self):
        return inspect_ev_setup(self.config, self.states, self.now)

    def test_preview_is_live_plan_and_selects_cheapest_six_hours(self):
        before = deepcopy(self.states)
        report = self.inspect()
        self.assertTrue(report["control_ready"], report)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["plan"], build_ev_plan(self.config, self.states, self.now)[0])
        slots = report["plan"]["selected_slots"]
        self.assertEqual(len(slots), 12)
        self.assertTrue(all(slot["price_p_per_kwh"] == -20 for slot in slots))
        self.assertEqual(self.states, before)

    def test_advisory_does_not_require_charger_feedback(self):
        self.config.pop("ev_charger_switch")
        self.config.pop("connection_status_entity")
        report = self.inspect()
        self.assertEqual(report["issues"], [])
        self.assertFalse(report["control_configured"])
        self.assertFalse(report["control_ready"])

    def test_stale_units_fault_and_manual_on_are_explained(self):
        self.states["sensor.battery"]["last_reported"] = (self.now - timedelta(hours=1)).isoformat()
        self.states["sensor.capacity"]["attributes"]["unit_of_measurement"] = "Wh"
        self.states["sensor.status"]["state"] = "fault"
        self.states["switch.charger"]["state"] = "on"
        report = self.inspect()
        self.assertFalse(report["control_ready"])
        for text in ("feedback is stale", "expected unit kWh", "reports a fault", "must be off"):
            self.assertTrue(any(text in issue for issue in report["issues"]), report)

    def test_incomplete_control_and_expensive_budget_are_not_silently_accepted(self):
        self.config.pop("ev_charge_energy_entity")
        self.config["ev_session_max_energy_kwh"] = 0.3
        self.config["ev_session_max_hours"] = 1
        report = self.inspect()
        self.assertIn("ev_charge_energy_entity: not configured", report["issues"])
        self.assertEqual(len(report["warnings"]), 2)

    def test_bad_target_reading_cannot_pass_using_fallback(self):
        self.config["target_percent_entity"] = "sensor.target"
        self.states["sensor.target"] = {"state": "NaN", "attributes": {"unit_of_measurement": "%"}}
        self.assertIn("target_percent_entity: invalid numeric reading", self.inspect()["issues"])

    def test_no_future_tariff_is_not_control_ready(self):
        self.states["sensor.rates"]["attributes"]["rates"] = []
        report = self.inspect()
        self.assertFalse(report["control_ready"])
        self.assertEqual(report["plan"]["status"], "not_ready")
