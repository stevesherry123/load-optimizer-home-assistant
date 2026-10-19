"""Effective graph prices use verified events, not browser calendar hints."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components/load_optimizer"))
from legacy import app_runtime as app


class PriceChartTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
        self.start = datetime(2026, 10, 20, 13, tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=1)
        self.periods = [{"start": self.start - timedelta(minutes=15),
                         "end": self.end + timedelta(minutes=15), "price_p_per_kwh": 30}]

    def chart(self, periods):
        return app.price_chart_data(periods, now=self.now, timezone_name="Europe/London")

    def test_future_power_up_has_exact_boundaries_and_preserves_contracted_source(self):
        before = deepcopy(self.periods)
        effective = app.overlay_free_windows(self.periods, [{"start": self.start, "end": self.end}])
        chart = self.chart(effective)
        self.assertEqual(chart["chart_price_status"], "ready")
        rows = chart["chart_price_periods"]
        self.assertEqual([row[2] for row in rows], [30, 0, 30])
        self.assertEqual(rows[1][:2], (self.start.timestamp() * 1000, self.end.timestamp() * 1000))
        self.assertEqual(self.periods, before)

    def test_free_calendar_does_not_fill_missing_tariff_prices(self):
        self.periods[0]["end"] = self.start
        rows = self.chart(app.overlay_free_windows(self.periods, [{"start": self.start, "end": self.end}]))["chart_price_periods"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], 30)
        self.assertEqual(self.chart([])["chart_price_status"], "no_prices")

    def test_tariff_day_bounds_handle_dst_and_clip_distant_rates(self):
        for day, hours in ((datetime(2026, 3, 29, 12, tzinfo=timezone.utc), 47),
                           (datetime(2026, 10, 25, 12, tzinfo=timezone.utc), 49)):
            start, end = app.price_chart_bounds(day, "Europe/London")
            self.assertEqual((end - start).total_seconds() / 3600, hours)
            chart = app.price_chart_data([{"start": start - timedelta(days=1),
                "end": end + timedelta(days=1), "price_p_per_kwh": -5}], now=day, timezone_name="Europe/London")
            self.assertEqual(chart["chart_price_periods"], [(start.timestamp() * 1000, end.timestamp() * 1000, -5)])

    def test_duplicate_rates_are_deduplicated_and_large_feeds_are_not_downsampled(self):
        self.assertEqual(len(self.chart(self.periods * 5)["chart_price_periods"]), 1)
        periods = [{"start": self.now + timedelta(minutes=i),
                    "end": self.now + timedelta(minutes=i + 1), "price_p_per_kwh": i} for i in range(257)]
        chart = self.chart(periods)
        self.assertEqual(chart["chart_price_status"], "too_many_periods")
        self.assertEqual(chart["chart_price_periods"], [])
        self.periods[0]["price_p_per_kwh"] = float("nan")
        self.assertEqual(self.chart(self.periods)["chart_price_status"], "invalid_price")

    def test_runtime_publishes_chart_before_learning_and_removes_cancelled_zero_price(self):
        config = app.instance_configs({"instances_yaml": json.dumps([{"id": "1", "power_sensor": "sensor.power"}]),
            "tariff_entity": "sensor.rates", "tariff_price_unit": "p_per_kwh", "free_window_entity": "calendar.free"})[0]
        sources = {"sensor.power": {"state": "0"}, "calendar.free": {"state": "off"},
                   "sensor.rates": {"state": "ready", "attributes": {"rates": [{
                       "start": self.periods[0]["start"].isoformat(), "end": self.periods[0]["end"].isoformat(),
                       "price": 30}]}}}
        event = {"start": self.start.isoformat(), "end": self.end.isoformat()}
        database = {"instances": {}}
        for events, prices in (([event], [30, 0, 30]), ([], [30]),
                               ([{**event, "status": "cancelled"}], [30]), (None, [30])):
            with self.subTest(events=events), patch.object(app, "source_state", side_effect=lambda _, key: sources.get(key)), \
                 patch.object(app, "api_request", return_value=events), patch.object(app, "publish_entity") as publish:
                app.update_instance("synthetic", database, config, now=self.now)
                attributes = next(call.args[3] for call in publish.call_args_list
                                  if call.args[1] == "sensor.load_optimizer_1_current_energy_price")
                self.assertEqual([row[2] for row in attributes["chart_price_periods"]], prices)
                self.assertEqual(attributes["chart_price_basis"], "effective_import_price")
        self.assertEqual(database["instances"]["1"].get("runs", 0), 0)

    def test_active_event_keeps_its_original_start_on_the_chart(self):
        self.now = self.start + timedelta(minutes=10)
        effective = app.overlay_free_windows(self.periods, [{"start": self.start, "end": self.end}])
        rows = self.chart(effective)["chart_price_periods"]
        self.assertEqual(rows[1][0], self.start.timestamp() * 1000)
        self.assertEqual(rows[1][2], 0)


class PriceChartJavascriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node") or os.environ.get("LOAD_OPTIMIZER_TEST_NODE")
        if not cls.node:
            if os.environ.get("CI"):
                raise RuntimeError("CI must run chart JavaScript acceptance with Node.js")
            raise unittest.SkipTest("Node.js is required for chart JavaScript acceptance (also run in CI)")
        dashboard = yaml.safe_load((ROOT / "homeassistant/dashboards/full/load_optimizer_dashboard.yaml").read_text())
        cls.chart = next(card for card in dashboard["views"][0]["sections"][0]["cards"]
                         if card.get("type") == "custom:apexcharts-card")
        cls.generator = cls.chart["series"][0]["data_generator"]

    def render(self, periods, *, browser_timezone="UTC", locale="server", raw=None):
        attributes = {} if periods is None else {"chart_price_periods": periods}
        script = "const input=JSON.parse(require('fs').readFileSync(0,'utf8')); global.window={}; "
        script += "const entity={attributes:input.attributes}; const hass={config:{time_zone:'Europe/London'},locale:{time_zone:input.locale},states:{'sensor.load_optimizer_1_cost_status':{attributes:{tariff_timezone:'Europe/London',tariff_entities:['event.rates']}},'event.rates':{attributes:{rates:input.raw}}}}; "
        script += "console.log(JSON.stringify(new Function('entity','hass',input.generator)(entity,hass)));"
        result = subprocess.run([self.node, "-e", script], input=json.dumps({"attributes": attributes,
            "generator": self.generator, "locale": locale, "raw": raw or []}), text=True, capture_output=True,
            env={**os.environ, "TZ": browser_timezone}, check=True)
        return json.loads(result.stdout)

    def test_zero_plateau_exact_end_recovery_gap_and_revision(self):
        start = 1792490400000
        periods = [[start, start + 900000, 30], [start + 900000, start + 4500000, 0],
                   [start + 4500000, start + 5400000, 40], [start + 7200000, start + 9000000, -5]]
        points = dict(self.render(periods))
        self.assertEqual(points[start + 900000], 0)
        self.assertEqual(points[start + 4500000], 40)
        self.assertIsNone(points[start + 5400001])
        revised = dict(self.render([[start, start + 5400000, 30]]))
        self.assertNotIn(0, [value for value in revised.values() if value is not None])

    def test_no_stale_fallback_but_older_integration_still_works(self):
        raw = [{"start": "2026-10-19T10:00:00Z", "end": "2026-10-19T10:30:00Z", "value_inc_vat": 0.3}]
        self.assertEqual(self.render([], raw=raw), [])
        self.assertEqual(self.render([[None, 5, 0]], raw=raw), [])
        self.assertEqual(self.render(None, raw=raw)[0][1], 30)

    def test_tariff_wall_time_when_browser_is_in_the_usa(self):
        start = datetime(2026, 10, 20, 13, tzinfo=timezone.utc).timestamp() * 1000
        periods = [[start, start + 3600000, 0]]
        server = self.render(periods, browser_timezone="America/New_York")
        local = self.render(periods, browser_timezone="America/New_York", locale="local")
        self.assertEqual(server[0][0], start)
        self.assertEqual(local[0][0], start + 5 * 3600000)
        self.assertEqual(local[0][1], 0)
