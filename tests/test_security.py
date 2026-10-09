"""Dependency-free regressions for hostile imports and planner inputs."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"))
from optimizer import state_import, tariffs
from optimizer.ev_charging import plan_ev_charge
from legacy import costing


class StateImportTests(unittest.TestCase):
    def test_valid_memory_is_detached_and_preserves_learning(self):
        source = {"instances": {"1": {"runs": 114, "program_models": {"MixedLoad": {"runs": 4}}}}}
        result = state_import.validate_import(source)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["instances"], source["instances"])
        result["instances"]["1"]["runs"] = 0
        self.assertEqual(source["instances"]["1"]["runs"], 114)

    def test_bad_shapes_versions_and_counts_are_rejected(self):
        invalid = [[], {}, {"instances": []}, {"instances": {"1": None}},
                   {"instances": {}, "schema_version": 2}, {"instances": {}, "schema_version": True},
                   {"instances": {"sensor.bad": {}}}]
        invalid += [{"instances": {"1": item}} for item in (
            {"runs": -1}, {"runs": True}, {"runs": "4"}, {"program_models": []},
            {"program_models": {"Eco": None}}, {"last_cycle": []}, {"profile": {}},
            {"samples": []}, {"program_models": {"Eco": {"runs": -1}}},
        )]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                state_import.validate_import(payload)

    def test_nonfinite_and_deep_json_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                state_import.validate_import(json.dumps({"instances": {}, "extra": value}))
        nested = "x"
        for _ in range(34):
            nested = [nested]
        with self.assertRaises(ValueError):
            state_import.validate_import({"instances": {}, "extra": nested})

    def test_size_limit_checks_utf8_bytes_as_well_as_characters(self):
        with patch.object(state_import, "MAX_STATE_BYTES", 64):
            for payload in (" " * 65, json.dumps({"instances": {}, "note": chr(233) * 30}, ensure_ascii=False)):
                with self.assertRaises(ValueError):
                    state_import.validate_import(payload)


class PlannerBoundaryTests(unittest.TestCase):
    def test_both_planners_reject_unsafe_intervals_and_horizons(self):
        now = datetime.now(timezone.utc)
        for module in (costing, tariffs):
            for value in (0, -1, float("nan"), float("inf"), 0.00001, 61, True):
                with self.subTest(module=module.__name__, interval=value), self.assertRaises(ValueError):
                    module.recommend_cycle([], [], [], reference_utc=now, search_hours=24,
                                           candidate_interval_minutes=value)
                with self.assertRaises(ValueError):
                    module.recommend_cycle([], [], [], reference_utc=now, search_hours=24,
                                           candidate_interval_minutes=5, forecast_interval_minutes=value)
            for value in (-1, 73, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    module.recommend_cycle([], [], [], reference_utc=now, search_hours=value,
                                           candidate_interval_minutes=5)

    def test_tariff_prices_and_period_durations_must_be_valid(self):
        rate = {"start": "2026-10-09T00:00:00Z", "end": "2026-10-09T00:30:00Z", "price": 12}
        for module in (costing, tariffs):
            for override in ({"price": "NaN"}, {"price": "Infinity"}, {"end": rate["start"]}):
                with self.assertRaises(ValueError):
                    module.parse_structured_rates([{**rate, **override}], price_unit="p_per_kwh")

    def test_ev_rejects_nonfinite_inputs_and_bounds_large_tariff_intervals(self):
        now = datetime(2026, 10, 9, tzinfo=timezone.utc)
        values = {"periods": [{"start": now, "end": now + timedelta(days=365), "price_p_per_kwh": 10}],
                  "battery_percent": 40, "battery_capacity_kwh": 60, "charge_power_kw": 7,
                  "reference_utc": now}
        for key in ("battery_capacity_kwh", "charge_power_kw", "slot_minutes"):
            with self.subTest(key=key):
                self.assertEqual(plan_ev_charge(**{**values, key: float("nan")})["status"], "not_ready")
        for key, value in (("battery_capacity_kwh", 1e308), ("charge_power_kw", 1e-308),
                           ("charger_efficiency", 1e-308)):
            self.assertEqual(plan_ev_charge(**{**values, key: value})["status"], "not_ready")
        self.assertLessEqual(plan_ev_charge(**values)["slots_available"], 7 * 48)

    def test_duplicated_tariff_engines_remain_identical(self):
        root = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"
        self.assertEqual((root / "legacy/costing.py").read_bytes(), (root / "optimizer/tariffs.py").read_bytes())
