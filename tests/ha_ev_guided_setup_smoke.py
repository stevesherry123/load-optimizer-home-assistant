"""Exercise actual HA guided flows and append-only dashboard storage, no hardware."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_validation import custom_serializer
from probatio import to_field_list

from custom_components.load_optimizer.ev_dashboard import async_add_ev_view, dashboard_choices


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        commands = []
        try:
            assert await async_from_config_dict({}, hass) is hass
            await hass.async_start()
            async def command(call):
                commands.append(call)
            hass.services.async_register("switch", "turn_on", command)
            hass.services.async_register("switch", "turn_off", command)
            dashboard = LovelaceStorage(hass, {"id":"guided_test", "url_path":"load-optimizer", "title":"Load Optimizer"})
            original = {"title":"My dashboard", "views":[{"path":"existing", "cards":[{"type":"markdown", "content":"Keep me"}]}]}
            await dashboard.async_save(deepcopy(original))
            hass.data[LOVELACE_DATA] = SimpleNamespace(dashboards={"load-optimizer":dashboard,
                "yaml-only":SimpleNamespace(mode="yaml")})
            assert [choice["value"] for choice in dashboard_choices(hass)] == ["", "load-optimizer"]
            now = datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
            rates = [{"start":(now+timedelta(minutes=30*i)).isoformat(),
                      "end":(now+timedelta(minutes=30*(i+1))).isoformat(), "value_inc_vat":-10+i%3} for i in range(96)]
            hass.states.async_set("sensor.guide_rates","ready",{"rates":rates})
            for entity,state,unit in (("sensor.guide_battery",20,"%"), ("sensor.guide_capacity",6,"kWh"),
                ("sensor.guide_connected","connected",None), ("switch.guide_charger","off",None),
                ("sensor.guide_power",0,"W"), ("sensor.guide_energy",100,"kWh"), ("sensor.guide_status","idle",None)):
                hass.states.async_set(entity,state,{"unit_of_measurement":unit})
            sources = {"tariff_entity":"sensor.guide_rates", "battery_entity":"sensor.guide_battery",
                       "battery_capacity_entity":"sensor.guide_capacity", "connection_status_entity":"sensor.guide_connected"}
            preferences = {"charge_power_kw":1,"charger_efficiency":1,"target_percent":100,
                "ev_charger_switch":"switch.guide_charger", "ev_charge_power_entity":"sensor.guide_power",
                "ev_charge_energy_entity":"sensor.guide_energy", "ev_charging_status_entity":"sensor.guide_status"}
            async def configure(flow, values):
                to_field_list(flow["data_schema"],custom_serializer=custom_serializer)
                return await hass.config_entries.flow.async_configure(flow["flow_id"],values)
            with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status",
                       new=AsyncMock(return_value={"status":"not_configured"})):
                flow = await hass.config_entries.flow.async_init("load_optimizer",context={"source":"user"})
                flow = await configure(flow,{"name":"Guided car","load_type":"ev_charging"})
                assert flow["step_id"] == "ev_setup"
                flow = await configure(flow,sources)
                assert flow["step_id"] == "ev_preferences"
                flow = await configure(flow,preferences)
                assert flow["step_id"] == "ev_review"
                assert "Read-only preview" in flow["description_placeholders"]["review"]
                assert "p/kWh" in flow["description_placeholders"]["review"]
                assert not hass.config_entries.async_entries("load_optimizer") and not commands
                hass.states.async_set("sensor.guide_power","unavailable")
                flow = await configure(flow,{"action":"save","ev_dashboard_path":"load-optimizer"})
                assert flow["errors"] == {"base":"ev_review_incomplete"}
                assert not hass.config_entries.async_entries("load_optimizer")
                hass.states.async_set("sensor.guide_power",0,{"unit_of_measurement":"W"})
                flow = await configure(flow,{"action":"refresh"})
                assert flow["errors"] == {}
                result = await configure(flow,{"action":"save","ev_dashboard_path":"load-optimizer"})
                assert result["type"] == "create_entry",result
                await hass.async_block_till_done()
                entry = hass.config_entries.async_entries("load_optimizer")[0]
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                assert not coordinator.ev_controller.enabled and not commands
                saved = await dashboard.async_load(False)
                assert saved["views"][0] == original["views"][0]
                assert len(saved["views"]) == 2
                assert all(card["type"] == "markdown" for card in saved["views"][1]["cards"])
                assert "sensor.ev_charging_review" not in str(saved["views"][1])
                saved["views"][1]["cards"].append({"type":"markdown","content":"My custom EV note"})
                await dashboard.async_save(saved)
                assert await async_add_ev_view(hass,entry,"load-optimizer") == "existing_view_preserved"
                assert await dashboard.async_load(False) == saved
                registry = er.async_get(hass)
                before_ids = {item.unique_id:item.entity_id for item in er.async_entries_for_config_entry(registry,entry.entry_id)}
                before_options = dict(entry.options)
                edit = await hass.config_entries.options.async_init(entry.entry_id)
                edit = await hass.config_entries.options.async_configure(edit["flow_id"],{"next_step_id":"ev_setup"})
                edit = await hass.config_entries.options.async_configure(edit["flow_id"],sources)
                edit = await hass.config_entries.options.async_configure(edit["flow_id"],{**preferences,"ev_session_max_energy_kwh":0.3})
                assert edit["step_id"] == "ev_review" and dict(entry.options) == before_options
                hass.config_entries.options.async_abort(edit["flow_id"])
                assert dict(entry.options) == before_options
                assert {item.unique_id:item.entity_id for item in er.async_entries_for_config_entry(registry,entry.entry_id)} == before_ids
                edit = await hass.config_entries.options.async_init(entry.entry_id)
                edit = await hass.config_entries.options.async_configure(edit["flow_id"],{"next_step_id":"ev_setup"})
                edit = await hass.config_entries.options.async_configure(edit["flow_id"],sources)
                edit = await hass.config_entries.options.async_configure(edit["flow_id"],{**preferences,"ev_session_max_energy_kwh":0.3})
                hass.config_entries.async_update_entry(entry, options={**entry.options,"price_cap_region":"London"})
                await hass.async_block_till_done()
                result = await hass.config_entries.options.async_configure(edit["flow_id"],{"action":"save","ev_dashboard_path":"load-optimizer"})
                assert result["type"] == "create_entry", result
                await hass.async_block_till_done()
                assert entry.options["ev_session_max_energy_kwh"] == 0.3
                assert entry.options["price_cap_region"] == "London"
                assert await dashboard.async_load(False) == saved
                assert await async_add_ev_view(hass,entry,"yaml-only") == "dashboard_unavailable"
                changed = deepcopy(original)
                changed["title"] = "Concurrent user edit"
                raced = SimpleNamespace(mode="storage", async_load=AsyncMock(side_effect=[original,changed]), async_save=AsyncMock())
                hass.data[LOVELACE_DATA].dashboards["raced"] = raced
                assert await async_add_ev_view(hass,entry,"raced") == "dashboard_changed_retry"
                raced.async_save.assert_not_awaited()
                assert {item.unique_id:item.entity_id for item in er.async_entries_for_config_entry(registry,entry.entry_id)} == before_ids
                assert not commands
                print("Guided HA: staged create/edit, fresh save validation, no switch calls, stable identity, additive dashboard and custom-view preservation passed")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
