import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from load_optimizer.app.main import (
    bootstrap_program_models,
    instance_config,
    instance_configs,
    load_state,
    load_options,
    mark_interrupted_captures,
    normalise_profile,
    normalise_program,
    normalise_program_policy,
    parse_instances_yaml,
    profile_energy_kwh,
    profile_sample,
    program_summary,
    publish_restart_warning,
    repair_learning_quality,
    save_state,
    reset_configured_instances,
    reset_request_status,
    resolve_program_policies,
    running_instances,
    schedule_advice,
    tariff_entity_diagnostic,
    tariff_state_from_entity,
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


class ConfigurationTests(unittest.TestCase):
    def test_instance_config_combines_multiple_and_single_tariff_fields(self):
        config = instance_config("1", {
            "tariff_entities": "event.current_day_rates, event.next_day_rates",
            "tariff_entity": "sensor.single_feed",
        })

        self.assertEqual(config["tariff_entities"], [
            "event.current_day_rates",
            "event.next_day_rates",
            "sensor.single_feed",
        ])

    def test_instance_config_does_not_duplicate_single_tariff_entity(self):
        config = instance_config("1", {
            "tariff_entities": "sensor.single_feed",
            "tariff_entity": "sensor.single_feed",
        })

        self.assertEqual(config["tariff_entities"], ["sensor.single_feed"])

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

    def test_reset_request_status_reports_consumed_request(self):
        database = {"schema_version": 1, "processed_reset_instance_ids": ["2"]}

        self.assertEqual(
            reset_request_status(database, {"reset_instance_ids": "2"}),
            {
                "reset_status": "consumed",
                "reset_requested_instance_ids": ["2"],
                "reset_processed_instance_ids": ["2"],
                "reset_pending_instance_ids": [],
                "reset_invalid_tokens": [],
                "reset_message": "Reset request has already been applied for instance(s): 2.",
            },
        )

    def test_reset_request_status_reports_pending_and_invalid_values(self):
        database = {"schema_version": 1, "processed_reset_instance_ids": ["2"]}

        status = reset_request_status(database, {"reset_instance_ids": "2, 3, nope"})

        self.assertEqual(status["reset_status"], "partially_invalid")
        self.assertEqual(status["reset_requested_instance_ids"], ["2", "3"])
        self.assertEqual(status["reset_processed_instance_ids"], ["2"])
        self.assertEqual(status["reset_pending_instance_ids"], ["3"])
        self.assertEqual(status["reset_invalid_tokens"], ["nope"])

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

    @patch("load_optimizer.app.main.render_template")
    @patch("load_optimizer.app.main.source_state")
    def test_tariff_state_falls_back_to_template_attribute(self, source_state, render_template):
        source_state.return_value = {
            "entity_id": "event.rates",
            "state": "2026-07-06T00:00:00+00:00",
            "attributes": {"event_types": ["octopus_energy_electricity_current_day_rates"]},
        }
        render_template.side_effect = [
            [{
                "start": "2026-07-06T00:00:00+01:00",
                "end": "2026-07-06T00:30:00+01:00",
                "value_inc_vat": 0.241,
            }],
        ]

        state = tariff_state_from_entity("token", "event.rates")

        self.assertEqual(state["attributes"]["rates"][0]["value_inc_vat"], 0.241)
        self.assertEqual(state["attributes"]["tariff_rates_source"], "template_state_attr:rates")

    @patch("load_optimizer.app.main.render_template")
    @patch("load_optimizer.app.main.source_state")
    def test_tariff_state_keeps_direct_rate_attributes(self, source_state, render_template):
        source_state.return_value = {
            "entity_id": "event.rates",
            "state": "2026-07-06T00:00:00+00:00",
            "attributes": {"rates": [{"value_inc_vat": 0.241}]},
        }

        state = tariff_state_from_entity("token", "event.rates")

        self.assertEqual(state["attributes"]["rates"][0]["value_inc_vat"], 0.241)
        render_template.assert_not_called()

    def test_tariff_entity_diagnostic_reports_keys_and_counts(self):
        diagnostic = tariff_entity_diagnostic({
            "entity_id": "event.rates",
            "state": "2026-07-06T00:00:00+00:00",
            "attributes": {
                "rates": [{"value_inc_vat": 0.241}],
                "last_event_attributes": {"event_type": "rates"},
            },
        })

        self.assertEqual(diagnostic["entity_id"], "event.rates")
        self.assertEqual(diagnostic["rates_type"], "list")
        self.assertEqual(diagnostic["rates_count"], 1)
        self.assertEqual(diagnostic["last_event_attributes_type"], "dict")
        self.assertIn("rates", diagnostic["attribute_keys"])


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

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_empty_secondary_tariff_source_does_not_invalidate_costing(self, source, publish):
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": "0"},
            "sensor.test_energy": {"state": "3.5"},
            "sensor.test_program": {"state": "Eco"},
            "event.current_rates": {
                "entity_id": "event.current_rates",
                "state": "2026-01-01T00:00:00+00:00",
                "attributes": {"rates": [
                    {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-01T00:30:00+00:00", "value_inc_vat": 0.10},
                    {"start": "2026-01-01T00:30:00+00:00", "end": "2026-01-01T01:00:00+00:00", "value_inc_vat": 0.10},
                ]},
            },
            "event.next_rates": {
                "entity_id": "event.next_rates",
                "state": "2026-01-01T00:00:00+00:00",
                "attributes": {"rates": []},
            },
        }.get(entity_id)
        database = {"schema_version": 1, "instances": {"1": {"program_models": {
            "Eco": {
                "program": "Eco",
                "runs": 1,
                "expected_runtime_minutes": 30,
                "expected_energy_kwh": 1,
                "representative_profile_w": [1000, 1000],
                "confidence": 20,
            },
        }}}}
        config = {
            **self.config,
            "program_policies": [{"program": "Eco", "classification": "preferred", "allow_normal_recommendation": True}],
            "tariff_entity": "",
            "tariff_entities": ["event.current_rates", "event.next_rates"],
            "tariff_timezone": "Europe/London",
            "tariff_price_unit": "gbp_per_kwh",
            "cost_search_hours": 1,
            "cost_candidate_interval": 30,
        }

        update_instance("token", database, config, datetime(2026, 1, 1, tzinfo=timezone.utc))

        cost_status = next(
            call for call in publish.call_args_list
            if call.args[1] == "sensor.load_optimizer_1_cost_status"
        )
        self.assertEqual(cost_status.args[2], "insufficient_profile")
        self.assertEqual(cost_status.args[3]["tariff_periods"], 2)
        self.assertEqual(cost_status.args[3]["tariff_parse_errors"][0]["entity_id"], "event.next_rates")

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

    def test_profile_energy_integrates_power_samples(self):
        profile = [
            {"offset_seconds": 0, "power_w": 1000},
            {"offset_seconds": 1800, "power_w": 1000},
            {"offset_seconds": 3600, "power_w": 0},
        ]

        self.assertEqual(profile_energy_kwh(profile), 0.75)

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
        self.assertEqual(instance["last_cycle"]["energy_kwh"], 0.68)
        self.assertEqual(instance["last_cycle"]["energy_source"], "power_profile")
        self.assertEqual(instance["last_cycle"]["energy_sensor_delta_kwh"], 0.6)
        self.assertEqual(instance["last_cycle"]["sample_count"], 11)
        self.assertEqual(len(instance["last_cycle"]["power_profile"]), 11)
        self.assertEqual(instance["last_cycle"]["power_profile"][-1]["power_w"], 0.0)
        self.assertEqual(instance["last_cycle"]["finish"], (start + timedelta(minutes=59)).isoformat())
        self.assertEqual(instance["program_models"]["Eco"]["runs"], 1)

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_profile_energy_survives_daily_counter_reset(self, source, _publish):
        self.config["finish_delay"] = 1
        readings = {"power": "0", "energy": "0.1", "program": "Eco"}
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": readings["power"]},
            "sensor.test_energy": {"state": readings["energy"]},
            "sensor.test_program": {"state": readings["program"]},
        }.get(entity_id)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        database = {"schema_version": 1, "instances": {"1": {
            "cycle_start": start.isoformat(),
            "start_energy": 9.9,
            "peak_power": 1000,
            "samples": 2,
            "profile": [
                {"offset_seconds": 0, "power_w": 1000},
                {"offset_seconds": 1800, "power_w": 1000},
            ],
            "below_threshold": 0,
            "program": "Eco",
        }}}

        update_instance("token", database, self.config, start + timedelta(hours=1))

        last = database["instances"]["1"]["last_cycle"]
        self.assertEqual(last["energy_kwh"], 0.75)
        self.assertEqual(last["energy_source"], "power_profile")
        self.assertEqual(last["energy_sensor_delta_kwh"], 0.0)

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

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_interrupted_cycle_is_discarded_from_learning(self, source, _publish):
        self.config["finish_delay"] = 1
        readings = {"power": "0", "energy": "4.2", "program": "Eco"}
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
            "program_models": {"Eco": {"runs": 3}},
            "runs": 3,
        }}}
        mark_interrupted_captures(database, [{"instance_id": "1", "name": "Dishwasher 1", "cycle_start": start.isoformat()}])

        update_instance("token", database, self.config, start + timedelta(minutes=60))

        instance = database["instances"]["1"]
        self.assertNotIn("cycle_start", instance)
        self.assertEqual(instance["runs"], 3)
        self.assertEqual(instance["program_models"]["Eco"]["runs"], 3)
        self.assertNotIn("last_cycle", instance)
        self.assertTrue(instance["last_discarded_cycle"]["learning_excluded"])
        self.assertEqual(instance["last_discarded_cycle"]["exclusion_reason"], "app_restarted_during_cycle")

    @patch("load_optimizer.app.main.publish_entity")
    @patch("load_optimizer.app.main.source_state")
    def test_suspicious_completed_cycle_is_discarded_from_learning(self, source, _publish):
        self.config["finish_delay"] = 1
        readings = {"power": "0", "energy": "4.2", "program": "Eco"}
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": readings["power"]},
            "sensor.test_energy": {"state": readings["energy"]},
            "sensor.test_program": {"state": readings["program"]},
        }.get(entity_id)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        database = {"schema_version": 1, "instances": {"1": {
            "cycle_start": start.isoformat(), "start_energy": 4.1999,
            "peak_power": 10.8, "samples": 2,
            "profile": [
                {"offset_seconds": 0, "power_w": 10.8},
                {"offset_seconds": 60, "power_w": 0.0},
            ],
            "below_threshold": 0,
            "program": "Eco",
            "program_models": {"Eco": {"runs": 3}},
            "runs": 3,
        }}}

        update_instance("token", database, self.config, start + timedelta(minutes=1))

        instance = database["instances"]["1"]
        self.assertEqual(instance["runs"], 3)
        self.assertEqual(instance["program_models"]["Eco"]["runs"], 3)
        self.assertNotIn("last_cycle", instance)
        self.assertTrue(instance["last_discarded_cycle"]["learning_excluded"])
        self.assertEqual(instance["last_discarded_cycle"]["exclusion_reason"], "runtime_below_5_minutes")


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
        self.assertEqual(summary["profile_count"], 2)
        self.assertEqual(summary["first_seen"], "2026-01-01T12:00:00+00:00")
        self.assertEqual(summary["last_seen"], "2026-01-01T12:00:00+00:00")
        self.assertEqual(len(summary["recent_cycles"]), 2)
        self.assertEqual(summary["expected_runtime_minutes"], 65.0)
        self.assertEqual(summary["expected_energy_kwh"], 1.1)
        self.assertEqual(summary["average_peak_power_w"], 1100.0)
        self.assertEqual(len(summary["representative_profile_w"]), 20)
        self.assertGreater(summary["confidence"], 0)

    def test_program_summary_reports_historic_last_updated_as_last_seen(self):
        summary = program_summary("Eco", {
            "runs": 1,
            "last_updated": "2026-01-01T12:00:00+00:00",
            "statistics": {
                "runtime_minutes": {"count": 1, "mean": 60.0, "m2": 0.0},
                "energy_kwh": {"count": 1, "mean": 1.0, "m2": 0.0},
                "peak_power_w": {"count": 1, "mean": 1000.0, "m2": 0.0},
            },
        })

        self.assertEqual(summary["last_seen"], "2026-01-01T12:00:00+00:00")

    def test_bootstrap_seeds_model_only_once(self):
        database = {"instances": {"1": {"last_cycle": self.cycle(60, 1.0, 1000)}}}

        bootstrap_program_models(database)
        bootstrap_program_models(database)

        model = database["instances"]["1"]["program_models"]["Eco"]
        self.assertEqual(model["runs"], 1)
        self.assertEqual(program_summary("Eco", model)["confidence"], 20)

    def test_repair_learning_quality_removes_suspicious_recent_cycles(self):
        database = {"instances": {"1": {
            "runs": 4,
            "program_models": {"Quick65": {
                "runs": 4,
                "first_seen": "2026-01-01T01:00:00+00:00",
                "last_seen": "2026-01-01T04:00:00+00:00",
                "profile_count": 4,
                "representative_profile_w": [10.0, 1000.0, 10.0],
                "recent_cycles": [
                    {"finish": "2026-01-01T01:00:00+00:00", "runtime_minutes": 49.7, "energy_kwh": 1.0253, "peak_power_w": 2458.4, "sample_count": 49, "energy_source": "power_profile"},
                    {"finish": "2026-01-01T02:00:00+00:00", "runtime_minutes": 43.4, "energy_kwh": 1.1099, "peak_power_w": 2519.2, "sample_count": 42, "energy_source": "power_profile"},
                    {"finish": "2026-01-01T03:00:00+00:00", "runtime_minutes": 1.1, "energy_kwh": 0.0001, "peak_power_w": 10.8, "sample_count": 2, "energy_source": "power_profile"},
                    {"finish": "2026-01-01T04:00:00+00:00", "runtime_minutes": 42.1, "energy_kwh": 0.9158, "peak_power_w": 2159.6, "sample_count": 41, "energy_source": "power_profile"},
                ],
            }},
        }}}

        repair_learning_quality(database, [{"instance_id": "1", "learning_min_runtime_minutes": 5, "learning_min_samples": 3, "learning_min_energy_kwh": 0.001}])

        instance = database["instances"]["1"]
        model = instance["program_models"]["Quick65"]
        self.assertEqual(instance["runs"], 3)
        self.assertEqual(model["runs"], 3)
        self.assertEqual(len(model["recent_cycles"]), 3)
        self.assertEqual(program_summary("Quick65", model)["expected_runtime_minutes"], 45.1)
        self.assertEqual(model["representative_profile_w"], [10.0, 1000.0, 10.0])
        self.assertEqual(instance["last_discarded_cycle"]["finish"], "2026-01-01T03:00:00+00:00")
        self.assertEqual(instance["last_discarded_cycle"]["exclusion_reason"], "runtime_below_5_minutes")

    def test_repair_learning_quality_restores_missing_profile_from_last_cycle(self):
        database = {"instances": {"1": {
            "last_cycle": self.cycle(45, 0.9, 2000),
            "program_models": {"Eco": {
                "runs": 5,
                "profile_count": 0,
                "representative_profile_w": [],
                "statistics": {
                    "runtime_minutes": {"count": 5, "mean": 45.0, "m2": 0.0},
                    "energy_kwh": {"count": 5, "mean": 0.9, "m2": 0.0},
                },
            }},
        }}}

        repair_learning_quality(database, [{"instance_id": "1", "learning_min_runtime_minutes": 5, "learning_min_samples": 3, "learning_min_energy_kwh": 0.001}])

        model = database["instances"]["1"]["program_models"]["Eco"]
        self.assertEqual(len(model["representative_profile_w"]), 20)
        self.assertEqual(model["profile_count"], 1)
        self.assertEqual(model["representative_profile_repaired_from"], "last_cycle_power_profile")


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

    def test_instance_configs_ignore_legacy_instance_ids(self):
        options = {"instance_ids": "1, 2, nope, 2, 0", "instance_2_name": "Washer"}

        configs = instance_configs(options)

        self.assertEqual(configs, [])

    def test_empty_repeatable_instances_list_does_not_fall_back_to_legacy_fields(self):
        configs = instance_configs({"instances": [], "instance_ids": "1", "instance_1_name": "Dishwasher 1"})

        self.assertEqual(configs, [])

    def test_repeatable_instances_list_drives_dynamic_instance_config(self):
        options = {
            "instances": [
                {"id": "1", "name": "Dishwasher 1", "power_sensor": "sensor.dishwasher_power"},
                {"id": "2", "name": "Washing Machine 1", "power_sensor": "sensor.washer_power"},
                {
                    "id": "3",
                    "name": "Tumble Dryer 1",
                    "power_sensor": "sensor.dryer_power",
                    "active_power_threshold": 25,
                    "finish_delay": 3,
                    "program_policies": [{"program": "Default", "classification": "preferred"}],
                },
            ],
            "tariff_entities": "event.current,event.next",
        }

        configs = instance_configs(options)

        self.assertEqual([config["instance_id"] for config in configs], ["1", "2", "3"])
        self.assertEqual(configs[2]["name"], "Tumble Dryer 1")
        self.assertEqual(configs[2]["power_sensor"], "sensor.dryer_power")
        self.assertEqual(configs[2]["active_power_threshold"], 25)
        self.assertEqual(configs[2]["finish_delay"], 3)
        self.assertEqual(configs[2]["program_policies"][0]["program"], "Default")
        self.assertEqual(configs[2]["tariff_entities"], ["event.current", "event.next"])

    def test_instances_yaml_drives_dynamic_instance_config(self):
        options = {
            "instances_yaml": """
- id: 1
  name: Dishwasher 1
  power_sensor: sensor.dishwasher_power
- id: 3
  name: Tumble Dryer 1
  power_sensor: sensor.dryer_power
  active_power_threshold: 25
  finish_delay: 3
  schedule_strategy: cheapest_latest_finish
  schedule_equivalent_cost_tolerance_pence: 1.5
  schedule_window_preference: prefer_overnight
  schedule_overnight_start: "20:00"
  schedule_overnight_end: "08:00"
  program_policies:
    - program: Default
      classification: preferred
      allow_normal_recommendation: true
""",
            "instance_ids": "1,2",
            "instance_2_name": "Legacy Washer",
            "cost_forecast_interval": 30,
        }

        configs = instance_configs(options)

        self.assertEqual([config["instance_id"] for config in configs], ["1", "3"])
        self.assertEqual(configs[1]["name"], "Tumble Dryer 1")
        self.assertEqual(configs[1]["power_sensor"], "sensor.dryer_power")
        self.assertEqual(configs[1]["active_power_threshold"], 25)
        self.assertEqual(configs[1]["finish_delay"], 3)
        self.assertEqual(configs[1]["schedule_strategy"], "cheapest_latest_finish")
        self.assertEqual(configs[1]["schedule_equivalent_cost_tolerance_pence"], 1.5)
        self.assertEqual(configs[1]["schedule_window_preference"], "prefer_overnight")
        self.assertEqual(configs[1]["schedule_overnight_start"], "20:00")
        self.assertEqual(configs[1]["schedule_overnight_end"], "08:00")
        self.assertEqual(configs[1]["cost_forecast_interval"], 30)
        self.assertEqual(configs[1]["program_policies"][0]["program"], "Default")
        self.assertTrue(configs[1]["program_policies"][0]["allow_normal_recommendation"])

    def test_instances_yaml_accepts_json_list(self):
        parsed = parse_instances_yaml('[{"id": "4", "name": "EV 1", "power_sensor": "sensor.ev_power"}]')

        self.assertEqual(parsed[0]["id"], "4")
        self.assertEqual(parsed[0]["name"], "EV 1")

