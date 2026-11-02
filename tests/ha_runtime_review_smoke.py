"""Exercise HACS runtime/ownership fixes with real HA, without live devices."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from custom_components.load_optimizer import (
    _async_claim_native_status_entity_ids, _async_migrate_native_status_entities,
)
from custom_components.load_optimizer.const import DOMAIN
from custom_components.load_optimizer.legacy import app_runtime
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime
from custom_components.load_optimizer.orchestration import NativeOrchestrator


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        try:
            await er.async_get(hass).async_load()
            await ir.async_get(hass).async_load()
            notifications = []
            hass.services.async_register("persistent_notification", "create",
                lambda call: notifications.append(call.data))
            loop_thread = get_ident()
            runtime = LegacyRuntime(hass)
            runtime.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
            hass.states.async_set("sensor.test_power", "0", {"unit_of_measurement": "W"})
            options = {"instances": [{"id": "1", "power_sensor": "sensor.test_power"}]}
            seen = []
            original = app_runtime.update_instance
            def guarded(*args, **kwargs):
                assert get_ident() != loop_thread, "Calculation ran on HA's event loop"
                seen.append(get_ident())
                runtime._api_request("", "/services/persistent_notification/create", {"message": "Worker notification"})
                return original(*args, **kwargs)
            runtime.external_state_provider = lambda entity_id: (
                (_ for _ in ()).throw(AssertionError("Provider called off loop"))
                if get_ident() != loop_thread else None
            )
            with patch.object(app_runtime, "update_instance", side_effect=guarded):
                result = await runtime.async_scan(options)
            await hass.async_block_till_done()
            assert seen and result.entities["sensor.load_optimizer_1_status"]["state"] != "error"
            assert any(item["message"] == "Worker notification" for item in notifications)
            assert hass.states.get("sensor.load_optimizer_1_status") is None, "Worker wrote a raw HA state"

            # Retired helpers must not hide the native scheduler's execution record.
            scheduler = NativeOrchestrator(hass, SimpleNamespace(entry_id="diagnostics"), None)
            scheduler.state.update(active=True, last_program="Quick45",
                last_attempt="2026-10-27T04:00:00+00:00", last_message="Test record")
            hass.states.async_set("input_text.load_optimizer_1_last_start_result", "obsolete")
            def native_provider(entity_id):
                assert get_ident() == loop_thread, "Native scheduler read off loop"
                return scheduler.legacy_state(entity_id)
            runtime.external_state_provider = native_provider
            def publish_execution():
                runtime._patch_legacy_runtime()
                app_runtime.publish_execution_entities("", "sensor.load_optimizer_1", "Test", "1")
                return runtime.published_entities
            for status, result, cycle, lifecycle in (
                ("queued", None, "idle", "ready"),
                ("commanding", None, "idle", "starting"),
                ("idle", "confirmed", "running", "running"),
                ("idle", "completed", "idle", "completed"),
                ("failed", "failed", "idle", "failed"),
            ):
                scheduler.state.update(execution_status=status, last_result=result)
                hass.states.async_set("sensor.load_optimizer_1_cycle_state", cycle)
                runtime._publish_entity("", "sensor.load_optimizer_1_cycle_state", cycle, {})
                entities = await hass.async_add_executor_job(publish_execution)
                prefix = "sensor.load_optimizer_1_"
                assert entities[prefix + "execution_status"]["state"] == status
                assert entities[prefix + "execution_lifecycle"]["state"] == lifecycle, (status, result, cycle, entities[prefix + "execution_lifecycle"])
                assert entities[prefix + "last_start_program"]["state"] == "Quick45"
                assert entities[prefix + "last_start_result"]["state"] == (result or "unknown")
                assert entities[prefix + "last_start_attempt"]["state"] == "2026-10-27T04:00:00+00:00"
            # Other appliances must not inherit the dishwasher's execution record.
            snapshot = await hass.async_add_executor_job(runtime._execution_snapshot, "load_optimizer_2")
            assert snapshot["program"] == "unknown" and snapshot["attempt"] == "unknown"
            hass.states.async_set("sensor.load_optimizer_1_cycle_state", "idle")
            runtime._publish_entity("", "sensor.load_optimizer_1_cycle_state", "idle", {})
            runtime.external_state_provider = None
            print("Native execution diagnostics passed five lifecycle states without legacy helpers")

            # Cancellation must not release the import lock while the worker writes memory.
            entered, release = Event(), Event()
            def slow(*args, **kwargs):
                entered.set()
                assert release.wait(5), "Test did not release worker"
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
            print("Worker calculations, loop-only reads, thread-safe notifications and cancelled-scan/import serialization passed")

            registry = er.async_get(hass)
            target = "sensor.load_optimizer_1_overnight_readiness"
            foreign = registry.async_get_or_create("sensor", "template", "foreign-template",
                suggested_object_id=target.split(".")[1])
            hass.states.async_set(target, "unavailable")
            entry = SimpleNamespace(entry_id="ownership-test", data={"load_type": "learned_appliance"})
            ev = SimpleNamespace(entry_id="advisory-ev", data={"load_type": "ev_charging"})
            _async_migrate_native_status_entities(hass, ev)
            assert not ir.async_get(hass).async_get_issue(DOMAIN, "legacy_status_conflict_advisory-ev")
            _async_migrate_native_status_entities(hass, entry)
            assert registry.async_get(target) == foreign and hass.states.get(target).state == "unavailable"
            issue_id = f"legacy_status_conflict_{entry.entry_id}"
            assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
            native = registry.async_get_or_create("sensor", DOMAIN,
                f"{entry.entry_id}_orchestration_overnight_readiness", suggested_object_id="native_readiness")
            registry.async_update_entity(native.entity_id, config_entry_id=entry.entry_id)
            _async_claim_native_status_entity_ids(hass, entry)
            assert registry.async_get(target) == foreign
            assert registry.async_get(native.entity_id), "Native alternative ID was removed"
            _async_migrate_native_status_entities(hass, entry)
            assert registry.async_get(native.entity_id), "Reload removed the registered native sensor"
            # Only the user removes the old template. Reload can then claim the free ID.
            registry.async_remove(target)
            hass.states.async_remove(target)
            _async_migrate_native_status_entities(hass, entry)
            _async_claim_native_status_entity_ids(hass, entry)
            assert registry.async_get(target).unique_id == native.unique_id
            assert not ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
            assert runtime.state["instances"]["1"]["runs"] == 777
            print("Foreign template preserved, repair reported, native ID claimed only after user cleanup; learning unchanged")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
