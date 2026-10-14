"""Regression checks for missing measurements and mandatory no-run sources."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from legacy import app_runtime as app


class CaptureDataSafetyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 10, tzinfo=timezone.utc)
        self.config = {
            "instance_id": "1", "name": "Synthetic appliance", "power_sensor": "sensor.power",
            "energy_sensor": "sensor.energy", "program_sensor": "sensor.program", "state_sensor": "",
            "active_power_threshold": 10, "finish_delay": 2,
        }
        self.sources = {"sensor.power": {"state": "1000"}, "sensor.energy": {"state": "1"},
                        "sensor.program": {"state": "MixedLoad"}}
        self.database = {"schema_version": 1, "instances": {}}
        for target, kwargs in (
            ("source_state", {"side_effect": lambda _token, entity: self.sources.get(entity)}),
            ("api_request", {"return_value": None}), ("publish_entity", {}),
        ):
            mock = patch.object(app, target, **kwargs)
            setattr(self, target, mock.start())
            self.addCleanup(mock.stop)
        for minute in range(7):
            self.scan(minute)

    def scan(self, minute):
        app.update_instance("synthetic", self.database, self.config, self.now + timedelta(minutes=minute))

    def status(self):
        return next(call for call in reversed(self.publish_entity.call_args_list)
                    if call.args[1] == "sensor.load_optimizer_1_status")

    def test_invalid_power_does_not_finish_or_grow_capture(self):
        for value in (None, "unknown", "unavailable", "NaN", "inf", "-inf", "-10", True):
            with self.subTest(value=value):
                original = deepcopy(self.database)
                self.sources["sensor.power"] = {"state": value} if value is not None else None
                for minute in range(7, 75):
                    self.scan(minute)
                instance = self.database["instances"]["1"]
                self.assertIn("cycle_start", instance)
                self.assertEqual(instance["samples"], 7)
                self.assertEqual(instance.get("runs", 0), 0)
                self.assertEqual(instance["below_threshold"], 0)
                self.assertNotIn("last_cycle", instance)
                self.assertNotIn("finish_candidate", instance)
                self.assertEqual(self.status().args[2], "source_unavailable")
                self.assertEqual(self.status().args[3]["health_status"], "power_source_unavailable")
                self.database = original

    def test_outage_resets_low_power_debounce_and_recovery_excludes_learning(self):
        self.sources["sensor.power"]["state"] = "0"
        self.scan(7)
        self.sources["sensor.power"]["state"] = "unavailable"
        self.scan(8)
        # Persistence keeps the gap marker; no conversion to invented zero power.
        self.database = json.loads(json.dumps(self.database))
        self.sources["sensor.power"]["state"] = "1000"
        self.scan(9)
        self.assertIn("cycle_start", self.database["instances"]["1"])
        self.sources["sensor.power"]["state"] = "0"
        self.scan(10)
        self.assertIn("cycle_start", self.database["instances"]["1"])
        self.scan(11)
        instance = self.database["instances"]["1"]
        self.assertNotIn("cycle_start", instance)
        self.assertEqual(instance.get("runs", 0), 0)
        discarded = instance["last_discarded_cycle"]
        self.assertEqual(discarded["exclusion_reason"], "power_source_gap_during_cycle")
        self.assertIsNone(discarded["energy_kwh"])
        self.scan(12)
        self.assertEqual(instance.get("runs", 0), 0)
        self.assertEqual(len(instance["quality_excluded_cycles"]), 1)
        # A later uninterrupted cycle still learns normally.
        self.sources["sensor.power"]["state"] = "1000"
        for minute in range(13, 20):
            self.scan(minute)
        self.sources["sensor.power"]["state"] = "0"
        self.scan(20)
        self.scan(21)
        self.assertEqual(instance["runs"], 1)

    def test_terminal_signal_during_outage_can_end_but_not_learn_capture(self):
        self.config["state_sensor"] = "sensor.operation"
        self.sources["sensor.operation"] = {"state": "BSH.Common.EnumType.OperationState.Ready"}
        self.sources["sensor.power"]["state"] = "unavailable"
        self.scan(7)
        instance = self.database["instances"]["1"]
        self.assertNotIn("cycle_start", instance)
        self.assertEqual(instance.get("runs", 0), 0)
        self.assertEqual(instance["last_discarded_cycle"]["completion_signal"], "bosch_operation_ready")

    def test_existing_learning_and_last_valid_cycle_are_not_rewritten(self):
        instance = self.database["instances"]["1"]
        old_cycle = {"program": "MixedLoad", "runtime_minutes": 108, "energy_kwh": 0.9,
                     "peak_power": 2440, "sample_count": 10, "finish": self.now.isoformat(),
                     "power_profile": [{"offset_seconds": 0, "power_w": 1000},
                                       {"offset_seconds": 6480, "power_w": 0}]}
        app.update_program_model(instance, old_cycle)
        instance["runs"] = 101
        instance["last_cycle"] = old_cycle
        before = deepcopy(instance["program_models"])
        self.sources["sensor.power"]["state"] = "unavailable"
        self.scan(7)
        self.scan(8)
        self.sources["sensor.power"]["state"] = "0"
        self.scan(9)
        self.scan(10)
        self.assertEqual(instance["runs"], 101)
        self.assertEqual(instance["program_models"], before)
        self.assertEqual(instance["last_cycle"], old_cycle)

    def test_real_low_power_without_outage_still_learns(self):
        self.sources["sensor.power"]["state"] = "0"
        self.scan(7)
        self.scan(8)
        instance = self.database["instances"]["1"]
        self.assertEqual(instance["runs"], 1)
        self.assertEqual(instance["last_cycle"]["completion_signal"], "power_below_threshold")

    def test_invalid_energy_does_not_poison_valid_power_profile(self):
        self.sources["sensor.energy"]["state"] = "NaN"
        self.sources["sensor.power"]["state"] = "0"
        self.scan(7)
        self.scan(8)
        instance = self.database["instances"]["1"]
        self.assertEqual(instance["runs"], 1)
        self.assertIsNone(instance["last_cycle"]["energy_sensor_delta_kwh"])
        json.dumps(self.database, allow_nan=False)

    def test_unreadable_no_run_source_blocks_published_intents_without_hiding_price_estimates(self):
        self.sources["sensor.power"]["state"] = "0"
        self.scan(7)
        self.scan(8)
        self.config.update(
            tariff_entity="sensor.rates", tariff_entities=["sensor.rates"], tariff_timezone="Europe/London",
            tariff_price_unit="gbp_per_kwh", cost_search_hours=2, cost_candidate_interval=5,
            publish_diagnostics=False, blocked_window_entity="calendar.no_run",
            program_policies=[{"program": "MixedLoad", "enabled": True, "allow_normal_recommendation": True}],
        )
        self.sources["sensor.rates"] = {"state": "ready", "attributes": {"rates": [{
            "start": self.now.isoformat(), "end": (self.now + timedelta(hours=3)).isoformat(),
            "value_inc_vat": 0.1,
        }]}}
        self.scan(9)
        published = {call.args[1]: call.args[2:] for call in self.publish_entity.call_args_list}
        cost, attributes = published["sensor.load_optimizer_1_cost_status"]
        self.assertEqual(cost, "ready")
        self.assertFalse(attributes["blocked_window_source_ready"])
        self.assertNotIn("blocked_window_diagnostic", attributes)
        now, attributes = published["sensor.load_optimizer_1_now_recommendation"]
        self.assertEqual(now, "blocked_window_unavailable")
        self.assertFalse(attributes["ready_to_start"])
        self.assertEqual(attributes["reason"], "blocked_window_source_unavailable")
        self.assertEqual(attributes["program_options"], [])
        self.assertTrue(attributes["display_program_options"])
        self.assertEqual(published["sensor.load_optimizer_1_schedule_status"][0], "blocked_window_unavailable")
        self.assertFalse(published["sensor.load_optimizer_1_schedule_status"][1]["automation_ready"])
        self.assertEqual(published["sensor.load_optimizer_1_good_to_start"][0], "off")
        self.assertEqual(published["sensor.load_optimizer_1_overnight_window_active"][0], "off")
        self.sources["calendar.no_run"] = {"state": "off", "attributes": {}}
        self.api_request.return_value = []
        self.scan(10)
        published = {call.args[1]: call.args[2:] for call in self.publish_entity.call_args_list}
        self.assertEqual(published["sensor.load_optimizer_1_now_recommendation"][0], "MixedLoad")
        self.assertTrue(published["sensor.load_optimizer_1_cost_status"][1]["blocked_window_source_ready"])


class NoRunSourceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 10, tzinfo=timezone.utc)
        self.source = patch.object(app, "source_state")
        self.api = patch.object(app, "api_request")
        self.state = self.source.start()
        self.events = self.api.start()
        self.addCleanup(self.source.stop)
        self.addCleanup(self.api.stop)

    def read(self, entity="calendar.no_run", green=False):
        reader = app.green_windows_from_entity if green else app.blocked_windows_from_entity
        return reader("synthetic", entity, start=self.now, end=self.now + timedelta(days=1))

    def test_unconfigured_is_distinct_from_valid_empty_calendar(self):
        self.assertEqual(self.read(""), ([], None))
        self.state.return_value = {"state": "off", "attributes": {}}
        self.events.return_value = []
        windows, health = self.read()
        self.assertEqual(windows, [])
        self.assertTrue(health["readable"])
        self.state.return_value["attributes"] = {"start_time": None, "end_time": None}
        self.assertTrue(self.read()[1]["readable"])

    def test_unavailable_state_or_failed_calendar_fetch_is_not_empty_success(self):
        self.events.return_value = []
        for state in (None, {"state": "unknown"}, {"state": "unavailable"}):
            with self.subTest(state=state):
                self.state.return_value = state
                self.assertFalse(self.read()[1]["readable"])
        self.state.return_value = {"state": "off", "attributes": {}}
        for response in (None, {}, "error", [None], [{"start": "bad", "end": "bad"}]):
            with self.subTest(response=response):
                self.events.return_value = response
                self.assertFalse(self.read()[1]["readable"])
        # Green windows remain optional/advisory.
        self.events.return_value = None
        self.assertTrue(self.read(green=True)[1]["readable"])

    def test_event_source_requires_a_valid_window_contract(self):
        for attributes, readable in (({}, False), ({"events": []}, True),
                                     ({"events": "bad"}, False), ({"events": [None]}, False),
                                     ({"events": [{"start": "bad", "end": "bad"}]}, False)):
            with self.subTest(attributes=attributes):
                self.state.return_value = {"state": "ready", "attributes": attributes}
                self.assertEqual(self.read("event.no_run")[1]["readable"], readable)

    def test_multiple_sources_require_all_to_be_readable_and_recover(self):
        self.state.side_effect = lambda _token, entity: (
            {"state": "ready", "attributes": {"events": []}} if entity == "event.good" else None)
        self.assertFalse(self.read("event.good,event.bad")[1]["readable"])
        self.state.side_effect = None
        self.state.return_value = {"state": "ready", "attributes": {"events": []}}
        self.assertTrue(self.read("event.good,event.bad")[1]["readable"])

    def test_valid_events_outside_horizon_are_readable_not_malformed(self):
        self.state.return_value = {"state": "ready", "attributes": {"events": [{
            "start": (self.now - timedelta(days=2)).isoformat(),
            "end": (self.now - timedelta(days=1)).isoformat(),
        }]}}
        windows, health = self.read("event.no_run")
        self.assertEqual(windows, [])
        self.assertTrue(health["readable"])


class PlanningWindowCoverageTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 10, tzinfo=timezone.utc)
        self.config = {
            "instance_id": "1", "name": "Synthetic appliance", "power_sensor": "sensor.power",
            "energy_sensor": "", "program_sensor": "", "state_sensor": "",
            "active_power_threshold": 10, "finish_delay": 2,
            "tariff_entities": ["sensor.rates"], "tariff_timezone": "Europe/London",
            "tariff_price_unit": "gbp_per_kwh", "cost_search_hours": 2,
            "cost_forecast_hours": 2, "cost_candidate_interval": 30,
            "cost_forecast_interval": 30, "publish_diagnostics": True,
            "blocked_window_entity": "event.no_run", "green_window_entity": "event.green",
            "program_policies": [{"program": "MixedLoad", "enabled": True,
                                  "allow_normal_recommendation": True}],
        }
        self.instance = {"runs": 5, "program_models": {}}
        cycle = {"program": "MixedLoad", "runtime_minutes": 120, "energy_kwh": 2,
                 "peak_power": 1000, "sample_count": 121, "finish": self.now.isoformat(),
                 "power_profile": [{"offset_seconds": 0, "power_w": 1000},
                                   {"offset_seconds": 7200, "power_w": 1000}]}
        for _ in range(5):
            app.update_program_model(self.instance, cycle)
        self.database = {"schema_version": 1, "instances": {"1": self.instance}}
        self.sources = {
            "sensor.power": {"state": "0"},
            "sensor.rates": {"state": "ready", "attributes": {"rates": [
                {"start": self.now.isoformat(), "end": (self.now + timedelta(hours=2)).isoformat(),
                 "value_inc_vat": 0.3},
                {"start": (self.now + timedelta(hours=2)).isoformat(),
                 "end": (self.now + timedelta(hours=6)).isoformat(), "value_inc_vat": 0.01},
            ]}},
            "event.no_run": {"state": "ready", "attributes": {"events": []}},
            "event.green": {"state": "ready", "attributes": {"events": []}},
        }
        for target, kwargs in (
            ("source_state", {"side_effect": lambda _token, entity: self.sources.get(entity)}),
            ("api_request", {"return_value": []}), ("publish_entity", {}),
        ):
            mock = patch.object(app, target, **kwargs)
            setattr(self, target, mock.start())
            self.addCleanup(mock.stop)

    def scan(self):
        memory = deepcopy(self.database)
        app.update_instance("synthetic", self.database, self.config, self.now)
        self.assertEqual(self.database, memory)
        return {call.args[1]: call.args[2:] for call in self.publish_entity.call_args_list}

    def event(self, start, finish):
        return {"start": (self.now + timedelta(hours=start)).isoformat(),
                "end": (self.now + timedelta(hours=finish)).isoformat()}

    def test_no_run_after_search_boundary_rejects_late_cheapest_start(self):
        self.sources["event.no_run"]["attributes"]["events"] = [self.event(3, 4)]
        published = self.scan()
        self.assertEqual(published["sensor.load_optimizer_1_cheapest_start"][0],
                         (self.now + timedelta(hours=1)).isoformat())
        status = published["sensor.load_optimizer_1_cost_status"][1]
        self.assertEqual(status["blocked_window_count"], 1)
        self.assertGreater(status["blocked_window_candidate_count"], 0)

    def test_forecast_tail_is_checked_when_forecast_is_longer_than_search(self):
        self.config["cost_forecast_hours"] = 4
        self.sources["event.no_run"]["attributes"]["events"] = [self.event(5, 6)]
        published = self.scan()
        forecast = published["sensor.load_optimizer_1_cost_forecast"][1]["forecast"]
        self.assertTrue(forecast)
        self.assertTrue(all(datetime.fromisoformat(point["finish"]) <= self.now + timedelta(hours=5)
                            for point in forecast))

    def test_green_overlap_covers_tail_without_extending_candidate_starts(self):
        self.sources["event.green"]["attributes"]["events"] = [self.event(3, 4)]
        published = self.scan()
        self.assertEqual(published["sensor.load_optimizer_1_cheapest_start"][0],
                         (self.now + timedelta(hours=2)).isoformat())
        status = published["sensor.load_optimizer_1_cost_status"][1]
        self.assertEqual(status["green_window_count"], 1)
        greenest = published["sensor.load_optimizer_1_greenest_cost"][1]
        self.assertEqual(greenest["green_window_overlap_percent"], 50)

    def test_event_beginning_at_cycle_finish_does_not_block_that_candidate(self):
        self.sources["event.no_run"]["attributes"]["events"] = [self.event(4, 5)]
        published = self.scan()
        self.assertEqual(published["sensor.load_optimizer_1_cheapest_start"][0],
                         (self.now + timedelta(hours=2)).isoformat())

    def test_duration_padding_does_not_change_saved_search_settings_or_learning(self):
        before = deepcopy(self.config)
        self.assertEqual(app.planning_window_end(self.config, self.instance, self.now),
                         self.now + timedelta(hours=4))
        self.assertEqual(self.config, before)
        self.assertEqual(app.planning_window_end(self.config, {}, self.now),
                         self.now + timedelta(hours=2))

    def test_active_elapsed_padding_rounds_up_like_a_new_learned_summary(self):
        self.instance["cycle_start"] = (self.now - timedelta(hours=3, seconds=4)).isoformat()
        self.assertEqual(app.planning_window_end(self.config, self.instance, self.now),
                         self.now + timedelta(hours=5, seconds=6))

    def test_invalid_horizons_or_durations_reject_calendar_range(self):
        for invalid in (float("nan"), float("inf"), -1, 73):
            with self.subTest(horizon=invalid):
                with self.assertRaises(ValueError):
                    app.planning_window_end({**self.config, "cost_forecast_hours": invalid},
                                            self.instance, self.now)
        for invalid in (float("nan"), float("inf"), -1, 1e300):
            with self.subTest(duration=invalid):
                instance = deepcopy(self.instance)
                instance["program_models"]["MixedLoad"]["statistics"]["runtime_minutes"]["mean"] = invalid
                with self.assertRaises(ValueError):
                    app.planning_window_end(self.config, instance, self.now)


if __name__ == "__main__":
    unittest.main()
