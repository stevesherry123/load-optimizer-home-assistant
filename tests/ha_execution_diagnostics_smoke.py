"""Verify native execution diagnostics without production helpers or devices."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.legacy import app_runtime
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime
from custom_components.load_optimizer.orchestration import NativeOrchestrator


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        try:
            runtime = LegacyRuntime(hass)
            scheduler = NativeOrchestrator(hass, SimpleNamespace(entry_id="test"), None)
            scheduler.state.update(active=True, execution_status="idle", last_result="completed",
                last_program="Quick45", last_attempt="2026-10-27T04:00:00+00:00")
            runtime.external_state_provider = scheduler.legacy_state
            runtime._patch_legacy_runtime()
            app_runtime.PUBLISHED_ENTITY_CACHE.clear()
            app_runtime.publish_execution_entities("", "sensor.load_optimizer_1", "Test", "1")
            entities = runtime.published_entities
            assert entities["sensor.load_optimizer_1_execution_status"]["state"] == "idle"
            assert entities["sensor.load_optimizer_1_last_start_result"]["state"] == "completed"
            assert entities["sensor.load_optimizer_1_last_start_program"]["state"] == "Quick45"
            assert entities["sensor.load_optimizer_1_last_start_attempt"]["state"] == "2026-10-27T04:00:00+00:00"
            assert hass.states.get("input_text.load_optimizer_1_last_start_result") is None
            print("Execution diagnostics use native scheduler records without retired helpers")
        finally:
            await hass.async_stop()


asyncio.run(main())
