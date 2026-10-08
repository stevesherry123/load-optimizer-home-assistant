"""Tariff history and analysis acceptance tests, independent of Home Assistant."""

from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/optimizer/intelligence.py"
spec = importlib.util.spec_from_file_location("intelligence", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def day(value, prices=None):
    start, end = module.bounds(value, "Europe/London")
    slots = []
    while start < end:
        price = prices[len(slots) % len(prices)] if prices else 20.0
        slots.append(module.TariffSlot(start, start + timedelta(minutes=30), price))
        start += timedelta(minutes=30)
    return module.TariffDay(value, "Europe/London", tuple(slots), "test")


class IntelligenceTests(unittest.TestCase):
    def test_dst_complete_days(self):
        for value, count in ((date(2026, 3, 29), 46), (date(2026, 10, 25), 50), (date(2026, 10, 8), 48)):
            value = day(value)
            self.assertEqual(len(value.slots), count)
            self.assertTrue(module.complete(value))
            self.assertEqual(module.TariffDay.from_dict(value.as_dict()), value)

    def test_invalid_prices_and_times(self):
        start = datetime(2026, 10, 8, tzinfo=timezone.utc)
        for end, price in ((start, 20), (start + timedelta(minutes=30), float("nan")), (start + timedelta(minutes=30), float("inf"))):
            with self.assertRaises(ValueError):
                module.TariffSlot(start, end, price)
        with self.assertRaises(ValueError):
            module.utc("2026-10-08T00:00:00")

    def test_duplicates_overlaps_and_revisions(self):
        first = day(date(2026, 10, 8))
        values = [s.as_dict() for s in first.slots]
        self.assertEqual(len(module.normalize(values + values)), 48)
        revised = {**values[0], "price_p_per_kwh": 21}
        with self.assertRaises(ValueError):
            module.normalize(values + [revised])
        with self.assertRaises(ValueError):
            module.normalize(values + [{**values[0], "start": module.utc(values[0]["start"]) + timedelta(minutes=15)}])
        other = day(date(2026, 10, 8), [21])
        self.assertNotEqual(first.fingerprint, other.fingerprint)

    def test_incomplete_day_not_classified(self):
        target = day(date(2026, 10, 9))
        result = module.analyse(target.slots[:-1], [], now=module.utc("2026-10-08T12:00:00Z"), timezone_name="Europe/London", source="test")
        self.assertFalse(result["tomorrow_complete"])
        self.assertEqual(result["tomorrow_classification"], "waiting")

    def test_warmup_boundaries_and_future_exclusion(self):
        target = day(date(2026, 10, 9), [10])
        for count in (0, 3, 7, 13, 14):
            history = [day(date(2026, 10, 7) - timedelta(days=i), [20]) for i in range(count)]
            result = module.analyse(target.slots, history + [target], now=module.utc("2026-10-08T12:00:00Z"), timezone_name="Europe/London", source="test")
            self.assertEqual(result["history_days"], count)
            self.assertEqual(result["tomorrow_classification"], "cheap" if count == 14 else "warming_up")

    def test_future_windows_negative_prices_and_ties(self):
        target = day(date(2026, 10, 9), [-5])
        now = target.slots[0].start + timedelta(minutes=1)
        for hours in range(1, 5):
            result = module.cheapest_window(target.slots, hours, now)
            self.assertEqual(module.utc(result["start"]), target.slots[1].start)
            self.assertEqual(result["cost_at_1kw_pence"], -5 * hours)
        self.assertIsNone(module.cheapest_window(target.slots[:1] + target.slots[2:3], 1, target.slots[0].start))

    def test_round_trip_and_tamper_rejection(self):
        target = day(date(2026, 10, 9))
        value = target.as_dict()
        value["slots"][0]["price_p_per_kwh"] = 100
        with self.assertRaises(ValueError):
            module.TariffDay.from_dict(value)

    def test_shape_similarity_ignores_vertical_shift(self):
        prices = [10, 20, 30, 20]
        target = day(date(2026, 10, 9), [p + 3 for p in prices])
        past = [day(date(2026, 10, 7) - timedelta(days=i), prices) for i in range(14)]
        result = module.analyse(target.slots, past, now=module.utc("2026-10-08T12:00:00Z"), timezone_name="Europe/London", source="test")
        self.assertAlmostEqual(result["shape_similarity"], 1)
        self.assertAlmostEqual(result["raw_baseline_difference_p_per_kwh"], 3)

    def test_equal_prices_are_typical_not_expensive(self):
        target = day(date(2026, 10, 9))
        past = [day(date(2026, 10, 7) - timedelta(days=i)) for i in range(14)]
        result = module.analyse(target.slots, past, now=module.utc("2026-10-08T12:00:00Z"), timezone_name="Europe/London", source="test")
        self.assertEqual(result["tomorrow_classification"], "typical")
        self.assertEqual(result["recent_percentile"], 50)

    def test_old_history_cannot_satisfy_recent_warmup(self):
        target = day(date(2026, 10, 9))
        past = [day(date(2026, 1, 1) + timedelta(days=i)) for i in range(14)]
        result = module.analyse(target.slots, past, now=module.utc("2026-10-08T12:00:00Z"), timezone_name="Europe/London", source="test")
        self.assertEqual(result["history_days"], 0)


if __name__ == "__main__":
    unittest.main()
