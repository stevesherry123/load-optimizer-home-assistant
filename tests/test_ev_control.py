"""Synthetic EV control; no Home Assistant services or physical plug are used."""

import ast
import asyncio
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"
sys.path.insert(0, str(ROOT))
from optimizer.ev_charging import plan_ev_charge
from optimizer.ev_monitor import EVDeliveryMonitor, measurement

tree = ast.parse((ROOT / "ev_control.py").read_text())
tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
namespace = {"asyncio": asyncio, "datetime": datetime, "timedelta": timedelta, "timezone": timezone,
             "math": math, "EVDeliveryMonitor": EVDeliveryMonitor, "measurement": measurement,
             "Store": Mock(), "HomeAssistantError": RuntimeError, "EVENT_HOMEASSISTANT_STOP": "stop",
             "async_track_time_interval": lambda *args: lambda: None}
exec(compile(tree, str(ROOT / "ev_control.py"), "exec"), namespace)


class Clock(datetime):
    current = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


class EVControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Clock.current = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        self.clock = patch.dict(namespace, datetime=Clock)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.values = {}
        self.config = {"ev_charger_switch": "switch.charger", "battery_entity": "sensor.battery",
            "battery_capacity_entity": "sensor.capacity", "connection_status_entity": "sensor.connection",
            "ev_charge_power_entity": "sensor.power", "ev_charge_energy_entity": "sensor.energy",
            "ev_charging_status_entity": "sensor.charging", "target_percent": 100, "charger_efficiency": 1}
        async def command(domain, service, payload, **kwargs):
            self.put(payload["entity_id"], "on" if service == "turn_on" else "off")
        self.hass = SimpleNamespace(data={}, states=SimpleNamespace(get=self.values.get),
            services=SimpleNamespace(async_call=AsyncMock(side_effect=command)),
            bus=SimpleNamespace(async_listen_once=Mock(return_value=lambda: None)))
        self.controller = namespace["EVChargeController"](self.hass,
            SimpleNamespace(entry_id="synthetic", data=self.config, options={}), Mock())
        self.controller.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        for entity, value, unit in (("switch.charger", "off", None), ("sensor.battery", "10", "%"),
            ("sensor.capacity", "60", "kWh"), ("sensor.connection", "connected", None),
            ("sensor.power", "1000", "W"), ("sensor.energy", "100", "kWh"),
            ("sensor.charging", "charging", None)):
            self.put(entity, value, unit)
        self.plan = {"status": "ready", "selected_slots": [{"start": Clock.current.isoformat(),
            "end": (Clock.current + timedelta(minutes=30)).isoformat()}]}
        self.controller.set_plan(self.plan, Clock.current)

    def put(self, entity, value, unit=None):
        self.values[entity] = SimpleNamespace(state=value, attributes={"unit_of_measurement": unit},
                                            last_updated=Clock.current, last_reported=Clock.current)

    async def start(self):
        await self.controller.async_enable()
        await self.controller.async_tick()

    async def test_default_off_does_not_adopt_manual_charge(self):
        await self.controller.async_start()
        self.hass.services.async_call.assert_not_awaited()
        self.put("switch.charger", "on")
        await self.controller.async_tick()
        self.assertFalse(self.controller.enabled)
        self.assertEqual(self.controller.reason, "manual_charging_not_owned")
        self.hass.services.async_call.assert_not_awaited()

    async def test_selected_slot_on_then_end_off(self):
        await self.start()
        self.assertEqual(self.values["switch.charger"].state, "on")
        self.assertEqual(self.controller.owned_target, "switch.charger")
        Clock.current += timedelta(minutes=30)
        self.controller.set_plan(self.plan, Clock.current)
        self.put("sensor.energy", "100.5", "kWh")
        for value in self.values.values():
            value.last_reported = Clock.current
        await self.controller.async_tick()
        await self.controller.async_tick()
        self.assertEqual(self.values["switch.charger"].state, "off")
        self.assertIsNone(self.controller.owned_target)

    async def test_disconnect_target_and_stale_data_stop_owned_charge(self):
        for cause in ("disconnect", "target", "stale", "missing_power", "fault"):
            with self.subTest(cause=cause):
                self.setUp()
                await self.start()
                if cause == "disconnect": self.put("sensor.connection", "disconnected")
                if cause == "target": self.put("sensor.battery", "100", "%")
                if cause == "stale": Clock.current += timedelta(minutes=2)
                if cause == "missing_power": self.put("sensor.power", "unavailable", "W")
                if cause == "fault": self.put("sensor.charging", "error")
                await self.controller.async_tick()
                self.assertEqual(self.values["switch.charger"].state, "off")

    async def test_manual_off_disarms_without_fighting_user(self):
        await self.start()
        self.hass.services.async_call.reset_mock()
        self.put("switch.charger", "off")
        await self.controller.async_tick()
        await self.controller.async_tick()
        self.assertFalse(self.controller.enabled)
        self.hass.services.async_call.assert_not_awaited()

    async def test_restart_cleans_owned_charge_but_does_not_resume(self):
        self.controller.store.async_load.return_value = {"owned_target": "switch.charger"}
        self.put("switch.charger", "on")
        await self.controller.async_start()
        self.assertEqual(self.values["switch.charger"].state, "off")
        self.assertFalse(self.controller.enabled)

    async def test_failed_journal_cannot_energise(self):
        self.controller.store.async_save.side_effect = OSError("synthetic")
        await self.controller.async_enable()
        self.hass.services.async_call.assert_not_awaited()
        self.assertFalse(self.controller.enabled)

    async def test_no_feedback_or_unavailable_plug_cannot_start(self):
        self.config["ev_charge_energy_entity"] = ""
        with self.assertRaises(RuntimeError):
            await self.controller.async_enable()
        self.config["ev_charge_energy_entity"] = "sensor.energy"
        self.put("switch.charger", "unavailable")
        with self.assertRaises(RuntimeError):
            await self.controller.async_enable()
        self.hass.services.async_call.assert_not_awaited()

    async def test_failed_charging_confirmation_stops_and_disarms(self):
        await self.start()
        Clock.current += timedelta(seconds=121)
        self.controller.set_plan(self.plan, Clock.current)
        self.put("sensor.charging", "idle")
        await self.controller.async_tick()
        self.assertFalse(self.controller.enabled)
        self.assertEqual(self.values["switch.charger"].state, "off")
        self.assertEqual(self.controller.monitor.result["status"], "charging_not_confirmed")


