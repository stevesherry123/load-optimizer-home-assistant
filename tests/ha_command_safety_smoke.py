"""Exercise command cancellation and safety on real HA, with synthetic devices."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.core import HomeAssistant

from custom_components.load_optimizer.orchestration import NativeOrchestrator


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        try:
            for action in ("async_cancel", "async_stop"):
                for pause in range(5):
                    scheduler = NativeOrchestrator(hass, SimpleNamespace(entry_id="synthetic"), None)
                    scheduler.store = SimpleNamespace(async_save=AsyncMock())
                    scheduler.state.update(active=True, auto_mode_enabled=False,
                                           auto_negative_price_enabled=False)
                    scheduler.config = {
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
                    hass.states.async_set("sensor.synthetic_operation", "BSH.Common.EnumType.OperationState.Ready")
                    hass.states.async_set("sensor.load_optimizer_1_cycle_state", "idle")
                    hass.states.async_set("binary_sensor.synthetic_door", "off")
                    for name in ("connected", "remote_control", "remote_start"):
                        hass.states.async_set("binary_sensor.synthetic_" + name, "on")
                    hass.states.async_set("select.synthetic_programme", "ready",
                                          {"options": ["Dishcare.Dishwasher.Program.MixedLoad"]})
                    request = {"mode": "now", "program": "MixedLoad", "automatic": False,
                               "explicit_program_override": True}
                    scheduler.state["request"] = request
                    waiting = asyncio.Event()
                    calls = AsyncMock()
                    count = 0

                    async def delay(_seconds):
                        nonlocal count
                        current = count
                        count += 1
                        if current == pause:
                            waiting.set()
                            await asyncio.Event().wait()

                    with patch.object(hass.services, "async_call", calls), patch.object(
                        asyncio, "sleep", side_effect=delay
                    ):
                        task = asyncio.create_task(scheduler._async_execute(dict(request)))
                        scheduler._execution_task = task
                        await asyncio.wait_for(waiting.wait(), 5)
                        before = list(calls.await_args_list)
                        await getattr(scheduler, action)()
                        assert task.cancelled(), (action, pause)
                        assert calls.await_args_list == before, (action, pause)
                    assert scheduler.state["request"] == (request if action == "async_stop" else None)
                    await scheduler.async_stop()

            # A manual convenience override never exempts physical interlocks.
            scheduler._stopping = False
            for name, value in (("door", "on"), ("door", "unavailable"), ("connected", "off")):
                hass.states.async_set("binary_sensor.synthetic_door", "off")
                hass.states.async_set("binary_sensor.synthetic_connected", "on")
                hass.states.async_set("binary_sensor.synthetic_" + name, value)
                assert not await scheduler._async_start_allowed(request, recheck=True), name
            await scheduler.async_stop()
            print("Real-HA cancellation/unload at all five delays and manual physical interlocks passed")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
