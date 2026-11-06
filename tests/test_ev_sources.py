"""EV sources preserve actual coverage and reject conflicting forecasts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from optimizer.ev_sources import ev_tariff_periods


class EVSourceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 4, 21, tzinfo=timezone.utc)

    def source(self, offset=0, price=0.25):
        start = self.now + timedelta(minutes=offset)
        return {"state": self.now.isoformat(), "attributes": {"rates": [
            {"start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat(),
             "value_inc_vat": price}]}}

    def plan(self, *sources):
        return ev_tariff_periods(sources, reference_utc=self.now,
                                 timezone_name="Europe/London", price_unit="gbp_per_kwh")

    def test_current_price_only_sensor_is_not_a_forecast(self):
        with self.assertRaisesRegex(ValueError, "future prices"):
            self.plan({"state": "0.25", "attributes": {"start": self.now.isoformat(),
                                                        "end": (self.now + timedelta(minutes=30)).isoformat()}})

    def test_today_survives_unpublished_tomorrow_without_filling_the_gap(self):
        periods, issues = self.plan(self.source(), {"state": self.now.isoformat(), "attributes": {"rates": []}})
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]["price_p_per_kwh"], 25)
        self.assertEqual(len(issues), 1)

    def test_sources_combine_deduplicate_and_keep_real_gaps(self):
        periods, issues = self.plan(self.source(), self.source(), self.source(60, -0.1))
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[1]["price_p_per_kwh"], -10)
        self.assertEqual(periods[1]["start"] - periods[0]["end"], timedelta(minutes=30))
        self.assertFalse(issues)

    def test_conflicting_sources_never_pick_an_arbitrary_winner(self):
        for offset in (0, 15):
            with self.assertRaisesRegex(ValueError, "overlapping"):
                self.plan(self.source(), self.source(offset, 0.3))

    def test_unavailable_cached_prices_and_expired_slots_are_not_used(self):
        cached = {**self.source(), "state": "unavailable"}
        with self.assertRaisesRegex(ValueError, "future prices"):
            self.plan(cached, self.source(-30))
        periods, issues = self.plan(cached, self.source(30))
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]["start"], self.now + timedelta(minutes=30))
        self.assertEqual(len(issues), 1)
