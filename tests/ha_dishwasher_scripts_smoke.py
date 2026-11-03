"""Execute public dishwasher scripts with synthetic button services only."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries
from homeassistant.setup import async_setup_component
from homeassistant.helpers import entity_registry as er, device_registry as dr

ROOT = Path(__file__).resolve().parents[1]


async def main():
    definitions = yaml.safe_load((ROOT / "docs/examples/dishwasher-scripts.yaml").read_text())
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        hass.config_entries = ConfigEntries(hass, {})
        dr.async_setup(hass)
        await dr.async_load(hass)
        await er.async_load(hass)
        calls = []

        async def pressed(call):
            calls.append(call.data["entity_id"])

        hass.services.async_register("button", "press", pressed)
        try:
            assert await async_setup_component(hass, "script", {"script": definitions})
            await hass.async_block_till_done()
            for key in definitions:
                await hass.services.async_call("script", key, {}, blocking=True)
            assert calls == [
                ["button.load_optimizer_1_request_overnight"],
                ["button.load_optimizer_1_request_now"],
                ["button.load_optimizer_1_cancel_schedule"],
            ], calls
            assert not hass.services.has_service("switch", "turn_on")
            print("All three documented scripts dispatch only their intended native button")
        finally:
            await hass.async_stop()


asyncio.run(main())
