"""Free calendars override only covered tariff intervals, never cached hints."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from legacy import app_runtime as app


class PowerUpTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 18, 13, tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=1)
        self.state = {"state": "off", "attributes": {}}
        self.events = [{"start": {"dateTime": self.start.isoformat()}, "end": {"dateTime": self.end.isoformat()}}]

    def read(self, sources="calendar.free"):
        return app.free_windows_from_entity("synthetic", sources, start=self.start - timedelta(hours=1), end=self.end,
                                            state_reader=lambda _: self.state, calendar_reader=lambda _: self.events)

    def test_explicit_calendar_and_utc_offsets(self):
        self.events[0]["start"]["dateTime"] = "2026-10-18T14:00:00+01:00"
        windows, diagnostic = self.read()
        self.assertTrue(diagnostic["readable"])
        self.assertEqual(windows[0]["start"], self.start)

    def test_empty_or_cancelled_calendar_does_not_use_stale_current_event(self):
        self.state["attributes"] = {"start_time": self.start.isoformat(), "end_time": self.end.isoformat()}
        for events in ([], [{**self.events[0], "status": "cancelled"}]):
            self.events = events
            windows, diagnostic = self.read()
            self.assertTrue(diagnostic["readable"])
            self.assertEqual(windows, [])

    def test_unavailable_or_malformed_data_cannot_grant_zero_prices(self):
        for events in (None, {}, [{"start": "nonsense", "end": self.end.isoformat()}], [None],
                       [{"start": "2026-10-18T13:00:00", "end": self.end.isoformat()}],
                       [{"start": {"date": "2026-10-18"}, "end": {"date": "2026-10-19"}}]):
            self.events = events
            windows, diagnostic = self.read()
            self.assertFalse(diagnostic["readable"])
            self.assertEqual(windows, [])
        self.state["state"] = "unavailable"
        self.assertFalse(self.read()[1]["readable"])
        self.assertFalse(self.read("event.free")[1]["readable"])

    def test_failure_of_any_configured_calendar_invalidates_combined_free_windows(self):
        windows, diagnostic = app.free_windows_from_entity("synthetic", "calendar.good,calendar.failed",
            start=self.start, end=self.end, state_reader=lambda _: self.state,
            calendar_reader=lambda entity: self.events if entity == "calendar.good" else None)
        self.assertEqual(windows, [])
        self.assertFalse(diagnostic["readable"])

    def test_overlay_clips_splits_and_preserves_source(self):
        original = [{"start": self.start - timedelta(minutes=15), "end": self.end + timedelta(minutes=15), "price_p_per_kwh": 30}]
        before = deepcopy(original)
        windows = self.read()[0]
        result = app.overlay_free_windows(original, windows)
        self.assertEqual(original, before)
        self.assertEqual([row["price_p_per_kwh"] for row in result], [30, 0, 30])
        self.assertEqual(result[1]["contracted_price_p_per_kwh"], 30)
        self.assertEqual(result[1]["source"], "free_electricity_calendar")
        self.assertEqual(result[1]["start"], self.start)
        self.assertEqual(result[1]["end"], self.end)
        self.assertEqual(app.overlay_free_windows(result, windows), result)

    def test_overlay_never_creates_tariff_coverage_or_bridges_holes(self):
        periods = [{"start": self.start, "end": self.start + timedelta(minutes=15), "price_p_per_kwh": 30},
                   {"start": self.end - timedelta(minutes=15), "end": self.end, "price_p_per_kwh": 40}]
        result = app.overlay_free_windows(periods, self.read()[0])
        self.assertEqual(len(result), 2)
        self.assertLess(result[0]["end"], result[1]["start"])
        self.assertEqual(app.overlay_free_windows([], self.read()[0]), [])

    def test_explicit_manual_price_is_applied_after_calendar(self):
        periods = [{"start": self.start, "end": self.end, "price_p_per_kwh": 30}]
        result = app.overlay_free_windows(periods, self.read()[0])
        result = app.overlay_price_window(result, start=self.start, end=self.end, price_p_per_kwh=-2)
        self.assertEqual(result[0]["price_p_per_kwh"], -2)
