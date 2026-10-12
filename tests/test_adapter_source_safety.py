"""Exercise actual adapter methods using isolated states and calendar responses."""

import ast
import asyncio
from datetime import datetime, timedelta, timezone
import logging
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
             "logging": logging, "re": re, "Any": object, "Callable": object, "HomeAssistant": object,
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


if __name__ == "__main__":
    unittest.main()
