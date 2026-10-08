import json
import re
import struct
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "load_optimizer"
sys.path.insert(0, str(INTEGRATION_ROOT))

from legacy.app_runtime import (
    PUBLISHED_ENTITY_CACHE,
    bootstrap_program_models,
    bool_option,
    compact_profile_data,
    current_tariff_period,
    datetime_from_entity_state,
    instance_config,
    instance_configs,
    load_state,
    load_options,
    mark_interrupted_captures,
    normalise_profile,
    normalise_program,
    normalise_program_policy,
    parse_instances_yaml,
    normalise_instances_yaml,
    public_program_summary,
    publish_cost_entities,
    publish_entity,
    profile_energy_kwh,
    profile_sample,
    program_catalogue,
    publish_restart_safety,
    publish_schedule_entities,
    publish_execution_entities,
    green_windows_from_entity,
    program_summary,
    publish_status,
    publish_restart_warning,
    refresh_publish_cache,
    special_price_window,
    repair_learning_quality,
    runtime_health,
    save_state,
    save_state_if_changed,
    reset_configured_instances,
    reset_request_status,
    resolve_program_policies,
    running_instances,
    schedule_advice,
    blocked_windows_from_entity,
    tariff_entity_diagnostic,
    tariff_periods_from_entity,
    tariff_state_from_entity,
    update_instance,
    update_program_model,
)


