"""Real minimum-HA safety acceptance with synthetic data and no device I/O."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from ha_onboarding_smoke import Clock, CONTROL, ROOT, configure, identities
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import HomeAssistant, SupportsResponse
from custom_components.load_optimizer.legacy import app_runtime

DOMAIN = "load_optimizer"
EXAMPLE = '''- id: "1"
  name: Synthetic dishwasher
  power_sensor: sensor.synthetic_power
  energy_sensor: sensor.synthetic_energy
  program_sensor: sensor.synthetic_program
  state_sensor: sensor.synthetic_operation
  active_power_threshold: 10
  finish_delay: 2
  program_policies:
    - program: MixedLoad
      enabled: true
      allow_normal_recommendation: true
      allow_negative_price_run: false
'''


async def main():
    with tempfile.TemporaryDirectory(prefix="load-optimizer-safety-") as directory:
        (Path(directory) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        physical_commands = []
        calendar_response = {"calendar.synthetic_no_run": {"events": []}}
        calendar_queries = []
        original_call = type(hass.services).async_call

        async def guarded_call(registry, domain, service, service_data=None, *args, **kwargs):
            if domain in {"switch", "select", "button", "home_connect", "home_connect_alt"}:
                physical_commands.append((domain, service))
                raise AssertionError("Physical command attempted in safety acceptance")
            return await original_call(registry, domain, service, service_data, *args, **kwargs)

        async def calendar_events(_call):
            calendar_queries.append(dict(_call.data))
            start_at = datetime.fromisoformat(_call.data["start_date_time"])
            end_at = datetime.fromisoformat(_call.data["end_date_time"])
            entity_ids = _call.data["entity_id"]
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            return {entity: {"events": [deepcopy(event) for event in calendar_response[entity]["events"]
                                        if datetime.fromisoformat(event["end"]) > start_at
                                        and datetime.fromisoformat(event["start"]) < end_at]}
                    for entity in entity_ids}

        Clock.current = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        start = Clock.current
        with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status",
                   new=AsyncMock(return_value={"status": "not_configured"})), \
             patch("custom_components.load_optimizer.legacy_runtime.datetime", Clock), \
             patch("custom_components.load_optimizer.orchestration.datetime", Clock), \
             patch.object(app_runtime, "datetime", Clock), \
             patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
             patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()), \
             patch.object(type(hass.services), "async_call", new=guarded_call):
            try:
                assert await async_from_config_dict({"homeassistant": {"time_zone": "Europe/London"}}, hass) is hass
                await hass.async_start()
                hass.services.async_register("calendar", "get_events", calendar_events,
                                             supports_response=SupportsResponse.ONLY)
                hass.states.async_set("sensor.synthetic_power", 0)
                hass.states.async_set("sensor.synthetic_energy", 100)
                hass.states.async_set("sensor.synthetic_program", "MixedLoad")
                hass.states.async_set("sensor.synthetic_operation", "Run")
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": [{
                    "start": start.isoformat(), "end": (start + timedelta(hours=48)).isoformat(),
                    "value_inc_vat": 0.2,
                }]})
                entry = await configure(hass, "learned_appliance", "Synthetic safety hub", {
                    "instances_yaml": EXAMPLE, "tariff_entity": "sensor.synthetic_rates",
                    "tariff_price_unit": "gbp_per_kwh", "tariff_timezone": "Europe/London",
                    "blocked_window_entity": "calendar.synthetic_no_run",
                })
                coordinator = hass.data[DOMAIN][entry.entry_id]
                before = identities(hass, entry.entry_id)
                for minute in range(7):
                    Clock.current = start + timedelta(minutes=minute)
                    hass.states.async_set("sensor.synthetic_power", 1000)
                    await coordinator.async_refresh()
                hass.states.async_set("sensor.synthetic_power", "unavailable")
                for minute in (7, 8, 40):
                    Clock.current = start + timedelta(minutes=minute)
                    await coordinator.async_refresh()
                instance = coordinator.legacy_runtime.state["instances"]["1"]
                assert instance["samples"] == 7 and instance.get("runs", 0) == 0
                assert hass.states.get("sensor.load_optimizer_1_status").state == "source_unavailable"
                assert hass.states.get("sensor.load_optimizer_1_status").attributes["attention_required"] is True
                assert hass.states.get("sensor.load_optimizer_1_cycle_state").state == "running"
                await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = hass.data[DOMAIN][entry.entry_id]
                instance = coordinator.legacy_runtime.state["instances"]["1"]
                assert instance["capture_power_gap"] is True and instance["samples"] == 7
                hass.states.async_set("sensor.synthetic_operation", "BSH.Common.EnumType.OperationState.Ready")
                await coordinator.async_refresh()
                assert instance.get("runs", 0) == 0 and "cycle_start" not in instance
                assert instance["last_discarded_cycle"]["learning_excluded"] is True
                assert identities(hass, entry.entry_id) == before
                print("Real HA: missing power retains capture without sample growth; reload preserves gap; terminal state excludes learning")

                hass.states.async_set("sensor.synthetic_power", 0)
                await coordinator.async_refresh()
                cost = hass.states.get("sensor.load_optimizer_1_cost_status")
                assert cost.attributes["blocked_window_source_ready"] is False
                assert "blocked_window_diagnostic" not in cost.attributes
                assert hass.states.get("sensor.load_optimizer_1_now_recommendation").state == "blocked_window_unavailable"
                controller = coordinator.orchestrator
                controller.config = dict(CONTROL)
                controller.state["door_opened_since_last_cycle"] = True
                for key in ("bosch_connected_sensor", "bosch_remote_control_sensor", "bosch_remote_start_sensor"):
                    hass.states.async_set(CONTROL[key], "on")
                hass.states.async_set(CONTROL["bosch_door_sensor"], "off")
                request = {"mode": "automatic", "program": "MixedLoad", "automatic": True,
                           "start": Clock.current.isoformat(),
                           "finish": (Clock.current + timedelta(hours=2)).isoformat()}
                assert not await controller._async_start_allowed(request)
                assert controller.state["last_reason"] == "blocked_window_source_unavailable"
                hass.states.async_set("calendar.synthetic_no_run", "off")
                await coordinator.async_refresh()
                assert await controller._async_start_allowed(request)
                calendar_response["calendar.synthetic_no_run"]["events"] = [{
                    "start": (Clock.current + timedelta(minutes=90)).isoformat(),
                    "end": (Clock.current + timedelta(hours=3)).isoformat(),
                }]
                # No scan: the real coordinator callback must fetch changed events itself.
                assert not await controller._async_start_allowed(request)
                assert controller.state["last_reason"] == "blocked_window_overlap"
                assert coordinator.legacy_runtime.state["instances"]["1"].get("runs", 0) == 0
                assert identities(hass, entry.entry_id) == before
                assert not physical_commands
                print("Real HA: missing no-run source blocks, valid empty feed recovers, fresh overlapping event blocks saved plan; no device commands")

                Clock.current = (Clock.current + timedelta(hours=1)).replace(minute=0)
                reference = Clock.current
                cycle = {"program": "MixedLoad", "runtime_minutes": 120, "energy_kwh": 2,
                         "peak_power": 1000, "sample_count": 121, "finish": reference.isoformat(),
                         "power_profile": [{"offset_seconds": 0, "power_w": 1000},
                                           {"offset_seconds": 7200, "power_w": 1000}]}
                for _ in range(5):
                    app_runtime.update_program_model(instance, cycle)
                instance["runs"] = 5
                instance["last_cycle"] = cycle
                memory_before = deepcopy(coordinator.legacy_runtime.state)
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": [
                    {"start": reference.isoformat(), "end": (reference + timedelta(hours=24)).isoformat(),
                     "value_inc_vat": 0.3},
                    {"start": (reference + timedelta(hours=24)).isoformat(),
                     "end": (reference + timedelta(hours=72)).isoformat(), "value_inc_vat": 0.01},
                ]})
                calendar_response["calendar.synthetic_no_run"]["events"] = [{
                    "start": (reference + timedelta(hours=25)).isoformat(),
                    "end": (reference + timedelta(hours=27)).isoformat(),
                }]
                await coordinator.async_refresh()
                assert datetime.fromisoformat(calendar_queries[-1]["end_date_time"]) >= reference + timedelta(hours=26)
                assert hass.states.get("sensor.load_optimizer_1_cheapest_start").state == (reference + timedelta(hours=23)).isoformat()
                assert coordinator.legacy_runtime.state == memory_before
                calendar_response["calendar.synthetic_no_run"]["events"][0]["start"] = (reference + timedelta(hours=26)).isoformat()
                await coordinator.async_refresh()
                assert hass.states.get("sensor.load_optimizer_1_cheapest_start").state == (reference + timedelta(hours=24)).isoformat()
                assert coordinator.legacy_runtime.state == memory_before
                assert identities(hass, entry.entry_id) == before and not physical_commands
                print("Real HA: calendar fetch and recommendation cover the cycle tail; exact-finish boundary, learning and identities preserved")

                # A legacy record can bootstrap its first model during startup.
                await coordinator.legacy_runtime.async_import_state({
                    "schema_version": 1, "instances": {"1": {"runs": 1, "last_cycle": cycle}},
                })
                calendar_response["calendar.synthetic_no_run"]["events"][0]["start"] = (reference + timedelta(hours=25)).isoformat()
                calendar_queries.clear()
                await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = hass.data[DOMAIN][entry.entry_id]
                assert datetime.fromisoformat(calendar_queries[0]["end_date_time"]) >= reference + timedelta(hours=26)
                assert hass.states.get("sensor.load_optimizer_1_cheapest_start").state == (reference + timedelta(hours=23)).isoformat()
                assert coordinator.legacy_runtime.state["instances"]["1"]["runs"] == 1
                assert identities(hass, entry.entry_id) == before and not physical_commands
                print("Real HA: startup model bootstrap precedes calendar coverage, without a false learning increment")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