class EVDeliveryTests(unittest.TestCase):
    def test_unit_conversion_and_invalid_values(self):
        for quantity, value, unit, expected in (("power", "1.5", "kW", 1500),
            ("energy", "1500", "Wh", 1.5), ("power", "NaN", "W", None),
            ("energy", "-1", "kWh", None), ("power", "10", "unknown", None)):
            state = SimpleNamespace(state=value, attributes={"unit_of_measurement": unit})
            self.assertEqual(measurement(state, quantity), expected)

    def test_meter_progress_battery_gain_and_reset(self):
        start = Clock.current
        cases = ((101, 15, "charging", None), (100, 10, "charging", "charging_energy_not_increasing"),
                 (110, 10, "charging", "battery_gain_below_expected"), (99, 10, "charging", "energy_meter_reset"))
        for energy, battery, status, expected in cases:
            monitor = EVDeliveryMonitor()
            monitor.start(start, 10, 100)
            result = monitor.update(start + timedelta(minutes=5), battery=battery, capacity=20,
                efficiency=1, power=1000, energy=energy, charging_status=status)
            self.assertEqual(result, expected)


class EVSplitSlotTests(unittest.TestCase):
    def plan(self, periods, now, capacity=6):
        return plan_ev_charge(periods=periods, reference_utc=now, battery_percent=0,
            battery_capacity_kwh=capacity, charge_power_kw=1, charger_efficiency=1)

    def test_twelve_hours_selects_six_nonconsecutive_cheapest_hours(self):
        start = Clock.current
        periods = [{"start": start + timedelta(minutes=30 * i), "end": start + timedelta(minutes=30 * (i + 1)),
                    "price_p_per_kwh": -20 if i % 2 else -1} for i in range(24)]
        plan = self.plan(periods, start)
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(len(plan["selected_slots"]), 12)
        self.assertTrue(all(slot["price_p_per_kwh"] == -20 for slot in plan["selected_slots"]))
        self.assertEqual(sum(slot["energy_kwh"] for slot in plan["selected_slots"]), 6)

    def test_mid_slot_refresh_keeps_current_remaining_energy(self):
        start = Clock.current
        periods = [{"start": start, "end": start + timedelta(hours=1), "price_p_per_kwh": -20}]
        plan = self.plan(periods, start + timedelta(minutes=10), capacity=0.75)
        self.assertTrue(plan["charge_now"])
        self.assertEqual(plan["status"], "ready")
        self.assertAlmostEqual(plan["selected_slots"][0]["energy_kwh"], 1 / 3, places=4)

    def test_overlaps_cannot_count_the_same_energy_twice(self):
        start = Clock.current
        period = {"start": start, "end": start + timedelta(hours=1), "price_p_per_kwh": -20}
        self.assertEqual(self.plan([period, period], start, capacity=1.5)["status"], "not_ready")
        conflict = {**period, "price_p_per_kwh": -10}
        self.assertEqual(self.plan([period, conflict], start)["reason"], "invalid_tariff_periods")
