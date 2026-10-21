"""Cold timezone setup, cached Ofgem lookups and DST boundaries, no network."""

import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import aiozoneinfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from custom_components.load_optimizer import async_setup_entry
from custom_components.load_optimizer.optimizer.ofgem import PriceCapReference
from custom_components.load_optimizer.price_cap import PriceCapManager
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        entry = SimpleNamespace(entry_id="timezone_test", data={"tariff_timezone":"Pacific/Chatham"},
            options={}, async_on_unload=Mock(), add_update_listener=Mock())
        hass.config_entries = SimpleNamespace(async_forward_entry_setups=AsyncMock())
        seen = []
        factory = Mock(side_effect=lambda hass, entry, *, local_timezone: (
            seen.append(local_timezone) or SimpleNamespace(async_config_entry_first_refresh=AsyncMock(),
                orchestrator=None)))
        original = aiozoneinfo.get_time_zone
        threads = []
        def resolve(name):
            threads.append(get_ident())
            return original(name)
        ZoneInfo.clear_cache()
        aiozoneinfo.CachedZoneInfo.clear_cache()
        try:
            with patch("aiozoneinfo.get_time_zone", side_effect=resolve), \
                 patch("custom_components.load_optimizer.LoadOptimizerCoordinator",factory), \
                 patch("custom_components.load_optimizer._async_migrate_native_status_entities"), \
                 patch("custom_components.load_optimizer._async_remove_obsolete_control_entities"), \
                 patch("custom_components.load_optimizer._async_claim_native_status_entity_ids"):
                assert await async_setup_entry(hass,entry)
            assert len(seen)==1 and seen[0].key=="Pacific/Chatham"
            assert len(threads)==1 and threads[0]!=get_ident(), threads
            with patch("custom_components.load_optimizer.dt_util.async_get_time_zone",new=AsyncMock(return_value=None)), \
                 patch("custom_components.load_optimizer.LoadOptimizerCoordinator") as invalid_factory:
                from homeassistant.exceptions import ConfigEntryError
                try:
                    await async_setup_entry(hass,entry)
                except ConfigEntryError:
                    pass
                else:
                    raise AssertionError("Invalid timezone must fail before starting a coordinator")
                invalid_factory.assert_not_called()
            print("Cold entry setup: one asynchronous resolution, timezone I/O off the event loop, invalid names rejected")

            london = await dt_util.async_get_time_zone("Europe/London")
            async def manager(start=date(2026,1,1),end=date(2027,1,1)):
                value = PriceCapManager(hass,entry)
                value.store = SimpleNamespace(async_load=AsyncMock(return_value=None),async_save=AsyncMock())
                value._async_fetch = AsyncMock(return_value=[PriceCapReference(
                    effective_from=start,effective_to=end,unit_rate_p_per_kwh=26.49,
                    region="North Western England",payment_method="direct_debit",source="ofgem")])
                return value
            async def status(value, stamp):
                # No timezone construction may occur while serving the result.
                with patch("zoneinfo.ZoneInfo",side_effect=AssertionError("Synchronous timezone construction")):
                    return await value.async_status(region="North Western England",payment_method="direct_debit",
                        local_timezone=london,now_utc=datetime.fromisoformat(stamp))
            value = await manager()
            await status(value,"2026-06-01T23:30:00+00:00")
            await status(value,"2026-06-02T00:30:00+00:00")
            assert value._async_fetch.await_count==1, "Same local day must reuse cache across UTC midnight"
            value = await manager()
            await status(value,"2026-06-01T22:30:00+00:00")
            await status(value,"2026-06-01T23:30:00+00:00")
            assert value._async_fetch.await_count==2, "Local midnight must refresh even on the same UTC date"
            for start,end,stamp,hours in ((date(2026,3,29),date(2026,3,30),"2026-03-29T12:00:00+00:00",23),
                                         (date(2026,10,25),date(2026,10,26),"2026-10-25T00:30:00+00:00",25)):
                value = await manager(start,end)
                result = await status(value,stamp)
                assert result["status"]=="ready",result
                reference = result["references"][0]
                duration = datetime.fromisoformat(reference["effective_to_utc"]) - datetime.fromisoformat(reference["effective_from_utc"])
                assert duration.total_seconds()==hours*3600,(hours,reference)
                if hours==25:
                    await status(value,"2026-10-25T01:30:00+00:00")
                    assert value._async_fetch.await_count==1, "Repeated DST hour must not refetch"
            print("Ofgem: no synchronous zone construction; local/UTC midnight cache rules and 23/25-hour DST boundaries passed")
            runtime = LegacyRuntime(hass)
            runtime.store = SimpleNamespace(async_load=AsyncMock(return_value=None),async_save=AsyncMock())
            hass.services.async_register("persistent_notification","create",lambda call:None)
            hass.states.async_set("sensor.timezone_test_power","0",{"unit_of_measurement":"W"})
            from custom_components.load_optimizer.legacy import app_runtime
            update = app_runtime.update_instance
            def guarded_update(*args, **kwargs):
                with patch("zoneinfo._common.load_data",side_effect=AssertionError("Cold legacy timezone read")):
                    return update(*args, **kwargs)
            with patch.object(app_runtime,"update_instance",side_effect=guarded_update):
                result = await runtime.async_scan({"instances":[{"id":"1","power_sensor":"sensor.timezone_test_power"}],
                    "tariff_timezone":"Pacific/Fiji"})
            assert "Pacific/Fiji" in runtime._timezones
            assert result.entities["sensor.load_optimizer_1_status"]["state"] != "error"
            print("Legacy scan: configured timezone retained before calculations; no cold timezone-file reads")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
