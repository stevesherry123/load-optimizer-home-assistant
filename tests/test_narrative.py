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
        self.call = AsyncMock(return_value={"data": "Prices vary moderately, with a pronounced evening peak."})
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

    async def test_authoritative_facts_are_rendered_from_analysis(self):
        self.analysis["tomorrow_date"] = "2026-10-09"
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["text"].startswith("2026-10-09. Tomorrow averages 20 p/kWh."))
        self.assertIn("Prices vary moderately", result["text"])

    async def test_real_provider_incorrect_coverage_is_rejected(self):
        self.call.return_value = {"data": (
            "On 17 October 2026, prices are warming up, averaging 33.47 p/kWh up to 22:00. "
            "Prices are available from midnight to 12:00, while the trailing prices remain unknown.")}
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "unverified_narrative_facts")
        self.assertIsNone(result["text"])
        self.assertEqual(self.call.await_count, 1)

    async def test_spelled_out_coverage_and_warmup_claims_are_rejected(self):
        for text in ("Prices are available until midnight.", "Prices are warming up.",
                     "Only the morning hours are published."):
            self.call.return_value = {"data": text}
            result = await self.narrative.async_generate(self.analysis, "ai_task.test")
            self.assertEqual(result["reason"], "unverified_narrative_facts")
            self.assertIsNone(result["text"])

    async def test_usable_partial_analysis_can_generate_with_explicit_scope(self):
        self.analysis.update(tomorrow_complete=False, forecast_usable=True, tomorrow_date="2026-10-09",
                             analysis_scope="published_hours", forecast_fingerprint="synthetic-rates-1",
                             forecast_coverage={"status": "partial_day", "start": "2026-10-08T23:00:00Z",
                                                "end": "2026-10-09T22:00:00Z", "known_minutes": 1380,
                                                "trailing_missing_minutes": 60, "source_id": "DO_NOT_SEND"})
        result = await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.assertEqual(result["status"], "ready")
        instructions = self.call.call_args.args[2]["instructions"]
        self.assertIn("partial_day", instructions)
        self.assertIn("trailing prices are unknown", instructions)
        self.assertIn("Europe/London", instructions)
        self.assertNotIn("DO_NOT_SEND", instructions)
        self.assertNotIn("synthetic-rates-1", instructions)

    async def test_coverage_or_source_error_vetoes_even_complete_analysis(self):
        for status in ("limited", "error", "ready"):
            self.analysis.update(status=status, forecast_usable=False)
            self.assertEqual((await self.narrative.async_generate(self.analysis, "ai_task.test"))["status"], "waiting")
        self.call.assert_not_called()

    async def test_rate_only_or_coverage_revision_invalidates_summary_without_recalling(self):
        self.analysis["forecast_fingerprint"] = "synthetic-rates-1"
        await self.narrative.async_generate(self.analysis, "ai_task.test")
        self.analysis["forecast_fingerprint"] = "synthetic-rates-2"
        self.assertEqual(self.narrative.snapshot(self.analysis)["status"], "stale")
        self.analysis["forecast_fingerprint"] = "synthetic-rates-1"
        self.analysis["forecast_coverage"] = {"end": "2026-10-09T22:30:00Z"}
        self.assertIsNone(self.narrative.snapshot(self.analysis)["text"])
        self.assertEqual(self.call.await_count, 1)

    async def test_revision_during_generation_never_returns_old_ready_text(self):
        gate = asyncio.Event()
        async def provider(*args, **kwargs):
            await gate.wait()
            return {"data": "A summary of the earlier prices."}
        self.call.side_effect = provider
        self.analysis["forecast_fingerprint"] = "synthetic-rates-1"
        task = asyncio.create_task(self.narrative.async_generate(self.analysis, "ai_task.test"))
        await asyncio.sleep(0)
        self.analysis["forecast_fingerprint"] = "synthetic-rates-2"
        gate.set()
        result = await task
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["text"])
        self.assertEqual(self.call.await_count, 1)

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
