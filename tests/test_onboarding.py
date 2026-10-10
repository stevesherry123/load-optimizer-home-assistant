"""Exercise the actual documentation examples without Home Assistant or network."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components/load_optimizer"))

from legacy.app_runtime import (
    instance_configs,
    parse_instances_yaml,
    program_summary,
    resolve_program_policies,
    update_instance,
)
from legacy.costing import recommend_cycle, tariff_periods_from_entity


class OnboardingTests(unittest.TestCase):
    def config(self, example="learned-appliance.yaml"):
        raw = (ROOT / "docs/examples" / example).read_text()
        configs = instance_configs({"instances_yaml": raw})
        self.assertEqual(len(configs), 1)
        return raw, configs[0]

    def learn(self, config, programme=None):
        database = {"schema_version": 1, "instances": {}}
        start = datetime(2026, 10, 10, 8, tzinfo=timezone.utc)
        sources = {}
        if programme is not None:
            sources[config["program_sensor"]] = {"state": programme}
        with patch("legacy.app_runtime.source_state", side_effect=lambda _, key: sources.get(key)), \
             patch("legacy.app_runtime.publish_entity"), \
             patch("legacy.app_runtime.api_request", return_value=None):
            for minute in range(18):
                sources[config["power_sensor"]] = {"state": "1000" if minute < 13 else "0"}
                sources[config["energy_sensor"]] = {"state": str(100 + min(minute, 13) / 60)}
                update_instance("isolated-example", database, config,
                                now=start + timedelta(minutes=minute))
        instance = database["instances"][config["instance_id"]]
        self.assertEqual(instance["runs"], 1)
        self.assertNotIn("cycle_start", instance)
        self.assertNotIn("last_discarded_cycle", instance)
        return instance

    def recommendation(self, config, instance):
        reference = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        periods = [{"start": reference, "end": reference + timedelta(hours=6),
                    "price_p_per_kwh": 20}]
        models = instance["program_models"]
        return recommend_cycle(
            [program_summary(name, model) for name, model in models.items()],
            resolve_program_policies(models, config["program_policies"]), periods,
            reference_utc=reference, search_hours=2, candidate_interval_minutes=5,
            forecast_hours=0,
        )

    def test_inline_quick_start_matches_the_executable_example(self):
        raw, config = self.config()
        guide = (ROOT / "docs/getting-started.md").read_text()
        blocks = re.findall(r"```yaml\n(.*?)\n```", guide, re.DOTALL)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(parse_instances_yaml(blocks[0]), parse_instances_yaml(raw))
        self.assertEqual(config["instance_id"], "1")
        self.assertFalse(config["program_sensor"])

    def test_quick_start_learns_default_and_produces_a_recommendation(self):
        _, config = self.config()
        instance = self.learn(config)
        self.assertEqual(set(instance["program_models"]), {"Default"})
        result = self.recommendation(config, instance)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["program"], "Default")
        self.assertGreater(result["energy_cost_pence"], 0)

    def test_named_dishwasher_example_learns_its_explicit_programme(self):
        _, config = self.config("home-connect-dishwasher.yaml")
        instance = self.learn(config, "Dishcare.Dishwasher.Program.Eco50")
        self.assertEqual(set(instance["program_models"]), {"Eco50"})
        self.assertEqual(self.recommendation(config, instance)["program"], "Eco50")

    def test_both_examples_disallow_negative_price_runs(self):
        for example in ("learned-appliance.yaml", "home-connect-dishwasher.yaml"):
            with self.subTest(example=example):
                _, config = self.config(example)
                policies = resolve_program_policies({}, config["program_policies"])
                self.assertTrue(policies[0]["allow_normal_recommendation"])
                self.assertFalse(policies[0]["allow_negative_price_run"])
                self.assertFalse(any(key.startswith("bosch_") for key in config))

    def test_missing_policy_reproduces_the_old_documentation_dead_end(self):
        _, config = self.config()
        config["program_policies"] = []
        instance = self.learn(config)
        result = self.recommendation(config, instance)
        self.assertEqual(result["status"], "no_eligible_programs")

    def test_default_policy_does_not_silently_enable_named_programmes(self):
        _, config = self.config("home-connect-dishwasher.yaml")
        config["program_policies"][0]["program"] = "Default"
        instance = self.learn(config, "Dishcare.Dishwasher.Program.Eco50")
        self.assertEqual(self.recommendation(config, instance)["status"], "no_eligible_programs")

    def test_learning_round_trip_keeps_counts_and_recommendations(self):
        _, config = self.config()
        restored = json.loads(json.dumps(self.learn(config)))
        self.assertEqual(restored["runs"], 1)
        self.assertEqual(restored["program_models"]["Default"]["runs"], 1)
        self.assertEqual(self.recommendation(config, restored)["status"], "ready")

    def test_documented_price_units_represent_the_same_price(self):
        reference = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        results = []
        for unit, value in (("gbp_per_kwh", 0.25), ("p_per_kwh", 25)):
            payload = {"attributes": {"rates": [{
                "start": reference.isoformat(),
                "end": (reference + timedelta(minutes=30)).isoformat(),
                "value_inc_vat": value,
            }]}}
            results.append(tariff_periods_from_entity(
                payload, reference_utc=reference, timezone_name="Europe/London",
                price_unit=unit,
            ))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0]["price_p_per_kwh"], 25)

    def test_new_guides_have_resolvable_local_links(self):
        for relative in (
            "README.md", "CONTRIBUTING.md", "docs/getting-started.md",
            "docs/compatibility.md", "docs/dishwasher-control.md", "docs/ev-charging.md",
            "docs/troubleshooting.md", "docs/dashboard.md", "docs/onboarding-acceptance.md",
            "docs/architecture.md", "docs/native-orchestration-migration.md",
        ):
            path = ROOT / relative
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
                parsed = urlsplit(link)
                if parsed.scheme or not parsed.path:
                    continue
                target = path.parent / unquote(parsed.path)
                with self.subTest(document=relative, link=link):
                    self.assertTrue(target.is_file(), target)
                    if parsed.fragment and target.suffix == ".md":
                        headings = re.findall(r"^#+ (.+)$", target.read_text(), re.MULTILINE)
                        anchors = {re.sub(r"[^\w -]", "", title.lower()).replace(" ", "-")
                                   for title in headings}
                        self.assertIn(parsed.fragment, anchors)


if __name__ == "__main__":
    unittest.main()
