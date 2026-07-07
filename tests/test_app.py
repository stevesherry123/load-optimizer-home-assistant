import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from load_optimizer.app.main import (
    bootstrap_program_models,
    configured_instance_ids,
    instance_config,
    instance_configs,
    load_state,
    load_options,
    normalise_profile,
    normalise_program,
    normalise_program_policy,
    profile_sample,
    program_summary,
    publish_restart_warning,
    save_state,
    reset_configured_instances,
    resolve_program_policies,
    running_instances,
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

    def test_reset_configured_instances_only_removes_requested_instances(self):
        database = {"schema_version": 1, "instances": {
            "1": {"runs": 3},
            "2": {"runs": 1},
            "3": {"runs": 5},
        }}

        removed = reset_configured_instances(database, {"reset_instance_ids": "2, nope"})

        self.assertEqual(removed, ["2"])
        self.assertIn("1", database["instances"])
        self.assertNotIn("2", database["instances"])
        self.assertIn("3", database["instances"])
        self.assertEqual(database["processed_reset_instance_ids"], ["2"])

    def test_reset_configured_instances_is_one_shot_while_config_remains_set(self):
        database = {"schema_version": 1, "instances": {"2": {"runs": 1}}}
        options = {"reset_instance_ids": "2"}

        self.assertEqual(reset_configured_instances(database, options), ["2"])
        database["instances"]["2"] = {"runs": 99}
        self.assertEqual(reset_configured_instances(database, options), [])

        self.assertIn("2", database["instances"])
        self.assertEqual(database["instances"]["2"]["runs"], 99)

    def test_clearing_reset_config_allows_future_reset(self):
        database = {
            "schema_version": 1,
            "instances": {"2": {"runs": 99}},
            "processed_reset_instance_ids": ["2"],
        }

        self.assertEqual(reset_configured_instances(database, {"reset_instance_ids": ""}), [])
        self.assertNotIn("processed_reset_instance_ids", database)
        self.assertEqual(reset_configured_instances(database, {"reset_instance_ids": "2"}), ["2"])

    def test_empty_reset_does_not_default_to_instance_one(self):
        database = {"schema_version": 1, "instances": {"1": {"runs": 3}}}

        removed = reset_configured_instances(database, {"reset_instance_ids": "nope"})

        self.assertEqual(removed, [])
        self.assertIn("1", database["instances"])

    def test_running_instances_reports_active_captures(self):
        database = {"schema_version": 1, "instances": {
            "1": {"cycle_start": "2026-01-01T00:00:00+00:00"},
            "2": {"runs": 1},
        }}
        configs = [
            {"instance_id": "1", "name": "Dishwasher 1"},
            {"instance_id": "2", "name": "Washing Machine 1"},
        ]

        self.assertEqual(running_instances(database, configs), [{
            "instance_id": "1",
            "name": "Dishwasher 1",
            "cycle_start": "2026-01-01T00:00:00+00:00",
        }])

    @patch("load_optimizer.app.main.api_request")
    def test_restart_warning_creates_persistent_notification(self, api_request):
        publish_restart_warning("token", [{
            "instance_id": "2",
            "name": "Washing Machine 1",
            "cycle_start": "2026-01-01T00:00:00+00:00",
        }])

        api_request.assert_called_once()
        self.assertEqual(api_request.call_args.args[1], "/services/persistent_notification/create")
        self.assertEqual(
            api_request.call_args.args[2]["notification_id"],
            "load_optimizer_restart_running_cycle",
        )
        self.assertIn("Washing Machine 1", api_request.call_args.args[2]["message"])

    def test_options_are_loaded_from_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"instance_1_program_policies": [{"program": "Eco"}]}))
            self.assertEqual(load_options(path)["instance_1_program_policies"][0]["program"], "Eco")


class InstanceMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "instance_id": "1",
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

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_second_instance_uses_own_state_and_entity_prefix(self, source, publish):
        source.side_effect = lambda _token, entity_id: {
            "sensor.washer_power": {"state": "500"},
            "sensor.washer_energy": {"state": "8.25"},
            "sensor.washer_program": {"state": "Cottons"},
        }.get(entity_id)
        database = {"schema_version": 1, "instances": {"1": {"runs": 3}}}
        config = {
            **self.config,
            "instance_id": "2",
            "name": "Washing Machine 1",
            "power_sensor": "sensor.washer_power",
            "energy_sensor": "sensor.washer_energy",
            "program_sensor": "sensor.washer_program",
        }

        update_instance("token", database, config, datetime(2026, 1, 1, tzinfo=timezone.utc))

        self.assertIn("1", database["instances"])
        self.assertIn("2", database["instances"])
        self.assertEqual(database["instances"]["2"]["program"], "Cottons")
        published_ids = [call.args[1] for call in publish.call_args_list]
        self.assertIn("sensor.load_optimizer_2_status", published_ids)
        self.assertIn("sensor.load_optimizer_2_power", published_ids)

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


class ProgramPolicyTests(unittest.TestCase):
    def test_learned_program_defaults_to_safe_unclassified_policy(self):
        policies = resolve_program_policies({"Eco": {"runs": 2}}, [])

        self.assertEqual(policies[0]["classification"], "unclassified")
        self.assertFalse(policies[0]["allow_normal_recommendation"])
        self.assertFalse(policies[0]["allow_negative_price_run"])

    def test_configured_policy_overrides_learned_default(self):
        policies = resolve_program_policies({"Eco": {"runs": 2}}, [{
            "program": "Eco",
            "classification": "preferred",
            "enabled": True,
            "preference_rank": 1,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": False,
            "minimum_days_between_runs": 0,
            "maximum_runs_per_window": 1,
            "estimated_overhead_cost_pence": 12.5,
        }])

        self.assertEqual(policies[0]["classification"], "preferred")
        self.assertTrue(policies[0]["allow_normal_recommendation"])
        self.assertEqual(policies[0]["estimated_overhead_cost_pence"], 12.5)

    def test_minimal_policy_uses_safe_optional_defaults(self):
        policy = normalise_program_policy({
            "program": "PreRinse",
            "classification": "alternative",
        })

        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["preference_rank"], 50)
        self.assertFalse(policy["allow_normal_recommendation"])
        self.assertFalse(policy["allow_negative_price_run"])
        self.assertEqual(policy["maximum_runs_per_window"], 1)

    def test_disabled_policy_cannot_be_scheduled(self):
        policy = normalise_program_policy({
            "program": "Quick",
            "classification": "disabled",
            "enabled": True,
            "allow_normal_recommendation": True,
            "allow_negative_price_run": True,
        })

        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["allow_normal_recommendation"])
        self.assertFalse(policy["allow_negative_price_run"])

    def test_instance_config_reads_policy_options(self):
        configured = [{"program": "Eco", "classification": "preferred"}]
        config = instance_config({"instance_1_program_policies": configured})
        self.assertEqual(config["program_policies"], configured)

    def test_instance_config_reads_requested_instance(self):
        options = {
            "instance_ids": "1,2",
            "instance_2_name": "Washing Machine 1",
            "instance_2_power_sensor": "sensor.washing_power",
            "instance_2_program_policies": [{"program": "Cottons", "classification": "preferred"}],
        }

        config = instance_config("2", options)

        self.assertEqual(config["instance_id"], "2")
        self.assertEqual(config["name"], "Washing Machine 1")
        self.assertEqual(config["power_sensor"], "sensor.washing_power")
        self.assertEqual(config["program_policies"][0]["program"], "Cottons")

    def test_instance_configs_follow_configured_ids(self):
        options = {"instance_ids": "1, 2, nope, 2, 0", "instance_2_name": "Washer"}

        configs = instance_configs(options)

        self.assertEqual([config["instance_id"] for config in configs], ["1", "2"])
        self.assertEqual(configs[1]["name"], "Washer")

    def test_configured_instance_ids_default_to_first_instance(self):
        self.assertEqual(configured_instance_ids({}), ["1"])


if __name__ == "__main__":
    unittest.main()
