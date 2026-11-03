"""Observe real HA door events without appliance services or physical devices."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.orchestration import NativeOrchestrator


class Clock(datetime):
    current = datetime.now(timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        controller = NativeOrchestrator(hass, SimpleNamespace(entry_id="synthetic"), None)
        controller._loaded = True
        controller.store = SimpleNamespace(async_save=AsyncMock())
        controller.config = {"bosch_door_sensor": "binary_sensor.synthetic_door"}
        hass.states.async_set("binary_sensor.synthetic_door", "off")
        with patch("custom_components.load_optimizer.orchestration.datetime", Clock):
            try:
                await controller.async_start()
                for seconds, expected in ((119, False), (120, True)):
                    controller.state["door_opened_since_last_cycle"] = False
                    hass.states.async_set("binary_sensor.synthetic_door", "on")
                    await hass.async_block_till_done()
                    Clock.current += timedelta(seconds=seconds)
                    hass.states.async_set("binary_sensor.synthetic_door", "off")
                    await hass.async_block_till_done()
                    assert controller.state["door_opened_since_last_cycle"] is expected
                controller.state["door_opened_since_last_cycle"] = False
                hass.states.async_set("binary_sensor.synthetic_door", "on")
                await hass.async_block_till_done()
                await controller.async_stop()
                Clock.current += timedelta(minutes=3)
                await controller.async_start()
                hass.states.async_set("binary_sensor.synthetic_door", "off")
                await hass.async_block_till_done()
                assert controller.state["door_opened_since_last_cycle"] is False
                assert not hass.services.has_service("button", "press")
                print("Real HA door events enforce threshold and forget interrupted openings")
            finally:
                await controller.async_stop()
                await hass.async_stop()


asyncio.run(main())
