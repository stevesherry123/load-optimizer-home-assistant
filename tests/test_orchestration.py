"""Execute the native scheduler with isolated Home Assistant I/O."""

import ast
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo


SOURCE = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/orchestration.py"
tree = ast.parse(SOURCE.read_text())
tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
namespace = {
    "asyncio": asyncio, "datetime": datetime, "timedelta": timedelta,
    "timezone": timezone, "logging": logging, "ZoneInfo": ZoneInfo,
    "Any": object, "Callable": object, "HomeAssistant": object, "ConfigEntry": object,
    "OrchestrationMigration": object, "Event": object, "callback": lambda fn: fn,
    "Store": Mock, "DOMAIN": "load_optimizer", "STATE_ON": "on",
    "LEGACY_AUTOMATION_IDS": [], "HomeAssistantError": RuntimeError,
}
exec(compile(tree, str(SOURCE), "exec", flags=__import__("__future__").annotations.compiler_flag), namespace)
NativeOrchestrator = namespace["NativeOrchestrator"]


class Clock(datetime):
    current = datetime(2026, 10, 8, 15, 13, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.values = {}
        self.tasks = []

        def schedule(coroutine):
            task = asyncio.create_task(coroutine)
            self.tasks.append(task)
            return task

        self.hass = SimpleNamespace(
            states=SimpleNamespace(get=self.values.get),
            config=SimpleNamespace(time_zone="Europe/London"),
            services=SimpleNamespace(async_call=AsyncMock()),
            async_create_task=Mock(side_effect=schedule),
        )
        self.scheduler = NativeOrchestrator(self.hass, SimpleNamespace(entry_id="test"), None)
        self.scheduler.store = SimpleNamespace(async_save=AsyncMock())
        self.scheduler.state = {**namespace["CONTROL_DEFAULTS"], "schedule_events": [], "run_history": []}
        self.scheduler.state.update(active=True, auto_mode_enabled=True, door_opened_since_last_cycle=True)
        self.scheduler.config = {
            "bosch_operation_state_sensor": "sensor.operation",
            "bosch_door_sensor": "binary_sensor.door",
            "bosch_connected_sensor": "binary_sensor.connected",
            "bosch_remote_control_sensor": "binary_sensor.remote_control",
            "bosch_remote_start_sensor": "binary_sensor.remote_start",
            "bosch_power_switch": "switch.power",
        }
        self.put("sensor.operation", "BSH.Common.EnumType.OperationState.Ready")
        self.put("sensor.load_optimizer_1_cycle_state", "idle")
        self.put("sensor.load_optimizer_1_status", "ready")
        self.put("sensor.load_optimizer_1_last_finish", "2026-10-07T22:04:12+00:00")
        self.put("sensor.load_optimizer_1_schedule_status", "ready", confidence_threshold=50)
        self.put("sensor.load_optimizer_1_overnight_recommendation", "Quick45", status="ready",
                 program="Quick45", start="2026-10-08T22:00:00+00:00", confidence=88)
        for entity in ("connected", "remote_control", "remote_start"):
            self.put("binary_sensor." + entity, "on")
        self.put("binary_sensor.door", "off")
        self.clock = patch.dict(namespace, datetime=Clock)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        Clock.current = datetime(2026, 10, 8, 15, 13, tzinfo=timezone.utc)

    def put(self, entity_id, state, **attributes):
        self.values[entity_id] = SimpleNamespace(state=state, attributes=attributes,
                                                last_changed=Clock.current)

    async def test_firmware_update_does_not_cancel_overnight_request_or_claim_completion(self):
        await self.scheduler.async_evaluate(datetime(2026, 10, 8, 15, 0, 33, tzinfo=timezone.utc))
        queued = dict(self.scheduler.state["request"])
        self.put("sensor.load_optimizer_1_last_discarded_cycle", "ready",
                 exclusion_reason="runtime_below_5_minutes", runtime_minutes=3.4, peak_power_w=4.2)
        await self.scheduler._async_record_cycle_end(datetime(2026, 10, 8, 15, 9, tzinfo=timezone.utc))
        self.assertEqual(self.scheduler.state["request"], queued)
        self.assertEqual(self.scheduler.state["execution_status"], "queued")
        self.assertNotEqual(self.scheduler.state["last_result"], "completed")
        self.assertTrue(self.scheduler.state["door_opened_since_last_cycle"])
        event = self.scheduler.state["schedule_events"][0]
        self.assertEqual(event["event"], "capture_ignored")
        self.assertTrue(event["pending_request_preserved"])
        self.hass.services.async_call.assert_not_awaited()

    async def test_valid_learned_wash_still_confirms_completion(self):
        self.put("sensor.load_optimizer_1_last_finish", "2026-10-08T15:12:42+00:00")
        await self.scheduler._async_record_cycle_end(datetime(2026, 10, 8, 14, tzinfo=timezone.utc))
        self.assertEqual(self.scheduler.state["last_result"], "completed")
        self.assertEqual(self.scheduler.state["execution_status"], "idle")

    async def test_observed_real_run_can_complete_even_when_learning_is_rejected(self):
        self.scheduler.state["confirmed_cycle_started_at"] = "2026-10-08T15:09:05+00:00"
        await self.scheduler._async_record_cycle_end(datetime(2026, 10, 8, 15, 9, tzinfo=timezone.utc))
        self.assertEqual(self.scheduler.state["last_result"], "completed")

    async def test_old_confirmed_run_does_not_validate_a_new_firmware_capture(self):
        self.scheduler.state["confirmed_cycle_started_at"] = "2026-10-07T21:10:00+00:00"
        await self.scheduler._async_record_cycle_end(datetime(2026, 10, 8, 15, 9, tzinfo=timezone.utc))
        self.assertIsNone(self.scheduler.state["last_result"])

    async def test_power_only_capture_does_not_reset_loaded_door_flag(self):
        event = SimpleNamespace(data={"entity_id": "sensor.load_optimizer_1_cycle_state",
            "new_state": SimpleNamespace(state="running"), "old_state": SimpleNamespace(state="idle")})
        self.put("sensor.load_optimizer_1_cycle_state", "running")
        self.scheduler._async_state_changed(event)
        await asyncio.gather(*self.tasks)
        self.assertTrue(self.scheduler.state["door_opened_since_last_cycle"])

    async def test_observed_bosch_run_resets_door_flag_and_records_real_start(self):
        event = SimpleNamespace(data={"entity_id": "sensor.operation",
            "new_state": SimpleNamespace(state=namespace["RUNNING_OPERATION"], last_changed=Clock.current),
            "old_state": SimpleNamespace(state="BSH.Common.EnumType.OperationState.Ready")})
        self.put("sensor.load_optimizer_1_cycle_state", "running")
        self.scheduler._async_state_changed(event)
        await asyncio.gather(*self.tasks)
        self.assertFalse(self.scheduler.state["door_opened_since_last_cycle"])
        self.assertEqual(self.scheduler.state["confirmed_cycle_started_at"], Clock.current.isoformat())

    async def test_real_operation_can_start_before_the_next_power_scan(self):
        self.put("sensor.operation", namespace["RUNNING_OPERATION"])
        self.put("sensor.load_optimizer_1_cycle_state", "running")
        event = SimpleNamespace(data={"entity_id": "sensor.load_optimizer_1_cycle_state",
            "new_state": SimpleNamespace(state="running"), "old_state": SimpleNamespace(state="idle")})
        self.scheduler._async_state_changed(event)
        await asyncio.gather(*self.tasks)
        self.put("sensor.operation", "BSH.Common.EnumType.OperationState.Ready")
        await self.scheduler._async_record_cycle_end(Clock.current)
        self.assertEqual(self.scheduler.state["last_result"], "completed")
        self.assertNotIn("capture_had_reported_run", self.scheduler.state)

    async def test_real_completion_does_not_confirm_the_next_firmware_capture(self):
        self.scheduler.state["capture_had_reported_run"] = True
        await self.scheduler._async_record_cycle_end(Clock.current - timedelta(hours=1))
        await self.scheduler._async_record_cycle_end(Clock.current)
        self.assertEqual(self.scheduler.state["schedule_events"][0]["event"], "capture_ignored")

    async def test_window_reservation_is_explained_instead_of_reporting_green(self):
        self.scheduler.state["last_auto_normal_request"] = "2026-10-08T15:00:33+00:00"
        self.assertEqual(self.scheduler._automatic_decision(Clock.current)["reason"], "automatic_window_already_used")
        status = self.scheduler.automation_explanation
        self.assertEqual(status["state"], "attention_required")
        self.assertIn("No wash is queued", status["summary"])
        self.assertEqual(status["automatic_eligible_after"], "2026-10-09T15:00:00+00:00")
        readiness = self.scheduler.readiness("overnight")
        self.assertEqual(readiness["state"], "amber")
        self.assertIn("automatic_window_already_used", readiness["warnings"])

    async def test_next_eligibility_uses_home_time_after_the_autumn_clock_change(self):
        Clock.current = datetime(2026, 10, 25, 8, tzinfo=timezone.utc)
        self.scheduler.state["last_auto_normal_request"] = "2026-10-24T15:00:33+00:00"
        self.assertEqual(self.scheduler.automation_explanation["automatic_eligible_after"],
                         "2026-10-25T16:00:00+00:00")

    async def test_queue_and_last_attempt_are_not_confused_with_recommendation(self):
        await self.scheduler.async_evaluate()
        status = self.scheduler.automation_explanation
        self.assertEqual(status["state"], "scheduled")
        self.assertEqual(status["queued_start"], "2026-10-08T22:00:00+00:00")
        self.assertIsNone(status["last_start_attempt"])
        self.assertEqual(self.scheduler.state["schedule_events"][0]["event"], "queued")

    async def test_wait_reason_changes_are_persisted_but_not_logged_each_minute(self):
        self.scheduler.state["auto_mode_enabled"] = False
        await self.scheduler.async_evaluate()
        await self.scheduler.async_evaluate()
        self.assertEqual(len(self.scheduler.state["schedule_events"]), 1)
        self.assertEqual(self.scheduler.state["schedule_events"][0]["reason"], "automatic_overnight_mode_off")

    async def test_event_history_is_bounded_and_survives_reload(self):
        for i in range(30):
            self.scheduler._record_schedule_event("decision", str(i))
        await self.scheduler._async_save()
        stored = self.scheduler.store.async_save.call_args.args[0]
        self.assertEqual(len(stored["state"]["schedule_events"]), 20)
        restored = NativeOrchestrator(self.hass, SimpleNamespace(entry_id="test", data={}, options={}), None)
        restored.store = SimpleNamespace(async_load=AsyncMock(return_value=stored))
        await restored.async_load()
        self.assertEqual(restored.state["schedule_events"], self.scheduler.state["schedule_events"])

    async def test_cooldown_confidence_relaxation_is_preserved(self):
        self.put("sensor.load_optimizer_1_overnight_recommendation", "MixedLoad", status="ready",
                 confidence=25, decision_policy={"selection_factors": ["cooldown_rotation_active"]})
        self.assertEqual(self.scheduler._automatic_decision(Clock.current)["action"], "queue")
        self.assertIn("confidence_relaxed_for_cooldown_rotation", self.scheduler.readiness("overnight")["warnings"])

    async def test_negative_price_request_keeps_priority(self):
        self.scheduler.state["auto_negative_price_enabled"] = True
        self.put("sensor.load_optimizer_1_negative_price_recommendation", "Super60", status="ready",
                 ready_to_start=True, confidence=85)
        decision = self.scheduler._automatic_decision(Clock.current)
        self.assertEqual(decision["request_mode"], "negative_price")
        self.assertEqual(decision["program"], "Super60")
