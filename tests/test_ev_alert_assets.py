"""Test-bench notification assets must remain passive and narrowly scoped."""

import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class EVAlertAssetTests(unittest.TestCase):
    def test_observer_actions_cannot_switch_a_load(self):
        config = yaml.safe_load((ROOT / "dev/ev-test-alerts.yaml").read_text())
        services = {a["service"] for automation in config["automation"] for a in automation["action"] if "service" in a}
        self.assertEqual(services, {"input_text.set_value", "persistent_notification.create", "notify.ev_trial_phone"})
        self.assertNotIn("steves_laptop", json.dumps(config))
        self.assertEqual(config["automation"][1]["trigger"][0]["entity_id"], "switch.ev_trial_load")
        self.assertIsNone(config["automation"][1]["trigger"][0]["to"])

    def test_attribution_requires_a_matching_recent_context(self):
        config = yaml.safe_load((ROOT / "dev/ev-test-alerts.yaml").read_text())
        message = config["automation"][1]["action"][1]["variables"]["alert_message"]
        self.assertIn("command.get('context_id') == trigger.to_state.context.id", message)
        self.assertIn("0 <= age <= 30", message)
        self.assertIn("exact caller not confirmed", message)
        self.assertIn("not confirmation of a physical relay", message)
        self.assertIn("latest reported reason", message)

    def test_trial_settings_restore_but_simulation_requires_new_activation(self):
        package = yaml.safe_load((ROOT / "dev/ev-test-package.yaml").read_text())
        for item in package["input_number"].values():
            self.assertNotIn("initial", item)
        self.assertNotIn("initial", package["input_boolean"]["ev_trial_connected"])
        fill = yaml.safe_load((ROOT / "dev/ev-test-battery-fill.yaml").read_text())
        self.assertFalse(fill["input_boolean"]["ev_trial_simulate_battery_gain"]["initial"])
        self.assertIn("ev_trial_simulation_expires", fill["input_datetime"])
        status = fill["template"][0]["sensor"][0]["state"]
        self.assertIn("expired", status)
        self.assertIn("expiry_not_configured", status)
