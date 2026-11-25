"""Real HA late-publication/revision and request preservation acceptance."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from ha_onboarding_smoke import Clock, ROOT, configure, identities
from ha_negative_price_smoke import cycle
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.legacy import app_runtime

EXAMPLE = '''- id: "1"
  name: Synthetic overnight dishwasher
  power_sensor: sensor.synthetic_power
  program_sensor: sensor.synthetic_program
  schedule_latest_finish_entity: input_datetime.synthetic_deadline
  schedule_overnight_start: "20:00"
  schedule_overnight_end: "07:00"
  program_policies:
    - program: Quick65
      enabled: true
      allow_normal_recommendation: true
    - program: Eco50
      enabled: true
      allow_normal_recommendation: true
'''


async def main():
    with tempfile.TemporaryDirectory(prefix="load-optimizer-overnight-") as directory:
        (Path(directory) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        commands = []
        original_call = type(hass.services).async_call

        async def guarded_call(registry, domain, service, *args, **kwargs):
            if domain in {"switch", "select", "button", "home_connect", "home_connect_alt"}:
                commands.append((domain, service))
                raise AssertionError("Physical command attempted in overnight acceptance")
            return await original_call(registry, domain, service, *args, **kwargs)

        start = datetime(2026, 10, 13, 15, 0, 23, tzinfo=timezone.utc)
        Clock.current = start

        def rates(hours, cheap_first=9, cheap_last=14):
            first = start.replace(minute=0, second=0)
            return [{"start": (first + timedelta(minutes=i * 30)).isoformat(),
                     "end": (first + timedelta(minutes=(i + 1) * 30)).isoformat(),
                     "value_inc_vat": 0.01 if cheap_first <= i / 2 < cheap_last else 0.30}
                    for i in range(hours * 2)]

        with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status",
                   new=AsyncMock(return_value={"status": "not_configured"})), \
             patch("custom_components.load_optimizer.orchestration.datetime", Clock), \
             patch("custom_components.load_optimizer.legacy_runtime.datetime", Clock), \
             patch.object(app_runtime, "datetime", Clock), \
             patch.object(HomeAssistantHTTP, "async_bind", new=AsyncMock(), create=True), \
             patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
             patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()), \
             patch.object(type(hass.services), "async_call", new=guarded_call):
            try:
                assert await async_from_config_dict({"homeassistant": {"time_zone": "Europe/London"}}, hass) is hass
                await hass.async_start()
                hass.states.async_set("input_datetime.synthetic_deadline", "2026-10-13 04:29:00")
                hass.states.async_set("sensor.synthetic_power", 0)
                hass.states.async_set("sensor.synthetic_program", "Quick65")
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates(7)})
                entry = await configure(hass, "learned_appliance", "Synthetic overnight hub", {
                    "instances_yaml": EXAMPLE, "tariff_entity": "sensor.synthetic_rates",
                    "tariff_price_unit": "gbp_per_kwh", "tariff_timezone": "Europe/London",
                    "cost_search_hours": 18, "cost_forecast_hours": 1,
                })
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                controller = coordinator.orchestrator
                for remove in controller._remove_listeners:
                    remove()
                controller._remove_listeners.clear()
                assert hass.states.get("time.load_optimizer_1_overnight_start").state == "20:00:00"
                assert hass.states.get("time.load_optimizer_1_overnight_end").state == "07:00:00"
                await hass.services.async_call("time", "set_value", {
                    "entity_id": "time.load_optimizer_1_overnight_start", "time": "21:00:00",
                }, blocking=True)
                await hass.async_block_till_done()
                assert controller.state["overnight_start"] == "21:00"
                before_ids = identities(hass, entry.entry_id)
                instance = coordinator.legacy_runtime.state["instances"]["1"]
                for programme, duration, energy in (("Quick65", 51, 1), ("Eco50", 244, 0.8)):
                    for _ in range(5):
                        app_runtime.update_program_model(instance, cycle(programme, duration, energy, start - timedelta(days=2)))
                instance["runs"] = 10
                await coordinator.async_refresh()
                controller.state.update(active=True, auto_mode_enabled=True, door_opened_since_last_cycle=True)
                await controller.async_evaluate()
                assert controller.state["request"]["normal_wash"]
                assert controller.state["execution_status"] == "awaiting_plan"
                assert controller.automation_explanation["reason_code"] == "overnight_tariff_coverage_incomplete"
                assert "recommendation_quote" not in controller.state["request"]
                print("Real HA: partial prices retain wash permission, notify, and cannot start a wash")

                Clock.current += timedelta(minutes=2)
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates(32)})
                await coordinator.async_refresh()
                await controller.async_evaluate()
                assert controller.state["request"]["program"] == "Eco50"
                first_quote = deepcopy(controller.state["request"]["recommendation_quote"])
                assert first_quote["overnight_selection_reason"] == "best_overnight"
                assert first_quote["tariff_evidence"]["period_count"] >= 8
                assert first_quote["tariff_evidence"]["periods"][0]["rate_source"] == "contracted"
                original_created = controller.state["request"]["created_at"]
                original_reserved = controller.state["last_auto_normal_request"]
                Clock.current += timedelta(minutes=2)
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates(32, 12, 13)})
                await coordinator.async_refresh()
                await controller.async_evaluate()
                assert controller.state["request"]["program"] == "Quick65"
                assert controller.state["request"]["created_at"] == original_created
                assert controller.state["last_auto_normal_request"] == original_reserved
                assert any(e["event"] == "replanned" for e in controller.state["schedule_events"])
                revised_quote = controller.state["request"]["recommendation_quote"]
                recommendation = hass.states.get("sensor.load_optimizer_1_overnight_recommendation")
                assert revised_quote["program"] == recommendation.state == "Quick65"
                assert revised_quote["estimated_cost_pence"] == recommendation.attributes["cost_pence"]
                assert revised_quote["tariff_evidence"]["energy_cost_pence"] == recommendation.attributes["tariff_evidence"]["energy_cost_pence"]
                assert revised_quote["tariff_evidence"]["periods"][0]["start"] == revised_quote["start"]
                assert first_quote["program"] == "Eco50"
                print("Real HA: late full rates select Eco50; price revision replans without consuming another reservation")

                # The real planner and adapter both ignore a deadline predating
                # this permission. No hardware service is registered or called.
                request = deepcopy(controller.state["request"])
                assert await coordinator._async_automatic_start_block(request) is None
                hass.states.async_set("input_datetime.synthetic_deadline", "unavailable")
                assert await coordinator._async_automatic_start_block(request) == "normal_wash_schedule_constraint_unavailable"
                await coordinator.async_refresh()
                assert hass.states.get("sensor.load_optimizer_1_cost_status").state == "schedule_constraint_unavailable"
                hass.states.async_set("input_datetime.synthetic_deadline", "2026-10-13 04:29:00")
                await coordinator.async_refresh()
                assert not commands
                print("Real HA: stale travel deadline accepted consistently; unreadable constraint pauses planning and execution")

                # A manual programme and time must survive future planner changes and reload.
                manual = {**controller.state["request"], "automatic": False, "mode": "overnight"}
                manual.pop("normal_wash", None)
                controller.state["request"] = manual
                await controller._async_save()
                memory = deepcopy(coordinator.legacy_runtime.state)
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates(32)})
                await coordinator.async_refresh()
                await controller.async_evaluate()
                assert controller.state["request"] == manual
                await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                await coordinator.orchestrator.async_stop()
                assert coordinator.orchestrator.state["request"] == manual
                assert coordinator.legacy_runtime.state == memory
                assert identities(hass, entry.entry_id) == before_ids
                assert not commands
                print("Real HA: manual request, exact learning and registered identities survive revisions and reload; no device commands")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
