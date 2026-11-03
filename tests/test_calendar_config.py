import importlib.util
from pathlib import Path
import unittest

import yaml

PATH = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/optimizer/calendar_config.py"
SPEC = importlib.util.spec_from_file_location("calendar_config", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class CalendarConfigurationTests(unittest.TestCase):
    def test_cleanup_is_scoped_and_preserves_power_up_and_custom_calendars(self):
        source = {"green_window_entity": "calendar.account_greener_nights,calendar.custom_green",
                  "blocked_window_entity": "calendar.account_octoplus_saving_sessions,calendar.custom_block",
                  "free_window_entity": "calendar.account_octoplus_power_up", "scan_interval": 60}
        result = module.clean_calendar_settings(source)
        self.assertEqual(result["green_window_entity"], "calendar.custom_green")
        self.assertEqual(result["blocked_window_entity"], "calendar.account_octoplus_power_down,calendar.custom_block")
        self.assertEqual(result["free_window_entity"], source["free_window_entity"])
        self.assertEqual(source["scan_interval"], result["scan_interval"])
        self.assertIn("saving_sessions", source["blocked_window_entity"])
        self.assertEqual(module.clean_calendar_settings(result), result)

    def test_wrapped_yaml_cleans_every_appliance_without_changing_policy_or_ids(self):
        appliance = {"id": "1", "name": "Dishwasher", "green_window_entity": "calendar.account_greener_nights",
                     "blocked_window_entity": "calendar.account_octoplus_saving_sessions",
                     "program_policies": [{"program": "MixedLoad", "minimum_hours_between_runs": 48}]}
        wrapped = {"instances_yaml": yaml.safe_dump([appliance]), "green_window_entity": "calendar.account_greener_nights"}
        source = {"instances_yaml": yaml.safe_dump(wrapped), "free_window_entity": "calendar.account_octoplus_power_up"}
        result = module.clean_calendar_settings(source)
        parsed = yaml.safe_load(result["instances_yaml"])
        self.assertIn("instances_yaml: |", result["instances_yaml"])
        updated = yaml.safe_load(parsed["instances_yaml"])[0]
        self.assertEqual(parsed["green_window_entity"], "")
        self.assertEqual(updated["blocked_window_entity"], "calendar.account_octoplus_power_down")
        self.assertEqual(updated["program_policies"], appliance["program_policies"])
        self.assertEqual(updated["id"], "1")
        self.assertEqual(module.clean_calendar_settings(result), result)

    def test_current_yaml_keeps_formatting_and_missing_power_down_is_not_unblocked(self):
        raw = '# unchanged\n- id: "1"\n  blocked_window_entity: calendar.account_octoplus_power_down\n'
        self.assertEqual(module.clean_calendar_settings({"instances_yaml": raw})["instances_yaml"], raw)
        self.assertEqual(module.clean_calendar_settings({"blocked_window_entity": "calendar.missing_octoplus_saving_sessions"})["blocked_window_entity"],
                         "calendar.missing_octoplus_power_down")

    def test_entity_detection_includes_wrapped_yaml(self):
        ids = module.configured_entities({"instances_yaml": "blocked_window_entity: calendar.account_octoplus_power_down"})
        self.assertIn("calendar.account_octoplus_power_down", ids)