class VersionTests(unittest.TestCase):
    def test_integration_runtime_version_matches_manifest(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (root / "custom_components/load_optimizer/manifest.json").read_text()
        )
        runtime = (root / "custom_components/load_optimizer/legacy/app_runtime.py").read_text()
        match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', runtime, re.MULTILINE)

        self.assertIsNotNone(match)
        self.assertEqual(manifest["version"], match.group(1))

    def test_legacy_addon_packaging_is_retired(self):
        root = Path(__file__).resolve().parents[1]

        for path in (
            root / "repository.yaml",
            root / "load_optimizer/config.yaml",
            root / "load_optimizer/Dockerfile",
            root / "load_optimizer/run.sh",
            root / "load_optimizer/app",
        ):
            self.assertFalse(path.exists(), f"Legacy add-on artifact still present: {path}")

    def test_tests_import_the_packaged_integration_runtime(self):
        runtime = Path(sys.modules["legacy.app_runtime"].__file__).resolve()
        root = Path(__file__).resolve().parents[1]

        self.assertEqual(
            runtime,
            root / "custom_components/load_optimizer/legacy/app_runtime.py",
        )

    def test_native_legacy_entity_handover_preserves_entity_ids(self):
        root = Path(__file__).resolve().parents[1]
        sensor_source = (root / "custom_components/load_optimizer/sensor.py").read_text()
        runtime_source = (root / "custom_components/load_optimizer/legacy_runtime.py").read_text()

        self.assertIn("self.entity_id = entity_id", sensor_source)
        self.assertIn('entity_id.replace(\'.\', \'_\')', sensor_source)
        self.assertIn('"legacy_entities": result.entities', (
            root / "custom_components/load_optimizer/coordinator.py"
        ).read_text())
        publish_method = runtime_source.split("def _publish_entity", 1)[1].split("def _api_request", 1)[0]
        self.assertIn("self.published_entities[entity_id]", publish_method)
        self.assertNotIn("states.async_set", publish_method)

    def test_recovery_is_native_and_legacy_watchdog_is_retired(self):
        root = Path(__file__).resolve().parents[1]
        services = (root / "custom_components/load_optimizer/services.yaml").read_text()

        self.assertFalse(
            (root / "homeassistant/packages/load_optimizer_recovery_watchdog.yaml").exists()
        )
        self.assertFalse(
            (root / "homeassistant/packages/load_optimizer_recovery_watchdog.md").exists()
        )
        self.assertIn("recover:", services)

    def test_hacs_brand_and_optional_dashboard_are_packaged(self):
        root = Path(__file__).resolve().parents[1]
        icon = root / "custom_components/load_optimizer/brand/icon.png"
        dashboard = root / "custom_components/load_optimizer/dashboard.yaml"

        self.assertTrue(icon.exists())
        with icon.open("rb") as file_handle:
            self.assertEqual(file_handle.read(8), b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", file_handle.read(16)[8:16]), (256, 256))
        dashboard_text = dashboard.read_text()
        self.assertIn("sensor.load_optimizer_runtime_status", dashboard_text)
        self.assertIn("sensor.load_optimizer_1_total_runs", dashboard_text)
        self.assertIn("sensor.load_optimizer_1_tariff_horizon", dashboard_text)
        self.assertIn("switch.load_optimizer_1_auto_mode_enabled", dashboard_text)
        self.assertIn("button.load_optimizer_1_request_now", dashboard_text)
        self.assertIn("sensor.load_optimizer_1_orchestration_status", dashboard_text)
        self.assertIn("Automation Capabilities", dashboard_text)
        self.assertNotIn("custom:", dashboard_text)

    def test_full_dashboard_uses_tariff_time_not_browser_day(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            "homeassistant/dashboards/full/load_optimizer_dashboard.yaml",
        ):
            dashboard = (root / relative_path).read_text()
            self.assertIn("tariff_timezone", dashboard)
            self.assertIn("Intl.DateTimeFormat", dashboard)
            self.assertNotIn("datetimeUTC: false", dashboard)
            self.assertNotIn("binary_sensor.octopus_tomorrow_rates_available", dashboard)
            self.assertNotIn("start: day", dashboard)
            self.assertIn("graph_span: 24h", dashboard)
            self.assertIn("graph_span: 48h", dashboard)
            self.assertIn("&octopus_price_chart", dashboard)
            self.assertIn("<<: *octopus_price_chart", dashboard)
            self.assertIn('state: "24h"', dashboard)
            self.assertIn('state: "48h"', dashboard)
            self.assertIn(
                "sensor.load_optimizer_ofgem_price_cap_benchmark", dashboard
            )
            self.assertIn("Ofgem default-tariff benchmark", dashboard)
            self.assertIn("effective_from_utc", dashboard)
            self.assertIn("title: Automation Capabilities", dashboard)

    def test_options_flow_uses_home_assistant_config_entry_property(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "custom_components/load_optimizer/config_flow.py").read_text()

        self.assertIn("return LoadOptimizerOptionsFlow()", source)
        self.assertNotIn("self.config_entry = config_entry", source)

    def test_options_flow_separates_general_and_optional_dishwasher_settings(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "custom_components/load_optimizer/config_flow.py").read_text()
        translations = json.loads(
            (root / "custom_components/load_optimizer/translations/en.json").read_text()
        )

        for step in (
            "appliances_tariff",
            "optimisation",
            "publishing",
            "price_cap",
            "dishwasher_control",
        ):
            self.assertIn(f'async_step_{step}', source)
            self.assertIn(step, translations["options"]["step"])
        self.assertIn("self.config_entry.options, **user_input", source)
        self.assertIn(
            "Dishwasher control (optional)",
            translations["options"]["step"]["dishwasher_control"]["title"],
        )

    def test_price_cap_region_is_configurable(self):
        root = Path(__file__).resolve().parents[1]
        constants = (root / "custom_components/load_optimizer/const.py").read_text()
        config_flow = (root / "custom_components/load_optimizer/config_flow.py").read_text()

        self.assertIn('CONF_PRICE_CAP_REGION = "price_cap_region"', constants)
        self.assertIn('"North Western England"', constants)
        self.assertIn("_price_cap_schema", config_flow)

    def test_global_legacy_sensors_stay_on_hub_device(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "custom_components/load_optimizer/sensor.py").read_text()
        self.assertIn("if candidate_instance_id in legacy_instances", source)

    def test_child_devices_use_registered_hub_device_id(self):
        root = Path(__file__).resolve().parents[1]
        sensor = (root / "custom_components/load_optimizer/sensor.py").read_text()
        orchestration = (
            root / "custom_components/load_optimizer/orchestration_entity.py"
        ).read_text()

        for source in (sensor, orchestration):
            self.assertIn('"via_device_id": hub.id', source)
            self.assertIn("async_get_device_by_identifier", source)
            self.assertIn("(DOMAIN, entry.entry_id), entry.entry_id", source)
            self.assertNotIn("via_device=(DOMAIN", source)

    def test_only_empty_integration_devices_can_be_removed(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "custom_components/load_optimizer/__init__.py").read_text()
        self.assertIn("async_remove_config_entry_device", source)
        self.assertIn("include_disabled_entities=True", source)

    def test_orchestration_migration_is_non_destructive(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "custom_components/load_optimizer/orchestration_migration.py"
        ).read_text()
        integration = (root / "custom_components/load_optimizer/__init__.py").read_text()
        self.assertIn('"safe_to_remove_package": False', source)
        self.assertNotIn("automation.turn_off", source)
        self.assertNotIn("homeassistant.restart", source)
        self.assertIn("prepare_orchestration_migration", integration)

    def test_native_orchestration_platforms_are_complete(self):
        root = Path(__file__).resolve().parents[1]
        constants = (root / "custom_components/load_optimizer/const.py").read_text()

        platforms = re.search(r"PLATFORMS = \[(.*?)\]", constants, re.DOTALL)
        self.assertIsNotNone(platforms)
        for platform in re.findall(r'"([a-z_]+)"', platforms.group(1)):
            self.assertTrue(
                (root / f"custom_components/load_optimizer/{platform}.py").exists(),
                platform,
            )

    def test_native_orchestration_keeps_package_as_reversible_handover(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "custom_components/load_optimizer/orchestration.py").read_text()

        self.assertIn('"automation",\n                "turn_off"', source)
        self.assertIn('"automation",\n                "turn_on"', source)
        self.assertNotIn("os.remove", source)
        self.assertNotIn("Path.unlink", source)
        self.assertIn("door_not_opened_since_last_cycle", source)
        self.assertIn("confidence_threshold", source)
        self.assertIn("maximum_runs_per_window_reached", source)
        self.assertIn("and existing_automations", source)

    def test_native_orchestration_replaces_package_controls(self):
        root = Path(__file__).resolve().parents[1]
        expected_platforms = {
            "button": ("request_now", "cancel_schedule", "recalculate_now"),
            "switch": ("auto_mode_enabled", "auto_negative_price_enabled"),
            "select": ("override_program",),
            "datetime": ("special_price_window_start", "special_price_window_end"),
            "number": ("special_price_window_price",),
            "text": ("special_price_window_label",),
        }
        for platform, controls in expected_platforms.items():
            source = (
                root / f"custom_components/load_optimizer/{platform}.py"
            ).read_text()
            for control in controls:
                self.assertIn(control, source, f"{platform}: {control}")

        sensors = (root / "custom_components/load_optimizer/sensor.py").read_text()
        for status in (
            "orchestration_status",
            "overnight_readiness",
            "remote_activation",
            "data_freshness",
            "automatic_plan_resilience",
            "negative_price_readiness",
        ):
            self.assertIn(status, sensors)

        integration = (root / "custom_components/load_optimizer/__init__.py").read_text()
        self.assertIn("_async_migrate_native_status_entities", integration)
        self.assertIn("new_unique_id=unique_id", integration)
        self.assertIn('existing.platform == "template"', integration)
        self.assertIn('current_state.state == "unavailable"', integration)
        self.assertIn("hass.states.async_remove(entity_id)", integration)
        self.assertIn("_async_claim_native_status_entity_ids", integration)
        self.assertIn("new_entity_id=target_entity_id", integration)
        self.assertIn("entity_id not in NATIVE_STATUS_ENTITY_IDS", sensors)

    def test_retired_package_status_entity_is_removed(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (root / "custom_components/load_optimizer/legacy/app_runtime.py").read_text()
        integration = (root / "custom_components/load_optimizer/__init__.py").read_text()

        self.assertNotIn("publish_automation_package_status", runtime)
        self.assertIn("sensor.load_optimizer_1_automation_package_status", integration)

    def test_native_orchestration_confirms_cycle_end_and_relaxes_only_for_cooldown(
        self,
    ):
        root = Path(__file__).resolve().parents[1]
        source = (root / "custom_components/load_optimizer/orchestration.py").read_text()

        self.assertIn('"last_result": "completed"', source)
        self.assertIn('"last_reason": "cycle_state_returned_to_idle"', source)
        self.assertNotIn("ended_unconfirmed", source)
        self.assertIn('"cooldown_rotation_active" in selection_factors', source)
        self.assertIn("COOLDOWN_CONFIDENCE_FLOOR = 20", source)
        self.assertIn("confidence_relaxed_for_cooldown_rotation", source)

    def test_passive_appliances_do_not_publish_execution_controls(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (
            root / "custom_components/load_optimizer/legacy/app_runtime.py"
        ).read_text()
        integration = (
            root / "custom_components/load_optimizer/__init__.py"
        ).read_text()

        self.assertIn('if instance_id == "1":\n        publish_execution_entities', runtime)
        self.assertIn("OBSOLETE_CONTROL_ENTITY", integration)
        self.assertIn("entity_registry.async_remove", integration)

    def test_retired_greener_nights_calendar_is_ignored(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "custom_components/load_optimizer/legacy_runtime.py"
        ).read_text()

        self.assertIn('RETIRED_GREEN_WINDOW_SUFFIX = "_greener_nights"', source)
        self.assertIn('config[CONF_GREEN_WINDOW_ENTITY] = ""', source)
        self.assertIn('POWER_DOWN_SUFFIX = "_octoplus_power_down"', source)
        self.assertIn("self.hass.states.get(power_down)", source)
        self.assertIn("for config in configs:", source)
        self.assertIn("self._normalise_calendar_entities(config)", source)

    def test_retired_orchestration_packages_are_not_distributed(self):
        root = Path(__file__).resolve().parents[1]
        for name in (
            "load_optimizer_dishwasher_automation.yaml",
            "load_optimizer_1_bosch_helper_values.yaml",
        ):
            self.assertFalse((root / "homeassistant/packages" / name).exists())


class StatusHeartbeatTests(unittest.TestCase):
    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.datetime")
    def test_heartbeat_refreshes_only_after_interval(self, datetime_mock, publish_mock):
        first = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
        datetime_mock.now.side_effect = [first, first + timedelta(minutes=4), first + timedelta(minutes=5)]

        with patch("legacy.app_runtime.LAST_HEARTBEAT_AT", None):
            publish_status("token", 1)
            publish_status("token", 1)
            publish_status("token", 1)

        heartbeats = [call.args[3]["last_heartbeat"] for call in publish_mock.call_args_list]
        self.assertEqual(heartbeats, [first.isoformat(), first.isoformat(), (first + timedelta(minutes=5)).isoformat()])


class RuntimeHealthTests(unittest.TestCase):
    def test_publish_cache_is_forced_to_refresh_periodically(self):
        cache = {"sensor.example": "payload"}
        with (
            patch("legacy.app_runtime.PUBLISHED_ENTITY_CACHE", cache),
            patch("legacy.app_runtime.LAST_FULL_REPUBLISH_AT", None),
        ):
            self.assertTrue(refresh_publish_cache(100))
            cache["sensor.example"] = "new-payload"
            self.assertFalse(refresh_publish_cache(999))
            self.assertIn("sensor.example", cache)
            self.assertTrue(refresh_publish_cache(1000))
            self.assertEqual(cache, {})

    def test_runtime_health_fails_when_scan_completion_is_stale(self):
        now = datetime(2026, 8, 17, 12, 10, tzinfo=timezone.utc)
        with (
            patch("legacy.app_runtime.RUNTIME_STARTED_AT", now - timedelta(minutes=10)),
            patch("legacy.app_runtime.LAST_SCAN_STARTED_AT", now - timedelta(minutes=9)),
            patch("legacy.app_runtime.LAST_SCAN_COMPLETED_AT", now - timedelta(minutes=8)),
            patch("legacy.app_runtime.SCAN_HEALTH_TIMEOUT_SECONDS", 210),
        ):
            healthy, payload = runtime_health(now)

        self.assertFalse(healthy)
        self.assertEqual(payload["status"], "stalled")
        self.assertEqual(payload["scan_age_seconds"], 480)

    def test_runtime_health_allows_recent_scan_completion(self):
        now = datetime(2026, 8, 17, 12, 10, tzinfo=timezone.utc)
        with (
            patch("legacy.app_runtime.RUNTIME_STARTED_AT", now - timedelta(minutes=10)),
            patch("legacy.app_runtime.LAST_SCAN_STARTED_AT", now - timedelta(seconds=70)),
            patch("legacy.app_runtime.LAST_SCAN_COMPLETED_AT", now - timedelta(seconds=60)),
            patch("legacy.app_runtime.SCAN_HEALTH_TIMEOUT_SECONDS", 210),
        ):
            healthy, payload = runtime_health(now)

        self.assertTrue(healthy)
        self.assertEqual(payload["status"], "ok")


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

    def test_corrupt_state_restores_last_good_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            backup_path = path.with_suffix(".json.bak")
            expected = {
                "schema_version": 1,
                "instances": {"1": {"name": "Dishwasher 1"}},
            }
            backup_path.write_text(json.dumps(expected), encoding="utf-8")
            path.write_text("{not-json", encoding="utf-8")

            self.assertEqual(load_state(path), expected)
            self.assertFalse(path.exists())
            self.assertEqual(len(list(Path(directory).glob("state.json.corrupt-*"))), 1)

    def test_corrupt_state_is_quarantined_before_empty_state_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{not-json", encoding="utf-8")

            self.assertEqual(load_state(path), {"schema_version": 1, "instances": {}})
            self.assertFalse(path.exists())
            self.assertEqual(len(list(Path(directory).glob("state.json.corrupt-*"))), 1)

    def test_save_state_refreshes_last_good_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            first = {"schema_version": 1, "instances": {"1": {"runs": 1}}}
            second = {"schema_version": 1, "instances": {"1": {"runs": 2}}}

            save_state(first, path)
            save_state(second, path)

            self.assertEqual(json.loads(path.read_text()), second)
            self.assertEqual(json.loads(path.with_suffix(".json.bak").read_text()), first)

    @patch("legacy.app_runtime.save_state")
    def test_state_is_saved_only_when_signature_changes(self, save_state_mock):
        data = {"schema_version": 1, "instances": {"1": {"runs": 1}}}

        signature = save_state_if_changed(data, None)
        signature = save_state_if_changed(data, signature)
        data["instances"]["1"]["runs"] = 2
        save_state_if_changed(data, signature)

        self.assertEqual(save_state_mock.call_count, 2)


class DateTimeParsingTests(unittest.TestCase):
    def test_naive_input_datetime_uses_configured_timezone(self):
        parsed = datetime_from_entity_state(
            {"state": "2026-07-14 06:00:00"},
            naive_timezone="Europe/London",
        )

        self.assertEqual(parsed, datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc))

    def test_timezone_aware_input_datetime_keeps_own_offset(self):
        parsed = datetime_from_entity_state(
            {"state": "2026-07-14T06:00:00+00:00"},
            naive_timezone="Europe/London",
        )

        self.assertEqual(parsed, datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc))


class SpecialPriceWindowTests(unittest.TestCase):
    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
    def test_scheduled_window_uses_local_helper_times_and_publishes_provenance(self, source, publish):
        states = {
            "input_boolean.load_optimizer_special_price_window_enabled": {"state": "on"},
            "input_datetime.load_optimizer_special_price_window_start": {"state": "2026-09-13 13:00:00"},
            "input_datetime.load_optimizer_special_price_window_end": {"state": "2026-09-13 14:00:00"},
            "input_number.load_optimizer_special_price_window_price": {"state": "0"},
            "input_text.load_optimizer_special_price_window_label": {"state": "Octopus free hour"},
        }
        source.side_effect = lambda _token, entity_id: states.get(entity_id)

        result = special_price_window(
            "token",
            timezone_name="Europe/London",
            reference_utc=datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(result["start"], "2026-09-13T12:00:00+00:00")
        self.assertEqual(result["price_p_per_kwh"], 0)
        self.assertEqual(result["source"], "manual_special_price_window")
        self.assertEqual(publish.call_args.args[1], "sensor.load_optimizer_special_price_window")


class CurrentTariffPeriodTests(unittest.TestCase):
    def test_current_tariff_period_returns_period_containing_reference_time(self):
        periods = [
            {
                "start": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
                "end": datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
                "price_p_per_kwh": 10.0,
            },
            {
                "start": datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
                "end": datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
                "price_p_per_kwh": 12.5,
            },
        ]

        self.assertEqual(
            current_tariff_period(periods, datetime(2026, 1, 1, 0, 45, tzinfo=timezone.utc)),
            periods[1],
        )

    def test_current_tariff_period_returns_none_when_reference_is_outside_periods(self):
        periods = [{
            "start": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
            "price_p_per_kwh": 10.0,
        }]

        self.assertIsNone(
            current_tariff_period(periods, datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)),
        )


class PublishingTests(unittest.TestCase):
    def tearDown(self):
        PUBLISHED_ENTITY_CACHE.clear()

    @patch("legacy.app_runtime.api_request")
    def test_publish_entity_skips_unchanged_payloads(self, api_request):
        api_request.return_value = {"state": "ready"}

        publish_entity("token", "sensor.test_storage", "ready", {"friendly_name": "Storage Test"})
        publish_entity("token", "sensor.test_storage", "ready", {"friendly_name": "Storage Test"})
        publish_entity("token", "sensor.test_storage", "changed", {"friendly_name": "Storage Test"})

        self.assertEqual(api_request.call_count, 2)

    @patch("legacy.app_runtime.api_request")
    def test_cost_entities_publish_current_energy_price(self, api_request):
        api_request.return_value = {"state": "ready"}

        publish_cost_entities("token", "sensor.load_optimizer_1", "Dishwasher 1", {
            "status": "ready",
            "program": "Eco",
            "start": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            "finish": datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
            "total_cost_pence": 12.0,
            "cost_if_started_now_pence": 15.0,
            "potential_saving_pence": 3.0,
            "confidence": 20,
            "energy_kwh": 1.0,
            "energy_cost_pence": 12.0,
            "current_price_p_per_kwh": 17.456,
            "current_price_start": "2026-01-01T00:00:00+00:00",
            "current_price_end": "2026-01-01T00:30:00+00:00",
        })

        current_price = next(
            call for call in api_request.call_args_list
            if call.args[1] == "/states/sensor.load_optimizer_1_current_energy_price"
        )
        payload = current_price.args[2]
        self.assertEqual(payload["state"], "17.46")
        self.assertEqual(payload["attributes"]["unit_of_measurement"], "p/kWh")
        self.assertEqual(payload["attributes"]["current_price_p_per_kwh"], 17.46)
        self.assertEqual(payload["attributes"]["current_price_start"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(payload["attributes"]["current_price_end"], "2026-01-01T00:30:00+00:00")

    @patch("legacy.app_runtime.api_request")
    def test_cost_entities_publish_green_window_context(self, api_request):
        api_request.return_value = {"state": "ready"}

        publish_cost_entities("token", "sensor.load_optimizer_1", "Dishwasher 1", {
            "status": "ready",
            "program": "Eco",
            "start": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            "finish": datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
            "total_cost_pence": 12.0,
            "cost_if_started_now_pence": 15.0,
            "potential_saving_pence": 3.0,
            "confidence": 20,
            "energy_kwh": 1.0,
            "energy_cost_pence": 12.0,
            "green_window_entity": "calendar.greener_nights",
            "green_window_count": 1,
            "green_window_candidate_count": 2,
            "blocked_window_entity": "calendar.saving_sessions",
            "blocked_window_count": 1,
            "blocked_window_candidate_count": 3,
            "greenest_comparison": {
                "program": "Eco",
                "start": "2026-01-01T00:00:00+00:00",
                "finish": "2026-01-01T00:30:00+00:00",
                "cost_pence": 12.0,
                "green_window_overlap_percent": 100.0,
            },
        })

        cost_status = next(
            call for call in api_request.call_args_list
            if call.args[1] == "/states/sensor.load_optimizer_1_cost_status"
        )
        attributes = cost_status.args[2]["attributes"]
        self.assertEqual(attributes["green_window_entity"], "calendar.greener_nights")
        self.assertEqual(attributes["green_window_count"], 1)
        self.assertEqual(attributes["green_window_candidate_count"], 2)
        self.assertEqual(attributes["blocked_window_entity"], "calendar.saving_sessions")
        self.assertEqual(attributes["blocked_window_count"], 1)
        self.assertEqual(attributes["blocked_window_candidate_count"], 3)

    @patch("legacy.app_runtime.api_request")
    def test_intent_recommendations_are_blocked_while_cycle_is_running(self, api_request):
        api_request.return_value = {"state": "ready"}
        start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        publish_cost_entities(
            "token",
            "sensor.load_optimizer_1",
            "Dishwasher 1",
            {
                "status": "ready",
                "program": "Quick65",
                "start": start,
                "finish": start + timedelta(minutes=45),
                "total_cost_pence": -4.2,
                "cost_if_started_now_pence": -4.0,
                "potential_saving_pence": 0.2,
                "confidence": 90,
                "negative_price_recommendation": {
                    "status": "ready",
                    "program": "Quick45",
                    "start": start.isoformat(),
                    "finish": (start + timedelta(minutes=30)).isoformat(),
                    "cost_pence": -2.9,
                    "ready_to_start": True,
                    "reason": "best_negative_price_energy_intensity",
                },
            },
            cycle_running=True,
            active_cycle_start="2026-01-01T11:45:00+00:00",
        )

        negative_recommendation = next(
            call for call in api_request.call_args_list
            if call.args[1] == "/states/sensor.load_optimizer_1_negative_price_recommendation"
        )
        payload = negative_recommendation.args[2]
        self.assertEqual(payload["state"], "cycle_running")
        self.assertEqual(payload["attributes"]["status"], "cycle_running")
        self.assertEqual(payload["attributes"]["reason"], "cycle_already_running")
        self.assertEqual(payload["attributes"]["program"], "Quick45")
        self.assertFalse(payload["attributes"]["ready_to_start"])
        self.assertTrue(payload["attributes"]["blocked_by_active_capture"])


class ConfigurationTests(unittest.TestCase):
    def test_bool_option_accepts_common_string_values(self):
        self.assertTrue(bool_option("true"))
        self.assertTrue(bool_option("on"))
        self.assertFalse(bool_option("false", True))
        self.assertFalse(bool_option("0", True))
        self.assertTrue(bool_option("", True))

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
        self.assertFalse(config["publish_diagnostics"])
        self.assertTrue(config["publish_profile_data"])
        self.assertTrue(config["publish_cost_forecast"])
        self.assertEqual(config["green_window_entity"], "")
        self.assertEqual(config["blocked_window_entity"], "")

    def test_instance_config_parses_storage_publish_options(self):
        config = instance_config("1", {
            "publish_diagnostics": "true",
            "publish_profile_data": "false",
            "publish_cost_forecast": "off",
        })

        self.assertTrue(config["publish_diagnostics"])
        self.assertFalse(config["publish_profile_data"])
        self.assertFalse(config["publish_cost_forecast"])

    def test_instance_config_supports_green_window_override(self):
        config = instance_config("1", {
            "green_window_entity": "calendar.global_green",
            "instance_1_green_window_entity": "calendar.appliance_green",
        })

        self.assertEqual(config["green_window_entity"], "calendar.appliance_green")

    def test_instance_config_supports_blocked_window_override(self):
        config = instance_config("1", {
            "blocked_window_entity": "calendar.global_block",
            "instance_1_blocked_window_entity": "calendar.appliance_block",
        })

        self.assertEqual(config["blocked_window_entity"], "calendar.appliance_block")

    @patch("legacy.app_runtime.api_request")
    @patch("legacy.app_runtime.source_state")
    def test_blocked_window_entity_parses_octoplus_saving_session_events(self, source_state, api_request):
        api_request.return_value = None
        source_state.return_value = {
            "entity_id": "event.octopus_energy_saving_session_events",
            "state": "2026-07-24T15:33:24.759+00:00",
            "attributes": {
                "joined_events": [
                    {
                        "id": 4512,
                        "start": "2026-07-09T20:00:00+01:00",
                        "end": "2026-07-09T21:00:00+01:00",
                        "octopoints_per_kwh": 137,
                    },
                    {
                        "id": 4710,
                        "start": "2026-07-24T18:00:00+01:00",
                        "end": "2026-07-24T19:00:00+01:00",
                        "duration_in_minutes": 60,
                        "rewarded_octopoints": None,
                        "octopoints_per_kwh": 96,
                    },
                ],
            },
        }
        start = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)

        windows, diagnostics = blocked_windows_from_entity(
            "token",
            "event.octopus_energy_saving_session_events",
            start=start,
            end=end,
        )

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["start"], datetime(2026, 7, 24, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(windows[0]["end"], datetime(2026, 7, 24, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(windows[0]["summary"], "4710")
        self.assertEqual(windows[0]["metadata"]["id"], 4710)
        self.assertEqual(diagnostics["event_list_counts"]["joined_events"], 2)
        self.assertEqual(diagnostics["windows"], 1)

    @patch("legacy.app_runtime.api_request")
    @patch("legacy.app_runtime.source_state")
    def test_blocked_window_entity_parses_octoplus_power_down_events(self, source_state, api_request):
        source_state.return_value = {
            "entity_id": "event.octopus_energy_power_down_events",
            "state": "2026-08-17T12:00:00+00:00",
            "attributes": {
                "joined_events": [{
                    "id": 42,
                    "start": "2026-08-17T18:00:00+00:00",
                    "end": "2026-08-17T19:00:00+00:00",
                    "duration_in_minutes": 60,
                }],
            },
        }

        windows, diagnostic = blocked_windows_from_entity(
            "token",
            "event.octopus_energy_power_down_events",
            start=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["metadata"]["id"], 42)
        self.assertEqual(diagnostic["event_list_counts"], {"joined_events": 1})
        api_request.assert_not_called()

    @patch("legacy.app_runtime.api_request")
    @patch("legacy.app_runtime.source_state")
    def test_green_window_entity_merges_multiple_window_entities(self, source_state, api_request):
        api_request.return_value = []

        def state_for(_token, entity_id):
            return {
                "calendar.green": {
                    "entity_id": "calendar.green",
                    "state": "off",
                    "attributes": {
                        "start_time": "2026-07-24T23:00:00+01:00",
                        "end_time": "2026-07-25T06:00:00+01:00",
                        "greenness_score": 48,
                    },
                },
                "event.saving_sessions": {
                    "entity_id": "event.saving_sessions",
                    "state": "2026-07-24T15:33:24.759+00:00",
                    "attributes": {
                        "available_events": [{
                            "id": 4710,
                            "start": "2026-07-24T18:00:00+01:00",
                            "end": "2026-07-24T19:00:00+01:00",
                        }],
                    },
                },
            }.get(entity_id)

        source_state.side_effect = state_for
        start = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)

        windows, diagnostics = green_windows_from_entity(
            "token",
            "calendar.green, event.saving_sessions",
            start=start,
            end=end,
        )

        self.assertEqual(len(windows), 2)
        self.assertEqual(diagnostics["source"], "multiple_entities")
        self.assertEqual(len(diagnostics["entities"]), 2)
        self.assertEqual(diagnostics["windows"], 2)
        self.assertEqual([item["entity_id"] for item in diagnostics["entities"]], [
            "calendar.green",
            "event.saving_sessions",
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

    @patch("legacy.app_runtime.api_request")
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

    @patch("legacy.app_runtime.api_request")
    def test_restart_safety_blocks_when_capture_is_active(self, api_request):
        publish_restart_safety("token", [{
            "instance_id": "2",
            "name": "Washing Machine 1",
            "cycle_start": "2026-01-01T00:00:00+00:00",
        }])

        api_request.assert_called_once()
        self.assertEqual(api_request.call_args.args[1], "/states/sensor.load_optimizer_restart_safety")
        self.assertEqual(api_request.call_args.args[2]["state"], "blocked")
        self.assertTrue(api_request.call_args.args[2]["attributes"]["restart_blocked"])
        self.assertEqual(api_request.call_args.args[2]["attributes"]["active_capture_count"], 1)

    @patch("legacy.app_runtime.api_request")
    def test_restart_safety_reports_safe_when_no_capture_is_active(self, api_request):
        publish_restart_safety("token", [])

        api_request.assert_called_once()
        self.assertEqual(api_request.call_args.args[2]["state"], "safe")
        self.assertFalse(api_request.call_args.args[2]["attributes"]["restart_blocked"])

    def test_options_are_loaded_from_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"instance_1_program_policies": [{"program": "Eco"}]}))
            self.assertEqual(load_options(path)["instance_1_program_policies"][0]["program"], "Eco")

    @patch("legacy.app_runtime.render_template")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.render_template")
    @patch("legacy.app_runtime.source_state")
    def test_tariff_state_keeps_direct_rate_attributes(self, source_state, render_template):
        source_state.return_value = {
            "entity_id": "event.rates",
            "state": "2026-07-06T00:00:00+00:00",
            "attributes": {"rates": [{"value_inc_vat": 0.241}]},
        }

        state = tariff_state_from_entity("token", "event.rates")

        self.assertEqual(state["attributes"]["rates"][0]["value_inc_vat"], 0.241)
        render_template.assert_not_called()

    @patch("legacy.app_runtime.render_template")
    @patch("legacy.app_runtime.source_state")
    def test_tariff_state_keeps_direct_tuple_rate_attributes(self, source_state, render_template):
        source_state.return_value = {
            "entity_id": "event.rates",
            "state": "2026-07-06T00:00:00+00:00",
            "attributes": {"rates": ({"value_inc_vat": 0.241},)},
        }

        state = tariff_state_from_entity("token", "event.rates")

        self.assertEqual(state["attributes"]["rates"][0]["value_inc_vat"], 0.241)
        render_template.assert_not_called()

    def test_tariff_periods_accept_tuple_rate_attributes(self):
        periods = tariff_periods_from_entity(
            {
                "entity_id": "event.rates",
                "state": "2026-07-06T00:00:00+00:00",
                "attributes": {
                    "rates": (
                        {
                            "start": "2026-07-06T00:00:00+01:00",
                            "end": "2026-07-06T00:30:00+01:00",
                            "value_inc_vat": 0.241,
                        },
                    )
                },
            },
            reference_utc=datetime(2026, 7, 5, 23, 0, tzinfo=timezone.utc),
            timezone_name="Europe/London",
            price_unit="gbp_per_kwh",
        )

        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]["price_p_per_kwh"], 24.1)

    def test_tariff_periods_accept_tuple_of_read_only_mapping_attributes(self):
        periods = tariff_periods_from_entity(
            {
                "entity_id": "event.rates",
                "state": "2026-09-29T00:00:00+00:00",
                "attributes": {
                    "rates": (
                        MappingProxyType({
                            "start": "2026-09-29T00:00:00+01:00",
                            "end": "2026-09-29T00:30:00+01:00",
                            "value_inc_vat": 0.30744,
                        }),
                    )
                },
            },
            reference_utc=datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc),
            timezone_name="Europe/London",
            price_unit="gbp_per_kwh",
        )

        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0]["price_p_per_kwh"], 30.744)

    def test_tariff_periods_accept_home_assistant_datetime_attributes(self):
        periods = tariff_periods_from_entity(
            {
                "entity_id": "event.rates",
                "attributes": {
                    "rates": (
                        MappingProxyType({
                            "start": datetime(2026, 9, 29, 0, 0, tzinfo=timezone(timedelta(hours=1))),
                            "end": datetime(2026, 9, 29, 0, 30, tzinfo=timezone(timedelta(hours=1))),
                            "value_inc_vat": 0.30744,
                        }),
                    )
                },
            },
            reference_utc=datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc),
            timezone_name="Europe/London",
            price_unit="gbp_per_kwh",
        )

        self.assertEqual(periods[0]["start"], datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(periods[0]["end"], datetime(2026, 9, 28, 23, 30, tzinfo=timezone.utc))
        self.assertEqual(periods[0]["price_p_per_kwh"], 30.744)

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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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
            "publish_diagnostics": True,
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
    def test_bosch_ready_finishes_cycle_without_waiting_for_power_debounce(self, source, _publish):
        self.config.update(state_sensor="sensor.test_operation", finish_delay=5)
        source.side_effect = lambda _token, entity_id: {
            "sensor.test_power": {"state": "450"},
            "sensor.test_energy": {"state": "4.2"},
            "sensor.test_program": {"state": "Eco"},
            "sensor.test_operation": {"state": "BSH.Common.EnumType.OperationState.Ready"},
        }.get(entity_id)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        database = {"schema_version": 1, "instances": {"1": {
            "cycle_start": start.isoformat(), "start_energy": 3.5,
            "peak_power": 1200, "samples": 2,
            "profile": [
                {"offset_seconds": 0, "power_w": 1200},
                {"offset_seconds": 1800, "power_w": 800},
            ],
            "below_threshold": 0,
            "program": "Eco",
        }}}

        finish = start + timedelta(minutes=60)
        update_instance("token", database, self.config, finish)

        instance = database["instances"]["1"]
        self.assertNotIn("cycle_start", instance)
        self.assertEqual(instance["runs"], 1)
        self.assertEqual(instance["last_cycle"]["finish"], finish.isoformat())
        self.assertEqual(instance["last_cycle"]["completion_signal"], "bosch_operation_ready")

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.source_state")
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

    def test_public_program_summary_excludes_large_internal_fields(self):
        summary = {
            "program": "Eco",
            "runs": 3,
            "confidence": 60,
            "representative_profile_w": [1, 2, 3],
            "recent_cycles": [{"finish": "2026-01-01T12:00:00+00:00"}],
        }

        public = public_program_summary(summary)

        self.assertEqual(public["program"], "Eco")
        self.assertEqual(public["runs"], 3)
        self.assertEqual(public["confidence"], 60)
        self.assertNotIn("representative_profile_w", public)
        self.assertNotIn("recent_cycles", public)

    def test_compact_profile_data_exposes_chart_ready_points(self):
        instance = {}
        cycle = self.cycle(60, 1.0, 1000)
        update_program_model(instance, cycle)

        payload = compact_profile_data(instance["program_models"], cycle)

        self.assertEqual(payload["point_format"], ["offset_minutes", "power_w"])
        self.assertEqual(payload["program_profiles"][0]["program"], "Eco")
        self.assertEqual(payload["program_profiles"][0]["points"][0], [0.0, 0.0])
        self.assertEqual(payload["program_profiles"][0]["points"][-1], [60.0, 1000.0])
        self.assertEqual(payload["last_cycle"]["program"], "Eco")
        self.assertEqual(payload["last_cycle"]["points"], [[0.0, 0.0], [60.0, 1000.0]])

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
            "minimum_hours_between_runs": 6,
            "maximum_runs_per_window": 2,
            "negative_price_priority": 80,
            "estimated_overhead_cost_pence": 12.5,
        }])

        self.assertEqual(policies[0]["classification"], "preferred")
        self.assertTrue(policies[0]["allow_normal_recommendation"])
        self.assertEqual(policies[0]["minimum_hours_between_runs"], 6)
        self.assertEqual(policies[0]["maximum_runs_per_window"], 2)
        self.assertEqual(policies[0]["negative_price_priority"], 80)
        self.assertEqual(policies[0]["estimated_overhead_cost_pence"], 12.5)
        self.assertEqual(policies[0]["fixed_cost_pence"], 12.5)
        self.assertEqual(policies[0]["non_energy_cost_pence"], 12.5)

    def test_policy_calculates_true_non_energy_costs(self):
        policies = resolve_program_policies({"Eco": {"runs": 2}}, [{
            "program": "Eco",
            "classification": "preferred",
            "fixed_cost_pence": 14,
            "water_litres": 10,
            "water_cost_pence_per_litre": 0.25,
            "wear_cost_pence": 3,
        }])

        self.assertEqual(policies[0]["fixed_cost_pence"], 14)
        self.assertEqual(policies[0]["water_litres"], 10)
        self.assertEqual(policies[0]["water_cost_pence_per_litre"], 0.25)
        self.assertEqual(policies[0]["water_cost_pence"], 2.5)
        self.assertEqual(policies[0]["wear_cost_pence"], 3)
        self.assertEqual(policies[0]["non_energy_cost_pence"], 19.5)

    def test_configured_unlearned_policy_is_visible_in_catalogue(self):
        policies = resolve_program_policies({"Quick65": {"runs": 2}}, [
            {"program": "Quick65", "classification": "preferred", "allow_normal_recommendation": True},
            {"program": "MachineCare", "classification": "maintenance", "allow_negative_price_run": True},
        ])

        catalogue = program_catalogue({"Quick65": {"runs": 2}}, policies)
        by_program = {item["program"]: item for item in catalogue}

        self.assertEqual(by_program["Quick65"]["status"], "learned_configured")
        self.assertEqual(by_program["MachineCare"]["status"], "configured_unlearned")
        self.assertEqual(by_program["MachineCare"]["runs"], 0)
        self.assertTrue(by_program["MachineCare"]["allow_negative_price_run"])

    def test_learned_unconfigured_program_is_visible_for_review(self):
        policies = resolve_program_policies({"Auto2": {"runs": 1}}, [])

        catalogue = program_catalogue({"Auto2": {"runs": 1}}, policies)

        self.assertEqual(catalogue[0]["program"], "Auto2")
        self.assertEqual(catalogue[0]["status"], "learned_unconfigured")
        self.assertFalse(catalogue[0]["allow_normal_recommendation"])
        self.assertFalse(catalogue[0]["allow_negative_price_run"])

    def test_minimal_policy_uses_safe_optional_defaults(self):
        policy = normalise_program_policy({
            "program": "PreRinse",
            "classification": "alternative",
        })

        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["preference_rank"], 50)
        self.assertFalse(policy["allow_normal_recommendation"])
        self.assertFalse(policy["allow_negative_price_run"])
        self.assertEqual(policy["minimum_days_between_runs"], 0)
        self.assertEqual(policy["minimum_hours_between_runs"], 0)
        self.assertEqual(policy["maximum_runs_per_window"], 0)
        self.assertEqual(policy["negative_price_priority"], 50)
        self.assertEqual(policy["non_energy_cost_pence"], 0)

    def test_days_cooldown_backfills_hours_for_backwards_compatibility(self):
        policy = normalise_program_policy({
            "program": "MachineCare",
            "classification": "maintenance",
            "minimum_days_between_runs": 2,
        })

        self.assertEqual(policy["minimum_days_between_runs"], 2)
        self.assertEqual(policy["minimum_hours_between_runs"], 48)

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
  schedule_latest_finish_entity: input_datetime.dishwasher_deadline
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
        self.assertEqual(configs[1]["schedule_latest_finish_entity"], "input_datetime.dishwasher_deadline")
        self.assertEqual(configs[1]["cost_forecast_interval"], 30)
        self.assertEqual(configs[1]["program_policies"][0]["program"], "Default")
        self.assertTrue(configs[1]["program_policies"][0]["allow_normal_recommendation"])

    def test_instances_yaml_accepts_json_list(self):
        parsed = parse_instances_yaml('[{"id": "4", "name": "EV 1", "power_sensor": "sensor.ev_power"}]')

        self.assertEqual(parsed[0]["id"], "4")
        self.assertEqual(parsed[0]["name"], "EV 1")

    def test_instances_yaml_accepts_indented_paste(self):
        parsed = parse_instances_yaml("""
          - id: 1
            name: Dishwasher 1
            power_sensor: sensor.dishwasher_power
          - id: 2
            name: Washing Machine 1
            power_sensor: sensor.washer_power
""")

        self.assertEqual([item["id"] for item in parsed], [1, 2])
        self.assertEqual(parsed[1]["power_sensor"], "sensor.washer_power")

    def test_instances_yaml_extracts_full_addon_options_paste(self):
        raw = """
log_level: info
log_history: 25
scan_interval: 60
instances_yaml: |
  - id: "1"
    name: Dishwasher 1
    power_sensor: sensor.dishwasher_power
  - id: "2"
    name: Washing Machine 1
    power_sensor: sensor.washer_power
tariff_entities: >-
  event.current_day_rates,event.next_day_rates
"""

        self.assertIn("sensor.washer_power", normalise_instances_yaml(raw))
        parsed = parse_instances_yaml(raw)

        self.assertEqual([item["id"] for item in parsed], ["1", "2"])
        self.assertEqual(parsed[0]["name"], "Dishwasher 1")

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

    def test_running_cycle_blocks_schedule_automation(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        advice = schedule_advice({
            "status": "ready",
            "program": "Quick65",
            "start": now,
            "confidence": 90,
            "total_cost_pence": -4.2,
        }, {
            "schedule_confidence_threshold": 20,
            "schedule_start_tolerance_minutes": 5,
        }, now, cycle_running=True, active_cycle_start="2026-01-01T11:30:00+00:00")

        self.assertEqual(advice["status"], "cycle_running")
        self.assertFalse(advice["good_to_start"])
        self.assertFalse(advice["automation_ready"])
        self.assertEqual(advice["reason"], "cycle_already_running")
        self.assertTrue(advice["blocked_by_active_capture"])
        self.assertEqual(advice["active_cycle_start"], "2026-01-01T11:30:00+00:00")

    @patch("legacy.app_runtime.publish_entity")
    def test_schedule_publishes_recommended_finish_entity(self, publish_entity):
        publish_schedule_entities("token", "sensor.load_optimizer_1", "Dishwasher 1", {
            "status": "ready",
            "program": "Quick65",
            "recommended_start": "2026-01-01T12:00:00+00:00",
            "recommended_finish": "2026-01-01T12:45:00+00:00",
            "good_to_start": True,
            "estimated_cost_pence": 12.345,
        })

        published = {call.args[1]: call.args for call in publish_entity.call_args_list}
        self.assertIn("sensor.load_optimizer_1_recommended_finish", published)
        self.assertEqual(
            published["sensor.load_optimizer_1_recommended_finish"][2],
            "2026-01-01T12:45:00+00:00",
        )
        self.assertEqual(
            published["sensor.load_optimizer_1_recommended_finish"][3]["device_class"],
            "timestamp",
        )

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.render_template")
    def test_execution_publishes_not_configured_when_helpers_are_absent(self, render_template, publish_entity):
        render_template.return_value = {
            "status": "unknown",
            "message": "unknown",
            "result": "unknown",
            "failure_reason": "unknown",
            "program": "unknown",
            "attempt": "unknown",
        }

        publish_execution_entities("token", "sensor.load_optimizer_1", "Dishwasher 1", "1")

        published = {call.args[1]: call.args for call in publish_entity.call_args_list}
        self.assertEqual(published["sensor.load_optimizer_1_execution_status"][2], "not_configured")
        self.assertEqual(published["sensor.load_optimizer_1_last_start_attempt"][2], "unknown")

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.render_template")
    def test_execution_publishes_start_attempt_helpers(self, render_template, publish_entity):
        render_template.return_value = {
            "status": "failed",
            "message": "Dishwasher start failed for QuickD.",
            "result": "failed",
            "failure_reason": "not_running_after_start key=Dishcare.Dishwasher.Program.QuickD",
            "reason_code": "not_running_after_start",
            "reason_detail": "No running state after button and API attempts.",
            "decision_snapshot": "queued=12:00 latest=12:00 delta_min=0",
            "execution_event": "outcome=failed",
            "program": "QuickD",
            "attempt": "2026-01-01 12:00:00",
        }

        publish_execution_entities("token", "sensor.load_optimizer_1", "Dishwasher 1", "1")

        published = {call.args[1]: call.args for call in publish_entity.call_args_list}
        status_args = published["sensor.load_optimizer_1_execution_status"]
        self.assertEqual(status_args[2], "failed")
        self.assertEqual(status_args[3]["last_start_program"], "QuickD")
        self.assertEqual(
            status_args[3]["last_start_failure_reason"],
            "not_running_after_start key=Dishcare.Dishwasher.Program.QuickD",
        )
        self.assertEqual(status_args[3]["last_start_reason_code"], "not_running_after_start")
        self.assertEqual(
            published["sensor.load_optimizer_1_last_start_reason_detail"][2],
            "No running state after button and API attempts.",
        )
        self.assertEqual(
            published["sensor.load_optimizer_1_last_start_decision_snapshot"][2],
            "queued=12:00 latest=12:00 delta_min=0",
        )

    @patch("legacy.app_runtime.publish_entity")
    @patch("legacy.app_runtime.render_template")
    def test_cancelled_execution_is_published_as_aborted(self, render_template, publish_entity):
        render_template.return_value = {
            "status": "cancelled",
            "result": "cancelled",
            "reason_code": "recommended_start_changed",
            "reason_detail": "Queued start changed by 1,150 minutes.",
            "program": "Eco50",
            "attempt": "2026-08-25 11:02:00",
            "cycle_state": "idle",
        }

        publish_execution_entities("token", "sensor.load_optimizer_1", "Dishwasher 1", "1")

        published = {call.args[1]: call.args for call in publish_entity.call_args_list}
        self.assertEqual(published["sensor.load_optimizer_1_execution_lifecycle"][2], "aborted")
        self.assertEqual(
            published["sensor.load_optimizer_1_last_start_reason_code"][2],
            "recommended_start_changed",
        )


if __name__ == "__main__":
    unittest.main()
