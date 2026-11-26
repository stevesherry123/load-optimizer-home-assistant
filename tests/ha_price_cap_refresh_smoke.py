"""HA store, concurrent refresh, retry/restart and expiry behavior without network."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.optimizer.ofgem import PriceCapReference
from custom_components.load_optimizer.price_cap import PriceCapManager, PriceCapSourceError


async def main():
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        entry = SimpleNamespace(entry_id='benchmark-test')
        now = datetime(2026, 11, 26, tzinfo=timezone.utc)
        ref = PriceCapReference(date(2026, 10, 1), date(2027, 1, 1), 26.49, 'North Western England', 'direct_debit')
        manager = PriceCapManager(hass, entry)
        manager.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        async def status(value=manager, stamp=now, region='North Western England'):
            return await value.async_status(region=region, payment_method='direct_debit', local_timezone=timezone.utc, now_utc=stamp)
        manager._async_fetch = AsyncMock(return_value=[ref])
        await asyncio.gather(*(status() for _ in range(20)))
        assert manager._async_fetch.await_count == 1
        manager._async_fetch = AsyncMock(side_effect=PriceCapSourceError('no_matching_electricity_table'))
        tomorrow = now + timedelta(days=1)
        with patch('custom_components.load_optimizer.price_cap.LOGGER') as logger:
            results = await asyncio.gather(*(status(stamp=tomorrow) for _ in range(20)))
            assert manager._async_fetch.await_count == 1
            assert all(r['status'] == 'stale' and r['unit_rate_p_per_kwh'] == 26.49 for r in results)
            assert results[0]['error_detail'] == 'no_matching_electricity_table'
            assert results[0]['next_retry_at'] == (tomorrow + timedelta(minutes=15)).isoformat()
            logger.warning.assert_called_once()
            await status(stamp=tomorrow + timedelta(minutes=15))
            assert manager._async_fetch.await_count == 2
            logger.warning.assert_called_once()
        # A restart must not turn a persisted hold into a request storm.
        restored = PriceCapManager(hass, entry)
        restored.store = SimpleNamespace(async_load=AsyncMock(return_value=manager.cache.copy()), async_save=AsyncMock())
        restored._async_fetch = AsyncMock(side_effect=AssertionError('retry before deadline'))
        result = await status(restored, tomorrow + timedelta(minutes=16))
        assert result['status'] == 'stale'
        restored._async_fetch.assert_not_called()
        # Expired data is never advertised as a current benchmark.
        expiry_manager = PriceCapManager(hass, entry)
        expiry_manager.store = SimpleNamespace(async_load=AsyncMock(return_value=manager.cache.copy()), async_save=AsyncMock())
        expiry_manager._async_fetch = AsyncMock(side_effect=TimeoutError())
        expired = await status(expiry_manager, datetime(2027, 1, 1, tzinfo=timezone.utc))
        assert expired['status'] == 'error' and 'unit_rate_p_per_kwh' not in expired
        # Recovery clears the hold and restores daily caching.
        restored._async_fetch = AsyncMock(return_value=[ref])
        recovered = await status(restored, tomorrow + timedelta(hours=7))
        assert recovered['status'] == 'ready' and recovered['error'] is None
        assert 'refresh_failure' not in restored.cache
        await status(restored, tomorrow + timedelta(hours=8))
        assert restored._async_fetch.await_count == 1
        # Settings for a different region cannot be blocked by the previous hold.
        restored._async_fetch = AsyncMock(side_effect=TimeoutError())
        result = await status(restored, tomorrow + timedelta(days=1), region='London')
        assert result['status'] == 'error' and 'unit_rate_p_per_kwh' not in result
        restored._async_fetch.assert_awaited_once()
        # A save failure cannot publish a new retrieval date or destroy the old value.
        disk_failure = PriceCapManager(hass, entry)
        old_cache = {key: value for key, value in manager.cache.items() if key != 'refresh_failure'}
        disk_failure.store = SimpleNamespace(async_load=AsyncMock(return_value=old_cache.copy()),
            async_save=AsyncMock(side_effect=OSError('disk unavailable')))
        disk_failure._async_fetch = AsyncMock(return_value=[ref])
        result = await status(disk_failure, tomorrow)
        assert result['status'] == 'stale' and result['retrieved_at'] == now.isoformat()
        await status(disk_failure, tomorrow + timedelta(minutes=1))
        disk_failure._async_fetch.assert_awaited_once()
        # Persistent failures saturate at six-hour retry spacing.
        backoff = PriceCapManager(hass, entry)
        backoff.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        backoff._async_fetch = AsyncMock(side_effect=TimeoutError())
        stamp = now
        for delay in (15, 30, 60, 120, 240, 360, 360):
            result = await status(backoff, stamp)
            due = datetime.fromisoformat(result['next_retry_at'])
            assert due - stamp == timedelta(minutes=delay)
            stamp = due
        # Cancellation must propagate, rather than be cached as a failed fetch.
        cancelled = PriceCapManager(hass, entry)
        cancelled.store = manager.store
        cancelled._async_fetch = AsyncMock(side_effect=asyncio.CancelledError())
        try:
            await status(cancelled)
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('Cancellation swallowed')
        # Source layout errors have bounded public diagnostics.
        parser = PriceCapManager(hass, entry)
        with patch('custom_components.load_optimizer.price_cap.async_get_clientsession'), \
             patch.object(parser, '_async_fetch_text', new=AsyncMock(return_value='<html>no table</html>')):
            try:
                await parser._async_fetch('London', 'direct_debit')
            except PriceCapSourceError as error:
                assert str(error) == 'no_embedded_tables'
            else:
                raise AssertionError('Missing table silently accepted')
        print('Ofgem: concurrent daily cache, bounded retries, restart hold, expiry, recovery, settings isolation and cancellation passed')


if __name__ == '__main__':
    asyncio.run(main())
