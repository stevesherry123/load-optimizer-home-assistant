"""Published-horizon acceptance without weakening completed history validation."""

from datetime import date, datetime, timedelta
import unittest
from zoneinfo import ZoneInfo

from test_intelligence import day, module as core


class ForecastCoverageTests(unittest.TestCase):
    def analyse(self, target, history=(), now=None):
        return core.analyse(target.slots, list(history),
                            now=now or core.bounds(target.local_date - timedelta(days=1), "Europe/London")[0],
                            timezone_name="Europe/London", source="test")

    def history(self, target_date, prices=None):
        return [day(target_date - timedelta(days=i + 2), prices) for i in range(14)]

    def partial(self, target_date=date(2026, 10, 15), count=46, prices=None):
        value = day(target_date, prices)
        return core.TariffDay(value.local_date, value.timezone_name, value.slots[:count], value.source)

    def test_normal_trailing_hour_is_usable_not_complete_or_storable(self):
        target = self.partial()
        result = self.analyse(target)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["forecast_usable"])
        self.assertFalse(result["tomorrow_complete"])
        self.assertEqual(result["forecast_coverage"]["known_minutes"], 1380)
        self.assertEqual(result["forecast_coverage"]["trailing_missing_minutes"], 60)
        self.assertEqual(result["analysis_scope"], "published_hours")
        self.assertEqual(result["time_band_coverage"]["evening"], "complete")
        self.assertEqual(result["time_band_coverage"]["late"], "partial")
        self.assertIn("00:00-23:00", result["summary"])
        self.assertIn("remaining prices are not yet published", result["summary"])
        with self.assertRaises(ValueError):
            core.TariffDay.from_dict(target.as_dict())

    def test_readiness_is_semantic_coverage_not_slot_count(self):
        for count, usable in ((1, False), (37, False), (38, True), (46, True), (47, True), (48, True)):
            with self.subTest(count=count):
                result = self.analyse(self.partial(count=count))
                self.assertEqual(result["forecast_usable"], usable)
        full = day(date(2026, 10, 15))
        two_slots = core.TariffDay(full.local_date, full.timezone_name, (
            core.TariffSlot(full.slots[0].start, full.slots[37].end, 20),
            core.TariffSlot(full.slots[38].start, full.slots[45].end, 20)), "test")
        self.assertTrue(self.analyse(two_slots)["forecast_usable"])

    def test_missing_prefix_and_internal_hole_are_not_unpublished_tail(self):
        full = day(date(2026, 10, 15))
        for slots in (full.slots[1:], full.slots[:20] + full.slots[21:]):
            target = core.TariffDay(full.local_date, full.timezone_name, slots, "test")
            result = self.analyse(target)
            self.assertFalse(result["forecast_usable"])
            self.assertEqual(result["tomorrow_classification"], "waiting")
        missing = core.forecast_coverage(None, full.local_date, full.timezone_name)
        self.assertEqual(missing["status"], "missing")
        self.assertEqual(missing["known_minutes"], 0)

    def test_same_hours_comparison_excludes_expensive_unpublished_tail(self):
        target = self.partial(prices=[20])
        history = self.history(target.local_date, [20] * 46 + [100] * 2)
        result = self.analyse(target, history)
        self.assertEqual(result["tomorrow_classification"], "typical")
        self.assertEqual(result["recent_percentile"], 50)
        self.assertEqual(result["recent_average_p_per_kwh"], 20)
        self.assertEqual(result["raw_baseline_difference_p_per_kwh"], 0)
        self.assertNotIn("23:00", result["matching_half_hour_baseline"])

    def test_irregular_tail_uses_exact_matching_minutes_not_full_half_hour(self):
        full = day(date(2026, 10, 15))
        last = full.slots[-2]
        target = core.TariffDay(full.local_date, full.timezone_name,
            full.slots[:-2] + (core.TariffSlot(last.start, last.start + timedelta(minutes=15), 20),), "test")
        history = []
        for value in self.history(full.local_date):
            last = value.slots[-2]
            slots = value.slots[:-2] + (
                core.TariffSlot(last.start, last.start + timedelta(minutes=15), 20),
                core.TariffSlot(last.start + timedelta(minutes=15), value.slots[-1].end, 100))
            history.append(core.TariffDay(value.local_date, value.timezone_name, slots, "test"))
        result = self.analyse(target, history)
        self.assertEqual(result["recent_average_p_per_kwh"], 20)
        self.assertEqual(result["matching_half_hour_baseline"]["23:00"], 20)
        self.assertEqual(result["raw_baseline_difference_p_per_kwh"], 0)

    def test_time_bands_clip_prices_crossing_band_boundary(self):
        value = day(date(2026, 10, 15))
        start, end = core.bounds(value.local_date, value.timezone_name)
        split = start + timedelta(hours=8)
        target = core.TariffDay(value.local_date, value.timezone_name, (
            core.TariffSlot(start, split, 30), core.TariffSlot(split, end, 20)), "test")
        result = self.analyse(target)
        self.assertEqual(result["time_bands"]["overnight"], 30)
        self.assertAlmostEqual(result["time_bands"]["morning"], 23.333333)
        self.assertEqual(set(result["time_band_coverage"].values()), {"complete"})

    def test_dst_is_derived_from_local_bounds(self):
        for target_date, count, minutes in ((date(2026, 3, 29), 46, 1380),
                                             (date(2026, 10, 25), 50, 1500)):
            with self.subTest(date=target_date):
                target = day(target_date)
                result = self.analyse(target)
                self.assertEqual(len(target.slots), count)
                self.assertTrue(result["tomorrow_complete"])
                self.assertEqual(result["forecast_coverage"]["expected_minutes"], minutes)
                partial = core.TariffDay(target_date, target.timezone_name, target.slots[:-2], "test")
                result = self.analyse(partial)
                self.assertTrue(result["forecast_usable"])
                self.assertFalse(result["tomorrow_complete"])
                self.assertEqual(result["forecast_coverage"]["trailing_missing_minutes"], 60)

    def test_repeated_dst_hours_use_target_weights_and_one_reference_per_day(self):
        zone = ZoneInfo("Europe/London")
        target = day(date(2026, 10, 25))
        def morning_prices(value):
            return core.TariffDay(value.local_date, value.timezone_name,
                tuple(core.TariffSlot(s.start, s.end, 40 if s.start.astimezone(zone).hour == 1 else 20)
                      for s in value.slots), "test")
        target = morning_prices(target)
        result = self.analyse(target, [morning_prices(value) for value in self.history(target.local_date)])
        self.assertEqual(result["tomorrow_statistics"]["mean"], 21.6)
        self.assertAlmostEqual(result["recent_average_p_per_kwh"], 21.6)
        self.assertEqual(result["tomorrow_classification"], "typical")

    def test_missing_historical_dst_hour_cannot_fake_comparison_coverage(self):
        target = self.partial(date(2026, 4, 1))
        result = self.analyse(target, self.history(target.local_date))
        self.assertEqual(result["history_days"], 14)
        self.assertEqual(result["comparison_days"], 13)
        self.assertEqual(result["baseline_status"], "warming_up")
        self.assertEqual(result["tomorrow_classification"], "warming_up")

    def test_other_sources_or_timezones_cannot_satisfy_warmup(self):
        target = self.partial()
        history = [core.TariffDay(d.local_date, d.timezone_name, d.slots, "other-source")
                   for d in self.history(target.local_date)]
        self.assertEqual(self.analyse(target, history)["history_days"], 0)

    def test_added_tail_and_equal_statistics_revision_change_rates_fingerprint(self):
        target = self.partial(prices=[10, 20])
        first = self.analyse(target)
        revised = self.partial(prices=[20, 10])
        second = self.analyse(revised)
        self.assertEqual(first["tomorrow_statistics"], second["tomorrow_statistics"])
        self.assertNotEqual(first["forecast_fingerprint"], second["forecast_fingerprint"])
        full = self.analyse(day(target.local_date, [10, 20]))
        self.assertTrue(full["tomorrow_complete"])
        self.assertEqual(full["time_band_coverage"]["late"], "complete")
        self.assertNotEqual(first["forecast_fingerprint"], full["forecast_fingerprint"])

    def test_target_date_is_tariff_local_before_after_midnight_and_publication(self):
        target = self.partial()
        instant = core.utc("2026-10-14T15:00:00Z")
        self.assertEqual(self.analyse(target, now=instant)["tomorrow_date"], "2026-10-15")
        self.assertEqual(self.analyse(target, now=instant.astimezone(ZoneInfo("America/New_York")))["tomorrow_date"], "2026-10-15")
        for now in (instant - timedelta(minutes=1), instant + timedelta(minutes=1)):
            self.assertTrue(self.analyse(target, now=now)["forecast_usable"])
        slots = target.slots + day(date(2026, 10, 16)).slots
        result = core.analyse(slots, [], now=core.utc("2026-10-14T23:01:00Z"),
                              timezone_name="Europe/London", source="test")
        self.assertEqual(result["tomorrow_date"], "2026-10-16")
        self.assertTrue(result["tomorrow_complete"])

    def test_generic_window_cannot_cross_unknown_tail_or_gap(self):
        target = self.partial(prices=[-5])
        now = target.slots[-2].start
        result = self.analyse(target, now=now)
        self.assertIsNone(result["windows"]["2"])
        self.assertEqual(result["window_scope"], "known_future_prices")
        self.assertIsNone(core.cheapest_window(target.slots[-2:-1] +
                          (core.TariffSlot(target.slots[-1].end, target.slots[-1].end + timedelta(minutes=30), -5),),
                          1, now))


if __name__ == "__main__":
    unittest.main()
