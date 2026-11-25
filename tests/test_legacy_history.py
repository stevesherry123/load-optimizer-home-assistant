"""Verified legacy cache conversion, including DST and source protection."""

from datetime import date
from datetime import datetime, timezone
import ast
import asyncio
import json
from functools import partial
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import AsyncMock

import test_tariff_history as history_fixtures

from test_intelligence import day, module as core

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"
spec = importlib.util.spec_from_file_location("_tariff_test.optimizer.legacy_history", ROOT / "optimizer/legacy_history.py")
adapter = importlib.util.module_from_spec(spec)
package = ModuleType("_tariff_test")
package.__path__ = [str(ROOT)]
optimizer = ModuleType("_tariff_test.optimizer")
optimizer.__path__ = [str(ROOT / "optimizer")]
with patch.dict(sys.modules, {"_tariff_test": package, "_tariff_test.optimizer": optimizer,
                             "_tariff_test.optimizer.intelligence": core}):
    spec.loader.exec_module(adapter)


class LegacyHistoryTests(unittest.TestCase):
    def convert(self, records, **kwargs):
        args = {"history_tariff_code": "E-1R-AGILE-24-10-01-D",
                "target_tariff_code": "E-1R-AGILE-24-10-01-D", "source_id": "test-source",
                "now": core.utc("2026-10-08T12:00:00Z")}
        args.update(kwargs)
        return adapter.adapt_agile_buddy(records, **args)

    def records(self, date_value=date(2026, 10, 7)):
        return [{"dt": s.end.isoformat(), "r": s.price} for s in day(date_value, [-1.25]).slots]

    def test_period_end_conversion_and_negative_prices(self):
        payload, report = self.convert(self.records())
        self.assertEqual(report["complete_days"], 1)
        self.assertEqual(payload["source_id"], "test-source")
        self.assertEqual(core.utc(payload["days"][0]["slots"][0]["start"]), core.utc("2026-10-06T23:00:00Z"))
        self.assertEqual(payload["days"][0]["slots"][0]["price_p_per_kwh"], -1.25)

    def test_different_region_product_or_unverified_tariff_rejected(self):
        for code in (None, "North Western England", "E-1R-AGILE-24-10-01-G", "E-1R-AGILE-22-07-22-D"):
            with self.assertRaises(ValueError):
                self.convert(self.records(), history_tariff_code=code)

    def test_invalid_prices_timestamps_and_conflicting_duplicates_rejected(self):
        for record in ({"dt": "2026-10-07T00:30:00Z", "r": True},
                       {"dt": "2026-10-07T00:30:00Z", "r": float("nan")},
                       {"dt": "2026-10-07T00:30:00", "r": 1},
                       {"dt": "2026-10-07T00:31:00Z", "r": 1}):
            with self.assertRaises(ValueError):
                self.convert([record])
        records = self.records()
        records.append({**records[0], "r": 20})
        with self.assertRaises(ValueError):
            self.convert(records)

    def test_incomplete_days_reported_not_filled(self):
        payload, report = self.convert(self.records()[:-1])
        self.assertEqual(payload["days"], [])
        self.assertEqual(report["incomplete_days"], 1)

    def test_old_data_cannot_satisfy_recent_warmup(self):
        payload, report = self.convert(self.records(date(2026, 6, 24)))
        self.assertEqual(payload["days"], [])
        self.assertEqual(report["outside_retention_days"], 1)

    def test_dst_days_use_local_boundaries(self):
        for date_value, count in ((date(2026, 3, 29), 46), (date(2026, 10, 25), 50)):
            payload, report = self.convert(self.records(date_value),
                now=core.utc("2026-10-28T12:00:00Z"), retention_days=365)
            self.assertEqual(report["complete_days"], 1)
            self.assertEqual(len(payload["days"][0]["slots"]), count)


class LegacyImportServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_service_dry_run_checks_live_tariff_before_writing(self):
        fixture = history_fixtures.TariffHistoryTests()
        fixture.setUp()
        fixture.publish(day(date(2026, 10, 7)))
        fixture.states["sensor.rates"].attributes["tariff_code"] = "E-1R-AGILE-24-10-01-D"
        coordinator = SimpleNamespace(tariff_intelligence=fixture.service, async_request_refresh=AsyncMock())
        async def executor(function, *args):
            return await asyncio.to_thread(function, *args)
        fixture.hass.async_add_executor_job = executor
        tree = ast.parse((ROOT / "__init__.py").read_text())
        handler = next(node for node in ast.walk(tree)
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_import_tariff_history")
        authorization = next(node for node in ast.walk(tree)
                             if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_check_admin")
        namespace = {"hass": fixture.hass, "tariff_coordinator": lambda entry: coordinator,
                     "json": json, "partial": partial, "datetime": datetime, "timezone": timezone,
                     "adapt_agile_buddy": adapter.adapt_agile_buddy, "ServiceValidationError": ValueError}
        exec(compile(ast.Module(body=[authorization, handler], type_ignores=[]), "<actual-service-handler>", "exec"), namespace)
        records = [{"dt": slot.end.isoformat(), "r": slot.price} for slot in day(date(2026, 10, 7)).slots]
        data = {"entry_id": "test", "history_json": json.dumps(records), "format": "agile_buddy",
                "history_tariff_code": "E-1R-AGILE-24-10-01-D", "retention_days": 365,
                "dry_run": True, "overwrite_live": False}
        call = SimpleNamespace(data=data, context=SimpleNamespace(user_id=None))
        result = await namespace[handler.name](call)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["conversion"]["complete_days"], 1)
        self.assertEqual(history_fixtures.MemoryStore.writes, 0)
        data["history_tariff_code"] = "E-1R-AGILE-24-10-01-G"
        data["dry_run"] = False
        with self.assertRaises(ValueError):
            await namespace[handler.name](call)
        self.assertEqual(history_fixtures.MemoryStore.writes, 0)
        coordinator.async_request_refresh.assert_not_called()