class ScheduleAdviceTests(unittest.TestCase):
    def test_ready_recommendation_is_good_to_start_inside_tolerance(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        advice = schedule_advice({
            "status": "ready",
            "program": "Quick65",
            "start": now + timedelta(minutes=3),
            "confidence": 26,
            "total_cost_pence": 4.2,
            "cost_if_started_now_pence": 6.1,
            "potential_saving_pence": 1.9,
        }, {
            "schedule_confidence_threshold": 20,
            "schedule_start_tolerance_minutes": 5,
        }, now)

        self.assertTrue(advice["good_to_start"])
        self.assertTrue(advice["automation_ready"])
        self.assertEqual(advice["reason"], "ready")
        self.assertEqual(advice["program"], "Quick65")

    def test_low_confidence_blocks_automation_ready(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        advice = schedule_advice({
            "status": "ready",
            "program": "Quick65",
            "start": now,
            "confidence": 10,
            "total_cost_pence": 4.2,
        }, {
            "schedule_confidence_threshold": 20,
            "schedule_start_tolerance_minutes": 5,
        }, now)

        self.assertTrue(advice["good_to_start"])
        self.assertFalse(advice["automation_ready"])
        self.assertEqual(advice["reason"], "confidence_below_20")

    def test_future_recommendation_is_not_good_to_start_yet(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        advice = schedule_advice({
            "status": "ready",
            "program": "Quick65",
            "start": now + timedelta(minutes=30),
            "confidence": 50,
            "total_cost_pence": 4.2,
        }, {
            "schedule_confidence_threshold": 20,
            "schedule_start_tolerance_minutes": 5,
        }, now)

        self.assertFalse(advice["good_to_start"])
        self.assertFalse(advice["automation_ready"])
        self.assertEqual(advice["reason"], "recommended_start_in_future")


if __name__ == "__main__":
    unittest.main()
