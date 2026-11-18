"""Exercise command cancellation and safety on real HA, with synthetic devices."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.core import CoreState, HomeAssistant

from custom_components.load_optimizer.orchestration import NativeOrchestrator
from custom_components.load_optimizer.legacy.costing import QUOTE_TARIFF_PERIOD_LIMIT


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        async def notification(_call):
            pass

        hass.services.async_register("persistent_notification", "create", notification)
        try:
            for action in ("async_cancel", "async_stop"):
                for pause in range(5):
                    scheduler = NativeOrchestrator(hass, SimpleNamespace(entry_id=f"{action}_{pause}"), None)
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

                    with patch.object(type(hass.services), "async_call", calls), patch.object(
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

            scheduler = NativeOrchestrator(hass, SimpleNamespace(entry_id="committed"), None)
            scheduler.state["execution_status"] = "queued"
            await scheduler._async_save()
            hass.set_state(CoreState.stopping)
            try:
                scheduler.state["execution_status"] = "commanding"
                await scheduler._async_save()
                assert (await scheduler.store.async_load())["state"]["execution_status"] == "commanding"
                assert (await scheduler._async_committed_start_state())["execution_status"] == "queued"
                assert not await scheduler._async_start_allowed(request)
            finally:
                hass.set_state(CoreState.running)
            print("Real-HA deferred shutdown write is not treated as a committed command reservation")

            entry = SimpleNamespace(entry_id="estimate_record", data={}, options={})
            recorder = NativeOrchestrator(hass, entry, None)
            start = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
            finish = start + timedelta(hours=2, minutes=15)
            rates = [{"start": (start + timedelta(minutes=15 * index)).isoformat(),
                      "end": (start + timedelta(minutes=15 * (index + 1))).isoformat(),
                      "price_p_per_kwh": 10, "energy_kwh": 0.1, "energy_cost_pence": 1,
                      "event_title": "Private test fixture"} for index in range(QUOTE_TARIFF_PERIOD_LIMIT)]
            recommendation = {"status": "ready", "intent": "overnight", "reason": "best_overnight",
                              "program": "MixedLoad", "start": start.isoformat(), "finish": finish.isoformat(),
                              "cost_pence": 10, "tariff_evidence": {"period_count": 9, "periods": rates,
                              "energy_cost_pence": 9, "non_energy_cost_pence": 1}}
            record = recorder._recommendation_evidence(recommendation, recommendation)
            recorder.state["last_start_decision_snapshot"] = {"request": record}
            await recorder._async_save()
            rates[0]["price_p_per_kwh"] = 999
            restored = NativeOrchestrator(hass, entry, None)
            await restored.async_load()
            stored = restored.status["last_start_decision_snapshot"]["request"]["recommendation_quote"]
            assert stored == record["recommendation_quote"]
            assert stored["tariff_evidence"]["periods"][0]["price_p_per_kwh"] == 10
            assert "fixture" not in json.dumps(stored).lower()
            assert len(json.dumps(stored)) < 2000
            print("Real-HA store retained a detached, bounded tariff estimate through reload without source labels")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
