import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from load_optimizer.app.main import (
    bootstrap_program_models,
    load_state,
    normalise_profile,
    normalise_program,
    profile_sample,
    program_summary,
    save_state,
    update_instance,
    update_program_model,
)


class StateStorageTests(unittest.TestCase):
    def test_missing_state_returns_empty_versioned_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            self.assertEqual(
                load_state(path),
                {"schema_version": 1, "instances": {}},
            )

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            expected = {
                "schema_version": 1,
                "instances": {"1": {"name": "Dishwasher 1"}},
            }
            save_state(expected, path)
            self.assertEqual(json.loads(path.read_text()), expected)
            self.assertEqual(load_state(path), expected)


class InstanceMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "name": "Dishwasher 1",
            "power_sensor": "sensor.test_power",
            "energy_sensor": "sensor.test_energy",
            "program_sensor": "sensor.test_program",
            "state_sensor": "",
            "active_power_threshold": 10,
            "finish_delay": 2,
        }

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_active_power_starts_cycle(self, source, _publish):
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": "1200"},
            "sensor.test_energy": {"state": "3.5"},
            "sensor.test_program": {"state": "Eco"},
        }.get(entity_id)
        database = {"schema_version": 1, "instances": {}}

        update_instance("token", database, self.config, datetime(2026, 1, 1, tzinfo=timezone.utc))

        instance = database["instances"]["1"]
        self.assertEqual(instance["program"], "Eco")
        self.assertEqual(instance["peak_power"], 1200)
        self.assertEqual(instance["samples"], 1)

    def test_bosch_program_name_is_normalised(self):
        self.assertEqual(
            normalise_program("Dishcare.Dishwasher.Program.PreRinse"),
            "PreRinse",
        )

    def test_profile_sample_uses_cycle_relative_time(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(
            profile_sample(start, start + timedelta(seconds=90), 68.2345, 1.1234567),
            {"offset_seconds": 90, "power_w": 68.234, "energy_kwh": 1.123457},
        )

    def test_profile_is_interpolated_into_fixed_bins(self):
        profile = [
            {"offset_seconds": 0, "power_w": 0},
            {"offset_seconds": 10, "power_w": 100},
        ]
        self.assertEqual(normalise_profile(profile, bins=5), [0.0, 25.0, 50.0, 75.0, 100.0])

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_sustained_low_power_finishes_cycle(self, source, _publish):
        self.config["finish_delay"] = 5
        readings = {"power": "0", "energy": "4.1", "program": "Eco"}
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": readings["power"]},
            "sensor.test_energy": {"state": readings["energy"]},
            "sensor.test_program": {"state": readings["program"]},
        }.get(entity_id)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        database = {"schema_version": 1, "instances": {"1": {
            "cycle_start": start.isoformat(), "start_energy": 3.5,
            "peak_power": 1200, "samples": 10,
            "profile": [{"offset_seconds": minute * 60, "power_w": 1200} for minute in range(10)],
            "below_threshold": 0,
            "program": "Eco",
        }}}

        update_instance("token", database, self.config, start + timedelta(minutes=59))
        readings["energy"] = "4.2"
        for minute in range(60, 64):
            update_instance("token", database, self.config, start + timedelta(minutes=minute))

        instance = database["instances"]["1"]
        self.assertNotIn("cycle_start", instance)
        self.assertEqual(instance["runs"], 1)
        self.assertEqual(instance["last_cycle"]["runtime_minutes"], 59.0)
        self.assertEqual(instance["last_cycle"]["energy_kwh"], 0.6)
        self.assertEqual(instance["last_cycle"]["sample_count"], 11)
        self.assertEqual(len(instance["last_cycle"]["power_profile"]), 11)
        self.assertEqual(instance["last_cycle"]["power_profile"][-1]["power_w"], 0.0)
        self.assertEqual(instance["last_cycle"]["finish"], (start + timedelta(minutes=59)).isoformat())
        self.assertEqual(instance["program_models"]["Eco"]["runs"], 1)

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_power_resuming_cancels_finish_candidate(self, source, _publish):
        readings = {"power": "0", "energy": "3.6", "program": "Eco"}
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": readings["power"]},
            "sensor.test_energy": {"state": readings["energy"]},
            "sensor.test_program": {"state": readings["program"]},
        }.get(entity_id)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        database = {"schema_version": 1, "instances": {"1": {
            "cycle_start": start.isoformat(), "start_energy": 3.5,
            "peak_power": 1200, "samples": 10,
            "profile": [{"offset_seconds": minute * 60, "power_w": 1200} for minute in range(10)],
            "below_threshold": 0,
            "program": "Eco",
        }}}

        update_instance("token", database, self.config, start + timedelta(minutes=15))
        readings["power"] = "20"
        update_instance("token", database, self.config, start + timedelta(minutes=16))

        instance = database["instances"]["1"]
        self.assertNotIn("finish_candidate", instance)
        self.assertEqual(instance["below_threshold"], 0)
        self.assertEqual(instance["samples"], 12)
        self.assertEqual(instance["profile"][-2]["power_w"], 0.0)
        self.assertEqual(instance["profile"][-1]["power_w"], 20.0)


class ProgramLearningTests(unittest.TestCase):
    def cycle(self, runtime, energy, peak):
        return {
            "program": "Eco",
            "runtime_minutes": runtime,
            "energy_kwh": energy,
            "peak_power": peak,
            "finish": "2026-01-01T12:00:00+00:00",
            "power_profile": [
                {"offset_seconds": 0, "power_w": 0},
                {"offset_seconds": runtime * 60, "power_w": peak},
            ],
        }

    def test_repeated_cycles_update_program_average(self):
        instance = {}
        update_program_model(instance, self.cycle(60, 1.0, 1000))
        summary = update_program_model(instance, self.cycle(70, 1.2, 1200))

        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["expected_runtime_minutes"], 65.0)
        self.assertEqual(summary["expected_energy_kwh"], 1.1)
        self.assertEqual(summary["average_peak_power_w"], 1100.0)
        self.assertEqual(len(summary["representative_profile_w"]), 20)
        self.assertGreater(summary["confidence"], 0)

    def test_bootstrap_seeds_model_only_once(self):
        database = {"instances": {"1": {"last_cycle": self.cycle(60, 1.0, 1000)}}}

        bootstrap_program_models(database)
        bootstrap_program_models(database)

        model = database["instances"]["1"]["program_models"]["Eco"]
        self.assertEqual(model["runs"], 1)
        self.assertEqual(program_summary("Eco", model)["confidence"], 20)


if __name__ == "__main__":
    unittest.main()
