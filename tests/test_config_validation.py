"""Pre-save validation and compatibility parser regression coverage."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components/load_optimizer"))
from legacy.app_runtime import instance_configs, normalise_program_policy, parse_instances_yaml
from legacy.config_validation import (
    MAX_CONFIG_BYTES, ConfigurationError, appliance_document, validate_appliance_options,
)


class ConfigurationValidationTests(unittest.TestCase):
    def setUp(self):
        self.appliance = {
            "id": "1", "power_sensor": "sensor.test_power", "energy_sensor": "sensor.test_energy",
            "program_policies": [{"program": "Default", "classification": "preferred",
                                  "allow_normal_recommendation": True, "allow_negative_price_run": False}],
        }

    def check(self, entries=None, **options):
        return validate_appliance_options({
            "instances_yaml": json.dumps(entries if entries is not None else [self.appliance]),
            **options,
        })

    def test_documented_examples_match_runtime_configuration(self):
        for name in ("learned-appliance.yaml", "home-connect-dishwasher.yaml"):
            options = {"instances_yaml": (ROOT / "docs/examples" / name).read_text()}
            self.assertEqual(validate_appliance_options(options).instances, instance_configs(options))

    def test_existing_multiple_window_sources_remain_editable(self):
        for key in ("green_window_entity", "blocked_window_entity"):
            with self.subTest(key=key):
                sources = "calendar.first,event.second"
                self.assertEqual(self.check(**{key: sources}).instances[0][key], sources)
                entry = {**self.appliance, key: sources}
                self.assertEqual(self.check([entry]).instances[0][key], sources)
                with self.assertRaises(ConfigurationError):
                    self.check(**{key: "calendar.first,not-an-entity"})

    def test_validation_does_not_mutate_settings_or_enable_permissions(self):
        before = deepcopy(self.appliance)
        result = self.check()
        self.assertEqual(self.appliance, before)
        self.assertFalse(result.instances[0]["program_policies"][0]["allow_negative_price_run"])
        self.assertNotIn("auto_mode_enabled", result.options)

    def test_bad_document_shapes_are_not_silently_dropped(self):
        for raw in ("", "[]", "null", "power_sensor: sensor.test", "- 123", "- [broken",
                    "- &item {id: 1}\n- *item", "!!python/object:builtins.object {}"):
            with self.subTest(raw=raw), self.assertRaises(ConfigurationError):
                validate_appliance_options({"instances_yaml": raw})

    def test_duplicate_keys_reject_instead_of_overwriting(self):
        for raw in ("- id: 1\n  id: 2", '- {id: 1, power_sensor: sensor.a, power_sensor: sensor.b}'):
            with self.subTest(raw=raw), self.assertRaises(ConfigurationError):
                appliance_document(raw)

    def test_runtime_consumers_cannot_mutate_cached_configuration(self):
        raw = json.dumps([self.appliance])
        parsed, _ = appliance_document(raw)
        parsed[0]["program_policies"].clear()
        self.assertEqual(appliance_document(raw)[0], [self.appliance])

    def test_size_depth_alias_and_count_bounds(self):
        for raw in (" " * (MAX_CONFIG_BYTES + 1), "[" * 20 + "0" + "]" * 20,
                    json.dumps([self.appliance] * 65), "- id: " + "1" * 5000, "- id: \ud800",
                    "[" + ",".join("0" for _ in range(20_001)) + "]"):
            with self.subTest(size=len(raw)), self.assertRaises(ConfigurationError):
                appliance_document(raw)

    def test_invalid_ids_and_duplicate_effective_ids_reject(self):
        for value in (0, -1, False, True, 1.5, "oops", "", None, "١", "9" * 33):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                self.check([{**self.appliance, "id": value}])
        for entries in ([self.appliance, self.appliance],
                        [{"power_sensor": "sensor.a"}, self.appliance]):
            with self.assertRaises(ConfigurationError):
                self.check(entries)
        with self.assertRaises(ConfigurationError):
            self.check([{**self.appliance, "instance_id": "2"}])

    def test_implicit_and_legacy_ids_keep_their_identity(self):
        result = self.check([{"power_sensor": "sensor.a"}, {"instance_id": "03", "power_sensor": "sensor.b"}])
        self.assertEqual([item["instance_id"] for item in result.instances], ["1", "03"])
        options = {"instances_yaml": "- id: 001\n  power_sensor: sensor.a\n  schedule_overnight_start: 20:00\n  schedule_overnight_end: 08:00"}
        result = validate_appliance_options(options)
        self.assertEqual(result.instances, instance_configs(options))
        self.assertEqual(result.instances[0]["instance_id"], "001")
        self.assertEqual(result.instances[0]["schedule_overnight_start"], "20:00")

    def test_scalar_words_and_dates_are_not_reinterpreted(self):
        parsed, _ = appliance_document("- id: 1\n  name: On\n  power_sensor: sensor.a\n  custom_date: 2026-10-10")
        self.assertEqual(parsed[0]["name"], "On")
        self.assertEqual(parsed[0]["custom_date"], "2026-10-10")

    def test_flow_yaml_comments_quoted_strings_and_policy_indentation(self):
        raw = """
        - id: '1' # stable identity
          name: 'Test: appliance'
          power_sensor: sensor.a
          program_policies:
          - {program: Default, classification: preferred, allow_normal_recommendation: true}
          finish_delay: 5
        """
        parsed = parse_instances_yaml(raw)[0]
        self.assertEqual(parsed["id"], "1")
        self.assertEqual(parsed["name"], "Test: appliance")
        self.assertEqual(parsed["finish_delay"], 5)
        self.assertNotIn("finish_delay", parsed["program_policies"][0])
        self.assertEqual(len(validate_appliance_options({"instances_yaml": raw}).instances), 1)

    def test_entity_format_and_sensor_domain(self):
        for value in ("switch.plug", "sensor.Bad", "sensor.a,b", "sensor.a ' injected", [], 42, None):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                self.check([{**self.appliance, "power_sensor": value}])
        for key in ("tariff_entity", "green_window_entity", "blocked_window_entity", "tariff_entities"):
            with self.subTest(key=key), self.assertRaises(ConfigurationError):
                self.check(**{key: "bad ID"})
        self.check(tariff_entities="event.today,event.tomorrow", green_window_entity="calendar.green")
        self.check([{**self.appliance, "energy_sensor": "", "program_sensor": "select.program"}])

    def test_bad_numbers_are_rejected_before_runtime_conversion(self):
        for field in ("finish_delay", "learning_min_samples", "schedule_confidence_threshold"):
            for value in ("bad", 1.5, "1.5", True, None, float("nan"), float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ConfigurationError):
                    self.check([{**self.appliance, field: value}])
        for field in ("active_power_threshold", "learning_min_energy_kwh", "schedule_preference_weight_pence"):
            for value in (-1, True, None, float("nan"), float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ConfigurationError):
                    self.check([{**self.appliance, field: value}])
        for field in ("scan_interval", "cost_forecast_interval", "cost_search_hours"):
            with self.subTest(field=field), self.assertRaises(ConfigurationError):
                self.check(**{field: 0})

    def test_policy_types_duplicates_and_nonfinite_costs(self):
        for policies in (None, {}, ["invalid"], [{"program": ""}], [{"program": "unknown"}],
                         [{"program": "Default", "enabled": "false"}],
                         [{"program": "Default", "classification": "typo"}],
                         [{"program": "Default", "wear_cost_pence": float("inf")}],
                         [{"program": "Eco50"}, {"program": "Dishcare.Dishwasher.Program.Eco50"}],
                         [{"program": "Default"}] * 129):
            with self.subTest(policies=policies), self.assertRaises(ConfigurationError):
                self.check([{**self.appliance, "program_policies": policies}])

    def test_legacy_permission_values_fail_closed_even_before_a_user_edits(self):
        for value in ("false", "no", "off", "invalid", None, "", [], {}, float("nan"), float("inf")):
            with self.subTest(value=value):
                policy = normalise_program_policy({
                    "program": "Default", "classification": "preferred", "enabled": value,
                    "allow_normal_recommendation": value, "allow_negative_price_run": value,
                })
                self.assertFalse(policy["enabled"])
                self.assertFalse(policy["allow_normal_recommendation"])
                self.assertFalse(policy["allow_negative_price_run"])

    def test_scheduler_values_and_timezone(self):
        for key, value in (("schedule_strategy", "typo"), ("schedule_window_preference", []),
                           ("schedule_overnight_start", "25:00"), ("schedule_overnight_end", 800)):
            with self.subTest(key=key), self.assertRaises(ConfigurationError):
                self.check([{**self.appliance, key: value}])
        for options in ({"tariff_timezone": "Invalid/Timezone"}, {"tariff_timezone": []},
                        {"tariff_price_unit": []}, {"tariff_price_unit": "pounds"}):
            with self.subTest(options=options), self.assertRaises(ConfigurationError):
                self.check(**options)

    def test_legacy_wrapper_precedence_and_instances_wrapper(self):
        raw = 'tariff_timezone: UTC\ntariff_price_unit: gbp_per_kwh\ntariff_entities: >-\n  event.today,event.tomorrow\ninstances_yaml: |\n  - id: "1"\n    power_sensor: sensor.test\n'
        result = validate_appliance_options({"instances_yaml": raw, "tariff_price_unit": "p_per_kwh"})
        self.assertEqual(result.options["tariff_timezone"], "UTC")
        self.assertEqual(result.options["tariff_price_unit"], "p_per_kwh")
        self.assertEqual(result.instances[0]["tariff_entities"], ["event.today", "event.tomorrow"])
        self.assertEqual(appliance_document(json.dumps({"instances": [self.appliance]}))[0], [self.appliance])
        nested = 'instances_yaml: |\n  instances:\n    - power_sensor: sensor.a\n'
        self.assertEqual(validate_appliance_options({"instances_yaml": nested}).instances[0]["power_sensor"], "sensor.a")

    def test_maintenance_reset_cannot_be_hidden_in_a_pasted_wrapper(self):
        with self.assertRaises(ConfigurationError):
            validate_appliance_options({"instances_yaml": 'reset_instance_ids: "1"\ninstances_yaml: |\n  - power_sensor: sensor.a\n'})

    def test_error_does_not_echo_raw_yaml_or_parser_exception(self):
        private = "PRIVATE_EXAMPLE_DO_NOT_REPORT"
        with self.assertRaises(ConfigurationError) as context:
            validate_appliance_options({"instances_yaml": "- id: [" + private})
        self.assertNotIn(private, str(context.exception))


if __name__ == "__main__":
    unittest.main()
