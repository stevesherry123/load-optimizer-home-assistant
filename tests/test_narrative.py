"""Narrative privacy, isolation, failure and freshness checks."""

import copy
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

PATH = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/narrative.py"
spec = importlib.util.spec_from_file_location("optional_narrative_test", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NarrativeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.call = AsyncMock(return_value={"data": "Tomorrow is typical; prices are lower overnight."})
        self.hass = SimpleNamespace(services=SimpleNamespace(has_service=lambda *args: True, async_call=self.call))
        self.narrative = module.OptionalNarrative(self.hass)
        self.analysis = {"status": "ready", "tomorrow_complete": True, "timezone": "Europe/London",
                         "updated_at": "2026-10-08T12:00:00+00:00", "tomorrow_classification": "warming_up",
                         "baseline_status": "warming_up", "summary": "Tomorrow averages 20 p/kWh.",
                         "storage": {"secret": "DO_NOT_SEND"}, "raw_history": ["DO_NOT_SEND"]}

    async def test_disabled_by_default_and_no_background_calls(self):
        self.assertEqual(self.narrative.snapshot(self.analysis)["status"], "disabled")
        self.call.assert_not_called()

    async def test_compact_input_privacy_and_pending_ready_updates(self):
        changes = []
        self.narrative.on_update = lambda: changes.append(self.narrative.state["status"])
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(changes, ["pending", "ready"])
        args = self.call.call_args.args
        self.assertEqual(args[:2], ("ai_task", "generate_data"))
        self.assertNotIn("DO_NOT_SEND", args[2]["instructions"])
        self.assertNotIn("raw_history", args[2]["instructions"])
        self.assertIn("warming_up", args[2]["instructions"])

    async def test_incomplete_analysis_cannot_generate(self):
        self.analysis["tomorrow_complete"] = False
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "waiting")
        self.call.assert_not_called()

    async def test_provider_failure_does_not_change_analysis(self):
        before = copy.deepcopy(self.analysis)
        self.call.side_effect = RuntimeError("sensitive provider details")
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "RuntimeError")
        self.assertEqual(self.analysis, before)

    async def test_missing_service_and_bad_response_fail_independently(self):
        self.hass.services.has_service = lambda *args: False
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["reason"], "ai_task_unavailable")
        self.call.assert_not_called()
        self.hass.services.has_service = lambda *args: True
        self.call.return_value = {"data": {"unexpected": "object"}}
        self.assertEqual((await self.narrative.async_generate(self.analysis, "ai_task.test"))["status"], "failed")

    async def test_changed_rates_or_date_hide_stale_text(self):
        await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.analysis["updated_at"] = "2026-10-09T12:00:00+00:00"
        result = self.narrative.snapshot(self.analysis)
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["text"])

    async def test_provider_timeout_is_independent(self):
        self.call.side_effect = asyncio.TimeoutError()
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "TimeoutError")

    async def test_duplicate_concurrent_request_does_not_call_provider_twice(self):
        gate = asyncio.Event()
        async def provider(*args, **kwargs):
            await gate.wait()
            return {"data": "A verified short summary."}
        self.call.side_effect = provider
        task = asyncio.create_task(self.narrative.async_generate(self.analysis, "ai_task.test"))
        await asyncio.sleep(0)
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "pending")
        gate.set()
        await task
        self.assertEqual(self.call.call_count, 1)
