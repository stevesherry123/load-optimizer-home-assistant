"""Import dry runs, atomic validation and provenance protection."""

import copy
from datetime import date
import unittest
from unittest.mock import AsyncMock, patch

import test_tariff_history as history_fixtures
from test_intelligence import module as core, day

MemoryStore = history_fixtures.MemoryStore


class HistoryImportTests(unittest.IsolatedAsyncioTestCase):
    setUp = history_fixtures.TariffHistoryTests.setUp
    publish = history_fixtures.TariffHistoryTests.publish

    def payload(self, prices=None):
        value = day(date(2026, 10, 7), prices)
        return {"schema": 1, "timezone": "Europe/London", "price_unit": "p_per_kwh",
                "source_id": self.service.source_id,
                "days": [{"date": "2026-10-07", "slots": [slot.as_dict() for slot in value.slots]}]}

    async def test_dry_run_then_atomic_import_then_idempotent_retry(self):
        payload = self.payload()
        result = await self.service.async_import(payload, now=self.now)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(self.service.days, {})
        self.assertEqual(MemoryStore.writes, 0)
        await self.service.async_import(payload, dry_run=False, now=self.now)
        self.assertEqual(MemoryStore.writes, 1)
        result = await self.service.async_import(payload, dry_run=False, now=self.now)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(MemoryStore.writes, 1)

    async def test_live_day_requires_explicit_override(self):
        value = day(date(2026, 10, 7))
        value = core.TariffDay(value.local_date, value.timezone_name, value.slots, self.service.source_id)
        self.service.days = {"2026-10-07": value}
        self.service.loaded = True
        result = await self.service.async_import(self.payload([25]), dry_run=False, now=self.now)
        self.assertEqual(result["blocked_live"], 1)
        self.assertEqual(MemoryStore.writes, 0)
        result = await self.service.async_import(self.payload([25]), dry_run=False, overwrite_live=True, now=self.now)
        self.assertEqual(result["replaced"], 1)
        self.assertEqual(self.service.origins["2026-10-07"], "import")

    async def test_malformed_row_cannot_partially_write(self):
        payload = self.payload()
        payload["days"].append({"date": "2026-10-06", "slots": []})
        with self.assertRaises(ValueError):
            await self.service.async_import(payload, dry_run=False, now=self.now)
        self.assertEqual(self.service.days, {})
        self.assertEqual(MemoryStore.writes, 0)

    async def test_wrong_units_timezone_duplicates_nan_and_boolean_rejected(self):
        payloads = [self.payload() for _ in range(5)]
        payloads[0]["price_unit"] = "gbp_per_kwh"
        payloads[1]["timezone"] = "America/New_York"
        payloads[2]["days"].append(copy.deepcopy(payloads[2]["days"][0]))
        payloads[3]["days"][0]["slots"][0]["price_p_per_kwh"] = float("nan")
        payloads[4]["days"][0]["slots"][0]["price_p_per_kwh"] = True
        for payload in payloads:
            with self.assertRaises(ValueError):
                await self.service.async_import(payload, dry_run=False, now=self.now)
        self.assertEqual(MemoryStore.writes, 0)

    async def test_failed_save_preserves_memory(self):
        with patch.object(self.service.store, "async_save", AsyncMock(side_effect=OSError("test"))):
            with self.assertRaises(OSError):
                await self.service.async_import(self.payload(), dry_run=False, now=self.now)
        self.assertEqual(self.service.days, {})

    async def test_future_day_is_not_imported(self):
        payload = self.payload()
        value = day(date(2026, 10, 9))
        payload["days"] = [{"date": "2026-10-09", "slots": [slot.as_dict() for slot in value.slots]}]
        result = await self.service.async_import(payload, dry_run=False, now=self.now)
        self.assertEqual(result["outside_retention"], 1)
        self.assertEqual(MemoryStore.writes, 0)

    async def test_live_capture_supersedes_import_provenance(self):
        payload = self.payload()
        await self.service.async_import(payload, dry_run=False, now=self.now)
        self.publish(day(date(2026, 10, 7)))
        await self.service.async_status({}, self.now)
        self.assertEqual(self.service.origins["2026-10-07"], "live")

    async def test_missing_or_mismatched_source_rejected_even_with_override(self):
        for source in (None, "another-tariff-region"):
            payload = self.payload()
            payload["source_id"] = source
            for dry_run in (True, False):
                with self.assertRaises(ValueError):
                    await self.service.async_import(payload, dry_run=dry_run,
                                                    overwrite_live=True, now=self.now)
        self.assertEqual(self.service.days, {})
        self.assertEqual(MemoryStore.writes, 0)

    async def test_export_preserves_source_for_reimport(self):
        await self.service.async_import(self.payload(), dry_run=False, now=self.now)
        payload = await self.service.async_export(365)
        self.assertEqual(payload["source_id"], self.service.source_id)
        self.assertEqual(len(payload["days"]), 1)
        result = await self.service.async_import(payload, now=self.now)
        self.assertEqual(result["skipped"], 1)

    async def test_rollback_writer_cannot_erase_import_provenance(self):
        await self.service.async_import(self.payload(), dry_run=False, now=self.now)
        imported = copy.deepcopy(MemoryStore.values[self.service.store.key])
        # The old release can only write its original key, without origins.
        live = day(date(2026, 10, 9))
        live = core.TariffDay(live.local_date, live.timezone_name, live.slots, self.service.source_id)
        await self.service.legacy_store.async_save({"schema": 1, "days": {"2026-10-09": live.as_dict()}})
        fresh = history_fixtures.manager.TariffIntelligence(
            self.hass, self.service.source_id, ["sensor.rates"], "Europe/London", "p_per_kwh")
        await fresh.async_load()
        self.assertEqual(fresh.origins["2026-10-07"], "import")
        self.assertEqual(MemoryStore.values[fresh.store.key], imported)
        result = await fresh.async_import(self.payload([25]), dry_run=False, now=self.now)
        self.assertEqual(result["replaced"], 1)

    async def test_schema_one_migrates_without_changing_original(self):
        value = day(date(2026, 10, 7))
        value = core.TariffDay(value.local_date, value.timezone_name, value.slots, self.service.source_id)
        for origin in ("live", "import"):
            test_payload = {"schema": 1, "days": {"2026-10-07": value.as_dict()}}
            if origin == "import":
                test_payload["origins"] = {"2026-10-07": "import"}
            MemoryStore.values = {self.service.legacy_store.key: copy.deepcopy(test_payload)}
            fresh = history_fixtures.manager.TariffIntelligence(
                self.hass, self.service.source_id, ["sensor.rates"], "Europe/London", "p_per_kwh")
            await fresh.async_load()
            self.assertEqual(fresh.origins["2026-10-07"], origin)
            self.assertEqual(MemoryStore.values[fresh.store.key]["schema"], 2)
            self.assertEqual(MemoryStore.values[fresh.legacy_store.key], test_payload)

    async def test_failed_migration_preserves_original_and_disables_writes(self):
        value = day(date(2026, 10, 7))
        value = core.TariffDay(value.local_date, value.timezone_name, value.slots, self.service.source_id)
        payload = {"schema": 1, "days": {"2026-10-07": value.as_dict()}}
        MemoryStore.values[self.service.legacy_store.key] = copy.deepcopy(payload)
        with patch.object(self.service.store, "async_save", AsyncMock(side_effect=OSError("test"))):
            await self.service.async_load()
        self.assertTrue(self.service.read_only)
        self.assertEqual(self.service.days, {})
        self.assertEqual(MemoryStore.values[self.service.legacy_store.key], payload)

    async def test_missing_v2_provenance_is_not_silently_labelled_live(self):
        await self.service.async_import(self.payload(), dry_run=False, now=self.now)
        payload = MemoryStore.values[self.service.store.key]
        payload.pop("origins")
        original = copy.deepcopy(payload)
        fresh = history_fixtures.manager.TariffIntelligence(
            self.hass, self.service.source_id, ["sensor.rates"], "Europe/London", "p_per_kwh")
        await fresh.async_load()
        self.assertTrue(fresh.read_only)
        self.assertEqual(fresh.days, {})
        self.assertEqual(MemoryStore.values[fresh.store.key], original)
