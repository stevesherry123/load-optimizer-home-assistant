"""Execute public dishwasher scripts with synthetic button services only."""

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries
from homeassistant.setup import async_setup_component
from homeassistant.helpers import entity_registry as er, device_registry as dr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dev.build_dashboard_beta import build, walk


async def main():
    definitions = yaml.safe_load((ROOT / "docs/examples/dishwasher-scripts.yaml").read_text())
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        hass.config_entries = ConfigEntries(hass, {})
        await hass.config_entries.async_initialize()
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
            calls.clear()
            commands = [node for node in walk(build()) if node.get("action") == "perform-action"]
            for command in commands:
                domain, service = command["perform_action"].split(".")
                await hass.services.async_call(domain, service, command["target"], blocking=True)
            assert calls == [
                "button.load_optimizer_1_request_overnight", "button.load_optimizer_1_request_now",
                "button.load_optimizer_1_cancel_schedule", "button.load_optimizer_1_request_now_override",
            ], calls
            assert not hass.services.has_service("switch", "turn_on")
            print("Three scripts and four dashboard actions dispatch only their intended native buttons")
        finally:
            await hass.async_stop()


asyncio.run(main())
