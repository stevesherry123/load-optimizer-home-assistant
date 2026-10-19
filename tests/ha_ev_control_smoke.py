"""Real minimum HA storage/services; synthetic charger only, no network or car."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from homeassistant import loader
from custom_components.load_optimizer.ev_control import EVChargeController
from custom_components.load_optimizer.config_flow import _ev_schema
import voluptuous as vol


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        controller = None
        try:
            config = {"load_type": "ev_charging", "tariff_entity": "sensor.rates", "charge_power_kw": 1,
                "battery_entity": "sensor.battery", "battery_capacity_entity": "sensor.capacity",
                "connection_status_entity": "sensor.connection", "ev_charger_switch": "switch.synthetic",
                "ev_charge_power_entity": "sensor.power", "ev_charge_energy_entity": "sensor.energy",
                "ev_charging_status_entity": "sensor.charging"}
            form_values = {key: value for key, value in config.items() if key != "load_type"}
            assert vol.Schema(_ev_schema(config))(form_values)["ev_charger_switch"] == "switch.synthetic"
            values = {"switch.synthetic": ("off", {}), "sensor.battery": ("10", {"unit_of_measurement": "%"}),
                "sensor.capacity": ("60", {"unit_of_measurement": "kWh"}), "sensor.connection": ("connected", {}),
                "sensor.power": ("1000", {"unit_of_measurement": "W"}),
                "sensor.energy": ("100", {"unit_of_measurement": "kWh"}), "sensor.charging": ("charging", {})}
            for key, (state, attributes) in values.items():
                hass.states.async_set(key, state, attributes)
            commands = []
            async def command(call):
                assert call.data["entity_id"] == "switch.synthetic"
                commands.append(call.service)
                hass.states.async_set("switch.synthetic", "on" if call.service == "turn_on" else "off")
            hass.services.async_register("switch", "turn_on", command)
            hass.services.async_register("switch", "turn_off", command)
            entry = SimpleNamespace(entry_id="synthetic_ev_control", data=config, options={})
            controller = EVChargeController(hass, entry, lambda: None)
            now = datetime.now(timezone.utc)
            controller.set_plan({"status": "ready", "selected_slots": [{"start": now.isoformat(),
                "end": (now + timedelta(minutes=30)).isoformat()}]}, now)
            await controller.async_start()
            assert commands == [] and not controller.enabled
            await controller.async_enable()
            await controller.async_tick()
            assert commands == ["turn_on"] and controller.owned_target == "switch.synthetic"
            await controller.async_disable()
            await controller.async_tick()
            assert commands == ["turn_on", "turn_off"] and controller.owned_target is None
            hass.states.async_set("switch.synthetic", "on")
            await controller.async_tick()
            assert commands == ["turn_on", "turn_off"]
            await controller.store.async_save({"owned_target": "switch.synthetic"})
            await controller.async_stop()
            controller = EVChargeController(hass, entry, lambda: None)
            await controller.async_start()
            assert commands[-1] == "turn_off" and not controller.enabled
            print("Real HA: EV selectors validate; default off; synthetic start/stop; manual ownership respected; journal recovery disarmed")
        finally:
            if controller:
                await controller.async_stop()
            await hass.async_stop(force=True)


asyncio.run(main())
