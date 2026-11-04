"""Real HA mode edits, partial plans and lost sources without charger actions."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import logging
import yaml
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from ha_onboarding_smoke import Clock, ROOT, configure, identities
from ha_ev_lifecycle_smoke import edit
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template


async def main():
    with tempfile.TemporaryDirectory(prefix="load-optimizer-ev-modes-") as directory:
        (Path(directory) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        commands = []
        original_call = type(hass.services).async_call

        async def guarded_call(registry, domain, service, *args, **kwargs):
            if domain in {"switch", "button", "select", "home_connect", "home_connect_alt"}:
                commands.append((domain, service))
                raise AssertionError("Advisory EV planning attempted a device command")
            return await original_call(registry, domain, service, *args, **kwargs)

        start = datetime(2026, 11, 3, 22, tzinfo=timezone.utc)
        Clock.current = start + timedelta(minutes=7)
        rates = [{"start": (start + timedelta(minutes=i * 30)).isoformat(),
                  "end": (start + timedelta(minutes=(i + 1) * 30)).isoformat(),
                  "price": 20} for i in range(12)]
        settings = {"tariff_entity": "sensor.synthetic_ev_rates", "tariff_price_unit": "p_per_kwh",
                    "tariff_timezone": "Europe/London", "battery_entity": "sensor.synthetic_battery",
                    "battery_capacity_entity": "sensor.synthetic_capacity", "charge_power_kw": 2,
                    "charger_efficiency": 1, "slot_minutes": 30, "target_percent": 80,
                    "connection_status_entity": "binary_sensor.synthetic_ev_connected", "ready_by": "23:00"}

        with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status",
                   new=AsyncMock(return_value={"status": "not_configured"})), \
             patch("custom_components.load_optimizer.coordinator.datetime", Clock), \
             patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
             patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()), \
             patch.object(type(hass.services), "async_call", new=guarded_call):
            try:
                assert await async_from_config_dict({"homeassistant": {"time_zone": "Europe/London"}}, hass) is hass
                await hass.async_start()
                hass.states.async_set("sensor.synthetic_ev_rates", "ready", {"rates": rates})
                hass.states.async_set("sensor.synthetic_battery", 20)
                hass.states.async_set("sensor.synthetic_capacity", 10)
                hass.states.async_set("binary_sensor.synthetic_ev_connected", "on")
                entry = await configure(hass, "ev_charging", "Synthetic EV modes", settings)
                before = identities(hass, entry.entry_id)
                status_id = before[f"{entry.entry_id}_status"][0]
                card = yaml.safe_load((ROOT / "docs/examples/ev-plan-card.yaml").read_text())
                content = card["content"].replace("sensor.your_ev_status", status_id)
                original_data = deepcopy(dict(entry.data))
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                plan = coordinator.data["plan"]
                assert plan["charging_mode"] == "required"
                assert plan["status"] == "partial" and plan["charge_now"]
                assert plan["shortfall_battery_kwh"] > 4
                assert not plan["target_reachable"]
                await hass.async_block_till_done()
                rendered = Template(content, hass).async_render(parse_result=False)
                assert "Required charging" in rendered and "Target shortfall" in rendered
                assert "Remaining shortfall" in rendered and "does not operate a charger" in rendered
                assert plan["selected_slots"][0]["start"] == Clock.current.isoformat()
                assert not any(key.startswith(("button.", "switch.")) for key, device in before.values())

                await edit(hass, entry.entry_id, "ev", {**settings, "charging_mode": "opportunistic", "maximum_price_p_per_kwh": 0})
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                assert coordinator.data["plan"]["status"] == "waiting"
                assert not coordinator.data["plan"]["ready_to_charge"]
                assert coordinator.data["plan"]["selected_slots"] == []
                await hass.async_block_till_done()
                rendered = Template(content, hass).async_render(parse_result=False)
                assert "Opportunistic charging" in rendered and "No charging slots are selected" in rendered
                assert "Price ceiling" in rendered

                rates[0]["price"] = -5
                hass.states.async_set("sensor.synthetic_ev_rates", "ready", {"rates": rates})
                await coordinator.async_refresh()
                plan = coordinator.data["plan"]
                assert plan["charging_mode"] == "opportunistic"
                assert plan["charge_now"] and not plan["target_reachable"]
                assert all(slot["price_p_per_kwh"] <= 0 for slot in plan["selected_slots"])
                assert plan["estimated_electricity_credit_pence"] > 0

                for state in ("off", "unavailable"):
                    hass.states.async_set("binary_sensor.synthetic_ev_connected", state)
                    await coordinator.async_refresh()
                    assert coordinator.data["plan"]["reason"] == "vehicle_not_connected"
                    assert not coordinator.data["plan"]["charge_now"]
                hass.states.async_remove("binary_sensor.synthetic_ev_connected")
                await coordinator.async_refresh()
                assert coordinator.data["plan"]["reason"] == "vehicle_not_connected"
                hass.states.async_set("binary_sensor.synthetic_ev_connected", "on")

                hass.states.async_set("sensor.synthetic_ev_rates", "unavailable", {"rates": rates})
                await coordinator.async_refresh()
                assert coordinator.data["plan"]["reason"] == "tariff_error"
                assert not coordinator.data["plan"]["ready_to_charge"]
                hass.states.async_set("sensor.synthetic_ev_rates", "ready", {"rates": rates})
                await coordinator.async_refresh()
                assert coordinator.data["plan"]["charge_now"]

                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                assert coordinator.data["plan"]["charging_mode"] == "opportunistic"
                assert coordinator.data["plan"]["maximum_price_p_per_kwh"] == 0
                assert identities(hass, entry.entry_id) == before
                assert dict(entry.data) == original_data

                hass.states.async_set("sensor.synthetic_battery", 80)
                await coordinator.async_refresh()
                assert coordinator.data["plan"]["reason"] == "target_already_met"
                assert not coordinator.data["plan"]["charge_now"]
                assert not commands
                print("Real HA: required partial and opportunistic plans, binary connection loss, stale tariff rejection, recovery and reload retain identities; no device commands")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
