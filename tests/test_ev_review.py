"""Read-only EV dashboard data and real-engine fake-price replay."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components/load_optimizer"))
sys.path.insert(0, str(ROOT))
from optimizer.ev_review import review_snapshot
from optimizer.ev_monitor import EVDeliveryMonitor
from dev.ev_replay import all_scenarios


class EVReviewTests(unittest.TestCase):
    def test_empty_data_is_explained_without_enabling_control(self):
        now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        review = review_snapshot({}, {"status": "not_ready", "reason": "no_tariff_periods"}, [], {}, None, now)
        self.assertEqual(review["control"]["state"], "advisory")
        self.assertEqual(review["selected_slots"], [])
        self.assertIsNone(review["battery_percent"])
        self.assertTrue(all(source["status"] == "not_configured" for source in review["sources"]))

    def test_unknown_stale_and_zero_readings_remain_distinct(self):
        now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        sources = {"sensor.power": {"state": "0", "attributes": {"unit_of_measurement": "W"},
                                   "last_reported": (now - timedelta(hours=1)).isoformat()},
                   "sensor.energy": {"state": "unavailable", "attributes": {"unit_of_measurement": "kWh"}}}
        review = review_snapshot({"ev_charge_power_entity": "sensor.power", "ev_charge_energy_entity": "sensor.energy"},
            {}, [], sources, None, now)
        self.assertEqual(review["actual_power_w"], 0)
        self.assertIsNone(review["meter_energy_kwh"])
        status = {source["role"]: source["status"] for source in review["sources"]}
        self.assertEqual(status["ev_charge_power_entity"], "stale")
        self.assertEqual(status["ev_charge_energy_entity"], "unavailable")

    def test_static_capacity_does_not_need_a_recent_update(self):
        now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        review = review_snapshot({"battery_capacity_entity": "sensor.capacity"}, {}, [],
            {"sensor.capacity": {"state": "60", "last_reported": (now - timedelta(days=30)).isoformat()}}, None, now)
        source = next(source for source in review["sources"] if source["role"] == "battery_capacity_entity")
        self.assertEqual(source["status"], "available")
        self.assertFalse(source["freshness_required"])

    def test_large_slot_tables_are_bounded_and_explicitly_truncated(self):
        now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        slots = [{"start": (now + timedelta(minutes=i * 5)).isoformat(),
                  "end": (now + timedelta(minutes=(i + 1) * 5)).isoformat(), "price_p_per_kwh": -5,
                  "energy_kwh": 0.5, "cost_pence": -2.5} for i in range(500)]
        review = review_snapshot({}, {"selected_slots": slots}, [], {}, None, now)
        self.assertLess(len(json.dumps(review)), 28000)
        self.assertTrue(review["selected_slots_truncated"])
        self.assertEqual(review["selected_slot_count"], 500)
        self.assertGreater(review["planned_charging_minutes"], 0)

    def test_dashboard_is_read_only_and_uses_one_review_entity(self):
        dashboard = yaml.safe_load((ROOT / "custom_components/load_optimizer/ev_dashboard.yaml").read_text())
        raw = json.dumps(dashboard)
        self.assertNotIn("call-service", raw)
        self.assertNotIn("switch.volvo_charger", raw)
        self.assertNotIn("button.", raw)
        self.assertIn("sensor.ev_charging_review", raw)
        self.assertIn("48h", raw)
        self.assertIn("Selected Slots", raw)

    def test_delivery_totals_survive_separated_charging_slots(self):
        now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        monitor = EVDeliveryMonitor()
        monitor.start(now, 20, 100)
        monitor.start(now + timedelta(hours=1), 24, 102.5)
        self.assertEqual(monitor.energy_start, 100)
        self.assertEqual(monitor.battery_start, 20)
        monitor.record_totals(battery=28, capacity=60, efficiency=1, power=0, energy=105, charging_status="idle")
        self.assertEqual(monitor.result["delivered_wall_kwh"], 5)

    def test_meter_freeze_after_initial_success_is_detected(self):
        now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        monitor = EVDeliveryMonitor()
        monitor.start(now, 20, 100)
        kwargs = dict(battery=21, capacity=60, efficiency=1, power=1000, energy=100.1, charging_status="charging")
        self.assertIsNone(monitor.update(now + timedelta(minutes=2), **kwargs))
        self.assertEqual(monitor.update(now + timedelta(minutes=5), **kwargs), "charging_energy_not_increasing")


class EVReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_six_hours_selected_across_twelve_and_failure_stops(self):
        data = await all_scenarios()
        self.assertFalse(data["physical_services_possible"])
        normal = data["scenarios"][0]["frames"]
        self.assertEqual(normal[0]["snapshot"]["selected_slot_count"], 12)
        self.assertEqual(normal[0]["snapshot"]["planned_charging_minutes"], 360)
        self.assertEqual(len(normal[-1]["commands"]), 24)
        self.assertEqual(normal[-1]["snapshot"]["battery_percent"], 70)
        self.assertEqual(normal[-1]["snapshot"]["control"]["delivery"]["delivered_wall_kwh"], 30)
        for scenario in data["scenarios"][1:]:
            last = scenario["frames"][-1]
            self.assertEqual(last["snapshot"]["charger_state"], "off")
            self.assertIsNotNone(last["snapshot"]["control"]["last_stop_reason"])
