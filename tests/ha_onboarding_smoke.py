"""Real minimum-HA clean install using only documented examples and fake sources.

No HTTP server, login, supplier calls, migrated learning or physical device I/O.
Run separately from the dependency-free unittest suite.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import AsyncMock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_validation import custom_serializer
from voluptuous_serialize import convert

from custom_components.load_optimizer.legacy import app_runtime
from custom_components.load_optimizer.orchestration import LEGACY_CONFIG_HELPERS

DOMAIN = "load_optimizer"
CONTROL = {
    "bosch_device_id": "synthetic-home-connect-device",
    "bosch_power_switch": "switch.synthetic_dishwasher_power",
    "bosch_program_select": "select.synthetic_dishwasher_program",
    "bosch_start_button": "button.synthetic_dishwasher_start",
    "bosch_selected_program_sensor": "sensor.synthetic_dishwasher_program",
    "bosch_power_state_sensor": "sensor.synthetic_dishwasher_power_state",
    "bosch_connected_sensor": "binary_sensor.synthetic_dishwasher_connected",
    "bosch_door_sensor": "binary_sensor.synthetic_dishwasher_door",
    "bosch_remote_control_sensor": "binary_sensor.synthetic_dishwasher_remote_control",
    "bosch_remote_start_sensor": "binary_sensor.synthetic_dishwasher_remote_start",
    "bosch_operation_state_sensor": "sensor.synthetic_dishwasher_operation",
}


class Clock(datetime):
    current = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


def identities(hass, entry_id):
    return {item.unique_id: (item.entity_id, item.device_id)
            for item in er.async_entries_for_config_entry(er.async_get(hass), entry_id)}


def entities_in(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "entity" and isinstance(child, str):
                yield child
            else:
                yield from entities_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from entities_in(child)
    elif isinstance(value, str) and value.startswith("sensor."):
        yield value


async def configure(hass, kind, name, values):
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == "form", flow
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": name, "load_type": kind}
    )
    convert(flow["data_schema"], custom_serializer=custom_serializer)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], values)
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state.value == "loaded", entry.state
    return entry


async def session(config_dir, example_name, snapshot=None):
    example = (ROOT / "docs/examples" / example_name).read_text()
    appliance = yaml.safe_load(example)[0]
    is_dishwasher = bool(appliance.get("program_sensor"))
    programme = appliance["program_policies"][0]["program"]
    control = dict(CONTROL)
    if is_dishwasher:
        control.update(bosch_selected_program_sensor=appliance["program_sensor"],
                       bosch_operation_state_sensor=appliance["state_sensor"])
    hass = HomeAssistant(str(config_dir))
    loader.async_setup(hass)
    start = Clock.current
    rates = [{"start": (start + timedelta(minutes=30 * index)).isoformat(),
              "end": (start + timedelta(minutes=30 * (index + 1))).isoformat(),
              "value_inc_vat": 0.20} for index in range(96)]
    hass.states.async_set("sensor.synthetic_rates", "ready", {"rates": rates})
    hass.states.async_set(appliance["power_sensor"], 0)
    hass.states.async_set(appliance["energy_sensor"], 100)
    if is_dishwasher:
        hass.states.async_set(appliance["program_sensor"], "Dishcare.Dishwasher.Program." + programme)
        hass.states.async_set(appliance["state_sensor"], "BSH.Common.EnumType.OperationState.Ready")
    hass.states.async_set("sensor.synthetic_ev_battery", 40)
    hass.states.async_set("binary_sensor.ev_plugged_in", "on")
    for key, entity_id in (control.items() if is_dishwasher else []):
        if key == "bosch_device_id":
            continue
        state = "off" if key == "bosch_door_sensor" else "on"
        attributes = {}
        if key == "bosch_operation_state_sensor":
            state = "BSH.Common.EnumType.OperationState.Ready"
        elif key == "bosch_selected_program_sensor":
            state = "Dishcare.Dishwasher.Program." + programme
        elif key == "bosch_program_select":
            state = "Eco50"
            attributes = {"options": ["Eco50", "MixedLoad"]}
        hass.states.async_set(entity_id, state, attributes)

    ev_blocks = re.findall(r"```yaml\n(.*?)\n```",
                           (ROOT / "docs/ev-charging.md").read_text(), re.DOTALL)
    assert len(ev_blocks) == 2
    template_config = [item for block in ev_blocks for item in yaml.safe_load(block)["template"]]
    calls = []
    original_call = type(hass.services).async_call

    async def guarded_call(registry, domain, service, service_data=None, *args, **kwargs):
        if domain in {"switch", "select", "button", "home_connect"}:
            calls.append((domain, service, service_data))
            raise AssertionError("Unexpected device command during read-only onboarding")
        return await original_call(registry, domain, service, service_data, *args, **kwargs)

    with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status",
               new=AsyncMock(return_value={"status": "not_configured", "source": "test"})), \
         patch("custom_components.load_optimizer.legacy_runtime.datetime", Clock), \
         patch.object(app_runtime, "datetime", Clock), \
         patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
         patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()), \
         patch.object(type(hass.services), "async_call", new=guarded_call):
        try:
            assert await async_from_config_dict({
                "homeassistant": {"name": "Synthetic onboarding", "time_zone": "Europe/London"},
                "template": template_config,
            }, hass) is hass
            await hass.async_start()
            await hass.async_block_till_done()
            assert hass.states.get("sensor.ev_usable_battery_capacity").state == "60"
            assert hass.states.get("sensor.ev_charging_connection").state == "connected"
            dashboard_store = LovelaceStorage(hass, {"id": "onboarding", "url_path": "onboarding-test"})

            if snapshot is None:
                assert not hass.config_entries.async_entries(DOMAIN)
                entry = await configure(hass, "learned_appliance", "First appliance", {
                    "instances_yaml": example, "tariff_entity": "sensor.synthetic_rates",
                    "tariff_timezone": "Europe/London", "tariff_price_unit": "gbp_per_kwh",
                    "price_cap_region": "Merseyside and Northern Wales",
                    "price_cap_payment_method": "direct_debit",
                })
            else:
                entries = hass.config_entries.async_entries(DOMAIN)
                entry = next(item for item in entries if item.data["load_type"] == "learned_appliance")
                assert entry.entry_id == snapshot["entry_id"]

            coordinator = hass.data[DOMAIN][entry.entry_id]
            controller = coordinator.orchestrator
            assert not controller.state["auto_mode_enabled"]
            assert not controller.state["auto_negative_price_enabled"]
            assert controller.state["request"] is None

            if snapshot is None:
                assert not controller.state["active"]
                assert coordinator.legacy_runtime.state["instances"]["1"].get("runs", 0) == 0
                for minute in range(18):
                    Clock.current = start + timedelta(minutes=minute)
                    hass.states.async_set(appliance["power_sensor"], 1000 if minute < 13 else 0)
                    hass.states.async_set(appliance["energy_sensor"], 100 + min(minute, 13) / 60)
                    if is_dishwasher:
                        operation = "Run" if minute < 13 else "Ready"
                        hass.states.async_set(appliance["state_sensor"], "BSH.Common.EnumType.OperationState." + operation)
                    await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert hass.states.get("sensor.load_optimizer_1_total_runs").state == "1", coordinator.legacy_runtime.state
                assert hass.states.get("sensor.load_optimizer_1_cost_status").state == "ready"
                assert hass.states.get("sensor.load_optimizer_1_recommended_program").state == programme

                dashboard = yaml.safe_load((ROOT / "docs/examples/one-appliance-dashboard.yaml").read_text())
                expected = set(entities_in(dashboard))
                assert len(expected) == 12, expected
                for entity_id in expected:
                    assert hass.states.get(entity_id) is not None, entity_id
                    assert er.async_get(hass).async_get(entity_id).config_entry_id == entry.entry_id
                assert "custom:" not in (ROOT / "docs/examples/one-appliance-dashboard.yaml").read_text()
                dashboard["title"] = "My customised appliance dashboard"
                await dashboard_store.async_save(dashboard)

                try:
                    await hass.services.async_call(DOMAIN, "activate_native_orchestration", {}, blocking=True)
                except HomeAssistantError:
                    pass
                else:
                    raise AssertionError("Incomplete controller configuration unexpectedly activated")
                assert not controller.state["active"]
                if is_dishwasher:
                    assert set(control) == set(LEGACY_CONFIG_HELPERS)
                    flow = await hass.config_entries.options.async_init(entry.entry_id)
                    flow = await hass.config_entries.options.async_configure(
                        flow["flow_id"], {"next_step_id": "dishwasher_control"}
                    )
                    convert(flow["data_schema"], custom_serializer=custom_serializer)
                    result = await hass.config_entries.options.async_configure(flow["flow_id"], control)
                    assert result["type"] == "create_entry"
                    await hass.async_block_till_done()
                    coordinator = hass.data[DOMAIN][entry.entry_id]
                    assert not coordinator.orchestrator.state["active"]
                    await hass.services.async_call(DOMAIN, "activate_native_orchestration", {}, blocking=True)
                    controller = coordinator.orchestrator
                assert controller.state["active"] is is_dishwasher
                assert not controller.state["auto_mode_enabled"]
                assert not controller.state["auto_negative_price_enabled"]
                assert controller.state["request"] is None
                before = identities(hass, entry.entry_id)
                await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                assert identities(hass, entry.entry_id) == before
                assert hass.states.get("sensor.load_optimizer_1_total_runs").state == "1"
                assert await dashboard_store.async_load(False) == dashboard

                ev_entry = await configure(hass, "ev_charging", "Community EV", {
                    "tariff_entity": "sensor.synthetic_rates",
                    "battery_entity": "sensor.synthetic_ev_battery",
                    "battery_capacity_entity": "sensor.ev_usable_battery_capacity",
                    "connection_status_entity": "sensor.ev_charging_connection",
                    "charge_power_kw": 7.2, "target_percent": 80, "charger_efficiency": 0.9,
                    "slot_minutes": 30, "tariff_timezone": "Europe/London",
                    "tariff_price_unit": "gbp_per_kwh",
                    "price_cap_region": "Merseyside and Northern Wales",
                    "price_cap_payment_method": "direct_debit",
                })
                ev = hass.data[DOMAIN][ev_entry.entry_id]
                plan = ev.data["plan"]
                assert plan["status"] == "ready", plan
                assert plan["needed_battery_kwh"] == 24
                assert abs(plan["wall_energy_kwh"] - 26.6667) < 0.0001
                assert not any(value[0].startswith(("switch.", "button."))
                               for value in identities(hass, ev_entry.entry_id).values())
                for state in ("off", "unknown", "unavailable"):
                    hass.states.async_set("binary_sensor.ev_plugged_in", state)
                    await hass.async_block_till_done()
                    await ev.async_refresh()
                    assert ev.data["plan"]["reason"] == "vehicle_not_connected", (state, ev.data)
                    assert not ev.data["plan"]["charge_now"]
                snapshot = {"entry_id": entry.entry_id, "identities": before,
                            "dashboard": dashboard,
                            "ev_entry_id": ev_entry.entry_id,
                            "ev_identities": identities(hass, ev_entry.entry_id)}
                print(f"Fresh HA ({example_name}): learning, dashboard, safe control defaults and EV adapters passed")
            else:
                assert identities(hass, entry.entry_id) == snapshot["identities"]
                assert hass.states.get("sensor.load_optimizer_1_total_runs").state == "1"
                assert hass.states.get("sensor.load_optimizer_1_cost_status").state == "ready"
                assert controller.state["active"] is is_dishwasher
                assert identities(hass, snapshot["ev_entry_id"]) == snapshot["ev_identities"]
                assert await dashboard_store.async_load(False) == snapshot["dashboard"]
                print("Restart: learning, identities, customised dashboard and control opt-ins preserved")
            assert not calls, calls
            return snapshot
        finally:
            await hass.async_stop(force=True)


async def main():
    for example in ("learned-appliance.yaml", "home-connect-dishwasher.yaml"):
        Clock.current = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        with tempfile.TemporaryDirectory(prefix="load-optimizer-onboarding-") as directory:
            config_dir = Path(directory)
            (config_dir / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
            snapshot = await session(config_dir, example)
            await session(config_dir, example, snapshot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
