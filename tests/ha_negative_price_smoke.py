"""Exercise repeat recommendations, persistence and fresh vetoes in real HA."""

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
PROGRAMMES = [("Quick45", 28.4, 0.7, 1), ("MachineCare", 35.5, 0.6, 2), ("NormalOnly", 10, 5, 1)]
EXAMPLE = '''- id: "1"
  name: Synthetic repeat dishwasher
  power_sensor: sensor.synthetic_power
  program_sensor: sensor.synthetic_program
  active_power_threshold: 10
  finish_delay: 2
  program_policies:
'''
for programme, _, _, maximum in PROGRAMMES:
    EXAMPLE += f'''    - program: {programme}
      enabled: true
      allow_normal_recommendation: true
      allow_negative_price_run: {str(programme != "NormalOnly").lower()}
      minimum_hours_between_runs: 96
      maximum_runs_per_window: {maximum}
'''


def cycle(programme, duration, energy, finish):
    return {"program": programme, "runtime_minutes": duration, "energy_kwh": energy,
            "peak_power": 1000, "sample_count": 121, "finish": finish.isoformat(),
            "power_profile": [{"offset_seconds": 0, "power_w": 1000},
                              {"offset_seconds": duration * 60, "power_w": 1000}]}


async def main():
    with tempfile.TemporaryDirectory(prefix="load-optimizer-negative-") as directory:
        (Path(directory) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        physical_commands = []
        events = []
        original_call = type(hass.services).async_call

        async def guarded_call(registry, domain, service, *args, **kwargs):
            if domain in {"switch", "select", "button", "home_connect", "home_connect_alt"}:
                physical_commands.append((domain, service))
                raise AssertionError("Physical command attempted in isolated repeat acceptance")
            return await original_call(registry, domain, service, *args, **kwargs)

        async def get_events(call):
            first = datetime.fromisoformat(call.data["start_date_time"])
            last = datetime.fromisoformat(call.data["end_date_time"])
            return {"calendar.synthetic_no_run": {"events": [deepcopy(event) for event in events
                    if datetime.fromisoformat(event["end"]) > first and datetime.fromisoformat(event["start"]) < last]}}

        start = datetime.now(timezone.utc).replace(hour=8, minute=30, second=0, microsecond=0)
        Clock.current = start + timedelta(seconds=54, microseconds=183546)
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
                hass.services.async_register("calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY)
                hass.states.async_set("sensor.synthetic_power", 0)
                hass.states.async_set("sensor.synthetic_program", "Quick45")
                hass.states.async_set("calendar.synthetic_no_run", "off")
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": [
                    {"start": (start + timedelta(hours=first)).isoformat(),
                     "end": (start + timedelta(hours=last)).isoformat(), "value_inc_vat": price}
                    for first, last, price in ((0, 1, -0.01), (1, 2, 0), (2, 3, 0.2), (3, 4.5, -0.02), (4.5, 6, 0.2))
                ]})
                entry = await configure(hass, "learned_appliance", "Synthetic repeat hub", {
                    "instances_yaml": EXAMPLE, "tariff_entity": "sensor.synthetic_rates",
                    "tariff_price_unit": "gbp_per_kwh", "tariff_timezone": "Europe/London",
                    "cost_search_hours": 5, "cost_forecast_hours": 5,
                    "blocked_window_entity": "calendar.synthetic_no_run",
                })
                flow = await hass.config_entries.options.async_init(entry.entry_id)
                flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "dishwasher_control"})
                saved = await hass.config_entries.options.async_configure(flow["flow_id"], dict(CONTROL))
                assert saved["type"] == "create_entry"
                await hass.async_block_till_done()
                coordinator = hass.data[DOMAIN][entry.entry_id]
                controller = coordinator.orchestrator
                await controller.async_stop()
                assert controller.state["auto_negative_price_enabled"] is False
                before_ids = identities(hass, entry.entry_id)
                instance = coordinator.legacy_runtime.state["instances"]["1"]
                for programme, duration, energy, _ in PROGRAMMES:
                    for _ in range(5):
                        app_runtime.update_program_model(instance, cycle(programme, duration, energy, start - timedelta(days=1)))
                instance["runs"] = 15
                await coordinator.async_refresh()
                recommendation = hass.states.get("sensor.load_optimizer_1_negative_price_recommendation")
                assert recommendation.attributes["ready_to_start"] is True
                assert recommendation.attributes["start"] == Clock.current.isoformat()
                assert recommendation.state == "Quick45"
                controller.state.update(active=True, auto_negative_price_enabled=True, auto_mode_enabled=False,
                                        door_opened_since_last_cycle=False)
                assert controller._automatic_decision(Clock.current)["program"] == "Quick45"
                first_request = Clock.current
                controller.state["last_auto_negative_price_request"] = first_request.isoformat()
                Clock.current += timedelta(minutes=28.4)
                completed = cycle("Quick45", 28.4, 0.7, Clock.current)
                app_runtime.update_program_model(instance, completed)
                instance.update(runs=16, last_cycle=completed)
                await coordinator.async_refresh()
                assert controller._automatic_decision(Clock.current)["reason"] == "negative_price_retry_cooldown"
                assert controller.automation_explanation["mode"] == "negative_price"
                Clock.current += timedelta(minutes=2)
                await coordinator.async_refresh()
                recommendation = hass.states.get("sensor.load_optimizer_1_negative_price_recommendation")
                assert recommendation.state == "MachineCare" and recommendation.attributes["ready_to_start"] is True
                assert recommendation.attributes["cooldown_bypassed_for_negative_price"] is True
                assert "NormalOnly" not in [item["program"] for item in recommendation.attributes["program_options"]]
                print("Real HA: off-grid opportunity is ready; completed run rotates within limits despite normal cooldown")

                for key in ("bosch_connected_sensor", "bosch_remote_control_sensor", "bosch_remote_start_sensor"):
                    hass.states.async_set(CONTROL[key], "on")
                hass.states.async_set(CONTROL["bosch_door_sensor"], "off")
                hass.states.async_set(CONTROL["bosch_operation_state_sensor"], "BSH.Common.EnumType.OperationState.Ready")
                request = {"mode": "negative_price", "automatic": True, "program": "MachineCare",
                           "start": recommendation.attributes["start"], "finish": recommendation.attributes["finish"]}
                assert await controller._async_start_allowed(request)
                events.append({"start": (Clock.current + timedelta(minutes=20)).isoformat(),
                               "end": (Clock.current + timedelta(hours=1)).isoformat()})
                assert not await controller._async_start_allowed(request)
                assert controller.state["last_reason"] == "blocked_window_overlap"
                events.clear()
                hass.states.async_set("sensor.synthetic_power", "unavailable")
                assert not await controller._async_start_allowed(request)
                assert controller.state["last_reason"] == "power_source_unavailable"
                hass.states.async_set("sensor.synthetic_power", 0)
                print("Real HA: fresh no-run overlap and fresh power outage veto the repeat without another scan")

                rates_before = deepcopy(hass.states.get("sensor.synthetic_rates").attributes["rates"])
                positive_rates = [{**period, "value_inc_vat": 0.25} for period in rates_before]
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": positive_rates})
                assert recommendation.attributes["ready_to_start"] is True
                assert not await controller._async_start_allowed(request)
                assert controller.state["last_reason"] == "power_hungry_window_outside_negative_price"
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates_before})
                assert await controller._async_start_allowed(request)
                # The published MachineCare fit cannot authorize Quick45's exhausted allowance.
                assert not await controller._async_start_allowed({**request, "program": "Quick45"})
                assert controller.state["last_reason"] == "maximum_runs_per_window_reached"
                before_boundary = Clock.current
                Clock.current = start + timedelta(hours=2, minutes=-35.5, seconds=1)
                assert not await controller._async_start_allowed(request, recheck=True)
                assert controller.state["last_reason"] == "power_hungry_window_outside_negative_price"
                Clock.current = before_boundary
                assert await controller._async_start_allowed(request, recheck=True)
                print("Real HA: revised prices, exact-programme cap and delayed boundary rechecks veto stale published fits")

                controller.state["last_auto_negative_price_request"] = Clock.current.isoformat()
                await controller._async_save()
                memory_before = deepcopy(coordinator.legacy_runtime.state)
                await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = hass.data[DOMAIN][entry.entry_id]
                controller = coordinator.orchestrator
                await controller.async_stop()
                assert coordinator.legacy_runtime.state == memory_before
                assert identities(hass, entry.entry_id) == before_ids
                assert controller.state["request"] is None
                assert controller._automatic_decision(Clock.current)["reason"] == "negative_price_retry_cooldown"
                assert controller.automation_explanation["automatic_eligible_after"] == (Clock.current + timedelta(minutes=30)).isoformat()
                assert not physical_commands
                print("Real HA: reload preserves exact learning, identities, enabled state and anti-repeat interval; no device commands")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
