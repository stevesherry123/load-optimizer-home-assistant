"""Run test-bench observers in isolated HA with a synthetic switch and notifiers."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from homeassistant.core import Context, HomeAssistant
from homeassistant.setup import async_setup_component

ROOT = Path(__file__).resolve().parents[1]


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        delivered = []

        async def remember(call):
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
        config = yaml.safe_load((ROOT / "dev/ev-test-alerts.yaml").read_text())
        assert await async_setup_component(hass, "automation", {"automation": config["automation"]})
        await hass.async_start()
        await hass.async_block_till_done()

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
        await hass.async_stop()
        print("EV alerts: service context, unknown caller, availability, attribute filtering, both destinations and disable passed")


asyncio.run(main())
