"""Exercise actual adapter methods using isolated states and calendar responses."""

import ast
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
import math
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components/load_optimizer"))
from legacy import app_runtime
from legacy.config_validation import ConfigurationError, appliance_document

SOURCE = ROOT / "custom_components/load_optimizer/legacy_runtime.py"
tree = ast.parse(SOURCE.read_text())
tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef))
             or isinstance(node, ast.ClassDef) and node.name == "LegacyRuntime"]
namespace = {"asyncio": asyncio, "datetime": datetime, "timedelta": timedelta, "timezone": timezone,
             "logging": logging, "math": math, "re": re, "Any": object, "Callable": object, "HomeAssistant": object,
             "Store": Mock, "DOMAIN": "load_optimizer", "app_runtime": app_runtime,
             "unquote": unquote, "urlparse": urlparse, "ConfigurationError": ConfigurationError,
             "appliance_document": appliance_document,
             "CONF_INSTANCES_YAML": "instances_yaml", "CONF_GREEN_WINDOW_ENTITY": "green_window_entity",
             "CONF_BLOCKED_WINDOW_ENTITY": "blocked_window_entity"}
exec(compile(tree, str(SOURCE), "exec", flags=__import__("__future__").annotations.compiler_flag), namespace)
LegacyRuntime = namespace["LegacyRuntime"]


class AdapterSourceSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.values = {}
        self.hass = SimpleNamespace(states=SimpleNamespace(get=self.values.get),
                                    config=SimpleNamespace(time_zone="Europe/London"),
                                    services=SimpleNamespace(async_call=AsyncMock()))
        with patch.object(LegacyRuntime, "_patch_legacy_runtime"):
            self.runtime = LegacyRuntime(self.hass)
        self.options = {"instances_yaml": '- id: "1"\n  name: Synthetic\n  power_sensor: sensor.power',
                        "blocked_window_entity": "calendar.no_run"}
        self.request = {"start": self.now.isoformat(), "finish": (self.now + timedelta(hours=2)).isoformat()}
        self.put("sensor.power", "0")
        self.put("calendar.no_run", "off")

    def put(self, entity, state, **attributes):
        self.values[entity] = SimpleNamespace(state=state, attributes=attributes,
                                             last_changed=self.now, last_updated=self.now)

    async def check(self):
        return await self.runtime.async_automatic_start_block(self.options, self.request)

    def negative_fixture(self):
        self.options.update(tariff_entity="sensor.rates", tariff_price_unit="p_per_kwh")
        self.options["instances_yaml"] += '''
  program_policies:
    - program: Quick45
      enabled: true
      allow_negative_price_run: true
      maximum_runs_per_window: 1
'''
        self.request.update(mode="negative_price", automatic=True, program="Quick45",
                            finish=(self.now + timedelta(minutes=30)).isoformat())
        instance = {}
        cycle = {"runtime_minutes": 30, "energy_kwh": 0.7, "peak_power": 1000,
                 "sample_count": 31, "program": "Quick45",
                 "finish": (self.now - timedelta(days=1)).isoformat(),
                 "power_profile": [{"offset_seconds": 0, "power_w": 1000},
                                   {"offset_seconds": 1800, "power_w": 1000}]}
        for _ in range(5):
            app_runtime.update_program_model(instance, cycle)
        self.runtime.state = {"instances": {"1": instance}}
        self.put("sensor.rates", "ready", rates=[
            {"start": self.now.isoformat(), "end": (self.now + timedelta(hours=1)).isoformat(),
             "price": -1},
            {"start": (self.now + timedelta(hours=1)).isoformat(),
             "end": (self.now + timedelta(hours=6)).isoformat(), "price": 20},
        ])
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": []}}

    async def negative_check(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return self.now

        with patch.dict(namespace, datetime=Clock), \
             patch.object(app_runtime, "source_state", self.runtime._source_state), \
             patch.object(app_runtime, "publish_entity"):
            return await self.check()

    async def test_negative_preflight_reprices_actual_programme_without_mutating_learning(self):
        self.negative_fixture()
        before = deepcopy(self.runtime.state)
        self.assertIsNone(await self.negative_check())
        self.assertEqual(self.runtime.state, before)
        self.request["program"] = "Unlearned"
        self.assertEqual(await self.negative_check(), "negative_price_program_unavailable")

    async def test_negative_preflight_rejects_revised_positive_prices_without_a_scan(self):
        self.negative_fixture()
        self.assertIsNone(await self.negative_check())
        self.values["sensor.rates"].attributes["rates"][0]["price"] = 25
        self.assertEqual(await self.negative_check(), "power_hungry_window_outside_negative_price")

    async def test_free_calendar_is_fetched_fresh_and_cancellation_vetoes_command(self):
        self.negative_fixture()
        self.options["free_window_entity"] = "calendar.free"
        self.put("calendar.free", "on", start_time=self.now.isoformat(), end_time=(self.now + timedelta(hours=1)).isoformat())
        self.values["sensor.rates"].attributes["rates"][0]["price"] = 25
        events = [{"start": self.now.isoformat(), "end": (self.now + timedelta(hours=1)).isoformat()}]
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": []}, "calendar.free": {"events": events}}
        before = deepcopy(self.runtime.state)
        self.assertIsNone(await self.negative_check())
        self.assertEqual(self.runtime.state, before)
        self.hass.services.async_call.return_value["calendar.free"]["events"] = []
        self.assertEqual(await self.negative_check(), "power_hungry_window_outside_negative_price")

    async def test_free_source_failure_and_power_down_take_precedence(self):
        self.negative_fixture()
        self.options["free_window_entity"] = "calendar.free"
        self.put("calendar.free", "unavailable")
        self.assertEqual(await self.negative_check(), "free_window_source_unavailable")
        self.put("calendar.free", "on")
        events = [{"start": self.now.isoformat(), "end": (self.now + timedelta(hours=1)).isoformat()}]
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": events}, "calendar.free": {"events": events}}
        self.assertEqual(await self.negative_check(), "blocked_window_overlap")

    async def test_negative_preflight_rejects_missing_unavailable_and_incomplete_tariffs(self):
        self.negative_fixture()
        self.values.pop("sensor.rates")
        self.assertEqual(await self.negative_check(), "negative_price_tariff_unavailable")
        self.put("sensor.rates", "unavailable", rates=[{
            "start": self.now.isoformat(), "end": (self.now + timedelta(hours=1)).isoformat(), "price": -1}])
        self.assertEqual(await self.negative_check(), "negative_price_tariff_unavailable")
        self.put("sensor.rates", "ready", rates=[{
            "start": self.now.isoformat(), "end": (self.now + timedelta(minutes=29)).isoformat(), "price": -1}])
        self.assertEqual(await self.negative_check(), "negative_price_cycle_not_fully_priced")

    async def test_negative_preflight_checks_live_policy_and_window_cap(self):
        self.negative_fixture()
        self.options["instances_yaml"] = self.options["instances_yaml"].replace(
            "allow_negative_price_run: true", "allow_negative_price_run: false")
        self.assertEqual(await self.negative_check(), "negative_price_program_not_permitted")
        self.options["instances_yaml"] = self.options["instances_yaml"].replace(
            "allow_negative_price_run: false", "allow_negative_price_run: true")
        model = self.runtime.state["instances"]["1"]["program_models"]["Quick45"]
        model["recent_cycles"].append({"finish": self.now.isoformat(), "runtime_minutes": 1})
        model["runs"] += 1
        self.values["sensor.rates"].attributes["rates"][0]["start"] = (
            self.now - timedelta(minutes=30)).isoformat()
        self.assertEqual(await self.negative_check(), "maximum_runs_per_window_reached")

    async def test_negative_preflight_respects_live_deadline_and_remote_exclusion(self):
        self.negative_fixture()
        self.options["instances_yaml"] += "\n  schedule_latest_finish_entity: input_datetime.deadline\n"
        self.put("input_datetime.deadline", (self.now + timedelta(minutes=29)).isoformat())
        self.assertEqual(await self.negative_check(), "negative_price_outside_schedule_constraints")
        self.put("input_datetime.deadline", (self.now + timedelta(minutes=30)).isoformat())
        self.assertIsNone(await self.negative_check())
        self.put("input_text.load_optimizer_1_remote_start_blocked_programs", "Quick45")
        self.assertEqual(await self.negative_check(), "negative_price_program_not_permitted")

    async def test_negative_preflight_uses_time_after_awaited_calendar_fetch(self):
        self.negative_fixture()
        self.values["sensor.rates"].attributes["rates"][0]["end"] = (
            self.now + timedelta(minutes=30, seconds=5)).isoformat()
        self.values["sensor.rates"].attributes["rates"][1]["start"] = (
            self.now + timedelta(minutes=30, seconds=5)).isoformat()

        async def fetch(*_args, **_kwargs):
            self.now += timedelta(seconds=6)
            return {"calendar.no_run": {"events": []}}

        self.hass.services.async_call.side_effect = fetch
        self.assertEqual(await self.negative_check(), "power_hungry_window_outside_negative_price")

    async def test_negative_preflight_uses_learned_duration_for_full_cycle_calendar_check(self):
        self.negative_fixture()
        self.request["finish"] = (self.now + timedelta(minutes=1)).isoformat()
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": [{
            "start": (self.now + timedelta(minutes=20)).isoformat(),
            "end": (self.now + timedelta(minutes=40)).isoformat(),
        }]}}
        self.assertEqual(await self.negative_check(), "blocked_window_overlap")

    async def test_negative_preflight_rejects_conflicting_rates_but_deduplicates_identical_sources(self):
        self.negative_fixture()
        self.options["tariff_entities"] = "sensor.rates,sensor.same_rates"
        self.put("sensor.same_rates", "ready", rates=deepcopy(self.values["sensor.rates"].attributes["rates"]))
        self.assertIsNone(await self.negative_check())
        self.values["sensor.same_rates"].attributes["rates"][0]["price"] = 25
        self.assertEqual(await self.negative_check(), "negative_price_tariff_invalid")

    async def test_negative_preflight_distinguishes_unpublished_rates_from_malformed_published_rates(self):
        self.negative_fixture()
        self.options["tariff_entities"] = "sensor.rates,event.future_rates"
        self.put("event.future_rates", "ready", rates=[])
        self.assertIsNone(await self.negative_check())
        self.put("event.future_rates", "ready", rates=[{
            "start": self.now.isoformat(), "end": (self.now + timedelta(hours=1)).isoformat(),
            "price": "NaN"}])
        self.assertEqual(await self.negative_check(), "negative_price_tariff_invalid")

    async def test_negative_preflight_rechecks_manual_free_window_helpers(self):
        self.negative_fixture()
        self.values["sensor.rates"].attributes["rates"][0]["price"] = 25
        helpers = app_runtime.SPECIAL_PRICE_WINDOW_ENTITIES
        self.put(helpers["enabled"], "on")
        self.put(helpers["start"], self.now.isoformat())
        self.put(helpers["end"], (self.now + timedelta(hours=1)).isoformat())
        self.put(helpers["price"], "0")
        self.assertIsNone(await self.negative_check())
        self.put(helpers["enabled"], "off")
        self.assertEqual(await self.negative_check(), "power_hungry_window_outside_negative_price")

    async def test_negative_preflight_rejects_model_growth_during_calendar_fetch(self):
        self.negative_fixture()

        async def fetch(*_args, **_kwargs):
            model = self.runtime.state["instances"]["1"]["program_models"]["Quick45"]
            model["statistics"]["runtime_minutes"]["mean"] = 60
            return {"calendar.no_run": {"events": []}}

        self.hass.services.async_call.side_effect = fetch
        self.assertEqual(await self.negative_check(), "negative_price_model_changed")

    async def test_calendar_failure_is_not_cached_as_valid_empty_and_recovers(self):
        self.hass.services.async_call.side_effect = RuntimeError("Synthetic fetch failure")
        await self.runtime._async_prefetch_calendar_events([{"blocked_window_entity": "calendar.no_run"}], self.now)
        self.assertIsNone(self.runtime._api_request("synthetic", "/calendars/calendar.no_run"))
        self.assertEqual(await self.check(), "blocked_window_source_unavailable")
        self.hass.services.async_call.side_effect = None
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": []}}
        await self.runtime._async_prefetch_calendar_events([{"blocked_window_entity": "calendar.no_run"}], self.now)
        self.assertEqual(self.runtime._api_request("synthetic", "/calendars/calendar.no_run"), [])
        self.assertIsNone(await self.check())

    async def test_invalid_responses_fail_closed(self):
        for response in (None, {}, {"calendar.no_run": {}}, {"calendar.no_run": {"events": "invalid"}}):
            with self.subTest(response=response):
                self.hass.services.async_call.return_value = response
                self.assertEqual(await self.check(), "blocked_window_source_unavailable")

    async def test_all_day_no_run_uses_home_timezone_not_utc_midnight(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 7, 24, 22, 30, tzinfo=timezone.utc)

        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": [{
            "start": {"date": "2026-07-25"}, "end": {"date": "2026-07-26"},
        }]}}
        self.request = {"start": "2026-07-24T22:30:00+00:00", "finish": "2026-07-24T23:15:00+00:00"}
        with patch.dict(namespace, datetime=Clock):
            self.assertEqual(await self.check(), "blocked_window_overlap")

    async def test_overlapping_new_event_blocks_queued_start(self):
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": [{
            "start": (self.now + timedelta(minutes=90)).isoformat(),
            "end": (self.now + timedelta(minutes=120)).isoformat(),
        }]}}
        self.assertEqual(await self.check(), "blocked_window_overlap")

    async def test_fetch_latency_does_not_leave_the_end_of_the_cycle_unchecked(self):
        class Clock(datetime):
            current = self.now

            @classmethod
            def now(cls, tz=None):
                return cls.current

        async def fetch(*_args, **_kwargs):
            Clock.current += timedelta(seconds=8)
            return {"calendar.no_run": {"events": [{
                "start": (self.now + timedelta(hours=2, seconds=4)).isoformat(),
                "end": (self.now + timedelta(hours=3)).isoformat(),
            }]}}

        self.hass.services.async_call.side_effect = fetch
        with patch.dict(namespace, datetime=Clock):
            self.assertEqual(await self.check(), "blocked_window_overlap")

    async def test_unavailable_state_after_fetch_blocks_start(self):
        async def fetch(*_args, **_kwargs):
            self.put("calendar.no_run", "unavailable")
            return {"calendar.no_run": {"events": []}}
        self.hass.services.async_call.side_effect = fetch
        self.assertEqual(await self.check(), "blocked_window_source_unavailable")

    async def test_fresh_power_source_is_required_even_without_a_calendar(self):
        self.options["blocked_window_entity"] = ""
        for value in ("unavailable", "unknown", "NaN", "inf", "-1"):
            self.put("sensor.power", value)
            self.assertEqual(await self.check(), "power_source_unavailable")
        self.put("sensor.power", "0")
        self.assertIsNone(await self.check())
        self.hass.services.async_call.assert_not_awaited()

    async def test_multiple_sources_and_missing_duration_are_enforced(self):
        self.options["blocked_window_entity"] = "event.good,event.missing"
        self.put("event.good", "ready", events=[])
        self.assertEqual(await self.check(), "blocked_window_source_unavailable")
        self.put("event.missing", "ready", events=[])
        self.assertIsNone(await self.check())
        self.request["finish"] = None
        self.assertEqual(await self.check(), "blocked_window_duration_unavailable")

    async def test_calendar_prefetch_covers_longest_cycle_after_each_start_horizon(self):
        def instance(minutes):
            return {"program_models": {"Synthetic": {"statistics": {
                "runtime_minutes": {"count": 1, "mean": minutes, "m2": 0},
            }}}}

        self.runtime.state = {"instances": {"1": instance(120), "2": instance(90)}}
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": []}}
        await self.runtime._async_prefetch_calendar_events([
            {"instance_id": "1", "cost_search_hours": 24, "cost_forecast_hours": 12,
             "blocked_window_entity": "calendar.no_run"},
            {"instance_id": "2", "cost_search_hours": 12, "cost_forecast_hours": 48,
             "green_window_entity": "calendar.no_run"},
        ], self.now)
        request = self.hass.services.async_call.await_args.args[2]
        self.assertEqual(datetime.fromisoformat(request["end_date_time"]),
                         self.now + timedelta(hours=49, minutes=30))
        self.hass.services.async_call.assert_awaited_once()

    async def test_prefetch_covers_new_longer_model_when_active_capture_finishes(self):
        self.runtime.state = {"instances": {"1": {
            "cycle_start": (self.now - timedelta(hours=3)).isoformat(),
            "program_models": {"Synthetic": {"statistics": {
                "runtime_minutes": {"count": 1, "mean": 30, "m2": 0},
            }}},
        }}}
        self.hass.services.async_call.return_value = {"calendar.no_run": {"events": []}}
        await self.runtime._async_prefetch_calendar_events([
            {"instance_id": "1", "cost_search_hours": 24,
             "blocked_window_entity": "calendar.no_run"},
        ], self.now)
        request = self.hass.services.async_call.await_args.args[2]
        self.assertEqual(datetime.fromisoformat(request["end_date_time"]),
                         self.now + timedelta(hours=27))


if __name__ == "__main__":
    unittest.main()
