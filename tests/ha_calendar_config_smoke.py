"""Provider floor uses actual entity ownership, including renamed sources."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from custom_components.load_optimizer import _async_check_source_versions


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        try:
            registry = er.async_get(hass)
            await registry.async_load()
            source = registry.async_get_or_create("sensor", "octopus_energy", "synthetic_price",
                                                  suggested_object_id="renamed_tariff")
            entry = SimpleNamespace(data={"tariff_entity": source.entity_id}, options={})
            with patch("custom_components.load_optimizer.async_get_integration", new_callable=AsyncMock) as provider:
                for version in ("19.2.0", "19.2.1b0", None, "unknown"):
                    provider.return_value = SimpleNamespace(manifest={"version": version})
                    try:
                        await _async_check_source_versions(hass, entry)
                    except ConfigEntryError:
                        pass
                    else:
                        raise AssertionError(f"Unsupported provider version accepted: {version}")
                for version in ("19.2.1", "19.3.0", "20.0.0"):
                    provider.return_value = SimpleNamespace(manifest={"version": version})
                    await _async_check_source_versions(hass, entry)
                provider.reset_mock()
                await _async_check_source_versions(hass, SimpleNamespace(data={"tariff_entity": "sensor.other"}, options={}))
                provider.assert_not_awaited()
            print("Calendar source version floor: old/prerelease/invalid rejected; supported and generic providers passed")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
