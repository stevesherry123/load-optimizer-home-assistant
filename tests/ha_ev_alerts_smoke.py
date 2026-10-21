"""Run test-bench observers in isolated HA with a synthetic switch and notifiers."""

import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import Context, HomeAssistant

ROOT = Path(__file__).resolve().parents[1]


async def main():
    logging.basicConfig(level=logging.WARNING)
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        config = yaml.safe_load((ROOT / "dev/ev-test-alerts.yaml").read_text())
        assert await async_from_config_dict({
            "homeassistant": {"time_zone": "Europe/London"},
            "http": {"server_host": "127.0.0.1", "server_port": 18128},
            "automation": config["automation"],
        }, hass) is hass
        delivered = []

        async def remember(call):
            assert isinstance(call.data["value"], str)
            hass.states.async_set("input_text.ev_trial_switch_command", call.data["value"], context=call.context)

        async def notify(call):
            delivered.append(dict(call.data))

        async def fake_switch(call):
            value = "on" if call.service == "turn_on" else "off"
            hass.states.async_set("switch.ev_trial_load", value, context=call.context)

        hass.services.async_register("input_text", "set_value", remember)
        hass.services.async_register("persistent_notification", "create", notify)
        hass.services.async_register("notify", "ev_trial_phone", notify)
        hass.services.async_register("switch", "turn_on", fake_switch)
        hass.services.async_register("switch", "turn_off", fake_switch)
        hass.states.async_set("input_text.ev_trial_switch_command", "{}")
        hass.states.async_set("input_boolean.ev_trial_switch_alerts", "on")
        hass.states.async_set("switch.ev_trial_load", "off")
        hass.states.async_set("sensor.ev_trial_battery", "65")
        hass.states.async_set("sensor.ev_trial_target", "90")
        hass.states.async_set("switch.ev_trial_automatic_charging_control", "on", {"reason": "starting_selected_slot"})
        await hass.async_start()
        await hass.async_block_till_done()
        assert len(hass.data["automation"].entities) == 3

        async def settle():
            await asyncio.sleep(1.2)
            await hass.async_block_till_done()

        await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.ev_trial_load"}, blocking=True)
        await settle()
        assert len(delivered) == 2, delivered
        assert "switch.turn_on" in delivered[-1]["message"], delivered
        assert "starting selected slot" in delivered[-1]["message"]
        assert "exact caller not confirmed" in delivered[-1]["message"]

        await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.ev_trial_load"},
                                      blocking=True, context=Context(user_id="a" * 32))
        await settle()
        assert len(delivered) == 4
        assert "user/API initiated" in delivered[-1]["message"]
        hass.states.async_set("switch.ev_trial_load", "on", context=Context())
        await settle()
        assert len(delivered) == 6
        assert "no matching HA command" in delivered[-1]["message"]
        hass.states.async_set("switch.ev_trial_load", "on", {"watts": 50})
        await settle()
        assert len(delivered) == 6, "Attribute-only updates must not create relay alerts"
        hass.states.async_set("switch.ev_trial_load", "unavailable")
        await settle()
        assert len(delivered) == 8
        assert "not confirmation of a physical relay" in delivered[-1]["message"]
        hass.states.async_set("input_boolean.ev_trial_switch_alerts", "off")
        hass.states.async_set("switch.ev_trial_load", "off")
        await settle()
        assert len(delivered) == 8, "Alert toggle must suppress notifications"
        hass.states.async_set("input_boolean.ev_trial_switch_alerts", "on")
        attrs = {"reason": "charging_in_selected_slot", "delivery": {"warning": "battery_gain_below_expected"}}
        hass.states.async_set("switch.ev_trial_automatic_charging_control", "on", attrs)
        await settle()
        assert any("This warning does not cut power" in call["message"] for call in delivered)
        count = len(delivered)
        attrs["delivery"]["delivered_wall_kwh"] = 0.1
        hass.states.async_set("switch.ev_trial_automatic_charging_control", "on", attrs)
        await settle()
        assert len(delivered) == count, "An ongoing warning must not repeatedly notify"
        hass.states.async_set("switch.ev_trial_automatic_charging_control", "off", {
            "reason": "session_energy_limit_reached", "session_energy_kwh": 0.3,
            "session_max_energy_kwh": 0.3, "session_max_hours": 4})
        await settle()
        assert len(delivered) == count + 2, delivered
        assert "explicitly enable a new session" in delivered[-1]["message"]
        await hass.async_stop()
        print("EV alerts: service context, unknown caller, availability, attribute filtering, both destinations and disable passed")


asyncio.run(main())
