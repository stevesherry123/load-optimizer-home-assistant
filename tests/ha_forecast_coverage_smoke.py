"""Actual minimum-HA coverage, storage, sensor and manual-only narrative checks."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant import loader
from homeassistant.auth.const import GROUP_ID_ADMIN
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import Context, HomeAssistant, SupportsResponse

from custom_components.load_optimizer import async_setup
from custom_components.load_optimizer.const import DOMAIN
from custom_components.load_optimizer.narrative import OptionalNarrative
from custom_components.load_optimizer.optimizer.intelligence import bounds
from custom_components.load_optimizer.sensor import LoadOptimizerIntelligenceSensor
from custom_components.load_optimizer.tariff_intelligence import TariffIntelligence, get_service


async def main():
    with tempfile.TemporaryDirectory(prefix="load-optimizer-coverage-") as directory:
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        with patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
             patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()):
            try:
                assert await async_from_config_dict({"homeassistant": {"time_zone": "America/New_York"}}, hass) is hass
                await hass.async_start()
                assert await async_setup(hass, {})
                now = datetime(2026, 10, 14, 15, tzinfo=timezone.utc)
                start, end = bounds(date(2026, 10, 15), "Europe/London")
                rates = [{"start": (start + timedelta(minutes=30 * i)).isoformat(),
                          "end": (start + timedelta(minutes=30 * (i + 1))).isoformat(),
                          "price_p_per_kwh": 20} for i in range(int((end - start).total_seconds() / 1800))]
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates[:-2]})
                service = get_service(hass, {"tariff_entity": "sensor.synthetic_rates",
                    "tariff_timezone": "Europe/London", "tariff_price_unit": "p_per_kwh"})
                partial = await service.async_status({}, now)
                assert partial["status"] == "ready" and partial["forecast_usable"]
                assert not partial["tomorrow_complete"] and not service.days
                assert partial["forecast_coverage"]["known_minutes"] == 1380
                assert partial["time_band_coverage"]["late"] == "partial"
                fresh = TariffIntelligence(hass, service.source_id, service.entity_ids, "Europe/London", "p_per_kwh")
                await fresh.async_load()
                assert not fresh.days
                print("Real HA: normal published prefix is usable; incomplete history is never persisted; tariff timezone wins")

                calls = []
                gate = None
                started = asyncio.Event()
                async def provider(call):
                    calls.append(dict(call.data))
                    started.set()
                    if gate is not None:
                        await gate.wait()
                    options = call.data["structure"]["highlights"]["selector"]["select"]["options"]
                    return {"data": {"highlights": options[:2]}}
                hass.services.async_register("ai_task", "generate_data", provider, supports_response=SupportsResponse.ONLY)
                narrative = OptionalNarrative(hass)
                entry = SimpleNamespace(entry_id="synthetic-coverage", title="Synthetic coverage hub", data={})
                coordinator = SimpleNamespace(hass=hass, config_entry=entry, tariff_intelligence=service,
                    narrative=narrative, data={"tariff_intelligence": partial},
                    async_update_listeners=Mock(), last_update_success=True)
                hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
                assert narrative.snapshot(partial)["status"] == "disabled" and not calls
                sensor = LoadOptimizerIntelligenceSensor(coordinator, "tomorrow_average", "Tomorrow Average Price", "p/kWh")
                identity = sensor.unique_id
                assert sensor.native_value == 20
                assert sensor.extra_state_attributes["analysis_scope"] == "published_hours"
                assert sensor.extra_state_attributes["forecast_coverage"]["known_minutes"] == 1380
                admin = await hass.auth.async_create_user("Synthetic administrator", group_ids=[GROUP_ID_ADMIN])
                response = await hass.services.async_call(DOMAIN, "generate_tariff_summary",
                    {"entry_id": entry.entry_id, "ai_task_entity": "ai_task.synthetic_coverage"},
                    blocking=True, return_response=True, context=Context(user_id=admin.id))
                assert response["status"] == "ready" and len(calls) == 1
                instructions = calls[0]["instructions"]
                assert "partial_day" in instructions and "Europe/London" in instructions
                assert service.source_id not in instructions and "sensor.synthetic_rates" not in instructions
                print("Real HA: one explicitly requested synthetic provider call; coverage disclosed; no background calls or private source metadata")

                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates})
                complete = await service.async_status({}, now)
                coordinator.data = {"tariff_intelligence": complete}
                assert complete["tomorrow_complete"] and len(service.days) == 1
                assert narrative.snapshot(complete)["status"] == "stale"
                assert narrative.snapshot(complete)["text"] is None and len(calls) == 1
                assert sensor.unique_id == identity
                assert sensor.extra_state_attributes["analysis_scope"] == "full_day"
                restarted = TariffIntelligence(hass, service.source_id, service.entity_ids, "Europe/London", "p_per_kwh")
                await restarted.async_load()
                assert restarted.days == service.days
                print("Real HA: tail arrival completes/persists the day and hides stale prose; sensor identity and restart storage preserved")

                gate = asyncio.Event()
                started.clear()
                pending = asyncio.create_task(hass.services.async_call(DOMAIN, "generate_tariff_summary",
                    {"entry_id": entry.entry_id, "ai_task_entity": "ai_task.synthetic_coverage"},
                    blocking=True, return_response=True, context=Context(user_id=admin.id)))
                await asyncio.wait_for(started.wait(), 5)
                revised = [{**row, "price_p_per_kwh": 21} for row in rates]
                hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": revised})
                coordinator.data = {"tariff_intelligence": await service.async_status({}, now)}
                gate.set()
                response = await pending
                assert response["status"] == "stale" and response["text"] is None
                assert len(calls) == 2
                print("Real HA: source revision during synthetic provider execution returns stale status, never obsolete ready prose")

                for state, rows in (("unavailable", rates), ("ready", rates[:20] + rates[21:])):
                    hass.states.async_set("sensor.synthetic_rates", state, {"rates": rows})
                    limited = await service.async_status({}, now)
                    coordinator.data = {"tariff_intelligence": limited}
                    assert not limited["forecast_usable"]
                    response = await hass.services.async_call(DOMAIN, "generate_tariff_summary",
                        {"entry_id": entry.entry_id, "ai_task_entity": "ai_task.synthetic_coverage"},
                        blocking=True, return_response=True, context=Context(user_id=admin.id))
                    assert response["status"] == "waiting" and len(calls) == 2
                    assert len(service.days) == 1
                assert "storage" not in json.loads(instructions.split("\n", 1)[1])
                print("Real HA: cached unavailable source and internal gaps cannot trigger AI or destroy completed history; no live provider or device commands")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    asyncio.run(main())
