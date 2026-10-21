"""Test-only SOC feedback automation in isolated HA; never a physical load."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template


async def main():
    logging.basicConfig(level=logging.WARNING)
    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "dev/ev-test-battery-fill.yaml").read_text())
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        calls = []
        try:
            assert await async_from_config_dict({
                "homeassistant": {"time_zone": "Europe/London"},
                "http": {"server_host": "127.0.0.1", "server_port": 18129},
                "automation": config["automation"],
            }, hass) is hass

            async def fill(call):
                entity = call.data["entity_id"]
                assert entity in ("input_number.ev_trial_battery_percent", ["input_number.ev_trial_battery_percent"])
                calls.append(float(call.data["value"]))
                hass.states.async_set("input_number.ev_trial_battery_percent", call.data["value"])

            hass.services.async_register("input_number", "set_value", fill)
            for key, value in {
                "input_boolean.ev_trial_simulate_battery_gain": "on",
                "input_boolean.ev_trial_connected": "on",
                "switch.ev_trial_load": "on",
                "switch.ev_trial_automatic_charging_control": "on",
                "input_number.ev_trial_battery_percent": "54",
                "input_number.ev_trial_capacity_kwh": "0.6",
            }.items():
                hass.states.async_set(key, value)
            expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            hass.states.async_set("input_datetime.ev_trial_simulation_expires", expiry.isoformat(),
                                  {"timestamp": expiry.timestamp()})
            hass.states.async_set("sensor.ev_trial_load_energy", "10", {"unit_of_measurement": "kWh"})
            await hass.async_start()
            await hass.async_block_till_done()
            calls.clear()
            status = Template(config["template"][0]["sensor"][0]["state"], hass)
            assert status.async_render() == "active"

            async def meter(value, unit="kWh"):
                hass.states.async_set("sensor.ev_trial_load_energy", value, {"unit_of_measurement": unit})
                await hass.async_block_till_done()

            await meter("10.006")
            assert calls == [55.0], calls
            for value in ("unknown", "11", "0", "0.5"):
                await meter(value)
            assert calls == [55.0], "Unknown, reset and excessive meter jumps must not fill SOC"
            await meter("0.501", "Wh")
            assert calls == [55.0], "Wrong units must not fill SOC"
            hass.states.async_set("input_boolean.ev_trial_simulate_battery_gain", "off")
            assert status.async_render() == "disabled"
            await meter("0.502")
            assert calls == [55.0], "Disabled simulation must leave manual battery feedback alone"
            hass.states.async_set("input_boolean.ev_trial_simulate_battery_gain", "on")
            hass.states.async_set("switch.ev_trial_load", "off")
            await meter("0.503")
            assert calls == [55.0], "Manual/uncontrolled energy must not fill SOC"
            hass.states.async_set("switch.ev_trial_load", "on")
            hass.states.async_set("input_number.ev_trial_battery_percent", "99.9")
            await meter("0.509")
            assert calls[-1] == 100, calls
            count = len(calls)
            for attributes in ({}, {"timestamp": 0}):
                hass.states.async_set("input_datetime.ev_trial_simulation_expires", "unknown", attributes)
                assert status.async_render() == ("expired" if attributes else "expiry_not_configured")
                await meter("0.510" if not attributes else "0.511")
                assert len(calls) == count, "Missing/expired session must not fill SOC"
            print("Battery-fill expiry: missing and expired deadlines block updates")
            print("Battery-fill smoke: measured gain, reset/jump/unit rejection, opt-out, socket guard, target clamp passed")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
