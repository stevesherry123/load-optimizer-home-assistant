"""Confirm one bounded normal wash and stop a delayed sequence at window end."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.orchestration import NativeOrchestrator


class Clock(datetime):
    current = datetime(2026, 11, 3, 22, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        hass.config.time_zone = "Europe/London"
        controller = NativeOrchestrator(hass, SimpleNamespace(entry_id="synthetic"), None)
        controller.state.update(active=True, auto_mode_enabled=False, door_opened_since_last_cycle=False)
        controller.config = {
            "bosch_program_select": "select.synthetic_programme",
            "bosch_operation_state_sensor": "sensor.synthetic_operation",
            "bosch_door_sensor": "binary_sensor.synthetic_door",
            "bosch_connected_sensor": "binary_sensor.synthetic_connected",
            "bosch_remote_control_sensor": "binary_sensor.synthetic_remote_control",
            "bosch_remote_start_sensor": "binary_sensor.synthetic_remote_start",
            "bosch_power_switch": "switch.synthetic_power",
            "bosch_start_button": "button.synthetic_start",
            "bosch_device_id": "synthetic-device",
        }
        calls = []

        async def command(registry, domain, service, data, **kwargs):
            calls.append((domain, service))
            if (domain, service) == ("button", "press"):
                hass.states.async_set("sensor.synthetic_operation", "BSH.Common.EnumType.OperationState.Run")

        async def delay(seconds):
            Clock.current += timedelta(seconds=seconds)

        def ready():
            hass.states.async_set("sensor.synthetic_operation", "BSH.Common.EnumType.OperationState.Ready")
            hass.states.async_set("sensor.load_optimizer_1_cycle_state", "idle")
            hass.states.async_set("binary_sensor.synthetic_door", "off")
            for name in ("connected", "remote_control", "remote_start"):
                hass.states.async_set("binary_sensor.synthetic_" + name, "on")
            hass.states.async_set("select.synthetic_programme", "ready", {"options": ["Dishcare.Dishwasher.Program.Eco50"]})
            hass.states.async_set("sensor.load_optimizer_1_overnight_recommendation", "Eco50", {
                "program": "Eco50", "status": "ready", "confidence": 88,
                "start": Clock.current.isoformat(), "finish": (Clock.current + timedelta(hours=2)).isoformat(),
                "overnight_planning_coverage": {"complete": True, "search_complete": True,
                    "window_start": "2026-11-03T21:00:00+00:00", "window_end": "2026-11-04T07:00:00+00:00"},
            })

        with patch("custom_components.load_optimizer.orchestration.datetime", Clock), \
             patch.object(type(hass.services), "async_call", new=command), \
             patch.object(asyncio, "sleep", side_effect=delay):
            try:
                ready()
                controller.set_automatic_preflight(AsyncMock(return_value=None))
                await controller.async_request("overnight")
                task = controller._execution_task
                assert task is not None
                await task
                assert controller.state["request"] is None
                assert controller.state["last_result"] == "confirmed"
                assert calls.count(("button", "press")) == 1
                await controller.async_evaluate()
                assert calls.count(("button", "press")) == 1

                calls.clear()
                Clock.current = datetime(2026, 11, 4, 6, 59, 50, tzinfo=timezone.utc)
                ready()
                await controller.async_request("overnight")
                await controller._execution_task
                assert controller.state["last_reason"] == "outside_authorised_start_window"
                assert ("switch", "turn_on") in calls
                assert ("select", "select_option") not in calls
                assert ("button", "press") not in calls
                assert not any(domain.startswith("home_connect") for domain, service in calls)
                print("Real HA: explicit permission starts exactly once; delayed sequence cannot start after 07:00")
            finally:
                await controller.async_stop()
        await hass.async_stop(force=True)


asyncio.run(main())
