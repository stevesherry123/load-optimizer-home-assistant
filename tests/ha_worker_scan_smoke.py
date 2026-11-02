"""Exercise the experimental adapter's worker port without physical controls."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.legacy import app_runtime
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        try:
            loop_thread = get_ident()
            notifications = []
            hass.services.async_register("persistent_notification", "create",
                lambda call: notifications.append(call.data))
            hass.states.async_set("sensor.test_power", "0", {"unit_of_measurement": "W"})
            runtime = LegacyRuntime(hass)
            runtime.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
            options = {"instances": [{"id": "1", "power_sensor": "sensor.test_power"}]}
            original = app_runtime.update_instance
            seen = []

            def provider(entity_id):
                assert get_ident() == loop_thread, "Provider was called from a worker"
                return None

            runtime.external_state_provider = provider

            def guarded(*args, **kwargs):
                assert get_ident() != loop_thread, "CPU calculation ran on the HA loop"
                seen.append(get_ident())
                runtime._api_request("", "/services/persistent_notification/create", {"message": "Worker test"})
                return original(*args, **kwargs)

            with patch.object(app_runtime, "update_instance", side_effect=guarded):
                result = await asyncio.wait_for(runtime.async_scan(options), 20)
            await hass.async_block_till_done()
            assert seen and result.entities["sensor.load_optimizer_1_status"]["state"] != "error"
            assert any(item["message"] == "Worker test" for item in notifications)
            assert hass.states.get("sensor.load_optimizer_1_status") is None

            entered, release = Event(), Event()

            def slow(*args, **kwargs):
                entered.set()
                assert release.wait(5), "Test worker was not released"
                return original(*args, **kwargs)

            with patch.object(app_runtime, "update_instance", side_effect=slow):
                scan = asyncio.create_task(runtime.async_scan(options))
                for _ in range(500):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.01)
                assert entered.is_set()
                scan.cancel()
                imported = asyncio.create_task(runtime.async_import_state({"instances": {"1": {"runs": 777}}}))
                await asyncio.sleep(.05)
                assert not imported.done() and runtime._state_lock.locked()
                release.set()
                try:
                    await scan
                except asyncio.CancelledError:
                    pass
                await imported
            assert runtime.state["instances"]["1"]["runs"] == 777
            assert not runtime._state_lock.locked()

            other = LegacyRuntime(hass)
            other.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
            other_options = {"instances": [{"id": "2", "power_sensor": "sensor.test_power"}]}
            results = await asyncio.wait_for(asyncio.gather(
                runtime.async_scan(options), other.async_scan(other_options)), 20)
            assert "sensor.load_optimizer_1_status" in results[0].entities
            assert "sensor.load_optimizer_2_status" not in results[0].entities
            assert "sensor.load_optimizer_2_status" in results[1].entities
            assert "sensor.load_optimizer_1_status" not in results[1].entities
            print("Worker scans, loop-only source reads, notifications, cancellation/import and adapter isolation passed")
        finally:
            await hass.async_stop()


asyncio.run(main())
