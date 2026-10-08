"""Exercise the actual history manager with in-memory Home Assistant storage."""

import copy
from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from test_intelligence import module as core, day

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"


class MemoryStore:
    values = {}
    writes = 0

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return copy.deepcopy(self.values.get(self.key))

    async def async_save(self, value):
        type(self).writes += 1
        self.values[self.key] = copy.deepcopy(value)


def load_manager():
    prefix = "_tariff_test"
    package = ModuleType(prefix)
    package.__path__ = [str(ROOT)]
    const = ModuleType(prefix + ".const")
    const.DOMAIN = "load_optimizer"
    storage = ModuleType("homeassistant.helpers.storage")
    storage.Store = MemoryStore
    entries = {prefix: package, prefix + ".const": const,
               prefix + ".optimizer.intelligence": core, "homeassistant.helpers.storage": storage}
    spec = importlib.util.spec_from_file_location(prefix + ".tariff_intelligence", ROOT / "tariff_intelligence.py")
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, entries):
        spec.loader.exec_module(result)
    return result


manager = load_manager()


class TariffHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        MemoryStore.values = {}
        MemoryStore.writes = 0
        self.states = {}
        self.hass = SimpleNamespace(data={}, states=SimpleNamespace(get=self.states.get))
        self.settings = {"tariff_entities": "sensor.rates", "tariff_timezone": "Europe/London", "tariff_price_unit": "p_per_kwh"}
        self.service = manager.get_service(self.hass, self.settings)
        self.now = core.utc("2026-10-08T12:00:00Z")

    def publish(self, value):
        self.states["sensor.rates"] = SimpleNamespace(attributes={"rates": [s.as_dict() for s in value.slots]})

    async def test_capture_dedup_revision_and_restart(self):
        self.publish(day(date(2026, 10, 9)))
        result = await self.service.async_status({}, self.now)
        self.assertEqual(result["storage"]["day_count"], 1)
        await self.service.async_status({}, self.now)
        self.assertEqual(MemoryStore.writes, 1)
        self.publish(day(date(2026, 10, 9), [-2]))
        result = await self.service.async_status({}, self.now)
        self.assertEqual(result["tomorrow_statistics"]["mean"], -2)
        self.assertEqual(MemoryStore.writes, 2)
        fresh = manager.TariffIntelligence(self.hass, self.service.source_id, ["sensor.rates"], "Europe/London", "p_per_kwh")
        await fresh.async_load()
        self.assertEqual(fresh.days, self.service.days)

    async def test_source_shared_and_units_isolated(self):
        self.assertIs(self.service, manager.get_service(self.hass, self.settings))
        other = manager.get_service(self.hass, {**self.settings, "tariff_price_unit": "gbp_per_kwh"})
        self.assertNotEqual(self.service.store.key, other.store.key)

    async def test_incomplete_not_written_and_missing_source_recovers(self):
        result = await self.service.async_status({}, self.now)
        self.assertEqual(result["status"], "waiting")
        self.publish(day(date(2026, 10, 9)))
        self.states["sensor.rates"].attributes["rates"].pop()
        await self.service.async_status({}, self.now)
        self.assertEqual(MemoryStore.writes, 0)
        self.publish(day(date(2026, 10, 9)))
        self.assertEqual((await self.service.async_status({}, self.now))["status"], "ready")

    async def test_corrupt_store_not_overwritten(self):
        payload = {"schema": 999, "days": {}}
        MemoryStore.values[self.service.store.key] = copy.deepcopy(payload)
        self.publish(day(date(2026, 10, 9)))
        result = await self.service.async_status({}, self.now)
        self.assertEqual(result["data_quality"], "storage_error")
        self.assertEqual(MemoryStore.values[self.service.store.key], payload)
        self.assertEqual(MemoryStore.writes, 0)

    async def test_retention_and_learning_store_independence(self):
        learning_key = "load_optimizer.legacy.memory"
        MemoryStore.values[learning_key] = {"runs": 113}
        old = day(date(2025, 10, 1))
        old = core.TariffDay(old.local_date, old.timezone_name, old.slots, self.service.source_id)
        self.service.days = {old.local_date.isoformat(): old}
        self.service.loaded = True
        self.publish(day(date(2026, 10, 9)))
        await self.service.async_status({}, self.now)
        self.assertNotIn(old.local_date.isoformat(), self.service.days)
        self.assertEqual(MemoryStore.values[learning_key], {"runs": 113})

    async def test_transient_save_failure_recovers(self):
        self.publish(day(date(2026, 10, 9)))
        with patch.object(self.service.store, "async_save", AsyncMock(side_effect=OSError("test"))):
            result = await self.service.async_status({}, self.now)
            self.assertEqual(result["data_quality"], "storage_error")
            self.assertEqual(self.service.days, {})
        result = await self.service.async_status({}, self.now)
        self.assertIsNone(result["storage"]["error"])
        self.assertEqual(result["storage"]["day_count"], 1)

    async def test_explicit_export_excludes_future_and_has_unit_metadata(self):
        self.service.loaded = True
        today = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/London")).date()
        values = [day(today - timedelta(days=1)), day(today + timedelta(days=1))]
        self.service.days = {value.local_date.isoformat(): value for value in values}
        result = await self.service.async_export()
        self.assertEqual(result["price_unit"], "p_per_kwh")
        self.assertEqual(result["timezone"], "Europe/London")
        self.assertEqual(len(result["days"]), 1)
        self.assertEqual(result["days"][0]["date"], (today - timedelta(days=1)).isoformat())

    async def test_export_refuses_unhealthy_storage(self):
        self.service.loaded = True
        self.service.storage_error = "ValueError"
        with self.assertRaises(ValueError):
            await self.service.async_export()


if __name__ == "__main__":
    unittest.main()
